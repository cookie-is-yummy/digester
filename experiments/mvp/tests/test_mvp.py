"""Offline tests for the MVP skeleton: synthetic library, fake model, fake search engine. No API calls, no real data."""
import json
import os
import sqlite3
import sys
import urllib.request
from datetime import datetime, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("MVP_HOME", str(tmp_path / "home"))
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

    def fake_chat(system, user, purpose, prompt_version, person=None, max_tokens=0):
        calls.append(purpose)
        return env_state["answers"][purpose](user), 0.001
    env_state = {"answers": {}}
    monkeypatch.setattr(llm, "chat_json", fake_chat)
    monkeypatch.setattr(llm, "spent_today", lambda h, l: 0.0)
    monkeypatch.setattr(llm, "spent_total", lambda libs, since: 0.0)
    for name in ("interpret", "compose"):
        mod = __import__(f"mvp.{name}", fromlist=["x"])
        monkeypatch.setattr(mod.llm, "chat_json", fake_chat)

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
    assert first.date().isoformat() == "2026-11-23"


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
    assert "don't have your library" in last(ch)


def test_mac_reader_decodes_attributed_body_and_tapbacks(tmp_path):
    for m in [m for m in sys.modules if m.startswith("mvp")]:
        del sys.modules[m]
    from mvp.channels.imessage_mac import MacMessagesChannel, decode_attributed_body
    from mvp.store import Store
    db = tmp_path / "chat.db"
    c = sqlite3.connect(db)
    c.executescript("CREATE TABLE handle (ROWID INTEGER PRIMARY KEY, id TEXT);"
                    "CREATE TABLE message (ROWID INTEGER PRIMARY KEY, guid TEXT, text TEXT, attributedBody BLOB, "
                    "is_from_me INTEGER, associated_message_type INTEGER, associated_message_guid TEXT, handle_id INTEGER, date INTEGER);")
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
    c.commit()
    got = ch.receive()
    assert [m.text for m in got if m.text] == [msg]                   # old history and own messages skipped
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
