"""mvp35 (DESIGN 34): a private topic carried into a follow-up is said to be private. On a follow-up that does not
name the private topic the answer before resolved a name to (tools.Turn.carried_only), code adds one line under an
answer that includes it ("Includes the private topic you asked about."), whenever a result behind the answer that goes
out counted or showed it. Made-up library (tests/brain_library.py: its private topic and that topic's one channel) and
made-up messages only; no model call.
"""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from mvp.tests.test_brain_r30_tools import (  # noqa: E402,F401  (fixtures)
    S,
    W,
    brain,
    built,
    call,
    env,
    harness,
    local,
    no_real_keys,
    person,
    visible_rows,
)

NAMED = "how many dating videos did i open in 2024"      # names the private topic (the library's "dating")
FOLLOW = "and which month had the most"                  # names none
FOLLOW2 = "and the newest few"                           # names none
TOPIC = "relationships"                                  # the topic the library's "dating" resolves to
CHANNEL = "Heart Notes"                                  # the library's one channel wholly of the topic
Y24 = W("in 2024")
# the screen the follow-up reads holds the window's digits, as the answer before left them (window words are theirs)
SCREEN = json.dumps({"last_answer": {"plan": [{"window_said": "2024"}, {"window_said": "2023"}]}})


def _A():
    from mvp.brain import answer as A
    return A


def _carried(brain, message=FOLLOW, **kw):
    """A tools.Turn of a follow-up that carries the topic and does not name it."""
    from mvp.tests.test_brain_tools import turn
    t = turn(brain, message, carried_unlock=TOPIC, screen=SCREEN, **kw)
    assert t.unlock == TOPIC and t.carried_only
    return t


def _call(t, name, args):
    from mvp.brain import tools as TL
    env_ = TL.call(t, name, args)
    assert not env_.get("is_error"), env_
    return env_


def _out(t, form, mode="values"):
    """The answer that goes out for one model form, through loop._finish (as run_turn sends it)."""
    from mvp.brain import loop as BL
    from mvp.brain import verify as V
    cm = V.check_mode(mode)
    v = V.check_answer(form, t.results, V.Turn.of(t), mode=cm)
    rec = {"forms": [form], "events": []}
    BL._finish(rec, t, V.Turn.of(t), [v], cm)
    return rec, v


def _only(name="dating", **kw):
    return S(only=[name], **kw)


# ================================================================ 1. the line, through each tool that can include it
CALLS = {
    "breakdown": {"by": "none", "compare": "none", "order": "most", "top": 5, "window": Y24, "scope": None},
    "timeline": {"unit": "month", "window": Y24, "scope": None},
    "changes": {"level": "channel", "window": Y24, "scope": None},
    "compare": {"a": Y24, "b": W("in 2023"), "by": "none", "scope": None},
    "items": {"limit": 3, "order": "newest", "window": Y24, "scope": None},
}


@pytest.mark.parametrize("tool", sorted(CALLS))
@pytest.mark.parametrize("name", ["dating", CHANNEL])
def test_a_count_scoped_to_the_carried_topic_marks_its_result_and_the_answer_gets_the_line(brain, tool, name):
    A = _A()
    t = _carried(brain)
    args = dict(CALLS[tool], scope=_only(name))
    env_ = _call(t, tool, args)
    assert t.carried_in == {env_["rid"]}
    rec, _v = _out(t, {"lead": "Here is what that shows.", "points": []})
    a = rec["answer"]
    assert a["carried_line"] and A.CARRIED_LINE in a["text"].split("\n")
    assert rec["carried_in"] == [env_["rid"]]
    # the line names no topic, and no other private line is said beside it
    assert TOPIC not in A.CARRIED_LINE.lower() and "dating" not in A.CARRIED_LINE.lower()
    assert A.PRIVATE_LINE not in a["text"]


def test_first_last_and_find_and_learned_of_the_topic_mark_their_results(brain):
    from mvp.tests.fakes.fake_brain import fake_learned
    t = _carried(brain, learned=fake_learned)
    fl = _call(t, "first_last", {"subject": "dating", "which": "first"})
    fn = _call(t, "find", {"names": ["dating"]})
    ln = _call(t, "learned", {"topic": "dating"})
    assert ln["sheet"].get("on_topic"), "the learned result shows the topic as a row"
    assert t.carried_in == {fl["rid"], fn["rid"], ln["rid"]}
    for rid in sorted(t.carried_in):
        # a sentence that cites the one result: the line follows that result
        sheet = t.results[rid]["sheet"]
        ref = (sheet.get("names") or [{}])[0].get("row") or (sheet.get("on_topic") or [{}])[0].get("ref") or \
            (sheet.get("items") or [{}])[0].get("ref")
        assert ref, rid
        rec, v = _out(t, {"lead": f"That is the one[{ref}].", "points": []})
        assert v.lead_ok and rec["answer"]["carried_line"], rid
        assert _A().CARRIED_LINE in rec["answer"]["text"].split("\n")


def test_find_marks_a_name_whose_count_holds_the_topic_and_not_one_that_holds_none(brain):
    t = _carried(brain)
    ch = _call(t, "find", {"names": [CHANNEL]})
    assert ch["sheet"]["names"][0]["matches"][0]["items_all_time"] > 0
    other = _call(t, "find", {"names": ["cooking"]})
    assert ch["rid"] in t.carried_in and other["rid"] not in t.carried_in


def test_a_search_under_the_carry_leaves_the_topics_items_out_and_marks_nothing(brain):
    from mvp.tests.fakes.fake_brain import FakeEngine
    t = _carried(brain, search=FakeEngine())
    env_ = _call(t, "search", {"query": "dating advice first date", "how": "opened"})
    assert not any(t.carried_hidden(x["item_id"]) for x in env_["sheet"]["items"])
    assert t.carried_in == set()
    rec, _v = _out(t, {"lead": "Here is what that shows.", "points": []})
    assert not rec["answer"]["carried_line"] and "carried_in" not in rec


# ================================================================ 2. not where the topic is not behind the answer
def test_a_total_not_scoped_to_the_topic_is_not_marked_and_says_the_private_line_alone(brain):
    A = _A()
    t = _carried(brain)
    tot = _call(t, "breakdown", dict(CALLS["breakdown"], scope=S()))
    assert tot["meta"]["hidden"]["sensitive"] > 0 and t.carried_in == set()
    n = tot["sheet"]["totals"]["items"]
    rec, _v = _out(t, {"lead": f"In 2024 you opened {n}[{tot['rid']}.totals.items] videos.", "points": []})
    a = rec["answer"]
    assert a["private_line"] and not a["carried_line"]
    assert A.PRIVATE_LINE in a["text"].split("\n") and A.CARRIED_LINE not in a["text"]


def test_the_line_follows_the_result_behind_the_answer_not_every_result_of_the_turn(brain):
    t = _carried(brain)
    tot = _call(t, "breakdown", dict(CALLS["breakdown"], scope=S()))
    top = _call(t, "breakdown", dict(CALLS["breakdown"], scope=_only()))
    assert t.carried_in == {top["rid"]}
    n = tot["sheet"]["totals"]["items"]
    # the sentence that goes out cites the total only: the topic's result is not behind it
    rec, _v = _out(t, {"lead": f"In 2024 you opened {n}[{tot['rid']}.totals.items] videos.", "points": []})
    assert not rec["answer"]["carried_line"]
    # a refused sentence of the topic's result does not bring the line in either
    bad = top["sheet"]["totals"]["items"] + 7
    rec, v = _out(t, {"lead": f"In 2024 you opened {n}[{tot['rid']}.totals.items] videos.",
                      "points": [f"Of those, {bad}[{top['rid']}.totals.items] were on that topic."]})
    assert [o.kept for o in v.outcomes if o.where == "point"] == [False]
    assert not rec["answer"]["carried_line"]


def test_no_line_when_the_message_names_the_topic(brain):
    from mvp.tests.test_brain_tools import turn
    t = turn(brain, NAMED, carried_unlock=TOPIC)
    assert t.unlock == TOPIC and not t.carried_only
    env_ = _call(t, "breakdown", dict(CALLS["breakdown"], scope=_only()))
    assert t.carried_in == set()
    rec, _v = _out(t, {"lead": f"You opened {env_['sheet']['totals']['items']}[{env_['rid']}.totals.items] videos.",
                       "points": []})
    assert not rec["answer"]["carried_line"] and _A().CARRIED_LINE not in rec["answer"]["text"]


def test_no_line_on_a_turn_with_no_unlock(brain):
    from mvp.tests.test_brain_tools import turn
    t = turn(brain, FOLLOW, screen=SCREEN)
    assert t.unlock is None and not t.carried_only
    env_ = _call(t, "breakdown", dict(CALLS["breakdown"], scope=S()))
    rec, _v = _out(t, {"lead": f"You opened {env_['sheet']['totals']['items']}[{env_['rid']}.totals.items] videos.",
                       "points": []})
    assert t.carried_in == set() and not rec["answer"]["carried_line"]


def test_the_topic_left_out_by_scope_exclude_is_not_marked(brain):
    t = _carried(brain)
    _call(t, "breakdown", dict(CALLS["breakdown"], scope=S(exclude=["dating"])))
    assert t.carried_in == set()


# ================================================================ 3. every way an answer goes out
def test_code_lead_and_time_up_and_reword_carry_the_line_and_the_plain_line_does_not(brain):
    from mvp.brain import fallback as FB
    from mvp.brain import loop as BL
    from mvp.brain import verify as V
    A = _A()
    t = _carried(brain)
    top = _call(t, "breakdown", dict(CALLS["breakdown"], scope=_only()))
    n = top["sheet"]["totals"]["items"]
    good = f"In 2024 you opened {n}[{top['rid']}.totals.items] videos on it."
    bad = f"In 2024 you opened {n + 3}[{top['rid']}.totals.items] videos on it."
    cm = V.check_mode("values")
    vt = V.Turn.of(t)
    v_bad, v_good = (V.check_answer({"lead": x, "points": []}, t.results, vt, mode=cm) for x in (bad, good))
    assert not v_bad.lead_ok and v_good.lead_ok
    # the lead after a reword
    rec = {"forms": [{"lead": bad, "points": []}, {"lead": good, "points": []}], "events": []}
    BL._finish(rec, t, vt, [v_bad, v_good], cm)
    assert rec["lead_source"] == "model_after_repair" and rec["answer"]["carried_line"]
    # code's own lead (the reword failed too)
    rec = {"forms": [{"lead": bad, "points": []}, {"lead": bad, "points": []}], "events": []}
    BL._finish(rec, t, vt, [v_bad, v_bad], cm)
    assert rec["lead_source"] == "code" and rec["answer"]["carried_line"]
    assert A.CARRIED_LINE in rec["answer"]["text"].split("\n")
    # a turn that ran out of time: code's lead, the time line, and the line
    rec = {"forms": [], "events": ["time_up", "hard_stop"], "time_up_cause": "time"}
    BL._finish(rec, t, vt, [], cm)
    assert rec["lead_source"] == "code"
    assert BL.TIME_LINE in rec["answer"]["text"] and rec["answer"]["carried_line"]
    # the plain line shows no result: no line under it
    plain = FB.answer(V.Ledger({}), None, vt, mode=cm, others=True)
    assert plain["how"] == "plain"
    out = A.build(V.Ledger(t.results), verdict=None, code=plain, mode=cm, carried=sorted(t.carried_in))
    assert not out["carried_line"] and A.CARRIED_LINE not in out["text"]


def test_a_sentence_with_no_marker_on_a_turn_of_one_result_stands_on_it(brain):
    t = _carried(brain)
    _call(t, "breakdown", dict(CALLS["breakdown"], scope=_only()))
    rec, v = _out(t, {"lead": "Yes, quite a lot of it.", "points": []})
    assert v.lead_ok and rec["answer"]["carried_line"]


def test_the_cards_of_the_topics_items_carry_the_line(brain):
    t = _carried(brain)
    it = _call(t, "items", dict(CALLS["items"], scope=_only()))
    ref = it["sheet"]["items"][0]["ref"]
    tot = _call(t, "breakdown", dict(CALLS["breakdown"], scope=S()))
    n = tot["sheet"]["totals"]["items"]
    form = {"lead": f"In 2024 you opened {n}[{tot['rid']}.totals.items] videos.", "points": [],
            "items": [{"ref": ref}]}
    rec, v = _out(t, form)
    assert [x.get("kept") for x in v.items] == [True]
    assert rec["answer"]["cards"] and rec["answer"]["carried_line"]
    # the same answer without the card stands on the total alone
    rec, _v = _out(t, dict(form, items=[]))
    assert not rec["answer"]["carried_line"]


# ================================================================ 4. with the private line on the same answer
def test_with_the_private_line_the_two_are_one_line(brain):
    A = _A()
    t = _carried(brain)
    tot = _call(t, "breakdown", dict(CALLS["breakdown"], scope=S()))
    top = _call(t, "breakdown", dict(CALLS["breakdown"], scope=_only()))
    n, m = tot["sheet"]["totals"]["items"], top["sheet"]["totals"]["items"]
    rec, v = _out(t, {"lead": f"In 2024 you opened {n}[{tot['rid']}.totals.items] videos.",
                      "points": [f"Apart from those, {m}[{top['rid']}.totals.items] were on the topic you asked "
                                 "about."]})
    assert all(o.kept for o in v.outcomes if o.where in ("lead", "point"))
    a = rec["answer"]
    assert a["private_line"] and a["carried_line"]
    lines = a["text"].split("\n")
    assert A.CARRIED_PRIVATE_LINE in lines
    assert A.PRIVATE_LINE not in a["text"] and A.CARRIED_LINE not in lines
    # short, one line, names no topic
    assert "\n" not in A.CARRIED_PRIVATE_LINE and len(A.CARRIED_PRIVATE_LINE) <= 90
    assert TOPIC not in A.CARRIED_PRIVATE_LINE.lower() and "dating" not in A.CARRIED_PRIVATE_LINE.lower()


@pytest.mark.parametrize("mode", ["full", "cells", "values"])
def test_the_line_is_built_in_every_mode(brain, mode):
    t = _carried(brain)
    top = _call(t, "breakdown", dict(CALLS["breakdown"], scope=_only()))
    n = top["sheet"]["totals"]["items"]
    rec, _v = _out(t, {"lead": f"In 2024 you opened {n}[{top['rid']}.totals.items] videos on it.", "points": []},
                   mode=mode)
    assert rec["answer"]["carried_line"]


# ================================================================ 5. a chain of three turns, through the loop
def _turn_via_loop(harness, message, rounds, carry, screen, last=None):
    from mvp.brain import loop as BL
    from mvp.brain import provider as P
    from mvp.tests.fakes.fake_brain import FakeEngine, fake_learned
    prov = P.FakeProvider(list(rounds))
    t = harness.turn(message, last_window=last, search=FakeEngine(), learned=fake_learned, carried_unlock=carry)
    rec = BL.run_turn(prov, t, screen=screen, check="values")
    return rec, t, prov


def test_a_chain_of_three_turns_gets_the_line_on_each_carried_turn_and_never_tells_the_model(harness):
    from mvp.brain import loop as BL
    from mvp.brain import provider as P
    A = _A()
    bd = {"by": "none", "compare": "none", "order": "most", "top": 5, "window": Y24, "scope": _only()}
    tl = {"unit": "month", "window": Y24, "scope": _only()}
    it = {"limit": 3, "order": "newest", "window": Y24, "scope": _only()}
    lead = "Here is what that shows."
    rec1, t1, _p1 = _turn_via_loop(harness, NAMED, [[P.tool_use("breakdown", bd)], [P.tool_use(
        "give_answer", {"lead": lead, "points": []})]], None, {"now": "Sun 22 Nov 2026 12:00"})
    assert t1.unlock == TOPIC and not t1.carried_only and not rec1["answer"]["carried_line"]
    carry = BL.unlock_after(t1, rec1)
    assert carry == TOPIC
    screen = BL.screen_after(rec1, "Sun 22 Nov 2026 12:00")
    sent = []
    for message, call_ in ((FOLLOW, P.tool_use("timeline", tl)), (FOLLOW2, P.tool_use("items", it))):
        rec, t, prov = _turn_via_loop(harness, message, [[call_], [P.tool_use(
            "give_answer", {"lead": lead, "points": []})]], carry, screen)
        assert t.carried_only and rec["answer"]["carried_line"], message
        assert A.CARRIED_LINE in rec["answer"]["text"].split("\n")
        sent.append(prov.sent)
        carry = BL.unlock_after(t, rec)
        assert carry == TOPIC    # the chain carries on while a result resolves a name to the topic
        screen = BL.screen_after(rec, "Sun 22 Nov 2026 12:00")
        # the screen the next turn reads holds no line of code's private words
        for words in (A.CARRIED_LINE, A.CARRIED_PRIVATE_LINE, A.PRIVATE_LINE, "carried_line"):
            assert words not in json.dumps(screen)
    # nothing the model was sent (system, tools, messages) holds the line
    for reqs in sent:
        blob = json.dumps(reqs, default=str)
        for words in (A.CARRIED_LINE, A.CARRIED_PRIVATE_LINE, "private topic you asked", "carried_line",
                      "carried_in"):
            assert words not in blob
    assert "private topic you asked" not in BL.system_text()


# ================================================================ 6. mvp35 repair (DESIGN 34.5): offers and names
# An offer's label is code's, from the row its ref names; a sentence the values mode keeps may write a row's name with
# no marker. Either shows the carried topic's row, so its result is behind the answer.
def _total(t):
    tot = _call(t, "breakdown", dict(CALLS["breakdown"], scope=S()))
    return tot, f"In 2024 you opened {tot['sheet']['totals']['items']}[{tot['rid']}.totals.items] videos."


@pytest.mark.parametrize("mode", ["values", "full", "cells"])
def test_repair_an_offer_of_a_carried_row_brings_the_line_through_the_loop(harness, mode):
    from mvp.brain import provider as P
    A = _A()
    screen = {"last_answer": {"plan": [{"window_said": "2024"}]}, "now": "Sun 22 Nov 2026 12:00"}
    calls = [P.tool_use("breakdown", dict(CALLS["breakdown"], scope=S())),
             P.tool_use("breakdown", dict(CALLS["breakdown"], by="channel", scope=_only()))]
    first, t0, _p = _turn_via_loop(harness, FOLLOW, [calls, [P.tool_use("give_answer", {"lead": "x", "points": []})]],
                                   TOPIC, screen)
    tot, ch = sorted(t0.results)
    assert t0.carried_in == {ch}
    n = t0.results[tot]["sheet"]["totals"]["items"]
    ref = t0.results[ch]["sheet"]["channels"][0]["ref"]
    form = {"lead": f"In 2024 you opened {n}[{tot}.totals.items] videos.", "points": [],
            "offers": [{"kind": "only", "ref": ref}]}
    bad = dict(form, lead=f"In 2024 you opened {n + 9}[{tot}.totals.items] videos.")
    for rounds, source in (([calls, [P.tool_use("give_answer", form)]], "model"),
                           ([calls, [P.tool_use("give_answer", bad)], [P.tool_use("give_answer", bad)]], "code")):
        from mvp.brain import loop as BL
        prov = P.FakeProvider(list(rounds))
        from mvp.tests.fakes.fake_brain import FakeEngine, fake_learned
        t = harness.turn(FOLLOW, search=FakeEngine(), learned=fake_learned, carried_unlock=TOPIC)
        rec = BL.run_turn(prov, t, screen=screen, check=mode)
        a = rec["answer"]
        assert rec["lead_source"] == source, (mode, source)
        assert [o["label"] for o in a["offers"]] == [f"Only {CHANNEL}?"]
        assert a["carried_line"] and A.CARRIED_PRIVATE_LINE in a["text"].split("\n"), (mode, source, a["text"])


@pytest.mark.parametrize("name,kind", [("dating", "only"), (CHANNEL, "exclude")])
def test_repair_an_offer_of_a_find_row_of_the_topic_brings_the_line(brain, name, kind):
    A = _A()
    t = _carried(brain)
    fn = _call(t, "find", {"names": [name]})
    _tot, lead = _total(t)
    assert t.carried_in == {fn["rid"]}
    rec, v = _out(t, {"lead": lead, "points": [], "offers": [{"kind": kind, "ref": f"{fn['rid']}.names[0]"}]})
    a = rec["answer"]
    assert v.lead_ok and len(a["offers"]) == 1
    assert a["carried_line"] and A.CARRIED_PRIVATE_LINE in a["text"].split("\n")


def test_repair_an_offer_under_the_plain_line_brings_the_line_and_the_plain_line_alone_does_not(brain):
    from mvp.brain import fallback as FB
    A = _A()
    t = _carried(brain)
    fn = _call(t, "find", {"names": [CHANNEL]})
    plain = {"lead": FB.PLAIN, "how": "plain", "rid": fn["rid"], "items": [], "private_line": False, "points": []}
    form = {"lead": "x", "points": [], "offers": [{"kind": "only", "ref": f"{fn['rid']}.names[0]"}]}
    a = A.build(t.results, code=plain, form=form, carried=sorted(t.carried_in))
    assert a["offers"] and a["carried_line"] and A.CARRIED_LINE in a["text"].split("\n")
    a = A.build(t.results, code=plain, form=dict(form, offers=[]), carried=sorted(t.carried_in))
    assert not a["carried_line"] and A.CARRIED_LINE not in a["text"]


def test_repair_an_offer_of_a_row_not_of_the_topic_and_a_window_offer_bring_no_line(brain):
    t = _carried(brain)
    _call(t, "find", {"names": [CHANNEL]})
    other = _call(t, "find", {"names": ["cooking"]})
    _tot, lead = _total(t)
    assert other["rid"] not in t.carried_in
    rec, _v = _out(t, {"lead": lead, "points": [], "offers": [
        {"kind": "only", "ref": f"{other['rid']}.names[0]"}, {"kind": "window", "window_words": "2023"}]})
    a = rec["answer"]
    assert len(a["offers"]) == 2 and not a["carried_line"]


@pytest.mark.parametrize("which", ["channel", "title", "quoted title", "in a marked sentence"])
def test_repair_values_a_kept_sentence_naming_a_carried_row_brings_the_line(brain, which):
    A = _A()
    t = _carried(brain)
    tot, lead = _total(t)
    it = _call(t, "items", dict(CALLS["items"], scope=_only()))
    _call(t, "find", {"names": [CHANNEL]})
    title = it["sheet"]["items"][0]["title"]
    n = tot["sheet"]["totals"]["items"]
    form = {"lead": lead, "points": [{"channel": f"Many came from {CHANNEL}.", "title": f"The newest was {title}.",
                                      "quoted title": f"The newest was \"{title}\".",
                                      "in a marked sentence": f"That is {n}[{tot['rid']}.totals.items] in all, many "
                                                              f"from {CHANNEL}."}[which]]}
    rec, v = _out(t, form, mode="values")
    assert all(o.kept for o in v.outcomes if o.where in ("lead", "point")), [(o.where, o.reasons) for o in v.outcomes]
    a = rec["answer"]
    assert a["carried_line"] and A.CARRIED_PRIVATE_LINE in a["text"].split("\n"), a["text"]


def test_repair_values_a_lone_lead_with_no_marker_naming_the_channel_on_two_results_brings_the_line(brain):
    t = _carried(brain)
    _call(t, "find", {"names": [CHANNEL]})
    _total(t)
    rec, v = _out(t, {"lead": f"{CHANNEL} is one of the channels you watch.", "points": []}, mode="values")
    assert v.lead_ok and rec["answer"]["carried_line"]


def test_repair_a_kept_sentence_naming_a_channel_not_of_the_topic_brings_no_line(brain):
    t = _carried(brain)
    _tot, lead = _total(t)
    _call(t, "items", dict(CALLS["items"], scope=_only()))
    rec, v = _out(t, {"lead": lead, "points": ["One of them came from Pan Theory."]}, mode="values")
    assert all(o.kept for o in v.outcomes if o.where in ("lead", "point"))
    assert not rec["answer"]["carried_line"]


def test_repair_a_refused_sentence_naming_the_channel_brings_no_line(brain):
    """full mode refuses a name with no marker: what is not sent is not scanned."""
    t = _carried(brain)
    _tot, lead = _total(t)
    _call(t, "find", {"names": [CHANNEL]})
    rec, v = _out(t, {"lead": lead, "points": [f"Many came from {CHANNEL}."]}, mode="full")
    assert [o.kept for o in v.outcomes if o.where == "point"] == [False]
    assert not rec["answer"]["carried_line"]


def test_repair_judged_a_marked_find_of_two_names_brings_the_line_for_its_other_name_too(brain):
    """Judged (DESIGN 34.5): the line follows results, not rows. A find of the topic's channel and of cooking is one
    marked result; a sentence that writes "cooking" names a row of it, so the line shows. Over-showing is the safe
    side."""
    t = _carried(brain)
    _tot, lead = _total(t)
    fn = _call(t, "find", {"names": [CHANNEL, "cooking"]})
    assert fn["rid"] in t.carried_in
    rec, v = _out(t, {"lead": lead, "points": ["Some were about cooking."]}, mode="values")
    assert all(o.kept for o in v.outcomes if o.where in ("lead", "point"))
    assert rec["answer"]["carried_line"]


@pytest.mark.parametrize("tool", ["breakdown", "timeline"])
def test_repair_a_period_label_or_the_neutral_name_of_a_marked_result_brings_no_line(brain, tool):
    """A marked result's periods ("Feb 2024") and the neutral name its topic rows carry are not names of the topic: a
    sentence over the total that writes a month, or that says it leaves "the topic you asked about" out, gets no line."""
    t = _carried(brain)
    tot, lead = _total(t)
    top = _call(t, tool, dict(CALLS[tool], scope=_only()))
    assert top["rid"] in t.carried_in
    month = top["sheet"]["periods"][0]["label"]
    for point in (f"The first of them was in {month}.", "That count leaves the topic you asked about out."):
        rec, v = _out(t, {"lead": lead, "points": [point]}, mode="values")
        assert all(o.kept for o in v.outcomes if o.where in ("lead", "point")), (point, v.outcomes)
        assert not rec["answer"]["carried_line"], point
