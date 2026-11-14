"""Offline tests for the round 8 live fix pass (findings 98 to 102; DESIGN.md section 12, "Round 8, live fix pass"):
the composer's verdict leads an items answer, lower-case names listed on lines of their own are kept, an earlier
year's post is left out of a time-sensitive answer, a request for deadlines needs a date code can read, a changed
request says what changed in every opening line, and the candidate window is refilled after an avoid word. Synthetic
data, a fake model, a fake search pool and a fake clock only (today is 12 Nov 2026 in New York)."""
import json
import os
import sys
from datetime import date

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_round7 import ask, ig, items_fake, pick, use_lib  # noqa: E402
from mvp.tests.test_round7 import blender, shown_ids, ui  # noqa: E402,F401  (fixtures)
from mvp.tests.test_round8_answers import It, names  # noqa: E402
from mvp.tests.test_slice2 import H, say  # noqa: E402

UI_ASK = "what are some uiux libraries i should use for my next project"


# ---------- finding 98: the composer's verdict leads an items answer ----------
PANTRY = ("Pantry UI kit\nA polished set of UI building blocks I keep coming back to. Each piece ships with copy "
          "and paste code.")
PARTS = ("Hey friends, meet some interface parts\n01. Slider\n02. Toggle\n03. Stepper\n"
         "Hope you liked the post")
SITES = ("Morning all, where to find icons?\n01. www.iconpile.xyz\n02. www.glyphbox.com\n03. www.svg.io\n"
         "04. iconfarm.app\nHope you liked the post")
ROWS98 = [("k1", "pantryfan", PANTRY, "2026-10-14", "2026-10-15", "instagram"),
          ("p1", "uiteacher", PARTS, "2022-11-03", "2022-11-04", "instagram"),
          ("s1", "uiteacher", SITES, "2022-08-11", "2022-08-12", "instagram")]
TABLE98 = {
    "Pantry UI kit": {"items": [{"name": "Pantry", "about": "", "fit": "unknown"}],
                      "key_points": ["A polished set of UI building blocks I keep coming back to",
                                     "Each piece ships with copy and paste code."]},
    "some interface parts": {"items": [{"name": n, "about": "", "fit": "yes"}
                                       for n in ("Slider", "Toggle", "Stepper")]},
    "where to find icons": {"items": [{"name": n, "about": "", "fit": "yes"}
                                      for n in ("iconpile", "glyphbox", "svg", "iconfarm")]},
}


def compose98(u):
    """The composer: the post about one library is clear; the two list posts only come close."""
    return {"picks": [pick(u, "Pantry UI kit", title="Pantry UI kit"),
                      pick(u, "some interface parts", "close", title="Interface parts"),
                      pick(u, "where to find icons", "close", title="Where to find icons")]}


@pytest.fixture()
def lib98(env, tmp_path):
    use_lib(env, tmp_path, ROWS98, name="lib98")
    env["state"]["answers"]["mvp_compose"] = compose98
    env["state"]["answers"]["mvp_extract"] = items_fake(TABLE98)
    return env


def test_98_a_clear_post_about_one_thing_leads_and_close_lists_follow_under_their_own_label(lib98):
    msg = say(lib98, UI_ASK, ask("some uiux libraries i should use for my next project", ["ui libraries"]))
    # only the clear post's thing is counted as the kind asked for; the request's own spelling is not echoed
    assert msg.startswith("I found 1 UI/UX library in your saves, and 2 posts that come close.\n")
    lines = msg.split("\n")
    heads = [x for x in lines if x.startswith("From ")]
    assert heads[0].startswith('From "Pantry UI kit" by @pantryfan')   # never pushed down by a longer list
    assert "1. Pantry: A polished set of UI building blocks I keep coming back to; Each piece ships with copy and " \
           "paste code" in msg
    label = lines.index("Close, but not quite what you asked:")
    assert lines.index(heads[0]) < label < lines.index(heads[1]) and msg.count("Close, but not quite") == 1
    # one numbering through the whole answer, clear then close
    assert "2. Slider" in msg and "4. Stepper" in msg and "5. iconpile" in msg
    assert "I recommend" not in msg


def test_98_a_follow_up_acts_on_a_close_thing_by_number_and_by_name(lib98):
    say(lib98, UI_ASK, ask("UI/UX libraries", ["ui libraries"]))
    bot = lib98["bot"]
    say(lib98, "add the third one to my list", {"intent": "todo_add", "pick_number": 3})
    assert bot.store.todos(H)[-1]["text"] == "Toggle" and bot.store.todos(H)[-1]["url"] == ig("2022-11-03", 2)
    say(lib98, "add glyphbox to my list", {"intent": "act_on_last", "actions": [{"action": "todo.add", "params": {}}]})
    assert bot.store.todos(H)[-1]["text"] == "glyphbox" and bot.store.todos(H)[-1]["url"] == ig("2022-08-11", 3)
    say(lib98, "add the first one to my list", {"intent": "todo_add", "pick_number": 1})
    assert bot.store.todos(H)[-1]["text"] == "Pantry"


def test_98_with_no_clear_source_the_closest_wording_leads_never_a_count(lib98):
    lib98["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        pick(u, "Pantry UI kit", "close", title="Pantry UI kit"),
        pick(u, "some interface parts", "close", title="Interface parts")]}
    msg = say(lib98, UI_ASK, ask("UI/UX libraries", ["ui libraries"]))
    assert msg.startswith('Nothing I found is a clear fit for "UI/UX libraries".\nThese come closest:\n')
    assert "I found 1" not in msg and "named in" not in msg and "Close, but not quite" not in msg
    # inside a verdict, the post with more good things first (as before)
    assert "1. Slider" in msg and "4. Pantry" in msg


def test_98_a_post_the_composer_said_no_to_is_never_a_source(lib98):
    lib98["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        pick(u, "Pantry UI kit", title="Pantry UI kit"),
        pick(u, "some interface parts", "no", title="Interface parts"),
        pick(u, "where to find icons", "close", title="Where to find icons")]}
    msg = say(lib98, UI_ASK, ask("UI/UX libraries", ["ui libraries"]))
    assert "Slider" not in msg and "Interface parts" not in msg
    assert msg.startswith("I found 1 UI/UX library in your saves, and one post that comes close.\n")


def test_98_an_answer_whose_sources_are_all_clear_is_unchanged(ui):
    msg = say(ui, UI_ASK, ask("UI/UX libraries", ["ui ux libraries", "design systems"]))
    assert msg.startswith("I found 5 UI/UX libraries named in 2 of your saves.\n\nFrom \"Best design systems\"")
    assert "Close, but not quite" not in msg and "come close" not in msg and "closest" not in msg


def test_98_a_close_source_says_what_it_misses_when_the_composer_gave_it(lib98):
    lib98["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        pick(u, "Pantry UI kit", title="Pantry UI kit", criteria=[{"answer": "yes", "quote": "polished"}]),
        pick(u, "some interface parts", "close", title="Interface parts", criteria=[{"answer": "unknown"}])]}
    msg = say(lib98, UI_ASK, ask("UI/UX libraries", ["ui libraries"], criteria=["free to use"]))
    assert msg.count("I couldn't confirm") == 1 and 'I couldn\'t confirm it clearly fits "free to use".' in msg
    assert msg.index("4. Stepper") < msg.index("I couldn't confirm it")
    from mvp.render import close_note, negated
    from mvp.schema import RuleSpec
    spec = RuleSpec.model_validate({"when": {"type": "now"}, "content": {"goal": "UI kits", "searches": ["ui kits"], "criteria": ["free to use"]}})
    assert close_note({"criteria": ["no"]}, spec) == 'It doesn\'t fit "free to use".'
    assert close_note({"criteria": ["yes"]}, spec) == "" and close_note({}, spec) == ""
    assert negated("is under 10 minutes long") == "isn't under 10 minutes long"
    assert negated("walks you through a whole project") == "doesn't walk you through a whole project"


def test_98_lower_case_names_listed_on_lines_of_their_own_are_kept_together():
    from mvp.extract import clean_items
    got, dropped = clean_items([{"name": n, "about": "", "fit": "yes"}
                                for n in ("iconpile", "glyphbox", "svg", "iconfarm")], It(SITES))
    # a web address on a marked line lists the site by its name; the bare format word is still junk
    assert names(got) == ["iconpile", "glyphbox", "iconfarm"] and dropped == 1
    assert all(x.get("listed") for x in got)
    # lower-case names alone on lines, three or more: kept whatever their case
    text = ("My Favourite Kits For Every Project\n- radix ui\n- park ui\n- ark ui\nThanks For Reading Everyone")
    got, _ = clean_items([{"name": n, "about": ""} for n in ("radix ui", "park ui", "ark ui")], It(text))
    assert names(got) == ["radix ui", "park ui", "ark ui"]
    # near-variants: two such lines are not a run; a line that goes on after the name is a sentence, not a list entry
    got, _ = clean_items([{"name": n, "about": ""} for n in ("radix ui", "park ui")],
                         It("My Favourite Kits For Every Project\n- radix ui\n- park ui\nThanks For Reading"))
    assert names(got) == []
    got, _ = clean_items([{"name": n, "about": ""} for n in ("radix ui", "park ui", "notion")],
                         It("My Kits For Every Project\n- radix ui\n- park ui\n- notion is where i keep them\nThanks"))
    assert "notion" not in names(got)


def test_98_the_opening_line_reads_run_together_spellings_properly():
    from mvp.render import found_noun, one_of
    for goal in ("uiux libraries", "ui ux libraries", "UI-UX libraries", "ui/ux libraries", "some uiux libraries i "
                 "should use for my next project"):
        assert found_noun(goal) == "UI/UX libraries", goal
    assert found_noun("ux ui tools") == "UX/UI tools"
    assert found_noun("guiux libraries") != "UI/UX libraries"          # only a whole word is respelled
    assert found_noun("startup motivation reels") is None               # never a noun it invents
    assert one_of("UI/UX libraries") == "UI/UX library" and one_of("opportunities") == "opportunity"
    assert one_of("things") == "thing" and one_of("cosas") == "cosa"


# ---------- finding 99: an earlier year's post in a time-sensitive answer ----------
NOW = ("Student programmes worth a look\n- Northwind Lab: for first and second year students who build software\n"
       "- Orbit Fellows: a paid summer program for students in any major")
Y2024 = ("Side income plans for 2024? Side opportunities\n- Gigboard: find freelance clients for your skills\n"
         "- Taskly: sell small gigs to buyers online")
ROWS99 = [("n1", "chances", NOW, "2026-08-20", "2026-08-21", "instagram"),
          ("y1", "hustle", Y2024, "2024-03-15", "2024-05-01", "instagram")]
TABLE99 = {
    "Student programmes worth a look": {"items": [
        {"name": "Northwind Lab", "about": "for first and second year students who build software", "fit": "yes"},
        {"name": "Orbit Fellows", "about": "a paid summer program for students in any major", "fit": "yes"}]},
    "Side income plans for 2024": {"items": [
        {"name": "Gigboard", "about": "find freelance clients for your skills", "fit": "yes"},
        {"name": "Taskly", "about": "sell small gigs to buyers online", "fit": "yes"}]},
}


@pytest.fixture()
def lib99(env, tmp_path):
    use_lib(env, tmp_path, ROWS99, name="lib99")
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        pick(u, "Student programmes worth a look", title="Student programmes"),
        pick(u, "Side income plans for 2024", title="Side income plans for 2024?")]}
    env["state"]["answers"]["mvp_extract"] = items_fake(TABLE99)
    return env


def test_99_a_post_of_an_earlier_year_gives_no_things_in_a_time_sensitive_answer(lib99):
    msg = say(lib99, "opportunities to pursue soon", ask("opportunities to pursue soon"))
    assert "Northwind Lab" in msg and "Orbit Fellows" in msg
    assert "Gigboard" not in msg and "Taskly" not in msg and "Side income plans" not in msg
    run = lib99["bot"].store.one("SELECT dropped FROM runs WHERE kind='ask' ORDER BY id DESC LIMIT 1")
    assert json.loads(run["dropped"]).get("old_year") == 1          # a pick of the composer: left out before details
    # read only for its list (finding 94), it gives no things either
    lib99["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        pick(u, "Student programmes worth a look", title="Student programmes")]}
    msg = say(lib99, "other opportunities to pursue soon", ask("other opportunities to pursue soon"))
    assert "Northwind Lab" in msg and "Gigboard" not in msg
    run = lib99["bot"].store.one("SELECT dropped, steps FROM runs WHERE kind='ask' ORDER BY id DESC LIMIT 1")
    assert json.loads(run["steps"])["items_reads"] == 2 and json.loads(run["dropped"]).get("items_old_year") == 2


def test_99_the_same_post_in_a_request_that_is_not_time_sensitive_is_unchanged(lib99):
    msg = say(lib99, "side hustle ideas", ask("side hustle ideas"))
    assert "Gigboard: find freelance clients for your skills" in msg and "Northwind Lab" in msg


def test_99_an_earlier_years_pick_is_left_out_while_another_fits_and_alone_says_its_date():
    from mvp.answers import post_dates

    class Item:
        def __init__(self, iid, caption, posted):
            self.id, self.caption, self.raw_caption, self.platform = iid, caption, caption, "instagram"
            self.url, self.dates, self.kinds, self.first_line = ig(posted), {"save": posted}, {"save"}, caption

    old = {"item": Item("a", "Best side hustles of 2024, start now", "2024-03-15"), "verdict": "clear",
           "title": "Best side hustles of 2024"}
    new = {"item": Item("b", "Student programmes this winter", "2026-08-20"), "verdict": "close", "title": "Programmes"}
    result = {"picks": [old, new], "wider": [], "dropped": {}}
    post_dates(result, {}, date(2026, 11, 12), True)
    assert [p["title"] for p in result["picks"]] == ["Programmes"] and result["dropped"]["old_year"] == 1
    old2 = dict(old)
    result = {"picks": [old2], "wider": [], "dropped": {}}
    post_dates(result, {}, date(2026, 11, 12), True)
    from mvp.dates import date_note
    assert result["picks"][0]["title"] == "Best side hustles of 2024"
    assert date_note(result["picks"][0]["date_state"], date(2026, 11, 12)) == "from March 2024"
    # near-variants: a post that names this year, or a 2024 post less than a year old, is not an earlier year's post
    from mvp.answers import old_year_post
    today = date(2026, 11, 12)
    assert not old_year_post({"item": Item("c", "Plans for 2024 and 2026", "2024-03-15"), "title": "x",
                              "age_from": "2024-03-15"}, {}, today)
    assert not old_year_post({"item": Item("d", "Recap of 2025", "2026-01-10"), "title": "x",
                              "age_from": "2026-01-10"}, {}, today)


def test_99_categories_of_work_joined_by_and_are_not_things():
    from mvp.extract import activity_name, clean_items
    for n in ("Writing & Editing", "Tutoring & Coaching", "Web Design & Development", "Customer Support and Data Entry",
              "Graphic Design & Online Marketing"):
        assert activity_name(n), n
    for n in ("Procter & Gamble", "Ben & Jerry's", "Dungeons & Dragons", "Writing", "Gigboard"):
        assert not activity_name(n), n
    text = "Ways to earn\n- Writing & Editing: write for clients\n- Gigboard: find freelance clients fast"
    got, dropped = clean_items([{"name": "Writing & Editing", "about": "write for clients"},
                                {"name": "Gigboard", "about": "find freelance clients fast"}], It(text))
    assert names(got) == ["Gigboard"] and dropped == 1


def test_99_soon_and_to_pursue_make_a_part_time_sensitive_by_its_own_words(env, tmp_path):
    from mvp.dates import time_sensitive
    assert time_sensitive("things to pursue") and time_sensitive("upcoming things") and time_sensitive("this month")
    assert not time_sensitive("startup motivation reels")
    rows = [("m1", "grind", "Startup motivation reel: keep building. Applications are now open for our club",
             "2024-05-02", "2024-05-03", "instagram"),
            ("m2", "grants", "Founder grants to pursue: Seed Fund applications close January 15", "2026-10-01",
             "2026-10-02", "instagram")]
    use_lib(env, tmp_path, rows, name="lib99b")
    env["state"]["answers"]["mvp_extract"] = lambda u: {}

    def compose(u):
        body = u.split("Candidates:")[-1]
        if "motivation" in u.split("Candidates:")[0]:
            return {"picks": [pick(u, "Startup motivation reel", title="Keep building")]}
        return {"picks": [pick(u, "Founder grants", title="Founder grants")]} if "Founder grants" in body else {}
    env["state"]["answers"]["mvp_compose"] = compose
    msg = say(env, "send me startup motivation reels, or grants to pursue soon",
              ask("startup motivation reels, grants to pursue soon"))
    part1 = msg.split("Grants to pursue soon:")[0]
    assert part1.startswith("Startup motivation reels:")
    # the first part is not time-sensitive by its own words: no date talk about an old "now open"
    assert "probably closed" not in part1 and "from May 2024" not in part1
    assert "Deadline 15 January 2027" in msg.split("Grants to pursue soon:")[1]


# ---------- finding 100: a request for deadlines needs a date code can read ----------
STORY = ("Late night form\n3 friends. 1 form. 0 sleep. 2 hours before the deadline. All in.")
AHEAD = "Founder fellowship: applications close December 1. Apply with a short video"
PASSED = "Design award: deadline February 14, 2025. Send your best project"
ROWS100 = [("t1", "storyteller", STORY, "2026-05-12", "2026-05-13", "instagram"),
           ("t2", "fellows", AHEAD, "2026-10-01", "2026-10-02", "instagram"),
           ("t3", "awards", PASSED, "2024-12-01", "2024-12-02", "instagram")]


@pytest.fixture()
def lib100(env, tmp_path):
    use_lib(env, tmp_path, ROWS100, name="lib100")
    env["state"]["answers"]["mvp_extract"] = lambda u: {}
    return env


def test_100_a_story_that_mentions_a_deadline_with_no_date_is_only_the_closest(lib100):
    lib100["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [pick(
        u, "Late night form", title="Late night form", because="it mentions a deadline and a timed form",
        facts=[{"label": "deadline", "quote": "2 hours before the deadline"}])]}
    msg = say(lib100, "things with deadlines", ask("things with deadlines"))
    assert msg.startswith("Nothing in your saves has a deadline I can read that is still ahead.\n\nThe closest I have "
                          "is Late night form by @storyteller")
    assert "It mentions a deadline but gives no date." in msg
    assert "I recommend" not in msg and "because it mentions a deadline" not in msg


def test_100_a_pick_with_a_date_ahead_stays_a_clear_fit_and_leads(lib100):
    lib100["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        pick(u, "Late night form", title="Late night form"),
        pick(u, "Founder fellowship", title="Founder fellowship")]}
    msg = say(lib100, "things with deadlines", ask("things with deadlines"))
    assert "I recommend Founder fellowship by @fellows" in msg and "Deadline 1 December (in 19 days)." in msg
    assert "Or these, which are close too:" in msg and "• Late night form" in msg
    assert "Nothing in your saves has a deadline" not in msg


def test_100_a_passed_date_is_said_as_passed(lib100):
    lib100["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [pick(u, "Design award", title="Design award")]}
    msg = say(lib100, "things with deadlines", ask("things with deadlines"))
    assert msg.startswith("Nothing in your saves has a deadline I can read that is still ahead.")
    assert "Its deadline, 14 February 2025, has passed." in msg and "gives no date" not in msg


def test_100_a_request_that_does_not_ask_for_deadlines_is_unchanged(lib100):
    lib100["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [pick(u, "Late night form",
                                                                          title="Late night form")]}
    msg = say(lib100, "startup stories", ask("startup stories"))
    assert "I recommend Late night form" in msg and "Nothing in your saves has a deadline" not in msg
    from mvp.dates import asks_deadlines
    assert asks_deadlines("things with deadlines") and asks_deadlines("what closes soon") and \
        asks_deadlines("apply by friday") and asks_deadlines("scholarships due this month")
    assert not asks_deadlines("workouts due to my knee") and not asks_deadlines("startup stories")


# ---------- finding 101: a changed request says what changed; the window is refilled ----------
def test_101_the_closest_answer_to_a_changed_request_names_the_change(blender):
    blender["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        pick(u, "BLENDER BASICS", "close", title="BLENDER BASICS")]}
    msg = say(blender, "what about something that isnt a donut.",
              {"intent": "follow_up", "question": "What about something that isn't a donut?", "avoid": ["donut"]})
    assert msg.startswith("Nothing I found is a clear fit for basic Blender tutorials, leaving out anything about "
                          "donut.\n\nThe closest I have is BLENDER BASICS")
    # read as "more", the same
    blender["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        pick(u, "sword", "close", title="Sword modelling")]}
    msg = say(blender, "what about something that isnt a donut.", {"intent": "more", "avoid": ["donut"]})
    assert msg.startswith("Nothing I found is a clear fit for basic Blender tutorials, leaving out anything about "
                          "donut.")


def test_101_the_found_answer_to_a_changed_request_keeps_its_line(blender):
    blender["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [pick(u, "sword", title="Sword modelling")]}
    msg = say(blender, "what about something that isnt a donut.", {"intent": "more", "avoid": ["donut"]})
    assert msg.startswith("Here's what else I found in your saves for basic Blender tutorials, leaving out anything "
                          "about donut.")


def test_101_the_closest_pick_of_a_changed_request_says_what_is_missing(env, tmp_path, monkeypatch):
    from mvp.tests.test_round7 import BLENDER
    use_lib(env, tmp_path, BLENDER, name="lib101")
    import mvp.config as C
    monkeypatch.setattr(C, "OUTSIDE_ON", False)
    env["state"]["answers"]["mvp_extract"] = lambda u: {}
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        pick(u, "Beginner Blender 4.0", title="Beginner Blender 4.0", criteria=[{"answer": "yes", "quote": "Blender"}])]}
    say(env, "basic blender tutorials with free tools", ask("basic Blender tutorials", criteria=["uses only free tools"]))
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        pick(u, "sword", "close", title="Sword modelling", criteria=[{"answer": "unknown"}])]}
    msg = say(env, "what about something that isnt a donut.",
              {"intent": "follow_up", "question": "What about something that isn't a donut?", "avoid": ["donut"]})
    assert msg.startswith("Nothing I found is a clear fit for basic Blender tutorials, leaving out anything about "
                          "donut.\n\nI couldn't confirm any of these clearly fits \"uses only free tools\", but the "
                          "closest I have is Sword modelling")


def test_101_nothing_left_after_a_change_read_as_more_says_the_change(blender):
    blender["state"]["answers"]["mvp_compose"] = lambda u: {"picks": []}
    msg = say(blender, "what about something that isnt a donut.", {"intent": "more", "avoid": ["donut"]})
    assert msg.startswith("I found nothing else in your saves for basic Blender tutorials, leaving out anything about "
                          "donut.")
    # with no change words it is the plain "that's all" line, as before
    msg = say(blender, "another one", {"intent": "more"})
    assert msg.startswith("That's all I have in your saves for")


def test_101_an_avoid_word_read_in_descriptions_refills_the_window(env, tmp_path, monkeypatch):
    rows = [(f"d{i:02d}", "Guru", f"Beginner series video {i}", None, "2025-01-01", "youtube") for i in range(15)] + \
           [(f"o{i:02d}", f"maker{i}", f"Blender basics lesson {i}", None, "2025-01-01", "youtube") for i in range(40)]
    use_lib(env, tmp_path, rows, name="lib101b")
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key-not-real")
    from mvp import ytinfo
    monkeypatch.setattr(ytinfo, "fetch_batch", lambda ids, key, timeout=None: {"items": [
        {"id": v, "snippet": {"description": "we model a donut" if v.startswith("vidd") else "learn the basics",
                              "publishedAt": "2025-01-01T00:00:00Z"}, "contentDetails": {"duration": "PT9M"}}
        for v in ids]})
    import mvp.config as C
    monkeypatch.setattr(C, "OUTSIDE_ON", False)
    env["state"]["answers"]["mvp_extract"] = lambda u: {}
    env["seen"] = []

    def compose(u):
        env["seen"].append(u.split("Candidates:")[-1])
        return {"picks": [pick(u, "Blender basics lesson 0", title="Lesson 0")]}
    env["state"]["answers"]["mvp_compose"] = compose
    say(env, "blender basics please", ask("blender basics", avoid=["donut"]))
    seen = env["seen"][0]
    assert "donut" not in seen.lower() and "Beginner series" not in seen
    import re
    assert len(re.findall(r"^\d+\. ", seen, re.M)) == 40            # 25 from the first window, 15 refilled
    assert "Blender basics lesson 39" in seen
    run = env["bot"].store.one("SELECT steps FROM runs WHERE kind='ask' ORDER BY id DESC LIMIT 1")
    steps = json.loads(run["steps"])
    assert steps["avoided_by_description"] == 15 and steps["refilled"] == 15
    # near-variant: with no avoid word the window is the first 40, as before
    env["seen"].clear()
    say(env, "blender basics", ask("blender basics"))
    assert len(re.findall(r"^\d+\. ", env["seen"][0], re.M)) == 40 and "Beginner series video 0" in env["seen"][0]
    assert "Blender basics lesson 39" not in env["seen"][0]


# ---------- finding 102: a title that names the request's year or season ----------
def test_102_the_years_a_requests_qualifiers_name_are_counted_from_today():
    from mvp.dates import request_years
    today = date(2026, 11, 12)
    assert request_years(today, "programs for 2026 or next summer") == {2026, 2027}
    assert request_years(today, "this winter") == {2026} and request_years(date(2026, 3, 1), "next summer") == {2026}
    assert request_years(today, "internships") == set()


def test_102_a_title_that_names_a_kind_and_list_promises_a_list():
    from mvp.extract import promises_list
    assert promises_list("Summer 2027 job list") and promises_list("My tools list")
    assert not promises_list("Grocery list") and not promises_list("Bucket list for the summer")


ROUNDUP = "Opportunities roundup {n}\n- Alpha Lab {n}: a paid program\n- Beta Fund {n}: a small grant\n" \
          "- Gamma Prize {n}: a yearly award"
ROWS102 = [("m1", "chances", NOW, "2026-08-20", "2026-08-21", "instagram")] + \
    [(f"r{n}", f"lists{n}", ROUNDUP.format(n=n), "2026-08-01", "2026-08-02", "instagram") for n in range(1, 7)] + \
    [("q1", "summerlist", "Summer 2027 job list\nopportunities for students, by @someone", "2026-07-02",
      "2026-07-03", "instagram")]


def test_102_a_title_that_names_the_requests_season_year_is_read_first_and_says_where_its_names_are(env, tmp_path):
    use_lib(env, tmp_path, ROWS102, name="lib102")
    env["seen"] = []
    env["state"]["answers"]["mvp_extract"] = items_fake(TABLE99, env["seen"])
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        pick(u, "Student programmes worth a look", title="Student programmes")]}
    say(env, "opportunities for next summer", ask("opportunities for next summer", ["summer opportunities"]))
    read = [u.split("<item>", 1)[-1] for u in env["seen"]]
    assert len(read) == 6 and any("Summer 2027 job list" in x for x in read)   # read before the lists
    # near-variant: a request with no year or season reads the lists by their score alone
    env["seen"].clear()
    say(env, "other opportunities", ask("other opportunities", ["opportunities"]))
    assert not any("Summer 2027 job list" in u for u in env["seen"])
    # shown as a pick with nothing in its text: its title promises a list, so the line says where the names are
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        pick(u, "Student programmes worth a look", title="Student programmes"),
        pick(u, "Summer 2027 job list", "close", title="Summer 2027 job list")]}
    msg = say(env, "jobs for next summer", ask("jobs for next summer", ["summer jobs"]))
    assert "• Summer 2027 job list by @summerlist: the names are in its slides, not its text." in msg
