"""The answer verifier of the brain (SPEC.md section 4): nothing made up, with free numbers.

The model sees the real numbers of this turn's tool results and types them, each followed by a marker naming the cell
it claims to be (`36%[r1.areas[0].share]`, `Clip Factory[r1.channels[0]]`, `up 16 points[=points(r1.areas[0].share,
r1.areas[0].previous_share)]`, `the top 3[r1.channels.count]`). Code checks every sentence against the ledger (the
results of the turn, in the envelope of SPEC 2.3) before anything is sent, one sentence at a time, and sends nothing it
could not verify. Pure code: the same input always gives the same verdict. No model call, no network, no store.

Steps (SPEC 4.3): shape; split; per sentence: parse the markers, one result per sentence, every number cited, the
typed value equals the cell, calc markers re-done by code, row names, outside text kept apart, insight's checks (the
sentence turned into insight's slotted form and run through `insight.render` and `insight.check_sentence` against
the cited result's sheet), claims with no marker, psych and outcome words, sensitive words, "least", rank with hidden
rows, once, window words; then items, outside lines (4.4) and the verdict, with the repair text of 4.5.

How insight's checks are used one sentence at a time (the proof is in eval/convert_insight_cases.py and the design
session's verify_proof.md): every verified row marker and every cited plain name becomes that row's name slot (a name
left as typed beside a number slot fails `typed_name` in strict mode); the sheet given to insight is the result's sheet
without the keys the tools add (`ref`, `change_pts`), so insight's number pools are today's; `Facts.slotted` is set for
each call and the gate gets a fresh state; and every rewrite insight would make to a sentence (a value added to a
one-value change, a base inserted, a clause dropped) is a failure here, never applied: code never puts words into the
model's sentence. The one rewrite let through is the comparison period insight appends to a change ("against the 4
weeks before"): the scope line under every answer states it.
"""
from __future__ import annotations

import copy
import difflib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .. import insight as I

VERIFY_VERSION = "brain_verify_v1"

# ------------------------------------------------------------------ the marker grammar (SPEC 4.2)
PATH = r"(?:r\d+|ctx[12])(?:\.[A-Za-z_]+(?:\[\d+\])?)+"
VALUE = re.compile(r"(?P<said>[^\[\]]{1,40}?)\[(?P<path>" + PATH + r")\]")   # the spec's form (kept for reference)
CALC = re.compile(r"\[=(?P<op>diff|points|ratio|pct_change)\(\s*(?P<a>" + PATH + r")\s*,\s*(?P<b>" + PATH +
                  r")\s*\)\]")
_BRACKET = re.compile(r"\[(?:[^\[\]]|\[[^\[\]]*\])*\]")   # one marker: its index brackets inside it
_PATH_RX = re.compile(PATH)

LEAD_MAX, SENT_MAX, POINTS_MAX, ITEMS_MAX, NOTE_MAX = I.ANSWER_MAX, I.SENT_MAX, 3, 5, 80
OUTSIDE_MAX, OUTSIDE_CHARS, UNDERSTOOD_MAX = 1, 240, 140
MOVE_MIN_POINTS = 3.0   # facts.MOVE_MIN: "up", "rose" of a share need at least 3 points

_MONTHS = I.MONTHS
_MON_RX = r"(?:" + "|".join(sorted(set(_MONTHS) | {m[:3] for m in _MONTHS} | {"sept"}, key=len, reverse=True)) + r")"
_NUM_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
              "eleven": 11, "twelve": 12, "a dozen": 12, "dozen": 12}
_NUM_WORD_RX = r"(?:" + "|".join(sorted(_NUM_WORDS, key=len, reverse=True)) + r")"
_HEDGE_RX = (r"(?:just over|just under|more than|less than|fewer than|close to|about|around|nearly|almost|roughly|"
             r"over|under|some)")
_NUM_RX = r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
# a number typed right before a value or count marker, with its unit
NUM_TAIL = re.compile(r"(?:(?P<hedge>\b" + _HEDGE_RX + r")\s+)?(?P<sign>[+\-−])?(?P<num>" + _NUM_RX + r"|\b" +
                      _NUM_WORD_RX + r")(?P<unit>\s?%|\s?percent|\s?per cent|\s+percentage points?|\s+points?|"
                      r"\s+pts|\s+minutes?|\s+times)?\s*$", re.I)
DATE_TAIL = re.compile(r"(?P<date>\b\d{1,2}(?:st|nd|rd|th)? " + _MON_RX + r"\w*\.?(?:,? \d{4})?|\b" + _MON_RX +
                       r"\w*\.? \d{1,2}(?:st|nd|rd|th)?(?:,? \d{4})?|\b" + _MON_RX + r"\w*\.?(?: \d{4})?|"
                       r"\b(?:19|20)\d\d)\s*$", re.I)
_RATIO_WORDS = (r"(?:(?:nearly|almost|about|roughly|more than|over|just over|just under)\s+)?(?:twice|doubled|double|"
                r"doubling|tripled|triple|thrice|halved|half|a third|a quarter|" + _NUM_RX +
                r"\s+times|(?:two|three|four|five|six|seven|eight|nine|ten) times)")
CALC_TAIL = re.compile(r"(?:(?P<words>\b" + _RATIO_WORDS + r")|(?:(?P<hedge>\b" + _HEDGE_RX + r")\s+)?(?P<num>" +
                       _NUM_RX + r")(?P<unit>\s?%|\s?percent|\s?per cent|\s+percentage points?|\s+points?|\s+pts|"
                       r"\s+more|\s+fewer|\s+times)?)\s*$", re.I)
HOUR_TAIL = re.compile(r"(?P<num>\d{1,2})(?::\d\d)?\s*(?P<ap>am|pm|a\.m\.|p\.m\.)\s*$", re.I)

# words of numbers that need a marker (step 3.3); "one" is left out ("the one you saved")
_NUMBERISH = re.compile(r"\d|%|\b(?:" + _NUM_WORD_RX + r"|half|halves|halved|a third|a quarter|twice|thrice|double|"
                        r"doubled|doubling|tripled|triple|quadrupled|hundreds?|thousands?|dozens?)\b", re.I)
_YEAR = re.compile(r"\b(?:19|20)\d\d\b")
_DATE_IN = re.compile(I._DATE_RX, re.I)
_SPAN_N = re.compile(r"\b(?:the\s+)?(?:last\s+|past\s+)?(\d{1,3})\s+(weeks?|days?|months?|years?)\b", re.I)

# step 3.6: capitalised words that are not names
OPENERS = {"in", "on", "inside", "lately", "right", "your", "you", "since", "over", "next", "then", "most", "both",
           "across", "during", "from", "after", "before", "of", "this", "that", "these", "those", "it", "its", "the",
           "a", "an", "and", "but", "with", "at", "among", "overall", "almost", "nearly", "about", "only", "every",
           "each", "all", "last", "mostly", "here", "there", "compared", "against", "up", "down", "what", "when",
           "where", "which", "while", "by", "for", "so", "also", "together", "behind", "close", "just", "more",
           "fewer", "less", "recently", "these", "now", "around", "between", "through", "until", "to", "outside",
           "apart", "besides", "beyond", "within", "without", "including", "like", "unlike", "as", "if", "no",
           "not", "nothing", "none", "some", "many", "much", "few", "one", "first", "second", "third", "lastly",
           "finally", "meanwhile", "still", "yet", "even", "again", "once", "today", "yesterday", "earlier",
           "later", "back", "ok", "okay", "yes", "sure", "i", "i've", "i'm", "you're", "you've", "we", "they"}
# step 3.7: outside text in a history sentence
WORLD_CLAIMS = re.compile(r"\b(?:most popular|best[- ]known|well[- ]known|famous|renowned|on youtube\b(?! (?:export|"
                          r"videos|history))|in the world|everyone|everybody|subscribers?|views\b|viewers|followers|"
                          r"trending|viral|award[- ]winning|critically)\b", re.I)
_APPOSITIVE = re.compile(r"^\s*,\s*(?:a|an|the|which|who|whose|known for|famous for|run by|made by|hosted by)\b", re.I)
_KNOWN_FOR = re.compile(r"^\s*(?:,\s*)?(?:known for|famous for|run by|hosted by)\b", re.I)
# step 3.9: claims with no marker
_CONSUME = re.compile(r"\byou(?:'ve| have|'d| had)?\s+(?:been\s+)?(?:watch\w*|open\w*|sav\w*|lik\w*|view\w*|"
                      r"into|drop\w*|stopp\w*|start\w*|switch\w*|binge\w*|spent|spend\w*|follow\w*|keep|kept|"
                      r"mostly|mainly|often|usually|always|never|rarely)\b", re.I)
_COMPARATIVE = re.compile(r"\b(?:more|less|fewer)\b|\b\w+er than\b", re.I)
# step 3.10
PSYCH = re.compile(r"\byou(?:'re| are)? (?:really |clearly |truly |must )?(?:love|adore|obsessed|hooked|addicted|"
                   r"passionate|crave|want to learn|want to be|dream|need)\b|\bobsess\w*|\byou are an?\b|\byou're an?\b|"
                   r"\byour (?:passion|personality|identity|true self)\b|\baddict\w*", re.I)
OUTCOME = re.compile(r"\bi(?:'ve| have)? (?:sent|set up|scheduled|saved|created|added|emailed|booked|made|deleted|"
                     r"turned on|turned off)\b|\b(?:done|all set)\b[.!]?$|\bsaved it\b|\bit'?s (?:done|sent|set)\b",
                     re.I)
LIMITS = re.compile(r"\b(?:can'?t|cannot|can not|unable to|don'?t have|do not have|no access|export ends|"
                    r"doesn'?t (?:record|show|include)|not recorded)\b", re.I)
WATCH_TIME = re.compile(r"\bhours?\b(?:'|’)?(?: (?:of|worth|watching|watched|spent|on))?|\bminutes? (?:of|watching|"
                        r"watched|spent)\b|\bwatch(?:ing)? time\b|\btime spent\b|\bscreen time\b|\bbinge[- ]?hours\b",
                        re.I)
_LEAST = re.compile(r"\b(?:least|fewest|barely|lowest|smallest|bottom)\b", re.I)
_RANK = re.compile(r"\b(?:led|leads|leading|leader|top|most|biggest|largest|main|number one|first place|favou?rite|"
                   r"topped|tops|came first|ahead of (?:all|every)|dominat\w*|the most)\b", re.I)
_UPW = re.compile(r"\b(?:up|rose|risen|rise|rising|grew|grown|grow|growing|climb\w*|jump\w*|gain\w*|increas\w*|"
                  r"more than doubled|doubled|tripled|higher|surg\w*)\b", re.I)
_DOWNW = re.compile(r"\b(?:down|fell|fallen|fall|falling|drop\w*|slipp\w*|declin\w*|shr[aiu]nk\w*|fad\w*|"
                    r"decreas\w*|halved|lower|cool\w*)\b", re.I)
_LATELY = re.compile(r"\b(?:lately|right now|recently|these days|nowadays|at the moment|currently)\b", re.I)
_REL_YEAR = re.compile(r"\b(this|last) (year|month|week)\b", re.I)
_SEASON = re.compile(r"\b(spring|summer|autumn|fall|winter)\b", re.I)
_BREAKS = re.compile(r"[,;:()—–]|\b(?:while|whereas|but|and|than|against|compared|versus|vs)\b", re.I)
_OF_BASE = re.compile(r"^\s*(?:of\s+(?:what|everything|all|your|the|those|these|them|it)[^,;.()]{0,60})", re.I)

COUNT_KEYS = set(I.COUNT_KEYS) | {"times_opened", "items_all_time", "rows_total"}
DATE_KEYS = set(I.DATE_KEYS) | {"date", "when", "first", "last", "saved_at", "opened_at"}
OPEN_KEYS = {"times_opened", "events", "opens"}   # counts of openings, never of distinct videos
SHARE_EXTRA = {"faded_from", "faded_to", "grew_from", "grew_to"}
ADDED_KEYS = ("ref", "change_pts", "third_party_text")   # keys results.present() adds; insight never sees them
NON_SHEET_TOOLS = ("find", "search", "learned")
NAME_LISTS_SKIP = {"periods", "busiest_hours", "eras", "items", "examples", "so_what_candidates", "offers", "points",
                   "sources", "options", "matches"}

REASON_TEXT = {
    "bad_ref": "a marker that names no cell of this turn's results",
    "bad_marker": "a marker with no number or name right before it",
    "two_results": "one sentence cites two results; compare two windows through one compare result",
    "uncited_number": "a number with no marker right after it",
    "wrong_value": "the number typed is not the cell's value",
    "wrong_measure": "a percent cited to a count, or a count to a share",
    "wrong_name": "the name before a row marker is not that row's name",
    "calc": "the computed number is not what the two cells give",
    "direction": "the direction word does not fit the cited values",
    "unknown_name": "a name that is not in the results",
    "uncited_name": "a name of the library with no marker in the sentence",
    "outside_in_history": "outside knowledge inside a history sentence (put it in outside)",
    "uncited_claim": "a claim about what they watched with no marker",
    "psych": "a claim about their feelings or who they are",
    "outcome": "a claim that something was done",
    "limits": "talk of limits (code writes those lines)",
    "sensitive": "a sensitive topic",
    "least": "'least' needs the first row of a result ordered by least, over every entity",
    "rank": "a rank word that the cited result does not support",
    "tie": "a rank word on a tie",
    "repeat": "the same cells said again",
    "wrong_window": "the window words are not the cited result's window",
    "window_missing": "the lead does not name its window",
    "too_long": "too long",
    "watch_time": "watch time is never said",
    "filter_dropped": "a count said without the filter it was counted with",
    "one_value": "a change said with one value",
    "base": "the base said is not the result's base",
    "base_missing": "a share said without its base",
    "insight_rewrite": "the sentence would need code's words added to be true",
    "not_item": "an item ref that is not an item row of this turn's results",
    "weak_fit": "a weak match presented as the thing asked for",
    "point_text": "a learned point is only its marker",
}


# ------------------------------------------------------------------ the answer form (SPEC 3.6)
class ItemPick(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref: str
    note: Optional[str] = None


class ChartPick(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    from_: str = Field(alias="from")
    list: Literal["areas", "themes", "channels", "periods"]
    value: Literal["share", "items"]


class OutsideLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    about: str
    text: str
    source: str


class AskBack(BaseModel):
    model_config = ConfigDict(extra="forbid")
    between: list[str]


class OfferPick(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["exclude", "only", "length_long", "length_any", "window", "by_month", "examples"]
    ref: Optional[str] = None
    window_words: Optional[str] = None


class SetupPick(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answers_step: bool
    own_words: Optional[str] = None


class HandBack(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["reminder", "todo", "email_other", "app", "cancel", "library_rule", "setting", "other"]
    words: str


class AnswerForm(BaseModel):
    """The `give_answer` form. Sizes are checked in `check_answer` (a breach fails that field, not the form)."""
    model_config = ConfigDict(extra="forbid")
    understood: str = ""
    lead: str = ""
    points: list[str] = []
    items: list[ItemPick] = []
    chart: Optional[ChartPick] = None
    outside: list[OutsideLine] = []
    ask_back: Optional[AskBack] = None
    offers: list[OfferPick] = []
    setup: Optional[SetupPick] = None
    corrects_previous: bool = False
    hand_back: Optional[HandBack] = None


@dataclass
class Turn:
    """What the verifier knows of the turn besides the results: their message, the topic the turn unlocked, the
    screen, today, and extra names of their library (the person's name index; the results' own names are added)."""
    message: str = ""
    unlock: Optional[str] = None
    screen: str = ""
    today: Optional[date] = None
    names: list[str] = field(default_factory=list)
    sensitive_names: list[str] = field(default_factory=list)

    @classmethod
    def of(cls, tturn):
        """The verifier's turn from the tools' turn (brain/tools.Turn): the same message, screen, today and unlock
        (code's, from their message), and the person's name index from the library the tools read: the areas,
        themes, channels and collections they may see as `names`, the channels hidden as sensitive as
        `sensitive_names` (a hidden channel is never offered; naming it fails step 3.11 unless its topic is the
        turn's unlock). Duck-typed: verify does not import the tools."""
        names, sens = [], []
        lib = getattr(tturn, "lib", None) if getattr(tturn, "bot", None) is not None else None
        if lib is not None:
            from . import names as N
            names += sorted(set(N._area_words(lib).values()))
            names += [nm for _t, nm, _w in N._themes(lib)]
            for nm, hidden in sorted(N._channels(lib).items()):
                (sens if hidden else names).append(nm)
            names += sorted(N._collections(lib).values())
        return cls(message=getattr(tturn, "message", "") or "", unlock=getattr(tturn, "unlock", None),
                   screen=getattr(tturn, "screen", "") or "", today=getattr(tturn, "today", None),
                   names=[n for n in names if isinstance(n, str) and len(n) >= 2],
                   sensitive_names=[n for n in sens if isinstance(n, str) and len(n) >= 2])


@dataclass
class Marker:
    kind: str                 # value | row | calc | count
    start: int                # the said text's start
    end: int                  # the marker's end
    mstart: int               # the bracket's start
    said: str = ""
    path: str = ""            # the full path (r1.channels[0].items)
    rid: str = ""
    rest: str = ""            # the path inside the result (channels[0].items)
    value: Any = None
    key: str = ""
    owner: Optional[str] = None   # the row the cell belongs to (channels[0])
    op: str = ""
    a: str = ""
    b: str = ""
    hedge: str = ""
    num: Optional[float] = None
    unit: str = ""
    sign: str = ""            # a sign typed before the number ("+16 points")


@dataclass
class Outcome:
    where: str                # lead | point | note | outside
    index: int
    text: str                 # as the model wrote it (markers in)
    sent: Optional[str] = None   # as it would go out (markers out); None when dropped
    reasons: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)   # what is true, for the repair text
    cells: dict = field(default_factory=dict)          # cited path -> value
    rid: Optional[str] = None
    hidden_rank: bool = False
    layer: Optional[str] = None   # where it failed: "marker" (verify's own steps) or "insight" (step 3.8)
    insight: Optional[str] = None  # insight's own verdict on the sentence (step 3.8), when it ran
    notes: dict = field(default_factory=dict)   # reason -> its first detail (the repair text's words)

    @property
    def kept(self):
        return not self.reasons


@dataclass
class Verdict:
    outcomes: list[Outcome]
    items: list[dict] = field(default_factory=list)       # {ref, note, kept, reasons}
    outside: list[dict] = field(default_factory=list)     # {about, text, kept, reasons}
    chart: Optional[dict] = None
    form_error: Optional[str] = None
    private_line: bool = False   # SPEC 4.3 step 13: code's scope line adds "Leaving out topics you keep private."
    repair: bool = False
    version: str = VERIFY_VERSION

    @property
    def lead(self):
        return [o for o in self.outcomes if o.where == "lead"]

    @property
    def lead_ok(self):
        return bool(self.lead) and all(o.kept for o in self.lead)

    def kept_text(self, where):
        return [o.sent for o in self.outcomes if o.where == where and o.kept]

    def reason_counts(self):
        out = {}
        for o in self.outcomes:
            for r in o.reasons:
                out[r] = out.get(r, 0) + 1
        return out


# ------------------------------------------------------------------ the ledger
def _strip_added(o):
    if isinstance(o, dict):
        return {k: _strip_added(v) for k, v in o.items() if k not in ADDED_KEYS}
    if isinstance(o, list):
        return [_strip_added(v) for v in o]
    return o


def _segs(rest):
    return I._path_segs(rest)


def _resolve(sheet, rest):
    return I._resolve_raw(sheet, _segs(rest))


class Result:
    def __init__(self, env):
        self.env = env
        self.rid = env.get("rid")
        self.tool = env.get("tool") or ""
        self.meta = env.get("meta") or {}
        self.sheet = env.get("sheet") or {}
        self.is_sheet = self.tool not in NON_SHEET_TOOLS and bool(self.sheet.get("kind"))
        self._k = None
        self._facts = None
        self.names = _names_of(self.sheet)

    @property
    def sheet_k(self):
        """The sheet as insight reads it: without the keys the tools add."""
        if self._k is None:
            self._k = {k: v for k, v in _strip_added(self.sheet).items() if k not in ("hidden", "ranked")}
        return self._k

    @property
    def facts(self):
        if self._facts is None:
            self._facts = I.Facts(self.sheet_k)
        return self._facts

    def window(self):
        w = self.sheet.get("window") or {}
        return _as_d(w.get("start")), _as_d(w.get("end"))

    def prev_window(self):
        p = self.sheet.get("previous") or {}
        a, b = _as_d(p.get("start")), _as_d(p.get("end"))
        if a and b:
            return a, b
        w = str(p.get("words") or "").strip()
        my = re.fullmatch(r"(?:in\s+)?([A-Za-z]+)\s+((?:19|20)\d\d)", w)
        if my and my.group(1).lower() in _MONTHS:   # "September 2026": the whole month
            mi, y = _MONTHS.index(my.group(1).lower()) + 1, int(my.group(2))
            nxt = date(y + (mi == 12), mi % 12 + 1, 1)
            return date(y, mi, 1), date.fromordinal(nxt.toordinal() - 1)
        if re.fullmatch(r"(?:19|20)\d\d", w):
            return date(int(w), 1, 1), date(int(w), 12, 31)
        m = re.search(r"\((\d{1,2}) (\w+)(?: (\d{4}))? to (\d{1,2}) (\w+) (\d{4})\)", str(p.get("words") or ""))
        if m:
            try:
                y2 = int(m.group(6))
                b = date(y2, _MONTHS.index(m.group(5).lower()) + 1, int(m.group(4)))
                y1 = int(m.group(3)) if m.group(3) else y2
                a = date(y1, _MONTHS.index(m.group(2).lower()) + 1, int(m.group(1)))
                return a, b
            except ValueError:
                return None
        return None


def _as_d(v):
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v[:10]).date()
        except ValueError:
            return None
    return None


def _names_of(sheet):
    """[(name, row path)] of every named row of a sheet (areas, themes, channels, fields, topics, nested rows, the
    new and stopped lists), periods, items and examples left out (their labels are times, their titles third-party)."""
    out = []

    def walk(o, path, top):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in NAME_LISTS_SKIP or k in ("window", "filters", "when", "totals", "previous", "question"):
                    continue
                walk(v, (path + "." if path else "") + k, top)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                p = f"{path}[{i}]"
                if isinstance(v, dict):
                    nk = I._record_name_key(v)
                    if nk and nk != "title" and isinstance(v.get(nk), str):
                        out.append((v[nk].strip(), p))
                    walk(v, p, False)
                elif isinstance(v, str) and v.strip():
                    out.append((v.strip(), p))
    walk(sheet, "", True)
    return [(n, p) for n, p in out if len(n) >= 2]


class Ledger:
    """Every result of the turn by rid (a list of envelopes, or a dict rid -> envelope; `ctx1`, `ctx2` count)."""

    def __init__(self, results):
        envs = list(results.values()) if isinstance(results, dict) else list(results or [])
        self.by_rid = {}
        for e in envs:
            if isinstance(e, dict) and e.get("rid"):
                self.by_rid[e["rid"]] = Result(e)

    def get(self, rid):
        return self.by_rid.get(rid)

    def all_names(self):
        out = {}
        for r in self.by_rid.values():
            for n, p in r.names:
                out.setdefault(_low(n), []).append((r.rid, p, n))
        return out


def _low(s):
    return " ".join(str(s or "").lower().split())


# ------------------------------------------------------------------ parse (SPEC 4.2)
def _measure(rest, v):
    key = _segs(rest)[-1][0] if _segs(rest) else ""
    if isinstance(v, bool):
        return key, "bad"
    if key in I.LENGTH_KEYS:
        return key, "watch_time"
    if isinstance(v, str):
        if key in DATE_KEYS or (_as_d(v) and re.match(r"^\d{4}-\d\d-\d\d", v)):
            return key, "date"
        return key, "name"
    if not isinstance(v, (int, float)):
        return key, "bad"
    if key.endswith("share") or key in SHARE_EXTRA:
        return key, "share"
    if key == "change_pts" or key == "change":
        return key, "points"
    if key == "change_vs_previous":
        return key, "points"
    if key in I.HOUR_KEYS:
        return key, "hour"
    if key == "times":
        return key, "times"
    return key, "count"


def _points_of(rest, v):
    """A cell's value in percentage points (area rows carry change_vs_previous as a fraction, SPEC 2.3)."""
    key = _segs(rest)[-1][0]
    if key == "change_vs_previous" and (re.match(r"^(?:areas|top_areas|areas_change)\[", rest) or abs(v) <= 1):
        # areas carry it as a fraction (SPEC 2.3); older sheets carry a theme's as a fraction too (insight's own rule,
        # `_fmt_value`: a value of at most 1 is a fraction; a move under 1 point is never said)
        return float(v) * 100
    return float(v)


def _owner(rest):
    segs = _segs(rest)
    last = max((n for n, (_k, i) in enumerate(segs) if i is not None), default=None)
    return None if last is None else I._path_str(segs[:last + 1])


def _num_of(tok):
    t = tok.strip().lower()
    if t in _NUM_WORDS:
        return float(_NUM_WORDS[t])
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return None


def parse(sentence, ledger):
    """([Marker], [reason]) of one sentence. A bracket that is not a path, a calc of two paths or a count fails
    `bad_ref` (a calc with a literal number inside does not parse); a path that does not resolve in the ledger fails
    `bad_ref`; braces (insight's slots) are not part of this grammar and fail `bad_ref`."""
    out, bad = [], []
    if re.search(r"[{}]", sentence):
        bad.append("bad_ref")
    spans = list(_BRACKET.finditer(sentence))
    rest_txt = _BRACKET.sub(" ", sentence)
    if "[" in rest_txt or "]" in rest_txt:
        bad.append("bad_ref")
    prev_end = 0
    for m in spans:
        body = m.group(0)[1:-1]
        prefix = sentence[prev_end:m.start()]
        cm = CALC.fullmatch(m.group(0))
        if cm:
            mk = Marker("calc", m.start(), m.end(), m.start(), op=cm.group("op"), a=cm.group("a"), b=cm.group("b"))
            ok = True
            for p in (mk.a, mk.b):
                r = ledger.get(p.split(".", 1)[0])
                try:
                    v = _resolve(r.sheet, p.split(".", 1)[1]) if r else None
                except KeyError:
                    v = None
                if not isinstance(v, (int, float)) or isinstance(v, bool):
                    ok = False
            if not ok:
                bad.append("bad_ref")
                prev_end = m.end()
                continue
            mk.rid = mk.a.split(".", 1)[0]
            t = CALC_TAIL.search(prefix)
            if t:
                mk.start = prev_end + t.start()
                mk.said = t.group(0).strip()
                mk.hedge = (t.group("hedge") or "").lower()
                if t.group("num"):
                    mk.num = _num_of(t.group("num"))
                    mk.unit = (t.group("unit") or "").strip().lower()
            out.append(mk)
            prev_end = m.end()
            continue
        if not re.fullmatch(PATH, body):
            bad.append("bad_ref")
            prev_end = m.end()
            continue
        rid, rest = body.split(".", 1)
        r = ledger.get(rid)
        if r is None:
            bad.append("bad_ref")
            prev_end = m.end()
            continue
        if rest.endswith(".count") or rest == "count":
            lp = rest[:-len(".count")] if rest != "count" else ""
            try:
                lst = _resolve(r.sheet, lp) if lp else None
            except KeyError:
                lst = None
            if not isinstance(lst, list):
                bad.append("bad_ref")
                prev_end = m.end()
                continue
            mk = Marker("count", m.start(), m.end(), m.start(), path=body, rid=rid, rest=rest, value=len(lst))
            t = NUM_TAIL.search(prefix)
            if t:
                mk.start, mk.said = prev_end + t.start(), t.group(0).strip()
                mk.num, mk.unit = _num_of(t.group("num")), (t.group("unit") or "").strip().lower()
                mk.hedge = (t.group("hedge") or "").lower()
            out.append(mk)
            prev_end = m.end()
            continue
        try:
            v = _resolve(r.sheet, rest)
        except KeyError:
            bad.append("bad_ref")
            prev_end = m.end()
            continue
        segs = _segs(rest)
        if isinstance(v, dict) and segs and segs[-1][1] is not None:
            mk = Marker("row", m.start(), m.end(), m.start(), path=body, rid=rid, rest=rest, value=v, owner=rest)
            names = _row_names(v, rest)
            low = _low(prefix)
            hit = next((n for n in sorted(names, key=len, reverse=True) if low.endswith(_low(n))), None)
            if hit is not None:
                # the said name's start in the original prefix (case and spacing as typed)
                mt = re.search(r"\s+".join(re.escape(w) for w in hit.split()) + r"\s*$", prefix, re.I)
                if mt:
                    mk.start, mk.said = prev_end + mt.start(), prefix[mt.start():].strip()
            out.append(mk)
            prev_end = m.end()
            continue
        if isinstance(v, (dict, list)) or v is None:
            bad.append("bad_ref")
            prev_end = m.end()
            continue
        key, meas = _measure(rest, v)
        mk = Marker("value", m.start(), m.end(), m.start(), path=body, rid=rid, rest=rest, value=v, key=key,
                    owner=_owner(rest))
        if meas == "name":
            t = re.search(r"\s+".join(re.escape(w) for w in str(v).split()) + r"\s*$", prefix, re.I)
            if t:
                mk.start, mk.said = prev_end + t.start(), t.group(0).strip()
        elif meas == "date":
            t = DATE_TAIL.search(prefix)
            if t:
                mk.start, mk.said = prev_end + t.start(), t.group(0).strip()
        elif meas == "hour":
            t = HOUR_TAIL.search(prefix) or NUM_TAIL.search(prefix)
            if t:
                mk.start, mk.said = prev_end + t.start(), t.group(0).strip()
        else:
            t = NUM_TAIL.search(prefix)
            if t:
                mk.start, mk.said = prev_end + t.start(), t.group(0).strip()
                mk.num, mk.unit = _num_of(t.group("num")), (t.group("unit") or "").strip().lower()
                mk.hedge = (t.group("hedge") or "").lower()
                mk.sign = t.group("sign") or ""
        out.append(mk)
        prev_end = m.end()
    return out, bad


def _bad_detail(sentence, ledger):
    """The repair text for a bracket that is no marker, as exact as code can make it (the live probe's shapes:
    `[r1.sheet.totals.items]`, `[r1.meta.window_said]`, a rid with no result)."""
    if re.search(r"[{}]", sentence):
        return "braces are not markers: type the number, then [r1.path]"
    for m in _BRACKET.finditer(sentence):
        body = m.group(0)[1:-1].strip()
        if body.startswith("="):
            continue
        rid = body.split(".", 1)[0]
        if re.fullmatch(r"r\d+|ctx[12]", rid) and ledger.get(rid) is None:
            return f"{rid} is not a result with numbers in this turn"
        if re.match(r"^(?:r\d+|ctx[12])\.(?:sheet|meta)\.", body):
            fixed = re.sub(r"^((?:r\d+|ctx[12]))\.sheet\.", r"\1.", body)
            if ".meta." in body:
                return f"'{_clip(body, 40)}': meta is not cited; window words need no marker"
            return f"'{_clip(body, 40)}': a path starts after the result id, without 'sheet.' ({_clip(fixed, 40)})"
    return "a bracket that is not a marker of this turn's results"


def _row_names(row, rest):
    names = []
    for k in ("name", "title", "label", "theme", "channel"):
        if isinstance(row.get(k), str) and row[k].strip():
            names.append(row[k].strip())
            break
    if re.match(r"^(?:areas|top_areas)\[", rest) and names:
        names += _area_aliases(names[0])
    return names


def _area_aliases(name):
    """The words an area may be called by beside its own name: a whole word of the name ("cooking" for "food and
    cooking", "art" for "art and design"). themes.CATEGORY_WORDS is wider ("painting", "drawing" for art and design,
    which are themes' names too); the code-owned alias table of SPEC 2.2 (names.py) replaces this when it exists."""
    from .. import themes as T
    own = set(_low(name).split()) - {"and", "the", "of", "&"}
    return [w for w in (T.CATEGORY_WORDS or {}).get(_low(name), ()) if w in own]


def strip_markers(sentence, markers=None):
    """The sentence as it goes out: every marker removed, the words and numbers typed before it kept."""
    s = CALC.sub("", sentence)
    s = _BRACKET.sub("", s)
    s = re.sub(r"\s+([,.;:!?)])", r"\1", s)
    return " ".join(s.split())


# ------------------------------------------------------------------ the value checks (step 3.4, 3.5)
def _hedge_ok(said, cell, hedge, tol_abs):
    """A typed number against a cell with a hedge's direction: "over" / "more than" need the cell above it, "nearly" /
    "almost" / "under" below it."""
    h = (hedge or "").lower()
    if h in ("over", "more than", "just over"):
        return cell >= said - 1e-9 and cell - said <= tol_abs
    if h in ("under", "less than", "fewer than", "nearly", "almost", "just under"):
        return cell <= said + 1e-9 and said - cell <= tol_abs
    return abs(cell - said) <= tol_abs


def check_value(mk):
    """None, or (reason, detail) for one value or count marker."""
    if mk.kind == "count":
        if mk.num is None:
            return "bad_marker", f"{mk.path} = {mk.value}"
        if mk.unit:
            return "wrong_measure", f"{mk.path} is a count ({mk.value})"
        if mk.num != mk.value:
            return "wrong_value", f"'{mk.said}' is {mk.path} = {mk.value}"
        return None
    key, meas = _measure(mk.rest, mk.value)
    v = mk.value
    if meas == "watch_time":
        return "watch_time", f"{mk.path} is a length total, never said"
    if meas == "bad":
        return "bad_ref", f"{mk.path} is not a value"
    if meas == "name":
        if not mk.said or _low(mk.said) != _low(v):
            if _segs(mk.rest)[-1][0] in ("title", "text", "why_matched", "caption"):
                return "wrong_name", f"the words before {mk.path} are not that cell's text"
            return "wrong_name", f"{mk.path} = '{_clip(v)}'"
        return None
    if meas == "date":
        return _date_ok(mk)
    if meas == "hour":
        if not mk.said:
            return "bad_marker", f"{mk.path} = {v}"
        m = HOUR_TAIL.search(mk.said)
        h = int(m.group("num")) % 12 + (12 if m and m.group("ap").lower().startswith("p") else 0) if m else \
            _num_of(mk.said)
        hv = v.get("hour") if isinstance(v, dict) else v
        return None if h is not None and int(h) == int(hv) else ("wrong_value", f"{mk.path} = {hv}")
    if mk.num is None:
        return "bad_marker", f"{mk.path} = {_fmt(mk.rest, v)}"
    hedged = bool(mk.hedge)
    unit = mk.unit
    if meas == "share":
        if not unit or "point" in unit or unit == "pts":
            return "wrong_measure", f"{mk.path} is a share = {v} ({_fmt(mk.rest, v)})"
        if not _hedge_ok(mk.num, float(v) * 100, mk.hedge, 1.5 if hedged else 0.5):
            return "wrong_value", f"'{mk.said}' is {mk.path} = {round(float(v), 4)} ({_fmt(mk.rest, v)})"
        return None
    if meas == "points":
        if unit and ("%" in unit or "percent" in unit or "per cent" in unit):
            return "wrong_measure", f"{mk.path} is in points ({_fmt(mk.rest, v)})"
        pts = abs(_points_of(mk.rest, v))
        if not _hedge_ok(abs(mk.num), pts, mk.hedge, 1.5 if hedged else 0.5):
            return "wrong_value", f"'{mk.said}' is {mk.path} = {round(pts, 1)} points"
        return None
    if meas == "times":
        return None if abs(mk.num - float(v)) <= max(0.1 * float(v), 0.05) else \
            ("wrong_value", f"{mk.path} = {round(float(v), 2)}")
    # counts
    if (unit.startswith("minute") and key == "long_median_min") or (unit == "times" and key in OPEN_KEYS):
        unit = ""
    if unit:
        return "wrong_measure", f"{mk.path} is a count ({_fmt(mk.rest, v)})"
    if not hedged:
        if mk.num != float(v):
            return "wrong_value", f"'{mk.said}' is {mk.path} = {_fmt(mk.rest, v)}"
        return None
    if not (float(v) and _hedge_ok(mk.num, float(v), mk.hedge, 0.1 * float(v))):
        return "wrong_value", f"'{mk.said}' is {mk.path} = {_fmt(mk.rest, v)}"
    return None


def _date_ok(mk):
    d = _as_d(mk.value)
    if not mk.said or d is None:
        return "bad_marker", f"{mk.path} = {mk.value}"
    s = mk.said.lower()
    ys = re.findall(r"\b((?:19|20)\d\d)\b", s)
    mo = re.search(r"\b(" + _MON_RX + r")", s)
    dm = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b(?!\d)", re.sub(r"\b(?:19|20)\d\d\b", " ", s))
    ok = True
    if ys and int(ys[0]) != d.year:
        ok = False
    if mo:
        mi = next(i for i, m in enumerate(_MONTHS) if m.startswith(mo.group(1)[:3]))
        if mi + 1 != d.month:
            ok = False
    if dm and mo and int(dm.group(1)) != d.day:
        ok = False
    return None if ok else ("wrong_value", f"'{mk.said}' is {mk.path} = {d.day} {_MONTHS[d.month - 1].title()} "
                                           f"{d.year}")


def _fmt(rest, v):
    key = _segs(rest)[-1][0] if _segs(rest) else ""
    if key == "change_pts":
        return f"{round(abs(float(v)))} points"
    t = I._fmt_value(key, v)
    return t if t is not None else str(v)


def _clip(s, n=60):
    s = re.sub(r"[\[\]{}<>]", " ", " ".join(str(s or "").split()))
    return s if len(s) <= n else s[:n - 1] + "…"


_RATIO_BANDS = [(re.compile(r"^(?:nearly|almost) (?:twice|doubled|double|doubling)$"), 1.7, 2.0),
                (re.compile(r"^(?:twice|doubled|double|doubling)$"), 1.8, 2.2),
                (re.compile(r"^(?:more than|over|just over) (?:twice|doubled|double|doubling)$"), 2.0, 2.6),
                (re.compile(r"^(?:nearly|almost) (?:tripled|triple|thrice|three times)$"), 2.6, 3.0),
                (re.compile(r"^(?:tripled|triple|thrice|three times)$"), 2.7, 3.3),
                (re.compile(r"^(?:four times)$"), 3.6, 4.4),
                (re.compile(r"^(?:halved|half)$"), 0.45, 0.55),
                (re.compile(r"^(?:nearly|almost) (?:halved|half)$"), 0.5, 0.6),
                (re.compile(r"^a third$"), 0.3, 0.37),
                (re.compile(r"^a quarter$"), 0.22, 0.28)]


def _cell(ledger, p):
    rid, rest = p.split(".", 1)
    return _resolve(ledger.get(rid).sheet, rest), rest


def _family(rest):
    key = _segs(rest)[-1][0]
    if key in OPEN_KEYS:
        return "opens"
    if key.endswith("share") or key in SHARE_EXTRA:
        return "share"
    if key in ("change_pts", "change_vs_previous", "change"):
        return "points"
    if key in I.LENGTH_KEYS:
        return "length"
    return "count"


def _is_before(rest):
    key = _segs(rest)[-1][0]
    return rest.startswith("previous.") or key.startswith("previous_") or key in ("faded_from", "grew_from",
                                                                                   "from_share")


_CLOSE = re.compile(r"\b(?:close behind|right behind|just behind|not far behind|a close second|close second|"
                    r"neck and neck|nearly level|almost level|almost as (?:many|much)|nearly as (?:many|much)|"
                    r"close to|hot on)\b", re.I)
CLOSE_RATIO = 0.8   # "close behind": the second value at least four fifths of the first


def _close_check(low, markers, res):
    """'close behind' and its kin: the two values said (or the row and the row above it) within a fifth."""
    if not _CLOSE.search(low) or res is None:
        return None
    vals = [(mk.owner, mk.key, float(mk.value)) for mk in markers if mk.kind == "value" and mk.owner and
            isinstance(mk.value, (int, float)) and _family(mk.rest) in ("count", "share")]
    pairs = []
    for i, a in enumerate(vals):
        for b in vals[i + 1:]:
            if a[1] == b[1] and a[0] != b[0]:
                pairs.append((a[2], b[2]))
    if not pairs:
        for ow, key, v in vals:
            m = re.match(r"^(.*)\[(\d+)\]$", ow)
            if m and int(m.group(2)) > 0:
                try:
                    above = _resolve(res.sheet, f"{m.group(1)}[{int(m.group(2)) - 1}].{key}")
                except KeyError:
                    continue
                if isinstance(above, (int, float)):
                    pairs.append((float(above), v))
    for a, b in pairs:
        hi, lo = max(a, b), min(a, b)
        if hi and lo / hi < CLOSE_RATIO:
            return "not_close", f"'close' needs the two within a fifth: {round(lo, 4)} against {round(hi, 4)}"
    return None


def check_calc(mk, ledger, clause):
    """None, or (reason, detail): the op computed from the two cells, the typed number or words against it, and the
    direction words of its clause against its sign."""
    (va, ra), (vb, rb) = _cell(ledger, mk.a), _cell(ledger, mk.b)
    fa, fb = _family(ra), _family(rb)
    if "length" in (fa, fb):
        return "watch_time", "a length total is never said"
    va, vb = float(va), float(vb)
    op = mk.op
    det = f"{mk.a} = {round(va, 4)}, {mk.b} = {round(vb, 4)}"
    if op in ("diff", "pct_change") and (fa != "count" or fb != "count"):
        return "wrong_measure", f"{op} needs two counts of videos; {det}"
    if op == "points" and (fa != "share" or fb != "share"):
        return "wrong_measure", f"points needs two shares; {det}"
    if op == "ratio" and (fa != fb or fa not in ("count", "share")):
        return "wrong_measure", f"ratio needs two counts or two shares; {det}"
    if _is_before(ra) and not _is_before(rb):
        # the value of the period before goes second: "up" is now against before, never the other way round
        return "calc", f"{op}(now, before): {mk.b} is now, {mk.a} is the period before; {det}"
    if op == "diff":
        val = va - vb
    elif op == "points":
        val = (va - vb) * 100
    elif op == "pct_change":
        if vb == 0:
            return "calc", f"pct_change from 0; {det}"
        val = (va - vb) / vb * 100
    else:
        if vb == 0:
            return "calc", f"ratio over 0; {det}"
        val = va / vb
    said = (mk.said or "").lower()
    up, down = bool(_UPW.search(clause)), bool(_DOWNW.search(clause))
    if op == "ratio":
        words = " ".join(said.split())
        if mk.num is not None and (mk.unit or "").strip() == "times":
            if abs(mk.num - val) > 0.1 * val:
                return "calc", f"{mk.a} / {mk.b} = {round(val, 2)}"
        elif mk.num is not None:
            return "calc", f"a ratio is said in words or 'N times'; {mk.a} / {mk.b} = {round(val, 2)}"
        else:
            nt = re.match(r"^(?:(nearly|almost|about|roughly) )?(\S+) times$", words)
            if nt:
                n = _num_of(nt.group(2))
                if n is None or abs(n - val) > 0.1 * n:
                    return "calc", f"{mk.a} / {mk.b} = {round(val, 2)}"
            else:
                band = next(((lo, hi) for rx, lo, hi in _RATIO_BANDS if rx.match(words)), None)
                if band is None:
                    return "calc", f"{mk.a} / {mk.b} = {round(val, 2)}"
                if not (band[0] <= val <= band[1]):
                    return "calc", f"'{words}' needs {band[0]} to {band[1]}; {mk.a} / {mk.b} = {round(val, 2)}"
        if (up and val <= 1) or (down and val >= 1) or (re.search(r"doubl|tripl|twice|times", words) and val < 1) or \
                (re.search(r"halv|half|third|quarter", words) and val > 1):
            return "direction", f"{mk.a} / {mk.b} = {round(val, 2)}"
        return None
    if mk.num is None:
        return "bad_marker", f"{op}({mk.a}, {mk.b}) = {round(val, 1)}"
    tol = 0.0 if op == "diff" else (0.5 if op == "points" else 1.0)
    if mk.hedge:
        tol = max(tol, 1.5 if op == "points" else abs(val) * 0.1)
    if abs(abs(mk.num) - abs(val)) > tol + 1e-9:
        return "calc", f"{op}({mk.a}, {mk.b}) = {round(val, 1)}"
    if op == "points" and (mk.unit or "") and ("%" in mk.unit or "percent" in mk.unit):
        return "wrong_measure", f"a change of two shares is in points: {round(val, 1)} points"
    if op == "pct_change" and not (mk.unit and ("%" in mk.unit or "percent" in mk.unit)):
        return "wrong_measure", f"a percent change is said with %: {round(val)}%"
    if up and down:
        return None
    if up and (val <= 0 or (op == "points" and val < MOVE_MIN_POINTS)):
        return "direction", f"{op}({mk.a}, {mk.b}) = {round(val, 1)}"
    if down and (val >= 0 or (op == "points" and -val < MOVE_MIN_POINTS)):
        return "direction", f"{op}({mk.a}, {mk.b}) = {round(val, 1)}"
    if re.search(r"\bmore\b", said + " " + clause) and val < 0 and op == "diff":
        return "direction", f"diff = {round(val)}"
    if re.search(r"\b(?:fewer|less)\b", said + " " + clause) and val > 0 and op == "diff":
        return "direction", f"diff = {round(val)}"
    return None


# ------------------------------------------------------------------ one sentence (step 3)
def _clause_around(s, a, b):
    """The clause of s that holds [a, b): from the last break before a to the next break after b."""
    pre = [m.end() for m in _BREAKS.finditer(s[:a])]
    post = _BREAKS.search(s, b)
    return s[(pre[-1] if pre else 0):(post.start() if post else len(s))]


def _name_spans(text, names_idx, extra=()):
    """[(start, end, low name)] of library names in text, longest first, no overlaps."""
    found, taken = [], []
    cands = sorted(set(list(names_idx.keys()) + [_low(x) for x in extra if x]), key=len, reverse=True)
    low = text.lower()
    for n in cands:
        if len(n) < 2:
            continue
        for m in re.finditer(r"(?<![\w@])" + re.escape(n) + r"(?:s|es)?(?![\w])", low):
            if any(a < m.end() and m.start() < b for a, b in taken):
                continue
            found.append((m.start(), m.end(), n))
            taken.append((m.start(), m.end()))
    return sorted(found)


def _window_phrases(res):
    out = []
    for x in ((res.meta or {}).get("window_said"), (res.sheet.get("window") or {}).get("words"),
              (res.sheet.get("previous") or {}).get("words")):
        if isinstance(x, str) and x.strip():
            out.append(x.strip())
            out.append(re.split(r"[(,]", x)[0].strip())
    return sorted({x for x in out if len(x) >= 4}, key=len, reverse=True)


def _remove_phrases(text, phrases):
    for ph in phrases:
        text = re.sub(re.escape(ph), lambda m: " " * len(m.group(0)), text, flags=re.I)
    return text


def _allowed_numbers_out(text, res):
    """text with what may stand with no marker blanked: years, day-month dates, "the 4 weeks" of the window's own
    words, hours said inside window words."""
    t = _remove_phrases(text, _window_phrases(res) if res else [])
    t = _DATE_IN.sub(lambda m: " " * len(m.group(0)), t)
    t = re.sub(r"\b" + _MON_RX + r"\w*\.?\s+(?:19|20)\d\d\b", lambda m: " " * len(m.group(0)), t, flags=re.I)
    t = _YEAR.sub("    ", t)
    words = " ".join(_window_phrases(res)).lower() if res else ""
    for m in list(_SPAN_N.finditer(t)):
        unit = m.group(2).lower().rstrip("s")
        if re.search(r"\b" + m.group(1) + r"\s+" + unit, words):
            t = t[:m.start()] + " " * (m.end() - m.start()) + t[m.end():]
    return t


def _months_in(a, b):
    out, y, m = set(), a.year, a.month
    while (y, m) <= (b.year, b.month):
        out.add((y, m))
        y, m = (y + (m == 12), m % 12 + 1)
    return out


_PHRASE = re.compile(
    r"\b(?P<since>since\s+|after\s+)?(?:"
    r"(?:the\s+)?(?P<season>spring|summer|autumn|winter)(?:\s+of)?(?:\s+(?P<sy>(?:19|20)\d\d))?"
    r"|(?P<mon>january|february|march|april|may|june|july|august|september|october|november|december|"
    r"jan|feb|mar|apr|jun|jul|aug|sept|sep|oct|nov|dec)\.?(?:\s+(?P<my>(?:19|20)\d\d))?"
    r"|(?P<year>(?:19|20)\d\d)"
    r"|(?P<rel>today|yesterday|(?:this|last|past) (?:week|month|year))"
    r")\b", re.I)
_SEASON_M = {"spring": (3, 5), "summer": (6, 8), "autumn": (9, 11), "winter": (12, 2)}
FAR = date(2999, 12, 31)
WINDOW_MATCH = 0.85   # a time said of a count covers its window, and the window covers it, to this share of days


def _month_range(y, m):
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return date(y, m, 1), date.fromordinal(nxt.toordinal() - 1)


def _season(y, s0, s1):
    if s0 > s1:   # winter: December to February
        return date(y, 12, 1), _month_range(y + 1, 2)[1]
    return date(y, s0, 1), _month_range(y, s1)[1]


def _overlap(p, w):
    a, b = max(p[0], w[0]), min(p[1], w[1])
    return max(0, b.toordinal() - a.toordinal() + 1)


def _phrase_range(m, wins, turn):
    """(start, end) of a time phrase, or None when it cannot be placed (a relative word with no today)."""
    g = m.groupdict()
    end_year = max((b.year for _a, b in wins), default=None)
    if g.get("rel"):
        today = turn.today if turn and turn.today else None
        if today is None:
            return None
        r = g["rel"].lower()
        if r == "today":
            a = b = today
        elif r == "yesterday":
            a = b = date.fromordinal(today.toordinal() - 1)
        elif r.endswith("week"):
            mon = date.fromordinal(today.toordinal() - today.weekday())
            if r.startswith("last"):
                mon = date.fromordinal(mon.toordinal() - 7)
            a, b = (date.fromordinal(today.toordinal() - 7), today) if r.startswith("past") else \
                (mon, date.fromordinal(mon.toordinal() + 6))
        elif r.endswith("month"):
            y, mo = today.year, today.month
            if r.startswith("last"):
                y, mo = (y - (mo == 1), 12 if mo == 1 else mo - 1)
            a, b = _month_range(y, mo)
        else:
            y = today.year - r.startswith("last")
            a, b = date(y, 1, 1), date(y, 12, 31)
    elif g.get("season"):
        s0, s1 = _SEASON_M[g["season"].lower()]
        if g.get("sy"):
            y = int(g["sy"])
        else:   # the instance that overlaps the windows most
            cands = sorted({a.year for a, _b in wins} | {b.year for _a, b in wins} | {(end_year or 2000) - 1})
            y = max(cands, key=lambda yy: (sum(_overlap(_season(yy, s0, s1), w) for w in wins), yy))
        a, b = _season(y, s0, s1)
    elif g.get("mon"):
        mi = next(i for i, x in enumerate(_MONTHS) if x.startswith(g["mon"].lower()[:3])) + 1
        if g.get("my"):
            a, b = _month_range(int(g["my"]), mi)
        else:
            cands = sorted({y for w in wins for y in range(w[0].year, w[1].year + 1)} or {end_year or 2000})
            y = max(cands, key=lambda yy: (sum(_overlap(_month_range(yy, mi), w) for w in wins), yy))
            a, b = _month_range(y, mi)
    else:
        y = int(g["year"])
        a, b = date(y, 1, 1), date(y, 12, 31)
    if g.get("since"):
        b = FAR
    return a, b


def _matches(p, w, clipped):
    """The phrase's range and the window are the same stretch of time (each covers the other to WINDOW_MATCH); a
    window cut at the export's end, or an open "since", is read up to the window's end."""
    a, b = p
    if b == FAR or (clipped and b > w[1]):
        b = w[1]
    if b < a:
        return False
    ov = _overlap((a, b), w)
    lw = w[1].toordinal() - w[0].toordinal() + 1
    lp = b.toordinal() - a.toordinal() + 1
    return ov >= WINDOW_MATCH * lw and ov >= WINDOW_MATCH * lp


def _labels(sheet):
    """The periods a sheet names itself ("2021", "Oct 2026": periods, eras, the change's ends)."""
    out = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("label", "from", "to", "peak_period", "peak_label", "last_label") and isinstance(v, str):
                    out.add(_low(v))
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk({k: v for k, v in sheet.items() if k in ("periods", "eras", "change", "areas_change", "seasonal")})
    return out


def _label_range(label):
    m = _PHRASE.fullmatch(label.strip())
    if not m or m.group("rel") or m.group("since") or not (m.group("year") or m.group("my") or m.group("sy")):
        return None
    return _phrase_range(m, [], None)


def _phrase_ok(m, rng, res, wins, period_cells=False):
    """The phrase is the window (or the compare window); or, when the sentence cites a period's own cells (periods,
    eras, a change's two ends), one of the periods the sheet names."""
    if rng is None:
        return False
    clipped = bool((res.sheet.get("window") or {}).get("clipped"))
    if any(_matches(rng, w, clipped) for w in wins):
        return True
    if not period_cells:
        return False
    lab = _labels(res.sheet)
    return _low(m.group(0)) in lab or any(rng == _label_range(x) for x in lab)


def _windows_of(res, cites_prev):
    out = []
    w = res.window()
    if w[0] and w[1]:
        out.append(w)
    if cites_prev or res.tool == "compare" or res.sheet.get("kind") in ("compare", "compare_windows"):
        pw = res.prev_window()
        if pw:
            out.append(pw)
    return out


def _window_check(text, res, cites_prev, turn, period_cells=False):
    """None or (reason, detail): every time said in the sentence against the cited result's window (and its compare
    window when a previous or change cell is cited, or the result is a compare). A day must lie inside one; a month,
    a year, a season or a relative word ("this year", "last week") must be that window, not a stretch around or
    inside it (a count of 4 weeks said "in 2026" is the right number with a wrong window), unless the sheet names
    that period itself (its periods, eras, a change's ends)."""
    if res is None:
        return None
    wins = _windows_of(res, cites_prev)
    if not wins:
        return None
    said = (res.meta or {}).get("window_said") or (res.sheet.get("window") or {}).get("words") or ""
    det = f"{res.rid}'s window is '{_clip(said, 90)}'"
    t = _remove_phrases(text, _window_phrases(res))
    for m in _DATE_IN.finditer(t):
        g = m.groups()
        d_, mon, y = (g[0], g[1], g[2]) if g[0] else (g[4], g[3], g[5])
        mi = next((i for i, x in enumerate(_MONTHS) if x.startswith(mon.lower()[:3])), None)
        if mi is None:
            continue
        ok = False
        for a, b in wins:
            for yy in ([int(y)] if y else range(a.year, b.year + 1)):
                try:
                    dd = date(yy, mi + 1, int(d_))
                except ValueError:
                    continue
                ok = ok or a <= dd <= b
        if not ok:
            return "wrong_window", det
    t2 = _DATE_IN.sub(lambda m: " " * len(m.group(0)), t)
    for m in _PHRASE.finditer(t2):
        if m.group("mon") and m.group("mon").lower() in ("may", "mar") and not m.group("my"):
            continue   # "may" and "mar" are words as often as months
        if not _phrase_ok(m, _phrase_range(m, wins, turn), res, wins, period_cells):
            return "wrong_window", det
    if _LATELY.search(t2):
        lately = re.search(r"\b(?:4|four) weeks\b", said, re.I) or _LATELY.search(said)
        if not lately:
            return "wrong_window", det
    return None


def _end_in_base(sentence, markers, res, turn=None):
    """A value said with the other period's words: the end value of a change inside the base period ("from 12% to
    9% in the 4 weeks before"), or a value of the period before inside the window's words or dates."""
    if res is None:
        return None
    prevw = (res.sheet.get("previous") or {}).get("words")
    w, pw = res.window(), res.prev_window()
    clipped = bool((res.sheet.get("window") or {}).get("clipped"))
    for mk in markers:
        if mk.kind != "value" or not isinstance(mk.value, (int, float)):
            continue
        after = sentence[mk.end:mk.end + 120]
        stop = re.search(r"[;]|,\s*(?:while|and|but)\b|\b(?:while|whereas|but)\b|"
                         r"\b(?:to|from)\s+[+\-−]?\d[\d.,]*\s*(?:%|\[|points?\b)", after)
        after = after[:stop.start()] if stop else after
        if (mk.key or "") in ("change_vs_previous", "change_pts", "change"):
            continue   # a change is of both periods
        prev_cell = _is_before(mk.rest)
        m = re.match(r"^\s*(?:,\s*)?(?:[a-z]+\s+){0,2}?(?:in|during|over|across)\s+(.{3,80})", after, re.I)
        if not m:
            continue
        ph = m.group(1).lower()
        says_prev = bool(re.search(r"\bbefore\b|\bprevious\b|\bearlier\b|\bprior\b", ph)) or \
            bool(prevw and _low(prevw)[:20] in _low(ph))
        nw = [x for x in ((res.meta or {}).get("window_said"), (res.sheet.get("window") or {}).get("words")) if x]
        says_now = not says_prev and any(_low(re.split(r"[(,]", x)[0])[:24] in _low(ph) for x in nw)
        if not (says_prev or says_now):
            pm = _PHRASE.match(m.group(1))
            wins = [x for x in (w, pw) if x and x[0]]
            rng = _phrase_range(pm, wins, turn) if pm else None
            if rng and w[0]:
                in_now = _matches(rng, w, clipped)
                in_prev = bool(pw) and _matches(rng, pw, False)
                says_prev, says_now = in_prev and not in_now, in_now and not in_prev
        if says_prev and not prev_cell:
            return "wrong_window", f"{mk.path} is of {res.rid}'s window, not the period before"
        if says_now and prev_cell:
            return "wrong_window", f"{mk.path} is of the period before, not {res.rid}'s window"
    return None


def check_sentence(sentence, ledger, turn=None, where="point", index=0, state=None, probe=False):
    """One sentence -> Outcome (kept, or dropped with reason codes and the true values of its cells). `probe` (the
    proof and the tests only): insight's step runs even when an earlier step failed, its verdict in `insight`."""
    turn = turn or Turn()
    state = state if state is not None else {}
    out = Outcome(where, index, sentence)
    raw = " ".join(str(sentence or "").split())
    if not raw:
        out.reasons.append("too_long" if sentence else "bad_marker")
        return out
    if len(strip_markers(raw)) > SENT_MAX:
        out.reasons.append("too_long")
        return out
    markers, bad = parse(raw, ledger)
    fail = out.reasons

    def add(r, d=None):
        if r not in fail:
            fail.append(r)
        if d:
            out.details.append(d)
            out.notes.setdefault(r, d)
    for b in bad:
        add(b, _bad_detail(raw, ledger))
    for mk in markers:
        if mk.kind == "calc":
            for p in (mk.a, mk.b):
                try:
                    out.cells[p] = _cell(ledger, p)[0]
                except (KeyError, AttributeError):
                    pass
        elif mk.kind in ("value", "count"):
            out.cells[mk.path] = mk.value
    # 3.2 one sentence, one result
    rids = {mk.rid for mk in markers if mk.rid} | {p.split(".", 1)[0] for mk in markers if mk.kind == "calc"
                                                     for p in (mk.a, mk.b)}
    if len(rids) > 1:
        add("two_results", "markers of " + ", ".join(sorted(rids)))
    rid = sorted(rids)[0] if rids else None
    res = ledger.get(rid) if rid else None
    # a sentence with no marker says the turn's window in words: it is read against the turn's first result
    wres = res or next(iter(ledger.by_rid.values()), None)
    out.rid = rid
    plain = strip_markers(raw)
    low = plain.lower()
    # the text with every marked span blanked (what is left must cite nothing)
    blank = list(raw)
    for mk in markers:
        for i in range(mk.start, mk.end):
            blank[i] = " "
    blank = "".join(blank)
    # 3.3 every number cited
    left = _allowed_numbers_out(blank, wres)
    names_idx = ledger.all_names()
    for a, b, _n in _name_spans(left, names_idx):
        left = left[:a] + " " * (b - a) + left[b:]
    if _NUMBERISH.search(left):
        add("uncited_number", "every number needs its marker right after it")
    # 3.4 value, 3.5 calc
    for mk in markers:
        if mk.kind in ("value", "count"):
            if mk.kind == "value" and not mk.said and _measure(mk.rest, mk.value)[1] not in ("name",):
                add("bad_marker", f"{mk.path} = {_fmt(mk.rest, mk.value) if not isinstance(mk.value, str) else mk.value}")
                continue
            r = check_value(mk)
            if r:
                add(*r)
            elif mk.kind == "value" and _measure(mk.rest, mk.value)[1] == "points":
                # a move in points: its typed sign and the direction words of its clause against the cell's sign
                pts = _points_of(mk.rest, mk.value)
                clause = _clause_around(raw, mk.start, mk.mstart).lower()
                up, down = bool(_UPW.search(clause)), bool(_DOWNW.search(clause))
                if (mk.sign == "+" and pts < 0) or (mk.sign in ("-", "−") and pts > 0) or \
                        (up and not down and pts < 0) or (down and not up and pts > 0):
                    add("direction", f"{mk.path} = {round(pts, 1)} points")
        elif mk.kind == "row":
            if not mk.said:
                nm = _row_names(mk.value, mk.rest)
                if isinstance(mk.value, dict) and mk.value.get("title"):
                    # an item's title is third-party text: never put back into a message to the model
                    add("wrong_name", f"the words before {mk.path} are not that item's title")
                else:
                    add("wrong_name", f"{mk.path} is '{_clip(nm[0]) if nm else '?'}'")
        elif mk.kind == "calc":
            if len({mk.a.split('.', 1)[0], mk.b.split('.', 1)[0]}) > 1:
                add("two_results", f"{mk.a} and {mk.b}")
                continue
            if not mk.said:
                add("bad_marker", f"{mk.op}({mk.a}, {mk.b})")
                continue
            r = check_calc(mk, ledger, _clause_around(raw, mk.start, mk.mstart).lower())
            if r:
                add(*r)
    # value markers of a count of opens said as "videos" (re-opens are not videos)
    for mk in markers:
        if mk.kind == "value" and mk.key in OPEN_KEYS and re.match(r"^\s*(?:\w+\s+){0,2}videos?\b", raw[mk.end:]):
            add("wrong_measure", f"{mk.path} counts openings, not videos")
        if mk.kind == "calc" and any(_family(p.split(".", 1)[1]) == "opens" for p in (mk.a, mk.b)) and \
                re.search(r"\bvideos?\b", raw[mk.end:mk.end + 30]):
            add("wrong_measure", "a count of openings is not a count of videos")
    # 3.6 rows and names
    cited_rows = {}   # row rest -> rid
    for mk in markers:
        if mk.kind == "row" and mk.said:
            cited_rows[mk.rest] = mk.rid
        if mk.kind == "value" and mk.owner:
            cited_rows.setdefault(mk.owner, mk.rid)
        if mk.kind == "calc":
            for p in (mk.a, mk.b):
                ow = _owner(p.split(".", 1)[1])
                if ow:
                    cited_rows.setdefault(ow, p.split(".", 1)[0])
    allowed_scope = set()
    if res is not None:
        f = res.sheet.get("filters") or {}
        for v in (f.get("topic"), f.get("channel")):
            if isinstance(v, str) and v.strip():
                allowed_scope.add(_low(v))
        for k, v in ((res.meta or {}).get("resolved") or {}).items():
            allowed_scope.add(_low(k))
        for p in scope_parts(res):   # the labels of the tools' scope ("only gaming (area)": "gaming")
            if p.get("label"):
                allowed_scope.add(_low(p["label"]))
    cited_names = {}
    for rest_, rid_ in cited_rows.items():
        r_ = ledger.get(rid_)
        try:
            row = _resolve(r_.sheet, rest_)
        except (KeyError, AttributeError):
            continue
        if isinstance(row, dict):
            for n in _row_names(row, rest_):
                cited_names.setdefault(_low(n), rest_)
        elif isinstance(row, str):
            cited_names.setdefault(_low(row), rest_)
    blank2 = list(raw)
    for mk in markers:
        if mk.kind in ("row",) or (mk.kind == "value" and isinstance(mk.value, str)):
            for i in range(mk.start, mk.end):
                blank2[i] = " "
        else:
            for i in range(mk.mstart, mk.end):
                blank2[i] = " "
    blank2 = _remove_phrases("".join(blank2), _window_phrases(wres) if wres else [])
    plain_names = []
    for a, b, n in _name_spans(blank2, names_idx, turn.names):
        base_n = n
        if base_n in cited_names or base_n in allowed_scope:
            plain_names.append((a, b, base_n))
            continue
        add("uncited_name", f"'{_clip(blank2[a:b])}' is named with no marker")
    # capitalised words that are no name (the first word too)
    caps_text = blank2
    for a, b, _n in _name_spans(caps_text, names_idx, list(turn.names) + list(allowed_scope)):
        caps_text = caps_text[:a] + " " * (b - a) + caps_text[b:]
    titles = []
    for mk in markers:
        if mk.kind == "row" and isinstance(mk.value, dict) and isinstance(mk.value.get("title"), str):
            titles.append(mk.value["title"])
            if isinstance(mk.value.get("channel"), str):
                titles.append(mk.value["channel"])   # a cited item's own channel may be named (step 4)
    caps_text = _remove_phrases(caps_text, titles)
    caps_text = re.sub(r"\"[^\"]{1,90}\"|“[^”]{1,90}”", lambda m: " " * len(m.group(0)), caps_text) if titles else \
        caps_text
    for m in re.finditer(r"(?<![\w'’-])([A-Z][\w'’&-]*)", caps_text):
        w = m.group(1).lower().strip("'’")
        w0 = re.split(r"['’]", w)[0]
        if w in OPENERS or w0 in OPENERS or w in I.ALLOWED_CAPS or w0 in I.ALLOWED_CAPS or \
                any(x.startswith(w0[:3]) for x in _MONTHS if len(w0) >= 3 and w0[:3] == x[:3]) or \
                w0 in I.WEEKDAYS or w0.rstrip("s") in I.WEEKDAYS or w0 in ("shorts", "reels", "reel", "youtube's"):
            continue
        if re.fullmatch(r"[a-z]{3,}ly", w0) and not m.start():
            continue   # an adverb opening the sentence ("Mostly", "Overwhelmingly"): a word, not a name
        if not caps_text[:m.start()].strip() and w0 in ("is", "was", "were", "are", "had", "has", "did"):
            continue
        add("unknown_name", f"'{_clip(m.group(1), 30)}' is not a name of the results")
    # 3.7 outside text in a history sentence
    for mk in markers:
        if mk.kind == "row" and (_APPOSITIVE.match(raw[mk.end:]) or _KNOWN_FOR.match(raw[mk.end:])):
            add("outside_in_history")
    for a, b, _n in plain_names:
        if _APPOSITIVE.match(blank2[b:]) and re.match(r"^\s*,\s*(?:a|an|the)\s+\w+\s+(?:channel|creator|show|"
                                                      r"series|youtuber|artist|brand|studio)\b", blank2[b:], re.I):
            add("outside_in_history")
    if WORLD_CLAIMS.search(_remove_phrases(low, [p.lower() for p in _window_phrases(wres)] if wres else [])):
        add("outside_in_history", "claims about the world go in outside")
    # 3.9 claims with no marker
    if not markers and (_CONSUME.search(low) or _COMPARATIVE.search(low) or _RANK.search(low)):
        add("uncited_claim", "a claim about their history needs its marker")
    # 3.10 psych, outcome, limits; watch time
    if PSYCH.search(low):
        add("psych")
    if OUTCOME.search(low):
        add("outcome")
    no_win = re.sub(r"where your (?:youtube |instagram )?export ends", " ",
                    _remove_phrases(low, [p.lower() for p in _window_phrases(wres)] if wres else []))
    if LIMITS.search(no_win):
        add("limits")
    if WATCH_TIME.search(low):
        add("watch_time")
    # 3.11 sensitive
    if _sensitive(plain, turn):
        add("sensitive")
    # 3.12 least; rank words on a least result; ties
    if res is not None:
        order = (res.meta or {}).get("order") or "most"
        rows0 = [mk for mk in markers if mk.kind in ("row", "value") and mk.owner and re.search(r"\[0\]$", mk.owner)]
        if _LEAST.search(low):
            if not (order == "least" and (res.meta or {}).get("complete") is True and rows0):
                add("least", f"{res.rid} is ordered by {order}" + ("" if (res.meta or {}).get("complete") else
                                                                    ", not over every entity"))
            elif not any(_smallest(res, mk.owner) for mk in rows0):
                # the result is ordered by least, but the list cited is not the one it ranked (a sheet's other lists
                # keep their "most" order): its first row must be the smallest of its list, by code's own reading
                add("least", f"{res.rid}'s list cited is not ranked from the least")
        if order == "least" and _RANK.search(re.sub(r"\bthe least\b|\bleast\b", " ", low)):
            add("rank", f"{res.rid} is ordered by least: its first row is the smallest")
        r_ = _close_check(low, markers, res)
        if r_:
            add(*r_)
        if (_RANK.search(low) or _LEAST.search(low)) and rows0:
            for mk in rows0:
                tie = _tie(res, mk.owner)
                if tie:
                    add("tie", tie)
                    break
        # 3.13 rank with hidden rows (the founder's answer 4: code's scope line says it)
        hid = (res.meta or {}).get("hidden") or {}
        if hid.get("rank_hidden_above") and _RANK.search(low):
            out.hidden_rank = True
    # 3.15 window words; the end value of a change inside the base period's words
    cites_prev = any((mk.rest.startswith("previous.") or (mk.key or "").startswith("previous_") or
                      mk.key in ("change_vs_previous", "change_pts", "change")) for mk in markers
                     if mk.kind == "value") or any(
        ".previous" in p or p.split(".", 1)[1].startswith("previous.") for mk in markers if mk.kind == "calc"
        for p in (mk.a, mk.b))
    period_cells = any(re.match(r"^(?:periods|eras|change|areas_change|seasonal)\b", p.split(".", 1)[1])
                       for mk in markers for p in ([mk.path] if mk.kind != "calc" else [mk.a, mk.b]) if "." in p)
    # (a date said by a date marker is checked against its own cell: its words are left out here)
    wtext = list(raw)
    for mk in markers:
        dated = mk.kind == "value" and isinstance(mk.value, str) and _measure(mk.rest, mk.value)[1] == "date"
        for i in range(mk.start if dated else mk.mstart, mk.end):
            wtext[i] = " "
    r = _window_check("".join(wtext), wres, cites_prev, turn, period_cells)
    if r:
        add(*r)
    r = _end_in_base(raw, markers, res, turn)
    if r:
        add(*r)
    # a count of a result filtered to long (or short) videos said without that word
    if res is not None:
        r = _filter_dropped(raw, markers, res)
        if r:
            add(*r)
        # a number, a date or a rank of a result the tools scoped by a name, a weekday or a platform, said without
        # the scope's words (merge seam: the scope lives in meta.filters_said, not in the sheet's filters)
        r = _scope_dropped(raw, markers, res, low)
        if r:
            add(*r)
        r = _verb_dropped(raw, markers, res, low)
        if r:
            add(*r)
    # 3.8 insight's checks, one sentence (sheets only), or the rules of a result that is not a sheet (step 4)
    # (a sentence with no marker is read by insight against the turn's first result: insight's strict render drops a
    # direction or a number with no path, "the mix narrowed")
    ires = res if res is not None else (wres if not markers else None)
    # insight also runs after a failed value or name check, so the repair names every fault at once (its slots hold
    # the cells' true values); not after a marker that does not parse or resolve
    structural = {"bad_ref", "bad_marker", "two_results", "wrong_name", "too_long"}
    if ires is not None and ires.is_sheet and (not fail or probe or not (set(fail) & structural)):
        try:
            why = insight_check(raw, markers, plain_names, cited_names, ires, where, turn.unlock)
        except Exception as e:   # noqa: BLE001  (a sentence insight cannot read is dropped, never sent)
            why = ("insight_error", type(e).__name__)
        out.insight = why[0] if why else None
        if why and (not fail or not (set(fail) & structural)):
            if not fail:
                out.layer = "insight"
            add(*why)
    elif not fail and res is not None and not res.is_sheet:
        why = _non_sheet(raw, markers, res, low)
        if why:
            add(*why)
    # (a sentence with no marker holds plain words only: no number, name or claim passed the steps above)
    if not fail:
        out.sent = plain
    elif out.layer is None:
        out.layer = "marker"
    return out


def _tie(res, owner):
    """A rank word on the first row of a list whose second row has the same value."""
    try:
        lp = re.sub(r"\[0\]$", "", owner)
        lst = _resolve(res.sheet, lp)
    except KeyError:
        return None
    if not isinstance(lst, list) or len(lst) < 2 or not all(isinstance(x, dict) for x in lst[:2]):
        return None
    for k in ("items", "share", "n"):
        a, b = lst[0].get(k), lst[1].get(k)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            if a == b:
                return f"{res.rid}.{lp}[0] and [1] are tied at {a}"
            return None
    return None


def _smallest(res, owner):
    """The first row of its list holds the smallest value of the list (items, else share); a tie counts as not."""
    try:
        lst = _resolve(res.sheet, re.sub(r"\[0\]$", "", owner))
    except KeyError:
        return False
    if not isinstance(lst, list) or not lst or not all(isinstance(x, dict) for x in lst):
        return False
    for k in ("items", "share", "n"):
        vals = [x.get(k) for x in lst]
        if all(isinstance(v, (int, float)) for v in vals):
            return all(vals[0] < v for v in vals[1:])
    return False


def _filter_dropped(raw, markers, res):
    f = res.sheet.get("filters") or {}
    said = " ".join(str(x) for x in ((res.meta or {}).get("filters_said"), (res.meta or {}).get("base")) if x).lower()
    length = f.get("length") or ("long" if f.get("without_shorts") or re.search(r"\blong\b|without shorts", said)
                                 else ("short" if re.search(r"\bonly shorts\b|\bshorts only\b", said) else None))
    if not length:
        return None
    word = "long" if length == "long" else r"(?:short|shorts|reels?)"
    for mk in markers:
        if mk.kind != "value" or _family(mk.rest) != "count":
            continue
        if not re.match(r"^(?:totals|previous)\.", mk.rest):
            continue
        tail = raw[mk.end:mk.end + 40]
        m = re.match(r"^\s*((?:[\w&'-]+\s+){0,3}?)(?:videos?|items?|posts?|clips?)\b", tail, re.I)
        if m and not re.search(r"\b" + word + r"\b", m.group(1), re.I):
            return "filter_dropped", f"{res.rid} counted only {length} videos ({_clip(said, 60)})"
    return None


# the scope lines brain/tools.py writes in meta.filters_said, joined by "; " (tools._filters_said, tools._label_of):
# "only gaming (area)", "without Minecraft builds (theme)", "only videos with 'speedrun' in the title", "on Mondays",
# "YouTube only", and first_last's "watercolor: Watercolor painting (theme)". The length lines ("only videos known to
# be long", "only Shorts and reels") are _filter_dropped's.
_SCOPE_REF = re.compile(r"^(?:(?P<op>only|without)|(?P<subj>[^:]{1,80}):) (?:(?P<label>.+) \((?:area|theme|channel|"
                        r"collection)\)|videos with '(?P<words>.+)' in the title)$")
_SCOPE_DAY = re.compile(r"^on (?P<day>" + "|".join(d.capitalize() for d in
                                                   ("monday", "tuesday", "wednesday", "thursday", "friday",
                                                    "saturday", "sunday")) + r")s$")
_SCOPE_PLATFORM = re.compile(r"^(?P<p>YouTube|Instagram) only$")
_EXCLUDE_WORDS = re.compile(r"\b(?:without|except|excluding|leaving out|left out|other than|not counting|apart from|"
                            r"besides|outside of|minus|setting aside|no)\b", re.I)
_SCOPE_STOP = {"and", "the", "of", "for", "with", "videos", "video", "title", "your", "my"}


def scope_parts(res):
    """[{kind: only|without|subject|weekday|platform, label, words}] of a result the tools scoped (from
    meta.filters_said in the tools' own fixed forms; any other line, the helper's "only <topic>" included, is not a
    scope part here: insight's topic rules read the sheet's filters.topic)."""
    said = (res.meta or {}).get("filters_said") if res is not None else None
    if not isinstance(said, str) or not said.strip():
        return []
    theirs = [k for k in ((res.meta or {}).get("resolved") or {})]
    out = []
    for part in [p.strip() for p in said.split("; ") if p.strip()]:
        m = _SCOPE_REF.match(part)
        if m:
            label = m.group("label") or m.group("words") or ""
            kind = m.group("op") or "subject"
            extra = [m.group("subj")] if m.group("subj") else []
            words = {w for x in [label] + extra + theirs for w in re.findall(r"[a-z0-9]+", _low(x))
                     if len(w) >= 3 and w not in _SCOPE_STOP}
            out.append({"kind": kind, "label": label, "words": sorted(words)})
            continue
        m = _SCOPE_DAY.match(part)
        if m:
            out.append({"kind": "weekday", "label": "", "words": [m.group("day").lower()]})
            continue
        m = _SCOPE_PLATFORM.match(part)
        if m:
            out.append({"kind": "platform", "label": "", "words": [m.group("p").lower()]})
    return out


def _scope_dropped(raw, markers, res, low):
    """A number, a date, a count or a rank word of a scoped result needs the scope's words in the same sentence (a
    channel's count inside "only Minecraft builds" is its Minecraft videos only; a share is of the scoped items): the
    label or their own word for it, and for a "without" an exclusion word too. A sentence that only names a row
    claims nothing the scope changes."""
    parts = scope_parts(res)
    if not parts:
        return None
    mine = [mk for mk in markers if mk.rid == res.rid or (mk.kind == "calc" and mk.a.startswith(res.rid + "."))]
    claims = any(mk.kind != "row" for mk in mine) or (bool(mine) and bool(_RANK.search(low) or _LEAST.search(low)))
    if not claims:
        return None
    text = strip_markers(raw).lower()
    for p in parts:
        hit = any(re.search(r"\b" + re.escape(w) + r"(?:s|es)?\b", text) for w in p["words"])
        if p["kind"] == "without" and not _EXCLUDE_WORDS.search(text):
            hit = False
        if not hit:
            said = (res.meta or {}).get("filters_said") or ""
            return "filter_dropped", f"{res.rid} counts {_clip(said, 80)}: say it in the sentence"
    return None


_VERBS = {"opened": re.compile(r"\b(?:opened|watched|viewed)\b", re.I), "saved": re.compile(r"\bsaved\b", re.I),
          "liked": re.compile(r"\bliked\b", re.I)}


def _verb_dropped(raw, markers, res, low):
    """A count of a result the tools counted by saves (or likes) said as what they opened, or the reverse (merge seam:
    the tools' meta.base is "of what you saved" for a saved breakdown, and insight's checks read no verb)."""
    base = _low((res.meta or {}).get("base") or "")
    m = re.fullmatch(r"of what you (opened|saved|liked)", base)
    if not m or not res.is_sheet:
        return None
    if not any(mk.kind != "row" and mk.rid == res.rid for mk in markers):
        return None
    own = m.group(1)
    said = {v for v, rx in _VERBS.items() if rx.search(low)}
    if said and own not in said:
        return "base", f"{res.rid} counts what you {own}: say '{own}'"
    return None


def _sensitive(text, turn):
    from .. import profile as P
    if any(n and _low(n) in _low(text) for n in turn.sensitive_names):
        if not (turn.unlock and any(_low(turn.unlock) in _low(n) for n in turn.sensitive_names if _low(n) in
                                    _low(text))):
            return True
    # the unlock is per topic (SPEC 8.4): its own words are taken out, any other sensitive word still fails
    return bool(P.sensitive(_mask_unlocked(text, turn.unlock)))


# ------------------------------------------------------------------ step 3.8: insight's checks, one sentence
_NEUTRAL = "changed"


def slotted(raw, markers, plain_names, cited_names, res):
    """The sentence in insight's slotted form: value markers -> `{path}` (the hedge kept; a date stays as typed), row
    markers and cited plain names -> the row's name slot; a calc of a row's share against its share before -> that
    row's `{change_vs_previous}` slot; any other calc -> a neutral word for ratio words ("doubled" -> "changed") or
    nothing for a typed number (the direction words of its clause stay); count spans -> nothing (their words stay);
    the model's own "the 4 weeks" loses its digit unless it is the sheet's exact window phrase. None when a cited row
    has no name slot."""
    edits = []   # (start, end, new)
    for mk in markers:
        if mk.kind == "value":
            rest = re.sub(r"\.change_pts$", ".change_vs_previous", mk.rest)
            if isinstance(mk.value, str) and _measure(mk.rest, mk.value)[1] == "date":
                edits.append((mk.mstart, mk.end, ""))     # a date stays as typed (insight checks dates itself)
                continue
            if isinstance(mk.value, str):
                edits.append((mk.start, mk.end, "{" + rest + "}"))
                continue
            h = NUM_TAIL.search(raw[:mk.mstart])
            # the number (and its sign) becomes the slot; a hedge before it stays as typed
            st = (h.start("sign") if h.group("sign") else h.start("num")) if h else mk.start
            edits.append((max(st, mk.start), mk.end, "{" + rest + "}"))
        elif mk.kind == "row":
            nk = I._record_name_key(mk.value) if isinstance(mk.value, dict) else None
            if nk is None:
                return None
            edits.append((mk.start, mk.end, "{" + mk.rest + "." + nk + "}"))
        elif mk.kind == "calc":
            words = CALC_TAIL.search(raw[:mk.mstart])
            ra, rb = mk.a.split(".", 1)[1], mk.b.split(".", 1)[1]
            own = _owner(ra)
            if mk.op == "points" and own and own == _owner(rb) and {_segs(ra)[-1][0], _segs(rb)[-1][0]} == \
                    {"share", "previous_share"}:
                # a row's move in points, its share now against before: insight's own change cell says it, so
                # insight still reads a number beside the direction word (code verified the typed one)
                try:
                    has = isinstance(_resolve(res.sheet, own + ".change_vs_previous"), (int, float))
                except KeyError:
                    has = False
                if has:
                    edits.append((mk.start, mk.end, "{" + own + ".change_vs_previous}"))
                    continue
            if words and words.group("words"):
                edits.append((mk.start, mk.end, _NEUTRAL))
            else:
                edits.append((mk.start, mk.end, ""))
        elif mk.kind == "count":
            # the length of a list ("the top 3"): verified by code; insight's strict reading takes any number word
            # for a free number ("with four areas rising"), so the count goes and its words stay ("the top")
            edits.append((mk.start, mk.end, ""))
    # plain cited names (not inside a marker's span)
    spans = [(mk.start, mk.end) for mk in markers]
    for a, b, n in plain_names:
        if any(x < b and a < y for x, y in spans):
            continue
        rest = cited_names.get(n)
        if rest is None:
            f_ = res.sheet.get("filters") or {}
            if n in {_low(v) for v in (f_.get("topic"), f_.get("channel")) if isinstance(v, str)}:
                continue   # the filter's topic: insight allows it typed
            # a scope word of the tools (meta.resolved, meta.filters_said: "gaming" of "only gaming (area)"): insight
            # does not know the tools' scope and would read it as a name typed beside a number (typed_name); the
            # scope rule (_scope_dropped) has checked it, so insight reads the sentence without it
            edits.append((a, b, ""))
            continue
        try:
            row = _resolve(res.sheet, rest)
        except KeyError:
            return None
        nk = I._record_name_key(row) if isinstance(row, dict) else None
        if isinstance(row, str):
            edits.append((a, b, "{" + rest + "}"))
        elif nk:
            edits.append((a, b, "{" + rest + "." + nk + "}"))
    # the window said in the model's own words ("the 4 weeks to 30 Oct"), checked by step 15: its count of weeks is
    # no number of the sheet's, so it is taken out ("the weeks to 30 Oct") rather than read as a free number
    words = " ".join(_window_phrases(res)).lower()
    full = [x for x in ((res.meta or {}).get("window_said"), (res.sheet.get("window") or {}).get("words"),
                        (res.sheet.get("previous") or {}).get("words")) if isinstance(x, str) and x.strip()]
    exact = [(m.start(), m.end()) for ph in full for m in re.finditer(re.escape(ph.strip()), raw, re.I)]
    for m in _SPAN_N.finditer(raw):
        if any(x < m.end() and m.start() < y for x, y in spans) or any(a < m.end() and m.start() < b for a, b, _t in
                                                                        edits):
            continue
        if any(x <= m.start() and m.end() <= y for x, y in exact):
            continue   # the window's own words as the sheet says them: insight reads those itself
        if re.search(r"\b" + m.group(1) + r"\s+" + m.group(2).lower().rstrip("s"), words):
            edits.append((m.start(1), m.end(1) + 1, ""))
    s = raw
    for a, b, t in sorted(edits, key=lambda e: e[0], reverse=True):
        s = s[:a] + t + s[b:]
    s = re.sub(r"\s+([,.;:!?)])", r"\1", " ".join(s.split()))
    return s


def _plain_fill(text, sheet, lang="en"):
    sl = I.slots_of(text, sheet, lang)
    if isinstance(sl, str):
        return None
    out, last = [], 0
    for x in sl:
        out.append(text[last:x.start])
        t_ = x.text
        if x.key == "long_median_min" and re.match(r"^\s*-?\s*(?:min|minut)", text[x.end:x.end + 12], re.I):
            t_ = str(int(x.value))
        out.append(t_)
        last = x.end
    out.append(text[last:])
    r = re.sub(r"\s+", " ", "".join(out)).strip()
    return re.sub(r"\b(points?|puntos?)\s+(?:points?|puntos?|percentage points?)\b", r"\1", r)


def _norm_cmp(s):
    return " ".join(str(s or "").split()).strip()


def _inserted(a, b):
    """The pieces b has that a has not (words, case and punctuation aside), and whether b only inserts."""
    aw = re.findall(r"[\w%'’]+", a.lower())
    bw = re.findall(r"[\w%'’]+", b.lower())
    sm = difflib.SequenceMatcher(a=aw, b=bw, autojunk=False)
    ins, only = [], True
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        if op == "insert":
            ins.append(" ".join(bw[j1:j2]))
        else:
            only = False
            ins.append(" ".join(bw[j1:j2]) or "-" + " ".join(aw[i1:i2]))
    return ins, only


def _rewrite_reason(ins, only):
    t = " ".join(ins).lower()
    if not only:
        return "insight_rewrite"
    if re.search(r"\bto\b|\bfrom\b", t):
        return "one_value"
    if re.search(r"\bof\b", t):
        return "base_missing"
    if re.search(r"\babout\b|\bwhose\b", t):
        return "filter_dropped"
    return "insight_rewrite"


def _mask_unlocked(text, unlock):
    """The words of the turn's unlocked sensitive topic (SPEC 8.4) taken out of what insight's sensitive rule reads;
    any other sensitive word stays and still fails."""
    if not unlock:
        return text
    from .. import outside as O

    def sub(m):
        return "topic" if O.sensitive_topic([m.group(0)]) == unlock else m.group(0)
    return re.sub(r"[A-Za-z][A-Za-z'’-]*", sub, text)


def insight_check(raw, markers, plain_names, cited_names, res, where, unlock=None):
    """None or (reason, detail): the sentence through insight's own checks against the cited result's sheet."""
    s = slotted(raw, markers, plain_names, cited_names, res)
    if s is None:
        return "bad_ref", "a cited row with no name"
    s = _mask_unlocked(s, unlock)
    sheet, facts = res.sheet_k, res.facts
    lang = sheet.get("lang") or "en"
    text, why = I.render(s, sheet, facts, strict=True)
    if why:
        return why, _insight_detail(why)
    fill = _plain_fill(s, sheet, lang)
    if fill is not None and _norm_cmp(text) != _norm_cmp(fill):
        ins, only = _inserted(_norm_cmp(fill), _norm_cmp(text))
        base = I._base_of(sheet)
        bw_ = " ".join(re.findall(r"[\w%'’]+", str(base or "").lower()))
        benign = only and bool(base) and all(x in ("against " + bw_, "in " + bw_) for x in ins)
        if not benign:
            return _rewrite_reason(ins, only), "code would have to add: " + _clip(" / ".join(ins), 80)
        text = fill
    facts.slotted = bool(I.SLOT.search(s))
    try:
        why = I.check_sentence(text, facts, need_fact=False)
        if not why and where != "lead":
            why = I._obs_more(text, "", sheet, s, facts)
        if not why and I.n_numbers(text, facts) > I.NUMBERS_MAX:
            why = "number_run"
        if not why and I.shorts_left_out(text, sheet):
            why = "shorts_left_out"
    finally:
        facts.slotted = False
    if why:
        return why, _insight_detail(why)
    sc = I.scoped(text, sheet)
    if _norm_cmp(sc) != _norm_cmp(text):
        ins, only = _inserted(_norm_cmp(text), _norm_cmp(sc))
        r = "base" if not only else _rewrite_reason(ins, only)
        return r, "the base is " + _clip(" / ".join(ins) or (I.bases(sheet) or {}).get("opened") or "", 80)
    g, gwhy = I.gate_sentence(text, sheet, I._gate_names(sheet), {"opened_said": True})
    if gwhy:
        return gwhy, _insight_detail(gwhy)
    if _norm_cmp(g) != _norm_cmp(text):
        ins, only = _inserted(_norm_cmp(text), _norm_cmp(g))
        # the gate takes out a second "of what you opened" (the answer's base, said once): words it removes that are
        # the result's own base change nothing the sentence claims
        if not all(re.fullmatch(r"-of (?:what|everything|all) you (?:opened|watched)", x) for x in ins):
            return _rewrite_reason(ins, only), "code would have to add: " + _clip(" / ".join(ins), 80)
    return None


_INSIGHT_TEXT = {"bound": "a number stands only next to the name of its own row",
                 "mostly": "'mostly' needs a share of 50% or more", "spread": "'mostly' needs a share of 50% or more",
                 "not_top": "'led', 'top', 'most' need the first row", "typed_name": "every name needs its marker",
                 "free_number": "a number with no marker", "direction": "the direction does not fit the values",
                 "small_move": "a move under 3 points is not said", "no_base": "a change needs its base period",
                 "vague": "a direction with no number"}


def _insight_detail(why):
    return _INSIGHT_TEXT.get(str(why).split(":")[0], f"insight: {why}")


def _non_sheet(raw, markers, res, low):
    """Step 4 of 4.3: the rules of `search`, `learned` and `find` results (and item lists)."""
    tool = res.tool
    if tool == "find":
        if _RANK.search(low) or _UPW.search(low) or _DOWNW.search(low):
            return "rank", "a find result has names and counts only"
        return None
    if tool == "learned":
        if not re.fullmatch(r"\s*\[" + re.escape(res.rid) + r"\.points\[\d+\]\]\s*\.?\s*", raw) and any(
                mk.kind == "row" and ".points[" in mk.path for mk in markers):
            return "point_text", "a learned point is exactly its marker"
        for mk in markers:
            if mk.kind == "value":
                return "bad_marker", "a learned result carries a count marker and row markers only"
        return None
    # search and item lists
    for mk in markers:
        if mk.kind == "row" and not re.match(r"^items\[\d+\]$", mk.rest):
            return "not_item", f"{mk.path} is not an item row"
        if mk.kind == "value" and _measure(mk.rest, mk.value)[1] not in ("date", "count", "name"):
            return "bad_marker", f"{mk.path}"
    rows = [mk for mk in markers if mk.kind == "row"]
    for mk in rows:
        fit = mk.value.get("fit") if isinstance(mk.value, dict) else None
        if fit == "weak" and re.search(r"\b(?:here is|here's|this is|found it|that's the one|is the one)\b", low):
            return "weak_fit", f"{mk.path} is a weak match"
        # a search row carries no `how` of its own: the result's sheet says which kind it searched (merge seam)
        how = str((mk.value.get("how") if isinstance(mk.value, dict) else None) or res.sheet.get("how") or "")
        if re.search(r"\bsaved\b", low) and how and not re.search(r"save|collection|playlist", how):
            return "wrong_name", f"{mk.path} was not saved ({how})"
    for m in re.finditer(r"[\"“]([^\"”]{2,120})[\"”]", raw):
        if not any(isinstance(mk.value, dict) and _low(mk.value.get("title")) == _low(m.group(1)) for mk in rows):
            return "wrong_name", "a quoted title must be the row's own title"
    return None


# ------------------------------------------------------------------ outside lines (4.3 step 6) and items (step 5)
def check_outside(entry, ledger, kept_rows, turn=None):
    """(kept, [reasons]) for one outside entry. `kept_rows`: row paths cited in kept history sentences."""
    reasons = []
    about, text, source = entry.get("about"), entry.get("text") or "", entry.get("source")
    if source != "general":
        reasons.append("source")
    if about not in kept_rows:
        reasons.append("about_not_cited")
    t = " ".join(str(text).split())
    if not t or len(t) > OUTSIDE_CHARS or len(I._sentences(t)) > 2:
        reasons.append("too_long")
    if re.search(r"\d", _YEAR.sub(" ", t)):
        reasons.append("number")
    if re.search(r"\b(?:you|your|you're|yours|you've|yourself)\b", t, re.I):
        reasons.append("second_person")
    if re.search(r"[\[\]{}]", t):
        reasons.append("marker")
    if I._LINK.search(t) or re.search(r"@\w|\S+@\S+", t):
        reasons.append("link")
    if WORLD_CLAIMS.search(t) and re.search(r"\bsubscribers?|followers|views\b", t, re.I):
        reasons.append("number")
    turn = turn or Turn()
    if _sensitive(t, turn):
        reasons.append("sensitive")
    # no library name other than its own entity's
    own = set()
    if about and "." in about:
        rid, rest = about.split(".", 1)
        r = ledger.get(rid)
        try:
            row = _resolve(r.sheet, rest) if r else None
        except KeyError:
            row = None
        if isinstance(row, dict):
            # its own names, and what its row says of it (its theme, its area)
            own = {_low(n) for n in _row_names(row, rest)} | {_low(x) for x in row.values() if isinstance(x, str)}
    for a, b, n in _name_spans(t, ledger.all_names(), turn.names):
        if n not in own:
            reasons.append("other_name")
            break
    return (not reasons), reasons


def _item_rows(ledger):
    out = {}
    for r in ledger.by_rid.values():
        for i, it in enumerate(r.sheet.get("items") or []):
            if isinstance(it, dict):
                out[f"{r.rid}.items[{i}]"] = it
    return out


# ------------------------------------------------------------------ the whole answer
def _split(text):
    return I._sentences(text or "")


def _claim_key(o, markers):
    return frozenset(mk.path for mk in markers if mk.kind == "value") | frozenset(
        f"{mk.op}({mk.a},{mk.b})" for mk in markers if mk.kind == "calc")


def _lead_names_window(lead_text, ledger, rid):
    r = ledger.get(rid) if rid else None
    if r is None:
        r = next(iter(ledger.by_rid.values()), None)
    if r is None or not r.sheet.get("window"):
        return True
    plain = strip_markers(lead_text)
    said = (r.meta or {}).get("window_said") or ""
    if said and _low(re.split(r"[(,]", said)[0]) in _low(plain):
        return True
    if r.sheet.get("kind") in ("first", "last") and _low(said).startswith("all your history") and re.search(
            r"\[" + re.escape(r.rid) + r"\.items\[\d+\]\.(?:when|at|date)\]", lead_text):
        # merge seam (first_last over all of their history): the item's own day, checked against its cell, is the
        # time the lead claims; "in all your history" adds nothing to "you first opened ... on 10 January 2025"
        return True
    sheet = r.sheet_k
    wl = I.window_lead(plain, sheet)
    if wl == plain:
        return True
    w = r.window()
    if _LATELY.search(plain) and re.search(r"\b(?:4|four) weeks\b|\blately\b", said + " " +
                                           str((r.sheet.get("window") or {}).get("words") or ""), re.I):
        return True
    if w[0] and w[1]:
        # a month or a year that is the whole window ("In October 2026", "In 2025")
        if w[0].day == 1 and w[0].year == w[1].year:
            m = _MONTHS[w[0].month - 1]
            if w[0].month == w[1].month and re.search(r"\b" + m[:3] + r"\w*\b", plain, re.I):
                return True
            if w[0].month == 1 and w[1].month == 12 and re.search(r"\b" + str(w[0].year) + r"\b", plain):
                return True
    return False


def check_answer(form, ledger, turn=None):
    """The form against the ledger -> Verdict (SPEC 4.3). `form`: an AnswerForm or its dict; `ledger`: a Ledger, or
    the turn's result envelopes (a list, or a dict by rid)."""
    turn = turn or Turn()
    if not isinstance(ledger, Ledger):
        ledger = Ledger(ledger)
    try:
        f = form if isinstance(form, AnswerForm) else AnswerForm.model_validate(form)
    except ValidationError as e:
        return Verdict(outcomes=[], form_error=str(e.errors()[0].get("type")), repair=True)
    v = Verdict(outcomes=[])
    state = {}
    claimed = []
    # the lead (1 to 2 sentences, <= ANSWER_MAX) and the points (0 to 3, each <= SENT_MAX)
    lead_s = _split(f.lead)
    if not lead_s:
        v.outcomes.append(Outcome("lead", 0, f.lead or "", reasons=["window_missing" if f.lead else "too_long"]))
    elif len(strip_markers(f.lead)) > LEAD_MAX or len(lead_s) > 2:
        for k, s in enumerate(lead_s):
            v.outcomes.append(Outcome("lead", k, s, reasons=["too_long"]))
    else:
        for k, s in enumerate(lead_s):
            v.outcomes.append(check_sentence(s, ledger, turn, "lead", k, state))
    for k, p in enumerate(f.points):
        sents = _split(p)
        if k >= POINTS_MAX:
            v.outcomes.append(Outcome("point", k, p, reasons=["too_long"]))
            continue
        if len(sents) != 1:
            v.outcomes.append(Outcome("point", k, p, reasons=["too_long"]))
            continue
        v.outcomes.append(check_sentence(sents[0], ledger, turn, "point", k, state))
    # the lead names its window (step 2), when the lead holds no failure of its own
    lead_os = [o for o in v.outcomes if o.where == "lead"]
    if lead_os and all(o.kept for o in lead_os):
        rid = next((o.rid for o in lead_os if o.rid), None)
        if not _lead_names_window(f.lead, ledger, rid):
            lead_os[0].reasons.append("window_missing")
            r = ledger.get(rid) if rid else None
            lead_os[0].details.append(f"say the window: '{_clip((r.meta or {}).get('window_said') if r else '', 90)}'")
            lead_os[0].sent = None
    # 3.14 once: the same cells said again (the later sentence goes)
    for o in v.outcomes:
        if not o.kept:
            continue
        mks, _b = parse(" ".join(o.text.split()), ledger)
        key = _claim_key(o, mks)
        if key and any(key <= c for c in claimed):
            o.reasons.append("repeat")
            o.sent = None
            continue
        if key:
            claimed.append(key)
    v.private_line = any(o.kept and o.hidden_rank for o in v.outcomes)
    # items (step 5)
    rows = _item_rows(ledger)
    for k, it in enumerate(f.items[:ITEMS_MAX]):
        reasons = []
        if it.ref not in rows:
            reasons.append("not_item")
        note_o = None
        if it.note:
            if len(it.note) > NOTE_MAX:
                reasons.append("too_long")
            else:
                note_o = check_sentence(it.note, ledger, turn, "note", k, state)
                reasons += note_o.reasons
        v.items.append({"ref": it.ref, "note": note_o.sent if note_o and note_o.kept else None,
                        "kept": "not_item" not in reasons, "reasons": reasons})
    for it in f.items[ITEMS_MAX:]:
        v.items.append({"ref": it.ref, "note": None, "kept": False, "reasons": ["too_long"]})
    # outside (step 6): about a row cited in a kept history sentence
    kept_rows = set()
    for o in v.outcomes:
        if o.kept:
            for mk in parse(" ".join(o.text.split()), ledger)[0]:
                if mk.kind == "row":
                    kept_rows.add(mk.path)
    for k, e in enumerate(f.outside):
        if k >= OUTSIDE_MAX:
            v.outside.append({"about": e.about, "text": None, "kept": False, "reasons": ["too_many"]})
            continue
        ok, rs = check_outside(e.model_dump(), ledger, kept_rows, turn)
        v.outside.append({"about": e.about, "text": " ".join(e.text.split()) if ok else None, "kept": ok,
                          "reasons": rs})
    # chart (step 7)
    if f.chart is not None:
        v.chart = f.chart.model_dump(by_alias=True) if ledger.get(f.chart.from_) else None
    # repair (4.5): the lead failed, or more than half of the sentences
    sents = [o for o in v.outcomes if o.where in ("lead", "point")]
    failed = [o for o in sents if not o.kept]
    v.repair = (not v.lead_ok) or (len(sents) > 0 and len(failed) * 2 > len(sents))
    return v


# ------------------------------------------------------------------ the repair text (4.5)
def repair_message(verdict):
    """The text sent back as the give_answer call's tool_result with is_error: true, or None when no repair is due.
    It names each failed sentence by its place, the reason and the true values of its cells; it quotes no third-party
    text (titles are left out; brackets are neutralised)."""
    if not verdict.repair:
        return None
    if verdict.form_error:
        return f"The answer form did not validate ({verdict.form_error}). Send give_answer again with every field."
    parts = []
    for o in verdict.outcomes:
        if o.kept:
            continue
        where = "lead" if o.where == "lead" else f"point {o.index + 1}"
        if o.where == "lead" and len([x for x in verdict.outcomes if x.where == "lead"]) > 1:
            where = f"lead sentence {o.index + 1}"
        bits = []
        for r in o.reasons:
            # the true values when the step gave them ("'38%' is r1.areas[0].share = 0.356 (36%)"), else the rule
            bits.append(o.notes.get(r) or REASON_TEXT.get(r) or _insight_detail(r))
        seen, uniq = set(), []
        for b in bits:
            b = b if len(b) <= 160 else b[:159] + "…"
            if b not in seen:
                seen.add(b)
                uniq.append(b)
        parts.append(f"{where}: " + "; ".join(uniq))
    head = "These sentences failed the check. Rewrite only these, or drop the points: "
    return head + " ".join(p.rstrip(".") + "." for p in parts)
