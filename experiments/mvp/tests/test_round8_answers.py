"""Offline tests for round 8, slice A2 (findings 93 to 97; DESIGN.md section 12): the items answer holds real named
things, read from the posts whose text names them; several asks in one message; a creator's series after "something
that isn't"; a plain question about the saves read as small talk. Synthetic data, a fake model, a fake search pool and
a fake clock only (today is 12 Nov 2026 in New York)."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_round7 import ask, ig, items_fake, pick, use_lib  # noqa: E402
from mvp.tests.test_slice2 import H, say  # noqa: E402


class It:
    """The fields of a library item the item checks read."""
    def __init__(self, caption, platform="instagram"):
        self.raw_caption, self.caption, self.platform, self.id = caption, " ".join(caption.split()), platform, "x"
        self.first_line = next((" ".join(x.split()) for x in caption.splitlines() if x.strip()), "")


def names(items):
    return [x["name"] for x in items]


# ---------- finding 93: what an item is ----------
def test_93_a_category_a_plural_common_noun_and_a_kind_after_a_determiner_are_not_things():
    from mvp.extract import clean_items
    text = ("Design systems that excel\nHere is a list of the some best design systems that excel in these aspects\n"
            "Choosing the right Figma design system is crucial\nMaterial UI: Google's React components, themable")
    got, dropped = clean_items([{"name": "design systems", "about": "a list of the some best design systems"},
                                {"name": "Figma design system", "about": "choosing the right Figma design system"},
                                {"name": "Material UI", "about": "Google's React components, themable"}], It(text))
    assert names(got) == ["Material UI"] and dropped == 2
    # near-variants: a capitalised name kept; a lower-case name that is a site ("lucide.com") or a handle is kept;
    # a lower-case name with no capital, digit, dot or @ anywhere it occurs is a common noun
    text2 = "Icons\n- get them at lucide.com, really clean icon set\n- notion is where i keep them all together"
    got, _ = clean_items([{"name": "lucide", "about": "really clean icon set, get them"},
                          {"name": "notion", "about": "where i keep them all together"}], It(text2))
    assert names(got) == ["lucide"]
    # a brand before one kind word stays ("the Google STEP internship"): only two lower-case kind words make it a kind
    text3 = "Apply to the Google STEP internship this fall, paid and remote for first years"
    got, _ = clean_items([{"name": "Google STEP internship", "about": "paid and remote for first years"}], It(text3))
    assert names(got) == ["Google STEP internship"]


def test_93_an_audience_a_count_and_the_headline_are_not_things():
    from mvp.extract import clean_items, generic_name, restates_headline
    assert generic_name("underclassmen") and generic_name("5 tools") and generic_name("FREE PROGRAMS FOR STUDENTS")
    assert not generic_name("Kitchen") and not generic_name("Ant Design") and not generic_name("NASA Space Apps")
    text = ("4 FREE PROGRAMS FOR STUDENTS\nfor underclassmen especially\nNASA SPACE APPS: A GLOBAL HACKATHON FOR "
            "EVERYONE EACH OCTOBER\nAPPLY EARLY")
    got, dropped = clean_items([
        {"name": "FREE PROGRAMS FOR STUDENTS", "about": "4 FREE PROGRAMS FOR STUDENTS"},
        {"name": "underclassmen", "about": "for underclassmen"},
        {"name": "NASA SPACE APPS", "about": "A GLOBAL HACKATHON FOR EVERYONE EACH OCTOBER"}], It(text))
    # text in capitals throughout cannot use the capital test: the real name is kept, the others go by the other tests
    assert names(got) == ["NASA SPACE APPS"] and dropped == 2
    # the headline as a name, with words that only say it again; a real name in the headline with words of its own
    assert restates_headline("Notion Hacks I Use", "3 Notion Hacks I Use", It("3 Notion Hacks I Use\nmore below"))
    assert not restates_headline("Notion", "an all in one workspace for notes", It("3 Notion Hacks I Use\nx"))


def test_93_words_that_add_nothing_or_tell_a_story_are_not_words_about_a_thing():
    from mvp.extract import clean_items, story_about, thin_about
    text = ("My stack this year, Figma for everything. lol so true\nFramer: builds real sites from your designs, no "
            "code\n- Iconoir: free icons\nYC: 1 YC application. 0 startup experience. 4 hours before the deadline.")
    got, dropped = clean_items([{"name": "Figma", "about": "lol so true"},
                                {"name": "Framer", "about": "builds real sites from your designs, no code"},
                                {"name": "Iconoir", "about": "free icons"},
                                {"name": "YC", "about": "1 YC application. 0 startup experience. 4 hours before the "
                                                       "deadline."}], It(text))
    # the post names other things: a thing whose words add nothing is not shown; "Iconoir: free icons" is its own list
    # line (judgement: one content word or more of the rest of its own line are its words)
    assert names(got) == ["Framer", "Iconoir"] and dropped == 2
    assert thin_about("underclassmen", "for underclassmen") and not thin_about("Framer", "builds real sites fast")
    assert thin_about("Iconoir", "free icons", "Icons I like: Iconoir and its free icons")   # not its own line
    assert story_about("1 YC application. 0 startup experience. 4 hours before the deadline.")
    assert not story_about("Google's design system with 3 React components.")


def test_93_a_post_about_one_thing_gives_it_its_best_key_points():
    from mvp.extract import clean_items
    text = ("Kitchen\nOne of the most premium UI libraries out there. Every component is built to be copied and "
            "pasted. Free for personal use.")
    keys = ["One of the most premium UI libraries out there", "Every component is built to be copied and pasted",
            "Free for personal use"]
    got, _ = clean_items([{"name": "Kitchen", "about": ""}], It(text), key_points=keys)
    assert got[0]["about"] == "One of the most premium UI libraries out there; Every component is built to be " \
                              "copied and pasted"
    # near-variants: without key points the name has no words; with words of its own they are kept
    assert clean_items([{"name": "Kitchen", "about": ""}], It(text))[0][0]["about"] == ""
    got, _ = clean_items([{"name": "Kitchen", "about": "Free for personal use"}], It(text), key_points=keys)
    assert got[0]["about"] == "Free for personal use"


# ---------- the answer (findings 93 and 94) ----------
DS = ("Best design systems for UI/UX designers\n1. Material UI - Google's design system with React components\n"
      "2. Ant Design: an enterprise-class UI design language\n3. Chakra UI, simple and accessible components\n")
KITCHEN = ("Kitchen UI library\nOne of the most premium UI libraries out there. Every component is built to be copied "
           "and pasted.")
VIBES = "UI design vibes and calm workspace inspiration for designers"
SLIDES = "5 free UI libraries you need to know\nsave this for your next project"
ICONS = ("UI icon packs I use\n- Iconoir: free open source icons for any UI\n- Lucide: beautiful consistent UI icons, "
         "MIT licensed\n- Phosphor: a flexible UI icon family for interfaces")
FONTS = "UI fonts for product design\n- Inter: a clean sans serif for any UI\n- Geist: a modern UI typeface by Vercel"
CSS = "UI css frameworks\n- Tailwind: utility classes for fast UI building\n- Bulma: a modern UI css framework, free"
RECIPE = "Pasta night\n- 200g spaghetti\n- 2 lemons"
LIST_OFF = "Best cafes in Lisbon\n- Fabrica Coffee: great espresso and calm mornings\n- Hello Kristof: tiny and calm spot"

ROWS = [("v1", "vibes", VIBES, "2024-01-10", "2024-02-01", "instagram"),
        ("s1", "slides", SLIDES, "2025-03-01", "2025-03-02", "instagram"),
        ("d1", "designer", DS, "2023-06-20", "2023-07-02", "instagram"),
        ("k1", "kitchen", KITCHEN, "2025-05-01", "2025-05-02", "instagram"),
        ("i1", "iconfan", ICONS, "2022-09-01", "2022-09-15", "instagram"),
        ("f1", "fonts", FONTS, "2025-09-01", "2025-09-02", "instagram"),
        ("c1", "css", CSS, "2025-10-01", "2025-10-02", "instagram"),
        ("r1", "cook", RECIPE, "2025-10-01", "2025-10-02", "instagram"),
        ("l1", "lisbon", LIST_OFF, "2025-10-01", "2025-10-02", "instagram")]

TABLE = {
    "Best design systems": {"items": [
        {"name": "Material UI", "about": "Google's design system with React components", "fit": "yes"},
        {"name": "Ant Design", "about": "an enterprise-class UI design language", "fit": "yes"},
        {"name": "Chakra UI", "about": "simple and accessible components", "fit": "yes"}]},
    "Kitchen UI library": {"items": [{"name": "Kitchen", "about": "", "fit": "yes"}],
                           "key_points": ["One of the most premium UI libraries out there",
                                          "Every component is built to be copied and pasted"]},
    "UI icon packs": {"items": [
        {"name": "Iconoir", "about": "free open source icons for any UI", "fit": "yes"},
        {"name": "Lucide", "about": "beautiful consistent UI icons, MIT licensed", "fit": "yes"},
        {"name": "Phosphor", "about": "a flexible UI icon family for interfaces", "fit": "yes"}]},
    "UI fonts": {"items": [{"name": "Inter", "about": "a clean sans serif for any UI", "fit": "yes"},
                           {"name": "Geist", "about": "a modern UI typeface by Vercel", "fit": "yes"}]},
    "UI css frameworks": {"items": [{"name": "Tailwind", "about": "utility classes for fast UI building", "fit": "yes"},
                                    {"name": "Bulma", "about": "a modern UI css framework, free", "fit": "yes"}]},
    "Best cafes": {"items": [{"name": "Fabrica Coffee", "about": "great espresso and calm mornings", "fit": "yes"},
                             {"name": "Hello Kristof", "about": "tiny and calm spot", "fit": "yes"}]},
    "5 free UI libraries": {"items": [], "key_points": []},
    "UI design vibes": {"items": [], "key_points": ["calm workspace inspiration for designers"]},
}
UI_ASK = "what are some uiux libraries i should use for my next project"


def compose_vibes_first(u):
    """The composer picks the posts that are about the request: two whose text names nothing, then the design list."""
    return {"picks": [pick(u, "UI design vibes", title="UI design vibes"),
                      pick(u, "5 free UI libraries", title="5 free UI libraries you need to know"),
                      pick(u, "Best design systems", "close", title="Best design systems")],
            "intro": "Here are some UI libraries."}


@pytest.fixture()
def lib8(env, tmp_path):
    use_lib(env, tmp_path, ROWS, name="lib8")
    env["state"]["answers"]["mvp_compose"] = compose_vibes_first
    env["seen"] = []
    env["state"]["answers"]["mvp_extract"] = items_fake(TABLE, env["seen"])
    return env


def read_posts(env):
    return [next((k for k in TABLE if k in u.split("<item>", 1)[-1]), "?") for u in env["seen"]]


def test_94_an_items_request_reads_the_posts_whose_text_names_things(lib8):
    msg = say(lib8, UI_ASK, ask("UI/UX libraries", ["ui libraries"]))
    read = read_posts(lib8)
    # the shown picks first, then the candidates whose text lists named things, on the request's topic, at most 6
    assert sorted(read) == sorted(["UI design vibes", "5 free UI libraries", "Best design systems", "UI icon packs",
                                   "UI fonts", "UI css frameworks"])     # (the calls run in parallel: any order)
    assert "Best cafes" not in read and "?" not in read           # a list off the topic, a recipe: never read
    # the posts with the most good things come first, at most 3; the next two are named in one line each
    assert msg.startswith("I found 8 UI/UX libraries named in 3 of your saves.")
    heads = [x for x in msg.split("\n") if x.startswith("From ")]
    assert [h.split('"')[1] for h in heads] == ["Best design systems", "UI icon packs I use", "UI fonts for product design"]
    assert "More in your saves:" in msg
    assert "• UI css frameworks by @css: it names 2 more. https://" in msg
    assert "Kitchen UI library" not in msg      # its text lists nothing (a score of 0): never read beyond the picks
    # the shown picks with no things follow; the one whose title promises a list says where its names are
    assert "• 5 free UI libraries you need to know by @slides: the names are in its slides, not its text. https://" in msg
    assert "• UI design vibes by @vibes: calm workspace inspiration for designers." in msg
    run = lib8["bot"].store.one("SELECT steps FROM runs WHERE kind='ask' ORDER BY id DESC LIMIT 1")
    steps = json.loads(run["steps"])
    assert steps["items_reads"] == 6 and steps["extract_calls"] == 6


def test_94_the_numbers_and_the_stored_answer_follow_the_order_shown(lib8):
    say(lib8, UI_ASK, ask("UI/UX libraries", ["ui libraries"]))
    bot = lib8["bot"]
    kept = bot.store.answer(bot.store.last_answer(H)["run_id"])["picks"]
    assert [p["item_id"] for p in kept][:3] == ["d1", "i1", "f1"]
    assert [x["name"] for x in kept[1]["items"]] == ["Iconoir", "Lucide", "Phosphor"]
    say(lib8, "add the fourth one to my list", {"intent": "todo_add", "pick_number": 4})
    assert bot.store.todos(H)[-1]["text"] == "Iconoir"


def test_94_a_post_with_a_no_an_avoided_word_or_off_topic_is_never_read(lib8):
    def compose(u):
        out = compose_vibes_first(u)
        out["picks"].append(pick(u, "UI icon packs", "no", title="UI icon packs"))     # the composer said no
        return out
    lib8["state"]["answers"]["mvp_compose"] = compose
    say(lib8, UI_ASK, ask("UI/UX libraries", ["ui libraries"], avoid=["fonts"]))
    read = read_posts(lib8)
    assert "UI icon packs" not in read and "UI fonts" not in read and "Best cafes" not in read
    assert "UI css frameworks" in read and "Kitchen UI library" not in read


def test_94_a_request_that_names_no_kind_of_thing_reads_its_top_3_as_before(lib8):
    lib8["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        pick(u, "UI design vibes", title="UI design vibes"), pick(u, "Best design systems", title="Best design")]}
    say(lib8, "show me ui design inspiration", ask("UI design inspiration"))
    assert read_posts(lib8) == ["UI design vibes", "Best design systems"] or \
        sorted(read_posts(lib8)) == ["Best design systems", "UI design vibes"]


def test_94_the_opening_line_names_the_kind_only_when_the_goal_is_short():
    from mvp.render import found_noun
    assert found_noun("UI/UX libraries") == "UI/UX libraries"
    assert found_noun("some UI/UX libraries for my next project") == "UI/UX libraries"
    assert found_noun("opportunities to pursue soon") == "opportunities"
    assert found_noun("startup motivation reels") is None                 # not a kind of thing
    assert found_noun("free open source react component design libraries") is None    # too long: "things"


def test_93_only_the_kind_asked_for_is_shown_unless_fewer_than_2_would_be_left(env, tmp_path):
    cap = ("Free UI libraries\n- Material UI: Google's design system with React components\n- Ant Design: an "
           "enterprise-class UI design language\n- Dribbble: a place to share your shots with others")
    use_lib(env, tmp_path, [("a1", "x", cap, "2025-01-01", "2025-01-02", "instagram")])
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [pick(u, "Free UI libraries")]}
    table = {"Free UI": {"items": [
        {"name": "Material UI", "about": "Google's design system with React components", "fit": "yes"},
        {"name": "Ant Design", "about": "an enterprise-class UI design language", "fit": "yes"},
        {"name": "Dribbble", "about": "a place to share your shots with others", "fit": "unknown"}]}}
    env["state"]["answers"]["mvp_extract"] = items_fake(table)
    msg = say(env, "which ui libraries should i use", ask("UI libraries"))
    assert "1. Material UI" in msg and "2. Ant Design" in msg and "Dribbble" not in msg
    # one "yes" only: the unknown ones stay, so the answer is still made of things
    table["Free UI"]["items"][1]["fit"] = "unknown"
    msg = say(env, "which ui libraries are good", ask("good UI libraries"))
    assert "Material UI" in msg and "Ant Design" in msg and "Dribbble" in msg
    # a request that names no kind of thing keeps the unknown ones whatever the count
    table["Free UI"]["items"][1]["fit"] = "yes"
    msg = say(env, "show me what that design post says", ask("that design post"))
    assert "Dribbble" in msg


def test_93_fewer_than_2_good_things_make_no_items_answer_but_the_gist(env, tmp_path):
    use_lib(env, tmp_path, [("k1", "kitchen", KITCHEN, "2025-05-01", "2025-05-02", "instagram")])
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [pick(u, "Kitchen UI library", title="Kitchen")]}
    env["state"]["answers"]["mvp_extract"] = items_fake(TABLE)
    msg = say(env, "what ui libraries should i use", ask("UI libraries"))
    assert "I recommend Kitchen by @kitchen" in msg and "From \"" not in msg
    assert "• One of the most premium UI libraries out there" in msg


def test_93_a_post_about_one_thing_counts_as_one_grounded_item_beside_another(env, tmp_path):
    use_lib(env, tmp_path, [ROWS[3], ROWS[5]])
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [pick(u, "Kitchen UI library", title="Kitchen"),
                                                                  pick(u, "UI fonts", title="UI fonts")]}
    env["state"]["answers"]["mvp_extract"] = items_fake(TABLE)
    msg = say(env, "what ui libraries should i use", ask("UI libraries"))
    assert "Kitchen: One of the most premium UI libraries out there; Every component is built to be copied and " \
           "pasted" in msg


def test_93_a_title_that_promises_a_list_only_says_where_the_names_are_when_none_is_shown(env, tmp_path):
    use_lib(env, tmp_path, [ROWS[1], ROWS[2]])
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        pick(u, "Best design systems", title="Best design systems"),
        pick(u, "5 free UI libraries", title="5 free UI libraries you need to know")]}
    env["state"]["answers"]["mvp_extract"] = items_fake(TABLE)
    msg = say(env, "what ui libraries should i use", ask("UI libraries"))
    assert "5 free UI libraries you need to know by @slides: the names are in its slides, not its text." in msg
    from mvp.extract import promises_list
    assert promises_list("4 FREE PROGRAMS FOR STUDENTS") and promises_list("Best design systems for designers")
    assert not promises_list("Quick dinner in 15 minutes") and not promises_list("The best pasta ever")
    assert ig("2025-03-01", 1) in msg


def test_94_the_list_score_reads_lists_handles_sites_and_named_lines():
    from mvp.extract import list_score
    assert list_score("Best sites\n1. Figma: design\n2. Lucide - icons") >= 3
    assert list_score("follow @figma and @framer for more, or see www.example.com") >= 3
    assert list_score("Just a calm morning routine to start the day") == 0
    assert list_score("UI design vibes and calm workspace inspiration") == 0


# ---------- finding 96: "something that isn't a donut" and the rest of the donut series ----------
SERIES = [("s1", "Guru", "Blender Beginner Tutorial - Part 1", None, "2025-11-01", "youtube"),
          ("s2", "Guru", "Blender Beginner Tutorial - Part 4", None, "2025-10-20", "youtube"),
          ("s3", "Guru", "Blender Beginner Tutorial - Part 6", None, "2025-10-10", "youtube"),
          ("s4", "Guru", "Geometry nodes in Blender for beginners", None, "2025-10-05", "youtube"),
          ("o1", "CG Cookie", "Blender basics: the interface for beginners", None, "2025-09-01", "youtube"),
          ("o2", "Grant Abbitt", "Low poly sword in Blender for beginners", None, "2025-08-01", "youtube")]
SERIES_DESC = {"vids1": "We model a donut from start to finish", "vids2": "Adding the icing and sprinkles",
               "vids3": "Lighting and the final render", "vids4": "Nodes from scratch", "vido1": "Learn the interface",
               "vido2": "Model a low poly sword"}


def series_env(env, tmp_path, monkeypatch, rows=SERIES):
    use_lib(env, tmp_path, rows, name="series")
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key-not-real")
    from mvp import ytinfo
    monkeypatch.setattr(ytinfo, "fetch_batch", lambda ids, key, timeout=None: {"items": [
        {"id": v, "snippet": {"description": SERIES_DESC[v], "publishedAt": "2025-01-01T00:00:00Z"},
         "contentDetails": {"duration": "PT9M"}} for v in ids if v in SERIES_DESC]})
    import mvp.config as C
    monkeypatch.setattr(C, "OUTSIDE_ON", False)
    env["state"]["answers"]["mvp_extract"] = lambda u: {}
    env["orders"] = []

    def compose(u):   # every candidate, in the order the composer is shown them; the first ask shows Part 1 first
        block = u.split("Candidates:")[-1]
        titles = [r[2] for r in rows if r[2] in block]
        titles.sort(key=lambda t: block.index(t))
        env["orders"].append(titles)
        if len(env["orders"]) == 1:   # the first answer shows the donut video alone
            titles = titles[:1]
        return {"picks": [pick(u, t, title=t) for t in titles][:2]}
    env["state"]["answers"]["mvp_compose"] = compose
    say(env, "could you find me some basic blender tutorials", ask("basic Blender tutorials", ["blender basics"],
                                                                   count=2))
    return env


def test_96_the_rest_of_a_passed_on_series_goes_and_its_creator_comes_last(env, tmp_path, monkeypatch):
    series_env(env, tmp_path, monkeypatch)
    from mvp.tests.test_round7 import shown_ids
    assert shown_ids(env)[0] == "s1"
    msg = say(env, "what about something that isnt a donut.",
              {"intent": "follow_up", "question": "What about something that isn't a donut?", "avoid": ["donut"]})
    seen = env["orders"][-1]
    assert not any("Part 4" in t or "Part 6" in t for t in seen)           # the rest of the series never reaches it
    assert seen.index("Geometry nodes in Blender for beginners") > seen.index("Low poly sword in Blender for beginners")
    ids = shown_ids(env)
    assert ids[:2] == ["o1", "o2"] and "s4" not in ids                     # two others fit: the creator is not shown
    assert "same creator" not in msg


def test_96_one_of_that_creators_posts_is_shown_with_a_note_when_fewer_than_2_others_fit(env, tmp_path, monkeypatch):
    series_env(env, tmp_path, monkeypatch, rows=SERIES[:5])                 # one other creator only
    from mvp.tests.test_round7 import shown_ids
    msg = say(env, "what about something that isnt a donut.", {"intent": "more", "avoid": ["donut"]})
    ids = shown_ids(env)
    assert ids[0] == "o1" and "s4" in ids and "s2" not in ids and "s3" not in ids
    assert "Geometry nodes in Blender for beginners by Guru" in msg and "same creator as the one you passed on" in msg


def test_96_a_series_stem_is_read_from_the_title():
    from mvp.followup import series_key
    assert series_key("Blender Beginner Tutorial - Part 4") == ("blender beginner tutorial", True)
    assert series_key("Blender Beginner Tutorial (Part 1)")[0] == series_key("Blender Beginner Tutorial")[0]
    assert series_key("Donut tutorial #6") == ("donut tutorial", True)
    assert series_key("Low poly sword in Blender") == ("low poly sword in blender", False)
    assert series_key("Blender 4.0 for beginners")[1] is False                 # a version is not a part number


# ---------- finding 97: a plain question about the saves, read as small talk ----------
OPPS = ("Summer 2026 programs for students\n- NASA L'SPACE Academy: a free program, apply by December 10, 2026\n"
        "- Google STEP: a paid summer internship for first and second year students")


def test_97_a_question_about_their_own_saves_read_as_chat_is_answered_with_a_search(env, tmp_path):
    use_lib(env, tmp_path, [("o1", "progs", OPPS, "2026-10-10", "2026-10-11", "instagram")])
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [pick(u, "Summer 2026 programs")]}
    env["state"]["answers"]["mvp_extract"] = items_fake({"Summer 2026": {"items": [
        {"name": "NASA L'SPACE Academy", "about": "a free program, apply by December 10, 2026", "fit": "yes"},
        {"name": "Google STEP", "about": "a paid summer internship for first and second year students",
         "fit": "yes"}]}})
    chat = {"intent": "chat", "reply": "Sounds like a busy year!"}
    msg = say(env, "what other opportunities might i have missed for 2026, especially winter or next summer", chat)
    assert "Sounds like a busy year" not in msg and "1. NASA L'SPACE Academy" in msg
    q = env["bot"].pool.queries[-1]
    assert q.startswith("other opportunities i might have missed for 2026")
    # near-variants that stay small talk: about the bot, thanks, a feeling, too short, nothing asked for
    for text in ("what can you find for me in there", "thanks, that helps a lot with my plans", "i feel tired of "
                 "looking for opportunities", "any opportunities?", "my summer was really fun this year honestly"):
        n = len(env["bot"].pool.queries)
        msg = say(env, text, chat)
        assert msg == "Sounds like a busy year!" and len(env["bot"].pool.queries) == n, text


def test_97_the_guard_reads_kinds_and_first_person_words():
    from mvp.interpret import chat_guard
    from mvp.schema import Interpretation

    def guard(t):
        return chat_guard(Interpretation(intent="chat", reply="x"), t)
    assert guard("did i save any good pasta recipes last month").intent == "ask"
    assert guard("show me other blender tutorials from my saves").intent == "ask"
    assert guard("hey how are you doing today friend").intent == "chat"
    assert guard("send me pasta recipes every friday").intent == "chat"      # a rule's words: the reading stands
    assert chat_guard(Interpretation(intent="help"), "what other opportunities did i miss this year").intent == "help"
