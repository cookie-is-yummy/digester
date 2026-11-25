"""The brain's offline eval, step 1 (design/brain_v1/SPEC.md 12.2 step 1, 12.4, 4.8): the eval set, the hand-written
plans, eval_brain's modes, the fake brain, and the auditor's recount of the tools' results (eval_claims.audit_results,
audit_ledger, audit_lead).

Offline: no model call, no network. The library is the made-up one of tests/brain_library.py (fixtures of
test_brain_tools). Every title, channel and theme is made up."""
import copy
import json
import os
import re
import sys
from datetime import date

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_brain_tools import (  # noqa: E402,F401  (fixtures)
    NOW, TODAY, brain, built, call, no_real_keys, person)

MVP = os.path.dirname(HERE)
CORE = os.path.join(MVP, "evalset", "brain_core.jsonl")
PLANS = os.path.join(MVP, "evalset", "brain_plans.jsonl")
DRAFT = os.path.join(MVP, "design", "brain_v1", "eval_messages.draft.jsonl")
# the plans whose results hold a number the auditor does not recount true today (each a finding of the report):
# B05 and C13 eras[].share is the mean of the yearly shares, not the era's share; G06 code_form's "mostly <area>
# (44%) and <area> (26%)"; I05 an Instagram photo post's length word "short"
KNOWN_NOT_TRUE = {"B05", "C13", "G06", "I05"}
# the code leads that fail the eval's reading (fallback findings): B10 the plain line with two checked points in hand
# (learned's template fails its own verifier); C06 and K03 code_form leads that start in lower case and name only
# the window before; C08 and F04 a last with no day (the template fails insight's date check)
KNOWN_LEAD_NOT_OK = {"B10.0", "C06.0", "K03.0", "C08.0", "F04.0"}


def rows(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


@pytest.fixture()
def harness(brain):
    from mvp import eval_brain as E
    return E.Harness(brain["bot"], str(brain["lib"]), os.environ["MVP_DERIVED_HOME"], handle=person(brain)["handle"],
                     now=NOW)


# ================================================================ the eval set
def test_the_eval_set_keeps_every_conversation_and_message_of_the_draft():
    core, draft = rows(CORE), rows(DRAFT)
    assert len(core) == 111 and sum(len(r["messages"]) for r in core) == 130
    assert [(r["id"], r["messages"], r["block"], r["step"]) for r in core] == \
        [(r["id"], r["messages"], r["block"], r["step"]) for r in draft]
    blob = json.dumps(core)
    assert "not run: confirm in step 1" not in blob
    fixed = [r for r in core if r.get("corrections")]
    assert len(fixed) == 15 and sum(len(r["corrections"]) for r in fixed) == 15
    for r in fixed:
        for c in r["corrections"]:
            assert c["now"] in r["good"] and c["was"] not in r["good"] and c["why"]


def test_the_corrected_lines_hold_what_the_run_shows():
    core = {r["id"]: r for r in rows(CORE)}
    good = lambda cid: " ".join(core[cid]["good"])  # noqa: E731
    assert "Frame Perfect" not in good("A06") and "Pan Theory leads with 32 of 70" in good("A06")
    assert "@wetpaper.ig" in good("A07") and "@wetpaper.ig" in good("A01")
    assert "nothing was rewatched" in good("C09")
    assert "last 90 days" in good("C14") and "12 October 2026" in good("D04")
    assert "Heart Notes, 50 videos" in good("I02")


# ================================================================ the plans
def test_every_conversation_has_a_plan_record_and_the_counts_fall_out():
    from mvp.brain import tools as TL
    core, plans = rows(CORE), rows(PLANS)
    assert [p["id"] for p in plans] == [r["id"] for r in core]
    st = {}
    tiers = {}
    for p, r in zip(plans, core):
        assert len(p["messages"]) == len(r["messages"]), p["id"]
        assert [m["text"] for m in p["messages"]] == r["messages"]
        st[p["status"]] = st.get(p["status"], 0) + 1
        ts = {m["tier"] for m in p["messages"]}
        for m in p["messages"]:
            tiers[m["tier"]] = tiers.get(m["tier"], 0) + 1
            assert m["tier"] in ("plan", "step2", "step3")
            if m["tier"] != "plan":
                assert m.get("why"), (p["id"], m["n"])
                continue
            for rnd in m["rounds"]:
                for c in rnd:   # every call is one the registry takes, with arguments its model accepts
                    t = TL.REGISTRY[c["tool"]]
                    assert t.kind == "read" and t.run is not None
                    t.params(**c["args"])
        want = ("step3" if ts == {"step3"} else "step2" if "plan" not in ts else
                "plan" if ts == {"plan"} and not any(m.get("step2") for m in p["messages"]) else "partial")
        assert p["status"] == want, p["id"]
        if r["step"] == 3:
            assert p["status"] == "step3", p["id"]
    assert st == {"plan": 58, "partial": 18, "step2": 17, "step3": 18}
    assert tiers == {"plan": 91, "step2": 20, "step3": 19}


def test_the_plans_run_recount_and_say_their_findings(harness):
    from mvp import eval_brain as E
    s, out = E.plans(harness)
    assert s["conversations"] == 111 and s["messages"] == 130 and s["planned_messages"] == 91
    assert s["with_a_plan"] == 76 and s["waiting"] == {"step2": 17, "step3": 18}
    assert s["tool_errors"] == [] and s["expect_failed"] == [] and s["window_failed"] == []
    # every code lead is checked (a template through the verifier; code_form for its own window and its case; the
    # plain line counts as a failure when a result holds what was asked)
    assert {x.split(":")[0] for x in s["lead_not_ok"]} == KNOWN_LEAD_NOT_OK
    # every number of every result recounted (the sheet's and the meta's counts), but a season's "since" counts and
    # a few meta counts the auditor does not read (a length-filtered result's private count, a search's, a learned's,
    # friends on a result that saw nothing)
    assert s["numbers_in_results"] - s["numbers_recounted"] <= 25
    assert all(p.endswith(("since_items", "since_new", "meta.hidden.sensitive", "meta.hidden.friends"))
               for p in s["not_recounted"]), s["not_recounted"]
    assert {x["id"] for x in s["recount_not_true"]} == KNOWN_NOT_TRUE
    assert s["recount_true"] == s["with_a_plan"] - len(KNOWN_NOT_TRUE)
    assert [f["at"] for f in s["findings"]["window"]] == ["G04.0"]          # "late october" read as October
    assert {f["kind"] for f in s["findings"]["shape"]} == {"one name, two fields", "list cut"}
    assert any(f["at"] == "F11.0" and f["kind"] == "list cut" for f in s["findings"]["shape"])
    assert len(s["plan_findings"]) == 5
    # the fake brain stood for one request per round and one for the answer
    a01 = next(c for c in out if c["id"] == "A01")
    assert [m.get("requests") for m in a01["messages"] if m["tier"] == "plan"] == [2, 2, 2, 2, 2]


def test_a_follow_up_runs_on_the_last_window_and_the_screen(harness):
    from mvp import eval_brain as E
    p = next(x for x in rows(PLANS) if x["id"] == "A01")
    out = E.run_conversation(harness, p)
    ms = [m for m in out["messages"] if m["tier"] == "plan"]
    # "what about without gaming" names no window: same_as last is October's, from the message before
    assert ms[3]["_window"].start == date(2026, 10, 1)
    without = ms[3]["_results"]["r1"]
    assert without["meta"]["filters_said"] == "without gaming (area)"
    assert ms[4]["_results"]["r1"]["meta"]["filters_said"] == "without gaming (area); only videos known to be long"


# ================================================================ planted, insight, run
def test_planted_mode_drops_every_false_sentence_and_keeps_the_true():
    from mvp import eval_brain as E
    s = E.planted()
    assert s["false"] == s["false_dropped"] == s["false_dropped_expected"] and s["false"] >= 195
    assert s["true_kept"] / s["true"] >= 0.97 and s["bar"] == {"false_all_dropped": True, "true_kept_97": True}
    assert s["kept_false"] == [] and s["wrong_reason"] == []
    assert sum(b["false"] for b in s["by_class"].values()) == s["false"]


def test_insight_mode_counts_the_twenty_cases(harness):
    from mvp import eval_brain as E
    s = E.insight(harness)
    assert s["cases"] == 20
    assert s["by"] == {"identical": 9, "same numbers": 2, "no match (0 today)": 4, "not mapped": 5}
    assert s["truncated_identical"] == 4


def test_run_mode_refuses_in_step_1(capsys):
    from mvp import eval_brain as E
    assert E.main(["run", "--set", "x", "--provider", "anthropic"]) == 2
    assert "step 2" in capsys.readouterr().err


# ================================================================ the fake brain and the fake backends
def test_the_fake_brain_replays_rounds_and_refuses_a_broken_plan(brain):
    from mvp.brain import tools as TL
    from mvp.tests.fakes.fake_brain import FakeBrain, FakeBrainError, run_rounds
    fb = FakeBrain([[{"tool": "find", "args": {"names": ["gaming"]}}]], answer={"lead": "x"})
    assert fb.step() == [{"tool": "find", "args": {"names": ["gaming"]}}] and fb.step() is None
    assert fb.give_answer() == {"lead": "x"} and fb.requests == 2
    for bad in ([[]], [[{"tool": "find"}]], [{"tool": "find", "args": {}}]):
        with pytest.raises(FakeBrainError):
            FakeBrain(bad)
    from mvp.tests.test_brain_tools import turn
    t = turn(brain, "channels in october")
    out, fb = run_rounds(t, [[{"tool": "breakdown", "args": {"by": "channel", "window": {"words": "in October"}}}],
                             [{"tool": "items", "args": {"window": {"same_as": "r1"}, "limit": 2}}]], TL.call)
    assert [(k, c["tool"], r["rid"]) for k, c, r in out] == [(0, "breakdown", "r1"), (1, "items", "r2")]


def test_the_fake_engine_keeps_the_kind_asked_and_learned_only_saves(brain):
    from mvp.tests.fakes.fake_brain import FakeEngine, fake_learned
    from mvp.tests.test_brain_tools import turn
    t = turn(brain, "pasta")
    got = FakeEngine()(t, "pasta", "saved", None, None, 5)
    assert [x["item_id"] for x in got["items"]] == ["rx_pasta"]       # the friend's pasta post is a save too: code
    opened = FakeEngine()(t, "pasta", "opened", None, None, 5)      # (tools.run_search) leaves it out later
    assert opened["items"] and "rx_pasta" not in {x["item_id"] for x in opened["items"]}
    pts = fake_learned(t, "sourdough", None)["points"]
    assert [p["item_ids"] for p in pts] == [["rx_sour1"], ["rx_sour2"]]
    assert fake_learned(t, "calculus", None)["points"] == []       # watched, never saved


# ================================================================ the auditor on the tools' results
def _audit(brain, tool, args, message=""):
    from mvp import eval_claims as EC
    r, t = call(brain, tool, args, message)
    lib = EC.Library(str(brain["lib"]), os.environ["MVP_DERIVED_HOME"], "America/New_York", now=NOW,
                     hide_sensitive=True, unlock=t.unlock)
    return r, lib


def _bad(rows_):
    """The number findings (a shape finding, such as two theme fields of one shown name, is listed apart)."""
    from mvp import eval_brain as E
    return [x for x in rows_ if not x["ok"] and x["kind"] != "understood_window" and E.finding_class(x) != "shape"]


def test_the_auditor_recounts_a_true_result_and_catches_each_planted_error(brain):
    from mvp import eval_claims as EC
    args = {"by": "channel", "window": {"words": "in October"}}
    r, lib = _audit(brain, "breakdown", args, "which channels did i watch the most in october")
    c = {"tool": "breakdown", "args": args}
    assert _bad(EC.audit_results(lib, r, c, "which channels did i watch the most in october", TODAY)) == []
    for path, change, kind in ((("channels", 0, "items"), 1, "count"), (("totals", "items"), -3, "count"),
                               (("areas", 0, "share"), 0.05, "share"), (("channels", 1, "share"), -0.02, "share")):
        bad = copy.deepcopy(r)
        o = bad["sheet"]
        for k in path[:-1]:
            o = o[k]
        o[path[-1]] += change
        found = _bad(EC.audit_results(lib, bad, c, "", TODAY))
        assert any(f["kind"] == kind for f in found), (path, found)
    # two rows swapped: the order is wrong
    sw = copy.deepcopy(r)
    sw["sheet"]["channels"][0], sw["sheet"]["channels"][1] = sw["sheet"]["channels"][1], sw["sheet"]["channels"][0]
    assert any(f["kind"] == "rank" for f in _bad(EC.audit_results(lib, sw, c, "", TODAY)))
    # a window the call's words do not say
    ww = copy.deepcopy(r)
    ww["sheet"]["window"]["start"] = "2026-09-01"
    assert any(f["kind"] == "call window" for f in _bad(EC.audit_results(lib, ww, c, "", TODAY)))


def test_the_auditor_reads_each_scope_form_by_its_own_reading(brain):
    from mvp import eval_claims as EC
    for args, msg in (({"by": "channel", "window": {"words": "in October"}, "scope": {"exclude": ["gaming"]}}, ""),
                      ({"by": "none", "window": {"words": "in October"}, "scope": {"exclude": ["tofu"]}}, ""),
                      ({"by": "channel", "window": {"words": "in October"}, "scope": {"only": ["Gaming Daily"]}}, ""),
                      ({"by": "area", "window": {"words": "in October"}, "scope": {"exclude": ["minecraft"]}}, ""),
                      ({"by": "channel", "window": {"words": "in October"}, "scope": {"length": "long"}}, ""),
                      ({"by": "none", "window": {"words": "in October"}, "scope": {"length": "short"}}, ""),
                      ({"by": "none", "window": {"words": "in October"}, "scope": {"weekday": 0}}, ""),
                      ({"by": "none", "window": {"words": "in October"}, "scope": {"platforms": ["instagram"]}}, ""),
                      ({"by": "channel", "window": {"preset": "lately"}, "scope": {"how": "saved"}}, ""),
                      ({"by": "none", "window": {"preset": "all"}, "scope": {"only": ["Watercolor to try"],
                                                                             "how": "saved"}}, "")):
        r, lib = _audit(brain, "breakdown", args, msg)
        assert "sheet" in r, (args, r)
        assert _bad(EC.audit_results(lib, r, {"tool": "breakdown", "args": args}, "", TODAY)) == [], args
        # the same result counted under a scope it does not hold is caught (the scope is read, not taken as given)
        if args.get("scope", {}).get("exclude"):
            drop = {"tool": "breakdown", "args": dict(args, scope={})}
            assert _bad(EC.audit_results(lib, r, drop, "", TODAY)), args


def test_the_auditor_keeps_private_topics_out_unless_unlocked(brain):
    from mvp import eval_claims as EC
    args = {"by": "channel", "window": {"words": "in 2024"}}
    r, lib = _audit(brain, "breakdown", args, "which channels did i watch the most in 2024")
    assert _bad(EC.audit_results(lib, r, {"tool": "breakdown", "args": args}, "", TODAY)) == []
    assert r["sheet"]["totals"]["items"] == 8
    plain = EC.Library(str(brain["lib"]), os.environ["MVP_DERIVED_HOME"], "America/New_York", now=NOW)
    assert _bad(EC.audit_results(plain, r, {"tool": "breakdown", "args": args}, "", TODAY))   # 58 counted
    u, lib_u = _audit(brain, "breakdown", args, "which dating advice channels did i watch in 2024")
    assert u["sheet"]["channels"][0]["name"] == "Heart Notes"
    assert _bad(EC.audit_results(lib_u, u, {"tool": "breakdown", "args": args}, "", TODAY)) == []


def test_the_auditor_checks_item_rows_finds_and_searches(brain):
    from mvp import eval_claims as EC
    from mvp.tests.fakes.fake_brain import FakeEngine
    args = {"subject": "watercolor", "which": "first"}
    r, lib = _audit(brain, "first_last", args, "when did i start watercolor")
    c = {"tool": "first_last", "args": args}
    assert _bad(EC.audit_results(lib, r, c, "", TODAY)) == []
    wrong = copy.deepcopy(r)
    wrong["sheet"]["items"][0], wrong["sheet"]["items"][1] = wrong["sheet"]["items"][1], wrong["sheet"]["items"][0]
    assert any(f["kind"] == "first" for f in _bad(EC.audit_results(lib, wrong, c, "", TODAY)))
    f, lib = _audit(brain, "find", {"names": ["Gaming Daily", "bouldering"]})
    assert _bad(EC.audit_results(lib, f, {"tool": "find", "args": {}}, "", TODAY)) == []
    f["sheet"]["names"][0]["matches"][0]["items_all_time"] = 6
    assert _bad(EC.audit_results(lib, f, {"tool": "find", "args": {}}, "", TODAY))
    s, t = call(brain, "search", {"query": "pasta", "how": "saved"}, "find that pasta thing", search=FakeEngine())
    c = {"tool": "search", "args": {"query": "pasta", "how": "saved"}}
    assert s["sheet"]["items"] and _bad(EC.audit_results(lib, s, c, "", TODAY)) == []
    s["sheet"]["items"][0]["why_matched"] = "a line it does not hold"
    assert _bad(EC.audit_results(lib, s, c, "", TODAY))


def test_audit_ledger_recounts_each_cited_cell_its_base_and_its_rank(brain):
    from mvp import eval_claims as EC
    args = {"by": "channel", "window": {"words": "in October"}}
    r, lib = _audit(brain, "breakdown", args)
    calls = {"r1": {"tool": "breakdown", "args": args}}
    n0, n1 = r["sheet"]["channels"][0]["items"], r["sheet"]["channels"][1]["items"]
    share = round(100 * r["sheet"]["channels"][0]["share"])
    good = (f"In October 2026, Clip Factory[r1.channels[0]] led with {n0}[r1.channels[0].items] videos, "
            f"{share}%[r1.channels[0].share] of them; Pan Theory[r1.channels[1]] had {n1}[r1.channels[1].items].")
    cells = EC.cited_cells(good)
    assert [c["path"] for c in cells] == ["r1.channels[0].items", "r1.channels[0].share", "r1.channels[1].items"]
    rows_ = EC.audit_ledger(lib, cells, {"r1": r}, calls, "", TODAY)
    assert rows_ and all(x["ok"] for x in rows_)
    assert {x["kind"] for x in rows_} >= {"value", "base total", "rank"}
    lie = good.replace(f"{n1}[r1.channels[1].items]", f"{n1 + 2}[r1.channels[1].items]")
    assert [x["where"] for x in EC.audit_ledger(lib, EC.cited_cells(lie), {"r1": r}, calls, "", TODAY)
            if not x["ok"]] == ["r1.channels[1].items"]
    # a date marker: the row's date recounted, and the date typed before the marker compared with it
    f_args = {"subject": "watercolor", "which": "first"}
    fr, lib2 = _audit(brain, "first_last", f_args, "when did i start watercolor")
    fcalls = {"r1": {"tool": "first_last", "args": f_args}}
    ok = "You first opened a watercolor video on 10 January 2025[r1.items[0].when]."
    assert all(x["ok"] for x in EC.audit_ledger(lib2, EC.cited_cells(ok), {"r1": fr}, fcalls, "", TODAY))
    for wrong in ("on 16 January 2025[r1.items[0].when]", "in March 2025[r1.items[0].when]", "on[r1.items[0].when]"):
        rows_ = EC.audit_ledger(lib2, EC.cited_cells("You first opened one " + wrong + "."), {"r1": fr}, fcalls, "",
                                TODAY)
        assert rows_ and not all(x["ok"] for x in rows_), wrong
    assert all(x["ok"] for x in EC.audit_ledger(lib2, EC.cited_cells("It was in January 2025[r1.items[0].when]."),
                                                {"r1": fr}, fcalls, "", TODAY))


def test_audit_lead_reads_a_code_form_lead_with_the_text_audit(brain):
    from mvp import eval_claims as EC
    args = {"by": "area", "window": {"words": "lately"}}
    r, lib = _audit(brain, "breakdown", args, "what am i into lately")
    c = {"tool": "breakdown", "args": args}
    g = round(100 * r["sheet"]["areas"][0]["share"])
    ok = f"In the 4 weeks up to 30 October 2026, gaming led with {g}% of what you opened."
    assert [x for x in EC.audit_lead(lib, r, ok, None, c, "what am i into lately", TODAY) if not x["ok"]] == []
    lie = ok.replace(f"{g}%", f"{g + 9}%")
    assert [x for x in EC.audit_lead(lib, r, lie, None, c, "what am i into lately", TODAY) if not x["ok"]]


def test_the_auditor_reads_the_window_words_a_call_writes(brain):
    from mvp import eval_claims as EC
    lib = EC.Library(str(brain["lib"]), os.environ["MVP_DERIVED_HOME"], "America/New_York", now=NOW,
                     hide_sensitive=True)

    def span(words=None, preset=None):
        a, b, _p = EC.spec_window(EC.read_call_window(words, lib, TODAY, preset=preset), lib, TODAY)
        return date.fromordinal(a).isoformat() if a else None, date.fromordinal(b).isoformat()
    assert span("this autumn") == ("2026-09-01", "2026-10-30")
    assert span("last autumn") == ("2025-09-01", "2025-11-30")
    assert span("on 30 october") == ("2026-10-30", "2026-10-30")
    assert span("late october") == ("2026-10-21", "2026-10-31")
    assert span("yesterday") == ("2026-10-30", "2026-10-30")        # after the record: its last day
    assert span(preset="last_week") == ("2026-10-24", "2026-10-30")  # after the record: its last 7 days
    assert span(preset="last_month") == ("2026-10-01", "2026-10-30")
    assert span("the summer of 2023") == ("2023-06-01", "2023-08-31")
    assert span("ultimamente") == ("2026-10-03", "2026-10-30")


def test_eval_claims_still_imports_nothing_from_the_bot():
    """The audit imports nothing of the bot: its module level imports only the standard library, and the brain's
    audit section imports nothing at all (`capture` alone, which sends through the bot, imports it inside)."""
    with open(os.path.join(MVP, "eval_claims.py"), encoding="utf-8") as f:
        src = f.read()
    top = re.findall(r"^(?:from|import)\s+([\w.]+)", src, re.M)
    assert not [m for m in top if m.startswith(("mvp", "."))]
    start = src.index("# ============================================================================ the brain's results")
    end = src.index("# ============================================================================ capture")
    assert not re.search(r"^\s*(?:from|import)\s", src[start:end], re.M)
