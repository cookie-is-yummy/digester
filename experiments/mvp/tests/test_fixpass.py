"""Offline tests for the fix pass after the live run on the real library (12 Nov): one or more tests per finding
(findings 1 to 37 of the fix-pass list), each failing without its fix. Synthetic data, a fake model, a fake search
pool, a fake YouTube and a fake clock only; the fixtures come from the earlier test files."""
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import compose_picks, env, last, pasta_spec  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, ask_pasta, lemon_pick, note_spec, say  # noqa: E402
from mvp.tests.test_slice3 import add_items, ask, compose_once, yt_item  # noqa: E402
from mvp.tests.test_slice5 import (KEY, drop, fresh, standard_fake, yt, zip_dir, FIX_YT,  # noqa: E402,F401
                                   outside_ask)
from mvp.tests.test_slice6 import number_of, pick, rich  # noqa: E402,F401

UTC = timezone.utc
INTERNAL = ("candidates", "because I recommend", "because it matches what you asked for", ".”.", "Why:")


def num(user, needle):
    """The candidate number of the item whose text (which may run over several lines) holds `needle`."""
    import re
    for m in re.finditer(r"^(\d+)\. [^\n]*\n<item>(.*?)</item>", user, re.M | re.S):
        if needle.lower() in m.group(2).lower():
            return int(m.group(1))
    raise AssertionError(f"{needle} is not a candidate")


def interp_calls(e):
    return e["calls"].count("mvp_interpret")


def text_of(reply):
    return str(reply)


def clean(reply):
    """Nothing internal, invented or doubled reaches the person (findings 5, 7, 9, 10, 37)."""
    t = text_of(reply)
    return not any(x in t for x in INTERNAL)


# ---------- A. the wrong action taken ----------
def test_1_plain_commands_are_read_by_code_before_any_model_call(env):
    bot, ch = env["bot"], env["ch"]
    for t in ("stretch", "drink water"):
        say(env, f"every monday at 9 remind me to {t}", {"intent": "new_rule", "spec": note_spec(
            {"type": "schedule", "days": ["MON"], "times": ["09:00"]}, t)})
    n = interp_calls(env)
    env["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "skip", "rule_number": 2}   # the live misreading
    bot.on_message(H, "Stop 2.")
    rules = bot.store.rules(H, statuses=("active", "paused", "stopped"))
    assert rules[1]["status"] == "stopped" and rules[0]["status"] == "active"
    assert last(ch).startswith("Stopped: ") and "Skipped" not in last(ch)
    bot.on_message(H, "pause 1")
    assert bot.store.rules(H)[0]["status"] == "paused" and last(ch).startswith("Paused: ")
    bot.on_message(H, "RESUME 1!")
    assert bot.store.rules(H)[0]["status"] == "active"
    bot.on_message(H, "my rules")
    assert last(ch).startswith("Your rules:")
    bot.on_message(H, "undo")
    assert last(ch).startswith("Undone:") and bot.store.rules(H)[0]["status"] == "paused"
    bot.on_message(H, "help?")
    assert last(ch).startswith("I find things in what you've saved")
    bot.on_message(H, "skip 9")
    assert last(ch).startswith("Which rule?")
    assert interp_calls(env) == n                                          # not one model call
    say(env, "add basil to my list", {"intent": "todo_add", "todo_text": "basil"})
    n = interp_calls(env)
    bot.on_message(H, "done 1")
    assert last(ch).startswith("Done: basil") and interp_calls(env) == n
    say(env, "stop 1 please, it's too much", {"intent": "chat", "reply": "OK."})   # anything longer: the model
    assert interp_calls(env) == n + 1


def test_2_another_is_more_with_the_last_spec_and_filler_is_never_a_must_have(env):
    bot = env["bot"]
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": number_of(u, "Lemon garlic"), "verdict": "clear", "title": "Lemon garlic pasta"}]}
    say(env, "a pasta recipe", ask())
    first = bot.store.last_answer(H)["items"]
    n = interp_calls(env)
    env["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "more", "criteria": ["another"]}
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": number_of(u, "Pasta night"), "verdict": "clear", "title": "Pasta night",
         "criteria": [{"answer": "unknown"} for _ in range(5)]}]}
    for word in ("another", "One more", "next", "more please"):
        bot.on_message(H, word)
        msg = last(env["ch"])
        assert interp_calls(env) == n and "meets" not in msg and "another" not in msg.lower()
    assert bot.store.last_answer(H)["items"] != first
    spec = bot.store.get_state(f"lastspec:{H}")["spec"]
    assert not spec["content"].get("criteria")                            # the last spec unchanged
    # a longer message goes to the model; a must-have of its filler words is dropped by code
    msg = say(env, "can I get another one like that?", {"intent": "more", "criteria": ["another one", "different"]})
    assert "meets" not in msg and "couldn't confirm" not in msg
    from mvp.interpret import clean_criteria
    assert clean_criteria(["another", "something different", "no oven"]) == ["no oven"]


def test_3_two_things_go_on_the_grocery_list_and_the_list_name_is_never_in_the_text(env):
    bot = env["bot"]
    msg = say(env, "add oat milk and eggs to my grocery list",
              {"intent": "todo_add", "todo_text": "oat milk and eggs to my grocery list"})
    todos = bot.store.todos(H)
    assert [(t["text"], t["list"]) for t in todos] == [("oat milk", "grocery"), ("eggs", "grocery")]
    assert msg == "Added 2 things to your grocery list: oat milk; eggs."
    say(env, "undo", {"intent": "undo"})
    assert bot.store.todos(H) == []                                        # one write, undone whole
    say(env, "add mac and cheese", {"intent": "todo_add", "todo_text": "mac and cheese"})
    say(env, "add call mum and dad", {"intent": "todo_add", "todo_text": "call mum and dad"})
    assert [t["text"] for t in bot.store.todos(H)] == ["mac and cheese", "call mum and dad"]


def _recipe_with_steps(env):
    env["state"]["answers"]["mvp_extract"] = lambda u: {"ingredients": ["200g spaghetti", "2 lemons"],
                                                        "steps": ["4 cloves garlic", "Lemon garlic pasta"]}
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": number_of(u, "Lemon garlic"), "verdict": "clear", "title": "Lemon garlic pasta"},
        {"n": number_of(u, "Pasta night"), "verdict": "clear", "title": "Pasta night"}]}


def test_4_steps_of_a_shown_pick_are_answered_directly_never_with_i_recommend(env):
    bot = env["bot"]
    _recipe_with_steps(env)
    msg = say(env, "pasta recipes with the ingredients and steps", ask(extract=["ingredients", "steps"], count=2))
    assert "Steps (2):\n1. 4 cloves garlic" in msg
    n, c = interp_calls(env), env["calls"].count("mvp_compose")
    bot.on_message(H, "what are the steps for the first one?")
    msg = last(env["ch"])
    assert msg.startswith("Here are the steps of Lemon garlic pasta by @chef:\n1. 4 cloves garlic")
    assert "I recommend" not in msg and interp_calls(env) == n and env["calls"].count("mvp_compose") == c
    # the second pick never had its details read: the details step runs now, on its whole text; nothing is written
    # out in it, so one honest line and the post's link
    env["state"]["answers"]["mvp_extract"] = lambda u: {"steps": []}
    bot.on_message(H, "and the steps of the second one?")
    msg = last(env["ch"])
    assert msg.startswith("Pasta night by @chef doesn't write out the steps; they're in the video. Here's the post:")
    assert msg.endswith("https://example.com/itm_c") and "I recommend" not in msg
    # the model's follow_up form takes the same path
    msg = say(env, "how do I make it?", {"intent": "follow_up", "question": "How do I make the lemon pasta?",
                                         "pick_number": 1})
    assert msg.startswith("Here are the steps of Lemon garlic pasta") and "I recommend" not in msg


def test_5_key_points_of_a_youtube_pick_use_its_description_and_nothing_internal_is_shown(env, monkeypatch):
    from mvp import ytinfo
    add_items(env, [yt_item(iid="itm_y", vid="SYNvid00001", title="Study with me: how I learn fast")])
    env["bot"].pool.search = lambda lib, q, depth=300: {"ids": ["itm_y", "itm_a"], "mode": "normal", "cost_usd": 0.0}
    desc = {"v": "Key ideas:\n- Space your reviews\n- Test yourself before you reread"}
    monkeypatch.setattr(ytinfo, "fetch_batch", lambda ids, key, timeout=None: {"items": [
        {"id": ids[0], "snippet": {"description": desc["v"]}, "contentDetails": {"duration": "PT12M"}}]})
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    rule = {"intent": "new_rule", "spec": {"when": {"type": "schedule", "days": ["MON"], "times": ["08:00"]},
                                           "content": {"goal": "a study video", "searches": ["study"]}}}
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": num(u, "Study with me"), "verdict": "clear", "title": "Study with me"}],
        "none_reason": "The candidates only show titles"}
    say(env, "a study video every monday", rule)                         # a preview: its pick is the last answer
    env["state"]["answers"]["mvp_extract"] = lambda u: (
        {"key_points": ["Space your reviews", "Test yourself before you reread"]} if "Space your" in u else {})
    env["bot"].on_message(H, "what are the key points of that study video?")
    msg = last(env["ch"])
    assert msg.startswith("Here are the key points of Study with me by Synthetic Channel:\n• Space your reviews") and clean(msg)
    # a description that does not list them: one honest line, then the video
    env["bot"].store.x("DELETE FROM facts")
    env["bot"].store.x("DELETE FROM youtube_cache")
    env["bot"].store.set_state(f"facts:{H}", {})
    desc["v"] = "Thanks for watching!"
    env["bot"].on_message(H, "what are the key points of that video?")
    msg = last(env["ch"])
    assert msg.startswith("The description of Study with me by Synthetic Channel doesn't list the key points, so I can't quote them. "
                          "Here's the video:") and msg.endswith("watch?v=SYNvid00001") and clean(msg)
    # the composer's none_reason never reaches the person: code picks the sentence
    msg = compose_once(env, {"picks": [], "none_reason": "The candidates only show titles"})
    assert msg == "I didn't find a good match: nothing in your library fits well." and clean(msg)


def test_6_too_hard_something_shorter_records_it_and_sends_one_now(rich):
    bot, st = rich["bot"], rich["state"]
    st["answers"]["mvp_compose"] = pick("Low poly island")
    say(rich, "a blender tutorial", {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {
        "goal": "a Blender tutorial", "searches": ["blender tutorial"]}}})
    seen = []
    st["answers"]["mvp_compose"] = lambda u: (seen.append(u), pick("cosy room")(u))[1]
    msg = say(rich, "too hard, something shorter", {"intent": "feedback", "feedback": "easier",
                                                     "also": {"intent": "more", "criteria": ["shorter"]}})
    assert msg.startswith("Noted. Here's a shorter, easier one:") or msg.startswith("Noted, I'll keep it simpler")
    assert "Here's a shorter, easier one:" in msg and "cosy room" in msg and "Ask for" not in msg
    assert bot.store.one("SELECT kind FROM feedback ORDER BY id DESC LIMIT 1")["kind"] == "easier"
    # "shorter" is the length bound worked out by code (fix pass 2, finding 49), never a must-have
    assert len(seen) == 1 and '"order": "easiest_first"' in seen[0] and '"criteria": []' in seen[0]
    assert "Low poly island" not in seen[0]                                # not the one just shown


# ---------- B. wording ----------
LEMON_FACT = [{"label": "lemons", "quote": "2 lemons"}]


def _because(env, clause, facts=LEMON_FACT):
    return compose_once(env, {"picks": [{"n": 2, "verdict": "clear", "title": "Lemon garlic pasta", "because": clause,
                                         "facts": facts}], "intro": "I found a lemony pasta in your saves."})


def test_7_a_leading_i_recommend_because_is_stripped_from_the_clause(env):
    for clause in ("I recommend this one, because it needs just 2 lemons", "because it needs just 2 lemons",
                   "I recommend it because it needs just 2 lemons."):
        msg = _because(env, clause)
        assert "which you saved in March, because it needs just 2 lemons.\n" in msg
        assert msg.count("because") == 1 and "I recommend this" not in msg and clean(msg)
    from mvp import config
    prompt = open(os.path.join(config.HERE, "prompts", f"{config.PROMPT_COMPOSE}.md")).read()
    assert config.PROMPT_COMPOSE == "compose_v4" and 'never start it with "I recommend", "because"' in prompt


def test_8_a_clause_without_a_subject_follows_a_colon(env):
    msg = _because(env, "minimal effort and just 2 lemons")
    assert "which you saved in March: minimal effort and just 2 lemons.\n" in msg and "because minimal" not in msg
    msg = _because(env, "you only need 2 lemons")
    assert "because you only need 2 lemons." in msg


def test_9_no_double_full_stop_after_a_closing_quote(env):
    msg = _because(env, "it says “2 lemons.”")
    assert "because it says “2 lemons.”\n" in msg and ".”." not in msg


def test_10_an_unbacked_reason_is_dropped_not_replaced(env):
    msg = _because(env, "it is the best pasta ever", facts=[{"label": "x", "quote": "a pinch of chili"}])
    assert "I recommend Lemon garlic pasta by @chef, which you saved in March.\n" in msg
    assert "because" not in msg and clean(msg)


def test_11_the_finished_result_must_have_fits_the_topic_and_reads_naturally(rich):
    from mvp.interpret import clean_criteria
    assert clean_criteria(["a full routine from start to finish"], "beginner Blender tutorials") == \
        ["walks through one whole project from start to finish"]
    assert clean_criteria(["ends with a finished model"], "blender tutorials") == ["ends with a finished model"]
    assert clean_criteria(["a full routine from start to finish"], "a 20 minute workout") == \
        ["a full routine from start to finish"]
    rich["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": number_of(u, "cosy room"), "verdict": "close", "title": "Model a cosy room",
         "criteria": [{"answer": "unknown"}]}]}
    msg = say(rich, "beginner blender tutorials", {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {
        "goal": "beginner Blender tutorials", "searches": ["blender tutorial"],
        "criteria": ["a full routine from start to finish"]}}})
    assert msg.startswith("I couldn't confirm any of these walks you through a whole project, but the closest I have "
                          "is Model a cosy room") and "routine" not in msg and "meets" not in msg


def test_12_ingredients_only_for_food_and_never_the_same_lines_twice(env):
    from mvp.extract import kinds_for
    from mvp.render import details_lines
    assert kinds_for(["steps"]) == ["steps"] and kinds_for(["ingredients"]) == ["ingredients", "steps"]
    add_items(env, [{"id": "itm_w", "platform": "instagram", "source_url": "https://example.com/itm_w",
                     "caption": "Leg day workout\n- 10 squats\n- 10 lunges\n- 20 calf raises",
                     "interaction_kinds": ["save"], "platform_data": {"owner_handle": "coach", "owner_relation": "none"}}])
    env["bot"].pool.search = lambda lib, q, depth=300: {"ids": ["itm_w"], "mode": "normal", "cost_usd": 0.0}
    lines = ["10 squats", "10 lunges", "20 calf raises"]
    env["state"]["answers"]["mvp_extract"] = lambda u: {"ingredients": lines, "steps": lines}
    env["state"]["answers"]["mvp_compose"] = compose_picks({"n": 1, "verdict": "clear", "title": "Leg day workout"})
    msg = say(env, "a leg workout", {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {
        "goal": "a leg workout", "searches": ["leg workout"], "extract": ["steps"]}}})
    assert "Steps (3):\n1. 10 squats" in msg and "Ingredients" not in msg
    view = env["bot"].view(str(env["lib"]))
    p = {"item": view.get("itm_w"), "facts": {"ingredients": lines, "steps": lines}}
    out = details_lines(p, ["ingredients", "steps"])
    assert out.count("• 10 squats") + out.count("1. 10 squats") == 1 and "Steps (3):" not in out


def test_13_the_comma_comes_after_until_in_a_preview(env):
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    spec = pasta_spec({"type": "schedule", "days": ["MON", "TUE", "WED", "THU", "FRI"], "times": ["07:00", "18:00"],
                       "until": "2026-12-20"})
    msg = say(env, "weekdays at 7am and 6pm until 20 December", {"intent": "new_rule", "spec": spec})
    assert "Every weekday at 7am and 6pm until 20 December, I'll send" in msg and "December I'll" not in msg


def test_14_generic_words_are_not_counted_as_topics(env):
    msg = say(env, "how many cooking videos do I have", {"intent": "library_stats",
                                                          "stats": {"words": ["cooking", "videos"]}})
    assert "mention \"cooking\"." in msg and "videos\"" not in msg


def test_15_a_reply_is_all_spanish_or_all_english(env):
    seen = []
    env["state"]["answers"]["mvp_compose"] = lambda u: (seen.append(u), {"picks": [
        {"n": 2, "verdict": "clear", "title": "Lemon garlic pasta"}], "intro": "Encontré una receta de pasta."})[1]
    msg = say(env, "¿una receta de pasta?", dict(ask(), lang="es"))
    # (privacy review PRIV-8: an opening line is shown only when its words are the request's: "con limón" would not be)
    assert msg.startswith("Encontré una receta de pasta.\n\nTe recomiendo Lemon garlic pasta de @chef, que guardaste "
                          "en marzo.")
    assert "Ingredientes" in msg or "La receta" in msg or "Pasos" in msg or "\n" in msg
    assert "I recommend" not in msg and "which you" not in msg and '"lang": "es"' in seen[-1]
    env["state"]["answers"]["mvp_compose"] = lambda u: (seen.append(u), {"picks": [
        {"n": 2, "verdict": "clear", "title": "Lemon garlic pasta"}], "intro": "I found a lemon pasta in your saves."})[1]
    msg = say(env, "des pâtes ?", dict(ask(), lang="fr"))
    # checker: the composer is told to write English (left alone it follows the request's language: a mixed reply)
    assert "I recommend Lemon garlic pasta by @chef, which you saved in March" in msg and '"lang": "en"' in seen[-1]


# ---------- C. the choice ----------
def test_16_with_details_asked_the_recommended_pick_has_them_all(env):
    def extract(u):
        if "200g spaghetti" in u:
            return {"ingredients": ["200g spaghetti", "2 lemons"], "steps": ["4 cloves garlic", "Lemon garlic pasta"]}
        return {"ingredients": [], "steps": []}
    env["state"]["answers"]["mvp_extract"] = extract
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": number_of(u, "Pasta night"), "verdict": "clear", "title": "Pasta night"},
        {"n": number_of(u, "Lemon garlic"), "verdict": "clear", "title": "Lemon garlic pasta"}]}
    msg = say(env, "a pasta recipe with the ingredients and steps", ask(extract=["ingredients", "steps"]))
    assert "I recommend Lemon garlic pasta" in msg and "Steps (2):" in msg and "Ingredients (2):" in msg
    # the best one has only the ingredients written out: said plainly
    env["bot"].store.x("DELETE FROM facts")
    env["state"]["answers"]["mvp_extract"] = lambda u: {"ingredients": ["200g spaghetti", "2 lemons"], "steps": []} \
        if "200g spaghetti" in u else {}
    msg = say(env, "a pasta recipe with the ingredients and steps, please", ask(extract=["ingredients", "steps"]))
    assert "I recommend Lemon garlic pasta" in msg
    assert "The steps aren't written out in the post; they're in the video." in msg


def _yt_rows(env, rows):
    add_items(env, [yt_item(iid=i, vid=f"SYNvid{i[-5:]:0>5}", title=t, dur=d) for i, t, d in rows])
    env["bot"].pool.search = lambda lib, q, depth=300: {"ids": [r[0] for r in rows], "mode": "normal", "cost_usd": 0.0}


BLENDER_VIDS = [("ytb01", "Blender beginner tutorial: a whole kitchen scene", 26 * 60),
                ("ytb02", "Blender beginner tutorial: a mug", 8 * 60),
                ("ytb03", "Blender beginner tutorial: low poly tree", 15 * 60)]


def test_17_several_closest_up_to_the_count_shortest_first(env):
    _yt_rows(env, BLENDER_VIDS)
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": n, "verdict": "close", "title": t.split(": ")[1]} for n, t in
        [(num(u, "kitchen"), "x: A whole kitchen scene"), (num(u, "mug"), "x: A mug"), (num(u, "tree"), "x: Low poly tree")]]}
    msg = say(env, "show me 3 blender tutorials for beginners, shortest first", {"intent": "ask", "spec": {
        "when": {"type": "now"}, "content": {"goal": "Blender tutorials for beginners", "searches": ["blender"],
                                             "count": 3}}})
    # fix pass 2, finding 58: "for beginners" is a must-have now; nothing confirms it, and the reply says so
    assert "the closest I have is A mug" in msg and "Or these, which are close too:" in msg
    assert msg.index("A mug") < msg.index("Low poly tree") < msg.index("A whole kitchen scene")


def test_18_mini_is_a_length_bound_checked_against_youtube(env):
    _yt_rows(env, BLENDER_VIDS[:2])
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": num(u, "kitchen"), "verdict": "clear", "title": "A whole kitchen scene"},
        {"n": num(u, "mug"), "verdict": "clear", "title": "A mug"}]}
    spec = {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {"goal": "a mini Blender tutorial",
                                                                             "searches": ["blender tutorial"]}}}
    msg = say(env, "a mini blender tutorial", spec)
    assert "I recommend A mug by Synthetic Channel (8 minutes)" in msg and "kitchen" not in msg.split("\n\n")[1]
    _yt_rows(env, BLENDER_VIDS[:1])
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": num(u, "kitchen"), "verdict": "clear", "title": "A whole kitchen scene"}]}
    msg = say(env, "a mini blender tutorial please", spec)
    assert msg.startswith("None of what I found is under 10 minutes long, so the closest I have is A whole kitchen "
                          "scene by Synthetic Channel (26 minutes)")
    from mvp.executor import length_bound
    from mvp.schema import RuleSpec
    s = RuleSpec.model_validate(dict(spec["spec"], content=dict(spec["spec"]["content"], goal="a Blender tutorial")))
    assert length_bound(RuleSpec.model_validate(spec["spec"])) == 10      # a rule's goal counts (its timed sends)
    assert length_bound(s, "a quick blender tutorial") == 15 and length_bound(s, "under 7 minutes") == 7
    food = RuleSpec.model_validate(pasta_spec({"type": "now"}))
    assert length_bound(food, "a quick pasta recipe") is None            # cooking time, not the video's length


def test_19_a_rule_with_a_tiny_supply_says_so_in_its_preview(yt):
    yt["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": number_of(u, "Lemon garlic"), "verdict": "clear", "title": "Lemon garlic pasta"}]}
    spec = pasta_spec({"type": "schedule", "days": ["FRI"], "times": ["19:00"]})
    msg = str(say(yt, "a pasta recipe every friday at 7pm", {"intent": "new_rule", "spec": spec}))
    # fix pass 4, finding 77: the count is the ranked list's posts that look like recipes and name pasta (two here:
    # "Pasta night! recipe in the video" is one too), not only the composer's one verdict
    assert "Heads up: I only see about 2 posts in your library that fit, so this will run dry quickly." in msg
    assert "Want me to add related videos from outside your saves? Reply YES to start it that way" in msg
    assert not yt["yt"].searches()                                        # an offer only: nothing searched yet
    say(yt, "yes", {"intent": "confirm"})
    assert yt["bot"].store.rules(H)[0]["spec"]["content"]["outside"] == "some"


def test_20_an_ask_is_read_the_same_whatever_rules_exist(env, monkeypatch):
    from mvp import config, interpret as I
    monkeypatch.setattr(config, "INTERPRET_CACHE_HOURS", 6)
    store, now = env["bot"].store, env["clock"][0]
    person = {"handle": H, "timezone": "America/New_York"}
    forms = iter([{"intent": "ask", "spec": pasta_spec({"type": "now"})},
                  {"intent": "run_rule", "rule_number": 1}, {"intent": "run_rule", "rule_number": 1}])
    I.llm.chat_json = lambda *a, **k: (next(forms), 0.001)
    a, _ = I.interpret("pasta ideas?", person, [], None, None, now, store=store)
    rule = {"id": 1, "status": "active", "spec": pasta_spec()}
    b, cost = I.interpret("pasta ideas?", person, [rule], None, None, now, store=store)
    assert cost == 0.0 and a.spec.stored() == b.spec.stored()            # the same search after a rule was added
    I.interpret("the pasta one now", person, [rule], None, None, now, store=store)
    c, cost = I.interpret("the pasta one now", person, [rule, dict(rule, id=2)], None, None, now, store=store)
    assert cost > 0                                                       # a form about rules is read again


# ---------- D. carried over from the slice reports ----------
def test_21_a_rule_ended_by_time_alone_gets_one_notice(env):
    bot, clock, ch = env["bot"], env["clock"], env["ch"]
    now = clock[0]                                                        # Thu 12 Nov, 1pm New York
    say(env, "remind me at 3pm to call mum", {"intent": "new_rule", "spec": note_spec(
        {"type": "once", "date": "2026-11-12", "time": "15:00"}, "call mum")})
    say(env, "pause it until tomorrow", {"intent": "pause", "rule_number": 1, "until": "2026-11-13"})
    clock[0] = datetime(2026, 11, 13, 5, 1, tzinfo=UTC)                   # the pause ends; 3pm yesterday has passed
    n = len(ch.outbox)
    bot.tick()
    assert len(ch.outbox) == n                                            # checker: 00:01 there is quiet; it waits
    clock[0] = datetime(2026, 11, 13, 13, 1, tzinfo=UTC)                  # 8:01am: the quiet hours are over
    bot.tick()
    assert len(ch.outbox) == n + 1 and "\"call mum\" had no send left after its pause" in last(ch)
    # a temporary time zone that switches back and leaves a one-time send in the past
    clock[0] = now + timedelta(days=1)
    bot._move_timezone(H, "America/Los_Angeles", clock[0], revert_to="America/New_York",
                       revert_at=clock[0] + timedelta(hours=10))
    say(env, "remind me at 10pm to sleep", {"intent": "new_rule", "spec": note_spec(
        {"type": "once", "date": "2026-11-13", "time": "22:00"}, "sleep")})   # 10pm there is 9pm-ish here: passed
    clock[0] = clock[0] + timedelta(hours=10, minutes=1)
    n = len(ch.outbox)
    bot.tick()
    assert len(ch.outbox) == n                                            # 11:01pm in New York: held
    clock[0] = datetime(2026, 11, 14, 13, 1, tzinfo=UTC)
    bot.tick()
    assert len(ch.outbox) == n + 1 and last(ch).startswith("I'm back on New York time.") and "\"sleep\"" in last(ch)


def test_22_to_do_reminders_do_not_count_as_unanswered_sends(env):
    bot, now = env["bot"], env["clock"][0]
    bot.store.set_state(f"last_in:{H}", (now - timedelta(days=3)).isoformat())
    for i in range(6):
        bot.store.add_run(handle=H, kind="todo", status="sent", at=(now - timedelta(hours=i)).isoformat())
    assert bot._unanswered(H) == 0
    bot.store.add_run(handle=H, kind="scheduled", status="sent", at=now.isoformat())
    assert bot._unanswered(H) == 1


def test_23_an_empty_search_is_an_error_and_a_retry_never_nothing_found(env, monkeypatch):
    from mvp import config
    monkeypatch.setattr(config, "RANKED_CACHE_HOURS", 24)
    calls = []
    env["bot"].pool.search = lambda lib, q, depth=300: (calls.append(q), {"ids": [], "mode": "normal",
                                                                          "cost_usd": 0.0})[1]
    msg = compose_once(env, {"picks": []})
    assert msg.startswith("Something went wrong on my side") and "didn't find" not in msg
    assert len(calls) == 2 and env["bot"].store.one("SELECT COUNT(*) n FROM ranked_cache")["n"] == 0
    assert env["bot"].store.one("SELECT status FROM runs ORDER BY id DESC LIMIT 1")["status"] == "error"


def test_24_youtube_lines_kept_in_state_are_purged_with_the_youtube_cache(env):
    store = env["bot"].store
    old = (env["clock"][0] - timedelta(days=40)).isoformat()
    store.facts_put("lib", "itm_y", "key_points", ["from a description"], "extract_v1", source="youtube_api",
                    at=datetime.fromisoformat(old))
    store.set_state(f"facts:{H}", {"itm_y": {"key_points": ["from a description"]}, "itm_a": {"steps": ["x"]}})
    store.set_state(f"lines:{H}", {"itm_y": ["from a description"], "itm_a": ["x"]})
    store.set_state(f"linekinds:{H}", {"itm_y": ["key_points"], "itm_a": ["steps"]})
    store.purge_youtube((env["clock"][0] - timedelta(days=30)).isoformat())
    for k in ("facts", "lines", "linekinds"):
        assert list(store.get_state(f"{k}:{H}")) == ["itm_a"]


def test_25_undo_reverses_every_kind_of_write_one_message_made(env):
    bot = env["bot"]
    say(env, "every monday at 9 remind me to stretch", {"intent": "new_rule", "spec": note_spec(
        {"type": "schedule", "days": ["MON"], "times": ["09:00"]}, "stretch")})
    say(env, "add milk to my list and pause the stretch one", {"intent": "todo_add", "todo_text": "milk",
                                                                 "also": {"intent": "pause", "rule_number": 1}})
    assert bot.store.todos(H) and bot.store.rules(H)[0]["status"] == "paused"
    msg = say(env, "undo", {"intent": "undo"})
    assert bot.store.todos(H) == [] and bot.store.rules(H)[0]["status"] == "active"
    assert "off your list" in msg and "back as it was" in msg


# ---------- E. carried over from slices 4 to 6 ----------
TIPS = {"id": "itm_t", "platform": "instagram", "source_url": "https://example.com/itm_t",
        "caption": "Beginner modeling tips in Blender: 5 shortcuts you need", "interaction_kinds": ["save"],
        "platform_data": {"owner_handle": "maker", "owner_relation": "none"}}
DAILY_BLENDER = {"intent": "new_rule", "spec": {
    "when": {"type": "schedule", "days": ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"], "times": ["08:00"]},
    "content": {"goal": "mini beginner Blender tutorials", "searches": ["blender beginner tutorial"],
                "criteria": ["ends with a finished model"]}}}
FOUNDER = "send me mini beginner Blender tutorials to start doing daily"


def _tips_only(e):
    add_items(e, [dict(TIPS)])
    e["bot"].pool.search = lambda lib, q, depth=300: {"ids": ["itm_t"], "mode": "normal", "cost_usd": 0.0}
    e["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": 1, "verdict": "clear", "title": "Beginner modeling tips",
         "criteria": [{"answer": "yes", "quote": "Beginner modeling tips"}]}]}


def test_26_the_founders_blender_request_never_ends_with_nothing(yt):
    _tips_only(yt)
    msg = say(yt, FOUNDER, DAILY_BLENDER)
    reply = yt["replies"][-1]
    assert msg.startswith("Here's what that would look like now:\n\nNone of what I found walks you through a whole "
                          "project, so the closest I have is Beginner modeling tips")
    assert "None of your saved Blender tutorials fits, so here are a few from YouTube:" in msg   # finding 64
    vids = [p for p in reply.parts if p.get("outside")]
    assert len(vids) == 2 and len(yt["yt"].searches()) == 1             # one search, in the same reply
    # fix pass 2, findings 57 and 59: "mini" is at most 10 minutes; a longer video is never shown
    assert "(9 minutes 40 seconds)" in msg and "VIDaaaaaa04" in msg and "VIDaaaaaa02" not in msg
    assert yt["yt"].searches()[0][1]["videoDuration"] == "medium"
    assert "Want these every day at 8am from YouTube as well as your saves? Reply YES to start it that way" in msg
    say(yt, "yes", {"intent": "confirm"})
    rule = yt["bot"].store.rules(H)[0]
    assert rule["spec"]["content"]["outside"] == "some"
    shown = yt["bot"].store.get_state(f"outside_shown:{H}")
    assert set(shown[f"rule:{rule['id']}"]) == {p["video_id"] for p in vids}   # finding 33
    # an ask: the same honest line, the closest pick and the block; no route: no YouTube words, still a link
    yt["bot"].store.clear_pending(H)
    ask_form = {"intent": "ask", "spec": dict(DAILY_BLENDER["spec"], when={"type": "now"})}
    msg = say(yt, "a mini beginner blender tutorial", ask_form)
    # fix pass 2, finding 64: the block nobody asked for comes once per topic per day; the preview had it already
    assert "the closest I have is Beginner modeling tips" in msg and "YouTube" not in msg
    assert len(yt["yt"].searches()) == 1
    os.environ.pop("YOUTUBE_API_KEY")
    msg = say(yt, "a mini beginner blender tutorial to do", ask_form)
    assert "the closest I have is Beginner modeling tips" in msg and "https://example.com/itm_t" in msg
    assert "YouTube" not in msg and clean(msg)


def test_26_a_few_finished_ones_are_said_in_one_line(env):
    add_items(env, [dict(TIPS), {"id": "itm_p", "platform": "instagram", "source_url": "https://example.com/itm_p",
                                 "caption": "Blender donut tutorial for beginners, from start to finish",
                                 "interaction_kinds": ["save"], "platform_data": {"owner_handle": "maker"}}])
    env["bot"].pool.search = lambda lib, q, depth=300: {"ids": ["itm_p", "itm_t"], "mode": "normal", "cost_usd": 0.0}
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": 1, "verdict": "clear", "title": "Blender donut tutorial",
         "criteria": [{"answer": "yes", "quote": "from start to finish"},
                      {"answer": "yes", "quote": "tutorial for beginners"}]}]}   # finding 58: the level must-have
    msg = say(env, "a mini beginner blender tutorial", {"intent": "ask", "spec": dict(DAILY_BLENDER["spec"],
                                                                                      when={"type": "now"})})
    assert "I recommend Blender donut tutorial" in msg and msg.endswith(
        "You only have 1 saved Blender tutorial that fits.")   # fix pass 2, finding 64: in the request's terms


def test_27_only_new_stuff_after_an_answer_is_more_from_outside_only(yt):
    yt["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(yt, "a lemon pasta recipe", ask_pasta())
    n = interp_calls(yt)
    yt["bot"].on_message(H, "only new stuff, not from my saves")
    msg = str(yt["replies"][-1])
    assert interp_calls(yt) == n and msg.startswith("Here are some new recipes from YouTube, not from your saves:")   # (fix pass 5, finding 85)
    q = yt["yt"].searches()[-1][1]["q"]
    assert "pasta" in q and "new" not in q.split()


def test_28_a_recipe_gets_its_details_without_being_asked_and_add_its_ingredients_works(env):
    extracts = []
    env["state"]["answers"]["mvp_extract"] = lambda u: (extracts.append(u), {
        "ingredients": ["200g spaghetti", "2 lemons"], "steps": ["4 cloves garlic", "Lemon garlic pasta"]} if "200g" in u else {})[1]
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": number_of(u, "Lemon garlic"), "verdict": "clear", "title": "Lemon garlic pasta"},
        {"n": number_of(u, "Pasta night"), "verdict": "clear", "title": "Pasta night"}]}
    spec = pasta_spec({"type": "now"})
    spec["content"].update(extract=[], count=3, goal="easy pasta recipes")
    msg = say(env, "find me 3 easy pasta recipes", {"intent": "ask", "spec": spec})
    assert "Ingredients (2):\n• 200g spaghetti" in msg and "Steps (2):" in msg
    assert len(extracts) == 1                                              # the recommended pick only
    # "add its ingredients" when nothing was read yet: the details step runs now
    env["bot"].store.x("DELETE FROM facts")
    env["bot"].store.set_state(f"facts:{H}", {})
    env["bot"].store.x("UPDATE answers SET picks='[]'")
    msg = say(env, "add its ingredients to my grocery list", {"intent": "todo_add", "pick_number": 1,
                                                              "what": "ingredients", "list": "grocery"})
    assert msg == "Added 2 things to your grocery list: 200g spaghetti; 2 lemons."


@pytest.mark.parametrize("form", [
    {"intent": "act_on_last", "actions": ["message.send"], "pick_number": 2,
     "when": {"type": "once", "date": "2026-11-12", "time": "20:00"}},
    {"intent": "act_on_last", "actions": ["calendar.add"], "params": {"time": "20:00"}},
    {"intent": "new_rule", "spec": {"when": {"type": "once", "date": "2026-11-12", "time": "20:00"},
                                    "content": {"goal": "the second one", "searches": ["second one"]}}},
    {"intent": "new_rule", "spec": {"when": {"type": "once", "date": "2026-11-12", "time": "20:00"},
                                    "content": {"source": "note", "text": "the second one"}}},
    {"intent": "todo_add", "todo_text": "the second one", "due": "2026-11-12T20:00"},
])
def test_29_remind_me_of_the_second_one_tonight_always_ends_as_act_on_last(env, form):
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": number_of(u, "Lemon garlic"), "verdict": "clear", "title": "Lemon garlic pasta"},
        {"n": number_of(u, "Pasta night"), "verdict": "clear", "title": "Pasta night"}]}
    say(env, "pasta", ask(count=2))
    msg = say(env, "remind me of the second one tonight at 8", form)
    rule = env["bot"].store.rules(H)[-1]
    assert rule["spec"]["content"]["source"] == "items" and rule["spec"]["content"]["item_ids"] == ["itm_c"]
    assert rule["spec"]["when"] == {"type": "once", "date": "2026-11-12", "times": ["20:00"]}
    assert [a["action"] for a in rule["spec"]["do"]] == ["message.send"]
    assert msg.startswith("OK. Today at 8pm I'll send it to you here: \"Pasta night\".")


def test_30_a_dropped_waiting_email_is_said_once(env):
    from mvp.tests.test_slice4 import ask_with, last_code
    bot, clock = env["bot"], env["clock"]
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    for i in range(3):
        say(env, f"pasta {i}, email it to me", ask_with(["message.send", "email.send"]))
    msg = say(env, "pasta 4, email it to me", ask_with(["message.send", "email.send"]))
    assert "I can keep only 3 emails waiting, so the oldest one was dropped." in msg
    assert len(bot.store.get_state(f"emailwait:{H}")) == 3
    say(env, "a@b.co", {"intent": "chat"})
    clock[0] = clock[0] + timedelta(minutes=5)
    bot.store.set_state(f"emailwait:{H}", [dict(w, at=(clock[0] - timedelta(hours=25)).isoformat())
                                           for w in bot.store.get_state(f"emailwait:{H}")[:1]]
                        + bot.store.get_state(f"emailwait:{H}")[1:])
    msg = say(env, last_code(bot), {"intent": "chat"})
    assert "One email that waited more than a day for your address was dropped; ask me again if you still want it." \
        in msg and msg.count("I didn't send") == 2


def test_31_takeout_parts_wait_for_each_other_and_are_imported_together(fresh, tmp_path):
    from mvp import config
    config.INBOX_PARTS_MINUTES = 10
    bot = fresh["bot"]
    p1 = os.path.join(fresh["inbox"], "takeout-20261112T000000Z-001.zip")
    zip_dir(FIX_YT, p1)
    assert bot.refresher.poll(force=True) == 0                            # its other parts may still come
    old = time.time() - 11 * 60
    os.utime(p1, (old, old))
    p2 = os.path.join(fresh["inbox"], "takeout-20261112T000000Z-002.zip")
    zip_dir(FIX_YT, p2)
    assert bot.refresher.poll(force=True) == 0                            # a new part came: both wait
    os.utime(p2, (old, old))
    seen = []
    real = bot.refresher.import_files
    bot.refresher.import_files = lambda h, files, now=None: (seen.append(sorted(map(os.path.basename, files))),
                                                            real(h, files, now))[1]
    assert bot.refresher.poll(force=True) == 1
    assert seen == [["takeout-20261112T000000Z-001.zip", "takeout-20261112T000000Z-002.zip"]]


def test_32_an_import_in_quiet_hours_is_announced_when_they_end(fresh):
    bot, ch, clock = fresh["bot"], fresh["ch"], fresh["clock"]
    clock[0] = datetime(2026, 11, 13, 4, 0, tzinfo=UTC)                   # 11pm in New York: quiet
    drop(fresh, fresh["ig_zip"])
    n = len(ch.outbox)
    assert bot.refresher.poll(force=True) == 1
    assert len(ch.outbox) == n and bot.store.get_state(f"heldimport:{H}")   # switched, but not said yet
    bot.tick()
    assert len(ch.outbox) == n
    clock[0] = datetime(2026, 11, 13, 13, 5, tzinfo=UTC)                  # 8:05am
    bot.tick()
    assert last(ch).startswith("Your new export is in: ") and not bot.store.get_state(f"heldimport:{H}")


def test_34_the_first_requests_offer_closes_after_two_other_messages(env):
    bot = env["bot"]
    spec = pasta_spec({"type": "now"})
    bot.store.set_state(f"onboard:{H}", {"step": "offer", "at": env["clock"][0].isoformat(),
                                         "requests": [{"text": "a pasta recipe", "spec": spec}]})
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(env, "thanks!", {"intent": "chat", "reply": "Any time."})
    say(env, "what's the weather", {"intent": "unsupported", "reply": "I can't check that."})
    n = interp_calls(env)
    say(env, "1", {"intent": "chat", "reply": "One what?"})
    assert interp_calls(env) == n + 1 and bot.store.get_state(f"onboard:{H}")["step"] == "done"
    assert spec


@pytest.mark.parametrize("text", ["partner workout", "god tier builds in Elden Ring", "trading cards to collect",
                                  "keto recipes", "chicken stock from scratch", "budget meals",
                                  "a liberal amount of garlic", "a workout for a sore knee injury"])
def test_35_harmless_phrases_are_not_personal_topics(text):
    from mvp.outside import sensitive_topic
    from mvp.profile import sensitive
    assert sensitive_topic([text]) is None and not sensitive(text)


@pytest.mark.parametrize("text", ["advice after my divorce", "anxiety at night", "pay off my credit card debt",
                                  "bible study ideas", "the election results", "my coming out story",
                                  "dating advice", "green card interview tips"])
def test_35_personal_topics_still_are(text):
    from mvp.outside import sensitive_topic
    from mvp.profile import sensitive
    assert sensitive_topic([text]) is not None and sensitive(text)


def test_37_an_answer_reads_like_the_founders_target(yt):
    yt["state"]["answers"]["mvp_extract"] = lambda u: {"ingredients": ["200g spaghetti", "2 lemons"],
                                                       "steps": ["4 cloves garlic", "Lemon garlic pasta"]} if "200g" in u else {}
    yt["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": number_of(u, "Lemon garlic"), "verdict": "clear", "title": "Lemon garlic pasta",
         "because": "I recommend this one, because it needs just 2 lemons",
         "facts": [{"label": "lemons", "quote": "2 lemons"}]},
        {"n": number_of(u, "Pasta night"), "verdict": "clear", "title": "Pasta night"}],
        "intro": "I found some lemony pasta recipes in your saves."}
    a = outside_ask(count=2, extract=["ingredients", "steps"])
    msg = str(say(yt, "lemony pasta recipes, and some new ones", a))
    order = ["I found some lemony pasta recipes in your saves.",
             "I recommend Lemon garlic pasta by @chef, which you saved in March, because it needs just 2 lemons.",
             "https://example.com/itm_a", "Ingredients (2):", "Steps (2):", "Or try these:", "• Pasta night by @chef",
             "Not from your saves, but close to them:"]
    at = [msg.index(x) for x in order]
    assert at == sorted(at) and clean(msg) and "[" not in msg and "Alternatively" not in msg
