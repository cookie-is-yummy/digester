"""PROTOTYPE ONLY - the brain's offline eval, step 1 (design/brain_v1/SPEC.md 12.2 step 1, 12.4, 4.8).

    python3 -m mvp.eval_brain planted [--show dropped_true|kept_false|wrong_reason]   (from experiments/)
    python3 -m mvp.eval_brain plans [--json OUT] [--only A01,B07]
    python3 -m mvp.eval_brain insight
    python3 -m mvp.eval_brain run ...        step 2: refuses here (no model call in step 1)

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

Offline: no model call, no network. The library is built in a temporary folder (MVP_HOME, MVP_LEDGER_HOME,
MVP_INBOX and MVP_DERIVED_HOME point inside it before any of the bot's modules is imported); nothing is read from or
written to data/.
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
def scratch_env(base):
    """Point every home of the bot inside `base` (call before importing any of the bot's modules)."""
    for k, sub in (("MVP_HOME", "home"), ("MVP_LEDGER_HOME", "ledger"), ("MVP_INBOX", "inbox"),
                   ("MVP_DERIVED_HOME", "derived")):
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
    def scratch(cls, base=None):
        """A harness on a library built in a temporary folder (the command line's)."""
        base = base or tempfile.mkdtemp(prefix="eval_brain_")
        scratch_env(base)
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
    marker_form = None
    if cl["how"] == "template":
        res = V.Ledger(t.results).get(cl["rid"])
        forms = [x for x in FB.templates(res) if V.strip_markers(x) == cl["lead"]]
        marker_form = forms[0] if forms else None
        rec["lead_ok"] = bool(marker_form) and V.check_answer({"lead": marker_form, "points": []}, t.results,
                                                               vt).lead_ok
    elif cl["how"] == "code_form":
        rec["lead_ok"] = True    # code_form's answer passed today's checks inside fallback (insight._check, gate)
    else:
        rec["lead_ok"] = cl["lead"] == FB.PLAIN
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
                s["lead_not_ok"].append(where)
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
    for r in sc["rows"]:
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
    s["kept_false"] = [r["id"] for r in sc["rows"] if r["expect"] == "dropped" and r["kept"]]
    s["dropped_true"] = [r["id"] for r in sc["rows"] if r["expect"] == "kept" and not r["kept"]]
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


# ================================================================ the command line
RUN_REFUSED = ("eval_brain run is step 2: it calls a real model through the brain loop, and step 1 has no loop, no "
               "provider and no model call. Use `planted`, `plans` or `insight` (offline).")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m mvp.eval_brain")
    sub = ap.add_subparsers(dest="mode", required=True)
    p1 = sub.add_parser("planted")
    p1.add_argument("--show", default="", choices=("", "dropped_true", "kept_false", "wrong_reason"))
    p2 = sub.add_parser("plans")
    p2.add_argument("--json", default=None, help="write the full report here (keep it outside git)")
    p2.add_argument("--only", default="", help="conversation ids, comma separated")
    sub.add_parser("insight")
    sub.add_parser("run")    # SPEC 12.4's --set, --provider, --model, --out, --library: step 2
    a, extra = ap.parse_known_args(argv)
    if extra and a.mode != "run":
        ap.error("unrecognized arguments: " + " ".join(extra))
    if a.mode == "run":
        print(RUN_REFUSED, file=sys.stderr)
        return 2
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
