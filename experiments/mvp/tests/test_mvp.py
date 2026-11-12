"""Offline tests for the MVP skeleton: synthetic library, fake model, fake search engine. No API calls, no real data."""
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("MVP_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MVP_LEDGER_HOME", str(tmp_path / "ledger"))
    for m in [m for m in sys.modules if m.startswith("mvp")]:
        del sys.modules[m]
    lib = tmp_path / "lib"
    (lib / "corpus").mkdir(parents=True)
    items = [
        ("itm_a", "instagram", "Lemon garlic pasta\nIngredients:\n- 200g spaghetti\n- 2 lemons\n- 4 cloves garlic\nlink in bio for my storefront", ["save"], "following"),
        ("itm_b", "instagram", "Creamy mushroom pasta with heavy cream", ["save"], "following"),
        ("itm_c", "instagram", "Pasta night! recipe in the video", ["like"], "following"),
        ("itm_d", "instagram", "My friend's pasta", ["save"], "mutual"),
        ("itm_e", "youtube", "Best carbonara ever", ["watch"], "none"),
    ]
    with open(lib / "corpus" / "items.jsonl", "w") as f:
        for iid, plat, cap, kinds, rel in items:
            f.write(json.dumps({"id": iid, "platform": plat, "source_url": f"https://example.com/{iid}", "caption": cap,
                                "interaction_kinds": kinds, "platform_data": {"owner_handle": "chef", "owner_relation": rel}}) + "\n")
    with open(lib / "corpus" / "interactions.jsonl", "w") as f:
        for iid, *_ in items:
            f.write(json.dumps({"item_id": iid, "kind": "save", "at": "2026-03-01T10:00:00+00:00"}) + "\n")
    from mvp import llm
    calls = []

    def fake_chat(system, user, purpose, prompt_version, person=None, max_tokens=0, **kw):
        calls.append(purpose)
        return env_state["answers"][purpose](user), 0.001
    env_state = {"answers": {}}
    monkeypatch.setattr(llm, "chat_json", fake_chat)
    monkeypatch.setattr(llm, "spent_today", lambda h, l: 0.0)
    monkeypatch.setattr(llm, "spent_total", lambda libs: 0.0)
    for name in ("interpret", "compose"):
        mod = __import__(f"mvp.{name}", fromlist=["x"])
        monkeypatch.setattr(mod.llm, "chat_json", fake_chat)
    from mvp import config as _config
    # the fakes change their answer for the same text between steps; the cache has its own tests (test_slice2.py)
    monkeypatch.setattr(_config, "INTERPRET_CACHE_HOURS", 0)

    class FakePool:
        max_resident = 4

        def search(self, lib, q, depth=300):
            return {"ids": ["itm_d", "itm_b", "itm_a", "itm_c", "itm_e"], "mode": "normal", "cost_usd": 0.0}

        def warm(self, lib):
            pass

        def stop_all(self):
            pass
    from mvp.channels.console import ConsoleChannel
    from mvp.core import Bot
    from mvp.store import Store
    from mvp import config
    clock = [datetime(2026, 11, 12, 18, 0, tzinfo=timezone.utc)]
    ch = ConsoleChannel(printer=None)
    bot = Bot(ch, store=Store(config.DB), pool=FakePool(), clock=lambda: clock[0])
    people = tmp_path / "people.json"
    people.write_text(json.dumps({"+15550001": {"name": "T", "library": str(lib), "timezone": "America/New_York"}}))
    bot.load_people(str(people))
    bot.store.set_consent("+15550001", "test")
    return {"bot": bot, "ch": ch, "clock": clock, "state": env_state, "calls": calls, "lib": lib}


def pasta_spec(when=None, avoid=None):
    return {"when": when or {"type": "schedule", "days": ["FRI"], "time": "19:00"},
            "content": {"goal": "a pasta recipe", "searches": ["pasta recipe"], "count": 1, "extract": "ingredients",
                        "avoid": avoid or []}}


def compose_picks(*picks):
    return lambda user: {"picks": list(picks), "intro": "Here you go."}


def last(ch):
    return ch.outbox[-1][2]


def test_schedule_next_run_and_dst():
    from mvp.schedule import next_run, describe
    from mvp.schema import When
    w = When(type="schedule", days=["FRI"], time="19:00")
    after = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)   # Fri 30 Oct, before DST ends (1 Nov)
    assert next_run(w, "America/New_York", after) == datetime(2026, 10, 30, 23, 0, tzinfo=timezone.utc)
    after2 = datetime(2026, 10, 31, 0, 0, tzinfo=timezone.utc)
    assert next_run(w, "America/New_York", after2) == datetime(2026, 11, 7, 0, 0, tzinfo=timezone.utc)  # EST now
    assert describe(w) == "every Friday at 7pm"
    biweekly = When(type="schedule", days=["MON"], time="08:30", every_weeks=2)
    a = datetime(2026, 11, 9, 14, 0, tzinfo=timezone.utc)  # Monday 9:00 New York, anchor week
    first = next_run(biweekly, "America/New_York", a, anchor=a)
    # DESIGN.md section 11: "every other" starts on the first matching day after creation (here Monday 16 Nov),
    # then every second week from there
    assert first.date().isoformat() == "2026-11-16"
    second = next_run(biweekly, "America/New_York", first, anchor=a)
    assert second.date().isoformat() == "2026-11-30"


def test_schema_rejects_kinds_that_exclude_youtube():
    from mvp.schema import Content
    with pytest.raises(Exception):
        Content(goal="x y", searches=["a"], kinds=["save", "collection"], platforms=["youtube"])


def test_line_check_and_cleaning():
    from mvp.compose import clean_line, line_in_text
    text = "Ingredients:\n- 200g spaghetti\n- 2 lemons"
    assert line_in_text("200 g spaghetti", text)
    assert not line_in_text("300g spaghetti", text)
    assert clean_line("Ingredients:") is None
    assert clean_line("Click the link in bio") is None
    assert clean_line("2 lemons") == "2 lemons"


def test_ask_enforces_reliability_rules(env):
    bot, ch, st = env["bot"], env["ch"], env["state"]
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "ask", "spec": pasta_spec({"type": "now"}, avoid=["cream"])}
    # The model cites a non-candidate (99), a friend's post is not offered at all, it invents a line, and it picks
    # the creamy pasta that the person asked to avoid.
    def compose_answer(user):
        assert "My friend's pasta" not in user                      # rule 5
        assert "<item>" in user                                       # rule 6
        assert "heavy cream" not in user                            # avoided words never reach the model
        return {"picks": [{"n": 99, "title": "ghost", "why": "x", "fit": 0.9},
                          {"n": 1, "title": "Lemon garlic pasta", "why": "Fits pasta night.", "fit": 0.95,
                           "lines": ["200g spaghetti", "2 lemons", "1 cup cream", "link in bio for my storefront"]}],
                "intro": "Here you go."}
    st["answers"]["mvp_compose"] = compose_answer
    bot.on_message("+15550001", "pasta ideas?")
    msg = last(ch)
    assert "ghost" not in msg                                         # rule 1
    assert "1 cup cream" not in msg and "storefront" not in msg       # rule 2
    assert "(2 ingredients listed)" in msg                            # counts from code
    run = bot.store.one("SELECT * FROM runs WHERE kind='ask'")
    assert run["n_picks"] == 1 and run["n_dropped"] >= 2


def test_avoid_word_is_enforced_in_code(env):
    bot, ch, st = env["bot"], env["ch"], env["state"]
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "ask", "spec": pasta_spec({"type": "now"}, avoid=["cream"])}
    st["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Creamy thing", "why": "x", "fit": 0.9})
    bot.on_message("+15550001", "pasta, no cream")
    assert "didn't find a good match" in last(ch)                     # rule 3: no padding


def test_rule_preview_confirm_schedule_no_repeats(env):
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "new_rule", "spec": pasta_spec()}
    st["answers"]["mvp_compose"] = lambda u: {"picks": [{"n": 1, "title": "Pasta A", "why": "Good fit.", "fit": 0.9}], "intro": "Hi."}
    bot.on_message("+15550001", "pasta every friday at 7pm")
    assert "Reply YES to start" in last(ch)
    assert not bot.store.rules("+15550001")                           # rule 7: preview only
    bot.on_message("+15550001", "yes")
    rules = bot.store.rules("+15550001")
    assert len(rules) == 1 and rules[0]["next_run_at"] == "2026-11-14T00:00:00+00:00"
    sent_items = []
    for week in range(3):
        clock[0] = datetime(2026, 11, 14 + 7 * week, 0, 1, tzinfo=timezone.utc)
        assert bot.tick() == 1
        sent_items.append(bot.store.q("SELECT item_id FROM deliveries WHERE rule_id=? ORDER BY id DESC LIMIT 1",
                                      (rules[0]["id"],)))
    ids = [r[0]["item_id"] for r in sent_items if r]
    assert len(ids) == len(set(ids))                                  # rule 4: no repeats
    # once everything has been sent, it says so instead of repeating
    clock[0] = datetime(2026, 12, 5, 0, 1, tzinfo=timezone.utc)
    bot.tick()
    assert "Nothing new" in last(ch) or "React" in last(ch)


def test_feedback_down_is_never_sent_again(env):
    bot, ch, st = env["bot"], env["ch"], env["state"]
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "ask", "spec": pasta_spec({"type": "now"})}
    st["answers"]["mvp_compose"] = lambda u: {"picks": [{"n": 1, "title": "P", "why": "Good.", "fit": 0.9}]}
    bot.on_message("+15550001", "pasta?")
    first = bot.store.last_answer("+15550001")["items"][0]
    bot.on_message("+15550001", "👎 1")
    seen = []
    st["answers"]["mvp_compose"] = lambda u: (seen.append(u), {"picks": []})[1]
    bot.on_message("+15550001", "pasta again?")
    assert bot.view(str(env["lib"])).get(first).caption[:20] not in seen[0]   # rule 9


def test_quiet_hours_and_delete(env):
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "delete_data"}
    bot.on_message("+15550001", "delete my data")
    assert "Reply YES" in last(ch)
    bot.on_message("+15550001", "yes")
    assert bot.store.person("+15550001") is None


def test_unknown_person_and_consent(env):
    bot, ch = env["bot"], env["ch"]
    bot.on_message("+19999999", "hi")
    assert "not set up" in last(ch)
    bot.on_message("+19999999", "hi again")
    assert len(ch.outbox) == 1                                         # one reply a day to a stranger, not one per text


def test_mac_reader_decodes_attributed_body_and_tapbacks(tmp_path):
    for m in [m for m in sys.modules if m.startswith("mvp")]:
        del sys.modules[m]
    from mvp.channels.imessage_mac import MacMessagesChannel, decode_attributed_body
    from mvp.store import Store
    db = tmp_path / "chat.db"
    c = sqlite3.connect(db)
    c.executescript("CREATE TABLE handle (ROWID INTEGER PRIMARY KEY, id TEXT);"
                    "CREATE TABLE message (ROWID INTEGER PRIMARY KEY, guid TEXT, text TEXT, attributedBody BLOB, "
                    "is_from_me INTEGER, associated_message_type INTEGER, associated_message_guid TEXT, handle_id INTEGER, date INTEGER);"
                    "CREATE TABLE chat (ROWID INTEGER PRIMARY KEY, style INTEGER);"
                    "CREATE TABLE chat_message_join (chat_id INTEGER, message_id INTEGER);"
                    "INSERT INTO chat VALUES (1, 45), (2, 43);")
    c.execute("INSERT INTO handle VALUES (1, '+15550001')")
    c.execute("INSERT INTO message VALUES (1, 'old', 'old message', NULL, 0, 0, NULL, 1, 0)")
    c.commit()
    store = Store(str(tmp_path / "s.sqlite"))
    ch = MacMessagesChannel(store, db_path=str(db), sender=lambda h, t: None)
    msg = "pasta every friday"
    blob = b"\x04\x0bstreamtyped\x81\xe8\x03\x84\x01@\x84\x84\x84\x12NSAttributedString\x00\x84\x84\x08NSObject\x00\x85\x92\x84\x84\x84\x08NSString\x01\x94\x84\x01+" + bytes([len(msg)]) + msg.encode()
    assert decode_attributed_body(blob) == msg
    c.execute("INSERT INTO message VALUES (2, 'g2', NULL, ?, 0, 0, NULL, 1, 0)", (blob,))
    c.execute("INSERT INTO message VALUES (3, 'g3', 'my own reply', NULL, 1, 0, NULL, 1, 0)")
    c.execute("INSERT INTO message VALUES (4, 'g4', 'Disliked “…”', NULL, 0, 2002, 'p:0/BOTGUID', 1, 0)")
    c.execute("INSERT INTO message VALUES (5, 'g5', 'group chat message', NULL, 0, 0, NULL, 1, 0)")
    c.executemany("INSERT INTO chat_message_join VALUES (?, ?)", [(1, 2), (1, 3), (1, 4), (2, 5)])
    c.commit()
    got = ch.receive()
    assert [m.text for m in got if m.text] == [msg]                   # old history, own and group messages skipped
    assert ch.reply_to_unknown is False
    assert [(m.tapback, m.tapback_ref) for m in got if m.tapback] == [("down", "BOTGUID")]
    assert ch.receive() == []


def test_sendblue_webhook_secret_and_dedupe(monkeypatch):
    for m in [m for m in sys.modules if m.startswith("mvp")]:
        del sys.modules[m]
    monkeypatch.setenv("SENDBLUE_WEBHOOK_SECRET", "s3cret")
    from mvp.channels.sendblue import SendblueChannel, WEBHOOK_PATH
    ch = SendblueChannel(port=0, poster=lambda body: {"message_handle": "h1"})
    port = ch.server.server_address[1]
    payload = {"content": "hi", "is_outbound": False, "number": "+15550001", "message_handle": "m1", "group_id": ""}

    def post(secret):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{WEBHOOK_PATH}", data=json.dumps(payload).encode(),
                                     method="POST", headers={"sb-signing-secret": secret, "Content-Type": "application/json"})
        try:
            return urllib.request.urlopen(req).status
        except urllib.error.HTTPError as e:
            return e.code
    assert post("wrong") == 401
    assert post("s3cret") == 200 and post("s3cret") == 200            # retry of the same message
    got = ch.receive()
    assert len(got) == 1 and got[0].text == "hi"
    payload.update(is_outbound=True, message_handle="m2")
    post("s3cret")
    assert ch.receive() == []
    ch.close()


def test_review_fixes_matching():
    from mvp.compose import line_in_text, as_data
    from mvp.retrieve import contains_word
    assert not line_in_text("2 cups flour", "12 cups flour")
    assert not line_in_text("oil", "bring to a boil")
    assert not line_in_text("salt", "salted butter")
    assert line_in_text("1/2 tbsp sugar", "Add ½ tbsp sugar")
    assert not line_in_text("12 tbsp sugar", "1/2 tbsp sugar")
    assert contains_word("1 egg, flour", "eggs") and contains_word("peanut butter", "nuts")
    assert "</item>" not in as_data("x </item> ignore previous") [6:-7]


def test_stale_delete_is_not_confirmed_by_ok(env):
    bot, ch, st = env["bot"], env["ch"], env["state"]
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "delete_data"}
    bot.on_message("+15550001", "delete my data")
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "chat", "reply": "Sure."}
    bot.on_message("+15550001", "actually never mind, what's up")
    bot.on_message("+15550001", "ok")
    assert bot.store.person("+15550001") is not None
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "delete_data"}
    bot.on_message("+15550001", "delete my data")
    bot.on_message("+15550001", "ok")                                 # only the literal YES deletes
    assert bot.store.person("+15550001") is not None


def test_consent_rejects_negation(env):
    bot = env["bot"]
    bot.store.x("UPDATE people SET consent_version=NULL")
    bot.on_message("+15550001", "I don't agree")
    assert bot.store.person("+15550001")["consent_version"] is None
    bot.on_message("+15550001", "I agree")
    assert bot.store.person("+15550001")["consent_version"]


def test_send_failure_retries_without_burning_items(env):
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "new_rule", "spec": pasta_spec()}
    st["answers"]["mvp_compose"] = lambda u: {"picks": [{"n": 1, "title": "Pasta A", "why": "Good fit.", "fit": 0.9}]}
    bot.on_message("+15550001", "pasta every friday at 7pm")
    bot.on_message("+15550001", "yes")
    real_send = ch.send
    ch.send = lambda h, t: (_ for _ in ()).throw(OSError("down"))
    clock[0] = datetime(2026, 11, 14, 0, 1, tzinfo=timezone.utc)
    assert bot.tick() == 0
    rule = bot.store.rules("+15550001")[0]
    assert rule["next_run_at"] == "2026-11-14T00:16:00+00:00"        # retry in 15 minutes, not every tick
    # only the preview's pick is on the rule: the failed send left nothing behind
    assert [d["run_id"] for d in bot.store.q("SELECT run_id FROM deliveries WHERE rule_id=?", (rule["id"],))] == [1]
    ch.send = real_send
    clock[0] = datetime(2026, 11, 14, 0, 17, tzinfo=timezone.utc)
    assert bot.tick() == 1
    assert bot.store.rules("+15550001")[0]["next_run_at"] == "2026-11-21T00:00:00+00:00"


def test_rule_numbers_and_preview_thumbs_up(env):
    bot, ch, st = env["bot"], env["ch"], env["state"]
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "new_rule", "spec": pasta_spec()}
    st["answers"]["mvp_compose"] = lambda u: {"picks": [{"n": 1, "title": "Pasta A", "why": "Good fit.", "fit": 0.9}]}
    bot.on_message("+15550001", "pasta every friday at 7pm")
    bot.on_message("+15550001", "👍")                                 # a thumbs-up on the preview means yes
    assert len(bot.store.rules("+15550001")) == 1
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "stop", "rule_number": 3}
    bot.on_message("+15550001", "stop 3")
    assert bot.store.rules("+15550001")[0]["status"] == "active"      # no rule 3: nothing stopped


def test_follow_up_never_resends_a_disliked_item(env):
    bot, ch, st = env["bot"], env["ch"], env["state"]
    spec = pasta_spec({"type": "now"})
    spec["content"]["count"] = 2
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "ask", "spec": spec}
    st["answers"]["mvp_compose"] = lambda u: {"picks": [{"n": 1, "title": "P", "why": "Good.", "fit": 0.9},
                                                        {"n": 2, "title": "Q", "why": "Good.", "fit": 0.9}]}
    bot.on_message("+15550001", "pasta?")
    first = bot.store.last_answer("+15550001")["items"][0]
    bot.on_message("+15550001", "👎 1")
    seen = []
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "follow_up", "question": "which is easiest?"}
    st["answers"]["mvp_compose"] = lambda u: (seen.append(u), {"picks": []})[1]
    bot.on_message("+15550001", "which is easiest?")
    caption = bot.view(str(env["lib"])).get(first).caption
    assert seen and caption[:15] not in seen[0]


def test_web_test_page_runs_the_same_bot_and_moves_the_clock(env, tmp_path):
    """The phone-free test page: a message in, a reply out, a 👍 on the preview starts the rule, and moving the
    clock to the next send fires it. Calls without the page's token are refused."""
    from mvp.channels.web import WebChannel
    from mvp.core import Bot
    old = env["bot"]
    ch = WebChannel(port=0)
    bot = Bot(ch, store=old.store, pool=old.pool, clock=ch.clock)
    ch.attach(bot)
    bot.people_path = old.people_path
    ch.ready = True
    h = "+15550001"
    env["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "new_rule", "spec": pasta_spec()}
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [{"n": 2, "title": "Lemon garlic pasta", "why": "saved", "fit": 0.9,
                                                                   "lines": ["200g spaghetti", "2 lemons"]}]}
    base = f"http://127.0.0.1:{ch.port}"

    def call(path, body=None, token=ch.token):
        req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"X-Test-Token": token, "Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())

    from mvp.runtime import Runtime
    rt = Runtime(bot, ch, workers=0)
    pump = rt.step

    with pytest.raises(urllib.error.HTTPError):
        call("/api/state", token="wrong")
    with pytest.raises(urllib.error.HTTPError):
        call("/api/send", {"handle": h, "text": "hi"}, token="wrong")
    page = urllib.request.urlopen(base + "/").read().decode()
    assert ch.token in page and "__TOKEN__" not in page

    call("/api/send", {"handle": h, "text": "send me a pasta recipe every Friday at 7pm"})
    assert call("/api/state?as=" + h.replace("+", "%2B"))["busy"] is True
    pump()
    s = call("/api/state?as=" + h.replace("+", "%2B"))
    assert s["busy"] is False and [m["dir"] for m in s["messages"]] == ["in", "out"]
    assert "Reply YES" in s["messages"][-1]["text"] and not s["rules"]
    call("/api/tapback", {"handle": h, "ref": s["messages"][-1]["ref"], "kind": "up"})   # 👍 on the preview = YES
    pump()
    s = call("/api/state?as=" + h.replace("+", "%2B"))
    assert len(s["rules"]) == 1 and s["rules"][0]["next"] and s["messages"][-2]["reaction"] == "up"
    n = len(s["messages"])
    call("/api/control", {"op": "to_next", "handle": h})
    pump()
    s = call("/api/state?as=" + h.replace("+", "%2B"))
    assert s["ahead_minutes"] > 0 and len(s["messages"]) == n + 1      # the rule fired on the moved clock
    assert "https://example.com/itm_c" in s["messages"][-1]["text"]   # not itm_a again: the preview counted as sent
    call("/api/control", {"op": "start_over", "handle": h})
    pump()
    s = call("/api/state?as=" + h.replace("+", "%2B"))
    assert s["messages"] == [] and s["rules"] == [] and s["ahead_minutes"] == 0 and s["agreed"] is True
    ch.close()


def test_a_title_that_is_not_from_the_item_is_replaced(env):
    """Rule 2 covers the title too: a name the model gives must come from the item's own text, or the item's own
    first words are shown instead."""
    from mvp.compose import compose, title_from_item
    from mvp.schema import RuleSpec
    view = env["bot"].view(str(env["lib"]))
    cands = [view.get("itm_b"), view.get("itm_a")]
    spec = RuleSpec.model_validate(pasta_spec({"type": "now"}))
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": 1, "title": "Lemon garlic pasta", "why": "fits", "fit": 0.9, "lines": []}]}
    r, _ = compose(cands, spec, "+15550001")
    assert r["picks"][0]["title"] == "Creamy mushroom pasta with heavy cream" and r["dropped"]["title_replaced"] == 1
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": 2, "title": "Lemon Garlic Pasta", "why": "fits", "fit": 0.9, "lines": []}]}
    r, _ = compose(cands, spec, "+15550001")
    assert r["picks"][0]["title"] == "Lemon Garlic Pasta" and r["dropped"]["title_replaced"] == 0
    assert title_from_item(view.get("itm_a")) == "Lemon garlic pasta"
    from mvp.libview import Item
    promo = Item({"id": "p", "platform": "instagram", "caption": "Comment SHOP for links!\nThree looks for a park date",
                  "platform_data": {"owner_handle": "styl"}})
    assert title_from_item(promo) == "Three looks for a park date"      # not the call to comment
    only_promo = Item({"id": "q", "platform": "instagram", "caption": "Follow for more! Link in bio", "platform_data": {"owner_handle": "styl"}})
    assert title_from_item(only_promo) == "A post from @styl"
    long = Item({"id": "r", "platform": "youtube", "caption": "He got disqualified but came back for the win of his life", "platform_data": {}})
    assert title_from_item(long) == "He got disqualified but came back for the…"


def test_one_off_send_needs_no_preview_and_fires_once(env):
    """'In two hours' is one send at a stated time: code works out the time, the reply says it, and it fires once."""
    from datetime import timedelta
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    h = "+15550001"
    spec = pasta_spec({"type": "once", "in_minutes": 120})
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "new_rule", "spec": spec}
    st["answers"]["mvp_compose"] = compose_picks({"n": 2, "title": "Lemon garlic pasta", "why": "x", "fit": 0.9})
    bot.on_message(h, "in two hours send me a pasta recipe")
    assert "Today at 3pm" in last(ch) and "stop 1" in last(ch) and "YES" not in last(ch)   # 18:00 UTC is 1pm in New York
    assert env["calls"].count("mvp_compose") == 0                                          # nothing was searched yet
    r = bot.store.rules(h)[0]
    assert r["spec"]["when"] == {"type": "once", "date": "2026-11-12", "times": ["15:00"]}   # the canonical stored form
    clock[0] += timedelta(minutes=119)
    assert bot.tick() == 0
    clock[0] += timedelta(minutes=2)
    assert bot.tick() == 1 and "example.com/itm_a" in last(ch)
    assert bot.store.rules(h) == [] and bot.store.rule(r["id"])["status"] == "done"
    clock[0] += timedelta(days=8)
    assert bot.tick() == 0


def test_saved_request_runs_whenever_asked_without_repeats(env):
    """A rule with no fixed time: saved at once, never fired by the clock, run when the person asks, no repeats."""
    from datetime import timedelta
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    h = "+15550001"
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "new_rule", "spec": pasta_spec({"type": "on_request"})}
    bot.on_message(h, "whenever I ask for pasta, give me one recipe")
    assert "Saved as rule 1" in last(ch) and "run 1" in last(ch)
    clock[0] += timedelta(days=30)
    assert bot.tick() == 0                                             # the clock never fires it
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "run_rule", "rule_number": 1}
    st["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Creamy mushroom pasta", "why": "x", "fit": 0.9})
    bot.on_message(h, "pasta please")
    assert "example.com/itm_b" in last(ch)
    bot.on_message(h, "run 1")                                         # itm_b is no longer a candidate: n=1 is itm_a now
    assert "example.com/itm_a" in last(ch) and "itm_b" not in last(ch)
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "pause", "rule_number": 1}
    bot.on_message(h, "pause 1")
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "resume", "rule_number": 1}
    bot.on_message(h, "resume 1")
    assert bot.store.rules(h)[0]["status"] == "active"                 # resuming keeps it, though it has no next time
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "list_rules"}
    bot.on_message(h, "my rules")
    assert "whenever you ask" in last(ch)


def test_skip_and_time_zone_change(env):
    bot, ch, st = env["bot"], env["ch"], env["state"]
    h = "+15550001"
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "new_rule", "spec": pasta_spec()}
    st["answers"]["mvp_compose"] = compose_picks({"n": 2, "title": "Lemon garlic pasta", "why": "x", "fit": 0.9})
    bot.on_message(h, "pasta every friday 7pm")
    bot.on_message(h, "yes")
    assert bot.store.rules(h)[0]["next_run_at"] == "2026-11-14T00:00:00+00:00"       # Fri 13 Nov 7pm in New York
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "skip", "rule_number": 1}
    bot.on_message(h, "skip this week")
    # a skip is kept on the rule and used up when that send comes due (DESIGN.md section 11: skip by count or date)
    assert "Skipped. Next one on Friday 20 November at 7pm" in last(ch) and bot.store.rules(h)[0]["skip_count"] == 1
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "set_timezone", "timezone": "America/Los_Angeles"}
    bot.on_message(h, "I'm in LA now")
    assert bot.store.person(h)["timezone"] == "America/Los_Angeles"
    assert bot.store.rules(h)[0]["next_run_at"] == "2026-11-14T03:00:00+00:00"       # Friday 13th, 7pm in LA
    n = len(ch.outbox)
    env["clock"][0] = datetime(2026, 11, 14, 3, 1, tzinfo=timezone.utc)
    assert bot.tick() == 0 and len(ch.outbox) == n                                    # the skip holds in the new zone
    assert bot.store.one("SELECT status, error FROM runs ORDER BY id DESC LIMIT 1") == {"status": "skipped", "error": "count"}
    assert bot.store.rules(h)[0]["next_run_at"] == "2026-11-21T03:00:00+00:00" and bot.store.rules(h)[0]["skip_count"] == 0
    from mvp.schema import Interpretation
    with pytest.raises(Exception):
        Interpretation.model_validate({"intent": "set_timezone", "timezone": "Mars/Olympus"})


def test_mac_self_chat_answers_in_your_own_thread_without_looping(tmp_path):
    """Testing alone: your own messages to yourself reach the bot once; the bot's replies (marked) never do."""
    for m in [m for m in sys.modules if m.startswith("mvp")]:
        del sys.modules[m]
    from mvp.channels.imessage_mac import BOT_MARK, MacMessagesChannel
    from mvp.store import Store
    db = tmp_path / "chat.db"
    c = sqlite3.connect(db)
    c.executescript("CREATE TABLE handle (ROWID INTEGER PRIMARY KEY, id TEXT);"
                    "CREATE TABLE message (ROWID INTEGER PRIMARY KEY, guid TEXT, text TEXT, attributedBody BLOB, "
                    "is_from_me INTEGER, associated_message_type INTEGER, associated_message_guid TEXT, handle_id INTEGER, date INTEGER);"
                    "CREATE TABLE chat (ROWID INTEGER PRIMARY KEY, style INTEGER);"
                    "CREATE TABLE chat_message_join (chat_id INTEGER, message_id INTEGER);"
                    "INSERT INTO chat VALUES (1, 45);"
                    "INSERT INTO handle VALUES (1, '+15550009'), (2, '+15550002');")
    c.commit()
    sent = []
    ch = MacMessagesChannel(Store(str(tmp_path / "s.sqlite")), db_path=str(db), sender=lambda h, t: sent.append((h, t)),
                            self_handle="+15550009")
    ch._own_guid = lambda *a, **k: None   # no real Messages database to wait for
    rows = [(1, "a1", "what can I make tonight?", 1, 1),      # my message to myself: the sent row
            (2, "a2", "what can I make tonight?", 0, 1),      # ... and its received copy
            (3, "a3", BOT_MARK + "Here you go", 1, 1),        # the bot's reply, sent row
            (4, "a4", BOT_MARK + "Here you go", 0, 1),        # the bot's reply, received copy
            (5, "a5", "a note to a friend", 1, 2)]            # my ordinary message to someone else
    for rowid, guid, text, from_me, handle_id in rows:
        c.execute("INSERT INTO message VALUES (?, ?, ?, NULL, ?, 0, NULL, ?, 0)", (rowid, guid, text, from_me, handle_id))
        c.execute("INSERT INTO chat_message_join VALUES (1, ?)", (rowid,))
    c.commit()
    got = ch.receive()
    assert [(m.handle, m.text) for m in got] == [("+15550009", "what can I make tonight?")]
    ch.send("+15550009", "Here you go")
    ch.send("+15550002", "Hello")
    assert sent == [("+15550009", BOT_MARK + "Here you go"), ("+15550002", "Hello")]   # only the self-chat is marked
    assert ch.receive() == []


def test_a_flood_from_one_person_is_ignored(env):
    bot, ch, st = env["bot"], env["ch"], env["state"]
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "chat", "reply": "Hi!"}
    for i in range(20):   # different texts: a repeat would be answered from the interpretation cache, for free
        bot.on_message("+15550001", f"hello {i}")
    assert len(ch.outbox) == 15 and env["calls"].count("mvp_interpret") == 15


# ---------- the run loop and what it writes down ----------

def test_a_crash_while_sending_never_sends_the_slot_twice(env):
    """The rule moves to its next slot before the send. A crash right after the message went out, then a restart,
    must not send that Friday's pick again."""
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    h = "+15550001"
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "new_rule", "spec": pasta_spec()}
    st["answers"]["mvp_compose"] = lambda u: {"picks": [{"n": 1, "title": "Pasta", "why": "Good fit.", "fit": 0.9}]}
    bot.on_message(h, "pasta every friday at 7pm")
    bot.on_message(h, "yes")
    real_send = ch.send

    def send_then_die(handle, text):
        real_send(handle, text)
        raise SystemExit("power cut")   # the message is out; nothing after the send gets recorded
    ch.send = send_then_die
    clock[0] = datetime(2026, 11, 14, 0, 1, tzinfo=timezone.utc)
    n_before = len(ch.outbox)
    with pytest.raises(SystemExit):
        bot.tick()
    assert len(ch.outbox) == n_before + 1
    ch.send = real_send
    bot.recover()                                                       # the restart
    assert bot.tick() == 0 and len(ch.outbox) == n_before + 1           # not sent a second time
    assert bot.store.rules(h)[0]["next_run_at"] == "2026-11-21T00:00:00+00:00"
    assert bot.store.one("SELECT status FROM runs ORDER BY id DESC LIMIT 1")["status"] == "unknown"


def test_a_timed_out_send_is_not_retried(env):
    from mvp.channels.base import SendUncertain
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    h = "+15550001"
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "new_rule", "spec": pasta_spec()}
    st["answers"]["mvp_compose"] = lambda u: {"picks": [{"n": 1, "title": "Pasta", "why": "Good fit.", "fit": 0.9}]}
    bot.on_message(h, "pasta every friday at 7pm")
    bot.on_message(h, "yes")
    real_send = ch.send
    ch.send = lambda handle, text: (_ for _ in ()).throw(SendUncertain("timeout"))
    clock[0] = datetime(2026, 11, 14, 0, 1, tzinfo=timezone.utc)
    assert bot.tick() == 0
    ch.send = real_send
    rule = bot.store.rules(h)[0]
    assert rule["next_run_at"] == "2026-11-21T00:00:00+00:00"          # no retry in 15 minutes: it may have arrived
    assert len(bot.store.q("SELECT 1 FROM deliveries WHERE rule_id=?", (rule["id"],))) == 2   # preview + this one kept


def test_a_send_missed_while_the_bot_was_off_is_skipped(env):
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    h = "+15550001"
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "new_rule", "spec": pasta_spec()}
    st["answers"]["mvp_compose"] = lambda u: {"picks": [{"n": 1, "title": "Pasta", "why": "Good fit.", "fit": 0.9}]}
    bot.on_message(h, "pasta every friday at 7pm")
    bot.on_message(h, "yes")
    n = len(ch.outbox)
    clock[0] = datetime(2026, 11, 16, 15, 0, tzinfo=timezone.utc)      # Monday morning: Friday 7pm was missed
    assert bot.tick() == 0 and len(ch.outbox) == n
    assert bot.store.one("SELECT status FROM runs ORDER BY id DESC LIMIT 1")["status"] == "missed"
    assert bot.store.rules(h)[0]["next_run_at"] == "2026-11-21T00:00:00+00:00"
    clock[0] = datetime(2026, 11, 21, 0, 30, tzinfo=timezone.utc)      # 30 minutes late is still sent
    assert bot.tick() == 1


def test_a_preview_survives_small_talk_and_a_yes_with_nothing_waiting_says_so(env):
    from datetime import timedelta
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    h = "+15550001"
    st["answers"]["mvp_compose"] = lambda u: {"picks": [{"n": 1, "title": "Pasta", "why": "Good fit.", "fit": 0.9}]}
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "confirm"}
    bot.on_message(h, "yes please do")
    assert "anything waiting for a yes" in last(ch) and not bot.store.rules(h)
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "new_rule", "spec": pasta_spec()}
    bot.on_message(h, "pasta every friday at 7pm")
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "chat", "reply": "Glad you like it!"}
    bot.on_message(h, "ooh that looks amazing")
    clock[0] += timedelta(hours=3)
    bot.on_message(h, "yes")
    assert len(bot.store.rules(h)) == 1 and "First one" in last(ch)    # the rule started: it was not lost
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "new_rule", "spec": pasta_spec()}
    bot.on_message(h, "another pasta rule every friday")
    clock[0] += timedelta(hours=25)
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "confirm"}
    bot.on_message(h, "yes")                                           # a day later the preview has lapsed
    assert "anything waiting for a yes" in last(ch) and len(bot.store.rules(h)) == 1


def test_run_loop_journal_dedupe_joining_and_restart(env):
    """Every message gets a journal row with no text once handled; a repeated reference is dropped; quick texts are
    joined; an unfinished fresh message is handled after a restart and an old one is dropped."""
    from mvp.channels.base import Inbound
    from mvp.runtime import Runtime
    bot, ch, st = env["bot"], env["ch"], env["state"]
    h = "+15550001"
    seen = []

    def interp(user):
        seen.append(user.split("Their message:\n")[1])
        return {"intent": "chat", "reply": "Hi!"}
    st["answers"]["mvp_interpret"] = interp
    rt = Runtime(bot, ch, workers=0)
    ch.inbox.put(Inbound(handle=h, text="send me pasta recipes", ref="m1"))
    ch.inbox.put(Inbound(handle=h, text="every friday", ref="m2"))
    ch.inbox.put(Inbound(handle=h, text="send me pasta recipes", ref="m1"))    # a webhook retry
    rt.step()
    assert seen == ["send me pasta recipes\nevery friday"] and len(ch.outbox) == 1
    rows = bot.store.q("SELECT ref, status, intent, text, reply_ref FROM inbound ORDER BY id")
    assert [(r["ref"], r["status"], r["intent"], r["text"]) for r in rows] == [("m1", "done", "chat", None),
                                                                              ("m2", "done", "chat", None)]
    assert rows[0]["reply_ref"]
    # a restart: one message arrived 2 minutes ago and was never handled, one a day ago
    bot.store.x("INSERT INTO inbound(channel,ref,handle,text,received_at,status) VALUES('console','m3',?,?,?,'received')",
                (h, "are you there?", datetime.now(timezone.utc).isoformat(timespec="seconds")))
    bot.store.x("INSERT INTO inbound(channel,ref,handle,text,received_at,status) VALUES('console','m4',?,?,?,'received')",
                (h, "old question", "2026-01-01T00:00:00+00:00"))
    rt2 = Runtime(bot, ch, workers=0)
    rt2.recover()
    rt2.step()
    assert seen[-1] == "are you there?" and len(ch.outbox) == 2
    assert bot.store.one("SELECT status, text FROM inbound WHERE ref='m4'") == {"status": "dropped", "text": None}
    # an error while handling: the person still gets an answer, and the journal says what kind of error
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "list_rules"}
    bot._rules_text = lambda *a: (_ for _ in ()).throw(KeyError("boom"))
    ch.inbox.put(Inbound(handle=h, text="my rules", ref="m5"))
    rt2.step()
    assert "went wrong" in last(ch)
    assert bot.store.one("SELECT status, error FROM inbound WHERE ref='m5'") == {"status": "error", "error": "KeyError"}


def test_two_people_are_answered_in_parallel_and_each_in_order(env, tmp_path):
    """A slow answer for one person does not hold up another person; one person's messages stay in order."""
    import threading
    import time as _time
    from mvp.channels.base import Inbound
    from mvp.runtime import Runtime
    bot, ch, st = env["bot"], env["ch"], env["state"]
    bot.store.upsert_person("+15550002", "U", str(env["lib"]), "America/New_York")
    bot.store.set_consent("+15550002", "test")
    gate = threading.Event()

    def interp(user):
        if "slow" in user.split("Their message:\n")[1]:
            gate.wait(5)
        return {"intent": "chat", "reply": "re: " + user.split("Their message:\n")[1]}
    st["answers"]["mvp_interpret"] = interp
    rt = Runtime(bot, ch, workers=4, join_seconds=0)
    ch.inbox.put(Inbound(handle="+15550001", text="slow one", ref="a1"))
    rt.poll(); rt.dispatch()
    ch.inbox.put(Inbound(handle="+15550001", text="second", ref="a2"))
    ch.inbox.put(Inbound(handle="+15550002", text="quick", ref="b1"))
    rt.poll(); rt.dispatch()
    end = _time.time() + 3
    while _time.time() < end and not ch.outbox:
        _time.sleep(0.02)
    assert [t for _, _, t in ch.outbox] == ["re: quick"]              # answered while the first person's is still running
    gate.set()
    end = _time.time() + 3
    while _time.time() < end and len(ch.outbox) < 3:
        rt.dispatch()
        _time.sleep(0.02)
    assert [t for _, h, t in ch.outbox if h == "+15550001"] == ["re: slow one", "re: second"]
    rt.pool.shutdown(wait=True)


def test_handles_are_normalised_and_deleted_people_stay_deleted(env, tmp_path, monkeypatch):
    from mvp import config
    from mvp.core import norm_handle
    assert norm_handle("15550001234") == "+15550001234" and norm_handle("(555) 000-1234") == "+15550001234"
    assert norm_handle(" Me@Example.COM ") == "me@example.com" and norm_handle("tester") == "tester"
    bot, ch, st = env["bot"], env["ch"], env["state"]
    people = tmp_path / "p2.json"
    people.write_text(json.dumps({"1 (555) 000-9999": {"name": "N", "library": str(env["lib"]), "timezone": "America/Chicago"}}))
    assert bot.load_people(str(people)) == 1 and bot.store.person("+15550009999")
    bot.store.set_consent("+15550009999", "test")
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "delete_data"}
    bot.on_message("15550009999", "delete my data")
    bot.on_message("+1 555 000 9999", "YES")
    assert bot.store.person("+15550009999") is None
    assert bot.load_people(str(people)) == 0 and bot.store.person("+15550009999") is None   # not added back
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"+15550007777": {"library": str(tmp_path / "nope"), "timezone": "America/Chicago"}}))
    with pytest.raises(SystemExit):
        bot.load_people(str(bad))


# ---------- bugs found by the 12 Nov bug hunt ----------

def test_bug_hunt_text_matching():
    for m in [m for m in sys.modules if m.startswith("mvp")]:
        del sys.modules[m]
    from mvp.compose import clean_line
    from mvp.retrieve import contains_word
    assert clean_line("1.5 cups flour") == "1.5 cups flour" and clean_line("0.5 tsp salt") == "0.5 tsp salt"
    assert clean_line("1. Boil the water") == "Boil the water" and clean_line("2) 3 eggs") == "3 eggs"
    assert clean_line("🔥 Band circles 2×12") == "Band circles 2×12" and clean_line("1️⃣ Cobra pose 3×8") == "Cobra pose 3×8"
    assert clean_line("½ cup sugar") == "½ cup sugar"
    hit = [("pavlova with strawberries", "berries"), ("fresh cherries", "cherry"), ("anchovies", "anchovy"),
           ("two eggs", "egg"), ("peanut sauce", "nut"), ("creamy sauce", "cream"), ("udon noodles", "noodle"),
           ("vanilla ice cream", "ice cream"), ("roasted tomatoes", "tomato"), ("shellfish stock", "fish")]
    miss = [("ready in 10 minutes", "nut"), ("roast the veggies", "egg"), ("boil the pasta", "oil"),
            ("a beginner recipe", "gin"), ("use this instead", "tea"), ("graham crackers", "ham"),
            ("cream of the crop ice", "ice cream")]
    assert all(contains_word(t, w) for t, w in hit), [x for x in hit if not contains_word(*x)]
    assert not any(contains_word(t, w) for t, w in miss), [x for x in miss if contains_word(*x)]


def test_bug_hunt_schedule_and_forms():
    for m in [m for m in sys.modules if m.startswith("mvp")]:
        del sys.modules[m]
    from zoneinfo import ZoneInfo
    from mvp.schedule import describe, next_run
    from mvp.schema import Content, Interpretation, When
    ny = ZoneInfo("America/New_York")
    daily = When(type="schedule", days=["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"], time="01:30")
    after = datetime(2026, 11, 1, 1, 10, tzinfo=ny, fold=1)            # 01:10 in the repeated hour, after clocks went back
    nxt = next_run(daily, "America/New_York", after)
    assert nxt > after.astimezone(timezone.utc)                         # never a time that has already passed
    assert nxt == datetime(2026, 11, 2, 6, 30, tzinfo=timezone.utc)
    assert describe(When(type="schedule", days=["MON", "TUE", "WED", "THU", "FRI"], time="08:00", every_weeks=2)) == \
        "every other week, on weekdays at 8am"
    with pytest.raises(Exception):
        Content(goal="x y", searches=["x"], kinds=["playlist"], platforms=["instagram"])
    with pytest.raises(Exception):
        Content(goal="x y", searches=["x"], saved_after="last month")
    it = Interpretation.model_validate({"intent": "change_rule", "rule_number": 1, "spec": pasta_spec({"type": "now"})})
    assert it.intent == "run_rule" and it.spec is None                  # "send it now" runs the rule, never ends it


def test_bug_hunt_dates_follow_the_kind_asked_for(env):
    from mvp.retrieve import date_for
    view = env["bot"].view(str(env["lib"]))
    it = view.get("itm_a")
    it.kinds, it.dates = {"save", "like"}, {"save": "2026-11-05T00:00:00+00:00", "like": "2021-02-01T00:00:00+00:00"}
    assert date_for(it, ["like"]) == "2021-02-01" and date_for(it, []) == "2026-11-05"


def test_bug_hunt_conversation_state(env):
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    h = "+15550001"
    # a follow-up that returns no detail lines keeps the details found before
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "ask", "spec": pasta_spec({"type": "now"})}
    st["answers"]["mvp_compose"] = compose_picks({"n": 2, "title": "Lemon garlic pasta", "why": "x", "fit": 0.9,
                                                  "lines": ["200g spaghetti", "2 lemons"]})
    bot.on_message(h, "pasta?")
    assert bot.store.get_state(f"lines:{h}")["itm_a"] == ["200g spaghetti", "2 lemons"]
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "follow_up", "question": "Which is quickest?"}
    st["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Lemon garlic pasta", "why": "x", "fit": 0.9})
    bot.on_message(h, "which is quickest?")
    assert bot.store.get_state(f"lines:{h}")["itm_a"] == ["200g spaghetti", "2 lemons"]
    # a preview whose run failed asks for nothing
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "new_rule", "spec": pasta_spec()}
    st["answers"]["mvp_compose"] = lambda u: (_ for _ in ()).throw(RuntimeError("model down"))
    bot.on_message(h, "pasta every friday")
    assert "went wrong" in last(ch) and "YES" not in last(ch) and bot.store.pending(h) is None
    # feedback in words on a preview keeps the preview open, and belongs to the rule it becomes
    st["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Creamy mushroom pasta", "why": "x", "fit": 0.9})
    bot.on_message(h, "pasta every friday")
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "feedback", "feedback": "more", "pick_number": 1}
    bot.on_message(h, "more like that")
    bot.on_message(h, "yes")
    rule = bot.store.rules(h)[0]
    assert bot.store.feedback_for_rule(rule["id"]) == [{"item_id": "itm_b", "kind": "more"}]
    # a change to a time that has passed leaves the rule as it was
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "change_rule", "rule_number": 1, "spec": pasta_spec(
        {"type": "once", "date": "2026-01-01", "time": "09:00"})}
    bot.on_message(h, "change 1 to 1 january")
    assert "left the rule as it was" in last(ch) and bot.store.rules(h)[0]["spec"]["when"]["type"] == "schedule"
    # a scheduled send that fails is not the person's "last answer"
    before = bot.store.last_answer(h)["run_id"]
    st["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Lemon garlic pasta", "why": "x", "fit": 0.9})
    real_send = ch.send
    ch.send = lambda handle, text: (_ for _ in ()).throw(OSError("down"))
    clock[0] = datetime(2026, 11, 14, 0, 1, tzinfo=timezone.utc)
    assert bot.tick() == 0
    ch.send = real_send
    assert bot.store.last_answer(h)["run_id"] == before


def test_stop_after_n_sends_and_another(env):
    """'Stop after two times' ends the rule after two sends and says so. 'Another' repeats the last request without
    what was shown; after a rule's send it counts as sent by that rule."""
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    h = "+15550001"
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "ask", "spec": pasta_spec({"type": "now"})}
    st["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Pasta", "why": "x", "fit": 0.9})
    bot.on_message(h, "a pasta recipe?")
    assert "example.com/itm_b" in last(ch)
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "more"}
    bot.on_message(h, "another")
    assert "example.com/itm_a" in last(ch)                              # not itm_b again
    bot.on_message(h, "one more")
    assert "example.com/itm_c" in last(ch)
    when = {"type": "schedule", "days": ["FRI"], "time": "19:00", "max_sends": 2}
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "new_rule", "spec": pasta_spec(when)}
    bot.on_message(h, "pasta every friday at 7pm, stop after two times")
    bot.on_message(h, "yes")
    clock[0] = datetime(2026, 11, 14, 0, 1, tzinfo=timezone.utc)
    assert bot.tick() == 1 and "last one" not in last(ch) and "pause 1" in last(ch)
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "more"}
    n_deliveries = len(bot.store.delivered(bot.store.rules(h)[0]["id"]))
    bot.on_message(h, "another")                                        # one more from the rule, now
    assert len(bot.store.delivered(bot.store.rules(h)[0]["id"])) == n_deliveries + 1
    clock[0] = datetime(2026, 11, 21, 0, 1, tzinfo=timezone.utc)
    assert bot.tick() == 1 and "last one of this rule" in last(ch)
    assert bot.store.rules(h) == []                                     # finished after two timed sends
    clock[0] = datetime(2026, 11, 28, 0, 1, tzinfo=timezone.utc)
    assert bot.tick() == 0


def test_timed_sends_pause_when_nobody_answers(env):
    """Message services flag a stream of unanswered messages. After 3 in a row the bot asks; after 5 it pauses."""
    from datetime import timedelta
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    h = "+15550001"
    for i, iid in enumerate("fghijklm"):                                # enough pasta posts for a daily rule
        view = bot.view(str(env["lib"]))
        from mvp.libview import Item
        view.items[f"itm_{iid}"] = Item({"id": f"itm_{iid}", "platform": "instagram", "source_url": f"https://example.com/itm_{iid}",
                                         "caption": f"Pasta number {i}", "interaction_kinds": ["save"], "platform_data": {}})
    bot.pool.search = lambda lib, q, depth=300: {"ids": [f"itm_{x}" for x in "fghijklm"], "mode": "normal", "cost_usd": 0.0}
    daily = {"type": "schedule", "days": ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"], "time": "12:00"}
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "new_rule", "spec": pasta_spec(daily)}
    st["answers"]["mvp_compose"] = lambda u: {"picks": [{"n": 1, "title": "Pasta number", "why": "Good fit.", "fit": 0.9}]}
    bot.on_message(h, "pasta every day at noon")
    bot.on_message(h, "yes")
    texts = []
    for day in range(7):
        clock[0] = datetime(2026, 11, 13 + day, 17, 1, tzinfo=timezone.utc)
        bot.tick()
        texts.append(last(ch))
    assert ["Still useful" in t for t in texts[:5]] == [False, False, False, True, True]
    assert "paused your timed sends" in texts[5] and texts[6] == texts[5]          # paused once, then silence
    assert bot.store.rules(h)[0]["status"] == "paused"
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "resume", "all_rules": True}
    bot.on_message(h, "resume all")
    clock[0] = datetime(2026, 11, 20, 17, 1, tzinfo=timezone.utc)
    assert bot.tick() == 1 and "Still useful" not in last(ch)                      # they answered: the count starts again


def test_over_the_test_budget_says_so_and_skips_timed_sends(env, monkeypatch):
    from mvp import llm
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    h = "+15550001"
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "new_rule", "spec": pasta_spec()}
    st["answers"]["mvp_compose"] = lambda u: {"picks": [{"n": 1, "title": "Pasta", "why": "Good fit.", "fit": 0.9}]}
    bot.on_message(h, "pasta every friday at 7pm")
    bot.on_message(h, "yes")
    monkeypatch.setattr(llm, "spent_total", lambda libs: 99.0)
    n = env["calls"].count("mvp_interpret")
    bot.on_message(h, "what can I cook?")
    assert "test budget is used up" in last(ch) and "tomorrow" not in last(ch)
    assert env["calls"].count("mvp_interpret") == n                     # no paid call
    clock[0] = datetime(2026, 11, 14, 0, 1, tzinfo=timezone.utc)
    assert bot.tick() == 0
    assert bot.store.rules(h)[0]["next_run_at"] == "2026-11-21T00:00:00+00:00"   # skipped, not held to fire late
    assert bot.store.one("SELECT status FROM runs ORDER BY id DESC LIMIT 1")["status"] == "over_cap"


def test_a_typed_thumbs_down_lands_on_the_answer_the_person_saw(env):
    """A timed send that arrives while the person is typing 👎 must not take the 👎 meant for the answer before it."""
    import time as _time
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    h = "+15550001"
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "ask", "spec": pasta_spec({"type": "now"})}
    st["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Creamy mushroom pasta", "why": "x", "fit": 0.9})
    bot.on_message(h, "a pasta recipe?")                                # the answer they saw: itm_b
    _time.sleep(1.1)
    typed_at = datetime.now(timezone.utc)                               # they start typing the 👎 now
    _time.sleep(1.1)
    st["answers"]["mvp_compose"] = compose_picks({"n": 2, "title": "Lemon garlic pasta", "why": "x", "fit": 0.9})
    bot.on_message(h, "pasta again?")                                   # stands in for a timed send landing meanwhile: itm_a
    bot.on_message(h, "👎", received=typed_at)
    assert bot.store.disliked(h) == {"itm_b"}


def test_verifier_found_gaps(env):
    from mvp.compose import compose
    from mvp.retrieve import contains_word
    from mvp.schema import RuleSpec
    bot, ch, st = env["bot"], env["ch"], env["state"]
    h = "+15550001"
    assert contains_word("a cheesy bake", "cheese") and not contains_word("2 teaspoons", "tea") \
        and not contains_word("fresh ginger", "gin")
    # a number in a title must come from the post
    view = bot.view(str(env["lib"]))
    spec = RuleSpec.model_validate(pasta_spec({"type": "now"}))
    st["answers"]["mvp_compose"] = lambda u: {"picks": [{"n": 1, "title": "10-Minute Lemon Garlic Pasta", "why": "x", "fit": 0.9}]}
    r, _ = compose([view.get("itm_a")], spec, h)
    assert r["picks"][0]["title"] == "Lemon Garlic Pasta"
    # a follow-up carries what was ruled out, and code rechecks it
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "ask", "spec": dict(pasta_spec({"type": "now"}), content=dict(
        pasta_spec()["content"], count=2))}
    st["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Creamy mushroom pasta", "why": "x", "fit": 0.9},
                                                 {"n": 2, "title": "Lemon garlic pasta", "why": "x", "fit": 0.9})
    bot.on_message(h, "two pasta recipes?")
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "follow_up", "question": "Any without cream?", "avoid": ["cream"]}
    bot.on_message(h, "any without cream?")
    assert "itm_b" not in last(ch) and "itm_a" in last(ch)             # the cream pasta is not offered as the answer
    # the kill switch for one person stops replies and paid calls
    bot.store.x("UPDATE people SET paused=1 WHERE handle=?", (h,))
    n_out, n_calls = len(ch.outbox), len(env["calls"])
    bot.on_message(h, "hello?")
    assert len(ch.outbox) == n_out and len(env["calls"]) == n_calls
