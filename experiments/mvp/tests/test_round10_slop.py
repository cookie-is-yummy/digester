"""Round 10, slice S (DESIGN.md section 17.S): reels whose caption may not match the video ("slop").

A synthetic library only: a made-up meme account with three pasted chatbot recipes, a real creator with a joke hook,
a repost page copying another creator's genuine caption, a coach who uses **bold** in their own tips, and a caption
that says it is unrelated. The fake model (tests/test_mvp.py) answers; no test makes a real model call."""
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
from mvp.tests.test_slice6 import AllPool  # noqa: E402

MVP = os.path.dirname(HERE)

MEME_RECIPE = ("Here's a delicious recipe for {dish}:\n\n**Ingredients:**\n- 2 cups pasta\n- 1 cup cream\n"
               "- 3 tbsp butter\n- 2 cloves garlic\n\n**Instructions:**\n1. Boil the pasta until soft.\n"
               "2. Melt the butter with the garlic.\n3. Stir in the cream and simmer.\nEnjoy your delicious {dish}!")
BROWNIES = ("Fudgy brownies\nIngredients:\n- 200g dark chocolate\n- 150g butter\n- 3 eggs\n- 200g sugar\n- 100g flour\n"
            "Melt, whisk, fold and bake 25 minutes at 180C until just set in the middle.")
ROWS = [
    # a made-up meme account: three chatbot recipes pasted under its clips
    ("m1", "lol_clipz_daily", "Daily LOL Clips", MEME_RECIPE.format(dish="Chicken Alfredo"), ["like"]),
    ("m2", "lol_clipz_daily", "Daily LOL Clips", MEME_RECIPE.format(dish="Garlic Pasta"), ["like"]),
    ("m3", "lol_clipz_daily", "Daily LOL Clips", MEME_RECIPE.format(dish="Creamy Penne"), ["like"]),
    # a real creator with a joke hook over their own recipe
    ("j1", "chef_rosa", "Rosa Cooks", "POV: my flatmate ate it all 💀\nMy lasagne, the way I make it every week\n"
     "Ingredients:\n- 500g pasta sheets\n- 400g tomato sauce\n- 250g ricotta\n- 100g parmesan", ["save"]),
    # a genuine creator and a repost page that copies their caption word for word
    ("g1", "baker_jo", "Jo Bakes", BROWNIES, ["save"]),
    ("r1", "food.finds.page", "Food Finds", BROWNIES, ["like"]),
    # a coach who uses **bold** in their own tips
    ("c1", "coach_kim", "Coach Kim", "5 habits that changed my mornings\n1. **Wake up early** and drink water first\n"
     "2. **Move your body** for ten minutes\n3. **Plan the day** before you open email\n"
     "4. **No phone** for the first hour\n5. **Read a page** of a good book", ["save"]),
    # a caption that says it has nothing to do with the clip
    ("u1", "random_vids_hub", "", "Don't mind this post. Here is a strudel recipe:\nIngredients:\n- 2 apples\n"
     "- 1 sheet pastry\n- 50g sugar\n- 1 tsp cinnamon\nRoll, bake 30 minutes.", ["like"]),
    # a genuine recipe with no mark: the fit that should lead
    ("ok1", "home_cook_ann", "Ann", "Creamy chicken alfredo, the one I make on busy nights\nIngredients:\n"
     "- 300g fettuccine\n- 2 chicken breasts\n- 200ml cream\n- 50g parmesan\nSteps:\n1. Cook the pasta.\n"
     "2. Sear the chicken.\n3. Stir in cream and cheese.", ["save"]),
]


def write_lib(path, rows=ROWS):
    (path / "corpus").mkdir(parents=True, exist_ok=True)
    with open(path / "corpus" / "items.jsonl", "w") as f:
        for iid, handle, name, cap, kinds in rows:
            f.write(json.dumps({"id": iid, "platform": "instagram", "source_url": f"https://example.com/{iid}",
                                "caption": cap, "interaction_kinds": kinds,
                                "platform_data": {"owner_handle": handle, "owner_name": name,
                                                  "owner_relation": "none", "media_kind": "reel"}}) + "\n")
    with open(path / "corpus" / "interactions.jsonl", "w") as f:
        for iid, *_, kinds in rows:
            f.write(json.dumps({"item_id": iid, "kind": kinds[0], "at": "2026-03-01T10:00:00+00:00"}) + "\n")
    return str(path)


def raw_rows(rows=ROWS):
    return [{"id": iid, "platform": "instagram", "caption": cap, "interaction_kinds": kinds,
             "platform_data": {"owner_handle": handle, "owner_name": name, "owner_relation": "none"}}
            for iid, handle, name, cap, kinds in rows]


@pytest.fixture()
def slop(env, tmp_path):
    """The env bot on the synthetic library, with its caption marks built (as refresh or the bot's start would)."""
    from mvp import captionmark
    lib = write_lib(tmp_path / "sloplib")
    captionmark.build_file(lib)
    env["bot"].store.x("UPDATE people SET library=? WHERE handle=?", (lib, H))
    env["bot"].pool = AllPool(lib)
    env["slib"] = lib
    env["bot"].max_per_minute = None
    return env


def cands_of(user):
    """{candidate number: its text} from the composer's prompt."""
    return {int(n): t for n, t in re.findall(r"^(\d+)\. [^\n]*\n<item>(.*?)</item>", user, re.M | re.S)}


def composer(*order):
    """A fake composer that returns the candidates whose text holds each (words, verdict, title) in that order."""
    def compose(user):
        cs = cands_of(user)
        out = []
        for words, verdict, title in order:
            n = next((n for n, t in sorted(cs.items()) if words.lower() in t.lower() and n not in
                      [p["n"] for p in out]), None)
            if n is not None:
                out.append({"n": n, "verdict": verdict, "title": title, "because": "", "facts": []})
        return {"picks": out, "intro": ""}
    return compose


ALFREDO = {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {
    "goal": "a chicken alfredo recipe", "searches": ["chicken alfredo recipe"], "count": 3,
    "extract": "ingredients"}}}


def ask(env, compose, spec=ALFREDO, text="a chicken alfredo recipe"):
    env["state"]["answers"]["mvp_compose"] = compose
    env["state"]["answers"]["mvp_extract"] = lambda u: {"ingredients": []}
    return say(env, text, spec)


def run_steps(env):
    r = env["bot"].store.one("SELECT steps FROM runs WHERE kind='ask' ORDER BY id DESC LIMIT 1")
    return json.loads(r["steps"] or "{}")


# ---------- S1: the mark ----------
def test_the_marks_on_the_synthetic_library_are_as_designed():
    from mvp import captionmark
    m = captionmark.build_rows(raw_rows())
    level = {i: (m.get(i) or [None])[0] for i, *_ in ROWS}
    assert level["m1"] == level["m2"] == level["m3"] == "strong"   # chatbot openers, a meme account
    assert "chatbot_text" in m["m1"][1] and "account_memes" in m["m1"][1]
    assert level["u1"] == "strong" and m["u1"][1][0] == "says_unrelated"
    assert level["j1"] != "strong"    # the creator's own voice under a joke hook: never strong
    assert level["g1"] != "strong" and level["r1"] != "strong"   # pasted from one other account alone: never strong
    assert "pasted_elsewhere" in m["r1"][1]
    assert level["c1"] != "strong"    # **bold** in a coach's own tips: never strong
    assert level["ok1"] is None
    assert m["m1"][2] == captionmark.fingerprint(ROWS[0][3]) and len(m["m1"][2]) == 16
    assert set(r for v in m.values() for r in v[1]) <= set(captionmark.REASONS)


def test_near_variants_of_the_signals():
    from mvp import captionmark as cm
    assert cm.OPENER.search("No problem! Here's the information about it")
    assert cm.OPENER.search("Sure, here is a simple guide to sourdough")
    assert not cm.OPENER.search("Here's how I make my sourdough every week")   # the creator's own voice
    assert cm.DISCLAIM.search("caption for the algo, ignore it")
    assert not cm.DISCLAIM.search("the algorithm loved this one")
    assert cm.own_voice("Follow @x for more\nI make this every Sunday")       # a follow line is skipped
    assert not cm.own_voice("Ingredients:\n- 2 eggs\nwe love it")               # third line: not looked at
    # a caption in another language is missed, never a false alarm
    spanish = ("¡Aquí tienes una receta deliciosa de pollo!\nIngredientes:\n- 2 tazas de arroz\n- 1 pollo\n"
               "Instrucciones: cocina todo junto 20 minutos.")
    assert not cm.build_rows([{"id": "s", "platform": "instagram", "caption": spanish,
                               "platform_data": {"owner_handle": "cocina_casa"}}])
    # YouTube rows are never marked (the uploader's own title is the text)
    assert not cm.build_rows([{"id": "y", "platform": "youtube", "caption": MEME_RECIPE.format(dish="x"),
                               "platform_data": {"owner_name": "funny clips"}}])
    # the same chatbot recipe under a single account with a plain name and no other evidence: a weak mark at most
    one = cm.build_rows([{"id": "a", "platform": "instagram", "caption": BROWNIES + "\n**Enjoy**",
                          "platform_data": {"owner_handle": "plain_kitchen"}}])
    assert (one.get("a") or [None])[0] in (None, "weak")


def test_the_marks_file_is_derived_versioned_and_never_built_by_the_view(tmp_path):
    from mvp import captionmark
    from mvp.libview import LibraryView
    lib = write_lib(tmp_path / "lib1")
    v = LibraryView(lib)
    assert not os.path.exists(captionmark.marks_path(lib))   # a miss never builds (W-8): no item is marked yet
    assert all(it.caption_mark is None for it in v.items.values())
    assert captionmark.ensure(v)
    assert v.get("m1").caption_mark == "strong" and v.get("ok1").caption_mark is None
    data = json.load(open(captionmark.marks_path(lib)))
    assert data["version"] == "cm-v1" and set(data["items"]) == {i for i, x in data["items"].items() if x[0]}
    log = [json.loads(x) for x in open(os.path.join(lib, "marks", "build_log.jsonl"))]
    assert set(log[-1]) >= {"items", "marked_strong", "marked_weak", "items_per_s", "wall_s"}
    assert LibraryView(lib).get("m1").caption_mark == "strong"   # a new view reads the file
    # the library is rebuilt: the old file is not used until it is built again
    with open(os.path.join(lib, "corpus", "items.jsonl"), "a") as f:
        f.write(json.dumps({"id": "new", "platform": "instagram", "caption": "x", "platform_data": {}}) + "\n")
    os.utime(os.path.join(lib, "corpus", "items.jsonl"), (1, 1))
    assert LibraryView(lib).get("m1").caption_mark is None
    # a new version writes beside the old one
    old = captionmark.SIGNAL_VERSION
    try:
        captionmark.SIGNAL_VERSION = "cm-test"
        captionmark.build_file(lib)
        assert os.path.exists(captionmark.marks_path(lib, "cm-test")) and os.path.exists(captionmark.marks_path(lib, old))
    finally:
        captionmark.SIGNAL_VERSION = old
    # friends' posts are never read for marks (rule 5)
    rows = captionmark._rows(write_lib(tmp_path / "lib2", [("f", "pal", "", MEME_RECIPE.format(dish="x"), ["like"])]))
    assert len(rows) == 1
    p = tmp_path / "lib3"
    write_lib(p)
    lines = open(p / "corpus" / "items.jsonl").read().replace('"owner_relation": "none"', '"owner_relation": "mutual"')
    (p / "corpus" / "items.jsonl").write_text(lines)
    assert captionmark._rows(str(p)) == []


def test_probe_same_and_env_fixtures_carry_no_mark(env, tmp_path):
    """probe_same's library (the round 7 probe) and the shared test library: 0 marks, so their bytes cannot change."""
    from mvp import captionmark
    probe = [
        ("r1", "cook", "One pot chicken and rice\nIngredients:\n- 2 cups rice\n- 1 lb chicken thighs\nSteps:\n"
         "1. Brown the chicken.\n2. Add the rice and 3 cups water.\n3. Cook 20 minutes."),
        ("r2", "cook2", "Instant pot chicken rice, ready in 15 minutes\nIngredients:\n- 1 cup rice\n- 2 chicken breasts"),
        ("r3", "cook3", "Chicken fried rice in 10 minutes"),
        ("w1", "coach", "20 minute full body workout\n1. Squats x 15\n2. Push ups x 10\n3. Lunges x 12"),
        ("w2", "coach2", "Core workout for beginners\n- Plank 30 seconds\n- Dead bug x 10"),
        ("b1", "artist", "Blender beginner donut tutorial part 1"),
        ("t1", "prod", "5 productivity tips:\n1. Time blocking: plan each hour\n2. Pomodoro: 25 minutes on, 5 off"),
        ("t2", "prod2", "Morning routine for focus and calm"),
        ("m1", "mot", "Startup motivation: keep going when it gets hard"),
        ("s1", "trav", "Best cafes in Lisbon:\n- Fabrica Coffee: great espresso\n- Hello Kristof: tiny and calm")]
    rows = [{"id": i, "platform": "instagram", "caption": c, "platform_data": {"owner_handle": w}} for i, w, c in probe]
    assert captionmark.build_rows(rows) == {}
    assert captionmark.build_file(str(env["lib"]))["counts"]["strong"] == 0
    assert json.load(open(captionmark.marks_path(str(env["lib"]))))["items"] == {}


# ---------- S3: ranking ----------
def test_ranking_drops_the_long_caption_boost_and_weighs_a_strong_mark_down(tmp_path):
    from mvp import captionmark
    from mvp.libview import LibraryView
    from mvp.retrieve import candidates
    from mvp.schema import RuleSpec
    lib = write_lib(tmp_path / "rk", [ROWS[0], ROWS[-1]])   # the meme recipe first in the search, then the genuine one
    captionmark.build_file(lib)
    v = LibraryView(lib)

    class Pool:   # the meme recipe first; the genuine one 40 places lower (ids not in the library still take a rank)
        def search(self, lib, q, depth=300):
            return {"ids": ["m1"] + [f"gone{i}" for i in range(39)] + ["ok1"], "mode": "normal", "cost_usd": 0.0}
    how = RuleSpec.model_validate({"when": {"type": "now"}, "content": {"goal": "a recipe", "searches": ["alfredo"],
                                                                        "extract": "ingredients"}})
    out, _ = candidates(Pool(), v, how)
    assert [it.id for it in out] == ["ok1", "m1"]   # x0.4 on a how-to request; still in the window
    other = RuleSpec.model_validate({"when": {"type": "now"}, "content": {"goal": "funny clips", "searches": ["x"]}})
    out, _ = candidates(Pool(), v, other)
    assert [it.id for it in out] == ["m1", "ok1"]   # x0.8 only: 1.1 * 0.8/60 (a like) still beats 1.3/100 (a save)
    assert captionmark.rank_factor("strong", True) == 0.4 and captionmark.rank_factor("strong", False) == 0.8
    assert captionmark.rank_factor("weak", True) == 1.0 and captionmark.rank_factor(None, True) == 1.0
    # without the file: today's order and boost
    os.remove(captionmark.marks_path(lib))
    out, _ = candidates(Pool(), LibraryView(lib), how)
    assert [it.id for it in out] == ["m1", "ok1"]


# ---------- S3: order, the only fit, the titles ----------
def test_a_strong_pick_never_leads_when_an_unmarked_fit_exists(slop):
    msg = ask(slop, composer(("recipe for Chicken Alfredo", "clear", "Chicken Alfredo"), ("busy nights", "clear",
                                                                               "Creamy chicken alfredo")))
    assert msg.startswith("Here's what I found") or "I recommend Creamy chicken alfredo" in msg
    assert "I recommend Creamy chicken alfredo by @home_cook_ann" in msg
    assert "A reel from @lol_clipz_daily" in msg and "Chicken Alfredo" not in msg.replace("chicken alfredo", "")
    assert msg.index("@home_cook_ann") < msg.index("@lol_clipz_daily")
    assert "Heads-up" not in msg and "only match" not in msg
    assert run_steps(slop).get("mark_demoted") == 1


def test_a_close_unmarked_fit_leads_over_a_clear_strong_one_and_is_called_the_closest(slop):
    msg = ask(slop, composer(("recipe for Chicken Alfredo", "clear", "Chicken Alfredo"), ("busy nights", "close",
                                                                               "Creamy chicken alfredo")))
    assert "The closest I have is Creamy chicken alfredo" in msg and "I recommend" not in msg
    assert run_steps(slop).get("mark_demoted") == 1


def test_the_only_fit_is_said_plainly_with_a_neutral_title_and_the_doubt_line(slop):
    msg = ask(slop, composer(("recipe for Chicken Alfredo", "clear", "Chicken Alfredo")))
    lines = msg.split("\n")
    lead = next(i for i, x in enumerate(lines) if x.startswith("The only match I found is"))
    assert lines[lead].startswith("The only match I found is A reel from @lol_clipz_daily, which you liked")
    assert lines[lead + 1] == ("Heads-up: its caption is a recipe, but the account mostly posts memes, so the video "
                               "may show something else.")
    assert "I recommend" not in msg and "Chicken Alfredo" not in msg
    stored = slop["bot"].store.one("SELECT picks FROM answers ORDER BY run_id DESC LIMIT 1")
    assert json.loads(stored["picks"])[0]["title"] == "A reel from @lol_clipz_daily"   # what outputs and to-dos use


def test_the_doubt_reason_follows_the_fixed_order_and_the_precision_switch(slop, monkeypatch):
    from mvp import captionmark, config
    assert captionmark.doubt_reason(["chatbot_text", "account_memes", "says_unrelated"]) == "says_unrelated"
    assert captionmark.doubt_reason(["you_said", "account_memes"]) == "you_said"
    assert captionmark.doubt_reason(["chatbot_text", "pasted_elsewhere"]) == "pasted_elsewhere"
    assert captionmark.doubt_reason(["account_mostly_chatbot"]) == "account_memes"
    assert captionmark.doubt_reason(["chatbot_text"], all_reasons=False) is None
    msg = ask(slop, composer(("strudel", "clear", "Apple strudel")), spec={"intent": "ask", "spec": {
        "when": {"type": "now"}, "content": {"goal": "a strudel recipe", "searches": ["strudel"], "count": 1}}},
        text="a strudel recipe")
    assert "Heads-up: its caption is a recipe, but the caption itself says it has nothing to do with the video" in msg
    monkeypatch.setattr(config, "CM_DOUBT_ALL", False)   # below 85% precision: only the reasons that do not rest on it
    msg = ask(slop, composer(("recipe for Chicken Alfredo", "clear", "Chicken Alfredo")))
    assert "Going by its caption: I can't watch the video, so check it shows the same." in msg
    assert "memes" not in msg


def test_details_of_a_strong_only_fit_sit_under_from_the_caption(slop):
    slop["state"]["answers"]["mvp_compose"] = composer(("recipe for Chicken Alfredo", "clear", "Chicken Alfredo"))
    slop["state"]["answers"]["mvp_extract"] = lambda u: {"ingredients": ["2 cups pasta", "1 cup cream"]}
    msg = say(slop, "a chicken alfredo recipe", ALFREDO)
    assert "From the caption:\nIngredients (2):" in msg


def test_a_weak_lead_on_a_how_to_request_gets_the_caption_line_and_keeps_its_place(slop):
    from mvp.libview import LibraryView
    assert LibraryView(slop["slib"]).get("c1").caption_mark == "weak"
    spec = {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {
        "goal": "morning routine tips", "searches": ["morning habits"], "count": 2}}}
    msg = ask(slop, composer(("habits", "clear", "5 habits for mornings"), ("busy nights", "clear", "Alfredo")),
              spec=spec, text="morning routine tips")
    assert "I recommend 5 habits for mornings" in msg
    assert "Going by its caption: I can't watch the video, so check it shows the same." in msg
    assert "mark_demoted" not in run_steps(slop)
    # not a how-to request: no line
    spec = {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {"goal": "something about mornings",
                                                                           "searches": ["mornings"], "count": 1}}}
    msg = ask(slop, composer(("habits", "clear", "5 habits for mornings")), spec=spec, text="something about mornings")
    assert "Going by its caption" not in msg


def test_display_title_rules():
    from types import SimpleNamespace as S
    from mvp.compose import display_title, title_from_item
    base = dict(platform="instagram", creator="@x", media="reel", caption_reasons=(), caption_fp=None)
    meme = S(**base, caption_mark="strong", first_line="Chicken Alfredo", caption="Chicken Alfredo",
             raw_caption="Chicken Alfredo")
    assert display_title(meme, "Chicken Alfredo") == "A reel from @x"
    assert display_title(meme, "Chicken Alfredo", level=None) == "Chicken Alfredo"   # the person said it was fine
    plain = S(**base, caption_mark=None, first_line="Here's a delicious recipe for Chicken Alfredo:",
              caption="Here's a delicious recipe for Chicken Alfredo: pasta", raw_caption="")
    assert title_from_item(plain).startswith("Here's a delicious")   # the internal keys keep the item's own words
    assert display_title(plain) == "A reel from @x"   # never an assistant's opener as a name
    assert display_title(plain, "Alfredo") == "Alfredo"
    yt = S(platform="youtube", creator="Some Channel", media=None, caption_mark="strong", first_line="x", caption="x")
    assert display_title(yt, "x") == "A video from Some Channel"


def test_the_display_call_sites_use_display_title_and_the_internal_ones_keep_the_item_words():
    """W-9: display uses go through compose.display_title; title_from_item stays only where it builds keys."""
    allowed = {"compose.py": {"def title_from_item", "title_from_item(it, words=1000)", "for t in (title_from_item(it), ",
                              "title = title_from_item(it)\n    return neutral_title", "(title_from_item: never"},
               "executor.py": {"from .compose import title_from_item", "title_from_item(it, words=1000)"},
               "followup.py": {"from .compose import own_text, title_from_item", "title_from_item(x, words=1000)"}}
    for name in ("executor.py", "followup.py", "outputs.py", "handler.py", "compose.py", "render.py", "todos.py",
                 "drafts.py", "places.py", "postacts.py", "receipts.py"):
        src = open(os.path.join(MVP, name), encoding="utf-8").read()
        for m in re.finditer(r"title_from_item", src):
            line = src[src.rfind("\n", 0, m.start()) + 1:src.find("\n", m.end())]
            ok = any(a.split("\n")[0] in line for a in allowed.get(name, ())) or "def display_title" in line \
                or line.strip().startswith(("\"", "#", "line its name", "differently"))
            assert ok, (name, line)
    src = open(os.path.join(MVP, "executor.py"), encoding="utf-8").read()
    assert src.count("display_title(") >= 3
    for name, n in (("followup.py", 2), ("handler.py", 1), ("outputs.py", 1)):
        assert open(os.path.join(MVP, name), encoding="utf-8").read().count("display_title(") >= n, name


# ---------- S2: what the person says ----------
def test_fit_reads_learns_a_mismatch_and_takes_the_reel_out(slop):
    bot = slop["bot"]
    ask(slop, composer(("busy nights", "clear", "Creamy chicken alfredo"), ("recipe for Garlic Pasta", "close", "Garlic pasta")))
    out = say(slop, "the second one had nothing to do with it", {"intent": "chat", "reply": "?"})
    assert out == ("Thanks, that helps. I've taken that reel out of your picks and I'll trust captions from "
                   "@lol_clipz_daily less from now on. Say \"another\" for a different one.")
    rows = bot.store.caption_feedback(H)
    assert [(r["item_id"], r["kind"], r["source"]) for r in rows] == [("m2", "mismatch", "words")]
    assert "m2" in bot.store.disliked(H)
    from mvp import captionmark
    fb = captionmark.index(rows)
    v = bot.view(slop["slib"])
    assert captionmark.effective(v.get("c1"), fb)[0] == "weak"   # another account: unchanged
    assert captionmark.creator_weights(fb) == {"@lol_clipz_daily": 0.5}
    # "that one was fine" on the same reel: trusted again, back in the picks
    out = say(slop, "that one was fine", {"intent": "chat", "reply": "?"})
    assert out == "Good to know. I'll trust @lol_clipz_daily's captions again." or "Good to know." in out


def test_fit_reads_phrasings_and_what_it_leaves_alone(slop):
    from mvp import captionmark as cm
    for t in ("that reel had nothing to do with it", "the video doesn't match", "wrong video", "it's just a meme",
              "the caption was copied", "the video is something else", "reel 2 had nothing to do with chicken",
              "the caption has nothing to do with the video", "the 2nd one had nothing to do with it"):
        assert cm.MISMATCH.search(t), t
    for t in ("that one was fine", "the video was right", "it did match", "the caption was right"):
        assert cm.MATCH_OK.search(t), t
    for t in ("slop", "that's slop", "this is slop!", "pure slop"):
        assert cm.SLOP.search(t), t
    for t in ("another", "find me a video about matching outfits", "stop sending memes", "that one was fine but long",
              "I love slop bowls", "the video was fine yesterday but"):
        assert not (cm.MISMATCH.search(t) or cm.MATCH_OK.search(t) or cm.SLOP.search(t)), t
    # with no answer in view, nothing is taken
    bot = slop["bot"]
    slop["state"]["answers"]["mvp_interpret"] = lambda u: {"intent": "chat", "reply": "Hi."}
    bot.on_message(H, "wrong video")
    assert last(slop["ch"]) == "Hi." and bot.store.caption_feedback(H) == []


def test_fit_reads_needs_an_answer_from_the_last_48_hours(slop):
    ask(slop, composer(("busy nights", "clear", "Creamy chicken alfredo")))
    slop["clock"][0] += timedelta(hours=49)
    out = say(slop, "the video doesn't match", {"intent": "chat", "reply": "Okay."})
    assert out == "Okay." and slop["bot"].store.caption_feedback(H) == []


def test_slop_asks_first_and_the_answer_learns(slop):
    bot = slop["bot"]
    ask(slop, composer(("recipe for Chicken Alfredo", "clear", "Chicken Alfredo")))
    assert say(slop, "that's slop", {"intent": "chat"}) == ("Was it that the video didn't match what its caption "
                                                           "said? Reply \"yes\" or \"no\".")
    assert bot.store.caption_feedback(H) == []   # "slop" alone teaches nothing (W-6)
    out = say(slop, "yes", {"intent": "chat"})
    assert out.startswith("Thanks, that helps.") and "@lol_clipz_daily" in out
    assert [r["kind"] for r in bot.store.caption_feedback(H)] == ["mismatch"]
    # "no" after the question
    ask(slop, composer(("busy nights", "clear", "Creamy chicken alfredo")))
    say(slop, "slop", {"intent": "chat"})
    assert say(slop, "no", {"intent": "chat"}) == "OK, noted."
    assert len(bot.store.caption_feedback(H)) == 1
    # any other message ends the question: a later "yes" is not taken
    say(slop, "slop", {"intent": "chat"})
    say(slop, "what time is it", {"intent": "chat", "reply": "Not sure."})
    assert say(slop, "yes", {"intent": "chat", "reply": "Yes to what?"}) == "Yes to what?"


def test_the_fingerprint_reaches_copies_under_other_accounts(slop):
    bot = slop["bot"]
    ask(slop, composer(("Fudgy", "clear", "Fudgy brownies")), spec={"intent": "ask", "spec": {
        "when": {"type": "now"}, "content": {"goal": "brownies", "searches": ["brownies"], "count": 1}}},
        text="brownies")
    out = say(slop, "the video doesn't match", {"intent": "chat"})
    assert out.endswith("The same text is under 1 other account; I'll treat those the same.")
    from mvp import captionmark
    fb = captionmark.index(bot.store.caption_feedback(H))
    v = bot.view(slop["slib"])
    said = bot.store.caption_feedback(H)[0]["item_id"]
    other = "r1" if said == "g1" else "g1"
    level, reasons = captionmark.effective(v.get(other), fb)
    assert level == "strong" and reasons[0] == "you_said"


def test_creator_learning_two_mismatches_and_two_fines(slop):
    from types import SimpleNamespace as S
    from mvp import captionmark
    rows = [{"item_id": "a", "creator": "@k", "fp": None, "kind": "mismatch"}]
    fb = captionmark.index(rows)
    howto_cap = "Ingredients:\n- 2 cups rice\n- 1 tbsp oil\n- 3 cups water"

    def item(i, level, cap="short"):
        return S(id=i, creator="@k", platform="instagram", caption=cap, raw_caption=cap, caption_mark=level,
                 caption_reasons=("chatbot_text",) if level else (), caption_fp=None)
    assert captionmark.effective(item("b", "weak"), fb)[0] == "strong"     # one mismatch: weak becomes strong
    assert captionmark.effective(item("c", None, howto_cap), fb)[0] is None  # an unmarked how-to: not yet
    fb2 = captionmark.index(rows + [{"item_id": "d", "creator": "@k", "fp": None, "kind": "mismatch"}])
    assert captionmark.effective(item("c", None, howto_cap), fb2)[0] == "strong"   # two: every how-to of theirs
    assert captionmark.effective(item("e", None), fb2)[0] is None                # a short caption stays unmarked
    fine = captionmark.index(rows + [{"item_id": "f", "creator": "@k", "fp": None, "kind": "match_ok"}])
    assert captionmark.creator_weights(fine) == {}                                # a "fine" clears the weight
    two_fine = captionmark.index([{"item_id": x, "creator": "@k", "fp": None, "kind": "match_ok"} for x in "gh"])
    assert captionmark.effective(item("i", "strong"), two_fine)[0] == "weak"
    assert captionmark.effective(item("g", "strong"), two_fine)[0] is None        # that item itself: no mark


def test_a_creator_said_to_mismatch_counts_half_in_the_next_answer(slop):
    from mvp import captionmark, executor
    seen = {}
    real = executor.candidates

    def spy(*a, **kw):
        seen.update(kw)
        return real(*a, **kw)
    ask(slop, composer(("busy nights", "clear", "Creamy chicken alfredo"), ("recipe for Garlic Pasta", "close", "Garlic")))
    say(slop, "the second one had nothing to do with it", {"intent": "chat"})
    import mvp.executor as ex
    ex.candidates = spy
    try:
        ask(slop, composer(("busy nights", "clear", "Creamy chicken alfredo")))
    finally:
        ex.candidates = real
    assert seen["creator_weights"].get("@lol_clipz_daily") == 0.5
    assert seen["caption_fb"]["items"] == {"m2": "mismatch"} and "m2" in seen["disliked"]
    assert captionmark.creator_weights(seen["caption_fb"]) == {"@lol_clipz_daily": 0.5}


# ---------- S2: the thumbs-down question and its guards (W-7) ----------
def test_a_thumbs_down_on_a_marked_answer_asks_once(slop):
    bot = slop["bot"]
    ask(slop, composer(("recipe for Chicken Alfredo", "clear", "Chicken Alfredo")))
    out = say(slop, "👎", {"intent": "chat"})
    assert out == "Noted. I won't send that again.\n\nWas it that the video didn't match what its caption said? " \
                  "Reply \"yes\" or \"no\"."
    out = say(slop, "yes", {"intent": "chat"})
    assert out.startswith("Thanks, that helps.")
    assert [(r["kind"], r["source"]) for r in bot.store.caption_feedback(H)] == [("mismatch", "thumbs")]
    assert say(slop, "👎", {"intent": "chat"}) == "Noted. I won't send that again."   # once per answer


def test_a_thumbs_down_on_an_answer_with_nothing_marked_and_no_instagram_how_to_asks_nothing(slop, tmp_path):
    spec = {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {"goal": "mornings", "searches": ["x"],
                                                                           "count": 1}}}
    rows = [("p1", "plain_page", "", "A calm morning walk by the sea", ["save"])]
    from mvp import captionmark
    lib = write_lib(tmp_path / "plainlib", rows)
    captionmark.build_file(lib)
    slop["bot"].store.x("UPDATE people SET library=? WHERE handle=?", (lib, H))
    slop["bot"].pool = AllPool(lib)
    ask(slop, composer(("walk", "clear", "A calm morning walk")), spec=spec, text="mornings")
    assert say(slop, "👎", {"intent": "chat"}) == "Noted. I won't send that again."


def test_the_question_is_not_asked_when_a_preview_or_a_draft_is_newer_or_a_browser_run_is_open(slop, monkeypatch):
    from mvp import browser
    bot = slop["bot"]
    ask(slop, composer(("recipe for Chicken Alfredo", "clear", "Chicken Alfredo")))
    run_at = bot.store.one("SELECT at FROM runs WHERE kind='ask' ORDER BY id DESC LIMIT 1")["at"]
    from datetime import datetime
    later = datetime.fromisoformat(run_at) + timedelta(minutes=1)
    bot.store.set_pending(H, "confirm_rule", {"spec": {}}, at=later)
    person = bot.store.person(H)
    items = bot.store.last_answer(H)["items"]
    run_id = bot.store.last_answer(H)["run_id"]
    assert bot._mismatch_offer(person, run_id, items, None, slop["clock"][0]) is None   # a preview is newer
    bot.store.clear_pending(H)
    bot.store.set_state(f"draft_open:{H}", {"id": 1, "at": later.isoformat()})
    monkeypatch.setattr(type(bot), "open_draft", lambda self, h, now=None: {"state": {"at": later.isoformat()}})
    assert bot._mismatch_offer(person, run_id, items, None, slop["clock"][0]) is None   # a draft card is newer
    monkeypatch.setattr(type(bot), "open_draft", lambda self, h, now=None: None)
    monkeypatch.setattr(browser, "run_open", lambda store, h, now=None: True)
    assert bot._mismatch_offer(person, run_id, items, None, slop["clock"][0]) is None   # a browser run is open
    monkeypatch.setattr(browser, "run_open", lambda store, h, now=None: False)
    assert bot._mismatch_offer(person, run_id, items, None, slop["clock"][0]) is not None


def test_a_tapback_down_asks_and_a_typed_reaction_too(slop):
    bot = slop["bot"]
    ask(slop, composer(("recipe for Chicken Alfredo", "clear", "Chicken Alfredo")))
    run_id = bot.store.last_answer(H)["run_id"]
    bot.store.record_sent("ref-1", H, run_id)
    n = len(slop["ch"].outbox)
    bot.on_message(H, "", tapback="down", tapback_ref="ref-1")
    assert len(slop["ch"].outbox) == n + 1 and last(slop["ch"]).startswith("Was it that the video didn't match")
    bot.on_message(H, "", tapback="down", tapback_ref="ref-1")   # once per answer
    assert len(slop["ch"].outbox) == n + 1
    ask(slop, composer(("busy nights", "clear", "Creamy chicken alfredo")))
    bot.on_message(H, "Disliked “I recommend Creamy chicken alfredo”")
    assert last(slop["ch"]).startswith("Was it that the video didn't match")   # an Instagram how-to


# ---------- core data: delete, export, old stores ----------
def test_delete_my_data_removes_the_feedback_and_the_question(slop):
    bot = slop["bot"]
    ask(slop, composer(("recipe for Chicken Alfredo", "clear", "Chicken Alfredo")))
    say(slop, "wrong video", {"intent": "chat"})
    ask(slop, composer(("busy nights", "clear", "Creamy chicken alfredo")))
    say(slop, "slop", {"intent": "chat"})
    assert bot.store.caption_feedback(H) and bot.store.get_state(f"mismatchask:{H}")
    bot.store.delete_person_data(H)
    assert bot.store.one("SELECT COUNT(*) AS n FROM caption_feedback")["n"] == 0
    assert bot.store.get_state(f"mismatchask:{H}") is None and bot.store.get_state(f"mismatchasked:{H}") is None


def test_export_lists_the_feedback_without_words(slop):
    from mvp import export
    bot = slop["bot"]
    ask(slop, composer(("recipe for Chicken Alfredo", "clear", "Chicken Alfredo")))
    say(slop, "wrong video", {"intent": "chat"})
    out = export.export(bot, bot.store.person(H), slop["clock"][0])
    path = dict(out["files"])["reel_feedback.json"]
    rows = json.load(open(path))
    assert rows == [{"item_id": "m1", "kind": "mismatch", "source": "words", "at": rows[0]["at"]}]
    assert "Alfredo" not in open(path).read() and "lol_clipz" not in open(path).read()


def test_a_store_from_before_gains_the_table_and_keeps_its_rows(tmp_path):
    from mvp.store import Store
    path = str(tmp_path / "old.sqlite")
    s = Store(path)
    s.add_todo(H, "buy milk")
    s.db.execute("DROP TABLE caption_feedback")
    s.db.commit()
    s.db.close()
    db = sqlite3.connect(path)
    assert not db.execute("SELECT name FROM sqlite_master WHERE name='caption_feedback'").fetchall()
    db.close()
    s2 = Store(path)
    assert [t["text"] for t in s2.todos(H)] == ["buy milk"] and s2.caption_feedback(H) == []
    s2.add_caption_feedback(H, "x", "@a", None, "mismatch", "words")
    assert s2.disliked(H) == {"x"}
    with pytest.raises(AssertionError):
        s2.add_caption_feedback(H, "x", "@a", None, "liked", "words")


# ---------- the hook order, the merge checks, rule runs ----------
def test_the_hooks_sit_where_the_map_puts_them():
    src = open(os.path.join(MVP, "handler.py"), encoding="utf-8").read()

    def order(*needles):
        at = [src.index(n) for n in needles]
        assert at == sorted(at), needles
    order('pending["kind"] == "confirm_delete"', "ref = self.fit_reads(person, text, now)", "self.draft_reads(")
    order("captionmark.take_ask(", "self._deadline_answer(", "place_answer(self, person, text, now)",
          "self._mismatch_answer(person, text, now, ask)", "self._doit_answer(")


def test_a_rule_run_never_places_a_strong_pick_in_an_outside_app():
    from mvp import captionmark
    from mvp import texts as T
    picks = [{"cm": "strong"}, {"cm": None}, {"cm": "weak"}]
    keep, n = captionmark.placeable(picks)
    assert keep == picks[1:] and n == 1
    assert T.cm_left_out(1) == "1 left out: its caption may not match the video."
    assert T.cm_left_out(2) == "2 left out: their captions may not match the videos."


def test_the_screenshot_case_end_to_end_with_another_and_no_caption_words(slop):
    """The meme recipe for "a recipe": never first while a real recipe fits; its caption's dish name never shown."""
    spec = {"intent": "ask", "spec": {"when": {"type": "now"}, "content": {"goal": "a recipe", "searches": ["recipe"],
                                                                           "count": 1, "extract": "ingredients"}}}
    msg = ask(slop, composer(("recipe for Chicken Alfredo", "clear", "Chicken Alfredo"), ("busy nights", "clear", "Alfredo")),
              spec=spec, text="a recipe")
    assert "I recommend Alfredo by @home_cook_ann" in msg
    assert "Chicken Alfredo" not in msg
