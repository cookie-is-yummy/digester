"""Offline tests for the second merge of round 10 (DESIGN.md section 17, the hook order table and "where the slices
meet"): slices Y (YouTube, Instagram links), V (the browser that cancels, the virtual machine) and T (the self-test)
on top of K, W, S, D, G and C, and the fixes the self-test's trial merges found. Fakes only (the fake interpreter and
composer of test_mvp, the fake MCP and OAuth servers, the fake Google, the fake merchant): no network, no model call.
Made-up data only."""
import os
import sys
from datetime import timedelta

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, say  # noqa: E402
from mvp.tests.test_round10_grants import (NAMES, SUNDAY, first, make_rule, tick_at,  # noqa: E402,F401
                                           tok)
from mvp.tests.test_round10_mcp import INJECT, Fakes, connect, mcp  # noqa: E402,F401  (mcp is a fixture)
from mvp.tests.test_round7 import use_lib  # noqa: E402

TODOIST_TEXT = "every sunday at 6pm put 3 pasta recipes in my todoist"


def _mcp_rule(e, tmp_path):
    """The operator signed in to Todoist (no token), 12 made-up pasta recipes, and a rule that adds to Todoist."""
    connect(e)
    use_lib(e, tmp_path, [(f"p{i}", f"cook{i}", f"{n} recipe with ingredients", "2026-10-01", "2026-10-02",
                           "instagram") for i, n in enumerate(NAMES)], name="libm")
    e["state"]["answers"]["mvp_compose"] = first(3)
    preview = make_rule(e, text=TODOIST_TEXT)
    bot = e["bot"]
    rid = bot.store.rules(H)[0]["id"]
    return bot, rid, preview


# ================================ self-test c26: "undo" after a rule's adds on Todoist's sign-in route ===========
def test_undo_after_a_rule_run_on_the_todoist_sign_in_route_takes_the_tasks_out_there(mcp, tmp_path):
    bot, rid, _ = _mcp_rule(mcp, tmp_path)
    srv = mcp["fk"].srv
    _, sent = tick_at(mcp, SUNDAY)
    assert "Added 3 tasks to Todoist (rule 1):" in sent and len(srv.items) == 3
    out = say(mcp, "undo", {"intent": "undo"})
    assert "couldn't" not in out, out
    assert "out of Todoist" in out and "3" in out
    assert srv.items == {} and bot.store.placements(H) == []


def test_undo_rule_n_after_a_run_on_the_todoist_sign_in_route_takes_the_tasks_out_there(mcp, tmp_path):
    bot, rid, _ = _mcp_rule(mcp, tmp_path)
    srv = mcp["fk"].srv
    tick_at(mcp, SUNDAY)
    assert len(srv.items) == 3
    out = say(mcp, "undo rule 1", {"intent": "unsupported"})
    assert "couldn't" not in out and srv.items == {}, out
