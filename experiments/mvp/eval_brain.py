"""PROTOTYPE ONLY - the brain's offline eval, step 1 (design/brain_v1/SPEC.md 12.2 step 1, 12.4, 4.8).

    python3 -m mvp.eval_brain planted [--show dropped_true|kept_false|wrong_reason]   (from experiments/)
    python3 -m mvp.eval_brain plans [--json OUT] [--only A01,B07]
    python3 -m mvp.eval_brain insight
    python3 -m mvp.eval_brain run --half tune --out DIR [--limit N] [--ids A02,B04] [--parallel N] [--max-usd 1.5]
    python3 -m mvp.eval_brain run --set fresh --half a|b|all --out DIR [--set-file F]   (evalset/brain_fresh.jsonl)
    python3 -m mvp.eval_brain audit --run DIR      (offline: auditor hints and G2 again)
    python3 -m mvp.eval_brain read --run DIR [--out FILE]      (offline: the plain-text reading sheet)
    python3 -m mvp.eval_brain marks --run DIR --marks FILE     (offline: the hand marks into summary.json)
    python3 -m mvp.eval_brain count [--out DIR]

`run` (step 2's thin live slice, LIVE: claude-haiku-5-5, paid, needs the Claude key and MVP_LEDGER_HOME): every "plan"
message of the half (the split: half_of) through brain/loop.run_turn on the same made-up library, the screen carried
from message to message; per message one JSON (calls with results, forms, verdicts, the repair, the answer sent,
lead_source, sentence counts, seconds, tokens, cost, G2 against every acceptable reading, the auditor's hints on what
was sent) and summary.json (G1 to G6). G1 (false or wrongly based sentences sent) needs a hand recount: it stays empty
until `marks` fills it; the auditor's findings are `auditor_hints`, not a G1 figure (mvp22: on the held-out half it
caught 1 of 5 false sentences). `read` writes one sheet for a hand reader (eval/brain_reading_rubric.md); `marks`
fills summary.json's `reading` fields and the hand G1 from it. `count`: count_tokens (free) on the prefix and a
typical turn.

`planted`: eval/brain_planted.json through the verifier (brain/planted.py's scorer): every false sentence dropped (and
with which reason), every true one kept, by class.

`plans`: every hand-written plan of evalset/brain_plans.jsonl (the tool calls a good model would make for each
message of evalset/brain_core.jsonl) run through the tools on the made-up library of tests/brain_library.py, with
tests/fakes/fake_brain.py standing in for the model (it replays the plan's rounds). Per planned message: the results;
the code lead made from them (brain/fallback.py) and verified; every number of every result recounted by the
auditor (eval_claims.audit_results: its own reading of the raw rows, sharing no code with the bot), and every cell
the code lead cites recounted (eval_claims.audit_ledger); the plan's own expected facts (`expect`) checked; the window
the auditor reads from the message set against the window code resolved (`understood_window`, reported apart).

`insight`: the 20 questions of eval/insight_cases.json: how many a tool call answers with today's fact sheet
(facts.sheet) byte for byte, how many with the same numbers, how many the library cannot answer, and which no one
call maps.

`planted`, `plans`, `insight`, `audit` and the tests are offline: no model call, no network. The library is built in a
temporary folder (MVP_HOME, MVP_LEDGER_HOME, MVP_INBOX and MVP_DERIVED_HOME point inside it before any of the bot's
modules is imported); nothing is read from or written to data/. `run` (live) keeps the caller's MVP_LEDGER_HOME: its
only write under data/ is the ledger, through ai.log_batch.
"""
import argparse
import json
import os
import re
import sys
import tempfile
from datetime import date, datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.join(HERE, "evalset", "brain_core.jsonl")
PLANS = os.path.join(HERE, "evalset", "brain_plans.jsonl")
INSIGHT = os.path.join(HERE, "eval", "insight_cases.json")
HANDLE = "+15550000000"
TZ = "America/New_York"
NOW = datetime(2026, 11, 22, 17, 0, tzinfo=timezone.utc)      # Sunday 22 November 2026, noon in New York
TODAY = date(2026, 11, 22)
ADDRESS = "test.person@example.com"
TIERS = ("plan", "t0", "step2", "step3")


# ================================================================ the made-up library and a bot to read it
def scratch_env(base, keep_ledger=False):
    """Point every home of the bot inside `base` (call before importing any of the bot's modules). keep_ledger (the
    live `run` mode): MVP_LEDGER_HOME stays the caller's, so every paid request lands in the shared ledger and the
    Claude cap counts it."""
    for k, sub in (("MVP_HOME", "home"), ("MVP_LEDGER_HOME", "ledger"), ("MVP_INBOX", "inbox"),
                   ("MVP_DERIVED_HOME", "derived")):
        if keep_ledger and k == "MVP_LEDGER_HOME":
            continue
        os.environ[k] = os.path.join(base, sub)
    os.environ.pop("YOUTUBE_API_KEY", None)


def build_library(base):
    """tests/brain_library.py written under base/lib, its lengths from the fake videos.list and its themes from the fake
    namer (code only), into the derived home already set. Returns the library path."""
    from mvp import lengths as L, themes as T
    from mvp.tests import brain_library as B
    from pathlib import Path
    lib = B.write(Path(base) / "lib")
    L.run(str(lib), key="made-up-key", fetch=B.fake_videos_list(), now=NOW, log=lambda s: None)
    T.build(str(lib), chat=B.fake_namer([]), log=lambda s: None)
    return str(lib)


class LiteBot:
    """What the read tools need of the bot: a store (the person's profile) and a cached library view."""

    def __init__(self, home):
        from mvp.libview import LibraryView
        from mvp.store import Store
        self.store = Store(os.path.join(home, "eval_brain.db"))
        self._view_cls = LibraryView
        self.views = {}

    def view(self, library):
        if library not in self.views:
            self.views[library] = self._view_cls(library)
        return self.views[library]


class Harness:
    """One made-up library, one person, the eval's clock."""

    def __init__(self, bot, library, derived, handle=HANDLE, now=NOW):
        self.bot, self.library, self.derived, self.now = bot, library, derived, now
        self.person = {"handle": handle, "library": library, "timezone": TZ}
        self._audit_lib = None

    @classmethod
    def scratch(cls, base=None, keep_ledger=False):
        """A harness on a library built in a temporary folder (the command line's)."""
        base = base or tempfile.mkdtemp(prefix="eval_brain_")
        scratch_env(base, keep_ledger=keep_ledger)
        lib = build_library(base)
        bot = LiteBot(os.environ["MVP_HOME"])
        bot.store.upsert_person(HANDLE, "Test", lib, TZ)
        return cls(bot, lib, os.environ["MVP_DERIVED_HOME"])

    def turn(self, message="", screen="", last_window=None, search=None, learned=None):
        from mvp.brain import tools as TL
        return TL.Turn(self.bot, self.person, self.now, message=message, screen=screen, last_window=last_window,
                       search=search, learned=learned)

    def audit_lib_for(self, unlock=None):
        """The auditor's own reading of the same raw rows (eval_claims.Library), the sensitive themes left out as the
        tools leave them out, but for the topic the turn unlocked."""
        if self._audit_lib is None:
            self._audit_lib = {}
        if unlock not in self._audit_lib:
            from mvp import eval_claims as EC
            self._audit_lib[unlock] = EC.Library(self.library, self.derived, TZ, now=self.now, hide_sensitive=True,
                                                 unlock=unlock)
        return self._audit_lib[unlock]


# ================================================================ the eval set and the plans
def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def _segs(path):
    out = []
    for part in path.split("."):
        m = re.fullmatch(r"([^\[\]]+)((?:\[(?:\d+|\*)\])*)", part)
        if not m:
            raise ValueError(path)
        out.append(m.group(1))
        out += [int(x) if x != "*" else "*" for x in re.findall(r"\[(\d+|\*)\]", m.group(2))]
    return out


def get_at(results, path):
    """A value of a result by an expect path: 'r1.channels[0].name' (in the sheet), 'r1.meta.filters_said',
    'r1.sheet.filters.without_shorts', 'r1.error', 'r1.channels[*].name' (a list). None when it is not there."""
    rid, _, rest = path.partition(".")
    env = results.get(rid)
    if env is None:
        return None
    segs = _segs(rest) if rest else []
    o = env if segs and segs[0] in ("meta", "sheet", "error", "options", "name") else env.get("sheet")

    def walk(o, segs):
        for k, s in enumerate(segs):
            if s == "*":
                return [walk(x, segs[k + 1:]) for x in o] if isinstance(o, list) else None
            if isinstance(s, int):
                o = o[s] if isinstance(o, list) and -len(o) <= s < len(o) else None
            else:
                o = o.get(s) if isinstance(o, dict) else None
            if o is None:
                return None
        return o
    return walk(o, segs)


def check_expect(results, expect):
    """The plan's own facts, read on the results by name (a third reading: written by hand from the library's plan,
    not from the tools nor the auditor). -> [failure lines]."""
    bad = []
    for e in expect or []:
        v = get_at(results, e["at"])
        ok = True
        if "eq" in e:
            ok = v == e["eq"]
        if "starts" in e:
            ok = ok and isinstance(v, str) and v.startswith(e["starts"])
        if "has" in e:
            ok = ok and isinstance(v, list) and all(x in v for x in e["has"])
        if "lacks" in e:
            ok = ok and isinstance(v, list) and not any(x in v for x in e["lacks"])
        if "set" in e:
            ok = ok and isinstance(v, list) and sorted(v) == sorted(e["set"])
        if "only" in e:
            ok = ok and isinstance(v, list) and bool(v) and all(x in e["only"] for x in v)
        if "gt" in e:
            ok = ok and isinstance(v, (int, float)) and v > e["gt"]
        if "max" in e:
            ok = ok and isinstance(v, list) and bool(v) and all(isinstance(x, (int, float)) and x <= e["max"]
                                                                for x in v)
        if "len" in e:
            ok = ok and isinstance(v, list) and len(v) == e["len"]
        if not ok:
            want = {k: x for k, x in e.items() if k != "at"}
            bad.append(f"{e['at']}: got {json.dumps(v)[:160]}, want {json.dumps(want)}")
    return bad


def _has_content(env):
    s = (env or {}).get("sheet") or {}
    return bool(s.get("points") or s.get("items") or s.get("names") or (s.get("totals") or {}).get("items"))


def _window_of(env):
    w = ((env or {}).get("sheet") or {}).get("window") or {}
    return [w.get("start"), w.get("end")] if isinstance(w, dict) else [None, None]


def run_message(h, m, screen="", last_window=None, audit=True):
    """One planned message: the rounds replayed through the tools (the fake brain), the code lead, its check, the
    audit. -> a record (no third-party text in it but the results themselves)."""
    from mvp.brain import fallback as FB, tools as TL, verify as V
    from mvp.tests.fakes.fake_brain import FakeEngine, fake_learned, run_rounds
    engine = FakeEngine()
    t = h.turn(m["text"], screen=screen, last_window=last_window, search=engine, learned=fake_learned)
    calls, fb = run_rounds(t, m["rounds"], TL.call)
    rec = {"n": m["n"], "requests": fb.requests + 1, "calls": [], "errors": [], "expect_failed": [],
           "window_failed": [], "lead": None, "lead_how": None, "lead_ok": None, "findings": [], "checked": 0,
           "understood_window": []}
    by_rid = {}
    for k, c, r in calls:
        if r.get("is_error"):
            rec["errors"].append(f"{c['tool']}: {r.get('error')}")
            rec["calls"].append({"round": k, "tool": c["tool"], "error": r.get("error")})
            continue
        by_rid[r["rid"]] = r
        rec["calls"].append({"round": k, "tool": c["tool"], "rid": r["rid"], "args": c["args"],
                             "error": r.get("error")})
    rec["expect_failed"] = check_expect(by_rid, m.get("expect"))
    for rid, want in (m.get("window") or {}).items():
        got = _window_of(by_rid.get(rid))
        if got != want:
            rec["window_failed"].append(f"{rid}: got {got}, want {want}")
    vt = V.Turn.of(t)
    cl = FB.code_lead(t.results, turn=vt)
    rec.update(lead=cl["lead"], lead_how=cl["how"], private_line=cl["private_line"])
    marker_form, issues = None, []
    ledger = V.Ledger(t.results)
    if cl["how"] == "template":
        res = ledger.get(cl["rid"])
        forms = [x for x in FB.templates(res) if V.strip_markers(x) == cl["lead"]]
        marker_form = forms[0] if forms else None
        if not (marker_form and V.check_answer({"lead": marker_form, "points": []}, t.results, vt).lead_ok):
            issues.append("the template does not pass the verifier")
    elif cl["how"] == "code_form":
        # code_form's answer passed today's checks inside fallback (insight._check, the gate); the verifier's own
        # rule for a lead (SPEC 4.3 step 2: it names its window) is checked here, and a sentence starts as one
        if not V._lead_names_window(cl["lead"], ledger, cl["rid"]):
            issues.append("window_missing")
    if cl["lead"][:1].islower():
        issues.append("starts in lower case")
    core = re.split(r"[(,]", (((t.results.get(cl["rid"]) or {}).get("meta") or {}).get("window_said") or ""))[0]
    if cl["how"] == "code_form" and core.strip() and core.strip().lower() not in cl["lead"].lower():
        # the verifier's window rule (verify._lead_names_window, through insight.window_lead) passed it; the eval's
        # own reading: the lead holds the core words of its result's window
        issues.append("does not say its own window")
    if cl["how"] == "plain" and any(_has_content(env) for env in t.results.values()):
        # the plain line ("I couldn't check an answer to that in time") while a result holds what was asked
        issues.append("plain line with a result in hand")
    if cl["how"] != "plain" and cl["rid"] is None:
        issues.append("no result named")
    env0 = (t.results.get(cl["rid"]) or {}) if cl["rid"] else {}
    first_last = env0.get("tool") == "first_last"
    said = (env0.get("meta") or {}).get("window_said") or ""
    bare = cl["lead"].replace(said, " ") if said else cl["lead"]   # the window's own dates are not the item's day
    if first_last and not re.search(r"\b\d{1,2} (?:January|February|March|April|May|June|July|August|September|"
                                    r"October|November|December) \d{4}\b", bare):
        issues.append("a first or a last without the item's day")
    rec["lead_ok"], rec["lead_issues"] = not issues, issues
    rec["marker_form"] = marker_form
    if audit:
        from mvp import eval_claims as EC
        for k, c, r in calls:
            if r.get("is_error") or "sheet" not in r:
                continue
            lib = h.audit_lib_for(t.unlock)
            rows = EC.audit_results(lib, r, c, question=m["text"], today=TODAY, earlier=t.windows,
                                    last_window=last_window)
            n_all, n_rec, miss = EC.coverage(r, rows)
            rec["numbers"] = rec.get("numbers", 0) + n_all
            rec["recounted"] = rec.get("recounted", 0) + n_rec
            rec.setdefault("not_recounted", []).extend(
                f"{r['tool']}/{(r.get('sheet') or {}).get('kind')}:{re.sub(r'\[\d+\]', '[]', p)}" for p in miss)
            rec["checked"] += sum(1 for x in rows if x["kind"] != "understood_window")
            rec["findings"] += [x for x in rows if not x["ok"] and x["kind"] != "understood_window"]
            rec["understood_window"] += [x for x in rows if not x["ok"] and x["kind"] == "understood_window"]
        if cl["rid"] and cl["how"] != "plain":
            lib = h.audit_lib_for(t.unlock)
            call_of = {r["rid"]: c for _k, c, r in calls if r.get("rid")}
            rows = EC.audit_lead(lib, by_rid.get(cl["rid"]) or t.results.get(cl["rid"]),
                                 cl["lead"], marker_form, call=call_of.get(cl["rid"]), question=m["text"],
                                 today=TODAY)
            rec["checked"] += len(rows)
            rec["findings"] += [x for x in rows if not x["ok"]]
    rec["_window"] = t.windows.get("r1")
    rec["_results"] = by_rid
    return rec


def run_conversation(h, p, audit=True):
    """Every message of one conversation's plan, in order: the screen is the last code lead, the last window the last
    planned message's first result's."""
    out = {"id": p["id"], "status": p["status"], "messages": []}
    screen, last = "", None
    if p.get("before"):
        b = run_message(h, {"n": -1, "text": p["before"]["message"], "rounds": p["before"]["rounds"]}, audit=False)
        screen, last = b["lead"] or "", b["_window"]
    for m in p["messages"]:
        if m["tier"] != "plan":
            out["messages"].append({"n": m["n"], "tier": m["tier"], "why": m.get("why")})
            continue
        r = run_message(h, m, screen, last, audit=audit)
        r["tier"] = "plan"
        r["step2"] = m.get("step2") or []
        r["plan_finding"] = m.get("finding")
        screen, last = r["lead"] or screen, r["_window"] or last
        out["messages"].append(r)
    return out


# a finding's class: a number (a value, a rank, a date, a word of a sent lead) is what "recounts true" is about; a
# shape (a sheet row whose label says less than the name) and a window reading are listed apart, each with its why
SHAPE_KINDS = {"one name, two fields", "list cut"}


def finding_class(row):
    if row.get("audit") == "window":
        return "window"
    if row.get("kind") in SHAPE_KINDS:
        return "shape"
    return "number"


def _brief(row):
    return {k: row.get(k) for k in ("audit", "kind", "where", "said", "recount", "note")}


def plans(h, only=None):
    """Run every plan -> (summary, per-conversation records without the results)."""
    core = {r["id"]: r for r in load_jsonl(CORE)}
    out, convs = [], load_jsonl(PLANS)
    for p in convs:
        if only and p["id"] not in only:
            continue
        if p["status"] in ("step2", "step3"):
            out.append({"id": p["id"], "status": p["status"],
                        "messages": [{"n": m["n"], "tier": m["tier"], "why": m.get("why")} for m in p["messages"]]})
            continue
        out.append(run_conversation(h, p))
    s = {"conversations": len(out), "messages": sum(len(c["messages"]) for c in out),
         "by_status": {}, "messages_by_tier": {}, "planned_messages": 0, "calls": 0, "tool_errors": [],
         "expect_failed": [], "window_failed": [], "lead_how": {}, "lead_not_ok": [], "numbers_in_results": 0,
         "numbers_recounted": 0, "not_recounted": {}, "checked": 0, "findings": {"number": [], "shape": [],
                                                                                 "window": []},
         "understood_window": [], "recount_true": 0, "recount_not_true": [], "plan_findings": [],
         "step2_parts": 0}
    for c in out:
        s["by_status"][c["status"]] = s["by_status"].get(c["status"], 0) + 1
        bad = []
        for m in c["messages"]:
            s["messages_by_tier"][m["tier"]] = s["messages_by_tier"].get(m["tier"], 0) + 1
            if m["tier"] != "plan":
                continue
            where = f"{c['id']}.{m['n']}"
            s["planned_messages"] += 1
            s["calls"] += len(m["calls"])
            s["step2_parts"] += len(m.get("step2") or [])
            s["tool_errors"] += [f"{where}: {e}" for e in m["errors"]]
            s["expect_failed"] += [f"{where}: {e}" for e in m["expect_failed"]]
            s["window_failed"] += [f"{where}: {e}" for e in m["window_failed"]]
            s["lead_how"][m["lead_how"]] = s["lead_how"].get(m["lead_how"], 0) + 1
            if not m["lead_ok"]:
                s["lead_not_ok"].append(f"{where}: {'; '.join(m.get('lead_issues') or [])}")
            s["numbers_in_results"] += m.get("numbers", 0)
            s["numbers_recounted"] += m.get("recounted", 0)
            for p in m.get("not_recounted", []):
                s["not_recounted"][p] = s["not_recounted"].get(p, 0) + 1
            s["checked"] += m["checked"]
            for f in m["findings"]:
                cls = finding_class(f)
                s["findings"][cls].append(dict(_brief(f), at=where))
                if cls == "number":
                    bad.append(f)
            s["understood_window"] += [dict(_brief(f), at=where, message=core[c["id"]]["messages"][m["n"]])
                                       for f in m["understood_window"]]
            if m.get("plan_finding"):
                s["plan_findings"].append(f"{where}: {m['plan_finding']}")
        if c["status"] in ("plan", "partial"):
            if bad:
                s["recount_not_true"].append({"id": c["id"], "why": [dict(_brief(f)) for f in bad]})
            else:
                s["recount_true"] += 1
    s["with_a_plan"] = s["by_status"].get("plan", 0) + s["by_status"].get("partial", 0)
    s["waiting"] = {"step2": s["by_status"].get("step2", 0), "step3": s["by_status"].get("step3", 0)}
    return s, out


# ================================================================ planted
def planted():
    """eval/brain_planted.json through the verifier (brain/planted.py's scorer), by class."""
    from mvp.brain import planted as BP
    sc = BP.score()
    by = {}
    apart = ("audit_true", "attack", "attack_true")
    for r in sc["rows"]:
        if r.get("source") in ("attack", "attack_true"):
            continue   # mvp20 fix: the verifier attack's cases are scored apart (attack_kept_false, by_source)
        b = by.setdefault(r.get("class") or "?", {"false": 0, "dropped": 0, "dropped_expected": 0, "true": 0,
                                                    "kept": 0})
        if r["expect"] == "dropped":
            b["false"] += 1
            b["dropped"] += not r["kept"]
            b["dropped_expected"] += bool(not r["kept"] and r.get("reason_ok"))
        else:
            b["true"] += 1
            b["kept"] += r["kept"]
    s = {k: v for k, v in sc.items() if k != "rows"}
    s["true_kept_share"] = round(sc["true_kept"] / sc["true"], 4) if sc["true"] else None
    s["bar"] = {"false_all_dropped": sc["false_dropped"] == sc["false"],
                "true_kept_97": bool(sc["true"]) and sc["true_kept"] / sc["true"] >= 0.97}
    s["by_class"] = by
    s["kept_false"] = [r["id"] for r in sc["rows"] if r["expect"] == "dropped" and r["kept"]
                       and r.get("source") not in apart]
    s["dropped_true"] = [r["id"] for r in sc["rows"] if r["expect"] == "kept" and not r["kept"]
                         and r.get("source") not in apart]
    # the step 1 audit's own true sentences, scored apart from the bar (brain/planted.py)
    s["audit_true_dropped"] = [r["id"] for r in sc["rows"] if r.get("source") == "audit_true" and not r["kept"]]
    # mvp20 fix: the verifier attack's sentences, scored apart (false ones kept, true ones dropped)
    s["attack_kept_false"] = [r["id"] for r in sc["rows"] if r.get("source") == "attack" and r["kept"]]
    s["attack_true_dropped"] = [r["id"] for r in sc["rows"] if r.get("source") == "attack_true" and not r["kept"]]
    s["wrong_reason"] = [r["id"] for r in sc["rows"] if r["expect"] == "dropped" and not r["kept"]
                         and r.get("reason_ok") is False]
    return s


# ================================================================ the 20 insight cases
# each question of eval/insight_cases.json as the one tool call a good model would make (tests/test_brain_tools.py
# holds the same mapping for its own checks): SAME = the whole sheet the model reads is today's facts.sheet of the
# question; NUMBERS = a topic read by today's code as words is a resolved ref here (the numbers agree, not the shape);
# NO_MATCH = nothing of the topic in this library (today's sheet counts 0, the tool gives no number); NOT_MAPPED =
# history.read reads nothing of the question on this clock, or no one call is the question
INSIGHT_SAME = {
    "top_lately": ("breakdown", {"by": "area", "window": {"words": "lately"}}),
    "top_summer": ("breakdown", {"by": "area", "window": {"words": "the summer of 2023"}}),
    "channels_2025": ("breakdown", {"by": "channel", "window": {"words": "in 2025"}}),
    "channels_october": ("breakdown", {"by": "channel", "window": {"words": "in october"}}),
    "day_oct30": ("items", {"window": {"words": "on october 30"}, "limit": 10}),
    "day_sep12": ("items", {"window": {"words": "on 12 september"}, "limit": 10}),
    "changed_since_2020": ("changes", {"level": "area", "window": {"words": "since 2020"}}),
    "cmp_years": ("compare", {"a": {"words": "2024"}, "b": {"words": "2025"}}),
    "es_top": ("breakdown", {"by": "area", "window": {"preset": "lately"}}),
}
INSIGHT_NUMBERS = {
    "count_minecraft": ("breakdown", {"by": "none", "window": {"words": "this year"}, "scope": {"only": ["minecraft"]}}),
    "last_cooking": ("first_last", {"subject": "cooking", "which": "last"}),
}
INSIGHT_NO_MATCH = {
    "count_blender_all": ("breakdown", {"by": "none", "window": {"preset": "all"}, "scope": {"only": ["blender"]}}),
    "first_blender": ("first_last", {"subject": "blender", "which": "first"}),
    "first_chess": ("first_last", {"subject": "chess", "which": "first"}),
    "last_guitar": ("first_last", {"subject": "guitar", "which": "last"}),
}
INSIGHT_NOT_MAPPED = {
    "changed_this_year": "history.read returns None on this clock (no sheet to agree with)",
    "cmp_months": "history.read returns None on this clock",
    "cmp_cooking_guitar": "history.read returns None on this clock",
    "es_cmp": "history.read returns None on this clock",
    "cmp_gaming_art": "two topics in one window (compare_topics): no tool takes two topics; two breakdowns with "
                      "scope.only give the same numbers",
}


def insight(h):
    """How many of the 20 questions a tool call answers with today's fact sheet, identically."""
    from mvp import facts as F, history as Hm
    from mvp.brain import results as R, tools as TL
    with open(INSIGHT, encoding="utf-8") as f:
        cases = {c["id"]: c["sheet"]["question"] for c in json.load(f)["cases"]}
    rows = []

    def today_sheet(q):
        hq = Hm.read(q, TODAY)
        return None if hq is None else F.build(h.bot, h.person, hq, h.now, text=q, hide_sensitive=True)
    for cid in sorted(cases):
        q = cases[cid]
        if cid in INSIGHT_SAME:
            tool, args = INSIGHT_SAME[cid]
            t = h.turn(q)
            r = TL.call(t, tool, args)
            raw = today_sheet(q)
            lst = {"area": "areas", "channel": "channels", "theme": "themes"}.get(args.get("by"))
            want = R.present(raw, "r1", limits={lst: args.get("top", 8)} if lst else None)
            got = dict(r.get("sheet") or {})
            same_items = True
            if tool == "items":
                same_items = [i["item_id"] for i in got.pop("items", [])] == [i["id"] for i in raw.get("items")
                                                                             or []][:10]
                want["items"] = []
            # the tools' own presentation steps (results.honest, step 1 fix): no empty new/stopped without a window
            # before, one row per field name, no first save said as a first watch; every count is facts.sheet's
            R.honest(want, (args.get("scope") or {}).get("how", "opened"))
            R.cut_to_size(want, keep=lst or {"items": "items", "changes": "periods"}.get(tool))
            if tool == "items":
                want.pop("items", None)
            rows.append({"id": cid, "how": "identical" if (got == want and same_items) else "differs",
                         "truncated": bool((r.get("meta") or {}).get("truncated"))})
        elif cid in INSIGHT_NUMBERS:
            tool, args = INSIGHT_NUMBERS[cid]
            r = TL.call(h.turn(q), tool, args)
            raw = today_sheet(q)
            ok = (r.get("sheet") or {}).get("totals", {}).get("items") == (raw.get("totals") or {}).get("items")
            rows.append({"id": cid, "how": "same numbers" if ok else "numbers differ"})
        elif cid in INSIGHT_NO_MATCH:
            tool, args = INSIGHT_NO_MATCH[cid]
            r = TL.call(h.turn(q), tool, args)
            raw = today_sheet(q)
            ok = r.get("error") == "no_match" and (raw.get("totals") or {}).get("items") == 0
            rows.append({"id": cid, "how": "no match (0 today)" if ok else "differs"})
        else:
            rows.append({"id": cid, "how": "not mapped", "why": INSIGHT_NOT_MAPPED.get(cid, "?")})
    s = {"cases": len(rows), "by": {}}
    for r in rows:
        s["by"][r["how"]] = s["by"].get(r["how"], 0) + 1
    s["identical"] = s["by"].get("identical", 0)
    s["truncated_identical"] = sum(1 for r in rows if r["how"] == "identical" and r.get("truncated"))
    s["rows"] = rows
    return s


# ================================================================ run: the model on the tools, live (step 2's slice)
# The split (the brief of mvp20, fixed before any run): a conversation with a plan is in the TUNE half when
# int(sha1(id), 16) % 2 == 0, else in the HELD-OUT half. Only the tune half may be read while the prompt or the
# verifier changes.
NOW_WORDS = "Sun 22 Nov 2026 12:00, America/New_York"
PLAN_STATUSES = ("plan", "partial")
COUNTING = ("breakdown", "timeline", "changes", "compare", "first_last", "items", "search", "learned")


FRESH = os.path.join(HERE, "evalset", "brain_fresh.jsonl")
SETS = {"plans": PLANS, "fresh": FRESH}
HALVES = {"plans": ("tune", "heldout", "all"), "fresh": ("a", "b", "all")}


def half_of(cid, set_name="plans"):
    """The split. brain_plans.jsonl: tune or heldout. The fresh set (mvp22 brief): half a when the same sha1 is even,
    else b (b is locked: only a run and its independent readers read it)."""
    import hashlib
    even = int(hashlib.sha1(cid.encode()).hexdigest(), 16) % 2 == 0
    if set_name == "fresh":
        return "a" if even else "b"
    return "tune" if even else "heldout"


def run_set(half, ids=None, limit=None, set_name="plans", path=None):
    """[(plan conversation, core conversation)] of the half, in file order; `ids` keeps those conversations only;
    `limit` stops once that many plan messages are taken (whole conversations). set_name "plans": brain_plans.jsonl
    (halves tune, heldout, all; its conversations with a plan; the core conversation from brain_core.jsonl). "fresh":
    evalset/brain_fresh.jsonl or `path` (halves a, b, all; every conversation with a plan message; the line is its own
    core conversation)."""
    if half not in HALVES[set_name]:
        raise ValueError(f"half {half!r} is not one of {HALVES[set_name]} for the {set_name} set")
    path = path or SETS[set_name]
    core = {r["id"]: r for r in load_jsonl(CORE)} if set_name == "plans" else {}
    out, n = [], 0
    for p in load_jsonl(path):
        if set_name == "plans" and p["status"] not in PLAN_STATUSES:
            continue
        k = sum(1 for m in p["messages"] if m["tier"] == "plan")
        if set_name == "fresh" and not k:
            continue
        if half != "all" and half_of(p["id"], set_name) != half:
            continue
        if ids and p["id"] not in ids:
            continue
        if limit is not None and n >= limit:
            break
        out.append((p, core[p["id"]] if set_name == "plans" else p))
        n += k
    return out


def _scope_said(env):
    meta = (env or {}).get("meta") or {}
    parts = sorted(x.strip() for x in str(meta.get("filters_said") or "").split("; ") if x.strip())
    if ((env or {}).get("sheet") or {}).get("filters", {}).get("without_shorts") and \
            "only videos known to be long" not in parts:
        parts.append("only videos known to be long")
    return parts


def _scope_norm(parts):
    """mvp22: first_last says its subject as "<word>: <label>" (tools.first_last's meta.filters_said) where every
    other tool says "only <label>": the same scope, said one way."""
    out = []
    for x in parts:
        m = re.fullmatch(r"([^:]+): (.+)", x)
        out.append("only " + m.group(2) if m and not re.match(r"(?:only|without|on) ", x) else x)
    return sorted(out)


_COUNT_KEYS = ("name", "items", "previous_items", "by_platform", "shorts", "long")


def _counted(env):
    """mvp22: what a result counted, as a short hash of its counts only: every row's name and count, at any depth,
    and the totals' counts (no share, median or usual-day figure, no words of the ask, no refs); None for a result
    that counted nothing (two empty results are alike under any scope, so they prove nothing)."""
    import hashlib
    sheet = (env or {}).get("sheet") or {}
    if not ((sheet.get("totals") or {}).get("items")):
        return None

    def clean(o):
        if isinstance(o, dict):
            out = {}
            for k, v in o.items():
                if k == "by_platform":
                    out[k] = v
                elif isinstance(v, (dict, list)):
                    c = clean(v)
                    if c:
                        out[k] = c
                elif k in _COUNT_KEYS:
                    out[k] = v
            return out
        if isinstance(o, list):
            return [c for c in (clean(v) for v in o) if c not in ({}, [])] if any(isinstance(v, (dict, list))
                                                                              for v in o) else []
        return o
    body = clean({k: v for k, v in sheet.items() if k not in ("question", "kind", "window", "filters")})
    return hashlib.sha1(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:12]


def call_key(tool, args, env):
    """What one counting call counts, as code resolved it: the tool and what it ranks by, the window as days (and the
    second window of a compare), the base, the scope (meta.filters_said, code's fixed words) and the order. mvp22:
    also `scope_n` (the scope said one way, _scope_norm) and `counted` (_counted), read by the scorer's rules only."""
    args = args or {}
    sheet = (env or {}).get("sheet") or {}
    meta = (env or {}).get("meta") or {}
    what = {"breakdown": args.get("by", None), "changes": args.get("level"), "timeline": args.get("unit"),
            "compare": args.get("by", "none"), "first_last": args.get("which"), "items": None,
            "search": None, "learned": None}.get(tool)
    order = meta.get("order") or "most"
    if tool == "items":
        order = args.get("order") or "most_opened"
    w = sheet.get("window") or {}
    prev = sheet.get("previous") or {}
    window = [w.get("start"), w.get("end")] if isinstance(w, dict) else [None, None]
    if tool == "compare":
        # the second window: its days when the sheet has them, else read from its words (verify's own reader), else
        # the words themselves (a compare's `previous` carries words, not dates)
        from mvp.brain import verify as V
        pw = V.Result(env).prev_window() if env else None
        if pw:
            window = window + [pw[0].isoformat(), pw[1].isoformat()]
        else:
            window = window + [prev.get("start") or prev.get("words"), prev.get("end")]
    scope = _scope_said(env)
    return {"tool": tool, "what": what, "window": window, "base": meta.get("base"), "scope": scope,
            "order": order, "scope_n": _scope_norm(scope), "counted": _counted(env)}


DIMS = ("tool", "what", "window", "base", "scope", "order")
CORE_DIMS = ("window", "base", "scope", "order")
# mvp22: the scorer's rules (each one named, so a figure can be given with and without it):
# - first_round: a reading's calls of its first round with a counting call are what the message asks; later rounds
#   act on what the first found ("a second, longer look when the first finds nothing stopped") and are reported, not
#   required
# - first_last_scope: the scope compared as _scope_norm says it
# - total_in_breakdown: a hand breakdown by none (a total) is in any breakdown of the same window, base, scope, order
# - finer_unit: a hand timeline by year is in a timeline by month of the same window, base, scope, order
# - same_counts: a model scope that is the hand's plus more filters, whose result counted exactly the same (and not
#   nothing), is the hand's scope
RULES = ("first_round", "first_last_scope", "total_in_breakdown", "finer_unit", "same_counts")
UNIT_RANK = {"month": 1, "year": 2}


def _dim_ok(d, hk, mk, rules=()):
    if d == "scope":
        hs, ms = hk["scope"], mk["scope"]
        if "first_last_scope" in rules:
            hs, ms = hk.get("scope_n", hs), mk.get("scope_n", ms)
        if hs == ms:
            return True
        return "same_counts" in rules and set(hs) < set(ms) and hk.get("counted") is not None and \
            hk.get("counted") == mk.get("counted")
    if d == "what":
        if hk["what"] == mk["what"]:
            return True
        if hk["tool"] != mk["tool"]:
            return False
        if "total_in_breakdown" in rules and hk["tool"] == "breakdown" and hk["what"] == "none":
            return True
        return "finer_unit" in rules and hk["tool"] == "timeline" and \
            UNIT_RANK.get(mk["what"], 99) < UNIT_RANK.get(hk["what"], 0)
    return hk.get(d) == mk.get(d)


def compare_plans(hand, model, rules=()):
    """G2 for one message: `hand`, `model` lists of call_key. -> {"verdict": "understood" | "other_plan" | "differs" |
    "no_hand_plan", "diffs": [...]}. Understood: every hand call has a model call equal on every dimension; other plan
    (for a human to judge, never counted as understood): every hand call has a model call with the same window, base,
    scope and order, but the tool or what it ranks by differs; differs: some hand call has no such model call (the
    nearest model call's differing dimensions are listed). Extra model calls do not count against it. `rules` (mvp22,
    RULES): the equalities the scorer accepts beyond the exact one; none (the default) is the scorer as it was."""
    if not hand:
        return {"verdict": "no_hand_plan", "diffs": []}
    verdicts, diffs = [], []

    def ok(hk, mk, dims):
        return all(_dim_ok(d, hk, mk, rules) for d in dims)
    for hk in hand:
        if any(ok(hk, mk, DIMS) for mk in model):
            verdicts.append("understood")
            continue
        if any(ok(hk, mk, CORE_DIMS) for mk in model):
            near = next(mk for mk in model if ok(hk, mk, CORE_DIMS))
            verdicts.append("other_plan")
            diffs.append({"hand": hk, "model": near, "differs": [d for d in DIMS if not _dim_ok(d, hk, near, rules)]})
            continue
        verdicts.append("differs")
        near = max(model, key=lambda mk: sum(_dim_ok(d, hk, mk, rules) for d in DIMS)) if model else None
        diffs.append({"hand": hk, "model": near, "differs": [d for d in DIMS if near is None or
                                                             not _dim_ok(d, hk, near, rules)]})
    v = "differs" if "differs" in verdicts else "other_plan" if "other_plan" in verdicts else "understood"
    return {"verdict": v, "diffs": diffs}


_RANK = {"understood": 0, "other_plan": 1, "differs": 2}


def score_readings(readings, model, rules=RULES):
    """G2 over every acceptable reading of a message (mvp22): `readings` a list, one per reading, of the hand keys of
    its counting calls (each with its `round`), the preferred reading first. The best verdict of any reading, and which
    reading it was (the first of the best). With "first_round" in `rules`, a reading's later rounds are not required
    (listed in `later_rounds_missed` when no model call matches them)."""
    best = None
    for i, keys in enumerate(readings or []):
        if not keys:
            continue
        req = keys
        if "first_round" in rules:
            first = min(k.get("round", 0) for k in keys)
            req = [k for k in keys if k.get("round", 0) == first]
        v = compare_plans(req, model, rules)
        later = [k for k in keys if k not in req]
        v["later_rounds_missed"] = [k for k in later if compare_plans([k], model, rules)["verdict"] != "understood"]
        v["reading"] = i
        if best is None or _RANK[v["verdict"]] < _RANK[best["verdict"]]:
            best = v
    if best is None:
        return {"verdict": "no_hand_plan", "diffs": [], "reading": None, "later_rounds_missed": []}
    return best


def g2_of(readings, model):
    """The record's g2: the verdict of score_readings with every rule, its reading, how many readings there were, and
    `verdict_strict`: the scorer as it was before mvp22 (the preferred reading only, every call, exact equality)."""
    v = score_readings(readings, model)
    first = readings[0] if readings else []
    v["readings"] = len(readings or [])
    v["verdict_strict"] = compare_plans(first, model)["verdict"] if first else "no_hand_plan"
    return v


def readings_of(m):
    """The acceptable readings of one plan message: the fresh set's `readings` (1 to 3, the preferred first: {rounds,
    window, note}), or brain_plans.jsonl's one hand plan (its rounds and window)."""
    if m.get("readings"):
        return [{"rounds": r.get("rounds") or [], "window": r.get("window") or {}, "note": r.get("note")}
                for r in m["readings"]]
    if m.get("rounds"):
        return [{"rounds": m["rounds"], "window": m.get("window") or {}, "note": "the hand plan"}]
    return []


def hand_readings(h, m, screen="", last=None):
    """Every acceptable reading of a message replayed through the tools (the fake brain) from the hand chain's screen
    and last window. -> (the preferred reading's record, on which the chain goes on, or None; [hand_keys of each
    reading]; and the set's faults, not the model's: [a reading's window that is not the one it states], [a tool error
    of a reading, a reading with no counting result])."""
    recs = []
    for r in readings_of(m):
        recs.append(run_message(h, {"n": m["n"], "text": m["text"], "rounds": r["rounds"], "window": r["window"]},
                                screen, last, audit=False))
    windows, errors = [], []
    for k, x in enumerate(recs):
        windows += [f"reading {k}: {f}" for f in x["window_failed"]]
        errors += [f"reading {k}: tool error {e}" for e in x["errors"]]
        if not hand_keys(x):
            errors.append(f"reading {k}: no counting call with a result (the reading scores nothing)")
    return (recs[0] if recs else None), [hand_keys(x) for x in recs], windows, errors


def hand_keys(hand_rec):
    out = []
    for c in hand_rec["calls"]:
        if c.get("error") or c["tool"] not in COUNTING or not c.get("rid"):
            continue
        env = hand_rec["_results"].get(c["rid"])
        if env is None or "sheet" not in env:
            continue
        out.append(dict(call_key(c["tool"], c.get("args"), env), round=c.get("round", 0)))
    return out


def model_keys(rec):
    out = []
    for c in rec["calls"]:
        env = c.get("result") or {}
        if c["name"] not in COUNTING or env.get("is_error") or "sheet" not in env:
            continue
        out.append(call_key(c["name"], c.get("args"), env))
    return out


def audit_sent(h, results, unlock, rec, question):
    """The auditor on what was SENT, one sentence at a time (audit_sentence: its value markers through
    eval_claims.audit_ledger, its words through TextAudit over the result it cites), and a code lead through
    audit_lead. Hints for a hand recount, not a count of false sentences (mvp22). `results`: {rid: envelope} of the
    turn. -> [rows not ok, each naming its sentence], rows checked. Reading one sentence at a time leaves out the
    auditor's answer-level checks (a fact said twice, more than two base phrasings)."""
    calls = calls_of(rec)
    rows = []
    src = rec["lead_source"]
    sent = []
    if src in ("model", "model_after_repair"):
        k = len(rec["verdicts"]) - 1 if src == "model_after_repair" else 0
        sent = [o for o in rec["verdicts"][k]["outcomes"] if o["kept"] and o["where"] in ("lead", "point")]
    elif rec["verdicts"]:
        sent = [o for o in rec["verdicts"][-1]["outcomes"] if o["kept"] and o["where"] == "point"]
    # mvp22: one sentence at a time, so each hint names the one sentence it is about (the sentences of a result were
    # read joined before, and the reader split them again, so a hint could stand on two sentences)
    for o in sent:
        rows += audit_sentence(h, results, calls, unlock, o["text"], o["sent"] or "",
                               o.get("rid") or rec["answer"].get("rid"), question)
    if src == "code" and rec.get("code_lead") and rec["code_lead"].get("rid"):
        rows += audit_code_lead(h, results, calls, unlock, rec["code_lead"], question)
    bad = [{k: r.get(k) for k in ("audit", "kind", "where", "said", "recount", "note", "sentence")}
           for r in rows if not r["ok"]]
    return bad, len(rows)


def calls_of(rec):
    """{rid: {tool, args}} of a saved run record's calls."""
    return {c["rid"]: {"tool": c["name"], "args": c["args"]} for c in rec["calls"] if c.get("rid")}


def audit_sentence(h, results, calls, unlock, marked, sent, rid, question):
    """The auditor on ONE sentence of the model: its value markers recounted (eval_claims.audit_ledger on the marker
    form `marked`) and its words (`sent`, the markers out) read by TextAudit over the result it cites (`rid`).
    -> every row, ok or not, each with `sentence` set to `sent`."""
    from mvp import eval_claims as EC
    lib = h.audit_lib_for(unlock)
    rows = []
    if marked:
        rows += EC.audit_ledger(lib, EC.cited_cells(marked), results, calls, question, TODAY)
    env = results.get(rid) if rid else None
    if sent and env is not None and "sheet" in env and env.get("tool") not in ("find", "search", "learned"):
        ctx, _w = EC.brain_ctx(lib, env, calls.get(rid), question, TODAY)
        F = EC.Findings("text", env.get("tool"))
        EC.TextAudit(ctx, F).run(sent)
        rows += [dict(r, audit="text:" + r["audit"]) for r in F.rows]
    return [dict(r, sentence=sent) for r in rows]


def audit_code_lead(h, results, calls, unlock, code_lead, question):
    """The auditor on a code lead (brain/fallback.py): a template through its marker form, a code form as text."""
    from mvp import eval_claims as EC
    lib = h.audit_lib_for(unlock)
    env = results.get(code_lead["rid"])
    marked = None
    if code_lead["how"] == "template":
        from mvp.brain import fallback as FB, verify as V
        forms = [x for x in FB.templates(V.Ledger(results).get(code_lead["rid"]))
                 if V.strip_markers(x) == code_lead["lead"]]
        marked = forms[0] if forms else None
    rows = EC.audit_lead(lib, env, code_lead["lead"], marked, call=calls.get(code_lead["rid"]), question=question,
                         today=TODAY)
    return [dict(r, sentence=code_lead["lead"]) for r in rows]


def _g2_again(h, rec, chains, path=None):
    """G2 of a saved record, every reading of its message replayed on its own hand chain (conversation records in
    message order). The set is the record's own (`set`, brain_plans.jsonl when absent); `path` overrides its file."""
    set_name = rec.get("set") or "plans"
    key = "_set:" + set_name
    if key not in chains:
        chains[key] = {p["id"]: p for p in load_jsonl(path or SETS[set_name])}
    p = chains[key][rec["id"]]
    st = chains.get(rec["id"])
    if st is None:
        st = {"screen": "", "last": None}
        if p.get("before"):
            b = run_message(h, {"n": -1, "text": p["before"]["message"], "rounds": p["before"]["rounds"]}, audit=False)
            st = {"screen": b["lead"] or "", "last": b["_window"]}
        chains[rec["id"]] = st
    m = next(x for x in p["messages"] if x["n"] == rec["n"])
    hand, readings, _windows, _errors = hand_readings(h, m, st["screen"], st["last"])
    if hand is not None:
        st["screen"], st["last"] = hand["lead"] or st["screen"], hand["_window"] or st["last"]
    return g2_of(readings, model_keys(rec))


def run_records(run_dir):
    """The message records of a run folder, in conversation and message order (summary files left out)."""
    import glob
    files = [f for f in glob.glob(os.path.join(run_dir, "*.json")) if not os.path.basename(f).startswith("summary")]
    files.sort(key=lambda f: (os.path.basename(f).split(".")[0], int(os.path.basename(f).split(".")[1])))
    out = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            out.append((f, json.load(fh)))
    return out


def reaudit(a, h=None):
    """Offline: the auditor's hints and G2 again over a saved run folder (the envelopes are in each record), and
    summary.json rewritten; the first summary is kept as summary.first.json. No model call. The hand reading's marks
    (summary `reading`) and the hand recount (`G1_false_sent`) are carried over. `h`: a harness already built (tests)."""
    h = h or Harness.scratch()
    recs = []
    chains = {}
    set_file = set_file_of(a.run, getattr(a, "set_file", None))
    for f, rec in run_records(a.run):
        results = {c["rid"]: c["result"] for c in rec["calls"] if c.get("rid")}
        bad, checked = audit_sent(h, results, h.turn(rec["message"]).unlock, rec, rec["message"])
        rec["audit"] = {"checked": checked, "findings": bad}
        rec["g2"] = _g2_again(h, rec, chains, path=set_file)
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(rec, fh, indent=1, default=str, ensure_ascii=False)
        recs.append(rec)
    sp = os.path.join(a.run, "summary.json")
    old = {}
    if os.path.exists(sp):
        with open(sp, encoding="utf-8") as fh:
            old = json.load(fh)
        if not os.path.exists(os.path.join(a.run, "summary.first.json")):
            with open(os.path.join(a.run, "summary.first.json"), "w", encoding="utf-8") as fh:
                json.dump(old, fh, indent=1, default=str, ensure_ascii=False)
    s = summarize(recs, old.get("settings"))
    for k in ("ledger",):
        if k in old:
            s[k] = old[k]
    if (old.get("reading") or {}).get("by_message"):
        s["reading"] = old["reading"]
        s["G1_false_sent"] = old.get("G1_false_sent") or s["G1_false_sent"]
    with open(sp, "w", encoding="utf-8") as fh:
        json.dump(s, fh, indent=1, default=str, ensure_ascii=False)
    print(json.dumps({k: s["auditor_hints"][k] for k in ("messages_with_hints", "hints")}, indent=1, default=str))
    print(json.dumps({k: v for k, v in s["G2_understood"].items() if not isinstance(v, (dict, list))}, indent=1))
    return 0


def dropped_of(rec):
    """Every sentence the model wrote that did not go out: where, the text (markers in), reasons, the true values."""
    out = []
    for k, v in enumerate(rec["verdicts"]):
        for o in v["outcomes"]:
            if not o["kept"]:
                out.append({"form": k + 1, "where": o["where"], "index": o["index"], "text": o["text"],
                            "reasons": o["reasons"], "details": o["details"], "cells": o["cells"]})
    return out


def live_conversation(h, provider, p, core_conv, out_dir=None, max_usd=None, log=print, set_name="plans"):
    """Every plan message of one conversation through the live brain, in order: the screen and the last window come
    from the brain's own last answer; every acceptable reading (the hand plan of brain_plans.jsonl, or the fresh set's
    readings) runs beside it on its own hand chain, which goes on from the preferred reading (G2 compares them)."""
    from mvp.brain import loop as BL
    from mvp.tests.fakes.fake_brain import FakeEngine, fake_learned
    screen = {"now": NOW_WORDS}
    last = None
    hscreen, hlast = "", None
    if p.get("before"):
        b = run_message(h, {"n": -1, "text": p["before"]["message"], "rounds": p["before"]["rounds"]}, audit=False)
        hscreen, hlast = b["lead"] or "", b["_window"]
        last = b["_window"]
        plan = [{"rid": c["rid"], "tool": c["tool"], "args": c["args"],
                 "window_said": ((b["_results"].get(c["rid"]) or {}).get("meta") or {}).get("window_said"),
                 "filters_said": ((b["_results"].get(c["rid"]) or {}).get("meta") or {}).get("filters_said")}
                for c in b["calls"] if c.get("rid")]
        screen = {"now": NOW_WORDS, "last_answer": {"minutes_ago": 1, "plan": plan, "scope_line": None}}
    outs = []
    for m in p["messages"]:
        if m["tier"] != "plan":
            continue
        if max_usd is not None and provider.spent >= max_usd:
            outs.append({"id": p["id"], "n": m["n"], "key": f"{p['id']}.{m['n']}", "set": set_name,
                         "message": m["text"], "skipped": "budget"})
            continue
        hand, readings, rwindows, rerrors = hand_readings(h, m, hscreen, hlast)
        if hand is not None:
            hscreen, hlast = hand["lead"] or hscreen, hand["_window"] or hlast
        t = h.turn(m["text"], screen="", last_window=last, search=FakeEngine(), learned=fake_learned)
        rec = BL.run_turn(provider, t, m["text"], screen)
        g2 = g2_of(readings, model_keys(rec))
        bad, checked = audit_sent(h, t.results, t.unlock, rec, m["text"])
        rec.update(id=p["id"], n=m["n"], key=f"{p['id']}.{m['n']}", set=set_name, half=half_of(p["id"], set_name),
                   g2=g2, hand_plan=[{"tool": c["tool"], "args": c["args"]} for c in (hand or {}).get("calls", [])],
                   reading_window_failed=rwindows, reading_errors=rerrors,
                   audit={"checked": checked, "findings": bad}, dropped=dropped_of(rec))
        screen = BL.screen_after(rec, NOW_WORDS)
        last = BL.last_window(t, rec) or last
        if out_dir:
            with open(os.path.join(out_dir, f"{p['id']}.{m['n']}.json"), "w", encoding="utf-8") as f:
                json.dump(rec, f, indent=1, default=str, ensure_ascii=False)
        log(f"{rec['key']}: {rec['lead_source']} g2={g2['verdict']} {rec['seconds']}s ${rec['cost_usd']:.4f} "
            f"sent {rec['sentences']['kept_sent']}/{rec['sentences']['written']} auditor hints {len(bad)}")
        outs.append(rec)
    return outs


def _pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo), 2)


def summarize(recs, settings=None):
    """summary.json of a run: the gate figures G2 to G6, every dropped sentence, lead_source counts. G1 (false or
    wrongly based sentences sent) needs a hand recount and stays empty until one is filled in (`marks`); the auditor's
    findings are hints for that recount (`auditor_hints`), not a G1 figure (mvp22). The hand reading's marks (`reading`)
    start empty. Definitions are written into the summary itself."""
    done = [r for r in recs if not r.get("skipped")]
    n = len(done)
    src = {}
    for r in done:
        src[r["lead_source"]] = src.get(r["lead_source"], 0) + 1
    g2 = {}
    for r in done:
        g2[r["g2"]["verdict"]] = g2.get(r["g2"]["verdict"], 0) + 1
    planned = sum(v for k, v in g2.items() if k != "no_hand_plan")
    strict = {}
    for r in done:
        v = r["g2"].get("verdict_strict", r["g2"]["verdict"])
        strict[v] = strict.get(v, 0) + 1
    planned_strict = sum(v for k, v in strict.items() if k != "no_hand_plan")
    written = sum(r["sentences"]["written"] for r in done)
    first = sum(r["sentences"]["kept_first_pass"] for r in done)
    sent = sum(r["sentences"]["kept_sent"] for r in done)
    secs = [r["seconds"] for r in done]
    costs = [r["cost_usd"] for r in done]
    own = src.get("model", 0) + src.get("model_after_repair", 0)
    findings = {r["key"]: r["audit"]["findings"] for r in done if r["audit"]["findings"]}
    req = [q for r in done for q in r["requests"]]
    s = {
        "messages": n, "skipped": [f"{r['id']}.{r['n']}" for r in recs if r.get("skipped")],
        "settings": settings or {},
        "lead_source": src,
        "G2_understood": {"understood": g2.get("understood", 0), "other_plan": g2.get("other_plan", 0),
                          "differs": g2.get("differs", 0), "no_hand_plan": g2.get("no_hand_plan", 0),
                          "share": round(g2.get("understood", 0) / planned, 4) if planned else None, "bar": 0.90,
                          # mvp20 tune: the gate's own four fields (window, base, scope, order): "other_plan" (same
                          # four, another tool or ranking) counts as understood here; "share" above stays the strict
                          # figure (tool and ranking too), both reported
                          "share_gate_fields": round((g2.get("understood", 0) + g2.get("other_plan", 0)) / planned, 4)
                          if planned else None,
                          # mvp22: the scorer as it was (the preferred reading only, every call, exact equality)
                          "share_strict_v1": round(strict.get("understood", 0) / planned_strict, 4)
                          if planned_strict else None,
                          "understood_strict_v1": strict.get("understood", 0),
                          "rules": list(RULES),
                          "by_reading": _counts(str(r["g2"].get("reading")) for r in done
                                                if r["g2"]["verdict"] == "understood"),
                          "later_rounds_missed": [r["key"] for r in done if r["g2"].get("later_rounds_missed")],
                          "reading_window_failed": {r["key"]: r["reading_window_failed"] for r in done
                                                    if r.get("reading_window_failed")},
                          "reading_errors": {r["key"]: r["reading_errors"] for r in done if r.get("reading_errors")},
                          "no_hand_plan_list": [r["key"] for r in done if r["g2"]["verdict"] == "no_hand_plan"],
                          "other_plan_list": [r["key"] for r in done if r["g2"]["verdict"] == "other_plan"],
                          "differs_list": {r["key"]: r["g2"]["diffs"] for r in done
                                           if r["g2"]["verdict"] == "differs"}},
        "G3_own_lead": {"own": own, "of": n, "share": round(own / n, 4) if n else None, "bar": 0.85,
                        "not_own": {r["key"]: {"lead_source": r["lead_source"], "error": r.get("error"),
                                               "events": r.get("events")} for r in done
                                    if r["lead_source"] not in ("model", "model_after_repair")}},
        "G4_sentences": {"written": written, "kept_first_pass": first, "kept_sent": sent,
                         "missing_first_pass": round(1 - first / written, 4) if written else None,
                         "missing_after_repair": round(1 - sent / written, 4) if written else None, "bar": 0.15},
        "G5_seconds": {"median": _pct(secs, 0.5), "p90": _pct(secs, 0.9), "max": max(secs) if secs else None,
                       "bar_median": 6.0, "bar_p90": 10.0,
                       "retries": sum(q.get("retries", 0) for q in req)},
        "G6_cost": {"mean_cents": round(100 * sum(costs) / n, 4) if n else None, "total_usd": round(sum(costs), 6),
                    "bar_mean_cents": 0.5},
        "G1_false_sent": {"false_or_wrongly_based": None, "sent_sentences": sum(_sent_count(r) for r in done),
                          "recounted_messages": 0, "of": n, "bar": 0,
                          "how": "NEEDS A HAND RECOUNT: every sent sentence recounted from the rows of "
                                 "tests/brain_library.py, its framing words too (window, base, scope, direction, "
                                 "'only'/'all', rank across levels). Fill it from a marks file (false=N on each "
                                 "message's mark line): " + MARKS_CMD + ". Until every message is recounted this "
                                 "line stays empty. The auditor's hints below are not this figure."},
        "auditor_hints": {"messages_with_hints": len(findings), "hints": sum(len(v) for v in findings.values()),
                          "by_message": findings,
                          "note": "eval_claims' own reading of the sent sentences, for a hand recount to look at "
                                  "first; NOT a count of false sentences. Measured after its two fixes of mvp22 on "
                                  "the brain slice's held-out half, recounted by hand: of the 110 sent sentences of "
                                  "the first look it flagged 1 of 5 false (by reading the wrong subject) and 2 of 105 "
                                  "true (lower-case 'shorts'); of every sentence the model wrote (first and repair "
                                  "forms) it flagged 2 of 11 false and 24 of 185 true (first look), 1 of 12 false and "
                                  "19 of 171 true (second look)."},
        "reading": empty_reading(n),
        "requests": {"count": len(req), "per_message_mean": round(len(req) / n, 3) if n else None,
                     "stop_reasons": _counts(q["stop_reason"] for q in req),
                     "input_tokens": sum(q["usage"]["input_tokens"] for q in req),
                     "output_tokens": sum(q["usage"]["output_tokens"] for q in req),
                     "cache_read_input_tokens": sum(q["usage"]["cache_read_input_tokens"] for q in req),
                     "cache_creation_input_tokens": sum(q["usage"]["cache_creation_input_tokens"] for q in req)},
        "repairs": sum(1 for r in done if r.get("repair_message")),
        "decomposition": _decomposition(done),
        "events": _counts(e for r in done for e in r.get("events") or []),
        "dropped": {r["key"]: r["dropped"] for r in done if r["dropped"]},
        "dropped_reasons": _counts(x for r in done for d in r["dropped"] for x in d["reasons"]),
        "definitions": {
            "G2": "per plan message, for the best of its acceptable readings (each run on its own hand chain): every "
                  "counting call of the reading's first round with one (later rounds are reported in "
                  "later_rounds_missed, not required) has a model call with the same tool, what it ranks by, window "
                  "days, base, scope (meta.filters_said) and order, under the rules of G2_rules; 'other_plan' = same "
                  "window, base, scope and order but another tool or ranking (for a human to judge, not counted); "
                  "share = understood / messages with a reading that ran (no_hand_plan_list: those left out). "
                  "A compare's window is both windows (the second read from previous.words). Any matching model "
                  "call earns the credit, even when the answer cites another call; extra calls do not count against "
                  "it",
            "G2_rules": "mvp22: understood = for SOME acceptable reading (the fresh set's readings; the one hand "
                        "plan of brain_plans.jsonl), every counting call of its first round with one has a model "
                        "call equal on tool, ranking, window, base, scope and order, where a total is in any "
                        "breakdown, a year is in a timeline by month, first_last's subject is an 'only' scope, and "
                        "extra filters that changed no count (the same non-empty result) do not change the scope. "
                        "share_strict_v1 is the figure of the scorer before mvp22",
            "G1": "false or wrongly based sentences sent, by a hand recount from the rows (the auditor is not a "
                  "source for it)",
            "reading": "the hand reader's marks by eval/brain_reading_rubric.md: good / acceptable / poor, says what "
                       "the numbers mean, answers the question asked, carries an offer worth taking",
            "G3": "answers whose lead is the model's own (lead_source model or model_after_repair) / every plan "
                  "message attempted (API failures and turns with no form count as not own)",
            "G4": "micro-averaged: written = sentences of the model's FIRST form (lead sentences + points); "
                  "kept_first_pass = of those, kept by the first verdict; kept_sent = the model's sentences in the "
                  "answer that went out (the repaired form's kept sentences, or the passed points under a code lead), "
                  "capped at written",
            "G5": "wall seconds of the turn (all requests, tool runs, verification, repair, back-off), at the run's "
                  "parallelism", "G6": "ledger cost of every request of the message, mean in cents"}}
    return s


def _sent_count(rec):
    a = rec.get("answer") or {}
    return (1 if a.get("lead") else 0) + len(a.get("points") or [])


MARKS_CMD = "python3 -m mvp.eval_brain marks --run DIR --marks FILE"
READ_CMD = "python3 -m mvp.eval_brain read --run DIR"
RUBRIC = "experiments/mvp/eval/brain_reading_rubric.md"
GRADES = ("good", "acceptable", "poor")
YES_NO = ("means", "answers", "offer")


def empty_reading(n):
    """The hand reading's fields of summary.json, empty until a marks file fills them."""
    return {"rubric": RUBRIC, "sheet": READ_CMD, "fill": MARKS_CMD, "marked": 0, "of": n,
            "grade": {g: None for g in GRADES},
            "says_what_the_numbers_mean": None, "answers_the_question": None, "carries_an_offer": None,
            "unmarked": [], "by_message": {}}


def _decomposition(done):
    """What the measured G3 and G4 mix: repairs spent on a form that did not validate (an invented key), and the first
    pass read on the first form that DID validate (a decomposition, not a gate figure)."""
    def sents(v):
        return [o for o in (v or {}).get("outcomes", []) if o["where"] in ("lead", "point")]
    key_repairs = [r["key"] for r in done if r.get("verdicts") and r["verdicts"][0].get("form_error")]
    w = k = 0
    for r in done:
        v = next((v for v in r.get("verdicts") or [] if not v.get("form_error")), None)
        w += len(sents(v))
        k += sum(1 for o in sents(v) if o["kept"])
    not_own = [r["key"] for r in done if r["lead_source"] not in ("model", "model_after_repair")]
    return {"repairs_on_a_form_error": len(key_repairs), "repairs_on_a_form_error_list": key_repairs,
            "not_own_whose_repair_went_on_a_form_error": sorted(set(key_repairs) & set(not_own)),
            "first_valid_form_written": w, "first_valid_form_kept": k,
            "first_valid_form_missing": round(1 - k / w, 4) if w else None}


def _counts(it):
    out = {}
    for x in it:
        out[x] = out.get(x, 0) + 1
    return out


RUN_NO_KEY = ("eval_brain run calls claude-haiku-5-5 live: set DIGESTER_ANTHROPIC_API_KEY (or ANTHROPIC_API_KEY) and "
              "MVP_LEDGER_HOME first; nothing was sent.")


def run_live(a):
    """The `run` mode: the made-up library as the plans mode builds it, every plan message of the half live (the set:
    brain_plans.jsonl, halves tune / heldout / all, or the fresh set, halves a / b / all)."""
    set_path = getattr(a, "set_file", None) or SETS[a.set]
    if a.half not in HALVES[a.set]:
        print(f"--half {a.half} is not a half of the {a.set} set ({', '.join(HALVES[a.set])}); nothing was sent.",
              file=sys.stderr)
        return 2
    if not os.path.exists(set_path):
        print(f"no set file at {set_path}; nothing was sent.", file=sys.stderr)
        return 2
    if not (os.environ.get("DIGESTER_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")) or \
            not os.environ.get("MVP_LEDGER_HOME"):
        print(RUN_NO_KEY, file=sys.stderr)
        return 2
    ledger_home = os.path.abspath(os.environ["MVP_LEDGER_HOME"])
    base = tempfile.mkdtemp(prefix="eval_brain_run_")
    h = Harness.scratch(base, keep_ledger=True)
    from mvp import llm
    from mvp.brain import loop as BL, provider as P
    if os.path.abspath(llm.ai.LEDGER).startswith(os.path.abspath(base)) or \
            os.path.dirname(os.path.abspath(llm.ai.LEDGER)) != ledger_home:
        print(f"the ledger is not MVP_LEDGER_HOME's: {llm.ai.LEDGER}", file=sys.stderr)
        return 2
    os.makedirs(a.out, exist_ok=True)
    rows_before = _ledger_rows(llm.ai.LEDGER)
    prov = P.AnthropicProvider(prompt_version=BL.PROMPT_VERSION, loose=tuple(x for x in a.loose.split(",") if x))
    sets = run_set(a.half, set(x for x in a.ids.split(",") if x) or None, a.limit, set_name=a.set, path=set_path)
    h.audit_lib_for(None)
    recs = []
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max(1, min(4, a.parallel))) as ex:
        futs = [ex.submit(live_conversation, h, prov, p, c, a.out, a.max_usd, set_name=a.set) for p, c in sets]
        for f in futs:
            recs += f.result()
    settings = dict(prov.settings(), prompt_version=BL.PROMPT_VERSION, rounds=BL.ROUNDS, soft_s=BL.SOFT_S,
                    deep_s=BL.DEEP_S, hard_s=BL.HARD_S, parallel=a.parallel, half=a.half, set=a.set,
                    set_file=os.path.relpath(set_path, HERE),
                    tool_result_shape="rid, tool, meta and the sheet's keys at the top (loop.present)",
                    max_usd=a.max_usd, spent_usd=round(prov.spent, 6), requests=prov.requests)
    s = summarize(recs, settings)
    rows_after = _ledger_rows(llm.ai.LEDGER)
    new = [r for r in rows_after[len(rows_before):] if r.get("purpose") == P.PURPOSE]
    s["ledger"] = {"rows_added": len(rows_after) - len(rows_before), "brain_eval_rows": len(new),
                   "brain_eval_usd": round(sum(r.get("cost_usd") or 0 for r in new), 6),
                   "matches_requests": len(new) == prov.requests}
    with open(os.path.join(a.out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1, default=str, ensure_ascii=False)
    short = {k: s[k] for k in ("messages", "lead_source", "repairs", "events", "dropped_reasons", "ledger")}
    for k in ("G2_understood", "G3_own_lead", "G4_sentences", "G5_seconds", "G6_cost"):
        short[k] = {x: y for x, y in s[k].items() if not isinstance(y, (dict, list))}
    short["auditor_hints"] = {k: s["auditor_hints"][k] for k in ("messages_with_hints", "hints")}
    short["G1_false_sent"] = s["G1_false_sent"]["how"]
    print(json.dumps(short, indent=1, default=str))
    return 0


def _ledger_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def count_prefix(a):
    """count_tokens (free) on the real prefix (system text + tool schemas) and on a typical turn."""
    if not (os.environ.get("DIGESTER_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")):
        print(RUN_NO_KEY, file=sys.stderr)
        return 2
    h = Harness.scratch(keep_ledger=True)
    from mvp.brain import loop as BL, provider as P, tools as TL
    prov = P.AnthropicProvider(prompt_version=BL.PROMPT_VERSION, loose=tuple(x for x in a.loose.split(",") if x))
    system, tools = BL.system_text(), BL.tool_list()
    out = {}
    one = [{"role": "user", "content": "x"}]
    out["prefix_plus_one_token_message"] = prov.count_tokens(system, tools, one)
    out["tools_only"] = prov.count_tokens("x", tools, one)
    out["system_only"] = prov.count_tokens(system, [], one)
    msg = "which channels did I watch the most in October?"
    t = h.turn(msg)
    env = TL.call(t, "breakdown", {"by": "channel", "window": {"words": "in October"}})
    u = {"type": "tool_use", "id": "toolu_count01", "name": "breakdown",
         "input": {"by": "channel", "window": {"words": "in October", "preset": None, "same_as": None}}}
    turn_msgs = [{"role": "user", "content": BL.user_text(msg, {"now": NOW_WORDS})},
                 {"role": "assistant", "content": [u]},
                 {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_count01",
                                               "content": BL.present(env)}]}]
    out["typical_round2_request"] = prov.count_tokens(system, tools, turn_msgs)
    out["user_turn_only"] = prov.count_tokens(system, tools, turn_msgs[:1]) - out["prefix_plus_one_token_message"]
    out["one_result"] = out["typical_round2_request"] - out["prefix_plus_one_token_message"] - out["user_turn_only"]
    out["result_chars"] = len(BL.present(env))
    print(json.dumps(out, indent=1))
    if a.out:
        os.makedirs(a.out, exist_ok=True)
        with open(os.path.join(a.out, "count_tokens.json"), "w") as f:
            json.dump(out, f, indent=1)
    return 0


# ================================================================ the hand reading (mvp22)
def _texts_of(conv):
    """[(n, text, tier)] of a conversation, from brain_core.jsonl (a list of strings) or a set line (dicts)."""
    out = []
    for k, m in enumerate(conv.get("messages") or []):
        if isinstance(m, str):
            out.append((k, m, None))
        else:
            out.append((m.get("n", k), m.get("text", ""), m.get("tier")))
    return out


def set_file_of(run_dir, given=None):
    """The set file of a run: the one given, else the one its summary.json settings name (relative to this folder),
    else None (the set's default file)."""
    if given:
        return given
    sp = os.path.join(run_dir, "summary.json")
    if os.path.exists(sp):
        with open(sp, encoding="utf-8") as f:
            rel = ((json.load(f).get("settings") or {}).get("set_file"))
        if rel and os.path.exists(os.path.join(HERE, rel)):
            return os.path.join(HERE, rel)
    return None


def reading_sheet(run_dir, set_file=None):
    """One plain-text file for a hand reader: every message of the run in conversation order, the earlier messages of
    its conversation (with the first line of what was sent to each), and the answer EXACTLY as sent (answer.text,
    verbatim), then its parts (lead and whose, points, scope line, private line, offers) and an empty mark line
    (eval/brain_reading_rubric.md). Messages not run (budget) and failed turns are listed too."""
    recs = [r for _f, r in run_records(run_dir)]
    set_name = next((r.get("set") for r in recs if r.get("set")), "plans")
    set_file = set_file_of(run_dir, set_file)
    convs, before, tiers = {}, {}, {}
    if set_name == "plans":
        convs = {c["id"]: c for c in load_jsonl(CORE)}
        plan_lines = load_jsonl(set_file or PLANS)
        before = {p["id"]: p["before"]["message"] for p in plan_lines if p.get("before")}
        tiers = {(p["id"], m["n"]): m["tier"] for p in plan_lines for m in p["messages"]}
    else:
        for c in load_jsonl(set_file or SETS[set_name]):
            convs[c["id"]] = c
            if c.get("before"):
                before[c["id"]] = c["before"].get("message")
    sent_by = {r.get("key") or f"{r['id']}.{r['n']}": r for r in recs}
    n_done = sum(1 for r in recs if not r.get("skipped"))
    out = [(f"Reading sheet of {os.path.basename(os.path.normpath(run_dir))}: {n_done} answers "
            f"({sum(1 for r in recs if r.get('skipped'))} not run). Set: {set_name}."),
           (f"Read by {RUBRIC}. Fill each 'mark:' line, then: {MARKS_CMD.replace('DIR', run_dir)} "
            "(FILE: this sheet)."),
           "mark line: grade=good|acceptable|poor means=y|n answers=y|n offer=y|n false=N note=free words",
           ("  false=N: how many sent sentences a recount from the rows finds false or wrongly based (leave it empty "
            "when you did not recount)"),
           ""]
    for r in recs:
        key = r.get("key") or f"{r['id']}.{r['n']}"
        conv = convs.get(r["id"]) or {}
        head = f"==== {key} | conversation {r['id']}, message {r['n']}"
        if r.get("skipped"):
            out += [head + f" | NOT RUN ({r['skipped']})", f"message: {r.get('message', '')}", ""]
            continue
        out.append(head + f" | lead: {r.get('lead_source')}" + (f" | error: {r['error']}" if r.get("error") else ""))
        earlier = [(n, t, tier or tiers.get((r["id"], n))) for n, t, tier in _texts_of(conv) if n < r["n"]]
        if before.get(r["id"]) or earlier:
            out.append("before:")
            if before.get(r["id"]):
                out.append(f"  (set up) you: {before[r['id']]}")
            for n, t, tier in earlier:
                out.append(f"  [{n}] you: {t}")
                prev = sent_by.get(f"{r['id']}.{n}")
                if prev is not None and not prev.get("skipped"):
                    first = ((prev.get("answer") or {}).get("text") or "").split("\n")[0]
                    out.append(f"      sent: {first}")
                elif tier and tier != "plan":
                    out.append(f"      (not run here: {tier})")
        out.append(f"message: {r.get('message', '')}")
        a = r.get("answer") or {}
        out.append("sent:")
        out += ["  | " + line for line in (a.get("text") or "(nothing was sent)").split("\n")]
        offers = " · ".join(o.get("label") or "?" for o in a.get("offers") or []) or "none"
        out.append(f"parts: lead ({r.get('lead_source')}) · points: {len(a.get('points') or [])} · scope line: "
                   f"{'yes' if a.get('scope_line') else 'no'} · private line: {'yes' if a.get('private_line') else 'no'}"
                   f" · offers: {offers}")
        m = next((x for x in conv.get("messages") or [] if isinstance(x, dict) and x.get("n") == r["n"]), None)
        good = (m or {}).get("good") or {}
        if good:
            out.append(f"the set's note: means: {good.get('means', '')} | offer: {good.get('offer', '')}")
        out += ["mark: grade= means= answers= offer= false= note=", ""]
    return "\n".join(out) + "\n"


_MARK_FIELDS = ("grade", "means", "answers", "offer", "false")


def parse_marks(text):
    """{key: {grade, means, answers, offer, false, note}} of a filled reading sheet (the '==== KEY' headers and their
    'mark:' lines). Empty fields are None; a value out of the rubric raises ValueError naming the message."""
    out, key = {}, None
    for line in text.splitlines():
        m = re.match(r"^==== (\S+)", line)
        if m:
            key = m.group(1)
            continue
        m = re.match(r"^mark:(.*)$", line.strip())
        if not m or key is None:
            continue
        body = m.group(1)
        note = ""
        if "note=" in body:
            body, note = body.split("note=", 1)
        vals = dict(re.findall(r"(\w+)=(\S*)", body))
        row = {"note": note.strip()}
        for f in _MARK_FIELDS:
            v = (vals.get(f) or "").strip().lower() or None
            if v is not None:
                if f == "grade" and v not in GRADES:
                    raise ValueError(f"{key}: grade={v} (good, acceptable or poor)")
                if f in YES_NO:
                    if v not in ("y", "n", "yes", "no"):
                        raise ValueError(f"{key}: {f}={v} (y or n)")
                    v = v.startswith("y")
                if f == "false":
                    if not v.isdigit():
                        raise ValueError(f"{key}: false={v} (a count)")
                    v = int(v)
            row[f] = v
        out[key] = row
    return out


def reading_of(marks, keys):
    """summary.json's `reading` and the hand recount's G1 from the marks of the run's answers (`keys`)."""
    r = empty_reading(len(keys))
    by = {k: marks[k] for k in keys if k in marks}
    graded = [k for k in keys if (by.get(k) or {}).get("grade")]
    r["marked"] = len(graded)
    r["unmarked"] = [k for k in keys if k not in graded]
    r["by_message"] = by
    if graded:
        r["grade"] = {g: sum(1 for k in graded if by[k]["grade"] == g) for g in GRADES}
        for f, name in (("means", "says_what_the_numbers_mean"), ("answers", "answers_the_question"),
                        ("offer", "carries_an_offer")):
            told = [k for k in graded if by[k].get(f) is not None]
            yes = sum(1 for k in told if by[k][f])
            r[name] = {"yes": yes, "of": len(told), "share": round(yes / len(told), 4) if told else None}
    rec = [k for k in keys if (by.get(k) or {}).get("false") is not None]
    g1 = {"recounted_messages": len(rec), "of": len(keys),
          "false_or_wrongly_based": sum(by[k]["false"] for k in rec) if rec and len(rec) == len(keys) else None,
          "false_so_far": sum(by[k]["false"] for k in rec) if rec else None,
          "messages_with_false": sorted(k for k in rec if by[k]["false"])}
    return r, g1


def fill_marks(run_dir, marks_path):
    """The `marks` mode: a filled reading sheet into the run's summary.json (`reading`, and `G1_false_sent` once every
    answer carries false=N). The rest of the summary is kept as it is."""
    with open(marks_path, encoding="utf-8") as f:
        marks = parse_marks(f.read())
    recs = [r for _f, r in run_records(run_dir)]
    keys = [r.get("key") or f"{r['id']}.{r['n']}" for r in recs if not r.get("skipped")]
    sp = os.path.join(run_dir, "summary.json")
    if os.path.exists(sp):
        with open(sp, encoding="utf-8") as f:
            s = json.load(f)
    else:
        s = summarize(recs)
    reading, g1 = reading_of(marks, keys)
    s["reading"] = reading
    base = s.get("G1_false_sent") or {}
    s["G1_false_sent"] = dict(base, **g1)
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1, default=str, ensure_ascii=False)
    return s


# ================================================================ the command line


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m mvp.eval_brain")
    sub = ap.add_subparsers(dest="mode", required=True)
    p1 = sub.add_parser("planted")
    p1.add_argument("--show", default="", choices=("", "dropped_true", "kept_false", "wrong_reason"))
    p2 = sub.add_parser("plans")
    p2.add_argument("--json", default=None, help="write the full report here (keep it outside git)")
    p2.add_argument("--only", default="", help="conversation ids, comma separated")
    sub.add_parser("insight")
    p4 = sub.add_parser("run", help="live: claude-haiku-5-5 through the brain loop on the plan messages of a half")
    p4.add_argument("--set", choices=tuple(SETS), default="plans",
                    help="plans: evalset/brain_plans.jsonl; fresh: evalset/brain_fresh.jsonl")
    p4.add_argument("--set-file", default=None, help="another file of the set's shape (tests)")
    p4.add_argument("--half", choices=("tune", "heldout", "all", "a", "b"), required=True,
                    help="plans: tune, heldout or all; fresh: a, b or all")
    p4.add_argument("--limit", type=int, default=None, help="stop once this many plan messages are taken")
    p4.add_argument("--ids", default="", help="conversation ids, comma separated")
    p4.add_argument("--out", required=True, help="a folder outside git: one JSON per message and summary.json")
    p4.add_argument("--parallel", type=int, default=2, help="conversations at once (at most 4)")
    p4.add_argument("--max-usd", type=float, default=1.50, help="no new message once the run spent this much")
    p4.add_argument("--loose", default="give_answer", help="tools sent without strict (comma separated)")
    p6 = sub.add_parser("audit", help="offline: the auditor's hints and G2 again over a saved run folder, "
                                      "summary.json rewritten")
    p6.add_argument("--run", required=True)
    p6.add_argument("--set-file", default=None, help="the set file, when not the one the records name")
    p7 = sub.add_parser("read", help="offline: one plain-text reading sheet of a run (every message, every answer "
                                     "as sent, a mark line each)")
    p7.add_argument("--run", required=True)
    p7.add_argument("--out", default=None, help="default: <run>/reading_sheet.txt")
    p7.add_argument("--set-file", default=None)
    p8 = sub.add_parser("marks", help="offline: the hand reader's marks (a filled reading sheet) into summary.json")
    p8.add_argument("--run", required=True)
    p8.add_argument("--marks", required=True)
    p5 = sub.add_parser("count", help="count_tokens (free) on the real prefix and a typical turn")
    p5.add_argument("--out", default=None)
    p5.add_argument("--loose", default="give_answer")
    a = ap.parse_args(argv)
    if a.mode == "run":
        return run_live(a)
    if a.mode == "count":
        return count_prefix(a)
    if a.mode == "audit":
        return reaudit(a)
    if a.mode == "read":
        out = a.out or os.path.join(a.run, "reading_sheet.txt")
        with open(out, "w", encoding="utf-8") as f:
            f.write(reading_sheet(a.run, set_file=a.set_file))
        print(out)
        return 0
    if a.mode == "marks":
        s = fill_marks(a.run, a.marks)
        print(json.dumps({k: v for k, v in s["reading"].items() if k != "by_message"}, indent=1))
        print(json.dumps({k: v for k, v in s["G1_false_sent"].items() if k != "how"}, indent=1))
        return 0
    if a.mode == "planted":
        s = planted()
        by = s.pop("by_class")
        print(json.dumps(s, indent=1))
        print("class: false dropped (with an expected reason) / true kept")
        for cls in sorted(by):
            b = by[cls]
            print(f"  {cls}: {b['dropped']}/{b['false']} ({b['dropped_expected']}) / {b['kept']}/{b['true']}")
        return 0 if all(s["bar"].values()) else 1
    h = Harness.scratch()
    if a.mode == "insight":
        s = insight(h)
        print(json.dumps(s, indent=1))
        return 0
    s, out = plans(h, set(x for x in a.only.split(",") if x) or None)
    if a.json:
        def strip(o):
            if isinstance(o, dict):
                return {k: strip(v) for k, v in o.items() if not k.startswith("_")}
            if isinstance(o, list):
                return [strip(v) for v in o]
            return o
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"summary": s, "conversations": strip(out)}, f, indent=1, default=str)
    short = {k: v for k, v in s.items() if k not in ("not_recounted", "findings")}
    short["not_recounted"] = sorted(s["not_recounted"].items(), key=lambda x: -x[1])[:12]
    short["findings"] = {"number": s["findings"]["number"], "window": s["findings"]["window"],
                         "shape": {"count": len(s["findings"]["shape"]),
                                   "kinds": sorted({f["kind"] for f in s["findings"]["shape"]}),
                                   "results": sorted({f["at"] for f in s["findings"]["shape"]})}}
    print(json.dumps(short, indent=1, default=str))
    return 0 if not s["recount_not_true"] and not s["expect_failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
