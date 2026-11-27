"""mvp28 rules: this round's values-mode rules are off by default and one switch turns them on.
(mvp30 re-pin: the default is now last round's rules and verify.VALUES_RULES_R30, pinned in test_brain_r30_rules.py;
the switch still only adds rules, and VALUES_RULES_ALL gains "quote_at_row" and "length_cells". Point 1 below reads
"last round's rule set and the r30 set".)

1. The default values mode (MVP_BRAIN_CHECK=values, eval `--check values`, verify.VALUES) runs last round's rule set:
   row_name, cell_found, day_typed, motive_you. Its refuse list and codes are last round's (tests/test_brain_values.py
   pins the digest); "item_count" is in VALUES_REFUSE_R28 and VALUES_CODES_R28.
2. MVP_BRAIN_VALUES_RULES names the rules of VALUES_RULES_R28 to switch on: a comma list, or "r28" for all of them.
   verify reads it once, where VALUES is built; a name that is no values rule stops the import.
3. The eval records the rules a run checks with in its settings.
4. The rules' code is kept: with the switch on, a count of a page said over fewer cards is refused as before.

Made-up library and made-up sentences only; no model call.
"""
import hashlib
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
MVP = os.path.dirname(HERE)
EXP = os.path.dirname(MVP)
sys.path.insert(0, EXP)
from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_brain_tools import brain, built, call, no_real_keys, person  # noqa: E402,F401
from mvp.tests.test_brain_toolfix2 import S, W  # noqa: E402
from mvp.tests.test_brain_toolgaps import ledger_of  # noqa: E402
from mvp.tests.test_brain_evaltools import OCT, harness, made_up_fresh  # noqa: E402,F401  (harness is a fixture)

LAST_ROUND = frozenset({"row_name", "cell_found", "day_typed", "motive_you"})
R28 = frozenset({"item_count", "item_count_free", "cards_found", "rows_shown", "row_text", "screen_window",
                 "cited_rows", "row_group", "outcome_you",
                 "row_quote", "rows_before", "screen_uncited", "outcome_cited", "page_cited", "shown_said",
                 "rows_kept"})
# mvp30: the r30 set, on by default (test_brain_r30_rules.py pins it and why; the mvp30 repair took outcome_you,
# row_text, row_group and their guards out of it and added length_cells)
R30 = frozenset({"timing_out", "cards_found", "item_count_free", "screen_window", "screen_uncited", "rows_before",
                 "page_cited", "rows_kept", "shown_said", "length_cells"})
R31 = frozenset({"length_unit", "days_unit", "cite_hint", "paren_tidy"})   # mvp31 (DESIGN 31.9), on by default
R32 = frozenset({"private_behind",   # mvp32 (DESIGN 32), on by default: the private line, no verdict
                 "whole_title"})     # mvp32 part two (DESIGN 32.8): a row named by its whole title
# the refuse list of the build round's merge (all rules on): last round's list plus VALUES_REFUSE_R28
PIN_REFUSE_ALL = "2118f9724f41851419b4e2c1216c7c61e0c9623de2eb6e7e7b24f9ede67f4432"
PIN_REFUSE_R28 = "fa77e127cf6408e946c3b50a053d9f9e30ad0581fae1e3362f63ab1c8dbbbe31"


def _h(x):
    return hashlib.sha256(json.dumps(x, sort_keys=True, default=str).encode()).hexdigest()


def _import_with(value):
    """verify imported in a fresh process with MVP_BRAIN_VALUES_RULES set to `value` (None: unset) -> its VALUES rules,
    values_mode()'s, check_mode('values')'s and the eval's settings, or the error of the import."""
    e = {k: v for k, v in os.environ.items() if k not in ("MVP_BRAIN_VALUES_RULES", "MVP_BRAIN_CHECK")}
    if value is not None:
        e["MVP_BRAIN_VALUES_RULES"] = value
    code = ("import json\n"
            "try:\n"
            "    from mvp.brain import verify as V\n"
            "except ValueError as x:\n"
            "    print(json.dumps({'error': str(x)}))\n"
            "    raise SystemExit(0)\n"
            "from mvp import eval_brain as E\n"
            "print(json.dumps({'values': sorted(V.VALUES.rules), 'mode': sorted(V.values_mode().rules),\n"
            "                  'check': sorted(V.check_mode('values').rules),\n"
            "                  'settings': E.values_rules_settings('values')}))\n")
    out = subprocess.run([sys.executable, "-B", "-c", code], cwd=EXP, env=e, capture_output=True, text=True,
                         timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


# ================================================================ 1. the default
def test_the_default_rule_set_is_last_rounds():
    from mvp.brain import verify as V
    assert V.VALUES_RULES == LAST_ROUND
    assert V.VALUES_RULES_R28 == R28 and not (R28 & LAST_ROUND)
    assert V.VALUES_RULES_ALL == LAST_ROUND | R28 | {"timing_out", "quote_at_row", "length_cells"} | R31 | R32
    assert V.VALUES_DEFAULT_RULES == LAST_ROUND | R30 | R31 | R32 | V.values_rules_env()
    assert V.values_mode().rules == V.VALUES.rules and V.check_mode("values") is V.VALUES
    # full and cells never run a values rule, on or off
    assert not (V.VALUES_RULES_ALL & (V.FULL.rules | V.CELLS.rules))


def test_with_the_switch_unset_values_runs_exactly_last_rounds_rules():
    got = _import_with(None)
    want = sorted(LAST_ROUND | R30 | R31 | R32 | {"values", "nw_refuse"})
    assert got["values"] == want and got["mode"] == want and got["check"] == want
    assert got["settings"] == {"values_rules": sorted(LAST_ROUND | R30 | R31 | R32), "values_rules_r28": sorted(R30)}
    assert _import_with("")["values"] == want   # an empty switch is no rule


def test_the_refuse_lists_are_last_rounds_and_this_rounds_apart():
    from mvp.brain import verify as V
    assert "item_count" not in V.VALUES_REFUSE and "item_count" not in V.VALUES_CODES
    assert sorted(V.VALUES_REFUSE_R28) == ["item_count"] and V.VALUES_CODES_R28 == frozenset({"item_count"})
    assert _h(V.VALUES_REFUSE_R28) == PIN_REFUSE_R28, _h(V.VALUES_REFUSE_R28)
    # together they are the merged build's list, word for word
    assert _h({**V.VALUES_REFUSE, **V.VALUES_REFUSE_R28}) == PIN_REFUSE_ALL
    assert not (set(V.VALUES_REFUSE) & set(V.VALUES_REFUSE_R28))


# ================================================================ 2. the switch
def test_the_switch_reads_a_comma_list_or_r28():
    from mvp.brain import verify as V
    assert V.values_rules_env("") == frozenset() and V.values_rules_env(" , ") == frozenset()
    assert V.values_rules_env("r28") == R28 and V.values_rules_env("R28") == R28
    assert V.values_rules_env("item_count, row_text") == {"item_count", "row_text"}
    assert V.values_rules_env("ROW_TEXT,row_quote") == {"row_text", "row_quote"}
    assert V.values_rules_env("r28,item_count") == R28
    assert V.values_rules_env("row_name") == frozenset()   # last round's rules are on already
    for bad in ("item_counts", "nw_refuse", "values", "period_bind", "all"):
        with pytest.raises(ValueError):
            V.values_rules_env(bad)


@pytest.mark.parametrize("value,want", [
    ("r28", R28),
    ("item_count", {"item_count"}),
    ("row_text,row_quote", {"row_text", "row_quote"}),
])
def test_the_switch_is_read_once_where_values_is_built(value, want):
    got = _import_with(value)
    rules = set(LAST_ROUND) | R30 | R31 | R32 | set(want) | {"values", "nw_refuse"}
    assert set(got["values"]) == rules and set(got["mode"]) == rules and set(got["check"]) == rules
    assert got["settings"] == {"values_rules": sorted(LAST_ROUND | R30 | R31 | R32 | set(want)),
                               "values_rules_r28": sorted(R30 | set(want))}


def test_a_name_that_is_no_values_rule_stops_the_import():
    got = _import_with("item_count,no_such_rule")
    assert "MVP_BRAIN_VALUES_RULES" in got["error"] and "no_such_rule" in got["error"]


# ================================================================ 3. the eval records it
def test_the_eval_records_the_rules_only_for_a_values_run():
    from mvp import eval_brain as E
    from mvp.brain import verify as V
    assert E.values_rules_settings("full") == {} and E.values_rules_settings("cells") == {}
    s = E.values_rules_settings("values")
    assert s["values_rules"] == sorted(V.VALUES.rules & V.VALUES_RULES_ALL)
    assert s["values_rules_r28"] == sorted(V.VALUES.rules & V.VALUES_RULES_SWITCHED)
    import inspect
    # in the run's settings and on every record (a summary whose settings are lost still has them per message)
    assert "values_rules_settings(check)" in inspect.getsource(E.run_live)
    assert 'values_rules_settings(rec.get("check"))' in inspect.getsource(E.live_conversation)


@pytest.mark.parametrize("check", ["values", None])
def test_every_record_of_a_values_run_carries_its_rules(harness, tmp_path, check):
    from mvp import eval_brain as E
    from mvp.brain import provider as P
    path = str(tmp_path / "fresh.jsonl")
    made_up_fresh(path)
    (p, core), = E.run_set("a", set_name="fresh", path=path)
    lead = "In October 2026, gaming[r1.areas[0]] led what you opened."
    script = [[P.tool_use("breakdown", {"by": "area", "window": OCT})],
              [P.tool_use("give_answer", {"lead": lead, "points": []})]] * 2
    recs = E.live_conversation(harness, P.FakeProvider(script), p, core, log=lambda s: None, set_name="fresh",
                               check=check)
    assert recs
    for r in recs:
        if check == "values":
            assert r["check"] == "values" and r["values_rules"] == sorted(LAST_ROUND | R30 | R31 | R32)
            assert r["values_rules_r28"] == sorted(R30)
        else:
            assert r["check"] == "full" and "values_rules" not in r and "values_rules_r28" not in r


# ================================================================ 4. the rules' code is kept behind the switch
def test_a_page_count_over_fewer_cards_is_kept_by_default_and_refused_with_the_switch_on(brain):
    from mvp.brain import verify as V
    env_, t = call(brain, "items", {"limit": 5, "order": "most_opened", "window": W(preset="all"),
                                    "scope": S(only=["cooking"])}, "some cooking videos please")
    rows = env_["sheet"]["items"]
    assert len(rows) == 5
    led, vt = ledger_of(t)
    form = {"lead": "Here are 5[r1.items.count] of the 72[r1.totals.items] food and cooking videos you opened.",
            "points": [], "items": [{"ref": r["ref"], "note": None} for r in rows[:3]]}
    v = V.check_answer(form, led, vt, mode=V.values_mode(rules=V.VALUES_RULES))
    assert v.lead_ok and not v.repair and v.outcomes[0].reasons == []
    for rules in (V.VALUES_RULES | {"item_count"}, V.VALUES_RULES_ALL):
        v2 = V.check_answer(form, led, vt, mode=V.values_mode(rules=rules))
        assert not v2.lead_ok and v2.repair and v2.outcomes[0].reasons == ["item_count"]
    # all five cards: kept either way
    full = dict(form, items=[{"ref": r["ref"], "note": None} for r in rows])
    for rules in (V.VALUES_RULES, V.VALUES_RULES_ALL):
        assert V.check_answer(full, led, vt, mode=V.values_mode(rules=rules)).lead_ok
