"""Offline tests for the merge of round 10 (DESIGN.md section 17, the hook order table at its top): what crosses the
border between slices K, W, S, D, G and C. Fakes only (the fake interpreter and composer of test_mvp, the fake HTTP
opener of round 9, the fake MCP and OAuth servers of slice K): no network, no model call. Made-up data only."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H  # noqa: E402
from mvp.tests.test_round10_grants import (PREVIEW_LINES, TEXT, boom, make_rule, rule_form,  # noqa: E402,F401
                                           tok)


def replies_since(e, n0):
    return [m[2] for m in e["ch"].outbox[n0:]]


# ================================ (a) W-13's line is replaced by slice G's place ================================
def test_a_rule_that_names_an_app_gets_one_preview_with_the_place_and_no_stop_gap_line(tok):
    n0 = len(tok["ch"].outbox)
    make_rule(tok, yes=False)
    out = replies_since(tok, n0)
    assert len(out) == 1, out                      # one message: the preview, never a separate line before it
    assert out[0].endswith(PREVIEW_LINES)
    assert "on a schedule yet" not in out[0]
