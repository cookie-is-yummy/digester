"""The brain's thin live slice of step 2 (design/brain_v1/SPEC.md 3.4, 3.10, 4.5; DECISIONS 3, 4; the mvp20 brief):
brain/provider.py, brain/loop.py, brain/answer.py, prompts/brain_v1.md and eval_brain's `run` mode, with the FAKE
provider only. No model call, no network, no money. The library is the made-up one of tests/brain_library.py.
"""
import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_brain_tools import (  # noqa: E402,F401  (fixtures)
    NOW, TODAY, brain, built, no_real_keys, person)

OCT = {"by": "channel", "window": {"words": "in October", "preset": None, "same_as": None}}
TRUE_LEAD = "In October 2026, Clip Factory[r1.channels[0]] led with 61[r1.channels[0].items] videos."
TRUE_POINT = "Pan Theory[r1.channels[1]] came next with 32[r1.channels[1].items] videos."
FALSE_LEAD = "In October 2026, Clip Factory[r1.channels[0]] led with 60[r1.channels[0].items] videos."
FALSE_POINT = "Pan Theory[r1.channels[1]] came next with 33[r1.channels[1].items] videos."


@pytest.fixture()
def harness(brain):
    from mvp import eval_brain as E
    return E.Harness(brain["bot"], str(brain["lib"]), os.environ["MVP_DERIVED_HOME"], handle=person(brain)["handle"],
                     now=NOW)


def turn(h, message):
    from mvp.tests.fakes.fake_brain import FakeEngine, fake_learned
    return h.turn(message, search=FakeEngine(), learned=fake_learned)


def ga(lead, points=(), **kw):
    from mvp.brain import provider as P
    return P.tool_use("give_answer", dict({"lead": lead, "points": list(points)}, **kw))


def bd(args=OCT):
    from mvp.brain import provider as P
    return P.tool_use("breakdown", args)


def run(h, script, message="which channels did I watch the most in October?", **kw):
    from mvp.brain import loop as BL, provider as P
    prov = P.FakeProvider(list(script))
    t = turn(h, message)
    rec = BL.run_turn(prov, t, screen={"now": "Sun 22 Nov 2026 12:00"}, **kw)
    return rec, prov, t


def no_marker(text):
    return not re.search(r"\[(?:=|r\d)", text)


# ================================================================ the loop's rounds
def test_one_round_then_an_answer_that_passes_goes_out_as_the_models(harness):
    rec, prov, t = run(harness, [[bd()], [ga(TRUE_LEAD, [TRUE_POINT])]])
    assert rec["lead_source"] == "model" and rec["n_requests"] == 2 and rec["rounds"] == 1
    assert [c["name"] for c in rec["calls"]] == ["breakdown"] and rec["calls"][0]["rid"] == "r1"
    assert rec["answer"]["lead"] == "In October 2026, Clip Factory led with 61 videos."
    assert rec["answer"]["points"] == ["Pan Theory came next with 32 videos."]
    assert no_marker(rec["answer"]["text"]) and rec["sentences"] == {"written": 2, "kept_first_pass": 2,
                                                                       "kept_sent": 2}
    # the second request carries every tool_result, the result's cells at the top beside rid, tool and meta
    last = prov.sent[1][2][-1]
    assert last["role"] == "user" and last["content"][0]["type"] == "tool_result"
    body = json.loads(last["content"][0]["content"])
    assert body["rid"] == "r1" and "meta" in body and "channels" in body and "sheet" not in body
    assert body["channels"][0]["ref"] == "r1.channels[0]"
    # the ledger keeps the envelope untouched
    assert "sheet" in t.results["r1"] and rec["calls"][0]["result"] is t.results["r1"]


def test_give_answer_beside_read_calls_is_refused_and_the_reads_run(harness):
    from mvp.brain import loop as BL
    rec, prov, _t = run(harness, [[bd(), ga(TRUE_LEAD)], [ga(TRUE_LEAD)]])
    res = prov.sent[1][2][-1]["content"]
    assert [x.get("is_error", False) for x in res] == [False, True] and res[1]["content"] == BL.ALONE
    assert rec["lead_source"] == "model" and len(rec["forms"]) == 1


def test_rounds_run_out_then_time_is_up_once_then_the_code_lead(harness):
    from mvp.brain import loop as BL
    script = [[bd()], [bd()], [bd()], [ga(TRUE_LEAD)]]
    rec, prov, _t = run(harness, script, rounds=1)
    assert rec["rounds"] == 1 and "time_up" in rec["events"]
    assert prov.sent[2][2][-1]["content"][0]["content"] == BL.TIME_UP
    assert "tools_after_time_up" in rec["events"] and rec["lead_source"] == "code"
    assert no_marker(rec["answer"]["text"]) and rec["answer"]["lead"]


def test_the_soft_deadline_is_a_time_up_and_the_hard_stop_ends_the_turn(harness):
    from mvp.brain import loop as BL, provider as P
    clock = [0.0]
    prov = P.FakeProvider([{"blocks": [bd()], "seconds": 2.0}, {"blocks": [bd()], "seconds": 5.0},
                           {"blocks": [ga(TRUE_LEAD)], "seconds": 1.0}], clock=lambda s: clock.__setitem__(0, clock[0] + s))
    t = turn(harness, "which channels did I watch the most in October?")
    rec = BL.run_turn(prov, t, screen={}, now=lambda: clock[0])
    assert rec["events"] == ["time_up"] and rec["rounds"] == 1 and len(rec["calls"]) == 1
    assert rec["lead_source"] == "model" and rec["seconds"] == 8.0
    assert prov.sent[2][2][-1]["content"][0]["content"] == BL.TIME_UP
    prov = P.FakeProvider([{"blocks": [bd()], "seconds": 16.0}, [ga(TRUE_LEAD)]],
                          clock=lambda s: clock.__setitem__(0, clock[0] + s))
    clock[0] = 0.0
    rec = BL.run_turn(prov, turn(harness, "which channels did I watch the most in October?"), screen={},
                      now=lambda: clock[0])
    # 16 s for round 1: past the soft deadline no tool runs, then the hard stop; nothing in hand: the plain line
    assert rec["events"] == ["time_up", "hard_stop"] and rec["n_requests"] == 1 and rec["lead_source"] == "plain"


def test_text_with_no_call_gets_one_nudge(harness):
    from mvp.brain import loop as BL, provider as P
    rec, prov, _t = run(harness, [[bd()], [P.text("Clip Factory led.")], [ga(TRUE_LEAD)]])
    assert rec["events"] == ["nudge"] and prov.sent[2][2][-1] == {"role": "user", "content": BL.NUDGE}
    assert rec["lead_source"] == "model"
    rec, _p, _t = run(harness, [[bd()], [P.text("a")], [P.text("b")]])
    assert rec["events"] == ["nudge", "no_call_after_nudge"] and rec["lead_source"] == "code"


def test_a_provider_failure_ends_the_turn_with_what_is_in_hand(harness):
    from mvp.brain import provider as P
    rec, _p, _t = run(harness, [P.ProviderError("http 529 overloaded_error")])
    assert rec["error"] == "http 529 overloaded_error" and rec["lead_source"] == "plain"
    rec, _p, _t = run(harness, [[bd()], P.ProviderError("ClaudeTimeout")])
    assert rec["lead_source"] == "code" and no_marker(rec["answer"]["text"])


# ================================================================ the repair (SPEC 4.5) and the code lead
def test_a_failed_lead_gets_one_repair_as_the_is_error_result_of_give_answer(harness):
    from mvp.brain import verify as V
    first = ga(FALSE_LEAD, [TRUE_POINT])
    rec, prov, t = run(harness, [[bd()], [first], [ga(TRUE_LEAD, [TRUE_POINT])]])
    assert rec["lead_source"] == "model_after_repair" and rec["n_requests"] == 3
    rep = prov.sent[2][2][-1]["content"]
    assert rep == [{"type": "tool_result", "tool_use_id": first["id"], "content": rec["repair_message"],
                    "is_error": True}]
    assert "'60' is r1.channels[0].items = 61" in rec["repair_message"]
    assert rec["repair_message"] == V.repair_message(V.check_answer(first["input"], t.results, V.Turn.of(t)))
    assert rec["sentences"] == {"written": 2, "kept_first_pass": 1, "kept_sent": 2}
    assert rec["answer"]["lead"] == "In October 2026, Clip Factory led with 61 videos."


def test_a_lead_that_fails_its_repair_becomes_the_code_lead_with_the_points_that_passed(harness):
    from mvp.brain import fallback as FB, verify as V
    rec, _p, t = run(harness, [[bd()], [ga(FALSE_LEAD, [TRUE_POINT])], [ga(FALSE_LEAD, [TRUE_POINT])]])
    assert rec["lead_source"] == "code"
    want = FB.code_lead(t.results, turn=V.Turn.of(t))
    assert rec["answer"]["lead"] == want["lead"] and rec["answer"]["points"] == ["Pan Theory came next with 32 videos."]
    assert rec["sentences"] == {"written": 2, "kept_first_pass": 1, "kept_sent": 1}
    assert no_marker(rec["answer"]["text"])


def test_one_repair_only_and_a_failed_point_alone_is_dropped_without_one(harness):
    rec, _p, _t = run(harness, [[bd()], [ga(TRUE_LEAD, [FALSE_POINT])]])
    assert rec["lead_source"] == "model" and rec["repair_message"] is None and rec["answer"]["points"] == []
    assert rec["sentences"] == {"written": 2, "kept_first_pass": 1, "kept_sent": 1}
    # a repair round that calls a tool instead of give_answer ends the turn: no second repair, no fourth request
    rec, _p, _t = run(harness, [[bd()], [ga(FALSE_LEAD)], [bd()], [ga(TRUE_LEAD)]])
    assert rec["n_requests"] == 3 and "repair_without_answer" in rec["events"] and rec["lead_source"] == "code"


def test_an_invented_top_level_key_is_dropped_before_the_check_and_spends_no_repair(harness):
    # mvp20 tune: run1 spent 12 of its 30 repairs on keys like "understood_note": "x"; the key is left out (its value
    # is never read or sent) and the form is checked as it is
    rec, prov, _t = run(harness, [[bd()], [ga(TRUE_LEAD, [TRUE_POINT], understood_note="x", lead_fix=None)]])
    assert rec["repair_message"] is None and rec["lead_source"] == "model" and rec["n_requests"] == 2
    assert "form_keys_dropped" in rec["events"] and rec["dropped_keys"] == [["lead_fix", "understood_note"]]
    assert "understood_note" not in rec["forms"][0] and rec["sentences"]["kept_first_pass"] == 2


def test_a_form_that_does_not_validate_is_repaired_with_the_field_named(harness):
    # an unknown key INSIDE a field (an offer here) still fails validation and is named in the repair
    bad = ga(TRUE_LEAD, [TRUE_POINT])
    bad["input"]["offers"] = [{"kind": "by_month", "label_text": "x"}]
    rec, _p, _t = run(harness, [[bd()], [bad], [ga(TRUE_LEAD, [TRUE_POINT])]])
    assert "not a field of give_answer" in rec["repair_message"] and "label_text" in rec["repair_message"]
    assert rec["lead_source"] == "model_after_repair"
    assert rec["sentences"] == {"written": 2, "kept_first_pass": 0, "kept_sent": 2}


# ================================================================ answer.py: the private line and the scope line
PRIVATE_COUNT = "In 2024, you opened 8[r1.totals.items] videos."
Y2024 = {"by": "channel", "window": {"words": "in 2024", "preset": None, "same_as": None}}


def test_a_count_of_a_result_with_hidden_private_items_never_goes_out_without_the_private_line(harness):
    from mvp.brain import answer as A
    rec, _p, t = run(harness, [[bd(Y2024)], [ga(PRIVATE_COUNT)]], message="how many videos did I watch in 2024?")
    assert t.results["r1"]["meta"]["hidden"]["sensitive"] > 0
    assert rec["lead_source"] == "model" and rec["answer"]["lead"] == "In 2024, you opened 8 videos."
    assert rec["answer"]["private_line"] and A.PRIVATE_LINE in rec["answer"]["text"]
    # the code-lead path too: both forms fail, the code lead counts the same result
    bad = "In 2024, you opened 9[r1.totals.items] videos."
    rec, _p, t = run(harness, [[bd(Y2024)], [ga(bad)], [ga(bad)]], message="how many videos did I watch in 2024?")
    assert rec["lead_source"] == "code" and re.search(r"\d", rec["answer"]["lead"])
    assert rec["answer"]["private_line"] and A.PRIVATE_LINE in rec["answer"]["text"]
    # and no line where nothing private was left out
    rec, _p, _t = run(harness, [[bd()], [ga(TRUE_LEAD)]])
    assert not rec["answer"]["private_line"] and A.PRIVATE_LINE not in rec["answer"]["text"]


def test_the_scope_line_comes_whenever_the_result_was_filtered(harness):
    rec, _p, _t = run(harness, [[bd()], [ga(TRUE_LEAD)]])
    assert rec["answer"]["scope_line"] is None and "Counted:" not in rec["answer"]["text"]
    ex = dict(OCT, scope={"exclude": ["gaming"]})
    lead = "In October 2026, without gaming, Pan Theory[r1.channels[0]] led with 32[r1.channels[0].items] videos."
    rec, _p, t = run(harness, [[bd(ex)], [ga(lead)]], message="what about without gaming")
    assert t.results["r1"]["meta"]["filters_said"] == "without gaming (area)"
    assert rec["lead_source"] == "model"
    assert rec["answer"]["scope_line"].startswith("Counted: channels · what you opened · October 2026")
    assert rec["answer"]["scope_line"].endswith("· without gaming (area)")
    assert rec["answer"]["scope_line"] in rec["answer"]["text"]
    # a length filter is a filter too (the code lead's path: the scope line still comes)
    lg = dict(OCT, scope={"length": "long"})
    rec, _p, t = run(harness, [[bd(lg)], [P_text_only()], [P_text_only()]], message="only the long ones")
    assert rec["lead_source"] in ("code", "plain") and rec["answer"]["filtered"]
    assert rec["answer"]["scope_line"] and "long" in rec["answer"]["scope_line"]


def P_text_only():
    from mvp.brain import provider as P
    return [P.text("...")]


def test_offers_get_code_labels_and_bad_ones_are_dropped(harness):
    offers = [{"kind": "exclude", "ref": "r1.areas[0]", "window_words": None},
              {"kind": "only", "ref": "r9.areas[0]", "window_words": None},
              {"kind": "by_month", "ref": None, "window_words": None},
              {"kind": "length_long", "ref": None, "window_words": None}]
    rec, _p, _t = run(harness, [[bd()], [ga(TRUE_LEAD, offers=offers)]])
    assert [o["label"] for o in rec["answer"]["offers"]] == ["Without gaming?", "By month?"]
    assert rec["answer"]["text"].endswith("Without gaming? · By month?")


# ================================================================ follow-ups carry the screen
def test_a_follow_up_reuses_the_last_window_through_the_screen(harness):
    from mvp.brain import loop as BL, provider as P
    rec1, _p, t1 = run(harness, [[bd()], [ga(TRUE_LEAD)]])
    screen = BL.screen_after(rec1, "Sun 22 Nov 2026 12:00")
    assert screen["last_answer"]["plan"][0]["tool"] == "breakdown"
    assert screen["last_answer"]["plan"][0]["window_said"].startswith("October 2026")
    follow = {"by": "channel", "window": {"words": None, "preset": None, "same_as": "last"},
              "scope": {"exclude": ["gaming"]}}
    lead = "In October 2026, without gaming, Pan Theory[r1.channels[0]] led with 32[r1.channels[0].items] videos."
    prov = P.FakeProvider([[bd(follow)], [ga(lead)]])
    from mvp.tests.fakes.fake_brain import FakeEngine, fake_learned
    t2 = harness.turn("what about without gaming", last_window=BL.last_window(t1, rec1), search=FakeEngine(),
                      learned=fake_learned)
    rec2 = BL.run_turn(prov, t2, screen=screen)
    assert not rec2["calls"][0]["result"].get("is_error")
    assert t2.results["r1"]["sheet"]["window"]["start"] == "2026-10-01" and rec2["lead_source"] == "model"
    assert '"last_answer"' in prov.sent[0][2][0]["content"] and json.loads(t2.screen) == screen


# ================================================================ the prompt
PROMPT_KEPT = [
    (0, "In October 2026, Moss Garden[r1.channels[0]] led what you opened, with 61[r1.channels[0].items] of "
        "142[r1.totals.items] videos."),
    (0, "Kettle Craft[r1.channels[1]] came next with 32[r1.channels[1].items] videos."),
    (0, "Gardening[r1.areas[0]] was 51%[r1.areas[0].share] of what you opened, up 35 points[r1.areas[0].change_pts] on "
        "September 2026."),
    (1, "In the 4 weeks up to 30 October 2026, without gardening, travel[r1.areas[0]] led with 48%[r1.areas[0].share] "
        "of what you opened."),
    (1, "Without gardening, drinks[r1.areas[1]] came next at 45%[r1.areas[1].share], up 40 "
        "points[r1.areas[1].change_pts] on the 4 weeks before."),
]
# (ledger, a sentence of the failing shape, the words of it the prompt quotes)
PROMPT_DROPPED = [
    (0, "Out of 142 videos, Moss Garden[r1.channels[0]] led.", "Out of 142 videos, Moss Garden[r1.channels[0]] led."),
    (0, "61 of the 142 videos you opened[r1.channels[0].items] were from Moss Garden[r1.channels[0]].",
     "61 of the 142 videos you opened[r1.channels[0].items]"),
    (0, "Moss Garden[r1.channels[0]] made 61[r1.sheet.channels[0].items] videos.", "61[r1.sheet.channels[0].items]"),
    (0, "In October 2026[r1.meta.window_said], Moss Garden[r1.channels[0]] led.",
     "In October 2026[r1.meta.window_said]"),
    (0, "Travel[r1.areas[1]] had a drop of 46.5 points from before[=points(r1.areas[1].share, "
        "r1.areas[1].previous_share)].", "a drop of 46.5 points from before[=points(...)]"),
    (0, "Quiet Orbit[r1.channels[5]] dropped the most.", "Quiet Orbit[r1.channels[5]] dropped the most."),
    (0, "Kettle Craft came second, and Tidepool Tours made 29[r1.channels[2].items].",
     "Kettle Craft came second, and Tidepool Tours made 29[r1.channels[2].items]."),
]


def _norm(s):
    return " ".join(s.split())


def test_every_example_of_the_prompt_is_in_it_and_passes_or_fails_as_it_says(harness):
    from mvp.brain import loop as BL, verify as V
    from mvp.tests import brain_prompt_fixture as PF
    text = _norm(BL.system_text())
    ledgers = PF.ledgers(harness)
    vt = V.Turn(message="x", today=TODAY)
    for k, s in PROMPT_KEPT:
        assert _norm(s) in text, s
        where = "lead" if s.startswith("In ") else "point"
        o = V.check_sentence(s, V.Ledger(ledgers[k]), vt, where)
        assert o.kept, (s, o.reasons, o.details)
    for k, s, quoted in PROMPT_DROPPED:
        assert _norm(quoted) in text, quoted
        o = V.check_sentence(s, V.Ledger(ledgers[k]), vt, "point")
        assert not o.kept, s
    # the down-47-points fix of the prompt is true: 0.2394 - 0.7045 is -46.5
    fix = "Travel[r1.areas[1]] fell 47 points[=points(r1.areas[1].share, r1.areas[1].previous_share)] on September 2026."
    assert V.check_sentence(fix, V.Ledger(ledgers[0]), vt, "point").kept
    # the made-up names of the examples are in no library the tools read
    lib_names = {n.lower() for n in V.Turn.of(harness.turn("x")).names}
    for n in PF.RENAME.values():
        assert n.lower() not in lib_names, n


def test_the_tool_list_is_the_nine_read_tools_and_give_answer_with_the_form_schema():
    from mvp.brain import loop as BL, provider as P, tools as TL
    tl = BL.tool_list()
    assert [t["name"] for t in tl] == sorted(TL.REGISTRY[n].name for n in TL.REGISTRY
                                             if TL.REGISTRY[n].kind == "read") + ["give_answer"]
    sch = tl[-1]["input_schema"]
    assert sch["additionalProperties"] is False and "lead" in sch["properties"] and "from" in json.dumps(sch)
    defs = P.tool_defs(tl, strict=True, loose=P.LOOSE)
    assert [d.get("strict") for d in defs] == [True] * 9 + [None]
    assert json.dumps(BL.tool_list()) == json.dumps(tl)   # byte-stable (the cached prefix)


def test_the_anthropic_body_has_the_settings_of_the_skill_for_haiku_5_5():
    from mvp.brain import provider as P
    p = P.AnthropicProvider.__new__(P.AnthropicProvider)
    p.model, p.effort, p.max_tokens, p.thinking, p.strict, p.loose, p.cache = ("claude-haiku-5-5", "low", 4000,
                                                                              "adaptive", True, P.LOOSE, True)
    b = p.body("sys", [{"name": "give_answer", "description": "d", "input_schema": {"type": "object"}}],
               [{"role": "user", "content": "q"}])
    assert b["tool_choice"] == {"type": "auto"} and b["thinking"] == {"type": "adaptive"}
    assert b["output_config"] == {"effort": "low"} and b["cache_control"] == {"type": "ephemeral"}
    assert b["system"][0]["cache_control"] == {"type": "ephemeral"}   # 5 minutes: the price table's write rate
    for k in ("temperature", "top_p", "top_k", "fallbacks", "betas"):
        assert k not in b


# ================================================================ eval_brain run: the split and the summary
def test_the_split_is_sha1_of_the_conversation_id_and_is_pinned():
    from mvp import eval_brain as E
    import hashlib
    plans = E.load_jsonl(E.PLANS)
    for p in plans:
        want = "tune" if int(hashlib.sha1(p["id"].encode()).hexdigest(), 16) % 2 == 0 else "heldout"
        assert E.half_of(p["id"]) == want
    tune, held = E.run_set("tune"), E.run_set("heldout")
    assert len(tune) == 34 and len(held) == 42
    assert {p["id"] for p, _c in tune}.isdisjoint({p["id"] for p, _c in held})
    n = lambda s: sum(1 for p, _c in s for m in p["messages"] if m["tier"] == "plan")  # noqa: E731
    assert n(tune) == 38 and n(held) == 53
    assert E.half_of("A02") == "tune" and E.half_of("B04") == "tune" and E.half_of("A01") == "heldout"
    assert [p["id"] for p, _c in E.run_set("tune", limit=3)] == ["A02", "B04", "B06"]
    assert [p["id"] for p, _c in E.run_set("tune", ids={"C05"})] == ["C05"]


def _rec(key, src, written, first, sent, secs, cost, g2="understood", findings=(), dropped=()):
    return {"key": key, "id": key.split(".")[0], "n": int(key.split(".")[1]), "lead_source": src,
            "sentences": {"written": written, "kept_first_pass": first, "kept_sent": sent}, "seconds": secs,
            "cost_usd": cost, "g2": {"verdict": g2, "diffs": []}, "audit": {"checked": 3, "findings": list(findings)},
            "dropped": list(dropped), "requests": [{"stop_reason": "tool_use", "retries": 0,
                                                    "usage": {"input_tokens": 1, "output_tokens": 2,
                                                              "cache_read_input_tokens": 3,
                                                              "cache_creation_input_tokens": 4}}],
            "events": [], "repair_message": "x" if src == "model_after_repair" else None, "error": None}


def test_the_summary_arithmetic():
    from mvp import eval_brain as E
    recs = [_rec("A.0", "model", 4, 4, 4, 2.0, 0.001),
            _rec("B.0", "model_after_repair", 4, 2, 3, 5.0, 0.003, g2="other_plan"),
            _rec("C.0", "code", 2, 0, 1, 8.0, 0.002, g2="differs", findings=[{"kind": "value"}],
                 dropped=[{"reasons": ["wrong_value"]}, {"reasons": ["wrong_value", "base"]}]),
            _rec("D.0", "plain", 0, 0, 0, 12.0, 0.0, g2="no_hand_plan"),
            {"id": "E", "n": 0, "skipped": "budget"}]
    s = E.summarize(recs)
    assert s["messages"] == 4 and s["skipped"] == ["E.0"]
    assert s["G3_own_lead"]["own"] == 2 and s["G3_own_lead"]["share"] == 0.5
    assert s["G2_understood"]["understood"] == 1 and s["G2_understood"]["other_plan"] == 1
    assert s["G2_understood"]["share"] == round(1 / 3, 4)                    # no_hand_plan is left out
    assert s["G4_sentences"]["written"] == 10 and s["G4_sentences"]["missing_first_pass"] == 0.4
    assert s["G4_sentences"]["missing_after_repair"] == 0.2
    assert s["G5_seconds"]["median"] == 6.5 and s["G5_seconds"]["p90"] == 10.8
    assert s["G6_cost"]["mean_cents"] == 0.15 and s["G6_cost"]["total_usd"] == 0.006
    assert s["G1_auditor"]["findings"] == 1 and list(s["G1_auditor"]["by_message"]) == ["C.0"]
    assert s["dropped_reasons"] == {"wrong_value": 2, "base": 1} and s["repairs"] == 1
    assert s["requests"]["count"] == 4 and s["requests"]["cache_read_input_tokens"] == 12


def test_g2_compares_window_base_scope_and_order_and_keeps_other_plans_apart():
    from mvp import eval_brain as E
    k = {"tool": "breakdown", "what": "channel", "window": ["2026-10-01", "2026-10-30"], "base": "of what you opened",
         "scope": [], "order": "most"}
    assert E.compare_plans([k], [dict(k)])["verdict"] == "understood"
    assert E.compare_plans([k], [dict(k), dict(k, tool="find")])["verdict"] == "understood"   # extra calls are fine
    o = E.compare_plans([k], [dict(k, what="area")])
    assert o["verdict"] == "other_plan" and o["diffs"][0]["differs"] == ["what"]
    d = E.compare_plans([k], [dict(k, window=["2026-10-03", "2026-10-30"])])
    assert d["verdict"] == "differs" and d["diffs"][0]["differs"] == ["window"]
    assert E.compare_plans([k], [dict(k, scope=["without gaming (area)"])])["verdict"] == "differs"
    assert E.compare_plans([k], [dict(k, order="least")])["verdict"] == "differs"
    assert E.compare_plans([k], [])["verdict"] == "differs"
    assert E.compare_plans([], [k])["verdict"] == "no_hand_plan"


def test_g2_reads_both_windows_of_a_compare(harness):
    from mvp import eval_brain as E
    from mvp.brain import tools as TL
    msg = "compare this autumn with last autumn, and with 2024"
    t = harness.turn(msg)
    right = {"a": {"words": "this autumn"}, "b": {"words": "last autumn"}, "by": "area"}
    wrong = {"a": {"words": "this autumn"}, "b": {"words": "2024"}, "by": "area"}
    r1, r2 = TL.call(t, "compare", right), TL.call(t, "compare", wrong)
    k1, k2 = E.call_key("compare", right, r1), E.call_key("compare", wrong, r2)
    assert k1["window"][:2] == k2["window"][:2] and k1["window"][2:] != k2["window"][2:]
    assert k1["window"][2] == "2025-09-01" and None not in k1["window"]
    assert E.compare_plans([k1], [k2])["verdict"] == "differs"
    assert E.compare_plans([k1], [k2, dict(k1)])["verdict"] == "understood"


def test_the_decomposition_reads_the_first_form_that_validated():
    from mvp import eval_brain as E
    out = {"outcomes": [{"where": "lead", "kept": True}, {"where": "point", "kept": False}]}
    r = _rec("A.0", "code", 2, 0, 0, 1.0, 0.0)
    r["verdicts"] = [{"form_error": "extra_forbidden", "outcomes": []}, dict(out, form_error=None)]
    d = E.summarize([r])["decomposition"]
    assert d["repairs_on_a_form_error"] == 1 and d["not_own_whose_repair_went_on_a_form_error"] == ["A.0"]
    assert d["first_valid_form_written"] == 2 and d["first_valid_form_kept"] == 1 and d["first_valid_form_missing"] == 0.5


def test_run_refuses_without_a_key(monkeypatch, capsys):
    from mvp import eval_brain as E
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DIGESTER_ANTHROPIC_API_KEY", raising=False)
    assert E.main(["run", "--half", "tune", "--out", "/nonexistent"]) == 2
    assert "nothing was sent" in capsys.readouterr().err


def test_present_lifts_the_sheet_and_keeps_it_nested_on_a_clash():
    from mvp.brain import loop as BL
    env = {"rid": "r1", "tool": "breakdown", "meta": {"a": 1}, "sheet": {"totals": {"items": 3}}, "cost_usd": 0}
    assert json.loads(BL.present(env)) == {"rid": "r1", "tool": "breakdown", "meta": {"a": 1}, "totals": {"items": 3}}
    env["sheet"]["meta"] = {"x": 1}
    assert "sheet" in json.loads(BL.present(env))
    assert json.loads(BL.present({"is_error": True, "error": "no"})) == {"error": "no", "is_error": True}


def test_the_auditor_reads_each_sent_sentence_against_the_result_it_cites(harness):
    from mvp import eval_brain as E
    point = "In 2024, you opened 8[r2.totals.items] videos."
    rec, _p, t = run(harness, [[bd(), bd(Y2024)], [ga(TRUE_LEAD, [point])]],
                     message="which channels did I watch most in October, and how many videos in 2024?")
    assert rec["lead_source"] == "model" and rec["sentences"]["kept_sent"] == 2, rec["verdicts"]
    bad, checked = E.audit_sent(harness, t.results, t.unlock, rec, rec["message"])
    assert checked > 0 and bad == []
    # a false cell is found (the auditor's own recount, not the verifier's)
    rec["verdicts"][0]["outcomes"][1]["text"] = "In 2024, you opened 9[r2.totals.items] videos."
    bad, _n = E.audit_sent(harness, t.results, t.unlock, rec, rec["message"])
    assert any(b["kind"] == "value" and str(b["said"]).endswith("9") for b in bad)
