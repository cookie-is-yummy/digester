"""Offline tests for round 9, slice C, V1 (DESIGN.md section 16.C): "add them all", "add 2, 4 and 5", a reminder or
calendar links for all the things of an items answer, and a question about a numbered thing, all read by code with no
model call. Synthetic data, a fake model and a fake clock only (today is Thursday 12 Nov 2026 in New York)."""
import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_round7 import UI_ASK, ask, ig, ui, use_lib  # noqa: E402,F401  (ui is a fixture)
from mvp.tests.test_slice2 import H, ask_pasta, lemon_pick, say  # noqa: E402


def T():
    from mvp import texts
    return texts


def calls(e):
    return len(e["calls"])


def tell(e, text):
    """A message the code must read by itself: the fake interpreter is unset, so a model call fails the test."""
    e["state"]["answers"].pop("mvp_interpret", None)
    n = calls(e)
    e["bot"].on_message(H, text)
    assert calls(e) == n, f"a model call for {text!r}"
    return last(e["ch"])


def seed(e, tmp_path, posts, goal="UI libraries"):
    """posts: [(id, creator, caption, posted day, [thing dicts])]: a library and a kept items answer, as the executor
    keeps one (each thing numbered across the posts, in order)."""
    use_lib(e, tmp_path, [(iid, who, cap, day, day, "instagram") for iid, who, cap, day, _ in posts])
    bot = e["bot"]
    run_id = bot.store.add_run(handle=H, kind="ask", status="picked")
    picks, n = [], 0
    for i, (iid, who, cap, day, things) in enumerate(posts, 1):
        items = []
        for x in things:
            n += 1
            items.append(dict({"about": "", "when": ""}, **x, n=n))
        picks.append({"item_id": iid, "title": cap.split("\n")[0], "url": ig(day, i), "platform": "instagram",
                      "video_id": None, "creator": f"@{who}", "facts": {}, "lines": [], "line_kinds": None,
                      "items": items, "posted": day})
    bot.store.put_answer(run_id, H, None, goal, "picks", [{"type": "text", "text": "the answer"}], picks)
    bot.store.set_last_answer(H, run_id, None, [p["item_id"] for p in picks], goal)
    return run_id


# ---------- "add them all" after a real items answer ----------
def test_add_them_all_adds_each_thing_with_its_posts_link_and_no_model_call(ui):
    say(ui, UI_ASK, ask("UI/UX libraries"))
    bot = ui["bot"]
    msg = tell(ui, "add them all")
    todos = bot.store.todos(H)
    assert [t["text"] for t in todos] == ["Material UI", "Ant Design", "Chakra UI", "Iconoir", "lucide"]
    assert {t["url"] for t in todos[:3]} == {ig("2023-06-20", 1)} and todos[3]["url"] == ig("2022-09-01", 2)
    assert msg.startswith("Added 5 things to your list:\n1. Material UI\n2. Ant Design")
    assert "Each one links to the post it came from." in msg and 'Reply "undo" within 10 minutes' in msg
    # the log holds counts, never the names
    row = bot.store.one("SELECT detail FROM action_log WHERE action='todo.add' ORDER BY id DESC LIMIT 1")
    assert json.loads(row["detail"]) == {"count": 5, "from": "things", "already": 0}
    assert "Material" not in row["detail"]
    assert tell(ui, "undo").startswith("Undone: I took those off your list")
    assert bot.store.todos(H) == []


def test_the_list_named_and_near_forms(ui):
    say(ui, UI_ASK, ask("UI/UX libraries"))
    bot = ui["bot"]
    msg = tell(ui, "add all of them to my reading list")
    assert msg.startswith("Added 5 things to your reading list:")
    assert {t["list"] for t in bot.store.todos(H)} == {"reading"}
    msg = tell(ui, "please put everything on my to-do list")
    assert msg.startswith("Added 5 things to your list:") and len(bot.store.todos(H)) == 10


def test_all_n_against_a_different_count_asks_and_writes_nothing(ui):
    say(ui, UI_ASK, ask("UI/UX libraries"))
    msg = tell(ui, "put all 6 on my list")
    assert msg == 'I listed 5 things. Reply "add them all" for all 5, or give the numbers.'
    assert ui["bot"].store.todos(H) == []
    assert tell(ui, "add both").startswith("I listed 5 things.")
    assert tell(ui, "put all 5 on my list").startswith("Added 5 things")


def test_several_numbers_and_a_number_past_them(ui):
    say(ui, UI_ASK, ask("UI/UX libraries"))
    bot = ui["bot"]
    msg = tell(ui, "add 2, 4 and 5")
    assert msg == ('Added 3 things to your list: Ant Design, Iconoir, lucide. Reply "undo" within 10 minutes to take '
                   'them off.')
    assert [t["text"] for t in bot.store.todos(H)] == ["Ant Design", "Iconoir", "lucide"]
    assert tell(ui, "add 1 and 9") == "My last message listed 5 things. Which number?"
    assert tell(ui, "add the first and third to my list").startswith("Added 2 things to your list: Material UI, Chakra")


def test_one_already_on_the_list_is_said_and_not_added_twice(ui):
    say(ui, UI_ASK, ask("UI/UX libraries"))
    bot = ui["bot"]
    say(ui, "add iconoir to my list", {"intent": "act_on_last", "actions": [{"action": "todo.add", "params": {}}]})
    msg = tell(ui, "add them all")
    assert msg.startswith('Added 4 things to your list:') and '"Iconoir" was already on it.' in msg
    assert [t["text"] for t in bot.store.todos(H)].count("Iconoir") == 1
    assert tell(ui, "add them all") == "They're all on your list already."
    # on another list it is not "already on it"
    assert tell(ui, "add them all to my shopping list").startswith("Added 5 things to your shopping list")


def test_a_posts_answer_is_unchanged(env):
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(env, "pasta", ask_pasta())
    n = calls(env)
    say(env, "add them all", {"intent": "act_on_last", "actions": [{"action": "todo.add", "params": {}}]})
    assert calls(env) == n + 1   # the interpreter, as before
    assert [t["text"] for t in env["bot"].store.todos(H)] == ["Lemon garlic pasta"]


def test_more_than_12_adds_the_first_12_then_the_rest(env, tmp_path):
    things = [{"name": f"Tool {chr(65 + i)}", "about": "a tool"} for i in range(15)]
    seed(env, tmp_path, [("t1", "maker", "15 tools for designers\n" + ", ".join(x["name"] for x in things),
                          "2026-10-01", things)])
    bot = env["bot"]
    msg = tell(env, "add them all")
    assert msg.startswith("Added 12 things to your list:") and 'Say "add the rest" for the other 3.' in msg
    assert len(bot.store.todos(H)) == 12
    msg = tell(env, "add the rest")
    assert msg.startswith("Added 3 things to your list: Tool M, Tool N, Tool O.")
    assert len(bot.store.todos(H)) == 15
    assert tell(env, "add the rest") == "They're all on your list already."


# ---------- one later send for all of them ----------
def test_remind_me_about_all_of_them_is_one_send_with_every_thing_once(ui):
    say(ui, UI_ASK, ask("UI/UX libraries"))
    bot, clock = ui["bot"], ui["clock"]
    msg = tell(ui, "remind me about all of them on friday")
    assert msg == ('OK. Tomorrow at 9am I\'ll send you the 5 things again, with their links. Reply "stop 1" to '
                   'cancel.')
    rules = bot.store.rules(H)
    assert len(rules) == 1
    c = rules[0]["spec"]["content"]
    assert c["item_ids"] == ["d1", "d2"]   # each post once
    assert c["item_names"] == ["Material UI", "Ant Design", "Chakra UI", "Iconoir", "lucide"]
    clock[0] = datetime(2026, 11, 13, 14, 1, tzinfo=timezone.utc)
    assert bot.tick() == 1
    sent = last(ui["ch"])
    for name in ("Material UI", "Ant Design", "Chakra UI", "Iconoir", "lucide"):
        assert sent.count(f". {name}") == 1, name
    assert sent.count(ig("2023-06-20", 1)) == 1


def test_remind_me_about_two_numbered_things_at_a_time(ui):
    say(ui, UI_ASK, ask("UI/UX libraries"))
    msg = tell(ui, "remind me about 2 and 4 tomorrow at 6pm")
    assert msg == 'OK. Tomorrow at 6pm I\'ll send you the 2 things again, with their links. Reply "stop 1" to cancel.'
    c = ui["bot"].store.rules(H)[0]["spec"]["content"]
    assert c["item_names"] == ["Ant Design", "Iconoir"] and c["item_ids"] == ["d1", "d2"]


# ---------- calendar links only for things with a date ahead ----------
def test_put_them_all_in_my_calendar_links_only_dates_ahead(env, tmp_path):
    things = [{"name": "NASA L'SPACE Academy", "about": "a summer academy", "when": "apply by 30 November 2026"},
              {"name": "Design Jam", "about": "a weekend jam", "when": "5 December"},
              {"name": "Old Camp", "about": "a camp", "when": "closed 1 March 2026"},
              {"name": "Book Club", "about": "monthly"}, {"name": "Writing Lab", "about": "online"},
              {"name": "Film School", "about": "evenings"}]
    seed(env, tmp_path, [("p1", "edu", "Programmes for students\nNASA L'SPACE Academy, Design Jam, Old Camp",
                          "2026-10-01", things[:3]),
                         ("p2", "edu", "More things to do\nBook Club, Writing Lab, Film School", "2026-10-02",
                          things[3:])])
    bot = env["bot"]
    env["ch"].link_previews = True   # each link its own message
    tell(env, "put them all in my calendar")
    sent = [t for _, _, t in env["ch"].outbox[-4:]]
    assert sent[0] == ("2 of them have a date I can read: NASA L'SPACE Academy (30 November) and Design Jam "
                       "(5 December). Tap to add each:")
    assert sent[1].startswith("https://calendar.google.com/calendar/render?") and "20261130" in sent[1]
    assert "20261205" in sent[2]
    assert sent[3] == "3 of them have no date in their words. 1 of them has a date that has passed."
    assert len(bot.store.outbox(H)) == 2   # two .ics files, nothing for the others
    assert bot.store.todos(H) == [] and bot.store.rules(H) == []


# ---------- a question about a numbered thing ----------
def test_a_question_about_a_numbered_thing_is_its_own_words(ui):
    say(ui, UI_ASK, ask("UI/UX libraries"))
    msg = tell(ui, "how long is the second one?")
    assert msg.startswith('Ant Design: "an enterprise-class UI design language". The post doesn\'t say more about it. '
                          'It\'s in "Best design systems" by @designer:')
    assert msg.endswith(ig("2023-06-20", 1))
    assert tell(ui, "what's number 4?").startswith('Iconoir: "free open source icons".')
    assert tell(ui, "tell me about 5").startswith("lucide:")
    assert tell(ui, "what's number 9?") == "My last message listed 5 things. Which number?"


def test_a_details_question_about_a_numbered_thing_makes_no_details_call(ui):
    say(ui, UI_ASK, ask("UI/UX libraries"))
    n_extract = ui["calls"].count("mvp_extract")
    msg = tell(ui, "what are the key points of the fourth one")
    assert msg.startswith('Iconoir: "free open source icons".')
    assert ui["calls"].count("mvp_extract") == n_extract


def test_after_a_posts_answer_the_question_is_not_read_here(env):
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(env, "pasta", ask_pasta())
    from mvp.followup import thing_question
    assert thing_question("what's number 2?") == 2
    n = calls(env)
    env["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "chat", "reply": "Hi."}
    env["bot"].on_message(H, "what's number 2?")
    assert calls(env) == n + 1   # no things shown: the interpreter, as before


# ---------- the readers, and their near misses ----------
def test_the_readers_and_what_they_leave_alone():
    from mvp.followup import all_things, numbers_in, thing_question
    from mvp.postacts import things_request
    assert all_things("them all") == (True, None) and all_things("all 6") == (True, 6)
    assert all_things("all six") == (True, 6) and all_things("both") == (True, 2)
    assert all_things("all of them") == (True, None) and all_things("the second one") is None
    assert numbers_in("2, 4 and 5") == [2, 4, 5] and numbers_in("numbers 2 and 4") == [2, 4]
    assert numbers_in("the first and third") == [1, 3] and numbers_in("1 & 3") == [1, 3]
    assert numbers_in("2") is None and numbers_in("2 recipes") is None and numbers_in("milk and eggs") is None
    for text in ("add them all", "add all of them to my reading list", "put all 6 on my list", "add 2, 4 and 5",
                 "add the rest", "remind me about all of them on friday", "put them all in my calendar",
                 "can you add everything to my list please"):
        assert things_request(text), text
    for text in ("add 2 to my list", "add milk and eggs", "add it to my list", "add them all every friday",
                 "remind me about all of them", "add the rest of the milk", "put them all in my email",
                 "2 recipes please", "add all the pasta recipes you can find"):
        assert things_request(text) is None, text
    assert things_request("add them all to my reading list")["list"] == "reading"
    assert things_request("put all 6 on my list")["list"] == "todo"
    for text in ("what's number 4?", "how long is the second one?", "what is the 2nd one", "tell me about #3"):
        assert thing_question(text), text
    for text in ("what's in the second one", "what about the second one", "what's number 4 like compared to 3",
                 "how long is a marathon", "what's new"):
        assert thing_question(text) is None, text


def test_answer_picks_gives_the_things_for_several_numbers(ui):
    say(ui, UI_ASK, ask("UI/UX libraries"))
    bot = ui["bot"]
    picks, whole, _, problem = bot._answer_picks(H, [2, 4])
    assert problem is None and not whole and [p["title"] for p in picks] == ["Ant Design", "Iconoir"]
    picks, _, _, _ = bot._answer_picks(H, None, all_things=True)
    assert len(picks) == 5
    assert bot._answer_picks(H, [2, 7])[3] == "My last message listed 5 things. Which number?"
