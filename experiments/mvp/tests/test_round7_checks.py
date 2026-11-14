"""Checker's tests for round 7, slice A (DESIGN.md section 12): near-variants of the builder's cases. An item's words are
about that item; dates written loosely; a reminder counted back from a thing's own date; follow-ups that ask about a
pick, add a creator, refine the request or say "the opposite". Synthetic data and the fakes only."""
import json
import os
import sys
from datetime import date, datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, say  # noqa: E402
from mvp.tests.test_round7 import (UI_ASK, ask, blender, code_for, ig, items_fake, pick, shown_ids,  # noqa: E402,F401
                                   ui, ui_compose, use_lib)


# ---------- an item's words are about that item ----------
def test_r7c_a_sentence_about_another_item_is_never_shown_under_this_ones_name():
    from mvp.extract import verify_items
    text = ("Programs for students:\nNASA L'SPACE Academy: a free program for undergrads.\n"
            "Google STEP: internship for first and second year students. Prior experience is not required.")
    items, _ = verify_items([{"name": "NASA L'SPACE Academy", "about": "Prior experience is not required."},
                             {"name": "Google STEP", "about": "internship for first and second year students"}], text)
    assert items[0] == {"name": "NASA L'SPACE Academy", "about": "", "when": "", "fit": "unknown"}
    assert items[1]["about"] == "internship for first and second year students"
    # the builder's case: a sentence after the name, without the name, is still that thing's
    text2 = "NASA L'SPACE Academy: a free program. NASA explicitly says prior experience is not required."
    got, _ = verify_items([{"name": "NASA L'SPACE Academy",
                            "about": "NASA explicitly says prior experience is not required."}], text2)
    assert got[0]["about"] == "NASA explicitly says prior experience is not required."


def test_r7c_a_one_line_list_is_not_the_words_about_each_of_its_things():
    from mvp.extract import verify_items
    text = "My design stack: Figma | Framer | Webflow | Spline. Use them all."
    items, _ = verify_items([{"name": n, "about": "My design stack: Figma | Framer | Webflow | Spline"}
                             for n in ("Figma", "Framer", "Webflow", "Spline")], text)
    assert [x["name"] for x in items] == ["Figma", "Framer", "Webflow", "Spline"]
    assert all(x["about"] == "" for x in items)


def test_r7c_two_posts_naming_the_same_thing_show_it_under_each_post_in_its_own_words(env, tmp_path):
    a = "Best icon sets\n- Lucide: clean icons\n- Iconoir: free icons"
    b = "Icons I use daily\n- Lucide: my favourite set\n- Phosphor: flexible icon family"
    use_lib(env, tmp_path, [("a1", "x", a, "2025-01-01", "2025-01-02", "instagram"),
                            ("a2", "y", b, "2025-02-01", "2025-02-02", "instagram")])
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [pick(u, "Best icon sets"), pick(u, "Icons I use")]}
    env["state"]["answers"]["mvp_extract"] = items_fake({
        "Best icon sets": {"items": [{"name": "Lucide", "about": "clean icons"},
                                     {"name": "Iconoir", "about": "free icons"}]},
        "Icons I use": {"items": [{"name": "Lucide", "about": "my favourite set"},
                                  {"name": "Phosphor", "about": "flexible icon family"}]}})
    msg = say(env, "what icon libraries should i use", ask("icon libraries"))
    assert "1. Lucide: clean icons" in msg and "3. Lucide: my favourite set" in msg and msg.count("Lucide") == 2


def test_r7c_the_numbers_run_across_posts_as_the_person_read_them_and_spanish_reads_naturally(ui):
    say(ui, UI_ASK, ask("UI/UX libraries"))
    say(ui, "add the fourth one to my list", {"intent": "todo_add", "pick_number": 4})
    t = ui["bot"].store.todos(H)[-1]
    assert t["text"] == "Iconoir" and t["url"] == ig("2022-09-01", 2)
    form = ask("librerías de UI/UX")
    form["lang"] = "es"
    ui["state"]["answers"]["mvp_compose"] = lambda u: dict(ui_compose(u), intro="")
    msg = say(ui, "¿qué librerías de ui ux debería usar?", form)
    assert "(publicado en junio de 2023, guardaste en julio de 2023):" in msg


# ---------- dates ----------
def test_r7c_dates_written_loosely():
    from mvp.dates import date_note, deadline_in, find_dates, instagram_posted, state_of
    today = date(2026, 11, 14)
    st = state_of("Apply by December 1", "2025-10-20", None, today)          # no year, a post from last year
    assert st["state"] == "passed" and st["date"] == date(2025, 12, 1)
    assert deadline_in("Program runs June 1 - August 15, 2027", "2026-10-01")[0] == date(2027, 8, 15)   # a range
    assert find_dates("Here are 5 tools, 3 may surprise you", "2026-01-01") == []                     # not 3 May
    assert deadline_in("Deadline: may 3", "2026-01-01")[0] == date(2026, 5, 3)
    assert find_dates("Event on 3 May", "2026-01-01")[0][0] == date(2026, 5, 3)
    st = state_of("Applications are open until further notice", "2024-05-01", None, today)
    assert date_note(st, today) == "from May 2024; check whether it is still open"     # never "probably closed"
    assert state_of("Applications now open!", None, "2026-11-13", today)["state"] is None   # kept yesterday: fresh
    code = code_for("2025-03-04")
    assert instagram_posted(f"https://instagram.com/reel/{code}?utm_source=ig_web_copy_link") == "2025-03-04"
    assert instagram_posted(f"https://www.instagram.com/p/{code}/?img_index=2") == "2025-03-04"
    assert instagram_posted(f"https://www.instagram.com/someuser/p/{code}/") == "2025-03-04"
    for not_a_post in ("https://www.instagram.com/someuser/", "https://www.instagram.com/explore/tags/design/",
                       "https://www.instagram.com/stories/someuser/3345678901234567890/"):
        assert instagram_posted(not_a_post) is None


PROGS = ("Programs to apply to:\nNASA L'SPACE Academy: free, apply by December 10, 2026\n"
         "City Lab fellowship: rolling applications")


def progs(env, tmp_path):
    use_lib(env, tmp_path, [("p1", "progs", PROGS, "2026-10-10", "2026-10-11", "instagram")])
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [pick(u, "Programs to apply")]}
    env["state"]["answers"]["mvp_extract"] = lambda u: {"items": [
        {"name": "NASA L'SPACE Academy", "about": "free, apply by December 10, 2026", "when": "December 10, 2026"},
        {"name": "City Lab fellowship", "about": "rolling applications", "when": ""}]}
    return say(env, "opportunities to apply for", ask("opportunities to apply for"))


def test_r7c_an_items_date_is_said_without_brackets_in_brackets(env, tmp_path):
    msg = progs(env, tmp_path)
    assert "1. NASA L'SPACE Academy: free, apply by December 10, 2026 (deadline 10 December, in 28 days)" in msg


def test_r7c_remind_me_two_days_before_its_deadline_counts_back_from_the_things_own_date(env, tmp_path):
    progs(env, tmp_path)
    bot = env["bot"]
    # the model cannot know the date, so its form has no time; code reads the thing's own date and counts back
    msg = say(env, "remind me about the nasa one two days before its deadline",
              {"intent": "act_on_last", "actions": [{"action": "message.send", "params": {}}]})
    assert "Tuesday 8 December at 9am" in msg and "NASA L'SPACE Academy" in msg
    spec = json.loads(bot.store.q("SELECT spec FROM rules WHERE handle=?", (H,))[-1]["spec"])
    assert spec["when"]["date"] == "2026-12-08" and spec["content"]["item_names"] == ["NASA L'SPACE Academy"]
    # a thing whose words give no date: said plainly, nothing set
    n = len(bot.store.q("SELECT id FROM rules WHERE handle=?", (H,)))
    msg = say(env, "remind me about city lab two days before its deadline",
              {"intent": "act_on_last", "actions": [{"action": "message.send", "params": {}}]})
    assert msg.startswith("The post gives no date for City Lab fellowship")
    assert len(bot.store.q("SELECT id FROM rules WHERE handle=?", (H,))) == n
    # "a week before" that is already past: said, nothing set; the day itself works
    env["clock"][0] = datetime(2026, 12, 5, 15, 0, tzinfo=timezone.utc)
    msg = say(env, "remind me about nasa a week before its deadline",
              {"intent": "act_on_last", "actions": [{"action": "message.send", "params": {}}]})
    assert "sooner than that" in msg and len(bot.store.q("SELECT id FROM rules WHERE handle=?", (H,))) == n


def test_r7c_put_it_in_my_calendar_takes_the_things_date_for_any_request(env, tmp_path):
    cap = "Design conferences\n- Config: the Figma conference, May 20, 2027\n- Awwwards Conference: Amsterdam"
    use_lib(env, tmp_path, [("c1", "conf", cap, "2026-10-10", "2026-10-11", "instagram")])
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [pick(u, "Design conferences")]}
    env["state"]["answers"]["mvp_extract"] = lambda u: {"items": [
        {"name": "Config", "about": "the Figma conference, May 20, 2027", "when": "May 20, 2027"},
        {"name": "Awwwards Conference", "about": "Amsterdam", "when": ""}]}
    say(env, "design talks worth watching", ask("design talks"))     # not a time-sensitive request
    msg = say(env, "put config in my calendar", {"intent": "act_on_last",
                                                  "actions": [{"action": "calendar.add", "params": {}}]})
    assert "20270520" in msg


# ---------- follow-ups ----------
def test_r7c_a_question_about_a_pick_with_change_words_in_it_stays_a_question(blender):
    from mvp.followup import request_change
    from mvp.schema import Interpretation
    q = Interpretation(intent="follow_up", question="x")
    assert request_change(q, "does the first one work without a gpu?") is None
    assert request_change(q, "what about the second one, is it long?") is None
    assert request_change(q, "not from the second one's creator")["creator"]       # plain change words still win
    assert request_change(q, "not on youtube")["platform"] == "instagram"           # never the platform it rules out
    assert request_change(q, "not on youtube")["avoid"] == []
    n_runs = blender["bot"].store.one("SELECT COUNT(*) n FROM runs WHERE kind='ask'")["n"]
    say(blender, "what about the second one, is it long?", {"intent": "follow_up", "question": "is the second one long?",
                                                            "pick_number": 2})
    assert blender["bot"].store.one("SELECT COUNT(*) n FROM runs WHERE kind='ask'")["n"] == n_runs


def test_r7c_what_about_ones_from_a_creator_asks_for_that_creator(blender):
    msg = say(blender, "what about ones from grant abbitt",
              {"intent": "follow_up", "question": "what about ones from grant abbitt"})
    assert shown_ids(blender) == ["b5"]
    assert msg.startswith("Here's what else I found in your saves for basic Blender tutorials, only from Grant Abbitt.")
    msg = say(blender, "what about ones from nobody known", {"intent": "follow_up", "question": "x"})
    assert msg == "I found nothing from that creator in your saves."


def test_r7c_ok_and_for_dinner_refines_the_request_and_the_opposite_is_asked_about(env, tmp_path):
    rows = [("f1", "cook", "Chicken and rice for lunch boxes", None, "2026-01-01", "instagram"),
            ("f2", "cook2", "Chicken and rice dinner in one pan", None, "2026-01-02", "instagram")]
    use_lib(env, tmp_path, rows)
    seen = []

    def compose(u):
        seen.append(u)
        return {"picks": [pick(u, "Chicken and rice for lunch")]} if "dinner" not in u.split("Candidates:")[0] else \
            {"picks": [pick(u, "dinner in one pan")]}
    env["state"]["answers"]["mvp_compose"] = compose
    env["state"]["answers"]["mvp_extract"] = lambda u: {}
    say(env, "chicken and rice recipes", ask("chicken and rice recipes"))
    msg = say(env, "ok and for dinner?", {"intent": "follow_up", "question": "and for dinner?"})
    assert msg.startswith("Here's what I found in your saves for chicken and rice recipes for dinner.")
    assert shown_ids(env) == ["f2"] and env["bot"].pool.queries[-1].endswith("for dinner")
    n_runs = env["bot"].store.one("SELECT COUNT(*) n FROM runs")["n"]
    msg = say(env, "the opposite", {"intent": "follow_up", "question": "the opposite"})
    assert msg.startswith("I'm not sure what the opposite would be here.")
    assert env["bot"].store.one("SELECT COUNT(*) n FROM runs")["n"] == n_runs


def test_r7c_a_thing_whose_own_words_name_only_an_earlier_year_is_left_out_for_a_years_request(env, tmp_path):
    cap = ("Opportunities for students\n- Design award 2024: for student designers\n- Summer lab: paid research for "
           "undergrads\n- Hack week 2026: build with mentors")
    use_lib(env, tmp_path, [("y1", "opps", cap, "2026-08-01", "2026-08-02", "instagram")])
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [pick(u, "Opportunities for students")]}
    env["state"]["answers"]["mvp_extract"] = lambda u: {"items": [
        {"name": "Design award 2024", "about": "for student designers", "fit": "unknown"},
        {"name": "Summer lab", "about": "paid research for undergrads", "fit": "unknown"},
        {"name": "Hack week 2026", "about": "build with mentors", "fit": "yes"}]}
    msg = say(env, "what opportunities might i have missed for 2026", ask("opportunities for 2026"))
    assert "Design award 2024" not in msg and "1. Hack week 2026" in msg and "2. Summer lab" in msg


def test_r7c_the_donut_change_read_as_more_still_leaves_the_donut_out(blender):
    # live, 14 Nov: the interpreter read "what about something that isnt a donut." as "more" with avoid ["donut"]; the
    # guard that lets a message's own words win over an avoid entry took "isnt a donut" as asking for one
    msg = say(blender, "what about something that isnt a donut.", {"intent": "more", "avoid": ["donut"]})
    ids = shown_ids(blender)
    assert ids and "b1" not in ids and "b3" not in ids
    assert msg.startswith("Here's what else I found in your saves for basic Blender tutorials, leaving out anything "
                          "about donut.")
    from mvp.profile import avoid_for
    assert avoid_for(["donut"], "something that isn't a donut") == ["donut"]
    assert avoid_for(["donut"], "anything other than donut") == ["donut"]
    assert avoid_for(["chicken"], "chicken and rice please") == []          # a message that asks for it still wins
