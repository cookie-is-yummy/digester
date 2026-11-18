"""Offline tests for the merge of round 10 (DESIGN.md section 17, the hook order table at its top): what crosses the
border between slices K, W, S, D, G and C. Fakes only (the fake interpreter and composer of test_mvp, the fake HTTP
opener of round 9, the fake MCP and OAuth servers of slice K): no network, no model call. Made-up data only."""
import json
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


# ================================ (g) the Connections panel (D) and the page footer (K) agree ===================
from mvp.tests.test_round10_sending import b  # noqa: E402,F401  (b is a fixture)


def _agree(values):
    from mvp import panel, settings
    sw, st = settings.switches(), panel.state()
    rows = {r["name"]: r for r in st["rows"]}
    assert (sw["sending"] == "on") == (panel.sending_state() == "on"), (sw, panel.sending_state())
    for name, label in (("MVP_TICKTICK_TOKEN", "TickTick"), ("MVP_TODOIST_TOKEN", "Todoist"),
                        ("MVP_WEBHOOK_URL", "webhook")):
        assert (sw[label] == "on") == (rows[name]["state"] in ("setting", "sealed")), (label, sw, rows[name])
    shown = settings.page_status() + json.dumps(st)
    for v in values:
        assert v not in shown
    return sw


def test_the_panel_and_the_footer_say_the_same_and_never_show_a_value(b, monkeypatch):
    from mvp import config, panel
    monkeypatch.setattr(config, "OPERATOR", None)
    monkeypatch.setattr(config, "PAGE_OPERATOR", True)
    for k in ("MVP_TICKTICK_TOKEN", "MVP_TODOIST_TOKEN", "MVP_WEBHOOK_URL", "MVP_MAILBOX_SMTP_HOST"):
        monkeypatch.delenv(k, raising=False)
    tick, pw = "tt-made-up-token-0123456789abcdef", "abcd efgh ijkl mnop"
    values = [tick, pw, pw.replace(" ", "")]
    assert _agree(values)["sending"] == "off"
    panel.save("MVP_MAILBOX_ADDRESS", "me@example.com")
    panel.save("MVP_MAILBOX_APP_PASSWORD", pw)
    _agree(values)
    monkeypatch.setenv("MVP_MAILBOX_SMTP_HOST", "smtp.example.invalid")
    monkeypatch.setenv("MVP_MAILBOX_SMTP_PORT", "465")
    assert _agree(values)["sending"] == "on"
    assert _agree(values)["TickTick"] == "off"
    panel.save("MVP_TICKTICK_TOKEN", tick)
    assert _agree(values)["TickTick"] == "on"
    monkeypatch.setenv("MVP_TODOIST_TOKEN", "td-made-up-token-0123456789abcdef")
    assert _agree(values + ["td-made-up-token-0123456789abcdef"])["Todoist"] == "on"
    panel.remove("MVP_TICKTICK_TOKEN")
    panel.remove("MVP_MAILBOX_APP_PASSWORD")
    sw = _agree(values)
    assert sw["TickTick"] == "off" and sw["sending"] == "off"


# ================================ (h) the three questions are true for everything merged =======================
def _connections_json():
    from mvp import config
    found = sorted((os.path.getmtime(os.path.join(d, n)), os.path.join(d, n))
                   for d, _, fs in os.walk(config.HOME) for n in fs if n == "connections.json")
    with open(found[-1][1], encoding="utf-8") as f:
        return json.load(f)


def test_connected_did_and_export_tell_the_truth_about_a_rule_adding_to_todoist_by_sign_in(mcp, tmp_path):
    bot, rid, _ = _mcp_rule(mcp, tmp_path)
    tick_at(mcp, SUNDAY)
    mcp["clock"][0] = SUNDAY + timedelta(hours=1)
    assert "• Todoist: connected." in say(mcp, "what are you connected to", boom)
    did = say(mcp, "what did you do for me", boom)
    assert "• added 3 tasks in Todoist (3 by rule 1)" in did
    assert "Standing permissions:\n• rule 1 may add tasks to Todoist: at most 3 a run and 10 a day" in did
    assert "Tomato" not in did
    say(mcp, "export my data", boom)
    body = _connections_json()
    assert [(g["rule"], g["app"], g["action"], g["status"]) for g in body["standing_permissions"]] == \
        [(1, "todoist", "todoist.mcp_add", "active")]
    assert body["sign_ins_kept"] == ["todoist"] and body["pinned_tools"] == {"todoist": ["add-tasks", "delete-object"]}
    assert len(body["placements"]) == 3 and "Tomato" not in json.dumps(body)
    # a changed tool: the three answers follow
    mcp["fk"].srv.change_tool("add-tasks", description="Add tasks. " + INJECT)
    tick_at(mcp, SUNDAY + timedelta(days=7))
    mcp["clock"][0] = SUNDAY + timedelta(days=7, hours=1)
    assert "Standing permissions" not in say(mcp, "what did you do for me", boom)
    assert "Todoist: connected." not in say(mcp, "what are you connected to", boom)
    say(mcp, "export my data", boom)
    assert [g["status"] for g in _connections_json()["standing_permissions"]] == ["ended"]


# ================================ the hook order of DESIGN.md section 17 (verdict 3.2), in the source ===========
# (where, needle in handler.py); the rows of slices Y and V are "later" (not merged yet) and have no needle here:
# browser_reads after secret_reads; youtube_answer (4a) between places.asked_reads and _mismatch_answer;
# youtube_reads (5b) after email_reads; the browser offer inside cancel_reads.
HOOK_ORDER = {
    "_on_message": ["ref = self.secret_reads(person, text, now)",
                    "ref = self._asked_reads(person, text, now)",
                    'if pending and pending["kind"] == "confirm_delete":',
                    "ref = self.fit_reads(person, text, now)",                       # 0 (S)
                    "ref = self.draft_reads(person, text, pending, now)",            # 1 (A, W, D)
                    "ref = self.offer_reads(person, text, pending, now)",            # 2 (C of round 9)
                    "ref = self.onboard_step(person, text, now)",                    # the setup (W inside)
                    "return self.answer_normally(person, text, now)"],
    "_asked_reads": ["ask = captionmark.take_ask(self.store, person[\"handle\"])",
                     "ref = self._deadline_answer(person, text, now)",
                     "ref = self._overdue_reply(person, text, now)",
                     "ref = self._cancel_answer(person, text, now)",                 # 3 (B, D)
                     "ref = place_answer(self, person, text, now)",                  # 4 (D)
                     "ref = self._mismatch_answer(person, text, now, ask)",          # 4b (S)
                     "return self._doit_answer(person, text, now)"],
    "answer_normally": ["ref = self._rule_reads(person, text, now)",
                        "for text in phrasing.variants(said):",
                        "ref = export_reads(self, person, text, now)",              # 5a (W)
                        "ref = self.email_reads(person, text, now)",                # 5 (A)
                        "ref = self.self_email_reads(person, text, now)",           # 5 (W: the message itself only)
                        "ref = self.cancel_reads(person, text, now)",               # 6 (B, D)
                        "ref = self.postact_reads(person, text, now)",              # 7 (C of round 9)
                        "ref = place_reads(self, person, text, now)",               # 8 (D, E, C)
                        "ref = grant_reads(self, person, text, now)",               # 8a (G)
                        "ref = self.receipts_reads(person, text, now)",             # 8 (W9)
                        "ref = self.do_it(person, text, now)",                      # 8 (W10)
                        "text = said",                                              # end of the two tries
                        "ref = self.split_reads(person, text, now)",                # 8z (W)
                        "done, ref = self.integration_reads(person, text, now)",
                        "it, _ = interpret(",
                        "it = chat_guard(it, text)",
                        "screened = self.screen_guard(person, it, text, now)",      # then the errand form (W)
                        "if screened is not None:"],
}


def test_the_hooks_run_in_the_order_of_design_section_17():
    src = open(os.path.join(os.path.dirname(HERE), "handler.py"), encoding="utf-8").read()
    for fn, needles in HOOK_ORDER.items():
        start = src.index(f"    def {fn}(")
        end = src.index("\n    def ", start + 10)
        body = src[start:end]
        at = []
        for n in needles:
            assert body.count(n) == 1, (fn, n, body.count(n))
            at.append(body.index(n))
        assert at == sorted(at), (fn, [n for _, n in sorted(zip(at, needles))])
    # every read of hooks 5a to 8 is inside the loop over the message and its normalised form; 8z and the model after
    body = src[src.index("    def answer_normally("):]
    loop, after = body.index("for text in phrasing.variants(said):"), body.index("        text = said\n")
    for n in HOOK_ORDER["answer_normally"][2:11]:
        assert loop < body.index(n) < after, n


# ================================ the stubs of slice K after the six merges ======================================
def test_the_stubs_after_the_merge_real_phrasing_marks_titles_and_routes_and_no_browser_or_youtube(mcp):
    from types import SimpleNamespace

    from mvp import browser, captionmark, compose, connectors, phrasing, yt_auth
    assert phrasing.STUB is False and phrasing.variants("hey can u connect my todoist pls")[-1] == "connect my todoist"
    assert captionmark.STUB is False
    it = SimpleNamespace(platform="instagram", creator="@memes", media="reel", caption_reasons=(), caption_fp=None,
                         first_line="Creamy pasta", caption="Creamy pasta", raw_caption="Creamy pasta",
                         caption_mark="strong")
    assert compose.display_title(it, "Creamy pasta") == "A reel from @memes"   # slice S: a neutral name when strong
    st = mcp["bot"].store
    connect(mcp)
    assert connectors.route_for(st, H, "todoist", "todo") == "todoist.mcp_add"   # slice C: the sign-in route
    assert browser.STUB is True and browser.available(None, {"handle": H}, "netflix") is False
    assert browser.run_open(None, H) is False
    assert yt_auth.STUB is True and yt_auth.connectable(None, H) is False and yt_auth.connected(None, H) is False


# ================================ the review of the merge (DESIGN.md section 17, "the review of the merge") ========
def test_a_reel_the_person_called_fine_is_placed_by_a_granted_run_though_the_library_marks_it_strong(tok):
    """Slice S's level with what the person said (effective), not the library's mark alone: "that one was fine" on a
    strong-marked reel puts it back in the rule's adds, and no "left out" line is said."""
    from mvp import captionmark
    _mark_strong(tok["lib"], "p3")   # "Tomato rigatoni", which the composer picks first
    make_rule(tok)
    bot = tok["bot"]
    it = bot.view(bot.store.person(H)["library"]).get("p3")
    bot.store.add_caption_feedback(H, "p3", it.creator, captionmark.fp_of(it), "match_ok", "words", tok["clock"][0])
    tok["state"]["answers"]["mvp_compose"] = _composer_of("Tomato", "Pesto", "Garlic")
    _, sent = tick_at(tok, SUNDAY)
    titles = [c["body"]["title"] for c in posts(tok)]
    # the reel is added (under slice S's neutral name, which compose gives from the library's mark)
    assert titles == ["A post from @cook3", "Pesto fusilli", "Garlic linguine"], titles
    assert "left out" not in sent


def test_a_reel_the_person_called_a_mismatch_is_left_out_though_the_library_has_no_mark(tok):
    from mvp import captionmark
    from mvp.places import route
    make_rule(tok)
    bot = tok["bot"]
    rid = bot.store.rules(H)[0]["id"]
    it = bot.view(bot.store.person(H)["library"]).get("p0")
    assert captionmark.mark(it) is None
    bot.store.add_caption_feedback(H, "p0", it.creator, captionmark.fp_of(it), "mismatch", "words", tok["clock"][0])
    o = route(bot, ctx_for(tok, rid, [pick(0), pick(1)], SUNDAY), "todo.add", {"list": "ticktick"})
    assert [c["body"]["title"] for c in posts(tok)] == ["Lemon orzo"]
    assert o.line.endswith(" 1 left out: its caption may not match the video.")


def test_a_token_set_after_a_todoist_sign_in_ends_the_grant_with_one_line_and_adds_nothing(mcp, tmp_path,
                                                                                            monkeypatch):
    """The yes was given for the sign-in route; with a token set the app is reached the other way. Nothing is added
    either way, the grant ends, the run says so once, and "use todoist for rule 1" asks for a new yes."""
    from mvp.actions import web
    from mvp.tests.test_round9_tokens import TD, FakeOpener
    bot, rid, _ = _mcp_rule(mcp, tmp_path)
    f = FakeOpener()
    monkeypatch.setattr(web, "OPENER", f)
    monkeypatch.setenv("MVP_TODOIST_TOKEN", TD)
    _, sent = tick_at(mcp, SUNDAY)
    assert ("The way I reach Todoist changed since you said yes to rule 1, so I didn't add anything there. Say \"use "
            "todoist for rule 1\" to add them again.") in sent
    assert mcp["fk"].srv.items == {} and [c for c in f.calls if c["method"] == "POST"] == []
    g, = bot.store.grants_of(H, active_only=False)
    assert (g["status"], g["end_reason"]) == ("ended", "route_changed")
    _, sent = tick_at(mcp, SUNDAY + timedelta(days=7))   # said once: the next run is the picks here only
    assert "The way I reach" not in sent and [c for c in f.calls if c["method"] == "POST"] == []
    out = say(mcp, "use todoist for rule 1", boom)
    assert "I'll also add them to Todoist" in out
    assert say(mcp, "yes", boom) == "OK. Rule 1 will add them to Todoist again, and tell you here what it added."
    g = [x for x in bot.store.grants_of(H, active_only=False) if x["status"] == "active"]
    assert [x["action"] for x in g] == ["todoist.add"]


@pytest.mark.parametrize("app,word", [("ticktick", "TickTick"), ("todoist", "Todoist")])
def test_a_tester_naming_an_app_in_a_rule_is_never_told_to_connect_it(tok, app, word, monkeypatch):
    """Slice G's "isn't connected for you ... Say "connect todoist"" line told a tester to do what slice C (and round 9)
    answer with "isn't ready yet" / "only for the person who runs me". A tester hears that it is the operator's only."""
    from mvp import config
    monkeypatch.setattr(config, "OPERATOR", "+15559999")
    out = say(tok, f"every sunday at 6pm put 3 pasta recipes in my {app}", rule_form())
    assert out.endswith(f" {word} is only for the person who runs me, so I'll put them in my message here instead.")
    assert "connect" not in out.split("stay quiet.")[-1]
    say(tok, "yes", boom)
    assert say(tok, f"use {app} for rule 1", boom) == \
        f"{word} is only for the person who runs me, so I'll put them in my message here instead."
    assert tok["bot"].store.grants_of(H, active_only=False) == []
