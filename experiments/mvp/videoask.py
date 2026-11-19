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
FIRST_NOTE = ("Before I ask: asking a video sends its link and your question to Google (Gemini), which watches the "
              "video and answers. I keep only that answer and its times, never the video or what it says in full. "
              "Say \"ask the video\" again to go ahead.")
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


def consent_note():
    """The sentence the consent message gains while the setting is on."""
    return (" If you ask me to ask a YouTube video itself, its link and your question go to Google (Gemini); I keep "
            "only its answer.") if on() else ""


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
                     "Gemini, which watches it. I keep only its answer.")
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


def check_points(out, length_s, clip_s):
    """(kept points [(seconds, text)], counts of what was left out by reason). The model's form is data: only its
    'at' and 'says' strings are read, as strings."""
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
        if OTHER_VIDEO.search(says):
            dropped["other"] += 1
            continue
        if ACTING.search(says) or ASSISTANT_NOTE.search(says):
            dropped["acting"] += 1
            continue
        words = says.split()
        if len(words) > MAX_WORDS:
            says = " ".join(words[:MAX_WORDS]).rstrip(",;:") + "…"
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
    if it is None or not video_id(it):
        return msg
    h = person["handle"]
    bot.store.set_state(f"videoask:{h}", {"item_id": it.id, "question": " ".join(str(question or "").split())[:300],
                                          "at": now.isoformat()})
    bot.store.set_state(f"videoask_seen:{h}", now.isoformat())   # the offer says what leaves this computer
    return Reply.of(msg) + Reply([{"type": "text", "text": "\n" + OFFER}])


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
    if it is None:
        return bot.send(h, NO_VIDEO)
    if it.platform != "youtube":
        return bot.send(h, NOT_YOUTUBE)
    if not question and st and st.get("item_id") == it.id:
        question = st.get("question") or ""
    if not question:
        bot.store.set_state(f"videoask:{h}", {"item_id": it.id, "question": "", "at": now.isoformat()})
        return bot.send(h, ASK_WHAT)
    if not bot.store.get_state(f"videoask_seen:{h}"):
        # the first time: what leaves this computer, then "ask the video" again
        bot.store.set_state(f"videoask:{h}", {"item_id": it.id, "question": question[:300], "at": now.isoformat()})
        bot.store.set_state(f"videoask_seen:{h}", now.isoformat())
        return bot.send(h, FIRST_NOTE)
    return run(bot, person, it, question, now)


def _used_today(bot, person, now):
    from .actions import local_day_bounds
    start, end = local_day_bounds(now, person.get("timezone") or "America/New_York")
    return bot.store.actions_in(person["handle"], ["video.ask"], start, end)


def _log(bot, h, status, vid, now, **detail):
    bot.store.log_action(h, None, None, "video.ask", status, detail={"video_id": vid, **detail}, at=now)


def run(bot, person, it, question, now):
    from . import llm
    from .compose import display_title
    from .settings import secret
    from .ytinfo import minutes_text
    h = person["handle"]
    vid = video_id(it)
    if not vid:
        return bot.send(h, UNAVAILABLE)
    if not secret("GEMINI_API_KEY"):
        return bot.send(h, NO_KEY)
    if _used_today(bot, person, now) >= per_day():
        return bot.send(h, PER_DAY_USED.format(n=per_day()))
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
        return bot.send(h, TOTAL_ROOM)
    if llm.spent_today(h, person["library"]) + est > config.DAILY_CAP_USD:
        return bot.send(h, DAILY_ROOM.format(cents=max(1, round(est * 100))))
    from .llm import ai
    req = ai.youtube_video_request(prompt(), "Question: " + " ".join(question.split())[:300], watch_url(vid),
                                   end_s=clip, media_resolution="MEDIA_RESOLUTION_LOW", max_tokens=MAX_OUT,
                                   response_schema=SCHEMA, thinking_budget=0)
    try:
        out, cost, raw = call_model(model(), req, int(secs * (VIDEO_TPS + AUDIO_TPS) + TEXT_TOKENS), h)
    except Exception as e:  # noqa: BLE001 - every failure is said plainly; nothing is kept
        if llm.budget_stop(e):
            _log(bot, h, "skipped", vid, now, why="budget")
            return bot.send(h, TOTAL_ROOM)
        code = _http_code(e)
        _log(bot, h, "failed", vid, now, why=f"http {code}" if code else type(e).__name__)
        return bot.send(h, UNAVAILABLE if code in (400, 403, 404) else BUSY if code == 429 else FAILED)
    bot.store.set_state(f"videoask:{h}", None)
    if out is None or not isinstance(out, dict):
        _log(bot, h, "done", vid, now, points=0, refused=True, cost_usd=round(cost or 0, 6))
        return bot.send(h, REFUSED + f"\n{watch_url(vid)}")
    kept, dropped = check_points(out, length, clip)
    answered = out.get("answered") is True
    if not answered:   # "it doesn't say": any points beside it are not passed on
        kept, dropped = [], {k: 0 for k in dropped}
    clip_line = ""
    if clip:
        clip_line = (CLIPPED.format(length=minutes_text(length), mins=cap // 60) if length
                     else CLIPPED_UNKNOWN.format(mins=cap // 60))
    title = display_title(it)
    _log(bot, h, "done", vid, now, points=len(kept), dropped=sum(dropped.values()), answered=answered,
         cost_usd=round(cost or 0, 6))
    bot.store.set_state(f"videoans:{h}", {"video_id": vid, "item_id": it.id, "model": model(),
                                          "points": [{"at": s, "says": x} for s, x in kept], "at": now.isoformat()})
    return bot.send(h, answer_text(title, vid, kept, dropped, answered, clip_line))
