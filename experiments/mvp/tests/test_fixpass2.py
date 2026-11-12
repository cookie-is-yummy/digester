"""Offline tests for fix pass 2 (live findings of 12 Nov, round 2): one or more tests per finding 38 to 61, each failing
without its fix. Group F is the setup, G answers and rules, H what was left from the first pass. Synthetic data, a fake
model, a fake search pool, a fake YouTube and a fake clock only; the fixtures come from the earlier test files."""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last, pasta_spec  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, ask_pasta, lemon_pick, say  # noqa: E402
from mvp.tests.test_slice3 import add_items  # noqa: E402
from mvp.tests.test_slice4 import ask_with, confirmed, outbox_rows, read_eml  # noqa: E402
from mvp.tests.test_slice5 import standard_fake, yt  # noqa: E402,F401
from mvp.tests.test_slice6 import (AllPool, first_requests_answer, number_of, pick, rich, start,  # noqa: E402,F401
                                   lines_of)
from mvp.tests.test_interpret_round import S, ask as ask_form, rule as rule_form  # noqa: E402

UTC = timezone.utc
CHAT = {"intent": "chat", "reply": "unused"}


def T():
    from mvp import texts
    return texts


def P():
    from mvp import profile
    return profile


def guessed(topic, saved=0, watched=0, level=None, quote=None, words=(), doing=None):
    return {"topic": topic, "share": 0.1, "support": 3, "saved": saved, "watched": watched, "words": list(words),
            "level": level, "quote": quote, "why": None, "doing": doing, "confirmed": False, "source": "guess"}


# ======================================= F. the setup =======================================
def test_38_their_own_goal_is_kept_and_only_a_personal_clause_is_left_out(rich):
    bot = rich["bot"]
    goal = "making short animated videos and eating healthier on a budget"
    res = P().apply_merge(bot.store, H, {"kind": "about_me", "direction": goal}, "I'm working toward " + goal)
    assert P().get(bot.store, H)["direction"] == goal and not res["skipped_sensitive"]
    for g in ("eating healthier", "getting fit", "saving money", "cooking on a budget", "learning to invest",
              "sleeping better"):
        assert not P().stated_sensitive(g), g             # ordinary goals the person states are kept
    for g in ("I was diagnosed with ADHD", "pay off my $4k debt", "grow in my faith at church", "I'm married",
              "vote for my party in the election", "coming out to my parents"):
        assert P().stated_sensitive(g), g
    assert P().keep_stated("cook more at home, pay off my debt and learn Blender") == \
        ("cook more at home and learn Blender", True)


def test_38_42_the_answer_to_the_read_is_one_message_that_keeps_the_goal_and_says_the_left_out_line_once(rich):
    bot, ch, st = rich["bot"], rich["ch"], rich["state"]
    start(rich)
    said = "I'm working toward making short animated videos and eating healthier on a budget, and managing my ADHD"
    st["answers"]["mvp_profile_merge"] = lambda u: {
        "kind": "both", "direction": "making short animated videos and eating healthier on a budget, and managing "
                                     "my ADHD", "note": "diagnosed with ADHD"}
    n0 = len(ch.outbox)
    say(rich, said, {"intent": "profile_update"})   # the interpreter reads it as only about them
    texts = [m[2] for m in ch.outbox[n0:]]
    assert len(texts) == 1                                                  # finding 42: one message, no "Noted:"
    assert ("You're working toward \"making short animated videos and eating healthier on a budget\"."
            in texts[0])                                                    # finding 38: kept, in their words
    assert texts[0].count(T().PROFILE_SENSITIVE) == 1                      # said once
    assert "ADHD" not in texts[0] and "relationships" not in texts[0] and "politics" not in texts[0]
    assert rich["calls"].count("mvp_profile_merge") == 1
    assert P().get(bot.store, H)["notes"] == []


def test_39_a_level_goes_only_to_the_topic_the_person_named(rich):
    bot = rich["bot"]
    P().set_interests(bot.store, H, [guessed("Animation", saved=12, watched=4, words=["blender", "animation"]),
                                     guessed("Home cooking", saved=4, words=["pasta"])])
    msg = "I'm a beginner at Blender"
    P().apply_merge(bot.store, H, {"kind": "about_me", "levels": [{"topic": "Blender", "level": "beginner"}]}, msg)
    P().apply_merge(bot.store, H, {"kind": "about_me", "levels": [{"topic": "Animation", "level": "beginner"}]}, msg)
    got = {i["topic"]: i for i in P().get(bot.store, H)["interests"]}
    assert got["Animation"]["level"] is None and not got["Animation"]["confirmed"]       # untouched
    assert got["Animation"]["saved"] == 12 and got["Animation"]["watched"] == 4         # counts kept
    assert got["Blender"]["level"] == "beginner" and got["Blender"]["source"] == "person"  # added beside it
    shown = P().show_text(P().get(bot.store, H))
    assert "• Animation (my guess, from 12 saved posts and 4 watched videos)" in shown
    assert "• Blender (a beginner, you told me)" in shown
    # a level for a guessed topic they named keeps that topic's counts
    P().apply_merge(bot.store, H, {"levels": [{"topic": "Home cooking", "level": "advanced"}]}, "I've cooked for years")
    P().apply_merge(bot.store, H, {"levels": [{"topic": "cooking", "level": "advanced"}]}, "cooking: advanced")
    shown = P().show_text(P().get(bot.store, H))
    assert "• Home cooking (advanced, you told me, from 4 saved posts)" in shown


def test_40_only_shown_topics_are_confirmed_and_a_confirmed_guess_reads_you_confirmed(rich):
    bot, st = rich["bot"], rich["state"]
    start(rich)
    have = P().get(bot.store, H)["interests"]
    P().set_interests(bot.store, H, have + [guessed("Woodworking", saved=3, words=["wood"])])   # not shown in the read
    st["answers"]["mvp_profile_merge"] = lambda u: {"kind": "about_me", "confirm_all": True}
    say(rich, "mostly right", CHAT)
    shown = P().show_text(P().get(bot.store, H))
    assert "• Blender 3D (just starting, you confirmed it, from 5 saved posts and 3 watched videos)" in shown
    assert "• Home cooking (you confirmed it, from 4 saved posts)" in shown
    assert "• Woodworking (my guess, from 3 saved posts)" in shown
    assert "you told me" not in shown                       # they wrote nothing about any of these


def _many_topics_library(path):
    """Six activities with different numbers of saves (most first: guitar 8 ... chess 3), each save its own line."""
    (path / "corpus").mkdir(parents=True)
    rows, inter = [], []
    sizes = [("guitar", "Guitar riff lesson", 8), ("sourdough", "Sourdough loaf method", 7),
             ("minecraft", "Minecraft castle build", 6), ("pottery", "Pottery bowl throwing", 5),
             ("watercolor", "Watercolor sky study", 4), ("chess", "Chess opening trap", 3)]
    for word, text, n in sizes:
        for k in range(n):
            iid = f"{word}{k}"
            rows.append({"id": iid, "platform": "instagram", "source_url": f"https://example.com/{iid}",
                         "caption": f"{text} number {k}", "interaction_kinds": ["save"],
                         "platform_data": {"owner_handle": f"maker{k}", "owner_relation": "none"}})
            inter.append({"item_id": iid, "kind": "save", "at": "2026-10-01T10:00:00+00:00"})
    with open(path / "corpus" / "items.jsonl", "w") as f:
        f.write("\n".join(json.dumps(r) for r in rows) + "\n")
    with open(path / "corpus" / "interactions.jsonl", "w") as f:
        f.write("\n".join(json.dumps(r) for r in inter) + "\n")
    return path


def _six_topics_guess(user):
    ls = lines_of(user)
    out = []
    for name, word, doing in [("chess", "chess", "following"), ("watercolor skies", "watercolor", "practising"),
                              ("pottery", "pottery", "making"), ("Minecraft builds", "minecraft", "making"),
                              ("sourdough", "sourdough", "collecting"), ("guitar", "guitar", "learning")]:
        out.append({"topic": name, "items": [k for k, t in ls.items() if word in t.lower()], "words": [word],
                    "doing": doing})
    return {"topics": out}   # the smallest first: code puts them in order


@pytest.fixture()
def many(env, tmp_path):
    lib = _many_topics_library(tmp_path / "many")
    bot = env["bot"]
    bot.store.x("UPDATE people SET library=? WHERE handle=?", (str(lib), H))
    bot.pool = AllPool(str(lib))
    env["state"]["answers"]["mvp_profile_guess"] = _six_topics_guess
    env["lib"] = lib
    return env


def test_41_the_read_shows_every_topic_most_saved_first_and_a_direction_to_correct(many):
    from mvp import config
    assert config.PROMPT_PROFILE_GUESS == "profile_guess_v3" and config.PROFILE_MAX_TOPICS == 8
    read = start(many)
    lines = [x for x in read.splitlines() if x.startswith("• ")]
    assert lines == ["• Guitar (8 saved)", "• Sourdough (7 saved)", "• Minecraft builds (6 saved)", "• Pottery (5 saved)",
                     "• Watercolor skies (4 saved)", "• Chess (3 saved)"]                     # all 6, most saved first
    assert "\nIt looks like you're learning guitar and collecting sourdough.\n" in read   # built by code
    say(many, "yes", CHAT)                                  # a bare yes keeps the direction they were shown
    assert P().get(many["bot"].store, H)["direction"] == "learning guitar and collecting sourdough"


def test_41_what_they_chose_to_keep_outweighs_playlists_and_watch_history(env, tmp_path):
    """A library where a few cooking saves sit beside hundreds of newer playlist items and watched channels: every
    save is in the sample (the old sample took the 60 newest of everything kept, so it missed most of them)."""
    lib = tmp_path / "mixed"
    (lib / "corpus").mkdir(parents=True)
    rows, inter = [], []
    for k in range(6):
        rows.append({"id": f"cook{k}", "platform": "instagram", "source_url": f"https://example.com/c{k}",
                     "caption": f"Quick dinner recipe {k}", "interaction_kinds": ["save"], "platform_data": {}})
        inter.append({"item_id": f"cook{k}", "kind": "save", "at": "2025-01-01T10:00:00+00:00"})
    for k in range(300):
        rows.append({"id": f"pl{k}", "platform": "youtube", "source_url": f"https://www.youtube.com/watch?v=p{k}",
                     "caption": f"Game clip {k}", "interaction_kinds": ["playlist"], "platform_data": {}})
        inter.append({"item_id": f"pl{k}", "kind": "playlist", "at": "2026-10-01T10:00:00+00:00"})
    for c in range(20):
        for k in range(3):
            rows.append({"id": f"w{c}_{k}", "platform": "youtube", "source_url": f"https://www.youtube.com/watch?v=w{c}{k}",
                         "caption": f"Stream {c} part {k}", "interaction_kinds": ["watch"],
                         "platform_data": {"owner_name": f"Channel {c}"}})
    with open(lib / "corpus" / "items.jsonl", "w") as f:
        f.write("\n".join(json.dumps(r) for r in rows) + "\n")
    with open(lib / "corpus" / "interactions.jsonl", "w") as f:
        f.write("\n".join(json.dumps(r) for r in inter) + "\n")
    from mvp import config
    items, chans = P().sample(env["bot"].view(str(lib)))
    assert {it.id for it in items if it.id.startswith("cook")} == {f"cook{k}" for k in range(6)}
    assert len(chans) <= config.PROFILE_CHANNELS == 6
    block = P().sample_block(items, chans)
    assert "instagram, saved: <item>Quick dinner recipe" in block and "youtube, in a playlist" in block


def test_42_the_summary_after_the_read_keeps_every_topic_including_the_ones_just_added(rich):
    bot, ch, st = rich["bot"], rich["ch"], rich["state"]
    start(rich)
    have = P().get(bot.store, H)["interests"]
    P().set_interests(bot.store, H, have + [guessed("Woodworking", 3), guessed("Knitting", 3), guessed("Chess", 3)])
    st["answers"]["mvp_profile_merge"] = lambda u: {"kind": "about_me", "add_topics": ["origami"],
                                                    "levels": [{"topic": "Blender", "level": "beginner"}]}
    n0 = len(ch.outbox)
    say(rich, "Also origami, and I'm a beginner at Blender", CHAT)
    texts = [m[2] for m in ch.outbox[n0:]]
    assert len(texts) == 1 and texts[0].startswith(
        "Thanks. Here's what I have now: You're into Blender 3D (a beginner), Home cooking, Woodworking, Knitting, "
        "Chess and origami.")


def _to_the_last_message(e, first=first_requests_answer):
    start(e)
    say(e, "skip", CHAT)                                     # the read
    e["state"]["answers"]["mvp_first_requests"] = first
    return say(e, "skip", CHAT)                              # the email and the time zone


def test_43_44_the_export_offer_is_one_line_its_yes_one_line_and_the_steps_come_with_the_reminder(rich):
    bot, ch, clock = rich["bot"], rich["ch"], rich["clock"]
    final = _to_the_last_message(rich)
    assert "(Instagram every 4 weeks, YouTube every 2 months) and send the steps then. OK?" in final
    assert "takeout.google.com" not in final and "accountscenter" not in final and "\n1. Open" not in final
    n0 = len(ch.outbox)
    bot.on_message(H, "yes")
    assert [m[2] for m in ch.outbox[n0:]] == ["Done. Next Instagram reminder 10 December, next YouTube one 12 January."]
    clock[0] = datetime(2026, 12, 10, 15, 1, tzinfo=UTC)    # 10am New York on 10 December
    bot.tick()
    sent = last(ch)
    assert sent.startswith("Time for a fresh Instagram export. Here's how:")
    assert "https://accountscenter.instagram.com/info_and_permissions/dyi" in sent and "Leave Messages unticked" in sent
    # on request, the steps too
    msg = say(rich, "how do I export my saves again?", {"intent": "library_status"})
    assert "Instagram, every 4 weeks:\n1. Open https://accountscenter" in msg and "YouTube, every 2 months:" in msg
    assert "Instagram, every 4 weeks:" not in say(rich, "did my export come in?", {"intent": "library_status"})


def test_44_every_morning_and_the_reminders_start_with_one_line_for_the_reminders(rich):
    bot, ch, st = rich["bot"], rich["ch"], rich["state"]
    _to_the_last_message(rich)
    st["answers"]["mvp_compose"] = pick("Low poly island in Blender",
                                        criteria=[{"answer": "yes", "quote": "from start to finish"},
                                                  {"answer": "yes", "quote": "for beginners"}])
    say(rich, "every morning", CHAT)
    n0 = len(ch.outbox)
    bot.on_message(H, "yes")
    texts = [m[2] for m in ch.outbox[n0:]]
    assert len(texts) == 2 and texts[0].startswith("Got it: every day at 8am")
    assert texts[1] == "Done. Next Instagram reminder 10 December, next YouTube one 12 January."
    assert len(bot.store.rules(H)) == 3


def test_45_the_setup_closes_once_the_offer_is_used_and_stays_closed(rich):
    bot, st = rich["bot"], rich["state"]
    _to_the_last_message(rich)
    st["answers"]["mvp_compose"] = pick("Lemon garlic pasta")
    say(rich, "2", CHAT)
    assert bot.store.get_state(f"onboard:{H}")["step"] == "done"
    for i in range(6):
        assert say(rich, f"thanks {i}", {"intent": "chat", "reply": f"ok {i}"}) == f"ok {i}"
    assert bot.store.get_state(f"onboard:{H}")["step"] == "done"
    # never used: the answer to the last question and one more message close it as well
    start(rich)
    say(rich, "skip", CHAT)
    say(rich, "skip", CHAT)
    st["answers"]["mvp_profile_merge"] = lambda u: {"kind": "about_me", "time": "20 minutes a day"}
    say(rich, "20 minutes a day", CHAT)
    say(rich, "hello", {"intent": "chat", "reply": "Hi"})
    assert bot.store.get_state(f"onboard:{H}")["step"] == "done"


def test_46_one_optional_question_last_and_the_whole_setup_within_five_short_messages(rich):
    bot, ch, st = rich["bot"], rich["ch"], rich["state"]
    bot.store.x("UPDATE people SET consent_version=NULL WHERE handle=?", (H,))
    n0 = len(ch.outbox)
    bot.on_message(H, "hi")                                              # 1: the consent text
    bot.on_message(H, "I agree")                                         # 2: the read
    st["answers"]["mvp_profile_merge"] = lambda u: {"kind": "about_me", "confirm_all": True,
                                                    "direction": "finish a small Blender scene every week"}
    say(rich, "Yes. I want to finish a small Blender scene every week", CHAT)   # 3: what I have now, email, zone
    st["answers"]["mvp_first_requests"] = first_requests_answer
    final = say(rich, "skip", CHAT)                                      # 4: reminders, first requests, the question
    assert final.endswith(T().PREFS_QUESTION)
    st["answers"]["mvp_profile_merge"] = lambda u: {"kind": "about_me", "avoid": ["mushrooms"],
                                                    "tools": ["Instant Pot"], "time": "20 minutes a day"}
    reply = say(rich, "no mushrooms, I have an Instant Pot, and usually 20 minutes a day", CHAT)   # 5
    assert "you usually have 20 minutes a day" in reply and "you have Instant Pot" in reply
    assert "you'd rather avoid mushrooms" in reply
    prefs = P().get(bot.store, H)["prefs"]
    assert prefs["time"] == "20 minutes a day" and prefs["tools"] == ["Instant Pot"] and prefs["avoid"] == ["mushrooms"]
    texts = [m[2] for m in ch.outbox[n0:]]
    assert len(texts) <= 5 and all(len(t) <= 900 for t in texts), [len(t) for t in texts]
    assert "usually has 20 minutes a day" in "\n".join(P().about_lines(bot.store, H))   # it reaches the interpreter


# ======================================= G. answers and rules =======================================
def test_47_a_reason_that_promises_details_not_shown_is_left_out(env):
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [{
        "n": number_of(u, "Lemon garlic"), "verdict": "clear", "title": "Lemon garlic pasta",
        "because": "it has the ingredients and step-by-step guides", "facts": [{"label": "x", "quote": "2 lemons"}],
        "lines": ["200g spaghetti", "2 lemons"]}]}
    msg = say(env, "a lemon pasta recipe", ask_with(["message.send"], extract=["ingredients", "steps"]))
    assert "I recommend Lemon garlic pasta" in msg and "step-by-step" not in msg and "because" not in msg
    assert "Ingredients (2):" in msg


def test_47_the_email_and_the_calendar_carry_the_same_detail_lines(env):
    bot = env["bot"]
    confirmed(env)
    env["state"]["answers"]["mvp_compose"] = lemon_pick()
    say(env, "lemon pasta, email it and put it on my calendar at 7pm",
        ask_with(["message.send", "email.send", {"action": "calendar.add", "params": {"time": "19:00"}}],
                 extract=["ingredients"]))
    assert "Ingredients (2):\n• 200g spaghetti\n• 2 lemons" in last(env["ch"])
    mail = read_eml([r for r in outbox_rows(bot, "email")][-1]["path"])
    body = mail.get_body(preferencelist=("plain",)).get_content()
    assert "Ingredients (2):\n• 200g spaghetti\n• 2 lemons" in body
    ics = open([r for r in outbox_rows(bot, "calendar")][-1]["path"], encoding="utf-8", newline="").read().replace("\r\n ", "")
    assert "Ingredients (2):\\n• 200g spaghetti\\n• 2 lemons" in ics


def test_48_two_copies_of_one_post_are_one_pick(env):
    copy = "One pot tomato pasta\nIngredients: 200g pasta"
    add_items(env, [{"id": f"dup{k}", "platform": "instagram", "source_url": f"https://example.com/dup{k}",
                     "caption": copy, "interaction_kinds": ["save"], "platform_data": {"owner_handle": "chef"}}
                    for k in (1, 2)])
    env["bot"].pool.search = lambda lib, q, depth=300: {"ids": ["dup1", "dup2", "itm_a"], "mode": "normal",
                                                        "cost_usd": 0.0}
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        {"n": 1, "verdict": "clear", "title": "One pot tomato pasta"},
        {"n": 2, "verdict": "clear", "title": "Tomato pasta in one pot"},
        {"n": 3, "verdict": "clear", "title": "Lemon garlic pasta"}]}
    msg = say(env, "3 pasta recipes", ask_pasta() | {"spec": dict(ask_pasta()["spec"], content=dict(
        ask_pasta()["spec"]["content"], count=3))})
    assert msg.count("tomato pasta") == 1 and "Lemon garlic pasta" in msg
    assert env["bot"].store.last_answer(H)["items"] == ["dup1", "itm_a"]


FOUNDER = "send me mini beginner blender tutorials to start doing daily"


def test_49_timing_words_and_mini_are_never_must_haves():
    form = rule_form({"type": "schedule", "days": ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"], "times": ["08:00"]},
                     goal="mini beginner Blender tutorials",
                     criteria=["daily", "mini", "to start doing", "every day", "ends with a finished model"])
    it = S(form, FOUNDER)
    assert it.spec.content.criteria == ["mini", "ends with a finished model", "suits a beginner"]   # no timing


def test_49_mini_is_the_length_bound_and_never_asked_of_the_composer_or_said_as_unchecked(env):
    seen = []
    env["state"]["answers"]["mvp_compose"] = lambda u: (seen.append(u), {"picks": [
        {"n": number_of(u, "Lemon garlic"), "verdict": "clear", "title": "Lemon garlic pasta",
         "criteria": [{"answer": "yes", "quote": "200g spaghetti"}]}]})[1]
    form = ask_pasta()
    form["spec"]["content"].update(avoid=[], criteria=["mini", "has written ingredients"])
    msg = say(env, "a mini pasta recipe with written ingredients", form)
    assert '"criteria": ["has written ingredients"]' in seen[0]
    assert "mini" not in msg.lower().replace("a mini pasta", "") and "couldn't check" not in msg


def _founder_rule(e, outside="none"):
    spec = {"when": {"type": "schedule", "days": ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"], "times": ["08:00"]},
            "content": {"goal": "mini beginner Blender tutorials", "searches": ["blender beginner tutorial"],
                        "outside": outside}}
    rid = e["bot"].store.add_rule(H, FOUNDER, spec, "active", "2026-11-13T13:00:00+00:00",
                                  created_at="2026-11-12T18:00:00+00:00")
    return rid, spec


def test_50_51_a_change_says_what_changed_and_the_rule_keeps_its_own_words_for_its_search(yt):
    bot = yt["bot"]
    rid, spec = _founder_rule(yt)
    new = json.loads(json.dumps(spec))
    new["content"]["outside"] = "only"
    msg = say(yt, "only new ones, not from my saves", {"intent": "change_rule", "rule_number": 1, "spec": new})
    assert msg == "Changed: every day at 8am, mini beginner Blender tutorials, now from YouTube, outside your saves."
    assert bot.store.rule(rid)["text"] == FOUNDER + " / only new ones, not from my saves"
    yt["clock"][0] = datetime(2026, 11, 13, 13, 1, tzinfo=UTC)
    assert bot.tick() == 1
    sent = last(yt["ch"])
    assert T().OUTSIDE_NO_WORDS not in sent and "Not from your saves, but close to them:" in sent
    q = yt["yt"].searches()[-1][1]["q"]
    assert "blender" in q.lower() and "new" not in q.split()


def test_52_too_hard_something_shorter_read_as_plain_dislike_still_sends_an_easier_shorter_one(rich):
    bot, st = rich["bot"], rich["state"]
    st["answers"]["mvp_compose"] = pick("Low poly island")
    say(rich, "a blender tutorial", {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {
        "goal": "a Blender tutorial", "searches": ["blender tutorial"]}}})
    st["answers"]["mvp_compose"] = pick("cosy room")
    msg = say(rich, "too hard, something shorter", {"intent": "feedback", "feedback": "down"})
    assert "Here's a shorter, easier one:" in msg and "cosy room" in msg and "Ask for" not in msg
    assert bot.store.one("SELECT kind FROM feedback ORDER BY id DESC LIMIT 1")["kind"] == "easier"


def test_53_54_kit_they_have_lifts_picks_is_never_a_must_have_and_is_said_when_it_fits(env):
    add_items(env, [{"id": "itm_ip", "platform": "instagram", "source_url": "https://example.com/itm_ip",
                     "caption": "Vegetarian lentil curry in the Instant Pot", "interaction_kinds": ["save"],
                     "platform_data": {"owner_handle": "chef"}},
                    {"id": "itm_sf", "platform": "instagram", "source_url": "https://example.com/itm_sf",
                     "caption": "Vegetarian veggie stir fry", "interaction_kinds": ["save"],
                     "platform_data": {"owner_handle": "wok"}}])
    env["bot"].pool.search = lambda lib, q, depth=300: {"ids": ["itm_sf", "itm_ip"], "mode": "normal", "cost_usd": 0.0}
    seen = []

    def composer(u):
        seen.append(u)
        crit = json.loads(u.split("\n")[0][len("Request: "):])["criteria"]
        picks = []
        for needle in ("lentil curry", "stir fry"):
            n = number_of(u, needle)
            ans = [{"answer": "no"} if "instant pot" in c.lower() and needle == "stir fry" else
                   {"answer": "yes", "quote": "Vegetarian"} for c in crit]
            picks.append({"n": n, "verdict": "clear", "title": needle.title(), "criteria": ans})
        return {"picks": picks}
    env["state"]["answers"]["mvp_compose"] = composer
    form = {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {
        "goal": "a vegetarian dinner for tonight", "searches": ["vegetarian dinner"], "count": 2,
        "criteria": ["uses an instant pot", "vegetarian"], "avoid": ["meat"]}}}
    msg = say(env, "I have an instant pot and I'm vegetarian now. what should I cook tonight?", form)
    assert '"criteria": ["vegetarian"]' in seen[0]                         # the kit is not a must-have
    assert number_of(seen[0], "lentil curry") == 1                         # it lifts the pick that uses it
    assert "I recommend Lentil Curry" in msg and "because it uses your instant pot" in msg   # finding 54
    assert "Stir Fry" in msg                                               # the other one is still shown
    from mvp.executor import kit_words
    assert kit_words("I have an Instant Pot and I've got a new air fryer now") == ["instant pot", "air fryer"]
    assert kit_words("I have a party tonight, finger food?") == [] and kit_words("I have a question") == []


def test_54_the_profile_level_is_said_only_when_it_chose_the_pick(rich):
    from mvp import profile as Pm
    bot, st = rich["bot"], rich["state"]
    Pm.adopt_guess(bot.store, H, Pm.guess(bot.view(str(rich["lib"])), store=bot.store, handle=H)[0])
    st["answers"]["mvp_compose"] = pick("Blender donut tutorial")
    blender = {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {"goal": "a Blender project",
                                                                              "searches": ["blender project"]}}}
    assert "because it's good for a beginner" in say(rich, "a blender project please", blender)
    blender["spec"]["content"]["goal"] = "a beginner Blender project"
    assert "good for a beginner" not in say(rich, "a beginner blender project please", blender)   # they named it
    st["answers"]["mvp_compose"] = pick("Lemon garlic pasta")
    msg = say(rich, "pasta?", {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {
        "goal": "a pasta dish", "searches": ["pasta"]}}})
    assert "because" not in msg                                            # nothing from the profile chose it


def test_55_on_the_test_page_an_outside_video_is_one_card_with_its_channel_and_length(yt):
    from mvp.channels.web import WebChannel
    bot = yt["bot"]
    web = WebChannel(serve=False)
    web.attach(bot)
    bot.channel = web
    try:
        yt["state"]["answers"]["mvp_compose"] = lemon_pick()
        yt["state"]["answers"]["mvp_interpret"] = lambda u: dict(ask_pasta(), spec=dict(ask_pasta()["spec"], content=dict(
            ask_pasta()["spec"]["content"], outside="some")))
        bot.on_message(H, "lemon pasta, and some new ones from outside my saves")
        msgs = web.threads[H]
        cards = [m["link"] for m in msgs if m.get("link") and m["link"].get("outside")]
        assert cards and cards[0]["channel"] == "Cook &amp; Co" and cards[0]["length"] == "9 minutes 40 seconds"
        assert not any(m["text"].startswith("• One Pot Chicken") for m in msgs if not m.get("link"))
        page = open(os.path.join(os.path.dirname(HERE), "channels", "web_page.html")).read()
        assert "[l.channel, l.length]" in page
    finally:
        web.close()
    # a channel without cards still gets the line
    from mvp.channels.console import ConsoleChannel
    bot.channel = ConsoleChannel(printer=None)
    bot.on_message(H, "lemon pasta, and some new ones from outside my saves please")
    assert "• One Pot Chicken" in bot.channel.outbox[-1][2] or "One Pot Chicken" in str(yt["replies"][-1])


def test_56_the_calendar_link_is_a_card_on_the_test_page_with_the_ics_beside_it(env):
    from mvp.channels.web import WebChannel
    bot = env["bot"]
    web = WebChannel(serve=False)
    web.attach(bot)
    bot.channel = web
    try:
        env["state"]["answers"]["mvp_compose"] = lemon_pick()
        form = ask_with(["message.send", {"action": "calendar.add", "params": {"time": "19:00"}}])
        env["state"]["answers"]["mvp_interpret"] = lambda u: form
        bot.on_message(H, "lemon pasta on my calendar at 7pm")
        msgs = web.threads[H]
        cal = [m["link"] for m in msgs if m.get("link") and m["link"].get("platform") == "calendar"]
        assert cal and cal[0]["event_title"] == "Lemon garlic pasta" and cal[0]["when"] == "today at 7pm"
        ics = outbox_rows(bot, "calendar")[-1]
        assert cal[0]["outbox_id"] == ics["id"]
        line = [m["text"] for m in msgs if not m.get("link")][-1]
        assert line.endswith('on your calendar today at 7pm, tap this link:') and "https://" not in line
        page = open(os.path.join(os.path.dirname(HERE), "channels", "web_page.html")).read()
        assert 'l.platform === "calendar"' in page and "Add to Google Calendar" in page and 'class="embed ics"' in page
    finally:
        web.close()


def test_57_outside_search_asks_youtube_for_the_length_and_drops_what_breaks_it(yt):
    from mvp.outside import video_duration
    assert (video_duration(3), video_duration(10), video_duration(20), video_duration(45), video_duration(None)) == \
        ("short", "medium", "medium", None, None)
    yt["state"]["answers"]["mvp_compose"] = lemon_pick()
    form = ask_pasta()
    form["spec"]["content"].update(goal="Blender tutorials", searches=["blender tutorials"], outside="only")
    msg = say(yt, "new blender tutorials under 10 minutes", form)
    params = yt["yt"].searches()[-1][1]
    assert params["videoDuration"] == "medium"
    assert "Lemon Pasta in 15 Minutes" not in msg and "Garlic Butter Pasta" not in msg      # 15 and 65 minutes
    assert "One Pot Chicken" in msg and "(9 minutes 40 seconds)" in msg


def test_59_a_rule_with_a_length_bound_never_sends_a_longer_video(yt):
    bot = yt["bot"]
    spec = {"when": {"type": "schedule", "days": ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"], "times": ["08:00"]},
            "content": {"goal": "mini Blender tutorials", "searches": ["blender tutorial"], "outside": "only"}}
    bot.store.add_rule(H, "send me mini blender tutorials from youtube every day", spec, "active",
                       "2026-11-13T13:00:00+00:00", created_at="2026-11-12T18:00:00+00:00")
    for day in (13, 14):
        yt["clock"][0] = datetime(2026, 11, day, 13, 1, tzinfo=UTC)
        bot.tick()
    first, second = [str(r) for r in yt["replies"][-2:]]
    assert "VIDaaaaaa01" in first and "VIDaaaaaa04" in first and "VIDaaaaaa03" not in first
    assert "VIDaaaaaa03" not in second and "VIDaaaaaa02" not in second                       # 65 and 15 minutes
    assert "There's no new one on YouTube under 10 minutes today, so I didn't send a longer one." in second


# ======================================= H. left over =======================================
def test_58_a_level_word_in_their_message_is_a_must_have_or_given_to_the_composer(env):
    it = S(ask_form("a photo editing tutorial", platforms=["youtube"], criteria=["ends with a finished result"]),
           "Find me a beginner photo editing tutorial on YouTube")
    assert "suits a beginner" in it.spec.content.criteria
    it = S(ask_form("a cake"), "an easy cake I can bake")
    assert it.spec.content.criteria == []                     # "easy" is the level given to the composer (below)
    it = S(ask_form("a craft"), "a craft for kids")
    assert it.spec.content.criteria == ["suits kids"]
    it = S(ask_form("a Blender project", criteria=["suits a complete beginner"]), "a blender project for a beginner")
    assert it.spec.content.criteria == ["suits a complete beginner"]   # already there: not twice
    from mvp import profile as Pm
    text, _, _ = Pm.composer_context(env["bot"].store, H, "easy pasta recipes")
    assert "The level they asked for, in their words: easy" in text


def test_60_random_one_is_the_order_not_the_timing():
    it = S(ask_form("a recipe"), "send me a random recipe from my saves")
    assert it.spec.content.order == "random" and it.spec.when.type == "now"
    it = S(ask_form("a workout"), "surprise me with any workout")
    assert it.spec.content.order == "random"
    assert S(ask_form("a recipe"), "the best recipe for tonight").spec.content.order == "best"
    assert S(ask_form("one-pot recipes"), "do you have any one-pot recipes").spec.content.order == "best"


def test_60_too_hard_is_easier_and_too_easy_is_harder():
    assert S({"intent": "feedback", "feedback": "down"}, "this is too hard for me").feedback == "easier"
    assert S({"intent": "feedback", "feedback": "less"}, "way too basic, something harder").feedback == "harder"
    it = S({"intent": "more", "criteria": ["shorter"]}, "too hard, something shorter")
    assert (it.intent, it.feedback, it.also.intent) == ("feedback", "easier", "more")
    assert S({"intent": "feedback", "feedback": "down"}, "not for me").feedback == "down"
    assert S({"intent": "feedback", "feedback": "down"}, "too much cream in that one").feedback == "down"


def test_60_another_language_sets_the_reply_language():
    assert S(ask_form("una receta"), "quiero una receta de pasta fácil para la cena").lang == "es"
    assert S(ask_form("une recette"), "je veux une recette rapide pour ce soir").lang == "fr"
    assert S(ask_form("a recipe"), "给我一个简单的晚餐食谱").lang == "zh"
    assert S(ask_form("pasta"), "send me a pasta recipe for dinner").lang is None
    assert S(dict(ask_form("pasta"), lang="pt"), "quero uma receita").lang == "pt"   # the form's own value wins


def test_60_how_do_i_get_my_new_saves_in_is_the_library_status_with_the_steps(env):
    it = S({"intent": "unsupported", "reply": "I can't do that."}, "how do I get my new saves in?")
    assert it.intent == "library_status"
    assert S({"intent": "help"}, "how do I update my library").intent == "library_status"
    assert S({"intent": "unsupported"}, "can you book me a table").intent == "unsupported"
    msg = say(env, "how do I get my new saves in?", {"intent": "unsupported", "reply": "Sorry, I can't."})
    assert msg.startswith("I haven't added an export for you yet") and "Instagram, every 4 weeks:" in msg


def test_60_every_day_with_a_routine_phrase_stays_every_day():
    form = rule_form({"type": "schedule", "days": ["MON", "TUE", "WED", "THU", "FRI"], "times": ["07:00"]},
                     goal="a stretch routine")
    it = S(form, "every day before work send me a stretch routine at 7am")
    assert it.spec.when.days == ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
    it = S(form, "every weekday before work send me a stretch routine at 7am")
    assert it.spec.when.days == ["MON", "TUE", "WED", "THU", "FRI"]


def test_60_a_to_do_and_a_request_keep_their_two_parts():
    it = S({"intent": "todo_add", "todo_text": "milk and find me a pancake recipe"},
           "add milk to my list and find me a pancake recipe")
    assert it.intent == "todo_add" and it.todo_text == "milk"
    assert it.also.intent == "ask" and it.also.spec.content.goal == "a pancake recipe"
    it = S(ask_form("a pancake recipe"), "add milk to my shopping list and find me a pancake recipe")
    assert (it.intent, it.todo_text, it.todo_list, it.also.intent) == ("todo_add", "milk", "shopping", "ask")
    it = S(ask_form("lunch recipes", count=2), "put a couple of easy lunch recipes on my to-do list")
    assert it.also is None                                    # one request: _find_for_list's case, untouched


def test_60_the_new_cases_are_in_the_extra_development_file():
    path = os.path.join(os.path.dirname(HERE), "evalset", "rules_dev_extra.jsonl")
    cases = {c["id"]: c for c in map(json.loads, open(path, encoding="utf-8"))}
    for i in range(35, 42):
        assert f"x-dev-{i:03d}" in cases


def test_61_no_must_have_no_other_than_the_finished_result_is_ever_shown(env):
    from mvp.compose import check
    from mvp.schema import RuleSpec
    view = env["bot"].view(str(env["lib"]))
    tips = view.get("itm_b")   # any item; its text is made tips-only below
    tips.caption = "Beginner modeling tips in Blender"
    spec = RuleSpec.model_validate({"when": {"type": "now"}, "content": {
        "goal": "a Blender project", "searches": ["blender"],
        "criteria": ["ends with a finished model", "suits a beginner"]}})
    no_level = {"picks": [{"n": 1, "verdict": "clear", "title": "Beginner modeling tips",
                           "criteria": [{"answer": "yes", "quote": "tips"}, {"answer": "no"}]}]}
    assert check(no_level, [tips], spec)["picks"] == []           # a "no" on another must-have: never shown
    only_finished = {"picks": [{"n": 1, "verdict": "clear", "title": "Beginner modeling tips",
                                "criteria": [{"answer": "yes", "quote": "tips"},
                                             {"answer": "yes", "quote": "Beginner modeling tips"}]}]}
    r = check(only_finished, [tips], spec)
    assert len(r["picks"]) == 1 and r["closest"]                  # its only "no" is the finished result
    unknown_no = {"picks": [{"n": 1, "verdict": "close", "title": "Beginner modeling tips",
                             "criteria": [{"answer": "unknown"}, {"answer": "no"}]}]}
    assert check(unknown_no, [tips], spec)["picks"] == []
