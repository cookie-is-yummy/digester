"""Offline tests for the merge of round 10 (DESIGN.md section 17, the hook order table at its top): what crosses the
border between slices K, W, S, D, G and C. Fakes only (the fake interpreter and composer of test_mvp, the fake HTTP
opener of round 9, the fake MCP and OAuth servers of slice K): no network, no model call. Made-up data only."""
import os
from datetime import timedelta
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


# ================================ (b) slice G's grant covers slice C's MCP route ================================
from mvp.tests.test_round10_grants import NAMES, SUNDAY, first, tick_at  # noqa: E402
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


def test_the_mcp_route_is_a_grant_action_and_a_rule_on_todoist_gets_a_grant_on_it(mcp, tmp_path):
    from mvp import connectors as C
    from mvp.actions import REGISTRY
    assert REGISTRY["todoist.mcp_add"].rule_grant is True
    bot, rid, preview = _mcp_rule(mcp, tmp_path)
    assert C.route_for(bot.store, H, "todoist", "todo") == "todoist.mcp_add"
    assert "I'll also add them to Todoist" in preview
    g, = bot.store.grants_of(H)
    assert (g["rule_id"], g["connector"], g["action"], g["status"]) == (rid, "todoist", "todoist.mcp_add", "active")


def test_a_rule_run_adds_through_the_mcp_route_under_its_grant(mcp, tmp_path):
    bot, rid, _ = _mcp_rule(mcp, tmp_path)
    srv = mcp["fk"].srv
    _, sent = tick_at(mcp, SUNDAY)
    assert [n for n, _ in srv.calls] == ["add-tasks"] and len(srv.items) == 3
    assert "Added 3 tasks to Todoist (rule 1):" in sent
    rows = bot.store.placements(H)
    assert {(r["connector"], r["action"], r["route"], r["rule_id"]) for r in rows} == \
        {("todoist", "todoist.mcp_add", "todoist.mcp_add", rid)}


def test_a_changed_pinned_tool_voids_the_grant_and_the_run_says_the_changed_tool_line(mcp, tmp_path):
    bot, rid, _ = _mcp_rule(mcp, tmp_path)
    srv = mcp["fk"].srv
    srv.change_tool("add-tasks", description="Add tasks. " + INJECT)
    _, sent = tick_at(mcp, SUNDAY)
    assert srv.items == {} and [n for n, _ in srv.calls] == []
    assert ('Todoist changed how adding a task works, so I stopped adding there. Say "yes todoist" to keep using it, '
            'or "disconnect todoist".') in sent
    assert "didn't answer" not in sent and INJECT not in sent
    g, = bot.store.grants_of(H, active_only=False)
    assert (g["status"], g["end_reason"]) == ("ended", "changed")
    _, sent = tick_at(mcp, SUNDAY + timedelta(days=7))   # the next run: the picks here only, nothing at Todoist
    assert srv.items == {} and "changed how adding" not in sent


def test_a_rule_run_that_needs_a_new_sign_in_says_so_once_a_day_and_opens_nothing(mcp, tmp_path, monkeypatch):
    from mvp import oauth
    bot, rid, _ = _mcp_rule(mcp, tmp_path)
    oauth.stop_listener()
    mcp["fk"].oa.provider.withdraw()
    real = oauth._now
    monkeypatch.setattr(oauth, "_now", lambda: real() + 7 * 86400)
    _, sent = tick_at(mcp, SUNDAY)
    assert 'Todoist needs you to sign in again: say "connect todoist".' in sent
    assert "didn't answer" not in sent and not oauth.pending(H) and oauth._LISTENER["it"] is None
    assert mcp["fk"].srv.items == {}
    g, = bot.store.grants_of(H, active_only=False)
    assert g["status"] == "active" and not g["fails"]   # the app did not fail; the person signs in again


def test_a_broken_stream_after_the_create_in_a_rule_run_says_it_may_have_arrived_and_is_never_retried(mcp, tmp_path):
    bot, rid, _ = _mcp_rule(mcp, tmp_path)
    srv = mcp["fk"].srv
    srv.drop_after_create = True
    _, sent = tick_at(mcp, SUNDAY)
    assert [n for n, _ in srv.calls] == ["add-tasks"]   # one call, not retried
    assert "Todoist didn't answer, so I kept them in my message here. It may have arrived in Todoist anyway; check " \
           "before asking again." in sent
