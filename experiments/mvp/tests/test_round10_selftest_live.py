"""The first full live self-test of round 10 (18 Nov; DESIGN.md section 17.T, "The first live run") and its fix pass:
the harness's clock at a rule's slot, a daily request read as a daily rule, a model's "now" minute never a rule's
time, an email to a group, and the clumsy lines found in the founder's examples. Offline: fakes only, made-up names and
example.com addresses."""
import json
import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_round10_errand import e, form  # noqa: E402,F401  (e is a fixture)
from mvp.tests.test_round10_selftest import TOUCHED, run, write_convs  # noqa: E402
from mvp.tests.test_mvp import env  # noqa: E402,F401
from mvp.tests.test_slice2 import H, say  # noqa: E402

UNSUP = {"intent": "unsupported", "reply": "I can't do that."}
TZ = "America/New_York"


@pytest.fixture()
def st(tmp_path, monkeypatch):
    for k in TOUCHED:
        monkeypatch.setenv(k, "x")
        monkeypatch.delenv(k)
    monkeypatch.setenv("MVP_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MVP_TOTAL_CAP_USD", "30")
    for m in [m for m in sys.modules if m.startswith("mvp") and not m.startswith("mvp.tests")]:
        del sys.modules[m]
    import mvp.selftest as S
    yield S
    for m in [m for m in sys.modules if m.startswith("mvp") and not m.startswith("mvp.tests")]:
        del sys.modules[m]


def transcript(tmp_path):
    d = tmp_path / "home" / "selftest"
    return "\n".join(p.read_text() for p in sorted(d.glob("*.md")))


SUNDAY_9AM = {"mvp_interpret": {"intent": "new_rule", "spec": {"when": {"type": "schedule", "days": ["SUN"],
                                                                         "times": ["09:00"]},
                                                                "content": {"goal": "3 recipes", "searches": ["recipe"],
                                                                            "count": 3}}}}


def rule_conv(advance, then=()):
    return {"id": "t1", "who": "operator", "needs": ["G"], "setup": {"ticktick": True}, "steps": [
        {"say": "every sunday put 3 recipes you find in my ticktick", "expect": {"pending": "confirm_rule"},
         "dry": SUNDAY_9AM},
        {"say": "yes", "expect": {"rule_made": {"connector": "ticktick"}}},
        {"advance": advance, "expect": {"reply_has": ["to TickTick", "undo"]}}, *then]}


# ---------- the harness's clock (c10, c26, c27) ----------
def test_an_advance_past_a_rule_slot_stops_there_so_the_run_happens(st, tmp_path):
    """Live, the model set 9am; the clock jumped from Tuesday to Sunday 6:05pm and the scheduler skipped the send as
    more than 2 hours late. The advance now stops just after the slot and ticks there."""
    code, c = run(st, tmp_path, "--only", "t1", conv_file=write_convs(tmp_path, [rule_conv("SUN 18:05")]))
    assert code == 0 and c["failed"] == [], c["failed"]


def test_next_run_goes_just_past_the_next_slot_and_undo_is_still_in_time(st, tmp_path):
    undo = {"say": "undo", "expect": {"reply_not": ["nothing from the last 10 minutes"], "reply_has": ["TickTick"]}}
    code, c = run(st, tmp_path, "--only", "t1", conv_file=write_convs(tmp_path, [rule_conv("next run", [undo])]))
    assert code == 0 and c["failed"] == [], c["failed"]


def test_next_run_with_no_rule_fails_the_step(st, tmp_path):
    conv = {"id": "t2", "who": "tester", "needs": [], "steps": [{"advance": "next run", "expect": {}}]}
    code, c = run(st, tmp_path, "--only", "t2", conv_file=write_convs(tmp_path, [conv]))
    assert code == 1 and c["failed"] == ["t2.1"]


def test_what_a_run_says_on_the_way_belongs_to_the_step(st, tmp_path):
    """The counts are taken before the clock moves: the run's line and its adds are this step's."""
    conv = rule_conv("SUN 18:05")
    conv["steps"][2]["expect"]["placed"] = 3
    code, c = run(st, tmp_path, "--only", "t1", conv_file=write_convs(tmp_path, [conv]))
    assert code == 0 and c["by_check"]["placed"] == [1, 1]


def test_the_outside_change_comes_before_the_clock(st):
    """c27: the vendor changes the tool, then the clock reaches the run (which must see the changed tool)."""
    import inspect
    src = inspect.getsource(st.Run.run_step)
    assert src.index('step.get("do")') < src.index("self._advance(") < src.index("self.bot.tick()")


def test_the_conversations_use_next_run_where_a_model_picks_the_time():
    rows = {json.loads(x)["id"]: json.loads(x) for x in open(os.path.join(os.path.dirname(HERE), "selftest",
                                                                           "conversations.jsonl")) if x.strip()}
    assert rows["c10"]["steps"][2]["advance"] == "next run"
    assert rows["c26"]["steps"][4]["advance"] == "next run"
    assert rows["c27"]["steps"][0]["advance"] == "next run"
    assert "on youtube" in rows["c28"]["steps"][2]["say"] and "on youtube" in rows["c34"]["steps"][2]["say"]
    # c07b: either lead, the doubt line always
    exp = rows["c07b"]["steps"][0]["expect"]
    assert "The best match I found is" in exp["reply_any"] and exp["reply_has"] == ["Heads-up"]


# ---------- a daily request is a daily rule's preview (c15) ----------
def settle(raw, text, now=None):
    from mvp.interpret import settle as S
    return S(raw, text, [], now or datetime(2026, 11, 18, 15, 0, tzinfo=timezone.utc), TZ)


ASK = {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {"goal": "mini Blender tutorials",
                                                                       "searches": ["mini blender tutorial"]}}}


@pytest.mark.parametrize("text", [
    "mini blender tutorials to start doing daily",
    "send me mini beginner blender tutorials to start doing daily",
    "short stretches to do every day",
    "beginner sketching exercises to practice daily",
    "mini blender tutorials daily",
])
def test_a_request_to_do_something_daily_is_a_daily_rule(text):
    it = settle(json.loads(json.dumps(ASK)), text)
    assert it.intent == "new_rule"
    w = it.spec.when
    assert w.type == "schedule" and w.days == ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"] and w.times == ["09:00"]


@pytest.mark.parametrize("text", [
    "what can i eat daily for more protein",
    "how do i stretch every day without getting bored?",
    "a stretch to do today, i want to start doing it daily",
    "mini blender tutorials",
    "a daily routine for beginners",
    "any blender tutorials i could do every day?",
])
def test_a_question_or_a_request_for_now_stays_an_answer(text):
    it = settle(json.loads(json.dumps(ASK)), text)
    assert it.intent == "ask" and it.spec.when.type == "now"


def test_a_daily_request_shows_the_rules_preview_and_waits_for_yes(env):
    from mvp.tests.test_slice2 import ask_pasta, lemon_pick
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    out = say(env, "pasta recipes to try every day", ask_pasta())
    assert "Reply YES to start" in out and "every day at 9am" in out.lower()
    assert env["bot"].store.pending(H)["kind"] == "confirm_rule"
    assert not env["bot"].store.rules(H, statuses=("active",))


# ---------- a model's "now" minute is never a rule's time (c26) ----------
NOW_808PM = datetime(2026, 11, 23, 1, 8, tzinfo=timezone.utc)   # Sunday 22 Nov, 8:08pm in New York


def sunday_rule(times):
    return {"intent": "new_rule", "spec": {"when": {"type": "schedule", "days": ["SUN"], "times": times},
                                           "content": {"goal": "recipes", "searches": ["recipe"], "count": 3}}}


@pytest.mark.parametrize("times", [["20:08"], ["20:07"], ["20:10"]])
def test_the_minute_it_is_now_becomes_9am(times):
    it = settle(sunday_rule(times), "every sunday put 3 recipes in my todoist", NOW_808PM)
    assert it.spec.when.times == ["09:00"]


@pytest.mark.parametrize("text,times,want", [
    ("every sunday at 8:08pm put 3 recipes in my todoist", ["20:08"], ["20:08"]),   # they said it
    ("every sunday at this time put 3 recipes in my todoist", ["20:08"], ["20:08"]),
    ("every sunday evening put 3 recipes in my todoist", ["20:08"], ["20:08"]),
    ("every sunday put 3 recipes in my todoist", ["20:30"], ["20:30"]),   # not the minute it is now
    ("every sunday put 3 recipes in my todoist", ["18:00"], ["18:00"]),
])
def test_a_stated_or_other_time_is_kept(text, times, want):
    it = settle(sunday_rule(times), text, NOW_808PM)
    assert it.spec.when.times == want


# ---------- an email to a group (c04) ----------
@pytest.mark.parametrize("to,group", [
    ("everyone in my class", True), ("my whole team", True), ("all my friends", True), ("the class", True),
    ("everybody", True), ("todos en mi clase", True),
    ("my teacher", False), ("jordan", False), ("my team lead", False), ("my mom", False),
])
def test_group_words(to, group):
    from mvp.drafts import is_group
    assert is_group(to) is group


def test_an_email_to_everyone_in_a_class_greets_everyone_and_asks_for_one_address(e):
    form(e, {"errand": "email_other", "to_words": "everyone in my class", "say_words": "the meeting moved"})
    out = say(e, "email everyone in my class that the meeting moved", UNSUP)
    from mvp import texts as T
    assert out == T.DRAFT_WHO_GROUP and "Everyone In My Class" not in out
    d = e["bot"].open_draft(H)
    assert d and d["parts"]["greet_name"] == "everyone" and d["parts"].get("group") is True
    from mvp.drafts import render_body
    assert render_body(d["parts"], "Sam").startswith("Hi everyone,")
    out = say(e, "email it to me", UNSUP)
    assert "Everyone In My Class" not in out and "The draft to everyone is still open" in out


def test_an_email_to_one_person_still_asks_for_their_address(e):
    form(e, {"errand": "email_other", "to_words": "my coach", "say_words": "i'll be late to practice"})
    out = say(e, "can u let my coach know by email that i'll be late to practice", UNSUP)
    assert out.startswith("Who should it go to? Reply with your coach's email address")


# ---------- the clumsy lines in the founder's examples ----------
def _pick(title, platform="instagram", caption="watch the video", facts=None, **kw):
    it = SimpleNamespace(platform=platform, caption=caption, raw_caption=caption, creator="@made_up_demo",
                         media="reel", first_seen=None, kinds=[], dates={})
    return {"item": it, "title": title, "facts": facts or {}, **kw}


def test_a_tutorial_alternative_says_its_steps_are_in_the_video_never_the_recipe():
    from mvp.render import alt_note, code_reason
    p = _pick("Blender tutorial for beginners", facts={"steps": []})
    assert alt_note(p, ["steps"]) == "the steps are in the video"
    assert alt_note(_pick("Pasta night", facts={"ingredients": []}), ["ingredients"]) == "the recipe is in the video"
    assert code_reason(p, ["steps"]) == ""   # never a reason code stands behind
    assert alt_note(p, ["steps"], "es") == "los pasos están en el video"


@pytest.mark.parametrize("line,title,want", [
    ("Accessible component libraries: React Aria and Radix.", "Accessible component libraries", "React Aria and Radix."),
    ("UI library roundup: shadcn/ui, Radix UI and Headless UI", "UI library roundup", "shadcn/ui, Radix UI and Headless UI"),
    ("ui library roundup - shadcn/ui and Radix", "UI library roundup", "shadcn/ui and Radix"),
    ("React Aria and Radix.", "Accessible component libraries", "React Aria and Radix."),
    ("UI library roundup", "UI library roundup", "UI library roundup"),            # nothing after: kept
    ("UI library roundups are great", "UI library roundup", "UI library roundups are great"),
])
def test_a_key_point_never_repeats_the_title(line, title, want):
    from mvp.render import untitled
    assert untitled(line, title) == want


def test_the_key_points_list_and_an_alternative_drop_the_title():
    from mvp.render import alt_note, kind_lines
    p = _pick("Accessible component libraries", facts={"key_points": ["Accessible component libraries: React Aria."]})
    assert alt_note(p, ["items", "key_points"]) == "React Aria."
    assert kind_lines("key_points", p["facts"]["key_points"], pick=p) == ["Key points (1):", "• React Aria."]


def test_a_neutral_title_reads_in_the_middle_of_the_sentence():
    from mvp.render import pick_sentence
    s = pick_sentence("The only match I found is", _pick("A reel from @lol_reels_demo"))
    assert s.startswith("The only match I found is a reel from @lol_reels_demo")
    s = pick_sentence("I recommend", _pick("Lemon pasta"))
    assert s.startswith("I recommend Lemon pasta")


def test_only_doubted_reels_open_with_the_plain_line(st, tmp_path):
    """c07b and c08: the opening never says "I found a pasta recipe" when every fit's caption may not match its
    video, and the neutral title is lower case after the lead."""
    code, c = run(st, tmp_path, "--only", "c07b")
    t = transcript(tmp_path)
    assert code == 0, c["failed"]
    assert "The only match I found is a reel from @lol_reels_daily" in t
    step = t.split("### c07b.1", 1)[1]
    assert "Here's what I found in your saves." in step


def test_the_youtube_lines_a_tester_sees_name_no_operator_part_and_say_what_next():
    from mvp import texts as T
    assert "client" not in T.YT_NOT_SET_UP and "person who runs me" not in T.YT_NOT_SET_UP
    assert T.YT_NOT_SET_UP.endswith(T.YT_FEED)
    assert "\"on youtube\"" in T.YT_NO_YT_PICKS
