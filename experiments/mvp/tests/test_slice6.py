"""Offline tests for slice 6 (DESIGN.md sections 3, 5 and 11): the profile guess on a synthetic library with a fake
model (shares by code, sensitive topics removed even when the model returns them, the cache per library build),
onboarding step by step (skips, a request in the middle, the merge of the person's answer, the email and time zone
step, the export routine and the checked first requests), profile_show and profile_update, the profile reaching the
interpreter and the composer, level feedback, "done", and the finished-result must-have. No network, no real data."""
import json
import os
import re
import sqlite3
import sys
from datetime import timedelta

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, say  # noqa: E402
from mvp import texts as T  # noqa: E402

BLENDER = [
    ("b1", "Blender donut tutorial for absolute beginners, part 1: modeling the donut"),
    ("b2", "Beginner modeling tips in Blender: 5 shortcuts you need"),
    ("b3", "Low poly island in Blender, full tutorial from start to finish render"),
    ("b4", "Blender: model a cosy room step by step for beginners"),
    ("b5", "Blender lighting tricks for better renders"),
]
COOKING = [
    ("k1", "Lemon garlic pasta\nIngredients:\n- 200g spaghetti\n- 2 lemons"),
    ("k2", "One pot chicken pasta and rice, ingredients and method below"),
    ("k3", "Creamy tomato pasta in 15 minutes, recipe in caption"),
    ("k4", "Sourdough loaf from scratch, the whole method"),
]
MONEY = [("m1", "How to invest in index funds as a beginner"), ("m2", "Budget tips: the 50/30/20 rule"),
         ("m3", "Investing mistakes to avoid in your twenties")]
WATCHED = [("y1", "Blender Guru", "Blender beginner tutorial part 2"), ("y2", "Blender Guru", "Blender render settings"),
           ("y3", "Blender Guru", "Blender modeling a chair"), ("y4", "Random Vlogs", "My day in the city")]


def write_library(path):
    (path / "corpus").mkdir(parents=True)
    rows, inter = [], []
    for iid, cap in BLENDER + COOKING + MONEY:
        rows.append({"id": iid, "platform": "instagram", "source_url": f"https://example.com/{iid}", "caption": cap,
                     "interaction_kinds": ["save"], "platform_data": {"owner_handle": "maker", "owner_relation": "none"}})
        inter.append({"item_id": iid, "kind": "save", "at": "2026-10-01T10:00:00+00:00"})
    rows.append({"id": "f1", "platform": "instagram", "source_url": "https://example.com/f1",
                 "caption": "My friend's secret Blender render", "interaction_kinds": ["save"],
                 "platform_data": {"owner_handle": "pal", "owner_relation": "mutual"}})
    for iid, chan, title in WATCHED:
        rows.append({"id": iid, "platform": "youtube", "source_url": f"https://www.youtube.com/watch?v={iid}",
                     "caption": title, "interaction_kinds": ["watch"],
                     "platform_data": {"owner_name": chan, "video_id": iid}})
        inter.append({"item_id": iid, "kind": "watch", "at": "2026-10-02T10:00:00+00:00"})
    with open(path / "corpus" / "items.jsonl", "w") as f:
        f.write("\n".join(json.dumps(r) for r in rows) + "\n")
    with open(path / "corpus" / "interactions.jsonl", "w") as f:
        f.write("\n".join(json.dumps(r) for r in inter) + "\n")
    return path


def lines_of(user):
    """{id: text} for the S and C lines of the guess prompt."""
    return {m.group(1): m.group(2) for m in re.finditer(r"^((?:S|C)\d+)\. .*?<item>(.*?)</item>", user, re.M)}


def fake_guess(user):
    ls = lines_of(user)
    blender = [k for k, t in ls.items() if "blender" in t.lower()]
    cook = [k for k, t in ls.items() if re.search(r"pasta|rice|sourdough", t, re.I)]
    money = [k for k, t in ls.items() if re.search(r"invest|budget", t, re.I)]
    return {"topics": [
        {"topic": "Blender 3D", "items": blender + ["S99", blender[0]], "words": ["blender", "zebra"],
         "level": "new", "level_quote": "for absolute beginners", "why": "Modeling and rendering in Blender."},
        {"topic": "Home cooking", "items": cook, "words": ["pasta"], "level": "advanced",
         "level_quote": "made by a pro chef", "why": "Pasta and bread."},
        {"topic": "Personal finance", "items": money, "words": ["invest"], "level": None, "why": "Saving."},
        {"topic": "Weekend projects", "items": money[:1], "why": "Ways to grow your money."},
    ]}


class AllPool:
    """A search engine that returns every item of the library, in file order (the synthetic library is tiny)."""
    max_resident = 4

    def __init__(self, lib):
        with open(os.path.join(lib, "corpus", "items.jsonl")) as f:
            self.ids = [json.loads(line)["id"] for line in f if line.strip()]
        self.queries = []

    def search(self, lib, q, depth=300):
        self.queries.append(q)
        return {"ids": list(self.ids), "mode": "normal", "cost_usd": 0.0}

    def warm(self, lib):
        pass

    def stop_all(self):
        pass


@pytest.fixture()
def rich(env, tmp_path):
    lib = write_library(tmp_path / "richlib")
    bot = env["bot"]
    bot.store.x("UPDATE people SET library=? WHERE handle=?", (str(lib), H))
    bot.pool = AllPool(str(lib))
    env["state"]["answers"]["mvp_profile_guess"] = fake_guess
    env["lib"] = lib
    return env


def first_requests_answer(user):
    return {"requests": [
        {"text": "a beginner Blender tutorial that ends with a finished model", "goal": "a beginner Blender project",
         "searches": ["blender beginner tutorial", "blender project"], "criteria": ["ends with a finished model"],
         "extract": ["steps"]},
        {"text": "a quilting pattern for my first quilt", "goal": "a quilting pattern", "searches": ["quilting"]},
        {"text": "a pasta recipe for tonight", "goal": "a pasta recipe", "searches": ["pasta recipe"],
         "criteria": ["ends with a dish you can eat"], "extract": ["ingredients", "steps"]},
        {"text": "a low poly Blender scene to model", "goal": "a low poly Blender scene", "searches": ["blender low poly"]},
        {"text": "a fourth one that is never needed", "goal": "blender extra", "searches": ["blender"]},
    ]}


def number_of(user, needle):
    """The candidate number of the item whose text holds `needle`, in a compose prompt."""
    for m in re.finditer(r"^(\d+)\. .*\n<item>(.*?)</item>", user, re.M):
        if needle.lower() in m.group(2).lower():
            return int(m.group(1))
    raise AssertionError(f"{needle} is not a candidate")


def pick(needle, criteria=None, extra=None):
    """A fake composer that picks the candidate whose text holds `needle`."""
    return lambda u: {"picks": [dict({"n": number_of(u, needle), "verdict": "clear", "title": needle},
                                     **({"criteria": criteria} if criteria else {}))]}


# ---------- the guess ----------
def test_the_guess_counts_by_code_removes_sensitive_topics_and_is_cached_per_build(rich):
    from mvp import profile as P
    bot, calls = rich["bot"], rich["calls"]
    seen = []
    rich["state"]["answers"]["mvp_profile_guess"] = lambda u: (seen.append(u), fake_guess(u))[1]
    view = bot.view(str(rich["lib"]))
    result, cost = P.guess(view, store=bot.store, handle=H)
    assert "friend's secret" not in seen[0]                                     # friends' items never reach the model
    assert "<item>" in seen[0] and "C1. YouTube channel <item>Blender Guru</item>, 3 videos watched" in seen[0]
    topics = [i["topic"] for i in result["interests"]]
    assert topics == ["Blender 3D", "Home cooking"]                     # the money topic and its disguise are removed
    assert result["removed"] == 2
    b, k = result["interests"]
    total = len(BLENDER + COOKING + MONEY) + 1                         # 12 kept items and 1 channel in the sample
    assert b["support"] == 6 and b["share"] == round(6 / total, 3)     # 5 posts + the channel; S99 and a repeat ignored
    assert k["support"] == 4 and k["share"] == round(4 / total, 3)
    assert b["words"] == ["blender"]                                    # a word not in its own lines is dropped
    assert b["saved"] == 5 and b["watched"] == 3                         # counted by code over the whole library
    assert b["level"] == "new" and b["quote"] == "for absolute beginners"
    assert k["level"] is None                                           # a level whose quote is not in its lines
    n = calls.count("mvp_profile_guess")
    again, cost2 = P.guess(view, store=bot.store, handle=H)
    assert again["cached"] and cost2 == 0.0 and calls.count("mvp_profile_guess") == n
    with open(rich["lib"] / "corpus" / "items.jsonl", "a") as f:     # a new build of the library: guessed again
        f.write(json.dumps({"id": "b9", "platform": "instagram", "caption": "Blender sculpting basics",
                            "interaction_kinds": ["save"], "platform_data": {}}) + "\n")
    os.utime(rich["lib"] / "corpus" / "items.jsonl", (1, 1))
    bot.views.clear()
    P.guess(bot.view(str(rich["lib"])), store=bot.store, handle=H)
    assert calls.count("mvp_profile_guess") == n + 1


def test_the_sensitive_filter_and_the_read_lines():
    from mvp import profile as P
    for t in ("Personal finance", "Dating advice", "Mental health", "Bible study", "Election news", "Weight loss",
              "LGBT culture", "crypto trading"):
        assert P.sensitive(t), t
    for t in ("Blender 3D", "Home cooking", "Home workouts", "Painting", "Transitions in video editing", "Strength"):
        assert not P.sensitive(t), t
    prof = {"interests": [{"topic": "Blender 3D", "level": "new", "quote": "for beginners", "saved": 47, "watched": 3,
                           "source": "guess", "confirmed": False},
                          {"topic": "Home cooking", "level": None, "saved": 12, "watched": 0, "source": "guess"}],
            "prefs": {}}
    # fix pass 2, finding 41: every topic, in the fewest words
    assert P.read_lines(prof) == ["• Blender 3D: new to it (about 45 saved, 3 watched)", "• Home cooking (12 saved)"]
    prof["prefs"] = {"guess_level": False}                               # "stop guessing my level"
    assert P.read_lines(prof)[0] == "• Blender 3D (about 45 saved, 3 watched)"


# ---------- onboarding ----------
def start(env):
    env["bot"].store.x("UPDATE people SET consent_version=NULL WHERE handle=?", (H,))
    env["bot"].on_message(H, "I agree")
    return last(env["ch"])


def test_onboarding_step_by_step(rich):
    bot, ch, st = rich["bot"], rich["ch"], rich["state"]
    n0 = len(ch.outbox)
    read = start(rich)
    assert read.startswith("Thanks! Here's my read of you from what you've saved and watched:\n"
                           "• Blender 3D: new to it (5 saved, 3 watched)\n"
                           "• Home cooking (4 saved)\n\nDid I get that right?")
    assert "finance" not in read.lower()
    st["answers"]["mvp_profile_merge"] = lambda u: {
        "kind": "about_me", "confirm_topics": ["Home cooking"], "levels": [{"topic": "Blender", "level": "beginner"}],
        "direction": "finish a small Blender scene every week", "tools": ["air fryer", "a pottery wheel"]}
    third = say(rich, "Mostly. I've done the donut already. I want to finish a small Blender scene every week. "
                      "I have an air fryer.", {"intent": "chat", "reply": "unused"})
    assert third.startswith("Thanks. Here's what I have now: You're into Blender 3D (a beginner) and Home cooking. "
                            "You're working toward \"finish a small Blender scene every week\".")
    assert "What's your email address?" in third and "I have you on New York time, where it's 1:00pm now." in third
    from mvp import profile as P
    prof = P.get(bot.store, H)
    assert prof["prefs"]["tools"] == ["air fryer"]                    # "a pottery wheel" is not in their words
    assert prof["interests"][0]["level"] == "beginner" and prof["interests"][0]["confirmed"]
    st["answers"]["mvp_first_requests"] = first_requests_answer
    fourth = say(rich, "it's me@example.com", {"intent": "chat", "reply": "unused"})
    assert fourth.startswith("I saved me@example.com as your email address and sent a 6-digit code to it.")
    assert "(Instagram every 4 weeks, YouTube every 2 months) and send the steps then. OK?" in fourth
    assert ('Or try one of these, picked from your own saves:\n1. "a beginner Blender tutorial that ends with a '
            'finished model"\n2. "a pasta recipe for tonight"\n3. "a low poly Blender scene to model"\n') in fourth
    assert "quilting" not in fourth                                    # nothing in their library: not offered
    assert fourth.endswith(T.PREFS_QUESTION)                           # finding 46: one optional question, last
    assert len(ch.outbox) - n0 == 3            # read, contact, routine (the consent text came before "I agree")
    assert bot.store.email_of(H) == ("me@example.com", False)
    # "2" runs the second request now, with no interpreter call
    st["answers"]["mvp_compose"] = pick("Lemon garlic pasta", criteria=[{"answer": "yes", "quote": "200g spaghetti"}],
                                        extra=[{"answer": "yes", "quote": "200g spaghetti"}])
    calls = len(rich["calls"])
    offer = bot.store.get_state(f"onboard:{H}")
    say(rich, "2", {"intent": "chat", "reply": "unused"})
    assert "mvp_interpret" not in rich["calls"][calls:] and bot.store.last_answer(H)["items"] == ["k1"]
    assert bot.store.get_state(f"onboard:{H}")["step"] == "done"    # fix pass, finding 34: used, so closed
    bot.store.set_state(f"onboard:{H}", offer)                       # (open again, for "every morning")
    # "every morning": a preview of number 1, whose YES also starts the export reminders
    st["answers"]["mvp_compose"] = pick("Low poly island in Blender",
                                        criteria=[{"answer": "yes", "quote": "from start to finish"}])
    preview = say(rich, "every morning", {"intent": "chat", "reply": "unused"})
    assert "Every day at 8am, I'll send 1 pick for \"a beginner Blender project\"" in preview
    assert preview.endswith("(Your export reminders will start with the same YES.)")
    bot.on_message(H, "yes")
    rules = bot.store.rules(H)
    assert len(rules) == 3 and rules[0]["spec"]["when"]["times"] == ["08:00"]
    assert sorted(r["spec"]["content"]["source"] for r in rules) == ["library", "note", "note"]
    assert bot.store.get_state(f"onboard:{H}")["step"] == "done"


def test_every_step_can_be_skipped(rich):
    bot, st = rich["bot"], rich["state"]
    start(rich)
    second = say(rich, "skip", {"intent": "chat", "reply": "unused"})
    assert second.startswith("No problem.\n\nWhat's your email address?")
    st["answers"]["mvp_first_requests"] = lambda u: {"requests": []}
    final = say(rich, "skip", {"intent": "chat", "reply": "unused"})
    assert "Instagram every 4 weeks" in final and final.endswith(T.PREFS_QUESTION)
    assert say(rich, "skip", {"intent": "chat", "reply": "unused"}) == T.PREFS_SKIPPED    # finding 46: skippable too
    assert bot.store.get_state(f"onboard:{H}")["step"] == "done"
    assert "mvp_profile_merge" not in rich["calls"]
    # after the setup, messages go the normal way
    assert say(rich, "thanks", {"intent": "chat", "reply": "Any time."}) == "Any time."


def test_a_guess_that_fails_still_runs_the_setup(env):
    """The basic library fixture has no profile_guess answer: the fake model fails, and step 2 asks without a read."""
    read = start(env)
    assert read.startswith("Thanks! I couldn't get a good read of your library yet.\n\nIn a sentence or two")
    assert env["bot"].store.get_state(f"onboard:{H}")["step"] == "read"


def test_a_request_in_the_middle_is_answered_and_the_setup_goes_on(rich):
    bot, ch, st = rich["bot"], rich["ch"], rich["state"]
    start(rich)
    st["answers"]["mvp_profile_merge"] = lambda u: {"kind": "request"}
    st["answers"]["mvp_compose"] = pick("Lemon garlic pasta")
    pasta = {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {"goal": "a pasta recipe",
                                                                            "searches": ["pasta"]}}}
    n0 = len(ch.outbox)
    again = say(rich, "find me a pasta recipe", pasta)
    texts = [m[2] for m in ch.outbox[n0:]]
    assert any("Lemon garlic pasta" in t for t in texts)                     # the request is answered
    assert again == ("When you're ready: did I get that right, and what are you working toward right now? "
                     "(Or say \"skip\".)")
    assert bot.store.get_state(f"onboard:{H}")["step"] == "read"
    say(rich, "skip", {"intent": "chat", "reply": "unused"})
    # at the email step, "I'm in Chicago" is a request of its own: the time zone changes (and says so), then step 4
    st["answers"]["mvp_first_requests"] = lambda u: {"requests": []}
    n0 = len(ch.outbox)
    say(rich, "I'm in Chicago this week", {"intent": "set_timezone", "timezone": "America/Chicago"})
    texts = [m[2] for m in ch.outbox[n0:]]
    assert texts[0].startswith("OK, I'll use Chicago time from now on") and "Instagram every 4 weeks" in texts[1]


def test_a_person_already_set_up_is_not_onboarded_again_until_they_ask(rich):
    bot = rich["bot"]
    assert say(rich, "hello", {"intent": "chat", "reply": "Hi!"}) == "Hi!"     # consented before slice 6: no setup
    assert bot.store.get_state(f"onboard:{H}") is None
    again = say(rich, "set me up again", {"intent": "chat", "reply": "unused"})
    assert again.startswith("OK, let's set you up again. Here's my read of you")
    assert bot.store.get_state(f"onboard:{H}")["step"] == "read"


def test_the_merge_checks_what_it_stores(rich):
    from mvp import profile as P
    bot = rich["bot"]
    P.adopt_guess(bot.store, H, P.guess(bot.view(str(rich["lib"])), store=bot.store, handle=H)[0])
    msg = "I'm not into cooking any more. Working toward a job in film. Vegetarian. I'm anxious about money."
    res = P.apply_merge(bot.store, H, {
        "kind": "about_me", "drop_topics": ["cooking"], "direction": "a job in film", "avoid": ["meat", "fish"],
        "add_topics": ["origami"], "note": "worries about money", "levels": [{"topic": "Juggling", "level": "advanced"}],
        "style": "brief", "exclude_kinds": ["like", "nonsense"]}, msg)
    prof = P.get(bot.store, H)
    assert [i["topic"] for i in prof["interests"]] == ["Blender 3D"]     # origami and juggling are not in their words
    assert prof["direction"] == "a job in film" and prof["prefs"]["avoid"] == ["meat", "fish"]
    assert prof["prefs"]["style"] == "brief" and prof["prefs"]["exclude_kinds"] == ["like"]
    assert res["skipped_sensitive"] and prof["notes"] == []               # nothing about money is kept
    assert "Home cooking is off your interests" in res["changes"]
    # fix pass 2, finding 38: only the clause that states a condition is left out, never the rest of their goal
    res = P.apply_merge(bot.store, H, {"direction": "cook more at home and manage my diabetes"},
                        "I want to cook more at home and manage my diabetes")
    assert res["skipped_sensitive"] and P.get(bot.store, H)["direction"] == "cook more at home"


# ---------- the profile any time ----------
def test_profile_show_and_update(rich):
    from mvp import profile as P
    bot, st = rich["bot"], rich["state"]
    P.adopt_guess(bot.store, H, P.guess(bot.view(str(rich["lib"])), store=bot.store, handle=H)[0])
    shown = say(rich, "what do you know about me", {"intent": "profile_show"})
    assert shown.startswith("Here's what I know about you:\n• Blender 3D (just starting, my guess, from 5 saved posts "
                            "and 3 watched videos)\n• Home cooking (my guess, from 4 saved posts)")
    assert "Email: none yet." in shown and "Time zone: New York. Quiet hours: from 10pm to 8am." in shown
    st["answers"]["mvp_profile_merge"] = lambda u: {"kind": "about_me",
                                                    "levels": [{"topic": "Blender", "level": "intermediate"}]}
    msg = say(rich, "I'm past beginner at Blender now", {"intent": "profile_update"})
    assert msg == ("Noted: Blender 3D: past the basics. Say \"what do you know about me\" to see it all.")
    st["answers"]["mvp_profile_merge"] = lambda u: {"kind": "about_me", "tools": ["air fryer"]}
    assert say(rich, "I have an air fryer", {"intent": "profile_update"}).startswith("Noted: you have air fryer.")
    st["answers"]["mvp_profile_merge"] = lambda u: {"kind": "about_me", "stop_guessing_level": True}
    assert say(rich, "stop guessing my level", {"intent": "profile_update"}).startswith(
        "Noted: I'll stop guessing your level.")
    shown = say(rich, "what do you know about me", {"intent": "profile_show"})
    assert "• Blender 3D (past the basics, you told me, from 5 saved posts and 3 watched videos)" in shown
    assert "• Home cooking (my guess" in shown                         # finding 39: a topic keeps its counts
    assert "You have air fryer; I don't guess your level." in shown
    # a statement the form cannot use is kept as a note, as before
    st["answers"]["mvp_profile_merge"] = lambda u: {"kind": "about_me"}
    assert say(rich, "I like rainy days", {"intent": "profile_update"}) == \
        "Noted. I'll keep that in mind when I read your requests."
    assert bot.store.profile_notes(H)[-1] == "I like rainy days"


def test_a_profile_note_inside_an_ask_is_merged_and_said(rich):
    st = rich["state"]
    st["answers"]["mvp_profile_merge"] = lambda u: {"kind": "both", "avoid": ["meat"], "note": "vegetarian now"}
    st["answers"]["mvp_compose"] = pick("Lemon garlic pasta")
    ask = {"intent": "ask", "profile_note": "vegetarian", "spec": {"when": {"type": "now"}, "content": {
        "goal": "a dinner idea", "searches": ["pasta"], "avoid": ["meat"]}}}
    msg = say(rich, "I'm vegetarian now, any dinner ideas?", ask)
    assert "I recommend Lemon garlic pasta" in msg
    assert msg.endswith("Noted: you'd rather avoid meat; noted: vegetarian now. Say \"what do you know about me\" to "
                        "see it all.")


# ---------- using it ----------
def test_the_profile_reaches_the_interpreter_and_the_composer(rich):
    from mvp import profile as P
    bot, st = rich["bot"], rich["state"]
    P.adopt_guess(bot.store, H, P.guess(bot.view(str(rich["lib"])), store=bot.store, handle=H)[0])
    bot.store.set_direction(H, "finish a small scene each week")
    seen = []
    chat = lambda u: (seen.append(u), {"intent": "chat", "reply": "Hi"})[1]   # noqa: E731
    say(rich, "a blender scene to model", chat)
    assert "Interests: Blender 3D (new, a guess)." in seen[0] and "Home cooking" not in seen[0]
    assert 'Direction, in their words: "finish a small scene each week".' in seen[0]
    say(rich, "hi", chat)                                       # a message on no topic of theirs gets no profile lines
    assert "Interests:" not in seen[1] and "Direction" not in seen[1]
    say(rich, "an advanced blender scene", chat)                # a level they state wins over the profile's
    assert "Interests: Blender 3D." in seen[2]
    composed = []
    st["answers"]["mvp_compose"] = lambda u: (composed.append(u), {"picks": [{
        "n": number_of(u, "Low poly island"), "verdict": "clear", "title": "Low poly island in Blender",
        "because": "since you're just starting, it walks through a whole scene",
        "facts": [{"label": "whole", "quote": "full tutorial from start to finish"}]}]})[1]
    blender = {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {"goal": "a Blender project",
                                                                              "searches": ["blender project"]}}}
    msg = say(rich, "a blender project please", blender)
    assert "Their level at Blender 3D: just starting (a guess from what they saved)" in composed[0]
    assert "<item>What they are working toward: finish a small scene each week" in composed[0]
    assert "because you're just starting, it walks through a whole scene." in msg
    assert "I'm guessing you're new to Blender 3D; tell me if that's wrong." in msg
    msg = say(rich, "another blender project please", blender)
    assert "I'm guessing" not in msg                                      # once per topic
    # a topic the request is not about gets no level, and a reason that talks about one is replaced by code
    composed.clear()
    st["answers"]["mvp_compose"] = lambda u: (composed.append(u), {"picks": [{
        "n": number_of(u, "Lemon garlic pasta"), "verdict": "clear", "title": "Lemon garlic pasta", "because": "as a beginner you'll like it",
        "facts": [{"label": "pasta", "quote": "Lemon garlic pasta"}]}]})[1]
    msg = say(rich, "pasta?", {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {
        "goal": "a pasta dish", "searches": ["pasta"]}}})
    assert "Their level" not in composed[0] and "as a beginner" not in msg
    assert "because" not in msg


def test_feedback_moves_the_level_and_done_hides_the_item(rich):
    from mvp import profile as P
    bot, st = rich["bot"], rich["state"]
    P.adopt_guess(bot.store, H, P.guess(bot.view(str(rich["lib"])), store=bot.store, handle=H)[0])
    st["answers"]["mvp_compose"] = pick("Blender donut tutorial")
    say(rich, "a blender tutorial", {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {
        "goal": "a Blender tutorial", "searches": ["blender tutorial"]}}})
    st["answers"]["mvp_compose"] = pick("cosy room")   # fix pass, finding 6: one is sent now, in the same reply
    msg = say(rich, "too easy", {"intent": "feedback", "feedback": "harder"})
    assert msg.startswith("Noted, I'll aim higher with Blender 3D: I now have you as a beginner. Here's a harder one:")
    assert "cosy room" in msg
    lv = P.get(bot.store, H)["interests"][0]
    assert lv["level"] == "beginner" and lv["confirmed"] and lv["source"] == "feedback"
    st["answers"]["mvp_compose"] = pick("Low poly island")
    assert say(rich, "too hard", {"intent": "feedback", "feedback": "easier"}).startswith(
        "Noted, I'll keep it simpler with Blender 3D: I now have you as just starting.")
    assert say(rich, "made it!", {"intent": "feedback", "feedback": "done"}) == \
        "Nice! I've marked it as done, so I won't send it again."
    first = bot.store.last_answer(H)["items"][0]
    assert first in bot.store.disliked(H)                                 # never shown again
    seen = []
    st["answers"]["mvp_compose"] = lambda u: (seen.append(u), {"picks": []})[1]
    say(rich, "a blender tutorial", {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {
        "goal": "a Blender tutorial", "searches": ["blender tutorial"]}}})
    assert "Low poly island" not in seen[0]   # the one marked done (sent with "too hard", finding 6)


# ---------- leads to a finished result ----------
def test_the_finished_result_must_have_drops_loose_tips(rich):
    from mvp.compose import check, tips_only
    from mvp.schema import RuleSpec
    bot = rich["bot"]
    view = bot.view(str(rich["lib"]))
    cands = [view.get("b2"), view.get("b3"), view.get("b5")]
    assert tips_only(cands[0].caption) and not tips_only(cands[1].caption) and tips_only(cands[2].caption)
    spec = RuleSpec.model_validate({"when": {"type": "now"}, "content": {
        "goal": "beginner Blender tutorials", "searches": ["blender"], "count": 2,
        "criteria": ["ends with a finished model"]}})
    raw = {"picks": [{"n": 1, "verdict": "clear", "title": "Beginner modeling tips",
                      "criteria": [{"answer": "yes", "quote": "Beginner modeling tips"}]},
                     {"n": 3, "verdict": "close", "title": "Blender lighting tricks", "criteria": [{"answer": "unknown"}]},
                     {"n": 2, "verdict": "clear", "title": "Low poly island in Blender",
                      "criteria": [{"answer": "yes", "quote": "from start to finish"}]}]}
    r = check(raw, cands, spec)
    assert [p["item"].id for p in r["picks"]] == ["b3"] and r["dropped"]["criterion_tips"] == 2
    # a tips request has no such must-have, so tips are fine there
    tips = RuleSpec.model_validate({"when": {"type": "now"}, "content": {"goal": "Blender tips", "searches": ["x"],
                                                                         "count": 2}})
    assert [p["item"].id for p in check(raw, cands, tips)["picks"]] == ["b2", "b3"]
    # both prompts say it
    from mvp import config
    interp = open(os.path.join(config.HERE, "prompts", f"{config.PROMPT_INTERPRET}.md")).read()
    comp = open(os.path.join(config.HERE, "prompts", f"{config.PROMPT_COMPOSE}.md")).read()
    assert "make, cook, build, draw or practise" in interp and "ends with a finished model" in interp
    assert "Tips, tricks, advice, theory, inspiration and recaps get criteria []" in interp
    assert "walks the person through making or doing ONE whole thing from start to finish" in comp


def test_a_daily_beginner_blender_request_never_recommends_tips(rich):
    """Development-style: the request the founder sent, with a fake model that likes the tips post best."""
    st = rich["state"]
    st["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": n, "verdict": "clear", "title": t, "criteria": [{"answer": "yes", "quote": q}, {"answer": "unknown"}]}
        for n, t, q in [(2, "Beginner modeling tips", "Beginner modeling tips"),
                        (1, "Blender donut tutorial", "part 1: modeling the donut"),
                        (3, "Low poly island in Blender", "from start to finish")]]}
    rule = {"intent": "new_rule", "spec": {"when": {"type": "schedule", "days": ["MON", "TUE", "WED", "THU", "FRI",
                                                                                  "SAT", "SUN"], "times": ["08:00"]},
                                           "content": {"goal": "a mini Blender tutorial to do",
                                                       "searches": ["blender beginner tutorial"],
                                                       "criteria": ["ends with a finished model", "suits a beginner"]}}}
    msg = say(rich, "mini blender tutorials to start doing daily", rule)
    assert "Beginner modeling tips" not in msg and "Reply YES to start" in msg


# ---------- stores and the test page ----------
def test_an_old_store_gains_the_profile_column(tmp_path):
    path = tmp_path / "old.sqlite"
    db = sqlite3.connect(path)
    db.executescript("CREATE TABLE people (handle TEXT PRIMARY KEY, name TEXT, library TEXT NOT NULL, timezone TEXT "
                     "NOT NULL, consent_version TEXT, consent_at TEXT, paused INTEGER DEFAULT 0, created_at TEXT);"
                     "INSERT INTO people(handle,library,timezone) VALUES('+1','/x','UTC');")
    db.commit()
    db.close()
    from mvp import profile as P
    from mvp.store import Store
    s = Store(str(path))
    assert s.profile_data("+1") == {} and P.get(s, "+1")["interests"] == []
    P.set_interests(s, "+1", [{"topic": "Blender"}])
    assert P.get(s, "+1")["interests"] == [{"topic": "Blender"}]
    s.delete_person_data("+1")
    assert s.person("+1") is None


def test_the_test_pages_profile_panel_and_start_over(rich):
    from mvp import profile as P
    from mvp.channels.web import WebChannel
    bot = rich["bot"]
    P.adopt_guess(bot.store, H, P.guess(bot.view(str(rich["lib"])), store=bot.store, handle=H)[0])
    bot.store.set_direction(H, "finish a scene a week")
    web = WebChannel(serve=False)
    web.attach(bot)
    bot.channel = web
    try:
        panel = web.state(H)["profile"]
        assert panel["interests"][0] == {"topic": "Blender 3D", "level": "just starting", "confirmed": False,
                                         "counts": "5 saved posts and 3 watched videos"}
        assert panel["direction"] == "finish a scene a week" and panel["email"] is None
        assert panel["timezone"] == "America/New_York" and panel["quiet"] == "from 10pm to 8am"
        web._control({"op": "start_over", "handle": H, "with_welcome": True})
        s = web.state(H)
        assert s["agreed"] is False and s["profile"]["interests"] == []
        assert [m["text"] for m in s["messages"]][0].startswith("Hi! I'm a prototype")   # the setup's first message
        page = open(os.path.join(os.path.dirname(HERE), "channels", "web_page.html")).read()
        assert 'id="profile"' in page and "Start over (runs the setup from its first message)" in page
    finally:
        web.close()


def test_onboarding_offer_expires(rich):
    bot, st = rich["bot"], rich["state"]
    start(rich)
    say(rich, "skip", {"intent": "chat", "reply": "unused"})
    st["answers"]["mvp_first_requests"] = first_requests_answer
    say(rich, "skip", {"intent": "chat", "reply": "unused"})
    assert bot.store.get_state(f"onboard:{H}")["step"] == "offer"
    rich["clock"][0] += timedelta(hours=25)
    assert say(rich, "2", {"intent": "chat", "reply": "Two what?"}) == "Two what?"


# ---------- checker fixes ----------
CHAT = {"intent": "chat", "reply": "unused"}
PASTA = {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {"goal": "a pasta recipe", "searches": ["pasta"]}}}


def test_only_a_bare_yes_confirms_the_read_or_the_time_zone(rich):
    bot, st = rich["bot"], rich["state"]
    from mvp import texts as T
    for s in ("yes", "Yes!", "spot on, thanks!", "Yep, you got it.", "ok"):
        assert T.RIGHT.match(s), s
    for s in ("yes, I'm a beginner", "ok but I'm in Chicago", "yes except cooking", "great idea, find me pasta"):
        assert not T.RIGHT.match(s), s
    start(rich)
    seen = []
    st["answers"]["mvp_profile_merge"] = lambda u: (seen.append(u), {"kind": "about_me", "levels": [
        {"topic": "Blender", "level": "beginner"}]})[1]
    say(rich, "yes, I'm a beginner at Blender", CHAT)   # finding 39: a level goes to the topic they name
    assert seen and P_level(bot) == "beginner"                       # the level they gave is kept
    st["answers"]["mvp_first_requests"] = lambda u: {"requests": []}
    say(rich, "ok but I'm in Chicago", {"intent": "set_timezone", "timezone": "America/Chicago"})
    assert bot.store.person(H)["timezone"] == "America/Chicago"      # not taken as "the time zone is right"


def P_level(bot):
    from mvp import profile as P
    return P.get(bot.store, H)["interests"][0]["level"]


def test_a_person_who_never_answers_is_not_held_in_the_setup(rich):
    bot, st = rich["bot"], rich["state"]
    start(rich)
    rich["clock"][0] += timedelta(hours=25)
    st["answers"]["mvp_compose"] = pick("Lemon garlic pasta")
    msg = say(rich, "find me a pasta recipe", PASTA)
    assert "mvp_profile_merge" not in rich["calls"] and "Lemon garlic pasta" in msg and "When you're ready" not in msg
    assert bot.store.get_state(f"onboard:{H}")["step"] == "done"


def test_the_read_is_asked_again_once_and_not_over_a_question(rich):
    bot, ch, st = rich["bot"], rich["ch"], rich["state"]
    start(rich)
    st["answers"]["mvp_profile_merge"] = lambda u: {"kind": "request"}
    st["answers"]["mvp_compose"] = pick("Lemon garlic pasta")
    assert say(rich, "find me a pasta recipe", PASTA).startswith("When you're ready")
    assert "When you're ready" not in say(rich, "another pasta recipe", PASTA)     # once is enough
    # a request that asks a question of its own: no second question, and the answer goes to it, not the form call
    start(rich)
    clar = {"intent": "clarify", "question": "When does the semester end?", "draft": {
        "intent": "new_rule", "spec": {"when": {"type": "schedule", "days": ["MON"], "time": "08:00"},
                                       "content": {"source": "note", "text": "study"}}}}
    n0 = len(ch.outbox)
    say(rich, "remind me to study every monday until the semester ends", clar)
    assert [m[2] for m in ch.outbox[n0:]] == ["When does the semester end?"]
    merges = rich["calls"].count("mvp_profile_merge")
    seen = []
    say(rich, "June 5", lambda u: (seen.append(u), {"intent": "chat", "reply": "ok"})[1])
    assert seen and rich["calls"].count("mvp_profile_merge") == merges
    assert bot.store.get_state(f"onboard:{H}")["step"] == "read"                 # the setup is still open after it


def test_no_paid_call_from_the_offer_over_the_cap(rich, monkeypatch):
    st = rich["state"]
    start(rich)
    say(rich, "skip", CHAT)
    st["answers"]["mvp_first_requests"] = first_requests_answer
    say(rich, "skip", CHAT)
    from mvp import llm
    monkeypatch.setattr(llm, "spent_today", lambda h, l: 99.0)
    n = len(rich["calls"])
    say(rich, "2", CHAT)
    say(rich, "every morning", CHAT)
    assert rich["calls"][n:] == [] and rich["bot"].store.rules(H) == []


def test_settings_changed_by_the_answer_to_the_read_are_said(rich):
    st = rich["state"]
    start(rich)
    st["answers"]["mvp_profile_merge"] = lambda u: {"kind": "about_me", "confirm_all": True,
                                                    "exclude_kinds": ["like"], "style": "brief"}
    msg = say(rich, "Spot on. Don't use my likes and keep answers short.", CHAT)
    assert msg.startswith("Thanks. Here's what I have now: You're into Blender 3D (just starting) and Home cooking. "
                          "You like brief answers; I won't use your likes.")


def test_more_sensitive_topics_are_removed_also_from_an_older_cached_guess(rich):
    from mvp import profile as P
    for t in ("Day trading", "Forex", "Fat loss", "Keto diet", "Jesus", "Side hustles", "Retirement planning"):
        assert P.sensitive(t), t
    for t in ("Christmas baking", "Woodworking", "Low poly modeling"):
        assert not P.sensitive(t), t
    bot = rich["bot"]
    old = {"interests": [{"topic": t, "share": 0.5, "support": 4, "saved": 4, "watched": 0, "words": [], "level": None,
                          "quote": None, "why": None, "confirmed": False, "source": "guess"}
                         for t in ("Day trading", "Woodworking")]}
    P.adopt_guess(bot.store, H, old)
    assert [i["topic"] for i in P.get(bot.store, H)["interests"]] == ["Woodworking"]


def test_the_finished_result_wording_of_each_topic_is_recognised():
    from mvp.compose import FINISHED
    for cr in ("ends with a finished model", "ends with a dish you can eat", "ends with a finished drawing",
               "a full routine from start to finish"):
        assert FINISHED.search(cr), cr
    for cr in ("suits a complete beginner", "uses whole wheat flour", "under 20 minutes", "suits a beginner"):
        assert not FINISHED.search(cr), cr


def test_delete_my_data_also_drops_the_guess_of_their_library(rich):
    from mvp import profile as P
    bot = rich["bot"]
    P.guess(bot.view(str(rich["lib"])), store=bot.store, handle=H)
    bot.store.upsert_person("+15550002", "B", str(rich["lib"]), "UTC")       # someone else on the same library
    bot.store.delete_person_data(H)
    assert bot.store.q("SELECT key FROM profile_guess")                     # still theirs
    bot.store.delete_person_data("+15550002")
    assert bot.store.q("SELECT key FROM profile_guess") == []


def test_an_address_and_a_request_together(rich):
    bot, st = rich["bot"], rich["state"]
    start(rich)
    say(rich, "skip", CHAT)
    st["answers"]["mvp_first_requests"] = lambda u: {"requests": []}
    seen = []
    say(rich, "me@example.com and I'm in Chicago",
        lambda u: (seen.append(u), {"intent": "set_timezone", "timezone": "America/Chicago"})[1])
    assert seen and "me@example.com" not in seen[0] and "I'm in Chicago" in seen[0]
    assert bot.store.email_of(H) == ("me@example.com", False) and bot.store.person(H)["timezone"] == "America/Chicago"


def test_a_note_in_an_answer_to_the_read_is_merged_once(rich):
    st = rich["state"]
    start(rich)
    st["answers"]["mvp_profile_merge"] = lambda u: {"kind": "both", "avoid": ["meat"]}
    st["answers"]["mvp_compose"] = pick("Lemon garlic pasta")
    say(rich, "I'm vegetarian, find me a pasta recipe", dict(PASTA, profile_note="vegetarian"))
    assert rich["calls"].count("mvp_profile_merge") == 1


def test_that_s_right_confirms_only_the_topics_the_read_showed(rich):
    from mvp import profile as P
    bot = rich["bot"]
    start(rich)
    assert bot.store.get_state(f"onboard:{H}")["shown"] == ["Blender 3D", "Home cooking"]
    have = P.get(bot.store, H)["interests"]
    P.set_interests(bot.store, H, have + [dict(have[1], topic="Woodworking", words=["wood"])])   # a 5th, not shown
    say(rich, "yes", CHAT)
    got = {i["topic"]: i["confirmed"] for i in P.get(bot.store, H)["interests"]}
    assert got == {"Blender 3D": True, "Home cooking": True, "Woodworking": False}
