"""PROTOTYPE ONLY - ask a YouTube video itself, with timestamps (round 11, slice Q; DESIGN.md section 18.Q; amendment
A-017, Proposed). Off unless MVP_VIDEO_ASK=1.

The bot reads titles, descriptions and captions, never what is said in a video. When a question about a pick already
shown is not answered by its text ("what did that video say about the settings to use"), today's honest line stays,
and, with this setting on and a YouTube pick, one line offers to ask the video itself. "ask the video" (or "ask the
video what ...", "ask video 2 ...") then sends ONE request to Google's Gemini API: the video's public link
(https://www.youtube.com/watch?v=<id>, Gemini's documented YouTube-URL input, `file_data.file_uri`) and the person's
question. Nothing else goes: no title, description, channel or caption (YouTube API Data stays out of the prompt).

What is kept: the answer's points and their timestamps, the video id, and the ledger row (model, tokens, cost). Never a
transcript, audio, video or frame: Google fetches the video, this computer never does.

Code, not the model, decides everything that matters:
  - YouTube items only (Instagram has no such route); one video per call; public only (Google refuses the rest, said
    plainly);
  - caps before the call: a length cap (MVP_VIDEO_ASK_MAX_MIN, default 20: a longer or unknown length is clipped to its
    first minutes, which is all Google bills), a per-person daily count (MVP_VIDEO_ASK_PER_DAY, default 5), and a
    worst-case cost estimate checked against the person's daily cap and the total cap;
  - the answer: each point's time must parse and lie inside the video (its known length, and the clip); a point that
    names another video or a link, or reads like an instruction ("email everyone", "add this to your rules"), is left
    out and counted; at most 5 points, each at most 40 words;
  - what the video says is data, never instructions: the answer is only ever sent as text. It is never read by the
    interpreter, never starts a rule, an email, a to-do or any action, and leaves nothing waiting for a yes.

The first time a person asks, the bot says what leaves this computer and waits for "ask the video" again.
"""
import json
import os
import re
from datetime import datetime, timedelta

from . import config

PROMPT_VERSION = "video_ask_v1"
PURPOSE = "mvp_video_ask"
OFFER_MINUTES = 30
MAX_POINTS = 5
MAX_WORDS = 40
MAX_OUT = 800
# Gemini 3 at low media resolution: about 70 tokens a frame at 1 frame a second, plus 32 audio tokens a second
# ("Video understanding" and "Media resolution", Gemini API docs, read 19 Nov 2026). Estimated with room to spare.
VIDEO_TPS, AUDIO_TPS, TEXT_TOKENS = 100, 32, 1500
_PROMPT = {}

SCHEMA = {"type": "object",
          "properties": {"answered": {"type": "boolean"},
                         "points": {"type": "array",
                                    "items": {"type": "object",
                                              "properties": {"at": {"type": "string"}, "says": {"type": "string"}},
                                              "required": ["at", "says"]}}},
          "required": ["answered", "points"]}


# ---------- settings ----------
def on():
    return os.environ.get("MVP_VIDEO_ASK", "0") == "1"


def model():
    return os.environ.get("MVP_VIDEO_ASK_MODEL") or "gemini-3.1-flash-lite"


def _int_env(name, default):
    try:
        return max(0, int(os.environ.get(name) or default))
    except ValueError:
        return default


def max_seconds():
    return _int_env("MVP_VIDEO_ASK_MAX_MIN", 20) * 60


def per_day():
    return _int_env("MVP_VIDEO_ASK_PER_DAY", 5)


def prompt():
    if "t" not in _PROMPT:
        with open(os.path.join(config.HERE, "prompts", f"{PROMPT_VERSION}.md"), encoding="utf-8") as f:
            _PROMPT["t"] = f.read()
    return _PROMPT["t"]


# ---------- what the person reads ----------
LABEL = "From the video (not checked against its text)"
OFFER = ("I can ask the video itself: say \"ask the video\". Its link and your question go to Google's Gemini, which "
         "watches it; I keep only the answer.")
# round 11 fix, B (V2): "yes" (or "ok", "go ahead", or "ask the video" again) is the go; the question is kept
FIRST_NOTE = ("Before I ask: asking a video sends its link and your question to Google (Gemini), which watches the "
              "video and answers. I keep only that answer and its times, never the video or what it says in full. "
              "Say \"yes\" to go ahead.")
ASK_WHAT = "What should I ask it? For example: \"ask the video what settings it uses\"."
WHICH = "Which video? Say \"ask video 2 <your question>\", by its number in my last message."
NO_VIDEO = "I haven't shown you a YouTube video to ask yet. Ask me for one first."
NOT_YOUTUBE = ("I can only ask YouTube videos. Instagram has no way for me to ask a post itself, so I go by its "
               "caption.")
NO_KEY = "Asking a video isn't set up on this bot yet."
PER_DAY_USED = "I've asked {n} videos for you today, the most I do in a day. I can ask again tomorrow."
DAILY_ROOM = ("Asking a video costs up to about {cents} cents, more than what's left of today's limit for you. I can "
              "ask tomorrow.")
TOTAL_ROOM = "The test budget is too low to ask a video right now. The founders need to raise it."
UNAVAILABLE = ("Google couldn't open that video (it may be private, unlisted, removed or blocked), so I couldn't ask "
               "it. Nothing was kept.")
BUSY = "Google's limit for asking videos is used up for now. Try again later."
FAILED = "Google didn't answer that one. Nothing was kept; try again in a bit."
REFUSED = "Google's model wouldn't answer about that video, so I have nothing from it. Nothing was kept."
NOT_SAID = "it doesn't seem to say anything about that."
NONE_KEPT = "nothing in the model's answer passed my checks, so I'm not passing it on."
CLIPPED = "It's {length} long, so I asked about its first {mins} minutes only."
CLIPPED_UNKNOWN = "I don't know its length, so I asked about its first {mins} minutes only."
KEEP = "A model at Google watched it for this; I keep only this answer."


def consent_note(store=None, h=None, now=None):
    """The sentence the consent message gains while the setting is on. Round 11 fix, B (V2): with `store`, a person
    who was shown it is remembered, so their first "ask the video" after agreeing asks at once."""
    if not on():
        return ""
    if store is not None and h:
        store.set_state(f"consent_video:{h}", (now or datetime.now().astimezone()).isoformat())
    # the merge of round 11's fixes (seam f): "ask them" sends up to 3 links, each with the question
    return (" If you ask me to ask a YouTube video itself, its link and your question go to Google (Gemini), up to 3 "
            "videos at once with \"ask them\"; I keep only the answers.")


def _seen(bot, person):
    """Round 11 fix, B (V2): the person was told what leaves this computer: an offer or the note was shown, or the
    consent they agreed to held the Google sentence."""
    h = person["handle"]
    return bool(bot.store.get_state(f"videoask_seen:{h}")
                or (person.get("consent_version") and bot.store.get_state(f"consent_video:{h}")))


# ---------- "what leaves this computer" (read always; the Gemini line only while the setting is on) ----------
LEAVES = re.compile(
    r"^\W*(?:(?:so|ok|okay|hey)[\s,]+)?(?:"
    r"what\s+(?:data\s+|info(?:rmation)?\s+|stuff\s+)?(?:leaves|goes\s+out\s+of|gets\s+sent\s+(?:out\s+)?(?:from|of)|"
    r"is\s+sent\s+(?:out\s+)?(?:from|of))\s+(?:this|my|the|your)\s+(?:computer|mac|machine|laptop|server)"
    r"|what\s+(?:do\s+you|does\s+the\s+bot)\s+send\s+(?:out\s+)?to\s+(?:google|openai|gemini|youtube|anyone|other\s+companies)"
    r"|where\s+does\s+my\s+data\s+go"
    r"|who\s+(?:else\s+)?(?:sees|gets)\s+my\s+data"
    r")\W*$", re.I)


def leaves_text():
    lines = ["What leaves this computer when I work for you:",
             "• OpenAI: your messages, the lines I keep about you, and the text of posts I consider (titles, captions, "
             "descriptions), to understand and answer you. Not used for training.",
             "• YouTube's official API: the ids of YouTube videos I show you (for their length and description) and, "
             "when you ask for new videos, search words from your message.",
             "• Emails, events and to-dos you ask for go only where you said."]
    if on():
        lines.append("• Asking a video: when you say \"ask the video\", its link and your question go to Google's "
                     "Gemini, which watches it; \"ask them\" sends up to 3 links, one at a time, each with your "
                     "question. I keep only the answers.")
    lines.append("Your library and my notes about you stay on this computer. \"delete my data\" removes them.")
    return "\n".join(lines)


# ---------- reading the message ----------
_ORD = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3}
ASK = re.compile(
    r"^\W*(?:(?:ok|okay|yes|yeah|sure|please|go\s+ahead(?:\s+and)?)[\s,.!]+)*(?:please\s+)?(?:can\s+you\s+)?"
    r"ask\s+(?:(?:the|that|this)\s+(?:(?P<ord>first|second|third|1st|2nd|3rd)\s+)?video|video\s+#?(?P<n>[1-9]))"
    r"(?:\s+(?:itself|directly|then|now|please))*"
    r"(?:(?:\s*[:,\-–]\s*|\s+)(?P<q>\S.*?))?\W*$", re.I | re.S)
_FILLER_Q = re.compile(r"^(?:again|too|for\s+me|please|pls|now|then|it|anyway)\W*$", re.I)


def read_ask(text):
    """(pick number or None, question or '') for an "ask the video" message, else None."""
    t = " ".join((text or "").split())
    if not t or len(t) > 400:
        return None
    m = ASK.match(t)
    if not m:
        return None
    n = int(m.group("n")) if m.group("n") else _ORD.get((m.group("ord") or "").lower())
    q = (m.group("q") or "").strip()
    if _FILLER_Q.match(q):
        q = ""
    return n, q


# ---------- round 11 fix, B: "ask that one" (R2, R8), "ask them" (V1), the go after the note (V2) ----------
ASK_ONE = re.compile(
    r"^\W*(?:(?:ok|okay|yes|yeah|sure|please|go\s+ahead(?:\s+and)?)[\s,.!]+)*(?:please\s+)?(?:can\s+you\s+)?"
    r"ask\s+(?:that|this)\s+one(?:\s+(?:instead|then|now|please|too))*"
    r"(?:(?:\s*[:,\-–]\s*|\s+)(?P<q>\S.*?))?\W*$", re.I | re.S)
_NUMW = {"2": 2, "two": 2, "both": 2, "3": 3, "three": 3}
ASK_MANY = re.compile(
    r"^\W*(?:(?:ok|okay|yes|yeah|sure|please|go\s+ahead(?:\s+and)?)[\s,.!]+)*(?:please\s+)?"
    r"(?:(?:can|could)\s+you\s+)?ask\s+(?:"
    r"(?:all\s+(?:of\s+)?)?(?:them|those|these)(?:\s+(?:videos|vids|ones))?(?:\s+(?P<k1>3|three|2|two))?"
    r"|all\s+(?P<k2>3|three|2|two)(?:\s+(?:of\s+them|videos|vids))?|(?P<k3>both)(?:\s+(?:of\s+them|videos|vids))?"
    r"|each\s+(?:of\s+them|one)|(?:all\s+)?the\s+(?:videos|vids)"
    r"|the\s+top\s+(?P<k4>3|three|2|two)(?:\s+(?:videos|vids|ones))?)"
    r"(?:\s+(?:themselves|directly|then|now|please|too|instead))*"
    r"(?:(?:\s*[:,\-–]\s*|\s+)(?P<q>\S.*?))?\W*$", re.I | re.S)
# the question after "ask them" reads as one ("ask them what lens they use"); "ask them for a refund" is not this read
_Q_START = re.compile(r"^(?:what|whats|what's|how|which|why|when|where|who|whether|if|about|does|do|did|is|are|was|"
                      r"were|can|could|should|would|will|any|anything|tell|explain|list|to\s+(?:tell|explain|list|say))\b",
                      re.I)
GO = re.compile(r"^\W*(?:yes|yeah|yep|yup|ok|okay|sure|go(?:\s+ahead)?|go\s+for\s+it|do\s+it|please(?:\s+do)?|"
                r"ask(?:\s+(?:it|them))?|yes\s+please|ok\s+go(?:\s+ahead)?|sounds\s+good|fine)(?:[\s,.!]+(?:please|go\s+ahead|"
                r"do\s+it))*\W*$", re.I)


def read_one(text):
    """The question (or '') of "ask that one ...", else None."""
    m = ASK_ONE.match(" ".join((text or "").split()))
    if not m:
        return None
    q = (m.group("q") or "").strip()
    return "" if _FILLER_Q.match(q) else q


def read_many(text):
    """(how many at most, question or '') for "ask them ...", "ask those videos ...", "ask the top 3 ...", else None."""
    t = " ".join((text or "").split())
    if not t or len(t) > 400:
        return None
    m = ASK_MANY.match(t)
    if not m:
        return None
    q = (m.group("q") or "").strip()
    if _FILLER_Q.match(q):
        q = ""
    if q and not _Q_START.match(q):
        return None
    k = next((m.group(g) for g in ("k1", "k2", "k3", "k4") if m.group(g)), None)
    return _NUMW.get((k or "3").lower(), 3), q
# ---------- end round 11 fix, B ----------


# ---------- youtube links and times ----------
_VID = re.compile(r"(?:[?&]v=|youtu\.be/|/shorts/|/live/|/embed/)([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])")


def video_id(it):
    if getattr(it, "platform", None) != "youtube":
        return None
    vid = getattr(it, "video_id", None)
    if vid and re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
        return vid
    m = _VID.search(getattr(it, "url", "") or "")
    return m.group(1) if m else None


def watch_url(vid, at=None):
    return f"https://www.youtube.com/watch?v={vid}" + (f"&t={int(at)}s" if at is not None else "")


_TS = re.compile(r"^\s*(?:(\d{1,2}):)?(\d{1,3}):([0-5]\d)\s*$")


def seconds(at):
    """'02:15' -> 135, '1:02:03' -> 3723; anything else None."""
    m = _TS.match(str(at or ""))
    if not m:
        return None
    h, mi, s = int(m.group(1) or 0), int(m.group(2)), int(m.group(3))
    if m.group(1) is not None and mi > 59:
        return None
    return h * 3600 + mi * 60 + s


def clock(s):
    h, rest = divmod(int(s), 3600)
    m, sec = divmod(rest, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


# ---------- the checks on each point ----------
OTHER_VIDEO = re.compile(r"https?://|www\.|youtu\.?be|\.com\b|watch\?v=|(?<!\w)@\w|"
                         r"\b(?:other|another|previous|next|last|earlier|later|separate|linked|older|newer|second|"
                         r"related|full|part\s+\d+\s+of\s+(?:my|this|the))\s+(?:video|videos|episode|upload)\b|"
                         r"\b(?:my|our|their|his|her)\s+(?:other\s+)?(?:channel|playlist|course|patreon)\b|"
                         r"\b(?:check\s+out|watch|see)\s+(?:my|our|their|the)\s+(?:video|channel|playlist)\b|"
                         r"\blink\s+(?:in|below)\b", re.I)
# words aimed at the person's accounts or at the bot, whoever says them (a video is data, never instructions)
ACTING = re.compile(
    r"\b(?:e-?mail|text|message|dm|forward)\s+(?:every\s*one|everybody|all|your|them|it|this|me|him|her|us)\b|"
    r"\bsend\s+(?:an?\s+)?(?:e-?mail|message|text|money|this|it|them|everyone)\b|"
    r"\b(?:add|put|save)\s+(?:this|it|that|these|them)\s+(?:to|in|into|on)\s+(?:your|my|the)\s+"
    r"(?:rules?|list|lists|to-?dos?|reminders?|calendar|notes?)\b|"
    r"\b(?:your|my|the\s+bot'?s?)\s+rules?\b|\b(?:new|a)\s+rule\b|\bremind\s+(?:you|me|them)\b|"
    r"\b(?:schedule|set\s+up)\s+(?:an?\s+)?(?:email|reminder|rule|send)\b|"
    r"\b(?:delete|erase|wipe)\s+(?:your|my|all)\b|\bunsubscribe\b|\bsubscribe\b|\bpassword\b|\bcredit\s+card\b|"
    r"\b(?:system\s+prompt|previous\s+instructions|as\s+an\s+ai|you\s+must\s+now|from\s+now\s+on)\b", re.I)


_TWORD = re.compile(r"[^\W_]+", re.UNICODE)


def _twords(s):
    return tuple(w.lower() for w in _TWORD.findall(s or ""))


def other_titles(view, it):
    """The round 11 check (DESIGN 18.X): the titles of the library's other YouTube videos, as word tuples (3 to 12
    words; a longer title by its first 8), so a point that names one ("<another title> covers this") is left out."""
    from .compose import display_title
    own = _twords(display_title(it))
    out = set()
    for x in view.items.values():
        if x.platform != "youtube" or x.id == it.id:
            continue
        w = _twords(x.first_line or x.caption)
        if len(w) > 12:
            w = w[:8]
        if len(w) >= 3 and sum(len(t) for t in w) >= 12 and w != own:
            out.add(w)
    return out


def _names_other(says, titles):
    if not titles:
        return False
    w = _twords(says)
    return any(w[i:i + n] in titles for n in range(3, 13) for i in range(0, max(0, len(w) - n) + 1))


def check_points(out, length_s, clip_s, titles=None):
    """(kept points [(seconds, text)], counts of what was left out by reason). The model's form is data: only its
    'at' and 'says' strings are read, as strings. `titles`: other videos' titles (other_titles), never named."""
    from .compose import ASSISTANT_NOTE
    pts = (out or {}).get("points") if isinstance(out, dict) else None
    kept, dropped = [], {"time": 0, "other": 0, "acting": 0, "empty": 0}
    end = min(x for x in (length_s, clip_s) if x) if (length_s or clip_s) else None
    for p in pts if isinstance(pts, list) else []:
        if len(kept) >= MAX_POINTS:
            break
        if not isinstance(p, dict) or not isinstance(p.get("says"), str):
            dropped["empty"] += 1
            continue
        says = " ".join(p["says"].split()).strip(" -•*")
        if not says:
            dropped["empty"] += 1
            continue
        s = seconds(p.get("at"))
        if s is None or (end is not None and s > end):
            dropped["time"] += 1
            continue
        if OTHER_VIDEO.search(says) or _names_other(says, titles):
            dropped["other"] += 1
            continue
        if ACTING.search(says) or ASSISTANT_NOTE.search(says):
            dropped["acting"] += 1
            continue
        words = says.split()
        if len(words) > MAX_WORDS:
            says = " ".join(words[:MAX_WORDS]).rstrip(",;:") + "…"
        says = says[:1].upper() + says[1:]   # round 11 fix, B (V3): each point starts with a capital, by code
        kept.append((s, says))
    kept.sort(key=lambda x: x[0])
    return kept, dropped


def answer_text(title, vid, kept, dropped, answered, clip_line=""):
    head = f"{LABEL}, \"{title}\":"
    lines = [head]
    if kept:
        for s, says in kept:
            lines.append(f"• {says} ({clock(s)}: {watch_url(vid, s)})")
    else:   # nothing that passed the checks: never a guess, the video's link to check
        lines = [f"{head} {NONE_KEPT if answered and any(dropped.values()) else NOT_SAID}", watch_url(vid)]
    left = []
    if dropped["time"]:
        left.append(f"{dropped['time']} with a time outside the video")
    if dropped["other"]:
        left.append(f"{dropped['other']} that pointed to another video or a link")
    if dropped["acting"]:
        left.append(f"{dropped['acting']} that read like an instruction, not an answer")
    if left:
        lines.append("I left out " + ", ".join(left) + ".")
    if clip_line:
        lines.append(clip_line)
    lines.append(KEEP)
    return "\n".join(lines)


# ---------- the call (the fake replaces call_model: tests/fakes/fake_gemini.py) ----------
def estimate_usd(secs, mdl=None):
    from . import llm
    p = llm.ai.prices().get(mdl or model()) or {}
    media = p.get("media_input_per_m", p.get("input_per_m", 0))
    audio = p.get("audio_input_per_m", p.get("input_per_m", 0))
    return round(secs * VIDEO_TPS / 1e6 * media + secs * AUDIO_TPS / 1e6 * audio
                 + TEXT_TOKENS / 1e6 * p.get("input_per_m", 0) + MAX_OUT / 1e6 * p.get("output_per_m", 0), 6)


def call_model(mdl, request, est_tokens, person):
    """One generateContent call through experiments/lib/ai.py (its price check, its Gemini budget guard, its ledger
    row with tokens by modality). Returns (parsed form or None, cost, raw text)."""
    from . import llm
    llm._tl.person, llm._tl.cost = person, 0.0
    try:
        out, _u, raw = llm.ai.gemini_youtube_json(mdl, request, est_tokens, purpose=PURPOSE,
                                                   prompt_version=PROMPT_VERSION)
        return out, llm._tl.cost, raw
    except Exception as e:
        if llm._cut_after_send(e) and not llm._tl.cost:
            # sent, but we stopped waiting: the worst case is written so both caps see it (as llm.chat_json does)
            llm._log({"provider": "gemini", "model": mdl, "purpose": PURPOSE, "prompt_version": PROMPT_VERSION,
                      "n": 1, "in_tokens": est_tokens, "out_tokens": MAX_OUT,
                      "cost_usd": estimate_usd(est_tokens / (VIDEO_TPS + AUDIO_TPS), mdl), "estimated": True,
                      "error": type(e).__name__})
        raise
    finally:
        llm._tl.person = None


def _http_code(e):
    import urllib.error
    return e.code if isinstance(e, urllib.error.HTTPError) else None


# ---------- the hook ----------
def _offer_state(bot, h, now):
    st = bot.store.get_state(f"videoask:{h}")
    if not st:
        return None
    try:
        if now - datetime.fromisoformat(st["at"]) > timedelta(minutes=OFFER_MINUTES):
            return None
    except (KeyError, ValueError, TypeError):
        return None
    return st


def offer(bot, person, last, n, question, msg, now):
    """After today's "I can't tell that from what X says" line for pick n: with the setting on and a YouTube pick, one
    more line offers to ask the video, and the pick and question are kept 30 minutes for "ask the video"."""
    from .render import Reply
    if not on() or not n or not last or not 1 <= n <= len(last.get("items") or []):
        return msg
    it = bot.view(person["library"]).get(last["items"][n - 1])
    line = offer_line(bot, person, it, question, now)
    return Reply.of(msg) + Reply([{"type": "text", "text": "\n" + line}]) if line else msg


def offer_line(bot, person, it, question, now):
    """The offer for one YouTube item with the setting on (else ""); the pick and the question are kept 30 minutes for
    "ask the video". The merge of round 11: also after the honest line of a details question ("what does it say about
    X" on a title-only video, followup._detail_answer)."""
    if not on() or it is None:
        return ""
    if not video_id(it):
        # round 11 fix, B (R2): an Instagram post can't be asked; the YouTube video the person watched on the same
        # topic, if there is one, is offered instead
        return also_watched(bot, person, question, now, item=it) if it.platform != "youtube" else ""
    h = person["handle"]
    bot.store.set_state(f"videoask:{h}", {"item_id": it.id, "question": " ".join(str(question or "").split())[:300],
                                          "at": now.isoformat()})
    bot.store.set_state(f"videoask_seen:{h}", now.isoformat())   # the offer says what leaves this computer
    return OFFER


# ---------- round 11 fix, B (R2, R8): the offer of a YouTube video the person watched on the topic in view ----------
ALSO = ("You also watched a YouTube video on this: \"{title}\" {url}\nSay \"ask that one\" and your question, and I'll "
        "ask it. Its link and your question go to Google's Gemini; I keep only the answer.")
ALL_INSTAGRAM = "Those are Instagram posts, and I can only ask YouTube videos: Instagram has no way for me to ask a post."


def topic_in_view(bot, h):
    """The topic of the answer in view: a history answer's topic or channel, else the request's words."""
    last = bot.store.last_answer(h) or {}
    goal = last.get("goal") or ""
    if goal.startswith("history:"):
        from . import history
        st = bot.store.get_state(history.STATE.format(h=h)) or {}
        q = (st.get("q") or {}) if st.get("run_id") == last.get("run_id") else {}
        return " ".join(q.get("topic") or []) or q.get("channel") or ""
    return (bot.store.get_state(f"lastspec:{h}") or {}).get("text") or goal


def _history_kind(bot, h):
    from . import history
    last = bot.store.last_answer(h) or {}
    st = bot.store.get_state(history.STATE.format(h=h)) or {}
    if not (last.get("goal") or "").startswith("history:") or st.get("run_id") != last.get("run_id"):
        return None
    return (st.get("q") or {}).get("kind")


def best_watched(bot, person, topic, now, latest=False, item=None):
    """The YouTube video the person watched that fits `topic` (else the Instagram `item` in view) best, the latest
    one with `latest`, or None. history.best_watched_video(bot, person, topic=None, item=None, latest=False,
    exclude=()) is fixer A's (round 11 fix, A); until the merge brings it, nothing is offered."""
    if not topic and item is None:
        return None
    try:
        from .history import best_watched_video
    except ImportError:
        return None
    try:
        it = best_watched_video(bot, person, topic=topic or None, item=item, latest=latest)
    except Exception:  # noqa: BLE001 - an offer never breaks the reply it is added to
        return None
    return it if it is not None and video_id(it) else None


def also_watched(bot, person, question, now, item=None):
    """The line offering the best-fitting YouTube video the person watched on the topic in view (or like the
    Instagram `item` in view), and the offer kept 30 minutes for "ask that one" / "ask the video"; or ""."""
    h = person["handle"]
    latest = _history_kind(bot, h) == "last"
    it = best_watched(bot, person, topic_in_view(bot, h), now, latest=latest, item=item)
    if it is None:
        return ""
    from .compose import display_title
    bot.store.set_state(f"videoask:{h}", {"item_id": it.id, "question": " ".join(str(question or "").split())[:300],
                                          "at": now.isoformat(), "also": True})
    bot.store.set_state(f"videoask_seen:{h}", now.isoformat())   # the line says what leaves this computer
    return ALSO.format(title=display_title(it), url=watch_url(video_id(it)))
# ---------- end round 11 fix, B ----------


def reads(bot, person, text, now):
    """The hook (DESIGN.md section 18.Q): "what leaves this computer" (always), "ask the video ..." (setting on only).
    Returns the reply's reference, or None when the message is not one of these."""
    t = " ".join((text or "").split())
    if LEAVES.match(t):
        bot.note(intent="what_leaves")
        return bot.send(person["handle"], leaves_text())
    if not on():
        return None
    got = read_ask(t)
    if got is None:
        # ---------- round 11 fix, B: "ask that one" after the offer of a watched video (R2, R8); "ask them" (V1)
        one = read_one(t)
        if one is not None and _offer_state(bot, person["handle"], now):
            bot.note(intent="video_ask")
            return ask(bot, person, None, one, now)
        many = read_many(t)
        if many is not None:   # only when the answer in view holds a video to ask (else the message goes on)
            return ask_many(bot, person, many[0], many[1], now)
        # ---------- end round 11 fix, B ----------
        return None
    bot.note(intent="video_ask")
    return ask(bot, person, got[0], got[1], now)


def ask(bot, person, n, question, now):
    h = person["handle"]
    st = _offer_state(bot, h, now)
    last = bot.store.last_answer(h)
    view = bot.view(person["library"])
    it = None
    if n:
        if not last or not 1 <= n <= len(last.get("items") or []):
            return bot.send(h, WHICH if last else NO_VIDEO)
        it = view.get(last["items"][n - 1])
    elif st:
        it = view.get(st["item_id"])
    elif last:
        shown = [x for x in (view.get(i) for i in last.get("items") or []) if x]
        yt = [x for x in shown if x.platform == "youtube"]
        if len(shown) == 1 or len(yt) == 1:
            it = yt[0] if yt else shown[0]
        elif len(yt) > 1:
            return bot.send(h, WHICH)
    # ---------- round 11 fix, B (R2, R8): an Instagram post, or a list of them, in view: say so plainly and offer the
    # YouTube video the person watched on that topic, when there is one ----------
    if it is None and last and on():
        shown = [x for x in (view.get(i) for i in last.get("items") or []) if x]
        if shown and not any(x.platform == "youtube" for x in shown):
            line = also_watched(bot, person, question, now)
            return bot.send(h, ALL_INSTAGRAM + ("\n" + line if line else ""))
    if it is not None and it.platform != "youtube" and on():
        line = also_watched(bot, person, question, now, item=it)
        if line:
            return bot.send(h, NOT_YOUTUBE + "\n" + line)
    # ---------- end round 11 fix, B ----------
    if it is None:
        return bot.send(h, NO_VIDEO)
    if it.platform != "youtube":
        return bot.send(h, NOT_YOUTUBE)
    if not question and st and st.get("item_id") == it.id:
        question = st.get("question") or ""
    if not question:
        bot.store.set_state(f"videoask:{h}", {"item_id": it.id, "question": "", "at": now.isoformat()})
        return bot.send(h, ASK_WHAT)
    if not _seen(bot, person):
        # the first time: what leaves this computer, then "yes" (round 11 fix, B, V2: the question is kept, and
        # "yes", "ok", "go ahead" or "ask the video" again is the go)
        bot.store.set_state(f"videoask:{h}", {"item_id": it.id, "question": question[:300], "at": now.isoformat()})
        bot.store.set_state(f"videoask_seen:{h}", now.isoformat())
        bot.store.set_state(f"videoask_go:{h}", {"item_id": it.id, "at": now.isoformat()})
        return bot.send(h, FIRST_NOTE)
    return run(bot, person, it, question, now)


# ---------- round 11 fix, B (V2): "yes" right after the note asks at once; any other message ends the note ----------
GO_MINUTES = 30


def take_go(store, h):
    """The open note's go, taken off as the next message arrives (answered by that message only)."""
    st = store.get_state(f"videoask_go:{h}")
    if st:
        store.set_state(f"videoask_go:{h}", None)
    return st or None


def go_answer(bot, person, text, now, go):
    """Hook 4c in _asked_reads: "yes" / "ok" / "go ahead" right after the first-time note: the kept question is
    asked. Any other message: None (handled as usual; "ask the video" again still works)."""
    if not go or not on() or not GO.match(" ".join((text or "").split())):
        return None
    try:
        if now - datetime.fromisoformat(go["at"]) > timedelta(minutes=GO_MINUTES):
            return None
    except (KeyError, TypeError, ValueError):
        return None
    h = person["handle"]
    view = bot.view(person["library"])
    bot.note(intent="video_ask")
    if go.get("many"):
        items = [x for x in (view.get(i) for i in go["many"]) if x is not None]
        return _run_many(bot, person, items, go.get("question") or "", go.get("nums") or [], now)
    st = _offer_state(bot, h, now) or {}
    it = view.get(go.get("item_id"))
    if it is None or st.get("item_id") != it.id or not st.get("question"):
        return None
    return run(bot, person, it, st["question"], now)
# ---------- end round 11 fix, B ----------


def _used_today(bot, person, now):
    from .actions import local_day_bounds
    start, end = local_day_bounds(now, person.get("timezone") or "America/New_York")
    return bot.store.actions_in(person["handle"], ["video.ask"], start, end)


def _log(bot, h, status, vid, now, **detail):
    bot.store.log_action(h, None, None, "video.ask", status, detail={"video_id": vid, **detail}, at=now)


def _ask_one(bot, person, it, question, now):
    """One video asked, with every check before the call (slice Q's, unchanged). Returns a dict: "line" (a plain
    line instead of an answer, nothing kept), "stop" (no other video can be asked now: a cap or the budget), or the
    answer's parts ("vid", "kept", "dropped", "answered", "clip_line", "title"). Round 11 fix, B: shared by one
    video's ask and "ask them" (V1), so both make the same checks, the same ledger row and the same action row."""
    from . import llm
    from .compose import display_title
    from .settings import secret
    from .ytinfo import minutes_text
    h = person["handle"]
    vid = video_id(it)
    if not vid:
        return {"line": UNAVAILABLE}
    if not secret("GEMINI_API_KEY"):
        return {"line": NO_KEY, "stop": True}
    if _used_today(bot, person, now) >= per_day():
        return {"line": PER_DAY_USED.format(n=per_day()), "stop": True}
    # the length: the library's, else YouTube's own (videos.list, cached 30 days)
    length = it.duration_s
    if not length:
        try:
            length = (bot._youtube().details([it], now).get(it.id) or {}).get("duration_s")
        except Exception:  # noqa: BLE001 - no length: the clip bounds the cost all the same
            length = None
    cap = max_seconds()
    clip = cap if (not length or length > cap) else None
    secs = min(length or cap, cap)
    est = estimate_usd(secs)
    libs = [p["library"] for p in bot.store.q("SELECT library FROM people")]
    if llm.spent_total(libs) + est + config.TOTAL_CAP_MARGIN_USD >= config.TOTAL_CAP_USD:
        return {"line": TOTAL_ROOM, "stop": True}
    if llm.spent_today(h, person["library"]) + est > config.DAILY_CAP_USD:
        return {"line": DAILY_ROOM.format(cents=max(1, round(est * 100))), "stop": True}
    from .llm import ai
    req = ai.youtube_video_request(prompt(), "Question: " + " ".join(question.split())[:300], watch_url(vid),
                                   end_s=clip, media_resolution="MEDIA_RESOLUTION_LOW", max_tokens=MAX_OUT,
                                   response_schema=SCHEMA, thinking_budget=0)
    try:
        out, cost, raw = call_model(model(), req, int(secs * (VIDEO_TPS + AUDIO_TPS) + TEXT_TOKENS), h)
    except Exception as e:  # noqa: BLE001 - every failure is said plainly; nothing is kept
        if llm.budget_stop(e):
            _log(bot, h, "skipped", vid, now, why="budget")
            return {"line": TOTAL_ROOM, "stop": True}
        code = _http_code(e)
        _log(bot, h, "failed", vid, now, why=f"http {code}" if code else type(e).__name__)
        return {"line": UNAVAILABLE if code in (400, 403, 404) else BUSY if code == 429 else FAILED,
                "stop": code == 429}
    bot.store.set_state(f"videoask:{h}", None)
    if out is None or not isinstance(out, dict):
        _log(bot, h, "done", vid, now, points=0, refused=True, cost_usd=round(cost or 0, 6))
        return {"line": REFUSED + f"\n{watch_url(vid)}", "refused": True, "vid": vid}
    try:
        titles = other_titles(bot.view(person["library"]), it)
    except Exception:  # noqa: BLE001 - the other checks still run
        titles = None
    kept, dropped = check_points(out, length, clip, titles)
    answered = out.get("answered") is True
    if not answered:   # "it doesn't say": any points beside it are not passed on
        kept, dropped = [], {k: 0 for k in dropped}
    clip_line = ""
    if clip:
        clip_line = (CLIPPED.format(length=minutes_text(length), mins=cap // 60) if length
                     else CLIPPED_UNKNOWN.format(mins=cap // 60))
    _log(bot, h, "done", vid, now, points=len(kept), dropped=sum(dropped.values()), answered=answered,
         cost_usd=round(cost or 0, 6))
    return {"vid": vid, "item_id": it.id, "kept": kept, "dropped": dropped, "answered": answered,
            "clip_line": clip_line, "title": display_title(it)}


def run(bot, person, it, question, now):
    h = person["handle"]
    r = _ask_one(bot, person, it, question, now)
    if "line" in r:
        return bot.send(h, r["line"])
    bot.store.set_state(f"videoans:{h}", {"video_id": r["vid"], "item_id": it.id, "model": model(),
                                          "points": [{"at": s, "says": x} for s, x in r["kept"]],
                                          "at": now.isoformat(), "after_run": _newest_run(bot, h)})
    return bot.send(h, answer_text(r["title"], r["vid"], r["kept"], r["dropped"], r["answered"], r["clip_line"]))


# ---------- round 11 fix, B (V1): "ask them": up to 3 YouTube videos of the answer in view, one question ----------
MANY_MAX = 3            # videos asked by one "ask them"
MANY_POINTS = 4         # points shown per video in that answer (all of them are kept for "email it to me")
MANY_CHARS = 3000       # the whole answer at most this long
MANY_MINUTES = 60       # "ask them" reads the summary's topic this long after it
ASK_THEM_WHAT = "What should I ask them? For example: \"ask them what settings they use\"."
MANY_NOTE = ("Before I ask: asking {these} sends their links and your question to Google (Gemini), which watches them "
             "and answers. I keep only those answers and their times, never the videos or what they say in full. Say "
             "\"yes\" to go ahead.")
MANY_START = "I'll ask {these}; their links and your question go to Google. I keep only the answers."
MANY_LABEL = "From the videos themselves (not checked against their text):"
MANY_KEEP = "A model at Google watched them for this; I keep only these answers."
MANY_STOPPED = "I stopped there. {line}"
MANY_MORE = "({n} more from this video in the email: say \"email it to me\".)"


def _these(n):
    return "this video" if n == 1 else f"these {n} videos"


def _many_in_view(bot, person, k):
    """([(number in the answer, item)], the answer in view) for its YouTube videos, the first k; ([], last) else."""
    h = person["handle"]
    last = bot.store.last_answer(h)
    if not last or not last.get("items"):
        return [], last
    view = bot.view(person["library"])
    out = []
    ids = last["items"]
    # the merge of round 11's fixes (seam b): a recall puts only its first video in view (for "what did it say" and
    # "ask the video"), but "ask them" asks the recall's own list, up to 3, numbered as the recall shows them
    from . import history
    st = bot.store.get_state(history.STATE.format(h=h)) or {}
    if st.get("recall") and st.get("run_id") == last.get("run_id") and st.get("ids"):
        ids = st["ids"]
    for n, iid in enumerate(ids, 1):
        it = view.get(iid)
        if it is not None and it.platform == "youtube" and video_id(it):
            out.append((n, it))
    return out[:k], last


def _default_question(bot, h, last, now):
    """The question of a summary just shown ("what do the videos i watched say about easing"): its topic."""
    st = bot.store.get_state(f"videomany:{h}") or {}
    if not st or not last or st.get("run_id") != last.get("run_id"):
        # the merge of round 11's fixes (seam b): after a recall or a history list, the topic of that answer
        from . import history
        topic = history.history_topic(bot, h, now)
        return f"What does it say about {topic}?" if topic else ""
    try:
        if now - datetime.fromisoformat(st["at"]) > timedelta(minutes=MANY_MINUTES):
            return ""
    except (KeyError, TypeError, ValueError):
        return ""
    return f"What does it say about {st['topic']}?" if st.get("topic") else ""


def ask_many(bot, person, k, question, now):
    """'ask them', 'ask those videos what ...', 'ask the top 3 ...': None when no answer in view holds a YouTube
    video (the message goes on as before), else the reply's reference."""
    h = person["handle"]
    pairs, last = _many_in_view(bot, person, min(k, MANY_MAX))
    view = bot.view(person["library"])
    shown = [x for x in (view.get(i) for i in (last or {}).get("items") or []) if x]
    if not pairs:
        if not shown:
            return None
        bot.note(intent="video_ask")
        line = also_watched(bot, person, question, now)
        return bot.send(h, ALL_INSTAGRAM + ("\n" + line if line else ""))
    bot.note(intent="video_ask")
    question = question or _default_question(bot, h, last, now)
    if not question:
        bot.store.set_state(f"videoask:{h}", {"item_id": pairs[0][1].id, "question": "", "at": now.isoformat()})
        return bot.send(h, ASK_THEM_WHAT if len(pairs) > 1 else ASK_WHAT)
    if len(pairs) == 1:   # one video: slice Q's own ask, its own answer
        return ask(bot, person, pairs[0][0], question, now)
    nums, items = [n for n, _ in pairs], [it for _, it in pairs]
    if not _seen(bot, person):
        bot.store.set_state(f"videoask_seen:{h}", now.isoformat())
        bot.store.set_state(f"videomany_seen:{h}", now.isoformat())
        bot.store.set_state(f"videoask_go:{h}", {"many": [it.id for it in items], "nums": nums,
                                                 "question": question[:300], "at": now.isoformat()})
        return bot.send(h, MANY_NOTE.format(these=_these(len(items))))
    return _run_many(bot, person, items, question, nums, now)


def _run_many(bot, person, items, question, nums, now):
    h = person["handle"]
    if not bot.store.get_state(f"videomany_seen:{h}"):   # the first time: what it will send, before it starts
        bot.store.set_state(f"videomany_seen:{h}", now.isoformat())
        bot.send(h, MANY_START.format(these=_these(len(items))))
    blocks, kept_all, stop = [], [], None
    for n, it in zip(nums or range(1, len(items) + 1), items):
        if stop is not None:
            break
        r = _ask_one(bot, person, it, question, now)
        from .compose import display_title
        head = f"Video {n}, \"{display_title(it)}\":"
        if r.get("stop"):
            stop = r["line"]
            break
        if "line" in r:   # this one failed or was refused: said plainly, the others still answer
            blocks.append(f"{head} {r['line']}" if not r.get("refused") else f"{head} {r['line']}")
            continue
        kept = r["kept"]
        lines = [head]
        if kept:
            for s, says in kept[:MANY_POINTS]:
                lines.append(f"• {says} ({clock(s)}: {watch_url(r['vid'], s)})")
            if len(kept) > MANY_POINTS:
                lines.append(MANY_MORE.format(n=len(kept) - MANY_POINTS))
        else:
            lines = [f"{head} {NONE_KEPT if r['answered'] and any(r['dropped'].values()) else NOT_SAID}",
                     watch_url(r["vid"])]
        left = sum(r["dropped"].values())
        if left:
            lines.append(f"I left out {left} that didn't pass my checks (a time outside the video, another video or a "
                         f"link, or an instruction).")
        if r["clip_line"]:
            lines.append(r["clip_line"])
        blocks.append("\n".join(lines))
        kept_all.append({"video_id": r["vid"], "item_id": it.id, "n": n,
                         "points": [{"at": s, "says": x} for s, x in kept]})
    if not blocks:   # nothing asked at all: the plain line of what stopped it
        return bot.send(h, stop or FAILED)
    body = [MANY_LABEL, ""] + ["\n\n".join(blocks)]
    if stop is not None:
        body += ["", MANY_STOPPED.format(line=stop)]
    body += ["", MANY_KEEP]
    text = "\n".join(body)
    if len(text) > MANY_CHARS:
        text = text[:MANY_CHARS].rsplit("\n", 1)[0] + "\n…\n" + MANY_KEEP
    if kept_all:
        bot.store.set_state(f"videoans:{h}", {"videos": kept_all, "model": model(), "at": now.isoformat(),
                                              "after_run": _newest_run(bot, h)})
    return bot.send(h, text)
# ---------- end round 11 fix, B (V1) ----------


# ---------- round 11 fix, B (V4): "email it to me" after a video's answer emails that answer ----------
def _newest_run(bot, h):
    """The newest run's id for this person (0 when none): a video answer is in view until a newer run is made."""
    row = bot.store.one("SELECT MAX(id) AS n FROM runs WHERE handle=?", (h,))
    return (row or {}).get("n") or 0


def answer_in_view(bot, h):
    """The video answer as an answer to email (kind "video": its title, points, timestamp links and the label),
    when it is the newest thing shown (no run since it), else None. Built by code from what slice Q keeps
    (`videoans`); nothing new is stored."""
    va = bot.store.get_state(f"videoans:{h}")
    if not va or "after_run" not in va or _newest_run(bot, h) != va["after_run"]:
        return None
    from .compose import display_title
    person = bot.store.person(h) or {}
    view = bot.view(person.get("library")) if person.get("library") else None

    def name(iid):
        it = view.get(iid) if view is not None else None
        return display_title(it) if it is not None else "the video"
    if va.get("videos"):
        lines, title = [MANY_LABEL], ""
        for v in va["videos"]:
            lines += ["", f"Video {v.get('n')}, \"{name(v.get('item_id'))}\":"]
            lines += [f"• {p['says']} ({clock(p['at'])}: {watch_url(v['video_id'], p['at'])})" for p in v["points"]]
            if not v["points"]:
                lines.append(NOT_SAID[:1].upper() + NOT_SAID[1:] + " " + watch_url(v["video_id"]))
        lines += ["", MANY_KEEP]
    else:
        title = name(va.get("item_id"))
        lines = [f"{LABEL}, \"{title}\":"]
        lines += [f"• {p['says']} ({clock(p['at'])}: {watch_url(va['video_id'], p['at'])})" for p in va["points"]]
        if not va["points"]:
            lines.append(NOT_SAID[:1].upper() + NOT_SAID[1:] + " " + watch_url(va["video_id"]))
        lines.append(KEEP)
    return {"run_id": None, "rule_id": None, "kind": "video", "goal": title or "your videos",
            "subject": f"From the video: {title}" if title else f"From your videos: {len(va['videos'])} answers",
            "parts": [{"type": "text", "text": "\n".join(lines)}], "picks": []}
# ---------- end round 11 fix, B (V4) ----------
