"""Offline tests for fix pass 5 (live findings of 13 Nov, round 5, after a full setup): one or more tests per finding 84
to 87, each failing without its fix. Synthetic data, a fake model, a fake search pool, a fake YouTube and a fake clock
only; the fixtures come from the earlier test files."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, say  # noqa: E402
from mvp.tests.test_slice5 import yt  # noqa: E402,F401
from mvp.tests.test_slice6 import AllPool, number_of  # noqa: E402

CHICKEN = "convenient chicken and rice recipes"
LEAD = "Rice cooker chicken and rice"
LEAD_TEXT = LEAD + "\nIngredients:\n- 2 cups rice\n- 1 lb chicken thighs\n- 1 tbsp soy sauce\nCook it all in the rice cooker."
ROWS = [   # (id, creator, caption)
    ("c1", "cook_a", LEAD + "\nSo easy."),                                     # a copy with less written out ...
    ("c2", "cook_a", LEAD_TEXT),                                               # ... and the fuller copy
    ("c3", "cook_b", "Easy rice cooker chicken and rice, recipe in the video"),  # the same dish, another creator
    ("c4", "cook_c", "Hainanese chicken rice recipe\nIngredients:\n- 1 whole chicken\n- 2 cups jasmine rice"),
    ("c5", "cook_d", "Chicken fried rice recipe in one pan, with ingredients below"),
    ("c6", "cook_e", "Teriyaki chicken rice bowl recipe for dinner"),
    ("c7", "cook_f", "Lemon pasta for one"),
]


def write_lib(path, rows=ROWS):
    (path / "corpus").mkdir(parents=True)
    with open(path / "corpus" / "items.jsonl", "w") as f:
        for iid, who, cap in rows:
            f.write(json.dumps({"id": iid, "platform": "instagram", "source_url": f"https://example.com/{iid}",
                                "caption": cap, "interaction_kinds": ["share_self"],
                                "platform_data": {"owner_handle": who, "owner_relation": "none"}}) + "\n")
    with open(path / "corpus" / "interactions.jsonl", "w") as f:
        for iid, *_ in rows:
            f.write(json.dumps({"item_id": iid, "kind": "share_self", "at": "2026-07-01T10:00:00+00:00"}) + "\n")
    return path


@pytest.fixture()
def food(env, tmp_path):
    lib = write_lib(tmp_path / "foodlib")
    env["bot"].store.x("UPDATE people SET library=? WHERE handle=?", (str(lib), H))
    env["bot"].pool = AllPool(str(lib))
    env["lib"] = lib
    return env


def chicken_form(count=3, criteria=()):
    return {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {
        "goal": "convenient chicken and rice recipes", "searches": ["chicken and rice"], "criteria": list(criteria),
        "count": count}}}


def has(u, needle):
    return needle.lower() in u.lower()


def pick_of(u, needle, verdict="clear", title=None, **kw):
    return dict({"n": number_of(u, needle), "verdict": verdict, "title": title or needle}, **kw)


LEAD_REASON = {"because": "it uses a rice cooker and gives ingredients and steps for a quick dinner",
               "facts": [{"label": "kit", "quote": "Cook it all in the rice cooker"}]}
LEAD_LINES = ["2 cups rice", "1 lb chicken thighs", "1 tbsp soy sauce"]


def first_call(u):
    """What the live composer did: the lead and the same dish twice (here once more, the copies being one now)."""
    return {"picks": [pick_of(u, LEAD, lines=LEAD_LINES, **LEAD_REASON),
                      pick_of(u, "Easy rice cooker chicken", "close", "Easy rice cooker chicken and rice")],
            "intro": "I've found some convenient chicken and rice recipes for you."}


def second_call(u):
    return {"picks": [pick_of(u, "Hainanese chicken rice", lines=LEAD_LINES),
                      pick_of(u, "Chicken fried rice", title="Chicken fried rice in one pan")]}


def composer(first, second, seen):
    def answer(u):
        seen.append(u)
        return first(u) if has(u, LEAD) else second(u)
    return answer


def steps_of(bot):
    row = bot.store.one("SELECT steps, cost_usd FROM runs WHERE kind='ask' ORDER BY id DESC LIMIT 1")
    return json.loads(row["steps"] or "{}"), row["cost_usd"]


# ======================================= 84. one pick, no reason, no alternatives =======================================
def test_84_copies_of_one_post_reach_the_composer_as_one_the_fuller_one(food):
    seen = []
    food["state"]["answers"]["mvp_compose"] = composer(first_call, second_call, seen)
    say(food, CHICKEN, chicken_form())
    first = seen[0]
    assert first.count("<item>" + LEAD) == 1 and "Cook it all in the rice cooker" in first   # c2 kept, c1 left out
    from mvp.compose import collapse_copies
    view = food["bot"].view(str(food["lib"]))
    three = [view.get("c1"), view.get("c2"), view.get("c1")]
    out, n = collapse_copies(three)
    assert [it.id for it in out] == ["c2"] and n == 2


def test_84_the_founders_example_gets_a_reason_and_two_different_dishes(food):
    seen = []
    food["state"]["answers"]["mvp_compose"] = composer(first_call, second_call, seen)
    msg = say(food, CHICKEN, chicken_form())
    assert len(seen) == 2 and not has(seen[1], LEAD) and not has(seen[1], "Easy rice cooker")   # the remaining ones
    assert "I recommend Rice cooker chicken and rice by @cook_a, which you sent to yourself in July, because it uses " \
           "a rice cooker and gives ingredients." in msg
    assert "Ingredients (3):" in msg and "Or try these:" in msg
    assert "• Hainanese chicken rice" in msg and "• Chicken fried rice in one pan" in msg
    assert "Easy rice cooker chicken and rice" not in msg   # the same dish, with two different ones to show
    steps, cost = steps_of(food["bot"])
    assert steps["copies"] == 1 and steps["second_look"]["merged"] == 2 and steps["second_look"]["candidates"] >= 2
    assert cost >= 0.002   # both composer calls are counted
    # the person reads them in the order they are numbered
    items = food["bot"].store.last_answer(H)["items"]
    assert items == ["c2", "c4", "c5"]


def test_84_an_alternative_of_the_leads_own_dish_gives_way_to_a_different_one(food):
    """(live check of fix pass 5) Three clear picks, one of them the lead's own dish: a second look, and the
    different dish it finds takes that place."""
    seen = []
    food["state"]["answers"]["mvp_compose"] = composer(
        lambda u: {"picks": [pick_of(u, LEAD, lines=LEAD_LINES), pick_of(u, "Hainanese chicken rice"),
                             pick_of(u, "Easy rice cooker chicken", title="Easy rice cooker chicken and rice")]},
        lambda u: {"picks": [pick_of(u, "Chicken fried rice", title="Chicken fried rice in one pan")]}, seen)
    msg = say(food, CHICKEN, chicken_form())
    assert len(seen) == 2 and "Easy rice cooker chicken and rice" not in msg
    assert food["bot"].store.last_answer(H)["items"] == ["c2", "c4", "c5"]
    # with nothing different found, the lead's own dish keeps its place (at most one)
    seen.clear()
    food["state"]["answers"]["mvp_compose"] = composer(
        lambda u: {"picks": [pick_of(u, LEAD, lines=LEAD_LINES), pick_of(u, "Hainanese chicken rice"),
                             pick_of(u, "Easy rice cooker chicken", title="Easy rice cooker chicken and rice")]},
        lambda u: {"picks": []}, seen)
    msg = say(food, CHICKEN + " please", chicken_form())
    assert len(seen) == 2 and msg.count("• Easy rice cooker chicken and rice") == 1


def test_84_the_lead_never_changes_because_of_the_second_call(food):
    seen = []

    def second(u):   # the second look finds one that has the details written out: it still only follows
        return {"picks": [pick_of(u, "Hainanese chicken rice", lines=["1 whole chicken", "2 cups jasmine rice"])]}
    food["state"]["answers"]["mvp_compose"] = lambda u: (seen.append(u), {"picks": [pick_of(u, "Teriyaki chicken")]}
                                                         if has(u, "Teriyaki") else second(u))[1]
    msg = say(food, CHICKEN, chicken_form())
    assert len(seen) == 2 and "I recommend Teriyaki chicken" in msg and "• Hainanese chicken rice" in msg


def test_84_enough_clear_different_picks_make_no_second_call_and_read_as_before(env, tmp_path):
    lib = write_lib(tmp_path / "nocopies", [r for r in ROWS if r[0] != "c1"])
    env["bot"].store.x("UPDATE people SET library=? WHERE handle=?", (str(lib), H))
    env["bot"].pool = AllPool(str(lib))
    food = env
    seen = []
    food["state"]["answers"]["mvp_compose"] = lambda u: (seen.append(u), {"picks": [
        pick_of(u, LEAD, lines=LEAD_LINES, because="it cooks in the rice cooker",
                facts=[{"label": "kit", "quote": "Cook it all in the rice cooker"}]),
        pick_of(u, "Hainanese chicken rice"), pick_of(u, "Chicken fried rice", title="Chicken fried rice in one pan"),
        pick_of(u, "Teriyaki chicken")], "intro": "I've found some convenient chicken and rice recipes for you."})[1]
    msg = say(food, CHICKEN, chicken_form())
    assert len(seen) == 1
    steps, _ = steps_of(food["bot"])
    assert "second_look" not in steps
    # the answer exactly as the code at 8b66b6d gives it for the same input
    assert msg == (
        "I've found some convenient chicken and rice recipes for you.\n\n"
        "I recommend Rice cooker chicken and rice by @cook_a, which you sent to yourself in July, because it cooks in "
        "the rice cooker.\n"
        "https://example.com/c2\n"
        "Ingredients (3):\n• 2 cups rice\n• 1 lb chicken thighs\n• 1 tbsp soy sauce\n\n"
        "Or try these:\n"
        "• Hainanese chicken rice by @cook_c https://example.com/c4\n"
        "• Chicken fried rice in one pan by @cook_d https://example.com/c5\n\n"
        "Or here's a wider selection:\n"
        "• Teriyaki chicken: https://example.com/c6")


def test_84_close_ones_follow_a_clear_lead_under_their_own_heading(food):
    food["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        pick_of(u, LEAD, lines=LEAD_LINES), pick_of(u, "Teriyaki chicken", "close"),
        pick_of(u, "Hainanese chicken rice"), pick_of(u, "Lemon pasta", "close", criteria=[])]} \
        if has(u, LEAD) else {"picks": []}
    msg = say(food, CHICKEN, chicken_form())
    head, close = msg.split("Or these, which are close too:")
    assert "Or try these:\n• Hainanese chicken rice" in head and "Teriyaki" not in head
    assert "• Teriyaki chicken" in close
    assert food["bot"].store.last_answer(H)["items"] == ["c2", "c4", "c6"]   # numbered as shown
    # a pick with any "no" is never shown, beside a clear lead or anywhere
    from mvp.compose import check
    from mvp.schema import RuleSpec
    view = food["bot"].view(str(food["lib"]))
    cands = [view.get(i) for i in ("c2", "c4", "c6")]
    spec = RuleSpec.model_validate({"when": {"type": "now"}, "content": {"goal": "chicken", "searches": ["chicken"], "count": 3,
                                                                         "criteria": ["has rice"]}})
    yes = [{"answer": "yes", "quote": "rice"}]
    r = check({"picks": [{"n": 1, "verdict": "clear", "title": LEAD, "criteria": yes},
                         {"n": 2, "verdict": "close", "title": "Hainanese chicken rice", "criteria": [{"answer": "no"}]},
                         {"n": 3, "verdict": "close", "title": "Teriyaki chicken", "criteria": [{"answer": "unknown"}]}]},
              cands, spec)
    assert [p["item"].id for p in r["picks"]] == ["c2", "c6"]


def test_84_at_most_one_alternative_is_the_leads_own_dish_and_it_goes_last(food):
    from mvp.compose import check, same_dish
    from mvp.schema import RuleSpec
    view = food["bot"].view(str(food["lib"]))
    cands = [view.get(i) for i in ("c2", "c3", "c4", "c5", "c6")]
    spec = RuleSpec.model_validate({"when": {"type": "now"}, "content": {"goal": "chicken", "searches": ["chicken"], "count": 3}})
    raw = {"picks": [{"n": 1, "verdict": "clear", "title": LEAD},
                     {"n": 2, "verdict": "clear", "title": "Easy rice cooker chicken and rice"},
                     {"n": 3, "verdict": "clear", "title": "Hainanese chicken rice"}]}
    r = check(raw, cands, spec)
    assert [p["item"].id for p in r["picks"]] == ["c2", "c4", "c3"]
    assert same_dish({"title": "Chicken and rice"}, {"title": "Easy chicken and rice"})
    assert not same_dish({"title": "Hainanese chicken rice"}, {"title": "One pot chicken and rice"})


def test_84_a_reason_is_trimmed_not_thrown_away():
    from mvp.executor import trim_reason, DETAIL_CLAIM
    facts = {"ingredients": ["x"]}

    def bad(part):
        return any(rx.search(part) and not facts.get(k) for k, rx in DETAIL_CLAIM.items())
    q = ["Cook it all in the rice cooker"]
    assert trim_reason("it uses a rice cooker and gives ingredients and steps for a quick dinner", bad, q) == \
        "it uses a rice cooker and gives ingredients"
    assert trim_reason("it uses a rice cooker", bad, q) == "it uses a rice cooker"        # nothing fails: unchanged
    assert trim_reason("the steps are clear, and it uses a rice cooker", bad, q) == "it uses a rice cooker"
    assert trim_reason("it has step-by-step steps", bad, q) is None                      # nothing left
    assert trim_reason("it has the steps and gives ingredients", bad, q) is None         # no subject left
    assert trim_reason("it has the steps and it is tasty", bad, q) is None               # no backed fact left


def test_84_with_nothing_left_of_the_reason_the_lead_gets_one_code_stands_behind(food):
    food["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [pick_of(
        u, LEAD, lines=LEAD_LINES, because="it gives step-by-step instructions",
        facts=[{"label": "kit", "quote": "Cook it all in the rice cooker"}])]} if has(u, LEAD) else {"picks": []}
    msg = say(food, CHICKEN, chicken_form(count=1))
    assert "which you sent to yourself in July, because the ingredients are written out, with amounts." in msg
    assert "step-by-step" not in msg


# ---------- near-variants ----------
def test_84_all_candidates_copies_of_one_post_give_one_pick_and_no_second_call(env, tmp_path):
    rows = [("c1", "cook_a", LEAD + "\nSo easy."), ("c2", "cook_a", LEAD_TEXT), ("c8", "cook_a", LEAD + "\nAgain."),
            ("c7", "cook_f", "Lemon pasta for one")]
    lib = write_lib(tmp_path / "copies", rows)
    env["bot"].store.x("UPDATE people SET library=? WHERE handle=?", (str(lib), H))
    env["bot"].pool = AllPool(str(lib))
    seen = []
    env["state"]["answers"]["mvp_compose"] = lambda u: (seen.append(u), {"picks": [pick_of(u, LEAD, lines=LEAD_LINES)]})[1]
    msg = say(env, CHICKEN, chicken_form())
    assert len(seen) == 1 and msg.count("Rice cooker chicken and rice") == 1 and "Or try these" not in msg


def test_84_a_second_call_that_returns_nothing_leaves_the_answer(food):
    seen = []
    food["state"]["answers"]["mvp_compose"] = composer(first_call, lambda u: {"picks": []}, seen)
    msg = say(food, CHICKEN, chicken_form())
    assert len(seen) == 2 and "I recommend Rice cooker chicken and rice" in msg
    assert "Or these, which are close too:\n• Easy rice cooker chicken and rice" in msg
    steps, _ = steps_of(food["bot"])
    assert steps["second_look"]["merged"] == 0


@pytest.mark.parametrize("failure", ["cut", "budget"])
def test_84_a_second_call_that_fails_leaves_the_first_answer(food, failure):
    seen = []

    def second(u):
        if failure == "cut":
            raise ValueError("the reply was cut off")
        raise RuntimeError("budget stop: total")
    food["state"]["answers"]["mvp_compose"] = composer(first_call, second, seen)
    msg = say(food, CHICKEN, chicken_form())
    assert len(seen) == 2 and "I recommend Rice cooker chicken and rice" in msg and "close too" in msg
    steps, _ = steps_of(food["bot"])
    assert steps["second_look"]["error"] in ("ComposeCut", "RuntimeError")
    run = food["bot"].store.one("SELECT status FROM runs WHERE kind='ask' ORDER BY id DESC LIMIT 1")
    assert run["status"] == "picked"


def test_84_a_timed_send_with_count_one_never_makes_a_second_call(food):
    from mvp.schema import RuleSpec
    seen = []
    food["state"]["answers"]["mvp_compose"] = lambda u: (seen.append(u), {"picks": []})[1]
    bot = food["bot"]
    spec = RuleSpec.model_validate({"when": {"type": "schedule", "days": ["FRI"], "time": "19:00"}, "content": {
        "goal": "a chicken and rice recipe", "searches": ["chicken and rice"], "count": 1}})
    bot.run(bot.store.person(H), spec, "scheduled")
    assert len(seen) == 2   # the one retry before "nothing" (section 4), and no second look
    row = bot.store.one("SELECT steps FROM runs WHERE kind='scheduled' ORDER BY id DESC LIMIT 1")
    assert "second_look" not in json.loads(row["steps"])


# ======================================= 86. one setup reply, one bot message =======================================
from mvp.tests.test_fixpass2 import CHAT, _to_the_last_message  # noqa: E402
from mvp.tests.test_slice6 import first_requests_answer, rich, start  # noqa: E402,F401

CONFIRM = {"intent": "confirm"}


def _to_contact(e):
    start(e)
    e["state"]["answers"]["mvp_first_requests"] = first_requests_answer
    return say(e, "skip", CHAT)                              # the read: the email and time zone question comes next


@pytest.mark.parametrize("reply", ["skip the email, time zone is fine", "no email, the time zone is right",
                                   "Skip the email. The time zone is correct, thanks"])
def test_86_the_email_and_time_zone_reply_gets_one_message(rich, reply):
    bot, ch = rich["bot"], rich["ch"]
    _to_contact(rich)
    n0, calls = len(ch.outbox), len(rich["calls"])
    rich["state"]["answers"]["mvp_interpret"] = lambda u: CONFIRM   # what the model read it as, live
    bot.on_message(H, reply)
    out = [m[2] for m in ch.outbox[n0:]]
    assert len(out) == 1 and "waiting for a yes" not in out[0] and "export" in out[0]
    assert "mvp_interpret" not in rich["calls"][calls:]          # read by code: no paid call


def test_86_a_contact_reply_with_more_in_it_still_never_says_nothing_is_waiting(rich):
    bot, ch = rich["bot"], rich["ch"]
    _to_contact(rich)
    n0 = len(ch.outbox)
    rich["state"]["answers"]["mvp_interpret"] = lambda u: CONFIRM
    bot.on_message(H, "yes that all sounds fine to me honestly")   # not read by code: the model reads "yes"
    out = [m[2] for m in ch.outbox[n0:]]
    assert len(out) == 1 and "waiting for a yes" not in out[0]


@pytest.mark.parametrize("reply", ["yes set up the export reminders", "sure, remind me", "ok", "yes please set them up"])
def test_86_a_yes_to_the_export_reminders_gets_one_message(rich, reply):
    bot, ch = rich["bot"], rich["ch"]
    _to_the_last_message(rich)
    n0 = len(ch.outbox)
    rich["state"]["answers"]["mvp_interpret"] = lambda u: CONFIRM
    rich["state"]["answers"]["mvp_profile_merge"] = lambda u: {"kind": "request"}
    bot.on_message(H, reply)
    out = [m[2] for m in ch.outbox[n0:]]
    assert len(out) == 1 and out[0].startswith("Done. Next Instagram reminder") and len(bot.store.rules(H)) == 2


def test_86_a_yes_with_a_request_in_it_still_answers_the_request(rich):
    bot, ch = rich["bot"], rich["ch"]
    _to_the_last_message(rich)
    n0 = len(ch.outbox)
    rich["state"]["answers"]["mvp_profile_merge"] = lambda u: {"kind": "request"}
    rich["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [{"n": number_of(u, "Lemon garlic"), "verdict": "clear",
                                                                    "title": "Lemon garlic pasta"}]}
    rich["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {
        "goal": "a pasta recipe", "searches": ["pasta"]}}}
    bot.on_message(H, "yes, and find me a pasta recipe")
    out = [m[2] for m in ch.outbox[n0:]]
    assert out[0].startswith("Done. Next Instagram reminder") and any("Lemon garlic pasta" in m for m in out)
    assert not any("waiting for a yes" in m for m in out)


# ======================================= 85. "new ... that I haven't seen" =======================================
from mvp.tests.test_slice5 import FakeYouTube, video  # noqa: E402

BLENDER_NEW = "find me new blender tutorials on YouTube that I haven't seen"


def blender_form(outside="some"):
    return {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {
        "goal": "new Blender tutorials", "searches": ["blender tutorial"], "platforms": ["youtube"],
        "criteria": ["walks through one whole project from start to finish"], "outside": outside}}}


@pytest.mark.parametrize("text,want", [
    (BLENDER_NEW, "only"),
    ("new pasta recipes I haven't watched", "only"),
    ("workouts I don't already have", "only"),
    ("sourdough videos that aren't in my library", "only"),
    ("find me new blender tutorials", "some"),                              # a plain "new" stays "some"
    ("a blender tutorial I haven't seen in a while", "none"),               # their own saves
    ("a saved video I haven't watched yet", "none"),
    ("pasta recipes, and show me a few new ones from outside my saves", "some"),   # both
])
def test_85_unseen_or_not_from_my_saves_is_new_things_only(text, want):
    from mvp.interpret import profile_guard
    from mvp.schema import Interpretation
    it = Interpretation.model_validate(blender_form(outside="none" if want == "none" else "some"))
    assert profile_guard(it, text, {"prefs": {}}).spec.content.outside == want


def test_85_the_answer_shows_no_pick_from_the_saves_and_no_video_they_have(yt):
    bot = yt["bot"]
    seen = []
    yt["state"]["answers"]["mvp_compose"] = lambda u: (seen.append(u), {"picks": [{"n": 1, "verdict": "clear",
                                                                                   "title": "Already saved video"}]})[1]
    msg = str(say(yt, BLENDER_NEW, blender_form()))
    assert not seen and "I recommend" not in msg and "Already saved" not in msg   # no library pick, no library video
    assert msg.startswith("Here are some new Blender tutorials from YouTube, not from your saves:")
    assert "LIBVID00001" not in msg and "VIDaaaaaa01" in msg


def test_85_outside_picks_for_something_to_make_put_whole_videos_before_tips_and_very_short_ones(yt):
    order = ["VIDshort001", "VIDtips0001", "VIDwhole001", "VIDwhole002"]
    yt["bot"].outside.http = FakeYouTube(order, [
        video("VIDshort001", "Blender donut in 90 seconds", dur="PT1M47S"),
        video("VIDtips0001", "5 Blender shortcuts you need", dur="PT8M"),
        video("VIDwhole001", "Blender low poly house, full tutorial", dur="PT22M"),
        video("VIDwhole002", "Model a chair in Blender", dur="PT12M")])
    msg = str(say(yt, BLENDER_NEW, blender_form()))
    shown = sorted([v for v in order if v in msg], key=msg.index)
    assert shown == ["VIDwhole001", "VIDwhole002", "VIDshort001"]   # a preference: still three picks
    # with only tips left, they are still shown (never fewer picks because of it)
    yt["bot"].outside.http = FakeYouTube(["VIDtips0001"], [video("VIDtips0001", "5 Blender shortcuts you need")])
    yt["bot"].store.x("DELETE FROM outside_cache")
    msg = str(say(yt, BLENDER_NEW + " please", blender_form()))
    assert "VIDtips0001" in msg


# ======================================= 87. a daily "mini" rule where nothing is that short =======================================
MINI = "mini blender tutorials to start doing daily"


@pytest.fixture()
def blender(env, tmp_path):
    lib = tmp_path / "blenderlib"
    (lib / "corpus").mkdir(parents=True)
    rows = [("v1", "VIDblend001", "Blender donut tutorial, full project from start to finish", 1077),
            ("v2", "VIDblend002", "Blender low poly island tutorial", 1500)]
    with open(lib / "corpus" / "items.jsonl", "w") as f:
        for iid, vid, title, dur in rows:
            f.write(json.dumps({"id": iid, "platform": "youtube", "source_url": f"https://www.youtube.com/watch?v={vid}",
                                "caption": title, "interaction_kinds": ["watch"],
                                "platform_data": {"video_id": vid, "owner_name": "Synthetic Channel",
                                                  "owner_relation": "none", "duration_s": dur}}) + "\n")
    with open(lib / "corpus" / "interactions.jsonl", "w") as f:
        for iid, *_ in rows:
            f.write(json.dumps({"item_id": iid, "kind": "watch", "at": "2026-07-01T10:00:00+00:00"}) + "\n")
    env["bot"].store.x("UPDATE people SET library=? WHERE handle=?", (str(lib), H))
    env["bot"].pool = AllPool(str(lib))
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": number_of(u, "donut"), "verdict": "clear", "title": "Blender donut tutorial"}]}
    return env


def mini_form():
    return {"intent": "new_rule", "spec": {"when": {"type": "schedule", "days": ["MON", "TUE", "WED", "THU", "FRI",
                                                                                 "SAT", "SUN"], "time": "09:00"},
                                           "content": {"goal": "mini Blender tutorials", "searches": ["blender tutorial"],
                                                       "criteria": ["mini"], "count": 1}}}


def _start_mini(e):
    preview = say(e, MINI, mini_form())
    assert "None of what I found is under 10 minutes long, so the closest I have is" in preview
    return say(e, "yes", CONFIRM)


def test_87_the_start_line_says_every_pick_may_be_longer_and_offers_the_ways_out(blender):
    started = _start_mini(blender)
    assert started.startswith("Got it: every day at 9am, mini Blender tutorials.")
    assert "nothing I found is under 10 minutes, so each pick may be longer. Say \"any length\" to drop the limit, " \
           "or \"include YouTube\" and I'll look for shorter ones there too." in started


def test_87_any_length_lifts_the_limit_for_that_rule_and_it_sticks(blender):
    bot, clock = blender["bot"], blender["clock"]
    _start_mini(blender)
    calls = len(blender["calls"])
    out = say(blender, "any length", CHAT)
    assert out == "Done: rule 1 now picks any length." and "mvp_interpret" not in blender["calls"][calls:]
    rule = bot.store.rules(H)[0]
    assert rule["text"].endswith(" / any length") and "mini" not in rule["spec"]["content"].get("criteria", [])
    blender["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": number_of(u, "low poly"), "verdict": "clear", "title": "Blender low poly island tutorial"}]}
    from datetime import datetime, timezone
    clock[0] = datetime(2026, 11, 13, 14, 1, tzinfo=timezone.utc)   # 9am New York
    assert bot.tick() == 1
    sent = last(blender["ch"])
    assert "I recommend Blender low poly island tutorial" in sent and "under 10 minutes" not in sent


def test_87_include_youtube_adds_new_videos_to_that_rule(blender):
    bot = blender["bot"]
    _start_mini(blender)
    out = say(blender, "include YouTube", CHAT)
    assert out == "Done: rule 1 now looks on YouTube too, for shorter ones."
    assert bot.store.rules(H)[0]["spec"]["content"]["outside"] == "some"


def test_87_both_replies_work_on_the_preview_too(blender):
    bot = blender["bot"]
    say(blender, MINI, mini_form())
    assert say(blender, "ok, any length", CHAT) == "OK, it'll pick any length. Reply YES to start it."
    started = say(blender, "yes", CONFIRM)
    assert "each pick may be longer" not in started
    assert bot.store.rules(H)[0]["text"].endswith(" / any length")


def test_87_any_length_with_nothing_offered_goes_the_normal_way(blender):
    calls = len(blender["calls"])
    say(blender, "any length", CHAT)
    assert "mvp_interpret" in blender["calls"][calls:]


def test_84_a_lead_whose_quotes_fail_still_gets_a_reason_code_stands_behind(food):
    """(live check of fix pass 5) The composer's reason quoted words the post does not have: the lead, with its
    ingredients shown under it, is not left without a reason."""
    food["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [pick_of(
        u, LEAD, lines=LEAD_LINES, because="it uses a rice cooker", facts=[{"label": "kit", "quote": "an Instant Pot"}])]} \
        if has(u, LEAD) else {"picks": []}
    msg = say(food, CHICKEN, chicken_form(count=1))
    assert "which you sent to yourself in July, because the ingredients are written out, with amounts." in msg
    # no reason at all from the model, or no details shown: nothing is made up
    food["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [pick_of(u, LEAD, lines=LEAD_LINES)]} \
        if has(u, LEAD) else {"picks": []}
    assert "because" not in say(food, CHICKEN + " now", chicken_form(count=1))
    food["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [pick_of(
        u, "Teriyaki", because="it uses a rice cooker", facts=[{"label": "kit", "quote": "an Instant Pot"}])]}
    assert "because" not in say(food, "teriyaki chicken rice", chicken_form(count=1))


# ======================================= checker of fix pass 5 =======================================
DISHES = [("d1", "cook_a", "Chicken rice\nIngredients:\n- 2 cups rice\n- 1 lb chicken"),
          ("d2", "cook_b", "Hainanese chicken rice recipe"),
          ("d3", "cook_c", "Chicken fried rice recipe"),
          ("d4", "cook_d", "Cajun chicken rice bowl")]


def test_check_different_dishes_one_word_apart_stay_and_read_as_before(env, tmp_path):
    """'Hainanese chicken rice' and 'Chicken fried rice' are not the dish 'Chicken rice': three clear, different picks
    are shown as before, with no second composer call."""
    lib = write_lib(tmp_path / "dishes", DISHES)
    env["bot"].store.x("UPDATE people SET library=? WHERE handle=?", (str(lib), H))
    env["bot"].pool = AllPool(str(lib))
    seen = []
    env["state"]["answers"]["mvp_compose"] = lambda u: (seen.append(u), {"picks": [
        {"n": number_of(u, "Chicken rice"), "verdict": "clear", "title": "Chicken rice"},
        pick_of(u, "Hainanese chicken rice"), pick_of(u, "Chicken fried rice")]})[1]
    msg = say(env, CHICKEN, chicken_form())
    assert len(seen) == 1 and "• Hainanese chicken rice" in msg and "• Chicken fried rice" in msg
    from mvp.compose import same_dish
    assert same_dish({"title": "Rice cooker chicken and rice"}, {"title": "Easy chicken and rice"})
    assert same_dish({"title": "One pot chicken and rice"}, {"title": "Chicken & rice bowl"})
    for other in ("Hainanese chicken rice", "Chicken fried rice", "Cajun chicken and rice"):
        assert not same_dish({"title": "Chicken rice"}, {"title": other}), other


def test_check_one_creators_posts_that_open_alike_are_not_copies(env, tmp_path):
    rows = [("h1", "cook_a", "Save this recipe!\nTeriyaki chicken and rice bowls"),
            ("h2", "cook_a", "Save this recipe!\nLemon chicken and rice soup"),
            ("h3", "cook_a", "Chicken and rice meal prep for the whole week, day 1"),
            ("h4", "cook_a", "Chicken and rice meal prep for the whole week, day 2"),
            ("h5", "cook_a", "Dinner tonight\nGarlic butter chicken"),
            ("h6", "cook_a", "Dinner tonight\nChicken curry with rice")]
    lib = write_lib(tmp_path / "hooks", rows)
    from mvp.compose import collapse_copies
    view = env["bot"].view(str(lib))
    out, n = collapse_copies([view.get(r[0]) for r in rows])
    assert n == 0
    out, n = collapse_copies([view.get("h1"), view.get("h1")])   # a real copy still takes one place
    assert n == 1


def test_check_a_second_look_pick_with_a_no_is_never_shown_beside_a_clear_lead(food):
    """The second call's only offer is a pick whose finished-result must-have is "no" (the closest-only tips case):
    it stays out; the first answer goes out as it was."""
    calls = []

    def answer(u):
        calls.append(u)
        if len(calls) == 1:
            return {"picks": [pick_of(u, LEAD, lines=LEAD_LINES, criteria=[{"answer": "yes", "quote": "Cook it all"}])]}
        return {"picks": [pick_of(u, "Hainanese chicken rice", criteria=[{"answer": "no"}])]}
    food["state"]["answers"]["mvp_compose"] = answer
    msg = say(food, CHICKEN, chicken_form(criteria=["ends with a dish you can eat"]))
    assert len(calls) == 2 and "Hainanese" not in msg and "I recommend Rice cooker chicken and rice" in msg


def test_check_a_trimmed_reason_is_never_a_fragment():
    from mvp.executor import DETAIL_CLAIM, trim_reason

    def bad_for(facts):
        return lambda part: any(rx.search(part) and not facts.get(k) for k, rx in DETAIL_CLAIM.items())
    q = ["Ingredients: 2 cups rice", "Cook it in the rice cooker in 15 minutes"]
    no_steps, no_ingredients = bad_for({"ingredients": ["x"]}), bad_for({"steps": ["x"]})
    assert trim_reason("the ingredients and steps are written out", no_steps, q) is None   # not "the ingredients"
    assert trim_reason("it takes 15 minutes, and the steps and ingredients are written out", no_ingredients, q) is None
    # a dropped part that is a verb phrase of its own leaves a whole clause before it
    assert trim_reason("it uses rice, chicken and soy sauce, and gives steps", no_steps, q) == \
        "it uses rice, chicken and soy sauce"
    # what the builder's tests keep is still kept
    assert trim_reason("it uses a rice cooker and gives ingredients and steps for a quick dinner", no_steps,
                       ["Cook it all in the rice cooker"]) == "it uses a rice cooker and gives ingredients"
    assert trim_reason("the steps are clear, and it uses a rice cooker", no_steps, q) == "it uses a rice cooker"


def test_check_any_length_said_twice_to_the_preview_never_turns_youtube_on(blender):
    bot = blender["bot"]
    say(blender, MINI, mini_form())
    say(blender, "any length", CHAT)
    assert say(blender, "any length", CHAT) == "OK, it'll pick any length. Reply YES to start it."
    payload = json.loads(bot.store.one("SELECT payload FROM pending WHERE handle=?", (H,))["payload"])
    assert payload["spec"]["content"].get("outside", "none") == "none"
    assert payload["text"].count("any length") == 1
