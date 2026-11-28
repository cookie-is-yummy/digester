"""Seams of the mvp25 merge: the cells-only checker (DESIGN 24.8) on the tools' new results (DESIGN 25). The checker's
own fixtures (eval/brain_planted.json, eval/brain_cells_attack2.json) freeze their tool results, so these tests build
results with today's tools on the made-up library of tests/brain_library.py. Offline: no model call, no network."""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_brain_tools import brain, built, call, no_real_keys, person, turn  # noqa: E402,F401
from mvp.tests.test_brain_toolgaps import S, W, kept  # noqa: E402

SUMMERS = {"a": W("this summer"), "b": W("last summer"), "by": "area", "scope": S()}


@pytest.mark.parametrize("sentence, want", [
    # true: 45 in the summer of 2026, 16 in the summer of 2025 (recounted in test_brain_toolgaps)
    ("This summer you opened 45[r1.totals.items] videos, up from 16[r1.previous.items] last summer.", True),
    ("Last summer you opened 16[r1.previous.items] videos.", True),
    ("You opened 16[r1.previous.items] videos last summer and 45[r1.totals.items] this summer.", True),
    # false: this summer's count said of last summer, and the two swapped
    ("Last summer you opened 45[r1.totals.items] videos.", False),
    ("You opened 45[r1.totals.items] videos last summer.", False),
    ("This summer you opened 16[r1.previous.items] videos, against 45[r1.totals.items] last summer.", False),
])
def test_last_summer_is_the_summer_before_in_the_cells_check(brain, sentence, want):
    # N010.0 "this summer vs last summer": the tools now give the summer of 2025 as 'last summer' (DESIGN 25.1). The
    # cells rule period_named read 'last summer' as the summer the cited windows overlap most, a tie that went to
    # 2026: the true compare was dropped as other_period and this summer's 45 got out as last summer's.
    env_, t = call(brain, "compare", SUMMERS, "this summer vs last summer")
    assert env_["meta"]["window_dates_b"]["start"] == "2025-06-01"
    assert kept(t, sentence, mode="cells") is want


def test_last_season_with_no_day_is_left_to_the_overlap(brain):
    # with no day on the turn the convention cannot be read: the phrase keeps the overlap reading it had before
    from mvp.brain import verify as V
    env_, t = call(brain, "compare", SUMMERS, "this summer vs last summer")
    vt = V.Turn.of(t)
    vt.today = None
    v = V.check_answer({"lead": "Last summer you opened 16[r1.previous.items] videos.", "points": []},
                       V.Ledger(t.results), vt, mode="cells")
    assert v.lead_ok
