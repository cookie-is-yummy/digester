"""mvp28 (limitonly): the soft deadline never pushes a turn to answer from nothing.

The class of case: a turn whose read calls have all come back as errors (a window after the export ends, a kind of
event the export does not hold, an argument out of bounds), or whose first request alone ran to the soft deadline, so
no read result is in hand when the deadline passes. The loop used to refuse the next read calls with "time is up ...
answer with the results you already have" when there were none; the model then answered with a limit alone, or said
it could not read their history when code had refused the read. Now (brain/loop.py):
- past the soft (or deep) deadline with no read result in hand, the round runs: the round that gives the turn its
  first result may run up to the hard stop (event "first_result_late");
- out of rounds with no read result in hand, the turn ends with the code lead (fallback.answer: with no result, its
  plain line) instead of asking the model to answer from nothing (event "no_result");
- a result in hand past the deadline still gets the one "time is up", and the hard stop still ends the turn.
A fake provider and the made-up library only. No model call.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_brain_tools import brain, built, no_real_keys, person  # noqa: E402,F401  (fixtures)
from mvp.tests.test_brain_slice import OCT, TRUE_LEAD, bd, ga, harness, turn  # noqa: E402,F401

MESSAGE = "which channels did I watch the most in October?"
# an argument out of bounds: the tool refuses it (an error result, no rid); any errored call is the same case
BAD = dict(OCT, top=99)


def _results(prov, k):
    """The tool_result blocks of request k (the user message that request carried last)."""
    return prov.sent[k][2][-1]["content"]


def _run(harness, steps, **kw):
    """steps: (blocks, seconds) per request, on a fake clock."""
    from mvp.brain import loop as BL, provider as P
    clock = [0.0]
    prov = P.FakeProvider([{"blocks": b, "seconds": s} for b, s in steps],
                          clock=lambda s: clock.__setitem__(0, clock[0] + s))
    t = turn(harness, MESSAGE)
    rec = BL.run_turn(prov, t, screen={}, now=lambda: clock[0], **kw)
    return rec, prov, t


def _ok(rec):
    return [c for c in rec["calls"] if not (c.get("result") or {}).get("is_error")]


# ================================================================ the fault path, and the new behaviour
def test_an_errored_call_then_a_slow_request_past_the_soft_deadline_still_runs_its_read(harness):
    from mvp.brain import loop as BL
    rec, prov, _t = _run(harness, [([bd(BAD)], 2.0), ([bd()], 6.0), ([ga(TRUE_LEAD)], 2.0)])
    # round 1 errored; the second request ended at 8 s, past the soft deadline of 7 s, with nothing in hand
    assert rec["calls"][0]["result"].get("is_error")
    # the read of round 2 runs (it used to get TIME_UP, and the model answered with nothing to cite)
    assert all(x["content"] != BL.TIME_UP for x in _results(prov, 2))
    assert len(_ok(rec)) == 1 and rec["rounds"] == 2
    assert "time_up" not in rec["events"] and "first_result_late" in rec["events"]
    # the answer cites the result the late round gave
    assert rec["lead_source"] == "model" and rec["answer"]["lead"] == "In October 2026, Clip Factory led with 61 videos."


def test_a_first_request_that_alone_reaches_the_soft_deadline_still_runs_its_read(harness):
    from mvp.brain import loop as BL
    rec, prov, _t = _run(harness, [([bd()], 7.0), ([ga(TRUE_LEAD)], 2.0)])
    # the turn's one read call came at 7.0 s: it used to be refused, and the model said it could not read their history
    assert all(x["content"] != BL.TIME_UP for x in _results(prov, 1))
    assert len(_ok(rec)) == 1 and rec["rounds"] == 1 and rec["events"] == ["first_result_late"]
    assert rec["lead_source"] == "model" and rec["seconds"] == 9.0


def test_with_a_result_in_hand_the_late_round_is_the_one_time_up_as_before(harness):
    from mvp.brain import loop as BL
    rec, prov, _t = _run(harness, [([bd(BAD)], 2.0), ([bd()], 6.0), ([bd()], 1.0), ([ga(TRUE_LEAD)], 1.0)])
    # the late round gave the first result; a further read call past the deadline gets TIME_UP once
    assert rec["events"] == ["first_result_late", "time_up"] and len(_ok(rec)) == 1
    assert [x["content"] for x in _results(prov, 3)] == [BL.TIME_UP]
    assert rec["lead_source"] == "model"


def test_a_result_in_hand_at_the_soft_deadline_still_gets_time_up(harness):
    from mvp.brain import loop as BL
    rec, prov, _t = _run(harness, [([bd()], 2.0), ([bd()], 5.0), ([ga(TRUE_LEAD)], 1.0)])
    assert rec["events"] == ["time_up"] and rec["rounds"] == 1 and len(rec["calls"]) == 1
    assert [x["content"] for x in _results(prov, 2)] == [BL.TIME_UP]
    assert rec["lead_source"] == "model" and rec["seconds"] == 8.0


def test_the_late_round_runs_only_up_to_the_hard_stop(harness):
    # the first request alone ran past the hard stop: no read runs, the turn ends with the plain line (as before)
    rec, prov, _t = _run(harness, [([bd()], 16.0), ([ga(TRUE_LEAD)], 1.0)])
    assert rec["events"] == ["time_up", "hard_stop"] and rec["n_requests"] == 1 and rec["lead_source"] == "plain"
    assert rec["calls"] == []
    # errored reads one after another past the soft deadline: rounds run until the hard stop ends the turn
    rec, prov, _t = _run(harness, [([bd(BAD)], 6.0), ([bd(BAD)], 5.0), ([bd(BAD)], 5.0), ([ga(TRUE_LEAD)], 1.0)])
    assert rec["events"] == ["first_result_late", "time_up", "hard_stop"] and rec["n_requests"] == 3
    assert _ok(rec) == [] and rec["lead_source"] == "plain"


def test_out_of_rounds_with_nothing_in_hand_the_turn_ends_with_the_code_lead(harness):
    from mvp.brain import fallback as FB, loop as BL
    rec, prov, _t = _run(harness, [([bd(BAD)], 1.0), ([bd(BAD)], 1.0), ([ga(TRUE_LEAD)], 1.0)], rounds=1)
    # no request is told "answer with the results you already have" when there are none
    assert all(x["content"] != BL.TIME_UP for k in range(len(prov.sent)) if k for x in _results(prov, k))
    assert rec["events"] == ["no_result"] and rec["n_requests"] == 2 and rec["forms"] == []
    # (the prep repair: time was not the cause, so the plain line says no result came back, not "in time")
    assert rec["lead_source"] == "plain" and rec["answer"]["lead"] == FB.NO_RESULT
    # with a result in hand, running out of rounds is the one time_up as before
    rec, prov, _t = _run(harness, [([bd()], 1.0), ([bd()], 1.0), ([ga(TRUE_LEAD)], 1.0)], rounds=1)
    assert rec["events"] == ["time_up"] and [x["content"] for x in _results(prov, 2)] == [BL.TIME_UP]
    assert rec["lead_source"] == "model"


def test_a_model_answer_with_no_read_result_is_still_checked_and_sent_as_before(harness):
    """Not built: refusing a model answer only because the turn holds no read result. A message about only what the
    export lacks (an errored call whose error says so) has a true answer with no result; the values check reads values,
    and such a lead holds none that is wrong. The loop no longer refuses the read that would give the result, so the
    sentence "I could not read your history" has no path from code's own refusal."""
    lead = "Your export holds no likes."
    rec, _prov, _t = _run(harness, [([bd(BAD)], 1.0), ([ga(lead)], 1.0)])
    assert _ok(rec) == [] and rec["events"] == [] and rec["lead_source"] == "model"


# ================================================================ the merge's seam with the argument check (args)
def test_a_call_refused_outside_the_schema_leaves_nothing_in_hand_and_the_eval_counts_the_late_round(harness):
    """A provider that says its grammar (here strict off) has the model's calls held to the schema sent; a refused call
    is an error result, so with it alone the turn holds no result. Past the soft deadline the corrected call's round
    runs (first_result_late), not time_up, and the eval's tool_args counts that path."""
    import copy
    from mvp import eval_brain as E
    from mvp.brain import loop as BL, provider as P
    from mvp.tests.test_brain_r28_args import FULL
    good = dict(copy.deepcopy(FULL["breakdown"]), by="channel")
    bad = {k: v for k, v in good.items() if k != "order"}
    clock = [0.0]
    prov = P.FakeProvider([{"blocks": [bd(bad)], "seconds": 2.0}, {"blocks": [bd(good)], "seconds": 6.0},
                           {"blocks": [ga(TRUE_LEAD)], "seconds": 1.0}],
                          clock=lambda s: clock.__setitem__(0, clock[0] + s))
    prov.strict = False
    rec = BL.run_turn(prov, turn(harness, MESSAGE), screen={}, now=lambda: clock[0])
    first, second = rec["calls"]
    assert first["result"]["is_error"] and first["result"]["outside_schema"] == ["order"]
    assert not second["result"].get("is_error") and second["rid"] == "r1"
    # the corrected call came at 8 s, past the soft deadline, with nothing in hand: it ran (its result is in request 2)
    assert all(x["content"] != BL.TIME_UP for x in _results(prov, 2))
    assert rec["events"] == ["first_result_late"]
    rec["key"] = "X1.0"
    one = E.tool_args_of(rec)
    assert one["arg_errors"] == 1 and one["time_up"] == 0 and one["first_result_late"] == 1 and one["no_result"] == 0
    s = E.tool_args_summary([rec], {"strict": False})
    assert s["arg_error_then_time_up"] == [] and s["arg_error_then_late"] == ["X1.0"]
