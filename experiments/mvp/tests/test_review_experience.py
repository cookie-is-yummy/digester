"""Offline tests for the experience review (findings X1 to X12): one or more per finding, each failing without its fix.
Fakes only: the fake model, a search pool that returns the whole synthetic library, a fake YouTube, the fake clock.
No network, no real data, no model calls."""
import json
import os
import re
import sys
import threading
from datetime import datetime, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, EXP)

from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)

H = "+15550001"
UTC = timezone.utc
DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]

# ---------- a small synthetic library (invented captions and creators) ----------
IG = [
    ("r1", "Instant pot chicken and rice in 15 minutes\nIngredients:\n- 2 chicken thighs\n- 1 cup jasmine rice\n"
           "- 1 cup chicken broth\n- 2 cloves garlic\nSteps:\n1. Saute the chicken in the instant pot\n"
           "2. Add the rice and broth\n3. Pressure cook for 15 minutes", "souschef"),
    ("r2", "Hainanese chicken rice, the full recipe is in the video", "wokhei"),
    ("r3", "One pan chicken and rice bake\nIngredients:\n- 300g chicken breast\n- 200g long grain rice\n- 1 onion\n"
           "- 500ml stock", "trayqueen"),
    ("r5", "5 tips for fluffier rice every time", "souschef"),
    ("b1", "Blender donut tutorial for absolute beginners, part 1: modeling the donut", "polyguy"),
    ("b3", "Low poly island in Blender, full tutorial from start to finish render", "lowpolyjo"),
    ("b4", "Blender: model a cosy room step by step for beginners", "roomrender"),
    ("w1", "20 minute full body dumbbell workout\n1. Goblet squats x 12\n2. Reverse lunges x 10\n3. Push ups x 10",
     "fitwithana"),
    ("w3", "Morning mobility routine, full routine from start to finish\n1. Cat cow x 10\n2. Hip circles x 10",
     "bendy"),
]
YT = [("y3", "YTcook00001", "Chicken fried rice in 10 minutes", "Fast Wok", 610)]


def write_library(path):
    (path / "corpus").mkdir(parents=True)
    rows, inter = [], []
    for iid, cap, who in IG:
        rows.append({"id": iid, "platform": "instagram", "source_url": f"https://www.instagram.com/p/{iid}SYN/",
                     "caption": cap, "interaction_kinds": ["save"],
                     "platform_data": {"owner_handle": who, "owner_relation": "none"}})
        inter.append({"item_id": iid, "kind": "save", "at": "2026-07-01T10:00:00+00:00"})
    for iid, vid, title, chan, _secs in YT:
        rows.append({"id": iid, "platform": "youtube", "source_url": f"https://www.youtube.com/watch?v={vid}",
                     "caption": title, "interaction_kinds": ["watch"],
                     "platform_data": {"owner_name": chan, "video_id": vid, "owner_relation": "none"}})
        inter.append({"item_id": iid, "kind": "watch", "at": "2026-10-02T10:00:00+00:00"})
    with open(path / "corpus" / "items.jsonl", "w") as f:
        f.write("\n".join(json.dumps(r) for r in rows) + "\n")
    with open(path / "corpus" / "interactions.jsonl", "w") as f:
        f.write("\n".join(json.dumps(r) for r in inter) + "\n")
    return path


def yt_fetch(ids, key, timeout=None):
    by = {v: (t, s) for _, v, t, _c, s in YT}
    return {"items": [{"id": i, "snippet": {"title": by[i][0], "description": ""},
                       "contentDetails": {"duration": f"PT{by[i][1] // 60}M{by[i][1] % 60}S"}} for i in ids if i in by]}


def fake_extract(user):
    kinds = json.loads(re.search(r"^Kinds wanted: (\[.*?\])", user, re.M).group(1))
    text = re.search(r"<item>(.*)</item>", user, re.S).group(1)
    out, sec = {k: [] for k in kinds}, None
    for line in text.splitlines():
        s = line.strip()
        if re.match(r"^ingredients?:?$", s, re.I):
            sec = "ingredients"
            continue
        if re.match(r"^steps:?$", s, re.I):
            sec = "steps"
            continue
        m = re.match(r"^(?:-|\d+\.)\s*(.+)$", s)
        if m:
            k = sec or "steps"
            if k in out:
                out[k].append(m.group(1))
    return out


def cands(user):
    return [(int(m.group(1)), m.group(2)) for m in re.finditer(r"^(\d+)\. .*?\n<item>(.*?)</item>", user, re.M | re.S)]


def composer(*plan):
    """plan: (needle, verdict, criteria answers): the picks the fake model returns, by caption words."""
    def f(user):
        picks = []
        for needle, verdict, crit in plan:
            for n, text in cands(user):
                if needle.lower() in text.lower():
                    picks.append({"n": n, "verdict": verdict, "title": needle, "because": "", "facts": [],
                                  "criteria": crit})
                    break
        return {"picks": picks, "intro": "I found some for you in your saves."} if picks else \
            {"picks": [], "none_reason": "The model's own words."}
    return f


def nomodel(u):
    raise RuntimeError("interpreter not expected")


@pytest.fixture()
def w(env, tmp_path, monkeypatch):
    from mvp.tests.test_slice5 import KEY, standard_fake
    from mvp.tests.test_slice6 import AllPool
    lib = write_library(tmp_path / "synlib")
    bot = env["bot"]
    bot.store.x("UPDATE people SET library=? WHERE handle=?", (str(lib), H))
    bot.views.clear()
    bot.pool = AllPool(str(lib))
    st = env["state"]["answers"]
    st["mvp_profile_guess"] = lambda u: {"topics": []}
    st["mvp_extract"] = fake_extract
    monkeypatch.setenv("YOUTUBE_API_KEY", KEY)
    from mvp.outside import Outside
    bot.outside = Outside(bot.store, http=standard_fake())
    from mvp import ytinfo
    monkeypatch.setattr(ytinfo, "fetch_batch", yt_fetch)
    bot.max_per_minute = 0
    return env


def say(w, text, form=None):
    w["state"]["answers"]["mvp_interpret"] = nomodel if form is None else (
        form if callable(form) else (lambda u, f=form: json.loads(json.dumps(f))))
    o0 = len(w["ch"].outbox)
    w["bot"].on_message(H, text)
    return "\n".join(str(m[2]) for m in w["ch"].outbox[o0:])


def tick_at(w, dt):
    w["clock"][0] = dt
    o0 = len(w["ch"].outbox)
    w["bot"].tick()
    return "\n".join(str(m[2]) for m in w["ch"].outbox[o0:])


def lib(goal, searches, when=None, **c):
    return {"when": when or {"type": "now"}, "content": {"source": "library", "goal": goal, "searches": searches, **c}}


def note(when, text):
    return {"intent": "new_rule", "spec": {"when": when, "content": {"source": "note", "text": text}}}


YES_ING = [{"answer": "yes", "quote": "Ingredients"}]
CR = {"intent": "ask", "spec": lib("quick chicken and rice dinners", ["chicken and rice"], count=3,
                                   extract=["ingredients", "steps"], criteria=["ends with a dish you can eat"])}


# ---------- X1: a rule keeps the number it was given ----------
def test_x1_stop_n_stops_the_rule_that_was_given_that_number(w):
    bot = w["bot"]
    a = say(w, "remind me to buy rice in 30 minutes", note({"type": "once", "in_minutes": 30}, "buy rice"))
    b = say(w, "every day at 9am remind me to stretch", note({"type": "schedule", "days": DAYS, "times": ["09:00"]},
                                                             "stretch"))
    c = say(w, "every day at 7pm remind me to floss", note({"type": "schedule", "days": DAYS, "times": ["19:00"]},
                                                           "floss"))
    assert '"stop 1"' in a and '"stop 2"' in b and '"stop 3"' in c
    assert "buy rice" in tick_at(w, datetime(2026, 11, 12, 18, 31, tzinfo=UTC))   # the one-time reminder: done
    foot = tick_at(w, datetime(2026, 11, 13, 0, 0, 30, tzinfo=UTC))                # 7pm New York: floss
    assert "floss" in foot and '"stop 3"' in foot
    listed = say(w, "my rules")
    assert re.search(r"^2\. .*stretch", listed, re.M) and re.search(r"^3\. .*floss", listed, re.M)
    assert say(w, "stop 2") == "Stopped: stretch."
    assert [r["spec"]["content"]["text"] for r in bot.store.rules(H)] == ["floss"]
    # a new rule never takes a number given before
    d = say(w, "every day at 8am remind me to read", note({"type": "schedule", "days": DAYS, "times": ["08:00"]},
                                                          "read"))
    assert '"stop 4"' in d
    # the interpreter's rule number is the rule's own number too: 1 and 2 are gone, 3 is floss
    assert say(w, "pause the floss one", {"intent": "pause", "rule_number": 3}) == "Paused: floss."
    assert say(w, "pause rule 1", {"intent": "pause", "rule_number": 1}) != "Paused: read."


def test_x1_a_store_from_an_older_build_keeps_the_numbers_it_showed(tmp_path):
    import sqlite3
    from mvp.store import Store
    path = tmp_path / "old.sqlite"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE rules (id INTEGER PRIMARY KEY AUTOINCREMENT, handle TEXT NOT NULL, text TEXT, "
               "spec TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT, next_run_at TEXT, last_run_at TEXT)")
    spec = json.dumps({"when": {"type": "on_request"}, "content": {"source": "note", "text": "x"}})
    for st in ("done", "active", "paused", "stopped", "active"):
        db.execute("INSERT INTO rules(handle,text,spec,status) VALUES(?,?,?,?)", (H, st, spec, st))
    db.commit()
    db.close()
    store = Store(str(path))
    # what an older build showed: active and paused rules by place
    assert [(r["number"], r["text"]) for r in store.rules(H)] == [(1, "active"), (2, "paused"), (3, "active")]
    new = store.add_rule(H, "new", json.loads(spec), "active", None)
    assert store.rule_number(H, new) == 6


# ---------- X2: reminders in the person's own words are not a stream they ignored ----------
def _water(w):
    w["clock"][0] = datetime(2026, 11, 12, 13, 30, tzinfo=UTC)   # 8:30am New York
    return say(w, "remind me to drink water every 2 hours from 9 to 5",
               note({"type": "schedule", "days": DAYS, "every_hours": 2, "window": ["09:00", "17:00"]}, "drink water"))


def test_x2_own_words_reminders_never_pause_the_rules_or_ask_still_useful(w):
    bot = w["bot"]
    from mvp import texts as T
    _water(w)
    sent = [tick_at(w, datetime(2026, 11, 12, hour, 0, 30, tzinfo=UTC)) for hour in (14, 16, 18, 20, 22)]
    assert all("drink water" in s for s in sent) and not any(T.STILL_USEFUL in s for s in sent)
    nxt = tick_at(w, datetime(2026, 11, 13, 14, 0, 30, tzinfo=UTC))
    assert "drink water" in nxt and T.PAUSED_QUIET not in nxt
    assert all(r["status"] == "active" for r in bot.store.rules(H))


def test_x2_a_rule_that_goes_over_the_daily_limit_with_the_others_says_so(w):
    from mvp import config
    _water(w)
    out = say(w, "every day at 6pm remind me to stretch",
              note({"type": "schedule", "days": DAYS, "times": ["18:00"]}, "stretch"))
    assert f"more than {config.MAX_SCHEDULED_PER_DAY} a day" in out
    # one more reminder well under the limit, with nothing else, says nothing about it
    bot = w["bot"]
    for r in bot.store.rules(H):
        bot.store.set_slot(r["id"], None, "stopped")
    out2 = say(w, "every day at 7pm remind me to floss",
               note({"type": "schedule", "days": DAYS, "times": ["19:00"]}, "floss"))
    assert "a day" not in out2.replace("every day", "")


def test_x2_a_thumbs_up_to_a_reminder_is_answered(w):
    _water(w)
    tick_at(w, datetime(2026, 11, 12, 14, 0, 30, tzinfo=UTC))
    w["clock"][0] = datetime(2026, 11, 12, 14, 5, tzinfo=UTC)
    from mvp import texts as T
    assert say(w, "👍") == T.KEEP_COMING
    out = say(w, "👎")
    assert '"stop 1"' in out and "Nothing to attach" not in out


# ---------- X3: adding to a list in Spanish ----------
def test_x3_spanish_add_the_ingredients_to_my_list_adds_them(w):
    bot = w["bot"]
    w["state"]["answers"]["mvp_compose"] = composer(("Instant pot chicken", "clear", YES_ING))
    say(w, "pollo con arroz", dict(CR, lang="es"))
    out = say(w, "agrega los ingredientes a mi lista del super",
              {"intent": "todo_add", "pick_number": 1, "what": "ingredients", "list": "super", "lang": "es"})
    texts = [t["text"] for t in bot.store.todos(H)]
    assert "2 chicken thighs" in texts and len(texts) == 4, out
    out2 = say(w, "agrégalo a mi lista", {"intent": "act_on_last", "actions": [{"action": "todo.add"}],
                                         "pick_number": 1, "lang": "es"})
    assert len(bot.store.todos(H)) == 5, out2


def test_x3_spanish_detail_words_are_read_as_a_detail_question():
    from mvp.followup import detail_kinds, only_detail_words
    assert detail_kinds("¿cuáles son los ingredientes?", "") == ["ingredients"]
    assert "steps" in detail_kinds("dame los pasos", "")
    assert only_detail_words("ingredientes por favor")


# ---------- X4: a yes/no question about a pick already shown ----------
def test_x4_a_question_the_posts_do_not_answer_names_the_pick(w):
    w["state"]["answers"]["mvp_compose"] = composer(("Instant pot chicken", "clear", YES_ING),
                                                     ("One pan chicken", "clear", YES_ING))
    say(w, "what can I make with chicken and rice?", CR)
    w["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [], "none_reason": "The second one has chicken."}
    out = say(w, "is the second one vegetarian?", {"intent": "follow_up", "question": "Is the second pick vegetarian?",
                                                    "pick_number": 2})
    assert "nothing in your library" not in out and "has chicken" not in out
    assert "I can't tell that from what One pan chicken" in out and "instagram.com/p/r3SYN" in out
    # one pick shown, a question about "the third one": which one?
    w["state"]["answers"]["mvp_compose"] = composer(("Instant pot chicken", "clear", YES_ING))
    say(w, "chicken and rice again?", CR)
    w["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [], "none_reason": "x"}
    out2 = say(w, "is the third one spicy?", {"intent": "follow_up", "question": "Is the third pick spicy?",
                                              "pick_number": 3})
    assert out2 == "My last message had 1 pick. Which one?"


# ---------- X5: "another" after three clear fits ----------
def test_x5_another_counts_the_fits_it_already_showed(w):
    w["state"]["answers"]["mvp_compose"] = composer(("Instant pot chicken", "clear", YES_ING),
                                                     ("One pan chicken", "clear", YES_ING),
                                                     ("Hainanese", "clear", [{"answer": "yes", "quote": "full recipe"}]))
    first = say(w, "what can I make with chicken and rice?", CR)
    assert "YouTube" not in first
    w["state"]["answers"]["mvp_compose"] = composer(("Chicken fried rice", "close", [{"answer": "unknown"}]))
    out = say(w, "another")
    assert "Chicken fried rice" in out
    assert not re.search(r"None of your saved \w+ fits", out) and "Nothing you saved fits" not in out


# ---------- X6: "ok sure, and I have an instant pot" at the last setup step ----------
def _to_last_setup_step(w):
    bot = w["bot"]
    bot.store.x("UPDATE people SET consent_version=NULL WHERE handle=?", (H,))
    say(w, "I agree")
    say(w, "skip", {"intent": "chat", "reply": "unused"})
    w["state"]["answers"]["mvp_first_requests"] = lambda u: {"requests": []}
    final = say(w, "skip", {"intent": "chat", "reply": "unused"})
    assert "OK?" in final and "Anything I should know" in final


def test_x6_a_yes_with_a_preference_starts_the_export_reminders_too(w):
    bot = w["bot"]
    _to_last_setup_step(w)
    w["state"]["answers"]["mvp_profile_merge"] = lambda u: {"kind": "about_me", "tools": ["instant pot"]}
    out = say(w, "ok sure, and I have an instant pot", {"intent": "profile_update"})
    assert out.startswith("Done. Next Instagram reminder") and "instant pot" in out.split("\n\n", 1)[1]
    assert len(bot.store.rules(H)) >= 1 and bot.store.pending(H) is None


def test_x6_a_no_with_a_preference_starts_nothing(w):
    bot = w["bot"]
    _to_last_setup_step(w)
    w["state"]["answers"]["mvp_profile_merge"] = lambda u: {"kind": "about_me", "tools": ["instant pot"]}
    out = say(w, "ok but no reminders, I have an instant pot", {"intent": "profile_update"})
    assert "Done. Next" not in out and bot.store.rules(H) == []


# ---------- X7: a rule made in Spanish is never two languages in one reply ----------
SPANISH = re.compile(r"\b(Te recomiendo|Lo más parecido|nada de tu biblioteca|Lo que guardaste|Encontré|guardaste)\b")


def test_x7_a_spanish_rule_preview_and_its_timed_sends_are_one_language(w):
    w["state"]["answers"]["mvp_compose"] = composer(
        ("20 minute full body", "clear", [{"answer": "yes", "quote": "full body"}]),
        ("Morning mobility", "clear", [{"answer": "yes", "quote": "full routine"}]))
    prev = say(w, "cada mañana a las 8 mandame un workout", {"intent": "new_rule", "lang": "es", "spec": lib(
        "un workout", ["workout"], when={"type": "schedule", "days": DAYS, "times": ["08:00"]}, count=1,
        criteria=["a full routine from start to finish"])})
    assert "Every day at 8am" in prev and not SPANISH.search(prev), prev
    say(w, "si", {"intent": "confirm", "lang": "es"})
    # the same thread, with Spanish left over from the last message, and nothing found: one language
    w["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [], "none_reason": "x"}
    w["bot"]._tl.lang = "es"
    nothing = tick_at(w, datetime(2026, 11, 13, 13, 0, 30, tzinfo=UTC))
    assert nothing and not SPANISH.search(nothing), nothing
    # on the scheduler's own thread too
    w["state"]["answers"]["mvp_compose"] = composer(("Morning mobility", "clear",
                                                     [{"answer": "yes", "quote": "full routine"}]))
    w["clock"][0] = datetime(2026, 11, 14, 13, 0, 30, tzinfo=UTC)
    o0 = len(w["ch"].outbox)
    t = threading.Thread(target=w["bot"].tick)
    t.start()
    t.join()
    sent = "\n".join(str(m[2]) for m in w["ch"].outbox[o0:])
    assert "Morning mobility" in sent and not SPANISH.search(sent)
