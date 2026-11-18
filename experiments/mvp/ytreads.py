"""PROTOTYPE ONLY - the person's YouTube by Google's own API, and one-tap Instagram links (round 10, slice Y; DESIGN.md
section 17.Y; amendment A-015, Proposed).

Code reads, no model call:
  hook 5b `youtube_reads` (handler.answer_normally, after email_reads, before cancel_reads):
    "connect youtube", "disconnect youtube", "is youtube connected", "done" while a sign-in code is open;
    "unsubscribe (me) from (that|this|the) channel", "unsubscribe from <name>" (a channel of a YouTube pick in view or,
    once connected, one of the person's subscriptions; a name that is also a paid service in cancel_routes.json asks
    which one; "unsubscribe from netflix" still reaches the cancel helper), "unfollow / mute <creator>";
    "unsubscribe from channels I haven't watched since 2024" (only with a Takeout watch history whose newest record is
    under 120 days old, M-15; the whole numbered list, at most 50 a message); "put these in a playlist called X"
    (always a private playlist; only the library's own YouTube items; Instagram picks are counted, never placed);
    Watch Later and history links; the Instagram weekly-export link; "stop" while a rest-tomorrow is waiting.
  hook 4a `youtube_answer` (handler._asked_reads, after places.asked_reads; the next message only, 30 minutes):
    "yes" to one channel or a playlist; "unsubscribe N" where N must be the count shown; "keep 4, 9" (a new list with
    a new yes token); "next"; "no"; "the channel" / "the subscription"; "done" / "next" after an Instagram link.
  `undo` (handler._undo): re-subscribes what the last unsubscribe took (7 days) or takes the videos out of the playlist
  (24 hours), when that is newer than the person's last own write.
  `tick` (scheduler.tick): asks Google about an open sign-in code; runs a rest-tomorrow that is due; drops
  subscription lists older than 24 hours.

State (all named "...:<handle>", so "delete my data" removes them): ytdevice (the open sign-in code, 30 minutes),
ytsubs (the subscription list, 24 hours), ytask (a preview waiting for its answer), ytundo (what "undo" takes back),
ytrest (the rest of a list for tomorrow), igtap (the Instagram links still to send). `yt_units:<Pacific day>` counts
this project's YouTube units (no person in it). Titles YouTube returns are shown back only in the preview; nothing it
returns becomes a library item, and no caption, title or tool answer ever names a channel, a link or an action.
"""
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import connectors as C
from . import texts as T
from .actions import link as L
from .store import now_iso

ASK_OPEN = timedelta(minutes=30)
SUBS_KEEP = timedelta(hours=24)
UNDO_UNSUB = timedelta(days=7)
UNDO_PLAYLIST = timedelta(hours=24)
HISTORY_DAYS = 120          # M-15: a watch history older than this cannot say what was watched since
LIST_MAX = 50               # channels in one list (one yes)
UNSUB_PER_DAY = 50          # channels a person may be unsubscribed from in one local day
ADD_PER_DAY = 50            # videos a person may have added to playlists in one local day
_VID = re.compile(r"^[A-Za-z0-9_-]{11}$")


# ---------- words ----------
def _norm(text):
    t = " ".join((text or "").lower().replace("’", "'").replace("‘", "'").split())
    return re.sub(r"^[\s\"'“”]+|[\s\"'“”.!?]+$", "", t)


_PLEASE = r"(?:(?:please|pls|hey|ok(?:ay)?|so)[\s,]+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?"
_TAILS = r"(?:\s+(?:for\s+me|please|pls|now))*"
_YT = r"(?:youtube|yt|you\s?tube)"
CONNECT = re.compile(r"^" + _PLEASE + r"(?:connect|link|hook\s+up|set\s*up|sign\s+in\s+to|log\s*in\s+to)\s+(?:to\s+)?"
                     r"(?:my\s+|the\s+)?" + _YT + r"(?:\s+account)?" + _TAILS + r"$")
DISCONNECT = re.compile(r"^" + _PLEASE + r"(?:disconnect|unlink|stop\s+using|(?:log|sign)\s+(?:me\s+)?out\s+of)\s+"
                        r"(?:my\s+|the\s+)?" + _YT +
                        r"(?:\s+account)?" + _TAILS + r"$")
IS_CONNECTED = re.compile(r"^(?:is\s+(?:my\s+)?" + _YT + r"\s+connected|are\s+you\s+connected\s+to\s+(?:my\s+)?" + _YT +
                          r"|is\s+" + _YT + r"\s+(?:linked|set\s+up))$")
DEVICE_DONE = re.compile(r"^(?:(?:ok(?:ay)?|yes|yep|so)[\s,]+)?(?:done|i'?m\s+done|i\s+did\s+it|i'?ve\s+done\s+it|"
                         r"i\s+typed\s+it(?:\s+in)?|i\s+entered\s+(?:it|the\s+code)|i\s+allowed\s+it|allowed|"
                         r"i\s+(?:pressed|clicked|tapped)\s+allow|it'?s\s+done|connected)$")
_UNSUB = r"(?:unsubscribe|unsub)"
_THAT = r"(?:that|this|the)\s+(?:" + _YT + r"\s+)?(?:channel|youtuber|creator|guy|girl)"
UNSUB_THAT = re.compile(r"^" + _PLEASE + _UNSUB + r"(?:\s+me)?\s+from\s+" + _THAT + r"(?:\s+on\s+" + _YT + r")?" +
                        _TAILS + r"$")
UNSUB_NAME = re.compile(r"^" + _PLEASE + _UNSUB + r"(?:\s+me)?\s+from\s+(?:the\s+)?(?P<name>[^,;?]{1,60}?)"
                        r"(?P<tail>\s+(?:" + _YT + r"\s+)?channel|\s+on\s+" + _YT + r")?" + _TAILS + r"$")
UNFOLLOW = re.compile(r"^" + _PLEASE + r"(?P<verb>unfollow|mute|stop\s+following)\s+(?P<who>[^?;]{1,80}?)"
                      r"(?:\s+on\s+(?P<app>instagram|insta|ig|" + _YT + r"))?" + _TAILS + r"$")
_SINCE_WORDS = (r"(?:haven'?t|have\s+not|never|didn'?t|don'?t|stopped|not)\s+(?:been\s+)?(?:watch(?:ed|ing)?|seen|"
                r"opened|visited)")
IDLE = re.compile(r"^" + _PLEASE + r"(?:" + _UNSUB + r"(?:\s+me)?\s+from|unfollow|get\s+rid\s+of|clean\s+up)\s+"
                  r"(?:all\s+)?"
                  r"(?:the\s+|my\s+)?(?:" + _YT + r"\s+)?(?:channels?|subscriptions?)\s+(?:on\s+" + _YT +
                  r"\s+)?(?:that\s+|which\s+)?(?:i\s+)?" + _SINCE_WORDS + r"\b(?P<when>.*)$")
_WHAT = (r"(?P<what>these|them|those|it|this|that|this\s+one|that\s+one|them\s+all|all\s+of\s+them|all|both|"
         r"(?:these|those|the)\s+(?:videos?|ones|youtube\s+ones)|the\s+(?:first|second|third|fourth|fifth|1st|2nd|3rd|"
         r"4th|5th)(?:\s+one)?|(?:number\s+|#\s*)?\d{1,2})")
PLAYLIST = re.compile(r"^" + _PLEASE + r"(?:put|add|save|move|stick)\s+" + _WHAT + r"\s+(?:in|into|to|on)\s+"
                      r"(?:a\s+|an\s+|my\s+|the\s+)?(?:new\s+)?(?:private\s+)?(?:" + _YT + r"\s+)?playlist"
                      r"(?:\s+(?:called|named)\s+(?P<name>[^?;]{1,60}?))?(?:\s+on\s+" + _YT + r")?" + _TAILS + r"$")
PLAYLIST_MY = re.compile(r"^" + _PLEASE + r"(?:put|add|save|move|stick)\s+" + _WHAT + r"\s+(?:in|into|to|on)\s+my\s+"
                         r"(?P<name>[\w' -]{1,40}?)\s+playlist(?:\s+on\s+" + _YT + r")?" + _TAILS + r"$")
PLAYLIST_MAKE = re.compile(r"^" + _PLEASE + r"(?:make|create|start)\s+(?:me\s+)?a\s+(?:new\s+)?(?:private\s+)?"
                           r"(?:" + _YT + r"\s+)?playlist(?:\s+(?:called|named)\s+(?P<name>[^?;]{1,60}?))?"
                           r"(?:\s+(?:with|of|from|for)\s+" + _WHAT + r")?" + _TAILS + r"$")
# "remove kitchen lab from my youtube subscriptions": "youtube" there, or "channel", says it is YouTube's; "remove
# netflix from my subscriptions" is left to the cancel helper unless one of the person's channels has that name
REMOVE_SUB = re.compile(r"^" + _PLEASE + r"(?:remove|delete|drop|take)\s+(?:the\s+)?(?P<name>[^,;?]{1,60}?)\s+"
                        r"(?:off|from|out\s+of)\s+my\s+(?P<yt>" + _YT + r"\s+)?(?:subscriptions|subs)"
                        r"(?P<on>\s+on\s+" + _YT + r")?" + _TAILS + r"$")
WATCH_LATER = re.compile(r"^" + _PLEASE + r"(?:add|put|save)\s+" + _WHAT + r"\s+(?:to|in|on)\s+(?:my\s+)?"
                         r"watch[\s-]?later(?:\s+on\s+" + _YT + r")?" + _TAILS + r"$")
HISTORY = re.compile(r"^" + _PLEASE + r"(?:clear|delete|erase|pause|turn\s+off|wipe|stop)\s+(?:my\s+)?" + _YT +
                     r"\s+(?:watch\s+)?history" + _TAILS + r"$")
IG_EXPORT = re.compile(r"^(?:(?:how\s+(?:do|can|could)\s+i|can\s+you|could\s+you|help\s+me|is\s+there\s+a\s+way\s+to|"
                       r"can\s+i|i\s+want\s+to)\s+)?(?:make|set\s+up|get|have|schedule)\s+(?:my\s+)?(?:instagram|insta|ig)\s+"
                       r"(?:export|exports|data\s+export|download)s?\b.*\b(?:repeat|regular(?:ly)?|every\s+week|weekly|"
                       r"automatic(?:ally)?|on\s+(?:a|its)\s+own|by\s+itself|schedule|scheduled)\b")
# "get rid of the kitchen lab channel", "delete the kitchen lab subscription on youtube", "take me off X's channel"
GET_RID = re.compile(r"^" + _PLEASE + r"(?:get\s+rid\s+of|drop|ditch|delete|remove|take\s+me\s+off)\s+(?:the\s+|my\s+)?"
                     r"(?P<name>[^,;?]{1,60}?)(?:'s)?\s+(?P<yt>" + _YT + r"\s+)?(?P<what>channel|subscription)"
                     r"(?P<on>\s+on\s+" + _YT + r")?" + _TAILS + r"$")
# "clean up my youtube subscriptions", "which channels do i never watch": the list of channels not watched, after
# "since when?"
CLEAN_UP = re.compile(r"^" + _PLEASE + r"(?:(?:clean|tidy)\s+up|go\s+through|prune|sort\s+out)\s+(?:my\s+)?" + _YT +
                      r"\s+(?:subscriptions|subs|channels)" + _TAILS + r"$|^which\s+(?:" + _YT + r"\s+)?channels\s+"
                      r"(?:do\s+)?i\s+(?:never|not|rarely|no\s+longer)\s+watch(?:\s+any\s?more)?$")
# "save these videos to youtube", "add this to my youtube": a playlist, and its name is asked
PLAYLIST_BARE = re.compile(r"^" + _PLEASE + r"(?:put|add|save)\s+" + _WHAT + r"\s+(?:to|on|in)\s+(?:my\s+)?" + _YT +
                           _TAILS + r"$")
OTHER_MUSIC = re.compile(r"\b(?:spotify|apple\s+music|soundcloud|tidal|deezer|amazon\s+music|pandora)\b")
REST_STOP = re.compile(r"^(?:please\s+)?(?:stop|stop\s+it|don'?t|do\s+not|stop\s+(?:that|unsubscribing|"
                       r"subscribing))$")
# the answers to a preview
UNSUB_N = re.compile(r"^(?:yes[\s,]+)?(?:unsubscribe|unsub)\s+(?:from\s+)?(?:all\s+)?(?P<n>\d{1,3})(?:\s+channels?)?$")
KEEP_N = re.compile(r"^(?:but\s+)?keep\s+(?:numbers?\s+|#\s*)?"
                    r"(?P<nums>\d{1,3}(?:\s*(?:,|and|&|\s)\s*(?:#\s*)?\d{1,3})*)$")
NEXT = re.compile(r"^(?:next|next\s+(?:one|page|ones)|more|show\s+(?:me\s+)?(?:the\s+)?(?:next|rest|more))$")
KEEP_ALL = re.compile(r"^(?:no|nope|nah|keep\s+(?:it|them|them\s+all|all)|leave\s+(?:it|them)|never\s?mind|"
                      r"don'?t|cancel)$")
CHANNEL_WORD = re.compile(r"\b(?:the\s+)?(?:" + _YT + r"|channel|youtuber)\b")
PAID_WORD = re.compile(r"\b(?:paid|subscription|membership|the\s+service|the\s+app|cancel(?:\s+it)?)\b")
_ORD = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4, "fifth": 5, "5th": 5}
_PRONOUN = {"it", "that", "this", "them", "him", "her", "that one", "this one", "it all", "everything", "all"}
_CREATOR_WORDS = re.compile(r"^(?:that|this|the)\s+(?:creator|account|person|guy|girl|page|youtuber|channel)$"
                            r"|^(?:them|him|her)$")


def _cased(text, name):
    """The name as the person typed it (the reads match on the lowercased text)."""
    if not name:
        return name
    m = re.search(r"\s+".join(map(re.escape, name.split())), " ".join((text or "").split()), re.I)
    return m.group(0) if m else name


def _key(s):
    """A name as compared: case and punctuation dropped, "the" in front dropped."""
    t = re.sub(r"[^\w\s&+]", " ", (s or "").casefold())
    t = " ".join(t.split())
    return re.sub(r"^the\s+", "", t)


def _day(d):
    return f"{d.day} {d:%b %Y}"


def _aware(now):
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


# ---------- the library side: what is in view, video ids, the watch history ----------
def _view(bot, person):
    try:
        return bot.view(person["library"])
    except Exception:
        return None


def in_view(bot, person):
    """The items of the last answer, in their order (friends' posts are never in a view)."""
    last = bot.store.last_answer(person["handle"])
    view = _view(bot, person)
    if not last or view is None:
        return []
    return [it for it in (view.get(i) for i in last.get("items") or []) if it is not None]


def video_id_of(it):
    """The video id of a library YouTube item: its own field, else its link; None when neither holds a valid id."""
    if getattr(it, "platform", None) != "youtube":
        return None
    vid = it.video_id
    if not vid and it.url:
        m = re.search(r"(?:[?&]v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{11})", it.url)
        vid = m.group(1) if m else None
    return vid if vid and _VID.match(vid) else None


def _title(it):
    from .compose import display_title
    return " ".join(display_title(it).split())[:100] or "a video"


def _select(items, what):
    """The picks a "these" / "it" / "the second one" / "2" names (None: nothing that matches)."""
    w = " ".join((what or "").split())
    if w in ("it", "this", "that", "this one", "that one"):
        return items[:1]
    m = re.match(r"^the\s+(first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th)(?:\s+one)?$", w)
    n = None
    if m:
        n = _ORD[m.group(1)]
    else:
        m = re.match(r"^(?:number\s+|#\s*)?(\d{1,2})$", w)
        if m:
            n = int(m.group(1))
    if n is not None:
        return items[n - 1:n] if 1 <= n <= len(items) else None
    return list(items)


def _cache_channels(bot, video_ids):
    """{video id: channel id} from youtube_cache (ytinfo.py keeps snippet.channelId there)."""
    out = {}
    ids = [v for v in video_ids if v]
    for i in range(0, len(ids), 400):
        chunk = ids[i:i + 400]
        marks = ",".join("?" * len(chunk))
        for r in bot.store.q(f"SELECT video_id, channel_id FROM youtube_cache WHERE video_id IN ({marks}) "
                             "AND channel_id IS NOT NULL", tuple(chunk)):
            out[r["video_id"]] = r["channel_id"]
    return out


def watch_history(bot, person):
    """{"newest": date or None, "by_id": {channel id: latest date}, "by_title": {title key: latest date}} from the
    library's YouTube items watched (Takeout's watch history)."""
    view = _view(bot, person)
    out = {"newest": None, "by_id": {}, "by_title": {}}
    if view is None:
        return out
    rows = []
    for it in view.items.values():
        d = it.dates.get("watch") if it.platform == "youtube" and "watch" in it.kinds else None
        if not d:
            continue
        try:
            day = datetime.fromisoformat(d[:10]).date()
        except ValueError:
            continue
        rows.append((it, day))
    if not rows:
        return out
    chans = _cache_channels(bot, [video_id_of(it) for it, _ in rows])
    for it, day in rows:
        out["newest"] = max(out["newest"] or day, day)
        ch = chans.get(video_id_of(it) or "")
        if ch:
            out["by_id"][ch] = max(out["by_id"].get(ch, day), day)
        if it.creator:
            k = _key(it.creator)
            out["by_title"][k] = max(out["by_title"].get(k, day), day)
    return out


_MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                       "september", "october", "november", "december"], 1)}
_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "six": 6, "twelve": 12}


def since_of(words, today):
    """The first day the person means by "since 2024" (1 Jan 2025), "in a year", "in 6 months", "this year", "since
    march 2025" (1 Apr 2025). None when the words give no time."""
    w = " ".join((words or "").split())
    m = re.search(r"\bsince\s+(?:the\s+end\s+of\s+)?(\d{4})\b", w)
    if m:
        y = int(m.group(1)) + 1
        return datetime(y, 1, 1).date() if 2006 <= y <= today.year else None
    m = re.search(r"\bsince\s+(?:the\s+start\s+of\s+|the\s+beginning\s+of\s+)(\d{4})\b", w)
    if m:
        y = int(m.group(1))
        return datetime(y, 1, 1).date() if 2005 <= y <= today.year else None
    m = re.search(r"\bsince\s+(" + "|".join(_MONTHS) + r")(?:\s+(\d{4}))?\b", w)
    if m:
        mo = _MONTHS[m.group(1)]
        y = int(m.group(2)) if m.group(2) else (today.year if mo < today.month else today.year - 1)
        y, mo = (y + 1, 1) if mo == 12 else (y, mo + 1)
        d = datetime(y, mo, 1).date()
        return d if d <= today else None
    if re.search(r"\bthis\s+year\b", w):
        return datetime(today.year, 1, 1).date()
    m = re.search(r"\b(?:in|for|over)\s+(?:the\s+)?(?:last\s+|past\s+)?(a|an|one|two|three|four|six|twelve|\d{1,2})?"
                  r"\s*(year|years|month|months|week|weeks)\b", w)
    if m:
        n = _NUM.get(m.group(1) or "a") or int(m.group(1))
        days = {"year": 365, "month": 30, "week": 7}[m.group(2).rstrip("s")] * n
        return today - timedelta(days=days)
    return None


# ---------- the person's subscriptions (24 hours in state) ----------
def subs(bot, h, api, now, fresh=False):
    st = bot.store.get_state(f"ytsubs:{h}")
    if st and not fresh and now - datetime.fromisoformat(st["at"]) < SUBS_KEEP:
        return [tuple(x) for x in st["items"]]
    items = api.subscriptions()
    bot.store.set_state(f"ytsubs:{h}", {"at": now_iso(now), "items": [list(x) for x in items]})
    return items


def _api(bot, h, now):
    from .actions.youtube import Api
    return Api(bot.store, h, now)


# ---------- hook 5b ----------
def youtube_reads(bot, person, text, now):
    """handler.answer_normally hook 5b. None when the message is none of the YouTube or Instagram asks."""
    t = _norm(text)
    if not t or len(t) > 200:
        return None
    h = person["handle"]
    now = _aware(now)
    from . import yt_auth
    if yt_auth.waiting(bot.store, h, now) and DEVICE_DONE.match(t):
        bot.note(intent="youtube")
        return _poll_now(bot, person, now)
    if bot.store.get_state(f"ytrest:{h}") and REST_STOP.match(t):
        bot.note(intent="youtube")
        bot.store.set_state(f"ytrest:{h}", None)
        return bot.send(h, T.YT_REST_STOPPED)
    for rx, fn in ((CONNECT, _connect), (DISCONNECT, _disconnect), (IS_CONNECTED, _status), (HISTORY, _history_link)):
        if rx.match(t):
            bot.note(intent="youtube")
            return fn(bot, person, now)
    if IG_EXPORT.match(t):
        bot.note(intent="youtube")
        return bot.send(h, T.ig_schedule())
    m = IDLE.match(t)
    if m:
        bot.note(intent="youtube")
        return _idle(bot, person, m.group("when"), now)
    if CLEAN_UP.match(t):
        bot.note(intent="youtube")
        return _idle(bot, person, "", now)
    m = PLAYLIST_BARE.match(t)
    if m:
        return _playlist(bot, person, m.group("what"), None, now)
    m = GET_RID.match(t)
    if m and not re.fullmatch(r"(?:that|this|it|them)", m.group("name")):
        said = bool(m.group("yt") or m.group("on")) or m.group("what") == "channel"
        return _unsub_name(bot, person, m.group("name"), said, text, now)
    if UNSUB_THAT.match(t):
        bot.note(intent="youtube")
        return _unsub_that(bot, person, now)
    for rx in (PLAYLIST, PLAYLIST_MY, PLAYLIST_MAKE):
        m = rx.match(t)
        if m:
            if _key(m.group("name") or "") == "watch later":   # no app can add to Watch Later: the link instead
                return _watch_later(bot, person, m.group("what") or "it")
            other = OTHER_MUSIC.search(m.group("name") or "")
            if other:   # "my spotify playlist": not YouTube's, and nothing is added anywhere
                bot.note(intent="youtube")
                return bot.send(person["handle"], T.yt_other_app(other.group(0)))
            return _playlist(bot, person, m.group("what") or "these", _cased(text, m.group("name")), now)
    m = WATCH_LATER.match(t)
    if m:
        return _watch_later(bot, person, m.group("what"))
    m = UNSUB_NAME.match(t)
    if m:
        # "channel" / "youtuber" / "on youtube" say it is the YouTube channel; "youtube" inside the name does not
        # ("unsubscribe from youtube premium" is the paid membership: the cancel helper)
        said = bool(m.group("tail")) or bool(re.search(r"\b(?:channel|youtuber)\b", t))
        return _unsub_name(bot, person, m.group("name"), said, text, now)
    m = REMOVE_SUB.match(t)
    if m:
        if re.fullmatch(_THAT, m.group("name")):
            bot.note(intent="youtube")
            return _unsub_that(bot, person, now)
        said = bool(m.group("yt") or m.group("on")) or bool(re.search(r"\b(?:channel|youtuber)\b", m.group("name")))
        return _unsub_name(bot, person, re.sub(r"\s+(?:channel|youtuber)$", "", m.group("name")), said, text, now)
    m = UNFOLLOW.match(t)
    if m:
        verb = "unfollow" if m.group("verb").startswith("stop") else m.group("verb")
        return _unfollow(bot, person, verb, m.group("who"), m.group("app"), text, now)
    return None


# ---------- connect, disconnect, status ----------
def _connect(bot, person, now):
    from . import yt_auth
    from .actions.youtube import YtError
    h = person["handle"]
    if yt_auth.connected(bot.store, h):
        return bot.send(h, T.YT_ALREADY)
    st = yt_auth.waiting(bot.store, h, now)
    if st:
        return bot.send(h, T.yt_code_waiting(st["user_code"]))
    try:
        got = yt_auth.start(bot.store, h, now)
    except YtError as e:
        line = {"not_set_up": T.YT_NOT_SET_UP, "no_key": T.YT_NO_KEY}.get(e.code, T.YT_CONNECT_FAILED)
        return bot.send(h, line)
    return bot.send(h, T.yt_connect_link(got["user_code"], got["minutes"]))


def connected_line(bot, h, now):
    """The line after Google said yes: how many channels and playlists (2 units), or the short line."""
    from .actions.youtube import YtError
    bot.store.set_connection(h, "youtube", status="connected", fails=0, last_error="", at=now)
    try:
        api = _api(bot, h, now)
        n = len(subs(bot, h, api, now, fresh=True))
        _, p = api.playlists()
    except YtError:
        return T.yt_status(True, True)
    return T.yt_connected(n, p)


def _poll_line(got):
    """The line after a sign-in code ended without a connection."""
    return {"denied": T.YT_DENIED, "expired": T.YT_CODE_EXPIRED, "scope": T.YT_SCOPE}.get(got, T.YT_CONNECT_FAILED)


def _poll_now(bot, person, now):
    from . import yt_auth
    h = person["handle"]
    st = yt_auth.waiting(bot.store, h, now)
    got = yt_auth.poll(bot.store, h, now, force=True)
    if got == "connected":
        return bot.send(h, connected_line(bot, h, now))
    if got == "pending":
        return bot.send(h, T.yt_code_waiting((st or {}).get("user_code") or ""))
    return bot.send(h, _poll_line(got))


def _forget_lists(bot, h):
    for k in ("ytsubs", "ytask", "ytrest"):
        bot.store.set_state(f"{k}:{h}", None)


def _disconnect(bot, person, now):
    from . import yt_auth
    h = person["handle"]
    if not yt_auth.connected(bot.store, h):
        if yt_auth.waiting(bot.store, h, now):
            yt_auth.end_device(bot.store, h)
            return bot.send(h, T.yt_disconnected(True))
        return bot.send(h, T.YT_NOT_ON)
    ok = yt_auth.disconnect(h)
    bot.store.set_connection(h, "youtube", status="off", at=now)
    bot.store.end_grants(h, connector="youtube", reason="disconnected", at=now)
    _forget_lists(bot, h)
    return bot.send(h, T.yt_disconnected(ok))


def _status(bot, person, now):
    from . import yt_auth
    h = person["handle"]
    return bot.send(h, T.yt_status(yt_auth.connected(bot.store, h), yt_auth.connectable(bot.store, h)))


def _history_link(bot, person, now):
    return bot.send(person["handle"], T.YT_HISTORY)


def revoked(bot, h, now):
    """Google refused our sign-in: it is gone (yt_auth deleted it); rules stop adding there; the lists go."""
    from . import tokens
    try:
        tokens.delete(h, "youtube")
    except tokens.TokenError:
        pass
    bot.store.set_connection(h, "youtube", status="off", last_error="needs_signin", at=now)
    bot.store.end_grants(h, connector="youtube", reason="revoked", at=now)
    _forget_lists(bot, h)
    return T.YT_REVOKED


def _blocked(bot, h, what="unsubscribe"):
    """The line when YouTube cannot be used for this person now, or None."""
    why = C.unavailable(bot.store, h, "youtube")
    if why is None:
        return None
    if why == "unreachable":
        return T.YT_NOT_SET_UP
    return T.YT_NOT_CONNECTED if what == "unsubscribe" else T.YT_NOT_CONNECTED_PLAYLIST


def _fail_line(bot, h, code, now):
    if code == "needs_signin":
        return revoked(bot, h, now)
    if code == "quota":
        return T.YT_QUOTA_NOTHING
    return T.YT_FAILED


# ---------- one channel ----------
def _channel_of(bot, api, it):
    vid = video_id_of(it)
    if not vid:
        return None
    ch = _cache_channels(bot, [vid]).get(vid)
    if ch or api is None:
        return ch
    from .actions.youtube import YtError
    try:
        return api.channel_of(vid)
    except YtError:
        return None


def _match_sub(rows, channel_id=None, name=None):
    if channel_id:
        for r in rows:
            if r[1] == channel_id:
                return r
    if name:
        k = _key(name)
        hits = [r for r in rows if _key(r[2]) == k]
        if len(hits) == 1:
            return hits[0]
    return None


def _yt_picks(bot, person):
    return [it for it in in_view(bot, person) if it.platform == "youtube"]


def _unsub_that(bot, person, now):
    h = person["handle"]
    picks = _yt_picks(bot, person)
    if not picks:   # only Instagram in view: "unsubscribe" there means unfollow, which only the person can do
        ig = [it for it in in_view(bot, person) if it.platform == "instagram" and it.creator]
        hd = L.instagram_handle(ig[0].creator) if len(ig) == 1 else None
        if hd:
            return _ig_send(bot, h, "unfollow", [hd], now)
    names = list(dict.fromkeys(it.creator for it in picks if it.creator))
    if len(names) > 1:
        return bot.send(h, T.yt_which_channel(names))
    line = _blocked(bot, h)
    if line:
        return bot.send(h, line)
    if not picks:
        return bot.send(h, T.YT_WHICH_NONE)
    return _unsub_pick(bot, person, picks[0], now)


def _unsub_pick(bot, person, it, now):
    from .actions.youtube import YtError
    h = person["handle"]
    api = _api(bot, h, now)
    try:
        rows = subs(bot, h, api, now)
        sub = _match_sub(rows, _channel_of(bot, api, it), it.creator)
    except YtError as e:
        return bot.send(h, _fail_line(bot, h, e.code, now))
    if sub is None:
        return bot.send(h, T.yt_not_subscribed(it.creator or "that channel"))
    return _ask_unsub(bot, person, [sub], now)


def _unsub_name(bot, person, name, channel_said, text, now):
    """"unsubscribe from <name>": a channel the person follows (or a YouTube pick's channel in view). A paid service
    (cancel_routes.json) with no such channel is left to the cancel helper; one that is both asks."""
    from . import cancel, yt_auth
    from .actions.youtube import YtError
    h = person["handle"]
    name = re.sub(r"^(?:my|the|that|this)\s+", "", " ".join((name or "").split())).strip(" '\"")
    if not name or name in _PRONOUN or cancel.NOT_CANCEL.search(name) or re.search(r"\d{3,}|@|https?:", name):
        return None
    if re.fullmatch(r"(?:" + _YT + r"\s+)?(?:channel|channels|youtuber|creator)", name):
        return None
    merchant = cancel.merchant_in(name)
    k = _key(name)
    pick = next((it for it in _yt_picks(bot, person) if it.creator and _key(it.creator) == k), None)
    if not yt_auth.connected(bot.store, h):
        if merchant and not channel_said:
            return None
        if pick is None and not channel_said:
            return None
        bot.note(intent="youtube")
        return bot.send(h, _blocked(bot, h) or T.YT_NOT_CONNECTED)
    api = _api(bot, h, now)
    try:
        rows = subs(bot, h, api, now)
        sub = _match_sub(rows, _channel_of(bot, api, pick) if pick else None, name)
    except YtError as e:
        if merchant and not channel_said:
            return None
        bot.note(intent="youtube")
        return bot.send(h, _fail_line(bot, h, e.code, now))
    if sub and merchant and not channel_said:
        bot.note(intent="youtube")
        bot.store.set_state(f"ytask:{h}", {"at": now_iso(now), "kind": "both", "text": text, "sub": list(sub)})
        return bot.send(h, T.YT_OR_PAID)
    if sub:
        bot.note(intent="youtube")
        return _ask_unsub(bot, person, [sub], now)
    if merchant and not channel_said:
        return None
    if pick is not None:
        bot.note(intent="youtube")
        return bot.send(h, T.yt_not_subscribed(pick.creator))
    if channel_said:
        bot.note(intent="youtube")
        return bot.send(h, T.yt_no_channel(name, len(rows)))
    return None


def _params_unsub(rows):
    from .actions import YtUnsubscribe
    return YtUnsubscribe(items=[{"subscription_id": s, "channel_id": c, "title": (t or "a channel")[:200]}
                                for s, c, t in rows])


def _ask_unsub(bot, person, rows, now, note=None, all_rows=None, start=1):
    """Shows the exact list and keeps it, with its yes token, for the next message."""
    from .actions.youtube import token_for
    h = person["handle"]
    params = _params_unsub(rows)
    st = {"at": now_iso(now), "kind": "unsub", "items": [list(r) for r in rows],
          "token": token_for(h, "unsubscribe", params), "start": start}
    if note:
        st["note"] = note
    if all_rows is not None:
        st["all"] = [list(r) for r in all_rows]
    bot.store.set_state(f"ytask:{h}", st)
    if note is None and len(rows) == 1:
        return bot.send(h, T.yt_unsub_one(rows[0][2]))
    return bot.send(h, _list_text(st))


def _list_text(st):
    n = st["note"]
    rows = st["items"]
    more = max(0, len(st.get("all") or rows) - (st["start"] - 1) - len(rows))
    return T.yt_idle_list(n["total"], [r[2] for r in rows], n["since"], n["newest"], n["unmatched"], more=more,
                          start=st["start"], kept=n.get("kept", 0))


# ---------- channels not watched since ----------
def _idle(bot, person, when, now):
    from .actions.youtube import YtError
    h = person["handle"]
    line = _blocked(bot, h)
    if line:
        return bot.send(h, line)
    today = now.astimezone(ZoneInfo(person["timezone"])).date()
    since = since_of(when, today)
    if since is None:
        return bot.send(h, T.YT_SINCE_ASK)
    hist = watch_history(bot, person)
    if hist["newest"] is None:
        return bot.send(h, T.YT_NO_HISTORY)
    if (today - hist["newest"]).days > HISTORY_DAYS:
        return bot.send(h, T.yt_history_old(_day(hist["newest"])))
    try:
        rows = subs(bot, h, _api(bot, h, now), now)
    except YtError as e:
        return bot.send(h, _fail_line(bot, h, e.code, now))
    idle, unmatched = [], 0
    for r in rows:
        last = [d for d in (hist["by_id"].get(r[1]), hist["by_title"].get(_key(r[2]))) if d]
        if not last:
            unmatched += 1      # never guessed: a channel with no record in the history is left out
            continue
        if max(last) < since:
            idle.append(r)
    note = {"total": len(rows), "since": _day(since), "newest": _day(hist["newest"]), "unmatched": unmatched}
    if not idle:
        return bot.send(h, T.yt_idle_none(len(rows), note["since"], note["newest"], unmatched))
    idle.sort(key=lambda r: _key(r[2]))
    return _ask_unsub(bot, person, idle[:LIST_MAX], now, note=note, all_rows=idle, start=1)


# ---------- the answer to a preview (hook 4a) ----------
def _open(bot, key, now, life=ASK_OPEN):
    st = bot.store.get_state(key)
    if not st:
        return None
    bot.store.set_state(key, None)   # the next message only
    return st if now - datetime.fromisoformat(st["at"]) <= life else None


def youtube_answer(bot, person, text, now):
    """handler._asked_reads hook 4a: the next message after a YouTube preview or an Instagram link. None: not an
    answer (the question is dropped and the message is handled as usual)."""
    h = person["handle"]
    now = _aware(now)
    t = _norm(text)
    st = _open(bot, f"igtap:{h}", now)
    if st:
        ref = _ig_answer(bot, person, st, t, now)
        if ref is not None:
            return ref
    st = _open(bot, f"ytask:{h}", now)
    if not st or not t:
        return None
    if st["kind"] == "both":
        return _both_answer(bot, person, st, t, text, now)
    if st["kind"] == "playlist":
        if T.YES.match(t) or re.match(r"^(?:yes[\s,]+)?(?:please\s+)?(?:do\s+it|add\s+them|go\s+ahead)$", t):
            bot.note(intent="youtube_yes")
            return _do_playlist(bot, person, st, now)
        if T.NO.match(t) or KEEP_ALL.match(t):
            bot.note(intent="youtube_no")
            return bot.send(h, T.YT_LEFT)
        return None
    # an unsubscribe list: "yes" takes one channel; a longer list needs "unsubscribe N" with N its count
    n = len(st["items"])
    m = UNSUB_N.match(t)
    if m or T.YES.match(t):
        bot.note(intent="youtube_yes")
        if (m and int(m.group("n")) == n) or (not m and n == 1):
            return _do_unsub(bot, person, st, now)
        bot.store.set_state(f"ytask:{h}", dict(st, at=now_iso(now)))   # the same list waits for the right number
        return bot.send(h, T.yt_count_mismatch(n))
    m = KEEP_N.match(t)
    if m:
        bot.note(intent="youtube")
        drop = {int(x) for x in re.findall(r"\d{1,3}", m.group("nums"))}
        start = st.get("start", 1)
        left = [r for i, r in enumerate(st["items"], start) if i not in drop]
        if not left:
            return bot.send(h, T.YT_KEEP_ALL)
        whole = [r for r in (st.get("all") or st["items"]) if r not in st["items"] or r in left]
        note = dict(st.get("note") or _one_note(st))
        note["kept"] = note.get("kept", 0) + (len(st["items"]) - len(left))
        return _ask_unsub(bot, person, [tuple(r) for r in left], now, note=note,
                          all_rows=[tuple(r) for r in whole], start=start)
    if NEXT.match(t) and st.get("all"):
        bot.note(intent="youtube")
        start = st.get("start", 1) + n
        rest = st["all"][start - 1:start - 1 + LIST_MAX]
        if not rest:
            return bot.send(h, T.IG_ALL_DONE)
        return _ask_unsub(bot, person, [tuple(r) for r in rest], now, note=st["note"],
                          all_rows=[tuple(r) for r in st["all"]], start=start)
    if T.NO.match(t) or KEEP_ALL.match(t):
        bot.note(intent="youtube_no")
        return bot.send(h, T.YT_LEFT)
    return None


def _one_note(st):
    return {"total": len(st["items"]), "since": "", "newest": "", "unmatched": 0}


def _both_answer(bot, person, st, t, text, now):
    from . import cancel
    if PAID_WORD.search(t) and not re.search(r"\bchannel\b", t):
        req = cancel.request(st["text"])
        if req is None:
            return None
        bot.note(intent="cancel")
        return bot._cancel_start(person, req, " ".join(st["text"].split()), now)
    if CHANNEL_WORD.search(t):
        bot.note(intent="youtube")
        return _ask_unsub(bot, person, [tuple(st["sub"])], now)
    return None


def _ctx(bot, person, now):
    from .actions.base import Ctx
    return Ctx(bot=bot, person=person, answer={}, picks=[], run_id=None, kind="act_on_last", now=now,
               tz=person["timezone"])


def _day_bounds(person, now):
    from .actions import local_day_bounds
    return local_day_bounds(now, person["timezone"])


def _tomorrow_9(person, now):
    """9am tomorrow where the person is, and never before Google's quota resets (midnight Pacific)."""
    tz = ZoneInfo(person["timezone"])
    local = now.astimezone(tz)
    nine = datetime.combine(local.date() + timedelta(days=1), datetime.min.time(), tzinfo=tz).replace(hour=9)
    pac = ZoneInfo("America/Los_Angeles")
    reset = datetime.combine(now.astimezone(pac).date() + timedelta(days=1), datetime.min.time(), tzinfo=pac)
    return max(nine, reset + timedelta(minutes=5)).astimezone(timezone.utc)


def _do_unsub(bot, person, st, now):
    """After the yes: the list read again from YouTube must still hold every channel shown, with the same title;
    else nothing is changed (a stale yes)."""
    from .actions import Refused, perform
    from .actions.youtube import YtError
    h = person["handle"]
    line = _blocked(bot, h)
    if line:
        return bot.send(h, line)
    shown = [tuple(r) for r in st["items"]]
    start, end = _day_bounds(person, now)
    if bot.store.placements_in(h, "youtube.unsubscribe", start, end) + len(shown) > UNSUB_PER_DAY:
        return bot.send(h, T.YT_UNSUB_CAP)
    api = _api(bot, h, now)
    try:
        fresh = {r[0]: r for r in subs(bot, h, api, now, fresh=True)}
    except YtError as e:
        return bot.send(h, _fail_line(bot, h, e.code, now))
    if any(s not in fresh or fresh[s][1] != c for s, c, _ in shown):
        return bot.send(h, T.YT_LIST_CHANGED)
    params = _params_unsub([fresh[s] for s, _, _ in shown])
    try:
        o = perform("youtube.unsubscribe", _ctx(bot, person, now), params.model_dump(), yes_token=st["token"])
        if o.detail is not None:   # the units of the check read too, so action_log holds what this yes cost
            o.detail["units"] = int(o.detail.get("units") or 0) + api.units
    except Refused:
        return bot.send(h, T.YT_LIST_CHANGED)   # a title changed since the list was shown: another list
    except YtError as e:
        if e.code in ("quota", "too_many"):
            return bot.send(h, _rest_later(bot, person, "unsub", [list(r) for r in shown], 0, e.code, now))
        bot.store.log_action(h, None, None, "youtube.unsubscribe", "failed", detail={"error": e.code}, at=now)
        return bot.send(h, _fail_line(bot, h, e.code, now))
    return bot.send(h, _after_unsub(bot, person, o, len(shown), shown, now))


def _after_unsub(bot, person, o, total, shown, now, kind="unsub"):
    """Placements, the action log, undo; then the line."""
    h = person["handle"]
    if o.status == "skipped":
        return o.line
    d = o.detail or {}
    placed = d.get("placed") or []
    ids = [bot.store.add_placement(h, "youtube", x["action"], x["remote_id"], None, None, now, route="youtube_api")
           for x in placed]
    bot.store.log_action(h, None, None, "youtube.unsubscribe", o.status, ref=",".join(map(str, ids)),
                         detail={"count": len(ids), "placements": ids, "units": d.get("units"), "route": "youtube_api"},
                         at=now)
    titles = {x[1]: x[2] for x in shown}
    if ids:
        old = bot.store.get_state(f"ytundo:{h}")
        keep = old["ids"] if old and old.get("kind") == "unsub" and kind == "rest" and \
            now - datetime.fromisoformat(old["at"]) <= UNDO_UNSUB else []
        bot.store.set_state(f"ytundo:{h}", {"at": now_iso(now), "kind": "unsub", "ids": keep + ids,
                                            "title": titles.get(placed[0]["remote_id"]) if len(placed) == 1 else None})
    if o.status == "done":
        if kind == "rest":
            return T.yt_rest_done(len(ids), "unsub")
        return T.yt_unsub_done(len(ids), titles.get(placed[0]["remote_id"]) if len(placed) == 1 else None)
    stop = d.get("stop")
    if stop in ("quota", "too_many"):
        return _rest_later(bot, person, "unsub", [[c["subscription_id"], c["channel_id"], c["title"]]
                                                  for c in d.get("left") or []], len(ids), stop, now, total=total)
    if stop == "needs_signin":
        return revoked(bot, h, now)
    return T.yt_unsub_stopped(len(ids), total)


def _rest_later(bot, person, kind, rows, done, code, now, total=None):
    h = person["handle"]
    total = total if total is not None else done + len(rows)
    bot.store.set_state(f"ytrest:{h}", {"at": now_iso(now), "due": now_iso(_tomorrow_9(person, now)), "kind": kind,
                                        "items": rows, "code": code})
    if kind == "resub":
        return T.yt_undo_rest(done, total)
    return T.yt_rest_tomorrow(done, total, code)


# ---------- a private playlist ----------
def _playlist(bot, person, what, name, now):
    from .actions import YtPlaylistAdd, YtPlaylistMake
    from .actions.youtube import YtError, token_for
    h = person["handle"]
    items = in_view(bot, person)
    if not items:
        if not name:
            return None
        bot.note(intent="youtube")
        return bot.send(h, T.YT_NOTHING_IN_VIEW)
    sel = _select(items, what)
    if not sel:
        return None
    bot.note(intent="youtube")
    yt = [(it, video_id_of(it)) for it in sel]
    yt = [(it, v) for it, v in yt if v]
    other = len(sel) - len(yt)
    if not yt:
        return bot.send(h, T.YT_NO_YT_PICKS)
    title = re.sub(r"\s+on\s+" + _YT + r"$", "", " ".join((name or "").split())).strip(" '\"“”")
    if not title:
        return bot.send(h, T.YT_PLAYLIST_NAME_ASK)
    title = (title[:1].upper() + title[1:])[:60]
    line = _blocked(bot, h, "playlist")
    if line:
        return bot.send(h, line)
    start, end = _day_bounds(person, now)
    if bot.store.placements_in(h, "youtube.playlist_add", start, end) + len(yt) > ADD_PER_DAY:
        return bot.send(h, T.YT_ADD_CAP)
    try:
        lists, _ = _api(bot, h, now).playlists()
    except YtError as e:
        return bot.send(h, _fail_line(bot, h, e.code, now))
    pid = next((p for p, tl in lists if tl and tl.casefold() == title.casefold()), None)
    if pid:
        title = next(tl for p, tl in lists if p == pid)
    seen, videos = set(), []
    for it, v in yt:
        if v not in seen:
            seen.add(v)
            videos.append({"video_id": v, "title": _title(it)[:200]})
    add = YtPlaylistAdd(playlist_title=title, playlist_id=pid, videos=videos)
    st = {"at": now_iso(now), "kind": "playlist", "title": title, "playlist_id": pid, "videos": videos,
          "token": token_for(h, "playlist_add", add)}
    if not pid:
        st["make_token"] = token_for(h, "playlist_make", YtPlaylistMake(title=title))
    bot.store.set_state(f"ytask:{h}", st)
    return bot.send(h, T.yt_playlist_ask(title, [v["title"] for v in videos], pid is None, other))


def _do_playlist(bot, person, st, now):
    from .actions import Refused, perform
    from .actions.youtube import YtError
    h = person["handle"]
    line = _blocked(bot, h, "playlist")
    if line:
        return bot.send(h, line)
    ctx = _ctx(bot, person, now)
    pid, made, ids = st.get("playlist_id"), None, []
    try:
        if not pid:
            o = perform("youtube.playlist_make", ctx, {"title": st["title"], "privacy": "private"},
                        yes_token=st.get("make_token"))
            if o.status != "done":
                return bot.send(h, o.line or T.YT_FAILED)
            pid = o.detail["playlist_id"]
            made = bot.store.add_placement(h, "youtube", "youtube.playlist_make", pid, None, None, now,
                                           route="youtube_api")
            bot.store.log_action(h, None, None, "youtube.playlist_make", "done", ref=str(made),
                                 detail={"count": 1, "placements": [made], "units": o.detail.get("units"),
                                         "route": "youtube_api"}, at=now)
        o = perform("youtube.playlist_add", ctx, {"playlist_title": st["title"], "playlist_id": pid,
                                                  "videos": st["videos"]}, yes_token=st["token"])
    except Refused:
        return bot.send(h, T.YT_FAILED)
    except YtError as e:
        bot.store.log_action(h, None, None, "youtube.playlist_add", "failed", detail={"error": e.code}, at=now)
        if made:
            bot.store.set_state(f"ytundo:{h}", {"at": now_iso(now), "kind": "playlist", "ids": [], "title": st["title"],
                                                "made": True})
        return bot.send(h, _fail_line(bot, h, e.code, now))
    if o.status == "skipped":
        return bot.send(h, o.line)
    d = o.detail or {}
    ids = [bot.store.add_placement(h, "youtube", x["action"], x["remote_id"], None, None, now, route="youtube_api")
           for x in d.get("placed") or []]
    bot.store.log_action(h, None, None, "youtube.playlist_add", o.status, ref=",".join(map(str, ids)),
                         detail={"count": len(ids), "placements": ids, "units": d.get("units"), "route": "youtube_api"},
                         at=now)
    bot.store.set_state(f"ytundo:{h}", {"at": now_iso(now), "kind": "playlist", "ids": ids, "title": st["title"],
                                        "made": bool(made)})
    if o.status == "done":
        return bot.send(h, T.yt_playlist_done(st["title"], len(ids), bool(made)))
    if d.get("stop") == "needs_signin":
        return bot.send(h, revoked(bot, h, now))
    return bot.send(h, T.yt_playlist_part(st["title"], len(ids), len(st["videos"])))


# ---------- links the person taps (actions/link.py builds each one from what code holds) ----------
IG_MAX = 10   # Instagram accounts in one "unfollow @a, @b ..." (one link at a time)


def _watch_later(bot, person, what):
    h = person["handle"]
    items = in_view(bot, person)
    sel = _select(items, what) if items else None
    if not sel:
        return None
    bot.note(intent="youtube")
    link = L.youtube_video(video_id_of(sel[0]))
    if not link:
        return bot.send(h, T.YT_NOT_A_VIDEO)
    return bot.send(h, T.yt_watch_later(link))


def _ig_handles(who):
    """'@a', '@a and @b', '@a, @b' typed by the person -> ['a', 'b'] (None when it is not that)."""
    parts = [p for p in re.split(r"\s*(?:,|\band\b|&)\s*", who) if p]
    out = []
    for p in parts:
        p = p.strip()
        hd = L.instagram_handle(p) if p.startswith("@") else None
        if not hd:
            return None
        out.append(hd)
    return list(dict.fromkeys(out))[:IG_MAX] or None


def _unfollow(bot, person, verb, who, app, text, now):
    h = person["handle"]
    who = " ".join((who or "").split())
    yt_app = bool(app) and bool(re.fullmatch(_YT, app))
    handles = _ig_handles(who) if not yt_app else None
    picks = in_view(bot, person)
    it = None
    if handles is None:
        if _CREATOR_WORDS.match(who):
            named = list(dict.fromkeys(p.creator for p in picks if p.creator))
            if len(named) != 1:   # "unfollow them" with two creators in view: never a guess
                return None
            it = next(p for p in picks if p.creator)
        else:
            k = _key(who.lstrip("@"))
            it = next((p for p in picks if p.creator and _key(p.creator.lstrip("@")) == k), None)
        if it is None:
            return None
        if it.platform == "instagram" and not yt_app:
            hd = L.instagram_handle(it.creator)
            if not hd:
                return None
            handles = [hd]
    bot.note(intent="youtube" if handles is None else "instagram_link")
    if handles is not None:
        return _ig_send(bot, h, verb, handles, now)
    if it.platform != "youtube":
        return None
    if verb == "mute":
        vid = video_id_of(it)
        ch = _cache_channels(bot, [vid]).get(vid) if vid else None
        return bot.send(h, T.yt_mute(it.creator or "the channel", L.youtube_channel(ch)))
    line = _blocked(bot, h)
    if line:
        return bot.send(h, line)
    return _unsub_pick(bot, person, it, now)


def _ig_send(bot, h, verb, handles, now):
    first, rest = handles[0], handles[1:]
    bot.store.set_state(f"igtap:{h}", {"at": now_iso(now), "verb": verb, "current": first, "queue": rest})
    return bot.send(h, T.ig_tap(verb, first, L.instagram_profile(first)))


def _ig_answer(bot, person, st, t, now):
    h = person["handle"]
    done = bool(re.match(r"^(?:ok(?:ay)?[\s,]+)?(?:done|did\s+it|i\s+did\s+it|unfollowed|muted|ok\s+done)$", t))
    if not done and not NEXT.match(t) and t not in ("skip", "skip it"):
        return None
    if done:
        L.tap(bot.store, h, "instagram", st["verb"], now)
    bot.note(intent="instagram_link")
    if not st.get("queue"):
        return bot.send(h, T.IG_ALL_DONE)
    return _ig_send(bot, h, st["verb"], st["queue"], now)


# ---------- undo (handler._undo) ----------
def undo_due(bot, h, now, lw=None):
    """True when "undo" means the last YouTube change: within its window and newer than the person's last own write."""
    st = bot.store.get_state(f"ytundo:{h}")
    if not st:
        return False
    at = datetime.fromisoformat(st["at"])
    life = UNDO_UNSUB if st["kind"] == "unsub" else UNDO_PLAYLIST
    if _aware(now) - at > life:
        return False
    return lw is None or at >= datetime.fromisoformat(lw["at"])


def undo(bot, person, now):
    from .actions import youtube as Y
    h = person["handle"]
    now = _aware(now)
    st = bot.store.get_state(f"ytundo:{h}")
    bot.store.set_state(f"ytundo:{h}", None)
    rows = bot.store.placements(h, ids=st.get("ids") or [])
    if st["kind"] == "playlist":
        if not rows and not st.get("made"):
            return T.NOTHING_TO_UNDO
        res = Y.remove(rows, bot.store, now) if rows else {"removed": [], "failed": [], "stop": None}
        bot.store.remove_placements(res["removed"], now)
        if res.get("stop") == "needs_signin":
            return revoked(bot, h, now)
        bot.store.log_action(h, None, None, "youtube.undo", "done",   # not an add: no daily cap counts it
                             detail={"count": len(res["removed"]), "units": res.get("units")}, at=now)
        return T.yt_undo_playlist(st["title"], len(res["removed"]), len(res["failed"]), st.get("made"))
    if not rows:
        return T.NOTHING_TO_UNDO
    line = _blocked(bot, h)
    if line:
        return line
    res = Y.remove(rows, bot.store, now)
    bot.store.remove_placements(res["removed"], now)
    bot.store.log_action(h, None, None, "youtube.subscribe", "done" if res["removed"] else "failed",
                         detail={"count": len(res["removed"]), "units": res.get("units"), "route": "youtube_api"},
                         at=now)
    if res.get("stop") == "needs_signin":
        return revoked(bot, h, now)
    if res.get("stop") in ("too_many", "quota"):
        left = [r["id"] for r in rows if r["id"] in res["failed"]]
        return _rest_later(bot, person, "resub", left, len(res["removed"]), res["stop"], now, total=len(rows))
    if res["failed"]:
        return T.yt_undo_unsub(len(res["removed"])) + " " + T.YT_FAILED
    return T.yt_undo_unsub(len(res["removed"]), st.get("title"))


# ---------- the scheduler's tick ----------
def tick(bot, now):
    """Sign-in codes, rests for tomorrow, old subscription lists. Returns how many messages went out."""
    from . import yt_auth
    from .actions.youtube import units_day
    now = _aware(now)
    sent = 0
    for row in bot.store.q("SELECT key FROM state WHERE key LIKE 'ytdevice:%'"):
        h = row["key"].split(":", 1)[1]
        try:
            got = yt_auth.poll(bot.store, h, now)
        except Exception:
            yt_auth.end_device(bot.store, h)
            got = "failed"
        if got in (None, "pending"):
            continue
        line = connected_line(bot, h, now) if got == "connected" else _poll_line(got)
        bot._notice(h, line, now)
        sent += 1
    for row in bot.store.q("SELECT key FROM state WHERE key LIKE 'ytrest:%'"):
        h = row["key"].split(":", 1)[1]
        st = bot.store.get_state(row["key"])
        if not st or now < datetime.fromisoformat(st["due"]):
            continue
        bot.store.set_state(row["key"], None)
        person = bot.store.person(h)
        if not person:
            continue
        try:
            line = _run_rest(bot, person, st, now)
        except Exception as e:
            bot.store.add_run(handle=h, kind="youtube_rest", status="error", error=type(e).__name__)
            continue
        if line:
            bot._notice(h, line, now)
            sent += 1
    # what YouTube listed (channel titles) is kept no longer than it is needed: the list 24 hours, a question with no
    # answer 30 minutes, what "undo" needs for its window; the project's unit counters of past days go
    keep = {"ytsubs": SUBS_KEEP, "ytask": ASK_OPEN, "igtap": ASK_OPEN}
    for row in bot.store.q("SELECT key, value FROM state WHERE key LIKE 'ytsubs:%' OR key LIKE 'ytask:%' OR "
                           "key LIKE 'igtap:%' OR key LIKE 'ytundo:%' OR key LIKE 'yt_units:%'"):
        kind = row["key"].split(":", 1)[0]
        if kind == "yt_units":
            if row["key"] < f"yt_units:{units_day(now - timedelta(days=2))}":
                bot.store.x("DELETE FROM state WHERE key=?", (row["key"],))
            continue
        st = bot.store.get_state(row["key"])
        if not st:
            continue
        life = keep.get(kind) or (UNDO_UNSUB if st.get("kind") == "unsub" else UNDO_PLAYLIST)
        if now - datetime.fromisoformat(st["at"]) > life:
            bot.store.set_state(row["key"], None)
    return sent


def _run_rest(bot, person, st, now):
    """The rest of a list the person said yes to, the day after: only channels still subscribed (or, for an undo,
    the same placements); the same lines as the first run."""
    from .actions import perform
    from .actions import youtube as Y
    from .actions.youtube import YtError, token_for
    h = person["handle"]
    if _blocked(bot, h):
        return None
    if st["kind"] == "resub":
        rows = bot.store.placements(h, ids=st["items"])
        if not rows:
            return None
        res = Y.remove(rows, bot.store, now)
        bot.store.remove_placements(res["removed"], now)
        if res.get("stop") in ("too_many", "quota"):
            left = [r["id"] for r in rows if r["id"] in res["failed"]]
            _rest_later(bot, person, "resub", left, len(res["removed"]), res["stop"], now)
            return T.yt_undo_rest(len(res["removed"]), len(rows))
        return T.yt_rest_done(len(res["removed"]), "resub")
    try:
        fresh = {r[0]: r for r in subs(bot, h, _api(bot, h, now), now, fresh=True)}
    except YtError as e:
        return _fail_line(bot, h, e.code, now)
    rows = [tuple(r) for r in st["items"] if r[0] in fresh]   # one the person dropped already is not done again
    if not rows:
        return None
    params = _params_unsub(rows)
    try:
        o = perform("youtube.unsubscribe", _ctx(bot, person, now), params.model_dump(),
                    yes_token=token_for(h, "unsubscribe", params))
    except YtError as e:
        if e.code in ("quota", "too_many"):
            _rest_later(bot, person, "unsub", [list(r) for r in rows], 0, e.code, now)
            return None
        return _fail_line(bot, h, e.code, now)
    return _after_unsub(bot, person, o, len(rows), rows, now, kind="rest")


