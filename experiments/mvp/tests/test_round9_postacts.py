"""Offline tests for round 9, slice C, W7 and W8 (DESIGN.md section 16.C): one numbered-offer reader, and acting on a
saved post (apply, book, buy) with what the bot can honestly prepare. Read by code with no model call. Synthetic data,
a fake model and a fake clock only (today is Thursday 12 Nov 2026, 1pm in New York)."""
import glob
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_round7 import ig, use_lib  # noqa: E402
from mvp.tests.test_slice2 import H, ask_pasta, lemon_pick, say  # noqa: E402

CLAIMS = re.compile(r"\b(?:booked|ordered|bought|applied|signed (?:you )?up|registered|cancell?ed|purchased)\b", re.I)


def T():
    from mvp import texts
    return texts


def tell(e, text, model=False):
    """A message the code must read by itself (model=False): the fake interpreter is unset, so a model call fails."""
    e["state"]["answers"].pop("mvp_interpret", None)
    n, sent = len(e["calls"]), len(e["ch"].outbox)
    e["bot"].on_message(H, text)
    if not model:
        assert len(e["calls"]) == n, f"a model call for {text!r}"
    msg = "\n".join(t for _, _, t in e["ch"].outbox[sent:])   # every message of the reply (a link is its own)
    assert not CLAIMS.search(msg), msg
    return msg


def seed(e, tmp_path, posts, goal="things to do"):
    """posts: [(id, creator, caption, posted day or None, title)]: a library and a kept answer that showed them."""
    use_lib(e, tmp_path, [(iid, who, cap, day, day or "2026-10-01", "instagram") for iid, who, cap, day, _ in posts])
    bot = e["bot"]
    run_id = bot.store.add_run(handle=H, kind="ask", status="picked")
    picks = []
    for i, (iid, who, cap, day, title) in enumerate(posts, 1):
        p = {"item_id": iid, "title": title, "url": ig(day, i) if day else f"https://example.com/{iid}",
             "platform": "instagram", "video_id": None, "creator": f"@{who}", "facts": {}, "lines": [],
             "line_kinds": None}
        if day:
            p["posted"] = day
        picks.append(p)
    bot.store.put_answer(run_id, H, None, goal, "picks", [{"type": "text", "text": "the answer"}], picks)
    bot.store.set_last_answer(H, run_id, None, [p["item_id"] for p in picks], goal)
    return run_id


NASA = ("NASA L'SPACE Academy for students\nApplications close 30 November 2026.\nRequirements:\n- transcript\n"
        "- one-page essay\n- a teacher's recommendation\n- DM me for the template\n- follow @spaceclub for more\n"
        "- https://example.com/apply\n\nGood luck!")
NASA_POST = ("n1", "spaceclub", NASA, "2026-10-05", "NASA L'SPACE Academy")


@pytest.fixture()
def nasa(env, tmp_path):
    seed(env, tmp_path, [NASA_POST])
    return env


# ---------- W8: apply ----------
@pytest.mark.parametrize("text", ["apply to the first one", "help me apply to NASA L'SPACE", "sign me up for 1",
                                  "register me for it", "get me ready for the academy", "can you apply for it please"])
def test_apply_phrasings_open_the_menu_with_no_model_call(nasa, text):
    msg = tell(nasa, text)
    assert msg.startswith("I can't fill in or send the application myself, but here's what I can set up for NASA "
                          "L'SPACE Academy (from your saves):\n")
    assert "1. Its deadline, 30 November, on your calendar, and a reminder on Friday 27 November at 9am, 3 days " \
           "before." in msg
    assert "2. A checklist from the post's own words: transcript, one-page essay, a teacher's recommendation." in msg
    assert "The post:\n" + ig("2026-10-05", 1) in msg and msg.endswith('Reply 1, 2, "all", or "none".')
    st = nasa["bot"].store.get_state(f"offers:{H}")
    assert [o["kind"] for o in st["offers"]] == ["deadline", "checklist"]


def test_all_sets_the_offered_effects_and_undo_takes_off_what_it_can(nasa):
    bot = nasa["bot"]
    tell(nasa, "apply to the first one")
    msg = tell(nasa, "all")
    assert msg.startswith("Here's what I set up:\n• Deadline 30 November: tap to add it to your calendar:\n"
                          "https://calendar.google.com/calendar/render?action=TEMPLATE")
    assert "• A reminder on Friday 27 November at 9am (rule 1)" in msg
    assert "• 3 things on your list \"NASA L'SPACE Academy\": transcript, one-page essay, a teacher's recommendation" \
        in msg
    assert msg.endswith('I didn\'t apply for you: you do that on their site. Reply "undo" within 10 minutes to take '
                        'the reminder and the list off.')
    todos = bot.store.todos(H)
    assert [t["text"] for t in todos] == ["transcript", "one-page essay", "a teacher's recommendation"]
    assert {t["list"] for t in todos} == {"nasa lspace academy"} and todos[0]["url"] == ig("2026-10-05", 1)
    r = bot.store.rules(H)[0]
    assert r["status"] == "active" and r["spec"]["when"]["date"] == "2026-11-27"
    assert bot.store.get_state(f"deadline:{r['id']}") == {"date": "2026-11-30", "deadline": True}
    assert bot.store.get_state(f"offers:{H}") is None   # every offer done
    msg = tell(nasa, "undo")
    assert msg.startswith("Undone:") and "I stopped the rule I just started" in msg and "off your list" in msg
    assert msg.endswith("I can't take back a calendar link, so that stays.")
    assert bot.store.todos(H) == [] and bot.store.rule(r["id"])["status"] == "stopped"
    # the log holds counts and kinds, never a line of the post
    rows = bot.store.q("SELECT action, detail FROM action_log WHERE handle=? ORDER BY id", (H,))
    assert [r["action"] for r in rows] == ["postact.menu", "calendar.add", "todo.add"]
    assert all("transcript" not in (r["detail"] or "") for r in rows)


def test_one_number_runs_only_that_and_the_rest_stays_open(nasa):
    bot = nasa["bot"]
    tell(nasa, "apply to the first one")
    msg = tell(nasa, "1")
    assert "• Deadline 30 November" in msg and "checklist" not in msg and bot.store.todos(H) == []
    assert msg.endswith('Reply "undo" within 10 minutes to take the reminder off.')
    assert tell(nasa, "1") == T().OFFER_DONE_ALREADY
    msg = tell(nasa, "the second one")
    assert "• 3 things on your list" in msg and len(bot.store.todos(H)) == 3
    assert len(bot.store.rules(H)) == 1


@pytest.mark.parametrize("text,picked", [("2", [2]), ("1 and 2", [1, 2]), ("1, 2", [1, 2]), ("do 2", [2]),
                                         ("yes to 1", [1]), ("the first one", [1]), ("both", [1, 2]),
                                         ("all of them", [1, 2]), ("2 please", [2])])
def test_each_whole_message_form_picks_the_right_offers(nasa, text, picked):
    bot = nasa["bot"]
    tell(nasa, "apply to the first one")
    tell(nasa, text)
    assert (len(bot.store.rules(H)) == 1) == (1 in picked)
    assert (len(bot.store.todos(H)) == 3) == (2 in picked)


def test_none_clears_a_number_past_them_asks_and_other_words_go_on(nasa):
    bot = nasa["bot"]
    tell(nasa, "apply to the first one")
    assert tell(nasa, "5") == "I offered 2 things. Reply 1 or 2."
    assert tell(nasa, "none") == "OK. They're still in your saves if you want them later."
    assert bot.store.get_state(f"offers:{H}") is None
    nasa["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "chat", "reply": "Hi."}
    n = len(nasa["calls"])
    bot.on_message(H, "1")
    assert len(nasa["calls"]) == n + 1 and bot.store.rules(H) == []   # no offers: the interpreter, as before
    from mvp.offers import parse_choice
    for text in ("2 recipes please", "what's in the second one", "add 2 to my list", "👎 3", "1 hour", "do it later"):
        assert parse_choice(text, 3) is None, text
    for text in ("not now", "no thanks", "neither", "none of them"):
        assert parse_choice(text, 3) == ("none", None), text


def test_a_new_answer_clears_the_offers_and_they_end_after_24_hours(nasa):
    bot, clock = nasa["bot"], nasa["clock"]
    tell(nasa, "apply to the first one")
    bot._keep_answer(999, H, None, "x", "picks", "an answer")
    assert bot.store.get_state(f"offers:{H}") is None
    tell(nasa, "apply to the first one")
    clock[0] = clock[0] + timedelta(hours=25)
    nasa["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "chat", "reply": "Hi."}
    n = len(nasa["calls"])
    bot.on_message(H, "1")
    assert len(nasa["calls"]) == n + 1 and bot.store.rules(H) == []


def test_with_a_rule_preview_waiting_yes_and_no_are_the_previews(nasa):
    bot = nasa["bot"]
    tell(nasa, "apply to the first one")
    bot.store.set_pending(H, "confirm_rule", {"text": "x", "spec": {}, "run_id": None}, at=nasa["clock"][0])
    assert tell(nasa, "no") == T().NOT_STARTED   # the preview, not the offers
    assert bot.store.get_state(f"offers:{H}") is not None
    seen = []
    bot.store.set_pending(H, "confirm_rule", {"text": "x", "spec": {}, "run_id": None}, at=nasa["clock"][0])
    bot._confirm = lambda person, pending: seen.append(pending["kind"]) or bot.send(H, "started")
    assert tell(nasa, "yes") == "started" and seen == ["confirm_rule"]
    assert bot.store.get_state(f"offers:{H}") is not None and bot.store.rules(H) == []


def test_a_setup_step_newer_than_the_offers_keeps_its_own_number(nasa):
    from mvp.store import now_iso
    bot, now = nasa["bot"], nasa["clock"][0]
    tell(nasa, "apply to the first one")
    bot.store.set_state(f"onboard:{H}", {"step": "offer", "at": now_iso(now + timedelta(minutes=1))})
    person = bot.store.person(H)
    assert bot.offer_reads(person, "2", None, now + timedelta(minutes=2)) is None
    bot.store.set_state(f"onboard:{H}", {"step": "done", "at": now_iso(now + timedelta(minutes=1))})
    assert bot.offer_reads(person, "2", None, now + timedelta(minutes=2)) is not None


def test_a_passed_deadline_is_said_and_only_the_checklist_is_offered(env, tmp_path):
    cap = NASA.replace("Applications close 30 November 2026.", "Applications close 14 February 2025.")
    seed(env, tmp_path, [("n1", "spaceclub", cap, "2024-12-01", "NASA L'SPACE Academy")])
    msg = tell(env, "apply to the first one")
    assert "1. A checklist from the post's own words" in msg and "2." not in msg
    assert "Its deadline, 14 February 2025, has passed." in msg and msg.endswith('Reply 1, or "none".')
    cap2 = "NASA L'SPACE Academy\nApplications close 14 February 2025."
    seed(env, tmp_path / "b", [("n2", "spaceclub", cap2, "2024-12-01", "NASA L'SPACE Academy")])
    msg = tell(env, "apply to it")
    assert msg.startswith("I can't fill in or send the application myself. Its deadline, 14 February 2025, has "
                          "passed.")
    assert env["bot"].store.get_state(f"offers:{H}") is None


def test_no_date_asks_for_it_and_the_date_or_the_checklist_answers(env, tmp_path):
    cap = NASA.replace("Applications close 30 November 2026.\n", "")
    seed(env, tmp_path, [("n1", "spaceclub", cap, "2026-10-05", "NASA L'SPACE Academy")])
    bot = env["bot"]
    msg = tell(env, "apply to the first one")
    assert "1. A checklist" in msg and "The post doesn't say when NASA L'SPACE Academy closes. Tell me the date" in msg
    msg = tell(env, "dec 5")   # the existing question's answer: the reminder, and the calendar entry
    assert msg.startswith("OK. I'll remind you about NASA L'SPACE Academy on Wednesday 2 December at 9am")
    assert len(bot.store.rules(H)) == 1
    msg = tell(env, "1")
    assert "• 3 things on your list" in msg


def test_no_date_and_no_requirement_lines_is_the_date_question_alone(env, tmp_path):
    seed(env, tmp_path, [("n1", "spaceclub", "NASA L'SPACE Academy\nA summer programme for students.",
                          "2026-10-05", "NASA L'SPACE Academy")])
    msg = tell(env, "apply to it")
    assert msg == ("I can't fill in or send the application myself. The post doesn't say when NASA L'SPACE Academy "
                   "closes. Tell me the date, like \"dec 5\", and I'll set the reminder.")
    assert env["bot"].store.get_state(f"offers:{H}") is None


def test_the_checklist_is_verbatim_runs_of_the_post_and_filtered():
    from mvp.postacts import checklist_lines
    assert checklist_lines(NASA) == ["transcript", "one-page essay", "a teacher's recommendation"]
    inline = "Fellowship\nTo apply, submit: a CV, a portfolio; two references and a cover letter.\nThanks"
    got = checklist_lines(inline)
    assert got == ["a CV", "a portfolio", "two references and a cover letter"]
    assert all(x in inline for x in got)
    plain = "Eligibility\nAge 16 to 19\nLiving in the US\n\nApply soon"
    assert checklist_lines(plain) == ["Age 16 to 19", "Living in the US"]
    assert checklist_lines("A great programme. Apply now!") == []
    long = "Requirements:\n- " + "x" * 130 + "\n- ok line\n- comment APPLY below\n- link in bio\n- me@example.com"
    assert checklist_lines(long) == ["ok line"]
    many = "You need:\n" + "\n".join(f"- item {i}" for i in range(12))
    assert len(checklist_lines(many)) == 8


# ---------- W8: book ----------
TACOS = ("Tacos El Gordo 🌮\n📍 Las Vegas, NV\nBook at evil.example/book or call (702) 555-0142\nOpen till 2am, "
         "dinner from 8pm every friday")


@pytest.fixture()
def tacos(env, tmp_path):
    seed(env, tmp_path, [("r1", "eats", TACOS, "2026-09-01", "Tacos El Gordo"),
                         ("r2", "eats", "Ramen Hood\nBest bowls", "2026-09-02", "Ramen Hood")])
    env["ch"].link_previews = True
    return env


def test_book_it_gives_maps_and_asks_when_and_never_uses_the_posts_link(tacos):
    msg = tell(tacos, "book it")
    lines = msg.split("\n")
    assert lines[0] == "I can't book for you. Here's what I can do for Tacos El Gordo (from your saves):"
    assert lines[1] == "1. Find it in Google Maps: https://www.google.com/maps/search/?api=1&query=Tacos+El+Gordo+Las+Vegas"
    assert T().BOOK_ASK_WHEN in msg and "The post gives this number: (702) 555-0142. I can't call for you." in msg
    assert "evil.example" not in msg and msg.endswith('Reply 1, or "none".')
    assert "To ask them by email, type their address" in msg


@pytest.mark.parametrize("text", ["book a table at the first one for saturday at 7",
                                  "reserve the taco place for saturday at 7pm",
                                  "get us a table at 1 saturday at 7"])
def test_a_day_and_time_typed_by_the_person_makes_a_hold_offer(tacos, text):
    msg = tell(tacos, text)
    assert "2. Put Saturday 14 November at 7pm on your calendar as a hold." in msg
    msg = tell(tacos, "all")
    assert "• Tacos El Gordo in Google Maps: https://www.google.com/maps/search/" in msg
    assert "• A hold for Saturday 14 November at 7pm: tap to add it to your calendar:" in msg
    assert "dates=20261114T190000%2F20261114T203000" in msg and "Tacos%20El%20Gordo%20%28hold%29" in msg
    assert msg.endswith("I didn't book anything: that's up to you and them.")


def test_a_day_without_a_time_asks_what_time_and_the_answer_makes_the_hold(tacos):
    msg = tell(tacos, "book it for friday")
    assert 'What time on Friday? Say a time like "7pm" and I\'ll put a hold on your calendar.' in msg
    assert "Put Friday" not in msg   # the post's "8pm every friday" is never the person's time
    msg = tell(tacos, "7:30pm")
    assert "• A hold for Friday 13 November at 7:30pm: tap to add it to your calendar:" in msg
    assert "20261113T193000" in msg


def test_book_names_and_what_is_left_to_the_interpreter(tacos):
    assert "Ramen Hood" in tell(tacos, "make a reservation at the ramen spot")
    tacos["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "unsupported"}
    for text in ("book me a table somewhere nice for saturday", "book the sushi place"):
        n = len(tacos["calls"])
        tacos["bot"].on_message(H, text)
        assert len(tacos["calls"]) == n + 1, text
        assert last(tacos["ch"]) == T().UNSUPPORTED_BOOK


def test_the_maps_link_is_built_by_code_only():
    from mvp.postacts import maps_link, place_word
    assert maps_link("Tacos El Gordo", "Las Vegas") == \
        "https://www.google.com/maps/search/?api=1&query=Tacos+El+Gordo+Las+Vegas"
    assert maps_link("A&B #1 ?", None).startswith("https://www.google.com/maps/search/?api=1&query=A%26B+%231+%3F")
    assert place_word("📍 evil.example/book") is None and place_word("Brunch in Brooklyn this week") == "Brooklyn"
    assert place_word("Open in December") is None and place_word("📍 Austin, TX") == "Austin"


def test_the_day_and_time_reader():
    from datetime import date
    from mvp.postacts import day_time, when_only
    thu = date(2026, 11, 12)
    assert day_time("book it for saturday at 7", thu) == (date(2026, 11, 14), "19:00")
    assert day_time("saturday at 11am", thu) == (date(2026, 11, 14), "11:00")
    assert day_time("tomorrow at noon", thu) == (date(2026, 11, 13), "12:00")
    assert day_time("thursday 8:15pm", thu) == (thu, "20:15")
    assert day_time("next thursday", thu) == (date(2026, 11, 19), None)
    assert day_time("get us a table at 2 friday at 7", thu) == (date(2026, 11, 13), "19:00")
    assert day_time("book it", thu) == (None, None)
    assert when_only("7pm") and when_only("saturday at 7") and when_only("at 7:30 pm")
    assert not when_only("7") and not when_only("book it") and not when_only("7 people")


# ---------- W8: buy ----------
def test_buy_the_ingredients_puts_them_on_the_shopping_list(env):
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(env, "pasta", ask_pasta())
    bot = env["bot"]
    msg = tell(env, "buy the ingredients for the first one")   # the rule eval's t-dev-040, read by code now
    assert msg == ("I can't buy things or pay for you. I put the 2 ingredients on your shopping list: 200g spaghetti, "
                   "2 lemons. Reply \"undo\" within 10 minutes to take them off.")
    assert [(t["text"], t["list"]) for t in bot.store.todos(H)] == [("200g spaghetti", "shopping"),
                                                                    ("2 lemons", "shopping")]
    tell(env, "undo")
    assert bot.store.todos(H) == []
    assert tell(env, "order these for me").startswith("I can't buy things or pay for you. I put the 2 ingredients")
    assert tell(env, "get me the stuff for this recipe").startswith("I can't buy things or pay for you. I put")


LAMP = "The Arc Lamp changed my desk setup. It's $49 and folds flat."


def test_a_product_gets_the_link_a_dated_price_and_an_offer(env, tmp_path):
    seed(env, tmp_path, [("l1", "desk", LAMP, "2024-05-10", "Arc Lamp")])
    env["ch"].link_previews = True
    bot = env["bot"]
    for text in ("buy the lamp in the first one", "where can I buy it", "order it for me"):
        msg = tell(env, text)
        assert msg == ("I can't buy things for you. Here's Arc Lamp from the post (it said $49 in May 2024, so check "
                       "today's price):\n" + ig("2024-05-10", 1) + "\nWant it on your list? Reply 1."), text
    msg = tell(env, "1")
    assert msg == 'Added "Arc Lamp" to your list. Reply "undo" within 10 minutes to take it off.'
    assert [t["text"] for t in bot.store.todos(H)] == ["Arc Lamp"]
    tell(env, "where can I buy it")
    assert tell(env, "yes").startswith('Added "Arc Lamp"')   # one offer: a yes takes it


def test_a_price_is_never_shown_without_the_month_it_was_posted(env, tmp_path):
    seed(env, tmp_path, [("l1", "desk", LAMP, None, "Arc Lamp")])
    msg = tell(env, "buy it")
    assert "$49" not in msg and msg.startswith("I can't buy things for you. Here's Arc Lamp from the post:")
    seed(env, tmp_path / "b", [("l2", "desk", "Arc Lamp $49, or the big one for $89", "2024-05-10", "Arc Lamp")])
    assert "$" not in tell(env, "buy it")   # two prices: neither is said
    from mvp.postacts import price_in
    assert price_in("only €12.50 today") == "€12.50" and price_in("no price") is None


def test_order_by_and_other_asks_are_not_a_purchase():
    from mvp.postacts import request
    assert request("order them by date") is None and request("buy it and email me the link") is None
    assert request("buy me a new phone") is None   # "a new": nothing shown
    assert request("where can i buy cheap furniture")["target"]["name"] == "cheap furniture"
    assert request("order these for me")["target"]["generic"]


# ---------- the nearest offer when nothing shown is meant ----------
def test_nothing_shown_gets_the_nearest_offer_line(env):
    env["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "unsupported", "reply": "Booked!"}
    env["bot"].on_message(H, "book me a table somewhere nice for saturday")   # t-dev-041
    assert last(env["ch"]) == T().UNSUPPORTED_BOOK
    env["bot"].on_message(H, "buy me a new phone")
    assert last(env["ch"]) == T().UNSUPPORTED_BUY
    env["bot"].on_message(H, "book it")   # nothing shown yet: the model, then the line
    assert last(env["ch"]) == T().UNSUPPORTED_BOOK
    env["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "unsupported", "lang": "es"}
    env["bot"].on_message(H, "resérvame una mesa")
    assert last(env["ch"]).startswith("Eso no lo puedo hacer.")


# ---------- the code reads against the rule eval set ----------
def test_the_rule_eval_texts_are_not_claimed_by_the_new_reads_but_the_listed_one():
    from mvp.followup import thing_question
    from mvp.offers import parse_choice
    from mvp.postacts import request, things_request, when_only
    claimed = []
    for path in sorted(glob.glob(os.path.join(os.path.dirname(HERE), "evalset", "rules_dev_*.jsonl"))):
        for line in open(path, encoding="utf-8"):
            if not line.strip():
                continue
            case = json.loads(line)
            t = case["text"]
            if request(t) or things_request(t) or thing_question(t) is not None or parse_choice(t, 3) or when_only(t):
                claimed.append(case["id"])
    assert claimed == ["t-dev-040"]   # "buy the ingredients for the first one": the ingredients on the list
