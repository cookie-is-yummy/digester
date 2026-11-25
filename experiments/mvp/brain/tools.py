"""PROTOTYPE ONLY - the processor's tools for the brain (design/brain_v1/SPEC.md section 2), step 1.

One registry: ToolDef(name, description, params, run, kind, cost, doors, version). The JSON Schema of every tool is
generated from its Pydantic model (keys sorted, tools sorted by name, every field required, no bounds: the bounds are
checked here), so a cached prefix is byte-identical. The read tools only read: they wrap facts.build (the fact sheet
of round 12) with a HistoryQuery built by code from the tool's arguments, so every number they return is one the
sheet's checks already know how to recount. `search` and `learned` wrap paid or embedding paths through callables the
caller injects (Turn.search, Turn.learned): the tests use fakes and nothing is spent. Step 2 builds the propose side
and give_answer; their argument models are declared here only.

Nothing here is wired into the message path.
"""
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .. import facts as F
from .. import history as Hm
from . import names as N
from . import results as R
from . import windows as W

TOOLS_VERSION = "brain_tools_v1"
SEARCH_PER_TURN, LEARNED_PER_TURN = 3, 1
FIT_CLEAR, FIT_CLOSE = 0.6, 0.4
HOW = {"opened": "watched", "liked": "liked", "saved": "saved", "any": "any"}
BASE = {"opened": "of what you opened", "liked": "of what you liked", "saved": "of what you saved",
        "any": "of everything you opened, liked or saved"}
LIST_OF = {"area": "areas", "theme": "themes", "channel": "channels"}
DEFAULT_CAP = {"area": F.AREAS_MAX, "theme": F.THEMES_MAX, "channel": F.CHANNELS_MAX}
WATCH_TIME_LINE = "Your export records which videos you opened, not for how long, so I count videos."
FRIENDS_LINE = "Posts from friends are not counted."


# ================================================================ argument models (strict: unknown keys refused)
class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


WindowArg = W.WindowArg


class ScopeArg(_Args):
    how: Literal["opened", "liked", "saved", "any"] = "opened"
    platforms: list[Literal["youtube", "instagram"]] = Field(default_factory=list)
    only: list[str] = Field(default_factory=list, max_length=5)
    exclude: list[str] = Field(default_factory=list, max_length=5)
    length: Literal["any", "long", "short"] = "any"
    weekday: Optional[int] = Field(default=None, ge=0, le=6)


class FindArgs(_Args):
    names: list[str] = Field(min_length=1, max_length=6)
    kinds: list[Literal["area", "theme", "channel", "collection", "words"]] = Field(default_factory=list)


class BreakdownArgs(_Args):
    by: Literal["area", "theme", "channel", "none"]
    window: WindowArg
    scope: ScopeArg = Field(default_factory=ScopeArg)
    compare: Literal["previous", "none"] = "previous"
    order: Literal["most", "least"] = "most"
    top: int = Field(default=8, ge=1, le=25)


class TimelineArgs(_Args):
    unit: Literal["month", "year"]
    window: WindowArg
    scope: ScopeArg = Field(default_factory=ScopeArg)


class ChangesArgs(_Args):
    level: Literal["area", "theme", "channel"]
    window: WindowArg
    against: Literal["previous", "same_last_year"] = "previous"
    scope: ScopeArg = Field(default_factory=ScopeArg)


class CompareArgs(_Args):
    a: WindowArg
    b: WindowArg
    by: Literal["area", "theme", "channel", "none"] = "none"
    scope: ScopeArg = Field(default_factory=ScopeArg)


class FirstLastArgs(_Args):
    subject: str = Field(min_length=1, max_length=80)
    which: Literal["first", "last"]
    scope: ScopeArg = Field(default_factory=ScopeArg)


class ItemsArgs(_Args):
    window: WindowArg
    scope: ScopeArg = Field(default_factory=ScopeArg)
    order: Literal["most_opened", "newest", "oldest"] = "most_opened"
    limit: int = Field(default=5, ge=1, le=10)
    offset: int = Field(default=0, ge=0, le=200)


class SearchArgs(_Args):
    query: str = Field(min_length=2, max_length=200)
    how: Literal["saved", "opened", "any"] = "saved"
    window: Optional[WindowArg] = None
    limit: int = Field(default=5, ge=1, le=8)


class LearnedArgs(_Args):
    topic: str = Field(min_length=2, max_length=80)
    scope: ScopeArg = Field(default_factory=ScopeArg)


# step 2 (declared only: nothing here runs them)
class ProposeRuleArgs(_Args):
    quote: str = Field(min_length=2, max_length=200)
    when: str = Field(min_length=2, max_length=600)    # a JSON string of today's schema.When, parsed by code
    output: Literal["chat", "email_self"] = "chat"
    plan: Literal["this_turn", "waiting_card"] = "this_turn"


class ProposeSendArgs(_Args):
    quote: str = Field(min_length=2, max_length=200)
    what: Literal["this_answer", "last_answer"] = "this_answer"


# ================================================================ the turn
@dataclass
class Turn:
    """What every tool call of one turn shares: who, when, their message and the screen (for the window digits), the
    sensitive topic their message unlocks (set by code here, never by an argument), the results so far, the injected
    paid backends and the per-turn counts."""
    bot: Any
    person: dict
    now: Any
    message: str = ""
    screen: str = ""
    scheduled: bool = False
    search: Optional[Callable] = None     # (turn, query, how, start, end, limit) -> {"items": [...], "cost_usd"}
    learned: Optional[Callable] = None    # (turn, topic, query) -> {"points": [...], "cost_usd"}
    last_window: Any = None
    results: dict = field(default_factory=dict)
    windows: dict = field(default_factory=dict)
    counts: dict = field(default_factory=dict)
    unlock: Optional[str] = field(default=None, init=False)
    _lib: Any = field(default=None, init=False, repr=False)

    def __post_init__(self):
        from .. import outside as O
        self.unlock = O.sensitive_topic([self.message]) if self.message else None

    @property
    def tz(self):
        return self.person.get("timezone") or "UTC"

    @property
    def today(self):
        return self.now.astimezone(ZoneInfo(self.tz)).date()

    @property
    def lib(self):
        if self._lib is None:
            self._lib = N.Lib(self.bot, self.person, self.unlock)
        return self._lib

    def next_rid(self):
        self.counts["rid"] = self.counts.get("rid", 0) + 1
        return f"r{self.counts['rid']}"


class ToolError(ValueError):
    pass


# ================================================================ shared steps
def _window(turn, arg):
    try:
        return W.resolve(arg, turn.today, turn.message, turn.screen, turn.scheduled, turn.windows, turn.last_window)
    except W.WindowError as e:
        raise ToolError(str(e)) from None


def _refs(turn, names_, resolved):
    """Every name as a ref, or the first that is not one: ("ambiguous"|"no_match", its resolution)."""
    out = []
    for nm in names_:
        r = N.resolve_one(turn.lib, nm)
        if r["status"] != "ok":
            return None, r
        m = r["matches"][0]
        resolved[nm] = f"{m['ref']} ({m['how']})"
        out.append(m["ref"])
    return out, None


def _query(turn, scope, kind, window, resolved, subject_ref=None, **extra):
    """The HistoryQuery of a tool call: the scope's refs resolved by code (or the name that did not resolve)."""
    only, bad = _refs(turn, scope.only, resolved)
    if subject_ref:
        only = [subject_ref]
    if bad:
        return None, bad
    excl, bad = _refs(turn, scope.exclude, resolved)
    if bad:
        return None, bad
    plats = sorted(set(scope.platforms))
    q = Hm.HistoryQuery(kind=kind, how=HOW[scope.how], platform=plats[0] if len(plats) == 1 else None,
                        window=window, only_refs=only, exclude_refs=excl, length=scope.length,
                        weekday=scope.weekday, **extra)
    return q, None


def _unresolved(turn, tool, r):
    """A counting tool given a name that is ambiguous or matches nothing: no rows, only the options."""
    rid = turn.next_rid()
    out = {"rid": rid, "tool": tool, "error": r["status"], "name": r["name"], "options": r["options"],
           "meta": {"complete": False, "notes": ["No numbers for a name that did not resolve: ask them which one, "
                                                 "or use one of the options."]}}
    out.update(_no_match_cell(turn, r))
    return out


NO_MATCH_NOTE = ("A name with no match carries `searched` (the words looked for) and `items_with_words`: how many of "
                 "their items (opened, liked or saved, ever) hold those words in their own text.")


def _no_match_cell(turn, r):
    """Toolfix 6 (a no-match had no cell, so "nothing called knitting in your history" could not be checked): the
    words searched and how many of their items hold them (names.words_count); nothing for a private name."""
    if r.get("status") != "no_match":
        return {}
    got = N.words_count(turn.lib, r.get("name"))
    if got is None:
        return {}
    return {"searched": R.neutral(got[0]), "items_with_words": got[1]}


def _filters_said(turn, scope, resolved):
    parts = []
    for nm in scope.only:
        ref = resolved.get(nm, "")
        parts.append(f"only {_label_of(turn, ref)}")
    for nm in scope.exclude:
        ref = resolved.get(nm, "")
        parts.append(f"without {_label_of(turn, ref)}")
    if scope.length == "long":
        parts.append("only videos known to be long")
    elif scope.length == "short":
        parts.append("only Shorts and reels")
    if scope.weekday is not None:
        parts.append("on " + Hm.DAYS[scope.weekday].capitalize() + "s")
    if len(set(scope.platforms)) == 1:
        parts.append(Hm.PNAME[scope.platforms[0]] + " only")
    return "; ".join(parts) or None


def _label_of(turn, resolved_line):
    ref, _, how = resolved_line.partition(" (")
    form = ref.split(":", 1)[0]
    label = N._label(turn.lib, ref) if ref else "?"
    if form == "words":
        return f"videos with '{label}' in the title"
    return f"{label} ({form})"


def _notes(turn, raw):
    """Code's own lines about limits (8.7); the renderer, not the model, decides which are said."""
    notes = []
    win = (raw or {}).get("window") or {}
    for p, d in sorted((win.get("ends") or {}).items()):
        notes.append(f"Your {Hm.PNAME.get(p, p)} export ends on {Hm.day_words(_date(d))}.")
    cs = (raw or {}).get("cannot_see") or {}
    if cs.get("reason") == "after" and cs.get("export_ends"):
        notes.append(f"Your export ends on {Hm.day_words(_date(cs['export_ends']))}, so I can't see after that. "
                     "A new export shows the rest.")
    if cs.get("reason") == "before" and cs.get("history_starts"):
        notes.append(f"Your history starts on {Hm.day_words(_date(cs['history_starts']))}.")
    if Hm.HOURS.search(Hm.normal(turn.message or "")):
        notes.append(WATCH_TIME_LINE)
    if Hm.FRIENDS_ASK.search(Hm.normal(turn.message or "")):
        notes.append(FRIENDS_LINE)
    return notes


def _date(s):
    from datetime import date
    return date.fromisoformat(str(s)[:10])


def _meta(turn, raw, scope, resolved, order="most", by=None, extra_notes=()):
    hidden = (raw or {}).get("hidden") or {}
    ranked = (raw or {}).get("ranked") or {}
    lst = LIST_OF.get(by)
    # merge seam: the verifier reads one flag for every list of the sheet, and a sentence may rank a list that is not
    # the one asked for (a compare by none still holds themes and channels): the flag is said when a hidden entity
    # would rank above the first row of ANY list shown, never under-said
    above = hidden.get("above") or {}
    sens, rank_above = int(hidden.get("sensitive", 0)), any(bool(v) for v in above.values())
    notes_extra = []
    if any(str(resolved.get(n, "")).startswith("words:") for n in list(scope.only) + list(scope.exclude)):
        # step 1 fix (the tools audit, L14: under only "words:texting" the private items left out were 17, under
        # "words:zzqx" 0, so private titles could be probed word by word): under a title-word scope the count of
        # private items left out is not said; a constant stands for it, so every number asks for the private line
        sens, rank_above = 1, True
        notes_extra.append("Under a title-word scope, how many private items were left out is not said.")
    return {"window_said": ((raw or {}).get("window") or {}).get("words"),
            "base": BASE[scope.how],
            "filters_said": _filters_said(turn, scope, resolved),
            "resolved": dict(resolved), "order": order, "complete": True,
            "rows_total": ranked.get(lst) if lst else None,
            # step 1 fix (the verifier audit, F67: "videos from 7[r1.channels.count] channels" of a list cut to 8 of
            # 9): how many rows each ranking holds, shown or not, so a count marker of a cut list can be refused
            "rows_of": {k: int(v) for k, v in sorted(ranked.items()) if isinstance(v, int)},
            "hidden": {"sensitive": sens, "friends": int(hidden.get("friends", 0)), "rank_hidden_above": rank_above},
            "notes": _notes(turn, raw) + list(extra_notes) + notes_extra}


def _sheet(turn, q):
    """facts.build with the sensitive topics left out (unlocked per topic by their message only)."""
    raw = F.build(turn.bot, turn.person, q, turn.now, text=turn.message or None, hide_sensitive=True,
                  unlock=turn.unlock)
    if raw is None:
        raise ToolError("nothing in their record for this: no platform holds that kind of event")
    return raw


PREVIOUS_KEYS = ("previous_share", "previous_items", "change_vs_previous", "change_pts")


def _no_previous(sheet):
    sheet.pop("previous", None)
    for k in ("themes", "areas", "channels"):
        for r in sheet.get(k) or []:
            if isinstance(r, dict):
                for x in PREVIOUS_KEYS:
                    r.pop(x, None)
    return sheet


REELS_NOTE = ("`shorts` counts YouTube Shorts; `reels` counts Instagram reels and videos. The length filter 'short' "
              "takes both.")


def _reels_cells(raw, sheet, meta):
    """Toolfix 4 (totals.shorts left out Instagram reels while the length filter counted them as short): facts'
    count of the reels beside the Shorts, in `totals` and `previous`."""
    for k in ("totals", "previous"):
        if isinstance(sheet.get(k), dict) and isinstance((raw.get(k) or {}).get("reels"), int):
            sheet[k]["reels"] = raw[k]["reels"]
    if any(isinstance(sheet.get(k), dict) and sheet[k].get("reels") for k in ("totals", "previous")):
        meta.setdefault("notes", []).append(REELS_NOTE)


def _channel_names(turn, sheet):
    """Toolfix 7 (an Instagram channel was named only by its handle, which an answer never prints): every channel row
    keeps the handle as its own field (`handle`) and is named by the account's display name when the export has one
    (names.displays); a top-level channel row says its platform. Item rows likewise (`channel`, `handle`)."""
    lib = turn.lib
    disp = N.displays(lib)
    plat = {}
    for it in lib.view.items.values():
        if it.creator:
            plat.setdefault(it.creator, it.platform)

    def fix(row, name_key):
        nm = row.get(name_key)
        if not isinstance(nm, str) or plat.get(nm) is None:
            return
        if nm.startswith("@") and plat[nm] == "instagram":
            row["handle"] = nm[1:]
            if disp.get(nm):
                row[name_key] = R.neutral(disp[nm], R.NAME_MAX)

    def walk(o, key=None, depth=0):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, k, depth + 1)
        elif isinstance(o, list):
            for row in o:
                if isinstance(row, dict):
                    if key == "channels":
                        nm = row.get("name")
                        if depth == 1 and isinstance(nm, str) and plat.get(nm):
                            row["platform"] = plat[nm]
                        fix(row, "name")
                    elif key == "items" and "item_id" in row:
                        fix(row, "channel")
                walk(row, None, depth + 1)
    walk(sheet)


def _finish(turn, tool, rid, raw, sheet, meta, t0, window=None, cost=0.0, keep=None, how="opened"):
    if window is not None:
        turn.windows[rid] = window
    if raw is not None and isinstance(sheet, dict) and sheet.get("kind"):
        for n in R.honest(sheet, how):
            if n not in meta.setdefault("notes", []):
                meta["notes"].append(n)
        _reels_cells(raw, sheet, meta)
    if isinstance(sheet, dict):
        _channel_names(turn, sheet)
    whole = (meta.get("rows_of") or {}).get(keep) if keep else None
    env = R.envelope(rid, tool, meta, sheet, cost, (time.monotonic() - t0) * 1000, keep=keep,
                     newest=keep == "periods")
    shown_n = len((sheet or {}).get(keep) or []) if keep else 0
    if keep == "periods" and isinstance(whole, int) and shown_n < whole:
        # toolfix 9 (a month timeline of all history was cut to its first 24 months while complete said true): the
        # list asked for lost rows (its oldest ones), so the result is not complete, and a note says what it holds
        env["meta"]["complete"] = False
        ps = sheet[keep]
        env["meta"]["notes"].append(f"Only the latest {shown_n} of {whole} periods fit in this result "
                                    f"({ps[0].get('label')} to {ps[-1].get('label')}); ask for a shorter window "
                                    "for the earlier ones.")
    turn.results[rid] = env
    return env


# ================================================================ the read tools
def run_find(turn, a: FindArgs):
    t0 = time.monotonic()
    rows = []
    for nm in a.names:
        r = N.resolve_one(turn.lib, nm, a.kinds)
        rows.append(dict({"name": R.neutral(r["name"]), "status": r["status"], "matches": R.clean(r["matches"]),
                          "options": R.clean(r["options"]), "also": R.clean(r["also"])}, **_no_match_cell(turn, r)))
    rid = turn.next_rid()
    # each name's row gets its path; a match's or an option's `ref` is the library ref to pass to the other tools
    sheet = {"names": [dict(row, row=f"{rid}.names[{n}]") for n, row in enumerate(rows)]}
    meta = {"complete": True, "notes": ["items_all_time counts what you opened, liked or saved, ever; options carry "
                                        "no numbers."]}
    if any("items_with_words" in r for r in rows):
        meta["notes"].append(NO_MATCH_NOTE)
    return _finish(turn, "find", rid, None, sheet, meta, t0, keep="names")


def run_breakdown(turn, a: BreakdownArgs):
    t0 = time.monotonic()
    w = _window(turn, a.window)
    resolved = {}
    kind = {"area": "top", "theme": "top", "channel": "top_channels", "none": "count"}[a.by]
    # facts.py's own caps (5 areas, 8 themes, 10 channels) are insight.shown's too: a `top` within the cap is today's
    # sheet trimmed; a larger one asks facts for more rows (of every ranking: the others are trimmed by shown)
    cap = DEFAULT_CAP.get(a.by)
    q, bad = _query(turn, a.scope, kind, w, resolved, order=a.order,
                    top=a.top if cap is not None and a.top > cap else None)
    if bad:
        return _unresolved(turn, "breakdown", bad)
    raw = _sheet(turn, q)
    rid = turn.next_rid()
    lst = LIST_OF.get(a.by)
    sheet = R.present(raw, rid, limits={lst: a.top} if lst else None)
    if a.compare == "none":
        _no_previous(sheet)
    meta = _meta(turn, raw, a.scope, resolved, a.order, a.by)
    return _finish(turn, "breakdown", rid, raw, sheet, meta, t0, w, keep=lst, how=a.scope.how)


def run_timeline(turn, a: TimelineArgs):
    t0 = time.monotonic()
    w = _window(turn, a.window)
    resolved = {}
    q, bad = _query(turn, a.scope, "timeline", w, resolved, by=a.unit)
    if bad:
        return _unresolved(turn, "timeline", bad)
    raw = _sheet(turn, q)
    for p in raw.get("periods") or []:   # a period too thin to say what was watched in it (facts.SPARSE_MIN)
        if isinstance(p, dict) and isinstance(p.get("items"), int):
            p["sparse"] = p["items"] < F.SPARSE_MIN
    rid = turn.next_rid()
    # toolfix 9: every period (insight.shown keeps its first 24); `rows_of.periods` says how many there are
    n_periods = len(raw.get("periods") or [])
    sheet = R.present(raw, rid, limits={"periods": n_periods} if n_periods else None)
    extra = [f"A period with fewer than {F.SPARSE_MIN} items is marked sparse."]
    meta = _meta(turn, raw, a.scope, resolved, extra_notes=extra)
    meta["rows_of"]["periods"] = n_periods
    return _finish(turn, "timeline", rid, raw, sheet, meta, t0, w, keep="periods", how=a.scope.how)


def _year_back(turn, w):
    """The same days a year earlier, of the window as the record holds it: a window that runs past where the export
    ends is cut there first ("this year" up to 30 October is set against 1 January to 30 October of last year, never
    the whole of last year); a range, so its words say its dates. 29 February becomes the 28th."""
    def back(d):
        try:
            return d.replace(year=d.year - 1)
        except ValueError:
            return d.replace(year=d.year - 1, day=28)
    if not w.start or not w.end:
        raise ToolError("same_last_year needs a window with dates: lately and all have no year before")
    newest = max(turn.lib.rec.ends.values()) if turn.lib.rec.ends else None
    end = min(w.end, newest) if newest else w.end
    if end < w.start:
        raise ToolError("that window is after where the export ends: there is nothing to set against last year")
    if end == w.end and w.kind in ("year", "month"):
        return Hm.Window(kind=w.kind, start=back(w.start), end=back(w.end))
    return Hm.Window(kind="range", start=back(w.start), end=back(end))


def run_changes(turn, a: ChangesArgs):
    """against previous: a channel level is the window's channels with the window before (new and stopped channels);
    an area or theme level is how the window changed from its first period to its last (rising, fading, eras). Against
    the same window last year: both windows in one result, with what is new and what stopped."""
    t0 = time.monotonic()
    w = _window(turn, a.window)
    resolved = {}
    notes = [f"New: at least {F.NEW_MIN_ITEMS} items and {int(F.NEW_MIN_SHARE * 100)}% of the window, with at most "
             f"{F.NEW_PREV_MAX} before; a channel new in the window: first opened in it, {F.NEW_CHANNEL_MIN} items or "
             f"more on {F.NEW_CHANNEL_DAYS} days or more; stopped: the reverse."]
    if a.against == "same_last_year":
        if w.kind == "lately":
            raise ToolError("same_last_year needs a window with dates: use words like 'this year' or 'in October'")
        q, bad = _query(turn, a.scope, "compare", w, resolved, window2=_year_back(turn, w))
    elif a.level == "channel":
        q, bad = _query(turn, a.scope, "top_channels", w, resolved)
    else:
        q, bad = _query(turn, a.scope, "changed", w, resolved)
        notes.append("Rising and fading: a move of 2 points or more between the first and the last full period.")
    if bad:
        return _unresolved(turn, "changes", bad)
    raw = _sheet(turn, q)
    rid = turn.next_rid()
    keep = "periods" if raw.get("kind") == "changed" else LIST_OF[a.level]
    n_periods = len(raw.get("periods") or []) if keep == "periods" else 0
    sheet = R.present(raw, rid, limits={"periods": n_periods} if n_periods else None)   # toolfix 9, as timeline
    meta = _meta(turn, raw, a.scope, resolved, by=a.level, extra_notes=notes)
    if keep == "periods":
        meta["rows_of"]["periods"] = n_periods
    return _finish(turn, "changes", rid, raw, sheet, meta, t0, w, keep=keep, how=a.scope.how)


def run_compare(turn, a: CompareArgs):
    t0 = time.monotonic()
    wa, wb = _window(turn, a.a), _window(turn, a.b)
    for w_ in (wa, wb):
        # step 1 fix (the tools audit, P03 and P06: November against October gave October against October, and
        # October against November a 0 for November): a window wholly after where the export ends has no count
        _not_after_end(turn, w_, "there is nothing to compare it with")
    resolved = {}
    q, bad = _query(turn, a.scope, "compare", wa, resolved, window2=wb)
    if bad:
        return _unresolved(turn, "compare", bad)
    raw = _sheet(turn, q)
    rid = turn.next_rid()
    sheet = R.present(raw, rid)
    meta = _meta(turn, raw, a.scope, resolved, by=None if a.by == "none" else a.by,
                 extra_notes=["Both windows are in this one result: `totals` is the first, `previous` the second."])
    _compare_days(turn, raw, wb, a.scope, meta)
    return _finish(turn, "compare", rid, raw, sheet, meta, t0, wa, keep=LIST_OF.get(a.by), how=a.scope.how)


def _compare_days(turn, raw, wb, scope, meta):
    """Toolfix 5 (this autumn, cut where the export ends on 30 October, was set against the whole of last autumn with
    no word): both windows as counted, with their days (`meta.windows`, `meta.same_days`), and a note when the days
    differ. The second window is cut where the export ends, as facts counts it."""
    from datetime import date
    rec = turn.lib.rec
    plats = sorted(set(scope.platforms)) or sorted(rec.ends)
    win = raw.get("window") or {}
    if not win.get("start") or not win.get("end"):
        return
    a0, a1 = date.fromisoformat(win["start"]), date.fromisoformat(win["end"])
    b0, b1 = Hm.resolve(wb, rec, plats, turn.today)
    ends = [rec.ends[p] for p in plats if p in rec.ends]
    if b1 is not None and ends:
        b1 = min(b1, max(ends))
    if b0 is None:   # a window with no start ("all") starts where the record does
        b0 = Hm._record_start(rec, plats, Hm.HistoryQuery(kind="count", how=HOW[scope.how]))
    if b0 is None or b1 is None:
        return
    da, db = (a1 - a0).days + 1, (b1 - b0).days + 1
    meta["windows"] = {"a": {"start": a0.isoformat(), "end": a1.isoformat(), "days": da},
                       "b": {"start": b0.isoformat(), "end": b1.isoformat(), "days": db}}
    meta["same_days"] = da == db
    if da != db:
        meta["notes"].append(f"The two windows are not the same length: the first has {da} days "
                             f"({Hm.day_words(a0)} to {Hm.day_words(a1)}), the second {db} days "
                             f"({Hm.day_words(b0)} to {Hm.day_words(b1)}). Say so beside any count set against the "
                             "other, or compare the same days.")


def run_first_last(turn, a: FirstLastArgs):
    t0 = time.monotonic()
    if a.scope.only:
        raise ToolError("put what it is about in `subject`, not in scope.only")
    r = N.resolve_one(turn.lib, a.subject)
    if r["status"] != "ok":
        return _unresolved(turn, "first_last", r)
    m = r["matches"][0]
    resolved = {a.subject: f"{m['ref']} ({m['how']})"}
    q, bad = _query(turn, a.scope, a.which, Hm.Window(), resolved, subject_ref=m["ref"])
    if bad:
        return _unresolved(turn, "first_last", bad)
    raw = _sheet(turn, q)
    rid = turn.next_rid()
    sheet = R.present(raw, rid)
    sheet["items"] = _item_rows(turn, raw, (raw.get("items") or [])[:3], q, rid)
    meta = _meta(turn, raw, a.scope, resolved)
    # merge seam: the subject line first, then the scope's own lines (an exclude, a length, a weekday, a platform),
    # so a filter applied to the query is never left unsaid
    meta["filters_said"] = "; ".join(x for x in (f"{a.subject}: {_label_of(turn, resolved[a.subject])}",
                                                 _filters_said(turn, a.scope, resolved)) if x)
    return _finish(turn, "first_last", rid, raw, sheet, meta, t0, keep="items", how=a.scope.how)


def _length_word(row, media=None):
    """short (a known Short, or an Instagram reel or video), long (known long), else unknown. Step 1 fix (the tools
    audit: Instagram photo posts were said "short"): only a reel or a video post is short; a photo post has no
    length."""
    s = row.get("is_short")
    if row.get("platform") == "instagram":
        return "short" if (media or "reel") in ("reel", "video") else "unknown"
    return "short" if s is True else "long" if s is False else "unknown"


def _item_rows(turn, raw, rows, q, rid, offset=0):
    """Item rows as the tools return them: never a link, the title neutralised and clipped."""
    from datetime import date
    win = raw.get("window") or {}
    a = date.fromisoformat(win["start"]) if win.get("start") else None
    b = date.fromisoformat(win["end"]) if win.get("end") else None
    out = []
    for n, r in enumerate(rows):
        iid = r.get("id")
        if not iid or not turn.lib.is_visible(iid):
            continue
        evs = turn.lib.rec.events.get(iid, [])
        opened = sum(1 for d, k in evs if k in ("watch", "view") and (a is None or d >= a) and (b is None or d <= b))
        when = r.get("at")
        if r.get("at_time") and when:
            when = f"{when} {r['at_time']}"
        out.append({"ref": f"{rid}.items[{len(out)}]", "item_id": iid, "title": R.neutral(r.get("title"), R.TITLE_MAX),
                    "channel": R.neutral(r.get("channel"), R.NAME_MAX), "platform": r.get("platform"),
                    "when": when, "times_opened": opened,
                    "length": _length_word(r, getattr(turn.lib.view.items.get(iid), "media", None))})
    return out


def run_items(turn, a: ItemsArgs):
    t0 = time.monotonic()
    w = _window(turn, a.window)
    resolved = {}
    day = w.kind == "day"
    kind = "on_day" if day else {"most_opened": "top_items", "newest": "list", "oldest": "first"}[a.order]
    extra = {} if day else {"n": a.limit, "offset": a.offset}
    q, bad = _query(turn, a.scope, kind, w, resolved, **extra)
    if bad:
        return _unresolved(turn, "items", bad)
    raw = _sheet(turn, q)
    rid = turn.next_rid()
    rows = raw.get("items") or []
    if day:
        sheet = R.present(raw, rid)
        # toolfix 3 (a day said order "newest" and listed its items oldest first): the day's items in the order asked,
        # then the page
        rows = _day_order(turn, raw, rows, a.order)[a.offset:a.offset + a.limit]
    else:
        if kind == "first":
            rows = rows[a.offset:a.offset + a.limit]
        sheet = {"kind": "items", "window": R.clean(raw.get("window")), "filters": R.clean(raw.get("filters")),
                 "totals": {"items": (raw.get("totals") or {}).get("items", 0)}}
    sheet["items"] = _item_rows(turn, raw, rows, q, rid)
    meta = _meta(turn, raw, a.scope, resolved)
    meta["order"] = a.order
    return _finish(turn, "items", rid, raw, sheet, meta, t0, w, keep="items", how=a.scope.how)


def _day_order(turn, raw, rows, order):
    """A day's item rows (facts gives them in time order, oldest first) in the order asked: newest first, oldest
    first, or the most opened that day first (a tie keeps time order)."""
    rows = list(rows)
    if order == "newest":
        return rows[::-1]
    if order == "most_opened":
        from datetime import date
        d = (raw.get("window") or {}).get("start")
        day = date.fromisoformat(d) if d else None

        def n(r):
            evs = turn.lib.rec.events.get(r.get("id"), [])
            return sum(1 for e, k in evs if k in ("watch", "view") and (day is None or e == day))
        return sorted(rows, key=lambda r: -n(r))
    return rows


def _fit(score):
    if not isinstance(score, (int, float)):
        return "weak"
    return "clear" if score >= FIT_CLEAR else "close" if score >= FIT_CLOSE else "weak"


def _why(text, why, query):
    """A line of the item's own text: the backend's when it is in the text, else the first line holding a word of
    the query, else none."""
    from ..compose import line_in_text
    if isinstance(why, str) and why.strip() and line_in_text(why, text):
        return why.strip()
    words = [w for w in re.findall(r"[a-z0-9]+", (query or "").lower()) if w not in Hm.STOP and len(w) > 2]
    for line in re.split(r"(?<=[.!?])\s+|\n", text or ""):
        if line.strip() and any(Hm.holds(line, w) for w in words):
            return line.strip()
    return None


def run_search(turn, a: SearchArgs):
    """By meaning, through the injected backend; code keeps only items they may see, of the kind and window asked,
    with a why-line that is in the item's own text."""
    t0 = time.monotonic()
    if turn.counts.get("search", 0) >= SEARCH_PER_TURN:
        raise ToolError(f"at most {SEARCH_PER_TURN} searches a turn")
    if turn.search is None:
        raise ToolError("search is not available in this build")
    w = _window(turn, a.window) if a.window is not None else None
    start = end = None
    if w is not None:
        rec = turn.lib.rec
        plats = sorted(rec.ends)
        start, end = Hm.resolve(w, rec, plats, turn.today)
    turn.counts["search"] = turn.counts.get("search", 0) + 1
    got = turn.search(turn, a.query, a.how, start, end, a.limit) or {}
    kinds = set(Hm.HOW_KINDS[HOW[a.how]])
    rid = turn.next_rid()
    rows, seen = [], set()
    for x in got.get("items") or []:
        iid = x.get("item_id") if isinstance(x, dict) else None
        if not iid or iid in seen or not turn.lib.is_visible(iid):
            continue
        evs = [(d, k) for d, k in turn.lib.rec.events.get(iid, []) if k in kinds
               and (start is None or d >= start) and (end is None or d <= end)]
        if not evs:
            continue
        seen.add(iid)
        it = turn.lib.view.items[iid]
        why = _why(it.caption or "", x.get("why"), a.query)
        fit = x.get("fit") if x.get("fit") in ("clear", "close", "weak") else _fit(x.get("score"))
        rows.append({"ref": f"{rid}.items[{len(rows)}]", "item_id": iid, "title": R.neutral(Hm._title(it), R.TITLE_MAX),
                     "channel": R.neutral(it.creator, R.NAME_MAX), "platform": it.platform,
                     "when": max(d for d, _k in evs).isoformat(),
                     "why_matched": R.neutral(why, R.TEXT_MAX) if why else None, "fit": fit})
        if len(rows) >= a.limit:
            break
    sheet = {"kind": "search", "query": R.neutral(a.query), "how": a.how, "items": rows}
    meta = {"window_said": None if w is None else _window_said(turn, w), "base": BASE[a.how], "filters_said": None,
            "resolved": {}, "order": "fit", "complete": False,
            "hidden": {"sensitive": 0, "friends": _friends(turn, a.how, start, end), "rank_hidden_above": False},
            "notes": ["Ranked by meaning; `fit` says how close each one is. Not a count of everything on the topic."]}
    return _finish(turn, "search", rid, None, sheet, meta, t0, w, got.get("cost_usd", 0.0), keep="items")


def _friends(turn, how, start, end, q=None):
    """Toolfix 8: the friends' posts left out of this result's window and base (facts.friends_in)."""
    return F.friends_in(turn.lib.view, turn.tz, Hm.HOW_KINDS[HOW[how]], sorted(turn.lib.rec.ends) or
                        ["youtube", "instagram"], start and start.toordinal(), end and end.toordinal(), q)


def _not_after_end(turn, w, why):
    rec = turn.lib.rec
    plats = sorted(rec.ends)
    if not plats:
        return
    s, _e = Hm.resolve(w, rec, plats, turn.today)
    newest = max(rec.ends.values())
    if s is not None and s > newest:
        raise ToolError(f"that window starts after where the export ends ({Hm.day_words(newest)}): {why}; say what "
                        "the export holds, or ask for a new export")


def _window_said(turn, w):
    rec = turn.lib.rec
    plats = sorted(rec.ends)
    s, e = Hm.resolve(w, rec, plats, turn.today)
    q = Hm.HistoryQuery(kind="count", window=w)
    return F.window_words(q, w, s, e, rec, plats)[0]


def run_learned(turn, a: LearnedArgs):
    """What their own items say on a topic, through the injected backend (today's synth path: a paid call); code
    keeps a point only with a source they may see, and neutralises its text."""
    t0 = time.monotonic()
    if turn.counts.get("learned", 0) >= LEARNED_PER_TURN:
        raise ToolError(f"at most {LEARNED_PER_TURN} learned call a turn")
    if turn.learned is None:
        raise ToolError("learned is not available in this build")
    resolved = {}
    q, bad = _query(turn, a.scope, "count", Hm.Window(), resolved)
    if bad:
        return _unresolved(turn, "learned", bad)
    turn.counts["learned"] = turn.counts.get("learned", 0) + 1
    got = turn.learned(turn, a.topic, q) or {}
    rid = turn.next_rid()
    points = []
    for p in got.get("points") or []:
        if not isinstance(p, dict) or not isinstance(p.get("text"), str):
            continue
        ids_ = [i for i in p.get("item_ids") or [] if isinstance(i, str)]
        src = [i for i in ids_ if turn.lib.is_visible(i)]
        if not src or len(src) != len(ids_):
            # step 1 fix (the tools audit): a point that rests on a source they may not see (a friend's post, a
            # sensitive item) may say what that source says, so the point goes, not only the source
            continue
        n = len(points)
        points.append({"ref": f"{rid}.points[{n}]", "text": R.neutral(p["text"], R.TEXT_MAX),
                       "sources": [{"item_id": i, "title": R.neutral(Hm._title(turn.lib.view.items[i]), R.TITLE_MAX)}
                                   for i in src]})
    sheet = {"kind": "learned", "topic": R.neutral(a.topic), "points": points}
    meta = {"window_said": None, "base": BASE[a.scope.how], "filters_said": _filters_said(turn, a.scope, resolved),
            "resolved": resolved, "order": None, "complete": False,
            "hidden": {"sensitive": 0, "friends": _friends(turn, a.scope.how, None, None, q),
                       "rank_hidden_above": False},
            "notes": ["Each point was checked against the text of its sources."]}
    return _finish(turn, "learned", rid, None, sheet, meta, t0, None, got.get("cost_usd", 0.0), keep="points")


# ================================================================ the registry
@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    params: type
    run: Optional[Callable]
    kind: str            # read | propose | final
    cost: str            # free | embedding | paid
    doors: frozenset = frozenset({"chat"})
    version: str = TOOLS_VERSION


UNITS = ("Shares are fractions (0.38 = 38%); `change_pts` and theme `change_vs_previous` are percentage points. "
         "Every row carries its `ref`; cite a cell as <ref>.<field>.")
REGISTRY = {t.name: t for t in (
    ToolDef("find", "Turn the names they use (an area, a theme, a channel, a collection, words in titles) into refs, "
            "and say how each was read. Ambiguous or unknown names come back with options and no numbers.",
            FindArgs, run_find, "read", "free", frozenset({"chat", "mcp"})),
    ToolDef("breakdown", "What they opened (or liked, saved) in one window, ranked by area, theme or channel (or just "
            "the totals), most or least first, with the window before. " + UNITS,
            BreakdownArgs, run_breakdown, "read", "free", frozenset({"chat", "mcp"})),
    ToolDef("timeline", "Their items per month or per year over a window, with the peaks. " + UNITS,
            TimelineArgs, run_timeline, "read", "free", frozenset({"chat", "mcp"})),
    ToolDef("changes", "What changed: new and stopped themes and channels, rising and fading areas and themes, against "
            "the window before or the same window last year. " + UNITS,
            ChangesArgs, run_changes, "read", "free", frozenset({"chat", "mcp"})),
    ToolDef("compare", "Two windows side by side in one result (`totals` is a, `previous` is b). " + UNITS,
            CompareArgs, run_compare, "read", "free", frozenset({"chat", "mcp"})),
    ToolDef("first_last", "The first or the last time they opened something of a subject, with the item.",
            FirstLastArgs, run_first_last, "read", "free", frozenset({"chat", "mcp"})),
    ToolDef("items", "Example items of a window and scope (most opened, newest or oldest); a one-day window returns the "
            "day against their usual day. Never a link.",
            ItemsArgs, run_items, "read", "free", frozenset({"chat", "mcp"})),
    ToolDef("search", "Find saved or opened items by meaning, with the line of their own text that matched.",
            SearchArgs, run_search, "read", "embedding", frozenset({"chat"})),
    ToolDef("learned", "What their own saved items say about a topic, as checked points with their sources.",
            LearnedArgs, run_learned, "read", "paid", frozenset({"chat"})),
    ToolDef("propose_rule", "Step 2: propose a rule as a card they confirm.", ProposeRuleArgs, None, "propose", "free"),
    ToolDef("propose_send", "Step 2: propose an email of an answer to themselves as a card.", ProposeSendArgs, None,
            "propose", "free"),
)}


def call(turn, name, args):
    """Run one tool call: `args` a dict or a JSON string. A bad call comes back as an error result (is_error) with
    code's reason, never an exception."""
    t = REGISTRY.get(name)
    if t is None:
        return R.error(f"no tool named {name!r}")
    if t.run is None:
        return R.error(f"{name} is not available in this build", tool=name)
    try:
        if isinstance(args, str):
            args = json.loads(args or "{}")
        a = t.params(**(args or {}))
    except (ValueError, TypeError, ValidationError) as e:
        return R.error(_short(e), tool=name)
    try:
        return t.run(turn, a)
    except ToolError as e:
        return R.error(str(e), tool=name)
    except Exception as e:  # noqa: BLE001 - a backend or a sheet that fails is an error result, never a crash
        return R.error(f"the tool failed ({type(e).__name__}); try another way or say what is missing", tool=name)


def _short(e):
    if isinstance(e, ValidationError):
        return "; ".join(f"{'.'.join(str(x) for x in er['loc']) or 'arguments'}: {er['msg']}" for er in e.errors()[:4])
    return str(e)[:300]


# ================================================================ the schemas sent to a provider
_STRIP = ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength", "minItems",
          "maxItems", "default", "title", "pattern")


def _strict(o):
    """Every object: all fields required, no others allowed; bounds and defaults stripped (checked in code)."""
    if isinstance(o, dict):
        o = {k: _strict(v) for k, v in o.items() if k not in _STRIP}
        if o.get("type") == "object" and isinstance(o.get("properties"), dict):
            o["required"] = sorted(o["properties"])
            o["additionalProperties"] = False
        return o
    if isinstance(o, list):
        return [_strict(v) for v in o]
    return o


def _sorted(o):
    if isinstance(o, dict):
        return {k: _sorted(o[k]) for k in sorted(o)}
    if isinstance(o, list):
        return [_sorted(v) for v in o]
    return o


def schema(name):
    t = REGISTRY[name]
    return _sorted(_strict(t.params.model_json_schema()))


def schemas(door="chat", kinds=("read",)):
    """[{name, description, input_schema}] of the tools open at a door, sorted by name (byte-identical each time)."""
    return [{"name": n, "description": REGISTRY[n].description, "input_schema": schema(n)}
            for n in sorted(REGISTRY) if door in REGISTRY[n].doors and REGISTRY[n].kind in kinds
            and REGISTRY[n].run is not None]
