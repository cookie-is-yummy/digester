"""Checker, round 8 (DESIGN.md sections 12 and 13): the claims of the answers and rules slices, tried on near-variants.
Each test here failed before the fix it names. Synthetic data, the fake model, the fake search pool and the fake clock
only (New York)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, say  # noqa: E402
from mvp.tests.test_round8_rules import no_model, opps, rules, spec_of, tick_at, tue_todo, u  # noqa: E402


class It:
    """A post as clean_items reads it: its text and its first line."""
    def __init__(self, text):
        self.id, self.raw_caption, self.caption = "x", text, " ".join(text.split())
        self.first_line = next((" ".join(x.split()) for x in text.splitlines() if x.strip()), "")


def names(items):
    return [x["name"] for x in items]


# ---------- finding 93: a real thing written in lower case is still a thing ----------
def test_a_lower_case_name_with_a_slash_or_on_its_own_list_line_is_kept():
    from mvp.extract import clean_items
    text = ("Best UI libraries:\n- shadcn/ui: beautifully designed components you can copy\n"
            "- daisyUI: tailwind components for everyone\n- lucide - clean open icons")
    got, dropped = clean_items([{"name": "shadcn/ui", "about": "beautifully designed components you can copy"},
                                {"name": "daisyUI", "about": "tailwind components for everyone"},
                                {"name": "lucide", "about": "clean open icons"}], It(text))
    assert names(got) == ["shadcn/ui", "daisyUI", "lucide"] and dropped == 0
    # a hyphen inside the name marks it too; a site keeps its name
    got, _ = clean_items([{"name": "react-hook-form", "about": "the forms library i use for every single project"},
                          {"name": "untitledui", "about": "free figma kits and a huge icon set"}],
                         It("Use react-hook-form, the forms library i use for every single project\n"
                            "untitledui.com: free figma kits and a huge icon set"))
    assert names(got) == ["react-hook-form", "untitledui"]
    # near-variants that stay dropped: a kind word, and a lower-case word that only starts a sentence on a list line
    got, _ = clean_items([{"name": "design systems", "about": "a list of the some best design systems"},
                          {"name": "notion", "about": "where i keep them all together"},
                          {"name": "Material UI", "about": "Google's React components, themable"}],
                         It("Design systems\n- a list of the some best design systems\n"
                            "- notion is where i keep them all together\n- Material UI: Google's React components, "
                            "themable"))
    assert names(got) == ["Material UI"]


def test_a_caption_written_without_capitals_cannot_use_the_capital_test():
    from mvp.extract import clean_items, common_noun
    text = ("my fav ui libs for side projects honestly 👇 shadcn, lucide and htmx. lucide has the cleanest open "
            "source icon set around and htmx keeps things simple and fast to ship with")
    got, _ = clean_items([{"name": "lucide", "about": "lucide has the cleanest open source icon set around"},
                          {"name": "htmx", "about": "htmx keeps things simple and fast to ship with"}], It(text))
    assert names(got) == ["lucide", "htmx"]
    # a text with capitals still uses it; a kind after a determiner is still a kind in a lower-case caption
    assert common_noun("htmx", "I use htmx for everything these days. It is simple and Fast and Good.")
    assert common_noun("figma design system", "choosing the right figma design system is crucial for teams who "
                                              "build things together every day")


# ---------- finding 95: one topic with two kind words is one ask ----------
def test_a_bare_kind_word_shares_the_topic_of_the_part_beside_it():
    from mvp.answers import split_asks
    for one in ("tools and resources for designers", "cafes and restaurants in lisbon", "books and podcasts about "
                "startups", "apps, tools and websites for designers", "show me productivity tips and tools",
                "jobs or internships in design", "ui kits and templates", "startup ideas and opportunities",
                "recipes and workouts"):
        assert split_asks(one) is None, one
    # near-variants that still split: every part has words of its own
    assert split_asks("send me startup motivation related reels, opportunities to pursue soon, or things with "
                      "deadlines") == ["startup motivation related reels", "opportunities to pursue soon",
                                       "things with deadlines"]
    assert split_asks("dinner ideas, also some workout videos") == ["dinner ideas", "workout videos"]
    assert split_asks("blender tutorials and some pasta recipes") == ["blender tutorials", "pasta recipes"]


# ---------- finding 97: a question about the app or the person's data is never a search ----------
def test_the_chat_guard_leaves_questions_about_the_app_and_statements_alone():
    from mvp.interpret import chat_guard
    from mvp.schema import Interpretation

    def guard(t):
        return chat_guard(Interpretation(intent="chat", reply="x"), t).intent
    for chat in ("what does the app do with my saves", "is my library private and safe", "where are my saves stored",
                 "can i delete my saves from here", "who can see my saves", "how does this work with my saves",
                 "is there any way to export my saves", "what is the best way to share my saves",
                 "any idea why the search is slow", "what happens to the posts I saved", "did i ever tell it my name",
                 "how many recipes did I save", "why did I save so many recipes", "I saved a lot of reels this "
                 "month huh", "i liked that last one a lot", "ugh i have missed so many deadlines this year"):
        assert guard(chat) == "chat", chat
    # near-variants that are still asks
    for ask in ("what other opportunities might i have missed for 2026, especially winter or next summer",
                "other opportunities i might have missed for 2026, especially winter or next summer",
                "did i save any good pasta recipes last month", "show me other blender tutorials from my saves",
                "what apps do i have saved for budgeting", "what do I have saved about design",
                "any other ui libraries in my saves"):
        assert guard(ask) == "ask", ask


# ---------- BN1: a reminder sent later says how far the date is from the day it is sent ----------
def test_a_fired_deadline_reminder_counts_the_days_from_the_send_not_from_the_answer(env, tmp_path):
    opps(env, tmp_path)
    bot, ch = env["bot"], env["ch"]
    say(env, "remind me 3 days before the NASA one closes", no_model)
    n0 = len(ch.outbox)
    env["clock"][0] = u(2026, 11, 27, 14, 1)
    assert bot.tick() == 1
    out = ch.outbox[n0][2]
    assert out.startswith("Reminder: NASA L'SPACE Academy's deadline is 30 November (in 3 days).")
    assert out.endswith("applications close 30 November 2026 (deadline 30 November, in 3 days)")
    assert "16 days" not in out


def test_the_same_across_a_year_end_and_for_a_later_send_the_model_set(env, tmp_path):
    items = [{"name": "Winter Lab", "about": "deadline Jan 5", "when": "Jan 5"},
             {"name": "Spring Camp", "about": "for first years, apply by Jan 2", "when": "Jan 2"}]
    cap = "Programs to apply to:\nWinter Lab: deadline Jan 5\nSpring Camp: for first years, apply by Jan 2"
    opps(env, tmp_path, cap=cap, items=items, posted="2026-12-10", clock=u(2026, 12, 20, 15, 0))
    bot, ch = env["bot"], env["ch"]
    msg = say(env, "remind me a week before winter lab closes", no_model)
    assert "Tuesday 29 December at 9am, a week before its deadline, 5 January 2027 (in 16 days)" in msg
    assert spec_of(rules(bot)[-1])["when"]["date"] == "2026-12-29"
    say(env, "remind me about spring camp on dec 30", {
        "intent": "act_on_last", "actions": [{"action": "message.send", "params": {}}],
        "when": {"type": "once", "date": "2026-12-30", "time": "10:00"}})
    n0 = len(ch.outbox)
    env["clock"][0] = u(2026, 12, 29, 14, 1)
    assert bot.tick() == 1
    assert ch.outbox[n0][2].startswith("Reminder: Winter Lab's deadline is 5 January 2027 (in 7 days).")
    assert ch.outbox[n0][2].endswith("1. Winter Lab: deadline Jan 5 (deadline 5 January 2027, in 7 days)")
    env["clock"][0] = u(2026, 12, 30, 15, 1)
    assert bot.tick() == 1
    assert ch.outbox[-1][2].endswith("(deadline 2 January 2027, in 3 days)")


def test_renew_note_leaves_other_notes_and_says_passed_when_the_day_is_gone():
    from datetime import date
    from mvp.render import renew_note
    x = {"n": 1, "name": "A", "about": "", "note": "from May 2024, so this round has probably closed", "date": None}
    assert renew_note(x, date(2026, 11, 14)) == x
    y = renew_note({"n": 2, "name": "B", "about": "apply soon", "note": "deadline 1 December (in 17 days)",
                    "date": "2026-12-01", "state": "open"}, date(2026, 12, 3))
    assert y["note"] == "its deadline, 1 December 2026, has passed" and y["state"] == "passed"
    assert y["shown"] == "B: apply soon (its deadline, 1 December 2026, has passed)"


# ---------- BN2 (c): one nudge at a time, so "drop it" is about the one asked ----------
def test_two_todos_past_due_are_nudged_one_at_a_time(env):
    bot, ch = env["bot"], env["ch"]
    tue_todo(env)
    tue_todo(env, text="post the letter")
    tick_at(env, u(2026, 11, 17, 23, 1))
    n0 = len(ch.outbox)
    assert tick_at(env, u(2026, 11, 18, 23, 1)) == 1
    assert [m[2] for m in ch.outbox[n0:]] == [
        '"call the bank" was due yesterday. Reply "done 1", "tomorrow" or "drop it".']
    assert tick_at(env, u(2026, 11, 18, 23, 30)) == 0                         # the other waits for the answer
    assert say(env, "drop it", no_model) == 'OK. I took "call the bank" off your list.'
    assert [t["text"] for t in bot.store.todos(H)] == ["post the letter"]
    assert tick_at(env, u(2026, 11, 18, 23, 31)) == 1
    assert last(ch) == '"post the letter" was due yesterday. Reply "done 1", "tomorrow" or "drop it".'
    # with no answer, the next one goes out 12 hours later (and never inside quiet hours)
    tue_todo(env, text="pay rent")
    tue_todo(env, text="water plants")
    tick_at(env, u(2026, 11, 17, 23, 2))
    env["clock"][0] = u(2026, 11, 18, 23, 40)
    bot.tick()
    first = last(ch)
    assert tick_at(env, u(2026, 11, 19, 3, 0)) == 0
    assert tick_at(env, u(2026, 11, 19, 13, 1)) == 1 and last(ch) != first


def test_two_reminders_for_two_things_of_one_post_each_send_their_own_thing(env, tmp_path):
    """The first reminder's send keeps only its thing with that post; the second must still send the second thing
    (it sent the first one again before the fix)."""
    opps(env, tmp_path)
    bot, ch = env["bot"], env["ch"]
    say(env, "remind me 3 days before the NASA one closes", no_model)
    say(env, "remind me about design jam on nov 28", {
        "intent": "act_on_last", "actions": [{"action": "message.send", "params": {}}],
        "when": {"type": "once", "date": "2026-11-28", "time": "10:00"}})
    assert spec_of(rules(bot)[-1])["content"]["item_names"] == ["Design Jam"]
    env["clock"][0] = u(2026, 11, 27, 14, 1)
    assert bot.tick() == 1 and "NASA L'SPACE Academy" in last(ch)
    env["clock"][0] = u(2026, 11, 28, 15, 1)
    assert bot.tick() == 1
    assert last(ch).endswith("1. Design Jam: a weekend event for beginners") and "NASA" not in last(ch)
