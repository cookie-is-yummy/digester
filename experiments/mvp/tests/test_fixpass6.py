"""Offline tests for fix pass 6 (live findings of 13 Nov, round 6, after a full setup): one or more tests per finding 88
and 89, their near-variants, and the checker's audit, each failing without its fix. Both findings are a message
changing lasting state it never asked to change. Synthetic data, a fake model, a fake search pool and a fake clock
only; the fixtures come from the earlier test files."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, say  # noqa: E402
from mvp.tests.test_slice6 import fake_guess, pick, rich, write_library  # noqa: E402,F401  (rich is a fixture)


def P():
    from mvp import profile
    return profile


def with_blender(e, level="beginner"):
    """The person's profile after the setup: Blender 3D at a level they gave, Home cooking, an air fryer."""
    bot = e["bot"]
    P().adopt_guess(bot.store, H, P().guess(bot.view(str(e["lib"])), store=bot.store, handle=H)[0])
    prof = P().get(bot.store, H)
    for i in prof["interests"]:
        if i["topic"] == "Blender 3D":
            i.update(level=level, confirmed=True, level_from="person")
    P().set_interests(bot.store, H, prof["interests"])
    bot.store.set_prefs(H, tools=["air fryer"])
    return P().get(bot.store, H)


def standing(prof):
    """Everything a request must never change as a side effect."""
    p = prof["prefs"]
    return {k: p.get(k) for k in ("outside", "exclude_platforms", "exclude_kinds", "avoid", "style", "guess_level")} | \
        {"direction": prof["direction"], "topics": sorted(i["topic"] for i in prof["interests"])}


def ask(goal, searches, note=None, **content):
    form = {"intent": "ask", "spec": {"when": {"type": "now"}, "content": dict({"goal": goal, "searches": searches},
                                                                              **content)}}
    return form | ({"profile_note": note} if note else {})


# what the live merge call made of the request: two standing preferences nobody asked for
LIVE_MERGE = {"kind": "both", "outside": True, "exclude_platforms": ["youtube"], "note": "Blender (beginner)"}
BLENDER_NEW = "find me new blender tutorials on YouTube that I haven't seen"


# ======================================= 88. a one-off request changed standing preferences =======================================
def test_88_the_live_request_changes_no_preference_and_says_no_noted_line(rich):
    bot, st = rich["bot"], rich["state"]
    before = standing(with_blender(rich))
    st["answers"]["mvp_profile_merge"] = lambda u: dict(LIVE_MERGE)
    st["answers"]["mvp_compose"] = pick("Low poly island")
    msg = str(say(rich, BLENDER_NEW, ask("new Blender tutorials", ["blender tutorial"], note="Blender (beginner)",
                                         platforms=["youtube"], outside="only")))
    prof = P().get(bot.store, H)
    assert standing(prof) == before and "Noted" not in msg
    assert "Blender (beginner)" not in prof["notes"]
    assert "mvp_profile_merge" not in rich["calls"]   # a note that restates the profile is not merged again


def test_88_a_note_that_is_new_still_cannot_change_a_standing_preference(rich):
    bot, st = rich["bot"], rich["state"]
    before = standing(with_blender(rich))
    st["answers"]["mvp_profile_merge"] = lambda u: dict(LIVE_MERGE, note="likes YouTube tutorials")
    st["answers"]["mvp_compose"] = pick("Low poly island")
    msg = str(say(rich, BLENDER_NEW, ask("new Blender tutorials", ["blender tutorial"], note="likes YouTube tutorials",
                                         platforms=["youtube"], outside="only")))
    prof = P().get(bot.store, H)
    assert "mvp_profile_merge" in rich["calls"]
    assert standing(prof) == before and "Noted" not in msg
    assert prof["notes"] == []   # "likes" is not in the message's own words


@pytest.mark.parametrize("text,goal", [
    ("show me new workouts from YouTube", "new workouts"),
    ("find recipes I haven't cooked", "recipes"),
    ("no YouTube please, only my Instagram saves", "Blender tutorials"),   # a limit on this request only
    # the same with "I" in them, so the interpreter's note survives to the merge call
    ("I want new workouts from YouTube", "new workouts"),
    ("no YouTube this time, I only want my Instagram saves", "Blender tutorials"),
])
def test_88_near_variants_of_a_request_leave_the_preferences_alone(rich, text, goal):
    bot, st = rich["bot"], rich["state"]
    before = standing(with_blender(rich))
    st["answers"]["mvp_profile_merge"] = lambda u: {"kind": "both", "outside": True, "exclude_platforms": ["youtube"],
                                                    "exclude_kinds": ["watch"], "style": "brief",
                                                    "add_topics": ["workouts"], "direction": "get fit",
                                                    "stop_guessing_level": True, "avoid": ["dairy"]}
    st["answers"]["mvp_compose"] = pick("Low poly island")
    msg = str(say(rich, text, ask(goal, [goal], note="wants new things")))
    assert standing(P().get(bot.store, H)) == before and "Noted" not in msg


def test_88_a_level_the_request_states_is_kept_for_its_own_topic(rich):
    bot, st = rich["bot"], rich["state"]
    with_blender(rich, level="new")
    st["answers"]["mvp_profile_merge"] = lambda u: {"kind": "both", "levels": [{"topic": "Blender", "level": "beginner"}],
                                                    "outside": True}
    st["answers"]["mvp_compose"] = pick("Low poly island")
    msg = str(say(rich, "I'm a beginner at Blender, find me a first project",
                  ask("a first Blender project", ["blender project"], note="beginner at Blender")))
    prof = P().get(bot.store, H)
    assert next(i for i in prof["interests"] if i["topic"] == "Blender 3D")["level"] == "beginner"
    assert prof["prefs"].get("outside") is None
    assert "Noted: Blender 3D: a beginner." in msg and "outside your saves" not in msg


def test_88_a_level_for_a_new_topic_lands_on_that_topic_only(rich):
    bot, st = rich["bot"], rich["state"]
    with_blender(rich, level="new")
    st["answers"]["mvp_profile_merge"] = lambda u: {"kind": "both", "levels": [
        {"topic": "guitar", "level": "beginner"}, {"topic": "Blender 3D", "level": "beginner"}],
        "add_topics": ["guitar", "music"], "exclude_platforms": ["instagram"]}
    st["answers"]["mvp_compose"] = lambda u: {"picks": []}
    say(rich, "I'm a beginner at guitar, find me a first song to learn",
        ask("a first guitar song", ["guitar song"], note="beginner at guitar"))
    prof = P().get(bot.store, H)
    levels = {i["topic"]: i.get("level") for i in prof["interests"]}
    assert levels["guitar"] == "beginner" and levels["Blender 3D"] == "new" and "music" not in levels
    assert not prof["prefs"].get("exclude_platforms")


def test_88_a_kit_and_a_usual_time_said_in_a_request_are_kept_a_guessed_one_is_not(rich):
    bot, st = rich["bot"], rich["state"]
    with_blender(rich)
    st["answers"]["mvp_profile_merge"] = lambda u: {"kind": "both", "tools": ["Instant Pot", "stand mixer"],
                                                    "time": "20 minutes", "outside": True}
    st["answers"]["mvp_compose"] = pick("Lemon garlic pasta")
    msg = str(say(rich, "a dinner for my new Instant Pot, I have 20 minutes",
                  ask("a dinner", ["pasta"], note="has an Instant Pot")))
    prefs = P().get(bot.store, H)["prefs"]
    assert prefs["tools"] == ["air fryer", "Instant Pot"] and prefs["time"] == "20 minutes"
    assert prefs.get("outside") is None and "Instant Pot" in msg


def test_88_a_stated_diet_in_a_request_still_counts_a_guessed_avoid_does_not():
    form = P().side_form({"kind": "both", "avoid": ["meat", "gluten"], "outside": True}, "I'm vegetarian now, dinner?")
    assert form["avoid"] == ["meat"] and "outside" not in form
    assert P().side_form({"avoid": ["pork"]}, "I don't eat pork, any ideas?")["avoid"] == ["pork"]
    assert P().side_form({"avoid": ["pork"]}, "pasta ideas please")["avoid"] == []


def test_88_never_use_my_youtube_history_as_a_statement_is_standing(rich):
    bot, st = rich["bot"], rich["state"]
    with_blender(rich)
    st["answers"]["mvp_profile_merge"] = lambda u: {"kind": "about_me", "exclude_platforms": ["youtube"]}
    msg = str(say(rich, "never use my YouTube history", {"intent": "profile_update"}))
    assert P().get(bot.store, H)["prefs"]["exclude_platforms"] == ["youtube"] and "I won't use YouTube" in msg


@pytest.mark.parametrize("text,key,val,kept", [
    ("no YouTube", "exclude_platforms", "youtube", True),
    ("not from YouTube", "exclude_platforms", "youtube", True),
    ("don't show me Instagram", "exclude_platforms", "instagram", True),
    ("without my watch history", "exclude_kinds", "watch", True),
    ("stop using my likes", "exclude_kinds", "like", True),
    ("I mostly watch YouTube", "exclude_platforms", "youtube", False),
    ("show me Instagram stuff", "exclude_platforms", "youtube", False),
    ("my likes are a mess", "exclude_kinds", "like", False),
])
def test_88_an_exclusion_needs_the_message_to_negate_it_in_words(env, text, key, val, kept):
    store = env["bot"].store
    P().apply_merge(store, H, {"kind": "about_me", key: [val]}, text)
    assert (P().get(store, H)["prefs"].get(key) == [val]) is kept


@pytest.mark.parametrize("text,val,kept", [
    ("always add new things from outside my saves", True, True),
    ("from now on show me new stuff too", True, True),
    ("I like new stuff", True, False),
    ("find me new blender tutorials", True, False),
    ("only use my own saves", False, True),
    ("in general stick to what I saved", False, True),
    ("ok", False, False),
])
def test_88_outside_as_a_standing_preference_needs_standing_words(env, text, val, kept):
    store = env["bot"].store
    P().apply_merge(store, H, {"kind": "about_me", "outside": val}, text)
    assert (P().get(store, H)["prefs"].get("outside") is val) is kept


def test_88_a_setup_answer_read_as_only_a_request_changes_no_preference(env):
    store = env["bot"].store
    res = P().apply_merge(store, H, {"kind": "request", "outside": True, "style": "brief",
                                     "exclude_platforms": ["youtube"]}, "always new stuff, no YouTube, keep it brief")
    assert res["changes"] == [] and P().get(store, H)["prefs"] == {}


def test_88_restates_reads_the_profile_in_other_words(rich):
    prof = with_blender(rich)
    assert P().restates(prof, "Blender (beginner)") and P().restates(prof, "has an air fryer")
    assert not P().restates(prof, "Blender (intermediate)")      # a new level is not a restatement
    assert not P().restates(prof, "vegetarian now") and not P().restates(prof, "beginner")


# ======================================= 89. "no, any length" to a preview overwrote rule 1 =======================================
from mvp.tests.test_fixpass5 import MINI, blender, mini_form  # noqa: E402,F401  (blender is a fixture)

CONFIRM = {"intent": "confirm"}
CHAT = {"intent": "chat", "reply": "unused"}


def exports(e):
    """Rule 1 and rule 2: the two export reminders, started with a yes, as the setup does."""
    from mvp.refresh import offer_export_routine
    bot = e["bot"]
    offer_export_routine(bot, H, platforms=["instagram", "youtube"], now=e["clock"][0])
    assert say(e, "yes", CONFIRM).startswith("Done. Next Instagram reminder")
    return snapshot(bot)


def snapshot(bot):
    return [(r["id"], r["text"], json.dumps(r["spec"], sort_keys=True), r["status"], r["next_run_at"])
            for r in bot.store.rules(H)]


def pending_spec(bot):
    row = bot.store.one("SELECT kind, payload FROM pending WHERE handle=?", (H,))
    return (row["kind"], json.loads(row["payload"])) if row else (None, None)


def live_change(number=1, criteria=("any length",), when=None):
    """What the live interpreter returned: change_rule on rule 1, a whole new spec, edits_pending."""
    f = mini_form()
    spec = dict(f["spec"], content=dict(f["spec"]["content"], criteria=list(criteria)))
    if when:
        spec["when"] = when
    return {"intent": "change_rule", "rule_number": number, "edits_pending": True, "spec": spec}


def test_89_no_any_length_to_the_preview_lifts_its_limit_and_leaves_the_reminders_alone(blender):
    bot = blender["bot"]
    before = exports(blender)
    preview = say(blender, MINI, mini_form())
    assert "the closest I have is" in preview
    calls = len(blender["calls"])
    out = say(blender, "no, any length", live_change())
    assert out == "OK, it'll pick any length. Reply YES to start it." and "mvp_interpret" not in blender["calls"][calls:]
    assert snapshot(bot) == before
    kind, payload = pending_spec(bot)
    assert kind == "confirm_rule" and not payload["spec"]["content"].get("criteria")
    started = say(blender, "yes", CONFIRM)
    rules = bot.store.rules(H)
    assert len(rules) == 3 and snapshot(bot)[:2] == before and "each pick may be longer" not in started
    assert rules[2]["text"].endswith(" / any length") and not rules[2]["spec"]["content"].get("criteria")


@pytest.mark.parametrize("reply", ["any length is fine", "no limit on length", "length doesn't matter",
                                   "longer is fine", "nah, any length please"])
def test_89_other_ways_to_say_no_limit_work_on_the_preview_too(blender, reply):
    bot = blender["bot"]
    before = exports(blender)
    say(blender, MINI, mini_form())
    assert say(blender, reply, live_change()) == "OK, it'll pick any length. Reply YES to start it."
    assert snapshot(bot) == before and pending_spec(bot)[0] == "confirm_rule"


def test_89_without_the_offer_state_the_model_change_still_goes_to_the_preview(blender):
    """The offer state is gone (an older preview, or one sent before the start line existed): the interpreter's
    change_rule with edits_pending is applied to the preview, never to rule 1, and "any length" is not a must-have."""
    bot = blender["bot"]
    before = exports(blender)
    say(blender, MINI, mini_form())
    bot.store.set_state(f"lengthout:{H}", None)
    kind, payload = pending_spec(bot)
    payload.pop("length_only", None)
    bot.store.set_pending(H, "confirm_rule", payload, at=blender["clock"][0])
    out = say(blender, "no, any length", live_change())
    assert snapshot(bot) == before and not out.startswith("Changed:")
    kind, payload = pending_spec(bot)
    assert kind == "confirm_rule" and "any length" not in json.dumps(payload["spec"]["content"].get("criteria", []))
    assert payload["text"].startswith(MINI) and "any length" in payload["text"]
    assert len(say(blender, "yes", CONFIRM) and bot.store.rules(H)) == 3 and snapshot(bot)[:2] == before


def test_89_a_change_that_names_no_rule_while_a_preview_waits_never_touches_an_ordinary_rule_1(blender):
    bot = blender["bot"]
    say(blender, "every morning at 7 remind me to stretch", {"intent": "new_rule", "spec": {
        "when": {"type": "schedule", "days": ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"], "time": "07:00"},
        "content": {"source": "note", "text": "stretch"}}})
    before = snapshot(bot)
    say(blender, MINI, mini_form())
    bot.store.set_state(f"lengthout:{H}", None)   # the interpreter's way, not the offer's
    say(blender, "no, make it weekly", live_change(criteria=(), when={"type": "schedule", "days": ["MON"],
                                                                      "time": "09:00"}))
    assert snapshot(bot) == before
    kind, payload = pending_spec(bot)
    assert kind == "confirm_rule" and payload["spec"]["when"]["days"] == ["MON"]
    assert payload["spec"]["content"]["source"] == "library"
    # the same change read without edits_pending, naming no rule: still the preview
    form = dict(live_change(criteria=(), when={"type": "schedule", "days": ["TUE"], "time": "09:00"}), edits_pending=False)
    say(blender, "no, make it tuesdays", form)
    assert snapshot(bot) == before and pending_spec(bot)[1]["spec"]["when"]["days"] == ["TUE"]


def test_89_no_alone_declines_the_preview(blender):
    bot = blender["bot"]
    before = exports(blender)
    say(blender, MINI, mini_form())
    out = say(blender, "no", {"intent": "decline"})
    assert pending_spec(bot)[0] is None and snapshot(bot) == before and "start" in out.lower()


def test_89_change_1_to_any_length_names_the_rule_a_content_rule_changes(blender):
    bot = blender["bot"]
    say(blender, MINI, mini_form())
    say(blender, "yes", CONFIRM)
    out = say(blender, "change 1 to any length", live_change(criteria=("mini", "any length")) | {"edits_pending": False})
    rule = bot.store.rules(H)[0]
    assert out.startswith("Changed: every day at 9am, mini Blender tutorials, any length")
    assert not rule["spec"]["content"].get("criteria") and "any length" in rule["text"]
    from mvp.executor import length_bound
    from mvp.schema import RuleSpec
    assert length_bound(RuleSpec.model_validate(rule["spec"]), rule["text"]) is None


def test_89_change_1_to_any_length_on_a_reminder_is_refused_in_a_plain_sentence(blender):
    bot = blender["bot"]
    before = exports(blender)
    out = say(blender, "change 1 to any length", live_change() | {"edits_pending": False})
    assert out == "Rule 1 is a reminder, so I can only change when it comes. You can also pause it, skip one or stop it."
    assert snapshot(bot) == before
    # its timing may still change, and it keeps its own words
    r1 = bot.store.rules(H)[0]
    spec = dict(r1["spec"], when=dict(r1["spec"]["when"], time="10:00"))
    out = say(blender, "move the instagram one to 10am", {"intent": "change_rule", "rule_number": 1, "spec": spec})
    assert out.startswith("Changed:") and bot.store.rules(H)[0]["spec"]["content"] == r1["spec"]["content"]


def test_89_a_must_have_that_only_says_no_limit_is_never_stored():
    from mvp.interpret import change_guard, no_limit_only
    from mvp.schema import Interpretation
    for cr in ("any length", "any duration", "no time limit", "length doesn't matter"):
        assert no_limit_only(cr), cr
    for cr in ("mini", "under 10 minutes", "ends with a finished model"):
        assert not no_limit_only(cr), cr
    it = Interpretation.model_validate({"intent": "ask", "spec": {"when": {"type": "now"}, "content": {
        "goal": "blender tutorials", "searches": ["blender"], "criteria": ["any length", "ends with a finished model"]}}})
    assert change_guard(it, "blender tutorials, any length").spec.content.criteria == ["ends with a finished model"]


# ======================================= the checker's audit =======================================
def _two_rules(e):
    """Rule 1: a daily reminder in their own words; rule 2: a daily Blender rule (started with a yes)."""
    say(e, "every morning at 7 remind me to stretch", {"intent": "new_rule", "spec": {
        "when": {"type": "schedule", "days": ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"], "time": "07:00"},
        "content": {"source": "note", "text": "stretch"}}})
    say(e, MINI, mini_form())
    say(e, "yes", CONFIRM)
    e["bot"]._wrote_final(H, "feedback on a pick")   # something else was the last write
    e["bot"].store.set_state(f"lastspec:{H}", None)
    return snapshot(e["bot"])


def test_audit_a_rule_number_the_model_filled_alone_never_stops_or_changes_that_rule(blender):
    bot = blender["bot"]
    before = _two_rules(blender)
    bot.store.x("DELETE FROM runs")   # no last answer from either rule
    assert say(blender, "stop it", {"intent": "stop", "rule_number": 1}) == "Which rule? Reply \"my rules\" to see their numbers."
    r1 = bot.store.rules(H)[0]
    moved = {"intent": "change_rule", "rule_number": 1,
             "spec": dict(r1["spec"], when=dict({k: v for k, v in r1["spec"]["when"].items() if k != "time"},
                                                times=["09:00"]))}
    assert say(blender, "make it 9 instead", moved).startswith("Which rule?")
    assert snapshot(bot) == before
    # naming the rule, by its number or its words, works as before
    assert say(blender, "move the stretch one to 9", moved).startswith("Changed:")
    assert bot.store.rules(H)[0]["spec"]["when"]["times"] == ["09:00"]
    assert say(blender, "stop 2", {"intent": "stop", "rule_number": 2}).startswith("Stopped")


def test_audit_the_rule_just_started_needs_no_name(blender):
    bot = blender["bot"]
    _two_rules(blender)
    r2 = bot.store.rules(H)[1]
    bot._wrote_rule(H, "started a rule", r2["id"])
    moved = {"intent": "change_rule", "rule_number": 2,
             "spec": dict(r2["spec"], when=dict({k: v for k, v in r2["spec"]["when"].items() if k != "time"},
                                                times=["10:00"]))}
    assert say(blender, "make it 10 instead", moved).startswith("Changed:")


@pytest.mark.parametrize("text,second,kept", [
    ("find me tacos in Chicago", {"intent": "set_timezone", "timezone": "America/Chicago"}, False),
    ("find me tacos, I'm in Chicago now", {"intent": "set_timezone", "timezone": "America/Chicago"}, True),
    ("a pasta recipe for 8pm", {"intent": "set_quiet_hours", "start": "20:00", "end": "08:00"}, False),
    ("a pasta recipe, and don't message me before 9", {"intent": "set_quiet_hours", "start": "21:00", "end": "09:00"},
     True),
    ("a pasta recipe for the weekend", {"intent": "snooze", "until": "2026-11-16T09:00"}, False),
    ("a pasta recipe for dinner", {"intent": "profile_update"}, False),
])
def test_audit_a_setting_carried_with_a_request_needs_words_for_it(text, second, kept):
    from mvp.interpret import change_guard
    from mvp.schema import Interpretation
    it = Interpretation.model_validate({"intent": "ask", "spec": {"when": {"type": "now"}, "content": {
        "goal": "a recipe", "searches": ["recipe"]}}, "also": second})
    out = change_guard(it, text)
    assert out.intent == "ask" and (out.also is not None) is kept
    # the same with the setting read first
    first = Interpretation.model_validate(dict(second, also={"intent": "ask", "spec": {"when": {"type": "now"},
                                                                                       "content": {"goal": "a recipe",
                                                                                                   "searches": ["recipe"]}}}))
    assert change_guard(first, text).intent == (second["intent"] if kept else "ask")


def test_audit_tacos_in_chicago_leaves_the_time_zone_alone(rich):
    bot, st = rich["bot"], rich["state"]
    st["answers"]["mvp_compose"] = lambda u: {"picks": []}
    zone = bot.store.person(H)["timezone"]
    say(rich, "find me tacos in Chicago", {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {
        "goal": "tacos", "searches": ["tacos"]}}, "also": {"intent": "set_timezone", "timezone": "America/Chicago"}})
    assert bot.store.person(H)["timezone"] == zone


def test_audit_a_level_moves_only_when_the_message_says_too_hard_or_too_easy(rich):
    bot, st = rich["bot"], rich["state"]
    with_blender(rich, level="beginner")
    st["answers"]["mvp_compose"] = pick("Low poly island")
    say(rich, "a blender project", ask("a Blender project", ["blender project"]))
    say(rich, "not this one", {"intent": "feedback", "feedback": "harder"})
    lv = {i["topic"]: i.get("level") for i in P().get(bot.store, H)["interests"]}
    assert lv["Blender 3D"] == "beginner"
    say(rich, "too easy", {"intent": "feedback", "feedback": "harder"})
    lv = {i["topic"]: i.get("level") for i in P().get(bot.store, H)["interests"]}
    assert lv["Blender 3D"] == "intermediate"


# ======================================= live check of finding 88 =======================================
def test_88_live_a_level_said_in_a_request_is_read_by_code_when_the_form_has_no_note(rich):
    """Live: the interpreter's form for "I'm a beginner at guitar, find me a first song to learn" had no note, so
    nothing was learned. Code reads the level the message states, for the topic it names, with no form call."""
    bot, st = rich["bot"], rich["state"]
    with_blender(rich, level="new")
    before = standing(P().get(bot.store, H))
    st["answers"]["mvp_compose"] = lambda u: {"picks": []}
    msg = str(say(rich, "I'm a beginner at guitar, find me a first song to learn",
                  ask("a first guitar song", ["guitar song"])))
    prof = P().get(bot.store, H)
    levels = {i["topic"]: i.get("level") for i in prof["interests"]}
    assert levels["guitar"] == "beginner" and levels["Blender 3D"] == "new"
    assert "mvp_profile_merge" not in rich["calls"] and "Noted: guitar: a beginner." in msg
    assert {k: v for k, v in standing(prof).items() if k != "topics"} == \
        {k: v for k, v in before.items() if k != "topics"}
    # a level already known is not said again
    n = len(rich["calls"])
    msg = str(say(rich, "I'm a beginner at guitar, find me an easy song", ask("an easy guitar song", ["guitar song"])))
    assert "Noted" not in msg and "mvp_profile_merge" not in rich["calls"][n:]


@pytest.mark.parametrize("text,want", [
    ("I'm a beginner at guitar, find me a first song to learn", ("guitar", "beginner")),
    ("I am new to sourdough and want a starter recipe", ("sourdough", "new")),
    ("I'm a total beginner at piano", ("piano", "new")),
    ("im intermediate at chess", ("chess", "intermediate")),
    ("find me guitar songs for beginners", None),
    ("I'm new to it, any tips?", None),
])
def test_88_live_level_stated_reads_only_a_level_said_for_a_named_topic(text, want):
    got = P().level_stated(text)
    assert (got[1:] if got else None) == want


def test_88_live_a_level_for_a_guessed_topic_is_stored_even_when_the_forms_note_restates_the_topic(rich):
    """Live, second run: the guess already held a guitar topic (no level) and the form's note only named the topic
    ("learning guitar"), so the note restated the profile and nothing was stored. The level the message states is
    still read by code, and goes to that topic only."""
    bot, st = rich["bot"], rich["state"]
    with_blender(rich, level="new")
    prof = P().get(bot.store, H)
    P().set_interests(bot.store, H, prof["interests"] + [dict(prof["interests"][1], topic="Guitar playing", level=None,
                                                              confirmed=False, words=["guitar"])])
    st["answers"]["mvp_compose"] = lambda u: {"picks": []}
    msg = str(say(rich, "I'm a beginner at guitar, find me a first song to learn",
                  ask("a first guitar song", ["guitar song"], note="learning guitar")))
    levels = {i["topic"]: i.get("level") for i in P().get(bot.store, H)["interests"]}
    assert levels["Guitar playing"] == "beginner" and levels["Blender 3D"] == "new" and "guitar" not in levels
    assert "mvp_profile_merge" not in rich["calls"] and "Noted: Guitar playing: a beginner." in msg


def test_88_live_a_note_with_more_than_the_level_still_gets_the_form_call_and_only_side_effects(rich):
    bot, st = rich["bot"], rich["state"]
    with_blender(rich, level="new")
    st["answers"]["mvp_profile_merge"] = lambda u: {"kind": "both", "tools": ["ukulele"], "outside": True}
    st["answers"]["mvp_compose"] = lambda u: {"picks": []}
    msg = str(say(rich, "I'm a beginner at guitar and I have a ukulele, find me a first song",
                  ask("a first song", ["guitar song"], note="beginner at guitar, has a ukulele")))
    prof = P().get(bot.store, H)
    assert {i["topic"]: i.get("level") for i in prof["interests"]}["guitar"] == "beginner"
    assert prof["prefs"]["tools"] == ["air fryer", "ukulele"] and prof["prefs"].get("outside") is None
    assert "guitar: a beginner" in msg and "ukulele" in msg
