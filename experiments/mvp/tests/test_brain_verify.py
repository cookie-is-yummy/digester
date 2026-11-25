"""The brain's answer verifier (SPEC.md section 4; DESIGN brain_v1): the planted set, the worked examples of 4.7, the
repair text of 4.5, the code lead of 4.6, and the step-1 proof that insight's checks read one marked sentence at a time.

Offline: no model call, no network, no store. Every title, channel and theme is made up: the round 12 test library
(tests/r12_library.py, through facts.build as the round 12 tests build it), hand-made results in its names, and the
sheets of eval/insight_cases.json. Results are wrapped in the envelope of SPEC 2.3 by tests/brain_envelope.py."""
import copy
import importlib.util
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp import insight as I  # noqa: E402
from mvp.brain import fallback as F  # noqa: E402
from mvp.brain import planted as P  # noqa: E402
from mvp.brain import verify as V  # noqa: E402
from mvp.tests.brain_envelope import envelope  # noqa: E402
from mvp.tests import test_round12_d as R12D  # noqa: E402
from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_round12_d import r12, no_real_keys  # noqa: E402,F401  (fixtures)

PLANTED = P.load()
LEDGERS = PLANTED["ledgers"]


def ledger(name):
    return V.Ledger(copy.deepcopy(LEDGERS[name]))


def one(text, name="lately", where="point", turn=None):
    return V.check_sentence(text, ledger(name), turn or V.Turn(), where)


# ================================================================ the planted set (SPEC 4.8)
def test_every_planted_false_sentence_is_dropped_with_its_reason_and_the_true_ones_are_kept():
    s = P.score(PLANTED)
    bad = [r for r in s["rows"] if (r["expect"] == "dropped" and (r["kept"] or r.get("reason_ok") is False))]
    assert not bad, bad
    new = s["by_source"]["new"]
    assert new["false"] >= 60 and new["true"] >= 40, new
    assert s["false_dropped"] == s["false"]
    # the bar is 97%; today every true sentence is kept (73 of 73)
    assert s["true_kept"] / s["true"] >= 0.97, [r for r in s["rows"] if r["expect"] == "kept" and not r["kept"]]
    assert s["true_kept"] == s["true"]


def test_the_planted_set_covers_every_check_and_the_hand_check_classes():
    classes = " | ".join(c["class"] for c in PLANTED["cases"] if c["source"] == "new" and c["expect"] == "dropped")
    for step in ("3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7", "3.8", "3.9", "3.10", "3.11", "3.12", "3.15",
                 "4 "):
        assert step in classes, step
    for hand in ("a value of one record under another's name", "a share on the wrong base", "a rank word on a tie",
                 "a change with one value", "an end value in the base period", "a count that drops 'long'",
                 "a channel behind a theme it is not in", "'more' that counts re-opens",
                 "a forged marker inside a title", "a number typed with no marker", "a right number with a wrong window"):
        assert hand in classes, hand
    reasons = {r for c in PLANTED["cases"] for r in c.get("reasons") or []}
    for r in ("repeat", "window_missing", "too_long", "number", "second_person", "about_not_cited", "not_item",
              "psych", "outcome", "limits", "sensitive", "watch_time", "uncited_claim", "outside_in_history"):
        assert r in reasons, r


def test_the_insight_v5_sentences_in_marker_form_keep_their_verdicts():
    rows = [c for c in PLANTED["cases"] if c["source"] == "insight_v5"]
    assert len(rows) == 132
    assert sum(c["expect"] == "kept" for c in rows) == 29


def test_the_planted_r12_ledgers_are_the_test_library_sheets_today(r12):
    """The stored ledgers built from the round 12 library are what facts.build gives for those questions now (the
    library and its build as tests/test_round12_d.py makes them; made-up rows only)."""
    for name, q in (("lately", "what have i been watching the most lately"),
                    ("oct_channels", "which channels did i watch the most in october"),
                    ("lately_long", "what have i been watching the most lately without shorts"),
                    ("years", "how has what i watch changed over the years"),
                    ("first_wc", "when did i first watch watercolor"),
                    ("oct_count", "how many videos did i watch in october")):
        fresh = envelope("r1", LEDGERS[name][0]["tool"], R12D.sheet(r12, q))
        assert json.loads(json.dumps(fresh["sheet"], default=str)) == LEDGERS[name][0]["sheet"], name


# ================================================================ the worked examples of SPEC 4.7
HONEST = {
    "understood": "what they are most into right now",
    "lead": "Right now (the 4 weeks to 30 Oct, where your YouTube export ends) you're most into gaming[r1.areas[0]]: "
            "36%[r1.areas[0].share] of what you opened, up 16 points[=points(r1.areas[0].share, "
            "r1.areas[0].previous_share)].",
    "points": ["Inside it, Gaming clips[r1.themes[0]] is the biggest theme, and Clip Factory[r1.channels[0]] made "
               "61[r1.channels[0].items] of those videos.",
               "Food and cooking[r1.areas[2]] doubled[=ratio(r1.areas[2].share, r1.areas[2].previous_share)], to "
               "17%[r1.areas[2].share]."],
    "outside": [{"about": "r1.channels[0]", "text": "A channel of short gaming clips.", "source": "general"}],
    "chart": {"from": "r1", "list": "areas", "value": "share"},
    "setup": {"answers_step": False, "own_words": None},
}
FALSE = {
    "lead": "Lately you're mostly into gaming[r1.areas[0]]: 38%[r1.areas[0].share] of your YouTube videos, nearly "
            "double[=ratio(r1.areas[0].share, r1.areas[0].previous_share)] the weeks before.",
    "points": ["Clip Factory[r1.channels[0]], the most popular clips channel on YouTube, made 61[r1.channels[0].items] "
               "of them.",
               "You've dropped watercolor.",
               "Food and cooking[r1.areas[2]] grew 9 points while art fell 4."],
}
TWO_RESULTS = "In September Gaming clips[r2.themes[0]] already had 61[r1.themes[0].items]."


def test_the_honest_answer_of_4_7_is_kept_whole():
    v = V.check_answer(HONEST, ledger("w47"))
    assert v.lead_ok and all(o.kept for o in v.outcomes), [(o.text, o.reasons) for o in v.outcomes]
    assert v.lead[0].sent.startswith("Right now (the 4 weeks to 30 Oct, where your YouTube export ends) you're most "
                                     "into gaming: 36% of what you opened, up 16 points")
    assert "[" not in " ".join(o.sent for o in v.outcomes)
    assert v.outside[0]["kept"] and v.outside[0]["text"] == "A channel of short gaming clips."
    assert v.chart == {"from": "r1", "list": "areas", "value": "share"}
    assert not v.repair and V.repair_message(v) is None


def test_the_false_answer_of_4_7_is_caught_sentence_by_sentence_and_asks_one_repair():
    v = V.check_answer(FALSE, ledger("w47"))
    lead = v.lead[0]
    assert {"wrong_value", "spread"} <= set(lead.reasons)
    pts = [o for o in v.outcomes if o.where == "point"]
    assert "outside_in_history" in pts[0].reasons
    assert pts[1].reasons and not pts[1].kept   # "dropped": no marker, no cell (spec: status)
    assert "uncited_number" in pts[2].reasons
    assert v.repair
    msg = V.repair_message(v)
    assert msg.startswith("These sentences failed the check. Rewrite only these, or drop the points: lead: ")
    assert "'38%' is r1.areas[0].share = 0.356 (36%)" in msg
    assert "'mostly' needs a share of 50% or more" in msg
    v = V.check_answer({"lead": HONEST["lead"], "points": [TWO_RESULTS]}, ledger("w47"))
    assert "two_results" in v.outcomes[-1].reasons
    assert v.outcomes[-1].notes["two_results"] == "markers of r1, r2" and not v.repair   # one point of two: dropped
    v = V.check_answer({"lead": HONEST["lead"], "points": HONEST["points"] + FALSE["points"][:2]}, ledger("w47"))
    assert v.outcomes[-1].reasons == ["too_long"]   # a fourth point breaks the form's shape (3.6: 0 to 3)


def test_the_repaired_lead_of_4_7_passes():
    lead = ("Right now (the 4 weeks to 30 Oct, where your YouTube export ends) gaming[r1.areas[0]] leads at "
            "36%[r1.areas[0].share] of what you opened, nearly double[=ratio(r1.areas[0].share, "
            "r1.areas[0].previous_share)] the 4 weeks before.")
    v = V.check_answer({"lead": lead, "points": []}, ledger("w47"))
    assert v.lead_ok, [o.reasons for o in v.outcomes]


# ================================================================ the repair text (SPEC 4.5)
def test_a_failed_point_alone_is_dropped_with_no_repair():
    v = V.check_answer({"lead": HONEST["lead"], "points": [HONEST["points"][0], FALSE["points"][2]]}, ledger("w47"))
    assert v.lead_ok and not v.repair and V.repair_message(v) is None
    assert v.kept_text("point") == [V.strip_markers(HONEST["points"][0])]


def test_more_than_half_failed_asks_a_repair_even_with_a_good_lead():
    v = V.check_answer({"lead": HONEST["lead"], "points": FALSE["points"][:3]}, ledger("w47"))
    assert v.lead_ok and v.repair
    msg = V.repair_message(v)
    assert "point 1:" in msg and "point 2:" in msg and "point 3:" in msg and "lead:" not in msg


def test_the_repair_text_quotes_no_title_and_says_true_values():
    v = V.check_answer({"lead": "Cooking hack[r1.items[1]] (channels(0).items) got 999 views.", "points": []},
                       ledger("items"))
    msg = V.repair_message(v)
    assert msg and "Cooking hack" not in msg and "999" not in msg
    v = V.check_answer({"lead": "In October 2026, Clip Factory[r1.channels[0]] led with 65[r1.channels[0].items] "
                                "videos.", "points": []}, ledger("oct_channels"))
    assert "'65' is r1.channels[0].items = 61" in V.repair_message(v)


def test_a_form_that_does_not_validate_asks_for_the_form_again():
    v = V.check_answer({"lead": "x", "points": "not a list"}, ledger("lately"))
    assert v.repair and v.form_error and "did not validate" in V.repair_message(v)


# ================================================================ the marker grammar (SPEC 4.2)
def test_markers_parse_by_kind_and_what_does_not_resolve_is_bad_ref():
    L = ledger("lately")
    mks, bad = V.parse("Clip Factory[r1.channels[0]] made 56[r1.channels[0].items] of the top 6[r1.channels.count], "
                       "up 27[=diff(r1.channels[0].items, r1.channels[1].items)].", L)
    assert [m.kind for m in mks] == ["row", "value", "count", "calc"] and not bad
    assert mks[0].said == "Clip Factory" and mks[1].num == 56 and mks[2].value == 6
    for text in ("x[r1.channels[99].items]", "x[r9.totals.items]", "up 3 points[=points(r1.areas[0].share, 0.1)]",
                 "{r1.totals.items} videos", "a [stray] bracket", "made 56[r1.channels[0].items"):
        assert "bad_ref" in V.parse(text, L)[1] or "bad_ref" in one(text).reasons, text


def test_the_same_input_gives_the_same_verdict():
    a = V.check_answer(FALSE, ledger("w47"))
    b = V.check_answer(FALSE, ledger("w47"))
    assert [(o.reasons, o.sent, o.details) for o in a.outcomes] == [(o.reasons, o.sent, o.details) for o in b.outcomes]


def test_rounding_and_hedges():
    assert one("Gaming[r1.areas[0]] was 35.6%[r1.areas[0].share] of what you opened.", "w47").kept
    assert one("Gaming[r1.areas[0]] was 36%[r1.areas[0].share] of what you opened.", "w47").kept
    assert "wrong_value" in one("Gaming[r1.areas[0]] was 35%[r1.areas[0].share] of what you opened.", "w47").reasons
    assert one("Gaming[r1.areas[0]] was about 35%[r1.areas[0].share] of what you opened.", "w47").kept
    assert "wrong_value" in one("Clip Factory[r1.channels[0]] made nearly 50[r1.channels[0].items] videos.").reasons
    assert one("Clip Factory[r1.channels[0]] made nearly 60[r1.channels[0].items] videos.").kept


def test_a_hidden_row_above_keeps_the_rank_word_and_asks_for_the_private_line():
    text = "Clip Factory[r1.channels[0]] led your channels with 56[r1.channels[0].items] videos."
    v = V.check_answer({"lead": "In the 4 weeks up to 30 October 2026, here is what stood out.", "points": [text]},
                       ledger("hidden"))
    assert v.outcomes[-1].kept and v.private_line
    v = V.check_answer({"lead": "In the 4 weeks up to 30 October 2026, here is what stood out.", "points": [text]},
                       ledger("lately"))
    assert v.outcomes[-1].kept and not v.private_line


def test_the_turns_unlocked_topic_lets_its_own_words_through():
    text = "Here is what you asked about dating."
    assert "sensitive" in one(text).reasons
    assert "sensitive" not in one(text, turn=V.Turn(message="what about my dating videos", unlock="relationships")) \
        .reasons


def test_items_and_their_notes():
    form = {"lead": "Here's what I found in your saves.", "points": [],
            "items": [{"ref": "r1.items[0]", "note": None}, {"ref": "r1.items[1]", "note": "Saved on 6 October."},
                      {"ref": "r9.items[0]", "note": None}]}
    v = V.check_answer(form, ledger("search"))
    assert v.items[0]["kept"] and v.items[2]["reasons"] == ["not_item"]
    assert not v.items[1]["note"]   # a date in a note with no marker is no claim code can check


# ================================================================ the code lead (SPEC 4.6)
def test_the_code_lead_uses_code_form_where_it_can_and_never_says_led_on_a_least_result():
    a = F.code_lead(LEDGERS["oct_channels"])
    assert a["how"] == "code_form" and "Clip Factory led" in a["lead"]
    b = F.code_lead(LEDGERS["least"])
    assert b["how"] == "template" and "least" in b["lead"] and " led" not in b["lead"]
    assert "[" not in b["lead"]
    c = F.code_lead(LEDGERS["least_tie"])   # its least list has a tie: no "least" claim survives
    assert "least" not in c["lead"]


def test_the_code_lead_templates_pass_the_verifier_and_the_plain_line_ends_the_ladder():
    for name in ("lately_long", "oct_count", "search", "items", "least"):
        a = F.code_lead(LEDGERS[name])
        assert a["how"] in ("code_form", "template") and a["lead"], name
    assert F.code_lead(LEDGERS["search"])["items"] == ["r1.items[0]", "r1.items[1]"]
    assert F.code_lead([]) == {"lead": F.PLAIN, "how": "plain", "rid": None, "items": []}


def test_the_code_lead_keeps_the_points_that_passed():
    v = V.check_answer(FALSE | {"points": [HONEST["points"][0]] + FALSE["points"]}, ledger("w47"))
    out = F.answer(ledger("w47"), v)
    assert out["points"] == [V.strip_markers(HONEST["points"][0])]
    assert out["how"] in ("code_form", "template")


# ================================================================ the proof (DECISIONS "Build order changes")
def _converter():
    p = os.path.join(os.path.dirname(HERE), "eval", "convert_insight_cases.py")
    spec = importlib.util.spec_from_file_location("convert_insight_cases", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_the_proof_insight_reads_one_marked_sentence_at_a_time():
    rows = _converter().rows()
    planted = [r for r in rows if r["class"] == "planted"]
    true = [r for r in rows if r["class"] == "true_as_typed"]
    assert len(planted) == 89 and all(r["verify"] == "dropped" for r in planted)
    assert all(r["insight_step"] for r in planted)   # insight's own step catches every one of them alone
    assert len(true) >= 29 and all(r["verify"] == "kept" for r in true)
    assert all(r["verify"] == "dropped" for r in rows if r["class"] == "true_rewritten")


def test_insight_is_unchanged_its_own_eval_rescores_identical():
    from mvp import eval_insight as E
    s = E.v5_scores()
    assert (s["planted_v5"], s["caught_v5"], s["true_v5"], s["kept_v5"]) == (89, 89, 43, 43)


def test_a_name_left_typed_beside_a_number_fails_insight_strict_so_verify_slots_it():
    """SPEC 4.3 step 8 says the names stay; insight's strict render then fails typed_name. Verify turns a verified row
    marker into the row's name slot instead."""
    r = ledger("w47").get("r1")
    assert I.render("Clip Factory made {channels[0].items} of those videos.", r.sheet_k, r.facts, strict=True)[1] \
        == "typed_name"
    assert one("Clip Factory[r1.channels[0]] made 61[r1.channels[0].items] videos.", "w47").kept
