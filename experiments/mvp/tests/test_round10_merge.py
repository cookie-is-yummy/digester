"""Offline tests for the merge of round 10 (DESIGN.md section 17, the hook order table at its top): what crosses the
border between slices K, W, S, D, G and C. Fakes only (the fake interpreter and composer of test_mvp, the fake HTTP
opener of round 9, the fake MCP and OAuth servers of slice K): no network, no model call. Made-up data only."""
import os
from datetime import timedelta
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, say  # noqa: E402
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


# ================================ (c) "delete my data" revokes a sealed sign-in at the server first =============
def _delete(e):
    say(e, "delete my data", {"intent": "delete_data"})
    return say(e, "YES", boom)


def test_delete_my_data_revokes_the_todoist_sign_in_before_the_sealed_file_goes_and_ends_grants(mcp, tmp_path,
                                                                                                 monkeypatch):
    from mvp import oauth, tokens
    bot, rid, _ = _mcp_rule(mcp, tmp_path)
    assert tokens.exists(H, "todoist") and bot.store.grants_of(H)
    order = []
    real_revoke, real_delete = oauth.revoke, tokens.delete_all
    monkeypatch.setattr(oauth, "revoke", lambda h, k: order.append(("revoke", k)) or real_revoke(h, k))
    monkeypatch.setattr(tokens, "delete_all", lambda h: order.append(("delete_all", None)) or real_delete(h))
    out = _delete(mcp)
    assert out.startswith("Done: your rules and history are deleted.") and "couldn't reach" not in out
    assert order == [("revoke", "todoist"), ("delete_all", None)]
    assert mcp["fk"].count("/revoke") == 1 and not tokens.exists(H, "todoist")
    assert bot.store.grants_of(H, active_only=False) == []


def test_delete_my_data_with_a_failed_revoke_still_deletes_and_says_where_to_remove_access(mcp, tmp_path):
    from mvp import tokens
    bot, rid, _ = _mcp_rule(mcp, tmp_path)
    mcp["fk"].revoke_status = 503
    out = _delete(mcp)
    assert out.endswith("I couldn't reach Todoist to cancel my access; remove it in Todoist under Settings › "
                        "Integrations.")
    assert not tokens.exists(H, "todoist") and bot.store.grants_of(H, active_only=False) == []


# ================================ (d) a strong-marked item is never placed by a rule run with a grant ===========
from mvp.tests.test_round10_grants import ctx_for, pick, posts  # noqa: E402


def _mark_strong(lib, *item_ids):
    """A marks file for this made-up library (slice S's derived file), with these items strong-marked."""
    import json as _json

    from mvp import captionmark
    from mvp.retrieve import _library_stamp
    lib = os.path.abspath(str(lib))
    path = captionmark.marks_path(lib)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        _json.dump({"version": captionmark.SIGNAL_VERSION, "stamp": _library_stamp(lib),
                    "items": {i: ["strong", ["says_unrelated"], "fp-" + i] for i in item_ids}}, f)


def test_a_pick_slice_s_marked_strong_is_left_out_of_the_app_and_the_run_says_so(tok):
    from mvp.places import route
    bot = tok["bot"]
    make_rule(tok)
    rid = bot.store.rules(H)[0]["id"]
    o = route(bot, ctx_for(tok, rid, [dict(pick(0), cm="strong"), pick(1)], SUNDAY), "todo.add", {"list": "ticktick"})
    assert [c["body"]["title"] for c in posts(tok)] == ["Lemon orzo"]
    assert o.line.endswith(" 1 left out: its caption may not match the video.")
    o = route(bot, ctx_for(tok, rid, [dict(pick(2), cm="strong")], SUNDAY + timedelta(minutes=3)), "todo.add",
              {"list": "ticktick"})
    assert o.status == "skipped" and len(posts(tok)) == 1 and o.line == "1 left out: its caption may not match the video."


def _composer_of(*needles):
    """A fake composer that picks the candidates whose caption holds these words, in this order."""
    import re

    def answer(user):
        found = re.findall(r"^(\d+)\. .*\n<item>(.*?)</item>", user, re.M)
        out = []
        for w in needles:
            out += [{"n": int(n), "verdict": "clear", "title": cap.split(" recipe")[0][:40]} for n, cap in found
                    if w in cap]
        return {"picks": out, "intro": "Here you go."}
    return answer


def test_a_timed_run_never_places_a_reel_the_library_marks_strong(tok):
    _mark_strong(tok["lib"], "p3")   # "Tomato rigatoni", which the composer picks first
    make_rule(tok)
    tok["state"]["answers"]["mvp_compose"] = _composer_of("Tomato", "Pesto", "Garlic")
    _, sent = tick_at(tok, SUNDAY)
    titles = [c["body"]["title"] for c in posts(tok)]
    assert "Tomato rigatoni" not in titles and len(titles) == 2, titles
    assert "1 left out: its caption may not match the video." in sent


# ================================ (e) hooks 5 to 8z try the message, then its normalised form ===================
ABOVE_HOOK_5 = ("secret_reads", "_asked_reads", "fit_reads", "draft_reads", "offer_reads", "_email_text",
                "understanding_reads", "_length_way_out", "onboard_step", "_rule_reads")


@pytest.fixture()
def seen(monkeypatch):
    """Every text the reads above hook 5 and the grant / place reads were given, by read."""
    from mvp import grants, places
    from mvp.core import Bot
    got = {}

    def wrap(name, f, at):
        def w(*a, **kw):
            got.setdefault(name, []).append(a[at])
            return f(*a, **kw)
        return w
    for name in ABOVE_HOOK_5:
        monkeypatch.setattr(Bot, name, wrap(name, getattr(Bot, name), 2))
    monkeypatch.setattr(grants, "grant_reads", wrap("grant_reads", grants.grant_reads, 2))
    monkeypatch.setattr(places, "place_reads", wrap("place_reads", places.place_reads, 2))
    return got


def _only_the_message_above_hook_5(got, said):
    for name in ABOVE_HOOK_5:
        assert all(t == said for t in got.get(name, [])), (name, got.get(name))


def test_slice_g_reads_the_normalised_form_and_nothing_above_hook_5_sees_it(tok, seen):
    make_rule(tok)
    seen.clear()
    said = "hey can u stop adding to ticktick thx"
    out = say(tok, said, boom)
    assert out.startswith("OK. I won't add anything to TickTick on my own any more.")
    assert seen["grant_reads"] == [said, "stop adding to ticktick"]
    _only_the_message_above_hook_5(seen, said)


def test_slice_c_connect_reads_the_normalised_form_and_nothing_above_hook_5_sees_it(mcp, seen):
    said = "hey can u connect my todoist pls"
    out = say(mcp, said, boom)
    assert out.startswith("To let me add tasks to your Todoist, open this link and press Allow: ")
    assert seen["place_reads"][-1] == "connect my todoist"
    _only_the_message_above_hook_5(seen, said)


def test_slice_d_cancel_notice_reads_the_message_and_nothing_above_hook_5_sees_a_normalised_form(env, seen, monkeypatch):
    from mvp.core import Bot
    got = []
    real = Bot.cancel_reads

    def w(self, person, text, now):
        got.append(text)
        return real(self, person, text, now)
    monkeypatch.setattr(Bot, "cancel_reads", w)
    said = "yo pls cancel my planet fitness membership thx"
    out = say(env, said, boom)
    assert out == "What name is the membership under? I only use it for the notice."   # the notice route (D)
    assert got == [said]   # taken on the message itself; the normalised form is only a second try
    _only_the_message_above_hook_5(seen, said)


# ================================ (f) the errand form reaches D, G and C only through code reads ================
UNSUP = {"intent": "unsupported", "reply": "I can't do that."}


@pytest.fixture()
def no_action(monkeypatch):
    """Any action performed while the errand form's helper runs fails the test (the errand never acts by itself)."""
    from mvp import actions, errand
    real_act = errand.act
    inside = {"on": False}
    real_perform = actions.perform

    def perform(*a, **kw):
        assert not inside["on"], ("an action ran from the errand form", a[0])
        return real_perform(*a, **kw)

    def act(*a, **kw):
        inside["on"] = True
        try:
            return real_act(*a, **kw)
        finally:
            inside["on"] = False
    monkeypatch.setattr(actions, "perform", perform)
    monkeypatch.setattr(errand, "act", act)
    monkeypatch.setenv("MVP_ERRAND_PER_DAY", "30")
    return inside


def _errand_form(e, f):
    e["state"]["answers"]["mvp_errand"] = lambda user: dict(f)


def test_the_errand_send_draft_is_slice_ds_question_read_and_never_sends(env, no_action, monkeypatch):
    from mvp import config
    from mvp import texts as T
    for k in ("MVP_SMTP_HOST", "MVP_MAILBOX_ADDRESS", "MVP_MAILBOX_APP_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(config, "OPERATOR", H)
    monkeypatch.setattr(config, "DRAFT_MODEL", False, raising=False)
    say(env, "email sam@example.com that the meeting moved to wednesday", UNSUP)
    _errand_form(env, {"errand": "send_draft"})
    out = say(env, "dale, envíalo ya mismo", {"intent": "chat", "reply": "Sure thing!"})
    assert "mvp_errand" in env["calls"]
    assert out == T.SEND_SWITCH_ON   # the operator hears how to switch sending on, as for "can you send it for me"
    assert env["bot"].store.get_state(f"sendhold:{H}") is None


def test_the_errand_connect_todoist_reaches_slice_cs_code_read(mcp, no_action):
    _errand_form(mcp, {"errand": "app_connection", "op": "connect", "app_words": "todoist"})
    out = say(mcp, "conecta mi todoist", UNSUP)
    assert out.startswith("To let me add tasks to your Todoist, open this link and press Allow: ")
    assert "mvp_errand" in mcp["calls"]


def test_the_errand_disconnect_reaches_the_code_read_that_ends_slice_gs_grants(tok, no_action):
    make_rule(tok)
    bot = tok["bot"]
    assert bot.store.grants_of(H, connector="ticktick")
    _errand_form(tok, {"errand": "app_connection", "op": "disconnect", "app_words": "ticktick"})
    say(tok, "desconecta mi ticktick", UNSUP)
    assert "mvp_errand" in tok["calls"] and bot.store.grants_of(H, connector="ticktick") == []


def test_the_errand_form_names_no_action_and_no_grant_read():
    import ast
    src = open(os.path.join(os.path.dirname(HERE), "errand.py"), encoding="utf-8").read()
    names = {n.attr if isinstance(n, ast.Attribute) else n.id for n in ast.walk(ast.parse(src))
             if isinstance(n, (ast.Attribute, ast.Name))}
    assert not names & {"perform", "REGISTRY", "run_place", "add_grant", "make", "grant_reads", "send_word",
                        "_mailbox_send_word", "draft_send"}
