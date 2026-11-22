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

PROMPT_VERSION = os.environ.get("MVP_INSIGHT_PROMPT", "insight_v1")
PURPOSE = "mvp_insight"
MAX_TOKENS = 700
TEMPERATURE = 0
SEED = 7
OBS_MIN, OBS_MAX = 2, 4
OFFERS_MAX = 3
SENT_MAX = 260          # characters in one sentence
ANSWER_MAX = 330        # characters in the answer (1 or 2 sentences)
CHART_ROWS = 8
BAR_CELLS = 10
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
        if rec.get("new_in_window") is True:
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
        for k in ("totals", "previous"):
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
        for k in ("weekday_share", "weekend_share"):
            if _num(wn.get(k)):
                self.has_weekpart = True
                self.glob.fracs.append(float(wn[k]))
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
            if ent:
                self.rank[ent] = min(self.rank.get(ent, 99), i)
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

GENERIC = set("""watch watched watching rewatch rewatched rewatching opened open opening opens saved save saving saves
liked like likes view viewed views video videos vid vids clip clips short shorts long longer longest length lengths
reel reels post posts item items channel channels creator creators account accounts youtuber youtubers theme themes
topic topics subject subjects interest interests mix mixed variety kind kinds type types stuff content
share shares part parts portion slice chunk bulk majority minority rest others lot lots plenty handful couple dozen
dozens hundreds thousands grew grow grows growing growth rose rise rises rising risen climbed climb climbing jumped
jump jumps spike spiked surge surged doubled double doubling tripled triple halved half halves quarter quarters third
thirds twice times fell fall falls falling fallen dropped drop drops dropping slipped slip shrank shrink shrinking
shrunk faded fade fades fading declined decline cooled cooling quiet quieter vanished disappeared gone stopped stop
paused new newer newest fresh first start started starting began begin beginning since returned return back
steady steadily stable similar constant consistent consistently regular regularly usual usually often occasional
occasionally rarely sometimes always never still yet already now lately recently recent latest earlier earliest
last previous prior later period stretch window phase spell streak burst bursts wave day days daily week weeks
weekly month months monthly year years yearly time hour hours minute minutes min mins late evening evenings night
nights nightly morning mornings afternoon afternoons weekend weekends weekday weekdays total totals together adding
add adds added sum overall altogether combined nearly almost roughly close exactly mainly mostly largely chiefly
heavily partly top leading lead leads led ahead behind main biggest big bigger largest large larger smaller smallest
small second fourth fifth next dominated dominate dominates dominant took take takes taking overtook replaced
replace shift shifted moved move swapped switch switched turned turn focus focused came come comes coming deep
dive binge binged marathon heavy light lighter compared compare versus vs one ones thing things way something
nothing anything everything everyone whole full entire single alone apart outside inside each want wanted try
pick finish queue list lists playlist library revisit go going see look check keep set aside plan learn learning
practice practise build make follow skip cut limit trim balance worth unopened unwatched yet sitting waiting left
leaving pile ready offer show shows showed shown spread split even ratio count counts number numbers figure
picture favourite favorite pull pulled pulls draw drew drawn hold holds held stayed stay stays kept keep keeps
mean means meaning suggests suggest seems looks clear clearly bit little lot gap edge tie tied level same share
compared beat beats beating outnumbered outpaced trailing trail percent rest tail mid around amount
busiest busier busy different differ went gave give gives way extra steadier steady slightly wins win won beat
points point percent tutorial tutorials guide guides lesson lessons recipe recipes episode episodes series review
reviews explainer walkthrough highlight highlights compilation compilations vlog vlogs stream streams fan return
whole mostly spread across sessions session evenings nothing alone almost all came latest earliest kept stuck
ver vi viste vistes visto videos video nunca paso pasa pasamos te ti puntos punto por ciento sesion sesiones
yes yeah no si brought bring brings work through clips corto cortos largos largo canal canales cuenta cuentas tema temas
diferencia menor mayor ventaja gana ganan gano supera superan supero frente seguido seguida juntos juntas casi
todo toda todos todas cada uno una lideraste empezaste volviste vuelve volvio quedo quedan queda habia hubo tuviste
mientras aunque apenas solamente mucha poca
mitad tercio cuarto doble veces vez casi cerca unos unas alrededor total suman sumaban duracion horas hora minutos
dia dias semana semanas mes meses ano anos tarde tardes noche noches manana mananas fin finde semana entre
creciste crecio crecieron subio subieron bajo bajaron cayo cayeron nuevo nueva nuevos nuevas empezaste empezo
dejaste dejo parado guardaste guardado guardados abriste abierto abiertos sin aun todavia lista quieres quieres
puedes podrias probar ver revisar mayoria parte resto principal principales primero primera ultimo ultima
recientes reciente antes despues mismo igual mas menos mucho muchos poco pocos varios lleva llevan sobre todo
sobretodo destaca destacan domina dominan lidera lideran detras viene vienen ahora ultimamente entonces luego
""".split())

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
                       r"antes|nuevo|mitad|doble|desde|solo)\b")
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
        s = s.replace(".", "").replace(",", ".") if re.match(r"^\d{1,3}(?:\.\d{3})+(?:,\d+)?$", s) or "," in s else s
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


def _check(text, facts, uses=None, chart_vals=None):
    """(why it is dropped or None, how many of the sheet's facts it names)."""
    from . import profile as P
    raw = " ".join(str(text or "").split())
    if not raw:
        return "empty", 0
    if len(raw) > SENT_MAX:
        return "too_long", 0
    if _LINK.search(raw):
        return "link", 0
    if P.sensitive(raw):
        return "sensitive", 0
    r = _check_body(raw, facts, uses, chart_vals)
    return (r, 0) if isinstance(r, str) else (None, r)


def _check_body(raw, facts, uses, chart_vals):
    t = _norm(raw)
    for ph in facts.allowed_phrases:   # the window's own words (they carry where the record ends) are always fine
        t = t.replace(_norm(ph).rstrip(", "), " ")
    t = re.sub(r"where your (?:youtube |instagram )?export ends|donde termina tu exportacion(?: de \w+)?", " ", t)
    if _WATCH_TIME.search(t):
        return "watch_time"
    if _LIMITS.search(t):
        return "limits"
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
            if not any(d.weekday() == i % 7 for d in facts.dates):
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
    num_re = (r"(?<![\w.,])(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?)" if facts.lang == "es" else
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
            elif not (_near_frac(v, pool.fracs, hedged) or any(abs(v - p) <= (3 if hedged else 1) for p in pool.points)):
                return "percent"
        elif m.group(3):
            if not re.search(r"add(?:s|ed|ing)? up|in length|\blong\b|length|worth of|of videos?|total|suman|"
                             r"duracion|de videos?", t):
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
            ok = (_near_count(v, pool.counts, hedged) or (v == int(v) and _diff_ok(int(v), pool.counts)
                                                          and _RELATION.search(t))
                  or (re.search(r"\bhours?\b|\bhoras?\b", t) and
                      any(abs(v - h) <= max(0.6, h * (0.15 if hedged else 0.06)) for h in pool.hours))
                  or (topn and v <= 10 and any(L >= v for L in facts.lengths)))
            if not ok:
                return "number"
    for w, n in _NUMWORD.items():
        if re.search(r"\b" + w + r"\b", rest_n) and not (w == "once" and facts.lang == "en"):
            if n not in pool.counts and n not in facts.lengths and not _diff_ok(n, pool.counts):
                return "number_word"
            n_facts += 1
    # ---- words: a word outside the sheet and outside plain words is a made-up fact ----
    for tok in re.findall(r"[a-z]+(?:'[a-z]+)?", rest_n):
        w = tok.split("'")[0]
        if len(w) < 3 or w in STOP or w in GENERIC or _stem(w) in GENERIC or w in _NUMWORD or w in _TIME_WORD:
            continue
        if w in _MON or w in WEEKDAYS or w in WEEKDAYS_ES or w.rstrip("s") in WEEKDAYS or w in SEASONS:
            continue
        if w in ALLOWED_CAPS or w in facts.vocab or _stem(w) in facts.vocab:
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
            not any(n in facts.top for n in names):
        return "not_top"
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
        a, _ = facts.names_in(g["a"])
        b, _ = facts.names_in(g["b"])
        if a and b and a[0] in facts.items_of and b[0] in facts.items_of:
            more = facts.items_of[a[0]] > facts.items_of[b[0]]
            want_more = g.get("w") in ("more", "mas", "bigger", "busier") if order else True
            if want_more != more:
                return "comparison"
    if chart_vals and nums and all(v in chart_vals for v in nums) and not _RELATION.search(rest_n.replace("|", " ")):
        return "restates_chart"
    return n_facts


_DATE_RX = (r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+|de\s+)?(" + _MON_RE + r")\w*\.?(?:,?\s+(?:de\s+)?(\d{4}))?|"
            r"\b(" + _MON_RE + r")\w*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b(?!\d)(?:,?\s+(\d{4}))?")
_CMP = [(r"\b(?P<w>more|fewer|less|mas|menos)\s+(?P<a>.{2,60}?)\s+(?:than|que)\s+(?P<b>.{2,60}?)(?:\s(?:this|in|on|that|en|este|esta)\b|$)", 1),
        (r"(?P<a>.{2,60}?)\s+(?:was|were|had|got|fue|tuvo)\s+(?P<w>more|fewer|less|bigger|busier|mas|menos)\s+(?:than|que)\s+(?P<b>.{2,60}?)(?:\s(?:this|in|on|that|en|este|esta)\b|$)", 1),
        (r"(?P<a>.{2,60}?)\s+(?:beat|outnumbered|outpaced|overtook|ahead of)\s+(?P<b>.{2,60}?)(?:\s(?:this|in|on|that)\b|$)", 0)]


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


def _sentences(s):
    s = " ".join(str(s or "").split())
    return [x for x in re.split(r"(?<=[.!?])\s+(?=[A-Z¿¡ÁÉÍÓÚÑ0-9\"])", s) if x]


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
    if isinstance(ans, str) and ans.strip() and len(ans) <= ANSWER_MAX:
        sents = _sentences(ans)
        res = [_check(x, facts) for x in sents]
        bad = [w for w, _ in res if w]
        if not bad and sum(n for _, n in res) == 0:
            bad = ["generic"]   # an answer that names nothing of the sheet answers nothing
        if sents and not bad and len(sents) <= 3:
            out["answer"] = " ".join(sents)
        else:
            out["dropped"].append(("answer", bad[0] if bad else "shape", ans))
    else:
        out["dropped"].append(("answer", "missing" if not ans else "too_long", ans))
    obs = raw.get("observations") if isinstance(raw.get("observations"), list) else []
    seen = set()
    for o in obs[:OBS_MAX + 2]:
        text, uses = (o.get("text"), o.get("uses")) if isinstance(o, dict) else (o, None)
        if not isinstance(text, str):
            continue
        sents = _sentences(text)
        why = None if len(sents) == 1 else "two_sentences"
        why = why or check_sentence(text, facts, uses=uses if uses is not None else [], chart_vals=chart_vals)
        key = " ".join(_words(text))
        if not why and key in seen:
            why = "repeat"
        if not why and out["answer"] and key == " ".join(_words(out["answer"])):
            why = "repeat"
        if why:
            out["dropped"].append(("observation", why, text))
            continue
        seen.add(key)
        out["observations"].append(" ".join(text.split()))
    out["observations"] = out["observations"][:OBS_MAX]
    sw = raw.get("so_what")
    if isinstance(sw, str) and sw.strip():
        why = check_sentence(sw, facts) if len(_sentences(sw)) <= 2 else "too_long"
        if why:
            out["dropped"].append(("so_what", why, sw))
        else:
            out["so_what"] = " ".join(sw.split())
    offers = sheet.get("offers") or []
    for x in raw.get("offers") or []:
        if isinstance(x, str) and x in offers and x not in out["offers"]:
            out["offers"].append(x)
    out["offers"] = out["offers"][:OFFERS_MAX]
    return out


# ====================================== the chart (code only) ====================================================
_EIGHTHS = " ▏▎▍▌▋▊▉"


def bar(v, top, cells=BAR_CELLS):
    """A bar of block characters, always `cells` wide (the empty part in light shade), so the labels after it line
    up in any font where the block characters share one width."""
    if top <= 0:
        return "░" * cells
    eighths = int(round(max(0.0, min(1.0, v / top)) * cells * 8))
    if v > 0 and eighths == 0:
        eighths = 1
    full, part = divmod(eighths, 8)
    s = "█" * full + (_EIGHTHS[part] if part else "")
    return s + "░" * (cells - len(s))


def _fmt(n, lang):
    s = f"{int(n):,}"
    return s.replace(",", ".") if lang == "es" else s


def _label(s):
    s = " ".join(str(s or "").split())
    return s if len(s) <= LABEL_MAX else s[:LABEL_MAX - 1].rstrip() + "…"


CAPTIONS = {
    "themes": {"en": "Share of what you opened, by theme:", "es": "Parte de lo que abriste, por tema:"},
    "channels": {"en": "Videos opened, by channel:", "es": "Videos abiertos, por canal:"},
    "periods": {"en": "Videos opened per {unit}, with the main theme:", "es": "Videos abiertos por {unit}, con el tema principal:"},
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
        ps = ps[-CHART_ROWS:]
        unit = ("mes" if lang == "es" else "month") if re.search(r"[A-Za-z]", str(ps[0]["label"])) else \
            ("año" if lang == "es" else "year")
        has_theme = any(p.get("themes") for p in ps)
        cap = CAPTIONS["periods" if has_theme else "periods_plain"][lang].format(unit=unit)
        rows = []
        for p in ps:
            th = (p.get("themes") or [{}])[0]
            name = th.get("name") if isinstance(th, dict) else None
            rows.append((str(p["label"]), p["items"], _fmt(p["items"], lang) + (f" · {name}" if name else ""),
                         p["items"]))
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
        return CAPTIONS["windows"][lang], [(_fmt(prev["items"], lang), prev["items"], _strip_in(lb), prev["items"]),
                                           (_fmt(tot["items"], lang), tot["items"], _strip_in(la), tot["items"])]
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


def offers_line(sheet, chosen=None, lang=None):
    """One line of follow-ups in words a person would type: 'Want it without Shorts, only cooking, or by month?'.
    `chosen` (the model's pick, checked) falls back to the sheet's first offers; only the sheet's offers are said."""
    lang = lang or (sheet or {}).get("lang") or "en"
    allowed = [o for o in (sheet or {}).get("offers") or [] if isinstance(o, str)]
    picks = [o for o in (chosen or []) if o in allowed] or allowed[:2]
    phrases = []
    for o in picks[:OFFERS_MAX]:
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


def _item_line(k, it, lang):
    title = " ".join(str(it.get("title") or "").split())[:90] or ("Un video" if lang == "es" else "A video")
    ch = it.get("channel")
    d = _as_date(it.get("at"))
    bits = []
    if d:
        bits.append(f"{d.day} {(MONTHS_ES if lang == 'es' else MONTHS)[d.month - 1][:3].capitalize()}")
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


def layout(form, sheet, items_parts=None, extra_lines=()):
    """The message parts: the answer, the observations, the chart, the so-what, the extra lines (a hint said once in
    6 hours), the offers. For a day, a first or a last: the overview, the items' lines, their cards, then the rest."""
    lang = sheet.get("lang") or "en"
    kind = sheet.get("kind")
    head = [window_lead(form["answer"], sheet)]
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
        head.append("\n".join(_item_line(k, it, lang) for k, it in enumerate(items[:SHOW["items"]], 1)))
        parts = [{"type": "text", "text": "\n\n".join(head)}]
        parts += list(items_parts or [])
        if tail:
            parts.append({"type": "text", "text": "\n".join(tail)})
        return parts
    body = "\n\n".join(head + (["\n".join(tail)] if tail else []))
    return [{"type": "text", "text": body}]


# ====================================== the one function the merger wires ========================================
def _ask_time_after(sheet):
    w = sheet.get("window") or {}
    return bool(w.get("clipped"))


def write(bot, person, sheet, now, info=None):
    """The history answer for one fact sheet, as message parts, or None (the caller sends today's code reply): the
    writer off, the cap reached, the model failing, the answer failing the check, or fewer than 2 observations left.
    `info` (a dict, optional) gets the run's numbers: cost, seconds, kept, dropped, prompt_version."""
    info = info if info is not None else {}
    info.update(prompt_version=PROMPT_VERSION, cost=0.0, seconds=0.0, kept=0, dropped=[], used=False)
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
    try:
        raw, cost = call(sheet, person=h)
    except Exception as e:  # noqa: BLE001 - a failed call: today's code reply
        info.update(seconds=round(time.time() - t0, 2), error=type(e).__name__)
        return None
    _, chart_vals = chart(sheet)
    form = check(raw, sheet, chart_vals=chart_vals)
    info.update(cost=cost, seconds=round(time.time() - t0, 2), kept=len(form["observations"]),
                dropped=form["dropped"], offers=form["offers"])
    if not form["answer"] or len(form["observations"]) < OBS_MIN:
        return None
    lang = sheet.get("lang") or "en"
    extra, said = [], []
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
    info.update(used=True, said=said)
    return parts
