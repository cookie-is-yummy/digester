"""Offline tests for round 9, slice U (DESIGN.md section 12, "Round 9, slice U"): requests for a kind of thing. What the
details model returned and why code left things out is counted for the kinds evaluation (eval_kinds.py); the details
call is told the kind asked for (extract_v4); clear picks lead even when their text names nothing; the posts read for
things are chosen steadily. Synthetic posts with made-up names, a fake model, a fake search pool and a fake clock."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_round7 import ask, items_fake, pick, use_lib  # noqa: E402
from mvp.tests.test_round8_answers import It, names  # noqa: E402
from mvp.tests.test_round8_live import ROWS98, TABLE98, compose98  # noqa: E402
from mvp.tests.test_slice2 import H, say  # noqa: E402

UI_ASK = "what are some uiux libraries i should use for my next project"


def runs(env):
    return env["bot"].store.q("SELECT * FROM runs WHERE handle=? ORDER BY id", (H,))


# ---------- point 4: what the model returned and why code left things out, counted ----------
def test_u4_the_details_check_counts_what_the_model_returned_and_what_it_left_out():
    from mvp.extract import verify_items
    text = "Three kits I like\n- Pantry: copy and paste blocks\n- Larder: a calm set of parts"
    tally = {}
    got, dropped = verify_items([{"name": "Pantry", "about": "copy and paste blocks", "fit": "yes"},
                                 {"name": "Larder", "about": "", "fit": "no"},
                                 {"name": "Cellar", "about": "not in the text", "fit": "yes"},
                                 {"name": "Pantry", "fit": "yes"}, "not an object"], text, tally)
    assert names(got) == ["Pantry"] and dropped == 3
    assert tally == {"raw": 5, "yes": 3, "fit_no": 1, "not_in_text": 2, "repeated": 1}
    # without a tally nothing changes (the round 8 callers)
    assert verify_items([{"name": "Pantry", "fit": "yes"}], text) == \
        ([{"name": "Pantry", "about": "", "when": "", "fit": "yes"}], 0)


def test_u4_clean_items_says_which_test_left_each_thing_out():
    from mvp.extract import clean_items, junk_reason
    text = ("My Favourite Kits\n- Pantry: copy and paste blocks for every screen\n- design systems\n"
            "we keep a toggle on every page\n- Writing & Editing\nLarder is mentioned once")
    why = {}
    got, dropped = clean_items([{"name": "Pantry", "about": "copy and paste blocks for every screen"},
                                {"name": "design systems", "about": ""}, {"name": "toggle", "about": ""},
                                {"name": "Writing & Editing", "about": ""}, {"name": "Larder", "about": ""}],
                               It(text), why=why)
    assert names(got) == ["Pantry"] and dropped == 4
    assert why == {"kind_word": 1, "common_noun": 1, "activity": 1, "no_words": 1}
    assert junk_reason("Pantry", "", It(text), text) is None
    # a post about one thing keeps it (no "no_words" for a lone thing)
    why = {}
    clean_items([{"name": "Larder", "about": ""}], It(text), why=why)
    assert why == {}


@pytest.fixture()
def lib98(env, tmp_path):
    use_lib(env, tmp_path, ROWS98, name="lib98")
    env["state"]["answers"]["mvp_compose"] = compose98
    env["state"]["answers"]["mvp_extract"] = items_fake(TABLE98)
    return env


def test_u4_a_run_keeps_the_counts_the_kinds_evaluation_reads(lib98):
    say(lib98, UI_ASK, ask("UI/UX libraries", ["ui libraries"]))
    steps = json.loads(runs(lib98)[-1]["steps"])
    assert steps["items_model"]["raw"] == 8 and steps["items_model"]["yes"] == 7
    assert steps["items_why"] == {"kind_word": 1}   # the bare format word among the site names
    assert steps["items_sources"] == {"clear": 1, "close": 2}
    assert steps["items"] == 7


def test_u4_the_evaluation_reads_the_kind_of_answer_from_fixed_phrases_and_steps():
    from mvp.eval_kinds import answer_kind, summary
    assert answer_kind("I found 3 ...", [{"items": 3}], ["ask"], 2) == "items"
    assert answer_kind("Here's what I found.\n\nI recommend X", [{}], ["ask"], 2) == "recommend"
    assert answer_kind("I recommend X\n\nNamed in other saves, close to what you asked:", [{}], ["ask"], 2) == \
        "recommend_named"
    assert answer_kind('Nothing I found is a clear fit for "x".\n\nThe closest I have is', [{}], ["ask"], 1) == \
        "closest"
    assert answer_kind("I couldn't find anything", [{}], ["ask"], 0) == "none"
    assert answer_kind("Hi!", [], ["chat"], 0) == "other"
    row = {"answer": "items", "errors": 0, "shown_things": 4, "model_items": 6, "model_yes": 5,
           "dropped_by_check": {"fit_no": 1}, "dropped_as_junk": {"kind_word": 1}, "dropped_not_the_kind": 0,
           "sources_clear": 1, "sources_close": 1, "nothing_clear_beside_clear": False, "cost_usd": 0.02}
    s = summary([row, dict(row, answer="recommend", cost_usd=0.04)])
    assert s["requests"] == 2 and s["answers"] == {"items": 1, "recommend": 1} and s["shown_things"] == 8
    assert s["dropped_as_junk"] == {"kind_word": 2} and s["cost_per_request"] == 0.03


def test_u4_the_kinds_set_holds_invented_requests_only():
    path = os.path.join(os.path.dirname(HERE), "evalset", "kinds_dev.jsonl")
    rows = [json.loads(x) for x in open(path, encoding="utf-8") if x.strip()]
    assert 12 <= len(rows) <= 20 and len({r["n"] for r in rows}) == len(rows)
    assert all(set(r) == {"n", "kind", "text"} and r["text"] == r["text"].lower() for r in rows)
    assert not any("@" in r["text"] or "http" in r["text"] for r in rows)
