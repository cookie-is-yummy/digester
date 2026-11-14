"""Offline tests for round 8, slice B, I2 and I3 (DESIGN.md section 15): "export my data" / "export my lists" (and
"email it to me" after one), and the forward-ready share text ("share it", "send this to my sister"). Synthetic data, a
fake model, a fake search pool and a fake clock (12 Nov 2026, New York); no network (no SMTP is set)."""
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import compose_picks, env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_round7 import UI_ASK, ask, ig, ui  # noqa: E402,F401  (ui is a fixture)
from mvp.tests.test_slice2 import H, ask_pasta, lemon_pick, say  # noqa: E402
from mvp.tests.test_slice4 import confirmed, last_code, outbox_rows, read_eml  # noqa: E402

HINT = "Press and hold that message to forward it. I can't send to other people myself."
HINT_ES = "Mantén pulsado ese mensaje para reenviarlo. Yo no puedo enviar mensajes a otras personas."
CHAT = {"intent": "chat", "reply": "Sure."}


def texts_of(ch, n):
    return [t for _, _, t in ch.outbox[-n:]]


def model_calls(e):
    return sum(1 for c in e["calls"] if c == "mvp_interpret")


def two_picks():
    return compose_picks({"n": 1, "title": "Lemon garlic pasta", "why": "Fits.", "verdict": "clear"},
                         {"n": 2, "title": "Pasta night", "why": "Fits.", "verdict": "clear"})


def folder(bot, kind="export"):
    from mvp.actions.base import outbox_dir
    return os.path.join(outbox_dir(H), f"{kind}-2026-11-12")


def all_text(d):
    out = ""
    for name in os.listdir(d):
        with open(os.path.join(d, name), encoding="utf-8") as f:
            out += f.read()
    return out


# ---------- I2: export my data ----------
def test_export_my_data_writes_every_file_in_its_shape(env):
    bot = env["bot"]
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(env, "pasta", ask_pasta())
    bot.store.add_rule(H, "pasta every friday", {"when": {"type": "schedule", "days": ["FRI"], "time": "19:00"},
                                                  "content": {"goal": "a pasta recipe", "searches": ["pasta"]}},
                       "active", "2026-11-14T00:00:00+00:00")
    from datetime import datetime, timezone
    bot.store.add_todo(H, 'buy "good" basil, fresh', due_at=datetime(2026, 11, 13, 14, 0, tzinfo=timezone.utc))
    done = bot.store.add_todo(H, "call the plumber", list_name="home")
    bot.store.update_todo(done, done_at="2026-11-12T10:00:00+00:00")
    gone = bot.store.add_todo(H, "removed one")
    bot.store.update_todo(gone, removed_at="2026-11-12T10:00:00+00:00")
    n = model_calls(env)
    msg = say(env, "export my data", CHAT)
    assert model_calls(env) == n                                   # read by code
    d = folder(bot)
    from mvp import texts as T
    assert msg == T.export_done(4, os.path.relpath(d, os.environ["MVP_HOME"]))
    assert msg.startswith("I saved a copy of your data:") and "outbox/" in msg and "export-2026-11-12" in msg
    assert sorted(os.listdir(d)) == sorted(["rules.json", "todos.csv", "todos.md", "profile.json", "answers.md",
                                            "saves.csv", "README.txt"])
    with open(os.path.join(d, "todos.csv"), encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["title", "due date", "notes", "done"]
    assert rows[1:] == [['buy "good" basil, fresh', "2026-11-13 09:00", "", "no"],
                        ["call the plumber", "", "list: home", "yes"]]          # never a removed one
    md = open(os.path.join(d, "todos.md"), encoding="utf-8").read()
    assert '- [ ] buy "good" basil, fresh (due 2026-11-13 09:00)' in md and "## home\n- [x] call the plumber" in md
    rules = json.load(open(os.path.join(d, "rules.json"), encoding="utf-8"))
    assert rules[0]["your_words"] == "pasta every friday" and rules[0]["when"] == "every Friday at 7pm"
    assert rules[0]["status"] == "active" and rules[0]["number"] == 1
    prof = json.load(open(os.path.join(d, "profile.json"), encoding="utf-8"))
    assert {"interests", "direction", "prefs", "notes", "email", "timezone"} <= set(prof)
    answers = open(os.path.join(d, "answers.md"), encoding="utf-8").read()
    assert "## a pasta recipe" in answers and "I recommend Lemon garlic pasta" in answers
    assert "https://example.com/itm_a" in answers
    assert "Saying \"delete my data\" to the bot removes this folder too." in open(os.path.join(d, "README.txt")).read()
    row = bot.store.one("SELECT action, status FROM action_log WHERE action='export.data'")
    assert row["status"] == "done"


def test_saves_csv_has_links_and_dates_but_no_post_text_and_no_friends(env):
    bot = env["bot"]
    say(env, "download my data", CHAT)
    d = folder(bot)
    with open(os.path.join(d, "saves.csv"), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == ["id", "link", "platform", "kept date", "how"]
    assert sorted(r["id"] for r in rows) == ["itm_a", "itm_b", "itm_c", "itm_e"]     # itm_d is a friend's post
    assert rows[0]["kept date"] == "2026-03-01" and rows[0]["link"].startswith("https://example.com/")
    text = all_text(d)
    for caption_words in ("Lemon garlic", "spaghetti", "Creamy mushroom", "Pasta night", "carbonara"):
        assert caption_words not in open(os.path.join(d, "saves.csv"), encoding="utf-8").read()
    assert "itm_d" not in text and "My friend's pasta" not in text


def test_the_phrasings_that_export_and_the_ones_that_do_not(env):
    from mvp.followup import EMAIL_EXPORT, EXPORT_DATA, EXPORT_LISTS
    for t in ("export my data", "Export my data please", "download my data", "send me everything you have on me",
              "give me a copy of my data", "can you export all my data?", "export everything you know about me"):
        assert EXPORT_DATA.match(t), t
    for t in ("send me my list", "what data do you have on me", "export my data to google drive", "delete my data",
              "export my blender videos", "my data"):
        assert not EXPORT_DATA.match(t), t
    for t in ("export my lists", "export my to-do list", "download my todos as a csv", "export my list"):
        assert EXPORT_LISTS.match(t), t
    for t in ("send me my list", "what's on my list", "export my shopping list to notion"):
        assert not EXPORT_LISTS.match(t), t
    for t in ("email it to me", "email me the files", "e-mail them", "send it to my email", "email my data to me"):
        assert EMAIL_EXPORT.match(t), t
    # "send me my list" is still the list in the chat, from the model as before
    n = model_calls(env)
    say(env, "send me my list", {"intent": "todo_list"})
    assert model_calls(env) == n + 1 and not os.path.isdir(folder(env["bot"]))


def test_export_my_lists_writes_only_the_two_todo_files(env):
    bot = env["bot"]
    msg = say(env, "export my lists", CHAT)
    from mvp import texts as T
    assert msg == T.EXPORT_LISTS_EMPTY and not os.path.isdir(folder(bot, "lists"))
    bot.store.add_todo(H, "buy basil")
    msg = say(env, "export my to-do list", CHAT)
    assert msg.startswith("I saved your lists (1 to-do) as two files: todos.csv")
    assert sorted(os.listdir(folder(bot, "lists"))) == ["todos.csv", "todos.md"]
    assert not os.path.isdir(folder(bot, "export"))


def test_email_it_to_me_after_an_export_sends_the_files(env):
    bot = env["bot"]
    confirmed(env)
    bot.store.add_todo(H, "buy basil")
    say(env, "export my data", CHAT)
    n = model_calls(env)
    msg = say(env, "email it to me", {"intent": "act_on_last", "actions": ["email.send"]})
    assert model_calls(env) == n
    assert msg == "Email isn't connected here, so I didn't send it. The email with your files is in the bot's outbox " \
                  "folder."
    row = outbox_rows(bot, "email")[-1]
    m = read_eml(row["path"])
    assert m["To"] == "a@b.co" and m["Subject"] == "Your data"
    assert sorted(a.get_filename() for a in m.iter_attachments()) == sorted(
        ["rules.json", "todos.csv", "todos.md", "profile.json", "answers.md", "saves.csv", "README.txt"])
    assert "README.txt says what each one is." in m.get_body(("plain",)).get_content()


def test_email_it_to_me_without_a_confirmed_address_waits_for_the_code(env):
    bot = env["bot"]
    say(env, "export my lists", CHAT)   # empty: nothing to email
    bot.store.add_todo(H, "buy basil")
    say(env, "export my lists", CHAT)
    from mvp import texts as T
    assert say(env, "email them", CHAT) == T.EMAIL_ASK
    say(env, "a@b.co", CHAT)
    msg = say(env, last_code(bot), CHAT)
    assert msg.startswith("Thanks, a@b.co is confirmed.") and "\"Your lists\"" in msg
    m = read_eml(outbox_rows(bot, "email")[-1]["path"])
    assert sorted(a.get_filename() for a in m.iter_attachments()) == ["todos.csv", "todos.md"]


def test_email_it_to_me_means_the_answer_again_once_a_new_answer_came_or_an_hour_passed(env):
    from datetime import timedelta
    bot = env["bot"]
    confirmed(env)
    say(env, "export my data", CHAT)
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(env, "pasta", ask_pasta())
    n = model_calls(env)
    say(env, "email it to me", {"intent": "act_on_last", "actions": ["email.send"]})
    assert model_calls(env) == n + 1                               # the interpreter's act_on_last, as before
    assert read_eml(outbox_rows(bot, "email")[-1]["path"])["Subject"] == "From your saves: a pasta recipe"
    say(env, "export my data", CHAT)
    env["clock"][0] += timedelta(minutes=61)
    n = model_calls(env)
    say(env, "email it to me", {"intent": "act_on_last", "actions": ["email.send"]})
    assert model_calls(env) == n + 1


def test_a_file_over_5mb_is_not_emailed(tmp_path, env):
    from mvp import export as X
    small, big = tmp_path / "todos.csv", tmp_path / "saves.csv"
    small.write_text("title,due date,notes,done\n")
    big.write_bytes(b"x" * (X.EMAIL_MAX_BYTES + 1))
    att, left = X.attachments([("todos.csv", str(small)), ("saves.csv", str(big))])
    assert [a[0] for a in att] == ["todos.csv"] and att[0][2:] == ("text", "csv") and left == ["saves.csv"]
    from mvp import texts as T
    assert T.export_emailed("a@b.co", "smtp", None, "x", left) == ("I emailed your files to a@b.co. saves.csv is too big "
                                                                   "to email (over 5 MB), so it's only in the folder.")


def test_delete_my_data_removes_the_export_folders(env):
    bot = env["bot"]
    bot.store.add_todo(H, "buy basil")
    say(env, "export my data", CHAT)
    say(env, "export my lists", CHAT)
    assert os.path.isdir(folder(bot)) and os.path.isdir(folder(bot, "lists"))
    say(env, "delete my data", {"intent": "delete_data"})
    say(env, "YES", CHAT)
    assert not os.path.isdir(folder(bot)) and not os.path.isdir(folder(bot, "lists"))
    assert bot.store.person(H) is None


def test_a_second_export_the_same_day_replaces_the_first(env):
    bot = env["bot"]
    say(env, "export my data", CHAT)
    with open(os.path.join(folder(bot), "stray.txt"), "w") as f:
        f.write("x")
    say(env, "export my data", CHAT)
    assert "stray.txt" not in os.listdir(folder(bot))


# ---------- I3: a message to forward ----------
def test_share_it_gives_a_message_to_forward_then_the_hint(env):
    bot, ch = env["bot"], env["ch"]
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(env, "pasta", ask_pasta())
    n, sent = model_calls(env), len(ch.outbox)
    say(env, "share it", CHAT)
    assert model_calls(env) == n and len(ch.outbox) == sent + 2
    share, hint = texts_of(ch, 2)
    assert share == "Lemon garlic pasta by @chef\nhttps://example.com/itm_a"
    assert hint == HINT
    for personal in ("you saved", "you sent", "I recommend", "because", "March", "Reply", "rule"):
        assert personal not in share
    assert bot.store.one("SELECT action FROM action_log WHERE action='share.text'")


def test_send_this_to_my_sister_never_repeats_or_keeps_who_it_is_for(env):
    bot, ch = env["bot"], env["ch"]
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(env, "pasta", ask_pasta())
    for t in ("send this to my sister", "forward this", "Forward that to Maria please", "share it with my team",
              "can you share this one with my roommate?", "send the recipe to my sister", "share the link"):
        say(env, t, CHAT)
        share, hint = texts_of(ch, 2)
        assert share.startswith("Lemon garlic pasta by @chef") and hint == HINT, t
    blob = json.dumps([bot.store.q(f"SELECT * FROM {t}") for t in ("requests", "inbound", "state", "action_log")])
    for who in ("sister", "Maria", "roommate"):
        assert who not in blob and not any(who in m for _, _, m in ch.outbox)


def test_share_a_pick_by_number_with_its_first_key_point(env):
    bot, ch = env["bot"], env["ch"]
    env["state"]["answers"]["mvp_compose"] = two_picks()
    form = ask_pasta()
    form["spec"]["content"]["count"] = 2   # two picks shown as picks (with count 1 the second is a wider link)
    say(env, "pasta", form)
    run = bot.store.last_answer(H)["run_id"]
    snap = bot.store.answer(run)
    snap["picks"][1]["facts"] = {"key_points": ["Make it on a Friday night with friends"]}
    bot.store.x("UPDATE answers SET picks=? WHERE run_id=?", (json.dumps(snap["picks"]), run))
    say(env, "share the second one", CHAT)
    assert texts_of(ch, 2) == ["Pasta night by @chef\nMake it on a Friday night with friends\nhttps://example.com/itm_c",
                               HINT]
    say(env, "share #1", CHAT)
    assert texts_of(ch, 2)[0] == "Lemon garlic pasta by @chef\nhttps://example.com/itm_a"
    say(env, "share them", CHAT)
    assert texts_of(ch, 2)[0].split("\n\n") == ["Lemon garlic pasta by @chef\nhttps://example.com/itm_a",
                                                ("Pasta night by @chef\nMake it on a Friday night with friends\n"
                                                 "https://example.com/itm_c")]
    from mvp import texts as T
    assert say(env, "share the third one", CHAT) == T.which_pick(2)


def test_share_a_thing_of_an_items_answer_by_number_and_by_name(ui):
    ch = ui["ch"]
    say(ui, UI_ASK, ask("UI/UX libraries"))
    say(ui, "share the fourth one", CHAT)
    want = f"Iconoir: free open source icons\nFrom \"High-quality icon sites\" by @iconfan\n{ig('2022-09-01', 2)}"
    assert texts_of(ch, 2) == [want, HINT]
    say(ui, "send iconoir to my brother", CHAT)
    assert texts_of(ch, 2) == [want, HINT]
    say(ui, "share the Ant Design one", CHAT)
    assert texts_of(ch, 2)[0].startswith("Ant Design: an enterprise-class UI design language\nFrom \"Best design")
    from mvp import texts as T
    assert say(ui, "share the ninth one", CHAT) == T.which_item(5)


def test_share_with_nothing_in_view_says_so_plainly(env):
    n = model_calls(env)
    assert say(env, "share it", CHAT) == "I haven't sent you anything to share yet. Ask me for something first."
    assert model_calls(env) == n


def test_share_in_spanish_gets_the_hint_in_spanish(env):
    ch = env["ch"]
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    form = ask_pasta()
    form["lang"] = "es"
    say(env, "recetas de pasta", form)
    say(env, "compártelo con mi hermana", CHAT)
    share, hint = texts_of(ch, 2)
    assert share == "Lemon garlic pasta by @chef\nhttps://example.com/itm_a" and hint == HINT_ES
    say(env, "share it", CHAT)                                     # the answer's language, whatever the words
    assert texts_of(ch, 1) == [HINT_ES]
    from mvp import lang as L
    assert set(L.ES) >= {"share_hint", "share_nothing"}


def test_what_is_not_a_share_goes_on_as_before(env):
    from mvp.followup import share_request
    for t in ("send me a pasta recipe", "send it to me", "send the second one to my calendar", "share my rules",
              "send this", "email it to my friend", "send it to a@b.co", "send it to my grocery list",
              "forward", "I'll pass on this one"):
        assert share_request(t) is None, t
    assert share_request("share the NASA one") == {"name": "NASA"}
    assert share_request("fwd #2 to my dad") == {"number": 2}
    assert share_request("share the last one") == {"number": -1}
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(env, "pasta", ask_pasta())
    from mvp.tests.test_slice4_checks import ONLY_YOU
    assert say(env, "email it to my friend", {"intent": "act_on_last", "actions": ["email.send"]}) == ONLY_YOU
    n = model_calls(env)
    say(env, "share the zucchini one", CHAT)                       # names nothing shown: the model reads it
    assert model_calls(env) == n + 1
