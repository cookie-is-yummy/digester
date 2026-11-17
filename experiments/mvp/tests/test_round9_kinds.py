"""Offline tests for round 9, slice U (DESIGN.md section 12, "Round 9, slice U"): requests for a kind of thing. What the
details model returned and why code left things out is counted for the kinds evaluation (eval_kinds.py); the details
call is told the kind asked for (extract_v4); clear picks lead even when their text names nothing; the posts read for
things are chosen steadily. Synthetic posts with made-up names, a fake model, a fake search pool and a fake clock."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_round7 import ask, items_fake, pick, use_lib  # noqa: E402
from mvp.tests.test_round8_answers import It, names  # noqa: E402
from mvp.tests.test_round8_live import ROWS98, TABLE98, compose98  # noqa: E402
from mvp.tests.test_slice2 import H, say  # noqa: E402

UI_ASK = "what are some uiux libraries i should use for my next project"


def runs(env):
    return env["bot"].store.q("SELECT * FROM runs WHERE handle=? ORDER BY id", (H,))


# ---------- point 4: what the model returned and why code left things out, counted ----------
def test_u4_the_details_check_counts_what_the_model_returned_and_what_it_left_out():
    from mvp.extract import verify_items
    text = "Three kits I like\n- Pantry: copy and paste blocks\n- Larder: a calm set of parts"
    tally = {}
    got, dropped = verify_items([{"name": "Pantry", "about": "copy and paste blocks", "fit": "yes"},
                                 {"name": "Larder", "about": "", "fit": "no"},
                                 {"name": "Cellar", "about": "not in the text", "fit": "yes"},
                                 {"name": "Pantry", "fit": "yes"}, "not an object"], text, tally)
    assert names(got) == ["Pantry"] and dropped == 3
    assert tally == {"raw": 5, "yes": 3, "fit_no": 1, "not_in_text": 2, "repeated": 1}
    # without a tally nothing changes (the round 8 callers)
    assert verify_items([{"name": "Pantry", "fit": "yes"}], text) == \
        ([{"name": "Pantry", "about": "", "when": "", "fit": "yes"}], 0)


def test_u4_clean_items_says_which_test_left_each_thing_out():
    from mvp.extract import clean_items, junk_reason
    text = ("My Favourite Kits\n- Pantry: copy and paste blocks for every screen\n- design systems\n"
            "we keep a toggle on every page\n- Writing & Editing\nLarder is mentioned once")
    why = {}
    got, dropped = clean_items([{"name": "Pantry", "about": "copy and paste blocks for every screen"},
                                {"name": "design systems", "about": ""}, {"name": "toggle", "about": ""},
                                {"name": "Writing & Editing", "about": ""}, {"name": "Larder", "about": ""}],
                               It(text), why=why)
    assert names(got) == ["Pantry"] and dropped == 4
    assert why == {"kind_word": 1, "common_noun": 1, "activity": 1, "no_words": 1}
    assert junk_reason("Pantry", "", It(text), text) is None
    # a post about one thing keeps it (no "no_words" for a lone thing)
    why = {}
    clean_items([{"name": "Larder", "about": ""}], It(text), why=why)
    assert why == {}


@pytest.fixture()
def lib98(env, tmp_path):
    use_lib(env, tmp_path, ROWS98, name="lib98")
    env["state"]["answers"]["mvp_compose"] = compose98
    env["state"]["answers"]["mvp_extract"] = items_fake(TABLE98)
    return env


def test_u4_a_run_keeps_the_counts_the_kinds_evaluation_reads(lib98):
    say(lib98, UI_ASK, ask("UI/UX libraries", ["ui libraries"]))
    steps = json.loads(runs(lib98)[-1]["steps"])
    assert steps["items_model"]["raw"] == 8 and steps["items_model"]["yes"] == 7
    assert steps["items_why"] == {"kind_word": 1}   # the bare format word among the site names
    assert steps["items_sources"] == {"clear": 1, "close": 2}
    assert steps["items"] == 7


def test_u4_the_evaluation_reads_the_kind_of_answer_from_fixed_phrases_and_steps():
    from mvp.eval_kinds import answer_kind, summary
    assert answer_kind("I found 3 ...", [{"items": 3}], ["ask"], 2) == "items"
    assert answer_kind("Here's what I found.\n\nI recommend X", [{}], ["ask"], 2) == "recommend"
    assert answer_kind("I recommend X\n\nNamed in other saves, close to what you asked:", [{}], ["ask"], 2) == \
        "recommend_named"
    assert answer_kind('Nothing I found is a clear fit for "x".\n\nThe closest I have is', [{}], ["ask"], 1) == \
        "closest"
    assert answer_kind("I couldn't find anything", [{}], ["ask"], 0) == "none"
    assert answer_kind("Hi!", [], ["chat"], 0) == "other"
    row = {"answer": "items", "errors": 0, "shown_things": 4, "model_items": 6, "model_yes": 5,
           "dropped_by_check": {"fit_no": 1}, "dropped_as_junk": {"kind_word": 1}, "dropped_not_the_kind": 0,
           "sources_clear": 1, "sources_close": 1, "nothing_clear_beside_clear": False, "cost_usd": 0.02}
    s = summary([row, dict(row, answer="recommend", cost_usd=0.04)])
    assert s["requests"] == 2 and s["answers"] == {"items": 1, "recommend": 1} and s["shown_things"] == 8
    assert s["dropped_as_junk"] == {"kind_word": 2} and s["cost_per_request"] == 0.03


def test_u4_the_kinds_set_holds_invented_requests_only():
    path = os.path.join(os.path.dirname(HERE), "evalset", "kinds_dev.jsonl")
    rows = [json.loads(x) for x in open(path, encoding="utf-8") if x.strip()]
    assert 12 <= len(rows) <= 20 and len({r["n"] for r in rows}) == len(rows)
    assert all(set(r) == {"n", "kind", "text"} and r["text"] == r["text"].lower() for r in rows)
    assert not any("@" in r["text"] or "http" in r["text"] for r in rows)


# ---------- point 1: the details call is told the kind asked for (extract_v4) ----------
def test_u1_config_points_at_extract_v4_and_v3_stays():
    from mvp import config
    here = os.path.join(os.path.dirname(HERE), "prompts")
    assert config.PROMPT_EXTRACT == "extract_v4"
    assert os.path.exists(os.path.join(here, "extract_v3.md"))
    v4 = open(os.path.join(here, "extract_v4.md"), encoding="utf-8").read()
    assert "Kind asked for" in v4 and "ITSELF one of the kind asked for" in v4
    # the contrast examples are about other topics, never interface libraries
    assert "hiking trails" in v4 and "budgeting apps" in v4
    assert not any(w in v4.lower() for w in ("ui/ux", "component", "uiux", "icon", "figma", "material ui"))


def test_u1_the_kind_phrase_is_the_requests_own_noun():
    from mvp.extract import kind_phrase
    assert kind_phrase("uiux libraries for my next project") == "UI/UX libraries"
    assert kind_phrase("fonts for motion graphics titles") == "fonts"
    assert kind_phrase("AI tools for designers") == "AI tools"
    assert kind_phrase("", "any podcasts about startups i should listen to") == "podcasts"
    assert kind_phrase("a quick dinner", "what should i cook") is None
    assert kind_phrase("which one should i pick") is None
    # a message's question words are never part of the kind
    assert kind_phrase("", "what websites have free textures for my renders") == "websites"
    assert kind_phrase("", "which youtube channels should i watch") == "youtube channels"
    assert kind_phrase("", "what are some sites for free stock footage") == "sites"


def test_u1_the_details_call_gets_the_kind_on_its_own_line(lib98):
    seen = []
    lib98["state"]["answers"]["mvp_extract"] = items_fake(TABLE98, seen)
    say(lib98, UI_ASK, ask("uiux libraries for my next project", ["ui libraries"]))
    assert seen and all('\nKind asked for: "UI/UX libraries"\n' in u for u in seen)


def test_u1_a_request_that_names_no_kind_gets_no_kind_line(env, tmp_path):
    rows = [("v1", "maker", "Calm studio vibes\nA slow morning in the studio with tea and plants", "2026-10-01",
             "2026-10-02", "instagram")]
    use_lib(env, tmp_path, rows, name="libv")
    seen = []
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [pick(u, "Calm studio", title="Calm studio vibes")]}
    env["state"]["answers"]["mvp_extract"] = items_fake({"Calm studio": {"items": [], "key_points": [
        "A slow morning in the studio with tea and plants"]}}, seen)
    say(env, "studio vibes please", ask("studio vibes", ["studio vibes"]))
    assert seen and not any("Kind asked for" in u for u in seen)


def test_u1_a_kind_and_the_prompt_are_part_of_the_items_cache_key(monkeypatch):
    from mvp import config
    from mvp.extract import items_cache_kind
    base = {"request": "fonts for titles", "about": ""}
    assert items_cache_kind(base) == items_cache_kind(dict(base, kind=None))   # unchanged without a kind
    a = items_cache_kind(dict(base, kind="fonts"))
    assert a != items_cache_kind(base) and a != items_cache_kind(dict(base, kind="tools"))
    monkeypatch.setattr(config, "PROMPT_EXTRACT", "extract_v3")
    assert items_cache_kind(dict(base, kind="fonts")) != a


# ---------- point 2: clear picks lead even when their text names nothing ----------
KITS = "7 UI kits that save hours\nThese kits cut my build time in half\nSwipe to see them all"
KITS2 = "5 UI kits I reach for on every client job\nEach one ships with dark mode and tokens"
ROWS_U2 = [("u1", "kitfan", KITS, "2026-09-14", "2026-09-15", "instagram"),
           ("u2", "kitfan2", KITS2, "2026-08-01", "2026-08-02", "youtube")] + ROWS98
TABLE_U2 = dict(TABLE98, **{
    "7 UI kits": {"items": [], "key_points": ["These kits cut my build time in half"]},
    "client job": {"items": [], "key_points": ["Each one ships with dark mode and tokens"]}})


def compose_u2(u):
    """The composer: a post about UI kits whose names are only in its slides is clear; two list posts come close."""
    return {"picks": [pick(u, "7 UI kits", title="7 UI kits that save hours"),
                      pick(u, "some interface parts", "close", title="Interface parts"),
                      pick(u, "where to find icons", "close", title="Where to find icons")]}


@pytest.fixture()
def lib_u2(env, tmp_path):
    use_lib(env, tmp_path, ROWS_U2, name="libu2")
    env["state"]["answers"]["mvp_compose"] = compose_u2
    env["state"]["answers"]["mvp_extract"] = items_fake(TABLE_U2)
    return env


def test_u2_a_clear_post_that_names_nothing_leads_and_the_close_things_follow(lib_u2):
    msg = say(lib_u2, UI_ASK, ask("UI/UX libraries", ["ui libraries"]))
    assert "Nothing I found is a clear fit" not in msg and "These come closest" not in msg
    assert msg.split("\n")[0] == "Here's what I found in your saves for UI/UX libraries."   # never "I found N ..."
    lines = msg.split("\n")
    lead = next(i for i, x in enumerate(lines) if x.startswith("I recommend 7 UI kits that save hours by @kitfan"))
    assert lines[lead + 1] == "The names are in its slides, not its text."
    assert "• These kits cut my build time in half" in msg   # its key points, under it
    label = lines.index("Named in other saves, close to what you asked:")
    assert lead < label < lines.index(next(x for x in lines if x.startswith('From "Interface parts"')))
    assert msg.count("Named in other saves") == 1 and "Close, but not quite" not in msg
    assert "1. Slider" in msg and "3. Stepper" in msg and "4. iconpile" in msg   # one numbering, things only
    # the close posts are shown once, under the label, never also as "Or these"
    assert msg.count("Interface parts") == 1 and "Or these, which are close too" not in msg
    run = runs(lib_u2)[-1]
    assert json.loads(run["steps"])["clear_leads"] == 1
    assert json.loads(run["fits"]) == ["clear", "close", "close"]


def test_u2_a_follow_up_by_number_acts_on_the_named_things(lib_u2):
    say(lib_u2, UI_ASK, ask("UI/UX libraries", ["ui libraries"]))
    bot = lib_u2["bot"]
    say(lib_u2, "add the second one to my list", {"intent": "todo_add", "pick_number": 2})
    assert bot.store.todos(H)[-1]["text"] == "Toggle"
    say(lib_u2, "add glyphbox to my list", {"intent": "act_on_last", "actions": [{"action": "todo.add", "params": {}}]})
    assert bot.store.todos(H)[-1]["text"] == "glyphbox"


def test_u2_a_video_says_its_video_and_a_second_clear_post_is_an_alternative(lib_u2):
    lib_u2["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        pick(u, "client job", title="5 UI kits I reach for"), pick(u, "7 UI kits", title="7 UI kits that save hours"),
        pick(u, "some interface parts", "close", title="Interface parts")]}
    msg = say(lib_u2, UI_ASK, ask("UI/UX libraries", ["ui libraries"]))
    lines = msg.split("\n")
    lead = next(i for i, x in enumerate(lines) if x.startswith("I recommend 5 UI kits I reach for by kitfan2"))
    assert lines[lead + 1] == "The names are in its video, not its text."
    assert "Or try these:" in msg and "• 7 UI kits that save hours by @kitfan" in msg
    assert msg.index("Or try these:") < msg.index("Named in other saves, close to what you asked:")
    assert "1. Slider" in msg and "Nothing I found" not in msg


def test_u2_spanish_says_the_same_in_spanish(lib_u2):
    from mvp import lang as L
    assert set(L.EN) <= set(L.ES) or all(k in L.ES for k in ("items_named_close", "names_in_slides", "names_in_video"))
    assert L.ES["items_named_close"] != L.EN["items_named_close"]


def test_u2_with_no_clear_pick_the_closest_wording_stays(lib_u2):
    lib_u2["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [
        pick(u, "7 UI kits", "close", title="7 UI kits that save hours"),
        pick(u, "some interface parts", "close", title="Interface parts"),
        pick(u, "where to find icons", "close", title="Where to find icons")]}
    msg = say(lib_u2, UI_ASK, ask("UI/UX libraries", ["ui libraries"]))
    assert msg.startswith('Nothing I found is a clear fit for "UI/UX libraries".\nThese come closest:\n')
    assert "I recommend" not in msg and "Named in other saves" not in msg


def test_u2_a_clear_source_with_things_keeps_the_items_answer(lib_u2):
    lib_u2["state"]["answers"]["mvp_compose"] = compose98   # the one-thing post is clear and has its thing
    msg = say(lib_u2, UI_ASK, ask("UI/UX libraries", ["ui libraries"]))
    assert msg.startswith("I found 1 UI/UX library in your saves, and 2 posts that come close.\n")
    assert "I recommend" not in msg and "Named in other saves" not in msg


def test_u2_the_slides_line_is_said_only_for_a_post_that_promises_a_list():
    from mvp.render import names_elsewhere
    from mvp.tests.test_round8_answers import It as It8

    def p(text, url, facts=None, title=None):
        it = It8(text)
        it.url = url
        return {"item": it, "facts": {"items": []} if facts is None else facts, "title": title or it.first_line}
    assert names_elsewhere(p(KITS, "https://www.instagram.com/reel/abc/")) == "The names are in its video, not its text."
    assert names_elsewhere(p(KITS, "https://www.instagram.com/p/abc/")) == "The names are in its slides, not its text."
    # a post that promises no list: nothing is claimed about where names are
    assert names_elsewhere(p("Calm studio vibes\nA slow morning with tea", "https://www.instagram.com/p/abc/")) == ""
    assert names_elsewhere(p(KITS, "https://www.instagram.com/p/abc/", facts={})) == ""   # never read for things
    assert names_elsewhere(p(KITS, "https://www.instagram.com/p/abc/",
                             facts={"items": [{"name": "Bolt"}]})) == ""   # it has a thing


# ---------- point 3: the posts read for things are chosen steadily ----------
LISTA = "UI goodies for your next project\n1. Bolt - fast and small\n2. Nimbus - light and airy\n3. Quill - tidy forms"
LISTB = "More UI picks for any project\n- Ember: warm tones\n- Frost: cool tones\n- Moss: green tones"
ONE = "Larder is the UI library I use on every project\nGrab it at larder.dev"
ONE_PLAIN = "Larder is what I use on every UI project\nGrab it at larder.dev"
U3_ASK = "what are some ui libraries i should use for my next project"


def u3_lib(env, tmp_path, one):
    rows = [("u1", "kitfan", KITS, "2026-09-14", "2026-09-15", "instagram"),
            ("a1", "lister", LISTA, "2026-07-01", "2026-07-02", "instagram"),
            ("b1", "lister2", LISTB, "2026-06-01", "2026-06-02", "instagram"),
            ("o1", "larderfan", one, "2026-05-01", "2026-05-02", "instagram")]
    use_lib(env, tmp_path, rows, name="libu3")
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [pick(u, "7 UI kits", title="7 UI kits")]}
    seen = []
    env["state"]["answers"]["mvp_extract"] = items_fake({"7 UI kits": {"items": [], "key_points": []}}, seen)
    return seen


def read_texts(seen):
    return [u.split("<item>", 1)[-1] for u in seen]


def test_u3_a_post_that_names_the_kind_is_read_before_posts_that_only_list_things(env, tmp_path, monkeypatch):
    from mvp.executor import ExecutorMixin
    monkeypatch.setattr(ExecutorMixin, "ITEM_READS", 2)   # the shown pick and one more
    seen = u3_lib(env, tmp_path, ONE)
    say(env, U3_ASK, ask("ui libraries for my next project", ["ui libraries"]))
    texts = read_texts(seen)
    assert len(texts) == 2 and any("Larder is the UI library" in t for t in texts)
    assert not any("UI goodies" in t or "More UI picks" in t for t in texts)


def test_u3_without_the_kind_word_the_list_score_order_stands(env, tmp_path, monkeypatch):
    from mvp.executor import ExecutorMixin
    monkeypatch.setattr(ExecutorMixin, "ITEM_READS", 2)
    seen = u3_lib(env, tmp_path, ONE_PLAIN)
    say(env, U3_ASK, ask("ui libraries for my next project", ["ui libraries"]))
    texts = read_texts(seen)
    assert len(texts) == 2 and not any("Larder is what I use" in t for t in texts)
    assert any("UI goodies" in t or "More UI picks" in t for t in texts)


def test_u3_with_room_for_all_every_candidate_is_read_as_before(env, tmp_path):
    seen = u3_lib(env, tmp_path, ONE)
    say(env, U3_ASK, ask("ui libraries for my next project", ["ui libraries"]))
    assert len(read_texts(seen)) == 4


# ---------- the kinds evaluation: "what <kind> should i ..." is an ask, never a question back ----------
def test_u4_what_kind_should_i_is_an_ask_from_the_guard():
    from mvp.interpret import chat_guard
    from mvp.schema import Interpretation
    def chat():
        return Interpretation(intent="chat", reply="Do you want iPhone or Android apps?")
    got = chat_guard(chat(), "what apps should i use to edit photos on my phone")
    assert got.intent == "ask" and got.spec.content.goal == "apps to edit photos on my phone"
    assert chat_guard(chat(), "what productivity apps should i try").spec.content.goal == "productivity apps"
    assert chat_guard(chat(), "what podcasts could i listen to on long drives").intent == "ask"
    # near-variants that stay small talk or a question about something else
    for t in ("what should i cook tonight", "what tools do i need", "what kind of apps should i use",
              "what else should i try", "which one should i pick", "what cameras should i look at as a beginner",
              "what apps should i delete from my phone"):
        assert chat_guard(chat(), t).intent == "chat", t


def test_u1_one_call_may_name_another_priced_model_and_is_logged_with_it(monkeypatch):
    from mvp import config, llm
    seen = []

    def fake(model, system, user, max_tokens=0, purpose="", prompt_version="", **extra):
        seen.append((model, extra))
        return {"items": []}, {}
    monkeypatch.setattr(llm.ai, "openai_chat_json", fake)
    llm.chat_json("s", "u", "mvp_extract_ab", "extract_v4", model="gpt-5.5", reasoning_effort="low", seed=7)
    llm.chat_json("s", "u", "mvp_extract", "extract_v4", temperature=0)
    assert seen[0] == ("gpt-5.5", {"seed": 7, "reasoning_effort": "low"})
    assert seen[1] == (config.MODEL, {"temperature": 0})   # the default model, nothing extra sent


def test_u3_a_post_naming_the_kind_is_read_before_the_composers_other_picks(env, tmp_path, monkeypatch):
    from mvp.executor import ExecutorMixin
    monkeypatch.setattr(ExecutorMixin, "ITEM_READS", 2)
    seen = u3_lib(env, tmp_path, ONE)
    # the composer returns a list post as a close pick past the count: before, it took the one place left
    env["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [pick(u, "7 UI kits", title="7 UI kits"),
                                                                  pick(u, "UI goodies", "close", title="UI goodies")]}
    say(env, U3_ASK, ask("ui libraries for my next project", ["ui libraries"], count=1))
    texts = read_texts(seen)
    assert len(texts) == 2 and any("Larder is the UI library" in t for t in texts)
    assert not any("UI goodies" in t for t in texts)
