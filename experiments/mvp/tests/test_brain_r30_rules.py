"""mvp30 rules: the default values mode is last round's rules and the r30 set (verify.VALUES_RULES_R30).

1. timing_out is in the default: the result envelope's took_ms (the tool's clock) is no cell, so no verdict hangs on
   how fast a tool ran. values_mode(rules=VALUES_RULES) is still last round's mode.
2. The r30 set: the switched-off rules that flipped a settled sentence rightly on their own when replayed on runs
   they were not written against (cards_found, item_count_free, screen_window), each with every guard built for it
   (screen_uncited; rows_before; page_cited, rows_kept, shown_said), and length_cells (a length cell stands for no
   bare figure, nor for time spent). item_count, rows_shown and cited_rows stay behind the switch, and so do
   outcome_you (with outcome_cited), row_text (with row_quote and quote_at_row) and row_group: on an independent
   attack each let out more false sentences than it released true ones. rows_kept acts only with rows_shown, so it is
   inert in the default.
3. quote_at_row (new; narrows row_text and row_quote, behind the switch with them): a figure of a row's own words is
   found only inside the words written as that row's name, from the start of one of its strings up to its own row
   marker. The same words said after the marker, before a cell's marker, or taken from the middle of a string stay
   unfound.
4. A count of a page's rows said with no marker must match the cards sent (item_count_free); the repair says what is
   counted. A count written with an items.count marker is compared only by item_count, which stays off: that is
   pinned here as open.
5. The eval records the rules a values run checks with.

Made-up library and made-up sentences only (none is taken from a saved answer); no model call.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MVP = os.path.dirname(HERE)
EXP = os.path.dirname(MVP)
sys.path.insert(0, EXP)
from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_brain_tools import brain, built, call, no_real_keys, person  # noqa: E402,F401
from mvp.tests.test_brain_toolfix2 import S, W  # noqa: E402

LAST_ROUND = frozenset({"row_name", "cell_found", "day_typed", "motive_you"})
R30 = frozenset({"timing_out", "cards_found", "item_count_free", "screen_window", "screen_uncited", "rows_before",
                 "page_cited", "rows_kept", "shown_said", "length_cells"})
R31 = frozenset({"length_unit", "days_unit", "cite_hint", "paren_tidy"})   # mvp31 (DESIGN 31.9), on by default
R32 = frozenset({"private_behind",   # mvp32 (DESIGN 32), on by default: the private line, no verdict
                 "whole_title"})     # mvp32 part two (DESIGN 32.8): a row named by its whole title
OUTSIDE = frozenset({"item_count", "rows_shown", "cited_rows", "outcome_you", "outcome_cited", "row_text",
                     "row_quote", "quote_at_row", "row_group"})
ROW_TEXT = frozenset({"row_text", "row_quote", "quote_at_row"})   # behind the switch since the mvp30 repair
OUTCOME = frozenset({"outcome_you", "outcome_cited"})              # behind the switch since the mvp30 repair
COOK5 = ("items", {"limit": 5, "offset": 0, "order": "most_opened", "window": W(preset="all"),
                   "scope": S(how="opened", only=["cooking"])}, "a few cooking videos please")


def _default():
    """The default values mode as shipped (with MVP_BRAIN_VALUES_RULES unset), built by name so that a switch another
    test set in this process cannot change it."""
    from mvp.brain import verify as V
    return V.values_mode(rules=V.VALUES_RULES | V.VALUES_RULES_R30)


def _check(t, form, mode=None):
    from mvp.brain import verify as V
    return V.check_answer(form, V.Ledger(t.results), V.Turn.of(t), mode=mode or _default())


def _point(t, text, mode=None):
    v = _check(t, {"lead": "Here is what it says.", "points": [text]}, mode)
    return [o for o in v.outcomes if o.where == "point"][0]


def _search(brain, query, message):
    from mvp.tests.fakes.fake_brain import FakeEngine
    return call(brain, "search", {"query": query, "how": "any", "limit": 5, "window": W(preset="all")}, message,
                search=FakeEngine())


# ================================================================ 1-2. the default and the r30 set
def test_the_r30_set_is_pinned_and_is_the_default():
    from mvp.brain import verify as V
    assert V.VALUES_RULES == LAST_ROUND
    assert V.VALUES_RULES_R30 == R30 and not (R30 & OUTSIDE)
    assert R30 <= V.VALUES_RULES_SWITCHED and V.VALUES_RULES_NEW30 == frozenset({"quote_at_row", "length_cells"})
    assert OUTSIDE <= V.VALUES_RULES_SWITCHED
    assert _default().rules == LAST_ROUND | R30 | {"values", "nw_refuse"}   # the mvp30 default, by name
    assert V.VALUES_RULES_R31 == R31 and R31 <= V.VALUES.rules and not (R31 & V.VALUES_RULES_SWITCHED)   # mvp31
    # full and cells never run a values rule
    assert not (V.VALUES_RULES_ALL & (V.FULL.rules | V.CELLS.rules))
    # what the default refuses: last round's list, item_count (item_count_free gives it) and, since mvp31,
    # length_bound (length_unit gives it)
    assert V.VALUES_REFUSE_DEFAULT == {**V.VALUES_REFUSE, **V.VALUES_REFUSE_R28, **V.VALUES_REFUSE_R31}
    assert sorted(V.VALUES_REFUSE_R31) == ["length_bound"]


def _import_with(value):
    e = {k: v for k, v in os.environ.items() if k not in ("MVP_BRAIN_VALUES_RULES", "MVP_BRAIN_CHECK")}
    if value is not None:
        e["MVP_BRAIN_VALUES_RULES"] = value
    code = ("import json\nfrom mvp.brain import verify as V\nfrom mvp import eval_brain as E\n"
            "print(json.dumps({'values': sorted(V.VALUES.rules), 'check': sorted(V.check_mode('values').rules),\n"
            "                  'settings': E.values_rules_settings('values')}))\n")
    out = subprocess.run([sys.executable, "-B", "-c", code], cwd=EXP, env=e, capture_output=True, text=True,
                         timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_with_the_switch_unset_values_runs_last_rounds_rules_and_the_r30_set():
    got = _import_with(None)
    want = sorted(LAST_ROUND | R30 | R31 | R32 | {"values", "nw_refuse"})
    assert got["values"] == want and got["check"] == want
    assert got["settings"] == {"values_rules": sorted(LAST_ROUND | R30 | R31 | R32), "values_rules_r28": sorted(R30)}
    # the switch only adds: a rule left out of the set is switched on by name
    got = _import_with("rows_shown")
    assert set(got["values"]) == set(want) | {"rows_shown"}


def _clock_envelope(took_ms):
    return {"r1": {"rid": "r1", "tool": "breakdown", "cost_usd": 0.0, "took_ms": took_ms,
                   "meta": {"window_said": "in March 2026"},
                   "sheet": {"kind": "top", "totals": {"items": 31},
                             "areas": [{"ref": "r1.areas[0]", "name": "Music", "items": 20}]}}}


def test_the_tools_clock_decides_no_verdict_by_default():
    from mvp.brain import verify as V
    sent = "In March 2026, you opened 31[r1.totals.items] videos across three kinds of thing."

    def reasons(ms, mode):
        v = V.check_answer({"lead": sent, "points": []}, _clock_envelope(ms), V.Turn(message="what did I open in March"),
                           mode=mode)
        return [o.reasons for o in v.outcomes if o.where == "lead"]
    # last round's mode: "three" is found when the tool happened to run in 3 ms
    old = V.values_mode(rules=V.VALUES_RULES)
    assert reasons(3, old) == [[]] and reasons(9, old) == [["unfound_number"]]
    # the default: the same verdict whatever the clock
    assert {str(reasons(ms, _default())) for ms in (0, 3, 9, 250)} == {str([["unfound_number"]])}


# ================================================================ 3. a quote of a row's words is its name
def test_a_figure_inside_the_words_written_as_a_rows_name_is_found(brain):
    r, t = _search(brain, "sourdough", "anything on starters")
    rows = r["sheet"]["items"]
    k = next(i for i, x in enumerate(rows) if "50 g water" in (x.get("why_matched") or ""))
    title = rows[k]["title"]
    assert title.startswith("Sourdough starter day 3"), title
    from mvp.brain import verify as V
    on = V.values_mode(rules=V.VALUES_RULES | V.VALUES_RULES_R30 | ROW_TEXT)
    for s in (f"The one to start with is Sourdough starter day 3[r1.items[{k}]].",
              f"Start from Sourdough starter day 3: feed 50 g flour[r1.items[{k}]] when you have a free evening."):
        assert _point(t, s, on).kept, s
        # the default (row_text behind the switch) and last round's mode refuse the title's own figure: the cost
        assert _point(t, s, V.values_mode(rules=V.VALUES_RULES)).reasons == ["unfound_number"], s
        assert _point(t, s).reasons == ["unfound_number"], s


def test_the_rows_words_said_anywhere_but_as_its_name_stay_unfound(brain):
    from mvp.brain import verify as V
    r, t = _search(brain, "sourdough", "anything on starters")
    rows = r["sheet"]["items"]
    k = next(i for i, x in enumerate(rows) if "50 g water" in (x.get("why_matched") or ""))
    r28 = V.values_mode(rules=V.VALUES_RULES | V.VALUES_RULES_R28)   # row_text and row_quote, as mvp28 built them
    for s in (f"Sourdough starter day 3[r1.items[{k}]] asks for 50 g water.",            # after its own marker
              f"Before you bake, leave it to wait 12 hours[r1.items[{k}]].",             # the middle of its line
              f"The flour note asks for 50 g water, saved on 5 October 2026[r1.items[{k}].when]."):   # a cell's marker
        assert _point(t, s).reasons == ["unfound_number"], s
        assert _point(t, s, r28).kept, s   # what row_text and row_quote alone let out
        assert _point(t, s, V.values_mode(rules=V.VALUES_RULES | V.VALUES_RULES_R30 | {"row_text", "row_quote"})).kept, s
        assert _point(t, s, V.values_mode(rules=V.VALUES_RULES | V.VALUES_RULES_R30 | ROW_TEXT)).reasons == \
            ["unfound_number"], s


# ================================================================ 4. counts of a page against the cards
def test_a_bare_page_count_over_fewer_cards_is_refused_and_the_repair_says_what_is_counted(brain):
    from mvp.brain import verify as V
    env_, t = call(brain, *COOK5)
    rows = env_["sheet"]["items"]
    assert len(rows) == 5 and env_["sheet"]["totals"]["items"] > 5
    three = [{"ref": x["ref"], "note": None} for x in rows[:3]]
    form = {"lead": "These are the 5 cooking videos you came back to most.", "points": [], "items": three}
    v = _check(t, form)
    assert v.outcomes[0].reasons == ["item_count"] and v.repair
    msg = V.repair_message(v)
    assert "the answer shows 3 of them (item cards)" in msg and "rows named" not in msg
    # with rows_shown switched on, rows named by a marker count, and the repair says so
    v2 = _check(t, form, V.values_mode(rules=V.VALUES_RULES | V.VALUES_RULES_R30 | {"rows_shown"}))
    assert "(item cards and rows named)" in V.repair_message(v2)
    # all five cards sent: kept; last round's mode kept it over three
    assert _check(t, dict(form, items=[{"ref": x["ref"], "note": None} for x in rows])).lead_ok
    assert _check(t, form, V.values_mode(rules=V.VALUES_RULES)).lead_ok


def test_the_number_of_cards_sent_is_found_where_it_introduces_them(brain):
    env_, t = call(brain, *COOK5)
    rows = env_["sheet"]["items"]
    total = env_["sheet"]["totals"]["items"]
    two = [{"ref": x["ref"], "note": None} for x in rows[:2]]
    form = {"lead": f"Two of your {total}[r1.totals.items] cooking videos are below.", "points": [], "items": two}
    assert _check(t, form).lead_ok
    assert not _check(t, dict(form, lead=form["lead"].replace("Two", "Four"))).lead_ok


def test_a_marked_page_count_over_fewer_cards_passes_while_item_count_is_off(brain):
    # open, by measure: item_count would refuse this, and also most honest counts of the list's length
    from mvp.brain import verify as V
    env_, t = call(brain, *COOK5)
    rows = env_["sheet"]["items"]
    form = {"lead": "These 5[r1.items.count] are the cooking videos you came back to most.", "points": [],
            "items": [{"ref": x["ref"], "note": None} for x in rows[:2]]}
    assert _check(t, form).lead_ok
    on = V.values_mode(rules=V.VALUES_RULES | V.VALUES_RULES_R30 | {"item_count"})
    assert _check(t, form, on).outcomes[0].reasons == ["item_count"]


def test_rows_kept_is_inert_without_rows_shown(brain):
    from mvp.brain import verify as V
    env_, t = call(brain, *COOK5)
    rows = env_["sheet"]["items"]
    form = {"lead": "These are the 5 cooking videos you came back to most.",
            "points": [f"{rows[3]['title']}[r1.items[3]] was opened on 1 January 1999[r1.items[3].when]."],
            "items": [{"ref": x["ref"], "note": None} for x in rows[:3]]}
    a = _check(t, form)
    b = _check(t, form, V.values_mode(rules=V.VALUES_RULES | V.VALUES_RULES_R30 - {"rows_kept"}))
    assert [(o.kept, o.reasons) for o in a.outcomes] == [(o.kept, o.reasons) for o in b.outcomes]


# ================================================================ the narrowed outcome rule, behind the switch
def test_their_own_save_with_a_saved_row_cited_is_history_and_the_bots_act_is_not(brain):
    from mvp.brain import verify as V
    on = V.values_mode(rules=V.VALUES_RULES | V.VALUES_RULES_R30 | OUTCOME)
    r, t = _search(brain, "sourdough", "anything on starters")
    rows = r["sheet"]["items"]
    k = next(i for i, x in enumerate(rows) if x.get("how") == "saved")
    day = rows[k]["when"]
    from datetime import date
    d = date.fromisoformat(day)
    said = f"{d.day} {d.strftime('%B')} {d.year}"
    sent = f"You saved it on {said}[r1.items[{k}].when], early in the week."
    assert _point(t, sent, on).kept
    # the default refuses it as last round did (outcome_you is behind the switch: the cost of the repair)
    assert "outcome" in _point(t, sent).reasons
    for s in ("You've saved it to your list now.", "I saved it for you."):
        assert "outcome" in _point(t, s).reasons and "outcome" in _point(t, s, on).reasons, s
