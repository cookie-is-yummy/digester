"""Offline tests for round 8, slice B, understanding and the loop (BN3, BN4, BN5; DESIGN.md section 14): what the
person has been into lately, the theme check, and the recap with one suggested rule. Synthetic data, a fake model, a
fake search pool and a fake clock only; no model call is made by any path tested here unless a test says so."""
import json
import os
import random
import re
import sys
from datetime import datetime, timedelta, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, say  # noqa: E402
from mvp.tests.test_slice6 import AllPool  # noqa: E402

UTC = timezone.utc


# ---------- a planted library ----------
def write_lib(path, rows):
    """rows: (id, platform, caption, {kind: day}, relation)."""
    (path / "corpus").mkdir(parents=True)
    with open(path / "corpus" / "items.jsonl", "w") as f:
        for iid, plat, cap, kinds, rel in rows:
            pd = {"owner_handle": f"c_{iid}", "owner_relation": rel}
            url = f"https://example.com/{iid}"
            if plat == "youtube":
                pd.update(video_id=f"vid{iid}", owner_name=f"Chan {iid}")
                url = f"https://www.youtube.com/watch?v=vid{iid}"
            f.write(json.dumps({"id": iid, "platform": plat, "source_url": url, "caption": cap,
                                "interaction_kinds": list(kinds), "platform_data": pd}) + "\n")
    with open(path / "corpus" / "interactions.jsonl", "w") as f:
        for iid, _, _, kinds, _ in rows:
            for kind, day in kinds.items():
                f.write(json.dumps({"item_id": iid, "kind": kind, "at": day + "T12:00:00+00:00"}) + "\n")
    return path


def day(start, k):
    return (datetime.fromisoformat(start) + timedelta(days=k)).date().isoformat()


def planted_rows():
    """Kept lately (the 56 days up to 15 Oct, Instagram's newest date): 20; in the 182 days before: 40, half the rate.
    Blender rises (1 -> 6), Sourdough fades (12 -> 1), Guitar keeps its share (8 -> 4), Climbing is small (0 -> 2,
    and 3 liked)."""
    rows, n = [], [0]

    def add(caption, kinds, plat="instagram", rel="none"):
        n[0] += 1
        rows.append((f"i{n[0]:03d}", plat, caption, kinds, rel))
    recent = [("Blender render study", 6), ("Guitar riff lesson", 4), ("Sourdough loaf bake", 1),
              ("Climbing bouldering session", 2), ("Street photo walk", 4), ("mental reset morning", 2)]
    k = 0
    for cap, count in recent:
        for j in range(count):
            add(f"{cap} {j}", {"save": day("2026-09-01", k)})
            k += 1
    add("Street photo walk last", {"save": "2026-10-15"})        # the newest Instagram date: the anchor
    before = [("Blender render study old", 1), ("Guitar riff lesson old", 8), ("Sourdough loaf bake old", 12),
              ("Street photo walk old", 19)]
    k = 0
    for cap, count in before:
        for j in range(count):
            add(f"{cap} {j}", {"collection": day("2026-03-01", k)})
            k += 1
    for j in range(3):   # likes are counted apart, never as kept
        add(f"Climbing wall video {j}", {"like": day("2026-09-20", j)})
    add("Blender scene from a friend", {"save": "2026-09-25"}, rel="mutual")   # a friend's post: never counted
    add("Blender render ancient", {"save": "2025-01-05"})                       # outside both windows
    add("Random vlog", {"watch": "2026-10-30"}, plat="youtube")                 # watched: YouTube's anchor, not kept
    return rows


INTERESTS = [
    {"topic": "Blender 3D", "words": ["blender"], "source": "guess", "confirmed": False, "saved": 7},
    {"topic": "Sourdough", "words": ["sourdough"], "source": "guess", "confirmed": False, "saved": 13},
    {"topic": "Guitar", "words": ["guitar"], "source": "guess", "confirmed": False, "saved": 12},
    {"topic": "Climbing", "words": ["climbing"], "source": "guess", "confirmed": False, "saved": 2},
    {"topic": "Mental health", "words": ["mental"], "source": "guess", "confirmed": False, "saved": 2},
]


@pytest.fixture()
def lib8(env, tmp_path):
    lib = write_lib(tmp_path / "lib8u", planted_rows())
    bot = env["bot"]
    bot.store.x("UPDATE people SET library=? WHERE handle=?", (str(lib), H))
    bot.pool = AllPool(str(lib))
    env["lib"] = lib
    from mvp import profile as P
    P.set_interests(bot.store, H, [dict(i) for i in INTERESTS])
    bot.store.set_direction(H, "getting better at Blender")
    env["state"]["answers"]["mvp_interpret"] = lambda u: pytest.fail("the model was called")
    return env


HEAD = ("What you kept lately: 20 posts in the 8 weeks up to 15 October 2026 on Instagram and 30 October 2026 on "
        "YouTube, and 40 in the 6 months before that.")
TRENDS = "\n".join([
    HEAD,
    "• Blender 3D is rising: 6 posts that mention it lately, 1 before.",
    "• Guitar is steady: 4 posts that mention it lately, 8 before.",
    "• Sourdough is fading: 1 post that mentions it lately, 12 before.",
    "• Climbing: too few to tell (2 posts that mention it lately, 0 before, 3 liked).",
    "You said you're working toward \"getting better at Blender\". Blender 3D: 6 posts that mention it lately, 1 before."])
QUESTION = ("One question, so I read these right: what is each one to you?\n"
            "1. Blender 3D  2. Guitar  3. Sourdough  4. Climbing\n"
            "Reply like \"1 practise, 2 for fun, 3 someday, 4 not me\" (or \"pursue\" for something you're going for). "
            "Anything else and I'll drop the question.")


def send(e, text):
    e["bot"].on_message(H, text)
    return last(e["ch"])


# ---------- BN3: rising, steady, fading ----------
def test_bn3_planted_library_gives_the_exact_lines_and_no_model_call(lib8):
    msg = send(lib8, "what have I been into lately?")
    assert msg == TRENDS + "\n\nReply \"every export\" and I'll send you this each time a new export of your library " \
                           "comes in.\n\n" + QUESTION
    assert len(TRENDS.split("\n")) <= 7
    assert lib8["calls"] == []                                   # code only
    assert "Mental health" not in msg                            # a sensitive topic never appears
    run = lib8["bot"].store.q("SELECT * FROM runs")
    assert run == []                                             # nothing is searched or composed


def test_bn3_labels_follow_the_shares_not_the_raw_counts():
    from mvp.attention import label
    assert label(6, 1, 20, 40) == "rising"
    assert label(1, 12, 20, 40) == "fading"
    assert label(4, 8, 20, 40) == "steady"            # half the posts, the same share: steady, never "fading"
    assert label(2, 0, 20, 40) == "few"
    # near-variants: the thresholds
    assert label(4, 0, 20, 40) == "steady"            # 4 lately is not enough to rise
    assert label(5, 0, 20, 40) == "rising"
    assert label(1, 9, 20, 40) == "few"               # 9 before is not enough to fade
    assert label(5, 10, 20, 40) == "steady"           # 0.25 now against 0.25 before
    assert label(5, 5, 20, 40) == "rising"            # 0.25 against 0.125: twice the share


def test_bn3_friends_posts_old_posts_likes_and_watches(lib8):
    from mvp import profile as P
    from mvp.attention import trends
    bot = lib8["bot"]
    data = trends(bot.view(str(lib8["lib"])), P.get(bot.store, H), None)
    rows = {t["topic"]: t for t in data["topics"]}
    assert rows["Blender 3D"]["recent"] == 6                     # the friend's Blender post is not counted
    assert rows["Blender 3D"]["before"] == 1                     # the one from January 2025 is outside both windows
    assert rows["Climbing"]["liked"] == 3 and rows["Climbing"]["recent"] == 2
    assert (data["recent_total"], data["before_total"]) == (20, 40)   # likes and the watched video are not kept
    assert "Mental health" not in rows
    assert data["direction"] is None


def test_bn3_moving_the_clock_changes_no_count_and_names_the_anchor_dates(lib8):
    first = send(lib8, "what am I into lately")
    lib8["clock"][0] += timedelta(days=60)
    again = send(lib8, "what's rising")
    assert again.split("\n\n")[0] == first.split("\n\n")[0] == TRENDS
    assert "15 October 2026" in again and "30 October 2026" in again


def test_bn3_direction_that_matches_nothing(lib8):
    lib8["bot"].store.set_direction(H, "learning to knit")
    msg = send(lib8, "what's fading?")
    assert msg.split("\n\n")[0].split("\n")[-1] == (
        "You said you're working toward \"learning to knit\". Nothing you kept lately mentions it, so I can't tell how "
        "that's going from your saves.")
    lib8["bot"].store.set_direction(H, None)   # no direction: no line about it
    assert "working toward" not in send(lib8, "what have i been into")


def test_bn3_phrases_read_by_code_and_others_left_to_the_model():
    from mvp.followup import TRENDS_ASK
    for t in ("what have I been into lately?", "What am I into lately", "what's rising", "whats fading?",
              "ok what have i been saving recently", "what's rising and what's fading", "What am I into these days?"):
        assert TRENDS_ASK.match(t), t
    for t in ("what have I been into lately? find me pasta", "what's rising in the stock market", "into blender",
              "what are the rising stars of jazz"):
        assert not TRENDS_ASK.match(t), t


def test_bn3_wording_of_20_generated_replies():
    from mvp import texts as T
    from datetime import date
    rnd = random.Random(8)
    bad = re.compile(r"\b(minutes?|hours?|time spent|obsess\w*|wasting|waste|misaligned|addict\w*|should)\b", re.I)
    for k in range(20):
        topics = []
        for j in range(rnd.randint(1, 6)):
            r, b = rnd.randint(0, 9), rnd.randint(0, 15)
            topics.append({"topic": f"Topic {j}", "relation": rnd.choice([None, None, "someday", "enjoy", "pursue"]),
                           "trend": rnd.choice(["rising", "steady", "fading", "few"]), "recent": r, "before": b,
                           "liked": rnd.randint(0, 4)})
        data = {"anchors": {"instagram": date(2026, 10, 15), "youtube": date(2026, 10, 30)},
                "recent_total": rnd.randint(1, 60), "before_total": rnd.randint(0, 120), "topics": topics,
                "direction": rnd.choice([None, {"text": "learning Blender", "topic": "Topic 0", "recent": 3, "before": 1},
                                         {"text": "cooking more", "topic": None, "recent": 0, "before": 0}])}
        msg = T.trends_message(data, 7)
        assert len(msg.split("\n")) <= 7 and not bad.search(msg), msg
        recap = [T.recap_head("Sunday 15 November"),
                 T.recap_rules([T.recap_rule_clause(1, "a pasta recipe", {"sent": rnd.randint(0, 5), "quiet": 2,
                                                                          "skipped": 1}, {"done": 1, "easier": 1})]),
                 T.recap_todos(rnd.randint(0, 3), rnd.randint(0, 3), rnd.randint(0, 1)), T.recap_calendar(2),
                 T.recap_suggest("pasta", 3, "Monday 2 November")]
        assert not bad.search("\n".join(recap))
    for t in (T.TRENDS_NO_TOPICS, T.TRENDS_NO_DATES, T.RECAP_NOTHING, T.RECAP_PREVIEW_EMPTY, QUESTION):
        assert not bad.search(t)


def test_bn3_no_topics_or_no_dates_say_so(env):
    env["state"]["answers"]["mvp_interpret"] = lambda u: pytest.fail("the model was called")
    assert send(env, "what have I been into lately") == (
        "I don't know your topics yet, so I can't say what's rising or fading. Tell me what you're into, or say "
        "\"set me up again\".")
    assert env["calls"] == []


# ---------- BN3: "every export" ----------
def test_bn3_every_export_makes_a_trends_rule_and_any_other_message_drops_the_offer(lib8):
    bot = lib8["bot"]
    send(lib8, "what have I been into lately")
    msg = send(lib8, "every export")
    rules = bot.store.rules(H)
    assert len(rules) == 1 and rules[0]["spec"]["content"]["source"] == "trends"
    assert rules[0]["spec"]["when"]["type"] == "new_items"
    assert msg == ("Got it: each time a new export of your library comes in, I'll send you what you've been into "
                   "lately. Reply \"stop 1\" to end it.")
    assert "every export" not in send(lib8, "what have I been into lately")   # a rule exists: not offered again
    assert lib8["calls"] == []
    send(lib8, "undo")
    assert bot.store.rules(H) == []
    # near-variant: anything else after the answer drops the offer; "every export" later is not read by code
    send(lib8, "what's rising")
    lib8["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "chat", "reply": "Sure."}
    send(lib8, "thanks")
    send(lib8, "every export")
    assert bot.store.rules(H) == [] and lib8["calls"].count("mvp_interpret") == 2


def test_bn3_a_trends_rule_runs_on_each_import_and_no_rule_sends_nothing(env, tmp_path, monkeypatch):
    from mvp.tests.test_slice5 import FIX_IG, drop, fake_prepare, zip_dir   # noqa: F401
    from mvp.refresh import Refresher, inbox_dir
    from mvp import config, profile as P
    from mvp.attention import message, trends
    bot, ch = env["bot"], env["ch"]
    (env["lib"] / "r7").mkdir()
    (env["lib"] / "r7" / "router.npz").write_bytes(b"synthetic")
    monkeypatch.setattr(config, "IMPORTS_PER_DAY", 10)
    bot.refresher = Refresher(bot, prepare=fake_prepare(), background=False, settle_seconds=0)
    env["inbox"] = inbox_dir(H)
    os.makedirs(env["inbox"])
    P.set_interests(bot.store, H, [{"topic": "Sourdough", "words": ["sourdough"], "source": "guess"}])
    zips = [zip_dir(FIX_IG, str(tmp_path / f"instagram-{k}.zip")) for k in (1, 2)]
    # no trends rule: the import sends its one message only
    drop(env, zips[0])
    n0 = len(ch.outbox)
    bot.refresher.poll(force=True)
    assert len(ch.outbox) == n0 + 1 and ch.outbox[-1][2].startswith("Your new export is in:")
    # with the rule: one trends message, computed on the library the import switched to
    old = bot.store.person(H)["library"]
    before = message(trends(bot.view(old), P.get(bot.store, H), None))
    rid = bot.store.add_rule(H, "every export", {"when": {"type": "new_items"}, "content": {"source": "trends"}},
                             "active", None)
    import shutil
    src = tmp_path / "ig-more"
    shutil.copytree(FIX_IG, src)
    saved = src / "your_instagram_activity" / "saved" / "saved_posts.json"
    data = json.loads(saved.read_text())
    extra = json.loads(json.dumps(data["saved_saved_media"][0]))
    extra["timestamp"] = 1760500000
    for lv in extra["label_values"]:
        if lv.get("label") == "URL":
            lv["value"] = "https://www.instagram.com/reel/SYNTHreel099/"
        if lv.get("label") == "Caption":
            lv["value"] = "Synthetic sourdough loaf, the second bake"
    data["saved_saved_media"].append(extra)
    saved.write_text(json.dumps(data))
    drop(env, zip_dir(str(src), str(tmp_path / "instagram-more.zip")))
    n0 = len(ch.outbox)
    bot.refresher.poll(force=True)
    new = bot.store.person(H)["library"]
    assert new != old
    sent = [m[2] for m in ch.outbox[n0:]]
    assert len(sent) == 2 and sent[0].startswith("Your new export is in:")
    expected = message(trends(bot.view(new), P.get(bot.store, H), None))
    assert sent[1] == expected + "\nReply \"stop 1\" to end these."
    assert expected.startswith("What you kept lately: ")
    assert expected != before                                    # the new library's counts, not the old one's
    run = bot.store.one("SELECT status FROM runs WHERE rule_id=? ORDER BY id DESC LIMIT 1", (rid,))
    assert run["status"] == "sent"
    assert "mvp_compose" not in env["calls"] and "mvp_interpret" not in env["calls"]


# ---------- BN4: the theme check ----------
def test_bn4_labels_by_number_are_stored_and_said_once(lib8):
    from mvp import profile as P
    bot = lib8["bot"]
    send(lib8, "what have I been into lately")
    msg = send(lib8, "1 practise 2 enjoy 3 someday 4 not me")
    assert msg == ("Thanks, noted. Blender 3D: a skill you're practising; Guitar: just for fun; Sourdough: parked for "
                   "someday; Climbing: not you, so I'll leave it out of what I say about you. Asking for it by name "
                   "still finds those posts. To change one, say \"Blender 3D is pursue now\".")
    rel = {i["topic"]: i.get("relation") for i in bot.store.profile_data(H)["interests"]}
    assert rel == {"Blender 3D": "practise", "Sourdough": "someday", "Guitar": "enjoy", "Climbing": "not_me",
                   "Mental health": None}
    assert all(i.get("relation_at") for i in bot.store.profile_data(H)["interests"] if i.get("relation"))
    assert "Climbing" not in [i["topic"] for i in P.get(bot.store, H)["interests"]]
    # the trends answer now: not_me left out, someday parked with no trend word, enjoy for fun; never asked again
    again = send(lib8, "what have I been into lately")
    body = again.split("\n\n")[0]
    assert "Climbing" not in again and "One question" not in again
    assert "Parked for someday: Sourdough (1 post that mentions it lately)." in body
    assert "Just for fun: Guitar (4 posts that mention it lately)." in body
    assert "Sourdough is" not in body and "fading" not in body and "Guitar is" not in body
    assert lib8["calls"] == []


def test_bn4_enjoy_is_never_compared_with_the_direction(lib8):
    bot = lib8["bot"]
    from mvp import profile as P
    P.set_relations(bot.store, H, [("Guitar", "enjoy")])
    bot.store.set_direction(H, "playing guitar every day")
    body = send(lib8, "what have I been into lately").split("\n\n")[0]
    assert body.split("\n")[-1] == ("You said you're working toward \"playing guitar every day\". Nothing you kept "
                                    "lately mentions it, so I can't tell how that's going from your saves.")
    P.set_relations(bot.store, H, [("Guitar", "pursue")])   # near-variant: a goal is compared
    body = send(lib8, "what have I been into lately").split("\n\n")[0]
    assert body.split("\n")[-1].endswith("Guitar: 4 posts that mention it lately, 8 before.")


def test_bn4_labels_by_name_a_number_past_the_list_and_a_request(lib8):
    from mvp import profile as P
    bot = lib8["bot"]
    send(lib8, "what have I been into lately")
    assert send(lib8, "5 someday") == "Which one? I listed 4. Reply with their numbers, like \"1 practise\"."
    assert bot.store.get_state(f"themecheck:{H}")                  # still open
    msg = send(lib8, "climbing someday, guitar not me")
    assert msg.startswith("Thanks, noted. Climbing: parked for someday; Guitar: not you")
    rel = {i["topic"]: i.get("relation") for i in bot.store.profile_data(H)["interests"]}
    assert rel["Climbing"] == "someday" and rel["Guitar"] == "not_me" and rel["Blender 3D"] is None
    # a request is not labels: it goes the normal way and ends the question
    P.set_relations(bot.store, H, [("Guitar", "pursue")])
    bot.store.set_state(f"themecheck_asked:{H}", None)
    send(lib8, "what have I been into lately")
    lib8["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "chat", "reply": "Hello."}
    assert send(lib8, "find me a pasta recipe") == "Hello."
    assert bot.store.get_state(f"themecheck:{H}") is None
    assert send(lib8, "1 someday") != "" and lib8["calls"].count("mvp_interpret") == 2   # no longer read as labels


def test_bn4_parse_labels_forms():
    from mvp.profile import parse_labels
    shown = ["Blender 3D", "Guitar", "Rock climbing"]
    assert parse_labels("1 practise, 2 for fun and 3 later", shown)["pairs"] == [
        ("Blender 3D", "practise"), ("Guitar", "enjoy"), ("Rock climbing", "someday")]
    assert parse_labels("blender: pursue. climbing nope", shown)["pairs"] == [("Blender 3D", "pursue"),
                                                                             ("Rock climbing", "not_me")]
    assert parse_labels("#2 is just for fun", shown)["pairs"] == [("Guitar", "enjoy")]
    assert parse_labels("1 practice 2 not really me", shown)["pairs"] == [("Blender 3D", "practise"),
                                                                         ("Guitar", "not_me")]
    assert parse_labels("4 someday", shown) == {"pairs": [], "bad": [4]}
    for t in ("find me a pasta recipe", "1 practise and find me a pasta recipe", "yes", "2", "guitar", "later",
              "send me 2 later"):
        assert parse_labels(t, shown) is None, t


def test_bn4_never_asked_during_the_setup(lib8):
    bot = lib8["bot"]
    bot.store.set_state(f"onboard:{H}", {"step": "contact", "at": lib8["clock"][0].isoformat()})
    msg = send(lib8, "what have I been into lately")
    assert msg.startswith(HEAD) and "One question" not in msg
    assert bot.store.get_state(f"themecheck:{H}") is None and bot.store.get_state(f"themecheck_asked:{H}") is None


def test_bn4_set_me_up_again_keeps_a_not_me_topic_out(lib8):
    from mvp import profile as P
    bot = lib8["bot"]
    view = bot.view(str(lib8["lib"]))
    cached = {"interests": [dict(i, source="guess") for i in INTERESTS[:4]], "sample": 10, "kept": 60, "removed": 0,
              "build": "b1", "cached": False}
    bot.store.x("INSERT INTO profile_guess(key,library,result,at) VALUES(?,?,?,?)",
                (P.guess_key(view), str(lib8["lib"]), json.dumps(cached), "2026-11-01T00:00:00+00:00"))
    P.set_relations(bot.store, H, [("Climbing", "not_me")])
    msg = send(lib8, "set me up again")
    assert "Climbing" not in msg and "Blender 3D" in msg
    assert "Climbing" not in [i["topic"] for i in P.get(bot.store, H)["interests"]]
    assert [i["topic"] for i in P.not_me_markers(bot.store, H)] == ["Climbing"]
    # the defect it fixes: a topic dropped by a profile update is a marker too, so a new guess never brings it back
    P.apply_merge(bot.store, H, {"kind": "about_me", "drop_topics": ["Sourdough"]}, "I'm not into sourdough any more")
    P.adopt_guess(bot.store, H, cached)
    assert "Sourdough" not in [i["topic"] for i in P.get(bot.store, H)["interests"]]
    # near-variant: their own words bring a marker's topic back
    P.apply_merge(bot.store, H, {"kind": "about_me", "add_topics": ["Sourdough"]}, "I'm into sourdough again")
    assert "Sourdough" in [i["topic"] for i in P.get(bot.store, H)["interests"]]
    assert "Sourdough" not in [i["topic"] for i in P.not_me_markers(bot.store, H)]


def test_bn4_a_not_me_topic_is_still_found_and_never_said(lib8):
    from mvp import profile as P
    bot = lib8["bot"]
    P.set_relations(bot.store, H, [("Guitar", "not_me")])
    assert not any("Guitar" in x for x in P.about_lines(bot.store, H))
    assert not any("Guitar" in x for x in P.about_lines(bot.store, H, "find my guitar riff saves"))
    text, _, _ = P.composer_context(bot.store, H, "guitar riffs")
    assert "Guitar" not in text
    assert "Guitar" not in P.show_text(P.get(bot.store, H))
    lib8["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "ask", "spec": {
        "when": {"type": "now"}, "content": {"goal": "guitar riffs", "searches": ["guitar riff"], "count": 1}}}

    def compose(u):
        m = re.search(r"^(\d+)\. [^\n]*\n<item>Guitar riff lesson 0", u, re.M)
        return {"picks": [{"n": int(m.group(1)), "title": "Guitar riff lesson", "verdict": "clear"}]}
    lib8["state"]["answers"]["mvp_compose"] = compose
    msg = send(lib8, "find my guitar riff saves")
    assert "Guitar riff lesson" in msg                     # themes never gate search


def test_bn4_topic_is_label_now_and_what_did_i_park(lib8):
    from mvp import profile as P
    bot = lib8["bot"]
    assert send(lib8, "what did I park?") == ("Nothing is parked yet. Say something like \"climbing is someday now\" "
                                              "to park a topic.")
    assert send(lib8, "climbing is someday now") == "OK: Climbing is parked for someday now."
    assert send(lib8, "sourdough is someday now") == "OK: Sourdough is parked for someday now."
    assert send(lib8, "what did I park?") == ("Parked for someday: Sourdough (13 saved posts), Climbing (2 saved "
                                              "posts).")
    assert send(lib8, "climbing is pursue now") == "OK: Climbing is something you're going for now."
    assert {i["topic"]: i.get("relation") for i in P.get(bot.store, H)["interests"]}["Climbing"] == "pursue"
    assert send(lib8, "guitar is not me now") == ("OK: I'll leave Guitar out of what I say about you. Asking for it by "
                                                  "name still finds those posts.")
    assert send(lib8, "guitar is pursue now") == "OK: Guitar is something you're going for now."   # back again
    assert "Guitar" in [i["topic"] for i in P.get(bot.store, H)["interests"]]
    assert lib8["calls"] == []
    # near-variants: no "now", or a topic that is not theirs, are left to the model
    lib8["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "chat", "reply": "Hm."}
    assert send(lib8, "climbing is fun") == "Hm."
    assert send(lib8, "knitting is someday now") == "Hm."


def test_bn4_delete_my_data_removes_the_labels(lib8):
    bot = lib8["bot"]
    send(lib8, "what have I been into lately")
    send(lib8, "1 practise")
    lib8["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "delete_data"}
    send(lib8, "delete my data")
    send(lib8, "YES")
    assert bot.store.person(H) is None
    left = [r["key"] for r in bot.store.q("SELECT key FROM state") if r["key"].endswith(H)]
    assert left == []
    assert bot.store.profile_data(H) == {}


# ---------- BN5: the recap ----------
SUN = datetime(2026, 11, 22, 23, 0, tzinfo=UTC)   # Sunday 22 November, 6pm in New York


def at(dt):
    return dt.isoformat(timespec="seconds")


def plant_week(e):
    """2 rules (5 sent, 2 quiet, 1 skipped), feedback (2 made it, 1 👍), to-dos (3 done, 2 open, 1 past due), one
    reminder about a thing on 27 Nov and one calendar link, all in the week before SUN."""
    s = e["bot"].store
    e["clock"][0] = SUN
    lib = library_spec = {"when": {"type": "schedule", "days": ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"],
                                   "times": ["08:00"]},
                          "content": {"goal": "a pasta recipe", "searches": ["pasta recipe"]}}
    a = s.add_rule(H, "pasta every morning", lib, "active", at(SUN + timedelta(hours=12)))
    b = s.add_rule(H, "blender every friday", dict(library_spec, content={"goal": "blender tutorials",
                                                                          "searches": ["blender tutorial"]}),
                   "active", at(SUN + timedelta(days=5)))
    for k, status in enumerate(["sent", "sent", "sent", "empty_quiet", "empty_quiet"]):
        s.add_run(handle=H, rule_id=a, kind="scheduled", status=status, at=at(SUN - timedelta(days=6 - k)))
    for k, status in enumerate(["sent", "skipped", "sent"]):
        s.add_run(handle=H, rule_id=b, kind="scheduled", status=status, at=at(SUN - timedelta(days=5 - k)))
    s.add_run(handle=H, rule_id=a, kind="scheduled", status="sent", at=at(SUN - timedelta(days=9)))   # before the week
    for kind in ("done", "done", "up"):
        s.x("INSERT INTO feedback(handle,item_id,rule_id,kind,at) VALUES(?,?,?,?,?)",
            (H, "itm_a", a, kind, at(SUN - timedelta(days=2))))
    s.x("INSERT INTO feedback(handle,item_id,rule_id,kind,at) VALUES(?,?,?,?,?)",
        (H, "itm_b", a, "down", at(SUN - timedelta(days=2))))   # not one of the four the recap names
    for k in range(3):
        t = s.add_todo(H, f"done thing {k}")
        s.update_todo(t, done_at=at(SUN - timedelta(days=1)))
    old = s.add_todo(H, "done long ago")
    s.update_todo(old, done_at=at(SUN - timedelta(days=20)))
    bank = s.add_todo(H, "call the bank", due_at=SUN - timedelta(days=2))
    s.update_todo(bank, reminded_at=at(SUN - timedelta(days=2)))   # reminded at its time; still open
    s.add_todo(H, "buy basil")
    once = s.add_rule(H, "remind me 3 days before it closes", {
        "when": {"type": "once", "date": "2026-11-27", "time": "09:00"},
        "content": {"source": "items", "item_ids": ["itm_a"], "item_names": ["NASA L'SPACE Academy"]}},
        "active", "2026-11-27T14:00:00+00:00")
    s.set_state(f"deadline:{once}", {"date": "2026-11-30", "deadline": True})
    s.log_action(H, None, a, "calendar.add", "done", at=SUN - timedelta(days=3))
    s.log_action(H, None, a, "calendar.add", "failed", at=SUN - timedelta(days=3))
    return a, b, once


RECAP = "\n".join([
    "Your recap since Sunday 15 November:",
    "• Rules: 1 \"a pasta recipe\" sent 3, stayed quiet twice with nothing new (2 made it, 1 👍); 2 \"blender "
    "tutorials\" sent 2, 1 skipped.",
    "• To-dos: you ticked off 3; 2 are open, 1 of them past its due date.",
    "• Coming up: a reminder about NASA L'SPACE Academy on Friday 27 November (its deadline is 30 November).",
    "• I gave you 1 calendar link.",
    "• Your library: the newest thing you kept is from 1 March 2026; your next Instagram export was due around "
    "Sunday 29 March; your next YouTube export was due around Friday 1 May."])


def test_bn5_a_planted_week_gives_the_expected_recap(env):
    plant_week(env)
    env["state"]["answers"]["mvp_interpret"] = lambda u: pytest.fail("the model was called")
    msg = send(env, "how did my rules do?")
    assert msg == RECAP
    assert len(msg.split("\n")) <= 6
    assert "added to your calendar" not in msg and "you added" not in msg
    assert env["calls"] == []
    for t in ("recap", "my week", "how was my week?", "send me my recap", "How are my rules doing"):
        assert send(env, t) == RECAP, t


def test_bn5_a_week_with_nothing_to_report(env):
    env["clock"][0] = SUN
    env["state"]["answers"]["mvp_interpret"] = lambda u: pytest.fail("the model was called")
    assert send(env, "recap") == "Nothing to report for the last 7 days: no rule sent anything and no to-do changed."
    from mvp.digest import build
    from mvp import profile as P
    bot = env["bot"]
    assert build(bot.store, bot.view(str(env["lib"])), P.get(bot.store, H), H, SUN - timedelta(days=7), SUN) == []
    bot.store.add_todo(H, "an open one, no date")     # an open to-do alone is not news
    assert build(bot.store, bot.view(str(env["lib"])), P.get(bot.store, H), H, SUN - timedelta(days=7), SUN) == []


def recap_rule_answer():
    return {"intent": "new_rule", "spec": {"when": {"type": "schedule", "days": ["SUN"], "times": ["18:00"]},
                                           "content": {"goal": "a recap", "searches": ["recap"]}}}


def test_bn5_a_recap_rule_previews_starts_on_yes_and_sends_sunday(env):
    bot = env["bot"]
    plant_week(env)
    env["clock"][0] = SUN - timedelta(hours=2)
    msg = say(env, "every sunday at 6pm send me a recap", recap_rule_answer())
    assert msg.startswith("Here's what that would look like now:\n\nYour recap since Sunday 15 November:")
    assert msg.endswith("Every Sunday at 6pm, I'll send you a recap like this one. The first one would come today at "
                        "6pm. Reply YES to start, or tell me what to change.")
    assert len([r for r in bot.store.rules(H) if r["spec"]["content"].get("source") == "recap"]) == 0
    assert env["calls"] == ["mvp_interpret"]                         # the timing only; the recap is code's
    send(env, "YES")
    rule = next(r for r in bot.store.rules(H) if r["spec"]["content"].get("source") == "recap")
    c = rule["spec"]["content"]
    assert rule["next_run_at"] == at(SUN) and (c["source"], c["goal"]) == ("recap", "your recap")
    env["clock"][0] = SUN + timedelta(minutes=1)
    n0 = len(env["ch"].outbox)
    bot.tick()
    sent = [m[2] for m in env["ch"].outbox[n0:]]
    assert len(sent) == 1 and sent[0].startswith("Your recap since Sunday 15 November:")
    assert sent[0].endswith(f"\nReply \"stop {bot.store.rule_number(H, rule['id'])}\" to end these.")
    assert "mvp_compose" not in env["calls"]


def test_bn5_an_empty_recap_records_none_and_sends_nothing_and_unanswered_recaps_ask(env):
    bot = env["bot"]
    env["clock"][0] = SUN - timedelta(hours=2)
    say(env, "every sunday at 6pm send me a recap", recap_rule_answer())
    assert "There's nothing to report this week yet. On a week like that I send nothing." in last(env["ch"])
    send(env, "yes")
    rid = next(r["id"] for r in bot.store.rules(H) if r["spec"]["content"].get("source") == "recap")
    env["clock"][0] = SUN + timedelta(minutes=1)
    n0 = len(env["ch"].outbox)
    bot.tick()
    assert len(env["ch"].outbox) == n0
    run = bot.store.one("SELECT status FROM runs WHERE rule_id=? ORDER BY id DESC LIMIT 1", (rid,))
    assert run["status"] == "none"
    assert bot.store.rule(rid)["next_run_at"] == at(SUN + timedelta(days=7))
    # an open to-do past its due date is news every week: three unanswered recaps, then "Still useful?"
    t = bot.store.add_todo(H, "call the bank", due_at=SUN - timedelta(days=1))
    bot.store.update_todo(t, reminded_at=at(SUN - timedelta(days=1)))   # its own reminder went out then
    from mvp.texts import STILL_USEFUL
    sends = []
    for week in range(1, 5):
        env["clock"][0] = SUN + timedelta(days=7 * week, minutes=1)
        n0 = len(env["ch"].outbox)
        bot.tick()
        sends += [m[2] for m in env["ch"].outbox[n0:]]
    assert len(sends) == 4 and all(s.startswith("Your recap since") for s in sends)
    assert [STILL_USEFUL in s for s in sends] == [False, False, False, True]
    assert bot._unanswered(H) == 4                                   # not the person's own words


def test_bn5_snooze_and_pause_hold_a_recap(env):
    bot = env["bot"]
    plant_week(env)
    env["clock"][0] = SUN - timedelta(hours=2)
    say(env, "every sunday at 6pm send me a recap", recap_rule_answer())
    send(env, "yes")
    rid = next(r["id"] for r in bot.store.rules(H) if r["spec"]["content"].get("source") == "recap")
    bot.store.set_snooze(H, SUN + timedelta(days=1))
    env["clock"][0] = SUN + timedelta(minutes=1)
    n0 = len(env["ch"].outbox)
    bot.tick()
    assert len(env["ch"].outbox) == n0
    assert bot.store.one("SELECT status FROM runs WHERE rule_id=? ORDER BY id DESC LIMIT 1", (rid,))["status"] == \
        "snoozed"
    bot.store.set_snooze(H, None)
    n = bot.store.rule_number(H, rid)
    send(env, f"pause {n}")
    env["clock"][0] = SUN + timedelta(days=7, minutes=1)
    n0 = len(env["ch"].outbox)
    bot.tick()
    assert not [m for m in env["ch"].outbox[n0:] if m[2].startswith("Your recap")]
    assert bot.store.rule(rid)["status"] == "paused"
    bot.store.x("UPDATE people SET paused=1 WHERE handle=?", (H,))
    n0 = len(env["ch"].outbox)
    send(env, f"resume {n}")
    assert len(env["ch"].outbox) == n0                               # the kill switch: no reply, no send


def pasta_asks(e, days=((0, 0), (0, 2), (1, 1))):
    """Three asks for pasta on 2 days (12 and 13 Nov)."""
    e["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "ask", "spec": {
        "when": {"type": "now"}, "content": {"goal": "a pasta recipe", "searches": ["pasta recipe"], "count": 1}}}
    e["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [{"n": 1, "title": "Pasta", "why": "Good.",
                                                                 "verdict": "clear"}]}
    base = datetime(2026, 11, 12, 15, 0, tzinfo=UTC)
    for d, h in days:
        e["clock"][0] = base + timedelta(days=d, hours=h)
        e["bot"].on_message(H, "pasta please")


SUGGEST = ("• You asked about pasta 3 times since Thursday 12 November. Want one pick for it every Saturday at 10am? "
           "Reply \"yes\" and I'll show you a preview first.")


def test_bn5_repeated_asks_give_one_suggestion_and_yes_shows_the_standard_preview(env):
    bot = env["bot"]
    pasta_asks(env)
    env["clock"][0] = datetime(2026, 11, 15, 16, 0, tzinfo=UTC)
    calls = len(env["calls"])
    msg = send(env, "recap")
    assert msg.split("\n")[-1] == SUGGEST and msg.split("\n")[0] == "Your recap since Sunday 8 November:"
    assert len(env["calls"]) == calls                                # building the recap and the suggestion: 0 calls
    msg = send(env, "yes")
    assert msg.startswith("Here's what that would look like now:")
    assert "Every Saturday at 10am, I'll send 1 pick for \"a pasta recipe\"" in msg and "Reply YES to start" in msg
    assert bot.store.rules(H) == []                                  # nothing starts without YES
    send(env, "YES")
    rules = bot.store.rules(H)
    w = rules[0]["spec"]["when"]
    assert len(rules) == 1 and (w["type"], w["days"], w["times"]) == ("schedule", ["SAT"], ["10:00"])
    assert rules[0]["spec"]["content"]["goal"] == "a pasta recipe"
    assert SUGGEST not in send(env, "recap")                         # a rule covers it now


def test_bn5_a_suggestion_is_offered_once_in_30_days_and_never_for_labelled_topics(env):
    from mvp import profile as P
    bot = env["bot"]
    pasta_asks(env)
    env["clock"][0] = datetime(2026, 11, 15, 16, 0, tzinfo=UTC)
    assert send(env, "recap").endswith(SUGGEST)
    env["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "chat", "reply": "OK."}
    send(env, "not now")                                             # any other message ends it
    send(env, "yes")
    assert bot.store.rules(H) == [] and bot.store.pending(H) is None
    assert "You asked about" not in send(env, "recap")               # not again within 30 days
    # labelled topics are never suggested: someday, and not me
    bot.store.set_state(f"suggested:{H}", None)
    P.set_interests(bot.store, H, [{"topic": "Pasta", "words": ["pasta"], "source": "guess"}])
    P.set_relations(bot.store, H, [("Pasta", "someday")])
    assert "You asked about" not in send(env, "recap")
    P.set_relations(bot.store, H, [("Pasta", "not_me")])
    assert "You asked about" not in send(env, "recap")
    P.set_relations(bot.store, H, [("Pasta", "pursue")])
    assert send(env, "recap").endswith(SUGGEST)                      # near-variant: a goal may be suggested


def test_bn5_two_asks_or_one_day_or_old_rows_give_no_suggestion(env):
    bot = env["bot"]
    pasta_asks(env, days=((0, 0), (0, 2), (0, 3)))                   # three asks, one day
    env["clock"][0] = datetime(2026, 11, 15, 16, 0, tzinfo=UTC)
    assert "You asked about" not in send(env, "recap")
    pasta_asks(env, days=((1, 1),))                                  # a second day: now it is offered
    env["clock"][0] = datetime(2026, 11, 15, 16, 0, tzinfo=UTC)
    bot.store.set_state(f"suggested:{H}", None)
    assert send(env, "recap").endswith("• You asked about pasta 4 times since Thursday 12 November. Want one pick "
                                       "for it every Saturday at 10am? Reply \"yes\" and I'll show you a preview "
                                       "first.")
    bot.store.set_state(f"suggested:{H}", None)
    bot.store.x("UPDATE answers SET spec=NULL")                      # answers kept before this round
    assert send(env, "recap") == "Nothing to report for the last 7 days: no rule sent anything and no to-do changed."


def test_bn5_old_stores_load_with_the_new_column(tmp_path):
    import sqlite3
    for m in [m for m in sys.modules if m.startswith("mvp")]:
        del sys.modules[m]
    from mvp.store import Store
    db = tmp_path / "old.sqlite"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE answers (run_id INTEGER PRIMARY KEY, handle TEXT NOT NULL, rule_id INTEGER, goal TEXT, "
              "kind TEXT, parts TEXT, picks TEXT, at TEXT)")
    c.execute("INSERT INTO answers VALUES (1, '+1', NULL, 'g', 'picks', '[]', '[]', '2026-11-01T00:00:00+00:00')")
    c.commit()
    c.close()
    s = Store(str(db))
    assert s.answer(1)["spec"] is None
    s.put_answer(2, "+1", None, "g", "picks", [], [], spec={"when": {"type": "now"}})
    assert json.loads(s.answer(2)["spec"]) == {"when": {"type": "now"}}


def test_bn5_the_recap_rule_regex_and_on_request_phrases():
    from mvp.followup import RECAP_ASK, RECAP_RULE
    for t in ("every sunday at 6pm send me a recap", "send me a weekly recap on fridays", "a recap of my week every "
              "monday", "every week tell me how my rules did"):
        assert RECAP_RULE.search(t), t
    for t in ("give me a recap of that video", "recap of the second one"):
        assert not RECAP_RULE.search(t), t
    for t in ("recap", "my recap", "Recap please", "how did my rules do", "my week", "how was my week?"):
        assert RECAP_ASK.match(t), t
    for t in ("recap the second one", "my week was long", "how did my rules do with pasta"):
        assert not RECAP_ASK.match(t), t


def test_bn5_changing_a_recap_rule_changes_its_timing_only(env):
    bot = env["bot"]
    rid = bot.store.add_rule(H, "every sunday at 6pm send me a recap", {
        "when": {"type": "schedule", "days": ["SUN"], "times": ["18:00"]}, "content": {"source": "recap"}},
        "active", at(SUN))
    say(env, "move my recap to saturdays at 10", {"intent": "change_rule", "rule_number": 1, "spec": {
        "when": {"type": "schedule", "days": ["SAT"], "times": ["10:00"]},
        "content": {"goal": "a recap", "searches": ["recap"]}}})
    spec = bot.store.rule(rid)["spec"]
    assert spec["content"]["source"] == "recap" and spec["when"]["days"] == ["SAT"]
    # near-variant: a library rule's change is the interpreter's, as before
    lib = bot.store.add_rule(H, "pasta", {"when": {"type": "schedule", "days": ["FRI"], "times": ["19:00"]},
                                          "content": {"goal": "a pasta recipe", "searches": ["pasta"]}}, "active", at(SUN))
    n = bot.store.rule_number(H, lib)
    say(env, "change the pasta one to a curry recipe", {"intent": "change_rule", "rule_number": n, "spec": {
        "when": {"type": "schedule", "days": ["FRI"], "times": ["19:00"]},
        "content": {"goal": "a curry recipe", "searches": ["curry"]}}})
    assert bot.store.rule(lib)["spec"]["content"]["goal"] == "a curry recipe"


# ---------- the checker's live script, the profile view, a trends rule over the cap ----------
def test_bn3_live_script_prints_counts_only(lib8, capsys):
    from mvp import attention, config
    from mvp import profile as P
    P.set_relations(lib8["bot"].store, H, [("Climbing", "not_me")])
    attention.main([str(lib8["lib"]), "--store", config.DB])
    out = capsys.readouterr().out
    assert "anchors: instagram 2026-10-15, youtube 2026-10-30" in out
    assert "kept lately: 20, in the 182 days before: 40" in out
    assert "topic 1: rising, lately 6, before 1, liked 0, label -" in out
    assert "direction: topic 1, lately 6, before 1" in out and "counted in" in out
    for name in ("Blender", "Guitar", "Sourdough", "Climbing", "Mental", "render", "getting better", H):
        assert name not in out                               # no topic names, captions, words or handles
    assert len([x for x in out.split("\n") if x.startswith("topic ")]) == 3   # not me and sensitive left out


def test_bn4_what_do_you_know_about_me_shows_the_labels(lib8):
    from mvp import profile as P
    bot = lib8["bot"]
    P.set_relations(bot.store, H, [("Sourdough", "someday"), ("Guitar", "enjoy"), ("Blender 3D", "practise"),
                                   ("Climbing", "not_me")])
    text = P.show_text(P.get(bot.store, H))
    assert "• Sourdough (my guess, parked for someday, from 13 saved posts)" in text
    assert "• Guitar (my guess, just for fun, from 12 saved posts)" in text
    assert "• Blender 3D (my guess, you're practising it, from 7 saved posts)" in text
    assert "Climbing" not in text


def test_bn3_a_trends_rule_runs_on_an_import_over_the_cap(lib8, monkeypatch):
    from mvp.refresh import run_new_items
    bot = lib8["bot"]
    bot.store.add_rule(H, "every export", {"when": {"type": "new_items"}, "content": {"source": "trends"}},
                       "active", None)
    monkeypatch.setattr(type(bot), "_over_cap", lambda self, person: "day")
    answers, nothing, _ = run_new_items(bot, bot.store.person(H), {"i001"}, lib8["clock"][0])
    assert len(answers) == 1 and answers[0][2].startswith(HEAD) and nothing == []
    answers, nothing, _ = run_new_items(bot, bot.store.person(H), set(), lib8["clock"][0])
    assert answers == [] and nothing == []                    # nothing new: the counts have not changed, and no line
