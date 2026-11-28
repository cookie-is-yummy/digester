"""Offline tests for the checker's fixes on top of the fix pass (findings of the live run of 12 Nov): near-variants the
fix pass missed, each failing without its fix. Synthetic data, the fake model, the fake search pool, the fake YouTube
and the fake clock only."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import compose_picks, env, last, pasta_spec  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, ask_pasta, lemon_pick, note_spec, say  # noqa: E402
from mvp.tests.test_slice3 import add_items, ask, compose_once  # noqa: E402
from mvp.tests.test_slice5 import outside_ask, yt  # noqa: E402,F401
from mvp.tests.test_slice6 import number_of, pick, rich  # noqa: E402,F401

UTC = timezone.utc


def interp_calls(e):
    return e["calls"].count("mvp_interpret")


# ---------- A ----------
def test_1_a_polite_plain_command_is_still_read_by_code(env):
    bot = env["bot"]
    for t in ("stretch", "drink water"):
        say(env, f"every monday at 9 remind me to {t}", {"intent": "new_rule", "spec": note_spec(
            {"type": "schedule", "days": ["MON"], "times": ["09:00"]}, t)})
    n = interp_calls(env)
    env["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "skip", "rule_number": 2}   # a misreading
    bot.on_message(H, "pls stop rule 2")
    assert bot.store.rules(H, statuses=("active", "stopped"))[1]["status"] == "stopped"
    bot.on_message(H, "undo please")
    assert last(env["ch"]).startswith("Undone:") and interp_calls(env) == n


def test_3_a_list_named_without_my_list_leaves_the_item_text(env):
    bot = env["bot"]
    say(env, "add eggs, oat milk and bread to groceries",
        {"intent": "todo_add", "todo_text": "eggs, oat milk and bread to groceries"})
    assert [(t["text"], t["list"]) for t in bot.store.todos(H)] == [
        ("eggs", "groceries"), ("oat milk", "groceries"), ("bread", "groceries")]
    # the form named the list and left it in the text too
    say(env, "add socks to packing", {"intent": "todo_add", "todo_text": "socks to packing", "list": "packing"})
    assert ("socks", "packing") in [(t["text"], t["list"]) for t in bot.store.todos(H)]


def test_4_a_question_about_a_shown_pick_never_says_i_recommend(env):
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": number_of(u, "Pasta night"), "verdict": "clear", "title": "Pasta night"},
        {"n": number_of(u, "Lemon garlic"), "verdict": "clear", "title": "Lemon garlic pasta"}]}
    say(env, "pasta recipes", ask(count=2, extract=[]))
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": number_of(u, "Lemon garlic"), "verdict": "clear", "title": "Lemon garlic pasta",
         "because": "it uses 2 lemons", "facts": [{"label": "lemons", "quote": "2 lemons"}]}],
        "intro": "Yes, this one has no meat."}
    msg = say(env, "is the second one vegetarian?", {"intent": "follow_up", "question": "is the second one vegetarian?",
                                                      "pick_number": 2})
    assert msg.startswith("Yes, this one has no meat.\n\nIt's Lemon garlic pasta by @chef, which you saved in March: "
                          "it uses 2 lemons.")
    assert "I recommend" not in msg
    # no line of its own from the composer: never an opening built from the question
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": number_of(u, "Lemon garlic"), "verdict": "clear", "title": "Lemon garlic pasta"}]}
    msg = say(env, "which one has no cream?", {"intent": "follow_up", "question": "which one has no cream?"})
    assert msg.startswith("It's Lemon garlic pasta by @chef") and "for which one" not in msg


def test_6_the_feedback_line_never_promises_one_that_did_not_come(rich):
    st = rich["state"]
    st["answers"]["mvp_compose"] = pick("Low poly island")
    say(rich, "a blender tutorial", {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {
        "goal": "a Blender tutorial", "searches": ["blender tutorial"]}}})
    st["answers"]["mvp_compose"] = lambda u: {"picks": []}                  # nothing easier left
    msg = say(rich, "too hard", {"intent": "feedback", "feedback": "easier"})
    assert "Here's an easier one" not in msg and msg.startswith("Noted")


def test_15_a_language_without_a_table_asks_the_composer_for_english(env):
    seen = []
    env["state"]["answers"]["mvp_compose"] = lambda u: (seen.append(u), {"picks": [
        {"n": number_of(u, "Lemon garlic"), "verdict": "clear", "title": "Lemon garlic pasta"}]})[1]
    say(env, "une recette de pâtes", dict(ask(), lang="fr"))
    assert '"lang": "en"' in seen[-1]
    say(env, "a pasta recipe", ask())
    assert '"lang"' not in seen[-1]                                        # English: nothing to say


def test_15_a_spanish_answer_with_new_videos_is_all_spanish(yt):
    yt["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": number_of(u, "Lemon garlic"), "verdict": "clear", "title": "Lemon garlic pasta"}],
        "intro": "Encontré una pasta con limón."}
    msg = str(say(yt, "una receta de pasta y algunas nuevas", dict(outside_ask(), lang="es")))
    assert "Te recomiendo" in msg and "No está en lo que guardaste, pero se le parece:" in msg
    assert "(9 minutos 40 segundos), en YouTube" in msg
    assert "Not from your saves" not in msg and ", on YouTube" not in msg and "minutes" not in msg


# ---------- B ----------
def test_7_i_would_and_id_recommend_are_stripped_too(env):
    for clause in ("I'd recommend this one, because it needs just 2 lemons",
                   "I’d recommend this one because it needs just 2 lemons"):
        msg = compose_once(env, {"picks": [{"n": 2, "verdict": "clear", "title": "Lemon garlic pasta", "because": clause,
                                            "facts": [{"label": "lemons", "quote": "2 lemons"}]}]})
        assert "which you saved in March, because it needs just 2 lemons.\n" in msg and "recommend this" not in msg


def test_8_one_is_not_a_subject(env):
    msg = compose_once(env, {"picks": [{"n": 2, "verdict": "clear", "title": "Lemon garlic pasta",
                                        "because": "one of the simplest, with just 2 lemons",
                                        "facts": [{"label": "lemons", "quote": "2 lemons"}]}]})
    assert "which you saved in March: one of the simplest, with just 2 lemons." in msg and "because one" not in msg


def test_12_a_workout_form_that_asks_for_ingredients_shows_none(env):
    add_items(env, [{"id": "itm_w", "platform": "instagram", "source_url": "https://example.com/itm_w",
                     "caption": "Leg day workout\n- 10 squats\n- 10 lunges\n- 20 calf raises",
                     "interaction_kinds": ["save"], "platform_data": {"owner_handle": "coach", "owner_relation": "none"}}])
    env["bot"].pool.search = lambda lib, q, depth=300: {"ids": ["itm_w"], "mode": "normal", "cost_usd": 0.0}
    lines = ["10 squats", "10 lunges", "20 calf raises"]
    env["state"]["answers"]["mvp_extract"] = lambda u: {"ingredients": lines, "steps": lines}
    env["state"]["answers"]["mvp_compose"] = compose_picks({"n": 1, "verdict": "clear", "title": "Leg day workout"})
    msg = say(env, "a leg workout with what I need", {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {
        "goal": "a leg workout", "searches": ["leg workout"], "extract": ["ingredients", "steps"]}}})
    assert "Ingredients" not in msg and "Steps (3):\n1. 10 squats" in msg


# ---------- C ----------
def test_19_the_heads_up_counts_what_is_left_after_the_preview_pick(yt):
    yt["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": number_of(u, "Lemon garlic"), "verdict": "clear", "title": "Lemon garlic pasta"},
        {"n": number_of(u, "Pasta night"), "verdict": "clear", "title": "Pasta night"},
        {"n": number_of(u, "carbonara"), "verdict": "close", "title": "Best carbonara ever"}]}
    spec = pasta_spec({"type": "schedule", "days": ["FRI"], "times": ["19:00"]})
    msg = str(say(yt, "a pasta recipe every friday at 7pm", {"intent": "new_rule", "spec": spec}))
    assert "Heads up: I only see about 3 posts in your library that fit" in msg   # 2 left after the one shown


def test_20_the_same_ask_right_after_starting_a_rule_is_read_from_the_cache(env, monkeypatch):
    from mvp import config
    monkeypatch.setattr(config, "INTERPRET_CACHE_HOURS", 6)
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(env, "a pasta recipe", ask_pasta())
    say(env, "every friday at 7 send me a pasta recipe", {"intent": "new_rule", "spec": pasta_spec()})
    say(env, "yes", {"intent": "confirm"})                                 # a write 'undo' could reverse
    n = interp_calls(env)
    msg = say(env, "a pasta recipe", {"intent": "chat", "reply": "a different reading"})
    assert interp_calls(env) == n and "a different reading" not in msg
    # "never mind" is not reused across "something to undo" and "nothing to undo"
    from mvp.interpret import RULE_FREE
    assert "chat" not in RULE_FREE


# ---------- E ----------
def test_29_a_pointer_and_a_time_in_minutes_ends_as_a_send_at_that_time(env):
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": number_of(u, "Lemon garlic"), "verdict": "clear", "title": "Lemon garlic pasta"},
        {"n": number_of(u, "Pasta night"), "verdict": "clear", "title": "Pasta night"}]}
    say(env, "pasta", ask(count=2))
    for form in ({"intent": "todo_add", "todo_text": "the 2nd one", "in_minutes": 60},
                 {"intent": "act_on_last", "actions": ["message.send"], "pick_number": 2,
                  "when": {"type": "once", "in_minutes": 60}}):
        msg = say(env, "remind me about the 2nd one in an hour", form)
        rule = env["bot"].store.rules(H)[-1]
        assert rule["spec"]["content"]["item_ids"] == ["itm_c"], msg
        assert rule["spec"]["when"] == {"type": "once", "date": "2026-11-12", "times": ["14:00"]}
        assert msg.startswith("OK. Today at 2pm I'll send it to you here: \"Pasta night\".")
        env["bot"].store.set_slot(rule["id"], None, "stopped")


# ---------- D ----------
def test_21_a_notice_waits_for_the_end_of_quiet_hours(env):
    bot, clock, ch = env["bot"], env["clock"], env["ch"]
    say(env, "remind me at 3pm to call mum", {"intent": "new_rule", "spec": note_spec(
        {"type": "once", "date": "2026-11-12", "time": "15:00"}, "call mum")})
    say(env, "pause it until tomorrow", {"intent": "pause", "rule_number": 1, "until": "2026-11-13"})
    clock[0] = datetime(2026, 11, 13, 5, 1, tzinfo=UTC)                   # 00:01 in New York: quiet
    n = len(ch.outbox)
    bot.tick()
    assert len(ch.outbox) == n and bot.store.get_state(f"heldnotice:{H}")
    clock[0] = datetime(2026, 11, 13, 13, 5, tzinfo=UTC)                  # 8:05am
    bot.tick()
    assert len(ch.outbox) == n + 1 and "\"call mum\"" in last(ch) and not bot.store.get_state(f"heldnotice:{H}")
    bot.tick()
    assert len(ch.outbox) == n + 1                                        # once


def test_24_description_lines_leave_the_kept_answer_text_too(env):
    store = env["bot"].store
    old = env["clock"][0] - timedelta(days=40)
    store.facts_put("lib", "itm_y", "key_points", ["Space your reviews", "Test yourself"], "extract_v1",
                    source="youtube_api", at=old)
    parts = [{"type": "text", "text": "I found a study video.\n\nI recommend Study with me."},
             {"type": "link", "url": "https://www.youtube.com/watch?v=SYNvid00001"},
             {"type": "text", "text": "Key points (2):\n• Space your reviews\n• Test yourself\n\nOr try these:\n• Other"}]
    picks = [{"item_id": "itm_y", "title": "Study with me", "facts": {"key_points": ["Space your reviews",
                                                                                  "Test yourself"]},
              "lines": ["Space your reviews", "Test yourself"]}]
    store.x("INSERT INTO answers(run_id,handle,rule_id,goal,kind,parts,picks,at) VALUES(?,?,?,?,?,?,?,?)",
            (99, H, None, "a study video", "picks", json.dumps(parts), json.dumps(picks), old.isoformat()))
    store.purge_youtube((env["clock"][0] - timedelta(days=30)).isoformat())
    kept = store.answer(99)
    text = "\n".join(p.get("text") or "" for p in kept["parts"])
    assert "Space your reviews" not in text and "Test yourself" not in text and "Key points" not in text
    assert "Or try these:\n• Other" in text and "I recommend Study with me." in text
    assert kept["picks"][0]["facts"] == {} and kept["picks"][0]["lines"] == []


def test_35_more_harmless_and_sensitive_phrases():
    from mvp.outside import sensitive_topic
    from mvp.profile import sensitive
    for text in ("healthy dinner ideas", "a stock pot recipe", "budget travel tips"):
        assert sensitive_topic([text]) is None and not sensitive(text), text
    for text in ("chemo diet", "trump rally", "my depression is bad", "pay off student loans"):
        assert sensitive_topic([text]) is not None and sensitive(text), text


def test_3_one_todo_add_per_item_chained_three_deep_keeps_every_item(env):
    """Found live by the checker: the model gave one todo_add per item, nested through `also`; the third was lost."""
    bot = env["bot"]
    form = {"intent": "todo_add", "todo_text": "bread", "list": "groceries",
            "also": {"intent": "todo_add", "todo_text": "rice", "list": "groceries",
                     "also": {"intent": "todo_add", "todo_text": "lemons", "list": "groceries"}}}
    msg = say(env, "add bread, rice and lemons to groceries", form)
    assert [(t["text"], t["list"]) for t in bot.store.todos(H)] == [
        ("bread", "groceries"), ("rice", "groceries"), ("lemons", "groceries")]
    assert msg == "Added 3 things to your groceries list: bread; rice; lemons."
    say(env, "undo", {"intent": "undo"})
    assert bot.store.todos(H) == []
