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

PROMPT_VERSION = os.environ.get("MVP_INSIGHT_PROMPT", "insight_v4")   # v1 to v3 stay as measured (DESIGN 19.W)
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
PERIOD_LABEL_MAX = 18   # round 12, fix: "Mar 2026 <theme>" wrapped at 430 px past about 18 characters of theme
WEEKPART_BASELINE = 0.10
SPREAD_SHARE = 0.20     # "mostly" / "centered on" only for a share of a fifth or more
BAR_CELLS = 12
LABEL_MAX = 26
# what the model is shown of a sheet (the checks read the same trimmed sheet)
SHOW = {"themes": 8, "channels": 10, "periods": 24, "topics": 6, "items": 10}
SHOW_INNER = 4          # channels under one theme, themes under one period


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

    def strip(o, depth=0):
        if isinstance(o, dict):
            r = {}
            for k, v in o.items():
                if k in ("examples", "id"):
                    continue
                if k in ("channels", "themes") and depth > 0 and isinstance(v, list):
                    v = v[:SHOW_INNER]
                r[k] = strip(v, depth + 1)
            return r
        if isinstance(o, list):
            return [strip(v, depth + 1) for v in o]
        return o
    return strip(out)


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
        if k == "length_hours":
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
        # round 12, fix: "led" / "the most" of a name first only in a list under another name (a channel first under
        # its theme) holds only where that name is said too; the order of names said with "followed by" / "then"
        self.top_level = set()  # names first in a list of the sheet's own (themes, channels, topics)
        self.inner_top = {}     # name -> the names above the lists it is first in
        self.order = {}         # name -> (list key, place) in the sheet's own lists
        self.topic_keys = set() # the question's topic(s): a list under one of them is the answer's own list
        self.long_window = False
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
        f = {k: rec[k] for k in ("items", "days", "length_hours", "share") if _num(rec.get(k))}
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
                if abs(float(wn.get("weekday_share") or 0) - 5 / 7) < WEEKPART_BASELINE:
                    continue
                self.has_weekpart = True
                self.glob.fracs.append(float(wn[k]))
        if self.has_weekpart and isinstance(wn.get("busiest_weekday"), str):
            self.busiest_weekday = wn["busiest_weekday"].lower()
        for key in ("themes", "channels", "periods", "topics", "items"):
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
            for k in ("channel", "theme", "words"):
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
            _scalars(rec, kp)
            for sub in ("channels", "themes"):
                if isinstance(rec.get(sub), list):
                    self.lengths.add(len(rec[sub]))
                    self._list(rec[sub], kp, sub, parent=ent)
            if parent and ent:   # a channel's or a period theme's numbers also belong to the entity above it
                self.entities[parent].add(_scalars(rec, Pool()))
                self.parents.setdefault(ent, set()).add(parent)

    def _change_rows(self, ch):
        """Round 12, fix (live: "Comedy edits rose from 0.1% in 2020 to 5.6% in 2026" was dropped): the "changed"
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
    r"(?:hours?|hrs?|h\b|minutes?|mins?)|watch[- ]?time|time (?:spent|watching)|\bspent\b|hours? (?:of|spent) "
    r"watching|minutes? (?:of|spent) watching|\bviste\s+(?:unas?\s+|casi\s+)?\d[\d.,]*\s*(?:horas?|minutos?)|"
    r"tiempo (?:viendo|de visualizacion)|pasaste", re.I)
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
            if not re.search(r"add(?:s|ed|ing)? up|in length|\blong\b|length|worth of|of videos?|total|suman|"
                             r"duracion|de videos?|\bsuma\b", t):
                return "hours_not_length"
            if not any(abs(v - h) <= max(0.6, h * (0.15 if hedged else 0.06)) for h in pool.hours):
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
        # round 12, fix (live: "Stand-up Maths" was dropped): a hyphenated name is its words
        parts = [x for x in re.split(r"[-&]", w) if x]
        if parts and all(x in facts.vocab or _stem(x) in facts.vocab for x in parts):
            continue
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
    periods = [n for n in names if n in facts.period_top]
    if periods and _SUPER.search(rest_n):
        if not any(facts.period_top[p] in names for p in periods if facts.period_top[p] != p):
            return "not_top"
    elif names and (_SUPER.search(rest_n) or re.search(r"\bmost of\b|\bla mayoria\b", rest_n)) and \
            not _leads_ok(facts, names):
        return "not_top"
    why = _order_claim(facts, names, rest_n) or _spread_claim(facts, names, rest_n)
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
                         r"(\d[\d,.]*)(?!\s*(?:%|percent|points?))", rest_n):
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
                     r"\bso the (?:lead|gap|difference)\b|\ba lead of \d|\beach (?:came )?from (?:just |only )?"
                     r"(?:1|one|a single)\b|"
                     r"\bcada uno con (?:1|un)\b")
_ORDER = re.compile(r"\b(?:followed by|then|ahead of|next came|after (?:it|that) came|seguid[oa]s? de|luego)\b")
_SPREAD = re.compile(r"\b(?:mostly|mainly|largely|centered on|centred on|dominated|dominant|mostly into|above all|"
                     r"sobre todo|principalmente|centrad[oa] en)\b")


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
    if shares and max(shares) < SPREAD_SHARE:
        return "spread"
    tot = facts.sheet.get("totals") or {}
    sh, lo = tot.get("shorts"), tot.get("long")
    if _num(sh) and _num(lo) and sh + lo > 0:
        if re.search(r"\b(?:mostly|mainly|largely)\s+(?:long|longer)\b", text) and lo / (sh + lo) < 0.6:
            return "spread"
        if re.search(r"\b(?:mostly|mainly|largely)\s+shorts\b", text) and sh / (sh + lo) < 0.6:
            return "spread"
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
    if len(named) >= 2:
        a, b = facts.fields[named[0]], facts.fields[named[1]]
        pairs = [(a[k], b[k]) for k in a if k in b]
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
    return [x for x in re.split(r"(?<=[.!?])\s+(?=[A-Z¿¡ÁÉÍÓÚÑ0-9\"])", s) if x]


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
            if float(top["items"]) not in said:
                return "shape"   # the channel that led, with its count: the answer to "which channels the most"
    elif kind in ("top", "day"):
        ts = _keys(sheet.get("themes"))
        if ts and (sheet.get("totals") or {}).get("items", 0) >= 3 and not any(n in ts for n in names):
            return "shape"
    elif kind == "compare_topics":
        tp = _keys(sheet.get("topics"))
        if len(tp) >= 2 and not all(t in names for t in tp[:2]):
            return "shape"
    return None


def n_numbers(text, facts):
    """How many numbers a sentence says, besides the window's own words, dates and years."""
    t = _norm(text)
    for ph in facts.allowed_phrases:
        t = t.replace(_norm(ph).rstrip(", "), " ")
    t = re.sub(_DATE_RX, " ", t)
    t = re.sub(r"\b(19[89]\d|20\d\d)\b", " ", facts.names_in(t)[1])   # "3Blue1Brown" says no number
    return len(re.findall(r"\d[\d,.]*", re.sub(r"\|[A-Z]\|", " ", t)))


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


def check(raw, sheet, chart_vals=None):
    """The form checked against the sheet: {"answer", "observations", "so_what", "offers", "dropped": [(where, why)]}.
    The answer is None when it failed."""
    s = shown(sheet)
    facts = Facts(s)
    out = {"answer": None, "observations": [], "so_what": None, "offers": [], "dropped": []}
    if not isinstance(raw, dict):
        out["dropped"].append(("form", "not_a_form", None))
        return out
    ans = raw.get("answer")
    if isinstance(ans, str) and sheet.get("kind") == "day":
        ans = _ONE_DAY_SAID.sub("", ans)   # round 12, fix: a day's "on 1 day" is left out, not the whole answer
    if isinstance(ans, str) and len(ans) > ANSWER_MAX and len(_sentences(ans)) > 1 and \
            len(_sentences(ans)[0]) <= SENT_MAX:
        out["dropped"].append(("answer_tail", "too_long", " ".join(_sentences(ans)[1:])))
        ans = _sentences(ans)[0]   # round 12, fix (live, Spanish): a long answer's first sentence may stand
    if isinstance(ans, str) and ans.strip() and len(ans) <= ANSWER_MAX:
        sents = _sentences(ans)
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
        if sents and not why and len(sents) <= 3:
            out["answer"] = _unit_before(tidy(" ".join(sents), facts.lang), sheet)
        else:
            out["dropped"].append(("answer", why or "shape", ans))
    else:
        out["dropped"].append(("answer", "missing" if not ans else "too_long", ans))
    obs = raw.get("observations") if isinstance(raw.get("observations"), list) else []
    seen = set()
    said = _signature(out["answer"] or "", facts)
    for o in obs[:OBS_MAX + 2]:
        text, uses = (o.get("text"), o.get("uses")) if isinstance(o, dict) else (o, None)
        if not isinstance(text, str):
            continue
        if sheet.get("kind") == "day":
            text = _ONE_DAY_SAID.sub("", text)
        sents = _sentences(text)
        why = None if len(sents) == 1 else "two_sentences"
        why = why or check_sentence(text, facts, uses=uses if uses is not None else [], chart_vals=chart_vals)
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
        said |= sig
        if why:
            out["dropped"].append(("observation", why, text))
            continue
        seen.add(key)
        out["observations"].append(_unit_before(tidy(" ".join(text.split()), facts.lang), sheet))
    out["observations"] = out["observations"][:OBS_MAX]
    sw = raw.get("so_what")
    if isinstance(sw, str) and sw.strip():
        why = check_sentence(sw, facts) if len(_sentences(sw)) <= 2 else "too_long"
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
    """A label cut at a word ("Motion graphics…", not "Motion graphics t…")."""
    s = " ".join(str(s or "").split())
    if len(s) <= n:
        return s
    cut = s[:n - 1].rsplit(" ", 1)[0] if " " in s[:n - 1] else s[:n - 1]
    return cut.rstrip(" ,;:-") + "…"


def _label(s, n=LABEL_MAX):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


CAPTIONS = {
    "themes": {"en": "Share of what you opened, by theme:", "es": "Parte de lo que abriste, por tema:"},
    "channels": {"en": "Videos opened, by channel:", "es": "Videos abiertos, por canal:"},
    "periods": {"en": "Videos opened per {unit} (the bar) and the main theme:",
                "es": "Videos abiertos por {unit} (la barra) y el tema principal:"},
    "periods_plain": {"en": "Videos opened per {unit}:", "es": "Videos abiertos por {unit}:"},
    "topics": {"en": "Videos opened, by topic:", "es": "Videos abiertos, por tema:"},
    "windows": {"en": "Videos opened:", "es": "Videos abiertos:"},
}
CHART_KINDS = {"top": ("themes", "channels"), "channels": ("channels",), "count": ("periods", "topics"),
               "changed": ("periods", "themes"), "compare_windows": ("windows", "themes"),
               "compare_topics": ("topics", "themes")}


def chart(sheet):
    """(text, values shown) of the small chart for the sheet's kind, or (None, set()). At most 8 rows and one caption;
    each row is a bar of the same width, then its number, then its label."""
    kind = sheet.get("kind")
    lang = sheet.get("lang") or "en"
    for src in CHART_KINDS.get(kind, ()):
        cap, rows = _rows(sheet, src, lang)
        if len(rows) >= 2:
            top = max(v for _, v, _, _ in rows) or 1
            lines = [cap] + [f"{bar(v, top)} {left} {_label(right)}".rstrip() for left, v, right, _ in rows]
            return "\n".join(lines), {x for *_, x in rows}
    return None, set()


def _rows(sheet, src, lang):
    """(caption, [(left text, value, right text, the number the row shows)])."""
    if src == "themes":
        ts = [t for t in sheet.get("themes") or [] if isinstance(t, dict) and _num(t.get("share")) and t.get("name")]
        return CAPTIONS["themes"][lang], [(f"{round(t['share'] * 100)}%", t["share"], t["name"],
                                           round(t["share"] * 100)) for t in ts[:CHART_ROWS]]
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
        tops = {((p.get("themes") or [{}])[0] or {}).get("name") for p in ps if p.get("themes")}
        # one main theme in every row says nothing per row (judge: "Minecraft PvP" 8 times): the counts instead
        has_theme = any(p.get("themes") for p in ps) and len(tops) > 1
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


def layout(form, sheet, items_parts=None, extra_lines=()):
    """The message parts: the answer, the observations, the chart, the so-what, the extra lines (a hint said once in
    6 hours), the offers. For a day, a first or a last: the overview, the items' lines, their cards, then the rest."""
    lang = sheet.get("lang") or "en"
    kind = sheet.get("kind")
    head = [_no_title_twice(window_lead(form["answer"], sheet), sheet)]
    if form["observations"]:
        head.append("\n".join("• " + o for o in form["observations"]))
    tail = []
    ch, _ = chart(sheet) if kind not in ITEM_KINDS else (None, set())
    if ch:
        head.append(ch)
    if form.get("so_what"):
        tail.append(form["so_what"])
    tail += [x for x in extra_lines if x]
    ol = offers_line(sheet, form.get("offers"), lang)
    if ol:
        tail.append(ol)
    items = [it for it in sheet.get("items") or [] if isinstance(it, dict)] if kind in ITEM_KINDS else []
    if items:
        end = _as_date((sheet.get("window") or {}).get("end"))
        head.append("\n".join(_item_line(k, it, lang, end.year if end else None)
                              for k, it in enumerate(items[:SHOW["items"]], 1)))
        parts = [{"type": "text", "text": "\n\n".join(head)}]
        parts += list(items_parts or [])
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


def code_form(sheet):
    """A form written by code from the sheet alone: {"answer", "observations": [{"text", "uses"}], "so_what"}.
    Every number and name comes from the sheet; the same check reads it before anything of it is sent."""
    s = shown(sheet)
    kind, lang = s.get("kind"), s.get("lang") or "en"
    es = lang == "es"
    f = _fmt
    tot, prev = s.get("totals") or {}, s.get("previous") or {}
    pw = (prev.get("words") or "").strip() if lang != "es" else ""   # the span before is said in English only
    themes = _rows_named(s.get("themes"), ("name", "share"))
    chans = _rows_named(s.get("channels"), ("name", "items"))
    obs, ans, sw = [], None, None

    def o(text, *uses):
        obs.append({"text": text, "uses": list(uses)})

    def shorts_long(lead=""):
        sh, lo = tot.get("shorts"), tot.get("long")
        if _num(sh) and _num(lo) and sh + lo > 0:
            if es:
                o(f"{lead}{f(sh, lang)} fueron Shorts y {f(lo, lang)} videos largos.", "totals")
            else:
                o(f"{lead}{f(sh, lang)} were Shorts and {f(lo, lang)} long videos.", "totals")

    def length_total():
        h, d = tot.get("length_hours"), tot.get("days_active")
        if not (_num(h) and h > 0 and _num(d)):
            return
        if es:
            o(f"Lo que abriste suma unas {_hrs(h, lang)} horas de video en {f(d, lang)} días.", "totals")
        else:
            t = f"What you opened adds up to about {_hrs(h)} hours of video on {f(d, lang)} days"
            if _num(prev.get("length_hours")) and prev["length_hours"] > 0 and pw:
                t += f", against about {_hrs(prev['length_hours'])} hours in {pw}"
            o(t + ".", "totals", "previous")

    def length_leader(rows, what):
        rows = [r for r in rows[:8] if _num(r.get("length_hours"))]
        if len(rows) < 2 or es:
            return
        x = max(rows, key=lambda r: r["length_hours"])
        if x is rows[0] or x["length_hours"] < rows[0]["length_hours"] * 1.2:
            return
        own = ("' videos" if x["name"].endswith("s") else "'s videos") if what == "channels" else " videos"
        o(f"By length the order changes: {x['name']}{own} add up to about {_hrs(x['length_hours'])} hours, "
          f"against about {_hrs(rows[0]['length_hours'])} hours for {rows[0]['name']}.", what)

    def theme_moves():
        ch = [t for t in themes if _num(t.get("change_vs_previous")) and _num(t.get("previous_share"))]
        up = sorted((t for t in ch if t["change_vs_previous"] >= 0.015), key=lambda t: -t["change_vs_previous"])
        down = sorted((t for t in ch if t["change_vs_previous"] <= -0.015), key=lambda t: t["change_vs_previous"])
        if up and pw:
            t = up[0]
            o((f"{t['name']} subió de {_pc(t['previous_share'], lang)} a {_pc(t['share'], lang)} frente a {pw}." if es
               else f"{t['name']} grew from {_pc(t['previous_share'])} to {_pc(t['share'])} against {pw}."), "themes")
        if down:
            t = down[0]
            o((f"{t['name']} bajó de {_pc(t['previous_share'], lang)} a {_pc(t['share'], lang)}." if es else
               f"{t['name']} fell from {_pc(t['previous_share'])} to {_pc(t['share'])}."), "themes")

    def behind(t):
        cs = _rows_named(t.get("channels"), ("name", "items"))[:2]
        if len(cs) == 2 and not es:
            o(f"Behind {t['name']}: {cs[0]['name']} ({f(cs[0]['items'], lang)} videos) and {cs[1]['name']} "
              f"({f(cs[1]['items'], lang)}).", "themes")

    if kind == "top" and len(themes) >= 2:
        t0, t1 = themes[0], themes[1]
        if t0["share"] >= SPREAD_SHARE:
            ans = (f"Sobre todo {t0['name']} ({_pc(t0['share'], lang)} de lo que abriste), luego {t1['name']} "
                   f"({_pc(t1['share'], lang)})." if es else
                   f"Mostly {t0['name']} ({_pc(t0['share'])} of what you opened), then {t1['name']} "
                   f"({_pc(t1['share'])}).")
        elif len(themes) >= 3:
            t2 = themes[2]
            ans = (f"Una mezcla amplia: primero {t0['name']} ({_pc(t0['share'], lang)}), luego {t1['name']} "
                   f"({_pc(t1['share'], lang)}) y {t2['name']} ({_pc(t2['share'], lang)})." if es else
                   f"A wide mix, led by {t0['name']} ({_pc(t0['share'])}), {t1['name']} ({_pc(t1['share'])}) and "
                   f"{t2['name']} ({_pc(t2['share'])}).")
        theme_moves()
        behind(t0)
        length_leader(themes, "themes")
        length_total()
        shorts_long()
    elif kind == "channels" and len(chans) >= 2:
        c0, c1 = chans[:2]
        topic = (s.get("filters") or {}).get("topic")
        head = (f"En {topic}, " if es else f"For {topic}, ") if topic else ""
        if len(chans) >= 3:
            c2 = chans[2]
            ans = (f"{head}{c0['name']} va primero con {f(c0['items'], lang)} videos, seguido de {c1['name']} "
                   f"({f(c1['items'], lang)}) y {c2['name']} ({f(c2['items'], lang)})." if es else
                   f"{head}{c0['name']} led with {f(c0['items'], lang)} videos, ahead of {c1['name']} "
                   f"({f(c1['items'], lang)}) and {c2['name']} ({f(c2['items'], lang)}).")
        else:
            ans = (f"{head}{c0['name']} va primero con {f(c0['items'], lang)} videos, seguido de {c1['name']} "
                   f"({f(c1['items'], lang)})." if es else
                   f"{head}{c0['name']} led with {f(c0['items'], lang)} videos, ahead of {c1['name']} "
                   f"({f(c1['items'], lang)}).")
        top5 = [c for c in chans[:5] if _num(c.get("shorts_share"))]
        sh = [c for c in top5 if c["shorts_share"] >= 0.8][:2]
        lo = [c for c in top5 if c["shorts_share"] <= 0.1][:2]
        if (sh or lo) and not es and not (s.get("filters") or {}).get("without_shorts"):
            bits = []
            if sh:
                bits.append(" and ".join(c["name"] for c in sh) + (" is" if len(sh) == 1 else " are") +
                            " almost all Shorts (" + " and ".join(_pc(c["shorts_share"]) for c in sh) + ")")
            if lo:
                bits.append(" and ".join(c["name"] for c in lo) + (" has" if len(lo) == 1 else " have") +
                            " almost no Shorts (" + " and ".join(_pc(c["shorts_share"]) for c in lo) + ")")
            o(", while ".join(bits) + ".", "channels")
        length_leader(chans, "channels")
        if not es:
            new = [c for c in _rows_named((s.get("new") or {}).get("channels"), ("name", "items"))
                   if c["name"] in {x["name"] for x in chans[:5]}]
            if new:
                o(f"{new[0]['name']} is new: first opened in this span, {f(new[0]['items'], lang)} videos.", "new")
        length_total()
    elif kind == "count" and _num(tot.get("items")) and (s.get("filters") or {}).get("topic"):
        topic = (s.get("filters") or {}).get("topic") or ""
        wt = (s.get("window_totals") or {}).get("items")
        d = tot.get("days_active")
        if es:
            ans = f"{f(tot['items'], lang)} videos de {topic} en {f(d, lang)} días" + (
                f", de {f(wt, lang)} que abriste en total." if _num(wt) else ".")
        else:
            ans = f"{f(tot['items'], lang)} {topic} videos on {f(d, lang)} days" + (
                f", out of {f(wt, lang)} you opened in all." if _num(wt) else ".")
        if _num(prev.get("items")) and pw and prev["items"] != tot["items"]:
            up = tot["items"] > prev["items"]
            o((f"Es {'más' if up else 'menos'} que los {f(prev['items'], lang)} de {pw}." if es else
               f"That is {'up' if up else 'down'} from {f(prev['items'], lang)} in {pw}."), "totals", "previous")
        if len(themes) >= 2 and not es:
            o(f"The biggest parts: {themes[0]['name']} ({_pc(themes[0]['share'])}) and {themes[1]['name']} "
              f"({_pc(themes[1]['share'])}).", "themes")
        theme_moves()
        h = tot.get("length_hours")
        sh, lo = tot.get("shorts"), tot.get("long")
        if _num(sh) and _num(lo) and _num(h) and h > 0 and not es:
            o(f"{f(sh, lang)} were Shorts and {f(lo, lang)} long videos, adding up to about {_hrs(h)} hours in "
              f"length.", "totals")
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
            t = (f"Since then you opened {f(tot['items'], lang)} {topic} videos on {f(tot['days_active'], lang)} days"
                 if kind == "first" else f"In all you opened {f(tot['items'], lang)} {topic} videos on "
                 f"{f(tot['days_active'], lang)} days")
            if _num(tot.get("length_hours")) and tot["length_hours"] > 0:
                t += f", adding up to about {_hrs(tot['length_hours'])} hours in length"
            o(t + ".", "totals")
        sh, lo = tot.get("shorts"), tot.get("long")
        if _num(sh) and _num(lo) and sh + lo > 0:
            o(f"{f(lo, lang)} were long videos and {f(sh, lang)} Shorts." if sh else
              f"All {f(lo, lang)} were long videos, no Shorts.", "totals")
        cs = [c for c in _rows_named((tp[0].get("channels") if tp else None) or s.get("channels"), ("name", "items"))
              if "@" not in c["name"]][:2]
        if len(cs) == 2:
            o(f"{cs[0]['name']} ({f(cs[0]['items'], lang)}) and {cs[1]['name']} ({f(cs[1]['items'], lang)}) are the "
              f"channels behind most of it.", "topics", "channels")
        sw = _path_line(s, topic)
    elif kind == "day" and _num(tot.get("items")):
        n, sh = tot["items"], tot.get("shorts")
        bits = f"{f(n, lang)} videos" + (f", {f(sh, lang)} of them Shorts" if _num(sh) and sh else "")
        if len(themes) >= 2 and n >= 3 and not es:
            ans = f"{bits}, led by {themes[0]['name']} ({_pc(themes[0]['share'])}) and {themes[1]['name']} " \
                  f"({_pc(themes[1]['share'])})."
        elif not es:
            ans = bits + "."
        if not es:
            h = tot.get("length_hours")
            if _num(h) and h > 0:
                o(f"Together they add up to about {_hrs(h)} hours in length.", "totals")
            bh = ((s.get("when") or {}).get("busiest_hours") or [{}])[0]
            if isinstance(bh, dict) and _num(bh.get("hour")) and n >= 3:
                if _num(bh.get("share")) and bh["share"] >= 0.5:
                    o(f"Most of it came around {_hour_words(bh['hour'])} ({_pc(bh['share'])} of the day).", "when")
                elif _num(bh.get("share")):
                    o(f"The busiest hour was {_hour_words(bh['hour'])}, with {_pc(bh['share'])} of the day.", "when")
            if chans and chans[0]["items"] >= 2:
                o(f"{chans[0]['name']} gave the most ({f(chans[0]['items'], lang)}).", "channels")
    elif kind == "compare_topics":
        tp = _rows_named(s.get("topics"), ("name", "items"))
        if len(tp) >= 2 and not es:
            a, b = tp[0], tp[1]
            big, small = (a, b) if a["items"] >= b["items"] else (b, a)
            r = big["items"] / small["items"] if small["items"] else 0
            if small["items"] and r >= 2:
                ans = (f"Much more {big['name']}: {f(big['items'], lang)} {big['name']} videos against "
                       f"{f(small['items'], lang)} {small['name']} ones, about {round(r)} times as many.")
            elif small["items"] and r >= 1.15:
                ans = (f"More {big['name']}, but not by much: {f(big['items'], lang)} {big['name']} videos against "
                       f"{f(small['items'], lang)} {small['name']} ones.")
            elif small["items"]:
                ans = (f"About even: {f(a['items'], lang)} {a['name']} videos and {f(b['items'], lang)} "
                       f"{b['name']} ones.")
            ta, tb = [x for x in a.get("themes") or [] if isinstance(x, str)], \
                [x for x in b.get("themes") or [] if isinstance(x, str)]
            if ta and tb:
                o(f"Inside {a['name']}: {' and '.join(ta[:2])}; inside {b['name']}: {' and '.join(tb[:2])}.", "topics")
            if all(_num(x.get("days")) for x in (a, b)):
                o(f"{a['name'].capitalize()} came on {f(a['days'], lang)} days, {b['name']} on {f(b['days'], lang)}.",
                  "topics")
            if all(_num(x.get("length_hours")) and x["length_hours"] > 0 for x in (a, b)):
                o(f"{a['name'].capitalize()} videos add up to about {_hrs(a['length_hours'])} hours in length, "
                  f"{b['name']} ones to about {_hrs(b['length_hours'])} hours.", "topics")
            if all(_num(x.get("shorts")) for x in (a, b)) and a["shorts"] + b["shorts"] > 0:
                o(f"{f(a['shorts'], lang)} of the {a['name']} videos were Shorts, against {f(b['shorts'], lang)} of "
                  f"the {b['name']} ones.", "topics")
    elif kind == "changed":
        ch = s.get("change") or {}
        ps = {str(p.get("label")): p for p in _rows_named(s.get("periods"), ("label",))}
        p0, p1 = ps.get(str(ch.get("from"))), ps.get(str(ch.get("to")))
        if p0 and p1 and len(p0.get("themes") or []) >= 2 and len(p1.get("themes") or []) >= 2:
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
        for part in ("rising", "fading"):   # the second of each, when the first was said already
            r = (_rows_named(ch.get(part), ("name", "from_share", "to_share"))[1:2] or [None])[0]
            if r:
                if es:
                    o(f"{r['name']} {'subió' if part == 'rising' else 'bajó'} de {_pc(r['from_share'], lang)} a "
                      f"{_pc(r['to_share'], lang)}.", "change")
                else:
                    o(f"{r['name']} {'rose' if part == 'rising' else 'fell'} from {_pc(r['from_share'])} to "
                      f"{_pc(r['to_share'])}.", "change")
        if p0 and p1 and _num(p0.get("items")) and _num(p1.get("items")) and not es:
            o(f"You opened {f(p1['items'], lang)} videos in {ch['to']}, against {f(p0['items'], lang)} in "
              f"{ch['from']}.", "periods")
        length_total()
    return {"answer": ans, "observations": obs, "so_what": sw, "offers": []}


def _path_line(s, topic, path_only=False):
    """The so-what of a first or a last (judge, Q4: "what could I learn with that"): where the person is on the
    topic, from their own record: still at it or lapsed (the last year against the busiest), and the saved videos on
    it never opened as the next step."""
    ps = _rows_named(s.get("periods"), ("label", "items"))
    lib = _rows_named((s.get("library") or {}).get("saved_not_opened"), ("theme", "n"))
    bits = []
    if len(ps) >= 2:
        last, peak = ps[-1], max(ps, key=lambda p: p["items"])
        if peak is last:
            bits.append(f"You are deeper into {topic} than ever: {_fmt(last['items'], 'en')} in {last['label']}, "
                        f"your busiest year for it")
        elif last["items"] >= 0.5 * peak["items"]:
            bits.append(f"You are still at it: {_fmt(last['items'], 'en')} in {last['label']}, against "
                        f"{_fmt(peak['items'], 'en')} in {peak['label']}, your busiest year")
        else:
            bits.append(f"It has faded: {_fmt(last['items'], 'en')} in {last['label']}, against "
                        f"{_fmt(peak['items'], 'en')} in {peak['label']}")
    path = (bits[0] + ".") if bits else None
    if path_only:
        return path
    if lib:
        x = lib[0]
        saved = f"You saved {_fmt(x['n'], 'en')} {x['theme']} videos you never opened, a next step. Want them as a list?"
        return (path + " " + saved) if path else saved
    return path


_SAVED_SW = re.compile(r"\bsaved\b|\bguardaste\b|\bguardad[oa]s?\b")
_SAVED_OBS = re.compile(r"\b(?:saved|guardaste|guardad[oa]s?)\b.*\b(?:never|without opening|not opened|unopened|nunca|"
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


def _theme_of(facts, name):
    for c in facts.sheet.get("channels") or []:
        if isinstance(c, dict) and " ".join(_words(c.get("name") or "")) == name and c.get("theme"):
            return " ".join(_words(c["theme"]))
    return None


def fill(form, raw, sheet, chart_vals=None):
    """Round 12, fix: the checked form with what failed filled by code (see code_form). Returns the form; its
    "filled" says what code wrote ("answer", "observations", "so_what")."""
    form["filled"] = []
    if not (isinstance(raw, dict) and isinstance(raw.get("answer"), str) and
            isinstance(raw.get("observations"), list)):
        return form
    facts = Facts(shown(sheet))
    cf = check(code_form(sheet), sheet, chart_vals=chart_vals)
    for _w, why, _t in cf["dropped"]:
        form["dropped"].append(("code", why, None))
    if not form["answer"] and cf["answer"]:
        form["answer"] = cf["answer"]
        form["filled"].append("answer")
    # the so-what: never twice (a bullet that says it goes), never about another theme, the code's when missing
    names = set(facts.names_in(" ".join([form["answer"] or ""] + [x for x in form["observations"]
                                                                   if not _SAVED_OBS.search(_norm(x))]))[0])
    sw = form.get("so_what")
    if sw and _SAVED_SW.search(_norm(sw)):
        sw_names = set(facts.names_in(sw)[0])
        if not sw_names & (names | facts.topic_keys | {_theme_of(facts, n) for n in names}):
            form["dropped"].append(("so_what", "unrelated", sw))
            sw = None
    path = _path_line(shown(sheet), (sheet.get("filters") or {}).get("topic") or "", path_only=True) \
        if sheet.get("kind") in ("first", "last") and facts.lang == "en" else None
    if path and check_sentence(path, facts) is None:
        # the person's path on the topic, from the record (judge, Q4: "what could I learn"), then the saved ones
        if not sw:
            sw = _saved_line(sheet, names | facts.topic_keys, facts)
            sw = sw if sw and check_sentence(sw, facts) is None else None
        sw = tidy(path, facts.lang) + (" " + tidy(sw, facts.lang) if sw else "")
        form["filled"].append("so_what")
    elif not sw:
        sw = _saved_line(sheet, names, facts)
        if sw and check_sentence(sw, facts) is None:
            sw = tidy(sw, facts.lang)
            form["filled"].append("so_what")
        else:
            sw = None
    form["so_what"] = sw
    # things saved and never opened are said in one place, the so-what line, and only on what the answer is about
    form["observations"] = [x for x in form["observations"] if not _SAVED_OBS.search(_norm(x))]
    said = _signature(" ".join([form["answer"] or "", sw or ""]), facts)
    for x in form["observations"]:
        said |= _signature(x, facts)
    hours = any(re.search(r"\d\s*(?:hours?|horas?|minutes?)\b", x) for x in form["observations"] + [form["answer"] or ""])
    obs_names = set(facts.names_in(" ".join(form["observations"]))[0])
    for x in cf["observations"]:
        sig = _signature(x, facts)
        if sig and sig <= said:
            continue
        own = set(facts.names_in(x)[0])
        if own and own <= obs_names:
            continue   # the same names an observation already speaks of ("X grew to 6%" and "X grew from 3% to 6%")
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
    return form


# ====================================== the one function the merger wires ========================================
def _ask_time_after(sheet):
    w = sheet.get("window") or {}
    return bool(w.get("clipped"))


def write(bot, person, sheet, now, info=None, say=None):
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
        if bot._over_cap(person):
            info["dropped"].append(("form", "cap", None))
            return None
    except Exception:  # noqa: BLE001 - a cap check that fails sends the code reply, never a paid call
        return None
    t0 = time.time()
    h = person.get("handle")
    info["called"] = True
    try:
        raw, cost = call(sheet, person=h)
    except Exception as e:  # noqa: BLE001 - a failed call: today's code reply
        info.update(seconds=round(time.time() - t0, 2), error=type(e).__name__)
        return None
    _, chart_vals = chart(sheet)
    form = check(raw, sheet, chart_vals=chart_vals)
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
                    cards.append(link_part(x, " ".join(str(it.get("title") or "").split())[:90]))
        except Exception:  # noqa: BLE001 - no cards: the lines alone
            cards = []
    parts = layout(form, sheet, cards, extra)
    if said:
        try:
            from . import history as Hs
            Hs.note_said(bot, h, now, said)
        except Exception:  # noqa: BLE001
            pass
    info.update(used=True, said=said, so_what=bool(form.get("so_what")),
                offers_shown=offers_shown(sheet, form.get("offers")))
    return parts
