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
from functools import lru_cache
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
    less: bool = False                  # round 11 fix, A (R5): compare asked "less / fewer", so its answer leads so


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
    t = re.sub(r"\bwhens\b", "when's", t)   # round 11 fix pass 2 (P4): "whens the first time i watched X"
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
# round 11 fix pass 2 (P4): "more videos in october or september?", "fewer reels this month than last month"
CMP_BARE = re.compile(r"^\W*(?:(?:so|and|ok|okay|hey)[,\s]+)?(?:more|less|fewer)\s+(?:youtube\s+|instagram\s+)?"
                      r"(?:videos?|vids?|reels?|youtube|instagram|watching)\s+(?:in|during|on|this|last)\b"
                      r".*\b(?:or|vs\.?|versus|than|compared\s+to)\b")
TOP_PLAIN = re.compile(r"^\W*(?:my\s+)?top\s+(?:\d+\s+|five\s+|ten\s+)?(?:channels|youtubers|creators)\b")
STATEMENT = re.compile(r"^\W*(?:i|i've|i'm|i was|yo|lol|haha)\b")
QUESTION = re.compile(r"\?|^\W*(?:what|which|who|when|how|show|list|tell|give|did|do|have|was|is|are|since|"
                      r"que|cual|cuales|cuantos|cuantas|cuando|desde|quien|muestrame|dime|como)\b|"
                      r"^\W*(?:the\s+)?(?:my\s+)?(?:top|most|first|last|latest|earliest|watch history|videos?|"
                      r"channels?)\b")
SPANISH = re.compile(r"\b(?:que|cuantos|cuantas|cuando|canales|vi|veo|visto|ayer|hoy|este mes|el mes pasado|"
                     r"semana|empece|ver|videos de|historial|mas)\b")

# ---------- the kind ----------
HOURS = re.compile(r"\b(?:hours?|minutes?|time spent|how long|horas|minutos)\b")
COMPARE = re.compile(r"\b(?:more|less|fewer|vs\.?|versus|compared?|comparison|than|or|mas|menos|compar\w+)\b")
TOP_ITEMS = re.compile(r"\b(?:re-?watch\w*|more than once|over and over|(?:watched|viewed)\s+(?:the\s+)?most\s+"
                       r"(?:times|often)|most\s+(?:watched|viewed|played)\s+(?:videos?|reels?|clips?)|"
                       r"(?:videos?|reels?)\s+(?:that\s+)?i(?:'ve| have)?\s+watched\s+(?:the\s+)?most|"
                       r"top\s+(?:\d+\s+)?(?:videos?|reels?)\s+i(?:'ve| have)?\s+watched)\b")
TIMELINE = re.compile(r"\b(?:which|what)\s+(?:month|year)\b|\bmost\s+(?:watched\s+)?(?:month|year)\b|"
                      r"\bbusiest\b|"
                      r"\b(?:over time|over the (?:years|months)|changed?|changing|trends?|trending|grown|growing|"
                      r"(?:by|per|each|every|a)\s+(?:month|year)|monthly|yearly|month by month|year by year|"
                      r"por mes|cada mes|por ano|cada ano|"
                      # round 11 fix pass 2 (P4): "como ha cambiado lo que veo (de cocina) (con el tiempo)"
                      r"ha cambiado|han cambiado|cambiado|ha ido cambiando|con el tiempo|a lo largo del tiempo|"
                      r"ha evolucionado)\b")
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
comparado comparada comparando comparar comparacion frente
como cambiado cambiando evolucionado ido tiempo largo
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
    # round 11 fix check (18.L check): "reels" are Instagram's ("how many reels have i liked" counted YouTube likes,
    # "the last color grading reel i watched" showed a YouTube video), unless videos are named beside them
    if platform is None and not re.search(r"\b(?:youtube|yt|videos?|vids?|shorts?)\b", rest) \
            and re.search(r"\b(?:reels?|insta|ig)\b", rest):
        platform = "instagram"
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
    for k, w in enumerate(toks):
        w2 = w.strip(".'-")
        if w2 == "after" and k + 1 < len(toks) and toks[k + 1].strip(".'-") == "effects":
            cur.append(w2)   # round 11 fix, A: "after effects" is a name, not "after" and a topic "effects"
            continue
        if (not w2 or w2 in STOP or w2.isdigit() or w2 in MONTHS or w2 in MON_ABBR or w2 in MONTH_ES
                or w2 in DAYS or w2 in DAYS_ES or re.fullmatch(_DAY_RE, w2) or re.fullmatch(r"\d+(?:st|nd|rd|th)", w2)
                or w2 in ("what's", "i've", "i'm", "it's", "i'd", "when's")):
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
    # round 11 fix pass 2 (P4): a comparison of two windows with no "i watched" ("more videos in october or
    # september?") and one with no question mark ("vi mas videos en 2024 o en 2025") are read only as comparisons
    compare_only = False
    if not marked and not loose and CMP_BARE.match(t):
        marked = compare_only = True
    if not marked and not loose:
        return None
    if STATEMENT.match(t) and "?" not in raw and not loose:
        return None
    if not QUESTION.search(t) and not loose:
        if not re.search(r"\b(?:more|less|fewer|mas|menos|compar\w+)\b", t):
            return None
        compare_only = True
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
        q.update(kind="compare", window=windows[0], window2=windows[1],
                 less=bool(re.search(r"\b(?:less|fewer|menos)\b", rest)) and not re.search(r"\b(?:more|mas)\b", rest))
    elif compare_only:
        return None
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
    return any(holds(text, x) for x in q.topic)


@lru_cache(maxsize=512)
def _keys(phrase):
    """Round 11 fix, A (R3, speed): the parts a text must hold, as plain substrings, for contains_word to match: each
    word's stem without its last letter ("berr" for "berries", "tomat" for "tomatoes")."""
    from .retrieve import WORD, _stem, norm
    out = []
    for w in WORD.findall(norm(phrase)):
        s = _stem(w)
        out.append(s[:-1] if len(s) > 2 else s)
    return tuple(out)


def holds(text, phrase):
    """retrieve.contains_word, with a cheap test first (the same answer, about ten times faster over a library)."""
    ks = _keys(phrase)
    if ks:
        low = unicodedata.normalize("NFKC", text or "").lower()
        if any(k not in low for k in ks):
            return False
    return contains_word(text, phrase)


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


# ---------- round 11 fix, A (R3): a topic's items must fit it by the engine's own item vectors, not only hold the
# word. The library's stored vectors (text-embedding-3-large @ 1024, the ones the engine ranks with: a demo library's
# int8 store, or a research root's float store) are read here, no model call: the topic's vector is the trimmed
# centroid of every item of the record whose text holds the word, and an item fits when its own vector is within
# FIT_CUT of the median of those items. Without vectors, or with fewer than FIT_MIN matches, nothing changes (word
# matches, said "mention"). The engine's own search would need its query rewrite (a model call) and its loaded
# process; this reads only the same vectors, in well under a second (DESIGN 18.LA).
FIT_MIN, FIT_CUT, FIT_TRIM = 6, 0.08, 0.25
_VECS, _FITS = {}, {}


def _vector_store(lib):
    """(id -> row, matrix, per-dimension scale or None) for the library's item vectors, or None."""
    import numpy as np
    for name, files in (("oai3l_1024_q8", ("q8.npy", "scale.npy")), ("oai3l_1024", ("emb.npy", None))):
        d = os.path.join(lib, "corpus", "emb", name)
        ids_path = os.path.join(d, "ids.json")
        if not (os.path.exists(ids_path) and os.path.exists(os.path.join(d, files[0]))):
            continue
        try:
            stamp = (ids_path, os.stat(ids_path).st_mtime_ns)
        except OSError:
            continue
        with _LOCK:
            hit = _VECS.get(lib)
            if hit and hit[0] == stamp:
                return hit[1]
        try:
            with open(ids_path, encoding="utf-8") as f:
                ids = json.load(f)
            mat = np.load(os.path.join(d, files[0]), mmap_mode="r")
            scale = np.load(os.path.join(d, files[1])).astype(np.float32) if files[1] else None
        except (OSError, ValueError):
            return None
        if len(ids) != mat.shape[0]:
            return None
        got = ({i: k for k, i in enumerate(ids)}, mat, scale)
        with _LOCK:
            _VECS.clear()
            _VECS[lib] = (stamp, got)
            _FITS.clear()
            _CENTS.clear()
        return got
    return None


def topic_fit(view, rec, phrase):
    """{item_id: score} for the record's items that hold `phrase`, with the cut (score >= cut fits), or None when the
    library has no vectors or too few items hold it to tell."""
    import numpy as np
    vs = _vector_store(view.lib)
    if vs is None:
        return None
    key = (view.lib, id(rec), phrase)
    with _LOCK:
        if key in _FITS:
            return _FITS[key]
    pos, mat, scale = vs
    have = [i for i in rec.events if view.items.get(i) is not None and i in pos
            and holds(view.items[i].caption or "", phrase)]
    if len(have) < FIT_MIN:
        out = None
    else:
        rows = sorted(pos[i] for i in have)
        m = np.asarray(mat[rows], dtype=np.float32)
        if scale is not None:
            m = m * scale
        m /= np.linalg.norm(m, axis=1, keepdims=True) + 1e-9
        order = {r: k for k, r in enumerate(rows)}
        keep = np.ones(len(rows), bool)
        s = None
        for _ in range(2):
            c = m[keep].mean(0)
            c /= np.linalg.norm(c) + 1e-9
            s = m @ c
            keep = s >= np.quantile(s, FIT_TRIM)
        cut = float(np.median(s)) - FIT_CUT
        out = ({i: float(s[order[pos[i]]]) for i in have}, cut)
        with _LOCK:
            _CENTS[key] = c   # round 11 fix pass 2 (P5c): any other item can be scored against it
    with _LOCK:
        _FITS[key] = out
    return out


_CENTS = {}


def fit_score(view, rec, phrase, iid):
    """Round 11 fix pass 2 (P5c): (the item's score against the topic's centroid, the cut) for any item with a stored
    vector, also one that does not hold the words (a summary's other word forms: "cooked" for "cooking"), or None
    when the topic's fit can't be told."""
    import numpy as np
    fit = topic_fit(view, rec, phrase)
    vs = _vector_store(view.lib)
    if fit is None or vs is None:
        return None
    if iid in fit[0]:
        return fit[0][iid], fit[1]
    pos, mat, scale = vs
    c = _CENTS.get((view.lib, id(rec), phrase))
    if c is None or iid not in pos:
        return None
    v = np.asarray(mat[pos[iid]], dtype=np.float32)
    if scale is not None:
        v = v * scale
    v /= np.linalg.norm(v) + 1e-9
    return float(v @ c), fit[1]


FIT_WATCHED_MIN = 6   # round 11 fix pass 2 (P6): fewer items of the kind asked hold the word: all shown, "mention"


def few_watched(view, rec, q, plats):
    """Round 11 fix pass 2 (P6): fewer than FIT_WATCHED_MIN items of the kind asked hold the topic's words. The check
    of fix pass 2 (DESIGN 18.L2 check): also True when the fit keeps none of them at any time (a topic whose record
    matches are mostly saves pointing elsewhere: "you watched no videos about X" while six watched titles say X);
    they are then shown by their words, "mention", as below the threshold."""
    if not q.topic or q.channel:
        return False
    h = hits(view, rec, q, None, None, plats)
    if len(h) < FIT_WATCHED_MIN:
        return True
    kept, _left, used = fit_hits(view, rec, q, h)
    return used and not kept


def fit_hits(view, rec, q, h):
    """(the hits that fit q's topic, how many were left out, whether the fit was used) for a first, last or list
    answer; the word matches unchanged when the fit can't be told. Round 11 fix pass 2 (P6, the orchestrator's
    decision): the callers skip it when fewer than FIT_WATCHED_MIN items the person watched (or liked, or saved: the
    kind asked) hold the topic's words, in the platforms asked and at any time (few_watched): they are all shown and
    said to "mention" it; the fit (whose centroid is made of every item that holds the words, mostly saves on a real
    library) is used only above that."""
    if not q.topic or q.channel or not h:
        return h, 0, False
    fits = [topic_fit(view, rec, x) for x in q.topic]
    if any(f is None for f in fits):
        return h, 0, False
    kept = {i: ds for i, ds in h.items() if any(i in f[0] and f[0][i] >= f[1] for f in fits)}
    return kept, len(h) - len(kept), True


def _nothing_fit(q, W, plats, left):
    """Round 11 fix, A (R3): the window holds only items that mention the topic without being about it."""
    if q.lang == "es":
        s = f"{W} no {verb(q)} {'ningún video' if q.how == 'watched' else 'nada'} sobre {topic_words(q)}."
    else:
        s = f"{W} you {verb(q)} no {noun(q, 2, plats)} about {topic_words(q)}."
    return s + " " + _left_line(q, left)


def _about_fit(q, used, n=2):
    """' about "cooking"' when the fit was used, else the word match's ' that mention "cooking"'."""
    if not used:
        return _about(q, n)
    return (" sobre " if q.lang == "es" else " about ") + topic_words(q)


def _left_line(q, left):
    if not left:
        return ""
    if q.lang == "es":
        return (f"(Otros {left} mencionan {topic_words(q)} pero no parecen ser de eso, así que no los cuento aquí.)"
                if left > 1 else f"(Otro menciona {topic_words(q)} pero no parece ser de eso, así que no lo cuento aquí.)")
    return (f"({left} more mention {topic_words(q)} but don't seem to be about it, so I left them out.)" if left > 1
            else f"(1 more mentions {topic_words(q)} but doesn't seem to be about it, so I left it out.)")
# ---------- end round 11 fix, A (R3) ----------


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
def answer(view, q, today, prof=None, rec=None, said_end=False, quiet=()):
    """(text, [item ids shown in order], extra) for a query. `extra`: {"channels": [...] for a ranking, "cards": True
    when the items go out as link cards, "said": the notes said}. `said_end`: the reply already says where the export
    ends. `quiet` (round 11 fix, A, R4): notes said already in this stretch ("friends", "range"), left out now."""
    rec = rec or record(view, "UTC")
    plats = _scope_platforms(q, view, rec)
    if q.topic and not q.channel and len(q.topic) == 1:
        # a topic is a topic first; it is a channel when the message says so ("from X", "X's channel"), or when no
        # title in the scope mentions it and a channel has exactly that name
        ch = channel_of(view, q.topic[0])
        if ch and (q.channel_hint or not any(holds(view.items[i].caption or "", q.topic[0])
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
        head += " " + REFRESH[lang]   # wholly after the record: the hint always stays (as a summary's, seam d)
        w2 = shifted(q.window, start, end, newest)
        q2 = q.model_copy(update={"window": w2})
        if q.kind == "compare":
            q2 = q.model_copy(update={"kind": "count", "window": w2, "window2": None})
        body, ids, extra = answer(view, q2, today, prof, rec, said_end=True, quiet=quiet)
        extra = dict(extra, said=list(extra.get("said") or []) + ["refresh"])
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
    said = []
    if said_end:
        pass
    elif q.window.kind == "all" and "range" not in quiet:
        tail.append(range_line(rec, plats, q))
        said.append("range")
        if "refresh" not in quiet:   # round 11 fix pass 2 (P5b): the hint once in 6 hours
            tail.append(REFRESH[lang])
            said.append("refresh")
    elif q.window.kind == "all":
        # round 11 fix, A (R4): the range was said in this stretch; an answer about the latest items still says where
        # the record ends (it changes the answer), the others say nothing more
        if q.kind in ("last", "list", "on_day") and reached:
            tail.append(ends_line(rec, reached, lang))
    elif reached:
        # the round 11 check (DESIGN 18.X): each platform whose export the window reaches is said, so "October 1 to
        # 15" says Instagram's ends on the 15th even while YouTube's runs on
        tail.append(ends_line(rec, reached, lang))
        # round 11 fix pass 2 (P5b): where the export ends always stays (it changes the answer); the hint on sending
        # a new export is said once in 6 hours, as summaries do (seam d)
        if not ({"refresh", "range"} & set(quiet)):
            tail.append(REFRESH[lang])
            said.append("refresh")
    if q.how == "saved":
        tail.append("(Guardado cuenta lo guardado, las colecciones, lo que te enviaste y las listas.)" if es else
                    "(Saved counts saves, collections, posts you sent yourself and playlists.)")
    if "instagram" in plats and "friends" not in quiet:   # friends' posts are an Instagram matter
        tail.append("No cuento las publicaciones de tus amigos." if es else "Posts from friends are not counted.")
        said.append("friends")   # round 11 fix, A (R4): once in a stretch of 6 hours
    extra = dict(extra, tail=" ".join(x for x in tail if x), said=said)
    return text + ("\n\n" + extra["tail"] if extra["tail"] else ""), ids, extra


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


def _opening(q, n, W, plats, extra="", fitted=False):
    about = _about_fit(q, fitted, n)   # round 11 fix, A (R3): "about" only when the engine's fit chose the items
    if q.lang == "es":
        return f"{W} {verb(q)} {num(n, 'es')} {noun(q, n, plats)}{about}{extra}."
    return f"{W} you {verb(q)} {num(n)} {noun(q, n, plats)}{about}{extra}."


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
        word = who_word(view, h, n, q.lang)   # round 11 fix, A (R7)
        if es:
            return f"{pre}{W} {verb(q)} videos de {num(n, 'es')} {word}.", [], {}
        return f"{pre}{W} you {verb(q)} {noun(q, 2, plats)} from {num(n)} {word}.", [], {}
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
        word = who_word(view, h, len(c), q.lang)   # round 11 fix, A (R7)
        lines.append(f"({num(len(c), 'es')} {word} en total.)" if es else f"({num(len(c))} {word} in all.)")
    if q.topics_too:
        tl = _topic_line(view, h, prof, q.lang)
        if tl:
            lines.append(tl)
    return "\n".join(lines), [], {"channels": [name for name, _ in top]}


def who_word(view, ids, n, lang="en"):
    """Round 11 fix, A (R7): what the counted creators are: YouTube channels, Instagram accounts, or both."""
    plats = {view.items[i].platform for i in ids if view.items[i].creator}
    one = n == 1
    if plats == {"instagram"}:
        return ("cuenta" if one else "cuentas") if lang == "es" else ("account" if one else "accounts")
    if "instagram" in plats:
        return ("cuenta o canal" if one else "cuentas y canales") if lang == "es" else \
            ("account or channel" if one else "accounts and channels")
    return ("canal" if one else "canales") if lang == "es" else ("channel" if one else "channels")


def _topic_counts(view, ids, prof):
    from . import profile as P
    from .attention import topic_words_of
    out = []
    for i in (prof or {}).get("interests") or []:
        if i.get("relation") == "not_me" or P.sensitive(i.get("topic"), i.get("why"), " ".join(i.get("words") or [])):
            continue
        words = topic_words_of(i)
        support = set(i.get("support_ids") or [])
        n = sum(1 for x in ids if x in support or any(holds(view.items[x].caption, w) for w in words))
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
    # round 11 fix, A (R3); fix pass 2 (P6): only with enough watched items that hold the words
    h, left, fitted = (h, 0, False) if few_watched(view, rec, q, plats) else fit_hits(view, rec, q, h)
    if not h:
        return _nothing_fit(q, W, plats, left), [], {}
    cap = DAY_MAX if q.kind == "on_day" else LIST_MAX
    order = sorted(h, key=lambda i: (-max(h[i]).toordinal(), i))
    page = order[q.offset:q.offset + cap]
    if not page:
        return ("No hay más." if es else "That's all of them."), [], {}
    if q.offset:
        lines = [(f"Los siguientes {len(page)}:" if es else f"The next {len(page)}:")]
    elif q.kind == "on_day":
        lines = [_opening(q, len(h), W, plats, fitted=fitted)[:-1] + ":"]
    else:
        k = len(page)
        lines = [_opening(q, len(h), W, plats, fitted=fitted) + (f" Los {k} más recientes:" if es else
                                                                 (" The latest:" if k == 1 else f" The latest {k}:"))]
    lines += [item_line(q.offset + k, view.items[i], max(h[i]), q.lang, today) for k, i in enumerate(page, 1)]
    rest = len(order) - q.offset - len(page)
    if rest > 0:
        lines.append(f"Y {rest} más (di \"más\" para verlos)." if es else f"And {rest} more (say \"more\" to see them).")
    if left and not q.offset:
        lines.append(_left_line(q, left))
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
    # round 11 fix, A (R3); fix pass 2 (P6): only with enough watched items that hold the words
    h, left, fitted = (h, 0, False) if few_watched(view, rec, q, plats) else fit_hits(view, rec, q, h)
    if not h:
        return _nothing_fit(q, W, plats, left), [], {}
    key = (lambda i: (-max(h[i]).toordinal(), i)) if last else (lambda i: (min(h[i]), i))
    order = sorted(h, key=key)[:FIRST_MAX]
    d0 = max(h[order[0]]) if last else min(h[order[0]])
    n1 = noun(q, 1, plats)
    win = "" if q.window.kind == "all" else " " + window_words(q.window, start, end, q.lang, cap=False)
    if es:
        word = "último" if last else "primer"
        head = f"El {word} {n1} que {verb(q)}{_about_fit(q, fitted, 1)}{win} fue el {day_words(d0, 'es')}:"
    else:
        head = (f"The {'last' if last else 'first'} {n1} you {verb(q)}{_about_fit(q, fitted, 1)}{win} was on "
                f"{day_words(d0)}:")
    lines = [head]
    for k, i in enumerate(order, 1):
        lines.append(item_line(k, view.items[i], max(h[i]) if last else min(h[i]), q.lang, None, url=False))
    if len(h) > 1:
        lines.append((f"({num(len(h), 'es')} en total" if es else f"({num(len(h))} in all") +
                     (f"{win}.)" if win else ".)"))
    if left:   # round 11 fix, A (R3): one line with the count, "(98 in all. 15 more mention ...)"
        ll = _left_line(q, left)
        if len(h) > 1:
            lines[-1] = lines[-1][:-1] + " " + ll[1:]
        else:   # the merge of round 11's fixes: one item left: its line stays, the count after it (it replaced it)
            lines.append(ll)
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
    # ---------- round 11 fix, A (R6): start at the first year (or month) with a count, never a row of leading zeros
    none_before = None
    seen = [d for ds in h.values() for d in ds if lo <= d <= hi]
    if seen and min(seen) > lo:
        f0 = min(seen)
        span_by_month = q.by == "month" if q.by else (hi.year - f0.year) * 12 + hi.month - f0.month < 18
        new_lo = date(f0.year, f0.month, 1) if span_by_month else date(f0.year, 1, 1)
        if new_lo > lo:
            none_before = new_lo if (new_lo.year, new_lo.month) > (lo.year, lo.month) and (
                span_by_month or new_lo.year > lo.year) else None
            lo = new_lo
    # ---------- end round 11 fix, A (R6) ----------
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
    if none_before:   # round 11 fix, A (R6)
        when = month_words(none_before, q.lang) if by_month else str(none_before.year)
        lines[1] += f" Nada antes de {when}." if es else f" None before {when}."
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
    if sum(1 for v in c.values() if v == n) > 1:
        return None   # round 11 fix check (18.L check): a tie has no "most" ("The most: November 2026, with 1." of four 1s)
    return (k, n) if n else None


def _compare(view, rec, q, start, end, plats, W, today, prof):
    es = q.lang == "es"
    s2, e2 = resolve(q.window2, rec, plats, today)
    a = len(hits(view, rec, q, start, end, plats))
    b = len(hits(view, rec, q, s2, e2, plats))
    W2 = window_words(q.window2, s2, e2, q.lang, cap=False)
    short = window_words(q.window, start, end, q.lang, cap=False)
    # ---------- round 11 fix, A (R5): the answer to "more in X or Y?" first, then both counts ----------
    if a != b:
        less = q.less
        hi_w, hi_n, lo_w, lo_n = (short, a, W2, b) if (a > b) != less else (W2, b, short, a)
        n2 = noun(q, 2 if hi_n != 1 else 1, plats)
        d = abs(a - b)
        if es:
            word = "Menos" if less else "Más"
            return (f"{word} {hi_w}: {num(hi_n, 'es')} {n2}{_about(q, hi_n)}, frente a {num(lo_n, 'es')} {lo_w} "
                    f"({num(d, 'es')} {'menos' if less else 'más'})."), [], {}
        word = "Fewer" if less else "More"
        return (f"{word} {hi_w}: {num(hi_n)} {n2}{_about(q, hi_n)}, against {num(lo_n)} {lo_w} "
                f"({num(d)} {'fewer' if less else 'more'})."), [], {}
    # ---------- end round 11 fix, A (R5) ----------
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
# ---------- round 11 fix, A (R4): the friends line and the all-time range, once in a stretch of 6 hours ----------
NOTES = "histnotes:{h}"


def said_lately(bot, h, now):
    """The notes ("friends", "range") a history answer said to this person in the last 6 hours."""
    st = bot.store.get_state(NOTES.format(h=h)) or {}
    out = set()
    for k, at in st.items():
        try:
            if now - datetime.fromisoformat(at) < timedelta(hours=FOLLOW_HOURS):
                out.add(k)
        except (TypeError, ValueError):
            continue
    return out


def note_said(bot, h, now, said):
    if not said:
        return
    st = dict(bot.store.get_state(NOTES.format(h=h)) or {})
    from .store import now_iso
    for k in said:
        st[k] = now_iso(now)
    bot.store.set_state(NOTES.format(h=h), st)
# ---------- end round 11 fix, A (R4) ----------
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
    elif q.kind in ("list", "on_day") and re.match(r"^\W*(?:how many|how much|cuant[oa]s?)\b", body):
        # the check of fix pass 2: "and how many in september?" after a list is a count, not the list again
        changes.update(kind="count", offset=0)
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
            return any(holds(it.caption or "", x) for it in view.items.values())
        f = follow_up(st, text, today, known)
        if isinstance(f, tuple):
            return _pick(bot, person, st, f[1], now, today)
        if f is not None:
            return send_answer(bot, person, f, now, follow=True)
    # ---------- round 11 fix, A (R1): "what was that video i watched about X" is a recall of the record ----------
    r = read_recall(text, today)
    if r is not None:
        ref = recall_answer(bot, person, r, now)
        if ref is not None:
            return ref
    # ---------- end round 11 fix, A (R1) ----------
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
    quiet = said_lately(bot, h, now)
    text, ids, extra = answer(view, q, today, P.get(bot.store, h), rec, quiet=quiet)
    note_said(bot, h, now, extra.get("said") or ())
    bot.note(intent="history")
    tail = extra.get("tail") or ""
    if extra.get("cards") and (not tail or text.endswith(tail)):
        # the cards of the first or last items go right under their lines, before where the record ends
        body = text[:-len(tail)].rstrip() if tail else text
        parts = [{"type": "text", "text": (lead + "\n\n" if lead else "") + body}]
        parts += [link_part(view.items[i], _title(view.items[i])) for i in ids if view.items[i].url]
        if tail:
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


# ====================================== round 11 fix, A (R1, R2, R8): recall ======================================
# "what was that video i watched about color grading" asks the record for one thing seen before: never a pick, never
# "I recommend". Read by code (`read_recall`), answered by code (`recall_answer`): the videos the person WATCHED
# (YouTube first; watched reels only when the message says reel or post, or nothing on YouTube fits), best fit first
# (the engine's ranking of the words, then how much of them the item's text holds, then the library's own vectors),
# up to 3, each with the day it was watched and its card. The first is the pick in view, so "what did it say about X"
# and "ask the video" work on it. Nothing watched fits: said, with the saved one that does. A plain "find me a video
# about X" stays a pick (it is not read here).
RECALL_MAX = 3
_KIND = r"(?:youtube\s+|yt\s+|insta(?:gram)?\s+|ig\s+)?(?P<kind>videos?|vids?|reels?|posts?|clips?|shorts?|tiktoks?|" \
        r"tutorials?)"
_SAW = (r"(?:i|we)\s+(?:once\s+|already\s+|just\s+|recently\s+|literally\s+)?(?:watched|saw|seen|viewed|"
        r"was\s+watching|have\s+watched|have\s+seen|'ve\s+watched|'ve\s+seen|had\s+watched|watched\s+on\s+youtube)")
_LEAD = (r"^\W*(?:(?:hey|yo|ok|okay|so|um+|uh+|wait|hmm+)[,\s]+)*(?:(?:can|could)\s+you\s+(?:help\s+me\s+)?|"
         r"(?:please\s+)?help\s+me\s+|pls\s+|please\s+)?")
RECALL = [
    # "what was that video i watched about X", "find the video i watched on X last month", "remember that reel i saw ..."
    re.compile(_LEAD + r"(?:(?:do\s+you\s+)?(?:remember|recall|know)\s+|what(?:'s|\s+is|\s+was|\s+were)\s+(?:the\s+"
               r"name\s+of\s+|the\s+title\s+of\s+)?|which\s+(?:one\s+)?(?:was|is)\s+|find\s+(?:me\s+)?|"
               r"look\s+up\s+|where(?:'s|\s+is)\s+|show\s+me\s+|get\s+me\s+|what\s+was\s+)?(?:that|the|this)\s+"
               + _KIND + r"\s+(?:that\s+|which\s+)?" + _SAW + r"\b(?P<rest>.*)$"),
    # "what's that video where ...", "remember that reel with the ..." ("what was that video about X", with no "i
    # watched", stays the interpreter's: "that video" may be a pick the bot showed)
    re.compile(_LEAD + r"(?:what(?:'s|\s+is|\s+was)\s+(?:the\s+name\s+of\s+)?|which\s+(?:one\s+)?was\s+|"
               r"(?:do\s+you\s+)?(?:remember|recall)\s+|find\s+(?:me\s+)?)that\s+" + _KIND +
               r"\s+(?P<prep>where|with|when)\s+(?P<rest>.+)$"),
    re.compile(_LEAD + r"what(?:'s|\s+is|\s+was)\s+the\s+" + _KIND + r"\s+(?P<prep>where|with|when)\s+(?P<rest>.+)$"),
    # "which video did i watch about X" (one video: "which videos did i watch ..." is a history list)
    re.compile(_LEAD + r"which\s+(?P<kind>video|vid|reel|clip|post|short|tutorial)\s+(?:was\s+it\s+(?:that\s+)?)?"
               r"(?:did|have)\s+i\s+(?:watch|see|watched|seen)\s+(?P<rest>(?:about|on|where|with|that|of|from)\b.+)$"),
    # "i watched something about X a while ago, what was it"
    re.compile(r"^\W*(?:(?:so|ok|okay|hey|yo)[,\s]+)?i\s+(?:once\s+|recently\s+)?(?:watched|saw)\s+(?:a|this|some|one|"
               r"that)\s+(?:youtube\s+)?(?:(?P<kind>video|vid|reel|clip|post|short|tutorial)|thing|something)\s+"
               r"(?P<rest>.+?)[,.;!\s-]+(?:and\s+)?(?:what\s+was\s+it(?:\s+called)?|what\s+was\s+that|which\s+(?:one\s+)?"
               r"was\s+it|what'?s\s+it\s+called|can\s+you\s+find\s+it|find\s+it|do\s+you\s+know\s+which(?:\s+one)?|"
               r"what\s+was\s+the\s+name)\W*$"),
    re.compile(r"^\W*(?:(?:so|ok|okay|hey|yo)[,\s]+)?i\s+(?:once\s+|recently\s+)?(?:watched|saw)\s+something\s+"
               r"(?P<rest>.+?)[,.;!\s-]+(?:and\s+)?(?:what\s+was\s+it(?:\s+called)?|what\s+was\s+that|which\s+(?:one\s+)?"
               r"was\s+it|what'?s\s+it\s+called|can\s+you\s+find\s+it|find\s+it|do\s+you\s+know\s+which(?:\s+one)?)\W*$"),
]
# "that <channel> video about X": read only when <channel> is a channel of the library (recall_answer checks it)
RECALL_CHANNEL = re.compile(_LEAD + r"(?:what(?:'s|\s+is|\s+was)\s+|find\s+(?:me\s+)?|(?:do\s+you\s+)?remember\s+)?"
                            r"that\s+(?P<chan>[a-z0-9&'.@_ -]{2,40}?)\s+(?P<kind>video|vid|reel|clip|tutorial)\s+"
                            r"(?:i\s+(?:watched|saw)\s+)?(?P<prep>about|on|where|with)\s+(?P<rest>.+)$")
# what never makes a recall, whatever its shape: reminders, rules, acting, a pick asked for, feedback
RECALL_NOT = re.compile(
    r"\b(?:remind|reminder|every|each|daily|weekly|from now on|whenever|should i|recommend\w*|suggest\w*|"
    r"something (?:new )?to watch|to watch (?:tonight|today|tomorrow|next|later)|"
    r"(?:add|put|save|send|email|e-mail|text|forward|share|dm|bookmark)\s+(?:it|this|that|them|those|me|to)|"
    r"delete|remove|unsubscribe|calendar|to-?do|my list|summar\w*|ask the video|ask video|"
    r"(?:was|is|were)\s+(?:so\s+|really\s+|too\s+|pretty\s+|kinda\s+)?(?:good|great|bad|boring|long|short|funny|"
    r"awesome|amazing|terrible|wrong|helpful|useless|cool|mid|fire|trash))\b")
_TAIL = re.compile(r"[,.;!\s-]*(?:\b(?:a\s+while\s+(?:ago|back)|a\s+long\s+time\s+ago|the\s+other\s+day|recently|"
                   r"before|once|again|at\s+some\s+point|some\s+time\s+ago|a\s+bit\s+ago|lol|haha|pls|please|i\s+think|"
                   r"or\s+something|on\s+youtube|on\s+yt|on\s+instagram|on\s+insta|on\s+ig|the\s+other\s+week|"
                   r"what\s+was\s+it(?:\s+called)?|do\s+you\s+remember|can\s+you\s+find\s+it|"
                   r"remember)\b[,.;!\s-]*)+$")
_PREP = re.compile(r"^\W*(?:(?:it\s+was\s+|that\s+was\s+|which\s+was\s+)?(?:about|on|where|with|of|from|when|that|"
                   r"which|in\s+which|explaining|showing|talking\s+about|covering)\s+)+")
GENERIC = set("""guy girl man woman dude bro someone somebody person people they he she him her his them explains
explained explain shows showed show talks talked talking makes made does did thing things stuff cool funny really
very kind sort how way some one video videos reel reels clip clips tutorial tutorials youtube instagram yt ig insta
was were is are it this that these those like literally basically out up down off into onto back where""".split())


REMIND_WHAT = re.compile(r"^\W*(?:(?:can|could)\s+you\s+|pls\s+|please\s+)?remind\s+me\s+(?P<wh>what|which)\s+"
                         r"(?P<rest>(?:that|the|this)\s+(?:youtube\s+|yt\s+|insta(?:gram)?\s+)?(?:videos?|vids?|reels?|"
                         r"posts?|clips?|shorts?|tutorials?)\s+.+?)\s+(?:was|is|was\s+called|is\s+called)$")


def phrasing_time(t):
    from .phrasing import TIME_WORDS
    return bool(TIME_WORDS.search(t)) or bool(re.search(r"\b(?:later|tonight|tomorrow|in\s+an?\s+(?:hour|bit))\b", t))


class Recall(BaseModel):
    """The form a recall is read into: the words to find, the kind said, a time window, a channel phrase."""
    words: str
    kind: Optional[str] = None
    window: Optional[Window] = None
    chan: Optional[str] = None


def read_recall(text, today):
    """A Recall for "what was that video i watched about X" and its shapes, else None."""
    raw = " ".join((text or "").split())
    if not raw or len(raw) > 220:
        return None
    t = normal(raw).rstrip(" ?!.")
    t = re.sub(r"\b(?:abt|abour|abut)\b", "about", t)   # round 11 fix check: "abt skin tones" said "abt" back
    # round 11 fix pass 2 (P4): "remind me what that video i watched about X was" asks to be told now, never a
    # reminder: read as "what was that video ..." when it names no time (a time or a repeat leaves it to the rules)
    m0 = REMIND_WHAT.match(t)
    if m0 and not TIMING.search(t) and not phrasing_time(t):
        t = f"{m0.group('wh')} was {m0.group('rest')}"
    if RECALL_NOT.search(t) or BOT_ASK.search(re.sub(r"\b(?:can|could|do)\s+you\b", " ", t)):
        return None
    m, chan = None, None
    for rx in RECALL:
        m = rx.match(t)
        if m:
            break
    if m is None:
        m = RECALL_CHANNEL.match(t)
        if m is None:
            return None
        chan = m.group("chan").strip()
        if chan.split()[0] in ("one", "same", "other", "first", "last", "new", "old", "youtube", "instagram", "long",
                               "short", "funny", "cool", "good", "weird", "random"):
            chan = None
    rest = (m.group("rest") or "").strip()
    rest = _TAIL.sub("", rest)
    rest = _PREP.sub("", rest).strip(" ,.?!")
    kind = (m.groupdict().get("kind") or "").rstrip("s") or None
    if kind in ("vid", "short", "tutorial", "clip", "tiktok"):
        kind = "video"
    window = None
    wins = find_windows(rest, today)
    if wins:
        spans = [s for _, s in wins]
        ws = [w for w, _ in wins if isinstance(w, Window)]
        window = ws[0] if ws else None
        rest = "".join(" " if any(a <= i < b for a, b in spans) else c for i, c in enumerate(rest))
        rest = re.sub(r"\s+(?:in|on|from|during|around|back\s+in)\s*$", "", " ".join(rest.split())).strip(" ,.")
        rest = _TAIL.sub("", rest).strip(" ,.?!")
    if not content_words(rest):
        return None
    if len(rest.split()) > 14:
        return None
    return Recall(words=rest, kind=kind, window=window, chan=chan)


def content_words(phrase):
    toks = re.findall(r"[a-z0-9][a-z0-9&'+.#-]*", normal(phrase))
    # the merge of round 11's fixes: "after effects" is a name here too, as in the history read (a recall said
    # "about \"effects\"" and a summary's fit read "effects")
    return [w for k, w in enumerate(toks)
            if (w.strip(".'-") == "after" and toks[k + 1:k + 2] and toks[k + 1].strip(".'-") == "effects")
            or (w.strip(".'-") not in STOP and w.strip(".'-") not in GENERIC and len(w.strip(".'-")) >= 2
                and not w.isdigit())]


def _watched_on(rec, iid, start=None, end=None):
    return [d for d, k in rec.events.get(iid, ()) if k in ("watch", "view")
            and (start is None or d >= start) and (end is None or d <= end)]


def _engine_rank(bot, person, words, now):
    """{item_id: rank} from the engine's own ranking of the words (one search, cached for the library build), or {}
    when the person is over a cap or the search fails (then the words and the vectors order alone)."""
    from .retrieve import ranked
    try:
        if bot._over_cap(person):
            return {}
        r = ranked(bot.pool, person["library"], words, store=bot.store, now=now)
    except Exception:  # noqa: BLE001 - a recall still answers from the words when the engine can't
        return {}
    return {i: k for k, i in enumerate(r.get("ids") or [])}


def _recall_level(text, phrase, words):
    """3 when the item's text holds the whole phrase, 2 all its words, 1 one of them, 0 none."""
    if len(phrase.split()) <= 4 and holds(text, phrase):
        return 3
    got = sum(1 for w in words if holds(text, w))
    if words and got == len(words):
        return 2
    return 1 if got else 0


def _few_watched(view, rec, phrase, words, platforms, how):
    """Round 11 fix pass 2 (P6): fewer than FIT_WATCHED_MIN items of the kind counted (watched, for a recall), in the
    platforms asked, hold the words (all of them, or the phrase), at any time. The check of fix pass 2: also True when
    the topic's fit keeps none of them (they are then shown by their words, "mention", never "Nothing you watched
    fits" and a save instead)."""
    n, have = 0, []
    for iid, evs in rec.events.items():
        it = view.items.get(iid)
        if it is None or (platforms and it.platform not in platforms) or not any(k in how for _, k in evs):
            continue
        if _recall_level(it.caption or "", phrase, words) >= 2:
            n += 1
            have.append(iid)
    if n < FIT_WATCHED_MIN:
        return True
    fit = topic_fit(view, rec, phrase)
    return fit is not None and not any(i in fit[0] and fit[0][i] >= fit[1] for i in have)


def recall_fitted(view, rec, r, platforms, how=("watch", "view")):
    """True when a recall's items were chosen by the topic's fit (said "about"), False when by the words ("mention")."""
    words = content_words(r.words)
    phrase = " ".join(words) if len(words) <= 4 else r.words
    if len(words) > 4 or topic_fit(view, rec, phrase) is None:
        return False
    return not _few_watched(view, rec, phrase, words, platforms, how)


def recall_items(bot, person, r, now, platforms=None, how=("watch", "view"), limit=RECALL_MAX, rank=None):
    """The items for a recall, best first: [(item, level, [dates])]. `how`: the event kinds counted."""
    from .compose import NEUTRAL_TITLES, display_title
    tz = person.get("timezone") or "UTC"
    view = bot.view(person["library"])
    rec = record(view, tz)
    words = content_words(r.words)
    phrase = " ".join(words) if len(words) <= 4 else r.words
    start, end = (r.window.start, r.window.end) if r.window else (None, None)
    ckey = _squash(r.chan) if r.chan else None
    rank = rank if rank is not None else {}
    fit = topic_fit(view, rec, phrase) if len(words) <= 4 else None
    if fit is not None and _few_watched(view, rec, phrase, words, platforms, how):
        fit = None   # round 11 fix pass 2 (P6): few of them hold the words: all shown, "mention"
    out = []
    for iid, evs in rec.events.items():
        it = view.items.get(iid)
        if it is None or (platforms and it.platform not in platforms):
            continue
        if ckey is not None and _squash(it.creator) != ckey:
            continue
        ds = [d for d, k in evs if k in how and (start is None or d >= start) and (end is None or d <= end)]
        if not ds:
            continue
        lv = _recall_level(it.caption or "", phrase, words)
        if lv == 0 or (lv == 1 and rank.get(iid, 10 ** 9) >= 50):
            continue
        if fit is not None and iid in fit[0] and fit[0][iid] < fit[1]:
            continue   # R3: it holds the words, but its vector says it is about something else
        score = fit[0].get(iid, 0.0) if fit else 0.0
        # the check of fix pass 2: a video with a title of its own comes before one shown as "A video from <channel>"
        # (the person can't tell what that one is, and it is never asked unless named by its number)
        untitled = display_title(it).startswith(NEUTRAL_TITLES)
        out.append((it, lv, ds, (-lv, untitled, rank.get(iid, 10 ** 9), -score, -max(ds).toordinal(), iid)))
    out.sort(key=lambda x: x[3])
    if out and out[0][1] >= 2:   # one that holds only one of the words is shown only when nothing holds them all
        out = [x for x in out if x[1] >= 2]
    return [(it, lv, ds) for it, lv, ds, _ in out[:limit]]


def recall_answer(bot, person, r, now):
    """The recall's reply (its reference), or None when the message names a channel the library doesn't have."""
    from .render import Reply, by, link_part
    from .store import now_iso
    h = person["handle"]
    tz = person.get("timezone") or "UTC"
    view = bot.view(person["library"])
    rec = record(view, tz)
    if r.chan:
        ch = channel_of(view, r.chan)
        if not ch:
            return None
        r = r.model_copy(update={"chan": ch})
    t0 = datetime.now()
    bot.note(intent="history")
    words = content_words(r.words)
    shown_words = " ".join(words) if len(words) <= 4 else r.words
    rank = _engine_rank(bot, person, r.words, now)
    want_ig = r.kind in ("reel", "post")
    first, second = (["instagram"], ["youtube"]) if want_ig else (["youtube"], ["instagram"])
    got = recall_items(bot, person, r, now, platforms=first, rank=rank)
    fell = False
    if not got:
        got = recall_items(bot, person, r, now, platforms=second, rank=rank)
        fell = bool(got)
    head_bits = f"\"{shown_words}\""
    if r.chan:
        head_bits += f" from {r.chan}"
    win = (" " + window_words(r.window, r.window.start, r.window.end, cap=False)) if r.window and r.window.start else ""
    parts = []
    ids = []
    if got:
        noun_ = "reel" if got[0][0].platform == "instagram" else "video"
        lead = ""
        if fell:
            lead = (f"No reel you watched{win} fits {head_bits}. " if want_ig else
                    f"No YouTube video you watched{win} fits {head_bits}. ")
        # round 11 fix pass 2 (P6): "about" only when the topic's fit chose them, else what their words say
        fitted = recall_fitted(view, rec, r, second if fell else first)
        if len(got) == 1:
            lead += (f"You watched this {noun_} about {head_bits}{win}:" if fitted else
                     f"You watched this {noun_} that mentions {head_bits}{win}:")
        else:
            lead += (f"You watched these about {head_bits}{win}, best match first:" if fitted else
                     f"You watched these that mention {head_bits}{win}, best match first:")
        parts.append({"type": "text", "text": lead})
        for k, (it, lv, ds) in enumerate(got, 1):
            title = _title(it)
            all_w = _watched_on(rec, it.id)
            n = len(all_w)
            when = (f"You watched it on {day_words(max(ds))}." if n <= 1 else
                    f"You watched it {n} times, last on {day_words(max(all_w))}.")
            num_ = f"{k}. " if len(got) > 1 else ""
            parts.append({"type": "text", "text": f"{num_}{title}{by(it, title=title)}. {when}"})
            if it.url:
                parts.append(link_part(it, title))
            ids.append(it.id)
    else:
        saved = recall_items(bot, person, r.model_copy(update={"window": None}), now, platforms=None,
                             how=("save", "collection", "share_self", "playlist", "like"), limit=1, rank=rank)
        if saved:
            it, _, ds = saved[0]
            title = _title(it)
            kinds = {k for d, k in rec.events.get(it.id, ())}
            verb_ = "saved" if kinds & {"save", "collection", "share_self", "playlist"} else "liked"
            parts.append({"type": "text", "text": f"Nothing you watched{win} fits {head_bits}. You {verb_} one about "
                                                  f"it: {title}{by(it, title=title)} ({verb_} on {day_words(max(ds))})."})
            if it.url:
                parts.append(link_part(it, title))
            ids.append(it.id)
        else:
            parts.append({"type": "text", "text": f"Nothing you watched{win} or saved fits {head_bits}. Try other words "
                                                  f"for it, or ask \"find me a video about {shown_words}\"."})
    if r.window and r.window.start:
        newest = max(rec.ends.values(), default=None)
        if newest and (r.window.end or r.window.start) >= newest:
            # round 11 fix pass 2 (P5b): the export's end always; the hint on a new export once in 6 hours
            hint = not ({"refresh", "range"} & said_lately(bot, h, now))
            parts.append({"type": "text", "text": ends_line(rec, sorted(rec.ends), "en") + (" " + REFRESH["en"]
                                                                                          if hint else "")})
            if hint:
                note_said(bot, h, now, ["refresh"])
    reply = Reply(parts)
    run_id = bot.store.add_run(handle=h, kind="history", at=now_iso(now), n_candidates=len(ids), n_picks=len(ids),
                               n_dropped=0, cost_usd=0.0, status="picked" if ids else "none", prompt_version=None,
                               seconds=round((datetime.now() - t0).total_seconds(), 3),
                               steps={"history": {"kind": "recall", "how": "watched", "platform": first[0],
                                                  "window": r.window.kind if r.window else "all",
                                                  "topic_words": len(words), "channel": bool(r.chan),
                                                  "engine": bool(rank), "fell_back": fell, "follow_up": False}})
    bot.note(run_id=run_id)
    recs = []
    for k, i in enumerate(ids, 1):
        it = view.items[i]
        bot.store.add_delivery(h, None, run_id, i, k, at=now)
        recs.append({"item_id": i, "title": _title(it), "url": it.url, "platform": it.platform,
                     "video_id": it.video_id, "creator": it.creator, "facts": {}, "lines": [], "line_kinds": None})
    goal = "history: recall"
    # the first is the pick in view ("what did it say about X", "ask the video"); "the second one" reads the state
    bot.store.set_last_answer(h, run_id, None, ids[:1], goal)
    bot.store.set_state(f"lines:{h}", {i: [] for i in ids[:1]})
    bot.store.set_state(f"linekinds:{h}", {i: None for i in ids[:1]})
    bot.store.set_state(f"facts:{h}", {i: {} for i in ids[:1]})
    bot._keep_answer(run_id, h, None, goal, "history", reply, recs)
    q = HistoryQuery(kind="list", topic=[shown_words] if len(words) <= 4 and words else [],
                     channel=r.chan, window=r.window or Window())
    bot.store.set_state(STATE.format(h=h), {"q": q.model_dump(mode="json"), "at": now_iso(now), "run_id": run_id,
                                            "ids": list(ids), "channels": [], "recall": True})
    return bot.send(h, reply, run_id)


def best_watched_video(bot, person, topic=None, item=None, latest=False, exclude=()):
    """Round 11 fix, A (R2, R8), for the offer after an Instagram post or reel in view: the YouTube video the person
    WATCHED that fits best, or None. `topic`: words ("color grading"); else `item`: a libview Item in view, matched by
    the words its caption shares with the video's and, when the library has them, by its stored vector. `latest`: the
    most recent fitting one instead of the best ("the last blender video"). Code only, no model call, no search."""
    import numpy as np
    tz = person.get("timezone") or "UTC"
    view = bot.view(person["library"])
    rec = record(view, tz)
    skip = set(exclude) | ({item.id} if item is not None else set())
    watched = {i: _watched_on(rec, i) for i, it in ((i, view.items.get(i)) for i in rec.events)
               if it is not None and it.platform == "youtube" and i not in skip}
    watched = {i: ds for i, ds in watched.items() if ds}
    if not watched:
        return None
    if topic:
        words = content_words(topic)
        if not words:
            return None
        phrase = " ".join(words) if len(words) <= 4 else topic
        cands = [i for i in watched if _recall_level(view.items[i].caption or "", phrase, words) >= 2]
        if not cands:
            return None
        fit = topic_fit(view, rec, phrase) if len(words) <= 4 else None
        if fit is not None:
            cands = [i for i in cands if i not in fit[0] or fit[0][i] >= fit[1]] or cands
        if latest or fit is None:
            best = max(cands, key=lambda i: (max(watched[i]), i))
        else:
            best = max(cands, key=lambda i: (fit[0].get(i, 0.0), max(watched[i]), i))
        return view.items[best]
    if item is None:
        return None
    words = [w for w in content_words(item.caption or "") if len(w) >= 4 and not w.startswith("#")][:20]
    if not words:
        return None
    shared = {}
    for i in watched:
        n = sum(1 for w in words if holds(view.items[i].caption or "", w))
        if n:
            shared[i] = n
    if not shared:
        return None
    vs = _vector_store(view.lib)
    if vs is not None and item.id in vs[0]:
        pos, mat, scale = vs
        rows = [i for i in shared if i in pos]
        if rows:
            m = np.asarray(mat[[pos[i] for i in rows]], dtype=np.float32)
            v = np.asarray(mat[pos[item.id]], dtype=np.float32)
            if scale is not None:
                m, v = m * scale, v * scale
            m /= np.linalg.norm(m, axis=1, keepdims=True) + 1e-9
            v /= np.linalg.norm(v) + 1e-9
            s = dict(zip(rows, (m @ v).tolist()))
            good = [i for i in rows if s[i] >= ITEM_NEAR]
            if not good:
                return None
            key = (lambda i: (max(watched[i]), i)) if latest else (lambda i: (s[i], shared[i], max(watched[i]), i))
            return view.items[max(good, key=key)]
    # no vectors: two shared words, or one of 5 letters or more ("blender", never "cat")
    long_ = [w for w in words if len(w) >= 5]
    good = [i for i in shared if shared[i] >= 2 or any(holds(view.items[i].caption or "", w) for w in long_)]
    if not good:
        return None
    key = (lambda i: (max(watched[i]), i)) if latest else (lambda i: (shared[i], max(watched[i]), i))
    return view.items[max(good, key=key)]


ITEM_NEAR = 0.5   # the cosine of two titles' stored vectors taken as "the same topic" (DESIGN 18.LA)


def history_topic(bot, handle, now):
    """The topic words of the history answer (or recall) still in view, else None: what an offer after it is about."""
    st = _fresh_state(bot, handle, now)
    if not st:
        return None
    try:
        q = HistoryQuery.model_validate(st["q"])
    except Exception:  # noqa: BLE001
        return None
    return " ".join(q.topic) if q.topic else None
# ====================================== end round 11 fix, A (R1, R2, R8) ==========================================


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
