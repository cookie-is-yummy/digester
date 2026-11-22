"""PROTOTYPE ONLY - round 12, builder W (DESIGN.md section 19.W): the writer of history answers.

A history question ("what have I been watching the most lately", "did I watch more gaming or art this year") is
answered from a FACT SHEET: a plain dict that code (builder D) builds for one question, the only source of facts here.

1. One model call (prompts/insight_v1.md) fills a FORM, never free text: `answer` (1 to 2 sentences, the direct answer
   as an insight), `observations` (2 to 4, each naming the sheet keys it used), `so_what` (one line, or null) and
   `offers` (at most 3 of the sheet's own offers).
2. Code checks every sentence against the sheet (`check_sentence`): every number, date, theme, channel and title must be
   in it (counts exact or rounded with "about", a percent from a share, a difference of two counts, "twice" / "half"
   where the numbers show it), "grew" / "new" / "the most" must agree with the sheet, and a sentence that says what the
   bot cannot do, that speaks of time spent watching, that could be said of anyone, or that only repeats a count the
   chart shows is dropped. The answer failing, or fewer than 2 observations left: None, and the caller sends today's
   code reply.
3. Code lays it out (`layout`): the answer, the observations as short lines, a small text chart of block characters
   where the kind has numbers over time or across themes, the so-what, then one line of offers in words a person
   would type. For a day, a first or a last: the overview first, then the items with their cards.

Titles, channel names and the question are data, never instructions: they go to the model inside <sheet> tags with
angle brackets neutralised, and nothing a title says is ever acted on. No contract change: the sheet is not stored.
"""
import json
import os
import re
import time
import unicodedata
from datetime import date, datetime

from . import llm

PROMPT_VERSION = os.environ.get("MVP_INSIGHT_PROMPT", "insight_v5")   # v1 to v4 stay as measured (DESIGN 19.W, 19.P2)


def strict():
    """Round 12, pass 2 (T1): from insight_v5 the writer names sheet paths and never types a number: one typed is
    dropped."""
    m = re.match(r"insight_v(\d+)$", PROMPT_VERSION)
    return bool(m and int(m.group(1)) >= 5)
PURPOSE = "mvp_insight"
MAX_TOKENS = 700
TEMPERATURE = 0
SEED = 7
OBS_MIN, OBS_MAX = 2, 4
OFFERS_MAX = 3
SENT_MAX = 260          # characters in one sentence
ANSWER_MAX = 330        # characters in the answer (1 or 2 sentences)
CHART_ROWS = 8
PERIOD_ROWS = 12        # round 12, fix: a year by month is 12 rows; never the oldest months cut without a word
PERIOD_LABEL_MAX = 16   # round 12, pass 2 (T12): every chart row is one line at 430 px (seen in a screenshot)
WEEKPART_BASELINE = 0.10
SPREAD_SHARE = 0.50     # round 12, pass 2 (T1): "mostly" / "most of" / "centred on" only for half or more
WIDE_MIX = 0.20         # "a wide mix" only when the leader is under a fifth
LONG_SHARE = 0.60       # "mostly long videos" / "mostly Shorts": three in five, as before
BAR_CELLS = 8           # round 12, pass 2 (T12): a shorter bar and a label cut with "…" keep each row on one line
LABEL_MAX = 18
# what the model is shown of a sheet (the checks read the same trimmed sheet)
SHOW = {"themes": 8, "channels": 10, "periods": 24, "topics": 6, "items": 10, "areas": 5, "so_what_candidates": 4}
# round 12, pass 2 (T2): a total of video length over a window reads as watch time and is not believable (9 hours a
# day); the writer never sees one, and code never says one. Lengths stay only as Shorts against long videos, the
# median long video, and which theme or channel is long-form (shorts_share).
HIDDEN = ("length_hours", "length_share", "length_known_share", "over_3h", "built_s", "versions", "unthemed",
          "examples", "id", "theme_id", "area_shares", "moving_lead", "into")
SHOW_INNER = 4          # channels under one theme, themes under one period
TOPIC_ONE_AREA = 0.80   # round 12, pass 2 fix: a topic whose videos are this much of one area is not told by area
OFFER_MIN_ITEMS = 10    # round 12, pass 4 (V5): no "only <theme>" of fewer videos than this in the answer


def on():
    """The writer runs unless MVP_INSIGHT=0 (read on each call: the tests turn it off and on)."""
    return os.environ.get("MVP_INSIGHT", "1") != "0"


_PROMPTS = {}


def prompt():
    if PROMPT_VERSION not in _PROMPTS:
        from . import config
        with open(os.path.join(config.HERE, "prompts", f"{PROMPT_VERSION}.md"), encoding="utf-8") as f:
            _PROMPTS[PROMPT_VERSION] = f.read()
    return _PROMPTS[PROMPT_VERSION]


# ====================================== the sheet as the model sees it ===========================================
def _clip(x):
    if isinstance(x, str):
        return x.replace("<", "‹").replace(">", "›")[:300]
    if isinstance(x, list):
        return [_clip(v) for v in x]
    if isinstance(x, dict):
        return {k: _clip(v) for k, v in x.items()}
    return x


def shown(sheet):
    """The sheet trimmed to what the model reads (and the checks read): the longest lists cut, item ids and example
    ids left out (they mean nothing to a reader), every string with its angle brackets neutralised."""
    s = {}
    for k, v in (sheet or {}).items():
        if k in SHOW and isinstance(v, list):
            v = v[:SHOW[k]]
        s[k] = v
    out = _clip(s)

    long_or_day = _long_or_one_day(sheet)

    def strip(o, depth=0):
        if isinstance(o, dict):
            r = {}
            for k, v in o.items():
                if k in HIDDEN or (k == "length_s" and depth < 2):
                    continue
                if long_or_day and k == "new_in_window":
                    continue   # round 12, pass 2 (T7): "new in the window" of a year or more, or of a day, is filler
                if k in ("channels", "themes") and depth > 0 and isinstance(v, list):
                    v = v[:SHOW_INNER]
                r[k] = strip(v, depth + 1)
            return r
        if isinstance(o, list):
            return [strip(v, depth + 1) for v in o]
        return o
    out = strip(out)
    if out.get("kind") == "compare_topics" and not out.get("comparison"):
        tp = [t for t in out.get("topics") or [] if isinstance(t, dict) and _num(t.get("items")) and t.get("name")]
        if len(tp) >= 2:
            from . import facts as F
            out["comparison"] = F._compare(tp, None, out.get("lang") or "en")
    if long_or_day and isinstance(out.get("new"), dict):
        out["new"] = dict(out["new"], channels=[])
    if out.get("kind") == "day":
        # round 12, pass 2 fix (judge A, row 6: areas that "grew" against the day before, on a 10-video day): a day is
        # compared with his usual day (`usual`), never with the one day before it
        out.pop("previous", None)
        for k in ("themes", "areas", "channels"):
            out[k] = [{a: b for a, b in r.items() if a not in ("previous_share", "previous_items", "change_vs_previous")}
                      if isinstance(r, dict) else r for r in out.get(k) or []]
    if (out.get("filters") or {}).get("without_shorts"):
        # round 12, pass 2 fix (live, "without shorts": "0% of its videos were Shorts"): no Shorts share is said of
        # an answer that left the Shorts out
        def no_sh(o):
            if isinstance(o, dict):
                return {k: no_sh(v) for k, v in o.items() if k not in ("shorts_share", "shorts", "day_shorts_share")}
            if isinstance(o, list):
                return [no_sh(v) for v in o]
            return o
        out = {k: (v if k in ("filters", "window", "question", "kind", "lang", "offers") else no_sh(v))
               for k, v in out.items()}
    if out.get("kind") == "compare_topics" and isinstance(out.get("totals"), dict):
        # round 12, pass 2 fix (live, row 5: "your watching was mostly Shorts at 81%, the long ones about 20 minutes"
        # under gaming against art): the window's own Shorts and lengths are of everything, not of the two sides
        for k_ in ("areas", "themes", "channels", "fields", "top_areas"):
            out.pop(k_, None)   # live: "your biggest area was gaming at 19%" under music against cooking
        for k_ in ("totals", "previous"):
            if isinstance(out.get(k_), dict):
                out[k_] = {k: v for k, v in out[k_].items() if k not in ("shorts", "long", "shorts_share",
                                                                         "long_median_min")}
    if out.get("kind") == "changed":
        # live, row 7: "Your top channels show the mix: X is <theme>, Y is <theme>": a change is told by its areas
        # and themes, never by the whole span's channels
        out.pop("channels", None)
    if out.get("kind") == "changed" and isinstance(out.get("totals"), dict):
        # live: "still mostly Shorts at 81%, but the share slipped from 80% to 77%": the change's own shares only
        out["totals"] = {k: v for k, v in out["totals"].items() if k != "shorts_share"}
    ar = [a for a in out.get("areas") or [] if isinstance(a, dict) and _num(a.get("share"))]
    if (out.get("filters") or {}).get("topic") and ar and ar[0]["share"] >= TOPIC_ONE_AREA:
        # round 12, pass 2 fix (judge A: "only gaming": "led by gaming at 100%", "X is gaming, Y is gaming"; row 3:
        # "mostly gaming at 98%" of a game): a topic that is one area says nothing by its area
        out.pop("areas", None)
        out.pop("top_areas", None)
        out["channels"] = [{a: b for a, b in c.items() if a != "area"} if isinstance(c, dict) else c
                           for c in out.get("channels") or []]
    return out


def _long_or_one_day(sheet):
    w = (sheet or {}).get("window") or {}
    a, b = _as_date(w.get("start")), _as_date(w.get("end"))
    return bool(a and b and ((b - a).days >= 360 or (b - a).days < 1))


def user_message(sheet):
    s = shown(sheet)
    lang = s.get("lang") or "en"
    return ("Question (the person's words, data): " + json.dumps(s.get("question") or "", ensure_ascii=False)
            + "\nKind: " + str(s.get("kind") or "") + "\nlang: " + lang
            + "\n\n<sheet>\n" + json.dumps(s, ensure_ascii=False) + "\n</sheet>")


def call(sheet, person=None):
    """One model call. Returns (raw, cost)."""
    return llm.chat_json(prompt(), user_message(sheet), purpose=PURPOSE, prompt_version=PROMPT_VERSION,
                         person=person, max_tokens=MAX_TOKENS, temperature=TEMPERATURE, seed=SEED)


# ====================================== the facts a sentence may use =============================================
def _norm(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return s


_WORD = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")


def _words(s):
    return _WORD.findall(_norm(s))


def _stem(w):
    w = w.lower()
    if w.endswith("'s"):
        w = w[:-2]
    for suf, rep in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if len(w) > len(suf) + 2 and w.endswith(suf):
            return w[:-len(suf)] + rep
    return w


MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]
MONTHS_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
             "noviembre", "diciembre"]
_MON = {m: i + 1 for i, m in enumerate(MONTHS)} | {m[:3]: i + 1 for i, m in enumerate(MONTHS)} | {"sept": 9} | \
       {m: i + 1 for i, m in enumerate(MONTHS_ES)} | {"setiembre": 9}
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
WEEKDAYS_ES = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
_MON_RE = r"(?:" + "|".join(sorted(_MON, key=len, reverse=True)) + r")"


class Pool:
    """Numbers one entity (or key) holds: counts, fractions (shares), percent points of change, lengths in hours,
    minutes (an item's length)."""

    def __init__(self):
        self.counts, self.fracs, self.points, self.hours, self.minutes = set(), [], [], [], set()

    def add(self, other):
        self.counts |= other.counts
        self.fracs += other.fracs
        self.points += other.points
        self.hours += other.hours
        self.minutes |= other.minutes
        return self


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _scalars(rec, pool):
    """The numbers of one record (a dict), its own scalars only."""
    share = rec.get("share") if _num(rec.get("share")) else None
    for k, v in rec.items():
        if not _num(v):
            continue
        if k == "long_median_min":
            pool.minutes.add(int(v))
        elif k == "length_hours":
            pool.hours.append(float(v))
        elif k == "length_s":
            pool.minutes.add(int(round(v / 60)))
            if v >= 3600:
                pool.hours.append(v / 3600)
        elif k.endswith("share"):
            pool.fracs.append(float(v))
        elif k == "change_vs_previous":
            pts = float(v) * 100 if abs(v) <= 1 else float(v)
            pool.points.append(abs(pts))
            if share is not None:
                pool.fracs.append(max(0.0, share - pts / 100))   # the share in the span before
        elif isinstance(v, int) or float(v).is_integer():
            pool.counts.add(int(v))
        else:
            pool.fracs.append(float(v)) if 0 <= v <= 1 else pool.hours.append(float(v))
    return pool


class Facts:
    def __init__(self, sheet):
        self.sheet = sheet
        self.lang = sheet.get("lang") or "en"
        self.entities = {}      # normalised name -> Pool
        self.change = {}        # normalised name -> change_vs_previous (themes, topics)
        self.items_of = {}      # normalised name -> items
        self.top = set()        # names first in some list
        self.new, self.stopped = set(), set()
        self.key_pool = {}      # top-level key -> Pool
        self.glob = Pool()      # numbers any sentence may use: totals, previous, list lengths
        self.lengths = set()    # lengths of the lists
        self.vocab = set()      # word stems of every string in the sheet
        self.dates, self.years, self.months, self.ym, self.md = set(), set(), set(), set(), set()
        self.hours_of_day = set()
        self.has_weekpart = False
        self.allowed_phrases = []
        self.alias = {}         # another way to say a name ("october 2026" for the period "Oct 2026")
        self.parents = {}       # a channel under a theme or topic, a theme under a period -> the names above it
        self.rank = {}          # name -> its best place in any list (0 = first)
        self.fields = {}        # name -> its own items, days, length_hours, share (the first record of it)
        self.periods = set()
        self.period_top = {}    # period -> the theme first in it
        self.period_area = {}   # period -> the area first in it (round 12, pass 2)
        # round 12, fix: "led" / "the most" of a name first only in a list under another name (a channel first under
        # its theme) holds only where that name is said too; the order of names said with "followed by" / "then"
        self.top_level = set()  # names first in a list of the sheet's own (themes, channels, topics)
        self.inner_top = {}     # name -> the names above the lists it is first in
        self.order = {}         # name -> (list key, place) in the sheet's own lists
        self.topic_keys = set() # the question's topic(s): a list under one of them is the answer's own list
        self.long_window = False
        self.slotted = False    # round 12, pass 2: the sentence read now came from paths (its order is bound)
        self._walk()

    # ---------- building ----------
    def _name(self, rec):
        for k in ("name", "title", "theme", "label"):
            if isinstance(rec.get(k), str) and rec.get(k).strip():
                return rec[k]
        return None

    def _entity(self, name, rec):
        key = " ".join(_words(name))
        if not key:
            return None
        p = self.entities.setdefault(key, Pool())
        _scalars(rec, p)
        if _num(rec.get("change_vs_previous")):
            self.change[key] = rec["change_vs_previous"]
        if _num(rec.get("items")):
            self.items_of[key] = max(self.items_of.get(key, 0), rec["items"])
        f = {k: rec[k] for k in ("items", "days", "length_hours", "share", "previous_share", "previous_items")
             if _num(rec.get(k))}
        if f and key not in self.fields:
            self.fields[key] = f
        if rec.get("new_in_window") is True and not self.long_window:
            self.new.add(key)
        return key

    def _text(self, s):
        for w in _words(s):
            self.vocab.add(_stem(w))
            self.vocab.add(w)
        for d in _dates_in(s):
            self._date(d)
        for md in _days_in(s):
            self.md.add(md)
            self.months.add(md[0])
        for y in re.findall(r"\b(19[89]\d|20\d\d)\b", str(s)):
            self.years.add(int(y))
        for mname, y in re.findall(r"\b(" + _MON_RE + r")\w*\.?\s+(\d{4})\b", _norm(s)):
            self.months.add(_MON[mname])
            self.ym.add((int(y), _MON[mname]))

    def _date(self, d):
        self.dates.add(d)
        self.md.add((d.month, d.day))
        self.years.add(d.year)
        self.months.add(d.month)
        self.ym.add((d.year, d.month))

    def _walk(self):
        s = self.sheet
        w = s.get("window") or {}
        for k in ("start", "end"):
            d = _as_date(w.get(k))
            if d:
                self._date(d)
        a, b = _as_date(w.get("start")), _as_date(w.get("end"))
        if a and b and a <= b and (b.year - a.year) * 12 + b.month - a.month <= 60:
            y, m = a.year, a.month
            while (y, m) <= (b.year, b.month):
                self.ym.add((y, m))
                self.months.add(m)
                self.years.add(y)
                y, m = (y + (m == 12), m % 12 + 1)
        a0, b0 = _as_date(w.get("start")), _as_date(w.get("end"))
        # round 12, fix (judge: "was new in this window" for 2020 to now): over more than about 13 months, "new" says
        # nothing a person can use
        self.long_window = bool(a0 and b0 and (b0 - a0).days > 400)
        for t in [(s.get("filters") or {}).get("topic")] + [x.get("name") for x in s.get("topics") or []
                                                             if isinstance(x, dict)]:
            if isinstance(t, str) and t.strip():
                self.topic_keys.add(" ".join(_words(t)))
        if w.get("words"):
            self.allowed_phrases.append(w["words"])
            for x in re.findall(r"\b(\d{1,3})\s+(?:weeks?|days?|months?|years?|semanas?|dias?|días?|meses|anos?|años?)\b",
                                w["words"]):
                self.glob.counts.add(int(x))   # "the 4 weeks up to ...": the 4 may be said
        self._text(s.get("question") or "")
        self._text(w.get("words") or "")
        for k, v in (s.get("filters") or {}).items():
            if isinstance(v, str):
                self._text(v)
            elif k == "left_out" and isinstance(v, dict):   # round 12, merge: the Shorts and reels left out
                self.glob.counts |= {int(x) for x in v.values() if _num(x)}
        for k in ("totals", "previous", "window_totals"):   # round 12, merge: D's window_totals ("of N then")
            if isinstance(s.get(k), dict):
                _scalars(s[k], self.glob)
                self._text(s[k].get("words") or s[k].get("label") or "")
                if s[k].get("words"):
                    self.allowed_phrases.append(s[k]["words"])
        wn = s.get("when") or {}
        for h in wn.get("busiest_hours") or []:
            hh = _hour(h)
            if hh is not None:
                self.hours_of_day.add(hh)
                if isinstance(h, dict) and _num(h.get("share")):
                    self.glob.fracs.append(float(h["share"]))   # round 12, fix: "9am (60% of the day)"
        self.busiest_weekday = None
        for k in ("weekday_share", "weekend_share"):
            if _num(wn.get(k)):
                # round 12, fix (judge: "68% was on weekdays" in two answers): a split near 5 days in 7 is everyone's
                # week, not an insight; it is not said then, nor the busiest weekday
                base = float(wn["usual_weekday_share"]) if _num(wn.get("usual_weekday_share")) else 5 / 7
                if abs(float(wn.get("weekday_share") or 0) - base) < WEEKPART_BASELINE:
                    continue   # round 12, pass 2 (T7): against his own usual week when the sheet has it
                self.has_weekpart = True
                self.glob.fracs.append(float(wn[k]))
        if self.has_weekpart and isinstance(wn.get("busiest_weekday"), str):
            self.busiest_weekday = wn["busiest_weekday"].lower()
        for key in ("areas", "themes", "channels", "periods", "topics", "items"):   # round 12, pass 2: areas
            lst = s.get(key)
            if not isinstance(lst, list):
                continue
            kp = self.key_pool.setdefault(key, Pool())
            self.lengths.add(len(lst))
            self._list(lst, kp, key)
        for part, target in (("new", self.new), ("stopped", self.stopped)):
            blk = s.get(part) or {}
            kp = self.key_pool.setdefault(part, Pool())
            for sub in ("themes", "channels"):
                xs = blk.get(sub) or []
                if part == "new" and sub == "channels" and self.long_window:
                    continue   # round 12, fix: a channel "new" since 2020 says nothing (its name stays a name)
                if xs:
                    self.lengths.add(len(xs))
                    kp.counts.add(len(xs))
                for x in xs:
                    name = x if isinstance(x, str) else self._name(x) if isinstance(x, dict) else None
                    if not name:
                        continue
                    self._text(name)
                    key = self._entity(name, x if isinstance(x, dict) else {})
                    if key:
                        target.add(key)
                        if isinstance(x, dict):
                            _scalars(x, kp)
        self._change_rows(s.get("change") or {})
        for blk in ("eras", "areas_change", "comparison", "usual", "new_today", "so_what_candidates", "seasonal",
                    "top_areas"):
            self._misc(blk, s.get(blk))
        if _hour((s.get("usual") or {}).get("busiest_hour")) is not None:
            self.hours_of_day.add(_hour(s["usual"]["busiest_hour"]))
        for blk in ("usual", "comparison", "top_areas"):   # numbers about the whole window, said with any name
            self.glob.add(self.key_pool.get(blk) or Pool())
        for nm in (s.get("new_today") or {}).get("names") or []:
            if isinstance(nm, str):
                self.new.add(" ".join(_words(nm)))
        for e in s.get("eras") or []:   # each era's leading area led that stretch ("gaming led from 2020 to 2022")
            if isinstance(e, dict) and isinstance(e.get("area"), str):
                self.inner_top.setdefault(" ".join(_words(e["area"])), set()).add("|eras")
                self.top.add(" ".join(_words(e["area"])))
        lib = (s.get("library") or {}).get("saved_not_opened") or []
        kp = self.key_pool.setdefault("library", Pool())
        for x in lib:
            if isinstance(x, dict):
                name = x.get("theme")
                if name:
                    self._text(name)
                if _num(x.get("n")):
                    kp.counts.add(int(x["n"]))
                    key = " ".join(_words(name or ""))
                    if key:
                        self.entities.setdefault(key, Pool()).counts.add(int(x["n"]))
        if lib:
            self.lengths.add(len(lib))
        for k in ("totals", "previous", "window", "filters", "when"):
            self.key_pool.setdefault(k, Pool())
        self.glob.counts |= self.lengths

    def _list(self, lst, kp, key, parent=None):
        for i, rec in enumerate(lst):
            if not isinstance(rec, dict):
                if isinstance(rec, str):
                    self._text(rec)
                continue
            name = self._name(rec)
            if name:
                self._text(name)
            for k in ("channel", "theme", "words", "area"):
                if isinstance(rec.get(k), str):
                    self._text(rec[k])
                    if k != "words":
                        self._entity(rec[k], {})   # an item's channel is a name too ("Sunday Pan" is no weekday)
            for k in ("at", "first_watched"):
                d = _as_date(rec.get(k))
                if d:
                    self._date(d)
                if k == "at" and isinstance(rec.get(k), str):
                    m = re.match(r"^\d{4}-\d{2}-\d{2}[T ](\d{2}):", rec[k])
                    if m:
                        self.hours_of_day.add(int(m.group(1)))
            ent = self._entity(name, rec) if name else None
            if ent and i == 0:
                self.top.add(ent)
                if parent is None:
                    self.top_level.add(ent)
                else:
                    self.inner_top.setdefault(ent, set()).add(parent)
            if ent:
                self.rank[ent] = min(self.rank.get(ent, 99), i)
                if parent is None:
                    self.order.setdefault(ent, (key, i))
            if ent and key == "periods":
                self.periods.add(ent)
                m = re.match(r"^([a-z]{3})[a-z]*\.?\s+(\d{4})$", ent)
                if m and m.group(1) in _MON:   # "Oct 2026" is also said "October 2026"
                    full = MONTHS[_MON[m.group(1)] - 1] + " " + m.group(2)
                    self.alias[full] = ent
                    self.alias[m.group(1) + " " + m.group(2)] = ent
                th = (rec.get("themes") or [None])[0]
                if isinstance(th, dict) and th.get("name"):
                    self.period_top[ent] = " ".join(_words(th["name"]))
                ar = (rec.get("areas") or [None])[0]   # round 12, pass 2 (T4): the period's leading area
                if isinstance(ar, dict) and ar.get("name"):
                    self.period_area[ent] = " ".join(_words(ar["name"]))
            _scalars(rec, kp)
            for sub in ("channels", "themes", "areas", "top_themes"):
                if isinstance(rec.get(sub), list):
                    self.lengths.add(len(rec[sub]))
                    self._list(rec[sub], kp, sub, parent=ent)
            if parent and ent:   # a channel's or a period theme's numbers also belong to the entity above it
                self.entities[parent].add(_scalars(rec, Pool()))
                self.parents.setdefault(ent, set()).add(parent)

    def _misc(self, key, blk):
        """Round 12, pass 2: the sheet's other blocks (eras, the areas' change, the comparison, the usual day, the
        so-what candidates): their words are the sheet's, their names are names, their numbers its own."""
        kp = self.key_pool.setdefault(key, Pool())

        def walk(o):
            if isinstance(o, dict):
                nm = next((o[k] for k in ("name", "area", "theme", "channel", "faded", "grew", "more", "less")
                           if isinstance(o.get(k), str) and o[k].strip()), None)
                for k, v in o.items():
                    if isinstance(v, str):
                        self._text(v)
                        if k in ("name", "area", "theme", "channel", "faded", "grew", "more", "less"):
                            self._entity(v, o if k == "name" or v == nm else {})
                    elif isinstance(v, (dict, list)):
                        walk(v)
                _scalars({k: v for k, v in o.items() if not isinstance(v, (dict, list, str))}, kp)
            elif isinstance(o, list):
                for v in o:
                    if isinstance(v, str):
                        self._text(v)
                    else:
                        walk(v)
        walk(blk)

    def _change_rows(self, ch):
        """Round 12, fix (live: "<theme> rose from 0.1% in 2020 to 5.6% in 2026" was dropped): the "changed"
        sheet's rising and fading themes, with their shares then and now, their change and their peak."""
        kp = self.key_pool.setdefault("change", Pool())
        for part in ("rising", "fading"):
            for k, r in enumerate(ch.get(part) or []):
                if not isinstance(r, dict) or not r.get("name"):
                    continue
                self._text(r["name"])
                self._text(str(r.get("peak_period") or ""))
                key = " ".join(_words(r["name"]))
                p = self.entities.setdefault(key, Pool())
                for f in ("from_share", "to_share", "peak_share"):
                    if _num(r.get(f)):
                        p.fracs.append(float(r[f]))
                        kp.fracs.append(float(r[f]))
                if _num(r.get("change")):
                    p.points.append(abs(float(r["change"])))
                    kp.points.append(abs(float(r["change"])))
                    self.change.setdefault(key, float(r["change"]) / 100)
                if k == 0:
                    self.top.add(key)
                    self.inner_top.setdefault(key, set()).add("|" + part)
        for x in (ch.get("from"), ch.get("to")):
            if x:
                self._text(str(x))

    # ---------- reading a sentence ----------
    def names_in(self, text):
        """The sheet's names a sentence holds (longest first, each once) and the text with them taken out."""
        t = " " + _norm(text) + " "
        found = []
        pats = [(k, k) for k in self.entities] + list(self.alias.items())
        for pat, key in sorted(pats, key=lambda x: len(x[0]), reverse=True):
            if len(pat) < 2:
                continue
            rx = r"(?<![a-z0-9])" + r"[\W_]+".join(re.escape(w) for w in pat.split()) + r"(?:'s)?(?![a-z0-9])"
            if re.search(rx, t):
                if key not in found:
                    found.append(key)
                t = re.sub(rx, f" |{chr(65 + found.index(key))}| ", t)
        return found, t

    def pool_for(self, keys, names):
        p = Pool().add(self.glob)
        if self.sheet.get("kind") in ("compare_topics", "compare_windows"):
            # a comparison may say the other side's number without naming it again ("140 hours against 60")
            for k in ("topics", "themes"):
                p.add(self.key_pool.get(k) or Pool())
        if names:
            for n in names:
                p.add(self.entities.get(n) or Pool())
                for up in self.parents.get(n, ()):
                    p.add(self.entities.get(up) or Pool())
        else:
            for k in keys or self.key_pool:
                p.add(self.key_pool.get(k) or Pool())
        return p


def _as_date(v):
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str) and re.match(r"^\d{4}-\d{2}-\d{2}", v):
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


def _dates_in(s):
    out = []
    for m in re.finditer(r"\b(\d{4}-\d{2}-\d{2})", str(s)):
        d = _as_date(m.group(1))
        if d:
            out.append(d)
    return out


def _days_in(s):
    """(month, day) of each '30 October' / 'October 30' a text holds (the year may be left out)."""
    t = _norm(s)
    out = []
    for d, mon in re.findall(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:de\s+)?(" + _MON_RE + r")\b", t):
        out.append((_MON[mon], int(d)))
    for mon, d in re.findall(r"\b(" + _MON_RE + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b(?!\d)", t):
        out.append((_MON[mon], int(d)))
    return out


def _hour(h):
    if isinstance(h, dict):   # round 12, fix: D's busiest_hours are {"hour", "share"}
        h = h.get("hour")
    if isinstance(h, int) and 0 <= h <= 23:
        return h
    if isinstance(h, str):
        m = re.match(r"^\s*(\d{1,2})(?::\d{2})?\s*(am|pm)?", h.lower())
        if m:
            x = int(m.group(1))
            if m.group(2) == "pm" and x < 12:
                x += 12
            if m.group(2) == "am" and x == 12:
                x = 0
            return x if 0 <= x <= 23 else None
    return None


# ====================================== the check =================================================================
STOP = set("""a an the of in on at to for from by with and or but nor so as is are was were be been being am do does
did done have has had having i me my mine you your yours yourself we our they them their it its this that these those
there here which who whom whose what where when how why if then than also just only even very really quite too much
many more most less least some any all each every both either neither no not none nor own same other another such
up down out off over under again further once into onto upon about around across after before during while within
without through between among against toward towards per via s t can could would should will shall may might must
el la los las un una unos unas de del al en con por para y o u que como cuando donde quien cual cuales es son fue
fueron era eran ser estar esta este estos estas ese esa esos esas lo le les se su sus tu tus mi mis nos muy mas menos
tambien solo ya aun sin sobre entre hasta desde hacia durante tras pero ni porque si no ha han has he hay""".split())

# Words that name a subject (a genre, a hobby, a kind of content). One of them in a sentence must be in the sheet: a
# theme the sheet does not name is a made-up fact ("you got into knitting", "gaming is a popular genre"). Every other
# plain word is allowed; names are checked as names (a capitalised word must be a word of the sheet's names).
TOPICAL = set("""gaming game games gamer gamers videogame videogames minecraft fortnite roblox esports speedrun speedruns
speedrunning anime manga cartoon cartoons comic comics music song songs singing singer rap hiphop pop rock jazz kpop
concert concerts guitar piano drums bass cooking cook cooks recipe recipes baking bake food foods meal meals diet
nutrition vegan fitness workout workouts gym exercise exercises yoga running runner sport sports football soccer
basketball baseball tennis golf hockey cricket boxing mma wrestling racing cars car automotive motorcycle motorcycles
bike bikes biking cycling travel travelling traveling trips news politics political election elections science
physics chemistry biology math maths mathematics philosophy psychology economics finance financial money investing
investment investments stocks crypto bitcoin business startup startups entrepreneurship marketing tech technology
programming coding code software gadgets phones art arts drawing painting sketching illustration animation design
fashion beauty makeup skincare hair knitting crochet sewing crafts craft diy woodworking gardening garden plants pets
dogs dog cats cat animals nature wildlife comedy memes meme pranks asmr horror crime podcast podcasts documentary
documentaries film films movie movies cinema trailers anime reality education study studying school college
languages chess photography editing architecture cleaning productivity motivation meditation religion spirituality
relationships dating parenting kids family health medical fishing hunting camping hiking climbing skating skateboarding
surfing dance dancing theater theatre poetry books book reading writing geography space astronomy
cocina cocinar receta recetas comida juegos juego videojuegos musica canciones deporte deportes futbol baloncesto
viajes viajar noticias politica ciencia matematicas finanzas dinero tecnologia programacion arte dibujo pintura moda
belleza maquillaje manualidades jardineria mascotas perros gatos comedia peliculas cine documentales educacion idiomas
ajedrez fotografia salud ejercicio gimnasio guitarra baile libros lectura""".split())
# sentences that would be true for anyone (rule I)
GENERIC_CLAIM = re.compile(r"\b(?:popular|genre|genres|great way|good way|it'?s (?:good|great|important|fun)|many "
                           r"people|everyone|people love|known for|a lot of people|worth learning|good for you|"
                           r"healthy|relaxing|fun to|muy popular|mucha gente|es bueno)\b")


_HEDGE = re.compile(r"\b(?:about|around|nearly|almost|roughly|over|under|more than|less than|close to|some|just over|"
                    r"just under|approximately|cerca de|casi|unos|unas|alrededor de|mas de|menos de)\s*$")
_LINK = re.compile(r"https?://|www\.|@\w|\.com\b")
_WATCH_TIME = re.compile(
    r"\bwatch(?:ed|ing)?\s+(?:for\s+)?(?:about\s+|around\s+|nearly\s+|over\s+|roughly\s+|almost\s+)?\d[\d,.]*\s*"
    r"(?:hours?|hrs?|h|minutes?|mins?)\b|watch[- ]?time|time (?:spent|watching)|\bspent\b|hours? (?:of|spent) "
    r"watching|minutes? (?:of|spent) watching|\bviste\s+(?:unas?\s+|casi\s+)?\d[\d.,]*\s*(?:horas?|minutos?)|"
    r"tiempo (?:viendo|de visualizacion)|pasaste|"
    # round 12, pass 2 fix (judge B: "took up 22% of your viewing", "you binged X for hours"): watch time in words
    r"\bof your viewing\b|\bviewing time\b|\bscreen time\b|\bfor hours\b|\bhours on end\b|\bbing(?:e|ed|ing)\w*",
    re.I)
_LIMITS = re.compile(
    r"\bi\s+can'?t\b|\bi\s+cannot\b|\bi\s+can not\b|\bunable\b|\bnot able\b|\bi\s+don'?t\s+(?:have|know|see|track)\b|"
    r"\bno (?:data|information|record)\b|\bnot (?:available|tracked|recorded|counted|included)\b|\bexports?\b|"
    r"\bfriends?\b|\bfact sheet\b|\bthe sheet\b|\bthe data\b|\bjson\b|\bas an ai\b|\bsorry\b|\bunfortunately\b|"
    r"\bno puedo\b|\bno veo\b|\bexportacion\w*\b|\bamigos?\b|\blo siento\b|\bdatos\b", re.I)
_TIME_WORD = {"morning": range(5, 12), "mornings": range(5, 12), "afternoon": range(12, 17),
              "afternoons": range(12, 17), "evening": range(17, 23), "evenings": range(17, 23),
              "night": list(range(20, 24)) + [0, 1, 2, 3], "nights": list(range(20, 24)) + [0, 1, 2, 3],
              "nightly": list(range(20, 24)) + [0, 1, 2, 3], "late": list(range(21, 24)) + [0, 1, 2, 3],
              "manana": range(5, 12), "mananas": range(5, 12), "tarde": range(12, 20), "tardes": range(12, 20),
              "noche": list(range(20, 24)) + [0, 1, 2, 3], "noches": list(range(20, 24)) + [0, 1, 2, 3]}
_WEEKPART = re.compile(r"\b(?:weekends?|weekdays?|fines? de semana|entre semana)\b")
_UP = re.compile(r"\b(?:grew|grow(?:s|n|ing)?|rose|ris(?:e|es|en|ing)|climb\w*|jump\w*|up from|up \d|doubl\w*|"
                 r"tripl\w*|surg\w*|took over|overtook|gain\w*|crec\w*|subi\w*|aument\w*)\b")
_DOWN = re.compile(r"\b(?:fell|fall(?:s|en|ing)?|dropp\w*|slipp\w*|shr[aiu]nk\w*|fad\w*|declin\w*|halv\w*|cool\w*|"
                   r"down from|down \d|quieter|baj\w*|cay\w*|disminu\w*)\b")
_NEW = re.compile(r"\b(?:new(?:ly)?|first time|picked up|nuevos?|nuevas?)\b")
_STOPPED = re.compile(r"\b(?:stopped|disappeared|vanished|gone|dropped off|no longer|dejaste|desaparec\w*)\b")
_SUPER = re.compile(r"\b(?:the most|most[- ](?:watched|opened|seen)|(?:watched|opened|saw) (?:the )?most|biggest|largest|top|main|mostly|leading|led|leads|dominat\w*|favou?rite|number one|"
                    r"sobre todo|principal\w*|mayoria|domina\w*|lidera\w*)\b")
_RELATION = re.compile(r"\b(?:than|more|less|fewer|grew|rose|fell|faded|up|down|twice|half|double\w*|since|before|"
                       r"previous|new|stopped|while|whereas|against|compared|behind|from|only|most|top|biggest|"
                       r"mostly|main|each|per|every|days?|hours?|shorts?|long|saved|never|que|frente|mas|menos|"
                       r"antes|nuevo|mitad|doble|desde|solo|ahead|lead|leads|led|versus|vs|lidera)\b")
# what makes a sentence more than a count the chart shows: a comparison, a change, Shorts against long, length, days
_INSIGHT = re.compile(r"\b(?:than|more|less|fewer|grew|rose|fell|faded|up|down|twice|half|double\w*|tripl\w*|since|"
                      r"before|previous|new|stopped|while|whereas|against|compared|versus|vs|ahead|shorts?|long|days?|"
                      r"hours?|saved|never|que|frente|mas|menos|antes|nuevo|mitad|doble|desde|dias?|horas?|cortos?)\b|%")
_RATIO = [(re.compile(r"\b(?:twice|double[sd]?|doubling|two times|el doble|dos veces)\b"), 2.0),
          (re.compile(r"\b(?:three times|tripled|triple|tres veces|el triple)\b"), 3.0),
          (re.compile(r"\b(?:four times|cuatro veces)\b"), 4.0)]
_FRAC = [(re.compile(r"\b(?:half|halved|la mitad|mitad)\b"), 0.5), (re.compile(r"\b(?:a third|one third|un tercio)\b"), 1 / 3),
         (re.compile(r"\b(?:two thirds|dos tercios)\b"), 2 / 3), (re.compile(r"\b(?:a quarter|one quarter|un cuarto)\b"), 0.25),
         (re.compile(r"\b(?:three quarters|tres cuartos)\b"), 0.75)]
_NUMWORD = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
            "eleven": 11, "twelve": 12, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
            "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12}
ALLOWED_CAPS = {"i", "youtube", "instagram", "shorts", "short", "tv"}
SEASONS = {"spring": (3, 4, 5), "summer": (6, 7, 8), "autumn": (9, 10, 11), "winter": (12, 1, 2),
           "primavera": (3, 4, 5), "verano": (6, 7, 8), "otono": (9, 10, 11), "invierno": (12, 1, 2)}
# what the totals call Shorts and long videos, for "Shorts doubled" and "long videos grew"
FIELDS = {"shorts": re.compile(r"\bshorts\b|\bcortos\b"),
          "long": re.compile(r"\blong(?:er)? (?:videos|ones)\b|\blong-form\b|\bvideos largos\b|\blargos\b")}


def _parse_num(s, lang):
    s = s.strip()
    if lang == "es":
        if re.match(r"^\d{1,3}(?:,\d{3})+$", s):
            s = s.replace(",", "")
        else:
            s = s.replace(".", "").replace(",", ".") if re.match(r"^\d{1,3}(?:\.\d{3})+(?:,\d+)?$", s) or "," in s \
                else s
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _near_count(n, counts, hedged):
    if not hedged:
        return int(n) == n and int(n) in counts
    for c in counts:
        if c and abs(n - c) / c <= 0.1:
            return True
    return False


def _near_frac(p, fracs, hedged):
    tol = 3.0 if hedged else 1.0
    return any(abs(p - f * 100) <= tol for f in fracs)


def _ratio_ok(r, pool):
    for xs in (sorted(pool.counts), sorted(pool.fracs), sorted(pool.hours)):
        xs = [x for x in xs if x > 0]
        for a in xs:
            for b in xs:
                if b < a and abs(a / b - r) <= r * 0.15:
                    return True
    return False


def _diff_ok(n, counts):
    cs = sorted(c for c in counts if c > 0)
    return any(abs(a - b) == n for i, a in enumerate(cs) for b in cs[i + 1:])


def check_sentence(text, facts, uses=None, chart_vals=None, need_fact=True):
    """None when the sentence holds only what the sheet holds; else why it is dropped (a short code word)."""
    why, n = _check(text, facts, uses, chart_vals)
    if why is None and need_fact and n == 0:
        return "generic"
    return why


def _check(text, facts, uses=None, chart_vals=None, maxlen=SENT_MAX):
    """(why it is dropped or None, how many of the sheet's facts it names)."""
    from . import profile as P
    raw = " ".join(str(text or "").split())
    if not raw:
        return "empty", 0
    if len(raw) > maxlen:
        return "too_long", 0
    if _LINK.search(raw):
        return "link", 0
    if P.sensitive(raw):
        return "sensitive", 0
    r = _check_body(raw, facts, uses, chart_vals)
    return (r, 0) if isinstance(r, str) else (None, r)


_ONE_DAY = re.compile(r"\b(?:on|across|over|in|en)\s+(?:1|one|un)\s+(?:different\s+|distintos?\s+|single\s+)?"
                      r"(?:days?|dias?)\b")
_COUNTED = re.compile(r"\s+(?:[a-z0-9&'-]+\s+){0,2}?(?:videos?|posts?|shorts?|clips?|vids?|reels?|publicaciones)\b")


def _check_body(raw, facts, uses, chart_vals):
    t = _norm(raw)
    for ph in facts.allowed_phrases:   # the window's own words (they carry where the record ends) are always fine
        t = t.replace(_norm(ph).rstrip(", "), " ")
    t = re.sub(r"where your (?:youtube |instagram )?export ends|donde termina tu exportacion(?: de \w+)?", " ", t)
    if _WATCH_TIME.search(t):
        return "watch_time"
    if _LIMITS.search(t):
        return "limits"
    if _ONE_DAY.search(t):   # round 12, merge: "on 1 different days" is never said (house style)
        return "one_day"
    keys = None
    if uses is not None:
        keys = [str(k).split(".")[0].split("[")[0] for k in (uses if isinstance(uses, list) else [uses])]
        keys = [k for k in keys if k in facts.sheet]
        if not keys:
            return "no_keys"
    # ---- dates first (a day before a month is never a count), then the sheet's names ----
    n_facts = 0
    for m in re.finditer(_DATE_RX, t):
        d, mon, y = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(5), m.group(4), m.group(6))
        mo = _MON[mon]
        ok = (any(x.month == mo and x.day == int(d) and x.year == int(y) for x in facts.dates) or
              ((mo, int(d)) in facts.md and int(y) in facts.years)) if y else (mo, int(d)) in facts.md
        if not ok:
            return "date"
        n_facts += 1
    t2 = re.sub(_DATE_RX, " ", t)
    names, rest = facts.names_in(t2)
    # quoted words must be a name or part of a title of the sheet
    for q in re.findall(r"\"([^\"]{3,80})\"", t):
        qn = " ".join(_words(q))
        # round 12, pass 3 fix: a follow-up's own words in quotes ("only gaming") name what they filter by
        qn = re.sub(r"^only\s+", "", qn) if re.match(r"^only\s+\S", qn) else qn
        if qn and not any(qn in e for e in facts.entities):
            return "quote"
    pool = facts.pool_for(keys, names)
    n_facts += len(names)
    # ---- months, years, hours of the day (taken out of the text once read) ----
    rest_n = rest
    for m in re.finditer(r"\b(" + _MON_RE + r")\b(?:\s+(?:de\s+)?(\d{4}))?", rest_n):
        mo = _MON[m.group(1)]
        if m.group(1) == "may" and not m.group(2):
            continue   # "may" is a word as often as a month
        if m.group(2):
            if (int(m.group(2)), mo) not in facts.ym:
                return "month"
        elif mo not in facts.months:
            return "month"
        n_facts += 1
    rest_n = re.sub(r"\b(" + _MON_RE + r")\b(?:\s+(?:de\s+)?(\d{4}))?", " ", rest_n)
    for m in re.finditer(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)|\b(\d{1,2}):(\d{2})\b", rest_n):
        h = int(m.group(1) or m.group(4))
        ap = (m.group(3) or "").replace(".", "")
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        if not any(abs(h - x) <= 1 or abs(h - x) == 23 for x in facts.hours_of_day):
            return "hour"
        n_facts += 1
    rest_n = re.sub(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)|\b(\d{1,2}):(\d{2})\b", " ", rest_n)
    for w in re.findall(r"[a-z]+", rest_n):
        if w in _TIME_WORD:
            if not any(h in _TIME_WORD[w] for h in facts.hours_of_day):
                return "time_of_day"
            n_facts += 1
    for w, months in SEASONS.items():
        if re.search(r"\b" + w + r"\b", rest_n):
            if not any(m in facts.months for m in months):
                return "season"
            n_facts += 1
    if _WEEKPART.search(rest_n):
        if not facts.has_weekpart:
            return "weekpart"
        n_facts += 1
    for i, wd in enumerate(WEEKDAYS + WEEKDAYS_ES):
        if re.search(r"\b" + wd + r"s?\b", rest_n):
            # round 12, fix: a weekday is a listed item's or the window's own day, or the busiest weekday when the
            # week's split is not everyone's (any date of the sheet used to do: a channel first watched on a Saturday)
            day_of_item = facts.sheet.get("kind") in ITEM_KINDS and any(d.weekday() == i % 7 for d in facts.dates)
            if not (day_of_item or facts.busiest_weekday == WEEKDAYS[i % 7]):
                return "weekday"
            n_facts += 1
    for y in re.findall(r"\b(19[89]\d|20\d\d)\b(?!\s*%)", rest_n):
        if int(y) not in facts.years:
            return "year"
        n_facts += 1
    rest_n = re.sub(r"\b(19[89]\d|20\d\d)\b(?!\s*%)", " ", rest_n)
    # ---- ratio and fraction words ----
    for rx, r in _RATIO:
        if rx.search(rest_n):
            if not _ratio_bound(r, facts, names, rest_n, pool):
                return "ratio"
            n_facts += 1
            rest_n = rx.sub(" ", rest_n)
    rest_n = re.sub(r"\b(\w+) times\b", lambda m: " " if m.group(1) in _NUMWORD else m.group(0), rest_n)
    for rx, f in _FRAC:
        if rx.search(rest_n):
            if not (any(abs(x - f) <= 0.07 for x in pool.fracs) or _ratio_ok(1 / f, pool)):
                return "fraction"
            n_facts += 1
    rest_n = re.sub(r"\b(?:twice|double[sd]?|doubling|half|halved|a third|a quarter)\b", " ", rest_n)
    # ---- numbers ----
    num_re = (r"(?<![\w.,])(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d{1,3}(?:,\d{3})+|\d+(?:,\d+)?)" if facts.lang == "es" else
              r"(?<![\w.,])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)")
    nums = []
    for m in re.finditer(num_re + r"\s+(?:of\s+(?:the\s+|your\s+)?|del?\s+|los\s+|las\s+)?\|([A-Z])\|", rest_n):
        v = _parse_num(m.group(1), facts.lang)
        idx = ord(m.group(2)) - 65
        if v is None or idx >= len(names):
            continue
        if names[idx] in facts.period_top or names[idx] in facts.periods:
            continue
        # a number said right before a name ("13 Blender 3D videos") is a count of a name of the sentence, never a
        # total that happens to be equal
        own = Pool()
        for n in names:
            own.add(facts.entities.get(n) or Pool())
        topic = " ".join(_words((facts.sheet.get("filters") or {}).get("topic") or ""))
        if topic and topic in names[idx]:
            tot = (facts.sheet.get("totals") or {}).get("items")
            if _num(tot):
                own.counts.add(int(tot))
        hedged = bool(_HEDGE.search(rest_n[:m.start()]))
        hours_ok = re.search(r"\bhours?\b|\bhoras?\b", t) and any(
            abs(v - h) <= max(0.6, h * (0.15 if hedged else 0.06)) for h in own.hours)
        if own.counts and not _near_count(v, own.counts, hedged) and not _diff_ok(int(v), own.counts) \
                and not hours_ok:
            return "number_of_name"
    for m in re.finditer(num_re + r"(\s*%|\s*percent|\s*per cent|\s*por ciento|\s*points?|\s*puntos?)?"
                         r"(\s*(?:hours?|hrs?|h\b|horas?))?(\s*(?:minutes?|mins?|minutos?))?(\s*(?:times|x\b|veces))?",
                         rest_n):
        v = _parse_num(m.group(1), facts.lang)
        if v is None:
            continue
        before = rest_n[:m.start()]
        hedged = bool(_HEDGE.search(before))
        nums.append(v)
        n_facts += 1
        if m.group(2):
            if "point" in m.group(2) or "punto" in m.group(2):
                if not any(abs(v - p) <= (3 if hedged else 1) for p in pool.points):
                    return "points"
            elif not (_near_frac(v, pool.fracs, hedged) or any(abs(v - p) <= (3 if hedged else 1) for p in pool.points)
                      or _share_of_total(v, facts, names, hedged)):
                return "percent"
        elif m.group(3):
            # round 12, pass 2 (T2): no total of video length, in any words ("about 3,356 hours of video on 359
            # days" read as 9 hours a day); an item's own length is said in minutes by the item lines
            return "hours"
        elif m.group(4):
            if not any(abs(v - x) <= (2 if hedged else 0) for x in pool.minutes):
                return "minutes"
        elif m.group(5):
            if not _ratio_ok(v, pool):
                return "ratio"
        else:
            topn = re.search(r"\b(?:top|first|primer\w*|los)\s*$", before)
            if _COUNTED.match(rest_n[m.end():]):
                # round 12, merge (live: "723.1 videos adding up to about 723 hours"): a number said of videos is
                # a count, never an hours figure that happens to sit in the same sentence
                if v != int(v) or not (_near_count(v, pool.counts, hedged) or topn or
                                       (_diff_ok(int(v), pool.counts) and _RELATION.search(t))):
                    return "count_of_videos"
                continue
            ok = (_near_count(v, pool.counts, hedged) or (v == int(v) and _diff_ok(int(v), pool.counts)
                                                          and _RELATION.search(t))
                  or (re.search(r"\bhours?\b|\bhoras?\b", t) and
                      any(abs(v - h) <= max(0.6, h * (0.15 if hedged else 0.06)) for h in pool.hours))
                  or (v == int(v) and int(v) in facts.hours_of_day
                      and re.search(r"\bbusiest\b|\bhours?\b|\bhoras?\b", t))
                  or (topn and v <= 10 and any(L >= v for L in facts.lengths)))
            if not ok:
                return "number"
    for w, n in _NUMWORD.items():
        if re.search(r"\b" + w + r"\b", rest_n) and not (w == "once" and facts.lang == "en"):
            if n not in pool.counts and n not in facts.lengths and not _diff_ok(n, pool.counts):
                return "number_word"
            n_facts += 1
    # ---- words: a subject the sheet does not name is a made-up fact; a claim true for anyone is worthless ----
    if GENERIC_CLAIM.search(rest_n):
        return "generic_claim"
    if _FILLER.search(rest_n):
        return "filler"
    if _UNSUPPORTED.search(rest_n) and not re.search(r"\b\d[\d,.]*\s+(?:different\s+)?(?:days|dias)\b", t):
        # (a steadiness the days say, "steadier: 190 days against 120", stands)
        return "unsupported"   # round 12, pass 2 fix (judge A: "art was smaller but steadier": no number says so)
    for tok in re.findall(r"[a-z]+(?:'[a-z]+)?", rest_n):
        w = tok.split("'")[0]
        if w not in TOPICAL and _stem(w) not in TOPICAL:
            continue
        if w in facts.vocab or _stem(w) in facts.vocab:
            continue
        return "word:" + w
    # a capitalised word inside a sentence that is no word of the sheet's names (a made-up channel of plain words)
    for m in re.finditer(r"\b([A-ZÁÉÍÓÚÑ][\w&-]+)", raw):
        pre = raw[:m.start()].rstrip(" \"“(¿¡")
        if not pre or pre[-1] in ".!?:;":
            continue   # the first word of a sentence
        w = _norm(m.group(1))
        if w in ALLOWED_CAPS or w in _MON or w in WEEKDAYS or w in WEEKDAYS_ES:
            continue
        if w in facts.vocab or _stem(w) in facts.vocab:
            continue
        # round 12, fix (live: a channel named "Stand-up <word>" was dropped): a hyphenated name is its words
        parts = [x for x in re.split(r"[-&]", w) if x]
        if parts and all(x in facts.vocab or _stem(x) in facts.vocab for x in parts):
            continue
        if len(parts) == 2 and parts[0] in ALLOWED_CAPS and parts[1] in ("heavy", "only", "free", "like", "style"):
            continue   # round 12, pass 2: "Shorts-heavy"
        return "name:" + w
    # ---- what the words claim must agree with the sheet ----
    one = [n for n in names if n in facts.change]
    if len(one) == 1:
        ch = facts.change[one[0]]
        if _UP.search(rest_n) and not _DOWN.search(rest_n) and ch <= 0:
            return "direction"
        if _DOWN.search(rest_n) and not _UP.search(rest_n) and ch >= 0:
            return "direction"
    if names and _NEW.search(rest_n) and not any(n in facts.new for n in names):
        return "not_new"
    if names and _STOPPED.search(rest_n) and not any(n in facts.stopped for n in names):
        return "not_stopped"
    topn = re.search(r"\btop (\d{1,2}|three|five|ten)\b", rest_n)
    if topn:
        k = int(topn.group(1)) if topn.group(1).isdigit() else _NUMWORD[topn.group(1)]
        if names and not any(facts.rank.get(n, 99) < k for n in names):
            return "not_top"
        rest_n = rest_n[:topn.start()] + " " + rest_n[topn.end():]
    periods = [n for n in names if n in facts.period_top or n in facts.period_area]
    if periods and _SUPER.search(rest_n):
        if not any((facts.period_top.get(p) in names and facts.period_top.get(p) != p) or
                   facts.period_area.get(p) in names
                   for p in periods):
            return "not_top"
    elif names and (_SUPER.search(rest_n) or re.search(r"\bmost of\b|\bla mayoria\b", rest_n)) and \
            not _leads_ok(facts, names):
        return "not_top"
    why = (None if facts.slotted else _order_claim(facts, names, rest_n)) or _spread_claim(facts, names, rest_n) \
        or _mix_claim(facts, rest_n)
    if why:
        return why
    if re.search(r"\b(?:saved|guardaste|guardado|guardados)\b", t) and re.search(
            r"\bnever\b|\bnot opened\b|\bunopened\b|\bnunca\b|\bsin abrir\b|\bno (?:los|las) has abierto\b", t):
        lib = (facts.sheet.get("library") or {}).get("saved_not_opened") or []
        ns = {int(x["n"]) for x in lib if isinstance(x, dict) and _num(x.get("n"))}
        said = {int(v) for v in nums if v == int(v)}
        if not ns or (said and not said & ns) or not said:
            return "library"
    if not names:
        why = _field_claim(facts, rest_n)
        if why:
            return why
    flat = " ".join(_words(raw))
    for rx, order in _CMP:
        cmp = re.search(rx, flat)
        if not cmp:
            continue
        g = cmp.groupdict()
        a, b = _first_name(facts, g["a"]), _first_name(facts, g["b"])
        if a and b and a != b and a in facts.items_of and b in facts.items_of:
            more = facts.items_of[a] > facts.items_of[b]
            want_more = g.get("w") in ("more", "mas", "bigger", "busier") if order else True
            if want_more != more:
                return "comparison"
    if chart_vals and nums:
        tot = {float(v) for v in ((facts.sheet.get("totals") or {}).get("items"),) if _num(v)}
        if all(v in chart_vals or v in tot for v in nums) and not _INSIGHT.search(rest_n.replace("|", " ")):
            return "restates_chart"
    # "up from 19 before" when 19 is a count of days: a number said of the span before is the span before's
    for m in re.finditer(r"\b(?:up|down|rising|falling|grew|fell|rose|climbed|dropped) from (?:about )?(\d[\d,.]*\d|\d)"
                         r"(?![\d,.]*\s*(?:%|percent|points?))|\b(?:against|versus|compared with) (\d[\d,.]*) (?:in )?"
                         r"(?:the (?:span|period|weeks?|months?|days?|year) )?before\b", rest_n):
        v = _parse_num(m.group(1) or m.group(2), facts.lang)
        prev = Pool()
        _scalars(facts.sheet.get("previous") or {}, prev)
        for per in facts.periods:
            prev.add(facts.entities.get(per) or Pool())
        if v is not None and not (_near_count(v, prev.counts, bool(re.search(r"about", m.group(0))))
                                  or any(abs(v - h) <= max(0.6, h * 0.15) for h in prev.hours)):
            return "previous"
    # "22% of your cooking videos" when 22% is a share of everything opened
    for m in re.finditer(r"(\d[\d.,]*)\s*%\s+of\s+(?:your|the|all)\s+(?:\|[A-Z]\||(?!what\b)[a-z]+(?: [a-z]+)?)\s+"
                         r"(?:videos|posts|items)", rest_n):
        if not re.search(r"\bshorts?\b|\blong\b|\bcortos?\b|\blargos?\b", rest_n):
            return "share_of_topic"
    # "led by 640" when it led by 428: a lead is a difference of two counts (or points)
    for m in re.finditer(r"\b(?:led|leads|ahead|more|fewer|up|down|grew|fell)\s+(?:\w+\s+)?by\s+(?:about\s+)?"
                         r"(\d[\d,.]*)(?![\d,.])(?!\s*(?:%|percent|points?))", rest_n):
        v = _parse_num(m.group(1), facts.lang)
        if v is not None and not _diff_ok(int(v), pool.counts | facts.glob.counts):
            return "lead"
    return n_facts


_DATE_RX = (r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+|de\s+)?(" + _MON_RE + r")\w*\.?(?:,?\s+(?:de\s+)?(\d{4}))?|"
            r"\b(" + _MON_RE + r")\w*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b(?!\d)(?:,?\s+(\d{4}))?")
_CMP = [(r"\b(?P<w>more|fewer|less|mas|menos)\s+(?P<a>.{2,60}?)\s+(?:than|que)\s+(?P<b>.{2,60}?)(?:\s(?:this|in|on|that|en|este|esta)\b|$)", 1),
        (r"(?P<a>.{2,60}?)\s+(?:was|were|had|got|fue|tuvo)\s+(?P<w>more|fewer|less|bigger|busier|mas|menos)\s+(?:than|que)\s+(?P<b>.{2,60}?)(?:\s(?:this|in|on|that|en|este|esta)\b|$)", 1),
        (r"(?P<a>.{2,60}?)\s+(?:beat|outnumbered|outpaced|overtook|ahead of)\s+(?P<b>.{2,60}?)(?:\s(?:this|in|on|that)\b|$)", 0)]


_FILLER = re.compile(r"\beach (?:had|with|got|gave) (?:just |only )?(?:1|one|a single)\b|\ba gap of\b|"
                     r"\bthe gap (?:was|is|came to)\b|\ba difference of\b|"   # round 12, pass 2 fix (judge A)
                     r"\b(?:all |each )?with (?:just |only )?(?:1|one|a single) video each\b|\bone video each\b|"
                     r"\bso the (?:lead|gap|difference)\b|\ba lead of \d|\beach (?:came )?from (?:just |only )?"
                     r"(?:1|one|a single)\b|"
                     r"\bcada uno con (?:1|un)\b")
_ORDER = re.compile(r"\b(?:followed by|then|ahead of|next came|after (?:it|that) came|seguid[oa]s? de|luego)\b")
_SPREAD = re.compile(r"\b(?:mostly|mainly|largely|centered on|centred on|dominated|dominant|mostly into|above all|"
                     r"primarily|predominantly|overwhelmingly|chiefly|almost entirely|almost everything|"   # pass 2 fix
                     r"nearly everything|"
                     r"the bulk of|the majority|sobre todo|principalmente|centrad[oa] en|la mayor parte)\b")
_SPREAD_V5 = re.compile(_SPREAD.pattern + r"|\bmost of (?:it|what|your|the window|that|them)\b")
# round 12, pass 2 fix (judge B: "overwhelmingly comedy (11%)"): these words need four in five
_OVERWHELM = re.compile(r"\b(?:overwhelmingly|almost entirely|almost everything|nearly everything|almost all|nearly all|"
                        r"casi todo)\b")
OVERWHELM_SHARE = 0.80
# words that claim a steadiness or an evenness no number of the sheet measures (judge A: "smaller but steadier")
_UNSUPPORTED = re.compile(r"\b(?:steadier|steady|steadily|consistent(?:ly)?|more evenly|evenly|stable|constante\w*)\b")
_ARRIVED = re.compile(r"\b(?:arriv\w*|came in|showed up|took off|appeared|lleg\w*|apareci\w*)\b")
_CONTRAST = re.compile(r"[;]|\b(?:while|whereas|but|against|than|compared|versus|vs|unlike|mientras|frente|pero)\b")
_MIX = re.compile(r"\b(?:a (?:wide|broad|big|real) (?:mix|spread|range)|all over the place|"
                  r"no single|una mezcla amplia|muy repartid[oa])\b")


def _leads_ok(facts, names):
    """Round 12, fix (judge: the 4th channel "led" because it was first under its theme): a name said to lead is
    first in one of the sheet's own lists, or first in a list under a name the sentence says too (a channel under its
    theme, a theme under its year), or under the question's topic."""
    for n in names:
        if n in facts.top_level:
            return True
        ups = facts.inner_top.get(n) or set()
        if ups & (set(names) | facts.topic_keys) or any(u.startswith("|") for u in ups):
            return True
        if n in facts.top and not ups and n not in facts.order:
            return True   # first in a list the walk does not rank (new, stopped)
    return False


def _order_claim(facts, names, text):
    """'X led with 107, followed by Y with 96': names said in a ranking order must be in that order in their list."""
    if not _ORDER.search(text):
        return None
    said = []   # the names in the order the sentence says them (names_in finds the longest first)
    for ch in re.findall(r"\|([A-Z])\|", text):
        k = ord(ch) - 65
        if k < len(names) and names[k] not in said:
            said.append(names[k])
    seq = [facts.order[n] for n in said if n in facts.order]
    for (k1, i1), (k2, i2) in zip(seq, seq[1:]):
        if k1 == k2 and i2 < i1:
            return "order"
    return None


def _spread_claim(facts, names, text):
    """'mostly X' / 'centered on X' when X is 6% of it is false framing (a spread); 'mostly long videos' for 431
    against 404 too."""
    if not _SPREAD.search(text):
        return None
    shares = [facts.fields[n]["share"] for n in names if "share" in facts.fields.get(n, {})]
    if shares and sum(shares) < SPREAD_SHARE:   # round 12, pass 2 (T1): "mostly X and Y" needs half together
        return "spread"
    tot = facts.sheet.get("totals") or {}
    sh, lo = tot.get("shorts"), tot.get("long")
    if _num(sh) and _num(lo) and sh + lo > 0:
        if re.search(r"\b(?:mostly|mainly|largely)\s+(?:long|longer)\b", text) and lo / (sh + lo) < LONG_SHARE:
            return "spread"
        if re.search(r"\b(?:mostly|mainly|largely)\s+shorts\b", text) and sh / (sh + lo) < LONG_SHARE:
            return "spread"
    return None


def _mix_claim(facts, text):
    """Round 12, pass 2 (T1): "a wide mix" only when the leader of the list it speaks of is under a fifth."""
    if not _MIX.search(text):
        return None
    for key in ("areas", "themes"):
        xs = [x for x in facts.sheet.get(key) or [] if isinstance(x, dict) and _num(x.get("share"))]
        if xs:
            return "mix" if xs[0]["share"] >= WIDE_MIX else None
    return None


def _first_name(facts, text):
    """The sheet's name that comes first in a piece of text (not the longest)."""
    t = " " + _norm(text) + " "
    best = None
    pats = [(k, k) for k in facts.entities] + list(facts.alias.items())
    for pat, key in pats:
        if len(pat) < 2:
            continue
        m = re.search(r"(?<![a-z0-9])" + r"[\W_]+".join(re.escape(w) for w in pat.split()) + r"(?![a-z0-9])", t)
        if m and (best is None or (m.start(), -len(pat)) < (best[0], -len(best[2]))):
            best = (m.start(), key, pat)
    return best[1] if best else None


def _ratio_bound(r, facts, names, text, pool):
    """'twice', 'three times': between the two names when two are named (their items, days or length), between
    this span and the one before for Shorts or long videos, else between any two numbers the sentence may use."""
    named = [n for n in names if n in facts.fields]
    for n in named:
        # round 12, pass 3 fix: a record's own move ("sports doubled, from 6% to 12%"): its share or count against the
        # span before
        a = facts.fields[n]
        for x, y in (("share", "previous_share"), ("items", "previous_items")):
            if _num(a.get(x)) and _num(a.get(y)) and min(a[x], a[y]) > 0 and \
                    abs(max(a[x], a[y]) / min(a[x], a[y]) - r) <= r * 0.15:
                return True
    if len(named) >= 2:
        a, b = facts.fields[named[0]], facts.fields[named[1]]
        pairs = [(a[k], b[k]) for k in a if k in b and not k.startswith("previous_")]
        return any(min(x, y) > 0 and abs(max(x, y) / min(x, y) - r) <= r * 0.15 for x, y in pairs)
    for f, rx in FIELDS.items():
        if rx.search(text):
            now, before = (facts.sheet.get("totals") or {}).get(f), (facts.sheet.get("previous") or {}).get(f)
            if _num(now) and _num(before) and min(now, before) > 0:
                return abs(max(now, before) / min(now, before) - r) <= r * 0.15
    return _ratio_ok(r, pool)


def _share_of_total(p, facts, names, hedged):
    """'about 1% of everything you opened': a named count over the window's total, worked out here."""
    tot = (facts.sheet.get("totals") or {}).get("items")
    if not (_num(tot) and tot > 0):
        return False
    tol = 1.0 if hedged else 0.5
    return any(abs(100 * facts.items_of[n] / tot - p) <= tol for n in names if n in facts.items_of)


def _field_claim(facts, text):
    """'Shorts grew', 'long videos fell': the totals against the span before must agree."""
    for f, rx in FIELDS.items():
        if rx.search(text):
            now, before = (facts.sheet.get("totals") or {}).get(f), (facts.sheet.get("previous") or {}).get(f)
            if not (_num(now) and _num(before)):
                continue
            if _UP.search(text) and not _DOWN.search(text) and now <= before:
                return "direction"
            if _DOWN.search(text) and not _UP.search(text) and now >= before:
                return "direction"
    return None


def _pairs(text, facts):
    """Round 12, pass 3 (U4): the (name, percent) pairs a sentence says: each sheet name with the first percent said
    within a few words after it ("Comedy edits (6%" -> ("comedy edits", 6))."""
    if not text:
        return set()
    names, t = facts.names_in(_norm(text))
    out = set()
    for m in re.finditer(r"\|([A-Z])\|", t):
        k = ord(m.group(1)) - 65
        if k >= len(names):
            continue
        nxt = re.match(r"[^|%]{0,24}?(\d+(?:\.\d+)?)\s*%", t[m.end():])
        if nxt:
            out.add((names[k], round(float(nxt.group(1)))))
    return out


def _signature(text, facts):
    """The numbers and names a sentence says (for telling a repeat)."""
    if not text:
        return set()
    names, rest = facts.names_in(_norm(text))
    nums = {x.replace(",", "").replace(".", "") for x in re.findall(r"\d[\d,.]*\d|\d", rest)}
    return {("n", n) for n in names} | {("v", v) for v in nums}


_SPAN_BEFORE = re.compile(r"\b(?:from|on|than|over|against) (?:the )?(?:span|period|stretch|window) before\b|"
                          r"\b(?:from|on|than|over|against) the previous (?:span|period|stretch|window)\b")


_PLURAL_VIDEOS = re.compile(r"\b(tutorials|episodes|clips|edits|memes|vlogs|reviews|highlights|workouts|challenges|"
                            r"projects|explainers|puzzles|pranks|mishaps|stunts|builds|games|videos) videos\b")


def tidy(text, lang="en"):
    """A checked sentence in the house style: ISO dates in words, counts with their separators, a capital first."""
    def iso(m):
        d = _as_date(m.group(0))
        if not d:
            return m.group(0)
        return (f"{d.day} de {MONTHS_ES[d.month - 1]} de {d.year}" if lang == "es" else
                f"{d.day} {MONTHS[d.month - 1].capitalize()} {d.year}")
    text = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", iso, text)

    def sep(m):
        n = int(m.group(0))
        if 1900 <= n <= 2099:
            return m.group(0)   # a year
        return _fmt(n, lang)
    text = re.sub(r"(?<![\d.,:%])\d{4,}(?![\d.,:%])", sep, text)
    text = re.sub(r"\b(\d+)\.0\b(?!\d)", r"\1", text)
    if lang == "es":
        text = re.sub(r"\b(\d{1,3}),(\d{3})\b(?!,\d)", r"\1.\2", text)
    if lang != "es":
        text = re.sub(r"\bitems\b", "videos", re.sub(r"\bitem\b", "video", text))
        # round 12, pass 2: the record says a video was opened, not watched through ("you watched about 3 times as
        # many" reads as time); the code's own sentences say "opened" too
        text = re.sub(r"\b([Yy])ou watched\b", r"\1ou opened", text)
        text = re.sub(r"\bas many as many\b", "as many", text)
        text = _SPAN_BEFORE.sub(lambda m: m.group(0).split()[0] + " before", text)
        # round 12, fix (judges: "episodes videos", "about 0.4 hours", "1 ... videos")
        text = re.sub(r"\b(about|around|nearly) 0\.(\d) hours\b",
                      lambda m: f"{m.group(1)} {int(m.group(2)) * 6} minutes", text)
        text = re.sub(r"\b(about|around|nearly) 0\.0 hours\b", r"\1 a few minutes", text)
        text = re.sub(r"\b(about|around|nearly) 1(?:\.0)? hours\b", r"\1 1 hour", text)
        text = re.sub(r"\b(about|around|nearly|almost|over) (\d{2,}|\d{1,3}(?:,\d{3})+)(\.\d+) hours\b",
                      lambda m: f"{m.group(1)} {round(float(m.group(2).replace(',', '') + m.group(3))):,} hours", text)
        text = re.sub(r"(?<![\d,.])\b1 ((?:[\w][\w&'-]* ){0,4}?)videos\b", r"1 \1video", text)
        text = _PLURAL_VIDEOS.sub(r"\1", text)
    return text[:1].upper() + text[1:] if text else text


def _sentences(s):
    s = " ".join(str(s or "").split())
    return [x for x in re.split(r"(?<=[.!?])\s+(?=[A-Z¿¡ÁÉÍÓÚÑ0-9\"{])", s) if x]   # pass 2: "{" opens a path


NUMBERS_MAX = 4
OBS_FILL = 3            # round 12, fix: code tops the observations up to 3 where the model's were dropped
_ONE_DAY_SAID = re.compile(r",?\s+(?:all\s+)?(?:on|across|over|in|en)\s+(?:1|one|a single|un)\s+(?:different\s+|single\s+|"
                           r"distintos?\s+)?(?:days?|d[ií]as?)\b")


NAMES_MAX = 5


def _keys(xs):
    return [" ".join(_words(x.get("name") or "")) for x in xs or [] if isinstance(x, dict) and x.get("name")]


def answer_shape(sheet, facts, text):
    """Round 12, fix (live: "which channels ... in 2025" answered with two themes; a day with 9 theme names): the
    answer names what was asked, a channel for a channels question, a theme for "the most" and a day, both topics
    of a comparison; and it is no run of names."""
    names = facts.names_in(text)[0]
    if len([n for n in names if n not in facts.periods]) > NAMES_MAX:   # "2020" or "Oct 2026" is a time, not a name
        return "name_run"
    kind = sheet.get("kind")
    if kind == "channels":
        cs = _keys(sheet.get("channels"))[:5]
        if cs and not any(n in cs for n in names):
            return "shape"
        top = next((c for c in sheet.get("channels") or [] if isinstance(c, dict) and c.get("name")), None)
        if top and cs and cs[0] in names and _num(top.get("items")):
            said = {_parse_num(x, facts.lang) for x in re.findall(r"\d[\d,.]*\d|\d", facts.names_in(text)[1])}
            if said and float(top["items"]) not in said:
                # the channel that led, with its count: the answer to "which channels the most"; round 12, pass 3 fix
                # (judge A, row 2): or in words only, the chart under it carrying the counts
                return "shape"
    elif kind in ("top", "day"):
        ts = _keys(sheet.get("themes")) + _keys(sheet.get("areas"))   # round 12, pass 2 (T3): an area leads too
        if ts and (sheet.get("totals") or {}).get("items", 0) >= 3 and not any(n in ts for n in names):
            return "shape"
    elif kind == "compare_topics":
        tp = _keys(sheet.get("topics"))
        if len(tp) >= 2 and not all(t in names for t in tp[:2]):
            return "shape"
    elif kind in ("first", "last") and (sheet.get("items") or []) and not re.search(_DATE_RX, _norm(text)):
        return "shape"   # round 12, pass 2: "when did I first ..." is answered with the date
    if kind == "day" and _num((sheet.get("totals") or {}).get("items")):
        n = (sheet.get("totals") or {})["items"]
        said = {_parse_num(x, facts.lang) for x in re.findall(r"\d[\d,.]*\d|\d", facts.names_in(text)[1])}
        if float(n) not in said:
            return "shape"   # round 12, pass 2 (T10): a day's overview says how many
    return None


def n_numbers(text, facts):
    """How many numbers a sentence says, besides the window's own words, dates and years."""
    t = _norm(text)
    for ph in facts.allowed_phrases:
        t = t.replace(_norm(ph).rstrip(", "), " ")
    t = re.sub(_DATE_RX, " ", t)
    years = len(re.findall(r"\b(?:19[89]\d|20\d\d)\b", t))
    t = re.sub(r"\b(19[89]\d|20\d\d)\b", " ", facts.names_in(t)[1])   # a name with digits ("Mesh3D") says no number
    n = len(re.findall(r"\d[\d,.]*", re.sub(r"\|[A-Z]\|", " ", t)))
    return n if years <= NUMBERS_MAX else n + years   # "in 2020, 2021, 2022, ... and 2026" is a run too


def _unit_before(text, sheet):
    """'up 15 points on the weeks before' when the span before is no weeks: 'before' alone."""
    said = _norm(" ".join(str(x) for x in ((sheet.get("window") or {}).get("words"),
                                            (sheet.get("previous") or {}).get("words")) if x))

    def fix(m):
        unit = m.group(2).rstrip("s")
        return m.group(0) if unit in said else m.group(1) + " before"
    text = re.sub(r"\b(from|on|than|over|against) the (weeks?|months?|days?|years?) before\b", fix, text)
    if sheet.get("kind") == "day":
        text = re.sub(r",? (?:all )?on (?:1|one) (?:different )?day\b", "", text)
    return text


# ====================================== round 12, pass 2 (T1): numbers bound to their thing by construction ======
# The writer of insight_v5 never types a number: it names sheet PATHS in braces ("{themes[2].share}",
# "{themes[0].channels[0].items}") and code puts the name and the number of that path into the sentence, so a number
# can only stand next to the thing it belongs to. A sentence is dropped when a path is not the sheet's, when a number
# is not next to its own thing ("{channels[0].items} of your {themes[0].name} videos": the channel's count for the
# whole window said as part of a theme; "{channels[2].days}" in a sentence about channels[1]), or when its words of
# rank and amount are not the sheet's ("led" / "top" need the first of a list; "followed by" the next one; "mostly",
# "most of", "centred on" half or more; "a wide mix" a leader under a fifth; "twice", "N times" the two numbers' own
# ratio; "N more" only the sheet's own difference). In the strict mode (the writer's live path) a number typed
# outside a path is dropped too: sums and differences are code's, in the sheet ("comparison"), or not said.
SLOT = re.compile(r"\{\s*([A-Za-z_]+(?:\s*\[\s*\d+\s*\])?(?:\s*\.\s*[A-Za-z_]+(?:\s*\[\s*\d+\s*\])?)*)\s*\}")
_SEG = re.compile(r"([A-Za-z_]+)(?:\[(\d+)\])?")
NAME_KEYS = ("name", "label", "title", "theme", "area", "channel", "faded", "grew", "more", "less", "field")
PHRASE_KEYS = ("words", "ratio_words", "previous_words", "balance", "direction", "how", "from", "to", "peak_period",
               "last_label", "peak_label", "busiest_weekday", "reason", "asked")
COUNT_KEYS = ("items", "days", "days_active", "shorts", "long", "n", "previous_items", "median_items", "years",
              "of_years", "last_items", "peak_items", "difference", "channels", "events", "a", "b")
DATE_KEYS = ("at", "first_watched", "last_watched", "start", "end", "export_ends", "history_starts")
HOUR_KEYS = ("hour", "busiest_hour")
LENGTH_KEYS = ("length_hours", "length_share", "length_known_share", "over_3h", "length_s")
RANKED = ("themes", "channels", "areas", "fields", "rising", "fading", "top_themes", "left", "arrived", "busiest_hours",
          "so_what_candidates")
_ROLE_NAME, _ROLE_NUM, _ROLE_PHRASE = "name", "number", "phrase"
_SUPER_V5 = re.compile(r"\b(?:the most|most[- ](?:watched|opened|seen)|biggest|largest|top|leading|led|leads|leader|"
                       r"main|dominat\w*|number one|first place|favou?rite|ahead of all|lidera\w*|principal\w*|"
                       r"topped|tops|came first|the top spot)\b")   # round 12, pass 2 fix: "topped", "came first"
_ORDINAL = re.compile(r"\b(second|third|fourth|fifth|segund[oa]|tercer[oa]?)\b")
_ORD_N = {"second": 1, "third": 2, "fourth": 3, "fifth": 4, "segundo": 1, "segunda": 1, "tercer": 2, "tercero": 2,
          "tercera": 2}
_RATIO_V5 = re.compile(r"\b(?:twice|double[sd]?|two times|three times|four times|five times|\w+ times as|"
                       r"half|halved|a third|one third|a quarter|three quarters|el doble|la mitad|veces)\b")
_DIFF_V5 = re.compile(r"^\s*(?:more|fewer|less|extra|mas|menos)\b")


class Slot:
    __slots__ = ("start", "end", "path", "segs", "value", "role", "owner", "key", "list_path", "index", "text")


def _path_segs(path):
    return [(m.group(1), int(m.group(2)) if m.group(2) is not None else None)
            for m in _SEG.finditer(re.sub(r"\s+", "", path))]


FALLBACK = {"previous.words": "before"}   # a path the prompt names that a sheet may not have


def _resolve(sheet, segs):
    try:
        return _resolve_raw(sheet, segs)
    except KeyError:
        if _path_str(segs) in FALLBACK:
            return FALLBACK[_path_str(segs)]
        raise


def _resolve_raw(sheet, segs):
    cur = sheet
    for key, idx in segs:
        if not isinstance(cur, dict) or key not in cur:
            raise KeyError(key)
        cur = cur[key]
        if idx is not None:
            if not isinstance(cur, list) or idx >= len(cur):
                raise KeyError(key)
            cur = cur[idx]
    return cur


def _path_str(segs):
    return ".".join(k + (f"[{i}]" if i is not None else "") for k, i in segs)


def _record_name_key(rec):
    for k in NAME_KEYS:
        if isinstance(rec, dict) and isinstance(rec.get(k), str) and rec[k].strip():
            return k
    return None


def _fmt_value(key, v, lang="en"):
    """A path's value as words, or None when it may not be said (a length total: T2)."""
    if key in LENGTH_KEYS:
        return None
    if isinstance(v, str):
        if key in DATE_KEYS and _as_date(v):
            return _day_words(_as_date(v), lang)
        return " ".join(v.split()) or None
    if not _num(v):
        return None
    if key in HOUR_KEYS:
        return _hour_words(v)
    if key.endswith("share") or key in ("faded_from", "faded_to", "grew_from", "grew_to"):
        return _pc(v, lang)
    if key == "change_vs_previous":
        pts = abs(float(v)) * 100 if abs(v) <= 1 else abs(float(v))
        return _points(pts, lang) if pts >= 1 else None
    if key == "change":
        return _points(abs(float(v)), lang)
    if key == "times":
        return f"{round(v)}" if v >= 3 else f"{round(v * 2) / 2:g}"
    if key == "long_median_min":
        return (f"{int(v)} minutos" if lang == "es" else f"{int(v)} minutes")
    if isinstance(v, int) or float(v).is_integer():
        return _fmt(int(v), lang)
    return None


def _points(pts, lang="en"):
    """Round 12, pass 3 (U7, live: "1 points from 2024"): "1 point", "12 points"."""
    n = round(pts)
    return (f"{n} punto" if n == 1 else f"{n} puntos") if lang == "es" else (f"{n} point" if n == 1 else f"{n} points")


def slots_of(text, sheet, lang="en"):
    """[Slot] of a template sentence, or a string (why it is dropped)."""
    out = []
    for m in SLOT.finditer(text):
        segs = _path_segs(m.group(1))
        try:
            v = _resolve(sheet, segs)
        except KeyError:
            return "bad_path"
        sl = Slot()
        sl.start, sl.end, sl.segs, sl.path, sl.value = m.start(), m.end(), segs, _path_str(segs), v
        key = segs[-1][0] if segs[-1][1] is None else None
        sl.key = key
        last_idx = max((n for n, (_k, i) in enumerate(segs) if i is not None), default=None)
        if last_idx is None:
            sl.owner, sl.list_path, sl.index = None, None, None
        else:
            sl.owner = _path_str(segs[:last_idx + 1])
            sl.list_path = _path_str(segs[:last_idx] + [(segs[last_idx][0], None)])
            sl.index = segs[last_idx][1]
            rec = _resolve(sheet, segs[:last_idx + 1])
            if not isinstance(rec, (dict, str)) or (isinstance(rec, dict) and not _record_name_key(rec)):
                sl.owner = None   # a record with no name (a busiest hour): its numbers are the window's
        if key is None and len(segs) and segs[-1][0] == "busiest_hours":
            key = sl.key = "hour"   # "{when.busiest_hours[0]}" is an hour of the day
        if isinstance(v, str):
            sl.role = _ROLE_NAME if (key in NAME_KEYS or key is None) else _ROLE_PHRASE
            sl.text = _fmt_value(key or "name", v, lang)
        elif isinstance(v, (dict, list)) or v is None or isinstance(v, bool):
            return "bad_path"
        else:
            sl.role = _ROLE_NUM
            sl.text = _fmt_value(key or "", v, lang)
            if sl.text is None:
                return "length" if key in LENGTH_KEYS else "bad_value"
        if sl.text is None:
            return "bad_value"
        out.append(sl)
    return out


def _lineage(a, b):
    if a is None or b is None:
        return False
    return a == b or a.startswith(b + ".") or b.startswith(a + ".")


def _name_owner(sl):
    """The entity a name slot names: its record (a channel's `theme` is an attribute of the channel's record)."""
    if sl.owner is not None:
        return sl.owner
    return sl.path if sl.index is not None else None


def _gap(text, a, b):
    return text[a.end:b.start] if a.end <= b.start else text[b.end:a.start]


_BREAK = re.compile(r"[,;:()—–]|\b(?:than|against|versus|vs|compared|while|whereas|and|but|y|frente|que)\b")


def bind_check(text, sheet, slots, facts, unit_slots=None):
    """None, or why the template's words or numbers are not bound to their own things (see above)."""
    names = [x for x in slots if x.role == _ROLE_NAME]
    unit_names = [x for x in (unit_slots or slots) if x.role == _ROLE_NAME]
    seq = [x for x in slots if x.role in (_ROLE_NAME, _ROLE_NUM)]
    low = _norm(text)
    for k, x in enumerate(seq):
        if x.role != _ROLE_NUM:
            continue
        # R1: a number of a named record stands only where that record is named
        if x.owner is not None and not any(_name_owner(n) == x.owner for n in unit_names) and \
                not _is_question_topic(sheet, x.owner) and not _named_as(sheet, x.owner, unit_names):
            return "unnamed_owner"
        # R2: the name next to it is its own (or the record above or below it)
        near = []
        for j in (k - 1, k + 1):
            if 0 <= j < len(seq) and seq[j].role == _ROLE_NAME:
                near.append((len(_gap(text, x, seq[j])), j < k, seq[j]))
        part_of = re.compile(r"^\s*(?:of|out of|de)\s+(?:the|your|all|all your|its|tus|los|las|sus)?\s*$")
        if k + 1 < len(seq) and seq[k + 1].role == _ROLE_NAME and part_of.match(_norm(_gap(text, x, seq[k + 1]))):
            # "N of your X videos": the N is a part of X, whatever stands before it
            no = _name_owner(seq[k + 1])
            if x.owner is None:
                return "bound_global"
            if not (no == x.owner or (no and x.owner.startswith(no + "."))):
                return "bound_to_other"
            near = []
        if near and x.owner is not None and any(_name_owner(t[2]) == x.owner or _named_as(sheet, x.owner, [t[2]])
                                                for t in near):
            near = []   # its own name stands right beside it
        if near:
            near.sort(key=lambda t: (t[0], not t[1]))
            gap_len, before, n = near[0]
            g = _norm(_gap(text, x, n))
            no = _name_owner(n)
            if x.owner is not None:
                if no != x.owner and not _named_as(sheet, x.owner, [n]):
                    # the record above it only as a part of it ("41 of your Blender 3D videos"), said after it
                    part = (not before and no and x.owner.startswith(no + ".") and
                            re.match(r"^\s*(?:of|out of|de)\s+(?:the|your|all|all your|its|tus|los|las|sus)?\s*$",
                                     g))
                    if not part and not (_BREAK.search(g) or gap_len > 40):
                        return "bound_to_other"
            elif not _BREAK.search(g) and gap_len <= 24 and not (n.owner is None and n.index is None):
                return "bound_global"
        # R3: a share of the window is never a share "of your <name>"
        if x.key in ("share", "previous_share", "from_share", "to_share", "peak_share") and k + 1 < len(seq) and \
                seq[k + 1].role == _ROLE_NAME and re.match(r"^\s*(?:of|de)\s+(?:your|the|all|all your|tus|los|las)?"
                                                           r"\s*$", _norm(_gap(text, x, seq[k + 1]))):
            return "share_of_name"
        if x.key == "shorts_share" and k + 1 < len(seq) and seq[k + 1].role == _ROLE_NAME and \
                re.match(r"^\s*(?:of|de)\b", _norm(_gap(text, x, seq[k + 1]))) and \
                not _lineage(_name_owner(seq[k + 1]), x.owner or "~"):
            return "share_of_name"
        # a count said as a share ("your Shorts share jumped from 3,716 to 12,080")
        if not (x.key or "").endswith("share") and x.key not in ("change_vs_previous", "change") and \
                re.search(r"\b(?:share|percent|proportion|parte|porcentaje)\b[^{}]{0,30}$", _norm(text[:x.start])) and \
                not re.search(r"[.;]", text[max(0, x.start - 30):x.start]):
            return "count_as_share"
        # R9: "N more" is the sheet's own difference, never a count typed before "more"
        nxt = text[x.end:x.end + 12]
        if _DIFF_V5.match(_norm(nxt)) and x.key != "difference":
            return "made_up_difference"
    plain = SLOT.sub(lambda m: " §" + str([sl.start for sl in slots].index(m.start())) + "§ ", text)
    pl = _norm(plain)
    # R4: words of rank need the first of a ranked list (or the topic with the most, for topics)
    for m in re.finditer(r"\btop (\d+|two|three|four|five|six|seven|eight|nine|ten)\b", pl):
        k_ = int(m.group(1)) if m.group(1).isdigit() else _NUMWORD[m.group(1)]
        near_ = sorted(((abs(pl.find("§" + str(slots.index(n)) + "§") - m.start()), n) for n in names),
                       key=lambda t: t[0])
        if near_ and near_[0][1].index is not None and near_[0][1].index >= k_:
            return "rank"
    pl = re.sub(r"\btop (?:\d+|two|three|four|five|six|seven|eight|nine|ten)\b", " ", pl)
    for m in _SUPER_V5.finditer(pl):
        cand = []
        for n in names:
            pos = pl.find("§" + str(slots.index(n)) + "§")
            cand.append((abs(pos - m.start()), n))
        if not cand:
            continue
        cand.sort(key=lambda t: t[0])
        n = cand[0][1]
        lst = (n.list_path or "").split(".")[-1]
        if lst in RANKED:
            # the closest name is the first of its list, or the first of that list is said with it ("X and Y led")
            if n.index != 0 and not any(x.list_path == n.list_path and x.index == 0 for x in names):
                return "rank"
        elif lst in ("topics", "periods", "items"):
            try:
                rows = _resolve(sheet, _path_segs(n.list_path))
                top = max(rows, key=lambda r: r.get("items") or 0) if rows else None
                if top is not rows[n.index]:
                    return "rank"
            except (KeyError, ValueError, TypeError):
                return "rank"
    # R5: "followed by", "then", "ahead of": the names of one list in their own order, the next after the last
    marks = {slots.index(n): n for n in names}
    for m in _ORDER.finditer(pl):
        before = [(pl.find("§" + str(k) + "§"), n) for k, n in marks.items()]
        prev_ = [x for x in before if 0 <= x[0] < m.start()]
        next_ = [x for x in before if x[0] >= m.end()]
        if not prev_ or not next_:
            continue
        a = max(prev_, key=lambda x: x[0])[1]
        b = min(next_, key=lambda x: x[0])[1]
        if not (a.list_path and a.list_path == b.list_path and a.index is not None and b.index is not None):
            continue
        lst = a.list_path.split(".")[-1]
        if lst in RANKED and b.index != a.index + 1 and b.index != a.index:
            return "order"
        if lst == "periods" and b.index < a.index:
            return "order"   # periods are in time order: "then" goes forward
        if lst == "topics":
            try:
                rows = _resolve(sheet, _path_segs(a.list_path))
                if (rows[b.index].get("items") or 0) > (rows[a.index].get("items") or 0):
                    return "order"
            except (KeyError, TypeError, IndexError):
                return "order"
    # R6: "mostly" / "most of" / "centred on": half or more, by the named records' own shares (or Shorts')
    if _SPREAD_V5.search(pl):
        sms = list(re.finditer(r"\b(mostly|mainly|largely|most of (?:it|them|what)\w*|almost entirely|almost all|"
                               r"nearly all|overwhelmingly)\s+(long|longer|shorts?)\b", pl))
        owners = {_name_owner(n) for n in names if _name_owner(n)}
        for sm in sms:
            frac = None
            prior = [(pl.find("§" + str(slots.index(n)) + "§"), n) for n in names]
            prior = [x for x in prior if 0 <= x[0] < sm.start()]
            if prior:   # the name said right before it ("X was mostly Shorts")
                try:
                    r = _resolve(sheet, _path_segs(_name_owner(max(prior, key=lambda x: x[0])[1]) or ""))
                    if isinstance(r, dict) and _num(r.get("shorts_share")):
                        frac = r["shorts_share"]
                except KeyError:
                    pass
            if frac is None:
                t = sheet.get("totals") or {}
                if _num(t.get("shorts")) and _num(t.get("long")) and t["shorts"] + t["long"]:
                    frac = t["shorts"] / (t["shorts"] + t["long"])
            need_ = 0.9 if _OVERWHELM.search(sm.group(1)) or sm.group(1) == "almost entirely" else LONG_SHARE
            if frac is None or (frac if sm.group(2).startswith("short") else 1 - frac) < need_:
                return "spread"
        if not sms:
            tot = 0.0
            seen = set()
            spm = _SPREAD_V5.search(pl)
            after = [(pl.find("§" + str(slots.index(n)) + "§"), n) for n in names]
            after = [x for x in after if x[0] >= spm.end()]
            nxt = min(after, key=lambda x: x[0])[1] if after else None
            if nxt is not None and nxt.key in ("theme", "area") and nxt.owner:
                # "X is mostly <its theme>": the share of X's own videos in that theme
                try:
                    r = _resolve(sheet, _path_segs(nxt.owner))
                    tot = float(r.get("theme_share") or 0) if isinstance(r, dict) else 0.0
                except KeyError:
                    tot = 0.0
                owners = set()
            owners = _subjects(sheet, owners, pl, slots, names)
            for o in owners:
                try:
                    r = _resolve(sheet, _path_segs(o))
                except KeyError:
                    continue
                if isinstance(r, dict) and _num(r.get("share")) and o not in seen:
                    tot += float(r["share"])
                    seen.add(o)
                elif isinstance(r, dict) and _num(r.get("items")) and "." in o and o not in seen:
                    # a part under its parent ("{topics[1].channels[0].name} carried most of it"): its own count
                    try:
                        up = _resolve(sheet, _path_segs(o.rsplit(".", 1)[0]))
                        if isinstance(up, dict) and _num(up.get("items")) and up["items"]:
                            tot += r["items"] / up["items"]
                            seen.add(o)
                    except KeyError:
                        pass
            share_slots = [float(x.value) for x in slots if x.role == _ROLE_NUM and x.key and x.key.endswith("share")
                           and (x.owner is None or x.owner in owners or not names)]
            need = OVERWHELM_SHARE if _OVERWHELM.search(pl) else SPREAD_SHARE
            if tot < need and not any(v >= need for v in share_slots):
                return "spread"
    # R7: "a wide mix": the leader of the list it names (areas, else themes) under a fifth
    if _MIX.search(pl):
        lists = [n.list_path.split(".")[-1] for n in names if n.list_path]
        key = "areas" if "areas" in lists or not lists and sheet.get("areas") else "themes"
        xs = [x for x in sheet.get(key) or [] if isinstance(x, dict) and _num(x.get("share"))]
        if not xs or xs[0]["share"] >= WIDE_MIX:
            return "mix"
    why = _bind_more(text, pl, sheet, slots, names)
    if why:
        return why
    why = _direction_check(text, pl, sheet, slots, names)   # round 12, pass 3 (U1)
    if why:
        return why
    if _change_words(pl, slots) == "no_direction":   # round 12, pass 3 (U7); a missing base is added by render
        return "no_direction"
    # R8: "twice", "N times", "half": two numbers of the sentence of one kind in that ratio, or the sheet's own
    rm = _RATIO_V5.search(pl)
    if rm and not any(x.key in ("ratio_words", "times") for x in slots):
        word = rm.group(0)
        r = 2.0 if re.search(r"twice|double|two times|el doble", word) else 0.5 if re.search(r"half|halved|mitad",
                                                                                              word) else \
            1 / 3 if "third" in word else 0.25 if "a quarter" in word else 0.75 if "three quarters" in word else \
            _NUMWORD.get(word.split()[0]) if word.split()[0] in _NUMWORD else None
        nums = [x for x in slots if x.role == _ROLE_NUM and _num(x.value) and x.value]
        ok = False
        if r:
            for a in nums:
                for b in nums:
                    if a is not b and ((a.key or "").endswith("share") == (b.key or "").endswith("share")):
                        q_ = float(a.value) / float(b.value)
                        if abs(q_ - r) <= 0.15 * r or abs(1 / q_ - r) <= 0.15 * r:
                            ok = True
        if not ok:
            return "ratio"
    return None


def _rec(sheet, path):
    try:
        r = _resolve(sheet, _path_segs(path or ""))
    except KeyError:
        return None
    return r if isinstance(r, dict) else None


def _area_of_slot(sheet, n):
    """(the area a name slot names, or None; the area its record belongs to, or None)."""
    o = _name_owner(n)
    if not o:
        return None, None
    lst = (n.list_path or "").split(".")[-1]
    r = _rec(sheet, o)
    if r is None:
        return None, None
    if lst == "areas" and n.key in (None, "name"):
        return r.get("name"), None
    if re.match(r"^areas\[\d+\]\.themes\[\d+\]$", o):
        up = _rec(sheet, o.rsplit(".", 1)[0])
        return None, (up or {}).get("name")
    if lst in ("themes", "top_themes") and n.key in (None, "name") and isinstance(r.get("area"), str):
        return None, r["area"]
    return None, None


def _subjects(sheet, owners, pl, slots, names):
    """Round 12, pass 2 fix (judge B: "mostly into gaming at 46%, led by A at 11% and B at 6%" counted 63%): the
    records a "mostly" is said of, without the themes inside a named area (they are part of it, not added to it)."""
    areas = set()
    for n in names:
        a, _ = _area_of_slot(sheet, n)
        if a:
            areas.add(_norm(a))
    if not areas:
        return owners
    out = set()
    for o in owners:
        if re.match(r"^areas\[\d+\]\.", o):
            continue
        r = _rec(sheet, o)
        if r is not None and re.match(r"^(?:themes|channels)\[\d+\]$", o) and _norm(r.get("area") or "") in areas:
            continue
        out.add(o)
    return out


def _bind_more(text, pl, sheet, slots, names):
    """Round 12, pass 2 fix: what the judges found bound to the wrong thing after the first pass (None, or why)."""
    low = _norm(text)
    # (a) a theme said inside, or leading, an area it does not belong to ("gaming, led by <a memes theme>")
    for i, a in enumerate(names):
        an, _ = _area_of_slot(sheet, a)
        if not an:
            continue
        for b in names[i + 1:] + names[:i]:
            _, ta = _area_of_slot(sheet, b)
            if ta is None or _norm(ta) == _norm(an):
                continue
            between = _gap(text, a, b)
            if not _CONTRAST.search(_norm(between)):
                return "wrong_area"
    # (b) the window's median long video said next to one record (judge A: art's side "typically about 20 minutes",
    # 20 being the whole year's); a topic's own sheet is its window
    if any(x.key == "long_median_min" and x.owner is None for x in slots):
        for n in names:
            o = _name_owner(n)
            if o and not _is_question_topic(sheet, o):
                return "median_of_window"
    for k, x in enumerate(slots):
        if x.role != _ROLE_NUM:
            continue
        after = _norm(text[x.end:x.end + 60])
        # (c) a count said where its share belongs ("Shorts made up 12,080 of your window")
        if x.key in COUNT_KEYS and re.match(r"^\s*of\s+(?:your|the|all|all your|everything)?\s*(?:window|span|what you "
                                            r"opened|everything|viewing|history|videos)\b", after):
            return "count_as_share"
        # (d) a Shorts share said as long-form ("leaned long-form at 69%" where 69% is its Shorts share)
        if x.key == "shorts_share":
            clause = re.split(r"[,;:.]", _norm(text[:x.start]))[-1]
            if not re.match(r"^\s*(?:shorts?|cortos?)\b", after) and re.search(r"\blong", clause) and \
                    not re.search(r"\bshorts?\b", clause.split("long")[-1]):
                return "shorts_as_long"
            v = float(x.value)
            pre = _norm(text[:x.start]) + " " + after[:20]
            if re.search(r"\b(?:almost|nearly|virtually)? ?all\s+(?:long|longer)\b", pre) and v > 0.1:
                return "spread"
            if re.search(r"\b(?:almost|nearly|virtually) all\s+shorts\b", pre) and v < 0.9:
                return "spread"
    # (e) "arrived" of a thing that was there before (live: "gaming arrived" of the area that led January)
    if _ARRIVED.search(pl):
        for n in names:
            r = _rec(sheet, _name_owner(n))
            if r is None:
                continue
            a, b = r.get("from_share", r.get("previous_share")), r.get("to_share", r.get("share"))
            if _num(a) and _num(b) and b > 0 and a >= 0.5 * b:
                return "not_new"
            if any(_norm(e.get("area") or "") == _norm(r.get("name") or "~") for e in (sheet.get("eras") or [])[:1]
                   if isinstance(e, dict)):
                return "not_new"
    # (f) a direction word said of a record that moved the other way (judge B: "<area> tripled to 9%" of an area
    # that fell from 16%): the record named nearest the word
    for m in list(_UP.finditer(pl)) + list(_DOWN.finditer(pl)):
        up = bool(_UP.match(pl, m.start()))
        cand = []
        for n in names:
            pos = pl.find("§" + str(slots.index(n)) + "§")
            if 0 <= pos < m.start() and m.start() - pos <= 40:
                cand.append((m.start() - pos, n))
        if not cand:
            continue
        r = _rec(sheet, _name_owner(min(cand, key=lambda t: t[0])[1]))
        if r is None:
            continue
        ch = r.get("change_vs_previous")
        if not _num(ch) and _num(r.get("from_share")) and _num(r.get("to_share")):
            ch = r["to_share"] - r["from_share"]
        if _num(ch) and ((up and ch < 0) or (not up and ch > 0)):
            return "direction"
    # (g) "opened X most", an ordinal ("came second", "your second area"): the place in its list
    for m in re.finditer(r"\b(?:opened|watched|saw|viewed)\s+§(\d+)§\s+(?:the\s+)?most\b", pl):
        n = slots[int(m.group(1))]
        if n.role == _ROLE_NAME and n.index not in (None, 0) and (n.list_path or "").split(".")[-1] in RANKED:
            return "rank"
    for m in _ORDINAL.finditer(pl):
        want = _ORD_N.get(m.group(1))
        cand = []
        for n in names:
            pos = pl.find("§" + str(slots.index(n)) + "§")
            if pos >= 0 and abs(pos - m.start()) <= 40 and (n.list_path or "").split(".")[-1] in RANKED:
                cand.append((abs(pos - m.start()), n))
        if cand and want is not None:
            n = min(cand, key=lambda t: t[0])[1]
            if n.index != want:
                return "rank"
    # round 12, pass 4 (V6, live: "MindYourDecisions came on 84 days and 106 videos, while 3Blue1Brown was close
    # behind at 98", the third channel): a word of the next place ("close behind", "came next", "runner-up") is said of
    # the record right after the one before it in the same list (the first one said, else the leader)
    for m in _NEXT_PLACE.finditer(pl):
        ranked = [n for n in names if (n.list_path or "").split(".")[-1] in RANKED and n.index is not None]
        at = {id(n): pl.find("§" + str(slots.index(n)) + "§") for n in ranked}
        cand = sorted(((abs(at[id(n)] - m.start()), n) for n in ranked if at[id(n)] >= 0 and
                       abs(at[id(n)] - m.start()) <= 40), key=lambda t: t[0])
        if not cand:
            continue
        n = cand[0][1]
        before = [x for x in ranked if x is not n and x.list_path == n.list_path and 0 <= at[id(x)] < at[id(n)]]
        want = (before[-1].index + 1) if before else 1
        if n.index != want:
            return "rank"
    return None


_NEXT_PLACE = re.compile(r"\b(?:close behind|right behind|just behind|not far behind|a close second|came next|"
                         r"next came|was next|runner[- ]up|trail(?:ed|ing)|in second place|second place)\b")


# ====================================== round 12, pass 3 (U1): a direction needs a path whose values support it ======
# Live (pass 3): "the mix shifted from one area to a broader mix with four areas rising, while Shorts became more of it",
# every direction false by recount, passed: the check bound numbers only. Now every word of direction or comparison
# comes from a sheet path whose two values code knows, in their order, exactly as numbers do; a sentence with such a
# word and no path that supports it is dropped.
_D_UP = re.compile(r"\b(?:grew|grow(?:s|n|ing)?|rose|ris(?:e|es|en|ing)|climb\w*|jump\w*|gain\w*|doubl\w*|tripl\w*|"
                   r"surg\w*|took over|overtook|picked up|up from|went up|bigger|larger|became|become|becoming|"
                   r"arriv\w*|took off|crec\w*|subi\w*|aument\w*)\b")
_D_DOWN = re.compile(r"\b(?:fell|fall(?:s|en|ing)?|dropp\w*|slipp\w*|shr[aiu]nk\w*|fad\w*|declin\w*|halv\w*|"
                     r"lost(?: ground)?|losing|down from|went down|smaller|gave way|giv(?:e|es|ing) way|left behind|"
                     r"cooled|baj\w*|cay\w*|disminu\w*)\b")
_D_SHIFT = re.compile(r"\b(?:shift\w*|moved?|moving|toward\w*|swung|swapp\w*|replaced)\b")
_D_SPREAD = re.compile(r"\b(?:broader|wider|narrow\w*|more varied|more spread|more focused|less varied|"
                       r"spread out|concentrat\w*)\b")
_D_PEAK = re.compile(r"\bpeak\w*\b")
_D_CMP = re.compile(r"\b(?:more|less|fewer|mas|menos)\b")
_D_AMOUNT = re.compile(r"\b(?:more|less|fewer) than (?:half|a (?:third|quarter|fifth)|§|\d|one|two|three|four|five|"
                       r"twice|double)|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+|§\d+§) more\b|"
                       r"\bmore of (?:the )?same\b|\bno more\b|\bonce more\b|\bany more\b|\bmore or less\b")
_D_ANY = re.compile("|".join(x.pattern for x in (_D_UP, _D_DOWN, _D_SHIFT, _D_SPREAD, _D_PEAK, _D_CMP)))
_COUNT_WORDS = re.compile(r"\b(?:three|four|five|six|seven|eight|nine|ten|tres|cuatro|cinco)\s+(?:\w+\s+)?"
                          r"(?:areas?|themes?|channels?|topics?|fields?|kinds?|categories|interests|of them)\b")


def _sign(x):
    return 0 if not _num(x) or abs(float(x)) < 1e-9 else (1 if x > 0 else -1)


def _rec_direction(sheet, path):
    """+1 (rose), -1 (fell), 0 (flat) or None (no two values of it known): from the record's own pair of values."""
    r = _rec(sheet, path)
    if r is None:
        return None
    if _num(r.get("change_vs_previous")):
        return _sign(r["change_vs_previous"])
    if _num(r.get("change")) and path.split("[")[0].split(".")[-1] in ("left", "arrived", "rising", "fading"):
        return _sign(r["change"])
    for a, b in (("from_share", "to_share"), ("previous_share", "share"), ("faded_from", "faded_to"),
                 ("previous_items", "items")):
        if _num(r.get(a)) and _num(r.get(b)):
            return _sign(float(r[b]) - float(r[a]))
    if r.get("kind") == "shorts_shift" and r.get("direction") in ("up", "down"):
        return 1 if r["direction"] == "up" else -1
    if r.get("kind") == "channel_rise":
        return 1
    if r.get("kind") == "path" and r.get("how") in ("deeper", "faded", "still"):
        return {"deeper": 1, "faded": -1, "still": 0}[r["how"]]
    return None


def _shorts_direction(sheet, slots):
    """The window's Shorts against the span before, when the sentence says a path of either."""
    paths = {x.path for x in slots}
    t, p = sheet.get("totals") or {}, sheet.get("previous") or {}

    def share(r):
        if _num(r.get("shorts_share")):
            return r["shorts_share"]
        if _num(r.get("shorts")) and _num(r.get("long")) and r["shorts"] + r["long"]:
            return r["shorts"] / (r["shorts"] + r["long"])
        return None
    if paths & {"totals.shorts_share", "previous.shorts_share", "totals.shorts", "previous.shorts"} and \
            share(t) is not None and share(p) is not None:
        return _sign(share(t) - share(p))
    ac = (sheet.get("areas_change") or {}).get("shorts") or {}
    if any(x.path.startswith("areas_change.shorts") for x in slots) and _num(ac.get("from_share")) and \
            _num(ac.get("to_share")):
        return _sign(ac["to_share"] - ac["from_share"])
    for x in slots:
        if x.path.startswith("so_what_candidates[") and x.owner:
            r = _rec(sheet, x.owner)
            if r and r.get("kind") == "shorts_shift":
                return 1 if r.get("direction") == "up" else -1
    return None


_CHANGE_KEYS = ("change_vs_previous", "change", "previous_share", "previous_items", "from_share", "faded_from",
                "grew_from")
_BASE_WORDS = re.compile(r"\b(?:before|against|than|compared|last year|earlier|previous|prior|since|the spring|"
                         r"the summer|the autumn|the fall|the winter|(?:in|from) (?:19|20)\d\d|antes|frente)\b")


def _base_of(sheet):
    """The span a change is against, in the person's words (the sheet's own), or None."""
    pw = str(((sheet or {}).get("previous") or {}).get("words") or "").strip()
    if pw and (sheet or {}).get("lang", "en") != "es":
        return re.sub(r"^(?:in|en)\s+", "", pw)
    return None


def _span_of(sheet):
    """(first, last) period of a change's own shares (areas_change), or None."""
    ac = (sheet or {}).get("areas_change") or {}
    if (sheet or {}).get("kind") == "changed" and ac.get("from") and ac.get("to") and \
            (sheet or {}).get("lang", "en") != "es":
        return str(ac["from"]), str(ac["to"])
    return None


def _change_words(pl, slots):
    """Round 12, pass 3 (U7, live: "X fell from 16% to 9%" with no base; "1 points from 2024" with no direction): a
    change says its direction (a word, or from one value to the other) and its base period."""
    if not any(x.role == _ROLE_NUM and x.key in _CHANGE_KEYS for x in slots):
        return None
    if not (_D_UP.search(pl) or _D_DOWN.search(pl) or re.search(r"\bfrom\b[^.;]*\bto\b|\b(?:up|down|higher|lower|"
                                                                r"more|less|fewer)\b", pl)):
        return "no_direction"
    if not (_BASE_WORDS.search(pl) or any(x.path in ("previous.words",) or x.key in ("from", "to", "label",
                                                                                    "peak_period", "previous_words")
                                          for x in slots)):
        return "no_base"
    return None


def _same_list_pair(owners, at):
    """[the first record said after `at`, the nearest one before it] when both are rows of one list, else None."""
    def lst(o):
        return re.sub(r"\[\d+\]$", "", o)
    before = [(p, o) for p, o, _n in owners if p < at and re.search(r"\[\d+\]$", o)]
    after = [(p, o) for p, o, _n in owners if p > at and re.search(r"\[\d+\]$", o)]
    if not before or not after:
        return None
    a, b = min(after)[1], max(before)[1]
    return [a, b] if lst(a) == lst(b) and a != b else None


def _direction_check(text, pl, sheet, slots, names):
    """None, or why a word of direction or comparison is not supported by a path of the sentence (U1)."""
    if not _D_ANY.search(pl):
        return None
    pos = {id(n): pl.find("§" + str(slots.index(n)) + "§") for n in slots}
    owners = []   # (position, owner path, slot) of the records the sentence names or gives a number of
    for n in slots:
        o = _name_owner(n) if n.role == _ROLE_NAME else n.owner
        if o:
            owners.append((pos[id(n)], o, n))
    shorts_said = bool(re.search(r"\bshorts?\b", pl))

    def near(at, before=48, after=36):
        c = [(at - p, o, n) for p, o, n in owners if 0 <= at - p <= before] + \
            [(p - at + 0.5, o, n) for p, o, n in owners if 0 < p - at <= after]
        return [o for _d, o, _n in sorted(c, key=lambda t: t[0])]

    def supported(at, want):
        # the record named nearest the word, or Shorts (the window's, or a candidate's) when the sentence is about them
        for o in near(at):
            d = _rec_direction(sheet, o)
            if d is not None:
                return d == want or (want == 0)
            if o.startswith("eras["):
                return True   # eras are in time order: what took over is the later one
        if shorts_said:
            d = _shorts_direction(sheet, slots)
            if d is not None:
                return d == want
        return False

    am = _D_AMOUNT.sub(" ", pl)
    # "more X than Y", "less", "fewer": the two records named, by the sheet's own order (or the comparison's)
    for m in _D_CMP.finditer(am):
        cmpx = sheet.get("comparison") or {}
        tail = am[m.end():m.end() + 80]
        if re.search(r"\b(?:than|que|against|over)\b", tail) or re.match(r"\s+§\d+§", tail):
            a_ = list(dict.fromkeys(o for p, o, n in sorted(owners, key=lambda t: t[0]) if p > m.start()))
            b_ = list(dict.fromkeys(o for p, o, n in sorted(owners, key=lambda t: t[0]) if p < m.start()))
            sides = (a_[:2] if len(a_) >= 2 else (b_[-1:] + a_[:1])) if (a_ or b_) else []
            if any(x.key in ("more", "less", "ratio_words", "difference") for x in slots) and cmpx:
                continue   # the comparison's own paths say which is more
            if len(sides) < 2:
                # "more of it", "Shorts became more of what you opened": a direction against the span before
                if not supported(m.start(), 1 if m.group(0) in ("more", "mas") else -1):
                    return "direction_unbound"
                continue
        elif _same_list_pair(owners, m.start()):
            # "Aug 2026 led, then Sep 2026, with far fewer in Jul 2026": the first one after against the one before
            sides = _same_list_pair(owners, m.start())
        else:
            if not supported(m.start(), 1 if m.group(0) in ("more", "mas") else -1):
                return "direction_unbound"
            continue
        ra, rb = _rec(sheet, sides[0]), _rec(sheet, sides[1])
        va = next((ra[k] for k in ("items", "share") if ra and _num(ra.get(k))), None)
        vb = next((rb[k] for k in ("items", "share") if rb and _num(rb.get(k))), None)
        if va is None or vb is None:
            return "direction_unbound"
        if (m.group(0) in ("more", "mas")) != (va > vb):
            return "direction"
    for m in _D_UP.finditer(pl):
        if m.group(0) in ("became", "become", "becoming") and not re.match(r"\s+(?:more|bigger|larger|the|your|a)\b",
                                                                          pl[m.end():]):
            continue
        if not supported(m.start(), 1):
            return "direction_unbound"
    for m in _D_DOWN.finditer(pl):
        if not supported(m.start(), -1):
            return "direction_unbound"
    for m in _D_SHIFT.finditer(pl):
        # a shift from A to B: A fell and B rose (or the eras' own order)
        win = sorted({(p, o) for p, o, _n in owners if -60 <= p - m.start() <= 80})
        if any(o.startswith("eras[") for _p, o in win):
            continue
        pi = [int(re.match(r"^periods\[(\d+)\]", o).group(1)) for _p, o in win if re.match(r"^periods\[\d+\]", o)]
        if len(pi) >= 2 and pi[0] < pi[-1]:
            continue   # from what led an earlier period to what led a later one: the periods' own order
        if shorts_said and _shorts_direction(sheet, slots) is not None and len(owners) <= 1:
            continue   # "a shift to Shorts" said with the window's Shorts paths: the sign was read above
        ds = [_rec_direction(sheet, o) for _p, o in win]
        if len(ds) >= 2:
            ok_ = ds[0] == -1 and ds[-1] == 1   # from the first one said (it fell) to the last (it rose)
        elif len(ds) == 1:
            away = bool(re.search(r"\baway\b", pl[m.start():max(m.start(), win[0][0])]))
            # "toward X": X rose; "X shifted away", "moved away from X": X fell
            ok_ = ds[0] == (1 if win[0][0] > m.start() and not away else -1)
        else:
            ok_ = False
        if not ok_:
            return "direction_unbound"
    for m in _D_SPREAD.finditer(pl):
        # broader / narrower: the leader of its list lost / gained share against the span before
        lead_ = [o for o in near(m.start(), before=80, after=80) if re.match(r"^(?:areas|themes)\[0\]$", o)]
        d = _rec_direction(sheet, lead_[0]) if lead_ else None
        broad = bool(re.match(r"broader|wider|more varied|more spread|spread out", m.group(0)))
        if d is None or d == 0 or (d == -1) != broad:
            return "direction_unbound"
    for m in _D_PEAK.finditer(pl):
        if not any(x.key in ("peak_period", "peak_share", "peak_label", "peak_items") for x in slots):
            return "direction_unbound"
    return None


def _named_as(sheet, owner, names):
    """The record is named under another path (a saved row's theme said as "{themes[0].name}")."""
    try:
        rec = _resolve(sheet, _path_segs(owner))
    except KeyError:
        return False
    k = _record_name_key(rec) if isinstance(rec, dict) else None
    own = _norm(rec[k]) if k else None
    return bool(own) and any(_norm(n.text) == own for n in names)


def _is_question_topic(sheet, owner):
    """A count's or a first's own topic (topics[k] of the question's topic) is the subject of every sentence of the
    answer: its numbers need not name it again ("They came on {topics[0].days} days")."""
    m = re.match(r"^topics\[(\d+)\]$", owner or "")
    if not m or sheet.get("kind") not in ("count", "first", "last"):
        return False
    try:
        t = (sheet.get("topics") or [])[int(m.group(1))]
    except IndexError:
        return False
    topic = (sheet.get("filters") or {}).get("topic")
    return isinstance(t, dict) and (topic is None or _norm(t.get("name")) == _norm(topic))


def _pct_vals(text, facts=None):
    """The numbers a sentence says: [(value, is a percent)] (years, dates and the digits of names left out)."""
    t = re.sub(_DATE_RX, " ", _norm(text))
    if facts is not None:
        t = re.sub(r"\|[A-Z]\|", " ", facts.names_in(t)[1])
    t = re.sub(r"\b(?:19[89]\d|20\d\d)\b", " ", t)
    out = []
    for m in re.finditer(r"(\d[\d,.]*\d|\d)(?:\s*(%|percent\b|points?\b|puntos?\b)|\s+([a-z]+))?", t):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        out.append((v, True if m.group(2) else (m.group(3) or "")))   # a count keeps the word after it (its unit)
    return out


_UNITS = {"videos", "video", "days", "day", "shorts", "short", "long", "minutes", "channels", "items", "hours"}


def _obs_more(text, answer, sheet, raw, facts):
    """Round 12, pass 2 fix: an observation that says nothing new or nothing at all (None, or why)."""
    low = _norm(text)
    # every number of it was said by the answer, a point either way (judge A, row 4: "89%" right after "88%")
    vals, avals = _pct_vals(text, facts), _pct_vals(answer, facts)
    def same(v, p, w, q):
        if p is True or q is True:
            return p is True and q is True and abs(v - w) <= 1.0
        return v == w and (p == q or p not in _UNITS or q not in _UNITS)
    # round 12, pass 4 (V2, live, row 8: "comedy grew from 9% to 14%" went as a repeat of "comedy (14%) and gaming
    # (10%)"): a move the answer does not say is new, whatever its two numbers
    moved = bool(re.search(r"\bfrom \S*\d", low)) and not re.search(r"\bfrom \S*\d", _norm(answer))
    if vals and avals and not moved and all(any(same(v, p, w, q) for w, q in avals) for v, p in vals):
        return "repeat"
    pv = [v for v, p in vals if p is True]
    if len(pv) >= 2 and not moved and all(any(q is True and abs(v - w) <= 1.0 for w, q in avals) for v in pv):
        return "repeat"   # live, row 7: "Shorts grew from 4% in 2020 to 81% in 2026" right after the answer said it
    # a direction with no number (judge A, row 7: "rose most", "fell from the early years")
    bare = low
    for ph in facts.allowed_phrases:
        bare = bare.replace(_norm(ph).rstrip(", "), " ")
    bare = re.sub(r"\b(?:19|20)\d\d\b", " ", re.sub(_DATE_RX, " ", bare))
    bare = re.sub(r"\|[A-Z]\|", " ", facts.names_in(bare)[1])
    if (_UP.search(low) or _DOWN.search(low) or re.search(r"\bshift\w*|\btowards?\b", low)) \
            and not re.search(r"\d", bare):
        return "vague"   # (live: "gaming gained share while comedy and sports lost ground" against "the 4 weeks before")
    # the answer's own date said again, with nothing else (live: "<its date> is the first <its date> in ...")
    ds, ads = re.findall(_DATE_RX, low), re.findall(_DATE_RX, _norm(answer))
    if ds and (len(ds) != len(set(ds)) or (set(ds) <= set(ads) and not vals) or
               (sheet.get("kind") in ("first", "last") and set(ds) & set(ads))):
        return "repeat"   # (live, row 4, twice: "<its date> is the first <topic> watch date, ...")
    cnts = [v for v, p in _pct_vals(re.sub(r"\b(\d[\d,]*) of (?:the |your |all |all your )?\1\b", " ", low), facts)
            if p is not True and v >= 10]   # ("behind 56 of the 56 X videos" is a whole, said right)
    if len(cnts) != len(set(cnts)):
        return "garbled"   # live, row 4: "90 Shorts made up 90 of 300 videos"
    kind = sheet.get("kind")
    if kind == "day" and re.search(r"\b(?:the )?day before\b|\bel dia anterior\b", low):
        return "filler"   # judge A, row 6: areas that "grew" against the day before, on a 10-video day
    sl = slots_of(raw, shown(sheet), sheet.get("lang") or "en") if isinstance(raw, str) and SLOT.search(raw) else []
    nums = [x for x in sl if isinstance(sl, list) and x.role == _ROLE_NUM] if isinstance(sl, list) else []
    if kind in ("top", "changed", "compare_windows") and nums and \
            all(x.key == "shorts_share" and (x.owner or "").startswith("channels[") for x in nums):
        return "filler"   # judges, rows 1 and 8: one channel's Shorts share says nothing about what he watched
    if kind in ("top", "changed", "compare_windows") and re.search(r"\bshorts?\b", low):
        chs = {" ".join(_words(c.get("name") or "")) for c in sheet.get("channels") or [] if isinstance(c, dict)}
        nm = facts.names_in(low)[0]
        if nm and all(n in chs for n in nm):
            return "filler"   # live, row 1: "X was your top channel and almost all Shorts, while Y leaned less on ..."
    return None


def free_numbers(text, facts):
    """Round 12, pass 2 (T1, strict): a digit typed outside a path, the window's own words, a date or a year."""
    t = SLOT.sub(" ", text)
    t = _norm(t)
    for ph in facts.allowed_phrases:
        t = t.replace(_norm(ph).rstrip(", "), " ")
    t = re.sub(_DATE_RX, " ", t)
    t = re.sub(r"\|[A-Z]\|", " ", facts.names_in(t)[1])   # a name with digits ("Blender 3D") types no number
    t = re.sub(r"\b(?:19[89]\d|20\d\d)\b", " ", t)
    t = re.sub(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)", " ", t)
    t = re.sub(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{4}\b", " ", t)
    return bool(re.search(r"\d", t))


def render(text, sheet, facts, strict=False, unit=None):
    """(the sentence with its paths filled, None) or (None, why). Plain text with no path passes as it is unless
    strict and it types a number."""
    if not isinstance(text, str):
        return None, "empty"
    lang = sheet.get("lang") or "en"
    sl = slots_of(text, sheet, lang)
    if isinstance(sl, str):
        return None, sl
    if strict and free_numbers(text, facts):
        return None, "free_number"
    if strict and _COUNT_WORDS.search(_norm(SLOT.sub(" ", text))):
        return None, "free_number"   # round 12, pass 3 (U1, live: "with four areas rising"): a count typed in words
    if not sl:
        if strict and _D_ANY.search(_D_AMOUNT.sub(" ", _norm(text))):
            return None, "direction_unbound"   # round 12, pass 3 (U1): a direction with no path to support it
        return text, None
    if strict and any(x.role == _ROLE_NUM for x in sl) and typed_names(text, sheet, facts):
        return None, "typed_name"
    us = None
    if unit and unit is not text:
        us = slots_of(unit, sheet, lang)
        us = us if isinstance(us, list) else None
    why = bind_check(text, sheet, sl, facts, unit_slots=us)
    if why:
        return None, why
    plain_ = _norm(SLOT.sub(lambda m: " §" + str([x.start for x in sl].index(m.start())) + "§ ", text))
    if _change_words(plain_, sl) == "no_base":
        # round 12, pass 3 (U7, live: "X fell from 16% to 9%", no base): code says the base period, in the person's
        # words, where the writer left it out; a change "from" a count, or with no base the sheet knows, is dropped
        # (a sheet that names no span before, a made-up one, keeps the sentence as it was)
        base = _base_of(sheet)
        tail_ = text.rstrip()
        m_end = re.search(r"from\s+(\{[^}]+\})\s*[.!]?$", tail_)
        froms = [next((x for x in sl if x.start == m.start(1)), None) for m in re.finditer(r"\bfrom\s+(\{[^}]+\})", text)]
        if base and any(x is not None and x.role == _ROLE_NUM and not (x.key or "").endswith("share") and
                        x.key not in ("faded_from", "grew_from") for x in froms):
            return None, "no_base"   # a change "from" a count ("down 3 points from 980")
        last_v = list(re.finditer(r"\b(?:from|to)\s+\{[^}]+\}", tail_))
        if base and last_v and not m_end and tail_[last_v[-1].end():].strip(" .!"):
            # round 12, pass 3 fix (judge A, "the last 3 months": "...; what would you like to lean into next? against
            # the 67 days before"): the base goes right after the change's last value, never after what follows it
            e_ = last_v[-1].end()
            text = tail_[:e_] + " against " + base + tail_[e_:]
            sl = slots_of(text, sheet, lang)
            if isinstance(sl, str):
                return None, sl
        elif base:
            punct = tail_[-1] if tail_[-1:] in ".!" else "."
            text = tail_.rstrip(".!") + (" in " if m_end else " against ") + base + punct
            sl = slots_of(text, sheet, lang)
            if isinstance(sl, str):
                return None, sl
        span_ = _span_of(sheet)
        mft = re.search(r"\bfrom\s+\{[^}]+\}\s+to\s+\{[^}]+\}", text)
        if not base and span_ and mft:
            # a change over the years (live, row 7: "Gaming faded from 22% to 16%, while ..."): its two years, right
            # after its two values
            text = text[:mft.end()] + f" between {span_[0]} and {span_[1]}" + text[mft.end():]
            sl = slots_of(text, sheet, lang)
            if isinstance(sl, str):
                return None, sl
    out, last = [], 0
    for x in sl:
        out.append(text[last:x.start])
        t_ = x.text
        if x.key == "long_median_min" and re.match(r"^\s*-?\s*(?:min|minut)", text[x.end:x.end + 12], re.I):
            t_ = str(int(x.value))   # live: "{totals.long_median_min} minutes" said "11 minutes minutes"
        out.append(t_)
        last = x.end
        m_ = re.match(r"\s+of (?:everything(?: you opened)?|what you opened|all(?: you opened)?|your window)\b",
                      text[x.end:]) if (x.key == "shorts_share" and x.owner is None) else None
        if m_:   # round 12, pass 2 fix (live: "Shorts made up 79% of everything you opened"): of the YouTube videos
            out.append(" of your YouTube videos")
            last = x.end + m_.end()
    out.append(text[last:])
    r = re.sub(r"\s+", " ", "".join(out)).strip()
    r = re.sub(r"\b(points?|puntos?)\s+(?:points?|puntos?|percentage points?)\b", r"\1", r)
    return r, None


def typed_names(text, sheet, facts):
    """Round 12, pass 2 (T1, strict): the sheet's names typed outside a path (a number next to one could not be
    bound to it): not the question's topic, a period or a word of the window."""
    t = _norm(SLOT.sub(" ", text))
    for ph in facts.allowed_phrases:
        t = t.replace(_norm(ph).rstrip(", "), " ")
    t = re.sub(_DATE_RX, " ", t)
    found = facts.names_in(t)[0]
    topic = " ".join(_words((sheet.get("filters") or {}).get("topic") or ""))
    return [n for n in found if n not in facts.periods and n != topic and n not in facts.topic_keys
            and len(n) >= 3 and n not in ("shorts", "youtube", "instagram")]


def _fact_paths(text, sheet):
    """Round 12, pass 3 (U4): the sheet paths of the numbers a template sentence says (the facts it rests on), the
    window's own words and dates left out; a record's share now is one fact, its share before (or its change) another."""
    if not isinstance(text, str) or not SLOT.search(text):
        return set()
    sl = slots_of(text, sheet, (sheet or {}).get("lang") or "en")
    if not isinstance(sl, list):
        return set()
    out = set()
    for x in sl:
        if x.role != _ROLE_NUM or x.path.startswith("window."):
            continue
        k = x.key or ""
        base = x.owner or x.path.rsplit(".", 1)[0]
        out.add((base, "share" if k in ("share", "to_share") else
                 "change" if k in ("previous_share", "change_vs_previous", "from_share", "change") else k))
    return out


def shorts_left_out(text, sheet):
    """Round 12, pass 3 (U3, live: a "without Shorts" answer said a channel is "almost all Shorts"): with the Shorts
    filtered out, nothing is said about Shorts but that they are left out."""
    if not ((sheet or {}).get("filters") or {}).get("without_shorts"):
        return False
    t = re.sub(r"\b(?:without|leaving out|left out|no|sin)\s+(?:the\s+)?shorts\b|\bshorts\s+(?:left\s+)?out\b", " ",
               _norm(text))
    return bool(re.search(r"\bshorts?\b|\bcortos?\b", t))


def uses_of(text):
    return sorted({_path_segs(m.group(1))[0][0] for m in SLOT.finditer(text or "")})


def check(raw, sheet, chart_vals=None, strict=False):
    """The form checked against the sheet: {"answer", "observations", "so_what", "offers", "dropped": [(where, why)]}.
    The answer is None when it failed. Round 12, pass 2 (T1): every sentence's paths ("{themes[0].share}") are filled
    by code first and their binding checked (`render`); `strict` (the writer's live path, insight_v5) also drops a
    number typed outside a path."""
    s = shown(sheet)
    facts = Facts(s)
    out = {"answer": None, "observations": [], "so_what": None, "offers": [], "dropped": [], "so_what_pick": None}
    if not isinstance(raw, dict):
        out["dropped"].append(("form", "not_a_form", None))
        return out
    ans = raw.get("answer")
    if isinstance(ans, str) and sheet.get("kind") == "day":
        ans = _ONE_DAY_SAID.sub("", ans)
    if isinstance(ans, str) and (SLOT.search(ans) or strict):
        kept = []
        for k, sent in enumerate(_sentences(ans)):
            r, why = render(sent, s, facts, strict, unit=ans)
            if why:
                out["dropped"].append(("answer" if k == 0 else "answer_tail", why, sent))
                break
            kept.append(r)
        ans = " ".join(kept) if kept else None
        ans_slotted = True
    else:
        ans_slotted = False
    if isinstance(ans, str) and sheet.get("kind") == "day":
        ans = _ONE_DAY_SAID.sub("", ans)   # round 12, fix: a day's "on 1 day" is left out, not the whole answer
    if isinstance(ans, str) and len(ans) > ANSWER_MAX and len(_sentences(ans)) > 1 and \
            len(_sentences(ans)[0]) <= SENT_MAX:
        out["dropped"].append(("answer_tail", "too_long", " ".join(_sentences(ans)[1:])))
        ans = _sentences(ans)[0]   # round 12, fix (live, Spanish): a long answer's first sentence may stand
    if isinstance(ans, str) and ans.strip() and len(ans) <= ANSWER_MAX:
        sents = _sentences(ans)
        facts.slotted = ans_slotted
        why, n = _check(" ".join(sents), facts, maxlen=ANSWER_MAX)   # one piece: "it" in the second is the first's
        if why is None and n == 0:
            why = "generic"   # an answer that names nothing of the sheet answers nothing
        if why is None and n_numbers(" ".join(sents), facts) > NUMBERS_MAX:
            why = "number_run"   # round 12, fix (judge, Q5: 7 numbers in two sentences): data, not an insight
        if why is None:
            why = answer_shape(sheet, facts, " ".join(sents))
        if why and len(sents) > 1:
            w1, n1 = _check(sents[0], facts)
            if w1 is None and n_numbers(sents[0], facts) > NUMBERS_MAX:
                w1 = "number_run"
            if w1 is None:
                w1 = answer_shape(sheet, facts, sents[0])
            if w1 is None and n1:   # the first sentence answers; a later one that fails is left out
                out["dropped"].append(("answer_tail", why, " ".join(sents[1:])))
                sents, why = sents[:1], None
        if not why and sents and shorts_left_out(" ".join(sents), sheet):
            why = "shorts_left_out"
        if sents and not why and len(sents) <= 3:
            out["answer"] = _unit_before(tidy(" ".join(sents), facts.lang), sheet)
        else:
            out["dropped"].append(("answer", why or "shape", ans))
    else:
        out["dropped"].append(("answer", "missing" if not ans else "too_long", ans))
    obs = raw.get("observations") if isinstance(raw.get("observations"), list) else []
    seen = set()
    said_paths = [_fact_paths(raw.get("answer"), s)] if out["answer"] and isinstance(raw.get("answer"), str) else []
    said = _signature(out["answer"] or "", facts)
    for o in obs[:OBS_MAX + 2]:
        text, uses = (o.get("text"), o.get("uses")) if isinstance(o, dict) else (o, None)
        if not isinstance(text, str):
            continue
        raw_obs = text
        if sheet.get("kind") == "day":
            text = _ONE_DAY_SAID.sub("", text)
        slotted = bool(SLOT.search(text))
        if SLOT.search(text) or strict:
            u = uses_of(text)
            text, why = render(text, s, facts, strict)
            if why:
                out["dropped"].append(("observation", why, o.get("text") if isinstance(o, dict) else o))
                continue
            uses = sorted(set(u) | set(uses if isinstance(uses, list) else []))
        if sheet.get("kind") == "day":
            text = _ONE_DAY_SAID.sub("", text)
        sents = _sentences(text)
        why = None if len(sents) == 1 else "two_sentences"
        facts.slotted = slotted
        if not why and (text.strip().endswith("?") or re.search(r"[,;:]\s*[?.!]?\s*$", text.strip())):
            why = "unfinished"   # round 12, fix (live, Spanish: "... suman 4,?"): an observation says, never asks
        why = why or check_sentence(text, facts, uses=uses if uses is not None else [], chart_vals=chart_vals)
        if not why and shorts_left_out(text, sheet):
            why = "shorts_left_out"
        if not why and n_numbers(text, facts) > NUMBERS_MAX:
            why = "number_run"
        key = " ".join(_words(text))
        if not why and key in seen:
            why = "repeat"
        if not why and out["answer"] and key == " ".join(_words(out["answer"])):
            why = "repeat"
        sig = _signature(text, facts)
        if not why and sig and sig <= said:
            why = "repeat"   # nothing new: every number and name of it was said above
        if not why and slotted:
            # round 12, pass 3 (U4, live, row 1: the first bullet said the lead again): two sentences that rest on the
            # same sheet paths are a repeat; the first stands
            mine = _fact_paths(raw_obs, s)
            if mine and any(mine <= other for other in said_paths):
                why = "repeat"
        if not why:
            why = _obs_more(text, out["answer"] or "", sheet, raw_obs, facts)
        if not why and sum(1 for n in facts.names_in(text)[0] if len(n) >= 3 and len(re.findall(
                r"(?<![a-z0-9])" + re.escape(n) + r"(?![a-z0-9])", _norm(text))) >= 2) >= 2:
            why = "filler"   # round 12, pass 3 (U4, live, row 6: "A and B were new that day; A and B were also ...")
        if not why and re.search(r"\b(?:while|whereas|but|and)\b", _norm(text)) and any(
                len(re.findall(r"(?<![a-z0-9])" + re.escape(n) + r"(?![a-z0-9])", _norm(text))) >= 2
                for n in facts.names_in(text)[0] if len(n) >= 4):
            # live: "2020 was led by gaming, while 2026 was led by gaming": one name on both sides says nothing
            if not re.search(r"\d", re.sub(r"\b(?:19|20)\d\d\b", " ", text)):
                why = "filler"
        said |= sig
        if why:
            out["dropped"].append(("observation", why, text))
            continue
        seen.add(key)
        if slotted:
            said_paths.append(_fact_paths(raw_obs, s))
        out["observations"].append(_unit_before(tidy(" ".join(text.split()), facts.lang), sheet))
    out["observations"] = out["observations"][:OBS_MAX]
    facts.slotted = False
    sw = raw.get("so_what")
    if isinstance(sw, dict):   # round 12, pass 2 (T5): {"pick": a candidate's id, "text": its words}
        out["so_what_pick"] = sw.get("pick") if isinstance(sw.get("pick"), str) else None
        sw = sw.get("text")
    if isinstance(sw, str) and sw.strip() and (SLOT.search(sw) or strict):
        r, why = render(sw, s, facts, strict)
        if why:
            out["dropped"].append(("so_what", why, sw))
            sw = None
        else:
            sw = r
    if isinstance(sw, str) and sw.strip():
        why = check_sentence(sw, facts) if len(_sentences(sw)) <= 2 else "too_long"
        if not why and shorts_left_out(sw, sheet):
            why = "shorts_left_out"
        if not why and re.search(r"\bonly\b|\bwithout shorts\b|\bby (?:month|theme)\b|\bsolo\b|\bsin shorts\b|"
                                 r"\bcloser look\b", _norm(sw)) and not re.search(r"\bsaved\b|\bguard", _norm(sw)):
            why = "offer_repeat"   # the offers line says it
        if why:
            out["dropped"].append(("so_what", why, sw))
        else:
            out["so_what"] = tidy(" ".join(sw.split()), facts.lang)
    offers = sheet.get("offers") or []
    for x in raw.get("offers") or []:
        if isinstance(x, str) and x in offers and x not in out["offers"]:
            out["offers"].append(x)
    out["offers"] = out["offers"][:OFFERS_MAX]
    return out


# ====================================== the chart (code only) ====================================================
def bar(v, top, cells=BAR_CELLS):
    """A bar of whole block characters, always `cells` wide (the empty part in light shade), so the labels after it
    line up. Whole cells only: the partial blocks (▏▎▍) come from another font on a phone and leave gaps (seen in the
    page's bubble at 430 px)."""
    if top <= 0:
        return "░" * cells
    n = int(round(max(0.0, min(1.0, v / top)) * cells))
    if v > 0 and n == 0:
        n = 1
    return "█" * n + "░" * (cells - n)


def _fmt(n, lang):
    s = f"{int(n):,}"
    return s.replace(",", ".") if lang == "es" else s


def _label_words(s, n):
    """A label cut at a word ("Watercolor painting…", not "Watercolor paint…")."""
    s = " ".join(str(s or "").split())
    if len(s) <= n:
        return s
    cut = s[:n - 1]
    if s[n - 1] != " " and " " in cut:   # round 12, pass 2: a whole last word that fits stays
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:-") + "…"


def _label(s, n=LABEL_MAX):
    return _label_words(s, n)   # round 12, fix: cut at a word, never inside one


CAPTIONS = {
    "themes": {"en": "Share of what you opened, by theme:", "es": "Parte de lo que abriste, por tema:"},
    "areas": {"en": "Share of what you opened, by area:", "es": "Parte de lo que abriste, por área:"},
    "shorts_periods": {"en": "Shorts' share of your YouTube videos, by {unit}:",
                       "es": "La parte de Shorts en tus videos de YouTube, por {unit}:"},
    "era_periods": {"en": "The main area each {unit} (the bar: its share of that {unit}):",
                    "es": "El área principal de cada {unit} (la barra: su parte de ese {unit}):"},
    "lead_area_periods": {"en": "The share of {area} in each {unit}:", "es": "La parte de {area} en cada {unit}:"},
    "channels": {"en": "Videos opened, by channel:", "es": "Videos abiertos, por canal:"},
    "periods": {"en": "Videos opened per {unit} (the bar) and the main theme:",
                "es": "Videos abiertos por {unit} (la barra) y el tema principal:"},
    "periods_plain": {"en": "Videos opened per {unit}:", "es": "Videos abiertos por {unit}:"},
    "topics": {"en": "Videos opened, by topic:", "es": "Videos abiertos, por tema:"},
    "topics_then": {"en": "Videos opened, by topic, against {then}:", "es": "Videos abiertos, por tema, frente a {then}:"},
    "windows": {"en": "Videos opened:", "es": "Videos abiertos:"},
}
CHART_KINDS = {"top": ("areas", "themes", "channels"), "channels": ("channels",), "count": ("periods", "topics"),
               "changed": ("era_periods", "periods", "themes"), "compare_windows": ("windows", "themes"),
               "compare_topics": ("topics", "themes")}


def chart(sheet, level=None):
    """(text, values shown) of the small chart for the sheet's kind, or (None, set()). At most 8 rows and one caption;
    each row is a bar of the same width, then its number, then its label. `level` (round 12, pass 3, U3): the level
    the answer leads with ("areas" or "themes"): the chart is drawn at the same level."""
    kind = sheet.get("kind")
    lang = sheet.get("lang") or "en"
    for src in CHART_KINDS.get(kind, ()):
        if level == "themes" and src == "areas":
            continue
        if level == "areas" and src == "areas" and kind == "top":
            ts = [t for t in sheet.get("areas") or [] if isinstance(t, dict) and _num(t.get("share")) and t.get("name")]
            if len(ts) >= 2:   # the answer leads with the areas: so does the chart, whatever they cover
                rows = [(f"{round(t['share'] * 100)}%", t["share"], t["name"], round(t["share"] * 100))
                        for t in ts[:CHART_ROWS]]
                top = max(v for _, v, _, _ in rows) or 1
                lines = [CAPTIONS["areas"][lang]] + [f"{bar(v, top)} {left} {_label(right)}".rstrip()
                                                     for left, v, right, _ in rows]
                return "\n".join(lines), {x for *_, x in rows}
        cap, rows = _rows(sheet, src, lang)
        if len(rows) >= 2:
            top = max(v for _, v, _, _ in rows) or 1
            lines = [cap] + [f"{bar(v, top)} {left} {_label(right)}".rstrip() for left, v, right, _ in rows]
            return "\n".join(lines), {x for *_, x in rows}
    return None, set()


def _rows(sheet, src, lang):
    """(caption, [(left text, value, right text, the number the row shows)])."""
    if src in ("themes", "areas"):
        ts = [t for t in sheet.get(src) or [] if isinstance(t, dict) and _num(t.get("share")) and t.get("name")]
        if src == "areas" and sum(t["share"] for t in ts) < 0.4:
            return "", []   # the areas cover too little of the window to be its picture
        return CAPTIONS[src][lang], [(f"{round(t['share'] * 100)}%", t["share"], t["name"],
                                      round(t["share"] * 100)) for t in ts[:CHART_ROWS]]
    if src == "era_periods":   # round 12, pass 2 (T4): one measure, the leading area's share of each period
        ps = [p for p in sheet.get("periods") or [] if isinstance(p, dict) and p.get("label") and p.get("areas")
              and not p.get("sparse")][-PERIOD_ROWS:]
        if len(ps) < 2:
            return "", []
        unit = ("mes" if lang == "es" else "month") if re.search(r"[A-Za-z]", str(ps[0]["label"])) else \
            ("año" if lang == "es" else "year")
        if len({p["areas"][0]["name"] for p in ps}) == 1:
            vals = [p["areas"][0]["share"] for p in ps if _num(p["areas"][0].get("share"))]
            if len(vals) == len(ps) and len(vals) >= 3 and max(vals) >= 1.4 * min(vals):   # (Spanish too, pass 3 fix)
                # round 12, pass 3 (U8, row 7): one area led every period but its weight moved: the bar is its share
                # of each period (the answer says the same)
                return CAPTIONS["lead_area_periods"][lang].format(unit=unit, area=ps[0]["areas"][0]["name"]), [
                    (str(p["label"]), p["areas"][0]["share"], f"{round(p['areas'][0]['share'] * 100)}%",
                     round(p["areas"][0]["share"] * 100)) for p in ps]
            # one area led every period: the bar would say nothing; the move between Shorts and long videos does
            sp = [p for p in ps if _num(p.get("shorts_share"))]
            if len(sp) >= 2:
                return CAPTIONS["shorts_periods"][lang].format(unit=unit), [
                    (str(p["label"]), p["shorts_share"], f"{round(p['shorts_share'] * 100)}%",
                     round(p["shorts_share"] * 100)) for p in sp]
        return CAPTIONS["era_periods"][lang].format(unit=unit), [
            (str(p["label"]), p["areas"][0]["share"], _label_words(p["areas"][0]["name"], PERIOD_LABEL_MAX),
             round(p["areas"][0]["share"] * 100)) for p in ps]
    if src == "topics" and sheet.get("kind") == "compare_topics":
        # round 12, pass 3 fix (judge A, row 5: two bars that repeat the answer's two numbers): each side now and in the
        # span before, which the answer does not draw
        xs = [c for c in sheet.get("topics") or [] if isinstance(c, dict) and _num(c.get("items")) and c.get("name")
              and _num(c.get("previous_items"))][:2]
        pv = sheet.get("previous") or {}
        w = sheet.get("window") or {}
        y0 = (re.findall(r"\b((?:19|20)\d\d)\b", str(pv.get("words") or "")) or [""])[-1]
        y1 = str(w.get("start") or "")[:4]
        if len(xs) == 2 and re.match(r"^\d{4}$", y0) and re.match(r"^\d{4}$", y1) and y0 != y1:
            then = re.sub(r"\s*\([^)]*\)\s*$", "", str(pv.get("words") or "")).strip() or y0
            rows = []
            for c in xs:
                rows += [(_fmt(c["items"], lang), c["items"], f"{c['name']} {y1}", c["items"]),
                         (_fmt(c["previous_items"], lang), c["previous_items"], f"{c['name']} {y0}",
                          c["previous_items"])]
            return CAPTIONS["topics_then"][lang].format(then=then), rows
    if src in ("channels", "topics"):
        xs = [c for c in sheet.get(src) or [] if isinstance(c, dict) and _num(c.get("items")) and c.get("name")]
        return CAPTIONS[src][lang], [(_fmt(c["items"], lang), c["items"], c["name"], c["items"])
                                     for c in xs[:CHART_ROWS]]
    if src == "periods":
        ps = [p for p in sheet.get("periods") or [] if isinstance(p, dict) and _num(p.get("items")) and p.get("label")]
        if not ps:
            return "", []
        cut = len(ps) > PERIOD_ROWS   # round 12, fix: a year by month is all 12 rows, never its oldest cut
        ps = ps[-PERIOD_ROWS:]
        unit = ("mes" if lang == "es" else "month") if re.search(r"[A-Za-z]", str(ps[0]["label"])) else \
            ("año" if lang == "es" else "year")
        names_ = [((p.get("themes") or [{}])[0] or {}).get("name") for p in ps if p.get("themes")]
        tops = set(names_)
        # one main theme in every row (or in most: round 12, pass 2, live) says nothing per row: the counts instead
        common = max((names_.count(n) for n in tops), default=0)
        has_theme = any(p.get("themes") for p in ps) and len(tops) > 1 and common < 0.7 * len(ps)
        cap = CAPTIONS["periods" if has_theme else "periods_plain"][lang].format(unit=unit)
        rows = []
        for p in ps:
            th = (p.get("themes") or [{}])[0]
            name = th.get("name") if isinstance(th, dict) else None
            # with a theme the row says the period and its main theme (the bar is the count): it fits a phone
            right = (_label_words(name, PERIOD_LABEL_MAX) if name else "") if has_theme else _fmt(p["items"], lang)
            rows.append((str(p["label"]), p["items"], right, p["items"]))
        if cut:
            cap = cap.rstrip(":") + (f" (los últimos {PERIOD_ROWS}):" if lang == "es" else f" (the last {PERIOD_ROWS}):")
        tp0 = (sheet.get("topics") or [{}])[0] if sheet.get("kind") == "count" and sheet.get("topics") else {}
        lead_n = (tp0 or {}).get("items") if _num((tp0 or {}).get("items")) else (sheet.get("totals") or {}).get("items")
        if not cut and _num(lead_n) and sum(r[1] for r in rows) > lead_n:
            # round 12, pass 3 (U9, row 3: the bars added up to more than the answer's count): what the bars count
            cap = cap.rstrip(":") + (" (un video abierto en dos meses cuenta en los dos):" if lang == "es" else
                                     " (a video opened in two months counts in both):")
        return cap, rows
    if src == "windows":
        tot, prev = sheet.get("totals") or {}, sheet.get("previous") or {}
        if not (_num(tot.get("items")) and _num(prev.get("items"))):
            return "", []
        w = sheet.get("window") or {}
        la = w.get("label") or w.get("words") or ""
        lb = prev.get("label") or prev.get("words") or ""
        if not la or not lb:
            return "", []
        return CAPTIONS["windows"][lang], [(_strip_in(lb) + ":", prev["items"], _fmt(prev["items"], lang), prev["items"]),
                                           (_strip_in(la) + ":", tot["items"], _fmt(tot["items"], lang), tot["items"])]
    return "", []


def _strip_in(s):
    return re.sub(r"^(?:in|en)\s+", "", str(s).strip().rstrip(","), flags=re.I)


# ====================================== offers (texts only; builder D reads what the person says) =================
OFFER_WORDS = {
    "without_shorts": {"en": "without Shorts", "es": "sin Shorts"},
    "only_topic": {"en": "only {topic}", "es": "solo {topic}"},
    "show_videos": {"en": "with the videos", "es": "con los videos"},
    "by_month": {"en": "by month", "es": "por mes"},
    "by_theme": {"en": "by theme", "es": "por tema"},
}
# the reply's first line when the person takes an offer
TAKEN = {
    "without_shorts": {"en": "Without Shorts:", "es": "Sin Shorts:"},
    "only_topic": {"en": "Only {topic}:", "es": "Solo {topic}:"},
    "show_videos": {"en": "The videos:", "es": "Los videos:"},
    "by_month": {"en": "By month:", "es": "Por mes:"},
    "by_theme": {"en": "By theme:", "es": "Por tema:"},
}
# what is said when taking an offer leaves nothing
TAKEN_EMPTY = {
    "without_shorts": {"en": "Without Shorts there is nothing left in {window}.",
                       "es": "Sin Shorts no queda nada en {window}."},
    "only_topic": {"en": "Nothing on {topic} in {window}.", "es": "Nada de {topic} en {window}."},
}


def _offer_key(o):
    k, _, arg = str(o).partition(":")
    return k, arg


def offer_phrase(o, lang="en"):
    k, arg = _offer_key(o)
    w = OFFER_WORDS.get(k)
    if not w:
        return None
    if k == "only_topic" and not arg.strip():
        return None
    return w["es" if lang == "es" else "en"].format(topic=arg.strip())


def offers_shown(sheet, chosen=None):
    """The offers the line says (round 12, merge): the model's checked pick, else the sheet's first two; at most 3."""
    allowed = [o for o in (sheet or {}).get("offers") or [] if isinstance(o, str)]
    picks = [o for o in (chosen or []) if o in allowed] or allowed[:2]
    return [o for o in picks[:OFFERS_MAX] if offer_phrase(o)]


def offers_fit(sheet, chosen, said, chart_text=None):
    """Round 12, pass 3 (U6, live: row 1 offered two themes it never showed): only what the answer showed is offered
    (its areas, then its themes), "without Shorts" where Shorts are in it, and nothing the chart already gives ("by
    month" under a chart by month). The model's checked pick first, then the sheet's own; at most two."""
    allowed = [o for o in (sheet or {}).get("offers") or [] if isinstance(o, str) and offer_phrase(o)]
    said_n = " " + " ".join(_words(said or "")) + " "
    per_month = bool(chart_text and re.search(r"\bper month\b|\bby month\b|\bpor mes\b", chart_text))
    areas = {" ".join(_words(a.get("name") or "")) for a in (sheet or {}).get("areas") or [] if isinstance(a, dict)}

    kind = (sheet or {}).get("kind")
    sizes = {}
    for key in ("areas", "themes", "channels"):
        for r in (sheet or {}).get(key) or []:
            if isinstance(r, dict) and r.get("name") and _num(r.get("items")):
                sizes.setdefault(" ".join(_words(r["name"])), r["items"])
            for t in (r.get("themes") or []) if isinstance(r, dict) else []:
                if isinstance(t, dict) and t.get("name") and _num(t.get("items")):
                    sizes.setdefault(" ".join(_words(t["name"])), t["items"])

    def fits(o):
        k, arg = _offer_key(o)
        if k == "only_topic":
            # round 12, pass 4 (V5, live: "only Relatable memes" under a day where it was 3 videos): never a handful
            n = sizes.get(" ".join(_words(arg)))
            return (" " + " ".join(_words(arg)) + " ") in said_n and not (_num(n) and n < OFFER_MIN_ITEMS)
        if kind in ("first", "last") and k in ("by_month", "show_videos"):
            return False   # round 12, pass 4 (V5): a first or a last shows its videos and its path already
        if k == "by_month":
            return not per_month
        return True
    picks = [o for o in (chosen or []) if o in allowed and fits(o)]
    rest = [o for o in allowed if o not in picks and fits(o)]
    # an area before a theme (the answer leads with its areas)
    rest.sort(key=lambda o: (0 if _offer_key(o)[0] == "without_shorts" else
                             1 if _offer_key(o)[0] == "only_topic" and " ".join(_words(_offer_key(o)[1])) in areas
                             else 2 if _offer_key(o)[0] == "only_topic" else 3))
    return (picks or rest)[:2]


def offers_line(sheet, chosen=None, lang=None):
    """One line of follow-ups in words a person would type: 'Want it without Shorts, only cooking, or by month?'.
    `chosen` (the model's pick, checked) falls back to the sheet's first offers; only the sheet's offers are said."""
    lang = lang or (sheet or {}).get("lang") or "en"
    phrases = []
    for o in offers_shown(sheet, chosen):
        p = offer_phrase(o, lang)
        if p and p not in phrases:
            phrases.append(p)
    if not phrases:
        return ""
    if lang == "es":
        body = phrases[0] if len(phrases) == 1 else ", ".join(phrases[:-1]) + " o " + phrases[-1]
        return f"¿Lo quieres {body}?"
    body = phrases[0] if len(phrases) == 1 else (" or ".join(phrases) if len(phrases) == 2 else
                                                 ", ".join(phrases[:-1]) + ", or " + phrases[-1])
    return f"Want it {body}?"


def taken_line(offer, lang="en", window=""):
    """The first line of the reply when the person takes an offer ('Without Shorts:', 'Only cooking:')."""
    k, arg = _offer_key(offer)
    t = TAKEN.get(k)
    return t["es" if lang == "es" else "en"].format(topic=arg.strip(), window=window) if t else ""


def taken_empty(offer, lang="en", window=""):
    k, arg = _offer_key(offer)
    t = TAKEN_EMPTY.get(k)
    return t["es" if lang == "es" else "en"].format(topic=arg.strip(), window=window) if t else ""


# ====================================== layout (code only) =======================================================
ITEM_KINDS = ("day", "first", "last")
REFRESH_SHORT = {"en": "For anything newer, send me a new export (ask \"how do I send you a new export?\").",
                 "es": "Para ver algo más nuevo, mándame una exportación nueva (escribe \"how do I send you a new "
                       "export?\")."}
FRIENDS_ASK = re.compile(r"\bfriends?\b|\bamig[oa]s?\b", re.I)
FRIENDS_LINE = {"en": "Posts from friends are not counted.", "es": "No cuento las publicaciones de tus amigos."}


def _item_line(k, it, lang, year=None):
    title = " ".join(str(it.get("title") or "").split())[:90] or ("Un video" if lang == "es" else "A video")
    ch = it.get("channel")
    d = _as_date(it.get("at"))
    bits = []
    if d:
        bits.append(f"{d.day} {(MONTHS_ES if lang == 'es' else MONTHS)[d.month - 1][:3].capitalize()}"
                    + (f" {d.year}" if year and d.year != year else ""))   # round 12, merge: a first in 2020
    if _num(it.get("length_s")) and it["length_s"] > 0:
        mins = int(round(it["length_s"] / 60))
        bits.append(f"{mins} min" if mins >= 1 else f"{int(it['length_s'])} s")
    if it.get("is_short"):
        bits.append("Short")
    by = (f" de {ch}" if lang == "es" else f" by {ch}") if ch else ""
    return f"{k}. {_clip(title)}{_clip(by)}" + (f" ({', '.join(bits)})" if bits else "")


def item_caption(k, it, lang="en", year=None, day=False):
    """Round 12, pass 3 (U4): a card's one caption line: its number, the channel, the day, the length ("2. Pixel
    Pencil · 30 Oct · 25 min"); the title is the card's own."""
    bits = [f"{k}."]
    if it.get("channel"):
        bits.append(_clip(" ".join(str(it["channel"]).split())[:60]))
    d = _as_date(it.get("at"))
    if d and not day:   # a day's cards are all that day (the overview says it)
        bits.append(f"{d.day} {(MONTHS_ES if lang == 'es' else MONTHS)[d.month - 1][:3].capitalize()}"
                    + (f" {d.year}" if year and d.year != year else ""))
    if _num(it.get("length_s")) and it["length_s"] > 0:
        mins = int(round(it["length_s"] / 60))
        bits.append(f"{mins} min" if mins >= 1 else f"{int(it['length_s'])} s")
    if it.get("is_short"):
        bits.append("Short")
    return bits[0] + " " + " · ".join(bits[1:]) if len(bits) > 1 else bits[0]


def window_lead(answer, sheet):
    """The answer begins with the window's words when the window is not all time (they carry where the record
    ends); code adds them when the model left them out: for a window that passes an export end, when the answer does
    not say the end's date; otherwise when it does not say the window."""
    w = (sheet.get("window") or {}).get("words") or ""
    if not w or not answer:
        return answer
    a = _norm(answer)
    if (sheet.get("window") or {}).get("clipped"):
        end = _as_date((sheet.get("window") or {}).get("end"))
        days = _days_in(w)
        need = [f"{d} {MONTHS[m - 1]}" for m, d in days] + [f"{MONTHS[m - 1]} {d}" for m, d in days]
        if end:
            need += [f"{end.day} {MONTHS[end.month - 1]}", f"{MONTHS[end.month - 1]} {end.day}",
                     f"{end.day} de {MONTHS_ES[end.month - 1]}"]
        need += [f"{d} de {MONTHS_ES[m - 1]}" for m, d in days]
        if not need or any(x in a for x in need) or re.search(r"export ends|termina tu exportacion", a):
            return answer
    else:
        core = re.split(r"[(,]", _norm(w))[0].strip()
        core = re.sub(r"^(?:in|en|on|el|since|desde|from|del)\s+", "", core)
        if not core or core in a:
            return answer
    lead = w.strip().rstrip(",")
    said = re.split(r"[(,]", w)[0].strip()
    if said and a.startswith(_norm(said)) and len(said) < len(lead):
        # the answer opens with the window's first words only ("Since 2020 you ..."): the full words take their place
        rest = answer[len(said):].lstrip(" ,")
        return lead[:1].upper() + lead[1:] + ", " + rest
    first = answer.split(" ", 1)[0]
    keep = first in ("I", "YouTube", "Instagram") or any(
        e.split()[0] == _norm(first).strip(",.") for e in Facts(shown(sheet)).entities)
    if keep and any(str(a.get("name") or "")[:1].islower() and _norm(a["name"]).split()[:1] == [_norm(first).strip(",.")]
                    for a in sheet.get("areas") or [] if isinstance(a, dict) and a.get("name")):
        keep = False   # round 12, pass 2 fix (judge A: a capital "Gaming" mid-sentence): an area is a common word
    return lead[:1].upper() + lead[1:] + ", " + (answer if keep else answer[:1].lower() + answer[1:])


def _no_title_twice(answer, sheet):
    """Round 12, fix (judge, Q4): a first's or a last's answer that names the first item's title says it once, in
    the list below it: the title (in quotes or not, with "by <channel>") becomes "(1 below)"."""
    if sheet.get("kind") not in ("first", "last") or not answer:
        return answer
    it = next((x for x in sheet.get("items") or [] if isinstance(x, dict) and x.get("title")), None)
    if not it:
        return answer
    title = " ".join(str(it["title"]).split())
    for t in (title, _clip(title)):
        rx = r"[\"“'‘]?" + re.escape(t) + r"[\"”'’]?" + (r"(?:\s+(?:by|de)\s+" + re.escape(str(it.get("channel") or "")) + r")?"
                                                          if it.get("channel") else "")
        m = re.search(rx, answer)
        if m:
            pre = re.sub(r"(?:,?\s+(?:with|watching|starting with|from|on|by opening|opening)|\s*[:,])\s*$", "",
                         answer[:m.start()].rstrip())
            out = pre + (" (the first video below)" if pre.strip() else "The first video below") + answer[m.end():]
            return re.sub(r"\s+([.,;])", r"\1", out)
    return answer


def scoped(text, sheet, answer=False):
    """Round 12, pass 2 (live): in a topic's answer a share is of the topic's videos, never "of what you opened"
    (it read as 89% of everything); a count with themes in it (T8) is said with "about"."""
    if not text:
        return text
    if sheet.get("kind") == "day":   # live: "2 channels were new today" of a day in October
        text = re.sub(r"\btoday\b", "that day", text)
    text = re.sub(r"\b(started watching \w+|first opened \w+(?: videos?)?) in (\d{1,2} [A-Z][a-z]+ \d{4})", r"\1 on \2",
                  text)   # live: "you first started watching blender in 11 April 2020"
    topic = (sheet.get("filters") or {}).get("topic")
    if (sheet.get("lang") or "en") == "en":
        # round 12, pass 4 (V1, live: "440 Shorts made up 22% of your YouTube videos" on "most watched channels in
        # math", 440 and 22% of the math videos): a filtered sheet's shares and counts are said with its own base,
        # whatever the kind and whoever wrote the sentence
        text = based(text, sheet)
    if topic and sheet.get("kind") in ("count", "first", "last") and (sheet.get("lang") or "en") == "en":
        # round 12, pass 3 (U9): "N% of them were Shorts" says whose
        text = re.sub(r"\b(\d[\d.,]*%) of (?:them|those|these)( were (?:YouTube )?Shorts)\b",
                      lambda m: f"{m.group(1)} of your {topic} videos{m.group(2)}", text)
    tp = (sheet.get("topics") or [{}])[0] if sheet.get("topics") else {}
    if answer and sheet.get("kind") == "count" and "themes" in str((tp or {}).get("matched_by") or "") and \
            _num((tp or {}).get("items")):
        n = _fmt(tp["items"], sheet.get("lang") or "en")
        if (sheet.get("lang") or "en") == "en":
            # round 12, pass 3 fix (judge A, row 3: "about 1,094" on a number code counted reads as a guess): the count
            # as counted, with what it counts
            # round 12, pass 4 (V6: "1,094 minecraft videos (by their titles and themes)" still read as a guess): it
            # says what it counts, "1,094 videos whose title or theme is about minecraft"
            text = re.sub(r"\b(?:[Aa]bout|[Aa]round|[Rr]oughly) (" + re.escape(n) + r")(?![\w,.])", r"\1", text)
            tw = " ".join(_words(topic or tp.get("name") or ""))
            m = re.search(r"(?<![\w,.])" + re.escape(n) + r"((?: [\w'-]+){0,3}?) videos\b", text)
            if m and tw:
                mid = " ".join(w for w in m.group(1).split() if " ".join(_words(w)) not in tw.split())
                what = f" whose title or theme is about {topic or tp.get('name')}"
                if what not in text:
                    return text[:m.start()] + n + (" " + mid if mid else "") + " videos" + what + text[m.end():]
                return text
        text = re.sub(r"(?<![\w,.])(?<![Aa]bout )(?<![Aa]round )(?<![Uu]nos )" + re.escape(n) + r"(?![\w,.])",
                      ("unos " if sheet.get("lang") == "es" else "about ") + n, text, count=1)
    return text


def bases(sheet):
    """Round 12, pass 4 (V1): the words a filtered sheet's shares and counts are of, or None when the sheet is not
    filtered: {"opened": of what (a share of everything the sheet counts), "yt": of what (its YouTube videos, the base
    of a Shorts share), "videos": what one of its videos is called ("math videos"), "day_yt": a day's YouTube videos}.
    A topic (an area or a theme too: "only gaming"), a channel, "without Shorts" and one platform each give their own."""
    f = (sheet or {}).get("filters") or {}
    if (sheet or {}).get("kind") == "compare_topics":
        return None   # each side is said by its own name
    topic, chan, ws, plat = f.get("topic"), f.get("channel"), bool(f.get("without_shorts")), f.get("platform")
    if not (topic or chan or ws or plat in ("youtube", "instagram")):
        return None
    lo = "long " if ws else ""
    if topic:
        return {"opened": f"your {lo}{topic} videos", "yt": f"your {lo}{topic} videos on YouTube",
                "videos": f"{lo}{topic} videos", "day_yt": f"the day's {lo}{topic} videos on YouTube"}
    if chan:
        return {"opened": f"the {lo}videos you opened from {chan}", "yt": f"your {lo}videos from {chan}",
                "videos": f"{lo}videos from {chan}", "day_yt": f"the day's {lo}videos from {chan}"}
    if ws:
        return {"opened": "your long videos", "yt": "your long videos", "videos": "long videos",
                "day_yt": "the day's long videos"}
    if plat == "instagram":
        return {"opened": "what you opened on Instagram", "yt": None, "videos": "posts", "day_yt": None}
    return {"opened": "your YouTube videos", "yt": "your YouTube videos", "videos": "YouTube videos",
            "day_yt": "the day's YouTube videos"}


_BASE_OPENED = re.compile(r"\bof (?:what you (?:opened|watched)|everything(?: (?:else )?you (?:opened|watched))?|"
                          r"the window|your window|all (?:that )?you (?:opened|watched)|all (?:of )?your videos|"
                          r"your viewing|your watching|all videos|your videos(?! (?:on|from)\b))(?! (?:from|on) )\b")
_BASE_YT = re.compile(r"\bof (?:all )?(?:(?:your|the) )?YouTube videos(?: (?:you )?(?:watched|opened))?\b(?! (?:from|on) )")
_BASE_DAY = re.compile(r"\bof the day's YouTube videos\b")
_BASE_CAPS = {"Share of what you opened": "Share of {opened}", "Shorts' share of your YouTube videos": "Shorts' share "
              "of {yt}", "Videos opened": "{Videos} opened"}


def based(text, sheet):
    """Round 12, pass 4 (V1): `text` with every share and count of a filtered sheet said of its own base ("of your
    math videos", "of the videos you opened from <channel>"), never "of your YouTube videos" or "of what you opened"
    (both read as everything he opened). Unfiltered, the text as it is."""
    b = bases(sheet)
    if not text or not b:
        return text
    if b.get("day_yt"):
        text = _BASE_DAY.sub("of " + b["day_yt"], text)
    if b.get("yt"):
        text = _BASE_YT.sub("of " + b["yt"], text)
    return _BASE_OPENED.sub("of " + b["opened"], text)


def based_chart(ch, sheet):
    """Round 12, pass 4 (V1): a chart's caption with the sheet's base ("Share of your math videos, by theme:")."""
    b = bases(sheet)
    if not ch or not b or (sheet.get("lang") or "en") != "en":
        return ch
    head, _, rest = ch.partition("\n")
    for old, new in _BASE_CAPS.items():
        if head.startswith(old) and (b.get("yt") or "{yt}" not in new):
            v = b["videos"]
            head = new.format(opened=b["opened"], yt=b["yt"], Videos=v[:1].upper() + v[1:]) + head[len(old):]
            break
    return head + ("\n" + rest if rest else "")


_SPAN_DATES = re.compile(r"\s*\((\d{1,2} [A-Z][a-z]+(?: \d{4})? to \d{1,2} [A-Z][a-z]+ \d{4})\)")


def _once_spans(form):
    """Round 12, pass 3 fix (judge A, row 8: "(1 March to 31 May 2023)" printed three times): the dates of a span
    before are said once, the first time; later sentences say its words alone ("against the spring before")."""
    seen = set()

    def once(t):
        if not t:
            return t

        def sub(m):
            if m.group(1) in seen:
                return ""
            seen.add(m.group(1))
            return m.group(0)
        return _SPAN_DATES.sub(sub, t)
    ans = once(form.get("answer"))
    obs = [once(o) for o in form.get("observations") or []]
    return dict(form, answer=ans, observations=obs, so_what=once(form.get("so_what")))


def areas_drawn(sheet):
    """The areas cover enough of the window to be its picture (the chart's own rule): the level a top answer leads
    with (round 12, pass 3, U3: lead and chart at the same level)."""
    ts = [t for t in (sheet or {}).get("areas") or [] if isinstance(t, dict) and _num(t.get("share")) and t.get("name")]
    return len(ts) >= 2 and sum(t["share"] for t in ts) >= 0.4


def answer_level(answer, sheet):
    """"areas" or "themes": the level the answer names (an area's name first), or None."""
    if not answer or (sheet or {}).get("kind") != "top":
        return None
    a = " " + " ".join(_words(answer)) + " "
    if any(" " + " ".join(_words(x.get("name") or "")) + " " in a for x in sheet.get("areas") or []
           if isinstance(x, dict) and x.get("name")):
        return "areas"
    if any(" " + " ".join(_words(x.get("name") or "")) + " " in a for x in sheet.get("themes") or []
           if isinstance(x, dict) and x.get("name")):
        return "themes"
    return None


def layout(form, sheet, items_parts=None, extra_lines=()):
    """The message parts: the answer, the observations, the chart, the so-what, the extra lines (a hint said once in
    6 hours), the offers. For a day, a first or a last: the overview, the items' lines, their cards, then the rest."""
    lang = sheet.get("lang") or "en"
    kind = sheet.get("kind")
    form = dict(form, answer=scoped(form["answer"], sheet, answer=True),
                observations=[scoped(o, sheet) for o in form["observations"]],
                so_what=scoped(form.get("so_what"), sheet))   # round 12, pass 4 (V1): the so-what with its base too
    form = _once_spans(form)
    head = [_no_title_twice(window_lead(form["answer"], sheet), sheet)]
    if form["observations"]:
        head.append("\n".join("• " + o for o in form["observations"]))
    tail = []
    ch, _ = chart(sheet, answer_level(form["answer"], sheet)) if kind not in ITEM_KINDS else (None, set())
    ch = based_chart(ch, sheet)
    if ch:
        head.append(ch)
    if form.get("so_what"):
        tail.append(form["so_what"])
    tail += [x for x in extra_lines if x]
    said_ = " ".join([head[0]] + list(form["observations"]) + [ch or "", form.get("so_what") or ""])
    form["offers_shown"] = offers_fit(sheet, form.get("offers"), said_, ch)
    ol = offers_line(dict(sheet, offers=form["offers_shown"]), form["offers_shown"], lang)
    if ol:
        tail.append(ol)
    items = [it for it in sheet.get("items") or [] if isinstance(it, dict)] if kind in ITEM_KINDS else []
    if items:
        end = _as_date((sheet.get("window") or {}).get("end"))
        year = end.year if end else None
        parts = [{"type": "text", "text": "\n\n".join(head)}]
        cards = list(items_parts or [])
        if not cards:   # no cards to show: the items as lines, as before
            parts[0]["text"] += "\n\n" + "\n".join(_item_line(k, it, lang, year)
                                                    for k, it in enumerate(items[:SHOW["items"]], 1))
        for k, card in enumerate(cards, 1):
            # round 12, pass 3 (U4, live: every item twice, a numbered list and then the same items as cards; row 6
            # was 6,400 px tall on a phone): the overview, then each card with one short caption line (its number, the
            # channel, the day, the length); a channel that draws cards shows the caption on the card itself
            it = card.get("item") if isinstance(card.get("item"), dict) else (items[k - 1] if k <= len(items) else {})
            cap = card.get("caption") or item_caption(k, it, lang, year, day=(kind == "day"))
            card = {a: b for a, b in card.items() if a != "item"}
            parts.append({"type": "text", "text": cap, "card_alt": True})
            parts.append(dict(card, caption=cap))
        if tail:
            parts.append({"type": "text", "text": "\n".join(tail)})
        return parts
    body = "\n\n".join(head + (["\n".join(tail)] if tail else []))
    return [{"type": "text", "text": body}]


# ====================================== round 12, fix: the sentences code writes from the sheet ===================
# Judges of round 12 (live, the real library): about 1 in 3 writer calls lost its answer or an observation to the check
# and today's code reply (the top 5 by count the founder graded "filler") went out instead, the call still paid for.
# Now a well-formed form keeps what passed and code fills the rest from the same sheet, in sentences built only from
# its numbers and names and checked by the same check: the answer when the model's failed, observations up to the
# minimum, the length of what was opened where no observation says it (R-D), the so-what when the model's is missing,
# repeated or about something else. Today's code reply stays the fallback when the model fails (an error, the cap, no
# script) or its reply is no form.
def _pc(x, lang="en"):
    v = float(x) * 100
    t = f"{round(v)}%" if v >= 1 or v == 0 else f"{v:.1f}%"
    return t.replace(".", ",") if lang == "es" else t


def _hrs(h, lang="en"):
    h = float(h)
    t = f"{round(h):,}" if h >= 2 else f"{h:.1f}"
    if lang == "es":
        t = t.replace(",", "X").replace(".", ",").replace("X", ".")
    return t


def _day_words(d, lang="en"):
    return f"{d.day} de {MONTHS_ES[d.month - 1]} de {d.year}" if lang == "es" else \
        f"{d.day} {MONTHS[d.month - 1].capitalize()} {d.year}"


def _rows_named(xs, need=("name",)):
    return [x for x in xs or [] if isinstance(x, dict) and all(x.get(k) not in (None, "") for k in need)]


def _hour_words(h):
    h = int(h)
    return "midnight" if h == 0 else "noon" if h == 12 else f"{h % 12}{'am' if h < 12 else 'pm'}"


def _cap(x):
    return x[:1].upper() + x[1:] if x else x


def code_form(sheet):
    """A form written by code from the sheet alone: {"answer", "observations": [{"text", "uses"}], "so_what"}.
    Every number and name comes from the sheet; the same check reads it before anything of it is sent.
    Round 12, pass 2: the broad picture first (areas: T3), no total of length anywhere (T2), eras for a change (T4),
    a day against the usual day (T10), a comparison in words (T9), what each top channel is (T11)."""
    s = shown(sheet)
    kind, lang = s.get("kind"), s.get("lang") or "en"
    es = lang == "es"
    f = _fmt
    tot, prev = s.get("totals") or {}, s.get("previous") or {}
    pw = (prev.get("words") or "").strip() if lang != "es" else ""   # the span before is said in English only
    areas = _rows_named(s.get("areas"), ("name", "share"))
    themes = _rows_named(s.get("themes"), ("name", "share"))
    chans = _rows_named(s.get("channels"), ("name", "items"))
    obs, ans, sw = [], None, None
    moving_said = None
    story = None

    def o(text, *uses, must=False):
        obs.append({"text": text, "uses": list(uses), **({"must": True} if must else {})})

    def pc(x):
        return _pc(x, lang)

    def lead(rows, what="of what you opened"):
        """T1, T3: "mostly" only for half or more; "a wide mix" only under a fifth; else the leader and the next."""
        if len(rows) < 2:
            return None
        a0, a1 = rows[0], rows[1]
        a2 = rows[2] if len(rows) >= 3 else None
        if a0["share"] >= SPREAD_SHARE:
            return (f"Sobre todo {a0['name']} ({pc(a0['share'])} de lo que abriste), luego {a1['name']} "
                    f"({pc(a1['share'])})." if es else
                    f"Mostly {a0['name']} ({pc(a0['share'])} {what}), then {a1['name']} ({pc(a1['share'])}).")
        if a0["share"] >= 2.5 * a1["share"] and a0["share"] >= 0.25:
            # round 12, pass 2 fix (judge A: "mostly gaming at 46%" is "mostly" under half): far ahead, said so
            return (f"{a0['name'][:1].upper() + a0['name'][1:]} por mucho: {pc(a0['share'])} de lo que abriste, muy por "
                    f"delante de {a1['name']} ({pc(a1['share'])})." if es else
                    f"{a0['name']} by far: {pc(a0['share'])} {what}, well ahead of {a1['name']} "
                    f"({pc(a1['share'])}).")
        if a0["share"] + a1["share"] >= SPREAD_SHARE:
            return (f"Sobre todo {a0['name']} ({pc(a0['share'])} de lo que abriste) y {a1['name']} "
                    f"({pc(a1['share'])})." if es else
                    f"Mostly {a0['name']} ({pc(a0['share'])} {what}) and {a1['name']} ({pc(a1['share'])}).")
        if a2 and a0["share"] + a1["share"] + a2["share"] >= SPREAD_SHARE:
            return (f"La mayor parte fue {a0['name']} ({pc(a0['share'])}), {a1['name']} ({pc(a1['share'])}) y "
                    f"{a2['name']} ({pc(a2['share'])})." if es else
                    f"Most of it was {a0['name']} ({pc(a0['share'])}), {a1['name']} ({pc(a1['share'])}) and "
                    f"{a2['name']} ({pc(a2['share'])}).")
        if a0["share"] < WIDE_MIX:
            return (f"Una mezcla amplia: primero {a0['name']} ({pc(a0['share'])}), luego {a1['name']} "
                    f"({pc(a1['share'])})." if es else
                    f"A wide mix: {a0['name']} led with {pc(a0['share'])}, then {a1['name']} ({pc(a1['share'])}).")
        return (f"Primero {a0['name']} ({pc(a0['share'])}), luego {a1['name']} ({pc(a1['share'])})." if es else
                f"{a0['name']} led with {pc(a0['share'])} {what}, then {a1['name']} ({pc(a1['share'])}).")

    def inside(a):
        ts = _rows_named(a.get("themes"), ("name", "share"))[:2]
        if len(ts) == 2:
            # round 12, pass 2 fix (judge B: "Inside gaming: X (5%)" read as 5% of gaming): whose share it is
            o((f"Dentro de {a['name']}: {ts[0]['name']} ({pc(ts[0]['share'])} de todo lo que abriste) y "
               f"{ts[1]['name']} ({pc(ts[1]['share'])})." if es else
               f"Inside {a['name']}: {ts[0]['name']} ({pc(ts[0]['share'])} of everything you opened) and "
               f"{ts[1]['name']} ({pc(ts[1]['share'])})."), "areas")
        elif len(ts) == 1 and ts[0]["name"].lower() != a["name"].lower():
            o((f"Dentro de {a['name']}, sobre todo {ts[0]['name']} ({pc(ts[0]['share'])})." if es else
               f"Inside {a['name']}, {ts[0]['name']} led with {pc(ts[0]['share'])}."), "areas")

    said_moves = set()

    def moves(rows, key):
        ch = [t for t in rows if _num(t.get("change_vs_previous")) and _num(t.get("previous_share"))
              and (round(t["previous_share"], 2), round(t["share"], 2)) not in said_moves]
        up = sorted((t for t in ch if t["change_vs_previous"] >= 0.015), key=lambda t: -t["change_vs_previous"])
        down = sorted((t for t in ch if t["change_vs_previous"] <= -0.015), key=lambda t: t["change_vs_previous"])
        # round 12, pass 3 (U7): every move said the same way: its direction, both values and the base period
        if up and pw:
            t = up[0]
            o(f"{t['name']} grew from {pc(t['previous_share'])} to {pc(t['share'])} against {pw}.", key)
        elif up and es:
            t = up[0]
            o(f"{t['name']} subió de {pc(t['previous_share'])} a {pc(t['share'])}.", key)
        if down and (pw or es):
            t = down[0]
            o((f"{t['name']} bajó de {pc(t['previous_share'])} a {pc(t['share'])}." if es else
               f"{t['name']} fell from {pc(t['previous_share'])} to {pc(t['share'])} against {pw}."), key)
        for t in (up[:1] + down[:1]) if (pw or es) else []:   # an area of one theme says the same move once
            said_moves.add((round(t["previous_share"], 2), round(t["share"], 2)))

    def behind(t):
        cs = _rows_named(t.get("channels"), ("name", "items"))[:2]
        if len(cs) == 2 and not es:
            o(f"Behind {t['name']}: {cs[0]['name']} ({f(cs[0]['items'], lang)} videos) and {cs[1]['name']} "
              f"({f(cs[1]['items'], lang)}).", "themes")

    def shorts_share_line(must=False, length=True):
        """Round 12, pass 2 fix (judge A, row 8: "Shorts made up 12,080 of your window"; the summer's three quarters
        Shorts not said): Shorts as a share of the YouTube videos, against the span before."""
        sh, lo, m = tot.get("shorts"), tot.get("long"), tot.get("long_median_min")
        psh, plo = prev.get("shorts"), prev.get("long")
        if not (_num(sh) and _num(lo) and sh + lo >= 20) or es:
            return False
        a = tot.get("shorts_share")
        if not _num(a):
            return False
        tail = f"; the long ones were typically about {int(m)} minutes" if _num(m) and lo >= 5 and length else ""
        b = prev.get("shorts_share")
        if pw and _num(b) and _num(psh) and _num(plo) and psh + plo >= 20 and abs(a - b) >= 0.05:
            o(f"Shorts were {pc(a)} of your YouTube videos, against {pc(b)} in {pw}{tail}.", "totals", "previous",
              must=must)
        else:
            o(f"Shorts were {pc(a)} of your YouTube videos{tail}.", "totals", must=must)
        return True

    def shorts_long():
        sh, lo, m = tot.get("shorts"), tot.get("long"), tot.get("long_median_min")
        if _num(sh) and _num(lo) and sh + lo > 0:
            tail = (f", the long ones typically about {int(m)} minutes" if _num(m) and lo else "") if not es else \
                (f", los largos de unos {int(m)} minutos" if _num(m) and lo else "")
            if not sh:
                o((f"Ningún Short: {f(lo, lang)} videos largos{tail}." if es else
                   f"No Shorts: {f(lo, lang)} long videos{tail}."), "totals")
            else:
                o((f"{f(sh, lang)} fueron Shorts y {f(lo, lang)} videos largos{tail}." if es else
                   f"{f(sh, lang)} were Shorts and {f(lo, lang)} long videos{tail}."), "totals")

    if kind == "top" and (len(areas) >= 2 or len(themes) >= 2):
        # round 12, pass 3 (U3): the areas lead only where the chart draws them (live, "without Shorts": a lead by
        # area over a chart by theme)
        by_area = len(areas) >= 2 and (areas_drawn(s) or len(themes) < 2)
        ans = lead(areas) if by_area else lead(themes)
        # (the move as the sheet had it before the last answer's so-what was taken out: the lead stays the same when
        # the question is asked again; history._write_now keeps it)
        mv_ = (sheet.get("moving_lead") if isinstance(sheet.get("moving_lead"), dict) else None) or \
            next((c for c in candidates(s) if c.get("kind") == "moving"), None)
        # (asked again, the fall was said by the answer before: the lead says both sides of the move, no so-what)
        again = mv_ is not None and not any(c.get("kind") == "moving" for c in candidates(s))
        into = sheet.get("into") if (isinstance(sheet.get("into"), dict) and by_area and not es) else None
        ml = _moving_lead(areas, mv_, pw, both=again) if (by_area and mv_ and not es and into is None) else None
        if into is not None:
            # round 12, pass 4 (V2, row 8: asked what he was INTO, the lead said how he watched): the biggest areas,
            # with the themes in them that peaked then or were new then; how he watched is a bullet
            il = _into_lead(areas, into, sheet)
            if il:
                ans, moving_said = il, "into"
        if ml:
            # round 12, pass 3 fix (judge A, row 1: "lead with the change, not the ranking"): the leader's move against
            # the weeks before is the answer to "lately"; what is said here is no so-what again
            ans, moving_said = ml
        if by_area:
            inside(areas[0])
            moves(areas, "areas")
        moves(themes, "themes")
        if themes:
            behind(themes[0])
        dt = _rows_named((s.get("distinct") or {}).get("themes"), ("name", "share", "rest_share"))[:2]
        rw = (s.get("distinct") or {}).get("rest_words")
        sea = re.match(r"^(?:in\s+)?the\s+(summer|spring|autumn|fall|winter)\b", str((s.get("window") or {}).get(
            "words") or "").strip(), re.I)
        story = None
        a_sh, b_sh = tot.get("shorts_share"), prev.get("shorts_share")
        fell = sorted((a for a in areas if _num(a.get("change_vs_previous")) and _num(a.get("previous_share"))
                       and a["change_vs_previous"] <= -0.10), key=lambda a: a["change_vs_previous"])
        if sea and by_area and pw and not es and not ml and _num(a_sh) and _num(b_sh) and a_sh - b_sh >= 0.25 and \
                not (s.get("filters") or {}).get("without_shorts") and moving_said == "into":
            # round 12, pass 4 (V2): the move to Shorts is the second point, the first bullet
            pws_ = re.sub(r"\s*\([^)]*\)\s*$", "", pw).strip()
            o(f"You moved to Shorts: {pc(a_sh)} of your YouTube videos, from {pc(b_sh)} in {pws_}" +
              (f", while {fell[0]['name']} fell from {pc(fell[0]['previous_share'])} to {pc(fell[0]['share'])}."
               if fell else "."), "totals", "previous", must=True)
            story = "bullet"
        elif sea and by_area and pw and not es and not ml and _num(a_sh) and _num(b_sh) and a_sh - b_sh >= 0.25 and \
                not (s.get("filters") or {}).get("without_shorts"):
            # round 12, pass 3 fix (judge A, row 8: "the lead buries the story"): a season that changed how he watched
            # leads with it, and with the area that fell most; what led is said after
            ssn = sea.group(1).lower()
            pws_ = re.sub(r"\s*\([^)]*\)\s*$", "", pw).strip()   # (the window words say the season's dates)
            story = (f"you moved to Shorts: {pc(a_sh)} of your YouTube videos, from {pc(b_sh)} in {pws_}" +
                     (f", while {fell[0]['name']} fell from {pc(fell[0]['previous_share'])} to {pc(fell[0]['share'])}"
                      if fell else "") + f"; {areas[0]['name']} came first in a wide mix." if areas[0]["share"] < WIDE_MIX
                     else f"; {areas[0]['name']} came first.")
            ans, moving_said = story, "story"
        if dt and rw and not es:
            # round 12, pass 3 (U8, row 8: "say what made that season distinct against the year around it"): the
            # themes that ran well above their share of the rest of that year, first among the bullets
            what = f"the {sea.group(1).lower()}" if sea else "this stretch"
            items_ = " and ".join(f"{t['name']} ({pc(t['share'])}, against {pc(t['rest_share'])})" for t in dt)
            dt = [t for t in dt if round(t["share"], 3) >= 2 * round(t["rest_share"], 3)]
            items_ = " and ".join(f"{t['name']} ({pc(t['share'])}, against {pc(t['rest_share'])})" for t in dt)
            if dt:
                # round 12, pass 3 fix (judge A, row 8: weak differences shown as the distinct thing); round 12, pass 4
                # (V2: "Little else set the summer apart ..." is filler): only what ran at twice its share is said
                o(f"What set {what} apart from {rw}: {items_}.", "distinct", must=True)
        if story:
            pass   # the Shorts are the answer's own (or its first bullet)
        elif moving_said == "into":
            # round 12, pass 4 (V2): how he watched, as a bullet, without the typical long video (filler here)
            shorts_share_line(must=False, length=False)
        elif not shorts_share_line(must=True):
            shorts_long()
    elif kind == "channels" and len(chans) >= 2:
        c0, c1 = chans[:2]
        topic = (s.get("filters") or {}).get("topic")
        head = (f"En {topic}, " if es else f"For {topic}, ") if topic else ""
        tail0 = ""
        if len(chans) >= 3 and not es and len(_rows(s, "channels", lang)[1]) >= 3:
            # round 12, pass 3 fix (judge A, row 2: "the lead's three numbers are printed again as the chart's top
            # three bars"): the lead in words, the chart carries the counts
            c2 = chans[2]
            ans = f"{head}{c0['name']} led, ahead of {c1['name']} and {c2['name']}."
            moving_said = "words"
        elif len(chans) >= 3:
            c2 = chans[2]
            ans = (f"{head}{c0['name']} va primero con {f(c0['items'], lang)} videos, seguido de {c1['name']} "
                   f"({f(c1['items'], lang)}) y {c2['name']} ({f(c2['items'], lang)})." if es else
                   f"{head}{c0['name']} led with {f(c0['items'], lang)} videos{tail0}, ahead of {c1['name']} "
                   f"({f(c1['items'], lang)}) and {c2['name']} ({f(c2['items'], lang)}).")
        else:
            ans = (f"{head}{c0['name']} va primero con {f(c0['items'], lang)} videos, seguido de {c1['name']} "
                   f"({f(c1['items'], lang)})." if es else
                   f"{head}{c0['name']} led with {f(c0['items'], lang)} videos{tail0}, ahead of {c1['name']} "
                   f"({f(c1['items'], lang)}).")
        ta = s.get("top_areas") or {}
        if not es and not topic and ta.get("area") and _num(ta.get("n")) and _num(ta.get("of")) and ta["n"] >= 2:
            # round 12, pass 2 fix (judge A, row 2: "say what each top channel is and what most of the top 5 are"):
            # one line, said whatever the writer chose (never under a topic: "X is gaming" in a gaming answer)
            same = [c["name"] for c in chans[:5] if c.get("area") == ta["area"]]
            other = [c for c in chans[:5] if c.get("area") and c.get("area") != ta["area"]][:2]
            line = (f"All {f(ta['n'], lang)} of your top {f(ta['of'], lang)} are {ta['area']} channels."
                    if ta["n"] == ta["of"] else
                    f"{f(ta['n'], lang)} of your top {f(ta['of'], lang)} are {ta['area']} channels ("
                    + ", ".join(same) + ")" + ("; " + " and ".join(f"{c['name']} is {c['area']}" for c in other)
                                               if other else "") + ".")
            o(line, "top_areas", "channels", must=True)
        elif not es and not topic and [c for c in chans[:5] if c.get("area") or c.get("theme")]:
            named = [c for c in chans[:5] if c.get("area") or c.get("theme")][:3]
            o("What they are: " + ", ".join(f"{c['name']} is {c.get('area') or c.get('theme')}" for c in named) + ".",
              "channels", must=True)
        elif not es and topic:
            # under a topic the area says nothing ("5 of your top 5 are math"): what each one is about inside it
            th_ = [c for c in chans[:3] if c.get("theme") and _num(c.get("theme_share")) and c["theme_share"] >= 0.4]
            if len(themes) >= 2:   # round 12, pass 2 fix (live, "only gaming": one bullet, the code reply went out)
                o(f"Inside {topic}: {themes[0]['name']} ({_pc(themes[0]['share'])} of your {topic} videos) and "
                  f"{themes[1]['name']} ({_pc(themes[1]['share'])}).", "themes")
                moves(themes, "themes")
            if len(th_) >= 2 and th_[0]["theme"] == th_[1]["theme"]:
                o(f"{th_[0]['name']} and {th_[1]['name']} are both about {th_[0]['theme']} "
                  f"({_pc(th_[0]['theme_share'])} and {_pc(th_[1]['theme_share'])} of their videos).", "channels")
            elif len(th_) >= 2:
                o("What they are: " + "; ".join(f"{c['name']} is about {c['theme']} ({_pc(c['theme_share'])} of its "
                                                f"videos)" for c in th_[:2]) + ".", "channels")
        top5 = [c for c in chans[:5] if _num(c.get("shorts_share"))]
        sh = [c for c in top5 if c["shorts_share"] >= 0.8][:2]
        lo = [c for c in top5 if c["shorts_share"] <= 0.1][:2]
        if sh and lo and not es and not (s.get("filters") or {}).get("without_shorts") and \
                all(_num(c.get("days")) for c in lo):
            # round 12, pass 3 (U8, row 2: "say what the ranking says about him"): the clip channels he grazes
            # against the long-form ones he keeps coming back to, from each one's Shorts share and days
            o(" and ".join(c["name"] for c in sh) + (" is a clip channel" if len(sh) == 1 else " are clip channels") +
              " you grazed (" + " and ".join(_pc(c["shorts_share"]) for c in sh) + " Shorts); " +
              " and ".join(c["name"] for c in lo) + (" is a long-form channel" if len(lo) == 1 else " are long-form channels") +
              " you kept coming back to (on " + " and ".join(f(c["days"], lang) for c in lo) + " days).", "channels",
              must=True)
        elif (sh or lo) and not es and not (s.get("filters") or {}).get("without_shorts"):
            bits = []
            if sh:
                bits.append(" and ".join(c["name"] for c in sh) + (" is" if len(sh) == 1 else " are") +
                            " almost all Shorts (" + " and ".join(_pc(c["shorts_share"]) for c in sh) + ")")
            if lo:
                bits.append(" and ".join(c["name"] for c in lo) + (" has" if len(lo) == 1 else " have") +
                            " almost no Shorts (" + " and ".join(_pc(c["shorts_share"]) for c in lo) + ")")
            o(", while ".join(bits) + ".", "channels")
        if not es and not _long_or_one_day(s):
            new = [c for c in _rows_named((s.get("new") or {}).get("channels"), ("name", "items"))
                   if c["name"] in {x["name"] for x in chans[:5]}]
            if new:
                o(f"{new[0]['name']} is new: first opened in this span, {f(new[0]['items'], lang)} videos.", "new")
    elif kind == "count" and _num(tot.get("items")) and (s.get("filters") or {}).get("topic"):
        topic = (s.get("filters") or {}).get("topic") or ""
        wt = (s.get("window_totals") or {}).get("items")
        d = tot.get("days_active")
        tp = (_rows_named(s.get("topics"), ("name",)) or [{}])[0]
        about = "themes" in str(tp.get("matched_by") or "")   # T8: a count with themes in it is an estimate
        if _num(tp.get("items")) and _num(tp.get("days")) and tp["items"] < tot["items"]:
            tot = dict(tot, items=tp["items"], days_active=tp["days"], shorts=tp.get("shorts"), long=tp.get("long"),
                       long_median_min=None)
            wt = wt if _num(wt) else (s.get("totals") or {}).get("items")
            d = tp["days"]
        if es:
            ans = ("Unos " if about else "") + f"{f(tot['items'], lang)} videos de {topic} en {f(d, lang)} días" + (
                f", de {f(wt, lang)} que abriste en total." if _num(wt) else ".")
        else:
            ans = ("About " if about else "") + f"{f(tot['items'], lang)} {topic} videos on {f(d, lang)} days" + (
                f", out of {f(wt, lang)} you opened in all." if _num(wt) else ".")
        if _num(prev.get("items")) and pw and prev["items"] != tot["items"]:
            up = tot["items"] > prev["items"]
            o(f"That is {'up' if up else 'down'} from {f(prev['items'], lang)} in {pw}.", "totals", "previous")
        if len(themes) >= 2 and not es:
            o(f"The biggest parts: {themes[0]['name']} ({_pc(themes[0]['share'])}) and {themes[1]['name']} "
              f"({_pc(themes[1]['share'])}).", "themes")
        if len(themes) >= 2:
            moves(themes, "themes")
        shorts_long()
        if chans and not es:
            o(f"{chans[0]['name']} gave the most: {f(chans[0]['items'], lang)} of them.", "channels")
    elif kind in ("first", "last") and not es:
        items = _rows_named(s.get("items"), ("title", "at"))
        tp = _rows_named(s.get("topics"), ("name",))
        topic = (s.get("filters") or {}).get("topic") or (tp[0]["name"] if tp else "")
        d0 = _as_date(items[0]["at"]) if items else None
        if d0 and topic:
            ans = (f"You first opened a {topic} video on {_day_words(d0)}." if kind == "first" else
                   f"The last {topic} video you opened was on {_day_words(d0)}.")
        if _num(tot.get("items")) and _num(tot.get("days_active")):
            o((f"Since then you opened {f(tot['items'], lang)} {topic} videos on {f(tot['days_active'], lang)} days."
               if kind == "first" else f"In all you opened {f(tot['items'], lang)} {topic} videos on "
               f"{f(tot['days_active'], lang)} days."), "totals")
        sh, lo = tot.get("shorts"), tot.get("long")
        if _num(sh) and _num(lo) and sh + lo > 0:
            m = tot.get("long_median_min")
            tail = f", typically about {int(m)} minutes" if _num(m) and lo else ""
            o(_split_line(tot, lang), "totals")
        cs = [c for c in _rows_named((tp[0].get("channels") if tp else None) or s.get("channels"), ("name", "items"))
              if "@" not in c["name"]][:2]
        if len(cs) == 2:
            o(f"{cs[0]['name']} ({f(cs[0]['items'], lang)}) and {cs[1]['name']} ({f(cs[1]['items'], lang)}) are the "
              f"channels behind it.", "topics", "channels")
        sw = _path_line(s, topic)
    elif kind == "day" and _num(tot.get("items")):
        n, sh = tot["items"], tot.get("shorts")
        us = s.get("usual") or {}
        mi = us.get("median_items")
        # round 12, pass 3 fix (judge A, row 6): the export's last day may hold only part of that day, so it is never
        # set against a usual day's count or hour; "a usual day" says what it is (a day of the 3 months before, with
        # anything opened, not the same weekday); a small day's leading theme is said as a count ("3 of them")
        last_day = "last day of your export" in str((s.get("window") or {}).get("words") or "")
        usual_w = "a usual day of the three months before"
        t0 = themes[0] if themes and _num(themes[0].get("items")) and n >= 3 else None
        led = (f"; {t0['name']} led with {f(t0['items'], lang)} of them." if t0 and t0["items"] >= 2 else
               f"; {themes[0]['name']} led with {_pc(themes[0]['share'])}." if themes and n >= 3 and not t0 else ".")
        if not es:
            if _num(mi) and mi > 0 and last_day:
                ans = f"{f(n, lang)} videos" + led
            elif _num(mi) and mi > 0:
                r = n / mi
                cmp_ = ("about as many as" if 0.8 <= r <= 1.25 else "more than" if r > 1.25 else "fewer than")
                ans = f"{f(n, lang)} videos, {cmp_} on {usual_w} ({f(mi, lang)})" + led
                usual_w = "a usual day"
            elif len(themes) >= 2 and n >= 3:
                ans = f"{f(n, lang)} videos" + (f", {f(sh, lang)} of them Shorts" if _num(sh) and sh else "") + \
                    f"; {themes[0]['name']} ({_pc(themes[0]['share'])}) led, then {themes[1]['name']} " \
                    f"({_pc(themes[1]['share'])})."
            else:
                ans = f"{f(n, lang)} videos" + (f", {f(sh, lang)} of them Shorts." if _num(sh) and sh else ".")
            if _num(us.get("day_shorts_share")) and _num(us.get("shorts_share")):
                # round 12, pass 2 fix (judge A, row 6: say the day's Shorts and busiest hour against his usual day)
                o(f"Shorts were {_pc(us['day_shorts_share'])} of the day's YouTube videos, against "
                  + (f"about {_pc(us['shorts_share'])}" if us["shorts_share"] >= 0.01 else "none")
                  + (" on a usual day of the months before." if usual_w.endswith("before") else f" on {usual_w}."),
                  "usual", must=True)
                usual_w = "a usual day"
            elif _num(sh) and sh:
                o(f"{f(sh, lang)} of them were Shorts.", "totals")
            bh = ((s.get("when") or {}).get("busiest_hours") or [{}])[0]
            bh = {"hour": bh} if _num(bh) else bh
            if isinstance(bh, dict) and _num(bh.get("hour")) and n >= 3 and last_day:
                # a day the export cuts off is never set against a usual day's hour (its hours stop where the export
                # does); its own busiest hour is said plainly
                o(f"The busiest hour was {_hour_words(bh['hour'])}.", "when")
            elif isinstance(bh, dict) and _num(bh.get("hour")) and n >= 3:
                if _num(us.get("busiest_hour")) and abs(int(us["busiest_hour"]) - int(bh["hour"])) >= 2:
                    o(f"The busiest hour was {_hour_words(bh['hour'])}, where {usual_w} peaks around "
                      f"{_hour_words(us['busiest_hour'])}.", "when", "usual", must=True)
                elif _num(us.get("busiest_hour")):
                    o(f"The busiest hour was {_hour_words(bh['hour'])}, as on {usual_w}.", "when", "usual",
                      must=True)
                elif _num(bh.get("share")):
                    o(f"The busiest hour was {_hour_words(bh['hour'])}, with {_pc(bh['share'])} of the day.", "when")
                else:
                    o(f"The busiest hour was {_hour_words(bh['hour'])}.", "when")
            nt = s.get("new_today") or {}
            if _num(nt.get("channels")) and nt["channels"] >= 1 and nt.get("names"):
                o(f"{nt['names'][0]} was new that day" + (f", one of {f(nt['channels'], lang)} channels you opened "
                                                          f"for the first time." if nt["channels"] >= 2 else "."),
                  "new_today")
            elif chans and chans[0]["items"] >= 2:
                o(f"{chans[0]['name']} gave the most ({f(chans[0]['items'], lang)}).", "channels")
    elif kind == "compare_topics":
        tp = _rows_named(s.get("topics"), ("name", "items"))
        cmpx = s.get("comparison") or {}
        if not cmpx and len(tp) >= 2:
            from . import facts as F
            cmpx = F._compare(tp, None, lang)
        if len(tp) >= 2 and not es:
            a, b = tp[0], tp[1]
            big, small = (a, b) if a["items"] >= b["items"] else (b, a)
            rw = cmpx.get("ratio_words")
            if small["items"] and rw and rw not in ("about the same", "a little more"):
                ans = (f"Much more {big['name']} than {small['name']}: {rw} ({f(big['items'], lang)} against "
                       f"{f(small['items'], lang)}).")
            elif small["items"] and rw == "a little more":
                ans = (f"A little more {big['name']} than {small['name']}: {f(big['items'], lang)} against "
                       f"{f(small['items'], lang)}.")
            elif small["items"]:
                ans = (f"About even: {f(a['items'], lang)} {a['name']} videos and {f(b['items'], lang)} "
                       f"{b['name']} ones.")
            for x in (big, small):
                tt = _rows_named(x.get("top_themes"), ("name", "items"))[:2]
                if len(tt) == 2:
                    o(f"Inside {x['name']}: {tt[0]['name']} ({f(tt[0]['items'], lang)}) and {tt[1]['name']} "
                      f"({f(tt[1]['items'], lang)}).", "topics")
                elif len(tt) == 1:
                    o(f"Inside {x['name']}, {tt[0]['name']} led with {f(tt[0]['items'], lang)}.", "topics")
            if pw and all(_num(x.get("previous_items")) for x in (a, b)) and cmpx.get("balance"):
                bal = {"wider": "the gap has widened", "narrower": "the gap has narrowed",
                       "about the same": "about the same balance"}[cmpx["balance"]]
                prw = cmpx.get("previous_ratio_words")
                # round 12, pass 2 fix (judges, row 5: how the balance moved against last year was not said)
                if prw and prw not in ("about the same", "a little more"):
                    o(f"In {pw} it was {prw} ({f(big['previous_items'], lang)} {big['name']} against "
                      f"{f(small['previous_items'], lang)} {small['name']}): {bal}.", "topics", "comparison",
                      must=True)
                else:
                    o(f"In {pw} it was {f(big['previous_items'], lang)} {big['name']} against "
                      f"{f(small['previous_items'], lang)} {small['name']}: {bal}.", "topics", "comparison", must=True)
            if all(_num(x.get("shorts")) for x in (a, b)) and a["shorts"] + b["shorts"] > 0:
                o(f"{f(a['shorts'], lang)} of the {a['name']} videos were Shorts, against {f(b['shorts'], lang)} of "
                  f"the {b['name']} ones.", "topics")
            if all(_num(x.get("days")) for x in (a, b)):
                o(f"{a['name'].capitalize()} came on {f(a['days'], lang)} days, {b['name']} on {f(b['days'], lang)}.",
                  "topics")
            for x in (big, small):
                c = (_rows_named(x.get("channels"), ("name", "items")) or [None])[0]
                if c and not x.get("top_themes"):
                    o(f"{c['name']} is behind {f(c['items'], lang)} of the {f(x['items'], lang)} {x['name']} videos.",
                      "topics")
    elif kind == "compare_windows" and not es and _num(tot.get("items")) and _num(prev.get("items")):
        w = s.get("window") or {}
        la = _strip_in(w.get("label") or "") or None
        lb = _strip_in(prev.get("label") or prev.get("words") or "") or None
        if la and lb:
            a, b = tot["items"], prev["items"]
            ans = (f"More in {la}: {f(a, lang)} videos, against {f(b, lang)} in {lb}." if a > b else
                   f"Fewer in {la}: {f(a, lang)} videos, against {f(b, lang)} in {lb}." if a < b else
                   f"As many in {la} as in {lb}: {f(a, lang)} videos.")
        moves(themes, "themes")
        nw_ = [x.get("name") if isinstance(x, dict) else x for x in (s.get("new") or {}).get("themes") or []]
        if nw_:
            o(f"{nw_[0]} is new in {la or 'it'}.", "new")
        shorts_long()
    elif kind == "changed":
        ch = s.get("change") or {}
        eras = _rows_named(s.get("eras"), ("area", "from", "to"))
        ac = s.get("areas_change") or {}
        shx0 = ac.get("shorts") or {}
        big_shorts = _num(shx0.get("from_share")) and _num(shx0.get("to_share")) and \
            abs(shx0["to_share"] - shx0["from_share"]) >= 0.25

        def span(e):
            return e["from"] if e["from"] == e["to"] else (f"{e['from']} a {e['to']}" if es else
                                                           f"{e['from']} to {e['to']}")
        if len(eras) >= 2 and eras[0]["area"] == eras[-1]["area"]:
            # round 12, pass 2 fix (judge A: "Gaming led from Jan 2026 to Mar 2026; since Oct 2026, gaming has"): the
            # same area at both ends led most of the time; what led in between is said by its stretch
            e0 = eras[0]
            mid = [e for e in eras if e["area"] != e0["area"]][:2]
            ans = (f"{e0['area'][:1].upper() + e0['area'][1:]} lideró casi todo el tiempo; entre medias, "
                   + " y ".join(f"{e['area']} ({span(e)})" for e in mid) + "." if es else
                   f"{e0['area'][:1].upper() + e0['area'][1:]} led most of the time; in between, "
                   + " and ".join(f"{e['area']} led {('in ' + e['from']) if e['from'] == e['to'] else 'from ' + span(e)}"
                                  for e in mid) + ".")
        elif len(eras) >= 2:
            e0, e1 = eras[0], eras[-1]
            ans = (f"De {span(e0)} lideró {e0['area']}; desde {e1['from']}, lidera {e1['area']}." if es else
                   f"{e0['area'][:1].upper() + e0['area'][1:]} led from {span(e0)}; since {e1['from']}, {e1['area']} "
                   f"has.")
        elif len(eras) == 1:
            e0 = eras[0]
            ar = (_rows_named(ac.get("arrived"), ("name", "from_share", "to_share")) or [None])[0]
            arr = [x["name"] for x in _rows_named(ac.get("arrived"), ("name", "from_share", "to_share"))
                   if x["name"] != e0["area"]][:2]
            ys = [(str(p["label"]), p["areas"][0]["share"]) for p in _rows_named(s.get("periods"), ("label",))
                  if not p.get("sparse") and p.get("areas") and p["areas"][0].get("name") == e0["area"]
                  and _num(p["areas"][0].get("share"))]
            pk = max(ys, key=lambda t: t[1]) if len(ys) >= 3 else None
            arc = bool(pk and pk[0] not in (ys[0][0], ys[-1][0]) and pk[1] >= 1.4 * ys[0][1] and
                       pk[1] >= 1.4 * ys[-1][1])
            closed = not (s.get("window") or {}).get("clipped")
            every = "every year" if closed else f"every year since {e0['from']}"   # (the window says its years)
            if arc:
                # round 12, pass 3 fix (judge A, row 7: the chart's cliff after the peak hid the year of the turn): the
                # year it fell most, tied to the move to Shorts when that is the year Shorts jumped most
                pi = [k for k, (lb, _v) in enumerate(ys) if lb == pk[0]][0]
                after = ys[pi:]
                drops = [(after[k][1] - after[k + 1][1], after[k + 1]) for k in range(len(after) - 1)]
                dv, turn = max(drops, key=lambda t: t[0]) if drops else (0, None)
                psh = {str(p["label"]): p.get("shorts_share") for p in _rows_named(s.get("periods"), ("label",))
                       if _num(p.get("shorts_share"))}
                lbs = [lb for lb, _v in ys]
                jumps = [(psh[lbs[k + 1]] - psh[lbs[k]], lbs[k + 1]) for k in range(len(lbs) - 1)
                         if lbs[k] in psh and lbs[k + 1] in psh]
                jv, jy = max(jumps, key=lambda t: t[0]) if jumps else (0, None)
                if not (turn and dv >= 0.15 and turn[0] != ys[-1][0]):
                    turn = None
            if arc and not es and turn:
                # (four numbers at most in an answer: the Shorts' own two are a bullet's)
                why = ", the year you moved to Shorts" if jy == turn[0] and jv >= 0.2 else ""
                ans = (f"{e0['area'][:1].upper() + e0['area'][1:]} led every year, but its weight moved: "
                       f"{_pc(ys[0][1])} in {ys[0][0]}, up to {_pc(pk[1])} in {pk[0]}, then down to {_pc(turn[1])} in "
                       f"{turn[0]}{why}, and {_pc(ys[-1][1])} in {ys[-1][0]}" +
                       (f"; {' and '.join(arr)} took more of it." if arr else "."))
            elif arc and es and turn:
                # round 12, pass 3 fix (judge A, row 7 in Spanish: the Shorts answer of pass 2, not the fixed one)
                why = ", el año del salto a los Shorts" if jy == turn[0] and jv >= 0.2 else ""
                ans = (f"{e0['area'][:1].upper() + e0['area'][1:]} lideró cada año, pero su peso cambió: "
                       f"{_pc(ys[0][1], lang)} en {ys[0][0]}, hasta {_pc(pk[1], lang)} en {pk[0]}, luego bajó a "
                       f"{_pc(turn[1], lang)} en {turn[0]}{why}, y {_pc(ys[-1][1], lang)} en {ys[-1][0]}" +
                       (f"; {' y '.join(arr)} ganaron peso." if arr else "."))
            elif arc and not es:
                # round 12, pass 3 (U8, row 7: "led every year" hid that its share doubled and then fell back): WHAT
                # changed first, the leading area's weight over the years and what took its place
                ans = (f"{e0['area'][:1].upper() + e0['area'][1:]} led every year, but its weight moved: "
                       f"{_pc(ys[0][1])} in {ys[0][0]}, up to {_pc(pk[1])} in {pk[0]}, then down to {_pc(ys[-1][1])} "
                       f"in {ys[-1][0]}" + (f", as {' and '.join(arr)} took more of it." if arr else "."))
            elif big_shorts:
                # round 12, pass 2 fix (judge A, row 7: lead with the biggest change): one area led every year, and
                # what changed most is how he watches, Shorts against long videos
                ans = (f"{e0['area'][:1].upper() + e0['area'][1:]} lideró cada año desde {e0['from']}, pero cambió cómo "
                       f"ves: los Shorts pasaron del {_pc(shx0['from_share'], lang)} de tus videos de YouTube en "
                       f"{shx0['from']} al {_pc(shx0['to_share'], lang)} en {shx0['to']}." if es else
                       f"{e0['area'][:1].upper() + e0['area'][1:]} has led {every}, but how you "
                       f"watch changed: Shorts went from {_pc(shx0['from_share'])} of your YouTube videos in "
                       f"{shx0['from']} to {_pc(shx0['to_share'])} in {shx0['to']}.")
            elif ar and not es and " ".join(_words(ar["name"])) == " ".join(_words(e0["area"])):
                # round 12, pass 3 fix (judge A, "from 2023 to 2025": "has led every year since 2023; around it, gaming
                # rose"): the leader that grew is said as one, with what fell most beside it
                lf = [x for x in _rows_named(ac.get("left"), ("name", "from_share", "to_share"))
                      if x["name"] != e0["area"]][:1]
                ans = (f"{e0['area'].capitalize()} led {every} and grew, from {_pc(ar['from_share'])} in {ac['from']} "
                       f"to {_pc(ar['to_share'])} in {ac['to']}" +
                       (f", while {lf[0]['name']} fell from {_pc(lf[0]['from_share'])} to {_pc(lf[0]['to_share'])}."
                        if lf else "."))
            elif ar and not es:
                # one area led throughout: the change is what grew around it (round 12, pass 2, live)
                ans = (f"{e0['area'].capitalize()} has led {every}; around it, {ar['name']} rose "
                       f"from {_pc(ar['from_share'])} in {ac['from']} to {_pc(ar['to_share'])} in {ac['to']}.")
            else:
                ans = (f"{e0['area'].capitalize()} lidera cada año desde {e0['from']}, con cerca del "
                       f"{_pc(e0['share'], lang)} de cada año." if es else
                       f"{e0['area'].capitalize()} has led {every}, at about {_pc(e0['share'])} "
                       f"of each year.")
        for part, verb, verb_es in (("left", "fell", "bajó"), ("arrived", "rose", "subió")):
            r = (_rows_named(ac.get(part), ("name", "from_share", "to_share")) or [None])[0]
            if r:
                o((f"{r['name'].capitalize()} {verb_es} de {_pc(r['from_share'], lang)} en {ac['from']} a "
                   f"{_pc(r['to_share'], lang)} en {ac['to']}." if es else
                   f"{r['name'].capitalize()} {verb} from {_pc(r['from_share'])} in {ac['from']} to "
                   f"{_pc(r['to_share'])} in {ac['to']}."), "areas_change")
        shx = ac.get("shorts") or {}
        if _num(shx.get("from_share")) and _num(shx.get("to_share")) and \
                abs(shx["to_share"] - shx["from_share"]) >= 0.05:
            o((f"Los Shorts pasaron del {_pc(shx['from_share'], lang)} de los videos de YouTube en {shx['from']} al "
               f"{_pc(shx['to_share'], lang)} en {shx['to']}." if es else
               f"Shorts went from {_pc(shx['from_share'])} of the YouTube videos in {shx['from']} to "
               f"{_pc(shx['to_share'])} in {shx['to']}."), "areas_change")
        ps = {str(p.get("label")): p for p in _rows_named(s.get("periods"), ("label",))}
        p0, p1 = ps.get(str(ch.get("from"))), ps.get(str(ch.get("to")))
        if not ch:
            full = [p for p in _rows_named(s.get("periods"), ("label",)) if not p.get("sparse")
                    and len(p.get("themes") or []) >= 2]
            if len(full) >= 2:
                p0, p1 = full[0], full[-1]
                ch = {"from": p0["label"], "to": p1["label"]}
                st_ = [x.get("name") if isinstance(x, dict) else x for x in (s.get("stopped") or {}).get("themes") or []]
                nw_ = [x.get("name") if isinstance(x, dict) else x for x in (s.get("new") or {}).get("themes") or []]
                if st_ and nw_ and not es:
                    o(f"{st_[0]} stopped and {nw_[0]} is new.", "new", "stopped")
                tm = [x for x in themes if _num(x.get("change_vs_previous"))]
                up = max(tm, key=lambda x: x["change_vs_previous"], default=None)
                if up and up["change_vs_previous"] > 0 and not es:
                    o(f"{up['name']} grew the most, to {pc(up['share'])} of what you opened.", "themes")
        if ans is None and p0 and p1 and len(p0.get("themes") or []) >= 2 and len(p1.get("themes") or []) >= 2:
            x, y = [t["name"] for t in p0["themes"][:2]], [t["name"] for t in p1["themes"][:2]]
            ans = (f"{x[0]} y {x[1]} dominaban en {ch['from']}; en {ch['to']}, {y[0]} y {y[1]}." if es else
                   f"{x[0]} and {x[1]} led in {ch['from']}; by {ch['to']}, {y[0]} and {y[1]} did.")
        for part in ("rising", "fading"):
            r = (_rows_named(ch.get(part), ("name", "from_share", "to_share")) or [None])[0]
            if r:
                if es:
                    o(f"{r['name']} {'subió' if part == 'rising' else 'bajó'} de {_pc(r['from_share'], lang)} en "
                      f"{ch['from']} a {_pc(r['to_share'], lang)} en {ch['to']}.", "change")
                else:
                    o(f"{r['name']} {'rose' if part == 'rising' else 'fell'} from {_pc(r['from_share'])} in "
                      f"{ch['from']} to {_pc(r['to_share'])} in {ch['to']}.", "change")
        for r in _rows_named(ch.get("rising"), ("name", "peak_period", "peak_share"))[:3]:
            if str(r["peak_period"]) not in (str(ch.get("from")), str(ch.get("to"))):
                o((f"{r['name']} tuvo su punto más alto en {r['peak_period']} ({_pc(r['peak_share'], lang)})." if es
                   else f"{r['name']} peaked in {r['peak_period']} at {_pc(r['peak_share'])}."), "change")
                break
    out = {"answer": ans, "observations": obs, "so_what": sw, "offers": []}
    if moving_said:
        out["moving_said"] = moving_said
    if kind == "top" and story == "bullet":
        out["shorts_said"] = True   # round 12, pass 4 (V2): the move to Shorts is a bullet; no so-what says it again
    return out


def _grew_words(a, b):
    """How a share grew from a to b, in words the check reads as a ratio ("nearly doubled") or plainly ("grew")."""
    r = b / a if a else 0
    return ("more than tripled" if r >= 3.3 else "tripled" if r >= 2.8 else "more than doubled" if r >= 2.25 else
            "doubled" if r >= 1.95 else "nearly doubled" if r >= 1.75 else "grew")


def _moving_lead(areas, mv, pw, both=False):
    """Round 12, pass 3 fix (judge A, row 1): a top answer over a short window led by what moved, when the leader is
    one of the two areas that moved most against the span before: (the answer, "grew" / "faded" / "both": which of
    the move's two sides it says), or None."""
    if not (isinstance(mv, dict) and len(areas) >= 2 and pw):
        return None
    if not all(_num(mv.get(k)) for k in ("grew_from", "grew_to", "faded_from", "faded_to")):
        return None
    a0, a1 = areas[0], areas[1]
    pws = pw.strip()   # (its dates are said once: later sentences say it without them, see _once_spans)
    n0 = " ".join(_words(a0["name"]))
    if n0 == " ".join(_words(mv["grew"])) and both:
        return (f"{a0['name']} {_grew_words(mv['grew_from'], mv['grew_to'])} to {_pc(mv['grew_to'])} of what you "
                f"opened, from {_pc(mv['grew_from'])} in {pws}, while {mv['faded']} fell from {_pc(mv['faded_from'])} "
                f"to {_pc(mv['faded_to'])}."), "both"
    if n0 == " ".join(_words(mv["grew"])):
        return (f"{a0['name']} {_grew_words(mv['grew_from'], mv['grew_to'])} to {_pc(mv['grew_to'])} of what you "
                f"opened, from {_pc(mv['grew_from'])} in {pws}; {a1['name']} came next ({_pc(a1['share'])})."), "grew"
    if n0 == " ".join(_words(mv["faded"])):
        g = mv["grew"][:1].upper() + mv["grew"][1:]
        return (f"{a0['name']} still led with {_pc(mv['faded_to'])} of what you opened, down from "
                f"{_pc(mv['faded_from'])} in {pws}. {g} {_grew_words(mv['grew_from'], mv['grew_to'])}, from "
                f"{_pc(mv['grew_from'])} to {_pc(mv['grew_to'])}."), "both"
    return None


def _span_noun(sheet):
    """Round 12, pass 4 (V2): what one span of the window's length is called ("year", "3 months", "4 weeks")."""
    w = (sheet or {}).get("window") or {}
    a, b = _as_date(w.get("start")), _as_date(w.get("end"))
    if not (a and b):
        return None
    n = (b - a).days + 1
    if n >= 360 and (a.month, a.day) == (1, 1):
        return "year"
    words = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 8: "eight"}
    if 88 <= n <= 92:
        return "three months"   # (in words: the answer's numbers are its facts)
    if n % 7 == 0 and n // 7 in words:
        return f"{words[n // 7]} weeks"
    return None


def _into_lead(areas, into, sheet):
    """Round 12, pass 4 (V2): the answer to "what was i into ...": the biggest areas, with the themes of the window that
    peaked then (at least 1.1 times their share in any other span of its length) or were new then; None when the areas
    say too little (fewer than two)."""
    shown_ = {" ".join(_words(t.get("name") or "")) for t in (shown(sheet).get("themes") or []) if isinstance(t, dict)}
    pk = [t for t in (into.get("peaked") or []) if " ".join(_words(t.get("name") or "")) in shown_][:2]
    nw = [t for t in (into.get("new") or []) if " ".join(_words(t.get("name") or "")) in shown_][:1]
    if len(pk) == 2:
        nw = []   # (at most four numbers in an answer: two areas and two themes)
    ar = [a for a in areas if _num(a.get("share")) and a.get("name")][:2 if (pk or nw) else 3]
    if len(ar) < 2:
        return None
    a0, a1 = ar[0], ar[1]
    if a0["share"] >= 2.5 * a1["share"] and a0["share"] >= 0.25:
        head = (f"you were into {a0['name']} by far the most: {_pc(a0['share'])} of what you opened, well ahead of "
                f"{a1['name']} ({_pc(a1['share'])})")
    else:
        rest = [f"{a['name']} ({_pc(a['share'])})" for a in ar[1:]]
        head = (f"you were into {a0['name']} ({_pc(a0['share'])} of what you opened), " + " and ".join(rest)
                if len(rest) == 2 else f"you were into {a0['name']} ({_pc(a0['share'])} of what you opened) and "
                f"{rest[0]}")
    span = _span_noun(sheet)
    bits = []
    if pk and span:
        names = " and ".join(t["name"] for t in pk)
        vals = " and ".join(_pc(t["share"]) for t in pk)
        bits.append(f"your {names} watching peaked then, at {vals}, more than in any other {span}" if len(pk) == 1 else
                    f"{names} peaked then, at {vals}, more than in any other {span}")
    if nw:
        bits.append(f"{nw[0]['name']} was new then ({_pc(nw[0]['share'])})")
    return head + ("; " + "; ".join(bits) if bits else "") + "."


def _path_line(s, topic, path_only=False):
    """The so-what of a first or a last (judge, Q4: "what could I learn with that"): where the person is on the
    topic, from their own record (the sheet's "path" candidate, T5), and the saved videos on it never opened (3 or
    more) as the next step."""
    c = next((x for x in s.get("so_what_candidates") or [] if isinstance(x, dict) and x.get("kind") == "path"), None)
    path = so_what_text(c, s, topic=topic) if c else None
    if path_only:
        return path
    sv = next((x for x in s.get("so_what_candidates") or [] if isinstance(x, dict) and
               x.get("kind") in ("saved", "lapsed_saves")), None)
    if sv:
        saved = f"You saved {_fmt(sv['n'], 'en')} {sv['theme']} videos you never opened, a next step. Want them as a list?"
        return (path + " " + saved) if path else saved
    return path


def so_what_text(c, s, topic=None, lang=None):
    """Round 12, pass 2 (T5): code's own words for a so-what candidate (the writer's words when they pass the
    check are used instead). Every number is the candidate's own."""
    if not isinstance(c, dict):
        return None
    lang = lang or s.get("lang") or "en"
    if lang == "es":
        if c.get("kind") in ("saved", "lapsed_saves"):
            return f"Guardaste {_fmt(c['n'], lang)} videos de {c['theme']} que nunca abriste. ¿Te los muestro en una " \
                   f"lista?"
        return None
    k = c.get("kind")
    pw = re.sub(r"^(?:in|en)\s+", "", ((s.get("previous") or {}).get("words") or "").strip())
    if k == "path":
        topic = topic or (s.get("filters") or {}).get("topic") or "it"
        li, ll, pi, pl = _fmt(c["last_items"], "en"), c["last_label"], _fmt(c["peak_items"], "en"), c["peak_label"]
        # round 12, pass 3 fix (judge A, row 4: "It has faded: 12 in 2026, against 131 in 2023": a part of a year set
        # against a whole one with no word of it, and "It" after three cards): the subject named, the part said
        end = _as_date((s.get("window") or {}).get("end"))
        part = (f"in {ll} up to {end.day} {MONTHS[end.month - 1].capitalize()}" if end and str(end.year) == str(ll)
                and (end.month, end.day) != (12, 31) else f"in {ll}")
        return {"deeper": f"You are deeper into {topic} than ever: {li} {part}, your busiest year for it.",
                "still": f"You are still at it: {li} {part}, against {pi} in {pl}, your busiest year.",
                "faded": f"Your {topic} watching has faded: {li} {part}, against {pi} in {pl}, your busiest year "
                         f"for it."}.get(c.get("how"))
    if k == "lapsed_saves":
        return (f"{c['theme']} has faded, and you still have {_fmt(c['n'], 'en')} saved {c['theme']} videos you never "
                f"opened. Want them as a list?")
    if k == "saved":
        return f"You saved {_fmt(c['n'], 'en')} {c['theme']} videos you never opened. Want them as a list?"
    if k == "learning_faded" and _num(c.get("faded_from")) and _num(c.get("grew_from")):
        if c.get("from") and c.get("to"):   # round 12, pass 2 fix: a change's own years
            return (f"The learning side gave way: {c['faded']} fell from {_pc(c['faded_from'])} in {c['from']} to "
                    f"{_pc(c['faded_to'])} in {c['to']}, while {c['grew']} grew from {_pc(c['grew_from'])} to "
                    f"{_pc(c['grew_to'])}.")
        return (f"{c['faded']} fell from {_pc(c['faded_from'])} to {_pc(c['faded_to'])} while {c['grew']} grew from "
                f"{_pc(c['grew_from'])} to {_pc(c['grew_to'])}: the learning side gave way.")
    if k == "moving" and all(_num(c.get(x)) for x in ("grew_from", "grew_to", "faded_from", "faded_to")):
        # round 12, pass 3 (U5, row 1): what is changing, against the weeks before, as something to notice
        base = f" against {pw}" if pw else ""
        return (f"Worth noticing: {c['grew']} grew from {_pc(c['grew_from'])} to {_pc(c['grew_to'])}{base}, while "
                f"{c['faded']} fell from {_pc(c['faded_from'])} to {_pc(c['faded_to'])}.")
    if k == "moving_fall" and all(_num(c.get(x)) for x in ("faded_from", "faded_to")) and c.get("faded"):
        # round 12, pass 3 fix (judge A, row 1: "the so-what is a notice, not something to do or open"): what fell, with
        # the follow-up code takes ("only <area>")
        base = f" against {pw}" if pw else ""
        return (f"Worth noticing: {c['faded']} fell from {_pc(c['faded_from'])} to {_pc(c['faded_to'])}{base}. Say "
                f"\"only {c['faded']}\" to see what in it you watched less.")
    if k == "shorts_shift":
        whose = f"your {c['topic']} videos" if c.get("topic") else "your YouTube videos"
        return (f"Shorts went {'up' if c['direction'] == 'up' else 'down'} to {_pc(c['share'])} of {whose}, "
                f"from {_pc(c['previous_share'])}" + (f" in {pw}." if pw else " before."))
    if k == "channel_rise":
        return (f"{c['channel']} is new at the top: {_fmt(c['items'], 'en')} videos now, against "
                f"{_fmt(c['previous_items'], 'en')}" + (f" in {pw}." if pw else " before."))
    if k == "seasonal":
        return (f"{c['theme']} comes back at this time of year: in {_fmt(c['years'], 'en')} of {_fmt(c['of_years'], 'en')} "
                f"years it ran well above its share of the year.")
    return None


_SAVED_SW = re.compile(r"\bsaved?\b|\bunopened\b|\bnever opened\b|\bguardaste\b|\bguardad[oa]s?\b")


def _sw_says(sw, c, facts):
    """Round 12, pass 3 (U5): the so-what's words are about its candidate (its theme, channel or areas; Shorts for a
    Shorts shift; the topic's path for a first or a last)."""
    k = c.get("kind")
    low = _norm(sw)
    if k == "shorts_shift":
        return bool(re.search(r"\bshorts?\b|\bcortos?\b", low)) and not _SAVED_SW.search(low)
    if k == "path":
        return True
    keys = [c.get(x) for x in ("theme", "channel", "faded", "grew") if c.get(x)]
    said = set(facts.names_in(sw)[0]) | {w for w in [" ".join(_words(x)) for x in keys] if w and w in low}
    return any(" ".join(_words(x)) in said for x in keys)
_SAVED_OBS = re.compile(r"\b(?:saved|guardaste|guardad[oa]s?)\b|"   # pass 2 fix (live: "1 ... video stayed saved")
                        r"\b(?:saved|guardaste|guardad[oa]s?)\b.*\b(?:never|without opening|not opened|unopened|nunca|"
                        r"sin abrir)\b|\b(?:never|nunca) (?:opened|abriste)\b|\bsin abrir\b")


def _saved_line(sheet, said_names, facts):
    """The library's so-what for a theme the answer is about (or the question's topic), or None."""
    lang = sheet.get("lang") or "en"
    for x in _rows_named(((shown(sheet).get("library") or {}).get("saved_not_opened")), ("theme", "n")):
        key = " ".join(_words(x["theme"]))
        # a first's or a last's saved rows are on the topic's own themes: all of them are what it is about
        if sheet.get("kind") in ("first", "last") or key in said_names or key in facts.topic_keys or any(key in facts.parents.get(n, ()) or
                                                               key == _theme_of(facts, n) for n in said_names):
            if lang == "es":
                return f"Guardaste {_fmt(x['n'], lang)} videos de {x['theme']} que nunca abriste. ¿Te los muestro en " \
                       f"una lista?"
            one = x["n"] == 1
            return (f"You saved 1 {x['theme']} video you never opened. Want to see it?" if one else
                    f"You saved {_fmt(x['n'], lang)} {x['theme']} videos you never opened. Want them as a list?")
    return None


def candidates(sheet):
    """The sheet's so-what candidates (facts.py), or, for a sheet built without them (the eval's made-up sheets), the
    same rules run here on it (a theme's change read as points)."""
    c = (sheet or {}).get("so_what_candidates")
    if isinstance(c, list):
        return [x for x in c if isinstance(x, dict) and x.get("key")]
    from . import facts as F
    sh = dict(sheet or {})
    sh["themes"] = [dict(t, change_vs_previous=t["change_vs_previous"] * 100)
                    if isinstance(t, dict) and _num(t.get("change_vs_previous")) and abs(t["change_vs_previous"]) <= 1
                    else t for t in sh.get("themes") or []]
    try:
        return F._so_what_candidates(sh, sh.get("kind"), None)
    except Exception:  # noqa: BLE001 - no candidates: no so-what
        return []


SW_KINDS = {   # round 12, pass 3 (U5): a so-what is about the question's own subject
    "channels": {"channel_rise", "saved", "lapsed_saves"},
    "compare_topics": {"saved", "lapsed_saves"},
    "first": {"path", "saved", "lapsed_saves"}, "last": {"path", "saved", "lapsed_saves"},
    "day": set(),
}


def _so_what_fits(c, sheet):
    kind = (sheet or {}).get("kind")
    if ((sheet or {}).get("filters") or {}).get("without_shorts") and c.get("kind") == "shorts_shift":
        return False   # U3: with the Shorts left out, nothing is said about them
    return kind not in SW_KINDS or c.get("kind") in SW_KINDS[kind]


def _theme_of(facts, name):
    for c in facts.sheet.get("channels") or []:
        if isinstance(c, dict) and " ".join(_words(c.get("name") or "")) == name and c.get("theme"):
            return " ".join(_words(c["theme"]))
    return None


# the window's Shorts as the subject of a sentence (not one theme's "with 90% Shorts")
_SHORTS_SUBJ = re.compile(r"^(?:your |the )?shorts\b|\b(?:your |the )?shorts (?:went|rose|grew|jumped|fell|dropped|were|"
                          r"made|climbed|share|took)\b|\bshorts\b[^.;]{0,25}\bfrom\b|\b\d[\d,.]*%? (?:of (?:your|the) "
                          r"(?:\w+ )?videos )?were shorts\b|\blong videos were typically\b|\blong ones were\b|"
                          # round 12, pass 3 fix (judge A: "9 of 10 videos were Shorts" and "867 of your 1,437 videos
                          # were Shorts" beside code's "Shorts were 90% / 79% of ..."): a count of Shorts is the same fact
                          r"\b\d[\d,.]* of (?:your |the |all )?(?:\d[\d,.]* )?(?:\w+ )?videos (?:\w+ )?were shorts\b|"
                          r"\bmostly shorts\b|\bthe typical long video\b")
_MUST_SUBJECTS = [("hour", re.compile(r"\bbusiest hour\b|\bpeak(?:s|ed)? (?:at|around)\b")),
                  ("shorts", _SHORTS_SUBJ),
                  ("top_areas", re.compile(r"\bof your top \d+\b|\bwhat they are\b")),
                  ("balance", re.compile(r"\bthe gap\b|\bbalance\b"))]


def _move_dir(text):
    t = _norm(text)
    up, down = bool(_UP.search(t)), bool(_DOWN.search(t))
    return "up" if up and not down else "down" if down and not up else None


def _moves_of(text, facts):
    """The names a sentence moves, each with its direction ("X grew ..., while Y fell ...": X up, Y down)."""
    out = {}
    for part in re.split(r";|\bwhile\b|\bwhereas\b|\bbut\b|\band\b(?=[^,;]*\b(?:rose|grew|fell|faded|dropped|"
                         r"climbed|jumped|slipped)\b)|(?<=[.!?])\s", text or ""):
        d = _move_dir(part)
        if d:
            for n in facts.names_in(part)[0]:
                out.setdefault(n, d)
    return out


def _nested_move(x, others, sheet, facts):
    """Round 12, pass 3 fix: whether every move `x` says is a theme's move inside an area that `others` say moved the
    same way (one fall said twice at two levels)."""
    mine = _moves_of(x, facts)
    if not mine:
        return False
    theirs = {}
    for o in others:
        for n, d in _moves_of(o, facts).items():
            theirs.setdefault(n, d)
    area_of = {" ".join(_words(t.get("name") or "")): " ".join(_words(t.get("area") or ""))
               for t in (sheet or {}).get("themes") or [] if isinstance(t, dict) and t.get("name") and t.get("area")}
    mine = {n: d for n, d in mine.items() if not any(n != m and n in m for m in mine)}   # "sports" in "action sports"
    said = [n for n, d in mine.items() if theirs.get(n) == d or (area_of.get(n) and theirs.get(area_of[n]) == d)]
    # every move said already, or (live, row 8: "comedy rose by 6 points and gaming fell by 23 points" under an answer
    # that says gaming's fall) half of them: the bullet goes, one fact once
    return bool(said) and 2 * len(said) >= len(mine)


def _split_line(tot, lang="en"):
    """A first's or a last's Shorts against long videos. Round 12, pass 3 fix (judge A, row 4: "201 long ... and 90
    Shorts" under 300 read as a sum gone wrong): the split says what it is of (the YouTube ones, or those of known
    length) when it adds up to less than the total."""
    sh, lo, m, n = tot.get("shorts"), tot.get("long"), tot.get("long_median_min"), tot.get("items")
    if not (_num(sh) and _num(lo) and sh + lo > 0):
        return None
    tail = f", typically about {int(m)} minutes" if _num(m) and lo else ""
    yt = (tot.get("by_platform") or {}).get("youtube")
    of = ""
    if _num(n) and sh + lo < n:
        of = (f"Of the {_fmt(yt, lang)} on YouTube, " if _num(yt) and yt == sh + lo else
              f"Of the {_fmt(sh + lo, lang)} of known length, ")
    if of:
        return of + (f"{_fmt(lo, lang)} were long videos{tail}, and {_fmt(sh, lang)} Shorts." if sh else
                     f"all {_fmt(lo, lang)} were long videos, no Shorts.")
    return (f"{_fmt(lo, lang)} were long videos{tail}, and {_fmt(sh, lang)} Shorts." if sh else
            f"All {_fmt(lo, lang)} were long videos, no Shorts.")


_SMALL_TOP = re.compile(r"\b(?:the |your )?(?:biggest|top|main|leading) theme(?: now)?(?: is| was)?\b")
_COUNT_CHANGE = re.compile(r"\b(?:jump\w*|grew|rose|climb\w*|went|fell|dropp\w*|slipp\w*) (?:up |down )?from "
                           r"\d[\d,]*(?![\d.,]*%)(?: (?:videos?|in (?:19|20)\d\d))*,? to \d[\d,]*(?![\d.,]*%)")
_RANK_WORD = re.compile(r"\b(?:was|is) (?:your |the )?(?:top|biggest|leading|main|number one|most[- ]watched)\b|"
                        r"\bled (?:with|the)\b|\btopped\b")


def _leader_again(text, answer, sheet, facts):
    """Round 12, pass 3 fix: a channels answer's bullet that says again that the answer's leader led."""
    if (sheet or {}).get("kind") != "channels" or not answer:
        return False
    top = next((c for c in (sheet or {}).get("channels") or [] if isinstance(c, dict) and c.get("name")), None)
    if not top:
        return False
    k = " ".join(_words(top["name"]))
    nx, na = facts.names_in(text)[0], facts.names_in(answer)[0]
    low = _norm(text)
    first = min(nx, key=lambda n: low.find(n) if low.find(n) >= 0 else 10 ** 6) if nx else None
    return first == k and k in na and bool(_RANK_WORD.search(low))


def _usual_again(text, answer, sheet):
    mi = ((sheet or {}).get("usual") or {}).get("median_items")
    if not (_num(mi) and answer):
        return False
    rx = r"(?<![\d.,])" + re.escape(_fmt(mi, "en")) + r"(?![\d.,]*%)(?![\d,.]*\d)"
    return bool(re.search(rx, answer)) and bool(re.search(rx, text or "")) and "usual" in _norm(text)


def _split_no_base(text, sheet):
    """Round 12, pass 3 fix (judge A, row 4: "90 Shorts and 201 long videos" under "300 videos"): the Shorts and long
    counts said without what they are of, where they add up to less than the total said above them."""
    tot = (sheet or {}).get("totals") or {}
    sh, lo, n = tot.get("shorts"), tot.get("long"), tot.get("items")
    if not (_num(sh) and _num(lo) and _num(n) and sh and lo and sh + lo < n):
        return False
    nums = {int(x.replace(",", "")) for x in re.findall(r"(?<![\d.,])\d[\d,]*(?![\d.,]*%)", text or "")}
    yt = (tot.get("by_platform") or {}).get("youtube")
    return {int(sh), int(lo)} <= nums and int(sh + lo) not in nums and not (_num(yt) and int(yt) in nums)


_DAY_FILLER = re.compile(r"\bcame next\b|\bweekend (?:watching|viewing)\b|\bweekday (?:watching|viewing)\b|"
                         r"\ball (?:weekend|weekday)\b")
_FLAT = re.compile(r"\bfrom (\d+(?:[.,]\d+)?)%[^.;%]{0,80}?\bto (\d+(?:[.,]\d+)?)%")


def _flat_move(text):
    """Round 12, pass 3 fix (live: "gaming fell from 17% ... to 17%"): a move whose two values read the same."""
    return any(m.group(1) == m.group(2) for m in _FLAT.finditer(text or ""))


def fill(form, raw, sheet, chart_vals=None):
    """Round 12, fix: the checked form with what failed filled by code (see code_form). Returns the form; its
    "filled" says what code wrote ("answer", "observations", "so_what")."""
    form["filled"] = []
    held = []
    if not (isinstance(raw, dict) and isinstance(raw.get("answer"), str) and
            isinstance(raw.get("observations"), list)):
        return form
    facts = Facts(shown(sheet))
    cform = code_form(sheet)
    cf = check(cform, sheet, chart_vals=chart_vals)
    if form["answer"]:
        # round 12, pass 2: code's observations are new against the answer that is sent (the model's), not its own
        cf["observations"] = check(dict(cform, answer=form["answer"]), sheet, chart_vals=chart_vals)["observations"]
    for _w, why, _t in cf["dropped"]:
        form["dropped"].append(("code", why, None))
    if cf["answer"] and form["answer"] and sheet.get("kind") in ("first", "last") and facts.lang == "en":
        # round 12, pass 2 fix (live, row 4: "You first started watching <its date>."): the date is said by code,
        # the writer's next sentence after it
        tail = [x for x in _sentences(form["answer"])[1:] if not re.search(_DATE_RX, _norm(x))]
        topic_ = " ".join(_words((sheet.get("filters") or {}).get("topic") or ""))
        head_ = " ".join(_words(_sentences(form["answer"])[0]))
        new = " ".join([cf["answer"]] + tail) if topic_ and topic_ not in head_ else form["answer"]
        if new != form["answer"]:
            form["dropped"].append(("answer", "code_answer", form["answer"]))
            form["answer"] = new
            form["filled"].append("answer")
    if cf["answer"] and (not form["answer"] or sheet.get("kind") == "compare_topics" or
                         (sheet.get("kind") == "changed" and (sheet.get("eras") or [])) or
                         # round 12, pass 3 (U4, live, row 6: the writer's "mostly Shorts at 9 of 10" above code's
                         # "Shorts were 90% ... against about 78% on a usual day"): a day's overview is code's, its count
                         # against the usual day, and the writer's bullets are read against it
                         (sheet.get("kind") == "day" and (sheet.get("usual") or {}).get("median_items")) or
                         # round 12, pass 3 fix (judge A, row 1): the leader's move against the weeks before leads
                         bool(cform.get("moving_said"))):
        # round 12, pass 2 (T4): a change is told as eras, by code (live: "shifted from gaming and internet culture
        # toward gaming, comedy, and internet culture")
        # round 12, pass 2 (T9): a comparison's answer is code's own (the ratio in words, then the two counts): the
        # live writer garbled it ("about 9 times as many as many gaming videos")
        if form["answer"] and form["answer"] != cf["answer"]:
            form["dropped"].append(("answer", "code_answer", form["answer"]))
        form["answer"] = cf["answer"]
        form["filled"].append("answer")
        # round 12, pass 2 fix (live, row 8: "Comedy led with 14%" right after code's answer said it): the model's
        # bullets are new against the answer that is sent
        keep = [x for x in form["observations"] if _obs_more(x, form["answer"], sheet, x, facts) != "repeat"]
        held = [x for x in form["observations"] if x not in keep]   # back only if code cannot fill the minimum
        for x in held:
            form["dropped"].append(("observation", "repeat", x))
        form["observations"] = keep
    # the so-what (round 12, pass 2, T5): only one of the sheet's candidates (code proposed them, with their facts),
    # picked by the writer; never about another theme; never for 1 or 2 saved clips; none on a day's list
    names = set(facts.names_in(" ".join([form["answer"] or ""] + [x for x in form["observations"]
                                                                   if not _SAVED_OBS.search(_norm(x))]))[0])
    cands = [c for c in candidates(sheet) if _so_what_fits(c, sheet)]   # round 12, pass 3 (U5)
    by_id = {c["key"]: c for c in cands}
    if cands and not shown(sheet).get("so_what_candidates"):
        facts = Facts(dict(shown(sheet), so_what_candidates=cands))   # their numbers are the sheet's too
    pick = form.get("so_what_pick")
    chosen = by_id.get(pick) if isinstance(pick, str) else None
    sw = form.get("so_what")
    mv = next((c for c in cands if c.get("kind") == "moving"), None)
    if (cform.get("moving_said") == "story" or cform.get("shorts_said")) and form["answer"] == cf["answer"]:
        # round 12, pass 3 fix (row 8): the answer says the move to Shorts; no so-what says it again
        cands = [c for c in cands if c.get("kind") != "shorts_shift"]
        by_id = {c["key"]: c for c in cands}
        if chosen is not None and chosen.get("kind") == "shorts_shift":
            if sw:
                form["dropped"].append(("so_what", "said_by_answer", sw))
            sw, chosen = None, None
    elif cform.get("moving_said") not in (None, "into") and form["answer"] == cf["answer"] and mv is None:
        cands = [c for c in cands if c.get("kind") != "moving"]   # said on the answer before: no so-what of it
    if mv is not None and cform.get("moving_said") not in (None, "into") and form["answer"] == cf["answer"]:
        # round 12, pass 3 fix (judge A, row 1): the answer says the move; the so-what says only what it left out (what
        # fell), with the follow-up that shows it, or nothing
        if sw and chosen is not None and chosen.get("kind") == "moving":
            form["dropped"].append(("so_what", "said_by_answer", sw))
            sw, chosen = None, None
        cands = [c for c in cands if c.get("kind") != "moving"]
        by_id = {c["key"]: c for c in cands}
        if cform["moving_said"] == "grew":
            mv = dict(mv, kind="moving_fall")
            cands = [mv] + cands
            by_id[mv["key"]] = mv
        else:
            mv = None
    if mv is not None and mv.get("kind") == "moving_fall":
        if sw:
            form["dropped"].append(("so_what", "moving_first", sw))
        sw, chosen = None, mv
    elif mv is not None and (chosen is None or chosen.get("kind") != "moving"):
        # round 12, pass 3 (U5, row 1): for "the most lately" the so-what is what is changing, in code's words
        if sw:
            form["dropped"].append(("so_what", "moving_first", sw))
        sw, chosen = None, mv
    if sw and chosen is None and isinstance(pick, str) and pick in {c.get("key") for c in candidates(sheet)}:
        form["dropped"].append(("so_what", "off_subject", sw))   # a candidate not about the question's subject
        sw = None
    if sw and chosen is None:
        said = set(facts.names_in(sw)[0])
        chosen = next((c for c in cands if said & {" ".join(_words(str(c.get(k) or ""))) for k in
                                                     ("theme", "channel", "faded", "grew")}), None)
        if chosen is None and sheet.get("kind") not in ("first", "last"):
            form["dropped"].append(("so_what", "not_a_candidate", sw))
            sw = None
    if sw and chosen is not None and not _sw_says(sw, chosen, facts):
        # round 12, pass 3 (U5, live, row 8: a so-what about saved clips under the pick of the Shorts shift): the words
        # are about the candidate picked, else code says that candidate in its own words
        form["dropped"].append(("so_what", "not_its_candidate", sw))
        sw = None
    if sw and chosen is not None and _SAVED_SW.search(_norm(sw)) and chosen.get("kind") not in ("saved",
                                                                                                  "lapsed_saves"):
        form["dropped"].append(("so_what", "not_its_candidate", sw))
        sw = None
    if sw and _SAVED_SW.search(_norm(sw)):
        sw_names = set(facts.names_in(sw)[0])
        near = names | facts.topic_keys | {_theme_of(facts, n) for n in names}
        if sheet.get("kind") not in ("first", "last") and (not sw_names & near or (sw_names - near)):
            # every theme it names is one the answer is about (live: a day's so-what added a theme of another day)
            form["dropped"].append(("so_what", "unrelated", sw))
            sw, chosen = None, None
    if chosen is not None and chosen.get("kind") in ("saved", "lapsed_saves") and \
            " ".join(_words(chosen.get("theme") or "")) not in (names | facts.topic_keys |
                                                               {_theme_of(facts, n) for n in names}):
        chosen = None   # saved things on a theme the answer is not about
    if sw and chosen is not None and chosen.get("kind") not in ("saved", "lapsed_saves", "path") and \
            sw.rstrip().endswith("?"):
        # a question code cannot follow ("want to look at what changed most?"): the notice in code's words
        form["dropped"].append(("so_what", "dead_question", sw))
        sw = None
    if not sw and chosen is not None and sheet.get("kind") not in ("first", "last"):
        t = so_what_text(chosen, shown(sheet))
        if t and check_sentence(t, facts) is None:
            sw = tidy(t, facts.lang)
            form["filled"].append("so_what")
        else:
            chosen = None
    if not sw and sheet.get("kind") not in ("first", "last", "day"):
        near = names | facts.topic_keys | {_theme_of(facts, n) for n in names}
        if sheet.get("kind") == "compare_topics":   # what is inside each side is the comparison's own subject
            near |= {" ".join(_words(t.get("name") or "")) for tp in _rows_named(sheet.get("topics"), ("name",))
                     for t in _rows_named(tp.get("top_themes"), ("name",))[:2]}
        # round 12, pass 2 fix (judge A, row 1: no so-what though there were candidates): code takes the strongest
        # candidate the writer left (a saved one only on what the answer is about)
        # round 12, pass 3 (U5, row 5: three saved episodes of an entertainment series under gaming against art): a
        # saved so-what is on a theme the answer or its bullets name, for a comparison and a ranking too

        def saved_near(c):
            return c.get("kind") in ("saved", "lapsed_saves") and " ".join(_words(c.get("theme") or "")) in near
        c = next((c for c in cands if c.get("kind") == "learning_faded" or
                  (c.get("kind") == "lapsed_saves" and saved_near(c))), None) or \
            next((c for c in cands if saved_near(c)), None) or \
            next((c for c in cands if c.get("kind") in ("channel_rise", "seasonal", "shorts_shift")), None)
        t = so_what_text(c, shown(sheet)) if c else None
        if t and check_sentence(t, facts) is None:
            sw, chosen = tidy(t, facts.lang), c
            form["filled"].append("so_what")
    path = _path_line(dict(shown(sheet), so_what_candidates=cands),
                      (sheet.get("filters") or {}).get("topic") or "", path_only=True) \
        if sheet.get("kind") in ("first", "last") and facts.lang == "en" else None
    if path and check_sentence(path, facts) is None:
        # the person's path on the topic, from the record (judge, Q4: "what could I learn"), then the saved ones
        if not sw:
            sv = next((c for c in cands if c.get("kind") in ("saved", "lapsed_saves")), None)
            sw = (f"You saved {_fmt(sv['n'], 'en')} {sv['theme']} videos you never opened, a next step. Want them "
                  f"as a list?") if sv else None
            sw = sw if sw and check_sentence(sw, facts) is None else None
        also = chosen["key"] if (sw and chosen is not None) else None
        if sw and also is None:
            sv_ = next((c for c in cands if c.get("kind") in ("saved", "lapsed_saves") and
                        " ".join(_words(c.get("theme") or "")) in set(facts.names_in(sw)[0])), None)
            also = sv_["key"] if sv_ else None
        sw = tidy(path, facts.lang) + (" " + tidy(sw, facts.lang) if sw else "")
        chosen = by_id.get(next((c["key"] for c in cands if c.get("kind") == "path"), None))
        if chosen is not None and also and also != chosen["key"]:
            # round 12, pass 2 fix (judges: rows 4 and 5 both said "You saved 6 <theme> tutorials"): every
            # candidate said is kept, so the next answer says none of them again
            chosen = dict(chosen, key=chosen["key"] + "|" + also)
        form["filled"].append("so_what")
    if sw and chosen is not None and chosen.get("kind") not in ("saved", "lapsed_saves", "path") and \
            not re.search(r"\d", re.sub(r"\([^)]*\)", " ", sw)) and facts.lang == "en":
        # live, row 8: "You could compare how much more of your summer watching was Shorts than the spring before":
        # a candidate with numbers is said with them, in code's words
        t = so_what_text(chosen, shown(sheet))
        if t and check_sentence(t, facts) is None:
            form["dropped"].append(("so_what", "no_number", sw))
            sw = tidy(t, facts.lang)
    if sw and chosen is not None and chosen.get("kind") in ("saved", "lapsed_saves") and "?" not in sw and \
            sheet.get("kind") not in ("first", "last"):
        # round 12, pass 3 fix (live, math: "You saved 11 <a theme>."): saved things are said with what they are
        # and the offer code takes ("want them as a list?")
        t = so_what_text(chosen, shown(sheet))
        if t and check_sentence(t, facts) is None:
            form["dropped"].append(("so_what", "no_offer", sw))
            sw = tidy(t, facts.lang)
    if sw and chosen is not None and chosen.get("kind") == "learning_faded" and chosen.get("from") and \
            " ".join(_words(chosen.get("grew") or "")) in names and facts.lang == "en":
        # round 12, pass 2 fix (live, row 7): what grew is said above; the so-what says what gave way
        # round 12, pass 3 (U4, live, row 7: what grew was said in the answer and a bullet, then a third time here)
        t = (f"The learning side gave way: {chosen['faded']} fell from {_pc(chosen['faded_from'])} in "
             f"{chosen['from']} to {_pc(chosen['faded_to'])} in {chosen['to']}.")
        if check_sentence(t, facts) is None:
            sw = tidy(t, facts.lang)
    if sw:
        # round 12, pass 2 fix (live: "11,932 videos were Shorts, up from 4,476" above "Shorts went up to 58% ..."):
        # a bullet the so-what says goes
        swv = [v for v, p in _pct_vals(sw, facts) if p is True]
        keep = []
        for x in form["observations"]:
            xv = [v for v, p in _pct_vals(x, facts) if p is True]
            shorts_move = ((chosen is not None and chosen.get("kind") == "shorts_shift") or
                           _SHORTS_SUBJ.search(_norm(sw))) and _SHORTS_SUBJ.search(_norm(x)) and re.search(r"\d", x)
            if shorts_move or (len(xv) >= 2 and sum(any(abs(a - b) <= 1 for b in swv) for a in xv) >= 2):
                form["dropped"].append(("observation", "said_by_so_what", x))
            else:
                keep.append(x)
        form["observations"] = keep
    form["so_what_id"] = chosen["key"] if (sw and chosen) else None
    form["so_what"] = sw
    form["so_what_kind"] = chosen.get("kind") if (sw and chosen) else None   # round 12, pass 4 (V4)
    form["so_what_faded"] = chosen.get("faded") if (sw and chosen) else None
    # things saved and never opened are said in one place, the so-what line, and only on what the answer is about
    form["observations"] = [x for x in form["observations"] if not _SAVED_OBS.search(_norm(x))]
    said = _signature(" ".join([form["answer"] or "", sw or ""]), facts)
    for x in form["observations"]:
        said |= _signature(x, facts)
    # round 12, pass 2 fix (judges: what each top channel is, a day against the usual day, the balance of a
    # comparison against last year, the Shorts share of a window, all left out by the writer): code's MUST lines are
    # said whatever the writer chose, in place of its last observations
    must = []
    for mo in [x for x in cform.get("observations") or [] if isinstance(x, dict) and x.get("must")]:
        mc = check(dict(cform, answer=form["answer"] or "-", observations=[mo]), sheet, chart_vals=chart_vals)
        for x in mc["observations"]:
            sig = _signature(x, facts)
            pv = [v for v in _pct_vals(x, facts) if v[1] is True]
            sv_ = [v for v in _pct_vals(sw or "", facts) if v[1] is True]
            if pv and sv_ and all(any(abs(a - b) <= 1 for b, _ in sv_) for a, _ in pv):
                continue   # the so-what says it (live: "Shorts went up to 82%" and "Shorts were 82%")
            if sw and _SHORTS_SUBJ.search(_norm(sw)) and _SHORTS_SUBJ.search(_norm(x)):
                continue   # round 12, pass 3 (U4, live, row 8): the window's Shorts said once, in the so-what
            if not (sig and sig <= said) and x not in form["observations"]:
                must.append(x)
                said |= sig
    hours = any(re.search(r"\d\s*(?:hours?|horas?|minutes?)\b", x) for x in form["observations"] + [form["answer"] or ""])
    obs_names = set(facts.names_in(" ".join(form["observations"]))[0])
    for x in cf["observations"]:
        sig = _signature(x, facts)
        if sig and sig <= said:
            continue
        own = set(facts.names_in(x)[0])
        if own and own <= obs_names and (_UP.search(_norm(x)) or _DOWN.search(_norm(x)) or
                                         len(form["observations"]) >= OBS_MIN):
            continue   # the same names an observation already speaks of ("X grew to 6%" and "X grew from 3% to 6%")
        if len(own) >= 2 and own <= set(facts.names_in(form["answer"] or "")[0]) and \
                len(form["observations"]) >= OBS_MIN:
            continue   # round 12, pass 3 (U4, live, row 4): the channels the answer named, named again
        need = len(form["observations"]) < OBS_FILL
        length = (not hours and re.search(r"\badd(?:s)? up\b|\bsuma\b", x) and sheet.get("kind") in ("top", "channels")
                  and len(form["observations"]) < OBS_MAX)
        if need or length:
            form["observations"].append(x)
            said |= sig
            obs_names |= own
            hours = hours or bool(length)
            if "observations" not in form["filled"]:
                form["filled"].append("observations")
    if must:
        # the must line is the one said on its subject (live: two "busiest hour" bullets on a day; "Shorts made up 79%"
        # beside "Shorts were 79% of your YouTube videos")
        subj = [r for r, rx in _MUST_SUBJECTS if any(rx.search(_norm(m)) for m in must)]
        keep = []
        for x in form["observations"]:
            if x in must:
                continue
            if any(rx.search(_norm(x)) for r, rx in _MUST_SUBJECTS if r in subj):
                form["dropped"].append(("observation", "said_by_code", x))
                continue
            keep.append(x)
        # round 12, pass 3 (U4, live, row 8: "Comedy edits (6%)" in three bullets): a bullet that says a name with
        # the same share as a MUST line goes (the MUST line says it, with more), never below the minimum
        mp = set().union(*[_pairs(m, facts) for m in must]) if must else set()
        if mp:
            k2 = [x for x in keep if not (_pairs(x, facts) & mp)]
            if len(k2) + len(must) >= OBS_MIN:
                for x in keep:
                    if x not in k2:
                        form["dropped"].append(("observation", "said_by_code", x))
                keep = k2
        room = max(0, OBS_MAX - len(must))
        form["observations"] = keep[:room] + must
        form["filled"].append("must")
    # a bullet whose every number and name another bullet says goes (live, row 2: "<channel A> was the top
    # channel, and 95% of its videos were Shorts" above "<channel A> and <channel B> are almost all Shorts (95% and
    # 100%) ...")
    sigs = [{t for t in _signature(x, facts) if not re.match(r"^(?:19|20)\d\d$", t[1])}
            for x in form["observations"]]   # (years left out: "from 15% in Jan 2026 to 11%" is "from 15% to 11%")
    if len(form["observations"]) < OBS_MIN and held:
        # never at the cost of the whole answer (today's code reply would go out): a repeat comes back
        form["observations"] = held[:OBS_MIN - len(form["observations"])] + form["observations"]
        sigs = [{t for t in _signature(x, facts) if not re.match(r"^(?:19|20)\d\d$", t[1])}
                for x in form["observations"]]
    sub = [x for i, x in enumerate(form["observations"])
           if not (sigs[i] and any(t[0] == "v" for t in sigs[i]) and any(t[0] == "n" for t in sigs[i]) and
                                    any(j != i and sigs[i] <= sigs[j] and (sigs[i] != sigs[j] or j < i)
                                                    for j in range(len(sigs))))]
    if len(sub) >= OBS_MIN or len(sub) == len(form["observations"]):
        form["observations"] = sub   # (never below the minimum: today's code reply would go out)
    # round 12, pass 3 (U4, live, row 2: "X had 137 videos, ahead of A and B; 95% of its videos were Shorts" under an
    # answer that said the 137 and a code line that said the 95%): a bullet whose every number and name the answer or
    # another bullet says goes, the later one first
    obs_ = list(form["observations"])
    for i in range(len(obs_) - 1, -1, -1):
        x = obs_[i]
        if len(obs_) <= OBS_MIN:
            break
        others = " ".join([form["answer"] or ""] + [y for j, y in enumerate(obs_) if j != i])
        mine, theirs = _pct_vals(x, facts), _pct_vals(others, facts)
        nm, onm = set(facts.names_in(x)[0]), set(facts.names_in(others)[0])
        if mine and nm and nm <= onm and all(any(v == w and (p is True) == (q is True) for w, q in theirs)
                                             for v, p in mine):
            form["dropped"].append(("observation", "said_elsewhere", x))
            obs_.pop(i)
    form["observations"] = obs_
    form["_spare"] = [x for x in cf["observations"] if x not in form["observations"]]
    form["_must"] = [x for x in must if x in form["observations"]]
    return _pass4(_last_reads(form, sheet, facts), sheet, facts)


def _last_reads(form, sheet, facts):
    """Round 12, pass 3 fix: the bullets read once more against the whole answer as it will be sent (code's own
    bullets included), never below the minimum: a move whose two values read the same (live: "gaming fell from 17%
    ... to 17%"), and a theme's move inside an area whose move the answer or the so-what says, the same way (judge A,
    row 1: "a sports theme fell from 6% to 4%" under "sports fell from 16% to 9%")."""
    obs = list(form["observations"])
    day = (sheet or {}).get("kind") == "day"
    for why, bad in (("flat_move", lambda x, rest: _flat_move(x)),
                     # judges, rows 6 and "september 12": "X came next (8%)" and "the day was all weekend watching"
                     # say nothing on a day
                     ("filler", lambda x, rest: day and bool(_DAY_FILLER.search(_norm(x)))),
                     ("nested_move", lambda x, rest: _nested_move(x, rest, sheet, facts)),
                     ("split_no_base", lambda x, rest: _split_no_base(x, sheet)),
                     # live, 12 September: "39 is your usual day's median" under the answer that says it
                     ("said_by_answer", lambda x, rest: day and _usual_again(x, form["answer"], sheet)),
                     # judge A, "without shorts": "<the leader> was your top channel ..." under the answer that says it
                     ("leader_again", lambda x, rest: _leader_again(x, form["answer"], sheet, facts)),
                     # judge A, "only gaming": "jumped from 35 in 2024 to 341", a change from a count
                     ("count_change", lambda x, rest: bool(_COUNT_CHANGE.search(x or ""))),
                     # judge A, row 7: "the biggest theme now is X at 3%" says nothing (a top theme of 3% is a
                     # fragmented mix, and the sentence does not say that)
                     ("filler", lambda x, rest: bool(_SMALL_TOP.search(_norm(x or ""))) and
                      all(float(v) < 5 for v in re.findall(r"(\d+(?:\.\d+)?)%", x or ""))),
                     # live, "without shorts": "Gaming slipped from 22% in 2024", a move with one value
                     ("half_move", lambda x, rest: bool(re.search(r"\bfrom \d+(?:[.,]\d+)?%", x or "")) and
                      len(re.findall(r"\d+(?:[.,]\d+)?%", x or "")) == 1 and
                      not re.search(r"\b(?:points?|puntos?)\b", x or ""))):
        for x in list(obs):
            if len(obs) <= OBS_MIN and why != "split_no_base":
                break
            rest = [form["answer"] or "", form.get("so_what") or ""] + [y for y in obs if y != x]
            if bad(x, [form["answer"] or "", form.get("so_what") or ""] if why == "nested_move" else rest):
                form["dropped"].append(("observation", why, x))
                alt = _split_line((sheet or {}).get("totals") or {}) if why == "split_no_base" else None
                if alt and check_sentence(alt, facts) is None and alt not in obs:
                    obs.remove(x)
                    obs.append(alt)   # after the total it is of
                else:
                    obs.remove(x)
    form["observations"] = obs
    return form


# ====================================== round 12, pass 4: what the fourth reading found ============================
# V2: asked what he was into, how he watched (the typical long video, the busiest hour) is filler. V3: one fact once
# in other words too (a record and a measure said twice). V4: a so-what is a step code can take; a notice with none is
# a bullet. V6: a theme said with no share, "was led by" on a plural name.
_INTO_FILLER = re.compile(r"\bbusiest hour\b|\btypically about \d+ minutes\b|\blong (?:videos|ones) were typically\b|"
                          r"\b(?:weekday|weekend) share\b|\bof (?:your )?activity\b")
_STEP = re.compile(r"\bsay \"[^\"]+\"|\bwant (?:them|it|those|these|to (?:open|see|watch)\b)[^?]*\?|"
                   r"\b(?:quieres|te los muestro)\b[^?]*\?")
_LED_BY = re.compile(r"^(?P<n>.+?) (?:was|were|is|are) (?:led|driven|powered|carried|fu?elled|dominated) by (?P<r>.+)$")


def _claims(text, facts):
    """Round 12, pass 4 (V3): what a sentence says, as (record, measure) pairs: a sheet name with a share ("share"), a
    move ("move", either way) or a count ("count"); the window's Shorts ("shorts", by share or by count alike); the
    busiest hour ("hour"); the typical long video ("long")."""
    out = set()
    if not text:
        return out
    low = _norm(text)
    if (_SHORTS_SUBJ.search(low) or re.search(r"\b(?:moved|went) to shorts\b|\bshorts (?:were|made up)\b|"
                                            r"\bof (?:the |them |\d[\d,]* )?(?:\w+ )?(?:videos )?were shorts\b",
                                            low)) and re.search(r"\d", re.sub(_DATE_RX, " ", low)):
        out.add(("shorts", "share"))   # (with a number: "the year you moved to Shorts" points to the fact, says none)
    if re.search(r"\bbusiest hour\b", low):
        out.add(("hour", "hour"))
    if re.search(r"\blong (?:videos|ones) were typically\b|\btypical long video\b", low):
        out.add(("long", "length"))
    names, t = facts.names_in(re.sub(r"\b(?:19|20)\d\d\b", " ", re.sub(_DATE_RX, " ", low)))
    moves = _moves_of(text, facts)
    if re.search(r"\bnew\b|\bstopped\b|\bfirst (?:opened|watched|seen)\b|\bleft behind\b", low):
        out |= {(n, "new") for n in names if n not in ("shorts", "youtube", "instagram")}
    for m in re.finditer(r"\|([A-Z])\|", t):
        k = ord(m.group(1)) - 65
        if k >= len(names) or names[k] in ("shorts", "youtube", "instagram"):
            continue
        n = names[k]
        nxt = t[m.end():m.end() + 30]
        if n in moves:
            out.add((n, "move"))
        elif re.match(r"[^|]{0,24}?\d+(?:\.\d+)?\s*%", nxt):
            out.add((n, "share"))
        elif re.match(r"[^|%]{0,12}?\(?\d[\d,]*\)?(?!\s*%)", nxt):
            out.add((n, "count"))
        else:
            out.add((n, "mention"))   # a name said with no number of its own is something said too
    return out


def _half_moved(c, said):
    """V3: a bullet of moves, half of which are said already (the other claims too): one fall said twice."""
    mv = {n for n, m in c if m == "move"}
    sm = {n for n, m in said if m == "move"}
    rest = {x for x in c if x[1] != "move"}
    return bool(mv) and 2 * len(mv & sm) >= len(mv) and rest <= said


def _pass4(form, sheet, facts):
    """Round 12, pass 4: the bullets and the so-what read once more against the whole answer (never below the minimum:
    a bullet dropped below it is replaced by one of code's that says something new, else it comes back)."""
    spare = list(form.pop("_spare", None) or [])
    musts = list(form.pop("_must", None) or [])
    if facts.lang != "en" or not form.get("answer"):
        return form
    obs = list(form["observations"])
    into = (sheet or {}).get("kind") == "top" and isinstance((sheet or {}).get("into"), dict)
    # V6: "<theme> was led by A, B and C" (and no share of it said): "Behind <theme> (6% of what you opened): A, B and C"
    shares = {}
    for key in ("themes", "areas"):
        for r in _rows_named((sheet or {}).get(key), ("name", "share")):
            shares.setdefault(" ".join(_words(r["name"])), r)
            for t_ in _rows_named(r.get("themes"), ("name", "share")):
                shares.setdefault(" ".join(_words(t_["name"])), t_)
    for i, x in enumerate(obs):
        m = _LED_BY.match(x or "")
        r = shares.get(" ".join(_words(m.group("n")))) if m else None
        if r is not None and "%" not in m.group("n"):
            said_ = (n_ := " ".join(_words(m.group("n")))) and any(p_[0] == n_ for p_ in _pairs(form["answer"], facts))
            pct = "" if (_pc(r["share"]) in m.group("r") or said_) else f" ({_pc(r['share'])} of what you opened)"
            obs[i] = f"Behind {m.group('n')}{pct}: {m.group('r')}"
    said = _claims(form["answer"], facts)
    lead_names = set(facts.names_in(form["answer"])[0])
    # a record the answer names, named again with its share (or again with nothing), is the same
    said |= {(n, m) for n in lead_names for m in ("share", "mention")}
    # the chart under the bullets says its rows' shares and counts (live, row 1: "Gaming was 22% of what you opened,
    # ahead of comedy at 11% and internet culture at 9%" above the chart of those three)
    if (sheet or {}).get("kind") not in ITEM_KINDS:
        ch_ = chart(sheet, answer_level(form["answer"], sheet))[0] or ""
        for src in ("areas", "themes", "channels"):
            if ch_.startswith(CAPTIONS[src][facts.lang if facts.lang in ("en", "es") else "en"]):
                rows_ = [r for r in (sheet or {}).get(src) or [] if isinstance(r, dict) and r.get("name")][:CHART_ROWS]
                said |= {(" ".join(_words(r["name"])), "share" if src != "channels" else "count") for r in rows_}
    for x in obs:
        if x in musts:
            said |= _claims(x, facts)   # code's MUST lines say their fact first (a writer's bullet of it goes)
    keep, dropped = [], []
    swc = _claims(form.get("so_what"), facts) if _STEP.search(_norm(form.get("so_what") or "")) or \
        form.get("so_what_kind") in ("moving", "learning_faded") else set()
    for x in obs:
        c = _claims(x, facts)
        why = None
        if x in musts:
            keep.append(x)
            continue
        if into and _INTO_FILLER.search(_norm(x)) and not (c - {("hour", "hour"), ("long", "length"),
                                                                ("shorts", "share")}):
            why = "into_filler"   # V2: how he watched, said to a question about what he was into
        elif c and c <= said:
            why = "same_fact"     # V3: every record and measure of it said before, in other words
        elif c and c <= said | swc:
            why = "said_by_so_what"   # (live, 2021: "Gaming grew from 22% to 46%" above the so-what that says it)
        elif _half_moved(c, said):
            why = "same_fact"     # (live, row 8: "gaming fell by 23 points" beside "while gaming fell from 33% to 10%")
        if why:
            dropped.append((why, x))
        else:
            keep.append(x)
            said |= c
    want = max(OBS_MIN, min(OBS_FILL, len(obs)))   # (as many as code would fill to, never more than there were)
    while len(keep) < want and spare:
        x = spare.pop(0)
        c = _claims(x, facts)
        if x not in keep and not (c and c <= said) and not (into and _INTO_FILLER.search(_norm(x))):
            keep.append(x)
            said |= c
    while len(keep) < OBS_MIN and dropped:
        keep.append(dropped.pop(0)[1])   # never at the cost of the whole answer
    keep.sort(key=lambda x: obs.index(x) if x in obs else len(obs))   # (in the order they came)
    for why, x in dropped:
        form["dropped"].append(("observation", why, x))
    form["observations"] = keep
    # V4: a so-what is a step code can take, tied to what the answer named; a notice with none is a bullet
    sw = form.get("so_what")
    if sw and not _STEP.search(_norm(sw)):
        c = form.get("so_what_kind")
        faded = form.get("so_what_faded")
        if c in ("moving", "learning_faded") and faded:
            form["so_what"] = sw.rstrip() + f" Say \"only {faded}\" to see what you still open of it."
        elif _SAVED_SW.search(_norm(sw)) and (any(isinstance(x, dict) and x.get("kind") in ("saved", "lapsed_saves")
                                                   for x in (sheet or {}).get("so_what_candidates") or []) or
                                               ((sheet or {}).get("library") or {}).get("saved_not_opened")):
            form["so_what"] = sw.rstrip() + " Want them as a list?"   # "yes" lists them (code takes it)
        else:
            cl = _claims(sw, facts)
            if len(form["observations"]) < OBS_MAX and not (cl and cl <= said):
                form["observations"].append(sw)
            form["dropped"].append(("so_what", "no_step", sw))
            form["so_what"], form["so_what_id"] = None, None
    form.pop("so_what_kind", None)
    form.pop("so_what_faded", None)
    return form


# ====================================== the one function the merger wires ========================================
def _ask_time_after(sheet):
    """Round 12, pass 2 (T6): the export hint only when the question's whole window lies after the record (never on
    an answer that has one)."""
    return bool((sheet.get("cannot_see") or {}).get("reason") == "after")


def write(bot, person, sheet, now, info=None, say=None, deadline=None):
    """The history answer for one fact sheet, as message parts, or None (the caller sends today's code reply): the
    writer off, the cap reached, the model failing, the answer failing the check, or fewer than 2 observations left.
    `info` (a dict, optional) gets the run's numbers: cost, seconds, kept, dropped, prompt_version.
    `say` (round 12, merge; seam d): the notes the caller decided to say ("refresh", "friends"), decided in one place
    (history._quiet_limits) for this reply and today's code reply alike; the caller then keeps the notes said. None:
    the writer decides and keeps them itself (as built by W)."""
    info = info if info is not None else {}
    info.update(prompt_version=PROMPT_VERSION, cost=0.0, seconds=0.0, kept=0, dropped=[], used=False, called=False,
                so_what=False, offers_shown=[])
    if not on() or not isinstance(sheet, dict) or not sheet.get("kind"):
        return None
    try:
        cap = bot._over_cap(person)
        if cap:
            info["dropped"].append(("form", "cap", None))
            # round 12, pass 3 (U10): the founder met the cap while grading and saw the old code reply with no word
            # why; the trace says it ("daily cap reached")
            info["error"] = "total cap reached" if cap == "total" else "daily cap reached"
            return None
    except Exception:  # noqa: BLE001 - a cap check that fails sends the code reply, never a paid call
        return None
    t0 = time.time()
    h = person.get("handle")
    if deadline is not None and time.time() > deadline:
        # round 12, pass 2 (T14): the answer is already late (the code reply went out); no paid call for nothing
        info["dropped"].append(("form", "late", None))
        return None
    info["called"] = True
    try:
        raw, cost = call(sheet, person=h)
    except Exception as e:  # noqa: BLE001 - a failed call: today's code reply
        info.update(seconds=round(time.time() - t0, 2), error=type(e).__name__)
        return None
    _, chart_vals = chart(sheet)
    form = check(raw, sheet, chart_vals=chart_vals, strict=strict())
    kept = len(form["observations"])
    form = fill(form, raw, sheet, chart_vals)   # round 12, fix: what failed, filled by code from the sheet
    info.update(cost=cost, seconds=round(time.time() - t0, 2), kept=kept,
                dropped=form["dropped"], offers=form["offers"], filled=form.get("filled") or [])
    if not form["answer"] or len(form["observations"]) < OBS_MIN:
        return None
    lang = sheet.get("lang") or "en"
    extra, said = [], []
    if say is not None:   # round 12, merge (seam d): the caller decided, in one place for both replies
        if "refresh" in say:
            extra.append(REFRESH_SHORT[lang])
        if "friends" in say:
            extra.append(FRIENDS_LINE[lang])
    else:
        quiet = set()
        try:
            from . import history as Hs
            quiet = Hs.said_lately(bot, h, now)
        except Exception:  # noqa: BLE001 - no notes kept: the hint stays out
            quiet = {"refresh", "friends"}
        if _ask_time_after(sheet) and "refresh" not in quiet:
            extra.append(REFRESH_SHORT[lang])
            said.append("refresh")
        if FRIENDS_ASK.search(str(sheet.get("question") or "")) and "friends" not in quiet:
            extra.append(FRIENDS_LINE[lang])
            said.append("friends")
    cards = []
    if sheet.get("kind") in ITEM_KINDS:
        try:
            from .render import link_part
            view = bot.view(person["library"])
            for it in (sheet.get("items") or [])[:SHOW["items"]]:
                x = view.items.get(it.get("id")) if isinstance(it, dict) else None
                if x is not None and x.url:
                    cards.append(dict(link_part(x, " ".join(str(it.get("title") or "").split())[:90]), item=it))
        except Exception:  # noqa: BLE001 - no cards: the lines alone
            cards = []
    parts = layout(form, sheet, cards, extra)
    if said:
        try:
            from . import history as Hs
            Hs.note_said(bot, h, now, said)
        except Exception:  # noqa: BLE001
            pass
    info.update(used=True, said=said, so_what=bool(form.get("so_what")), so_what_id=form.get("so_what_id"),
                offers_shown=form.get("offers_shown") if form.get("offers_shown") is not None else
                offers_shown(sheet, form.get("offers")))
    return parts
