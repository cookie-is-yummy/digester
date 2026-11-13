"""Offline tests for fix pass 4 (live findings of 13 Nov, round 4, after a full setup): one or more tests per finding 74
to 83, each failing without its fix. The common thread: what the setup taught the bot must make later answers better
and never block one. Synthetic data, a fake model, a fake search pool, a fake YouTube and a fake clock only; the
fixtures come from the earlier test files."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, say  # noqa: E402
from mvp.tests.test_slice3 import add_items  # noqa: E402
from mvp.tests.test_slice5 import yt  # noqa: E402,F401
from mvp.tests.test_slice6 import number_of, rich  # noqa: E402,F401

CHICKEN = "convenient chicken and rice recipes"


def request_of(user):
    return json.loads(user.split("\n", 1)[0][len("Request: "):])


def with_profile(bot, tools=("Instant Pot",), time="20 minutes on weeknights", note="trying to cook at home more",
                 interests=None):
    bot.store.set_prefs(H, tools=list(tools), time=time)
    if note:
        bot.store.add_profile_note(H, note)
    if interests is not None:
        from mvp import profile as P
        P.set_interests(bot.store, H, interests)


def ask_form(goal, searches, criteria=(), **content):
    return {"intent": "ask", "spec": {"when": {"type": "now"}, "content": dict(
        {"goal": goal, "searches": list(searches), "criteria": list(criteria)}, **content)}}


def rule_form(goal, searches, criteria=(), when=None, **content):
    return {"intent": "new_rule", "spec": {"when": when or {"type": "schedule", "every_days": 2,
                                                            "window": ["09:00", "21:00"]},
                                           "content": dict({"goal": goal, "searches": list(searches),
                                                            "criteria": list(criteria)}, **content)}}


def all_yes(seen):
    """A composer that picks the lemon pasta and answers every must-have it is given with a backed yes."""
    def answer(u):
        req = request_of(u)
        seen.append(req)
        return {"picks": [{"n": number_of(u, "Lemon garlic"), "verdict": "clear", "title": "Lemon garlic pasta",
                           "criteria": [{"answer": "yes", "quote": "Lemon garlic pasta"} for _ in req["criteria"]]}],
                "intro": "I found a convenient recipe in your saves."}
    return answer


# ======================================= 74. preferences are not must-haves =======================================
def test_74_the_kit_and_the_usual_time_from_the_profile_are_not_must_haves(env):
    bot, st = env["bot"], env["state"]
    with_profile(bot)
    seen = []
    st["answers"]["mvp_compose"] = all_yes(seen)
    msg = say(env, CHICKEN, ask_form("convenient chicken and rice recipes", ["chicken and rice"],
                                     ["convenient", "uses Instant Pot", "under 20 minutes on weeknights",
                                      "ends with a dish you can eat"]))
    assert seen[-1]["criteria"] == ["convenient", "ends with a dish you can eat"]
    assert "I recommend" in msg and "couldn't confirm" not in msg


def test_74_the_same_words_said_in_the_message_stay_must_haves(env):
    bot, st = env["bot"], env["state"]
    with_profile(bot)
    seen = []
    st["answers"]["mvp_compose"] = all_yes(seen)
    say(env, "chicken and rice in my instant pot, under 20 minutes",
        ask_form("chicken and rice", ["chicken and rice"], ["uses Instant Pot", "under 20 minutes"]))
    assert seen[-1]["criteria"] == ["under 20 minutes"] or "under 20 minutes" in seen[-1]["criteria"]
    # the kit they have and name is a preference the executor already handles (finding 53); the time they name stays
    from mvp.interpret import profile_guard
    from mvp.schema import Interpretation
    it = Interpretation.model_validate(ask_form("chicken and rice", ["chicken and rice"],
                                                ["uses Instant Pot", "under 20 minutes", "for weeknights"]))
    prof = {"prefs": {"tools": ["Instant Pot"], "time": "20 minutes on weeknights"}, "notes": [], "interests": []}
    out = profile_guard(it, "chicken and rice in my instant pot, under 20 minutes", prof)
    assert out.spec.content.criteria == ["uses Instant Pot", "under 20 minutes"]   # "weeknights" was not said


def test_74_a_rule_drops_restated_preferences_and_a_note_and_keeps_its_own_words(env):
    from mvp.interpret import profile_guard
    from mvp.schema import Interpretation
    prof = {"prefs": {"tools": ["Instant Pot"], "time": "20 minutes on weeknights"},
            "notes": ["trying to cook at home more", "vegetarian now"], "interests": []}
    it = Interpretation.model_validate(rule_form(
        "a quick dinner idea", ["quick dinner"],
        ["quick", "for weeknights", "uses an Instant Pot", "usually fits 20 minutes", "ends with a dish you can eat"],
        when={"type": "random", "per": "week", "count": 2}))
    out = profile_guard(it, "randomly surprise me with a quick dinner idea a couple of times a week", prof)
    assert out.spec.content.criteria == ["quick", "ends with a dish you can eat"]
    # a diet restated from a note is not a must-have: it is what the diet rules out, in avoid (the one hard limit)
    it = Interpretation.model_validate(ask_form("dinner ideas", ["dinner"], ["vegetarian", "cooked at home"]))
    out = profile_guard(it, "any dinner ideas?", prof)
    assert out.spec.content.criteria == []
    assert {"meat", "fish"} <= set(out.spec.content.avoid)


def test_74_the_composer_is_told_preferences_are_soft(env):
    from mvp import profile as P
    bot = env["bot"]
    with_profile(bot, note=None)
    bot.store.set_prefs(H, avoid=["mushroom"])
    # the interpreter's lines read as before (a "never must-haves" wording turned a live ask into chat); code drops a
    # restated preference instead (profile_guard, above)
    line = [x for x in P.about_lines(bot.store, H, CHICKEN) if x.startswith("Preferences")][0]
    assert line == "Preferences: avoid mushroom; has an Instant Pot; usually has 20 minutes on weeknights."
    text, _, _ = P.composer_context(bot.store, H, CHICKEN)
    assert "Leave out: avoid mushroom" in text
    assert "never a reason to call a pick close" in text and "usually has 20 minutes on weeknights" in text
    # the evaluation set's profile ("none given") reads exactly as before
    bot.store.x("UPDATE people SET prefs='{}' WHERE handle=?", (H,))
    P.set_interests(bot.store, H, [{"topic": "Pasta", "confirmed": True}])
    assert P.about_lines(bot.store, H, "a pasta recipe")[-1] == "Preferences: none given."


# ======================================= 80. a whole recipe written out is a finished result ==========================
COOK = "what should I cook tonight?"
COOK_FORM = ask_form("something to cook tonight", ["cook tonight", "easy dinner recipe"],
                     ["ends with a dish you can eat"])


def close_lemon(u):
    """The composer cannot quote "a dish you can eat": the lemon pasta comes back close, the must-have unknown."""
    return {"picks": [{"n": number_of(u, "Lemon garlic"), "verdict": "close", "title": "Lemon garlic pasta",
                       "criteria": [{"answer": "unknown"}]}], "intro": "Here's something to cook tonight."}


def test_80_a_pick_whose_text_holds_the_whole_recipe_is_recommended_not_the_closest(env):
    st = env["state"]
    st["answers"]["mvp_compose"] = close_lemon
    st["answers"]["mvp_extract"] = lambda u: {"ingredients": ["200g spaghetti", "2 lemons"],
                                              "steps": ["4 cloves garlic", "Lemon garlic pasta"]}
    msg = say(env, COOK, COOK_FORM)
    assert "I recommend Lemon garlic pasta" in msg
    assert "couldn't confirm" not in msg and "closest" not in msg and "couldn't check" not in msg
    assert "Ingredients (2):" in msg and "Steps (2):" in msg


@pytest.mark.parametrize("facts", [{"ingredients": ["200g spaghetti", "2 lemons"], "steps": ["4 cloves garlic"]},
                                   {"ingredients": ["200g spaghetti", "2 lemons"], "steps": []},
                                   {"steps": ["4 cloves garlic", "Lemon garlic pasta"]}],
                         ids=["one step", "no steps", "no ingredients"])
def test_80_without_the_whole_recipe_the_pick_stays_the_closest(env, facts):
    st = env["state"]
    st["answers"]["mvp_compose"] = close_lemon
    st["answers"]["mvp_extract"] = lambda u: dict(facts)
    msg = say(env, COOK, COOK_FORM)
    assert "I couldn't confirm" in msg and "I recommend" not in msg


def test_80_a_workout_with_two_steps_meets_its_full_routine_must_have_and_tips_stay_no():
    from mvp.executor import finished_by_details, makes_whole
    from mvp.libview import Item
    from mvp.schema import RuleSpec
    assert makes_whole({"steps": ["20 squats", "10 push-ups"]}, food=False)
    assert not makes_whole({"steps": ["20 squats", "10 push-ups"]}, food=True)
    spec = RuleSpec.model_validate({"when": {"type": "now"}, "content": {
        "goal": "a leg workout", "searches": ["leg workout"], "criteria": ["a full routine from start to finish"]}})

    def item(cap):
        return Item({"id": "w", "platform": "instagram", "source_url": "https://example.com/w", "caption": cap,
                     "interaction_kinds": ["save"], "platform_data": {"owner_handle": "coach"}})
    for cap, want in [("Leg day routine:\n20 squats\n10 push-ups", "clear"),
                      ("5 tips for better squats: 20 squats a day, 10 push-ups", "close")]:
        p = {"item": item(cap), "verdict": "close", "criteria": ["unknown"], "facts": {
            "steps": ["20 squats", "10 push-ups"]}, "too_long": False}
        result = {"picks": [p], "wider": [], "closest": True, "missing": [("x", "unknown")], "dropped": {},
                  "n_clear": 0, "n_close": 1, "extract": ["steps"]}
        finished_by_details(result, spec, {})
        assert p["verdict"] == want, cap
        assert result["closest"] is (want != "clear")


# ======================================= 81. one cut-off "step" =======================================
def test_81_one_line_or_a_sentence_about_the_video_is_never_shown_as_steps():
    from mvp.extract import usable
    desc = "This motion design tutorial teach how to create basic, beginner level motion graphics in under 20…"
    assert usable({"steps": [desc]})["steps"] == []
    assert usable({"steps": ["In this video I show my workflow", "Open After Effects"]})["steps"] == []
    assert usable({"steps": ["Open After Effects", "Make a new composition…", "Add a shape layer"]})["steps"] == \
        ["Open After Effects", "Add a shape layer"]
    assert usable({"steps": ["Boil the pasta", "Toss with lemon"], "ingredients": ["2 lemons"]}) == \
        {"steps": ["Boil the pasta", "Toss with lemon"], "ingredients": ["2 lemons"]}
    assert usable({"key_points": ["Space your reviews", "Test yourself before you reread and then…"]})["key_points"] \
        == ["Space your reviews"]


def test_81_a_youtube_pick_with_one_description_line_says_the_steps_are_in_the_video(env, monkeypatch):
    from mvp import ytinfo
    add_items(env, [{"id": "itm_v", "platform": "youtube", "source_url": "https://www.youtube.com/watch?v=MOTvid00001",
                     "caption": "Motion design for beginners", "interaction_kinds": ["watch"],
                     "platform_data": {"video_id": "MOTvid00001", "owner_name": "Motion School",
                                       "owner_relation": "none"}}])
    env["bot"].pool.search = lambda lib, q, depth=300: {"ids": ["itm_v"], "mode": "normal", "cost_usd": 0.0}
    desc = ("This motion design tutorial teach how to create basic, beginner level motion graphics in under 20 "
            "minutes with shapes, keyframes and easing, so you can follow along from the very first frame today")
    monkeypatch.setattr(ytinfo, "fetch_batch", lambda ids, key, timeout=None: {"items": [
        {"id": ids[0], "snippet": {"description": desc}, "contentDetails": {"duration": "PT18M"}}]})
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    st = env["state"]
    st["answers"]["mvp_compose"] = lambda u: {"picks": [{"n": 1, "verdict": "clear", "title": "Motion design for beginners"}]}
    st["answers"]["mvp_extract"] = lambda u: {"steps": [desc]}
    msg = say(env, "a motion design tutorial", ask_form("a motion design tutorial", ["motion design tutorial"]))
    assert "Steps" not in msg and "teach how to create" not in msg and "…" not in msg


# ======================================= 75. outside picks nobody asked for =======================================
from mvp.tests.test_slice5 import outside_ask  # noqa: E402


def lemon_clear(u):
    return {"picks": [{"n": number_of(u, "Lemon garlic"), "verdict": "clear", "title": "Lemon garlic pasta"}],
            "intro": "Here's a pasta recipe."}


def test_75_outside_some_without_an_ask_for_new_things_is_none(yt):
    yt["state"]["answers"]["mvp_compose"] = lemon_clear
    msg = str(say(yt, "a pasta recipe", outside_ask()))
    assert "Not from your saves" not in msg and "YouTube" not in msg
    assert not yt["yt"].searches()
    # the message asks for new ones: the block comes
    msg = str(say(yt, "a pasta recipe, and some new ones", outside_ask()))
    assert "Not from your saves, but close to them:" in msg and yt["yt"].searches()


def test_75_the_line_about_telling_me_what_kind_follows_only_an_ask_for_new_things(yt):
    yt["state"]["answers"]["mvp_compose"] = lemon_clear
    form = ask_form("something to cook tonight", ["cook tonight"], outside="some")
    msg = str(say(yt, "what should I cook tonight?", form))
    assert "Tell me what kind of thing you want" not in msg and not yt["yt"].searches()


@pytest.mark.parametrize("text,want", [
    ("mini blender tutorials to start doing daily", "none"),
    ("every 2 days send me a calisthenics workout at a random time", "none"),
    ("when I say boost, send me a motion design tutorial", "none"),
    ("I'm new to Blender, send me a tutorial", "none"),
    ("anything new like these?", "some"),
    ("find me new sourdough videos, not just stuff i already saved", "some"),
    ("every sunday send me something new close to my blender saves", "some"),
    ("more like these please", "some"),
    ("only new watercolor stuff pls, not from my saves", "only"),
])
def test_75_outside_is_kept_only_when_the_message_asks_for_new_things(text, want):
    from mvp.interpret import profile_guard
    from mvp.schema import Interpretation
    it = Interpretation.model_validate(ask_form("x things", ["x"], outside="only" if want == "only" else "some"))
    assert profile_guard(it, text, {"prefs": {}}).spec.content.outside == want
    # their profile says they want new things too: kept
    it = Interpretation.model_validate(ask_form("x things", ["x"], outside="some"))
    assert profile_guard(it, text, {"prefs": {"outside": True}}).spec.content.outside == "some"


def test_75_the_export_reminders_are_listed_to_the_model_by_their_short_names(env):
    from datetime import datetime, timezone
    from mvp.interpret import _context
    from mvp.refresh import reminder_spec
    now = datetime(2026, 11, 13, 3, 0, tzinfo=timezone.utc)
    rules = [{"id": i, "status": "active", "created_at": now.isoformat(), "spec": reminder_spec(p, now, "America/New_York").stored()}
             for i, p in enumerate(("instagram", "youtube"), 1)]
    ctx = _context({"timezone": "America/New_York", "handle": H}, rules, None, None, now)
    assert "Instagram export reminder" in ctx and "YouTube export reminder" in ctx
    for word in ("Takeout", "history", "Likes", "fresh", "playlists"):
        assert word not in ctx, word


def test_75_a_change_to_an_export_reminder_keeps_its_own_words(env):
    from datetime import datetime, timezone
    from mvp.refresh import REMINDER_OPENING, reminder_message, reminder_spec
    bot = env["bot"]
    now = datetime(2026, 11, 12, 18, 0, tzinfo=timezone.utc)
    spec = reminder_spec("youtube", now, "America/New_York").stored()
    bot.store.add_rule(H, "export reminders (youtube)", spec, "active", None, created_at=now.isoformat())
    changed = json.loads(json.dumps(spec))
    changed["content"]["text"] = "YouTube export reminder"
    changed["when"]["times"] = ["09:00"]
    say(env, "move the youtube export reminder to 9am", {"intent": "change_rule", "rule_number": 1, "spec": changed})
    stored = bot.store.rules(H)[0]["spec"]
    assert stored["when"]["times"] == ["09:00"]
    assert stored["content"]["text"].startswith(REMINDER_OPENING["youtube"])
    assert reminder_message(stored["content"]["text"]).startswith(REMINDER_OPENING["youtube"])


# ======================================= 76. a level from another topic =======================================
BLENDER_LEVEL = [{"topic": "Blender 3D", "level": "beginner", "confirmed": True, "words": ["blender"]},
                 {"topic": "2D animation", "level": "intermediate", "confirmed": True, "words": ["animation"]},
                 {"topic": "Calisthenics", "confirmed": True, "words": ["calisthenics"]}]


@pytest.mark.parametrize("text,crit,want", [
    ("every 2 days send me a calisthenics workout at a random time", "for a beginner", []),
    ("when I say boost, send me a motion design tutorial", "suits a beginner", []),
    # checker: the profile's level for the request's own topic is a preference for the composer, never a must-have
    # (it opened a live answer with "I couldn't confirm ... suits a beginner"); the composer still gets it
    ("mini blender tutorials to start doing daily", "suits a beginner", []),
    ("a 2d animation exercise for today", "suits a beginner", []),
    ("a beginner calisthenics workout", "suits a beginner", ["suits a beginner"]),
])
def test_76_a_level_comes_from_the_message_or_the_profile_for_the_same_topic(text, crit, want):
    from mvp.interpret import profile_guard
    from mvp.schema import Interpretation
    it = Interpretation.model_validate(ask_form("some things", ["things"], [crit, "ends with a finished result"]))
    out = profile_guard(it, text, {"prefs": {}, "interests": BLENDER_LEVEL})
    assert [c for c in out.spec.content.criteria if "finished" not in c] == want


def test_76_a_level_from_another_rule_never_reaches_the_stored_rule(rich):
    bot = rich["bot"]
    from mvp import profile as P
    P.set_interests(bot.store, H, BLENDER_LEVEL)
    rich["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": 1, "verdict": "clear", "title": "A routine", "criteria": [{"answer": "yes", "quote": "Blender"}] * 2}]}
    say(rich, "every 2 days send me a calisthenics workout at a random time",
        rule_form("a calisthenics workout", ["calisthenics workout"], ["for a beginner", "a full routine from start to finish"]))
    say(rich, "yes", {"intent": "confirm"})
    spec = bot.store.rules(H)[-1]["spec"]
    assert spec["content"]["criteria"] == ["a full routine from start to finish"]


# ======================================= 82. source limits nobody asked for =======================================
@pytest.mark.parametrize("text,kinds,platforms", [
    ("mini blender tutorials to start doing daily", [], []),
    ("every 2 days send me a calisthenics workout at a random time", [], []),
    ("the study tips vids i watched on yt, key points only", ["watch", "like", "playlist"], ["youtube"]),
    ("show me reels i saved about japan travel", ["save", "collection", "share_self", "playlist"], ["instagram"]),
    ("every other day at 7 a guitar lesson from my youtube", [], ["youtube"]),
    ("random outfit idea from my saves", ["save", "collection", "share_self", "playlist"], []),
])
def test_82_kinds_and_platforms_are_limited_only_when_the_message_says_so(text, kinds, platforms):
    from mvp.interpret import profile_guard
    from mvp.schema import Interpretation
    it = Interpretation.model_validate(ask_form("some things", ["things"], kinds=kinds or ["watch", "like", "playlist"],
                                                platforms=platforms or ["youtube"]))
    out = profile_guard(it, text, {"prefs": {}})
    assert out.spec.content.kinds == kinds and out.spec.content.platforms == platforms


def test_82_the_guard_keeps_every_limit_the_development_files_expect():
    """Every development case that expects a kinds, platforms or outside value says so in its own words, so the guard
    after the interpreter never undoes an expected value (the guard and the cases agree, case by case)."""
    from mvp.interpret import KINDS_ASKED, OUTSIDE_ASKED, PLATFORMS_ASKED
    here = os.path.join(os.path.dirname(HERE), "evalset")
    n = 0
    for name in ("rules_dev_timing.jsonl", "rules_dev_content.jsonl", "rules_dev_extra.jsonl"):
        for line in open(os.path.join(here, name), encoding="utf-8"):
            if not line.strip():
                continue
            case = json.loads(line)
            content = (case["expect"].get("content") or {})
            if content.get("outside") in ("some", "only"):
                assert OUTSIDE_ASKED.search(case["text"]), case["id"]
                n += 1
            if content.get("kinds"):
                assert KINDS_ASKED.search(case["text"]), case["id"]
                n += 1
            if content.get("platforms"):
                assert PLATFORMS_ASKED.search(case["text"]), case["id"]
                n += 1
    assert n >= 9


# ======================================= 83. wording =======================================
def test_83_my_rules_lists_the_export_reminders_by_a_short_name(env):
    from datetime import datetime, timezone
    from mvp.refresh import reminder_spec
    bot = env["bot"]
    now = datetime(2026, 11, 12, 18, 0, tzinfo=timezone.utc)
    for p in ("instagram", "youtube"):
        bot.store.add_rule(H, f"export reminders ({p})", reminder_spec(p, now, "America/New_York").stored(), "active",
                           None, created_at=now.isoformat())
    bot.on_message(H, "my rules")
    msg = last(env["ch"])
    assert "Instagram export reminder" in msg and "YouTube export reminder" in msg
    assert "takeout.google.com" not in msg and "accountscenter" not in msg


# ======================================= 77. "will run dry" on a topic with many saves =======================================
DINNERS = [{"id": f"itm_q{i}", "platform": "instagram", "source_url": f"https://example.com/q{i}",
            "caption": f"{name}, a quick dinner\nIngredients:\n- 2 cups rice\n- 1 tbsp oil\nBake for 20 minutes",
            "interaction_kinds": ["save"], "platform_data": {"owner_handle": "chef", "owner_relation": "following"}}
           for i, name in enumerate(["Sheet pan chicken", "Veggie fried rice", "Baked salmon", "Bean chili",
                                     "Lemon chicken", "Tofu bowl"])]
DINNER_RULE = rule_form("a quick dinner idea", ["quick dinner", "easy dinner recipe"], ["ends with a dish you can eat"],
                        when={"type": "random", "per": "week", "count": 2})


def one_dinner(u):
    return {"picks": [{"n": number_of(u, "Sheet pan chicken"), "verdict": "clear", "title": "Sheet pan chicken",
                       "criteria": [{"answer": "yes", "quote": "Bake for 20 minutes"}]}]}


def test_77_a_rule_on_a_topic_with_many_saves_gets_no_run_dry_warning(yt):
    add_items(yt, [dict(r) for r in DINNERS])
    yt["bot"].pool.search = lambda lib, q, depth=300: {"ids": [r["id"] for r in DINNERS], "mode": "normal",
                                                       "cost_usd": 0.0}
    yt["state"]["answers"]["mvp_compose"] = one_dinner
    msg = str(say(yt, "randomly surprise me with a quick dinner idea a couple of times a week", DINNER_RULE))
    assert "Sheet pan chicken" in msg and "Reply YES to start" in msg
    assert "run dry" not in msg and "Heads up" not in msg and "outside your saves" not in msg


def test_77_a_tiny_supply_still_gets_the_warning(yt):
    add_items(yt, [dict(r) for r in DINNERS[:2]])
    yt["bot"].pool.search = lambda lib, q, depth=300: {"ids": [r["id"] for r in DINNERS[:2]], "mode": "normal",
                                                       "cost_usd": 0.0}
    yt["state"]["answers"]["mvp_compose"] = one_dinner
    msg = str(say(yt, "randomly surprise me with a quick dinner idea a couple of times a week", DINNER_RULE))
    assert "Heads up: I only see about 2 posts in your library that fit, so this will run dry quickly." in msg


def test_77_a_rule_with_new_videos_says_where_picks_come_from_and_never_run_dry(yt):
    yt["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": number_of(u, "Lemon garlic"), "verdict": "clear", "title": "Lemon garlic pasta"}]}
    form = rule_form("a pasta recipe", ["pasta recipe"], when={"type": "schedule", "days": ["FRI"], "times": ["19:00"]},
                     outside="some")
    msg = str(say(yt, "every friday a pasta recipe, and new ones from youtube too", form))
    assert "Picks come from your saves, with related videos from YouTube as well, so it won't run dry." in msg
    assert "run dry quickly" not in msg and "Heads up" not in msg
    msg = str(say(yt, "yes", {"intent": "confirm"}))
    assert "Picks come from your saves, with related videos from YouTube as well" in msg
    assert yt["bot"].store.rules(H)[-1]["spec"]["content"]["outside"] == "some"


# ======================================= 78. "the ingredients" after a lead pick and one close one ====================
def test_78_the_ingredients_of_the_lead_pick_after_a_closest_answer_with_one_more(env):
    from mvp.tests.test_mvp import pasta_spec
    bot, st = env["bot"], env["state"]
    st["answers"]["mvp_compose"] = lambda u: {"picks": [   # nothing clear: the closest and one more close
        {"n": number_of(u, "Lemon garlic"), "verdict": "close", "title": "Lemon garlic pasta",
         "lines": ["200g spaghetti", "2 lemons"]},
        {"n": number_of(u, "Pasta night"), "verdict": "close", "title": "Pasta night"}]}
    spec = pasta_spec({"type": "now"})
    spec["content"]["count"] = 2
    msg = say(env, "a lemon pasta recipe", {"intent": "ask", "spec": spec})
    assert "The closest I have is Lemon garlic pasta" in msg and "Or these, which are close too:" in msg
    msg = say(env, "email it to me and add the ingredients to my grocery list",
              {"intent": "act_on_last", "actions": ["email.send", {"action": "todo.add", "params": {"list": "grocery"}}]})
    assert "Which one?" not in msg
    assert [t["text"] for t in bot.store.todos(H)] == ["200g spaghetti", "2 lemons"]


def test_78_equals_with_no_details_shown_still_ask_which_one(env):
    from mvp.tests.test_mvp import pasta_spec
    st = env["state"]
    st["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": number_of(u, "Pasta night"), "verdict": "clear", "title": "Pasta night"},
        {"n": number_of(u, "Lemon garlic"), "verdict": "clear", "title": "Lemon garlic pasta",
         "lines": ["200g spaghetti", "2 lemons"]}]}
    st["answers"]["mvp_extract"] = lambda u: {}
    spec = pasta_spec({"type": "now"})
    spec["content"]["count"], spec["content"]["extract"] = 2, []
    say(env, "two pasta posts", {"intent": "ask", "spec": spec})
    msg = say(env, "add the ingredients to my grocery list", {"intent": "todo_add", "what": "ingredients",
                                                               "list": "grocery"})
    assert "Which one?" in msg


# ======================================= 79. two copies by one creator; the fuller one leads ===========================
POOR = {"id": "itm_p1", "platform": "instagram", "source_url": "https://example.com/p1",
        "caption": "Chicken rice bowl! The recipe is in the video, save it for later",
        "interaction_kinds": ["save"], "platform_data": {"owner_handle": "bowlchef", "owner_relation": "none"}}
FULL = {"id": "itm_p2", "platform": "instagram", "source_url": "https://example.com/p2",
        "caption": "My chicken rice bowl\nIngredients:\n- 2 cups rice\n- 1 tbsp oil\n- 300g chicken\nSteps:\n"
                   "1. Cook the rice\n2. Fry the chicken in the oil",
        "interaction_kinds": ["save"], "platform_data": {"owner_handle": "bowlchef", "owner_relation": "none"}}
OTHER = dict(FULL, id="itm_p3", source_url="https://example.com/p3",
             caption=FULL["caption"].replace("My chicken rice bowl", "Sesame chicken and rice"),
             platform_data={"owner_handle": "ricecook", "owner_relation": "none"})


def bowls(env, items, picks):
    add_items(env, [dict(i) for i in items])
    env["bot"].pool.search = lambda lib, q, depth=300: {"ids": [i["id"] for i in items], "mode": "normal",
                                                        "cost_usd": 0.0}
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": number_of(u, needle), "verdict": "clear", "title": title} for needle, title in picks]}
    env["state"]["answers"]["mvp_extract"] = lambda u: (
        {"ingredients": ["2 cups rice", "1 tbsp oil", "300g chicken"], "steps": ["Cook the rice", "Fry the chicken in the oil"]}
        if "300g chicken" in u else {"ingredients": [], "steps": []})


def test_79_two_posts_with_the_same_title_by_one_creator_are_one_pick_and_the_fuller_one_is_kept(env):
    bowls(env, [POOR, FULL], [("The recipe is in the video", "Chicken rice bowl"), ("300g chicken", "Chicken rice bowl")])
    msg = say(env, "a chicken rice bowl recipe", ask_form("a chicken rice bowl recipe", ["chicken rice bowl"]))
    assert "example.com/p2" in msg and "example.com/p1" not in msg
    assert "Ingredients (3):" in msg and "Steps (2):" in msg and "in the video" not in msg


def test_79_among_picks_with_the_same_verdict_the_one_with_written_details_leads(env):
    poor = dict(POOR, platform_data={"owner_handle": "bowlfan", "owner_relation": "none"})
    bowls(env, [poor, OTHER], [("The recipe is in the video", "Chicken rice bowl"), ("Sesame", "Sesame chicken and rice")])
    msg = say(env, "chicken and rice recipes", ask_form("chicken and rice recipes", ["chicken and rice"]))
    assert "I recommend Sesame chicken and rice" in msg and "Ingredients (3):" in msg
    assert msg.index("example.com/p3") < msg.index("example.com/p1")   # the poorer one is still offered, after it


def test_83_the_guessed_direction_uses_a_verb_that_fits_any_topic_and_writes_2d_as_2D():
    from mvp import profile as P

    def g(topic, doing, level=None):
        return {"topic": topic, "doing": doing, "level": level, "source": "guess"}
    assert P.direction_guess([g("motion design", "making"), g("2d animation", "making")]) == \
        "into motion design and 2D animation"
    assert P.direction_guess([g("Blender 3D", "learning", "beginner"), g("2d animation", "making")]) == \
        "learning Blender 3D and into 2D animation"
    assert P.read_lines({"interests": [{"topic": "2d animation", "saved": 12}], "prefs": {}}) == \
        ["• 2D animation (12 saved)"]


def test_74_a_reason_names_the_kit_or_the_usual_time_only_when_the_post_says_it(env):
    bot, st = env["bot"], env["state"]
    with_profile(bot, note=None)
    st["answers"]["mvp_compose"] = lambda u: {"picks": [{
        "n": number_of(u, "Lemon garlic"), "verdict": "clear", "title": "Lemon garlic pasta",
        "because": "it suits your weeknights and needs only an Instant Pot",
        "facts": [{"label": "pasta", "quote": "Lemon garlic pasta"}]}]}
    msg = say(env, "a pasta recipe", ask_form("a pasta recipe", ["pasta recipe"]))
    assert "Instant Pot" not in msg and "weeknight" not in msg and "I recommend Lemon garlic pasta" in msg
    from mvp.executor import pref_backed
    assert pref_backed("it takes 20 minutes in an Instant Pot", "Instant Pot chicken, 20 minutes", ["Instant Pot"],
                       "20 minutes on weeknights")
    assert pref_backed("it has lemon and garlic", "Lemon garlic pasta", ["Instant Pot"], "20 minutes on weeknights")


def test_80_a_pick_still_the_closest_for_its_length_never_says_it_is_not_a_whole_project():
    from mvp.executor import finished_by_details
    from mvp.libview import Item
    from mvp.schema import RuleSpec
    spec = RuleSpec.model_validate({"when": {"type": "now"}, "content": {
        "goal": "mini blender tutorials", "searches": ["blender tutorial"],
        "criteria": ["walks through one whole project from start to finish"]}})
    it = Item({"id": "b", "platform": "instagram", "source_url": "https://example.com/b",
               "caption": "Blender donut tutorial, step by step", "interaction_kinds": ["save"],
               "platform_data": {"owner_handle": "maker"}})
    fin = spec.content.criteria[0]
    p = {"item": it, "verdict": "close", "criteria": ["no"], "too_long": True,
         "facts": {"steps": ["Add a torus", "Shape the icing"]}}
    result = {"picks": [p], "wider": [], "closest": True, "missing": [(fin, "no"), ("under 10 minutes", "no")],
              "dropped": {}, "n_clear": 0, "n_close": 1, "extract": ["steps"]}
    finished_by_details(result, spec, {})
    assert p["verdict"] == "close" and result["closest"] and result["missing"] == [("under 10 minutes", "no")]


def test_74_a_title_never_names_their_kit_when_the_post_does_not(env):
    bot, st = env["bot"], env["state"]
    with_profile(bot, note=None)
    st["answers"]["mvp_compose"] = lambda u: {"picks": [{
        "n": number_of(u, "Lemon garlic"), "verdict": "clear", "title": "Instant Pot lemon garlic pasta"}]}
    msg = say(env, "a pasta recipe", ask_form("a pasta recipe", ["pasta recipe"]))
    assert "Instant Pot" not in msg and "I recommend Lemon garlic pasta" in msg


# ======================================= checker of fix pass 4: near-variants =======================================
FULL_PROFILE = {"prefs": {"tools": ["Instant Pot"], "time": "usually has 20 minutes on weeknights", "avoid": ["mushroom"]},
        "notes": ["I usually cook for two people", "trying to eat more vegetables"],
        "direction": "making short 3D animations",
        "interests": [{"topic": "Blender 3D", "level": "beginner", "confirmed": True, "words": ["blender"]},
                      {"topic": "Calisthenics", "confirmed": True, "words": ["calisthenics"]}]}


def guarded(text, criteria, prof=FULL_PROFILE, **content):
    from mvp.interpret import profile_guard
    from mvp.schema import Interpretation
    it = Interpretation.model_validate(ask_form("some things", ["things"], criteria, **content))
    return profile_guard(it, text, json.loads(json.dumps(prof))).spec.content


@pytest.mark.parametrize("text,crit,kept", [
    ("chicken and rice", "pressure cooker friendly", False),        # their kit in other words
    ("chicken and rice", "under half an hour", False),              # their usual time in other units
    ("chicken and rice", "weeknight-fast", False),
    ("pasta in my pressure cooker", "uses an Instant Pot", True),   # the message names their kit
    ("something for my Instant Pot", "uses an Instant Pot", True),
    ("dinner in under half an hour", "under 30 minutes", True),     # the message gives a length of its own
    ("a quick dinner for a weeknight", "for weeknights", True),
    ("a quick pasta dinner", "quick to cook", True),                # shares "cook" with a note, "quick" with the message
    ("a veggie pasta", "has vegetables", True),
    ("chicken and rice", "serves two", False),                      # restates a note
    ("a blender tutorial", "helps make short 3D animations", False),  # restates the direction
])
def test_checker_74_the_profile_in_other_words_is_a_preference_and_the_message_wins(text, crit, kept):
    assert (crit in guarded(text, [crit]).criteria) is kept


def test_checker_74_an_avoid_entry_restated_as_a_must_have_is_a_hard_limit():
    c = guarded("chicken and rice", ["mushroom-free"])
    assert c.criteria == [] and "mushroom" in c.avoid
    c = guarded("chicken and rice, no mushrooms", ["no mushrooms"])   # said in the message: kept as said
    assert c.criteria == ["no mushrooms"]


@pytest.mark.parametrize("text,crit,want", [
    ("an easy dinner my kids will eat", "kid-friendly", ["kid-friendly"]),
    ("an easy dinner", "kid-friendly", []),
    ("mini blender tutorials", "suits a beginner", []),
    ("a beginner blender tutorial", "suits a beginner", ["suits a beginner"]),
])
def test_checker_76_a_level_must_have_only_from_the_message(text, crit, want):
    assert guarded(text, [crit]).criteria == want


def test_checker_76_the_composer_still_gets_the_level_for_the_requests_topic(env):
    from mvp import profile as P
    bot = env["bot"]
    P.set_interests(bot.store, H, FULL_PROFILE["interests"])
    text, level_ok, _ = P.composer_context(bot.store, H, "mini blender tutorials")
    assert "Their level at Blender 3D: a beginner" in text and level_ok
    text, _, _ = P.composer_context(bot.store, H, "a calisthenics workout")
    assert "Their level" not in text


@pytest.mark.parametrize("text,want", [
    ("fresh pasta recipes", "none"), ("an outside workout", "none"), ("a blender tutorial beyond the basics", "none"),
    ("send me my newest saves", "none"), ("pasta recipes, stuff that's new to me", "some"),
    ("show me new ones too", "some"), ("something fresh to cook", "some"),
])
def test_checker_75_outside_words_that_do_not_ask_for_new_things(text, want):
    assert guarded(text, [], prof={"prefs": {}}, outside="some").outside == want


def test_checker_75_no_line_about_new_ones_when_the_message_did_not_ask(yt):
    yt["bot"].store.set_prefs(H, outside=True)   # their profile turns new picks on: they still come when they can
    yt["state"]["answers"]["mvp_compose"] = lemon_clear
    form = ask_form("something to cook tonight", ["cook tonight"], outside="some")
    msg = str(say(yt, "what should I cook tonight?", form))
    assert "I recommend Lemon garlic pasta" in msg and "Tell me what kind of thing you want" not in msg
    msg = str(say(yt, "what should I cook tonight? show me new ones too", form))   # asked: the line comes
    assert "Tell me what kind of thing you want" in msg


@pytest.mark.parametrize("text,kept", [
    ("I'd like a quick workout", False), ("something to watch tonight", False), ("a recipe to save time", False),
    ("only from my likes", True), ("videos I watched about blender", True), ("from my saves", True),
])
def test_checker_82_like_watch_and_save_as_plain_verbs_name_no_kind(text, kept):
    c = guarded(text, [], prof={"prefs": {}}, kinds=["watch", "like", "playlist"])
    assert bool(c.kinds) is kept


def _lead_and_one_more(env):
    from mvp.tests.test_mvp import pasta_spec
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": number_of(u, "Lemon garlic"), "verdict": "clear", "title": "Lemon garlic pasta",
         "lines": ["200g spaghetti", "2 lemons"]},
        {"n": number_of(u, "Pasta night"), "verdict": "clear", "title": "Pasta night"}]}
    spec = pasta_spec({"type": "now"})
    spec["content"]["count"] = 2
    msg = say(env, "two pasta recipes", {"intent": "ask", "spec": spec})
    assert "I recommend Lemon garlic pasta" in msg and "Or try these:" in msg


def test_checker_78_add_it_to_my_list_after_a_lead_pick_adds_the_lead(env):
    bot = env["bot"]
    _lead_and_one_more(env)
    msg = say(env, "add it to my to-do list", {"intent": "act_on_last", "actions": [{"action": "todo.add"}]})
    assert [t["text"] for t in bot.store.todos(H)] == ["Lemon garlic pasta"], msg
    for t in bot.store.todos(H):
        bot.store.x("DELETE FROM todos WHERE id=?", (t["id"],))
    say(env, "add them both to my to-do list", {"intent": "act_on_last", "actions": [{"action": "todo.add"}]})
    assert [t["text"] for t in bot.store.todos(H)] == ["Lemon garlic pasta", "Pasta night"]


def test_checker_78_remind_me_of_it_later_is_the_lead_pick(env):
    _lead_and_one_more(env)
    msg = say(env, "remind me of it tonight at 8", {"intent": "act_on_last", "actions": ["message.send"],
                                                    "when": {"type": "once", "date": "2026-11-12", "time": "20:00"}})
    assert '"Lemon garlic pasta"' in msg and "2 picks" not in msg
