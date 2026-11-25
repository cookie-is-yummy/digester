"""PROTOTYPE ONLY - round 12, pass 5 (the auditor): every claim of a history answer recounted from the raw records.

Four passes of the insight answers (DESIGN 19.P2 to 19.P4) each ended with a checker who found, by hand, three or four
false or wrongly based sentences the pass had added. This file does that recount by code, for a list of questions. It
shares NO code with the answer: it never imports facts, insight, history or themes. It reads the library's raw
records (corpus/items.jsonl, corpus/interactions.jsonl), the derived lengths rows (lengths-v1/lengths.jsonl) and the
derived themes rows (themes-v2/<key>/build.json and themes.jsonl) directly, and counts again with its own reading of
DESIGN 19: the person's time zone, friends' posts left out (owner_relation friend or mutual), an "opened" video is a
watch or a view event, the Short rule of 19.D (at most 61 s; at most 180 s when published on or after 15 October
2024; with no date, at most 180 s and the title's own #shorts mark), a video over 3 hours left out of length sums, a
theme's area its category as a person says it (none for "other" or a sensitive category), two themes of one shown
name counted as one.

    python3 -m mvp.eval_claims capture QUESTIONS.jsonl --out DIR [--live N]   # send, keep what went out (bot only)
    python3 -m mvp.eval_claims audit DIR [--json OUT] [--library L]           # recount every captured answer
    python3 -m mvp.eval_claims gen --library L --out FILE                     # questions from the record's areas, years

Capture sends each question through the bot in process (a console channel on MVP_HOME), the writer either live (the
first N, through the real model and the ledger) or the made-up writer of the tests (`tests/r12_writer.py`, which fills
the form from the sheet's paths, so code's own templates, MUST lines and bases are still what goes out). What is kept
per answer: the question, the sent text, the sheet as the writer was shown it (read at the model's door: the trace
keeps neither the sheet nor a sentence's paths) and the writer's form (its paths).

The audit, per answer:
1. SHEET: every number of the shown sheet recounted in the window read from the question (a mismatch beyond rounding
   with both values; the window's own dates too).
2. BASE: every percent and count of the sent text, with the phrase that says what it is of; the candidate bases
   (everything opened, YouTube, YouTube with a known length, the filtered scope, long videos, a record's own videos)
   recounted; a said base that does not give the number, or none said where the bases differ, is reported.
3. WORD: "mostly" (half), "led / top / ahead of / followed by / came next" (order), "twice / N times / doubled"
   (ratio), "peaked / more than in any other <span>" (every span of that length, sliding by a month), "new" (absent
   before by the floor), "every year" (each year), "from X to Y" (both values and the direction).
4. A summary with codes only (no title, channel, theme or area name is printed: names become T12, A3, C5f2a).

Pass 6 (the hand check of build 7a689e2 found 5 must-fix sentences the audit had missed, and 38 false flags):
- reads: a calendar month and the month before it; a follow-up's window through its chain of messages; a topic row's
  full themes (its top themes when the row is cut at 4); "new" and a count bound to their own clause; "<channel> led
  <topic>" ranked inside the topic; a chart's labels by its caption ("by area"); a year outside the window.
- classes: a first or last by its INSTANT (the sentence's channel and theme, the first card, the cards' order, a date
  with no object); a share after "Inside <record>" with no base (read as of the record); a count of the whole scope
  recounted under the filters its own words say; a change of two values of one measure (no share against a count,
  no lone value); a move in points recounted, and under 3 points reported; "of your long videos" as the videos KNOWN
  to be long; a usual day on the base of the day's own share; "you saved N" against every video saved; one fact in
  two sentences; a chart row of 90% or more first, or of 0%; a bar within half a point of its share; "the gap" where
  the ratio and the difference move apart; limits said as a sentence; a narrow topic's themes whose items do not say
  its word; a channel named whose card is hidden; more than two base phrasings; "shorts" without its capital.
- eval_claims_allow.json is read: a mismatch of an allowed shape is marked `allowed` and listed apart.
- `python3 -m mvp.eval_claims planted` runs eval/claims_planted.json (a made-up record; a defect and a clean answer
  per item): every defect flagged with its kind, nothing flagged on a clean answer.
"""
import argparse
import bisect
import hashlib
import json
import os
import re
import statistics
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

OPEN = ("watch", "view")
SAVED = ("save", "collection", "share_self", "playlist")
FRIENDS = {"friend", "mutual"}
SENSITIVE = {"money", "health", "relationships", "politics", "religion"}
AREA_SAID = {"film and tv": "film and TV", "diy and making": "DIY and making"}
# the brain's audit (SPEC 4.8): what each `how` of a tool's scope counts (SPEC 2.2's table), and my own words for the
# sensitive topic a message unlocks (an item of a sensitive theme is counted when its own text is about it)
HOW_EVENTS = {"opened": OPEN, "liked": ("like",), "saved": SAVED, "any": OPEN + ("like",) + SAVED}
UNLOCK_WORDS = {"relationships": ("dating", "date", "relationship", "relationships", "partner", "breakup"),
                "money": ("money", "stock", "stocks", "invest", "investing", "budget", "debt"),
                "health": ("health", "diagnosis", "therapy", "symptom", "symptoms", "medication"),
                "politics": ("politics", "election", "vote", "political"),
                "religion": ("religion", "faith", "church", "prayer", "bible", "god")}


def _plain(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))


def slug(name):
    """A ref's slug ("art and design" -> "art-and-design"), my own spelling of SPEC 2.2."""
    return re.sub(r"[^a-z0-9]+", "-", _plain(name).lower()).strip("-")


def channel_key(name):
    """SPEC 2.2: "c" + the first 8 hex of sha1 of the channel's name, lower-cased with every non-word character out."""
    return "c" + hashlib.sha1(re.sub(r"[\W_]+", "", _plain(name).lower()).encode("utf-8")).hexdigest()[:8]
LONG_SHORTS_FROM = "2024-10-15"
CAP_S = 3 * 3600
# DESIGN 19.D: "the title's own mark (#shorts and its spellings)"; my own pattern of those spellings
MARK = re.compile(r"#\s?(?:yt|youtube)?shorts?\b|\byoutube\s+shorts\b|\(shorts?\)|\[shorts?\]|\|\s*shorts\s*$", re.I)
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]
MON3 = {m[:3]: i + 1 for i, m in enumerate(MONTHS)} | {m: i + 1 for i, m in enumerate(MONTHS)} | {"sept": 9}
SEASON_START = {"spring": 3, "summer": 6, "fall": 9, "autumn": 9, "winter": 12}
SEASON_BEFORE = {"spring": "winter", "summer": "spring", "fall": "summer", "autumn": "summer", "winter": "fall"}
SPAN_WORDS = {"month": 1, "two months": 2, "three months": 3, "3 months": 3, "four months": 4, "six months": 6,
              "season": 3, "summer": 3, "winter": 3, "spring": 3, "fall": 3, "year": 12, "12 months": 12,
              "4 weeks": 1, "weeks": 1}
NUM_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def short_rule(length, title, published):
    """My reading of DESIGN 19.D's Short rule. None when the length is not known."""
    if not length:
        return None
    if length <= 61:
        return True
    if length <= 180:
        if published:
            return str(published) >= LONG_SHORTS_FROM
        return bool(MARK.search(title or ""))
    return False


def _stem(w):
    """Singular: berries -> berry, dishes -> dish, eggs -> egg (plurals only)."""
    if w.endswith("'s"):
        w = w[:-2]
    for suf, rep in (("ies", "y"), ("shes", "sh"), ("ches", "ch"), ("oes", "o"), ("s", "")):
        if len(w) > len(suf) + 2 and w.endswith(suf) and not w.endswith("ss"):
            return w[:-len(suf)] + rep
    return w


_TOK = re.compile(r"[^\W\d_]+")   # letter runs: "#blender3d" holds "blender"


def holds(text, phrase):
    """My reading of "the item's own text holds the topic's words" (DESIGN 19.D): whole words, singular or plural,
    and a word of 4 letters or more also at the end of a longer word; a phrase as that phrase."""
    want = [_stem(w) for w in _TOK.findall(phrase.lower())]
    if not want:
        return False
    text = unicodedata.normalize("NFKC", text or "")   # the text as it reads: "ᵃʳᵗ" is "art"
    toks = [_stem(t) for t in _TOK.findall(text.lower())]
    if len(want) > 1:
        return any(toks[i:i + len(want)] == want for i in range(len(toks) - len(want) + 1))
    w = want[0]
    raw = _TOK.findall(text.lower())
    return any(t == w or (len(w) >= 4 and t.endswith(w)) or (r.startswith(w) and r[len(w):] in ("y", "ey", "ed", "ing"))
               for t, r in zip(toks, raw))


# DESIGN 19.D: "a broad topic maps to the themes of the category it names (a small table of the words people use:
# 'games' is gaming, 'drawing' is art and design)"; my own table of those words
CATEGORY_WORDS = {"gaming": ("gaming", "games", "video games", "videogames", "gamer", "gameplay", "game"),
                  "art and design": ("art", "arts", "drawing", "painting", "design", "artwork"),
                  "music": ("music", "songs"), "comedy": ("comedy", "funny", "humor", "humour"),
                  "film and TV": ("movies", "films", "film", "tv", "shows", "series", "film and tv"),
                  "sports": ("sports", "sport"), "fitness": ("fitness", "workouts", "gym", "exercise"),
                  "food and cooking": ("food", "cooking", "recipes", "food and cooking"), "travel": ("travel",),
                  "science": ("science",), "technology": ("tech", "technology"),
                  "math": ("math", "maths", "mathematics"), "education": ("education", "learning", "studying"),
                  "history": ("history",), "internet culture": ("internet culture", "memes"),
                  "DIY and making": ("diy", "making", "diy and making")}


def code_of(kind, name):
    return kind[0].upper() + hashlib.sha1(str(name).lower().encode()).hexdigest()[:5]


# ============================================================================ the record, read again
class Library:
    """The raw records of one library, read with my own reading of DESIGN 19 (never through the bot's modules)."""

    def __init__(self, lib, derived=None, tz="UTC", now=None, themes_dir=None, hide_sensitive=False, unlock=None):
        """`hide_sensitive` (the brain's audit, SPEC 4.8; off as before): the items of a sensitive theme (its build's
        own flag, or a sensitive category) are left out of everything, as the brain's tools leave them out, except
        those whose own text is about `unlock` (my own word list, UNLOCK_WORDS)."""
        self.lib = os.path.abspath(lib)
        self.zone = ZoneInfo(tz)
        derived = derived or os.environ.get("MVP_DERIVED_HOME") or os.path.join(REPO, "data", "mvp", "derived")
        now_s = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%S")
        self.items = {}
        with open(os.path.join(self.lib, "corpus", "items.jsonl"), encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                pd = r.get("platform_data") or {}
                if pd.get("owner_relation") in FRIENDS:
                    continue   # friends' posts are never counted
                p = r.get("platform")
                handle = (pd.get("owner_handle") or "").strip().lstrip("@")
                name = (pd.get("owner_name") or "").strip()
                creator = ("@" + handle if handle and p == "instagram" else (name or handle)) or None
                dur = pd.get("duration_s")
                self.items[r["id"]] = {"p": p, "cap": " ".join((r.get("caption") or "").split()), "c": creator,
                                       "vid": pd.get("video_id") if p == "youtube" else None,
                                       "dur": dur if isinstance(dur, (int, float)) else None,
                                       "coll": [c for c in pd.get("collections") or [] if isinstance(c, str)],
                                       "media": pd.get("media_kind")}
        self.opens = defaultdict(list)      # item -> sorted [(ordinal, hour, weekday)] of watch / view events
        self.open_at = defaultdict(list)    # item -> sorted instants (UTC seconds) of the same events (pass 6, A1)
        self.saved = set()
        self.ends = {}
        self.first_open = {}
        self.acts = defaultdict(list)       # item -> sorted [(ordinal, hour, weekday, kind)] of every dated event
        with open(os.path.join(self.lib, "corpus", "interactions.jsonl"), encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                it = self.items.get(r.get("item_id"))
                if it is None or not r.get("at") or r.get("kind") == "share_friend":
                    continue
                try:
                    d = datetime.fromisoformat(r["at"])
                except ValueError:
                    continue
                d = d.astimezone(self.zone) if d.tzinfo else d
                o = d.date().toordinal()
                p = it["p"]
                self.ends[p] = max(self.ends.get(p, o), o)
                self.acts[r["item_id"]].append((o, d.hour, d.weekday(), r["kind"]))
                if r["kind"] in OPEN:
                    self.opens[r["item_id"]].append((o, d.hour, d.weekday()))
                    self.open_at[r["item_id"]].append((d if d.tzinfo else d.replace(tzinfo=self.zone)).timestamp())
                elif r["kind"] in SAVED:
                    self.saved.add(r["item_id"])
        for i in self.opens:
            self.opens[i].sort()
            self.open_at[i].sort()
        for i in self.acts:
            self.acts[i].sort()
        self.open_days = {i: [e[0] for e in ev] for i, ev in self.opens.items()}
        # ---- lengths (the derived rows still inside their 30 days; the corpus's own duration when no row)
        rows = {}
        lp = os.path.join(derived, "lengths-v1", "lengths.jsonl")
        if os.path.exists(lp):
            with open(lp, encoding="utf-8") as f:
                for line in f:
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    if str(r.get("refresh_by") or "") > now_s:
                        rows[r["video_id"]] = (r.get("length_s"), r.get("published"))
        self.length, self.short = {}, {}
        for i, it in self.items.items():
            if it["p"] != "youtube":
                continue
            if it["vid"] in rows:
                ln, pub = rows[it["vid"]]
            else:
                ln, pub = it["dur"], None
            self.length[i] = ln
            self.short[i] = short_rule(ln, it["cap"], pub)
        # ---- themes (the derived rows) and areas
        self.theme_of, self.area_of, self.theme_names = {}, {}, {}
        self.theme_by_id, self.sensitive_items, self.hidden_items = {}, set(), set()
        tdir = themes_dir or self._themes_dir(derived)
        if tdir:
            b = json.load(open(os.path.join(tdir, "build.json"), encoding="utf-8"))
            fields = {f["id"]: f for f in b.get("fields") or []}
            themes = {t["id"]: t for t in b.get("themes") or []}
            canon_name = {}
            for tid in sorted(themes):
                t = themes[tid]
                if t.get("sensitive") or not t.get("name"):
                    continue
                canon_name[tid] = t["name"]
            first = {}
            for tid in sorted(canon_name):
                first.setdefault(canon_name[tid].lower(), tid)
            area = {}
            for tid, nm in canon_name.items():
                c = first[nm.lower()]
                cat = themes[c].get("category") or (fields.get(themes[c].get("field")) or {}).get("category")
                area[tid] = None if (not cat or cat == "other" or cat in SENSITIVE) else AREA_SAID.get(cat, cat)
            # the brain's refs: theme:<id> names the theme of that id (two themes of one shown name are one)
            self.theme_by_id = {tid: nm.lower() for tid, nm in canon_name.items()}
            sens_themes = {tid for tid, t in themes.items() if t.get("sensitive") or (
                (t.get("category") or (fields.get(t.get("field")) or {}).get("category")) in SENSITIVE)}
            with open(os.path.join(tdir, "themes.jsonl"), encoding="utf-8") as f:
                for line in f:
                    r = json.loads(line)
                    t = r.get("theme")
                    if r.get("item_id") in self.items and t in sens_themes:
                        self.sensitive_items.add(r["item_id"])
                    if r.get("item_id") in self.items and t in canon_name:
                        nm = canon_name[t]
                        self.theme_of[r["item_id"]] = nm.lower()
                        self.theme_names[nm.lower()] = canon_name[first[nm.lower()]]
                        if area.get(t):
                            self.area_of[r["item_id"]] = area[t]
        if hide_sensitive:
            self._hide(unlock)
        self.said_themes = {}   # a topic's themes as the answer's sheet lists them (set per answer by Ctx)
        self.month_items = defaultdict(set)   # (year, month) -> items opened then (the sliding spans of "peaked")
        for i, ds in self.open_days.items():
            for o in ds:
                d = date.fromordinal(o)
                self.month_items[(d.year, d.month)].add(i)
        self.newest = max(self.ends.values()) if self.ends else None
        self.oldest = min((ev[0][0] for ev in self.opens.values()), default=None)

    def _themes_dir(self, derived):
        root = os.path.join(derived, "themes-v2")
        key = hashlib.sha1(os.path.realpath(self.lib).encode()).hexdigest()[:12]
        if os.path.exists(os.path.join(root, key, "build.json")):
            return os.path.join(root, key)
        subs = [d for d in (os.listdir(root) if os.path.isdir(root) else [])
                if os.path.exists(os.path.join(root, d, "build.json"))]
        return os.path.join(root, subs[0]) if len(subs) == 1 else None

    def _hide(self, unlock):
        """Leave the items of a sensitive theme out of everything (the brain's audit), but those about `unlock`."""
        words = UNLOCK_WORDS.get(unlock or "", ())
        for i in sorted(self.sensitive_items):
            it = self.items.get(i)
            if it is None or (words and any(holds(it["cap"], w) for w in words)):
                continue
            self.hidden_items.add(i)
            for d in (self.items, self.opens, self.open_at, self.open_days, self.acts, self.theme_of, self.area_of):
                d.pop(i, None)
            self.saved.discard(i)

    # ---------------------------------------------------------------- the brain's scopes (SPEC 2.2, 4.8)
    def how_events(self, how):
        """({item: [(ordinal, hour, weekday)]}, {item: [ordinals]}) of the events a kind of `how` counts: opened (a
        watch or a view), liked, saved (a save, a collection, a self share, a playlist) or any of them."""
        if how in (None, "opened", "watched"):
            return self.opens, self.open_days
        memo = self.__dict__.setdefault("_how", {})
        if how not in memo:
            kinds = HOW_EVENTS[how]
            ev = {}
            for i, acts in self.acts.items():
                e = [(o, h, wd) for o, h, wd, k in acts if k in kinds]
                if e:
                    ev[i] = e
            memo[how] = (ev, {i: [x[0] for x in e] for i, e in ev.items()})
        return memo[how]

    def in_ref(self, i, ref):
        """Whether item i is in a ref of the brain's tools, by my own reading of each form: area:<slug> (my areas),
        theme:<id> (the build's id, its shown name), channel:<key> (c + sha1 of the name squashed), collection:<slug>,
        words:<text> (my own `holds` over the item's text)."""
        form, _, val = (ref or "").partition(":")
        it = self.items[i]
        if form == "area":
            return slug(self.area_of.get(i) or "") == val and bool(val)
        if form == "theme":
            try:
                nm = self.theme_by_id.get(int(val))
            except ValueError:
                return False
            return nm is not None and self.theme_of.get(i) == nm
        if form == "channel":
            return bool(it["c"]) and channel_key(it["c"]) == val
        if form == "collection":
            return any(slug(c) == val for c in it.get("coll") or [])
        if form == "words":
            return bool(val) and holds(it["cap"], val)
        return False

    def is_short_or_reel(self, i):
        it = self.items[i]
        return (it["p"] == "youtube" and self.short.get(i) is True) or (
            it["p"] == "instagram" and it.get("media") in ("reel", "video"))

    # ---------------------------------------------------------------- scopes
    def scope(self, a, b, f=None):
        """{item: [(ordinal, hour, weekday)] of opens in [a, b]} under the filters f (topic, channel, without
        Shorts, platform; for the brain's audit also only_refs, exclude_refs, short and how)."""
        f = f or {}
        out = {}
        evs, days = self.how_events(f.get("how"))
        for i, ds in days.items():
            lo = bisect.bisect_left(ds, a) if a is not None else 0
            hi = bisect.bisect_right(ds, b) if b is not None else len(ds)
            if lo >= hi:
                continue
            if f and not self.passes(i, f):
                continue
            ev = evs[i][lo:hi]
            if f.get("weekday") is not None:   # pass 6, second round: "on sundays" (0 Monday); "weekday_not": the rest
                ev = [e for e in ev if e[2] == f["weekday"]]
            elif f.get("weekday_not") is not None:
                ev = [e for e in ev if e[2] != f["weekday_not"]]
            if ev:
                out[i] = ev
        return out

    def passes(self, i, f):
        it = self.items[i]
        if f.get("platform") and it["p"] != f["platform"]:
            return False
        # pass 6, second round (the hand check: all 234 sheet flags on 30 answers were on the 7 without-Shorts ones, the
        # not-known-Short set against the sheet's known-long set): "without Shorts" is the YouTube videos KNOWN to be
        # long (DESIGN 19.P6, X6); a video of no known length may be a Short and is left out
        if f.get("without_shorts") and (it["p"] != "youtube" or self.short.get(i) is not False):
            return False
        if f.get("channel") and it["c"] != f["channel"]:
            return False
        if f.get("only_refs") and not any(self.in_ref(i, r) for r in f["only_refs"]):
            return False
        if f.get("exclude_refs") and any(self.in_ref(i, r) for r in f["exclude_refs"]):
            return False
        if f.get("short") and not self.is_short_or_reel(i):
            return False
        if f.get("topic"):
            if not self.on_topic(i, f["topic"], f.get("topic_themes") or ()) and \
                    not any(holds(it["cap"], w) for w in f.get("topic_also") or ()):
                return False
        return True

    def topic_themes(self, words, said=()):
        """The themes a topic counts: those of the area its word names (my table above), those the sheet lists for it
        (taken as given: the narrower mapping of themes.for_topic is not recounted), lower-cased."""
        key = (words.lower(), tuple(sorted(t.lower() for t in said)))
        memo = self.__dict__.setdefault("_tt", {})
        if key not in memo:
            out = {t.lower() for t in said if t != "(none)"}
            w = words.lower().strip()
            # the sheet's list (filters.topic_themes, or a topic row's themes with its top_themes) is taken as given;
            # a word that names an area also holds that area's themes (pass 6, A3: no longer a guess from a list of 4)
            if True:
                for area, ws in CATEGORY_WORDS.items():
                    if w in ws or w == area.lower():
                        out |= {self.theme_of[i] for i in self.area_of if self.area_of[i] == area and
                                i in self.theme_of}
            memo[key] = out
        return memo[key]

    def on_topic(self, i, words, themes):
        th = self.theme_of.get(i)
        themes = tuple(themes) + tuple(self.said_themes.get(words.lower(), ()))
        if th is not None and th in self.topic_themes(words, themes):
            return True
        memo = self.__dict__.setdefault("_holds", {})
        k = (i, words)
        if k not in memo:
            memo[k] = holds(self.items[i]["cap"], words)
        return memo[k]

    def member(self, i, ent):
        """Whether item i belongs to an entity: (kind, name)."""
        k, n = ent
        if k == "theme":
            return self.theme_of.get(i) == n.lower()
        if k == "area":
            return self.area_of.get(i) == n
        if k == "channel":
            return self.items[i]["c"] == n
        if k == "shorts":
            return self.items[i]["p"] == "youtube" and self.short.get(i) is True
        if k == "long":
            return self.items[i]["p"] == "youtube" and self.short.get(i) is False
        if k == "topic":
            return self.on_topic(i, n, self.said_themes.get(n.lower(), ()))
        if k == "all":
            return True
        return False

    def days(self, sc):
        return len({e[0] for ev in sc.values() for e in ev})

    def shorts_long(self, ids):
        s = sum(1 for i in ids if self.items[i]["p"] == "youtube" and self.short.get(i) is True)
        lo = sum(1 for i in ids if self.items[i]["p"] == "youtube" and self.short.get(i) is False)
        return s, lo

    def known(self, ids):
        return [i for i in ids if self.items[i]["p"] == "youtube" and self.short.get(i) is not None]

    def first_watch(self, creator):
        ds = [self.open_days[i][0] for i in self.open_days if self.items[i]["c"] == creator]
        return min(ds) if ds else None


# ============================================================================ the window, read from the question
def _d(o):
    return date.fromordinal(o) if o is not None else None


_CLAUSE = re.compile(r";|:|\bwhile\b|\bwhereas\b|\bbut\b|,\s*and\b|—|\s-\s")


def _clause_start(low, at):
    """Where the clause holding position `at` starts (after the last ';', ':', 'while', 'but', ', and', dash)."""
    st = 0
    for m in _CLAUSE.finditer(low, 0, at):
        st = m.end()
    return st


def season_bounds(name, year):
    m = SEASON_START[name]
    a = date(year, m, 1)
    b_m, b_y = (m + 2, year) if m + 2 <= 12 else (m + 2 - 12, year + 1)
    b = (date(b_y, b_m + 1, 1) if b_m < 12 else date(b_y + 1, 1, 1)) - timedelta(days=1)
    return a, b


def _month_end(y, m):
    return (date(y, m + 1, 1) if m < 12 else date(y + 1, 1, 1)) - timedelta(days=1)


def _whole_month(spec):
    try:
        a, b = date.fromisoformat(spec["start"]), date.fromisoformat(spec["end"])
    except (KeyError, TypeError, ValueError):
        return False
    return a.day == 1 and (a.year, a.month) == (b.year, b.month) and b == _month_end(a.year, a.month)


def read_window(text, lib, today):
    """My own reading of the question's window (DESIGN 19.D's words): a spec dict."""
    t = " " + text.lower().replace("’", "'") + " "
    years = [int(y) for y in re.findall(r"\b(20\d\d)\b", t)]
    m = re.search(r"\b(summer|winter|spring|fall|autumn) (?:of )?(20\d\d)\b", t)
    if m:
        return {"kind": "season", "season": m.group(1), "year": int(m.group(2))}
    if re.search(r"\b(?:from|between) 20\d\d (?:to|and) 20\d\d\b|\b20\d\d (?:vs\.?|versus) 20\d\d\b", t) and \
            len(years) >= 2:
        return {"kind": "years", "from": years[0], "to": years[1]}
    m = re.search(r"\b(?:since|desde) (?:el )?(20\d\d)\b", t)
    if m:
        return {"kind": "since", "year": int(m.group(1))}
    m = re.search(r"\b(?:the )?(?:last|past) (\d+|two|three|four|six) (month|week|day)s?\b", t)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else NUM_WORDS[m.group(1)]
        days = {"month": 30, "week": 7, "day": 1}[m.group(2)] * n
        return {"kind": "last_days", "days": days}
    if re.search(r"\blately\b|\bthese days\b|\bright now\b|\brecently\b", t):
        return {"kind": "lately"}
    if re.search(r"\bthis year\b|\beste a[nñ]o\b", t):
        return {"kind": "this_year"}
    m = re.search(r"\bon (" + "|".join(MON3) + r")\.? (\d{1,2})\b", t)
    if m:
        return {"kind": "day", "month": MON3[m.group(1)], "day": int(m.group(2))}
    # pass 6 (A3): a calendar month, "in march 2024" or "march 2024"; "in march" alone is the latest March begun
    m = re.search(r"(?<!\d )\b(" + "|".join(MONTHS) + r"|sept?|oct|nov|dec|jan|feb|mar|apr|jun|jul|aug) (20\d\d)\b", t)
    if m:
        return {"kind": "month", "month": MON3[m.group(1)], "year": int(m.group(2))}
    m = re.search(r"\b(?:in|during|for) (" + "|".join(x for x in MONTHS if x != "may") + r")\b(?! \d)", t)
    if m:
        mo = MON3[m.group(1)]
        return {"kind": "month", "month": mo, "year": today.year if mo <= today.month else today.year - 1}
    if years:
        return {"kind": "year", "year": years[0]}
    return {"kind": "all"}


def resolve(spec, lib, today):
    """(start, end, previous (start, end) or None, label) as ordinals, clipped to the record."""
    newest, oldest = lib.newest, lib.oldest
    k = spec.get("kind")
    prev = None
    if k == "lately":
        b = newest
        a = b - 27
        prev = (a - 28, a - 1)
    elif k == "last_days":
        n = int(spec["days"])
        b = newest
        a = b - (n - 1)
        prev = (a - n, a - 1)
    elif k == "this_year":
        y = today.year
        a, b = date(y, 1, 1).toordinal(), min(today.toordinal(), newest)
        bb = date.fromordinal(b)
        try:
            pb = bb.replace(year=y - 1)
        except ValueError:
            pb = bb.replace(year=y - 1, day=28)
        prev = (date(y - 1, 1, 1).toordinal(), pb.toordinal())
    elif k == "year":
        y = int(spec["year"])
        a, b = date(y, 1, 1).toordinal(), min(date(y, 12, 31).toordinal(), newest)
        if b == date(y, 12, 31).toordinal():
            prev = (date(y - 1, 1, 1).toordinal(), date(y - 1, 12, 31).toordinal())
        else:
            bb = date.fromordinal(b)
            prev = (date(y - 1, 1, 1).toordinal(), bb.replace(year=y - 1).toordinal())
    elif k == "season":
        y = int(spec["year"])
        sa, sb = season_bounds(spec["season"], y)
        a, b = sa.toordinal(), min(sb.toordinal(), newest)
        pm, py = (sa.month - 3, sa.year) if sa.month > 3 else (sa.month + 9, sa.year - 1)
        prev = (date(py, pm, 1).toordinal(), sa.toordinal() - 1)
        if a > newest:
            # pass 6, second round (X11, DESIGN 19.P6): a season after the record is answered over the latest
            # stretch of its length the record holds
            n = sb.toordinal() - sa.toordinal() + 1
            a, b = newest - n + 1, newest
            prev = (a - n, a - 1)
    elif k == "since":
        a, b = date(int(spec["year"]), 1, 1).toordinal(), newest
    elif k == "years":
        a, b = date(int(spec["from"]), 1, 1).toordinal(), min(date(int(spec["to"]), 12, 31).toordinal(), newest)
    elif k == "day":
        y = date.fromordinal(newest).year
        d = date(y, spec["month"], spec["day"])
        if d.toordinal() > newest:
            d = date(y - 1, spec["month"], spec["day"])
        a = b = d.toordinal()
        prev = (a - 1, a - 1)
    elif k == "month" or (k == "range" and _whole_month(spec)):
        # pass 6 (A3): a calendar month's span before is the month before (its same days when the month is cut by
        # the record's end), never the 31 days before
        if k == "range":
            s0 = date.fromisoformat(spec["start"])
            y, mo = s0.year, s0.month
        else:
            y, mo = int(spec["year"]), int(spec["month"])
        a, end = date(y, mo, 1), _month_end(y, mo)
        b = end.toordinal() if k == "range" else min(end.toordinal(), newest)
        py, pm = (y, mo - 1) if mo > 1 else (y - 1, 12)
        pa, plast = date(py, pm, 1), _month_end(py, pm)
        pb = plast if b == end.toordinal() else min(plast, date(py, pm, date.fromordinal(b).day))
        a = a.toordinal()
        prev = (pa.toordinal(), pb.toordinal())
    elif k == "range":
        a, b = date.fromisoformat(spec["start"]).toordinal(), date.fromisoformat(spec["end"]).toordinal()
        n = b - a + 1
        prev = (a - n, a - 1)
    else:
        a, b = None, newest
    if prev is not None and oldest is not None and prev[1] < oldest:
        prev = None
    return a, b, prev


def periods_of(a, b, lib, unit=None):
    """[(label, start, end)] by year, or by month for a span under 18 months (DESIGN 19.D)."""
    a = a if a is not None else lib.oldest
    lo, hi = date.fromordinal(a), date.fromordinal(b)
    months = (hi.year - lo.year) * 12 + hi.month - lo.month + 1
    unit = unit or ("month" if months < 18 else "year")
    out = []
    if unit == "year":
        for y in range(lo.year, hi.year + 1):
            out.append((str(y), date(y, 1, 1).toordinal(), date(y, 12, 31).toordinal()))
    else:
        y, m = lo.year, lo.month
        while (y, m) <= (hi.year, hi.month):
            end = (date(y, m + 1, 1) if m < 12 else date(y + 1, 1, 1)) - timedelta(days=1)
            out.append((f"{MONTHS[m - 1][:3].title()} {y}", date(y, m, 1).toordinal(), end.toordinal()))
            y, m = (y, m + 1) if m < 12 else (y + 1, 1)
    return out, unit


# ============================================================================ the audit's findings
class Findings:
    def __init__(self, qid, shape):
        self.qid, self.shape = qid, shape
        self.rows = []
        self.sentence = ""   # the sentence being read (kept in the rows file, never printed: it holds names)

    def add(self, audit, kind, ok, said, recount, where="", note="", severity=None):
        if severity is None:
            severity = _severity(said, recount) if not ok else 0.0
        self.rows.append({"q": self.qid, "shape": self.shape, "audit": audit, "kind": kind, "ok": bool(ok),
                          "said": said, "recount": recount, "where": where, "note": note,
                          "severity": round(float(severity), 3), "sentence": self.sentence})


def _severity(said, rec):
    try:
        s, r = float(said), float(rec)
        if s == r:
            return 0.0
        return abs(s - r) / max(abs(r), abs(s), 1e-9) + (0.5 if abs(s - r) >= 1 else 0)
    except (TypeError, ValueError):
        return 1.0


def close_share(said_pct, frac, about=False, tol=None):
    tol = tol if tol is not None else (1.6 if about else 1.0)
    return abs(float(said_pct) - 100.0 * float(frac)) <= tol


def close_count(said, n, about=False):
    if about:
        return abs(said - n) <= max(1, 0.1 * n)
    return said == n


# ============================================================================ 1. the sheet
def row_themes(t):
    """A topic row's themes as its sheet says them, in full (pass 6, A3): the row's `themes` (cut at 4 when the writer
    is shown it), its `top_themes` (which can hold one the cut left out) and a full list where the sheet carries one."""
    out = []
    for k in ("all_themes", "themes_all", "themes"):
        for x in t.get(k) or []:
            nm = x.get("name") if isinstance(x, dict) else x
            if isinstance(nm, str) and nm and nm not in out:
                out.append(nm)
    full = bool(t.get("all_themes") or t.get("themes_all"))
    cut = len(t.get("themes") or []) >= 4 and "themes" in str(t.get("matched_by") or "themes")
    if cut and not full:
        # a list of 4 may be cut: a top theme of a row matched by its themes is one of them (a row matched by words
        # alone has no themes: its top themes are those of the items its words found, never the topic's own)
        for x in t.get("top_themes") or []:
            if isinstance(x, dict) and x.get("name") and x["name"] not in out:
                out.append(x["name"])
    return out


class Ctx:
    """One answer's recount context: the window, its scopes and the record's entities said in it."""

    def __init__(self, lib, ans, today):
        self.lib = lib
        self.ans = ans
        self.sheet = ans.get("sheet") or {}
        self.spec = ans.get("window") or read_window(ans["text"], lib, today)
        if not ans.get("window") and ans.get("follow") and self.spec.get("kind") == "all":
            # pass 6 (A3): a follow-up that names no window ("without shorts", then "only music") keeps the window of
            # the message it follows, through any number of follow-ups
            for t in reversed(ans.get("chain") or [ans.get("parent_text") or ""]):
                sp = read_window(t, lib, today)
                if sp.get("kind") != "all":
                    self.spec = sp
                    break
        self.a, self.b, self.prev = resolve(self.spec, lib, today)
        fl = self.sheet.get("filters") or {}
        self.f = {}
        topic = fl.get("topic")
        if topic:
            self.f["topic"] = topic
            self.f["topic_themes"] = fl.get("topic_themes") or []
            m = re.search(r"\b" + re.escape(topic.lower()) + r"\s+(?:and|&)\s+(\w+)",
                          ((ans.get("text") or "") + " " + (ans.get("parent_text") or "")).lower())
            if m:   # "art and design" read by code as two topics (art or design), its sheet saying only the first
                self.f["topic_also"] = [m.group(1)]
        if fl.get("without_shorts"):
            self.f["without_shorts"] = True
        if fl.get("channel"):
            self.f["channel"] = fl["channel"]
        if fl.get("platform"):
            self.f["platform"] = fl["platform"]
        # pass 6, second round: a weekday asked as a habit ("what do i usually watch on sundays"), read from the
        # question's own words; its span before is the other days of the same window
        mwd = re.search(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)s\b|\ba (monday|tuesday|wednesday|"
                        r"thursday|friday|saturday|sunday)\b|\b(?:usually|normally|typically)\b.*\bon (monday|tuesday|"
                        r"wednesday|thursday|friday|saturday|sunday)\b",
                        ((ans.get("parent_text") or "") + " " + (ans.get("text") or "")).lower())
        if mwd:
            wd = DAYS_EN.index(next(g for g in mwd.groups() if g))
            self.f["weekday"] = wd
            self.prev = (self.a, self.b)
            self.prev_f = {k: x for k, x in self.f.items() if k != "weekday"} | {"weekday_not": wd}
        self.kind = self.sheet.get("kind")
        self._sc = {}
        said = {}
        if topic:
            said[topic.lower()] = list(fl.get("topic_themes") or []) or ["(none)"]
        for t in self.sheet.get("topics") or []:
            if isinstance(t, dict) and t.get("name"):
                said.setdefault(t["name"].lower(), row_themes(t))
        lib.said_themes = said

    def sc(self, which="filt"):
        """Named scopes: filt (the sheet's filters), all (nothing filtered), prev / prev_all, and topic:<word>."""
        if which in self._sc:
            return self._sc[which]
        lib = self.lib
        if which == "filt":
            v = lib.scope(self.a, self.b, self.f)
        elif which == "all":
            v = lib.scope(self.a, self.b, {k: x for k, x in self.f.items() if k in ("platform", "weekday")})
        elif which == "nofilt_topic":   # the window without the topic (a count's "of N then")
            v = lib.scope(self.a, self.b, {k: x for k, x in self.f.items()
                                           if k not in ("topic", "topic_themes", "topic_also")})
        elif which == "prev":
            v = lib.scope(*self.prev, getattr(self, "prev_f", None) or self.f) if self.prev else {}
        elif which == "prev_all":
            v = lib.scope(*self.prev, {k: x for k, x in (getattr(self, "prev_f", None) or self.f).items()
                                       if k in ("platform", "weekday_not")}) if self.prev else {}
        elif which.startswith("period:"):
            _, a, b = which.split(":")
            v = lib.scope(int(a), int(b), self.f)
        elif which.startswith("topic:"):
            word, themes = which[6:].split("|", 1)
            f = {k: x for k, x in self.f.items() if k not in ("topic", "topic_themes", "topic_also")}
            f.update(topic=word, topic_themes=[t for t in themes.split(";") if t])
            v = lib.scope(self.a, self.b, f)
        else:
            raise KeyError(which)
        self._sc[which] = v
        return v

    def period(self, label):
        lab = str(label).strip()
        if re.fullmatch(r"20\d\d", lab):
            y = int(lab)
            return date(y, 1, 1).toordinal(), date(y, 12, 31).toordinal()
        m = re.fullmatch(r"([A-Za-z]{3})[a-z]* (20\d\d)", lab)
        if m and m.group(1).lower() in MON3:
            mo, y = MON3[m.group(1).lower()], int(m.group(2))
            end = (date(y, mo + 1, 1) if mo < 12 else date(y + 1, 1, 1)) - timedelta(days=1)
            return date(y, mo, 1).toordinal(), end.toordinal()
        return None


def _count_of(lib, ids, ent):
    return sum(1 for i in ids if lib.member(i, ent))


def _rank(lib, ids, kind):
    c = Counter()
    for i in ids:
        if kind == "theme":
            k = lib.theme_of.get(i)
        elif kind == "area":
            k = lib.area_of.get(i)
        else:
            k = lib.items[i]["c"]
        if k:
            c[k] += 1
    return c


def audit_sheet(ctx, F):
    """Recount every number of the shown sheet I can recount; `used` marks a path the answer used."""
    sh, lib = ctx.sheet, ctx.lib
    if not sh:
        return
    used = ctx.ans.get("used_paths") or set()

    def chk(path, said, rec, kind, tol=0):
        if said is None or rec is None:
            return
        ok = abs(float(said) - float(rec)) <= tol + 1e-9
        F.add("sheet", kind, ok, said, rec, where=path, note="used" if path in used else "")

    w = sh.get("window") or {}
    a0 = ctx.a if ctx.a is not None else lib.oldest
    if w.get("start") and w.get("end") and a0 is not None:
        ws, we = date.fromisoformat(w["start"]).toordinal(), date.fromisoformat(w["end"]).toordinal()
        ok = (ws, we) == (a0, ctx.b)
        F.add("sheet", "window read", ok, f"{w['start']}..{w['end']}",
              f"{_d(a0).isoformat()}..{_d(ctx.b).isoformat() if ctx.b else None}" if a0 <= (ctx.b or 0) else
              f"{_d(a0).isoformat()} (after the record)", where="window", note="used", severity=2.0)
        if not ok:
            ctx.window_differs = True
            return   # every count of another window would differ: the window is the one finding
    topic = (sh.get("filters") or {}).get("topic")
    if topic and re.search(r"\b" + re.escape(topic.lower()) + r"\s+(?:and|&)\s+\w+",
                           (ctx.ans.get("text", "") + " " + (ctx.ans.get("parent_text") or "")).lower()):
        F.add("sheet", "topic read (cut)", False, "1 topic named", "2 topics counted (the second word too)",
              where="filters.topic", note="used", severity=1.5)
    S = ctx.sc("filt")
    ids = list(S)
    n = len(ids)

    def totals(t, sc, base):
        idl = list(sc)
        s, lo = lib.shorts_long(idl)
        chk(f"{base}.items", t.get("items"), len(idl), "count")
        chk(f"{base}.days_active", t.get("days_active"), lib.days(sc), "days")
        chk(f"{base}.shorts", t.get("shorts"), s, "count")
        chk(f"{base}.long", t.get("long"), lo, "count")
        if "shorts_share" in t and s + lo:
            chk(f"{base}.shorts_share", t["shorts_share"], round(s / (s + lo), 3), "share", 0.0015)
        bp = t.get("by_platform") or {}
        if bp:
            yt = sum(1 for i in idl if lib.items[i]["p"] == "youtube")
            chk(f"{base}.by_platform.youtube", bp.get("youtube"), yt, "count")
            chk(f"{base}.by_platform.instagram", bp.get("instagram"), len(idl) - yt, "count")
        if "long_median_min" in t:
            lens = [lib.length[i] for i in idl if lib.short.get(i) is False and lib.length.get(i) and
                    lib.length[i] <= CAP_S]
            if len(lens) >= 5:
                chk(f"{base}.long_median_min", t["long_median_min"], round(statistics.median(lens) / 60), "median",
                    0)

    totals(sh.get("totals") or {}, S, "totals")
    P = ctx.sc("prev") if ctx.prev else None
    if sh.get("previous") and P is not None:
        totals(sh["previous"], P, "previous")
    if sh.get("window_totals"):
        totals(sh["window_totals"], ctx.sc("nofilt_topic"), "window_totals")
    pids = list(P) if P is not None else []
    # themes, areas
    for key, kind in (("themes", "theme"), ("areas", "area")):
        rows = sh.get(key) or []
        rk = _rank(lib, ids, kind)
        prk = _rank(lib, pids, kind) if P is not None else None
        for k, r in enumerate(rows):
            if not isinstance(r, dict) or not r.get("name"):
                continue
            nm = r["name"].lower() if kind == "theme" else r["name"]
            c = rk.get(nm, 0)
            base = f"{key}[{k}]"
            chk(base + ".items", r.get("items"), c, "count")
            if "share" in r:
                chk(base + ".share", r["share"], round(c / n, 3) if n else 0, "share", 0.0015)
            mem = [i for i in ids if lib.member(i, (kind, r["name"]))]
            if "days" in r:
                chk(base + ".days", r["days"], lib.days({i: S[i] for i in mem}), "days")
            if "shorts_share" in r:
                s, lo = lib.shorts_long(mem)
                if s + lo:
                    chk(base + ".shorts_share", r["shorts_share"], round(s / (s + lo), 3), "share", 0.0015)
            if prk is not None and "previous_share" in r:
                pc = prk.get(nm, 0)
                ps = round(pc / len(pids), 3) if pids else 0.0
                chk(base + ".previous_share", r["previous_share"], ps, "share", 0.0015)
                if "previous_items" in r:
                    chk(base + ".previous_items", r["previous_items"], pc, "count")
                if isinstance(r.get("change_vs_previous"), (int, float)):
                    chk(base + ".change_vs_previous", r["change_vs_previous"],
                        round((round(c / n, 3) if n else 0) - ps, 3), "change", 0.0025)
            for j, ch in enumerate(r.get("channels") or []):
                if isinstance(ch, dict) and ch.get("name") and "items" in ch:
                    chk(f"{base}.channels[{j}].items", ch["items"],
                        sum(1 for i in mem if lib.items[i]["c"] == ch["name"]), "count")
            for j, t in enumerate(r.get("themes") or []):   # an area's themes, their share of the window
                if isinstance(t, dict) and t.get("name") and "share" in t:
                    chk(f"{base}.themes[{j}].share", t["share"],
                        round(rk_t(lib, ids, t["name"]) / n, 3) if n else 0, "share", 0.0015)
        # the order of the list
        for k in range(len(rows) - 1):
            a_, b_ = rows[k], rows[k + 1]
            if isinstance(a_, dict) and isinstance(b_, dict) and a_.get("name") and b_.get("name"):
                na = a_["name"].lower() if kind == "theme" else a_["name"]
                nb = b_["name"].lower() if kind == "theme" else b_["name"]
                F.add("sheet", "rank", rk.get(na, 0) >= rk.get(nb, 0), rk.get(na, 0), rk.get(nb, 0),
                      where=f"{key}[{k}]>={key}[{k + 1}]", severity=1.0)
    # channels
    crk = _rank(lib, ids, "channel")
    for k, r in enumerate(sh.get("channels") or []):
        if not isinstance(r, dict) or not r.get("name"):
            continue
        base = f"channels[{k}]"
        mem = [i for i in ids if lib.items[i]["c"] == r["name"]]
        chk(base + ".items", r.get("items"), len(mem), "count")
        if "days" in r:
            chk(base + ".days", r["days"], lib.days({i: S[i] for i in mem}), "days")
        if "share" in r:
            chk(base + ".share", r["share"], round(len(mem) / n, 3) if n else 0, "share", 0.0015)
        if "shorts_share" in r:
            s, lo = lib.shorts_long(mem)
            if s + lo:
                chk(base + ".shorts_share", r["shorts_share"], round(s / (s + lo), 3), "share", 0.0015)
        if "theme_share" in r and mem:
            tc = Counter(lib.theme_of[i] for i in mem if i in lib.theme_of)
            chk(base + ".theme_share", r["theme_share"], round(tc.most_common(1)[0][1] / len(mem), 3) if tc else 0,
                "share", 0.0015)
        if "previous_items" in r and P is not None:
            chk(base + ".previous_items", r["previous_items"], sum(1 for i in pids if lib.items[i]["c"] == r["name"]),
                "count")
        if r.get("first_watched"):
            fw = lib.first_watch(r["name"])
            chk(base + ".first_watched", date.fromisoformat(r["first_watched"]).toordinal(), fw, "date")
    chs = [r for r in sh.get("channels") or [] if isinstance(r, dict) and r.get("name")]
    for k in range(len(chs) - 1):
        F.add("sheet", "rank", crk.get(chs[k]["name"], 0) >= crk.get(chs[k + 1]["name"], 0),
              crk.get(chs[k]["name"], 0), crk.get(chs[k + 1]["name"], 0), where=f"channels[{k}]>=channels[{k + 1}]",
              severity=1.0)
    # when
    wh = sh.get("when") or {}
    evs = [e for ev in S.values() for e in ev]
    if evs:
        hc = Counter(e[1] for e in evs)
        for k, h in enumerate(wh.get("busiest_hours") or []):
            if isinstance(h, dict) and "hour" in h:
                chk(f"when.busiest_hours[{k}].share", h.get("share"), round(hc.get(h["hour"], 0) / len(evs), 3),
                    "share", 0.0015)
        top = sorted(hc, key=lambda x: (-hc[x], x))[:1]
        if wh.get("busiest_hours") and top:
            chk("when.busiest_hours[0].hour", wh["busiest_hours"][0].get("hour"), top[0], "rank")
        if "weekday_share" in wh:
            chk("when.weekday_share", wh["weekday_share"], round(sum(1 for e in evs if e[2] < 5) / len(evs), 3),
                "share", 0.0015)
        if "events" in wh:
            chk("when.events", wh["events"], len(evs), "count")
    # periods
    for k, p in enumerate(sh.get("periods") or []):
        if not isinstance(p, dict):
            continue
        bd = ctx.period(p.get("label"))
        if not bd:
            continue
        a_, b_ = max(bd[0], ctx.a) if ctx.a else bd[0], min(bd[1], ctx.b)
        if ctx.kind in ("first", "last"):
            a_ = bd[0]
        psc = ctx.sc(f"period:{a_}:{b_}")
        pid = list(psc)
        chk(f"periods[{k}].items", p.get("items"), len(pid), "count")
        for j, t in enumerate(p.get("themes") or []):
            if isinstance(t, dict) and t.get("name") and "share" in t and pid:
                chk(f"periods[{k}].themes[{j}].share", t["share"], round(rk_t(lib, pid, t["name"]) / len(pid), 3),
                    "share", 0.0015)
        for j, t in enumerate(p.get("areas") or []):
            if isinstance(t, dict) and t.get("name") and "share" in t and pid:
                chk(f"periods[{k}].areas[{j}].share", t["share"],
                    round(_count_of(lib, pid, ("area", t["name"])) / len(pid), 3), "share", 0.0015)
        if "shorts_share" in p:
            s, lo = lib.shorts_long(pid)
            if s + lo:
                chk(f"periods[{k}].shorts_share", p["shorts_share"], round(s / (s + lo), 3), "share", 0.0015)
    # topics (a comparison's two sides; a topic's own row)
    for k, t in enumerate(sh.get("topics") or []):
        if not isinstance(t, dict) or not t.get("name"):
            continue
        tsc = ctx.sc("topic:" + t["name"] + "|" + ";".join(row_themes(t) or ctx.f.get("topic_themes") or []))
        tid = list(tsc)
        chk(f"topics[{k}].items", t.get("items"), len(tid), "count")
        if "days" in t:
            chk(f"topics[{k}].days", t["days"], lib.days(tsc), "days")
        s, lo = lib.shorts_long(tid)
        if "shorts" in t:
            chk(f"topics[{k}].shorts", t["shorts"], s, "count")
        if "long" in t:
            chk(f"topics[{k}].long", t["long"], lo, "count")
    # saved and never opened
    for k, r in enumerate((sh.get("library") or {}).get("saved_not_opened") or []):
        if isinstance(r, dict) and r.get("theme") and "n" in r:
            # pass 6, second round (the hand check, b4: a saved count of the YouTube ones only, where 371 were saved
            # and never opened on both platforms): saved and never opened is counted on every platform
            nn = sum(1 for i in lib.saved if i not in lib.opens and lib.theme_of.get(i) == r["theme"].lower())
            chk(f"library.saved_not_opened[{k}].n", r["n"], nn, "count")


def rk_t(lib, ids, name):
    nm = name.lower()
    return sum(1 for i in ids if lib.theme_of.get(i) == nm)


# ============================================================================ 2 and 3. the sent text
DAYS_EN = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_PCT = re.compile(r"(\d+(?:[.,]\d{1,2})?)\s?%")
_BAR = re.compile(r"^[█░▏▎▍▌▋▊▉]+\s+")
_BASE = [   # (pattern after the number, base key); the first that matches the words right after the number
    (re.compile(r"^\s*of (?:everything|all|what) you (?:opened|watched)|^\s*of everything\b|^\s*of your watching|"
                r"^\s*of the window|^\s*of all your videos"), "all"),
    (re.compile(r"^\s*of (?:your|the) youtube videos with a (?:known )?length"), "known"),
    (re.compile(r"^\s*of (?:your|the|the day's|that day's|the window's|the season's|the year's) youtube videos|"
                r"^\s*of the youtube videos you"), "yt"),
    # pass 6 (A2, X6): videos that are not Shorts, said as what they are (YouTube videos of any length but Shorts)
    (re.compile(r"^\s*of your (?:youtube )?videos (?:that are not|other than|apart from|besides) shorts|"
                r"^\s*of your non-shorts?(?: youtube)? videos|^\s*of the non-shorts?(?: youtube)? videos"), "filt"),
    (re.compile(r"^\s*of your long (?P<x>[a-z][a-z &'-]*?) videos"), "long_x"),
    (re.compile(r"^\s*of your long videos|^\s*of the long videos"), "long_filt"),
    (re.compile(r"^\s*of your (?P<x>[a-z][a-z &'-]*?) videos on youtube"), "x_yt"),
    (re.compile(r"^\s*of your (?P<x>[a-z0-9][a-z0-9 &'-]*?) videos"), "x"),
    (re.compile(r"^\s*of (?:their|its|his|her) (?:own )?videos"), "own"),
    (re.compile(r"^\s*of the videos you opened from (?P<x>.+?)(?:[,.;)]|$)"), "chan"),
    (re.compile(r"^\s*of (?:them|it|these|those)\b"), "them"),
]
_CAPTION_BASE = [(re.compile(r"^share of what you opened", re.I), "all"),
                 (re.compile(r"^share of your (?:youtube )?videos (?:that are not|other than) shorts|"
                             r"^share of your non-shorts?", re.I), "filt"),
                 (re.compile(r"^share of your long (?:[a-z0-9 &'-]+ )?videos", re.I), "long_known"),
                 (re.compile(r"shorts' share of your youtube videos", re.I), "yt"),
                 (re.compile(r"^(?:long )?(?P<x>.+?) videos opened", re.I), "x_cap"),
                 (re.compile(r"^videos opened", re.I), "filt")]


_PHRASE = re.compile(r"^\s*of (?:everything|all|what) you (?:opened|watched)|^\s*of (?:your|the|the day's|that day's) "
                     r"(?:[a-z0-9 &'-]+? )?(?:youtube )?videos(?: on youtube| with a (?:known )?length)?")


def sentences(text):
    out = []
    caption = None
    for line in (text or "").split("\n"):
        s = line.strip()
        if not s:
            continue
        if _BAR.match(s):
            out.append(("bar", s, caption))
            continue
        if s.endswith(":") and len(s) < 90:
            caption = s
            out.append(("caption", s, None))
            continue
        caption = None
        s = s.lstrip("•").strip()
        parts = []
        for part in re.split(r"(?<=[.!?])\s+(?=[A-Z\"“])", s):
            if parts and re.search(r"(?:^|\s)[A-Z]\.$", parts[-1]):
                parts[-1] += " " + part   # an initial ("D. Films") ends no sentence
            elif part:
                parts.append(part)
        out += [("text", part, None) for part in parts]
    return out


class Names:
    """The record's names an answer can say (the sheet's own and my build's themes), longest first."""

    def __init__(self, ctx):
        sh, lib = ctx.sheet, ctx.lib
        found = {}
        for t in lib.theme_names.values():
            found[t.lower()] = ("theme", t)
        for a in set(lib.area_of.values()):
            found.setdefault(a.lower(), ("area", a))
        for k in ("channels",):
            for r in sh.get(k) or []:
                if isinstance(r, dict) and r.get("name"):
                    found.setdefault(r["name"].lower(), ("channel", r["name"]))
        for r in (sh.get("themes") or []):
            for ch in (r.get("channels") or []) if isinstance(r, dict) else []:
                if isinstance(ch, dict) and ch.get("name"):
                    found.setdefault(ch["name"].lower(), ("channel", ch["name"]))
        for r in (sh.get("topics") or []):
            if isinstance(r, dict) and r.get("name"):
                found[r["name"].lower()] = ("topic", r["name"])   # a topic's own word: its themes and its words
                for ch in r.get("channels") or []:
                    if isinstance(ch, dict) and ch.get("name"):
                        found.setdefault(ch["name"].lower(), ("channel", ch["name"]))
        topic = (sh.get("filters") or {}).get("topic")
        if topic:
            found[topic.lower()] = ("topic", topic)
        self.topic_said = {r["name"].lower(): row_themes(r) for r in sh.get("topics") or []
                           if isinstance(r, dict) and r.get("name")}
        self.found = found
        self.pat = re.compile(r"(?<![\w])(" + "|".join(re.escape(k) for k in sorted(found, key=len, reverse=True)
                                                       if len(k) >= 2) + r")(?![\w])", re.I) if found else None

    def spans(self, s):
        out = []
        if self.pat is not None:
            for m in self.pat.finditer(s):
                out.append((m.start(), m.end(), self.found[m.group(1).lower()]))
        taken = [(a, b) for a, b, _ in out]
        for m in re.finditer(r"\bShorts\b", s):
            if not any(a <= m.start() < b for a, b in taken):
                out.append((m.start(), m.end(), ("shorts", "Shorts")))
        for m in re.finditer(r"\blong(?:-form)? (?:videos|ones)\b", s, re.I):
            if not any(a <= m.start() < b for a, b in taken):
                out.append((m.start(), m.end(), ("long", "long videos")))
        out.sort()
        return out


def ent_code(e):
    return {"shorts": "Shorts", "long": "Long", "all": "All"}.get(e[0]) or code_of(e[0], e[1])


class TextAudit:
    def __init__(self, ctx, F):
        self.ctx, self.F, self.lib = ctx, F, ctx.lib
        self.names = Names(ctx)
        self.filtered = bool(ctx.f.get("topic") or ctx.f.get("channel") or ctx.f.get("without_shorts"))
        self.facts = []   # (kind, record, value, sentence index): one fact said in two sentences is a repeat (X9)
        self.si = 0

    # ---------------------------------------------------------------- bases
    def base_ids(self, key, ent=None, x=None, scope="cur"):
        """The ids of a candidate base. scope: cur (the window), prev (the span before), or period:<a>:<b>."""
        ctx, lib = self.ctx, self.lib
        if scope == "prev":
            filt, allv = ctx.sc("prev"), ctx.sc("prev_all")
        elif scope.startswith("rest:"):   # the rest of a season's year (the season's own days left out)
            y = int(scope[5:])
            sc = lib.scope(date(y, 1, 1).toordinal(), date(y, 12, 31).toordinal(), ctx.f)
            filt = allv = {i: v for i, v in sc.items() if any(not (ctx.a <= e[0] <= ctx.b) for e in v)}
        elif scope.startswith("period:"):
            filt = ctx.sc(scope)
            _, a, b = scope.split(":")
            allv = lib.scope(int(a), int(b), {})
        else:
            filt, allv = ctx.sc("filt"), ctx.sc("all")
        if key == "all":
            return list(allv)
        if key == "yt":
            return [i for i in allv if lib.items[i]["p"] == "youtube"]
        if key == "known":
            return lib.known(allv)
        if key == "filt":
            return list(filt)
        if key == "filt_yt":
            return [i for i in filt if lib.items[i]["p"] == "youtube"]
        if key == "filt_known":
            return lib.known(filt)
        if key == "long_known":
            return [i for i in filt if lib.short.get(i) is False]
        if key == "long":
            return [i for i in allv if lib.short.get(i) is False]
        if key == "own" and ent is not None:
            return [i for i in allv if lib.member(i, ent)]
        if key == "own_filt" and ent is not None:
            return [i for i in filt if lib.member(i, ent)]
        if key == "own_known" and ent is not None:
            return lib.known([i for i in allv if lib.member(i, ent)])
        if key == "own_filt_known" and ent is not None:
            return lib.known([i for i in filt if lib.member(i, ent)])
        raise KeyError(key)

    def candidates(self, ent, sub=None, scope="cur"):
        """{base key: share} of `ent` (or of `sub` inside `ent` for "their videos") over every candidate base."""
        lib = self.lib
        out = {}
        if sub is not None:   # "A is about T (99% of their videos)": T's share of A's videos
            for key in ("own", "own_filt"):
                ids = self.base_ids(key, ent, scope=scope)
                if ids:
                    out[key] = sum(1 for i in ids if lib.member(i, sub)) / len(ids)
            return out
        for key in ("all", "yt", "known", "filt", "filt_yt", "filt_known", "long", "long_known"):
            ids = self.base_ids(key, scope=scope)
            if ids:
                out[key] = sum(1 for i in ids if lib.member(i, ent)) / len(ids)
        if ent[0] in ("shorts", "long"):
            for key in ("own_known",):
                pass
        return out

    def said_base(self, after, ent):
        """The base key the words after a number say, or None."""
        low = after.lower()
        topic = (self.ctx.f.get("topic") or "").lower()
        for pat, key in _BASE:
            m = pat.search(low)
            if not m:
                continue
            x = (m.groupdict().get("x") or "").strip()
            if key == "x":
                if topic and (x == topic or x.endswith(" " + topic) or topic in x.split()):
                    return "filt"
                if x in ("youtube",):
                    return "yt"
                if x in ("long",):
                    return "long"
                # "of your <theme / area> videos": that record's own videos
                e = self.names.found.get(x)
                return ("ownof", e) if e else ("unknown", x)
            if key == "x_yt":
                if topic and (x == topic or topic in x.split()):
                    return "filt_yt"
                e = self.names.found.get(x)
                return ("ownof_yt", e) if e else ("unknown", x)
            if key == "long_x":
                # "of your long music videos": the long ones (a known length over the Short rule) of the scope
                if topic and (x == topic or topic in x.split()):
                    return "long_known"
                return ("unknown", "long " + x)
            if key == "long_filt":
                # pass 6 (A2, X6): "of your long videos" is the videos KNOWN to be long, never every video that is not
                # a Short (those of unknown length are not "long")
                return "long_known"
            if key == "chan":
                return ("ownof", ("channel", m.group("x").strip()))
            if key == "them":
                return ("them", None)
            return key
        return None

    def share_of_base(self, base, ent, sub=None, scope="cur"):
        """The share of ent in the said base (None when the base cannot be recounted)."""
        lib = self.lib
        if base is None:
            return None
        if isinstance(base, tuple):
            k, e = base
            if k in ("ownof", "ownof_yt"):
                if e is None or e[0] == "unknown":
                    return None
                ids = [i for i in self.base_ids("all", scope=scope) if lib.member(i, e)]
                if k == "ownof_yt":
                    ids = [i for i in ids if lib.items[i]["p"] == "youtube"]
                if ent[0] in ("shorts", "long"):
                    ids = lib.known(ids)
                return (sum(1 for i in ids if lib.member(i, ent)) / len(ids)) if ids else None
            return None
        if base == "own":
            if sub is None:
                return None
            ids = self.base_ids("own", ent, scope=scope)
            return (sum(1 for i in ids if lib.member(i, sub)) / len(ids)) if ids else None
        if base in ("them",):
            return None
        ids = self.base_ids(base, scope=scope)
        if ent[0] in ("shorts", "long") and base in ("filt", "filt_yt"):
            pass
        return (sum(1 for i in ids if lib.member(i, ent)) / len(ids)) if ids else None

    # ---------------------------------------------------------------- the sentences
    def run(self, text):
        if (self.ctx.sheet.get("lang") or "en") == "es":
            text = re.sub(r"(?<=\d)\.(?=\d{3}\b)", "", text)   # "3.630" is 3630 in Spanish
        caption_base = None
        prev_base = None
        charts = defaultdict(list)   # caption -> the bars' percents
        phrases = set()              # the base phrases said after a percent (X18)
        for typ, s, cap in sentences(text):
            self.F.sentence = s
            if typ == "caption":
                caption_base = self.caption_base(s)
                continue
            if typ == "bar":
                self.bar(s, cap, caption_base)
                pm = re.match(r"^(\d+)%\s", _BAR.sub("", s))
                if pm:
                    charts[cap].append(int(pm.group(1)))
                continue
            self.si += 1
            prev_base = self.sentence(s, prev_base)
            for m in _PCT.finditer(s):
                pm = _PHRASE.match(s[m.end():].lower())
                if pm:
                    phrases.add(" ".join(pm.group(0).split()))
        if len(phrases) > 2:
            # X18: one phrase for the answer's own base (said once), one for Shorts; a third reads as a third base
            self.F.sentence = "the answer's base phrases"
            self.F.add("word", "more than two base phrasings in one answer", False, len(phrases), 2,
                       note=" | ".join(sorted(phrases)), severity=0.3)
        for cap, vals in charts.items():
            # pass 6 (X10): a chart whose first row holds 90% or more says nothing a bar can show (the filter's own
            # topic), and a row that rounds to 0% is an empty row
            self.F.sentence = cap or "a chart"
            self.F.add("word", "chart: its first row is 90% or more", vals[0] < 90, f"{vals[0]}%", "under 90%",
                       severity=0.5)
            zeros = sum(1 for v in vals if v == 0)
            self.F.add("word", "chart: a row rounds to 0%", zeros == 0, f"{zeros} rows at 0%", "none", severity=0.5)
        self.repeats()
        # X16: a list cut by "and N more" names in its overview no channel whose card is hidden
        if re.search(r"\band \d+ more\b", text, re.I):
            shown = {c.lower() for _, c, _, _ in _cards(text)}
            if shown:
                named = set()
                for typ, s, _ in sentences(text):
                    if typ == "text" and not _CARD.match(s):
                        named |= {sp[2][1] for sp in self.names.spans(s) if sp[2][0] == "channel"}
                hidden = sorted(c for c in named if c.lower() not in shown)
                self.F.sentence = "the overview and its cards"
                self.F.add("word", "a channel named whose card is hidden", not hidden, len(hidden), 0,
                           where=",".join(code_of("channel", c) for c in hidden), severity=0.5)

    def caption_base(self, s):
        low = s.lower()
        for pat, key in _CAPTION_BASE:
            m = pat.search(low)
            if m:
                if key == "x_cap":
                    return "filt"
                return key
        return None

    def bar(self, s, cap, cbase):
        """A chart row: '████ 22% gaming' or '████ 110 <channel>' or '████ 2021 <area>' (a period)."""
        rest = _BAR.sub("", s)
        m = re.match(r"^(\d[\d,]*)(%?)\s+(.+)$", rest)
        if not m:
            return
        val, pct, label = m.group(1).replace(",", ""), m.group(2), m.group(3).strip()
        scope = "cur"
        ym = re.search(r"\s(20\d\d)$", label)
        if ym:
            label = label[:ym.start()].strip()
            if self.ctx.prev and date.fromordinal(self.ctx.prev[1]).year == int(ym.group(1)) and \
                    date.fromordinal(self.ctx.b).year != int(ym.group(1)):
                scope = "prev"
        elif cap and "against" in cap.lower():
            return   # a cut label of a two-span chart: which span it is cannot be read
        e = self.names.found.get(label.lower().rstrip("…"))
        bym = re.search(r"\bby (area|theme|channel|topic)\b", (cap or "").lower())
        if bym and e is not None and e[0] != bym.group(1):
            # pass 6 (A3): a chart "by area" names areas ("music" is the area there, not the topic of the filter)
            k = bym.group(1)
            if k == "area":
                hit = next((a for a in set(self.lib.area_of.values()) if a.lower() == label.lower()), None)
                e = ("area", hit) if hit else e
            elif k == "theme" and label.lower() in self.lib.theme_names:
                e = ("theme", self.lib.theme_names[label.lower()])
        if e is None and label.endswith("…"):
            pre = label[:-1].lower()
            hits = [v for k, v in self.names.found.items() if k.startswith(pre)]
            e = hits[0] if len(hits) == 1 else None
        if pct and e is not None:
            base = cbase or ("all" if not self.filtered else "filt")
            cands = self.candidates(e)
            got = cands.get(base) if isinstance(base, str) else self.share_of_base(base, e)
            # pass 6 (X13): a bar is rounded once, from the counts: it is within half a point of its share
            self.judge_share(float(val), base, cands, got, e, "chart share", about=False, tol=0.5 + 1e-9)
        elif not pct and e is not None and not re.fullmatch(r"20\d\d", val):
            n = _count_of(self.lib, self.base_ids("filt", scope=scope), e)
            self.F.add("base", "chart count", n == int(val), int(val), n, where=ent_code(e),
                       note="the span before" if scope == "prev" else "")

    def judge_share(self, said, base, cands, got, e, kind, about=False, sub=None, tol=None):
        fits = sorted(k for k, v in cands.items() if close_share(said, v, about, tol))
        where = ent_code(e) + (" in " + ent_code(sub) if sub else "")
        if base is None:
            # what a reader could take it as: of everything, of the YouTube videos (with a known length, for Shorts),
            # or, on a filtered answer, of the filtered videos; a share with no base said where those differ by more
            # than 2 points is reported (U9: "N% of them were Shorts" must say whose)
            keys = ["all", "filt"] if self.filtered else ["all"]
            if e[0] in ("shorts", "long"):
                keys = ["all", "yt", "known"] + (["filt", "filt_known"] if self.filtered else [])
            plaus = {k: round(cands[k] * 100, 1) for k in keys if k in cands}
            # pass 6 (A2): bases 1 point apart already read differently on a share over 10%
            spread = 1.0 if plaus and max(plaus.values()) > 10 else 2.0
            if len(plaus) > 1 and max(plaus.values()) - min(plaus.values()) > spread:
                self.F.add("base", "no base said", False, said, plaus, where=where,
                           note="fits: " + (",".join(fits) or "none"), severity=0.4 if fits else 1.0)
            elif not fits and cands:
                self.F.add("base", "share (no base said, fits no base)", False, said,
                           {k: round(v * 100, 1) for k, v in cands.items()}, where=where, severity=1.0)
            else:
                self.F.add("base", "share (no base said, bases agree)", True, said, plaus, where=where)
            return
        if got is None:
            self.F.add("base", kind + " (base not recounted)", True, said, None, where=where, note=str(base))
            return
        ok = close_share(said, got, about, tol)
        note = ("said base " + (base if isinstance(base, str) else base[0]) + "; fits: " + (",".join(fits) or "none"))
        self.F.add("base", kind, ok, said, round(got * 100, 1), where=where, note=note)

    def year_scope(self, y):
        ctx = self.ctx
        a, b = date(y, 1, 1).toordinal(), date(y, 12, 31).toordinal()
        if ctx.prev and ctx.kind != "changed" and ctx.a is not None and ctx.a > b and \
                date.fromordinal(ctx.prev[0]).year == y == date.fromordinal(ctx.prev[1]).year:
            return "prev"   # the span before, said by its year ("from 14% in 2023" in a 2024 answer)
        if ctx.a is not None and ctx.a <= b and a <= ctx.b:
            # a year the window holds: the window's part of it; a year outside the window (pass 6: "from 64% in 2023"
            # in a 2024 answer was the empty span) is that whole year, to the record's end
            a = max(a, ctx.a) if ctx.kind != "changed" else a
            b = min(b, ctx.b)
        return f"period:{a}:{min(b, self.lib.newest)}"

    def percents(self, s, spans):
        """Each percent of a sentence with its subject, its scope (the window, the span before, a year) and the base
        its words say (None when they say none)."""
        ctx = self.ctx
        low = s.lower()
        ms = list(_PCT.finditer(s))
        out = []
        years = [int(y) for y in re.findall(r"\b(?:in|en) (20\d\d)\b", s)]
        for k, m in enumerate(ms):
            before, after = s[:m.start()], s[m.end():]
            about = bool(re.search(r"\b(?:about|around|nearly|almost|roughly)\s*$", before[-20:].lower()))
            if re.match(r"^\s*on (?:a|your) usual day", after.lower()):
                # pass 6 (A2, X7): a usual day's median, recounted on the base of the day's own number it is set
                # against (sentence(): a pair on two bases is reported)
                out.append({"m": m, "said": float(m.group(1).replace(",", ".")), "about": about, "usual": True,
                            "e": ("shorts", "Shorts"), "scope": "cur", "after": "", "their": False, "names": [],
                            "pos": 0, "run_start": m.start()})
                continue
            ents = [sp for sp in spans if sp[1] <= m.start()]
            # a run of percents ("at 11% and 5%", "(100% and 99% ...)") goes with a run of names, in order
            run_start = k
            while run_start > 0 and re.fullmatch(r"\s*(?:,|and|,\s*and)\s*", s[ms[run_start - 1].end():ms[run_start].start()]):
                run_start -= 1
            pos = k - run_start
            first = ms[run_start]
            names_before = [sp for sp in spans if sp[1] <= first.start()]
            e = None
            if pos > 0 and names_before:
                # the names right before the run, joined by "and" / ","
                grp = [names_before[-1]]
                for sp in reversed(names_before[:-1]):
                    gap = s[sp[1]:grp[0][0]]
                    if re.fullmatch(r"\s*(?:,|and|,\s*and)\s*", gap):
                        grp.insert(0, sp)
                    else:
                        break
                if len(grp) >= pos + 1:
                    e = grp[pos][2]
                    ents = grp
            if e is None and pos == 0 and k + 1 < len(ms) and names_before:
                grp = [names_before[-1]]
                for sp in reversed(names_before[:-1]):
                    if re.fullmatch(r"\s*(?:,|and|,\s*and)\s*", s[sp[1]:grp[0][0]]):
                        grp.insert(0, sp)
                    else:
                        break
                nrun = 1
                while k + nrun < len(ms) and re.fullmatch(r"\s*(?:,|and|,\s*and)\s*", s[ms[k + nrun - 1].end():ms[k + nrun].start()]):
                    nrun += 1
                if len(grp) == nrun and nrun > 1:
                    e = grp[0][2]
            # pass 6 (A2, X3): "your Shorts share dropped from 64% ...", "the share of Shorts was 33%": the word
            # "share" names Shorts before the number, in the number's own clause
            cl = _clause_start(low, m.start())
            if re.search(r"\bshorts(?:'|’)?\s+share\b|\bshare of (?:your |the )?shorts\b", low[cl:m.start()]) and \
                    not any(cl <= sp[0] and sp[1] <= m.start() and sp[2][0] in ("theme", "area", "channel", "topic")
                            for sp in spans):
                e = ("shorts", "Shorts")
            if e is None:
                if not ents:
                    ents = [sp for sp in spans if sp[0] >= m.end()][:1]
                if not ents:
                    continue
                e = ents[-1][2]
            # "from X% (in Y1) to Y% (in Y2)": X before, Y now (or the two years of a change)
            scope = "cur"
            per = re.match(r"^\s*(?:of [^,.;%]*?\s)?(?:in|en) (20\d\d)\b(?! to\b)", after)
            # pass 6, second round (the hand check's false flags, b7: "2020 was led by gaming, then comedy, with 4%
            # Shorts" and "70% of your YouTube videos in 2026 was Shorts" in a "since 2020" answer): a year that leads
            # the sentence, or follows the number's base, is the number's own span
            if not per:
                per = re.match(r"^\s*(20\d\d)\s+(?:was|saw|had|is)\b", s)
            frm = re.search(r"\b(?:from|de)\s*$", before[-6:].lower())
            to = re.search(r"\b(?:to|a)\s*$", before[-4:].lower()) and \
                re.search(r"(?:from|de) \d+(?:[.,]\d+)?%[^%]*$", before.lower())
            # "N% were Shorts", "58% of your YouTube videos were Shorts", "100% of it was Shorts": the record after
            wr = re.match(r"^\s*(?:of [^,.;%]*?\s)?(?:were|was|are|is)\s+(?:all\s+)?(Shorts|long)\b", after)
            if wr:
                e = ("shorts", "Shorts") if wr.group(1) == "Shorts" else ("long", "long videos")
            elif re.match(r"^\s*Shorts\b", after) and not any(sp[2][0] == "channel" for sp in spans
                                                               if sp[1] <= m.start()):
                e = ("shorts", "Shorts")   # pass 6, second round (b7): "with 4% Shorts": a Shorts share
            # "from 64% in 2023 to 33%": the value after "to" is the same record's, in the same clause
            if out and to and not wr:
                gap = s[out[-1]["m"].end():m.start()]
                # pass 6, second round (the hand check's false flags, c06, n06.1: "from 19% of your minecraft videos on
                # YouTube to 34%"): the base said with the first value names no record of its own
                gap_wo = re.sub(r"of (?:your|the) [^,;]*?videos(?: on youtube)?", "", gap, flags=re.I)
                if not re.search(r"\bwhile\b|;", gap) and not any(out[-1]["m"].end() <= sp[0] < m.start() and
                                                                    gap_wo.find(s[sp[0]:sp[1]]) >= 0 for sp in spans):
                    e = out[-1]["e"]
                    if not re.match(r"^\s*of ", after):
                        after = out[-1]["after"]
            # "up to 61% of your minecraft videos, from 20% in ...": the same record, its value before
            if out and frm:
                gap = s[out[-1]["m"].end():m.start()]
                gap_wo = re.sub(r"of (?:your|the) [^,;]*?videos(?: on youtube)?", "", gap, flags=re.I)
                if not re.search(r"\bwhile\b|;", gap) and not any(out[-1]["m"].end() <= sp[0] < m.start() and
                                                                    gap_wo.find(s[sp[0]:sp[1]]) >= 0 for sp in spans):
                    e = out[-1]["e"]
                    after = out[-1]["after"] if not re.match(r"^\s*of ", after) else after
            if per:
                scope = self.year_scope(int(per.group(1)))
            elif ctx.kind == "changed" and (frm or to) and len(years) >= 2:
                scope = self.year_scope(years[0] if frm else years[-1])
            elif frm:
                scope = "prev"
            elif to:
                scope = "cur"
            elif re.match(r"^\s*(?:in|against|for) the (?:\d+ )?(?:weeks?|days?|spring|summer|winter|fall|month|year|"
                          r"same)[a-z0-9 ]*before|^\s*(?:in|against) the same part|^\s*(?:in|against) (?:the )?"
                          r"(?:spring|winter|summer|fall) before", after.lower()):
                scope = "prev"
            elif re.match(r"^\s*(?:in|against) (20\d\d)\b", after) and ctx.prev:
                scope = "prev"
            rest = re.search(r"apart from the rest of (20\d\d)", s)
            if rest and re.search(r",\s*against\s*$", before[-12:]) and ctx.a is not None:
                scope = "rest:" + rest.group(1)
            if frm and ctx.kind != "changed" and not per:
                scope = "prev" if ctx.prev else scope
            # whose base: the words after the number (or after the last number of its run)
            last = m
            j = k
            while j + 1 < len(ms) and re.fullmatch(r"\s*(?:,|and|,\s*and)\s*", s[ms[j].end():ms[j + 1].start()]):
                j += 1
                last = ms[j]
            their = re.match(r"^\s*of (?:their|its) (?:own )?videos", s[last.end():].lower())
            if re.match(r"^\s*Shorts\b", s[last.end():]) and not wr:
                # "A and B are clip channels (95% and 100% Shorts)": each channel's own Shorts share
                chans = [sp[2] for sp in spans if sp[1] <= first.start() and sp[2][0] == "channel"]
                grp = chans[-(j - run_start + 1):] if len(chans) >= j - run_start + 1 else []
                if grp:
                    out.append({"m": m, "said": float(m.group(1).replace(",", ".")), "about": about,
                                "e": ("shorts", "Shorts"), "scope": scope, "after": " of its videos",
                                "their": False, "names": ents, "pos": pos, "run_start": first.start(),
                                "chan_shorts": grp[pos]})
                    continue
            if per and out and out[-1]["scope"].startswith("period:") and not wr and \
                    not re.search(r"\bwhile\b|;|\bagainst\b|\bmientras\b", s[out[-1]["m"].end():m.start()]):
                e = out[-1]["e"]   # "22% in 2020, up to 48% in 2022, ... and 16% in 2026": one record's years
            out.append({"m": m, "said": float(m.group(1).replace(",", ".")), "about": about, "e": e, "scope": scope,
                        "after": s[last.end():], "their": bool(their), "names": ents, "pos": pos,
                        "run_start": first.start()})
        return out

    def sentence(self, s, prev_base):
        lib, ctx = self.lib, self.ctx
        spans = self.names.spans(s)
        low = s.lower()
        sentence_base = None
        base_kind = None
        # ---------------- percents
        inside = re.match(r"^\s*(?:inside|within|behind)\s+", low)
        inside_rec = next((sp[2] for sp in spans if inside and sp[0] == inside.end() and
                           sp[2][0] in ("theme", "area", "topic")), None)
        for p in self.percents(s, spans):
            said, about, e, scope = p["said"], p["about"], p["e"], p["scope"]
            if p.get("usual"):
                self.usual_pair(said, sentence_base if base_kind == "shorts" else None)
                continue
            if p.get("chan_shorts"):
                # "X is a clip channel you grazed (100% Shorts)": the Shorts of all its videos then, or (on a filtered
                # answer) of its filtered ones
                ch = p["chan_shorts"]
                cands = {}
                for key in ("own_known", "own_filt_known"):
                    ids = self.base_ids(key, ch, scope=scope)
                    if ids:
                        cands[key] = sum(1 for i in ids if lib.member(i, ("shorts", ""))) / len(ids)
                self.judge_share(said, "own_known", cands, cands.get("own_known"), ch, "Shorts share of a channel",
                                 about)
                continue
            if p["their"]:
                # "A and B are both about T (100% and 99% of their videos)": T's share of each channel's videos
                chans = [sp[2] for sp in spans if sp[1] <= p["run_start"] and sp[2][0] == "channel"]
                subs = [sp[2] for sp in spans if sp[1] <= p["m"].start() and sp[2][0] in ("theme", "area", "topic")]
                one = not re.match(r"^\s*(?:,|and)\s*\d", s[p["m"].end():]) and p["pos"] == 0
                if one and chans:
                    e = chans[-1]   # "X is about T (44% of its videos)": the channel right before
                elif e[0] != "channel" and chans and len(chans) > p["pos"]:
                    e = chans[p["pos"]]
                if e[0] == "channel" and subs:
                    cands = self.candidates(e, sub=subs[-1], scope=scope)
                    self.judge_share(said, "own", cands, cands.get("own"), e, "share of their videos", about,
                                     sub=subs[-1])
                    continue
                if e[0] in ("theme", "area") and chans:
                    continue
            base = p.get("base") or self.said_base(p["after"], e)
            if base == ("them", None):   # "100% of it was Shorts": of the record named before
                prior = [sp[2] for sp in spans if sp[1] <= p["m"].start() and sp[2] != e and
                         sp[2][0] in ("theme", "area", "topic", "channel")]
                base = ("ownof", prior[-1]) if prior else None
                if base is None:
                    continue
            if base is None and sentence_base is not None and base_kind == e[0]:
                base = sentence_base   # "comedy (14% of what you opened) and gaming (10%)"
            if base is None and re.search(r"\byour watching\b|\bwhat you opened\b|\bof everything\b", low) and \
                    e[0] not in ("shorts", "long"):
                base = "all"
            if base is None and re.search(r"\byour watching\b", low):
                base = "all"   # "your watching was mostly Shorts at 79%": of everything opened
            if base is None and inside_rec is not None and e != inside_rec and e[0] not in ("shorts", "long"):
                # pass 6 (A2, X2): "Inside gaming, <theme> led with 3%." says no base, so it reads as a share OF
                # gaming (its natural reading): recounted as that, it must hold, or the sentence must say its base
                base = ("ownof", inside_rec)
                cands = self.candidates(e, scope=scope)
                got = self.share_of_base(base, e, scope=scope)
                self.judge_share(said, base, cands, got, e, "share inside a record (no base said: of the record)",
                                 about)
                continue
            if base is not None:
                sentence_base, base_kind = base, e[0]
            cands = self.candidates(e, scope=scope)
            got = cands.get(base) if isinstance(base, str) else self.share_of_base(base, e, scope=scope)
            kind = "share" + (" before" if scope == "prev" else (" in a year" if scope.startswith("period") else
                                                                 (" in the rest of the year" if scope.startswith("rest")
                                                                  else "")))
            self.judge_share(said, base, cands, got, e, kind, about)
        # ---------------- counts
        self.counts(s, spans)
        # ---------------- words
        self.words(s, spans, sentence_base)
        return sentence_base

    def usual_medians(self):
        """A day's usual day (DESIGN 19.P2, T10, my reading): the 90 days before it with anything opened; on each, the
        Shorts share of the YouTube videos (yt) and of those with a known length (known); the median of each."""
        lib, ctx = self.lib, self.ctx
        if ctx.a is None or ctx.a != ctx.b:
            return {}
        per = defaultdict(set)
        for i, ds in lib.open_days.items():
            lo = bisect.bisect_left(ds, ctx.a - 90)
            hi = bisect.bisect_left(ds, ctx.a)
            for o in ds[lo:hi]:
                per[o].add(i)
        if len(per) < 5:
            return {}
        out = {}
        for key in ("yt", "known"):
            vals = []
            for o, ids in per.items():
                yt = [i for i in ids if lib.items[i]["p"] == "youtube"]
                pool = yt if key == "yt" else [i for i in yt if lib.short.get(i) is not None]
                if pool:
                    vals.append(sum(1 for i in pool if lib.short.get(i) is True) / len(pool))
            if vals:
                out[key] = statistics.median(vals)
        return out

    def usual_pair(self, said, day_base):
        """pass 6 (A2, X7): "Shorts were 90% of the day's YouTube videos, against about 78% on a usual day": the usual
        day's share must be on the base of the day's own share (said before it in the sentence)."""
        if day_base not in ("yt", "known"):
            return
        med = self.usual_medians()
        if day_base not in med:
            return
        same = med[day_base]
        fits = [k for k, v in med.items() if abs(said - 100 * v) <= 0.6]
        self.F.add("base", "usual day (on the day's own base)", abs(said - 100 * same) <= 0.6, said,
                   round(100 * same, 1), where="Shorts", note=f"day's base {day_base}; fits: " + (",".join(fits) or
                                                                                              "none"), severity=1.0)

    def filters_said(self, low, ent):
        """The sheet's filters a count's sentence says (pass 6, X4), and the names of those it drops."""
        f = dict(self.ctx.f)
        dropped = []
        topic = (f.get("topic") or "").lower()
        if topic and not re.search(r"(?<!\w)" + re.escape(topic) + r"(?!\w)", low):
            for k in ("topic", "topic_themes", "topic_also"):
                f.pop(k, None)
            dropped.append("topic")
        if f.get("without_shorts") and not (ent is not None and ent[0] == "long") and \
                not re.search(r"\bwithout shorts\b|\bnon-shorts?\b|\bnot shorts\b|\bother than shorts\b|"
                              r"\bapart from shorts\b|\bleaving out shorts\b", low):
            f.pop("without_shorts")
            dropped.append("without Shorts")
        ch = f.get("channel")
        if ch and ch.lower() not in low and not re.search(r"\b(?:their|its|from them)\b", low):
            f.pop("channel")
            dropped.append("channel")
        return f, dropped

    def context_ids(self, s, spans, at=None, pool=None):
        """The scope a sentence speaks of: the window's filtered videos, narrowed by "Behind <theme>:", "Inside
        <area>," or "its top channels" (the theme named before), and by one year named in it ("2020 leaned most on",
        "In 2021, ...") when the window runs over several years."""
        lib, ctx = self.lib, self.ctx
        ids = self.base_ids("filt") if pool is None else pool
        low = s.lower()
        m = re.match(r"^\s*(?:behind|inside|in|within)\s+", low)
        if m:
            e = next((sp[2] for sp in spans if sp[0] == m.end()), None)
            if e is not None and e[0] in ("theme", "area", "topic"):
                ids = [i for i in ids if lib.member(i, e)]
        elif re.search(r"\b(?:its|their) (?:top |main )?channels\b|\bthe channels behind\b|\bthe main channels behind\b",
                       low):
            e = next((sp[2] for sp in reversed(spans) if sp[2][0] in ("theme", "area") and (at is None or sp[0] < at)),
                     None)
            if e is None:
                e = next((sp[2] for sp in spans if sp[2][0] in ("theme", "area")), None)
            if e is not None:
                ids = [i for i in ids if lib.member(i, e)]
        span_years = range(date.fromordinal(lib.oldest).year, date.fromordinal(lib.newest).year + 1)
        yrs = {y for y in re.findall(r"(?<![\d,.])(20\d\d)(?![\d,.])(?! (?:videos|different|days|of))", s)
               if int(y) in span_years}
        a0 = ctx.a if ctx.a is not None else lib.oldest
        if len(yrs) == 1 and date.fromordinal(a0).year != date.fromordinal(ctx.b).year and \
                not re.search(r"\b\d{1,2} [a-z]+ 20\d\d\b", low) and not re.search(r"\bsince\b", low):
            y = int(next(iter(yrs)))
            a_, b_ = date(y, 1, 1).toordinal(), date(y, 12, 31).toordinal()
            a_, b_ = max(a_, a0), min(b_, ctx.b)
            ids = [i for i in ids if any(a_ <= o <= b_ for o in lib.open_days[i])]
        return ids

    def counts(self, s, spans):
        lib, ctx = self.lib, self.ctx
        filt = self.base_ids("filt")
        low = s.lower()
        done = set()
        # "N of the M <X> videos" / "behind N of the M <X>"
        for m in re.finditer(r"\b(\d[\d,]*) of (?:the|your|its|their) (\d[\d,]*)\b", s):
            a_, b_ = int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))
            done |= {m.start(1), m.start(2)}
            after = s[m.end():]
            sub = next((sp[2] for sp in spans if sp[0] >= m.end() and sp[0] - m.end() < 6), None)
            subj = next((sp[2] for sp in reversed(spans) if sp[1] <= m.start()), None)
            if sub is None and re.match(r"^\s*(?:videos|ones)", after):
                sub = ("all", "")
            if sub is None:
                continue
            pool = filt
            if sub[0] == "all" and re.match(r"^\s*videos you (?:opened|watched)", after) and ctx.f.get("topic"):
                pool = list(ctx.sc("nofilt_topic"))   # "1,094 of the 21,373 videos you opened then"
            whole = [i for i in pool if lib.member(i, sub)]
            self.F.add("base", "count of the whole", len(whole) == b_, b_, len(whole), where=ent_code(sub),
                       note="the M of 'N of the M'")
            if subj is not None and subj != sub:
                part = sum(1 for i in whole if lib.member(i, subj))
                self.F.add("base", "count of a part", part == a_, a_, part, where=ent_code(subj) + " in " +
                           ent_code(sub))
        # "on N (different) days"
        for m in re.finditer(r"\bon (\d[\d,]*) (?:different |separate )?days\b", s):
            n = int(m.group(1).replace(",", ""))
            done.add(m.start(1))
            subj = next((sp[2] for sp in reversed(spans) if sp[1] <= m.start() and sp[2][0] != "shorts"), None)
            if subj is not None and subj[0] == "topic" and subj[1].lower() == (ctx.f.get("topic") or "").lower():
                subj = None
            sc = ctx.sc("filt")
            if subj is not None:
                sc = {i: v for i, v in sc.items() if lib.member(i, subj)}
            d = lib.days(sc)
            self.F.add("base", "days", d == n, n, d, where=ent_code(subj) if subj else "window")
        # "<name> (48 videos)", "<name> (538)", "<name> led with 1,187 videos", "<name> at 767"
        # pass 6, second round (the hand check's false flags, n06.1, c03: "<ch> (14 long videos)", "<A> and <B> ...,
        # with 15 and 9 long videos"): a record's own count says "long" under "without Shorts"; two records, two counts
        for m in re.finditer(r"\b(?:with|at) (\d[\d,]*) and (\d[\d,]*)(?: long)? videos?\b", s):
            recs = [sp for sp in spans if sp[1] <= m.start() and sp[2][0] == "channel"]
            if len(recs) < 2:
                recs = [sp for sp in spans if sp[1] <= m.start() and sp[2][0] in ("theme", "area", "channel")]
            if len(recs) < 2:
                continue
            inside_t = next((x[2] for x in reversed(spans) if x[1] <= m.start() and x[2][0] == "theme"), None)
            for g_, sp in ((1, recs[-2]), (2, recs[-1])):
                done.add(m.start(g_))
                n = int(m.group(g_).replace(",", ""))
                ids = self.context_ids(s, spans, at=sp[0])
                if inside_t is not None and sp[2][0] == "channel":   # "the biggest <theme> channels, with 15 and 9"
                    ids = [i for i in ids if lib.member(i, inside_t)]
                got = _count_of(lib, ids, sp[2])
                self.F.add("base", "count of a record", got == n, n, got, where=ent_code(sp[2]))
        for m in re.finditer(r"\((\d[\d,]*)(?: long)?(?: videos?)?\)|\b(?:led with|at|with) (\d[\d,]*)(?: long)?"
                             r"(?: videos?)?(?=[ ,;.)]|$)", s):
            g = m.group(1) or m.group(2)
            pos = m.start(1) if m.group(1) else m.start(2)
            if pos in done or re.match(r"^\d[\d,]*(?:[.,]\d)?\s*(?:%|in 20)", s[pos:]) or \
                    re.match(r"^[.,]\d", s[m.end():]):
                continue
            n = int(g.replace(",", ""))
            if 1900 < n < 2100 and "," not in g:
                continue
            e = next((sp for sp in reversed(spans) if sp[1] <= m.start() and m.start() - sp[1] <= 3), None)
            if e is None or e[2][0] not in ("theme", "area", "channel", "topic"):
                continue
            done.add(pos)
            ids = self.context_ids(s, spans, at=e[0])
            got = _count_of(lib, ids, e[2])
            self.F.add("base", "count of a record", got == n, n, got, where=ent_code(e[2]))
        # "N in 2021", "against 4,474 in 2021": the topic's (or the window's) videos that year
        for m in re.finditer(r"\b(\d[\d,]*) in (20\d\d)\b", s):
            if m.start(1) in done or "%" in m.group(0):
                continue
            n, y = int(m.group(1).replace(",", "")), int(m.group(2))
            done.add(m.start(1))
            a_, b_ = date(y, 1, 1).toordinal(), date(y, 12, 31).toordinal()
            ids = list(lib.scope(a_, b_, ctx.f))
            e = next((sp[2] for sp in reversed(spans) if sp[1] <= m.start() and sp[2][0] in ("theme", "area", "channel")
                      and not re.search(r"[;.]|\bwhile\b", s[sp[1]:m.start()])), None)
            if e is not None:
                ids = [i for i in ids if lib.member(i, e)]
            got = len(ids)
            self.F.add("base", "count in a year", got == n, n, got, where=(ent_code(e) + " " if e else "") + str(y))
        # "N long videos", "N Shorts", "N videos", "N total videos", "N <name> videos"
        for m in re.finditer(r"\b(\d[\d,]*)\s+([A-Za-z][A-Za-z '&-]{0,40}?\s)?(videos|video|Shorts|ones)\b", s):
            if m.start(1) in done:
                continue
            g = m.group(1)
            n = int(g.replace(",", ""))
            if 1900 < n < 2100 and "," not in g:
                continue
            pre = s[max(0, m.start() - 12):m.start()].lower()
            if re.search(r"\bof (?:the|your)\s*$|\bfrom\s*$|\bto\s*$", pre):
                continue
            mid = (m.group(2) or "").strip()
            words = mid.lower().split()
            if any(w in ("more", "fewer", "less", "per", "a") for w in words):
                continue
            about = bool(re.search(r"\babout\s*$", pre))
            ids = self.context_ids(s, spans, at=m.start())
            rest = " ".join(w for w in words if w not in ("total", "different", "other", "youtube"))
            what = m.group(3).lower()
            ent = None
            if rest.startswith("long") or what == "ones" and "long" in low[max(0, m.start() - 30):m.start()] or \
                    re.match(r"^\s+largos\b", s[m.end():]):   # pass 6, second round (n07): "3.570 videos largos"
                ent, kind = ("long", ""), "count of long videos"
                rest = rest[4:].strip() if rest.startswith("long") else rest
            elif what == "shorts":
                ent, kind = ("shorts", ""), "count of Shorts"
            else:
                kind = "count of videos"
            bound = None
            if not rest and (re.search(r",\s*$", s[:m.start()]) or re.search(r"\bis new at the top:\s*$", s[:m.start()])) \
                    and spans and spans[0][0] == 0 and \
                    spans[0][2][0] in ("channel", "theme", "area"):
                # "<channel> is new: first opened in this span, 12 videos.": the sentence's own subject
                bound = spans[0][2]
            if not rest and bound is None:
                # pass 6 (A3): "<channel> had 137 videos", "<channel> adds another 11 videos": the record the verb
                # follows, in the number's own clause
                cl = _clause_start(low, m.start())
                near = [sp for sp in spans if cl <= sp[0] and sp[1] <= m.start() and
                        sp[2][0] in ("channel", "theme", "area", "topic")]
                if near and re.fullmatch(r"\s*(?:had|has|have|adds?|added|supplied|gave|brought|contributed|"
                                         r"fue el tema l[ií]der con|con|tuvo|"
                                         r"accounts? for|accounted for|made up|with|was behind|is behind)"
                                         r"(?:\s+(?:another|more|just|only|about|over|some|nearly|almost))*\s*",
                                         s[near[-1][1]:m.start()]):
                    bound = near[-1][2]
            if bound is not None:
                if not (bound[0] == "topic" and bound[1].lower() == (ctx.f.get("topic") or "").lower()):
                    ids = [i for i in ids if lib.member(i, bound)]
                kind = "count of a record's videos"
            named = bound is not None
            if rest:
                e = self.names.found.get(rest)
                if e is None:
                    continue   # words this audit cannot bind ("whose title or theme is about")
                if not (e[0] == "topic" and e[1].lower() == (ctx.f.get("topic") or "").lower()):
                    ids = [i for i in ids if lib.member(i, e)]
                    kind = "count of a record's videos"
                    named = True
            saved = bool(re.search(r"\byou saved\b", low[:m.start()]))
            mention = re.match(r'^\s*that mention "([^"]+)"(?: or "([^"]+)")?', s[m.end():])
            if not named and not saved and not mention and self.filtered and not re.match(r"^\s*of the \d", low):
                # ("Of the 291 on YouTube, 90 were Shorts": the part of a whole said before, not a count of its own)
                # pass 6 (A2, X4): a count of the whole scope is of what its words say: every filter in force must
                # be in the sentence (the topic's word, "long" or "without Shorts", the channel), else it is
                # recounted without the filter its words drop ("You opened 431 long videos" in an "only music"
                # answer is all the long videos)
                f_said, dropped = self.filters_said(low, ent)
                if dropped:
                    ids = self.context_ids(s, spans, at=m.start(), pool=list(lib.scope(ctx.a, ctx.b, f_said)))
                    kind = "count (its words drop a filter: " + ", ".join(dropped) + ")"
            if ent is not None:
                ids = [i for i in ids if lib.member(i, ent)]
            if mention:   # today's code reply: "N videos that mention "x"": the words alone
                ws = [w for w in mention.groups() if w]
                f0 = {k: x for k, x in ctx.f.items() if k not in ("topic", "topic_themes", "topic_also")}
                ids = [i for i in lib.scope(ctx.a, ctx.b, f0) if any(holds(lib.items[i]["cap"], w) for w in ws)]
                kind = "count of videos that mention the word"
            if saved:
                # pass 6 (A2, X8): "You saved 5 <theme> videos" is every such video saved; only "... you never
                # opened" (or "saved and never opened") is the ones never opened
                e = self.names.found.get(rest) if rest else None
                never = bool(re.search(r"\b(?:never|not yet|not|haven't|have not|didn't|did not) (?:opened|watched|"
                                       r"open|watch)\b|\bunopened\b|\bstill unopened\b", low))
                ids = [i for i in lib.saved if (e is None or lib.member(i, e)) and (i not in lib.opens or not never)]
                kind = "count of saved, never opened" if never else "count of saved (all of them)"
            got = len(ids)
            self.F.add("base", kind, close_count(n, got, about), n, got, where=ent_code(ent) if ent else "window")
        # pass 6 (X8): "You saved 6 <theme>" with no "videos" after the theme's name
        for m in re.finditer(r"\byou saved (\d[\d,]*) ", s, re.I):
            sp = next((x for x in spans if x[0] == m.end() and x[2][0] in ("theme", "area", "topic")), None)
            if sp is None or re.match(r"^\s*videos?\b", s[sp[1]:], re.I):
                continue   # "N <theme> videos" is read by the loop above
            n = int(m.group(1).replace(",", ""))
            never = bool(re.search(r"\b(?:never|not yet|not|haven't|have not|didn't|did not) (?:opened|watched|"
                                   r"open|watch)\b|\bunopened\b", low))
            ids = [i for i in lib.saved if lib.member(i, sp[2]) and (i not in lib.opens or not never)]
            self.F.add("base", "count of saved, never opened" if never else "count of saved (all of them)",
                       n == len(ids), n, len(ids), where=ent_code(sp[2]))
        # "N against M" (a comparison's two sides, now or in the span before)
        for m in re.finditer(r"\((\d[\d,]*) (?:[a-z ]+ )?against (\d[\d,]*)", s):
            tops = [t for t in self.ctx.sheet.get("topics") or [] if isinstance(t, dict) and t.get("name")]
            if len(tops) == 2:
                said = sorted([int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))], reverse=True)
                cur = sorted([len(self.ctx.sc("topic:" + t["name"] + "|")) for t in tops], reverse=True)
                prev = []
                if ctx.prev:
                    f0 = {k: x for k, x in ctx.f.items() if k not in ("topic", "topic_themes")}
                    prev = sorted([len(lib.scope(*ctx.prev, dict(f0, topic=t["name"]))) for t in tops], reverse=True)
                yrs = {int(y) for y in re.findall(r"\b(?:in|en) (20\d\d)\b", s, re.I)}
                before = bool(re.search(r"\bbefore\b|same part|\blast year\b", s, re.I)) or \
                    bool(yrs and date.fromordinal(ctx.b).year not in yrs)
                ok = said == (prev if before else cur)
                self.F.add("base", "comparison counts", ok, "/".join(map(str, said)),
                           "/".join(map(str, prev if before else cur)), note="the span before" if before else "")

    # ---------------------------------------------------------------- words
    def words(self, s, spans, base):
        lib, ctx = self.lib, self.ctx
        low = s.lower()
        # mostly / most of / mainly: half, by the named records together ("mostly A and B"), of the scope it speaks of
        m = re.search(r"\b(?:mostly|mainly|primarily|predominantly|chiefly|most of (?:it|them|your \w+) (?:was|were))"
                      r"\s+(?:on |about |into )?", low)
        if m:
            grp = []
            for sp in spans:
                if sp[0] < m.end() - 1:
                    continue
                gap = s[(grp[-1][1] if grp else m.end()):sp[0]]
                if not grp and len(gap.strip()) > 4:
                    break
                if grp and not re.fullmatch(r"(?:\s*at \d+(?:[.,]\d+)?%)?\s*(?:,|and|,\s*and|\(\d+%\)\s*and)\s*", gap):
                    break
                grp.append(sp)
            if grp:
                ents = [g[2] for g in grp]
                if ents[0][0] in ("shorts", "long"):
                    ents = ents[:1]
                b_ = base
                if b_ is None:
                    b_ = "filt" if (self.filtered and not re.search(r"\bof (?:everything|what you opened)\b", low)) \
                        else "all"
                if ents[0][0] in ("shorts", "long") and b_ in ("all", "filt"):
                    b_ = b_   # Shorts "mostly" of everything (or the filtered scope) unless a base is said
                ids = self.base_ids(b_) if isinstance(b_, str) and b_ not in ("own",) else None
                # pass 6 (A4's case): "<channel> was mostly <theme>": of that record's own videos, not the window's
                subj = next((sp for sp in spans if sp[1] <= m.start() and
                             re.fullmatch(r"\s*(?:was|were|is|are)\s+", s[sp[1]:m.start()]) and
                             sp[2][0] in ("channel", "theme", "area", "topic")), None)
                if subj is not None and ids and b_ in ("all", "filt"):
                    ids = [i for i in ids if lib.member(i, subj[2])]
                    b_ = b_ + " of " + ent_code(subj[2])
                if ids:
                    share = sum(1 for i in ids if any(lib.member(i, e) for e in ents)) / len(ids)
                    self.F.add("word", "mostly (half)", share >= 0.5, ">=50%", round(share * 100, 1),
                               where="+".join(ent_code(e) for e in ents), note="base " + b_, severity=1.0)
        # pass 6, second round (the hand check, b3 and n06.3: "That is up from 808 in the same part of 2025" after
        # "<theme> led with 373 videos": 808 was the topic's count): a change whose subject is only "That" or "It"
        if re.match(r"^\s*(?:that|this|it|these|those)(?:'s|\s+(?:is|was|were|are|has|had))?\s+(?:(?:been|gone|went|now)"
                    r"\s+)?(?:(?:up|down)\s+from|grew|rose|fell|dropped|climbed|slipped|faded|jumped|doubled|halved)\b", low):
            self.F.add("word", "a change with no subject", False, s.strip()[:40], "a named subject", severity=1.0)
        # pass 6, second round (the hand check, c06: "<A> and <B> were the biggest themes, with <ch1> and <ch2> behind
        # them": both channels were 95% a third theme): a channel set behind a theme has it as its own main theme
        if re.search(r"\bbehind (?:it|them)\b|\bdriven by\b|\bled by\b|\bits (?:biggest|main|top) channels?\b", low):
            ths = [sp[2] for sp in spans if sp[2][0] == "theme"]
            chs = [sp[2] for sp in spans if sp[2][0] == "channel"]
            if ths and chs:
                pool = self.base_ids("filt")
                for ch in chs:
                    c = Counter(lib.theme_of.get(i) for i in pool if lib.member(i, ch) and lib.theme_of.get(i))
                    if not c:
                        continue
                    main = c.most_common(1)[0][0]
                    ok = any(main == t[1].lower() for t in ths)
                    for t in ths if not ok else ():
                        # or one of that theme's own biggest channels ("<theme>, driven by A, B and C")
                        tc = Counter(lib.items[i]["c"] for i in pool if lib.theme_of.get(i) == t[1].lower() and
                                     lib.items[i]["c"])
                        if ch[1] in [k for k, _ in tc.most_common(5)]:
                            ok = True
                    self.F.add("word", "a channel behind a theme it is not in", ok, ent_code(ch),
                               code_of("theme", main), severity=1.0)
        # pass 6, second round (the hand check, n07: "subió 2 puntos frente a 2021", a 1.68-point move): X14 in Spanish
        for m in re.finditer(r"\b(?:subi[oó]|baj[oó]|cay[oó]|creci[oó]|aument[oó]|perdi[oó]|gan[oó])\s+(\d+(?:[.,]\d+)?)"
                             r"\s+puntos?\b", low):
            x = float(m.group(1).replace(",", "."))
            self.F.add("word", "move under 3 points said", x >= 3, f"{x:g} puntos", ">= 3 points", severity=0.5)
        # led / top / came first / ahead of / followed by / came next / close behind
        if re.search(r"\b(?:led|leads|top|topped|came first|ahead of|followed by|came next|close behind|then)\b", low):
            self.order(s, spans)
        # twice / N times / doubled
        m = re.search(r"\b(more than doubled|nearly doubled|doubled|tripled|twice|(?:about )?(\d+(?:\.\d+)?|two|three|"
                      r"four|five|six|seven|eight|nine|ten) times)\b", low)
        if m:
            self.ratio(s, m, spans)
        # peaked
        if re.search(r"\bpeaked\b|\bmore than in any other\b", low):
            self.peaked(s, spans)
        # new
        m = re.search(r"\b(?:was|were|is|are) new\b|\bnew (?:then|that year|this year|in 20\d\d)\b", low)
        if m:
            # pass 6 (A3): "new" goes with the names of its own clause ("A, B and C each supplied one, while 2 channels
            # were new" says nothing of A, B or C), and "N channels were new" is a count of the channels first opened
            cl = _clause_start(low, m.start())
            cnt = re.search(r"\b(\d+) (?:other |more )?(?:channels?|creators?) (?:were|was|are|is) new\b", low[cl:])
            if cnt:
                self.new_channels_count(int(cnt.group(1)))
            else:
                for sp in spans:
                    if cl <= sp[0] and sp[1] <= m.start() and sp[2][0] in ("theme", "channel"):
                        self.new_claim(sp[2])
                        if sp[2][0] == "channel" and ctx.a is not None and ctx.a == ctx.b:
                            self.facts.append(("new channels", None, "named", self.si))
        for m in re.finditer(r"\bone of (\d+) (?:new )?channels you opened for the first time\b|"
                             r"\b(\d+) (?:channels?|creators?) (?:you opened |you watched )?for the first time\b|"
                             r"\b(\d+) new channels\b", low):
            self.new_channels_count(int(next(g for g in m.groups() if g)))
        # every year
        if re.search(r"\bevery year\b|\beach year\b", low):
            self.every_year(s, spans)
        # pass 6 (A2, X5, X9, X13, X14): every change with its two values, of one measure
        self.changes(s, spans)
        m = re.search(r"\bgap (?:has |had )?(narrowed|widened|grown|grew|shrunk|shrank|closed)\b", low)
        if m:
            self.gap_word(m.group(1))
        # X3: "Shorts" with its capital (an offer in quotes, "say \"without shorts\"", is the person's own words)
        if re.search(r"\bshorts\b", re.sub(r"\"[^\"]*\"|“[^”]*”", " ", s)):
            self.F.add("word", "Shorts written without its capital", False, "shorts", "Shorts", severity=0.3)
        # from X% to Y% with a direction
        for m in re.finditer(r"\b(rose|grew|fell|faded|dropped|climbed|went up|went down|up|down|doubled|nearly doubled)"
                             r"\b[^.;%]{0,40}?\bfrom (\d+(?:\.\d+)?)%[^.;%]{0,60}?\bto (\d+(?:\.\d+)?)%", low):
            a_, b_ = float(m.group(2)), float(m.group(3))
            verb = m.group(1) or ""
            if verb:
                up = verb in ("rose", "grew", "climbed", "went up", "up", "doubled", "nearly doubled")
                self.F.add("word", "direction", (b_ > a_) == up, f"{verb} {a_}->{b_}", "up" if b_ > a_ else "down",
                           severity=1.0)

    _VERB = re.compile(r"\b(rose|grew|climbed|jumped|increased|went up|nearly doubled|more than doubled|doubled|"
                       r"tripled|fell|faded|dropped|slipped|declined|shrank|decreased|went down|halved|eased)\b")
    _UP = {"rose", "grew", "climbed", "jumped", "increased", "went up", "nearly doubled", "more than doubled",
           "doubled", "tripled"}

    def changes(self, s, spans):
        """pass 6 (A2, X5): a change is said with two values of the SAME measure ("from 3% to 6%", "from 126 to 205
        videos") or as a move in points ("rose by 16 points"); a share against a count ("climbed to 6% from 126
        videos before") or one value ("faded from 210") is reported. X14: a move under 3 points is not said. X9: the
        move is kept as a fact, so the same move said twice (in points, then as two values) is a repeat."""
        low = s.lower()
        cuts = [0] + [m.end() for m in _CLAUSE.finditer(low)] + [len(low)]
        for c0, c1 in zip(cuts, cuts[1:]):
            cl = low[c0:c1]
            v = self._VERB.search(cl)
            if not v:
                continue
            tail = cl[v.end():]
            # what is not a value of the change: dates, years, spans, ratios, minutes
            t2 = re.sub(r"\([^)]*\)", " ", tail)
            t2 = re.sub(r"\b\d{1,2} (?:" + "|".join(MONTHS) + r")\b|\b(?:" + "|".join(MONTHS) + r") \d{1,2}\b", " ", t2)
            t2 = re.sub(r"\b20\d\d\b", " ", t2)
            t2 = re.sub(r"\b\d+ (?:weeks?|months?|days?|years?|hours?|minutes?|min|times)\b", " ", t2)
            vals = [(float(x.replace(",", "")), unit.strip()) for x, unit in
                    re.findall(r"(\d[\d,]*(?:\.\d+)?)(\s?%|\s?points?\b)?", t2)]
            subj = [sp for sp in spans if c0 <= sp[0] and sp[1] <= c0 + v.start()]
            rec = subj[-1][2] if subj else None
            where = ent_code(rec) if rec else ""
            if not vals:
                # "while music slipped": a change said with no value at all (X5: two values, or it is not said);
                # "has faded: 12 in 2026 ..., against 131 in 2023" says its values after the colon
                if not cl.rstrip().endswith(":"):
                    self.F.add("word", "change with no value", False, v.group(1), "two values of one measure",
                               where=where, severity=0.5)
                continue
            pts = [x for x, u in vals if u.startswith("point")]
            if pts:
                for x in pts:
                    self.F.add("word", "move under 3 points said", x >= 3, f"{x:g} points", ">= 3 points",
                               where=where, severity=0.5)
                    self.facts.append(("move", rec, x, self.si))
                    if rec is not None and rec[0] in ("theme", "area", "topic", "channel") and self.ctx.prev:
                        # the move itself: the record's share now less its share in the span before, in points
                        b_ = "filt" if self.filtered else "all"
                        now_ids, pre_ids = self.base_ids(b_), self.base_ids(b_, scope="prev")
                        if now_ids and pre_ids:
                            d = 100 * (sum(1 for i in now_ids if self.lib.member(i, rec)) / len(now_ids) -
                                       sum(1 for i in pre_ids if self.lib.member(i, rec)) / len(pre_ids))
                            up = v.group(1) in self._UP
                            self.F.add("word", "move in points", abs(abs(d) - x) <= 1.0 and (d > 0) == up,
                                       f"{v.group(1)} {x:g}", round(d, 1), where=where, note="base " + b_,
                                       severity=1.0)
                continue
            pct = [x for x, u in vals if u == "%"]
            cnt = [x for x, u in vals if u != "%"]
            if pct and cnt:
                self.F.add("word", "change with mixed measures", False, f"{len(pct)} share, {len(cnt)} count",
                           "two values of one measure", where=where, severity=1.0)
            elif len(vals) < 2:
                self.F.add("word", "change with one value", False, f"{vals[0][0]:g}{vals[0][1]}",
                           "two values of one measure", where=where, severity=1.0)
            else:
                frm = re.search(r"\bfrom (\d[\d,]*(?:\.\d+)?)", t2)
                to = re.search(r"\bto (\d[\d,]*(?:\.\d+)?)", t2)
                if frm and to:
                    a_, b_ = float(frm.group(1).replace(",", "")), float(to.group(1).replace(",", ""))
                    up = v.group(1) in self._UP
                    self.F.add("word", "change with two values", (b_ > a_) == up, f"{v.group(1)} {a_:g}->{b_:g}",
                               "up" if b_ > a_ else "down", where=where, severity=1.0)
                    if pct:
                        self.facts.append(("move", rec, abs(b_ - a_), self.si))

    def gap_word(self, word):
        """X13: "the gap has narrowed / widened" said of a comparison where the ratio and the difference move apart."""
        lib, ctx = self.lib, self.ctx
        tops = [t for t in ctx.sheet.get("topics") or [] if isinstance(t, dict) and t.get("name")]
        if len(tops) != 2 or not ctx.prev:
            return
        f0 = {k: x for k, x in ctx.f.items() if k not in ("topic", "topic_themes", "topic_also")}
        cur = [len(ctx.sc("topic:" + t["name"] + "|")) for t in tops]
        prev = [len(lib.scope(*ctx.prev, dict(f0, topic=t["name"]))) for t in tops]
        if min(cur) == 0 or min(prev) == 0:
            return
        r_now, r_prev = max(cur) / min(cur), max(prev) / min(prev)
        d_now, d_prev = abs(cur[0] - cur[1]), abs(prev[0] - prev[1])
        apart = (r_now > r_prev) != (d_now > d_prev)
        self.F.add("word", "gap word (ratio and difference move apart)", not apart, f"gap {word}",
                   f"ratio {r_prev:.1f}->{r_now:.1f}, difference {d_prev}->{d_now}", severity=0.5)

    def repeats(self):
        """X9 (U4): one fact said in two sentences: a move (in points, or as two values: one fact), the channels
        new that day (their count, or one named as new)."""
        groups = defaultdict(list)
        for kind, rec, val, si in self.facts:
            groups[(kind, rec)].append((val, si))
        for (kind, rec), vs in groups.items():
            if kind == "new channels":
                sis = sorted({si for _, si in vs})
                if len(sis) > 1:
                    self.F.sentence = f"sentences {sis}"
                    self.F.add("word", "the same fact twice", False, "new channels", f"in {len(sis)} sentences",
                               severity=1.0)
                continue
            seen = []
            for val, si in vs:
                hit = next((s0 for v0, s0 in seen if s0 != si and abs(v0 - val) <= 1.0), None)
                if hit is not None:
                    self.F.sentence = f"sentences {[hit, si]}"
                    self.F.add("word", "the same fact twice", False, f"move of {val:g} points",
                               f"said in sentences {hit} and {si}", where=ent_code(rec) if rec else "",
                               severity=1.0)
                seen.append((val, si))

    def order(self, s, spans):
        """Names said in an order of rank: the first 'led', then 'ahead of' / 'followed by' / 'then' the next ones,
        ranked inside the scope the sentence speaks of (context_ids)."""
        lib = self.lib
        low = s.lower()
        named = [sp for sp in spans if sp[2][0] in ("theme", "area", "channel")]
        if not named:
            return
        led = re.search(r"\b(led|leads|topped|came first)\b|\bwas (?:the )?top\b", low)
        if led and not re.search(r"\bled by\b|\bwas led\b|\bled every\b|\bled each\b", low):
            e = next((sp for sp in reversed(named) if sp[1] <= led.start()), None) or \
                next((sp for sp in named if sp[0] >= led.end()), None)
            lead_in = re.match(r"^\s*(?:inside|in|within|behind)\s+", low)
            if e is not None:
                ids = self.context_ids(s, spans, at=e[0])
                if lead_in and e is named[0] and e[0] == lead_in.end():
                    e = named[1] if len(named) > 1 else None
                # pass 6 (A3): "<channel> led <topic>": ranked inside the record named right after "led"
                after = next((sp for sp in spans if sp[0] == led.end() + 1 and
                              sp[2][0] in ("topic", "theme", "area")), None)
                if after is not None and e is not None and after[2] != e[2]:
                    ids = [i for i in ids if lib.member(i, after[2])]
                if e is not None:
                    e = e[2]
                    rk = _rank(lib, ids, e[0])
                    key = e[1].lower() if e[0] == "theme" else e[1]
                    top = rk.most_common(1)[0] if rk else (None, 0)
                    self.F.add("word", "led (first)", rk.get(key, 0) >= top[1], rk.get(key, 0), top[1],
                               where=ent_code(e), severity=1.0)
        seq = re.search(r"\b(ahead of|followed by|then|came next|close behind|with [^,.;]+ next)\b", low)
        if seq:
            kinds = Counter(sp[2][0] for sp in named)
            kind = kinds.most_common(1)[0][0]
            chain = [sp for sp in named if sp[2][0] == kind]
            lead_in = re.match(r"^\s*(?:behind|inside|in|within)\s+", low)
            if lead_in and chain and chain[0][0] == lead_in.end():
                chain = chain[1:]
            if len(chain) >= 2:
                ids = self.context_ids(s, spans, at=chain[0][0])
                rk = _rank(lib, ids, kind)
                vals = [rk.get(c[2][1].lower() if kind == "theme" else c[2][1], 0) for c in chain]
                ok = all(vals[k] >= vals[k + 1] for k in range(len(vals) - 1))
                self.F.add("word", "order", ok, "/".join(map(str, vals)), "non-increasing",
                           where=">".join(ent_code(c[2]) for c in chain), severity=1.0)
                if re.search(r"\b(came next|close behind|followed by)\b", low) and ok:
                    order = [k for k, _ in rk.most_common()]
                    k0 = chain[0][2][1].lower() if kind == "theme" else chain[0][2][1]
                    k1 = chain[1][2][1].lower() if kind == "theme" else chain[1][2][1]
                    if k0 in order and k1 in order:
                        self.F.add("word", "next place", order.index(k1) == order.index(k0) + 1, order.index(k1) + 1,
                                   order.index(k0) + 2, where=ent_code(chain[1][2]), severity=1.0)

    def ratio(self, s, m, spans):
        word = m.group(1)
        nums = [float(x.replace(",", "")) for x in re.findall(r"(\d[\d,]*(?:\.\d+)?)%?", s)
                if not re.fullmatch(r"20\d\d", x)]
        if "doubled" in word or "tripled" in word:
            pc = re.findall(r"(\d+(?:\.\d+)?)%", s)
            if len(pc) >= 2:
                a_, b_ = sorted(float(x) for x in pc[:2])
                r = b_ / a_ if a_ else 0
                lo, hi = {"doubled": (1.8, 2.3), "nearly doubled": (1.6, 2.0), "more than doubled": (2.0, 99),
                          "tripled": (2.7, 3.4)}.get(word, (0, 99))
                self.F.add("word", "ratio word", lo <= r <= hi, word, round(r, 2), severity=1.0)
            return
        g2 = m.group(2) or ""
        n = 2 if word == "twice" else (float(g2) if re.fullmatch(r"\d+(?:\.\d+)?", g2) else NUM_WORDS.get(g2))
        pair = re.search(r"\((\d[\d,]*)[^()]*?against (\d[\d,]*)", s) or re.search(r"(\d[\d,]*) against (\d[\d,]*)", s)
        if pair and n:
            a_, b_ = int(pair.group(1).replace(",", "")), int(pair.group(2).replace(",", ""))
            r = a_ / b_ if b_ else 0
            about = "about" in word or "about" in s.lower()
            ok = (abs(r - n) <= max(0.5, 0.15 * n) if n >= 2 else abs(r - n) <= 0.25) if about else \
                (abs(r - n) <= 0.25 * n)
            self.F.add("word", "ratio word", ok, f"{n:g}x", round(r, 2), severity=1.0)

    def peaked(self, s, spans):
        """'<theme> peaked then, at 5%, more than in any other three months': the theme's share in the window against
        EVERY span of that length the record holds, sliding by a month (spans with at least 100 videos)."""
        lib, ctx = self.lib, self.ctx
        low = s.lower()
        pk = re.search(r"\bpeaked\b|\bmore than in any other\b", low)
        clause_start = max(low.rfind(";", 0, pk.start()), low.rfind(":", 0, pk.start()), 0)
        named = [sp[2] for sp in spans if clause_start <= sp[0] < pk.start() and sp[2][0] in ("theme", "area")]
        if not named or ctx.a is None:
            return
        m = re.search(r"more than in any other ([a-z0-9 ]+?)(?:[.,;)]|$)", low)
        months = None
        if m:
            w = m.group(1).strip()
            months = SPAN_WORDS.get(w) or next((v for k, v in SPAN_WORDS.items() if w.endswith(k)), None)
        if months is None:
            a, b = date.fromordinal(ctx.a), date.fromordinal(ctx.b)
            months = max(1, round(((b - a).days + 1) / 30.4))
        win = list(ctx.sc("filt"))
        keys = sorted(lib.month_items)
        f = ctx.f
        for e in named[:4]:
            here = _count_of(lib, win, e) / len(win) if win else 0
            best = (0.0, None)
            for k in range(len(keys) - months + 1):
                ks = keys[k:k + months]
                y0, m0 = ks[0]
                y1, m1 = (y0 + (m0 - 1 + months - 1) // 12, (m0 - 1 + months - 1) % 12 + 1)
                if ks[-1] != (y1, m1):
                    continue   # a gap in the record
                a_ = date(y0, m0, 1).toordinal()
                b_ = ((date(y1, m1 + 1, 1) if m1 < 12 else date(y1 + 1, 1, 1)) - timedelta(days=1)).toordinal()
                if b_ > lib.newest or (a_ <= ctx.a and b_ >= ctx.b):
                    continue   # a span past the record's end, or the window itself
                if abs(a_ - ctx.a) <= 3 and abs(b_ - ctx.b) <= 3:
                    continue
                ids = set().union(*(lib.month_items[x] for x in ks))
                if f:
                    ids = [i for i in ids if lib.passes(i, f)]
                if len(ids) < 100:
                    continue
                sh = _count_of(lib, ids, e) / len(ids)
                if sh > best[0]:
                    best = (sh, date(y0, m0, 1).isoformat())
            ok = here >= best[0] - 1e-9
            self.F.add("word", "peaked (every span)", ok, round(here * 100, 1), round(best[0] * 100, 1),
                       where=ent_code(e), note=f"{months}-month spans; highest from {best[1]}", severity=1.0)

    def new_claim(self, e):
        lib, ctx = self.lib, self.ctx
        if not ctx.prev:
            return
        cur = _count_of(lib, ctx.sc("filt"), e)
        if e[0] == "channel":
            fw = lib.first_watch(e[1])
            ok = fw is not None and ctx.a is not None and fw >= ctx.a
            self.F.add("word", "new (first seen in the window)", ok, "new", _d(fw).isoformat() if fw else None,
                       where=ent_code(e), severity=1.0)
            return
        before = _count_of(lib, ctx.sc("prev"), e)
        ok = before <= 5 and before * 2 <= cur
        self.F.add("word", "new (absent before)", ok, f"{cur} now", f"{before} before", where=ent_code(e), severity=1.0)

    def new_channels_count(self, n):
        """"2 channels were new that day": the channels of the window first opened in it."""
        lib, ctx = self.lib, self.ctx
        if ctx.a is None:
            return
        chans = {lib.items[i]["c"] for i in ctx.sc("filt") if lib.items[i]["c"]}
        new = [c for c in chans if (lib.first_watch(c) or 0) >= ctx.a]
        self.F.add("word", "new channels (count)", len(new) == n, n, len(new), severity=1.0)
        self.facts.append(("new channels", None, n, self.si))

    def every_year(self, s, spans):
        lib, ctx = self.lib, self.ctx
        named = [sp[2] for sp in spans if sp[2][0] in ("theme", "area", "channel")]
        if not named or ctx.a is None:
            return
        e = named[0]
        led = bool(re.search(r"\bled every year|\bled each year|\bleads every year", s.lower()))
        bad = []
        for label, a_, b_ in periods_of(ctx.a, ctx.b, lib, unit="year")[0]:
            sc = ctx.sc(f"period:{max(a_, ctx.a)}:{min(b_, ctx.b)}")
            if len(sc) < 50:
                continue
            rk = _rank(lib, sc, e[0])
            key = e[1].lower() if e[0] == "theme" else e[1]
            if led:
                if not rk or rk.get(key, 0) < rk.most_common(1)[0][1]:
                    bad.append(label)
            elif not rk.get(key):
                bad.append(label)
        self.F.add("word", "every year", not bad, "every year", ",".join(bad) or "each year", where=ent_code(e),
                   severity=1.0)


def audit_first_last(ctx, F, text):
    """A first or a last: the date said is the first (last) day a video on the topic was opened."""
    if ctx.kind not in ("first", "last") or not ctx.f.get("topic"):
        return
    lib = ctx.lib
    sc = lib.scope(None, lib.newest, ctx.f)
    if not sc:
        return
    days = [e[0] for v in sc.values() for e in v]
    want = min(days) if ctx.kind == "first" else max(days)
    first = (text or "").split("\n")[0]
    F.sentence = first
    m = re.search(r"\b(\d{1,2}) (" + "|".join(MONTHS) + r") (20\d\d)\b", first.lower())
    if m:
        said = date(int(m.group(3)), MONTHS.index(m.group(2)) + 1, int(m.group(1))).toordinal()
        F.add("base", "first or last date", said == want, _d(said).isoformat(), _d(want).isoformat(), severity=1.0)
    # pass 6 (A1): the first (last) item is the one opened at the earliest (latest) INSTANT, not any item of that day;
    # the sentence's names, the cards and their order are checked against that order
    is_first = ctx.kind == "first"
    key = {i: (min if is_first else max)(lib.open_at[i]) for i in sc if lib.open_at.get(i)}
    order = sorted(key, key=lambda i: (key[i] if is_first else -key[i], i))
    if not order:
        return
    top = order[0]
    it = lib.items[top]
    lost = re.search(r"\b(?:first|last) (?:watched|opened|saw|started watching)\s+(?:on\s+)?\d{1,2} [A-Z][a-z]+",
                     first)
    if lost:
        F.add("word", "first or last with no object", False, lost.group(0), "watched what?", severity=1.0)
    after_date = first[m.end():] if m else first
    # pass 6, second round (the hand check's false flag, n05a: "... from <channel>. Most of it has been <theme> (N of
    # M)." read as the first video's theme): the first or last is the sentence that says it, not the one after it
    after_date = re.split(r"(?<=[.!?])\s+(?=[A-Z])", after_date, maxsplit=1)[0]
    fm = re.search(r"\bfrom ([^,.;]+?)\s*(?:[,.;]|$)", after_date)
    if fm and it["c"]:
        said_c = fm.group(1).strip()
        known = {lib.items[i]["c"] for i in sc if lib.items[i]["c"]}
        if said_c in known:
            F.add("base", "first or last: its channel", said_c == it["c"], code_of("channel", said_c),
                  code_of("channel", it["c"]), severity=1.0)
    th = lib.theme_of.get(top)
    for nm in sorted(lib.theme_names, key=len, reverse=True):
        if re.search(r"(?<!\w)" + re.escape(nm) + r"(?!\w)", after_date.lower()):
            F.add("base", "first or last: its theme", nm == th, code_of("theme", nm),
                  code_of("theme", th) if th else None, severity=1.0)
            break
    cards = _cards(text)
    if not cards:
        return
    zone = lib.zone
    pos = {i: k for k, i in enumerate(order)}
    seq = []
    for n, ch, dd, title in cards:
        cand = [i for i in sc if lib.items[i]["c"] == ch and _title_fits(lib.items[i]["cap"], title)]
        if not cand:
            continue
        i = min(cand, key=lambda x: pos.get(x, 10 ** 9))
        seq.append((n, i))
        if dd and i in key:
            local = datetime.fromtimestamp(key[i], zone)
            want_dd = f"{local.day} {MONTHS[local.month - 1][:3].title()}"
            F.sentence = f"card {n}"
            F.add("base", "card date (first or last open)", dd.split(" 20")[0] == want_dd, dd, want_dd, severity=1.0)
    if seq:
        F.sentence = "the cards"
        F.add("base", "first or last: the first card", seq[0][1] == top, f"card {seq[0][0]}",
              f"item {pos.get(seq[0][1], -1) + 1} in order", severity=1.0)
        ks = [pos.get(i, 10 ** 9) for _, i in seq]
        F.add("base", "cards in order (by the instant)", all(ks[k] < ks[k + 1] for k in range(len(ks) - 1)),
              "/".join(str(n) for n, _ in seq), "/".join(str(k + 1) for k in ks), severity=1.0)


_CARD = re.compile(r"^(\d+)\. (.+?) · (?:(\d{1,2} [A-Z][a-z]{2}(?: 20\d\d)?) · )?")


def _cards(text):
    """[(n, channel, day words or None, title)] of the numbered cards of a reply (a card's header line, then its
    title on the next line; a repeated header or a link is not a title)."""
    lines = [x.strip() for x in (text or "").split("\n")]
    out, seen = [], set()
    for k, ln in enumerate(lines):
        m = _CARD.match(ln)
        if not m or int(m.group(1)) in seen:
            continue
        nxt = lines[k + 1] if k + 1 < len(lines) else ""
        if not nxt or _CARD.match(nxt) or nxt.startswith("http"):
            continue
        seen.add(int(m.group(1)))
        out.append((int(m.group(1)), m.group(2).strip(), m.group(3), nxt))
    return out


def _title_fits(cap, title):
    a = " ".join((cap or "").lower().split())
    b = " ".join(title.lower().rstrip("…").split())
    return bool(b) and a.startswith(b[:60])


# ============================================================================ the run over a folder of answers
def shape_of(ans):
    sh = ans.get("sheet") or {}
    f = sh.get("filters") or {}
    spec = ans.get("window") or {}
    bits = [sh.get("kind") or "code-only", spec.get("kind") or "?", ans.get("how") or "?"]
    if f.get("topic"):
        bits.append("topic")
    if f.get("without_shorts"):
        bits.append("without Shorts")
    if f.get("channel"):
        bits.append("channel")
    if ans.get("follow"):
        bits.append("follow-up")
    return " | ".join(bits)


def paths_of(form):
    out = set()
    if not isinstance(form, dict):
        return out
    blob = json.dumps(form)
    for m in re.finditer(r"\{([a-z_]+(?:\[\d+\])?(?:\.[a-z_]+(?:\[\d+\])?)*)\}", blob):
        out.add(m.group(1))
    return out


_LIMITS = re.compile(r"^(?:I can(?:'|’)?t see|I cannot see|I can not see|I don(?:'|’)?t have|I have no)\b")


def audit_limits(F, text):
    """pass 6 (X11, R-H): what the bot cannot see is one clause of the answer's own window words ("In the 10 days up to
    30 October, where your export ends, ..."), never a sentence of its own; the new-export hint at most once."""
    hints = 0
    for typ, s, _ in sentences(text):
        if typ != "text":
            continue
        F.sentence = s
        if _LIMITS.match(s):
            F.add("word", "limits said as a sentence of their own (R-H)", False, s.split(":")[0][:40],
                  "one clause of the window words", severity=1.0)
        hints += len(re.findall(r"\bnew export\b", re.sub(r"\"[^\"]*\"|“[^”]*”", " ", s), re.I))
    if hints > 1:
        F.add("word", "the new-export hint said more than once", False, hints, 1, severity=0.5)


def _area_word(w):
    w = w.lower().strip()
    return any(w in ws or w == a.lower() for a, ws in CATEGORY_WORDS.items())


NAME_RATE_FLOOR = 0.25   # my reading of 19.P2's T8: a theme is a narrow topic's only when this share of its own
                         # items' text says the topic's word


def audit_topic_mapping(ctx, F):
    """pass 6 (X12): a narrow topic word ("quilling") takes a theme only when a measured share of that theme's own
    items say the word (an area word, "gaming", takes its area's themes). The mapping is the sheet's, recounted."""
    lib = ctx.lib
    sh = ctx.sheet
    rows = []
    fl = sh.get("filters") or {}
    if fl.get("topic") and fl.get("topic_themes"):
        rows.append((fl["topic"], list(fl["topic_themes"]), "filters.topic_themes"))
    for k, t in enumerate(sh.get("topics") or []):
        if isinstance(t, dict) and t.get("name") and t.get("themes"):
            rows.append((t["name"], list(t["themes"]), f"topics[{k}].themes"))
    done = set()
    for word, themes, where in rows:
        if _area_word(word):
            continue
        for th in themes:
            nm = th.lower()
            if (word.lower(), nm) in done:
                continue
            done.add((word.lower(), nm))
            mem = [i for i, t in lib.theme_of.items() if t == nm and i in lib.opens]
            if not mem:
                continue
            said = sum(1 for i in mem if holds(lib.items[i]["cap"], word))
            rate = said / len(mem)
            F.sentence = f"topic {code_of('topic', word)}"
            F.add("sheet", "topic mapping (a theme whose items do not say the word)", rate >= NAME_RATE_FLOOR,
                  round(100 * rate, 1), f">= {int(100 * NAME_RATE_FLOOR)}%", where=where + ":" + code_of("theme", nm),
                  note=f"{said} of {len(mem)} items say it", severity=1.0)


def audit_answer(lib, ans, today):
    ans = dict(ans)
    ans["used_paths"] = paths_of(ans.get("form"))
    ctx = Ctx(lib, ans, today)
    ans["window"] = ctx.spec
    F = Findings(ans["id"], shape_of(ans))
    audit_limits(F, ans.get("sent") or "")
    if ctx.sheet:
        audit_topic_mapping(ctx, F)
        audit_sheet(ctx, F)
        if not getattr(ctx, "window_differs", False):
            TextAudit(ctx, F).run(ans.get("sent") or "")
            audit_first_last(ctx, F, ans.get("sent") or "")
    return F.rows


def load_answers(folder):
    out = []
    for name in sorted(os.listdir(folder)):
        if name.endswith(".json") and name.startswith("a_"):
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                out.append(json.load(f))
    return out


def link_follow_ups(answers):
    """A follow-up ("without shorts") is read with the messages it follows: `chain` holds their texts in order."""
    by_id = {a["id"]: a for a in answers}
    for a in answers:
        if not a.get("follow") or "." not in a["id"]:
            continue
        stem, k = a["id"].rsplit(".", 1)
        chain = []
        if k.isdigit():
            for j in range(int(k)):
                p = by_id.get(f"{stem}.{j}")
                if p is not None:
                    chain.append(p.get("text") or "")
        if not chain and a.get("parent_text"):
            chain = [a["parent_text"]]
        a["chain"] = chain
        if not a.get("parent_text") and chain:
            a["parent_text"] = chain[0]
    return answers


ALLOW = os.path.join(HERE, "eval_claims_allow.json")


def _shape_re(shape):
    """A case's shape ("<channel> was mostly <theme>, with N% of its videos in that theme.") as a pattern."""
    out = ""
    for part in re.split(r"(<[a-z ]+>|\bN\b)", shape):
        if not part:
            continue
        if part.startswith("<"):
            out += r".+?"
        elif part == "N":
            out += r"\d[\d,.]*"
        else:
            out += re.escape(part)
    return re.compile("^" + out.rstrip(r"\.") + r"\.?$", re.I)


def load_allow(path=ALLOW):
    """pass 6 (A4): the hand-counted cases where the auditor, not the sentence, is wrong."""
    try:
        cases = json.load(open(path, encoding="utf-8")).get("cases") or []
    except (OSError, ValueError):
        return []
    return [(c.get("kind") or "", _shape_re(c.get("shape") or ""), k) for k, c in enumerate(cases)]


def mark_allowed(rows, allow):
    """A mismatch that matches an allowed case (its kind and the shape of its sentence) is kept and marked
    `allowed` (the case's number): listed apart in the summary as the auditor's reading, never dropped silently."""
    for r in rows:
        if r["ok"]:
            continue
        for kind, pat, k in allow:
            if kind == f"{r['audit']}/{r['kind']}" and pat.match((r.get("sentence") or "").strip()):
                r["allowed"] = k
                break
    return rows


def summarise(rows, answers):
    allowed = [r for r in rows if not r["ok"] and r.get("allowed") is not None]
    bad = [r for r in rows if not r["ok"] and r.get("allowed") is None]
    by = Counter((r["audit"], r["kind"]) for r in bad)
    checked = Counter(r["audit"] for r in rows)
    out = {"answers": len(answers), "with_sheet": sum(1 for a in answers if a.get("sheet")),
           "claims_checked": len(rows), "by_audit": dict(checked), "mismatches": len(bad),
           "mismatches_by_kind": {f"{a}/{k}": n for (a, k), n in by.most_common()},
           "sheet_used_mismatches": sum(1 for r in bad if r["audit"] == "sheet" and r["note"] == "used"),
           "allowed": len(allowed),
           "allowed_rows": [{k: r[k] for k in ("q", "audit", "kind", "said", "recount", "where", "allowed")}
                            for r in allowed]}
    worst = sorted(bad, key=lambda r: (-r["severity"], r["q"]))
    out["worst"] = [{k: r[k] for k in ("q", "shape", "audit", "kind", "said", "recount", "where", "note")}
                    for r in worst[:40]]
    return out


def audit_folder(folder, library=None, derived=None, tz=None, today=None, json_out=None, quiet=False):
    answers = load_answers(folder)
    if not answers:
        raise SystemExit(f"no answers in {folder}")
    lib_path = library or answers[0].get("library")
    tz = tz or answers[0].get("timezone") or "UTC"
    today = today or date.fromisoformat(answers[0].get("today") or date.today().isoformat())
    lib = Library(lib_path, derived, tz)
    link_follow_ups(answers)
    rows = []
    for a in answers:
        rows += audit_answer(lib, a, today)
    mark_allowed(rows, load_allow())
    summ = summarise(rows, answers)
    if json_out:
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump({"summary": summ, "rows": rows}, f, indent=1, default=str)
    if not quiet:
        print(json.dumps({k: v for k, v in summ.items() if k != "worst"}, indent=1))
        for w in summ["worst"][:20]:
            print(w["q"], "|", w["shape"], "|", w["audit"], w["kind"], "| said", w["said"], "| recount",
                  w["recount"], "|", w["where"], w["note"])
    return summ, rows


# ============================================================================ capture (the bot, only to send)
def capture(qfile, out, live=0, today=None):
    """Send each question through the bot in process on MVP_HOME; keep the sent text, the sheet the writer was shown
    and its form. The first `live` writer calls go to the real model, the rest to the made-up writer."""
    sys.path.insert(0, os.path.dirname(HERE))
    from mvp import llm
    from mvp.bot import Bot, make_channel
    from mvp.store import Store
    from mvp.tests.r12_writer import fake_insight
    real = llm.chat_json
    box = {"live_left": live, "seen": [], "spent": 0.0, "other": []}

    def door(system, user, purpose, prompt_version, **kw):
        if purpose != "mvp_insight":   # a question code did not read as history: no paid call, its error reply
            box["other"].append(purpose)
            raise RuntimeError("no model call but the writer's in a capture: " + purpose)
        if box["mode"] == "live" and box["live_left"] > 0:
            box["live_left"] -= 1
            raw, cost = real(system, user, purpose, prompt_version, **kw)
            box["spent"] += cost or 0.0
            how = "live"
        else:
            raw, cost, how = fake_insight(user, system), 0.0, "fake"
        box["seen"].append({"user": user, "form": raw, "how": how, "cost": cost})
        return raw, cost
    llm.chat_json = door
    os.makedirs(out, exist_ok=True)
    store = Store(os.path.join(os.environ["MVP_HOME"], "claims.sqlite"))
    ch = make_channel("console", store, None)
    ch.printer = None
    bot = Bot(ch, store=store)
    bot.load_people()
    bot.max_per_minute = None
    person = dict(store.q("SELECT * FROM people")[0])
    h = person["handle"]
    box["mode"] = "fake"
    if not store.get_state("claims_setup:" + h):   # the setup once per store (the page's own steps)
        for m in ("I agree", "skip", "skip", "skip"):
            bot.on_message(h, m)
        store.set_state("claims_setup:" + h, {"done": True})
    if qfile == "made-up":
        qs = MADE_UP_QUESTIONS
    else:
        with open(qfile, encoding="utf-8") as f:
            qs = [json.loads(line) for line in f if line.strip()]
    for q in qs:
        box["mode"] = "live" if q.get("live") else "fake"
        for k, text in enumerate(q["msgs"]):
            if k == 0:
                store.set_state("history:" + h, {})   # a fresh conversation: no follow-up of the one before
            box["seen"], box["other"] = [], []
            n0 = len(ch.outbox)
            t0 = time.time()
            bot.on_message(h, text)
            sent = "\n".join(t for _, _, t in ch.outbox[n0:])
            seen = box["seen"][-1] if box["seen"] else None
            sheet = None
            if seen:
                try:
                    sheet = json.loads(seen["user"].split("<sheet>\n", 1)[1].rsplit("\n</sheet>", 1)[0])
                except (IndexError, ValueError):
                    sheet = None
            aid = q["id"] + (f".{k}" if len(q["msgs"]) > 1 else "")
            spec = (q.get("windows") or [None] * len(q["msgs"]))[k] if q.get("windows") else \
                (q.get("window") if k == 0 else None)
            rec = {"id": aid, "text": text, "follow": k > 0, "parent_text": q["msgs"][0] if k > 0 else "",
                   "sent": sent, "sheet": sheet,
                   "form": seen["form"] if seen else None,
                   "how": seen["how"] if seen else ("not read by code" if box["other"] else "code"),
                   "cost": seen["cost"] if seen else 0.0, "seconds": round(time.time() - t0, 2),
                   "library": person["library"], "timezone": person.get("timezone") or "UTC",
                   "today": (today or date.today()).isoformat()}
            if spec:
                rec["window"] = spec
            elif k > 0 and q.get("window"):
                rec["window"] = q["window"]
            with open(os.path.join(out, f"a_{aid}.json"), "w", encoding="utf-8") as f:
                json.dump(rec, f, indent=1, ensure_ascii=False)
            print(aid, rec["how"], rec["seconds"], "s", file=sys.stderr)
    print(f"spent {box['spent']:.4f}", file=sys.stderr)
    return box["spent"]


# ============================================================================ the made-up questions (in git)
# Every kind, window and filter of DESIGN 19 in generic words; the real ones (the founder's and those generated from
# his record) stay in scratch. `capture made-up` sends these.
MADE_UP_QUESTIONS = [
    {"id": "m01", "msgs": ["what have i been watching the most lately", "without shorts"], "window": {"kind": "lately"}},
    {"id": "m02", "msgs": ["which channels did i watch the most in 2025"], "window": {"kind": "year", "year": 2025}},
    {"id": "m03", "msgs": ["how many cooking videos did i watch this year"], "window": {"kind": "this_year"}},
    {"id": "m04", "msgs": ["when did i first start watching cooking videos"], "window": {"kind": "all"}},
    {"id": "m05", "msgs": ["did i watch more gaming or more cooking videos this year"], "window": {"kind": "this_year"}},
    {"id": "m06", "msgs": ["what did i watch on october 30"], "window": {"kind": "day", "month": 10, "day": 30}},
    {"id": "m07", "msgs": ["how has what i watch changed since 2024"], "window": {"kind": "since", "year": 2024}},
    {"id": "m08", "msgs": ["what was i into in the summer of 2025"],
     "window": {"kind": "season", "season": "summer", "year": 2025}},
    {"id": "m09", "msgs": ["most watched channels in gaming", "without shorts"], "window": {"kind": "all"}},
    {"id": "m10", "msgs": ["what have i been into the last 3 months"], "window": {"kind": "last_days", "days": 90}},
    {"id": "m11", "msgs": ["how did my watching change from 2024 to 2025"],
     "window": {"kind": "years", "from": 2024, "to": 2025}},
    {"id": "m12", "msgs": ["what was i watching back in 2025"], "window": {"kind": "year", "year": 2025}},
]


# ============================================================================ the planted set (pass 6, A5)
PLANTED = os.path.join(HERE, "eval", "claims_planted.json")


def build_planted(spec, folder):
    """Write the made-up library of a planted file (its `library`: themes and groups of videos) under `folder`, in the
    shapes the auditor reads. A group: {ch, theme, len, pub, p, cap, n, days: "A..B", hour, kinds}; its n videos are
    opened one a day over the days (cycling), at `hour` UTC. Returns (library folder, derived folder)."""
    lib = os.path.join(folder, "lib")
    der = os.path.join(folder, "derived")
    tdir = os.path.join(der, "themes-v2", "planted0001")
    for d in (os.path.join(lib, "corpus"), os.path.join(der, "lengths-v1"), tdir):
        os.makedirs(d, exist_ok=True)
    L = spec["library"]
    names = [t["name"] for t in L["themes"]]
    fields = [{"id": k, "name": t["name"], "category": t["category"]} for k, t in enumerate(L["themes"])]
    themes = [{"id": k, "name": t["name"], "field": k, "category": t["category"]} for k, t in enumerate(L["themes"])]
    items, inter, lens, trows = [], [], [], []
    for g in L["groups"]:
        a, b = (date.fromisoformat(x) for x in g["days"].split(".."))
        span = (b - a).days + 1
        for k in range(int(g.get("n", 1))):
            iid = f"itm_{len(items):05d}"
            p = g.get("p", "youtube")
            pd = {"owner_name": g["ch"], "owner_handle": g["ch"].lower().replace(" ", ""), "owner_relation": "none"}
            if p == "youtube":
                pd["video_id"] = f"vid{len(items):05d}"
                if g.get("len") is not None:
                    lens.append({"video_id": pd["video_id"], "length_s": g["len"], "published": g.get("pub"),
                                 "refresh_by": "2999-01-01T00:00:00+00:00", "version": "lengths-v1"})
            cap = g.get("cap") or f"made up video {len(items)}"
            items.append({"id": iid, "platform": p, "source_url": f"https://example.invalid/{len(items)}",
                          "caption": cap if "{k}" not in cap else cap.replace("{k}", str(k)), "platform_data": pd})
            d = a + timedelta(days=k % span)
            at = datetime(d.year, d.month, d.day, int(g.get("hour", 15)), int(g.get("minute", 0)),
                          tzinfo=timezone.utc).isoformat()
            for kind in g.get("kinds") or ["watch"]:
                inter.append({"item_id": iid, "kind": kind, "at": at})
            if g.get("theme"):
                tid = names.index(g["theme"])
                trows.append({"item_id": iid, "field": tid, "theme": tid, "name": g["theme"], "version": "themes-v2",
                              "embedding_model": "made-up"})
    for name, data in (("corpus/items.jsonl", items), ("corpus/interactions.jsonl", inter)):
        with open(os.path.join(lib, name), "w", encoding="utf-8") as f:
            f.writelines(json.dumps(x) + "\n" for x in data)
    with open(os.path.join(der, "lengths-v1", "lengths.jsonl"), "w", encoding="utf-8") as f:
        f.writelines(json.dumps(x) + "\n" for x in lens)
    with open(os.path.join(tdir, "themes.jsonl"), "w", encoding="utf-8") as f:
        f.writelines(json.dumps(x) + "\n" for x in trows)
    with open(os.path.join(tdir, "build.json"), "w", encoding="utf-8") as f:
        json.dump({"version": "themes-v2", "fields": fields, "themes": themes}, f)
    return lib, der


def run_planted(path=PLANTED, folder=None):
    """Every case of the planted file through the audit: [(case, mismatches)]. A defect case must have a mismatch of
    its `expect` kind; a clean case none at all."""
    import tempfile
    spec = json.load(open(path, encoding="utf-8"))
    folder = folder or tempfile.mkdtemp(prefix="planted_")
    lib_path, der = build_planted(spec, folder)
    L = Library(lib_path, der, spec["library"].get("timezone", "America/New_York"),
                now=datetime(2026, 11, 22, tzinfo=timezone.utc))
    today = date.fromisoformat(spec["library"].get("today", "2026-11-22"))
    out = []
    for c in spec["cases"]:
        L.__dict__.pop("_tt", None)
        rows = audit_answer(L, {"id": c["id"], "text": c["text"], "window": c.get("window"),
                                "sheet": c.get("sheet"), "sent": c["sent"], "form": None}, today)
        out.append((c, [r for r in rows if not r["ok"]]))
    return out


def planted_report(results):
    caught = [c for c, bad in results if c["defect"] and any(c["expect"] in r["kind"] for r in bad)]
    kept = [c for c, bad in results if not c["defect"] and not bad]
    n_def = sum(1 for c, _ in results if c["defect"])
    return {"defects": n_def, "caught": len(caught), "clean": len(results) - n_def, "kept": len(kept),
            "missed": [c["id"] for c, bad in results if c["defect"] and c not in caught],
            "false_flags": [(c["id"], [r["kind"] for r in bad]) for c, bad in results if not c["defect"] and bad]}


# ============================================================================ questions from the record
def generate(lib, today, n_min=130):
    """Questions of every kind, window, topic and filter, from the areas and years the record holds."""
    years = sorted({date.fromordinal(o).year for ds in lib.open_days.values() for o in ds[:1]} |
                   {date.fromordinal(lib.newest).year})
    counts = Counter(date.fromordinal(o).year for ds in lib.open_days.values() for o in ds)
    years = [y for y in years if counts.get(y, 0) >= 500]
    areas = [a for a, _ in Counter(lib.area_of.values()).most_common(8)]
    out = []

    def add(msgs, window=None):
        out.append({"id": f"g{len(out) + 1:03d}", "msgs": msgs, **({"window": window} if window else {})})
    for y in years:
        add([f"what was i into in {y}"], {"kind": "year", "year": y})
        add([f"which channels did i watch the most in {y}", "without shorts"], {"kind": "year", "year": y})
        add([f"what did i watch the most in {y}"], {"kind": "year", "year": y})
    for y in years[-4:]:
        for s in ("summer", "winter", "spring", "fall"):
            add([f"what was i into in the {s} of {y}"], {"kind": "season", "season": s, "year": y})
    for a in areas:
        add([f"most watched channels in {a}", "without shorts"], {"kind": "all"})
        add([f"how many {a} videos did i watch this year"], {"kind": "this_year"})
        add([f"when did i first start watching {a} videos"], {"kind": "all"})
        add([f"when did i last watch {a} videos"], {"kind": "all"})
        for y in years[-3:]:
            add([f"which {a} channels did i watch the most in {y}"], {"kind": "year", "year": y})
            add([f"how many {a} videos did i watch in {y}"], {"kind": "year", "year": y})
    for k in range(len(areas) - 1):
        for y in years[-2:]:
            add([f"did i watch more {areas[k]} or more {areas[k + 1]} videos in {y}"], {"kind": "year", "year": y})
    for y1, y2 in zip(years[-5:], years[-3:]):
        add([f"how did my watching change from {y1} to {y2}"], {"kind": "years", "from": y1, "to": y2})
        add([f"what did i watch in {y1} vs {y2}"], {"kind": "years", "from": y1, "to": y2})
    for y in years[-6:-1]:
        add([f"how has what i watch changed since {y}"], {"kind": "since", "year": y})
    for n, words in ((3, "3 months"), (2, "2 months"), (6, "6 months")):
        add([f"what have i been into the last {words}"], {"kind": "last_days", "days": 30 * n})
    add(["what have i been watching the most lately", "without shorts"], {"kind": "lately"})
    add(["what am i into these days"], {"kind": "lately"})
    end = date.fromordinal(lib.newest)
    for back in (0, 3, 9, 20, 41):
        d = end - timedelta(days=back)
        add([f"what did i watch on {MONTHS[d.month - 1]} {d.day}"], {"kind": "day", "month": d.month, "day": d.day})
    return out


# ============================================================================ main
def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("capture")
    c.add_argument("questions", help='a .jsonl of {"id", "msgs": [...], "window": {...}, "live": bool}, or made-up')
    c.add_argument("--out", required=True)
    c.add_argument("--live", type=int, default=0, help="at most this many live writer calls (questions marked live)")
    a = sub.add_parser("audit")
    a.add_argument("folder")
    a.add_argument("--json", default=None)
    a.add_argument("--library", default=None)
    a.add_argument("--derived", default=None)
    a.add_argument("--tz", default=None)
    g = sub.add_parser("gen")
    g.add_argument("--library", required=True)
    g.add_argument("--tz", default="UTC")
    g.add_argument("--out", required=True)
    g.add_argument("--derived", default=None)
    pl = sub.add_parser("planted")
    pl.add_argument("file", nargs="?", default=PLANTED)
    x = ap.parse_args(argv)
    if x.cmd == "planted":
        rep = planted_report(run_planted(x.file))
        print(json.dumps(rep, indent=1))
        return 0 if not rep["missed"] and not rep["false_flags"] else 1
    if x.cmd == "capture":
        capture(x.questions, x.out, x.live)
    elif x.cmd == "audit":
        audit_folder(x.folder, x.library, x.derived, x.tz, json_out=x.json)
    elif x.cmd == "gen":
        lib = Library(x.library, x.derived, x.tz)
        qs = generate(lib, date.today())
        with open(x.out, "w", encoding="utf-8") as f:
            for q in qs:
                f.write(json.dumps(q) + "\n")
        print(len(qs), "questions", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
