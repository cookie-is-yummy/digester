"""PROTOTYPE ONLY - round 11, slice H (DESIGN.md section 18.H): "ask your watch history anything", answered by code.

A history question is about the person's own watching, liking and saving as a record: how much, what, who, when,
first, last, most, change over time. Code reads the message into a small form (`HistoryQuery`), computes the answer
from the library's own files and says it in fixed words. No model writes a number, and no model call is made here.

- What counts. Watched = the watch and view events; liked = likes; saved = saves, collections, posts sent to
  yourself and playlists (attention.KEPT). Every event of interactions.jsonl counts, dated in the person's time
  zone, so a video watched in September and again in October is in both months (LibraryView keeps only the latest
  date of each kind). Friends' posts are never counted (LibraryView leaves them out). A video is counted once per
  window, however often it was watched in it.
- Topic words are the message's content words left after its question, time, platform and kind words are taken out
  ("watching", "most", "this month" are never search words); an item matches when its own text holds one of them
  (`retrieve.contains_word`, the engine's word match). A topic that is exactly a channel's name is that channel.
- The window is always said back with its dates, and an answer whose window touches or passes where the export ends
  says so, with the words that ask for the export steps. A window wholly after the record says it can't see it and
  answers for the latest stretch of the same length it can see.
- Read before the interpreter (`history_reads`, answer_normally after integration_reads) for the clear shapes, and
  after it (`after_interpret`) for a `library_stats` form the code read did not take. A rule made of a history
  question ("send me my top channels every month") is said plainly not to be possible yet, with today's answer.
- Follow-ups for 6 hours while the history answer is the last answer: another window ("and last month?"), a platform
  ("what about instagram"), liked or saved, a new topic ("what about guitar"), "show me them", "more", and a pick by
  number ("the first one": that item, or after a channel ranking, that channel's videos).
"""
import json
import os
import re
import threading
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from .retrieve import contains_word

KINDS = ("top_channels", "top_topics", "top_items", "count", "list", "first", "last", "timeline", "on_day", "compare")
HOW_KINDS = {"watched": ("watch", "view"), "liked": ("like",), "saved": ("save", "collection", "share_self", "playlist"),
             "any": ("watch", "view", "like", "save", "collection", "share_self", "playlist"),
             # the round 11 check (DESIGN 18.X): "did I like or save" never counts a watch
             "liked_saved": ("like", "save", "collection", "share_self", "playlist")}
FOLLOW_HOURS = 6
LIST_MAX, DAY_MAX, FIRST_MAX = 5, 8, 3


class Window(BaseModel):
    kind: Literal["all", "day", "week", "month", "year", "since", "days", "lately", "weekend", "range"] = "all"
    start: Optional[date] = None
    end: Optional[date] = None          # inclusive
    this: bool = False                  # "this week / month / year": up to today


class HistoryQuery(BaseModel):
    """The form a history question is read into (by code, or from the interpreter's library_stats form)."""
    kind: Literal[KINDS]
    how: Literal["watched", "liked", "saved", "any", "liked_saved"] = "watched"
    platform: Optional[Literal["youtube", "instagram"]] = None
    topic: list[str] = Field(default_factory=list, max_length=3)
    channel: Optional[str] = None
    window: Window = Field(default_factory=Window)
    window2: Optional[Window] = None    # compare
    n: int = Field(default=5, ge=1, le=10)
    unit: Literal["items", "channels"] = "items"
    hours: bool = False                 # asked in hours or minutes: videos are counted, never time
    topics_too: bool = False            # "what have I been watching the most": channels, and the profile's topics
    channel_hint: bool = False          # the topic followed "from" or "by", or the message says "channel"
    lang: Literal["en", "es"] = "en"
    offset: int = 0                     # "more" after a list
    by: Optional[Literal["month", "year"]] = None   # timeline: "by year", "per month"


# ====================================== reading the message ======================================================
TYPOS = {"wacth": "watch", "whatch": "watch", "wach": "watch", "watchd": "watched", "wached": "watched",
         "wacthed": "watched", "whatched": "watched", "watchted": "watched", "watchin": "watching",
         "wacthing": "watching", "whatching": "watching", "vidoes": "videos", "vids": "videos", "vid": "video",
         "viedos": "videos", "vidos": "videos", "chanels": "channels", "channles": "channels", "chanel": "channel",
         "channnels": "channels", "wich": "which", "whcih": "which", "wat": "what", "wht": "what", "whta": "what",
         "yt": "youtube", "ig": "instagram", "insta": "instagram", "u": "you", "ive": "i've", "im": "i'm",
         "yesteday": "yesterday", "yday": "yesterday", "lst": "last", "mnth": "month", "wk": "week",
         "mosty": "most", "mostt": "most", "fav": "favourite", "fave": "favourite", "hw": "how", "mny": "many",
         "dd": "did", "frist": "first", "fisrt": "first", "sept": "september",
         # the round 11 check (DESIGN 18.X): "this yr" was searched as the topic "yr"
         "yr": "year", "yrs": "years", "wks": "weeks", "mnths": "months", "ystrday": "yesterday",
         "yesterdy": "yesterday", "wkend": "weekend", "wknd": "weekend"}
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]
MON_ABBR = {m[:3]: i + 1 for i, m in enumerate(MONTHS)} | {"sept": 9}
MONTH_ES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
            "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DAYS_ES = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
NUM = {"one": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
       "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "couple": 2, "a couple of": 2, "few": 3, "a few": 3,
       "un": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
       "diez": 10}
_MONTH_RE = r"(?:" + "|".join(MONTHS + ["jan", "feb", "mar", "apr", "jun", "jul", "aug", "sept", "sep", "oct", "nov",
                                        "dec"]) + r")"
_DAY_RE = r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tues|tue|wed|thurs|thu|fri|sat|sun)"
_NUM_RE = r"(?:\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|a couple of|a few|few|couple)"
_NUM_ES = r"(?:\d{1,3}|un|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)"
_UNIT_ES = {"dia": "day", "dias": "day", "semana": "week", "semanas": "week", "mes": "month", "meses": "month",
            "ano": "year", "anos": "year"}


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normal(text):
    """Lower case, plain apostrophes, no accents, common typos fixed: what the reads below see."""
    t = strip_accents(unicodedata.normalize("NFKC", text or "")).lower()
    t = t.replace("’", "'").replace("‘", "'").replace("¿", " ").replace("¡", " ")
    t = re.sub(r"\b[a-z]+\b", lambda m: TYPOS.get(m.group(0), m.group(0)), t)
    t = re.sub(r"\bwhats\b", "what's", t)
    return " ".join(t.split())


# ---------- what is never a history question ----------
REMIND = re.compile(r"\b(?:remind|reminder|recuerdame|recordarme|alarm)\b")
SENDING = re.compile(r"\b(?:send|text|email|e-mail|mail|notify|ping|message|dm|tell|give|update|alert|show|envia\w*|"
                     r"mandame|manda|avisame)\b")
EVERY = re.compile(r"\b(?:every|each|daily|weekly|monthly|nightly|whenever|from now on|once a|cada|todos los|"
                   r"todas las)\b")
EVERY_TIMED = re.compile(r"\b(?:every|each|cada)\s+(?:other\s+)?(?:" + _DAY_RE + r"s?|morning|evening|night|day|"
                         r"weekend|weekday|lunes|martes|miercoles|jueves|viernes|sabado|domingo|dia|manana|noche)\b|"
                         r"\b(?:daily|weekly|nightly|from now on|whenever)\b")
ACTING = re.compile(r"\b(?:add|put|bookmark|unsubscribe|delete|remove|cancel|stop|pause|resume|calendar|to-?do|"
                    r"my list|email|e-mail|forward|share it|agrega|anade|borra)\b|"
                    r"\bsave (?:it|this|that|them|those)\b(?!\s+(?:week|month|year))")
SEARCHING = re.compile(
    r"\b(?:should i|shall i|what to watch|something (?:new )?to watch|anything to watch|to watch (?:tonight|today|"
    r"tomorrow|this weekend|next|now|later)|recommend\w*|suggest\w*|find|search|look(?:ing)? for|that (?:video|reel|"
    r"post|one|clip|short)|the (?:video|reel|post|clip|short) (?:where|that|with|about|on)|a (?:video|reel|post|"
    r"clip) (?:where|that|with|about|on)|what did (?:that|the|this|it)\b|say(?:s)? about|said about|summar\w*|"
    r"learn\w*|key points|main ideas|teach\w*|explain\w*|similar|like the ones|good (?:movie|show|video|channel)s?|"
    r"best (?:channel|video|tutorial)s?|debo|deberia|recomienda\w*|busca\w*)\b")
BOT_ASK = re.compile(r"\b(?:you|your)\b(?!\s*tube)")   # "what did you do for me", "who can see what i watch"
WHO_CAN = re.compile(r"\bwho\s+(?:can|could|else)\b|\bprivate\b|\bdelete\b")

# ---------- the history markers ----------
_VERB = r"(?:watch|watched|watching|rewatch\w*|re-watch\w*|saved|save|liked|like|seen|viewed|view)"
MARKERS = [
    re.compile(r"\bi(?:'ve|'d|'m| have| had| was| am)?\s+(?:been\s+|ever\s+|first\s+|last\s+|usually\s+|mostly\s+|"
               r"actually\s+|really\s+|even\s+|just\s+|recently\s+|already\s+|most\s+)*" + _VERB + r"\b"),
    re.compile(r"\b(?:did|do|have|had|was|am)\s+i\s+(?:\w+\s+){0,2}?" + _VERB + r"\b"),
    re.compile(r"\bi\s+(?:start|started|began|begin)\s+(?:watching|to watch|saving|liking)\b"),
    re.compile(r"\bmy\s+(?:\w+\s+)?(?:watch|viewing|watching)\s+history\b|\bwatch\s+history\b"),
    re.compile(r"\bmy\s+(?:[\w&'-]+\s+){0,2}(?:watching|viewing)\b"),
    re.compile(r"\bmy\s+(?:most\s+|top\s+)?(?:watched|viewed|rewatched|liked|saved)\b"),
    re.compile(r"\bmy\s+top\s+(?:\d+\s+|five\s+|ten\s+)?(?:channels|youtubers|creators)\b"),
    re.compile(r"\b(?:videos?|reels?|posts?|channels?)\s+(?:i\s+)?(?:watched|liked|saved|viewed)\s+(?:per|by|each|in|"
               r"this|last|since|on)\b"),
    # Spanish (accents removed by normal())
    re.compile(r"\b(?:he|has|hemos)\s+(?:estado\s+)?(?:visto|viendo|guardado|mirado)\b|\bvi\b|\bveo\b|\bmire\b|"
               r"\bguarde\b|\bme\s+gust(?:o|aron)\b|\bempece\s+a\s+ver\b|\bestuve\s+viendo\b|\bmi\s+historial\b"),
]
TOP_PLAIN = re.compile(r"^\W*(?:my\s+)?top\s+(?:\d+\s+|five\s+|ten\s+)?(?:channels|youtubers|creators)\b")
STATEMENT = re.compile(r"^\W*(?:i|i've|i'm|i was|yo|lol|haha)\b")
QUESTION = re.compile(r"\?|^\W*(?:what|which|who|when|how|show|list|tell|give|did|do|have|was|is|are|since|"
                      r"que|cual|cuales|cuantos|cuantas|cuando|desde|quien|muestrame|dime)\b|"
                      r"^\W*(?:the\s+)?(?:my\s+)?(?:top|most|first|last|latest|earliest|watch history|videos?|"
                      r"channels?)\b")
SPANISH = re.compile(r"\b(?:que|cuantos|cuantas|cuando|canales|vi|veo|visto|ayer|hoy|este mes|el mes pasado|"
                     r"semana|empece|ver|videos de|historial|mas)\b")

# ---------- the kind ----------
HOURS = re.compile(r"\b(?:hours?|minutes?|time spent|how long|horas|minutos)\b")
COMPARE = re.compile(r"\b(?:more|less|fewer|vs\.?|versus|compared?|comparison|than|or|mas|menos)\b")
TOP_ITEMS = re.compile(r"\b(?:re-?watch\w*|more than once|over and over|(?:watched|viewed)\s+(?:the\s+)?most\s+"
                       r"(?:times|often)|most\s+(?:watched|viewed|played)\s+(?:videos?|reels?|clips?)|"
                       r"(?:videos?|reels?)\s+(?:that\s+)?i(?:'ve| have)?\s+watched\s+(?:the\s+)?most|"
                       r"top\s+(?:\d+\s+)?(?:videos?|reels?)\s+i(?:'ve| have)?\s+watched)\b")
TIMELINE = re.compile(r"\b(?:which|what)\s+(?:month|year)\b|\bmost\s+(?:watched\s+)?(?:month|year)\b|"
                      r"\bbusiest\b|"
                      r"\b(?:over time|over the (?:years|months)|changed?|changing|trends?|trending|grown|growing|"
                      r"(?:by|per|each|every|a)\s+(?:month|year)|monthly|yearly|month by month|year by year|"
                      r"por mes|cada mes|por ano|cada ano)\b")
FIRST = re.compile(r"\b(?:first|earliest|since when|start(?:ed)?\s+(?:watching|to watch)|began|begin|primer\w*|"
                   r"empece|desde cuando)\b")
LAST = re.compile(r"\b(?:last|latest|most recent|newest|ultim[oa]s?|mas reciente)\b")
COUNT = re.compile(r"\b(?:how many|how much|number of|count|total|cuant[oa]s?)\b")
CHANNEL_WORD = re.compile(r"\b(?:channels?|youtubers?|creators?|accounts?|who|canal(?:es)?)\b")
RANK_WORD = re.compile(r"\b(?:most|top|favou?rite\w*|which|what|ranking|rank\w*|mas|que|cuales)\b")
TOPIC_WORD = re.compile(r"\b(?:topics?|subjects?|kinds? of|types? of|categor\w+|genres?|temas?)\b")
MOST = re.compile(r"\b(?:watch\w*|view\w*|liked?|saved?|see|seen|veo|visto|vi)\s+(?:the\s+)?most\b|"
                  r"\bmost\s+(?:watched|viewed|liked|saved|often|of all)\b|\bmas\b")
LISTING = re.compile(r"\b(?:what|which|show|list|tell me|que|muestrame|dime)\b|\bwatch history\b")
# time words a window should have taken (the round 11 check); "may" is a verb as often as a month
LEFT_TIME = re.compile(r"\b(?:days?|weeks?|weekends?|months?|years?|ago|dias?|semanas?|meses|anos?|" +
                       "|".join(m for m in MONTHS if m != "may") + "|" + "|".join(MONTH_ES) + r")\b")
TOP_N = re.compile(r"\btop\s+(\d{1,2}|five|ten|three)\b")
ONE_DAY = re.compile(r"\b(?:on|el)\s+(?:the\s+)?\w+")

# ---------- words that are never a topic ----------
STOP = set("""
i i've i'd i'm me my mine myself you your what what's which who whom when where how why many much number count total
totals did do does done have has had having been be being was were is are am will would could can the a an of on in at
to for about from by with that this these those it its it's them they their there here most more less fewer least top
first last latest earliest newest oldest recent recently ever all any some every each per than vs versus or and but so
ok okay hey hi please pls just really actually even usually mostly again also still ago time times once twice over
changed change changing trend trends trending grown growing history watch watched watching watches rewatch rewatched
rewatching view viewed views viewing see seen saw save saved saves saving like liked likes liking kept keep started
start starting began begin since show list tell give something anything stuff things thing content video videos clip
clips reel reels post posts short shorts channel channels youtuber youtubers creator creators account accounts topic
topics subject subjects kind kinds type types categories category genre genres related around involving regarding
compared compare comparison month months week weeks year years day days monthly yearly ranking rank ranked favorite
favourite favorites favourites youtube instagram overall altogether lately often frequently hours hour minutes minute
spent then before after now today yesterday far lol haha lot lots ones one two three four five six seven eight nine ten
eleven twelve couple few past previous current whole entire interest interests into habit habits played play playing
other else exactly roughly approximately about average usual normally more_than ranking order ordered
que cuantos cuantas cuando cual cuales he has ha hemos visto vi veo ver viendo mire mirado guardado guarde gusto
gustaron yo el la los las un una unos unas de del sobre en este esta estos estas ese esa mes meses semana semanas ano
anos dia dias hoy ayer pasado pasada ultimo ultima ultimos ultimas primer primero primera empece a al videos video
canales canal mas menos y o por cada desde historial cosas contenido publicaciones temas tema estado mi mis me
fue fueron es son era eran sido ser lo le les se su sus algo alguno alguna algun nada todo todos toda todas mucho muchos
mucha muchas cuanto cuanta cosa veces vez hace entre hasta para con sin ni tu tus te ago between until till
""".split())
PLATFORM_WORDS = {"youtube": "youtube", "instagram": "instagram"}


def _num(s):
    s = (s or "").strip()
    return int(s) if s.isdigit() else NUM.get(s)


def _month_start(y, m):
    return date(y, m, 1)


def _month_end(y, m):
    return (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))


def _past_month(m, today):
    """The most recent month `m` that has begun: this year's when it has, else last year's."""
    return today.year if m <= today.month else today.year - 1


def _past_day(m, d, today, year=None):
    if year:
        return date(year, m, d)
    if (m, d) == (2, 29):   # the round 11 check (DESIGN 18.X): the latest 29 February, never another window
        y = today.year
        while True:
            try:
                x = date(y, 2, 29)
            except ValueError:
                y -= 1
                continue
            if x <= today:
                return x
            y -= 1
    try:
        x = date(today.year, m, d)
    except ValueError:
        return None
    return x if x <= today else date(today.year - 1, m, d)


def _weekday_back(wd, today, strictly_before):
    back = (today.weekday() - wd) % 7
    if back == 0 and strictly_before:
        back = 7
    return today - timedelta(days=back)


def _win(kind, start, end, this=False):
    return Window(kind=kind, start=start, end=end, this=this)


def find_windows(t, today):
    """[(Window, (start, end) of the words)] in the order the message says them; the words of each are taken out of
    the topic. "since" before a window makes it run to today."""
    found = []
    taken = []

    def add(m, w, grp=0):
        s, e = m.span(grp)
        if any(s < b and a < e for a, b in taken):
            return
        taken.append((s, e))
        found.append((s, w, (s, e)))

    def rx(p):
        return re.finditer(p, t)
    # ---- the round 11 check (DESIGN 18.X): "2 weeks ago", weekends, Spanish "los ultimos 7 dias" ----
    for m in rx(r"\b(" + _NUM_RE + r"|an?)\s+(day|week|month|year)s?\s+ago\b|\bhace\s+(" + _NUM_ES +
                r")\s+(dias?|semanas?|meses|mes|anos?)\b"):
        n = _num(m.group(1) or m.group(3)) or 1
        unit = m.group(2) or _UNIT_ES[m.group(4)]
        if unit == "day":
            d = today - timedelta(days=n)
            add(m, _win("day", d, d))
        elif unit == "week":
            mon = today - timedelta(days=today.weekday() + 7 * n)
            add(m, _win("week", mon, mon + timedelta(days=6)))
        elif unit == "month":
            y, mo = today.year, today.month - n
            while mo < 1:
                y, mo = y - 1, mo + 12
            add(m, _win("month", _month_start(y, mo), _month_end(y, mo)))
        else:
            add(m, _win("year", date(today.year - n, 1, 1), date(today.year - n, 12, 31)))
    for m in rx(r"\b(?:(?:on|over|during)\s+)?(?:this\s+past|last|the\s+past|past|the|this)\s+weekend\b|"
                r"\b(?:el\s+)?fin\s+de\s+semana(?:\s+pasado)?\b"):
        w = m.group(0)
        sat = today - timedelta(days=(today.weekday() - 5) % 7)          # the latest Saturday up to today
        if today.weekday() >= 5 and re.search(r"\b(?:last|pasado)\b", w):
            sat -= timedelta(days=7)                                    # on a weekend, "last weekend" is the one before
        add(m, _win("weekend", sat, sat + timedelta(days=1)))
    for m in rx(r"\b(?:en\s+)?(?:los|las)\s+ultim[oa]s\s+(" + _NUM_ES + r")\s+(dias|semanas|meses|anos)\b|"
                r"\b(?:en\s+)?(?:la|el)\s+ultim[oa]\s+(semana|mes|ano)\b"):
        n = _num(m.group(1)) or 1 if m.group(1) else 1
        unit = _UNIT_ES[m.group(2) or m.group(3)]
        days = {"day": 1, "week": 7, "month": 30, "year": 365}[unit] * n
        add(m, _win("days", today - timedelta(days=days - 1), today))
    for m in rx(r"\b(?:(?:in|over|during|for|within)\s+)?(?:the\s+)?(?:last|past|previous)\s+(" + _NUM_RE +
                r")\s+(day|week|month|year)s?\b"):
        n = _num(m.group(1)) or 1
        days = {"day": 1, "week": 7, "month": 30, "year": 365}[m.group(2)] * n
        add(m, _win("days", today - timedelta(days=days - 1), today))
    for m in rx(r"\b(?:(?:in|over|during|for)\s+)?the\s+(?:last|past)\s+(week|month|year)\b|"
                r"\b(?:in|over)\s+the\s+(?:last|past)\s+(week|month|year)\b|\bpast\s+(week|month|year)\b"):
        unit = next(g for g in m.groups() if g)
        days = {"week": 7, "month": 30, "year": 365}[unit]
        add(m, _win("days", today - timedelta(days=days - 1), today))
    for m in rx(r"\b(?:this|the current|so far this)\s+(week|month|year)\b|\b(?:esta)\s+(semana)\b|"
                r"\b(?:este)\s+(mes|ano)\b"):
        unit = {"semana": "week", "mes": "month", "ano": "year"}.get(next(g for g in m.groups() if g),
                                                                    next(g for g in m.groups() if g))
        start = {"week": today - timedelta(days=today.weekday()), "month": today.replace(day=1),
                 "year": date(today.year, 1, 1)}[unit]
        add(m, _win(unit, start, today, this=True))
    for m in rx(r"\b(?:last|previous)\s+(week|month|year)\b|\b(?:la\s+)?(semana)\s+pasada\b|"
                r"\b(?:el\s+)?(mes|ano)\s+pasado\b"):
        unit = {"semana": "week", "mes": "month", "ano": "year"}.get(next(g for g in m.groups() if g),
                                                                    next(g for g in m.groups() if g))
        if unit == "week":
            mon = today - timedelta(days=today.weekday() + 7)
            add(m, _win("week", mon, mon + timedelta(days=6)))
        elif unit == "month":
            y, mo = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
            add(m, _win("month", _month_start(y, mo), _month_end(y, mo)))
        else:
            add(m, _win("year", date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)))
    for m in rx(r"\b(?:the\s+)?(week|month|year)\s+before(?:\s+that)?\b|\b(?:el\s+)?(mes)\s+anterior\b"):
        found.append((m.start(), "before:" + ({"mes": "month"}.get(m.group(2) or "", m.group(1) or "month")),
                      m.span()))
        taken.append(m.span())
    for m in rx(r"\b(?:so far\s+)?today\b|\bhoy\b"):
        add(m, _win("day", today, today))
    for m in rx(r"\byesterday\b|\bayer\b"):
        y = today - timedelta(days=1)
        add(m, _win("day", y, y))
    for m in rx(r"(?:\bnew year'?s eve\b|\bnew year'?s(?: day)?\b|\bchristmas eve\b|\bchristmas(?: day)?\b|"
                r"\bhalloween\b|\bvalentine'?s(?: day)?\b)(?:,?\s+(?:of\s+|in\s+)?((?:19|20)\d\d)\b)?"):
        w = m.group(0)
        md = (12, 31) if "eve" in w and "new" in w else (1, 1) if "new" in w else (12, 24) if "eve" in w else \
            (12, 25) if "christmas" in w else (10, 31) if "halloween" in w else (2, 14)
        # the round 11 check (DESIGN 18.X): "halloween 2025" is that year's, never this year's with 2025 dropped
        d = date(int(m.group(1)), *md) if m.group(1) else _past_day(*md, today)
        add(m, _win("day", d, d))
    for m in rx(r"\b(?:on\s+)?(" + _MONTH_RE + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b(?:,?\s+(\d{4}))?|"
                r"\b(?:on\s+)?(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(" + _MONTH_RE + r")\b(?:,?\s+(\d{4}))?|"
                r"\b(?:el\s+)?(\d{1,2})\s+de\s+(" + "|".join(MONTH_ES) + r")\b(?:\s+de\s+(\d{4}))?"):
        g = m.groups()
        if g[0]:
            mo, dd, yy = MON_ABBR.get(g[0][:4] if g[0].startswith("sept") else g[0][:3]), int(g[1]), g[2]
        elif g[4]:
            mo, dd, yy = MON_ABBR.get(g[4][:4] if g[4].startswith("sept") else g[4][:3]), int(g[3]), g[5]
        else:
            mo, dd, yy = MONTH_ES[g[7]], int(g[6]), g[8]
        if not mo or not 1 <= dd <= 31:
            continue
        try:
            d = _past_day(mo, dd, today, int(yy) if yy else None)
        except ValueError:
            d = None
        if d:
            add(m, _win("day", d, d))
    for m in rx(r"\b(?:(?:on|last|this past|this)\s+)?(" + _DAY_RE + r")\b|\b(?:el\s+)?(" + "|".join(DAYS_ES) +
                r")(?:\s+pasado)?\b"):
        word = m.group(1) or m.group(2)
        if m.group(1):
            if word in ("sat", "sun", "mon", "wed") and not re.match(r"(?:on|last|this)\b", m.group(0)):
                continue   # "sun", "sat" alone are words, not days
            wd = next(i for i, d in enumerate(DAYS) if d.startswith(word[:3]))
        else:
            wd = DAYS_ES.index(word)
        d = _weekday_back(wd, today, strictly_before=m.group(0).startswith("last") or "pasado" in m.group(0))
        add(m, _win("day", d, d))
    for m in rx(r"\b(?:(?:in|during|for|of|from|since|en|desde)\s+)?(?:(?:the\s+)?month\s+of\s+)?(" + _MONTH_RE +
                r")\b(?:,?\s+(?:of\s+)?(\d{4}))?|\b(?:(?:en|desde|de)\s+)?(" + "|".join(MONTH_ES) +
                r")\b(?:\s+(?:de|del)\s+(\d{4}))?"):
        g = m.groups()
        name = g[0] or g[2]
        if g[0] and name == "may" and not g[1] and not re.match(r"(?:in|during|for|of|from|since)\b", m.group(0)):
            continue
        if g[0] and name in ("mar", "jun", "jan", "dec", "nov", "oct", "aug", "apr", "feb", "jul", "sep") \
                and not g[1] and not re.match(r"(?:in|during|for|of|from|since)\b", m.group(0)):
            continue
        mo = MONTH_ES.get(name) or MON_ABBR.get(name[:4] if name.startswith("sept") else name[:3])
        yy = int(g[1] or g[3]) if (g[1] or g[3]) else _past_month(mo, today)
        add(m, _win("month", _month_start(yy, mo), _month_end(yy, mo)))
    for m in rx(r"\b(?:(?:in|during|for|of|from|since|en|desde|del)\s+)?((?:19|20)\d\d)\b"):
        y = int(m.group(1))
        add(m, _win("year", date(y, 1, 1), date(y, 12, 31)))
    for m in rx(r"\b(?:lately|recently|these days|of late|ultimamente|recientemente)\b"):
        add(m, _win("lately", None, None))
    # the round 11 check (DESIGN 18.X): "between oct 1 and oct 10", "from march to may": one range, never the first only
    wins = sorted((x for x in found if isinstance(x[1], Window) and x[1].start), key=lambda x: x[0])
    for (s1, w1, sp1), (s2, w2, sp2) in zip(wins, wins[1:]):
        if ((re.search(r"\b(?:between|from|entre|del?)\s+(?:the\s+)?$", t[:sp1[0]]) or
             re.match(r"(?:between|from|entre)\b", t[sp1[0]:])) and
                re.fullmatch(r"\s*(?:and|to|until|till|through|thru|-|y|a|al|hasta)\s+(?:the\s+)?", t[sp1[1]:sp2[0]])
                and w2.end and w1.start <= w2.end):
            found = [x for x in found if x[0] not in (s1, s2)]
            found.append((s1, _win("range", w1.start, w2.end), (sp1[0], sp2[1])))
            taken.append((sp1[0], sp2[1]))
            break
    # "since <window>": from its start to today; a window never runs past today ("in 2026" is up to today)
    found = [(s, _win(w.kind, w.start, min(w.end, today) if w.end else w.end, w.this) if isinstance(w, Window) else w,
              span) for s, w, span in found]
    out = []
    for s, w, span in sorted(found, key=lambda x: x[0]):
        if isinstance(w, Window) and re.search(r"\b(?:since|desde)\s+(?:the\s+)?(?:start\s+of\s+)?$", t[:s] + " ") \
                and w.start:
            w = _win("since", w.start, today)
            span = (t.rfind("since", 0, s + 1) if "since" in t[:s + 6] else t.rfind("desde", 0, s + 1), span[1])
        elif isinstance(w, Window) and re.match(r"(?:since|desde)\b", t[s:]) and w.start:
            w = _win("since", w.start, today)
        out.append((w, span))
    return out


def _topic_and_platform(t, spans):
    """(topic phrases, platform, how) from the words outside the windows."""
    rest = list(t)
    for a, b in spans:
        for i in range(a, b):
            rest[i] = " "
    rest = "".join(rest)
    platform = None
    if re.search(r"\byoutube\b", rest):
        platform = "youtube"
    if re.search(r"\binstagram\b", rest):
        platform = None if platform else "instagram"
    how = "watched"
    if re.search(r"\b(?:liked|like|likes|me gusto|me gustaron|di like)\b", rest):
        how = "liked"
    if re.search(r"\b(?:saved|save|saves|bookmarked|guarde|guardado|guardados)\b", rest):
        how = "saved" if how == "watched" else "liked_saved"
    if re.search(r"\b(?:watch\w*|viewed|seen|visto|vi|veo|viendo)\b", rest) and how != "watched":
        how = "watched" if how == "liked" and re.search(r"\bwatch\w*\b", rest) and not re.search(r"\bliked\b", rest) \
            else how
    toks = re.findall(r"[a-z0-9&'+.#-]+", rest)
    runs, cur = [], []
    for w in toks:
        w2 = w.strip(".'-")
        if (not w2 or w2 in STOP or w2.isdigit() or w2 in MONTHS or w2 in MON_ABBR or w2 in MONTH_ES
                or w2 in DAYS or w2 in DAYS_ES or re.fullmatch(_DAY_RE, w2) or re.fullmatch(r"\d+(?:st|nd|rd|th)", w2)
                or w2 in ("what's", "i've", "i'm", "it's", "i'd")):
            if cur:
                runs.append(cur)
            cur = []
            continue
        cur.append(w2)
    if cur:
        runs.append(cur)
    return [" ".join(r) for r in runs if r], platform, how


def read(text, today, loose=False):
    """A HistoryQuery for a history question, else None. `loose`: the interpreter already called it a question about
    the library (library_stats), so the history markers are not needed."""
    raw = " ".join((text or "").split())
    if not raw or len(raw) > 200:
        return None
    t = normal(raw)
    if REMIND.search(t) or ACTING.search(t) or SEARCHING.search(t) or WHO_CAN.search(t):
        return None
    if EVERY_TIMED.search(t) or (EVERY.search(t) and SENDING.search(t)):
        return None
    if BOT_ASK.search(t):
        return None
    marked = any(m.search(t) for m in MARKERS) or bool(TOP_PLAIN.match(t))
    if not marked and not loose:
        return None
    if STATEMENT.match(t) and "?" not in raw and not loose:
        return None
    if not QUESTION.search(t) and not loose:
        return None
    lang = "es" if SPANISH.search(t) and not re.search(r"\b(?:what|how|which|when|did|watch\w*)\b", t) else "en"
    if not loose and re.search(r"\b(?:saved?|saves|guarde|guardado)\b", t) and not re.search(
            r"\b(?:watch\w*|liked?|visto|vi|veo)\b", t):
        # saves stay where they were: "what did I save this week" is the recent answer, "how many recipes have I
        # saved" the library count (rule eval t-dev-014 and t-dev-049); the interpreter's form brings a dated one here
        return None
    wins = find_windows(t, today)
    spans = [s for _, s in wins]
    windows = [w for w, _ in wins if isinstance(w, Window)]
    before = next((w for w, _ in wins if isinstance(w, str)), None)
    topic, platform, how = _topic_and_platform(t, spans)
    hint = bool(topic) and len(topic) == 1 and bool(
        re.search(r"\b(?:from|by)\s+(?:the\s+)?" + re.escape(topic[0]) + r"\b", t)
        or re.search(r"\bchannel\b", t))
    if sum(len(x.split()) for x in topic) > 4 or len(topic) > 3:
        return None    # a longer request than a history question: the interpreter reads it
    rest = "".join(t[i] if not any(a <= i < b for a, b in spans) else " " for i in range(len(t)))
    if LEFT_TIME.search(TIMELINE.sub(" ", rest)):
        # the round 11 check (DESIGN 18.X): time words no window took ("the first week of october", "2 wks back",
        # "a day") are never answered as another window or as all time: the interpreter reads the message
        return None
    q = {"lang": lang, "topic": topic, "platform": platform, "how": how, "channel_hint": hint}
    m = TOP_N.search(t)
    if m:
        q["n"] = min(_num(m.group(1)) or 5, 10)
    q["hours"] = bool(HOURS.search(t))
    w1 = windows[0] if windows else Window()
    if before and windows:
        w2 = _before(windows[0], before.split(":", 1)[1])
        windows = [windows[0], w2] if w2 else windows
    if len(windows) >= 2 and COMPARE.search(rest):
        q.update(kind="compare", window=windows[0], window2=windows[1])
    elif TOP_ITEMS.search(rest):
        q.update(kind="top_items", window=w1, topic=[x for x in topic if x not in ("times", "often")])
    elif TIMELINE.search(rest):
        q.update(kind="timeline", window=w1,
                 by="year" if re.search(r"\b(?:year|years|yearly|ano|anos)\b", rest) else
                 "month" if re.search(r"\b(?:month|monthly|mes)\b", rest) else None)
    elif FIRST.search(rest) and not re.search(r"\bfirst\s+(?:one|1)\b", rest):
        q.update(kind="first", window=w1)
    elif COUNT.search(rest) or (topic and re.match(r"\W*(?:have|did)\s+i\s+(?:ever\s+)?(?:watch\w*|seen|see)\s+"
                                                   r"(?:any|anything|something|videos?)\b", t)):
        # "have I watched anything about knitting": how many, so the answer says yes or no with its count
        q.update(kind="count", window=w1,
                 unit="channels" if CHANNEL_WORD.search(rest) and not topic else "items")
    elif windows and not topic and re.match(r"\W*(?:have|did)\s+i\s+(?:ever\s+)?(?:watch\w*|see|seen)\s+"
                                            r"(?:any|anything|something|videos?)\b", t):
        # the round 11 check (DESIGN 18.X): "did I watch anything on nov 10" lists that day
        q.update(kind="on_day" if w1.kind == "day" else "list", window=w1)
    elif LAST.search(rest):
        q.update(kind="last", window=w1)
    elif TOPIC_WORD.search(rest) and MOST.search(rest):
        q.update(kind="top_topics", window=w1)
    elif CHANNEL_WORD.search(rest) and RANK_WORD.search(rest):
        q.update(kind="top_channels", window=w1)
    elif MOST.search(rest):
        q.update(kind="top_channels", window=w1, topics_too=not topic)
    elif w1.kind == "day" and LISTING.search(t):
        q.update(kind="on_day", window=w1)
    elif LISTING.search(t) and (windows or not topic):
        q.update(kind="list", window=w1 if windows else _win("lately", None, None))
    else:
        return None
    if q["kind"] == "count" and w1.kind == "day":
        pass
    if q["kind"] == "list" and q["window"].kind == "day":
        q["kind"] = "on_day"
    if q["kind"] in ("top_channels", "top_topics") and q.get("unit") == "channels":
        q.pop("unit")
    return HistoryQuery(**q)


def _before(w, unit):
    if not w.start:
        return None
    if unit == "month":
        y, m = (w.start.year, w.start.month - 1) if w.start.month > 1 else (w.start.year - 1, 12)
        return _win("month", _month_start(y, m), _month_end(y, m))
    if unit == "year":
        return _win("year", date(w.start.year - 1, 1, 1), date(w.start.year - 1, 12, 31))
    mon = w.start - timedelta(days=w.start.weekday() + 7)
    return _win("week", mon, mon + timedelta(days=6))


# ====================================== the record ================================================================
_INDEX = {}
_LOCK = threading.Lock()


class Record:
    """Every dated event of the view's items, as local dates: {item_id: [(date, kind)]}, with where each platform's
    export ends (its newest event of any kind) and starts."""

    def __init__(self, view, tz):
        zone = ZoneInfo(tz)
        self.events = defaultdict(list)
        path = os.path.join(view.lib, "corpus", "interactions.jsonl")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    it = view.items.get(r.get("item_id"))
                    at = r.get("at")
                    if it is None or not at or r.get("kind") == "share_friend":
                        continue
                    try:
                        d = datetime.fromisoformat(at)
                    except ValueError:
                        continue
                    d = d.astimezone(zone).date() if d.tzinfo else d.date()
                    self.events[it.id].append((d, r["kind"]))
        self.ends, self.starts = {}, {}
        for iid, evs in self.events.items():
            evs.sort()
            p = view.items[iid].platform
            if p not in self.ends or evs[-1][0] > self.ends[p]:
                self.ends[p] = evs[-1][0]
            for d, k in evs:
                key = (p, k)
                if key not in self.starts or d < self.starts[key]:
                    self.starts[key] = d


def record(view, tz):
    path = os.path.join(view.lib, "corpus", "interactions.jsonl")
    try:
        st = os.stat(path)
        stamp = (st.st_mtime_ns, st.st_size)
    except OSError:
        stamp = None
    key = (id(view), view.lib, tz, stamp)
    with _LOCK:
        r = _INDEX.get(key)
        if r is None:
            _INDEX.clear()   # one library at a time is plenty for a prototype
            r = _INDEX[key] = Record(view, tz)
        return r


# ====================================== computing the answer ======================================================
def _scope_platforms(q, view, rec):
    kinds = set(HOW_KINDS[q.how])
    plats = {p for (p, k) in rec.starts if k in kinds}
    if q.platform:
        plats = {q.platform}
    return sorted(plats) or ([q.platform] if q.platform else [])


def resolve(w, rec, plats, today):
    """(start, end) of a window; None for an open end. "lately" is the 4 weeks up to where the record ends."""
    if w.kind == "lately":
        end = max((rec.ends[p] for p in plats if p in rec.ends), default=today)
        return end - timedelta(days=27), end
    return w.start, w.end


def matches(it, q, channel_key=None):
    if channel_key is not None:
        # the round 11 check (DESIGN 18.X): the channel's own name, as the ranking counts it, so an Instagram
        # account of the same name ("@orbit.kitchen") is never added to the YouTube channel's count
        return (it.creator or "") == q.channel
    if not q.topic:
        return True
    text = it.caption or ""
    return any(contains_word(text, x) for x in q.topic)


def _squash(s):
    return re.sub(r"[\W_]+", "", strip_accents((s or "").lower()))


def channel_of(view, phrase):
    """The display name of the creator whose name is exactly the phrase (case, spaces, '@' and punctuation
    ignored), else None."""
    key = _squash(phrase)
    if len(key) < 3:
        return None
    named = Counter(it.creator for it in view.items.values() if it.creator and _squash(it.creator) == key)
    if not named:
        return None
    # the name with the most items (a YouTube channel before an Instagram account of the same name on a tie)
    return max(named, key=lambda c: (named[c], not c.startswith("@"), c))


def hits(view, rec, q, start, end, plats):
    """{item_id: [dates in the window of the counted kinds]} for the items that match the query."""
    kinds = set(HOW_KINDS[q.how])
    ckey = _squash(q.channel) if q.channel else None
    out = {}
    for iid, evs in rec.events.items():
        it = view.items.get(iid)
        if it is None or it.platform not in plats:
            continue
        ds = [d for d, k in evs if k in kinds and (start is None or d >= start) and (end is None or d <= end)]
        if not ds or not matches(it, q, ckey):
            continue
        out[iid] = ds
    return out


# ====================================== the words =================================================================
MONTH_EN = [m.capitalize() for m in MONTHS]
MONTHS_ES_LIST = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
                  "noviembre", "diciembre"]
WEEKDAY_EN = [d.capitalize() for d in DAYS]
WEEKDAY_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
PNAME = {"youtube": "YouTube", "instagram": "Instagram"}
# the words in quotes are the ones refresh.export_reads (hook 5a) answers with the steps
REFRESH = {"en": "For newer history, send me a new export (ask \"how do I send you a new export?\" for the steps).",
           "es": "Para ver historial más reciente, mándame una exportación nueva (escribe \"how do I send you a new "
                 "export?\" y te doy los pasos)."}


def day_words(d, lang="en", weekday=False):
    if lang == "es":
        s = f"{d.day} de {MONTHS_ES_LIST[d.month - 1]} de {d.year}"
        return f"{WEEKDAY_ES[d.weekday()]} {s}" if weekday else s
    s = f"{d.day} {MONTH_EN[d.month - 1]} {d.year}"
    return f"{WEEKDAY_EN[d.weekday()]} {s}" if weekday else s


def short_day(d, lang="en", today=None):
    if lang == "es":
        s = f"{d.day} {MONTHS_ES_LIST[d.month - 1][:3]}"
    else:
        s = f"{d.day} {MONTH_EN[d.month - 1][:3]}"
    return s if today is not None and d.year == today.year else s + f" {d.year}"


def span_words(a, b, lang="en"):
    """'9 to 15 November 2026', '21 October to 19 November 2026', '20 December 2025 to 3 January 2026'."""
    if a == b:
        return day_words(a, lang)
    to = " a " if lang == "es" else " to "
    if lang == "es":
        if a.year == b.year and a.month == b.month:
            return f"{a.day}{to}{day_words(b, lang)}"
        if a.year == b.year:
            return f"{a.day} de {MONTHS_ES_LIST[a.month - 1]}{to}{day_words(b, lang)}"
        return day_words(a, lang) + to + day_words(b, lang)
    if a.year == b.year and a.month == b.month:
        return f"{a.day}{to}{day_words(b, lang)}"
    if a.year == b.year:
        return f"{a.day} {MONTH_EN[a.month - 1]}{to}{day_words(b, lang)}"
    return day_words(a, lang) + to + day_words(b, lang)


def month_words(d, lang="en"):
    return f"{MONTHS_ES_LIST[d.month - 1]} de {d.year}" if lang == "es" else f"{MONTH_EN[d.month - 1]} {d.year}"


def window_words(w, start, end, lang="en", cap=True):
    """How the window is said back, with its dates: 'In October 2026', 'Last week (9 to 15 November 2026)'."""
    es = lang == "es"
    if w.kind == "all":
        s = "En todo tu historial," if es else "In all your history I can see,"
    elif w.kind == "day":
        s = ("El " if es else "On ") + day_words(start, lang, weekday=True)
    elif w.kind == "month" and not w.this:
        s = ("En " if es else "In ") + month_words(start, lang)
    elif w.kind == "month":
        s = f"Este mes ({span_words(start, end, lang)})" if es else f"This month ({span_words(start, end, lang)})"
    elif w.kind == "year" and not w.this:
        s = ("En " if es else "In ") + str(start.year)
    elif w.kind == "year":
        s = f"Este año ({span_words(start, end, lang)})" if es else f"This year ({span_words(start, end, lang)})"
    elif w.kind == "week":
        if w.this:
            s = f"Esta semana ({span_words(start, end, lang)})" if es else f"This week ({span_words(start, end, lang)})"
        else:
            s = (f"La semana del {span_words(start, end, lang)}" if es else
                 f"In the week of {span_words(start, end, lang)}")
    elif w.kind == "since":
        s = ("Desde el " if es else "Since ") + day_words(start, lang)
    elif w.kind == "lately":
        s = (f"En las 4 semanas hasta el {day_words(end, lang)}, donde termina tu exportación" if es else
             f"In the 4 weeks up to {day_words(end, lang)} (where your export ends),")
    elif w.kind == "weekend":
        s = (f"El fin de semana del {span_words(start, end, lang)}" if es else
             f"On the weekend of {span_words(start, end, lang)}")
    elif w.kind == "range" or (w.kind == "days" and start == end):
        s = (("Del " if es else "From ") + span_words(start, end, lang)) if start != end else \
            (("El " if es else "On ") + day_words(start, lang, weekday=True))
    else:
        n = (end - start).days + 1
        s = (f"En los últimos {n} días ({span_words(start, end, lang)})" if es else
             f"In the last {n} days ({span_words(start, end, lang)})")
    return s if cap else s[0].lower() + s[1:]


def noun(q, n, plats):
    es = q.lang == "es"
    if q.how == "watched" or plats == ["youtube"]:
        return ("video" if n == 1 else "videos") if es else ("video" if n == 1 else "videos")
    if plats == ["instagram"]:
        return ("publicación" if n == 1 else "publicaciones") if es else ("post" if n == 1 else "posts")
    return ("publicación o video" if n == 1 else "publicaciones y videos") if es else \
        ("post or video" if n == 1 else "posts and videos")


def verb(q):
    if q.lang == "es":
        return {"watched": "viste", "liked": "te gustaron", "saved": "guardaste", "any": "tocaste",
                "liked_saved": "te gustaron o guardaste"}[q.how]
    return {"watched": "watched", "liked": "liked", "saved": "saved", "any": "watched, liked or saved",
            "liked_saved": "liked or saved"}[q.how]


def topic_words(q):
    xs = [f"\"{x}\"" for x in q.topic]
    return (" o " if q.lang == "es" else " or ").join(xs)


def _about(q, n=2):
    """' that mention "blender"', ' from Pixel Forge', ''."""
    if q.channel:
        return (" de " if q.lang == "es" else " from ") + q.channel
    if q.topic:
        if q.lang == "es":
            return (" que menciona " if n == 1 else " que mencionan ") + topic_words(q)
        return (" that mentions " if n == 1 else " that mention ") + topic_words(q)
    return ""


def ends_line(rec, plats, lang="en"):
    have = [p for p in plats if p in rec.ends]
    if not have:
        return ""
    if lang == "es":
        parts = [f"tu exportación de {PNAME.get(p, p)} termina el {day_words(rec.ends[p], lang)}" for p in have]
        return _cap(" y ".join(parts)) + ", así que no veo nada después."
    parts = [f"your {PNAME.get(p, p)} export ends on {day_words(rec.ends[p])}" if i == 0 else
             f"your {PNAME.get(p, p)} export on {day_words(rec.ends[p])}" for i, p in enumerate(have)]
    return _cap(" and ".join(parts)) + ", so I can't see after that."


def _cap(s):
    return s[:1].upper() + s[1:]


def _title(it):
    from .compose import display_title
    try:
        return display_title(it)
    except Exception:  # noqa: BLE001 - a title is never worth failing an answer for
        return (it.first_line or it.caption or "")[:80] or ("A video" if it.platform == "youtube" else "A post")


def item_line(i, it, d, lang, today, url=True, times=None):
    from .render import by
    title = _title(it)
    when = short_day(d, lang, today)
    extra = ""
    if times:
        extra = (f", {times} veces, la última el {when}" if lang == "es" else f": {times} times, last on {when}")
        when = None
    s = f"{i}. {title}{by(it, None if lang == 'en' else 'es', title=title)}"
    s += f" ({when})" if when else extra
    return s + (f" {it.url}" if url and it.url else "")


# ====================================== the answers ==============================================================
def answer(view, q, today, prof=None, rec=None, said_end=False):
    """(text, [item ids shown in order], extra) for a query. `extra`: {"channels": [...] for a ranking, "cards": True
    when the items go out as link cards}. `said_end`: the reply already says where the export ends."""
    rec = rec or record(view, "UTC")
    plats = _scope_platforms(q, view, rec)
    if q.topic and not q.channel and len(q.topic) == 1:
        # a topic is a topic first; it is a channel when the message says so ("from X", "X's channel"), or when no
        # title in the scope mentions it and a channel has exactly that name
        ch = channel_of(view, q.topic[0])
        if ch and (q.channel_hint or not any(contains_word(view.items[i].caption or "", q.topic[0])
                                             for i in rec.events if view.items.get(i) is not None)):
            q = q.model_copy(update={"channel": ch, "topic": []})
    lang = q.lang
    es = lang == "es"
    if not plats:
        none = ("No tengo nada de eso en tu biblioteca." if es else
                f"I have nothing you {verb(q)} in your library to count.")
        return none, [], {}
    start, end = resolve(q.window, rec, plats, today)
    newest = max((rec.ends[p] for p in plats if p in rec.ends), default=None)
    # a window wholly after the record: say so, then the latest stretch of the same length the record holds
    if newest and start and start > newest and q.kind not in ("first", "last"):
        el = ends_line(rec, plats, lang)
        head = (f"No veo {window_noun(q.window, start, end, lang)}: " if es else
                f"I can't see {window_noun(q.window, start, end, lang)}: ") + el[:1].lower() + el[1:]
        head += " " + REFRESH[lang]
        w2 = shifted(q.window, start, end, newest)
        q2 = q.model_copy(update={"window": w2})
        if q.kind == "compare":
            q2 = q.model_copy(update={"kind": "count", "window": w2, "window2": None})
        body, ids, extra = answer(view, q2, today, prof, rec, said_end=True)
        lead = "Lo último que veo:" if es else "The latest I can see:"
        return head + "\n\n" + lead + "\n" + body, ids, extra
    W = window_words(q.window, start, end, lang)
    reached = [p for p in plats if p in rec.ends and (end is None or end >= rec.ends[p])]
    if q.kind == "compare" and q.window2:
        reached = [p for p in plats if p in reached or (p in rec.ends and (q.window2.end is None or
                                                                           q.window2.end >= rec.ends[p]))]
    tail = []
    oldest = _record_start(rec, plats, q)
    if oldest and end and end < oldest and q.kind != "compare":
        # a window wholly before the record: it can't be seen, never "you watched none"
        sl = start_line(rec, plats, q)
        return ((f"No veo {window_noun(q.window, start, end, lang)}: " if es else
                 f"I can't see {window_noun(q.window, start, end, lang)}: ") + sl[:1].lower() + sl[1:]), [], {}
    if oldest and start and start < oldest and q.window.kind != "all":
        tail.append(start_line(rec, plats, q))
    fn = {"top_channels": _top_channels, "top_topics": _top_topics, "top_items": _top_items, "count": _count,
          "list": _list, "on_day": _list, "first": _first, "last": _last, "timeline": _timeline,
          "compare": _compare}[q.kind]
    text, ids, extra = fn(view, rec, q, start, end, plats, W, today, prof)
    if said_end:
        pass
    elif q.window.kind == "all":
        tail += [range_line(rec, plats, q), REFRESH[lang]]
    elif reached:
        # the round 11 check (DESIGN 18.X): each platform whose export the window reaches is said, so "October 1 to
        # 15" says Instagram's ends on the 15th even while YouTube's runs on
        tail += [ends_line(rec, reached, lang), REFRESH[lang]]
    if q.how == "saved":
        tail.append("(Guardado cuenta lo guardado, las colecciones, lo que te enviaste y las listas.)" if es else
                    "(Saved counts saves, collections, posts you sent yourself and playlists.)")
    if "instagram" in plats:   # friends' posts are an Instagram matter
        tail.append("No cuento las publicaciones de tus amigos." if es else "Posts from friends are not counted.")
    extra = dict(extra, tail=" ".join(x for x in tail if x))
    return text + "\n\n" + extra["tail"], ids, extra


def _record_start(rec, plats, q):
    ds = [rec.starts[(p, k)] for p in plats for k in HOW_KINDS[q.how] if (p, k) in rec.starts]
    return min(ds) if ds else None


def start_line(rec, plats, q):
    """'Your YouTube history here starts on 19 September 2015, so I can't see before that.'"""
    have = []
    for p in plats:
        ds = [rec.starts[(p, k)] for k in HOW_KINDS[q.how] if (p, k) in rec.starts]
        if ds:
            have.append((p, min(ds)))
    if not have:
        return ""
    p, d = min(have, key=lambda x: x[1])
    lab = _LABEL.get(q.how)
    if q.lang == "es":
        if lab:   # the round 11 check (DESIGN 18.X): where the likes start is not where the history starts
            return f"{lab[1]} en {PNAME.get(p, p)} aquí empieza el {day_words(d, 'es')}, así que no veo nada antes."
        return f"Tu historial de {PNAME.get(p, p)} aquí empieza el {day_words(d, 'es')}, así que no veo nada antes."
    if lab:
        return f"Your {PNAME.get(p, p)} {lab[0]} here start on {day_words(d)}, so I can't see before that."
    return f"Your {PNAME.get(p, p)} history here starts on {day_words(d)}, so I can't see before that."


# what start_line and range_line call a record of likes or saves (English, Spanish); watches are "history"
_LABEL = {"liked": ("likes", "Lo que te gustó"), "saved": ("saves", "Lo que guardaste"),
          "liked_saved": ("likes and saves", "Lo que te gustó o guardaste")}


def range_line(rec, plats, q):
    """'Your YouTube history here runs from 5 January 2024 to 30 October 2026.' (each platform in scope)."""
    kinds = HOW_KINDS[q.how]
    have = []
    for p in plats:
        ds = [rec.starts[(p, k)] for k in kinds if (p, k) in rec.starts]
        if ds and p in rec.ends:
            have.append((p, min(ds), rec.ends[p]))
    if not have:
        return ""
    lab = _LABEL.get(q.how)
    if q.lang == "es":
        if lab:
            parts = [f"{lab[1].lower()} en {PNAME.get(p, p)} aquí va del "
                     f"{span_words(a, b, 'es').replace(' a ', ' al ', 1)}" for p, a, b in have]
            return _cap(" y ".join(parts)) + "."
        parts = [f"tu historial de {PNAME.get(p, p)} aquí va del {span_words(a, b, 'es').replace(' a ', ' al ', 1)}"
                 for p, a, b in have]
        return _cap(" y ".join(parts)) + "."
    if lab:
        parts = [(f"your {PNAME.get(p, p)} {lab[0]} here run from " if i == 0 else
                  f"your {PNAME.get(p, p)} {lab[0]} from ") + span_words(a, b) for i, (p, a, b) in enumerate(have)]
        return _cap(", and ".join(parts)) + "."
    parts = [(f"your {PNAME.get(p, p)} history here runs from " if i == 0 else f"your {PNAME.get(p, p)} history from ")
             + span_words(a, b) for i, (p, a, b) in enumerate(have)]
    return _cap(", and ".join(parts)) + "."


def window_noun(w, start, end, lang="en"):
    """The window as a thing to see: 'this month (1 to 19 November 2026)', 'Wednesday 18 November 2026'."""
    es = lang == "es"
    end = end or start
    if w.kind == "day":
        return day_words(start, lang, weekday=True)
    if w.kind == "month" and not w.this:
        return month_words(start, lang)
    if w.kind == "year" and not w.this:
        return str(start.year)
    if w.kind == "week" and not w.this:
        return ("la semana del " if es else "the week of ") + span_words(start, end, lang)
    if w.kind == "weekend":
        return ("el fin de semana del " if es else "the weekend of ") + span_words(start, end, lang)
    unit = {"month": ("este mes", "this month"), "year": ("este año", "this year"),
            "week": ("esta semana", "this week")}.get(w.kind)
    if unit:
        return f"{unit[0] if es else unit[1]} ({span_words(start, end, lang)})"
    if w.kind == "since":
        return ("nada desde el " if es else "anything since ") + day_words(start, lang)
    if es and start != end:   # the round 11 check (DESIGN 18.X): "No veo del 13 al 19 de noviembre"
        return "del " + span_words(start, end, lang).replace(" a ", " al ", 1)
    return span_words(start, end, lang)


def shifted(w, start, end, newest):
    if w.kind == "day":
        return _win("day", newest, newest)
    if w.kind == "month":
        return _win("month", newest.replace(day=1), _month_end(newest.year, newest.month))
    if w.kind == "year":
        return _win("year", date(newest.year, 1, 1), date(newest.year, 12, 31))
    n = ((end or newest) - start).days + 1 if start else 7
    n = max(n, 1)
    if n == 1:   # the round 11 check (DESIGN 18.X): "this week" on a Monday was "the last 1 days"
        return _win("day", newest, newest)
    return _win("days", newest - timedelta(days=n - 1), newest)


def num(n, lang="en"):
    """108,997 (English) or 108.997 (Spanish)."""
    s = f"{n:,}"
    return s.replace(",", ".") if lang == "es" else s


def _opening(q, n, W, plats, extra=""):
    if q.lang == "es":
        return f"{W} {verb(q)} {num(n, 'es')} {noun(q, n, plats)}{_about(q, n)}{extra}."
    return f"{W} you {verb(q)} {num(n)} {noun(q, n, plats)}{_about(q, n)}{extra}."


def _by_platform(view, ids, lang):
    c = Counter(view.items[i].platform for i in ids)
    if len(c) < 2:
        return ""
    en = " en " if lang == "es" else " on "
    return " (" + ", ".join(f"{num(n, lang)}{en}{PNAME.get(p, p)}" for p, n in c.most_common()) + ")"


def _count(view, rec, q, start, end, plats, W, today, prof):
    es = q.lang == "es"
    h = hits(view, rec, q, start, end, plats)
    pre = ("Cuento videos, no horas ni minutos. " if es else "I count videos, not hours or minutes. ") if q.hours else ""
    if q.unit == "channels":
        chans = {view.items[i].creator for i in h if view.items[i].creator}
        n = len(chans)
        if es:
            return f"{pre}{W} {verb(q)} videos de {num(n, 'es')} {'canal' if n == 1 else 'canales'}.", [], {}
        return (f"{pre}{W} you {verb(q)} {noun(q, 2, plats)} from {num(n)} {'channel' if n == 1 else 'channels'}.",
                [], {})
    n = len(h)
    if not (q.topic or q.channel):
        return pre + _opening(q, n, W, plats, _by_platform(view, h, q.lang)), [], {}
    q_all = q.model_copy(update={"topic": [], "channel": None})
    total = len(hits(view, rec, q_all, start, end, plats))
    if es:
        of = f" (de {num(total, 'es')} en total)"
    else:
        of = f" (of {num(total)} you {verb(q)} {'in all' if q.window.kind == 'all' else 'then'})"
    return pre + _opening(q, n, W, plats, of), [], {}


def _top_channels(view, rec, q, start, end, plats, W, today, prof):
    es = q.lang == "es"
    h = hits(view, rec, q, start, end, plats)
    if not h:
        return _nothing(q, W, plats), [], {}
    c = Counter(view.items[i].creator for i in h if view.items[i].creator)
    top = c.most_common(q.n)
    lines = [_opening(q, len(h), W, plats, _by_platform(view, h, q.lang)) + (" Más de:" if es else " Most from:")]
    lines += [f"{i}. {name}: {num(n, q.lang)}" for i, (name, n) in enumerate(top, 1)]
    if len(c) > len(top):
        lines.append(f"({num(len(c), 'es')} canales en total.)" if es else f"({num(len(c))} channels in all.)")
    if q.topics_too:
        tl = _topic_line(view, h, prof, q.lang)
        if tl:
            lines.append(tl)
    return "\n".join(lines), [], {"channels": [name for name, _ in top]}


def _topic_counts(view, ids, prof):
    from . import profile as P
    from .attention import topic_words_of
    out = []
    for i in (prof or {}).get("interests") or []:
        if i.get("relation") == "not_me" or P.sensitive(i.get("topic"), i.get("why"), " ".join(i.get("words") or [])):
            continue
        words = topic_words_of(i)
        support = set(i.get("support_ids") or [])
        n = sum(1 for x in ids if x in support or any(contains_word(view.items[x].caption, w) for w in words))
        if n:
            out.append((P.shown_topic(i["topic"]), n))
    out.sort(key=lambda x: (-x[1], x[0].lower()))
    return out


def _topic_line(view, ids, prof, lang):
    tc = _topic_counts(view, ids, prof)[:5]
    if not tc:
        return ""
    return ("Por tema: " if lang == "es" else "By topic: ") + ", ".join(f"{t} {n}" for t, n in tc) + "."


def _top_topics(view, rec, q, start, end, plats, W, today, prof):
    es = q.lang == "es"
    h = hits(view, rec, q, start, end, plats)
    if not h:
        return _nothing(q, W, plats), [], {}
    tc = _topic_counts(view, h, prof)[:q.n]
    if not tc:
        text, ids, extra = _top_channels(view, rec, q, start, end, plats, W, today, prof)
        lead = ("Todavía no sé tus temas, así que aquí van tus canales. Pregúntame por cualquier tema: \"¿cuántos "
                "videos de cocina vi?\"\n" if es else
                "I don't know your topics yet, so here are your channels. Ask me about any topic: \"how many cooking "
                "videos did I watch?\"\n")
        return lead + text, ids, extra
    lines = [_opening(q, len(h), W, plats) + (" Por tema (los que más):" if es else " By topic, the most:")]
    lines += [f"{i}. {t}: {n}" for i, (t, n) in enumerate(tc, 1)]
    lines.append("(Un video puede contar en más de un tema.)" if es else "(A video can count under more than one topic.)")
    return "\n".join(lines), [], {}


def _top_items(view, rec, q, start, end, plats, W, today, prof):
    es = q.lang == "es"
    h = hits(view, rec, q, start, end, plats)
    counted = sorted(((len(ds), max(ds), i) for i, ds in h.items() if len(ds) > 1),
                     key=lambda x: (-x[0], -x[1].toordinal(), x[2]))
    if not counted:
        s = (f"{W} no viste ningún video más de una vez{_about(q, 1)}." if es else
             f"{W} you watched nothing more than once{_about(q, 1)}.")
        return s, [], {}
    top = counted[:q.n]
    lines = [(f"{W.rstrip(',')}, lo que más repetiste{_about(q)}:" if es else
             f"{W.rstrip(',')}, what you watched most often{_about(q)}:")]
    lines += [item_line(k, view.items[i], d, q.lang, today, times=n) for k, (n, d, i) in enumerate(top, 1)]
    if len(counted) > len(top):
        lines.append(f"Y {len(counted) - len(top)} más que viste más de una vez." if es else
                     f"And {len(counted) - len(top)} more you watched more than once.")
    return "\n".join(lines), [i for _, _, i in top], {}


def _list(view, rec, q, start, end, plats, W, today, prof):
    es = q.lang == "es"
    h = hits(view, rec, q, start, end, plats)
    if not h:
        return _nothing(q, W, plats), [], {}
    cap = DAY_MAX if q.kind == "on_day" else LIST_MAX
    order = sorted(h, key=lambda i: (-max(h[i]).toordinal(), i))
    page = order[q.offset:q.offset + cap]
    if not page:
        return ("No hay más." if es else "That's all of them."), [], {}
    if q.offset:
        lines = [(f"Los siguientes {len(page)}:" if es else f"The next {len(page)}:")]
    elif q.kind == "on_day":
        lines = [_opening(q, len(h), W, plats)[:-1] + ":"]
    else:
        k = len(page)
        lines = [_opening(q, len(h), W, plats) + (f" Los {k} más recientes:" if es else
                                                  (" The latest:" if k == 1 else f" The latest {k}:"))]
    lines += [item_line(q.offset + k, view.items[i], max(h[i]), q.lang, today) for k, i in enumerate(page, 1)]
    rest = len(order) - q.offset - len(page)
    if rest > 0:
        lines.append(f"Y {rest} más (di \"más\" para verlos)." if es else f"And {rest} more (say \"more\" to see them).")
    return "\n".join(lines), page, {}


def _nothing(q, W, plats):
    """Nothing in a window the record covers."""
    if q.lang == "es":
        about = (" de " + q.channel) if q.channel else (" que mencione " + topic_words(q)) if q.topic else ""
        return f"{W} no {verb(q)} {'ningún video' if q.how == 'watched' else 'nada'}{about}."
    return f"{W} you {verb(q)} no {noun(q, 2, plats)}{_about(q)}."


def _first(view, rec, q, start, end, plats, W, today, prof, last=False):
    es = q.lang == "es"
    h = hits(view, rec, q, start, end, plats)
    if not h:
        return _nothing(q, W, plats), [], {}
    key = (lambda i: (-max(h[i]).toordinal(), i)) if last else (lambda i: (min(h[i]), i))
    order = sorted(h, key=key)[:FIRST_MAX]
    d0 = max(h[order[0]]) if last else min(h[order[0]])
    n1 = noun(q, 1, plats)
    win = "" if q.window.kind == "all" else " " + window_words(q.window, start, end, q.lang, cap=False)
    if es:
        word = "último" if last else "primer"
        head = f"El {word} {n1} que {verb(q)}{_about(q, 1)}{win} fue el {day_words(d0, 'es')}:"
    else:
        head = f"The {'last' if last else 'first'} {n1} you {verb(q)}{_about(q, 1)}{win} was on {day_words(d0)}:"
    lines = [head]
    for k, i in enumerate(order, 1):
        lines.append(item_line(k, view.items[i], max(h[i]) if last else min(h[i]), q.lang, None, url=False))
    if len(h) > 1:
        lines.append((f"({num(len(h), 'es')} en total" if es else f"({num(len(h))} in all") +
                     (f"{win}.)" if win else ".)"))
    return "\n".join(lines), order, {"cards": True}


def _last(view, rec, q, start, end, plats, W, today, prof):
    return _first(view, rec, q, start, end, plats, W, today, prof, last=True)


def _cells(h, lo, hi, by_month, lang):
    """'Jan 2026: 0, Feb 2026: 3, ...' or '2024: 0, 2025: 6, ...': each item counted once per month or year."""
    c = Counter()
    for ds in h.values():
        for k in {(d.year, d.month) if by_month else d.year for d in ds if lo <= d <= hi}:
            c[k] += 1
    if by_month:
        keys, (y, m) = [], (lo.year, lo.month)
        while (y, m) <= (hi.year, hi.month):
            keys.append((y, m))
            y, m = (y + (m == 12), m % 12 + 1)
        names = MONTHS_ES_LIST if lang == "es" else MONTH_EN
        cells = [f"{names[m - 1][:3]} {y}: {num(c[(y, m)], lang)}" for y, m in keys]
    else:
        cells = [f"{y}: {num(c[y], lang)}" for y in range(lo.year, hi.year + 1)]
    if hi.day != _month_end(hi.year, hi.month).day or (not by_month and hi < date(hi.year, 12, 31)):
        cells[-1] += f" (hasta el {short_day(hi, 'es')})" if lang == "es" else f" (up to {short_day(hi)})"
    return ", ".join(cells)


def _timeline(view, rec, q, start, end, plats, W, today, prof):
    """Counts per month or per year (by the span, unless the question says which); over all the history by year,
    with the last 6 months by month after it."""
    es = q.lang == "es"
    h = hits(view, rec, q, start, end, plats)
    newest = max((rec.ends[p] for p in plats if p in rec.ends), default=today)
    first = min((rec.starts[(p, k)] for p in plats for k in HOW_KINDS[q.how] if (p, k) in rec.starts),
                default=newest)
    lo = max(start, first) if start else first
    hi = min(end or newest, newest)
    if lo > hi:
        lo = hi
    by_month = q.by == "month" if q.by else (hi.year - lo.year) * 12 + hi.month - lo.month < 18
    unit = ("por mes" if es else "by month") if by_month else ("por año" if es else "by year")
    n2 = noun(q, 2, plats)
    said = "" if q.window.kind == "all" else f", {window_words(q.window, start, end, q.lang, cap=False)}"
    if es:
        head = f"{_cap(n2)} que {verb(q)}{_about(q)}, {unit}{said}:"
    else:
        head = f"{_cap(n2)} you {verb(q)}{_about(q)}, {unit}{said}:"
    if by_month and (hi.year - lo.year) * 12 + hi.month - lo.month >= 24:
        # months over many years: the last 12 in words, the busiest month over the whole span after them
        y, m = (hi.year, hi.month - 11) if hi.month > 11 else (hi.year - 1, hi.month + 1)
        lines = [head, ("Los últimos 12 meses: " if es else "The last 12 months: ") +
                 _cells(h, date(y, m, 1), hi, True, q.lang) + "."]
    else:
        lines = [head, _cells(h, lo, hi, by_month, q.lang) + "."]
    if not by_month and q.by != "year":
        y, m = (hi.year, hi.month - 5) if hi.month > 5 else (hi.year - 1, hi.month + 7)
        lo6 = max(lo, date(y, m, 1))
        lines.append(("Los últimos meses: " if es else "The last months, by month: ") +
                     _cells(h, lo6, hi, True, q.lang) + ".")
    peak = _peak(h, lo, hi, by_month)
    if peak:
        k, n = peak
        when = (month_words(date(k[0], k[1], 1), q.lang) if by_month else str(k))
        lines.append(f"Lo más: {when}, con {num(n, 'es')}." if es else f"The most: {when}, with {num(n)}.")
    lines.append(f"En total, {num(len(h), 'es')}." if es else f"{num(len(h))} in all.")
    return "\n".join(lines), [], {}


def _peak(h, lo, hi, by_month):
    c = Counter()
    for ds in h.values():
        for k in {(d.year, d.month) if by_month else d.year for d in ds if lo <= d <= hi}:
            c[k] += 1
    if not c:
        return None
    k, n = max(c.items(), key=lambda kv: (kv[1], kv[0]))
    return (k, n) if n else None


def _compare(view, rec, q, start, end, plats, W, today, prof):
    es = q.lang == "es"
    s2, e2 = resolve(q.window2, rec, plats, today)
    a = len(hits(view, rec, q, start, end, plats))
    b = len(hits(view, rec, q, s2, e2, plats))
    W2 = window_words(q.window2, s2, e2, q.lang, cap=False)
    short = window_words(q.window, start, end, q.lang, cap=False)
    s = _opening(q, a, W, plats)[:-1]
    if es:
        s += f", y {W2.replace('En ', 'en ', 1)}, {num(b, 'es')}"
        diff = (f": {num(abs(a - b), 'es')} {'más' if a > b else 'menos'} {short}." if a != b else ": lo mismo.")
    else:
        s += f", and {W2}, {num(b)}"
        diff = (f": {num(abs(a - b))} {'more' if a > b else 'fewer'} {short}." if a != b else ": the same.")
    return s + diff, [], {}


# ====================================== on the bot ===============================================================
STATE = "history:{h}"
PICK = re.compile(r"^\W*(?:(?:and|ok|so|y)\s+)?(?:show\s+me\s+|open\s+|what\s+about\s+|what\s+did\s+i\s+watch\s+from\s+|"
                  r"muestrame\s+)?(?:the\s+|el\s+|la\s+)?(?:#|number\s+|no\.?\s*)?"
                  r"(first|second|third|fourth|fifth|sixth|seventh|eighth|1st|2nd|3rd|4th|5th|6th|7th|8th|[1-8]|"
                  r"primer[oa]?|segund[oa]|tercer[oa]?)(?:\s+(?:one|channel|video|uno|una|canal))?\s*[?.!]*\s*$")
ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
       "1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5, "6th": 6, "7th": 7, "8th": 8, "primer": 1, "primero": 1,
       "primera": 1, "segundo": 2, "segunda": 2, "tercer": 3, "tercero": 3, "tercera": 3}
SHOW_THEM = re.compile(r"^\W*(?:(?:and|ok|okay|so|y|cool|great)[,\s]+)?(?:(?:can\s+you\s+|please\s+)?(?:show|list|"
                       r"give|send)\s+(?:me\s+)?(?:them|those|those\s+videos|the\s+videos|the\s+list|which\s+ones)|"
                       r"which\s+ones(?:\s+were\s+they)?|what\s+were\s+they|list\s+them|cuales(?:\s+son)?|"
                       r"muestramelos|cuales\s+fueron)(?:\s+please)?\s*[?.!]*\s*$")
MORE = re.compile(r"^\W*(?:(?:and|ok|y)\s+)?(?:show\s+me\s+)?(?:more|the\s+rest|next|mas|los\s+demas)(?:\s+please)?"
                  r"\s*[?.!]*\s*$")
FOLLOW_LEAD = re.compile(r"^\W*(?:(?:and|ok|okay|so|y|but)[,\s]+)?(?:(?:what|how)\s+about|and\s+for|and\s+in|and\s+on|"
                         r"for|in|on|only|just|y\s+(?:en|para|de)|y\s+que\s+tal|que\s+tal)?\b\s*")
# the round 11 check (DESIGN 18.X): a new topic needs a lead that asks again ("what about guitar", "and cooking?");
# "ok thanks", "for real?", "just kidding", "on my way" are never a topic
STRONG = re.compile(r"^\W*(?:(?:and|ok|okay|so|but)[,\s]+)?(?:what|how)\s+about\b|^\W*(?:y\s+)?que\s+tal\b")
AND_LEAD = re.compile(r"^\W*(?:and|y)\b(?!\s+(?:you|u|tu|then|why|so|what|yours|that|this|it)\b)")
ONES = re.compile(r"^\W*(?:(?:and|ok|okay|so|y)[,\s]+)?(?:(?:only|just)\s+)?(?:the\s+)?ones?\s+(?:that\s+)?i\s+"
                  r"(liked|saved|watched)\W*$")


def _fresh_state(bot, h, now):
    st = bot.store.get_state(STATE.format(h=h))
    if not st:
        return None
    try:
        at = datetime.fromisoformat(st["at"])
    except (KeyError, ValueError):
        return None
    if now - at > timedelta(hours=FOLLOW_HOURS):
        return None
    last = bot.store.last_answer(h) or {}
    if last.get("run_id") != st.get("run_id"):
        return None
    return st


def follow_up(st, text, today, known=None):
    """A changed query for a follow-up to the history answer in `st`, ("pick", n), or None. `known(topic)`: whether
    anything in the record mentions a topic (an "and X?" topic is taken only then)."""
    q = HistoryQuery.model_validate(st["q"])
    t = normal(text)
    if not t or len(t) > 80:
        return None
    if REMIND.search(t) or ACTING.search(t) or EVERY.search(t):
        return None
    m = ONES.match(t)
    if m:
        return q.model_copy(update={"how": m.group(1), "offset": 0})
    m = PICK.match(t)
    if m:
        return ("pick", ORD.get(m.group(1)) or int(m.group(1)))
    if SHOW_THEM.match(t):
        if q.kind in ("list", "on_day", "first", "last", "top_items"):
            return None
        kind = "on_day" if q.window.kind == "day" else "list"
        return q.model_copy(update={"kind": kind, "offset": 0, "window2": None, "unit": "items", "hours": False})
    if MORE.match(t) and q.kind in ("list", "on_day"):
        cap = DAY_MAX if q.kind == "on_day" else LIST_MAX
        return q.model_copy(update={"offset": q.offset + cap})
    body = FOLLOW_LEAD.sub("", t, count=1)
    body = re.sub(r"[?.!]+\s*$", "", body).strip()
    strong, anded = bool(STRONG.match(t)), bool(AND_LEAD.match(t))
    wins = find_windows(body, today)
    if not body or body == t.strip("?.! "):
        # no lead: only a bare window ("last month?") or "and ..." / "what about ..."
        if not (strong or anded or (wins and body == " ".join(body[a:b] for _, (a, b) in wins).strip())):
            return None
    spans = [s for _, s in wins]
    topic, platform, how = _topic_and_platform(body, spans)
    leftover = topic
    changes = {}
    w = [x for x, _ in wins if isinstance(x, Window)]
    before = next((x for x, _ in wins if isinstance(x, str)), None)
    if not w and before and q.window.start:
        # "and the month before that?" (the round 11 check, DESIGN 18.X)
        w2 = _before(q.window, before.split(":", 1)[1])
        w = [w2] if w2 else []
    if w:
        changes["window"] = w[0]
        changes["offset"] = 0
    if platform:
        changes["platform"] = platform
    if re.search(r"\b(?:liked|likes|the ones i liked)\b", body):
        changes["how"] = "liked"
    elif re.search(r"\b(?:saved|saves|the ones i saved)\b", body):
        changes["how"] = "saved"
    elif re.search(r"\b(?:watched|watches)\b", body):
        changes["how"] = "watched"
    if leftover and not w and not platform and "how" not in changes:
        if sum(len(x.split()) for x in leftover) > 3:
            return None
        if not strong and not (anded and known is not None and any(known(x) for x in leftover)):
            return None
        changes["topic"] = leftover
        changes["channel"] = None
    elif leftover:
        return None
    if not changes:
        return None
    if "window" in changes and q.kind == "compare":
        changes.update(kind="count", window2=None)
    return q.model_copy(update=changes)


def history_reads(bot, person, text, now):
    """Hook 8h (answer_normally, after integration_reads, before the model): a history question or a follow-up to a
    history answer, read and answered by code. Returns the reply's reference, or None."""
    h = person["handle"]
    tz = person.get("timezone") or "UTC"
    today = now.astimezone(ZoneInfo(tz)).date()
    st = _fresh_state(bot, h, now)
    if st:
        def known(x):
            view = bot.view(person["library"])
            return any(contains_word(it.caption or "", x) for it in view.items.values())
        f = follow_up(st, text, today, known)
        if isinstance(f, tuple):
            return _pick(bot, person, st, f[1], now, today)
        if f is not None:
            return send_answer(bot, person, f, now, follow=True)
    q = read(text, today)
    if q is None:
        return None
    return send_answer(bot, person, q, now)


def send_answer(bot, person, q, now, follow=False, lead=""):
    from .render import Reply, link_part
    from .store import now_iso
    from . import profile as P
    h = person["handle"]
    tz = person.get("timezone") or "UTC"
    today = now.astimezone(ZoneInfo(tz)).date()
    view = bot.view(person["library"])
    rec = record(view, tz)
    t0 = datetime.now()
    text, ids, extra = answer(view, q, today, P.get(bot.store, h), rec)
    bot.note(intent="history")
    tail = extra.get("tail") or ""
    if extra.get("cards") and tail and text.endswith(tail):
        # the cards of the first or last items go right under their lines, before where the record ends
        body = text[:-len(tail)].rstrip()
        parts = [{"type": "text", "text": (lead + "\n\n" if lead else "") + body}]
        parts += [link_part(view.items[i], _title(view.items[i])) for i in ids if view.items[i].url]
        parts.append({"type": "text", "text": tail})
    else:
        parts = [{"type": "text", "text": (lead + "\n\n" if lead else "") + text}]
    reply = Reply(parts)
    run_id = bot.store.add_run(handle=h, kind="history", at=now_iso(now), n_candidates=len(ids), n_picks=len(ids),
                               n_dropped=0, cost_usd=0.0, status="picked" if ids else "none", prompt_version=None,
                               seconds=round((datetime.now() - t0).total_seconds(), 3),
                               steps={"history": {"kind": q.kind, "how": q.how, "platform": q.platform,
                                                  "window": q.window.kind, "topic_words": len(q.topic),
                                                  "channel": bool(q.channel), "follow_up": follow}})
    bot.note(run_id=run_id)
    recs = []
    for k, i in enumerate(ids, 1):
        it = view.items[i]
        bot.store.add_delivery(h, None, run_id, i, k, at=now)
        recs.append({"item_id": i, "title": _title(it), "url": it.url, "platform": it.platform,
                     "video_id": it.video_id, "creator": it.creator, "facts": {}, "lines": [], "line_kinds": None})
    goal = ("history: " + q.kind)[:80]
    bot.store.set_last_answer(h, run_id, None, list(ids), goal)
    bot.store.set_state(f"lines:{h}", {i: [] for i in ids})
    bot.store.set_state(f"linekinds:{h}", {i: None for i in ids})
    bot.store.set_state(f"facts:{h}", {i: {} for i in ids})
    bot._keep_answer(run_id, h, None, goal, "history", reply, recs)
    bot.store.set_state(STATE.format(h=h), {"q": q.model_dump(mode="json"), "at": now_iso(now), "run_id": run_id,
                                            "ids": list(ids), "channels": extra.get("channels") or []})
    return bot.send(h, reply, run_id)


def _pick(bot, person, st, n, now, today):
    from .render import Reply, link_part
    h = person["handle"]
    q = HistoryQuery.model_validate(st["q"])
    chans = st.get("channels") or []
    ids = st.get("ids") or []
    if chans:
        if not 1 <= n <= len(chans):
            return bot.send(h, (f"¿Cuál? Mostré {len(chans)}." if q.lang == "es" else
                                f"Which one? I listed {len(chans)}."))
        q2 = q.model_copy(update={"kind": "list", "channel": chans[n - 1], "topic": [], "offset": 0,
                                  "topics_too": False})
        return send_answer(bot, person, q2, now, follow=True)
    if not ids:
        return None
    if not 1 <= n <= len(ids):
        return bot.send(h, (f"¿Cuál? Mostré {len(ids)}." if q.lang == "es" else f"Which one? I listed {len(ids)}."))
    view = bot.view(person["library"])
    it = view.items.get(ids[n - 1])
    if it is None:
        return None
    bot.note(intent="history")
    title = _title(it)
    # the merge of round 11 (DESIGN 18, seam d): the one item shown is the pick in view, so "what does it say about X"
    # and "ask the video" name it; the follow-ups above read the history state's own list, which stays as it was
    run_id = st.get("run_id")
    if run_id is not None:
        bot.store.set_last_answer(h, run_id, None, [it.id], (bot.store.last_answer(h) or {}).get("goal") or "")
        bot.store.set_state(f"lines:{h}", {it.id: []})
        bot.store.set_state(f"linekinds:{h}", {it.id: None})
        bot.store.set_state(f"facts:{h}", {it.id: {}})
    from .render import by
    line = f"{title}{by(it, None if q.lang == 'en' else 'es', title=title)}"
    parts = [{"type": "text", "text": line}]
    if it.url:
        parts.append(link_part(it, title))
    return bot.send(h, Reply(parts), st.get("run_id"))


# ---------- after the interpreter ----------
TIMING = re.compile(r"\b(?:every|each|cada)\s+(?:other\s+)?(?:" + _DAY_RE + r"s?|morning|evening|night|day|weekend|"
                    r"weekday|week|month|year|lunes|martes|miercoles|jueves|viernes|sabado|domingo|dia|semana|mes)\b|"
                    r"\b(?:daily|weekly|monthly|nightly|from now on|whenever \w+)\b|\b(?:on|los)\s+" + _DAY_RE +
                    r"s\b|\bat\s+\d{1,2}(?::\d\d)?\s*(?:am|pm)?\b|\bin the (?:morning|evening)\b")
SEND_LEAD = re.compile(r"^\W*(?:(?:please|pls|can you|could you)\s+)?(?:send|text|email|e-mail|mail|tell|give|show|"
                       r"message|dm|envia\w*|mandame|manda|dime)\s+(?:me\s+)?")
RULE_SOURCES = ("library", "recent", None)


def after_interpret(bot, person, it, text, now):
    """After the interpreter (no new prompt): a library_stats form for a message the code read did not take is
    answered here when its words have a history shape; else its function words are taken out of `stats.words`
    (finding H1: "watching", "most", "this month" were searched) and the old count runs. A new rule made of a history
    question is said plainly not to be possible yet, with today's answer. Returns a reply's reference or None."""
    tz = person.get("timezone") or "UTC"
    today = now.astimezone(ZoneInfo(tz)).date()
    if it.intent == "library_stats":
        q = read(text, today, loose=True)
        if q is not None and _history_shaped(q, text):
            return send_answer(bot, person, q, now)
        if it.stats and it.stats.words:
            it.stats.words = [w for w in it.stats.words if any(x not in STOP for x in normal(w).split())
                              and not find_windows(normal(w), today)]
        return None
    if it.intent == "new_rule" and it.spec is not None and it.spec.content.source in RULE_SOURCES:
        t = normal(text)
        if not TIMING.search(t) or REMIND.search(t):
            return None
        core = SEND_LEAD.sub("", TIMING.sub(" ", t)).strip(" ,.")
        core = re.sub(r"^\W*(?:and|then)\s+", "", core)
        q = read(core, today)
        if q is None:
            q = read(core + "?", today)
        if q is None or q.kind == "list" and q.window.kind == "lately":
            return None
        lead = (("Puedo responder eso ahora, pero todavía no puedo enviarlo con horario, así que no creé ninguna "
                 "regla. Aquí está por ahora:") if q.lang == "es" else
                "I can answer that now, but I can't send your history on a schedule yet, so I didn't set up a rule. "
                "Here it is for now:")
        return send_answer(bot, person, q, now, lead=lead)
    return None


def _history_shaped(q, text):
    """For the loose read: the message adds something the old count can't say (a window, watching, a ranking, a
    first or last, a timeline or a comparison)."""
    t = normal(text)
    return (q.kind != "count" or q.window.kind != "all" or q.unit == "channels" or q.hours
            or bool(re.search(r"\b(?:watch\w*|viewed|seen|visto|vi|veo)\b", t)))


# ====================================== the merge of round 11: the framing (DESIGN 18) ===========================
# The setup's suggestions, "help" and "what can you do" lead with asking the watch history, with example questions
# built from the person's own record (counts) and profile (topics). Every example is one the reads take: a history
# question (`read`) or a summary (synth.read), checked here before it is offered; a topic is offered only when the
# record holds something that mentions it.
def _example_topics(prof, n=4):
    """Short topic words from the profile's interests, most saved first: the topic itself when it is one or two
    words, else its longest content word."""
    out = []
    for i in (prof or {}).get("interests") or []:
        t = normal(str(i.get("topic") or ""))
        words = [w for w in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", t) if w not in STOP and len(w) >= 3]
        if not words:
            continue
        cand = " ".join(words) if len(words) <= 2 and len(t.split()) <= 2 else max(words, key=len)
        if cand not in out:
            out.append(cand)
        if len(out) >= n:
            break
    return out


def examples(bot, person, now):
    """(the count line, [example questions]) for this person, or ("", []) when there is no watch history to ask."""
    from . import profile as P
    from . import synth
    tz = person.get("timezone") or "UTC"
    today = now.astimezone(ZoneInfo(tz)).date()
    view = bot.view(person["library"])
    rec = record(view, tz)
    q0 = HistoryQuery(kind="count", how="watched")
    counts = []
    for p in ("youtube", "instagram"):
        if p in rec.ends:
            n = len(hits(view, rec, q0, None, None, [p]))
            if n:
                counts.append((p, n))
    if not counts:
        return "", []
    newest = max(rec.ends[p] for p, _ in counts)
    said = " and ".join((f"{num(n)} videos you watched on {PNAME[p]}" if i == 0 else f"{num(n)} on {PNAME[p]}")
                        for i, (p, n) in enumerate(counts))
    line = f"Ask your watch history anything. I can see {said}, up to {day_words(newest)}."
    month = MONTHS[newest.month - 1].capitalize()   # the month the record ends in: its answer says where it ends
    if (today.year * 12 + today.month) - (newest.year * 12 + newest.month) >= 12:
        month += f" {newest.year}"   # the round 11 check: an export over a year old names its year (never this year's)
    qs = [f"which channels did I watch the most in {month}?"]
    topic = None
    for t in _example_topics(P.get(bot.store, person["handle"])):
        q = read(f"when did I first watch videos about {t}?", today)
        if q is None or not q.topic or synth.read(f"summarize what I've learned about {t}") is None:
            continue
        if hits(view, rec, q, None, None, [p for p, _ in counts]):
            topic = t
            break
    if topic:
        qs += [f"when did I first watch videos about {topic}?", f"summarize what I've learned about {topic}"]
    else:
        qs += [f"what did I watch on {day_words(newest)}?", f"how many videos did I watch in {newest.year}?"]
    qs = [x for x in qs if read(x, today) is not None or synth.read(x) is not None]
    return line, qs


def examples_block(bot, person, now):
    """The block the help and the setup lead with, or "" (never fails the message it is in)."""
    try:
        line, qs = examples(bot, person, now)
    except Exception:  # noqa: BLE001 - the help and the setup never break for this
        return ""
    if not line:
        return ""
    return line + " Try:\n" + "\n".join(f"\"{x}\"" for x in qs)
