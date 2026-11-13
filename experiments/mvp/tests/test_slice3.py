"""Offline tests for slice 3 (DESIGN.md sections 3, 4 and 11: "Answers", "Content", "Link previews in Messages"): the
composer's verdicts and checks, the details step and its cache, YouTube details, retrieval filters and orders, the
caches, and replies made of parts. Synthetic data only; the fixtures come from test_mvp.py and test_slice2.py."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import compose_picks, env, last, pasta_spec  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, say  # noqa: E402

UTC = timezone.utc
LEMON = "Lemon garlic pasta\nIngredients:\n- 200g spaghetti\n- 2 lemons\n- 4 cloves garlic\nlink in bio for my storefront"


def ask(spec_content=None, **content):
    spec = pasta_spec({"type": "now"})
    spec["content"].update(spec_content or {}, **content)
    return {"intent": "ask", "spec": spec}


def compose_once(env, answer, **content):
    """One ask with the fake composer giving `answer`; returns the reply text."""
    env["state"]["answers"]["mvp_compose"] = answer if callable(answer) else (lambda u: answer)
    return say(env, "pasta?", ask(**content))


def add_items(env, rows):
    """More synthetic items in the test library (the view is read again)."""
    lib = env["lib"]
    with open(lib / "corpus" / "items.jsonl", "a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    with open(lib / "corpus" / "interactions.jsonl", "a") as f:
        for r in rows:
            for k, at in (r.pop("_dates", None) or {"save": "2026-03-01T10:00:00+00:00"}).items():
                f.write(json.dumps({"item_id": r["id"], "kind": k, "at": at}) + "\n")
    env["bot"].views.clear()


def yt_item(iid="itm_y", vid="SYNvid00001", title="Easy beginner donut in Blender", dur=None):
    return {"id": iid, "platform": "youtube", "source_url": f"https://www.youtube.com/watch?v={vid}", "caption": title,
            "interaction_kinds": ["watch"], "platform_data": {"video_id": vid, "owner_name": "Synthetic Channel",
                                                               "owner_relation": "none", "duration_s": dur}}


# ---------- the composer's checks ----------
def test_because_needs_quotes_from_the_item_and_numbers_from_its_text(env):
    good = {"picks": [{"n": 2, "verdict": "clear", "title": "Lemon garlic pasta",
                       "because": "it needs just 2 lemons and some garlic",
                       "facts": [{"label": "lemons", "quote": "2 lemons"}, {"label": "garlic", "quote": "4 cloves garlic"}]}],
            "intro": "I've found a lemony pasta in your saves."}
    msg = compose_once(env, good)
    assert "I recommend Lemon garlic pasta by @chef, which you saved in March, because it needs just 2 lemons and some " \
           "garlic." in msg
    assert "Why:" not in msg
    # a quote that is not in the item's text: the plain clause built by code
    bad_quote = json.loads(json.dumps(good))
    bad_quote["picks"][0]["facts"][1]["quote"] = "a pinch of chili"
    msg = compose_once(env, bad_quote)
    # (how they kept it is already in the sentence, so the clause does not say it twice)
    # fix pass, finding 10: an unbacked reason is dropped altogether, never "because it matches what you asked for"
    assert "which you saved in March.\n" in msg and "2 lemons and" not in msg and "because" not in msg
    # a number that is not in the text ("15 minutes") is never shown, even with good quotes
    bad_number = json.loads(json.dumps(good))
    bad_number["picks"][0]["because"] = "it takes 15 minutes and needs 2 lemons"
    msg = compose_once(env, bad_number)
    assert "15 minutes" not in msg and "because" not in msg
    # no facts at all: not backed
    no_facts = json.loads(json.dumps(good))
    no_facts["picks"][0]["facts"] = []
    assert "because" not in compose_once(env, no_facts)
    run = env["bot"].store.one("SELECT fits FROM runs ORDER BY id DESC LIMIT 1")
    assert json.loads(run["fits"]) == ["clear"]                     # verdicts, never a score


def test_a_criterion_no_drops_the_pick_and_an_unbacked_yes_is_unknown(env):
    from mvp.compose import check
    from mvp.schema import RuleSpec
    view = env["bot"].view(str(env["lib"]))
    cands = [view.get("itm_a"), view.get("itm_c")]
    spec = RuleSpec.model_validate(pasta_spec({"type": "now"}))
    spec.content.criteria = ["uses lemons"]
    raw = {"picks": [{"n": 1, "verdict": "clear", "title": "Lemon garlic pasta", "criteria": [{"answer": "no"}]},
                     {"n": 2, "verdict": "clear", "title": "Pasta night",
                      "criteria": [{"answer": "yes", "quote": "fresh lemons"}]}]}
    r = check(raw, cands, spec)
    assert [p["item"].id for p in r["picks"]] == ["itm_c"] and r["dropped"]["criterion_no"] == 1
    # the "yes" quote is not in itm_c's text: it counts as unknown, so the pick is only close
    assert r["closest"] and r["picks"][0]["criteria"] == ["unknown"] and r["dropped"]["criterion_unbacked"] == 1
    assert r["missing"] == [("uses lemons", "unknown")] and r["unknown_criteria"] == ["uses lemons"]
    raw["picks"][1]["criteria"] = [{"answer": "yes", "quote": "Pasta night"}]
    r = check(raw, cands, spec)
    assert not r["closest"] and r["picks"][0]["verdict"] == "clear" and r["unknown_criteria"] == []
    # section 3: code drops a pick with any "no", so a "no" is never a pick, an alternative or the closest; with
    # nothing else the bot says it found nothing (the composer's none_reason, or the default)
    r = check({"picks": [raw["picks"][0]]}, cands, spec)
    assert r["picks"] == [] and not r["closest"] and r["dropped"]["criterion_no"] == 1


def test_only_close_picks_show_the_closest_and_all_no_says_nothing(env):
    close = {"picks": [{"n": 2, "verdict": "close", "title": "Lemon garlic pasta"},
                       {"n": 3, "verdict": "close", "title": "Pasta night"}]}
    msg = compose_once(env, close)
    assert msg.startswith("Nothing I found is a clear fit for \"a pasta recipe\".")
    assert "The closest I have is Lemon garlic pasta by @chef" in msg and "Pasta night" not in msg
    assert env["bot"].store.last_answer(H)["items"] == ["itm_a"]
    calls = env["calls"].count("mvp_compose")
    msg = compose_once(env, {"picks": [{"n": 1, "verdict": "no", "title": "x"}], "none_reason": "none of these is pasta"})
    assert msg == "I didn't find a good match: nothing in your library fits well."   # finding 5: never the model's words
    assert env["calls"].count("mvp_compose") == calls + 2           # one more try before saying nothing (section 4)


def test_a_retry_that_finds_a_pick_is_used(env):
    answers = iter([{"picks": []}, {"picks": [{"n": 2, "verdict": "clear", "title": "Lemon garlic pasta"}]}])
    msg = compose_once(env, lambda u: next(answers))
    assert "I recommend Lemon garlic pasta" in msg


def test_a_must_have_unknown_for_every_candidate_is_said(env):
    raw = {"picks": [{"n": 2, "verdict": "clear", "title": "Lemon garlic pasta", "criteria": [{"answer": "unknown"}]}]}
    msg = compose_once(env, raw, criteria=["under 10 minutes"])
    # it is the closest, not a clear pick, and the must-have nobody's text answers is said once, with the reason
    assert msg.startswith("I couldn't confirm any of these is under 10 minutes long, but the closest I have "
                          "is Lemon garlic pasta")
    assert msg.count("under 10 minutes") == 1
    # two must-haves unknown for every shown item: the first opens the reply, the second gets its own line
    raw = {"picks": [{"n": 2, "verdict": "clear", "title": "Lemon garlic pasta",
                      "criteria": [{"answer": "unknown"}, {"answer": "unknown"}]}]}
    msg = compose_once(env, raw, criteria=["vegetarian", "under 10 minutes"])
    assert msg.startswith("I couldn't confirm any of these clearly fits \"vegetarian\", but the closest I have is")
    assert "I couldn't check \"under 10 minutes\" for any of these: the posts don't say." in msg
    assert msg.count("vegetarian") == 1


def test_alternatives_wider_selection_and_top_n(env):
    raw = {"picks": [{"n": 2, "verdict": "clear", "title": "Lemon garlic pasta"},
                     {"n": 3, "verdict": "clear", "title": "Pasta night", "because": "it is a pasta night pick",
                      "facts": [{"label": "pasta", "quote": "Pasta night"}]},
                     {"n": 4, "verdict": "clear", "title": "Best carbonara ever"}],
           "intro": "Here are some pasta ideas from your saves."}
    msg = compose_once(env, raw, count=2)
    # an alternative's line says what is written out, from the checked lines (here: nothing, on Instagram)
    assert "Or try these:\n• Pasta night by @chef: the recipe is in the video. https://example.com/itm_c" in msg
    assert "Or here's a wider selection:\n• Best carbonara ever: https://example.com/itm_e" in msg
    assert env["bot"].store.last_answer(H)["items"] == ["itm_a", "itm_c", "itm_e"]
    # a timed rule never gets the wider selection; a count that was cut says "top N"
    from mvp.schema import RuleSpec
    spec = RuleSpec.model_validate(dict(pasta_spec({"type": "now"}), content=dict(pasta_spec()["content"], count=12)))
    assert spec.content.count == 10 and spec.content.asked_count == 12
    from mvp.render import picks_message
    view = env["bot"].view(str(env["lib"]))
    p = {"item": view.get("itm_a"), "title": "Lemon garlic pasta", "because": "it fits", "facts": {}, "lines": []}
    out = picks_message({"picks": [p], "wider": []}, spec)
    assert "You asked for 12, so here are the top 10." in out


def test_profile_and_lang_reach_the_composer(env):
    bot = env["bot"]
    bot.store.add_profile_note(H, "Vegetarian")
    bot.store.x("UPDATE people SET direction=? WHERE handle=?", ("learning to cook for one", H))
    seen = []
    say(env, "x", {"intent": "chat", "reply": "hi"})
    env["state"]["answers"]["mvp_compose"] = lambda u: (seen.append(u), {"picks": []})[1]
    say(env, "¿pasta?", dict(ask(), lang="es"))
    assert "Vegetarian" in seen[0] and "learning to cook for one" in seen[0] and '"lang": "es"' in seen[0]
    assert "<item>What they are working toward" in seen[0]          # the profile goes in as data
    # fix pass, finding 15: a language with no phrase table gets an all-English answer (the composer writes English)
    say(env, "des pâtes ?", dict(ask(), lang="fr"))
    assert '"lang": "en"' in seen[-1]          # checker: told so, or it follows the request's language


# ---------- the details step ----------
def test_details_are_extracted_once_checked_and_cached(env):
    st, calls = env["state"], env["calls"]
    st["answers"]["mvp_extract"] = lambda u: {"ingredients": ["200g spaghetti", "2 lemons", "1 cup cream"],
                                              "steps": []}
    pick = {"picks": [{"n": 2, "verdict": "clear", "title": "Lemon garlic pasta"}]}
    msg = compose_once(env, pick, extract=["ingredients"])
    assert "Ingredients (2):\n• 200g spaghetti\n• 2 lemons" in msg and "cream" not in msg
    first = calls.count("mvp_extract")
    assert first == 2               # the text looks like a list and no step came back: tried once more
    rows = env["bot"].store.q("SELECT kind, lines, attempts, prompt_version FROM facts ORDER BY kind")
    assert [(r["kind"], json.loads(r["lines"]), r["attempts"]) for r in rows] == [
        ("ingredients", ["200g spaghetti", "2 lemons"], 1), ("steps", [], 2)]
    assert rows[0]["prompt_version"] == "extract_v1"
    st["answers"]["mvp_extract"] = lambda u: pytest.fail("cached details are reused")
    msg = compose_once(env, pick, extract=["ingredients", "steps"])
    assert "Ingredients (2):" in msg and calls.count("mvp_extract") == first


def test_an_empty_result_is_cached_only_after_two_attempts(env):
    add_items(env, [{"id": "itm_t", "platform": "instagram", "source_url": "https://example.com/itm_t",
                     "caption": "A calm evening walk by the river, nothing else to say about it really.",
                     "interaction_kinds": ["save"], "platform_data": {"owner_handle": "walker"}}])
    from mvp.extract import details
    bot = env["bot"]
    view = bot.view(str(env["lib"]))
    env["state"]["answers"]["mvp_extract"] = lambda u: {"key_points": []}
    lib = view.lib
    facts, info = details(view.get("itm_t"), ["key_points"], lib, store=bot.store)
    assert facts == {"key_points": []} and info["calls"] == 1      # no list in the text: no retry
    facts, info = details(view.get("itm_t"), ["key_points"], lib, store=bot.store)
    assert info["calls"] == 1 and bot.store.facts_get(lib, "itm_t", ["key_points"]) == {"key_points": []}
    facts, info = details(view.get("itm_t"), ["key_points"], lib, store=bot.store)
    assert info["calls"] == 0                                        # two empty attempts: cached as empty


def test_key_points_survive_long_lines_hashtags_and_list_marks(env):
    from mvp.extract import verify
    text = ("3 editing tips 📸\n1️⃣ Lower the highlights before you touch the shadows, because bright skies clip first "
            "and you cannot get them back later in the edit #lightroom\n2. Warm the white balance a little #tips\n"
            "Follow these steps for softer skin tones")
    lines, dropped = verify(["1️⃣ Lower the highlights before you touch the shadows, because bright skies clip first "
                             "and you cannot get them back later in the edit #lightroom",
                             "Warm the white balance a little #tips", "Follow these steps for softer skin tones",
                             "Use a preset for everything"], " ".join(text.split()), "key_points")
    # checker of fix pass 4, finding 81: a cut line is never shown, so a long one is kept whole (up to STEP_LIMIT)
    assert lines[0] == ("Lower the highlights before you touch the shadows, because bright skies clip first and you "
                        "cannot get them back later in the edit")
    assert "#" not in lines[1] and lines[1] == "Warm the white balance a little"
    assert "Follow these steps for softer skin tones" in lines                # "follow" alone is not a call to follow
    assert dropped == 1                                                       # the invented tip


def test_a_retry_when_the_text_is_a_list_and_no_line_survives(env):
    from mvp.extract import details
    bot = env["bot"]
    view = bot.view(str(env["lib"]))
    answers = iter([{"ingredients": ["spaghetti, lemons and garlic"], "steps": []},
                    {"ingredients": ["200g spaghetti"], "steps": []}])
    seen = []
    env["state"]["answers"]["mvp_extract"] = lambda u: (seen.append(u), next(answers))[1]
    facts, info = details(view.get("itm_a"), ["ingredients"], view.lib, store=bot.store)
    assert facts["ingredients"] == ["200g spaghetti"] and info["calls"] == 2
    assert "not exact copies" in seen[1] and '"ingredients"' in seen[1].split("\n")[0]


def test_missing_details_youtube_says_nothing_instagram_says_in_the_video(env):
    env["state"]["answers"]["mvp_extract"] = lambda u: {"ingredients": [], "steps": []}
    msg = compose_once(env, {"picks": [{"n": 3, "verdict": "clear", "title": "Pasta night"}]})
    assert "The recipe is in the video, not written in the post." in msg
    msg = compose_once(env, {"picks": [{"n": 4, "verdict": "clear", "title": "Best carbonara ever"}]})
    assert "video" not in msg.split("https://example.com/itm_e")[1] and "couldn't find" not in msg


# ---------- YouTube details ----------
def _resp(vid, desc, dur="PT12M5S"):
    return {"items": [{"id": vid, "snippet": {"description": desc}, "contentDetails": {"duration": dur}}]}


def test_youtube_details_are_used_and_expire(env, monkeypatch):
    from mvp import ytinfo
    bot, clock = env["bot"], env["clock"]
    add_items(env, [yt_item()])
    asked = []

    def fake_fetch(ids, key, timeout=None):
        asked.append(list(ids))
        assert key == "test-key"
        return _resp(ids[0], "Make a donut from start to finish.\nYou need:\n- Blender 4.2\n- a mouse")
    monkeypatch.setattr(ytinfo, "fetch_batch", fake_fetch)
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    env["state"]["answers"]["mvp_extract"] = lambda u: {"steps": [], "ingredients": [], "key_points": ["Blender 4.2"]}
    seen = []

    def composer(u):
        seen.append(u)
        return {"picks": [{"n": 1, "verdict": "clear", "title": "Easy beginner donut in Blender",
                           "because": "it takes 12 minutes and ends with a finished donut",
                           "facts": [{"label": "finished", "quote": "Make a donut from start to finish"},
                                     {"label": "length", "quote": "12 minutes"}],
                           "criteria": [{"answer": "yes", "quote": "from start to finish"}]}]}
    env["bot"].pool.search = lambda lib, q, depth=300: {"ids": ["itm_y"], "mode": "normal", "cost_usd": 0.0}
    msg = compose_once(env, composer, extract=["key_points"], criteria=["ends with a finished model"])
    assert "Video length: 12 minutes 5 seconds (from YouTube)" in seen[0] and "Make a donut from start to finish" in seen[0]
    assert "because it takes 12 minutes and ends with a finished donut." in msg
    assert "Key points (1):\n• Blender 4.2" in msg and asked == [["SYNvid00001"]]
    assert bot.store.one("SELECT source FROM facts WHERE item_id='itm_y'")["source"] == "youtube_api"
    compose_once(env, composer, extract=["key_points"], criteria=["ends with a finished model"])
    assert asked == [["SYNvid00001"]]                                # kept, not fetched again
    clock[0] = clock[0] + timedelta(days=31)                          # YouTube's 30 days: deleted and fetched again
    compose_once(env, composer, extract=["key_points"], criteria=["ends with a finished model"])
    assert asked == [["SYNvid00001"], ["SYNvid00001"]]
    assert bot.store.one("SELECT COUNT(*) n FROM youtube_cache")["n"] == 1


def test_without_a_key_or_on_an_error_youtube_works_as_before(env, monkeypatch):
    from mvp import ytinfo
    add_items(env, [yt_item()])
    env["bot"].pool.search = lambda lib, q, depth=300: {"ids": ["itm_y"], "mode": "normal", "cost_usd": 0.0}
    monkeypatch.setattr(ytinfo, "fetch_batch", lambda *a, **k: pytest.fail("no key: no call"))
    pick = {"picks": [{"n": 1, "verdict": "clear", "title": "Easy beginner donut in Blender",
                       "because": "it takes 12 minutes", "facts": [{"label": "length", "quote": "12 minutes"}]}]}
    msg = compose_once(env, pick)
    assert "12 minutes" not in msg and "I recommend Easy beginner donut in Blender by Synthetic Channel" in msg
    assert "video" not in msg.split("watch?v=SYNvid00001")[1]         # nothing about missing steps for YouTube

    def broken(*a, **k):
        raise ytinfo.urllib.error.URLError("down")
    monkeypatch.setattr(ytinfo, "fetch_batch", broken)
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    assert "I recommend Easy beginner donut" in compose_once(env, pick)
    assert env["bot"].yt.errors == 1


def test_videos_list_is_one_call_per_50_and_the_key_goes_in_a_header(env, monkeypatch):
    from mvp import ytinfo
    from mvp.libview import Item
    got = []

    class R:
        def __init__(self, req):
            got.append(req)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"items": []}'
    monkeypatch.setattr(ytinfo.urllib.request, "urlopen", lambda req, timeout=None, context=None: R(req))
    monkeypatch.setenv("YOUTUBE_API_KEY", "secret-key")
    items = [Item(yt_item(f"y{i}", f"VID{i:08d}")) for i in range(120)]
    info = ytinfo.YouTubeInfo(env["bot"].store)
    assert info.details(items) == {} and info.calls == 3
    assert all("secret-key" not in r.full_url and r.get_header("X-goog-api-key") == "secret-key" for r in got)
    assert env["bot"].store.one("SELECT COUNT(*) n FROM youtube_cache WHERE ok=0")["n"] == 120   # unavailable, kept


# ---------- retrieval ----------
def _view(env, rows):
    add_items(env, rows)
    return env["bot"].view(str(env["lib"]))


def _ig(iid, cap, creator="chef", kinds=("save",), cols=(), at="2026-03-01T10:00:00+00:00", platform="instagram"):
    return {"id": iid, "platform": platform, "source_url": f"https://example.com/{iid}", "caption": cap,
            "interaction_kinds": list(kinds), "_dates": {k: at for k in kinds},
            "platform_data": {"owner_handle": creator, "owner_relation": "none", "collections": list(cols)}}


def test_retrieval_filters_orders_and_sources(env):
    from mvp.retrieve import candidates
    from mvp.schema import RuleSpec
    view = _view(env, [_ig("r1", "Soup one", "anna", cols=["Dinners"], at="2026-01-05T10:00:00+00:00"),
                       _ig("r2", "Soup two", "ben", kinds=("like",), at="2026-02-05T10:00:00+00:00"),
                       _ig("r3", "Soup three", "anna", kinds=("save", "like"), cols=["Lunch ideas"],
                           at="2026-03-05T10:00:00+00:00"),
                       _ig("r4", "Soup four", "Blender Guru", at="2026-04-05T10:00:00+00:00", platform="youtube")])

    class Pool:
        def search(self, lib, q, depth=300):
            return {"ids": ["r1", "r2", "r3", "r4"], "mode": "normal", "cost_usd": 0.0}

    def ids(**content):
        spec = RuleSpec.model_validate({"when": {"type": "now"}, "content": dict(
            {"goal": "soup", "searches": ["soup"]}, **{k: v for k, v in content.items() if not k.startswith("_")})})
        got, _ = candidates(Pool(), view, spec, now=datetime(2026, 11, 12, tzinfo=UTC),
                            **{k[1:]: v for k, v in content.items() if k.startswith("_")})
        return [it.id for it in got]
    assert ids() == ["r1", "r3", "r4", "r2"]                          # relevance, with kept-by-saving first
    assert ids(creators=["@Anna"]) == ["r1", "r3"] and ids(avoid_creators=["anna"]) == ["r4", "r2"]
    assert ids(creators=["blender guru"]) == ["r4"]
    assert ids(collections=["dinners"]) == ["r1"] and ids(avoid_collections=["Lunch Ideas"]) == ["r1", "r4", "r2"]
    assert ids(order="newest") == ["r4", "r3", "r2", "r1"] and ids(order="oldest") == ["r1", "r2", "r3", "r4"]
    a, b = ids(order="random", _seed="rule1:2026-11-12"), ids(order="random", _seed="rule1:2026-11-12")
    assert a == b and sorted(a) == ["r1", "r2", "r3", "r4"]           # seeded: the same run gives the same order
    assert ids(_exclude_kinds=["like"]) == ["r1", "r3", "r4"]         # liked only: out; saved and liked: stays
    assert ids(_exclude_platforms=["youtube"]) == ["r1", "r3", "r2"]
    assert ids(saved_before="2026-03-05") == ["r1", "r2"]             # exclusive
    assert ids(saved_after="2026-03-05") == ["r3", "r4"]              # inclusive
    recent = ids(source="recent", saved_after="2026-02-01")
    # newest first, nothing searched (the fixture's own items were kept on 1 March, between r3 and r2)
    assert recent[:2] == ["r4", "r3"] and recent[-1] == "r2" and "r1" not in recent and "itm_d" not in recent
    assert ids(source="items", item_ids=["r3", "r1"]) == ["r3", "r1"]


def test_the_persons_exclusions_apply_to_every_request(env):
    bot = env["bot"]
    bot.store.set_prefs(H, exclude_kinds=["like"], exclude_platforms=["youtube"])
    seen = []
    env["state"]["answers"]["mvp_compose"] = lambda u: (seen.append(u), {"picks": []})[1]
    say(env, "pasta?", ask())
    assert "Pasta night" not in seen[0] and "carbonara" not in seen[0] and "Lemon garlic pasta" in seen[0]


# ---------- caches ----------
def test_the_same_spec_and_candidates_give_the_same_answer_and_another_bypasses(env, monkeypatch):
    from mvp import config
    monkeypatch.setattr(config, "ANSWER_CACHE_HOURS", 24)
    answers = iter([{"picks": [{"n": 2, "verdict": "clear", "title": "Lemon garlic pasta"}]},
                    {"picks": [{"n": 3, "verdict": "clear", "title": "Pasta night"}]},
                    {"picks": [{"n": 1, "verdict": "clear", "title": "Pasta night"}]}])
    env["state"]["answers"]["mvp_compose"] = lambda u: next(answers)
    first = say(env, "pasta?", ask())
    again = say(env, "pasta?", ask())
    assert first == again and env["calls"].count("mvp_compose") == 1
    assert env["bot"].store.one("SELECT COUNT(*) n FROM answer_cache")["n"] == 1
    other = say(env, "another", {"intent": "more"})
    assert "Lemon garlic pasta" not in other and env["calls"].count("mvp_compose") == 2


def test_the_same_search_text_reuses_its_ranked_list(env, monkeypatch, tmp_path):
    from mvp import config
    from mvp.retrieve import ranked
    monkeypatch.setattr(config, "RANKED_CACHE_HOURS", 24)
    n = []

    class Pool:
        def search(self, lib, q, depth=300):
            n.append(q)
            return {"ids": ["a", "b"], "mode": "normal", "cost_usd": 0.001}
    store, lib = env["bot"].store, str(env["lib"])
    now = datetime(2026, 11, 12, tzinfo=UTC)
    assert ranked(Pool(), lib, "Pasta  Recipe", store, now)["ids"] == ["a", "b"]
    r = ranked(Pool(), lib, "pasta recipe", store, now)
    assert r["ids"] == ["a", "b"] and r["cost_usd"] == 0.0 and len(n) == 1
    os.utime(env["lib"] / "corpus" / "items.jsonl", (1, 1))          # the library was rebuilt
    ranked(Pool(), lib, "pasta recipe", store, now)
    assert len(n) == 2


# ---------- replies made of parts ----------
def test_parts_are_joined_or_sent_one_by_one_and_a_reaction_on_any_maps_to_the_run(env):
    bot, ch = env["bot"], env["ch"]
    pick = {"picks": [{"n": 2, "verdict": "clear", "title": "Lemon garlic pasta", "lines": ["200g spaghetti"]}],
            "intro": "Found one."}
    msg = compose_once(env, pick)
    assert len(ch.outbox) == 1 and msg.startswith("Found one.") and "\nhttps://example.com/itm_a\n" in msg
    ch.link_previews = True
    n = len(ch.outbox)
    compose_once(env, pick)
    parts = [t for _, _, t in ch.outbox[n:]]
    assert len(parts) == 3 and parts[1] == "https://example.com/itm_a" and parts[0].startswith("Found one.")
    run = bot.store.one("SELECT id FROM runs ORDER BY id DESC LIMIT 1")["id"]
    refs = [r for r, _, _ in ch.outbox[n:]]
    assert {bot.store.run_for_ref(r) for r in refs} == {run}
    bot.on_message(H, "", tapback="down", tapback_ref=refs[1])        # 👎 on the link bubble
    assert bot.store.disliked(H) == {"itm_a"}


def test_reply_parts_join_with_plain_text():
    from mvp.render import Reply
    r = Reply([{"type": "text", "text": "Hi"}, {"type": "link", "url": "https://x.test/1"}])
    r = "Head\n\n" + r + "\n\nTail"
    assert r.text() == "Head\n\nHi\nhttps://x.test/1\nTail"
    assert [p["type"] for p in r.split()] == ["text", "link", "text"] and r.split()[2]["text"] == "Tail"
    assert "Tail" in r and r == r.text()


def test_a_partly_sent_reply_is_never_sent_again(env):
    from mvp.channels.base import SendUncertain
    from mvp.render import Reply
    bot, ch = env["bot"], env["ch"]
    ch.link_previews = True
    sent = []

    def flaky(handle, text):
        if sent:
            raise RuntimeError("down")
        sent.append(text)
        return "ref-1"
    ch.send = flaky
    with pytest.raises(SendUncertain):
        bot.send(H, Reply([{"type": "text", "text": "a"}, {"type": "link", "url": "https://x.test/1"}]))


def test_timed_sends_keep_their_footer_in_the_new_voice(env):
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    st["answers"]["mvp_compose"] = compose_picks({"n": 1, "title": "Pasta", "verdict": "clear"})
    say(env, "pasta every friday", {"intent": "new_rule", "spec": pasta_spec()})
    say(env, "yes", {"intent": "confirm"})
    clock[0] = datetime(2026, 11, 14, 0, 1, tzinfo=UTC)
    assert bot.tick() == 1
    assert last(ch).endswith("Not for you? Reply 👎. Want one more now? Reply \"another\". To pause these, reply "
                             "\"pause 1\".")


def test_the_contact_card_is_sent_once_after_the_first_reply(env):
    bot, ch = env["bot"], env["ch"]
    cards = []
    ch.send_contact_card = lambda handle: (cards.append(handle), "card-1")[1]
    h = "+15550001"
    bot.store.x("UPDATE people SET consent_version=NULL WHERE handle=?", (h,))
    bot.on_message(h, "hi")
    assert cards == []                                               # their first message gets the consent text
    bot.on_message(h, "I agree")
    assert cards == [h] and last(ch) == "Save me as a contact, so the links I send show a preview."
    bot.store.x("UPDATE people SET consent_version=NULL WHERE handle=?", (h,))
    bot.on_message(h, "I agree")
    assert cards == [h]                                              # once


def test_web_cards_never_carry_media_and_instagram_gets_a_permalink(tmp_path):
    from mvp.channels.web import WebChannel, instagram_permalink
    ch = WebChannel(serve=False)
    ch.send_link("+1", {"url": "https://www.youtube.com/watch?v=SYNvid00001", "title": "T", "platform": "youtube",
                        "video_id": "SYNvid00001"})
    ch.send_link("+1", {"url": "https://www.instagram.com/reel/ABC_12-3/?id=9", "title": "R", "platform": "instagram"})
    ch.send_link("+1", {"url": "https://www.youtube.com/watch?v=x", "title": "T", "platform": "youtube",
                        "video_id": "<script>"})
    yt, ig, bad = [m["link"] for m in ch.threads["+1"]]
    assert yt["video_id"] == "SYNvid00001" and ig["permalink"] == "https://www.instagram.com/reel/ABC_12-3/"
    assert bad["video_id"] is None and instagram_permalink("https://example.com/p/x/") is None
    page = open(os.path.join(os.path.dirname(HERE), "channels", "web_page.html")).read()
    assert 'width="480" height="270"' in page and "youtube-nocookie.com/embed/" in page
    assert "i.ytimg.com/vi/" in page and "instagram.com/embed.js" in page and "Open on Instagram" in page


def test_an_old_store_gains_the_new_tables_and_columns(tmp_path):
    import sqlite3
    path = tmp_path / "old.sqlite"
    db = sqlite3.connect(path)
    db.executescript("CREATE TABLE people (handle TEXT PRIMARY KEY, name TEXT, library TEXT NOT NULL, timezone TEXT "
                     "NOT NULL, consent_version TEXT, consent_at TEXT, paused INTEGER DEFAULT 0, created_at TEXT);"
                     "CREATE TABLE sent (channel_ref TEXT PRIMARY KEY, handle TEXT, run_id INTEGER, at TEXT);"
                     "INSERT INTO people(handle,library,timezone) VALUES('+1','/x','UTC');")
    db.commit()
    db.close()
    from mvp.store import Store
    s = Store(str(path))
    assert s.person_context("+1") == {"direction": None, "notes": [], "prefs": {}}
    s.record_sent("r1", "+1", 5, part=2)
    assert s.run_for_ref("r1") == 5
    s.facts_put("/lib", "i", "steps", ["a"], "extract_v1")
    assert s.facts_get("/lib", "i", ["steps"]) == {"steps": ["a"]}
