"""Offline tests for round 9, live fix (kinds; DESIGN.md section 12, "Round 9, live fix (kinds)", finding 103): two
wordings of one request for a kind of thing read the same posts. A post whose title or first lines name the kind with
one of its own modifiers is always read; a run-together spelling ("uiux") is read as its parts; a must-have that only
says what the things are for ("for my next project") is not a test each post must pass. Synthetic posts with made-up
names, a fake model, a fake search pool and a fake clock only."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_round7 import ask, items_fake, pick, use_lib  # noqa: E402
from mvp.tests.test_round9_judge import judge_on  # noqa: E402
from mvp.tests.test_slice2 import H, say  # noqa: E402

LONG_ASK = "what are some uiux libraries i should use for my next project"
SHORT_ASK = "What are some UI/UX libraries"

DESIGNS = ("Best design systems for designers\nPicking the right one matters\n1. Harbor - calm and roomy\n"
           "2. Lantern - bold type\n3. Meadow - soft colours")
RESOURCES = "Resources to help you get started in UI/UX\nSave this for later\n#uidesign #uxdesign"
ICONS = ("Where to find great icons?\n01. www.iconpile.xyz\n02. www.glyphbox.com\n03. www.svgden.io\n"
         "04. iconfarm.app")
GOODIES = ("UI goodies for your next build\n1. Bolt - fast and small\n2. Nimbus - light and airy\n"
           "3. Quill - tidy forms\n4. Reed - quiet tables")
KITCHEN = ("Kitchen\nOne of the most premium UI libraries I have come across\n"
           "Every part is built to feel like a real object")
SOUNDS = ("Studio notes\nMy library of sounds for every UI click\nAll free to download")

ROWS = [("d1", "systemsfan", DESIGNS, "2026-09-01", "2026-09-02", "instagram"),
        ("r1", "uiteacher", RESOURCES, "2026-08-01", "2026-08-02", "instagram"),
        ("i1", "iconfan", ICONS, "2026-07-01", "2026-07-02", "instagram"),
        ("g1", "lister", GOODIES, "2026-06-01", "2026-06-02", "instagram"),
        ("k1", "kitchenfan", KITCHEN, "2026-05-01", "2026-05-02", "instagram")]

TABLE = {
    "Best design systems": {"items": [{"name": n, "about": "", "fit": "unknown"} for n in ("Harbor", "Lantern",
                                                                                           "Meadow")]},
    "Resources to help": {"items": [], "key_points": ["Resources to help you get started in UI/UX"]},
    "Where to find great icons": {"items": [{"name": n, "about": "", "fit": "unknown"}
                                            for n in ("iconpile", "glyphbox", "svgden", "iconfarm")]},
    "UI goodies": {"items": [{"name": n, "about": "", "fit": "unknown"} for n in ("Bolt", "Nimbus", "Quill", "Reed")]},
    "Kitchen\nOne of the most": {"items": [{"name": "Kitchen", "about": "One of the most premium UI libraries",
                                            "fit": "yes"}]},
    "Studio notes": {"items": [{"name": "Studio notes", "about": "", "fit": "unknown"}]},
}
VERDICTS = {"Kitchen": "yes", "Harbor": "no", "Lantern": "no", "Meadow": "no", "iconpile": "no", "glyphbox": "no",
            "svgden": "no", "iconfarm": "no", "Bolt": "no", "Nimbus": "no", "Quill": "no", "Reed": "no"}


def compose_three(u):
    """The composer of the live run: three clear picks for the purpose, never the post about one library."""
    return {"picks": [pick(u, "Best design systems", title="Best design systems",
                           criteria=[{"answer": "yes", "quote": "Picking the right one matters"}]),
                      pick(u, "Resources to help", title="Resources to get started",
                           criteria=[{"answer": "yes", "quote": "Save this for later"}]),
                      pick(u, "Where to find great icons", title="Great icons",
                           criteria=[{"answer": "yes", "quote": "Where to find great icons?"}])]}


def long_form(**extra):
    return ask("uiux libraries", ["uiux libraries", "ui design libraries"], criteria=["for a next project"], **extra)


@pytest.fixture()
def lib(env, tmp_path, monkeypatch):
    use_lib(env, tmp_path, ROWS, name="libk3")
    seen = []
    env["state"]["seen"] = seen
    env["state"]["composed"] = []

    def compose(u):
        env["state"]["composed"].append(u)
        return compose_three(u)
    env["state"]["answers"]["mvp_compose"] = compose
    env["state"]["answers"]["mvp_extract"] = items_fake(TABLE, seen)
    judge_on(env, monkeypatch, VERDICTS)
    return env


def read_texts(env):
    return [u.split("<item>", 1)[-1] for u in env["state"]["seen"]]


def runs(env):
    return env["bot"].store.q("SELECT * FROM runs WHERE handle=? ORDER BY id", (H,))


# ---------- the helpers ----------
def test_k3_a_kind_is_named_by_its_head_noun_with_one_of_its_own_modifiers():
    from mvp.extract import kind_parts, names_kind_with_modifier as named
    assert kind_parts("UI/UX libraries") == ("library", {"ui", "ux"})
    assert kind_parts("uiux libraries") == ("library", {"ui", "ux"})   # spelled first
    assert kind_parts("chrome extensions") == ("extension", {"chrome"})
    assert kind_parts("apps") == ("app", set())
    assert kind_parts("good fonts") == ("font", set())   # a word that only grades is not a modifier
    for text in ("premium UI library", "a UX component library", "the best uiux libraries", "UI/UX LIBRARIES",
                 "my favourite ui-ux library"):
        assert named(text, "UI/UX libraries"), text
    # near-variants: the head noun alone, a modifier too far from it, another head, a kind of one word
    for text in ("a library of sounds", "UI design and a component library", "UI kits", "ui libraries"[:2], ""):
        assert not named(text, "UI/UX libraries"), text
    assert not named("my favourite apps", "apps")
    assert named("Three chrome extensions I use daily", "chrome extensions")
    assert not named("chrome is my browser and these are extensions", "chrome extensions")


def test_k3_a_purpose_is_told_apart_from_a_real_must_have():
    from mvp.extract import purpose_only
    for c in ("for a next project", "for my next project", "for beginners", "i should use", "for school",
              "for my portfolio", "that i should use for my next project", "to use for my startup",
              "useful for my next app", "For My New Project."):
        assert purpose_only(c), c
    for c in ("for android", "free", "for kids", "for 2026", "to edit photos", "open source", "for iphone",
              "with dark mode", "under $20", "for a next project with dark mode", ""):
        assert not purpose_only(c), c


def test_k3_only_a_request_for_a_kind_of_thing_is_a_kind_request():
    from mvp.extract import kind_request
    assert kind_request("uiux libraries", LONG_ASK) == "UI/UX libraries"
    assert kind_request("coding courses", "what are some coding courses for beginners") == "coding courses"
    for goal, text in (("chicken and rice recipes", "convenient chicken and rice recipes"),
                       ("Blender tutorials", "blender tutorials"), ("quick workouts", "a quick workout"),
                       ("startup motivation reels", "startup motivation reels")):
        assert kind_request(goal, text) is None, goal


# ---------- (b) a post that names the kind is read, however the request was worded ----------
def test_k3_the_long_wording_reads_the_post_that_names_the_kind_and_counts_its_library(lib):
    msg = say(lib, LONG_ASK, long_form())
    assert any("Kitchen\nOne of the most" in t for t in read_texts(lib))
    assert msg.startswith("I found 1 UI/UX library in your saves")
    assert "1. Kitchen" in msg and "I recommend" not in msg
    assert "iconpile" not in msg.split("\n")[1]   # never an icon site as the first thing


def test_k3_both_wordings_show_the_same_things(lib):
    long_msg = say(lib, LONG_ASK, long_form())
    lib["bot"].store.clear_pending(H)
    short_msg = say(lib, SHORT_ASK, ask("UI/UX libraries", ["UI UX libraries", "design system libraries"]))

    def things(msg):
        import re
        return [m for m in re.findall(r"^\d+\. ([^\s:]+)", msg, re.M)]
    assert things(long_msg) == things(short_msg) and "Kitchen" in things(long_msg)


def test_k3_a_named_post_gets_a_place_even_when_the_shown_picks_fill_every_place(lib, monkeypatch):
    from mvp.executor import ExecutorMixin
    monkeypatch.setattr(ExecutorMixin, "ITEM_READS", 3)
    say(lib, LONG_ASK, long_form())
    texts = read_texts(lib)
    assert any("Kitchen\nOne of the most" in t for t in texts)
    assert sum(1 for t in texts if "<item>" not in t) <= 3
    steps = json.loads(runs(lib)[-1]["steps"])
    assert steps["items_reads"] == 3


def test_k3_near_variant_the_head_noun_alone_is_not_read_first(env, tmp_path, monkeypatch):
    from mvp.executor import ExecutorMixin
    monkeypatch.setattr(ExecutorMixin, "ITEM_READS", 4)
    rows = [r for r in ROWS if r[0] != "k1"] + [("s1", "soundfan", SOUNDS, "2026-05-01", "2026-05-02", "instagram")]
    use_lib(env, tmp_path, rows, name="libk3s")
    seen = []
    env["state"]["answers"]["mvp_compose"] = compose_three
    env["state"]["answers"]["mvp_extract"] = items_fake(TABLE, seen)
    say(env, LONG_ASK, long_form())
    texts = [u.split("<item>", 1)[-1] for u in seen]
    # the fourth place goes to the list (by its score), not to the post that says "library" without "UI" before it
    assert any("UI goodies" in t for t in texts) and not any("Studio notes" in t for t in texts)


def test_k3_a_one_word_kind_reads_as_before(env, tmp_path, monkeypatch):
    from mvp.executor import ExecutorMixin
    monkeypatch.setattr(ExecutorMixin, "ITEM_READS", 3)
    use_lib(env, tmp_path, ROWS, name="libk3o")
    seen = []
    env["state"]["answers"]["mvp_compose"] = compose_three
    env["state"]["answers"]["mvp_extract"] = items_fake(TABLE, seen)
    say(env, "what are some libraries", ask("libraries", ["libraries"]))
    texts = [u.split("<item>", 1)[-1] for u in seen]
    assert not any("Kitchen\nOne of the most" in t for t in texts)   # the three shown picks take the three places


def test_k3_a_run_together_spelling_is_on_topic_for_the_posts_that_spell_it_apart(lib, monkeypatch):
    from mvp.executor import ExecutorMixin
    monkeypatch.setattr(ExecutorMixin, "NAMED_READS", 0)   # only the topic test, not the named place
    say(lib, LONG_ASK, long_form())
    # "uiux" is read as "ui" and "ux": the list that says "UI goodies" is now a candidate to read
    assert any("UI goodies" in t for t in read_texts(lib))


# ---------- (c) a purpose is not a must-have ----------
def test_k3_a_purpose_is_left_out_of_the_must_haves_of_a_kind_request(lib):
    msg = say(lib, LONG_ASK, long_form())
    assert '"for a next project"' not in lib["state"]["composed"][0]
    assert LONG_ASK in lib["state"]["composed"][0]   # the composer still reads it in the person's words
    assert json.loads(runs(lib)[-1]["steps"])["purpose_left_out"] == 1
    assert "couldn't check" not in msg


def test_k3_near_variants_keep_their_must_haves(lib):
    # a real must-have of a kind request stays
    say(lib, "what are some uiux libraries for android", ask("uiux libraries", ["uiux libraries"],
                                                               criteria=["for android"]))
    assert '"for android"' in lib["state"]["composed"][-1]
    assert "purpose_left_out" not in json.loads(runs(lib)[-1]["steps"])
    # a recipe request keeps every must-have (it is not a request for a kind of thing)
    lib["bot"].store.clear_pending(H)
    say(lib, "easy dinner recipes for beginners", ask("dinner recipes", ["dinner recipes"],
                                                      criteria=["for beginners"]))
    assert '"for beginners"' in lib["state"]["composed"][-1]
    assert "purpose_left_out" not in json.loads(runs(lib)[-1]["steps"])


# ---------- (a) the kind phrase itself is searched too ----------
def test_k3_the_kind_phrase_is_searched_when_no_search_says_it():
    from mvp.extract import kind_search
    assert kind_search("design tools", ["design tools portfolio", "portfolio design tools"]) == "design tools"
    assert kind_search("chrome extensions", ["chrome extensions for school"]) == "chrome extensions"
    # near-variants: a search already says it (grading words, spelling and plural do not count), or one word
    assert kind_search("chrome extensions", ["some chrome extensions"]) is None
    assert kind_search("UI/UX libraries", ["uiux libraries"]) is None
    assert kind_search("UI/UX libraries", ["UI UX library"]) is None
    assert kind_search("apps", ["apps to edit photos"]) is None
    assert kind_search("UI/UX libraries", ["ui design libraries"]) == "UI/UX libraries"


def test_k3_a_long_wording_searches_the_kind_phrase_beside_the_interpreters(lib):
    say(lib, "what are some ui libraries i should use for my portfolio",
        ask("ui libraries for a portfolio", ["ui libraries portfolio", "portfolio ui kits"]))
    assert lib["bot"].pool.queries[-3:] == ["ui libraries portfolio", "portfolio ui kits", "ui libraries"]
    assert json.loads(runs(lib)[-1]["steps"])["kind_search"] == 1
    # the stored request keeps the interpreter's searches
    kept = lib["bot"].store.get_state(f"lastspec:{H}")["spec"]["content"]["searches"]
    assert kept == ["ui libraries portfolio", "portfolio ui kits"]


def test_k3_near_variants_search_only_the_interpreters_words(lib, monkeypatch):
    # the short wording already says it
    n = len(lib["bot"].pool.queries)
    say(lib, "what are some ui libraries", ask("ui libraries", ["ui libraries"]))
    assert lib["bot"].pool.queries[n:] == ["ui libraries"]
    assert "kind_search" not in json.loads(runs(lib)[-1]["steps"])
    # a recipe request, and the setting turned off
    lib["bot"].store.clear_pending(H)
    n = len(lib["bot"].pool.queries)
    say(lib, "easy pasta recipes for my next dinner party", ask("pasta recipes for a dinner party", ["pasta dinner party"]))
    assert lib["bot"].pool.queries[n:] == ["pasta dinner party"]
    from mvp import config
    monkeypatch.setattr(config, "KIND_SEARCH", False)
    lib["bot"].store.clear_pending(H)
    n = len(lib["bot"].pool.queries)
    say(lib, "what are some ui libraries i should use for my portfolio",
        ask("ui libraries for a portfolio", ["ui libraries portfolio"]))
    assert lib["bot"].pool.queries[n:] == ["ui libraries portfolio"]
