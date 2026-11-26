"""The seams of the merge after the thin live slice (mvp22): the read tools' fix (brain-toolfix-local), the eval's
measuring tools (brain-evaltools-local) and the fresh eval set (brain-fresh-local), together.

- The eval's run mode loads the real fresh file, by half, before any key is asked for (no model call here).
- Every reading of the fresh set, replayed on today's tools along the eval's own hand chain, states the window the
  tools give it and holds a counting result (the set's faults, not the model's). Half B is reported by id only.
- A fresh conversation of half A runs through the live loop with a fake provider that calls the preferred reading:
  every plan message gives a record, scored against the set's readings, with no fault of the set.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from mvp.tests.test_brain_tools import (  # noqa: F401  (fixtures: the made-up library)
    NOW,
    brain,
    built,
    no_real_keys,
    person,
)
from mvp.tests.test_mvp import env  # noqa: F401  (env is a fixture)

FRESH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "evalset", "brain_fresh.jsonl")


@pytest.fixture()
def harness(brain):  # noqa: F811  (the fixture of test_brain_tools)
    from mvp import eval_brain as E
    return E.Harness(brain["bot"], str(brain["lib"]), os.environ["MVP_DERIVED_HOME"], handle=person(brain)["handle"],
                     now=NOW)


def _plan_count(sets):
    return sum(1 for p, _c in sets for m in p["messages"] if m["tier"] == "plan")


def test_the_run_mode_loads_the_real_fresh_file_by_half():
    from mvp import eval_brain as E
    a = E.run_set("a", set_name="fresh")
    b = E.run_set("b", set_name="fresh")
    every = E.run_set("all", set_name="fresh")
    # the fresh set's own counts (evalset/README_brain_fresh.md): 131 plan messages, A 65 and B 66
    assert (_plan_count(a), _plan_count(b), _plan_count(every)) == (65, 66, 131)
    assert len(a) + len(b) == len(every)
    assert all(E.half_of(p["id"], "fresh") == "a" for p, _c in a)
    assert all(E.half_of(p["id"], "fresh") == "b" for p, _c in b)
    assert all(core is p for p, core in every)   # a fresh line is its own core conversation
    with pytest.raises(ValueError):
        E.run_set("heldout", set_name="fresh")


def test_the_run_mode_on_the_fresh_set_stops_at_the_key_and_sends_nothing(tmp_path, capsys, monkeypatch):
    from mvp import eval_brain as E
    for k in ("DIGESTER_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY", "MVP_LEDGER_HOME"):
        monkeypatch.delenv(k, raising=False)
    assert E.main(["run", "--set", "fresh", "--half", "a", "--out", str(tmp_path / "o")]) == 2
    err = capsys.readouterr().err
    assert "nothing was sent" in err and "no set file" not in err and "is not a half" not in err
    assert not (tmp_path / "o").exists()


def test_every_reading_of_the_fresh_set_holds_on_todays_tools(harness):
    """As live_conversation chains them: each message's readings from the hand chain's screen and last window. A
    window a reading states that the tools no longer give, a tool error, or a reading with nothing to score is a
    fault of the set (half B: by id only)."""
    from mvp import eval_brain as E
    faults = []
    for p, _c in E.run_set("all", set_name="fresh"):
        hscreen, hlast = "", None
        for m in p["messages"]:
            if m["tier"] != "plan":
                continue
            hand, _readings, windows, errors = E.hand_readings(harness, m, hscreen, hlast)
            hscreen, hlast = E.hand_chain_next(hand, "fresh", hscreen, hlast)
            if windows or errors:
                key = f"{p['id']}.{m['n']}"
                faults.append((key, windows, errors) if E.half_of(p["id"], "fresh") == "a" else key)
    # before the merge's two seam fixes in eval_brain: N069.0 (a search result's window read as [None, None]) and
    # N058.1 (half B: the plans set's chain, the code lead as the screen, broke a follow-up's call)
    assert faults == []


def test_the_fresh_hand_chain_goes_on_from_the_window_words_and_the_plans_chain_from_the_lead():
    from mvp import eval_brain as E
    hand = {"lead": "In October 2026, gaming led.", "_window": {"words": "in October"},
            "_results": {"r1": {"meta": {"window_said": "October 2026"}}}}
    assert E.hand_chain_next(hand, "fresh", "", None) == ("October 2026", {"words": "in October"})
    assert E.hand_chain_next(hand, "plans", "", None) == ("In October 2026, gaming led.", {"words": "in October"})
    assert E.hand_chain_next(None, "fresh", "before", {"x": 1}) == ("before", {"x": 1})


class _ReadingProvider:
    """A fake model that, for each message, calls the rounds of its preferred reading in order, then answers with
    one plain sentence (and the same again on a repair)."""

    def __init__(self, conv):
        from mvp.brain import provider as P
        self.P = P
        self.fake = P.FakeProvider([])
        self.rounds = {m["text"]: m["readings"][0]["rounds"] for m in conv["messages"] if m["tier"] == "plan"}
        self.spent, self.requests = 0.0, 0

    def settings(self):
        return {"model": "fake"}

    def send(self, system, tools, messages, max_tokens=None, timeout=None):
        P = self.P
        first = str(messages[0]["content"])
        text = max((t for t in self.rounds if t in first), key=len)
        k = sum(1 for x in messages if x["role"] == "assistant")
        rounds = self.rounds[text]
        if k < len(rounds):
            blocks = [P.tool_use(c["tool"], c["args"]) for c in rounds[k]]
        else:
            blocks = [P.tool_use("give_answer", {"lead": "Here is what your history shows.", "points": []})]
        self.fake.script = [blocks]
        self.requests += 1
        return self.fake.send(system, tools, messages, max_tokens=max_tokens, timeout=timeout)


def test_a_fresh_conversation_of_half_a_runs_through_the_live_loop(harness, tmp_path):
    from mvp import eval_brain as E
    sets = E.run_set("a", set_name="fresh")
    # the first conversation of half A with a follow-up: the chain of windows and screens is exercised
    p, core = next((p, c) for p, c in sets if sum(1 for m in p["messages"] if m["tier"] == "plan") >= 2)
    recs = E.live_conversation(harness, _ReadingProvider(p), p, core, out_dir=str(tmp_path), log=lambda s: None,
                               set_name="fresh")
    plans = [m for m in p["messages"] if m["tier"] == "plan"]
    assert [r["key"] for r in recs] == [f"{p['id']}.{m['n']}" for m in plans]
    for r in recs:
        assert r["set"] == "fresh" and r["half"] == "a"
        assert r["reading_window_failed"] == [] and r["reading_errors"] == []
        assert r["g2"]["readings"] >= 1
    # the first message's calls are its preferred reading's: understood on reading 0
    assert recs[0]["g2"]["verdict"] == "understood" and recs[0]["g2"]["reading"] == 0
    s = E.summarize(recs, {"set": "fresh"})
    assert s["G1_false_sent"]["how"].startswith("NEEDS A HAND RECOUNT") and "auditor_hints" in s
