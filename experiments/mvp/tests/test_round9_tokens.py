"""Offline tests for round 9, E (DESIGN.md section 16.E): TickTick and Todoist by a personal token, and one webhook, on
slice D's places.route, connectors, connections and placements, and the registry fields. Every outside add shows the
exact rows and waits for "yes" (the founder's rule), through the same code as the Mac. A fake HTTP opener stands in
for the services: no test opens a network connection. Synthetic data only; made-up tokens and example addresses."""
import json
import os
import sys
from datetime import timedelta
from types import SimpleNamespace

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, ask_pasta, lemon_pick, say  # noqa: E402

TT = "tt-FAKE-0123456789abcdef0123456789"
TD = "td-FAKE-abcdef0123456789abcdef0123"
URL = "https://hooks.example.com/catch/FAKE-SECRET-PATH-42"
SECRETS = (TT, TD, URL, "FAKE-SECRET-PATH-42")
OTHER = "+15550002"


class FakeOpener:
    """Stands in for the network: records each request and answers like the service would. `script` holds the
    answers for the next calls in order (a status, or "timeout"); with nothing scripted every call succeeds."""

    def __init__(self):
        self.calls, self.script, self.n = [], [], 0

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append({"method": method, "url": url, "headers": dict(headers), "timeout": timeout,
                           "body": json.loads(body) if body else None})
        st = self.script.pop(0) if self.script else None
        if st == "timeout":
            raise TimeoutError()
        if st is not None:
            return st, b""
        if method == "POST" and "ticktick" in url:
            self.n += 1
            return 200, json.dumps({"id": f"tt{self.n}", "projectId": "inbox9", "title": "x"}).encode()
        if method == "POST" and "todoist" in url:
            self.n += 1
            return 200, json.dumps({"id": f"td{self.n}", "content": "x"}).encode()
        if method == "POST":
            return 200, b"Congratulations! You've fired the event"
        return 200, b"[]" if method == "GET" else b""

    def posts(self):
        return [c for c in self.calls if c["method"] == "POST"]


def boom(u):
    raise AssertionError("the model was called")


def ask(e, text):
    n = len(e["calls"])
    out = say(e, text, boom)
    assert len(e["calls"]) == n, text
    return out


@pytest.fixture()
def tok(env, monkeypatch):
    """The operator (H) with a TickTick token, a Todoist token and a webhook address in the environment."""
    from mvp import config
    from mvp.actions import web
    f = FakeOpener()
    monkeypatch.setattr(web, "OPENER", f)
    monkeypatch.setattr(config, "OPERATOR", H)
    monkeypatch.setenv("MVP_TICKTICK_TOKEN", TT)
    monkeypatch.setenv("MVP_TODOIST_TOKEN", TD)
    monkeypatch.setenv("MVP_WEBHOOK_URL", URL)
    for k in ("MVP_TICKTICK_PROJECT", "MVP_TODOIST_PROJECT"):
        monkeypatch.delenv(k, raising=False)
    env["web"] = f
    return env


def pasta(e):
    e["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(e, "pasta, no cream", ask_pasta())


def no_secret_anywhere(e):
    sent = "\n".join(t for _, _, t in e["ch"].outbox)
    for s in SECRETS:
        assert s not in sent
    rows = e["bot"].store.q("SELECT * FROM action_log") + e["bot"].store.q("SELECT * FROM placements") + \
        e["bot"].store.q("SELECT * FROM connections") + e["bot"].store.q("SELECT * FROM state")
    blob = json.dumps(rows, default=str)
    for s in SECRETS:
        assert s not in blob


# ================================ the request shapes (checked against the official pages) ================================
def test_ticktick_request_shape(tok):
    from mvp.actions import PlaceTodoParams, ticktick
    from mvp.actions.base import Ctx
    ctx = Ctx(bot=tok["bot"], person=tok["bot"].store.person(H), answer={}, picks=[], now=tok["clock"][0])
    o = ticktick.run(ctx, PlaceTodoParams(items=[{"title": "Call mum", "notes": "https://example.com/p",
                                                  "due": "2026-11-13T09:00"}]))
    c = tok["web"].calls[-1]
    assert c["method"] == "POST" and c["url"] == "https://api.ticktick.com/open/v1/task" and c["timeout"] == 10
    assert c["headers"]["Authorization"] == f"Bearer {TT}" and c["headers"]["Content-Type"] == "application/json"
    assert c["body"] == {"title": "Call mum", "projectId": "inbox", "content": "https://example.com/p",
                         "dueDate": "2026-11-13T14:00:00+0000", "timeZone": "America/New_York", "isAllDay": False}
    assert o.detail == {"placed": [{"action": "ticktick.add", "remote_id": "inbox9/tt1"}], "count": 1}
    assert ticktick.remove([{"id": 7, "remote_id": "inbox9/tt1"}]) == {"removed": [7], "failed": []}
    assert tok["web"].calls[-1]["method"] == "DELETE"
    assert tok["web"].calls[-1]["url"] == "https://api.ticktick.com/open/v1/project/inbox9/task/tt1"


def test_ticktick_project_from_the_settings(tok, monkeypatch):
    from mvp.actions import ticktick
    monkeypatch.setenv("MVP_TICKTICK_PROJECT", "proj42")
    assert ticktick.body_for(SimpleNamespace(title="a", notes="", due=None), ticktick.settings()["project"], "UTC") == \
        {"title": "a", "projectId": "proj42"}


def test_todoist_request_shape(tok):
    from mvp.actions import PlaceTodoParams, todoist
    from mvp.actions.base import Ctx
    ctx = Ctx(bot=tok["bot"], person=tok["bot"].store.person(H), answer={}, picks=[], now=tok["clock"][0])
    o = todoist.run(ctx, PlaceTodoParams(items=[{"title": "Call mum", "notes": "https://example.com/p",
                                                 "due": "2026-11-13T09:00"}, {"title": "Buy basil"}]))
    a, b = tok["web"].posts()
    assert a["url"] == "https://api.todoist.com/api/v1/tasks" and a["headers"]["Authorization"] == f"Bearer {TD}"
    assert a["body"] == {"content": "Call mum", "description": "https://example.com/p",
                         "due_datetime": "2026-11-13T14:00:00Z"}
    assert b["body"] == {"content": "Buy basil"}                     # the Inbox: no project_id; never due_string
    assert [p["remote_id"] for p in o.detail["placed"]] == ["td1", "td2"]
    todoist.remove([{"id": 1, "remote_id": "td1"}])
    assert tok["web"].calls[-1]["method"] == "DELETE" and tok["web"].calls[-1]["url"].endswith("/api/v1/tasks/td1")


def test_webhook_payload_is_fixed_by_code(tok):
    from mvp.actions import PlaceTodoParams, webhook
    p = PlaceTodoParams(list="Lemon garlic pasta", items=[{"title": "200g spaghetti", "notes": "https://example.com/a"},
                                                           {"title": "2 lemons", "notes": "https://example.com/a"}])
    got = webhook.payload(p, "America/New_York")
    assert got == {"kind": "todo", "title": "Lemon garlic pasta", "text": "200g spaghetti\n2 lemons",
                   "link": "https://example.com/a", "due": None, "list": "Lemon garlic pasta"}
    one = webhook.payload(PlaceTodoParams(items=[{"title": "Call mum", "due": "2026-11-13T09:00"}]), "America/New_York")
    assert one == {"kind": "todo", "title": "Call mum", "text": "", "link": None, "due": "2026-11-13T09:00:00-05:00",
                   "list": None}
    assert set(got) == {"kind", "title", "text", "link", "due", "list"}


def test_a_webhook_address_that_is_not_https_is_never_used(tok, monkeypatch):
    from mvp.actions import web, webhook
    monkeypatch.setenv("MVP_WEBHOOK_URL", "http://hooks.example.com/x")
    assert not webhook.reachable()
    assert ask(tok, "check my webhook").startswith("The webhook address on the computer I run on doesn't start with")
    with pytest.raises(Exception) as e:
        web.call("POST", "http://hooks.example.com/x", None, {})
    assert "hooks.example.com" not in str(e.value) and tok["web"].calls == []


# ================================ show, then wait for yes ================================
def test_ingredients_to_ticktick_preview_yes_undo(tok):
    pasta(tok)
    msg = ask(tok, "add the ingredients to my ticktick")
    assert msg == ('I\'ll add these 2 to TickTick:\n• 200g spaghetti\n• 2 lemons\nReply "yes" to add them, or "no" to '
                   'leave them.')
    assert tok["web"].calls == []                                        # nothing leaves before the yes
    assert ask(tok, "yes") == 'Added 2 tasks to TickTick. Reply "undo" within 10 minutes to remove them.'
    assert [c["body"]["title"] for c in tok["web"].posts()] == ["200g spaghetti", "2 lemons"]
    s = tok["bot"].store
    assert [(r["connector"], r["action"], r["remote_id"]) for r in s.placements(H)] == \
        [("ticktick", "ticktick.add", "inbox9/tt1"), ("ticktick", "ticktick.add", "inbox9/tt2")]
    row = s.one("SELECT * FROM action_log WHERE action='ticktick.add'")
    assert row["status"] == "done" and "spaghetti" not in row["detail"]
    assert s.todos(H) == []                                              # not on the list here too
    assert ask(tok, "undo") == "Undone: I took those 2 out of TickTick."
    assert [c["url"] for c in tok["web"].calls if c["method"] == "DELETE"] == [
        "https://api.ticktick.com/open/v1/project/inbox9/task/tt1",
        "https://api.ticktick.com/open/v1/project/inbox9/task/tt2"]
    assert s.placements(H) == []
    no_secret_anywhere(tok)


def test_no_leaves_nothing_and_a_tapback_never_says_yes(tok):
    pasta(tok)
    ask(tok, "put the ingredients in todoist")
    assert ask(tok, "no") == "OK, I didn't add anything."
    ask(tok, "put the ingredients in todoist")
    tok["bot"].on_message(H, "", tapback="up", tapback_ref=tok["ch"].outbox[-1][0])
    assert tok["web"].calls == []


def test_the_same_things_asked_again_are_not_added_twice(tok):
    pasta(tok)
    ask(tok, "add the ingredients to my todoist")
    ask(tok, "yes")
    n = len(tok["web"].calls)
    assert ask(tok, "add the ingredients to my todoist") == "I already added that to Todoist today."
    assert len(tok["web"].calls) == n


def test_a_yes_for_other_rows_is_refused_by_the_registry(tok):
    from mvp.actions import PlaceTodoParams, Refused, perform, ticktick
    from mvp.actions.base import Ctx
    ctx = Ctx(bot=tok["bot"], person=tok["bot"].store.person(H), answer={}, picks=[], now=tok["clock"][0])
    shown = PlaceTodoParams(items=[{"title": "milk"}])
    token = ticktick.yes_token(ctx, shown)
    with pytest.raises(Refused):
        perform("ticktick.add", ctx, {"items": [{"title": "milk and eggs"}]}, yes_token=token)
    with pytest.raises(Refused):
        perform("ticktick.add", ctx, {"items": [{"title": "milk"}]}, yes_token=None)
    assert tok["web"].calls == []
    assert perform("ticktick.add", ctx, {"items": [{"title": "milk"}]}, yes_token=token).status == "done"


def test_the_webhook_says_before_the_yes_that_it_cannot_be_undone(tok):
    pasta(tok)
    msg = ask(tok, "push the first one to my automation")
    assert msg == ('I\'ll send "Lemon garlic pasta" to your webhook.\nWith its link: https://example.com/itm_a\n'
                   'I can\'t see what your automation does with it, and I can\'t undo it.\nReply "yes" to send it, or '
                   '"no" to leave it.')
    assert tok["web"].calls == []
    assert ask(tok, "yes") == "I sent it to your webhook. I can't see what it did there, and I can't undo it."
    (c,) = tok["web"].posts()
    assert c["url"] == URL and "Authorization" not in c["headers"]
    assert c["body"] == {"kind": "todo", "title": "Lemon garlic pasta", "text": "", "link": "https://example.com/itm_a",
                         "due": None, "list": None}
    assert ask(tok, "undo") == "I can't take back something sent to your webhook, so I left everything else as it was."
    assert len(tok["web"].calls) == 1
    no_secret_anywhere(tok)


def test_send_my_list_moves_the_list_and_undo_brings_it_back(tok):
    s = tok["bot"].store
    for t in ("milk", "eggs"):
        s.add_todo(H, t, at=tok["clock"][0])
    msg = ask(tok, "send my list to ticktick")
    assert msg.startswith("I'll add these 2 to TickTick:\n• milk\n• eggs")
    assert ask(tok, "yes") == ('Added 2 tasks to TickTick. Reply "undo" within 10 minutes to remove them. They are off '
                               'your list here now.')
    assert s.todos(H) == []
    assert ask(tok, "undo") == "Undone: I took those 2 out of TickTick."
    assert [t["text"] for t in s.todos(H)] == ["milk", "eggs"]


def test_send_my_list_when_it_cannot_keeps_it_here_and_writes_nothing_twice(tok, monkeypatch):
    s = tok["bot"].store
    s.add_todo(H, "milk", at=tok["clock"][0])
    monkeypatch.delenv("MVP_TICKTICK_TOKEN")
    assert ask(tok, "send my list to ticktick") == ("I can't reach TickTick yet. Your list stays here. Text me \"connect "
                                                    "my ticktick\" to see how to set it up.")
    assert [t["text"] for t in s.todos(H)] == ["milk"]


def test_from_now_on_and_back(tok):
    assert ask(tok, "put my to-dos in ticktick from now on").startswith(
        "OK. From now on I'll offer to put new things for your lists in TickTick, and show you each one first.")
    assert tok["bot"].store.person_context(H)["prefs"]["place_todo"] == "ticktick"
    msg = say(tok, "add milk to my list", {"intent": "todo_add", "todo_text": "milk"})
    assert msg == 'I\'ll add "milk" to TickTick.\nReply "yes" to add it, or "no" to leave it.'
    assert ask(tok, "yes").startswith('Added "milk" to TickTick.')
    assert ask(tok, "use my list here again") == "OK. New things for your lists stay on your list here."
    assert say(tok, "add eggs to my list", {"intent": "todo_add", "todo_text": "eggs"}) == 'Added "eggs" to your list.'


def test_a_due_to_do_carries_its_time_and_the_bot_keeps_no_copy(tok):
    msg = say(tok, "add call mum to my todoist tomorrow at 9am",
              {"intent": "todo_add", "todo_text": "call mum", "list": "todoist", "due": "2026-11-13T09:00"})
    assert msg == 'I\'ll add "call mum" to Todoist, due tomorrow at 9am.\nReply "yes" to add it, or "no" to leave it.'
    assert ask(tok, "yes") == ('Added "call mum" to Todoist. It\'s due tomorrow at 9am there; I won\'t send my own '
                               'reminder. Reply "undo" within 10 minutes to remove it.')
    assert tok["web"].posts()[0]["body"]["due_datetime"] == "2026-11-13T14:00:00Z"
    assert tok["bot"].store.todos(H) == []


# ================================ every status, the breaker, the fallbacks ================================
@pytest.mark.parametrize("status,line", [
    (401, "TickTick refused my key, so I added \"milk\" to your list here, called \"ticktick\". Text me \"connect my "
          "ticktick\" to see how to make a new one."),
    (403, "TickTick refused my key, so I added \"milk\" to your list here, called \"ticktick\". Text me \"connect my "
          "ticktick\" to see how to make a new one."),
    (429, "TickTick asked me to slow down, so I added \"milk\" to your list here, called \"ticktick\"."),
    (500, "TickTick had a problem on its side, so I added \"milk\" to your list here, called \"ticktick\"."),
    (503, "TickTick had a problem on its side, so I added \"milk\" to your list here, called \"ticktick\"."),
    ("timeout", "TickTick didn't answer in time, so I added \"milk\" to your list here, called \"ticktick\". It may "
                "have reached TickTick anyway, so check there before you ask me again."),   # (round 9 checks)
    (400, "TickTick gave an error, so I added \"milk\" to your list here, called \"ticktick\"."),
    (404, "TickTick said that address doesn't exist, so I added \"milk\" to your list here, called \"ticktick\".")])
def test_each_failure_falls_back_to_the_list_here_with_a_plain_line(tok, status, line):
    say(tok, "add milk to my ticktick", {"intent": "todo_add", "todo_text": "milk", "list": "ticktick"})
    tok["web"].script = [status]
    assert ask(tok, "yes") == line
    assert [t["text"] for t in tok["bot"].store.todos(H)] == ["milk"]
    assert tok["bot"].store.placements(H) == []
    no_secret_anywhere(tok)


def test_a_batch_only_partly_taken_is_taken_out_again(tok):
    pasta(tok)
    ask(tok, "add the ingredients to my ticktick")
    tok["web"].script = [None, 500]                                       # the first one is made, the second fails
    assert ask(tok, "yes").startswith("TickTick had a problem on its side, so I added 2 things to your list here")
    assert [c["method"] for c in tok["web"].calls] == ["POST", "POST", "DELETE"]
    assert tok["bot"].store.placements(H) == []


def test_a_batch_part_that_cannot_be_taken_out_says_so(tok):
    pasta(tok)
    ask(tok, "add the ingredients to my ticktick")
    tok["web"].script = [None, 500, 500]
    assert ask(tok, "yes").startswith("TickTick took only part of it, and I couldn't take that part out again (check "
                                      "TickTick), so I added 2 things to your list here")


def test_three_failures_break_it_no_fourth_call_and_check_recovers(tok):
    for i in range(3):
        say(tok, f"add thing {i} to my ticktick", {"intent": "todo_add", "todo_text": f"thing {i}", "list": "ticktick"})
        tok["web"].script = [500]
        ask(tok, "yes")
    assert tok["bot"].store.connection(H, "ticktick")["status"] == "broken"
    n = len(tok["web"].calls)
    msg = say(tok, "add thing 4 to my ticktick", {"intent": "todo_add", "todo_text": "thing 4", "list": "ticktick"})
    assert msg == ('I\'ve stopped using TickTick after 3 failures in a row, so I added "thing 4" to your list here, '
                   'called "ticktick". Text me "check my ticktick" when it\'s ready.')
    assert len(tok["web"].calls) == n
    assert ask(tok, "check my ticktick") == "TickTick is connected. New tasks go to your Inbox there, unless you set a project."
    assert tok["web"].calls[-1]["method"] == "GET" and tok["web"].calls[-1]["url"].endswith("/open/v1/project")
    assert say(tok, "add thing 5 to my ticktick", {"intent": "todo_add", "todo_text": "thing 5",
                                                   "list": "ticktick"}).startswith('I\'ll add "thing 5" to TickTick')


def test_a_refused_check_says_make_a_new_one(tok):
    tok["web"].script = [401]
    assert ask(tok, "check my todoist") == ('Todoist refused my key. Make a new one, put it in the settings file, '
                                            'restart me, then text me "check my todoist" again.')
    no_secret_anywhere(tok)


def test_the_daily_cap_of_40(tok):
    from mvp.store import now_iso  # noqa: F401
    s = tok["bot"].store
    for i in range(40):
        s.add_placement(H, "ticktick", "ticktick.add", f"inbox9/x{i}", at=tok["clock"][0] - timedelta(minutes=5))
    msg = say(tok, "add milk to my ticktick", {"intent": "todo_add", "todo_text": "milk", "list": "ticktick"})
    assert msg == ('I\'ve reached my limit of 40 tasks a day for TickTick, so I added "milk" to your list here, called '
                   '"ticktick".')
    assert tok["web"].calls == []
    tok["clock"][0] += timedelta(days=1)
    assert say(tok, "add eggs to my ticktick", {"intent": "todo_add", "todo_text": "eggs", "list": "ticktick"}) \
        .startswith('I\'ll add "eggs" to TickTick')


# ================================ only the operator; never the model ================================
def test_a_tester_gets_the_honest_line_and_never_reaches_the_service(tok, monkeypatch):
    from mvp import config
    monkeypatch.setattr(config, "OPERATOR", OTHER)
    pasta(tok)
    assert ask(tok, "add the ingredients to my ticktick") == (
        'I can\'t reach TickTick, so I added 2 things to your list here, called "ticktick": 200g spaghetti; 2 lemons.')
    assert ask(tok, "connect my ticktick") == "TickTick is only for the person who runs me. I keep your lists here."
    assert ask(tok, "check my webhook") == "Your webhook is only for the person who runs me. I keep your lists here."
    assert tok["web"].calls == []
    assert tok["bot"].store.one("SELECT intent FROM requests ORDER BY id DESC")["intent"] == "wanted:ticktick"


def test_the_registry_refuses_a_tester_and_the_model(tok, monkeypatch):
    from mvp import config
    from mvp.actions import Refused, perform, ticktick, validate_action
    from mvp.actions.base import Ctx
    from mvp.schema import RuleSpec
    for name in ("ticktick.add", "todoist.add", "webhook.post"):
        with pytest.raises(ValueError):
            validate_action(name, {"items": [{"title": "x"}]})                 # a model form
        with pytest.raises(ValueError):
            validate_action(name, {"items": [{"title": "x"}]}, by="code", where="rule")
    with pytest.raises(Exception):
        RuleSpec.model_validate({"when": {"type": "now"}, "content": {"source": "note", "text": "x"},
                                 "do": [{"action": "ticktick.add", "params": {"items": [{"title": "x"}]}}]})
    monkeypatch.setattr(config, "OPERATOR", OTHER)
    ctx = Ctx(bot=tok["bot"], person=tok["bot"].store.person(H), answer={}, picks=[], now=tok["clock"][0])
    p = {"items": [{"title": "x"}]}
    from mvp.actions import PlaceTodoParams
    with pytest.raises(Refused):
        perform("ticktick.add", ctx, p, yes_token=ticktick.yes_token(ctx, PlaceTodoParams(**p)))
    assert tok["web"].calls == []


# ================================ connect, check, what are you connected to, disconnect ================================
def test_connect_gives_the_steps_and_never_asks_for_the_token(tok, monkeypatch):
    monkeypatch.delenv("MVP_TICKTICK_TOKEN")
    msg = ask(tok, "connect my ticktick")
    assert msg.startswith("I can add tasks to your TickTick with a personal API token. Never send the token here.")
    assert "Settings › Account › API Token" in msg and "MVP_TICKTICK_TOKEN" in msg and "chmod 600" in msg
    assert "send me" not in msg.lower()
    assert ask(tok, "check my ticktick") == ('TickTick isn\'t set up on the computer I run on yet. Text me "connect my '
                                             'ticktick" to see how.')
    assert "Settings › Integrations › Developer" in ask(tok, "connect todoist")
    msg = ask(tok, "set up a webhook")
    assert "MVP_WEBHOOK_URL" in msg and "https://" in msg and "can't see or undo" in msg
    assert ask(tok, "connect my todoist").endswith('It\'s already set up here. Text me "check my todoist" to test it.')


def test_check_my_webhook_sends_nothing(tok):
    assert ask(tok, "check my webhook").startswith("Your webhook's address is set. I haven't sent anything to it")
    assert tok["web"].calls == []


def test_what_are_you_connected_to_lists_them(tok):
    msg = ask(tok, "what are you connected to")
    assert "• TickTick: connected." in msg and "• Todoist: connected." in msg and "• Your webhook: connected." in msg
    no_secret_anywhere(tok)


def test_disconnect_then_remove_or_keep(tok):
    pasta(tok)
    ask(tok, "add the ingredients to my ticktick")
    ask(tok, "yes")
    assert ask(tok, "disconnect my ticktick") == ("I've stopped using TickTick. I added 2 tasks there in the last 30 "
                                                  "days. Reply REMOVE to delete those, or KEEP to leave them.")
    assert ask(tok, "REMOVE").startswith("I deleted the 2 tasks I'd added to TickTick.")
    assert tok["bot"].store.placements(H, "ticktick") == []
    n = len(tok["web"].calls)
    assert say(tok, "add milk to my ticktick", {"intent": "todo_add", "todo_text": "milk", "list": "ticktick"}) == (
        'TickTick is turned off, so I added "milk" to your list here, called "ticktick". Text me "check my ticktick" '
        'to turn it back on.')
    assert len(tok["web"].calls) == n
    assert ask(tok, "disconnect todoist") == ("I've stopped using Todoist. I hadn't added anything there in the last "
                                              "30 days. To stop it completely, delete the token in Todoist and take it "
                                              "out of the settings file.")


def test_disconnect_keep_leaves_them(tok):
    pasta(tok)
    ask(tok, "add the ingredients to my todoist")
    ask(tok, "yes")
    ask(tok, "disconnect my todoist")
    assert ask(tok, "keep").startswith("OK, they stay in Todoist.")
    assert len(tok["bot"].store.placements(H, "todoist")) == 2


def test_delete_my_data_says_what_stops(tok):
    pasta(tok)
    ask(tok, "add the ingredients to my ticktick")
    ask(tok, "yes")
    msg = say(tok, "delete my data", {"intent": "delete_data"})
    assert "This also stops TickTick. What I added there stays there." in msg
    say(tok, "YES", boom)
    s = tok["bot"].store
    assert s.placements(H, open_only=False) == [] and s.connections_of(H) == []


def test_receipts_name_each_place_in_its_own_words(tok):
    s = tok["bot"].store
    s.add_placement(H, "ticktick", "ticktick.add", "p/t1", at=tok["clock"][0] - timedelta(minutes=5))
    s.add_placement(H, "todoist", "todoist.add", "t9", at=tok["clock"][0] - timedelta(minutes=6))
    s.add_placement(H, "webhook", "webhook.post", "sent", at=tok["clock"][0] - timedelta(minutes=7))
    msg = ask(tok, "what did you do for me")
    assert "• added 1 task in TickTick" in msg and "• added 1 task in Todoist" in msg
    assert "• sent 1 thing to your webhook (I can't see what it did with it)" in msg


# ================================ the HTTP helper ================================
def test_redirects_to_another_host_are_not_followed():
    import urllib.request
    from mvp.actions.web import _SameHostOnly
    h = _SameHostOnly()
    req = urllib.request.Request("https://api.ticktick.com/open/v1/task", data=b"{}", method="POST")
    assert h.redirect_request(req, None, 302, "Found", {}, "https://evil.example.com/steal") is None
    assert h.redirect_request(req, None, 302, "Found", {}, "http://api.ticktick.com/open/v1/task") is None


def test_errors_carry_only_a_code(tok):
    from mvp.actions import web
    from mvp.connectors import ConnectorError
    for st, code in ((401, "refused"), (429, "rate"), (500, "server"), ("timeout", "timeout"), (302, "failed")):
        tok["web"].script = [st]
        with pytest.raises(ConnectorError) as e:
            web.call("POST", URL, TT, {"title": "secret title"}, app="TickTick")
        assert e.value.code == code
        text = f"{e.value!s} {e.value!r} {e.value.args}"
        assert URL not in text and TT not in text and "secret title" not in text
        assert e.value.__cause__ is None and (e.value.__context__ is None or e.value.__suppress_context__)


def test_the_real_opener_is_never_used_in_tests(tok):
    from mvp.actions import web
    assert web.OPENER is tok["web"]


# ================================ the narrow secret guard ================================
POSITIVE = [f"my ticktick token is {TT}", "MVP_TODOIST_TOKEN=abc", "here: MVP_WEBHOOK_URL", f"api key: {TD}",
            "my app password is abcd efgh ijkl mnop1234567890", "the password is Sup3rS3cretValue!!",
            "token: 0123456789abcdef0123", "https://maker.ifttt.com/trigger/x/json/with/key/abcdef123",
            "use hooks.zapier.com/hooks/catch/123/abc ok https://hooks.zapier.com/hooks/catch/123/abc"]
NEGATIVE = ["the token is valid until friday", "my password is too short", "what time does that open",
            "remind me to change my wifi password", "the api key is in the settings file", "send me a token of thanks",
            "password manager recipes", "https://www.instagram.com/p/C0FAKEabcdefghijklmnopq/", "what's my api key for",
            "a recipe for lemon garlic pasta with 200g spaghetti and 2 lemons from https://example.com/abcdefghijklmnop",
            "connect my ticktick", "how do I make a webhook"]


@pytest.mark.parametrize("text", POSITIVE)
def test_the_guard_fires_on_a_secret(text):
    from mvp.connectors import secret_said
    from mvp.cancel import password_said
    assert secret_said(text) or password_said(text), text


@pytest.mark.parametrize("text", NEGATIVE)
def test_the_guard_does_not_fire_on_ordinary_messages(text):
    from mvp.connectors import secret_said
    assert not secret_said(text), text


def inbound(e, text):
    s = e["bot"].store
    rid = s.inbound_add("console", SimpleNamespace(ref=f"r{len(s.q('SELECT id FROM inbound'))}", handle=H, text=text,
                                                     tapback=None, tapback_ref=None))
    out = ask(e, text)
    return out, s.one("SELECT text FROM inbound WHERE id=?", (rid,))["text"]


def test_a_key_in_the_chat_is_not_kept_and_no_model_or_request_row(tok):
    from mvp.texts import SECRET_IN_CHAT
    s = tok["bot"].store
    before = (s.one("SELECT COUNT(*) AS n FROM requests")["n"], s.one("SELECT COUNT(*) AS n FROM interp_cache")["n"])
    out, kept = inbound(tok, f"my ticktick token is {TT}")
    assert out == SECRET_IN_CHAT and kept is None
    assert (s.one("SELECT COUNT(*) AS n FROM requests")["n"], s.one("SELECT COUNT(*) AS n FROM interp_cache")["n"]) == \
        before
    row = s.one("SELECT * FROM action_log WHERE action='secret.refused'")
    assert row and row["detail"] is None
    no_secret_anywhere(tok)


def test_the_guards_are_reached_while_onboarding_asks_a_question(tok):
    from mvp.store import now_iso
    from mvp.texts import CANCEL_PASSWORD, SECRET_IN_CHAT
    s = tok["bot"].store
    for text, line in ((f"my api key is {TD}", SECRET_IN_CHAT), ("my netflix password is hunter22", CANCEL_PASSWORD)):
        s.set_state(f"onboard:{H}", {"step": "read", "at": now_iso(tok["clock"][0])})
        out, kept = inbound(tok, text)
        assert out == line and kept is None, text
        assert s.get_state(f"onboard:{H}")["step"] == "read"             # the setup's question is still open


def test_the_guards_are_reached_while_a_helper_waits_for_an_answer(tok):
    from mvp.texts import SECRET_IN_CHAT
    say(tok, "email my landlord that the sink is broken", {"intent": "chat", "reply": "OK."})
    out, kept = inbound(tok, f"token: {TT}")
    assert out == SECRET_IN_CHAT and kept is None
    row = tok["bot"].store.one("SELECT * FROM drafts ORDER BY id DESC")
    assert row["to_addr"] is None and TT not in (row["parts"] or "")
