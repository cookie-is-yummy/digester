"""mvp28 checks: the eval's auditor no longer crashes on a cell that holds no number, and the values mode's checks
measured against their live refusals.

1. eval_claims.audit_ledger reads a cited cell by its value: a date cell is a date whatever its path ends with
   (`new.small_channels[0].first_watched`, the crash on a new channel's first date), and a cell that holds no number
   (a weekday list) is no match for a typed number, never a float() of it.
2. Values mode, rule "item_count" (with "item_count_free", "cards_found", "rows_shown"): a count of the rows a page of
   items shows (its items.count, or a figure only the page's length holds) must be the number of its rows the answer
   shows, as item cards (answer._card_list, the cards build sends) or named by a marker; the number shown is found.
3. Rule "row_text": a figure or date quoted, with a word beside it, from a cited row's own text is found; another
   row's text holds nothing for it.
4. The kept codes narrowed: "outcome_you" ("you saved it" is their history, not the bot's act), and three narrowings
   of "found only in cells": "screen_window" (the window words code wrote on the screen), "cited_rows" and
   "row_group" (how many rows the sentence cites, or share a value with a cited row).

Full and cells mode never run these rules (tests/test_brain_values.py pins their digests). Made-up library and
made-up sentences only; no model call.

These rules were off by default in mvp28 (verify.VALUES_RULES_R28); since mvp30 most are in the default
(verify.VALUES_RULES_R30, pinned by tests/test_brain_r30_rules.py). Every test here runs with MVP_BRAIN_VALUES_RULES=r28
(the fixture `r28_on`) and checks with the merged build's rule set (`_r28`), as that build ran them.
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
MVP = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(MVP))
from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_brain_tools import NOW, TODAY, brain, built, call, no_real_keys, person  # noqa: E402,F401
from mvp.tests.test_brain_toolfix2 import S, W  # noqa: E402

# (the fixtures drop every mvp module between tests, so each test imports the brain's modules itself)


def _drop_mvp():
    for m in [m for m in sys.modules if m.startswith("mvp")]:
        del sys.modules[m]


@pytest.fixture(autouse=True)
def r28_on(monkeypatch):
    """This round's values rules on, as MVP_BRAIN_VALUES_RULES=r28 sets them: verify reads the switch once, when it is
    imported, so the brain's modules are imported afresh under it, and dropped again after the test (a later test
    imports them with the switch unset)."""
    monkeypatch.setenv("MVP_BRAIN_VALUES_RULES", "r28")
    _drop_mvp()
    yield
    _drop_mvp()

NEW_THIS_FALL = ("changes", {"against": "previous", "level": "channel", "scope": S(how="opened"),
                             "window": W(words="this fall")}, "new channels i picked up this fall")


def _lib(brain, t):
    from mvp import eval_claims as EC
    return EC.Library(str(brain["lib"]), os.environ["MVP_DERIVED_HOME"], "America/New_York", now=NOW,
                      hide_sensitive=True, unlock=t.unlock)


# ================================================================ 1. the auditor's crash (a date cell read as a number)
def test_a_date_cell_on_a_path_that_does_not_end_in_when_is_read_as_a_date(brain):
    from mvp import eval_claims as EC
    r, t = call(brain, *NEW_THIS_FALL)
    small = r["sheet"]["new"]["small_channels"]
    assert small and small[0]["first_watched"] == "2026-10-12"   # the value of the crash
    lib = _lib(brain, t)
    calls = {"r1": {"tool": "changes", "args": NEW_THIS_FALL[1]}}
    ok = "It was first opened on 12 October 2026[r1.new.small_channels[0].first_watched]."
    rows = EC.audit_ledger(lib, EC.cited_cells(ok), {"r1": r}, calls, NEW_THIS_FALL[2], TODAY)
    assert [(x["kind"], x["ok"]) for x in rows] == [("date", True)]
    for wrong in ("on 14 October 2026", "in November 2026", "in 2025"):
        rows = EC.audit_ledger(lib, EC.cited_cells(f"It was first opened {wrong}"
                                                   "[r1.new.small_channels[0].first_watched]."),
                               {"r1": r}, calls, "", TODAY)
        assert [(x["kind"], x["ok"]) for x in rows] == [("date", False)], wrong


def test_a_cell_that_holds_no_number_is_no_match_for_a_typed_number(brain):
    from mvp import eval_claims as EC
    r, t = call(brain, *NEW_THIS_FALL)
    assert r["sheet"]["when"]["busiest_weekdays"]
    lib = _lib(brain, t)
    calls = {"r1": {"tool": "changes", "args": NEW_THIS_FALL[1]}}
    s = "Your busiest were 2 days, Thursday and Friday[r1.when.busiest_weekdays]."
    rows = EC.audit_ledger(lib, EC.cited_cells(s), {"r1": r}, calls, "", TODAY)
    assert rows and [x["ok"] for x in rows if x["kind"] == "value"] == [False]


def test_the_number_helpers_read_values_not_paths():
    from datetime import date, datetime
    from mvp import eval_claims as EC
    assert EC._iso_day("2026-10-12") == date(2026, 10, 12) == EC._iso_day("2026-10-12 14:00")
    assert EC._iso_day(datetime(2026, 10, 12, 9)) == date(2026, 10, 12)
    for x in ("2026-10", "Thursday,Friday", "12", None, 12, "2026-13-40"):
        assert EC._iso_day(x) is None, x
    assert EC._as_num(3) == 3.0 and EC._as_num("0.25") == 0.25
    for x in ("2026-10-12", "Thursday,Friday", None, True, ["a"]):
        assert EC._as_num(x) is None, x


# ================================================================ 2. a count of the items shown against what is shown
COOKING = ("items", {"limit": 5, "offset": 0, "order": "most_opened", "window": W(preset="all"),
                     "scope": S(how="opened", only=["cooking"])}, "show me a few of the cooking ones")


def _form(lead, points=(), items=(), **kw):
    return dict({"lead": lead, "points": list(points), "items": [{"ref": r, "note": None} for r in items]}, **kw)


def _r28():
    """mvp30 re-pin: the merged build's values rules (last round's and every rule of VALUES_RULES_R28), which the
    switch "r28" ran before the r30 set became the default; these tests pin that build's rules as written."""
    from mvp.brain import verify as V
    return V.values_mode(rules=V.VALUES_RULES | V.VALUES_RULES_R28)


def _check(t, form, mode="values"):
    from mvp.brain import verify as V
    return V.check_answer(form, V.Ledger(t.results), V.Turn.of(t), mode=_r28() if mode == "values" else mode)


def _lead_reasons(v):
    return [o.reasons for o in v.outcomes if o.where == "lead"]


def _off(*rules):
    from mvp.brain import verify as V
    return V.values_mode(rules=(V.VALUES_RULES | V.VALUES_RULES_R28) - set(rules))


def test_the_rules_of_this_round_are_pinned_and_run_in_values_mode_only():
    from mvp.brain import answer as A, verify as V  # noqa: F401
    r28 = {"item_count", "item_count_free", "cards_found", "rows_shown", "row_text", "screen_window", "cited_rows",
           "row_group", "outcome_you"}
    # the repair's rules narrow or complete these (tests/test_brain_r28_repair.py)
    repair = {"row_quote", "rows_before", "screen_uncited", "outcome_cited", "page_cited", "shown_said", "rows_kept"}
    assert V.VALUES_RULES_R28 == frozenset(r28 | repair) and not (V.VALUES_RULES_R28 & V.VALUES_RULES)
    assert V.VALUES_RULES_ALL == V.VALUES_RULES | V.VALUES_RULES_R28 | V.VALUES_RULES_PREP | V.VALUES_RULES_NEW30
    assert r28 <= V.VALUES.rules and not (r28 & (V.FULL.rules | V.CELLS.rules))   # on here (the fixture)
    assert "item_count" in V.VALUES_REFUSE_R28 and "item_count" in V.VALUES_CODES_R28
    assert "item_count" not in V.VALUES_REFUSE and "item_count" not in V.VALUES_CODES   # last round's lists


def test_a_count_of_a_page_must_be_the_number_of_its_rows_the_answer_shows(brain):
    from mvp.brain import verify as V  # noqa: F401
    r, t = call(brain, *COOKING)
    assert r["sheet"]["totals"]["items"] == 72 and len(r["sheet"]["items"]) == 5   # a page: 5 of 72
    lead = "Here are 5[r1.items.count] of the 72[r1.totals.items] food and cooking items you opened."
    # fewer cards than the count (a page's length said over fewer cards): refused, and a reword is asked for
    v = _check(t, _form(lead, items=["r1.items[0]", "r1.items[1]", "r1.items[2]"]))
    assert _lead_reasons(v) == [["item_count"]] and v.repair
    assert "answer shows 3" in v.outcomes[0].notes["item_count"]
    # no card and rows named in the points: 3 shown, not 5
    pts = ["Cooking soup on the 30th[r1.items[0]] was opened on 30 October 2026[r1.items[0].when]."]
    assert _lead_reasons(_check(t, _form(lead, pts))) == [["item_count"]]
    # every row sent: kept
    assert _lead_reasons(_check(t, _form(lead, items=[f"r1.items[{k}]" for k in range(5)]))) == [[]]
    # the five named in the sentence itself are shown (rule rows_shown); with it off only cards count
    named = ("These 5[r1.items.count] are Cooking soup on the 30th[r1.items[0]], Cooking crispy rice[r1.items[1]], "
             "Weeknight cooking pasta[r1.items[2]], the hack video[r1.items[3]] and Cooking tofu three ways"
             "[r1.items[4]].")
    assert _lead_reasons(_check(t, _form(named))) == [[]]
    assert _lead_reasons(_check(t, _form(named), _off("rows_shown"))) == [["item_count"]]
    # the rule off: today's values mode keeps the false count
    assert _lead_reasons(_check(t, _form(lead, items=["r1.items[0]"]), _off("item_count"))) == [[]]


def test_an_unmarked_count_only_a_page_holds_is_compared_too(brain):
    r, t = call(brain, *COOKING)
    pts = ["Cooking crispy rice[r1.items[1]] was opened on 26 October 2026[r1.items[1].when]."]
    # a next page's length with no card; 5 is held by nothing but the page's length
    lead = "Here are the next 5 of the 72[r1.totals.items] food and cooking items you opened."
    assert _lead_reasons(_check(t, _form(lead, pts))) == [["item_count"]]
    assert _lead_reasons(_check(t, _form(lead, pts), _off("item_count_free"))) == [[]]
    assert _lead_reasons(_check(t, _form(lead.replace("next 5", "next five"), pts))) == [["item_count"]]
    assert _lead_reasons(_check(t, _form(lead, pts, items=[f"r1.items[{k}]" for k in range(5)]))) == [[]]


def test_a_true_total_a_count_of_something_else_and_a_sentence_alone_are_not_compared(brain):
    from mvp.brain import verify as V
    r, t = call(brain, *COOKING)
    three = ["r1.items[0]", "r1.items[1]", "r1.items[2]"]
    for lead in ("You opened 72[r1.totals.items] food and cooking items in all; these are the newest.",
                 "You opened 72 food and cooking items in all; here are the newest.",
                 "Here are a few of the 72[r1.totals.items] food and cooking items you opened."):
        assert _lead_reasons(_check(t, _form(lead, items=three))) == [[]], lead
    # a page the answer shows nothing of is not what it counts as shown (how many rows a page of the tool gives)
    assert _lead_reasons(_check(t, _form("The list gives 5[r1.items.count] at a time, so here are the totals: "
                                         "72[r1.totals.items] in all."))) == [[]]
    # a sentence checked alone has no cards to compare
    o = V.check_sentence_values("Here are 5[r1.items.count] of them.", V.Ledger(t.results), V.Turn.of(t))
    assert o.kept


def test_the_number_of_rows_shown_is_found_so_a_true_reword_passes(brain):
    r, t = call(brain, *COOKING)
    four = ["r1.items[0]", "r1.items[1]", "r1.items[2]", "r1.items[4]"]
    for lead in ("Here are 4 of the 72[r1.totals.items] food and cooking items you opened.",
                 "These four are from your 72[r1.totals.items] food and cooking items."):
        assert _lead_reasons(_check(t, _form(lead, items=four))) == [[]], lead
        assert _lead_reasons(_check(t, _form(lead, items=four), _off("cards_found"))) == [["unfound_number"]]
    # a figure that is not the number shown stays unfound
    assert _lead_reasons(_check(t, _form("Here are 4 of the 72[r1.totals.items] items.", items=four[:3]))) == \
        [["unfound_number"]]


def test_the_cards_the_check_counts_are_the_cards_build_sends(brain):
    from mvp.brain import answer as A, verify as V
    r, t = call(brain, *COOKING)
    led = V.Ledger(t.results)
    picks = [["r1.items[0]", "r1.items[0]", "r1.items[1]"],                     # a row picked twice: one card
             [f"r1.items[{k}]" for k in (0, 1, 2, 3, 4, 0)],                     # past ITEMS_MAX
             ["r1.items[1]", "r1.totals", "r9.items[0]"],                        # no item row
             []]
    for p in picks:
        f = _form("Here are some of the 72[r1.totals.items] items you opened.", items=p)
        v = _check(t, f)
        sent = [c["ref"] for c in A.build(led, verdict=v, form=f, also=[v], mode="values")["cards"]]
        shown, _touched = V._shown_cards(led, V.AnswerForm.model_validate(f), f, rows_shown=False)
        assert sent == A.card_refs(led, v, f) and shown == ({"r1": len(sent)} if sent else {}), p
    # an ask-back's cards are the rows it is between
    f = _form("Which one do you mean?", ask_back={"between": ["r1.items[2]", "r1.items[4]"]})
    v = _check(t, f)
    assert [c["ref"] for c in A.build(led, verdict=v, form=f, also=[v], mode="values")["cards"]] == \
        A.card_refs(led, v, f) == ["r1.items[2]", "r1.items[4]"]


# ================================================================ 3. a figure in the cited row's own text
def _search(brain, query, message, **args):
    from mvp.tests.fakes.fake_brain import FakeEngine
    a = dict({"query": query, "how": "any", "limit": 5, "window": W(preset="all")}, **args)
    return call(brain, "search", a, message, search=FakeEngine())


def _point(t, text, mode="values", lead="Here is what it says."):
    v = _check(t, {"lead": lead, "points": [text]}, mode)
    return [o for o in v.outcomes if o.where == "point"][0]


def test_a_figure_quoted_from_the_cited_rows_own_text_is_found(brain):
    r, t = _search(brain, "flour", "what did it say about flour")
    rows = r["sheet"]["items"]
    k = next(i for i, x in enumerate(rows) if "50 g water" in (x.get("why_matched") or ""))
    ok = [f"It says to feed 50 g flour and 50 g water, then wait 12 hours[r1.items[{k}]].",
          f"The post you saved, Sourdough starter day 3[r1.items[{k}]], gives the feeding step.",
          f"Its matching line reads: feed 50 g flour and 50 g water, wait 12 hours, saved on 5 October "
          f"2026.[r1.items[{k}].when]"]
    for s in ok:   # a quote of a saved post's own line, refused in every run before
        assert _point(t, s).kept, s
        assert _point(t, s, _off("row_text")).reasons == ["unfound_number"], s
    # the same words said with other words beside the figure are not a quote: a count of their history
    for s in (f"You opened 50 videos like Sourdough starter day 3[r1.items[{k}]].",
              f"Sourdough starter day 3[r1.items[{k}]] was opened 12 times."):
        assert _point(t, s).reasons == ["unfound_number"], s


def test_a_figure_of_another_rows_text_is_not_found(brain):
    r, t = _search(brain, "sourdough", "my sourdough saves")
    rows = r["sheet"]["items"]
    k = next((i for i, x in enumerate(rows) if "50 g water" in (x.get("why_matched") or "")), None)
    j = next((i for i, x in enumerate(rows) if "hydration" in (x.get("title") or "")), None)
    assert k is not None and j is not None and k != j, [x.get("title") for x in rows]
    assert _point(t, f"It says to wait 12 hours[r1.items[{k}]].").kept
    for s in (f"It says to wait 12 hours[r1.items[{j}]].", f"Sourdough crumb[r1.items[{j}]] uses 50 g flour.",
              f"Sourdough starter day 3[r1.items[{k}]] uses 75% hydration."):
        assert not _point(t, s).kept, s


def test_the_forged_title_cases_stay_refused(brain):
    from mvp.brain import planted as P, verify as V
    data = P.load()
    for cid in ("f_forged_title2", "audit_F50b", "audit_F50c"):
        c = next(x for x in data["cases"] if x["id"] == cid)
        f = (c.get("forms") or [c["form"]])[0]
        v = V.check_answer(f, V.Ledger(data["ledgers"][c["ledger"]]),
                           V.Turn(message=(c.get("turn") or {}).get("message", "")), mode="values")
        assert not [o for o in v.outcomes if o.where == "point"][0].kept, cid


# ================================================================ 4. the kept codes narrowed
def test_outcome_is_the_bot_saying_it_did_something_not_their_own_save(brain):
    r, t = _search(brain, "flour", "what did it say about flour")
    k = 0
    assert r["sheet"]["items"][k]["how"] == "saved" and r["sheet"]["items"][k]["when"] == "2026-10-05"
    for s in (f"You saved it on 5 October 2026[r1.items[{k}].when].",
              f"You also saved it on 5 October 2026[r1.items[{k}].when]."):
        assert _point(t, s).kept, s
        assert _point(t, s, _off("outcome_you")).reasons == ["outcome"], s
    for s in ("I saved it to your list.", "Saved it for you.", "I've set up a rule to send you these.", "All set."):
        assert "outcome" in _point(t, s).reasons, s


def test_a_window_code_wrote_on_the_screen_holds_its_figure_with_the_unit(brain):
    import json
    from mvp.brain import verify as V
    r, t = call(brain, "breakdown", {"by": "none", "compare": "none", "order": "most", "scope": S(how="opened"),
                                     "top": 1, "window": W(preset="all")}, "wait what, when does my export stop")
    s = "So the last 7 days shown on the screen are the days up to 30 October 2026."
    plan = {"rid": "r1", "tool": "breakdown", "args": {"top": 7, "window": {"preset": "this_week"}},
            "window_said": "the last 7 days up to 30 October 2026, where your export ends"}
    led, vt = V.Ledger(t.results), V.Turn.of(t)

    def kept_with(screen, mode="values"):
        vt.screen = json.dumps(screen)
        return _point_v(led, vt, s, mode)
    assert kept_with({"last_answer": {"plan": [plan]}})
    assert not kept_with({"last_answer": {"plan": [plan]}}, _off("screen_window"))
    assert not kept_with({})
    # the model's own arguments on the screen hold nothing ("top": 7)
    assert not kept_with({"last_answer": {"plan": [dict(plan, window_said="the summer of 2026")]}})


def _point_v(led, vt, text, mode="values"):
    from mvp.brain import verify as V
    v = V.check_answer({"lead": "Here is what it holds.", "points": [text]}, led, vt,
                       mode=_r28() if mode == "values" else mode)
    return [o for o in v.outcomes if o.where == "point"][0].kept


def test_a_count_of_rows_the_sentence_cites_or_that_share_a_cited_rows_value_is_found(brain):
    r, t = _search(brain, "watercolor tips", "the watercolor tips one from october", how="opened",
                   window=W(words="in October"))
    rows = r["sheet"]["items"]
    reels = [i for i, x in enumerate(rows) if x.get("channel") == "@wetpaper.ig"]
    assert len(reels) == 4, [x.get("channel") for x in rows]
    a, b = reels[0], reels[1]
    two = (f"Two watercolor reels from October also match: Watercolor reel 1[r1.items[{a}]] and Watercolor reel 2"
           f"[r1.items[{b}]].")
    four = f"Four Watercolor reel videos from @wetpaper.ig were also opened; the closest is Watercolor reel 1[r1.items[{a}]]."
    assert _point(t, two).kept and _point(t, four).kept
    assert not _point(t, two, _off("cited_rows", "row_group")).kept
    assert not _point(t, four, _off("row_group")).kept
    # a count that is no such count stays refused
    for s in (four.replace("Four", "Three"), four.replace("Four", "Seven")):
        assert _point(t, s).reasons == ["unfound_number"], s


def test_a_refused_count_goes_through_the_loop_a_reword_then_a_code_lead(brain):
    from mvp.brain import loop as BL, verify as V
    r, t = call(brain, *COOKING)
    vt, cm = V.Turn.of(t), V.check_mode("values")
    bad = _form("Here are 5[r1.items.count] of the 72[r1.totals.items] food and cooking items you opened.",
                ["Cooking soup on the 30th[r1.items[0]] was opened on 30 October 2026[r1.items[0].when]."],
                items=["r1.items[0]", "r1.items[1]", "r1.items[2]"])
    v1 = V.check_answer(bad, t.results, vt, mode=cm)
    msg = V.repair_message(v1)
    assert v1.repair and msg.startswith("These sentences failed the check.") and "answer shows 3" in msg
    assert "Cooking" not in msg   # no third-party text in the repair
    # the reword refused too: a code lead goes out with the cards, and nothing of the refused lead
    rec = {"forms": [bad, bad]}
    BL._finish(rec, t, vt, [v1, V.check_answer(bad, t.results, vt, mode=cm)], cm)
    assert rec["lead_source"] in ("code", "plain") and "Here are 5" not in rec["answer"]["text"]
    # a truthful reword goes out as the model's
    good = dict(bad, lead="Here are 3 of the 72[r1.totals.items] food and cooking items you opened.")
    rec = {"forms": [bad, good]}
    BL._finish(rec, t, vt, [v1, V.check_answer(good, t.results, vt, mode=cm)], cm)
    assert rec["lead_source"] == "model_after_repair" and rec["answer"]["text"].startswith("Here are 3 of the 72")
    assert len(rec["answer"]["cards"]) == 3
