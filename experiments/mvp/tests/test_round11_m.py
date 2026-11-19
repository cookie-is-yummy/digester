"""Round 11, slice M (DESIGN.md section 18.M): "summarize what I've learned about X" across many items (synth.py).

Made-up data only: the synthesis eval library (evalset/synth/, built on the self-test's made-up library) and the fakes.
No network, no model."""
import json
import os
import re
import shutil
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, say  # noqa: E402

MVP = os.path.dirname(HERE)
SET = os.path.join(MVP, "evalset", "synth")
TOPICS = [json.loads(x) for x in open(os.path.join(SET, "topics.jsonl"), encoding="utf-8") if x.strip()]
CHAT = {"intent": "chat", "reply": "INTERPRETER"}

TAKEN = [
    ("summarize what ive learned about motion design from what i watched", "motion design"),
    ("summarize what I have learned about sourdough", "sourdough"),
    ("what have i learned about budgeting", "budgeting"),
    ("what did I learn about color grading?", "color grading"),
    ("tell me what i've learned about running form", "running form"),
    ("what do my saves say about houseplants", "houseplants"),
    ("what do the videos i watched say about sleep", "sleep"),
    ("the main ideas across what i watched on motion design", "motion design"),
    ("what are the key takeaways from my saves about composting", "composting"),
    ("main takeaways about blender from my saves", "blender"),
    ("summarize blender from what i watched", "blender"),
    ("give me a summary of my saves on stretching", "stretching"),
    ("can you sum up everything i've watched about watercolor", "watercolor"),
    ("ok so what have i picked up about strength training so far", "strength training"),
]
# near variants that must go another way: a rule (a time or a repeat), an action, a question on one pick, the recap,
# the trends, a history question (slice H), small talk, a request for a pick, a topic that is the bot or the person
NOT_TAKEN = [
    "send me a summary of what i learned about blender every week",
    "every sunday summarize what i learned about sourdough",
    "summarize what i learned about blender this month",
    "what did i learn about running last week",
    "what have i learned about sleep lately",
    "remind me what i learned about blender tomorrow",
    "email me a summary of what i learned about pasta",
    "add a summary of what i learned about pasta to my list",
    "summarize it", "summarize the second one", "summarize the pasta video", "summarize", "summarize my saves",
    "summarize my week", "recap", "what have i been into lately",
    "how many videos about blender have i watched", "what did i watch last week",
    "which channels do i watch the most", "when did i first start watching cooking videos",
    "what was that video i watched about color grading",
    "what have i learned", "what have i learned about myself", "what did i learn about my rules",
    "what do you know about me", "what should i watch tonight", "find me a blender tutorial",
    "what are the main ideas", "i learned a lot about sourdough", "learn about sourdough",
]


# ---------- the read ----------
@pytest.mark.parametrize("text,topic", TAKEN)
def test_the_read_takes_these_and_keeps_only_the_topic(text, topic):
    from mvp import synth
    got = synth.read(text)
    assert got is not None and got["topic"] == topic and not got["these"], (text, got)


@pytest.mark.parametrize("text", NOT_TAKEN)
def test_near_variants_are_not_taken(text):
    from mvp import synth
    assert synth.read(text) is None, text


def test_these_forms_read_the_last_answer():
    from mvp import synth
    for t in ("what do these say", "what do those videos all say about lighting", "summarize all of these"):
        assert synth.read(t)["these"], t


def test_function_words_never_reach_the_topic():
    from mvp import synth
    for text, _ in TAKEN:
        topic = synth.read(text)["topic"]
        assert not re.search(r"\b(?:learn\w*|watch\w*|saves?|summar\w*|what|from|so far|takeaways?)\b", topic), topic


def test_the_eval_set_messages_are_all_taken():
    from mvp import synth
    assert len(TOPICS) == 12
    for t in TOPICS:
        assert synth.read(t["message"])["topic"] == t["topic"], t["id"]


def test_no_rule_eval_text_or_rule_phrasing_is_taken():
    """The 159 rule-eval texts and the rule phrasings of the earlier tests (test_round9_merge.py) are taken by no read
    of this slice."""
    from mvp import synth
    from mvp.tests.test_round9_merge import eval_texts, rule_phrasings
    texts, phr = eval_texts(), rule_phrasings()
    assert len(texts) == 159 and len(phr) == 123
    assert [t for t in texts + phr if synth.read(t) is not None] == []


# ---------- the checks on the model's points ----------
class It:
    def __init__(self, iid, caption, platform="instagram"):
        self.id, self.caption, self.raw_caption, self.platform = iid, caption, caption, platform
        self.url, self.creator, self.duration_s, self.video_id = f"https://example.com/{iid}", "@made_up", None, None
        self.caption_mark, self.caption_reasons, self.caption_fp = None, (), None


ITEMS = [It("a", "Feed your starter at the same time every day. Use a 1:1:1 ratio of starter, flour and water."),
         It("b", "A long cold proof in the fridge overnight gives more flavour and an easier score."),
         It("c", "Bake in a preheated dutch oven, lid on for 20 minutes, then lid off.")]


def pt(text, *sources):
    return {"text": text, "sources": [{"n": n, "quote": q} for n, q in sources]}


def test_a_point_traced_to_its_quote_is_kept():
    from mvp.synth import check_points
    raw = {"points": [pt("Feed the starter at the same time every day.", (1, "Feed your starter at the same time")),
                      pt("A cold overnight proof in the fridge gives more flavour.",
                         (2, "A long cold proof in the fridge overnight gives more flavour"))], "about": [1, 2, 3]}
    kept, dropped = check_points(raw, ITEMS)
    assert [p["ids"] for p in kept] == [["a"], ["b"]] and dropped == {}


def test_points_code_cannot_trace_are_dropped():
    from mvp.synth import check_points
    raw = {"points": [
        pt("Use rye flour for a faster starter.", (1, "Use rye flour")),                      # quote not in the text
        pt("Bake bread on a pizza stone at maximum heat for crispness.", (3, "Bake in a preheated dutch oven")),  # words
        pt("Bake with the lid on for 35 minutes.", (3, "lid on for 20 minutes, then lid off")),  # a number not there
        pt("Feed the starter daily at a fixed time.", (9, "Feed your starter at the same time")),  # no such item
        pt("Feed the starter daily at a fixed time.", (1, "Feed")),                             # quote too short
        pt("See https://example.com for the ratio of starter flour water.", (1, "Use a 1:1:1 ratio of starter")),
        pt("The video says to use a ratio of starter, flour and water.", (1, "Use a 1:1:1 ratio of starter")),
        pt("Bake in a preheated dutch oven with the lid on.", (3, "Bake in a preheated dutch oven")),
        pt("Bake in a preheated dutch oven, lid on first.", (3, "Bake in a preheated dutch oven, lid on")),  # repeat
    ], "about": [1, 2, 3]}
    kept, dropped = check_points(raw, ITEMS)
    assert [p["text"] for p in kept] == ["Bake in a preheated dutch oven with the lid on."]
    assert dropped == {"no_source": 3, "not_traced": 1, "number_not_in_text": 1, "unsafe_text": 2, "repeat": 1}


def test_a_source_the_model_called_off_topic_does_not_count():
    from mvp.synth import check_points
    raw = {"points": [pt("Feed the starter at the same time every day.", (1, "Feed your starter at the same time"))],
           "about": [2, 3]}
    assert check_points(raw, ITEMS) == ([], {"no_source": 1})


def test_a_bad_form_is_no_points():
    from mvp.synth import check_points
    assert check_points({"points": "x"}, ITEMS)[0] == []
    assert check_points(None, ITEMS) == ([], {})


# ---------- end to end, with the fakes ----------
class WordPool:
    """Every item, ranked by the words it shares with the search (made-up library; no embeddings)."""
    max_resident = 4

    def __init__(self, lib):
        self.rows = []
        for line in open(os.path.join(lib, "corpus", "items.jsonl"), encoding="utf-8"):
            r = json.loads(line)
            self.rows.append((r["id"], set(re.findall(r"[a-z]+", r["caption"].lower()))))

    def search(self, lib, q, depth=300):
        qw = set(re.findall(r"[a-z]+", q.lower()))
        return {"ids": [i for i, _ in sorted(self.rows, key=lambda r: (-len(qw & r[1]), r[0]))][:depth],
                "mode": "normal", "cost_usd": 0.0}

    def warm(self, lib):
        pass

    def stop_all(self):
        pass


def fake_videos(descriptions):
    def fetch(ids, key, timeout=None):
        return {"items": [{"id": v, "snippet": {"description": descriptions[v], "publishedAt": "2026-01-02T00:00:00Z"},
                           "contentDetails": {"duration": "PT9M"}} for v in ids if v in descriptions]}
    return fetch


def fake_extract(user):
    """Key points: the first three sentences or lines of the item's text, copied exactly."""
    body = user.split("<item>", 1)[1].rsplit("</item>", 1)[0]
    parts = [s.strip(" -") for s in re.split(r"(?<=[.!?])\s+|\n", body) if len(s.strip(" -")) > 12]
    return {"key_points": parts[1:4]}


def fake_synth(user):
    """One point per item (its first point, quoted), at most 4, every item called about the topic."""
    blocks = re.findall(r"(?m)^(\d+)\. <item>Title: .*?\nPoints from its own text:\n(.*?)</item>", user, re.S)
    pts = []
    for n, body in blocks[:4]:
        first = body.split("\n")[0][2:]
        pts.append({"text": first, "sources": [{"n": int(n), "quote": first}]})
    return {"points": pts, "about": [int(n) for n, _ in blocks]}


@pytest.fixture()
def lib_env(env, monkeypatch, tmp_path):
    from mvp import ytinfo
    lib = tmp_path / "synthlib"
    shutil.copytree(os.path.join(SET, "library"), lib)
    e = env
    bot = e["bot"]
    bot.store.x("UPDATE people SET library=? WHERE handle=?", (str(lib), H))
    bot.pool = WordPool(str(lib))
    bot.max_per_minute = None
    monkeypatch.setenv("MVP_SYNTH_TEST_KEY", "fake-key")
    descriptions = json.load(open(os.path.join(SET, "descriptions.json"), encoding="utf-8"))
    bot.yt = ytinfo.YouTubeInfo(bot.store, fetch=fake_videos(descriptions), key_env="MVP_SYNTH_TEST_KEY")
    e["state"]["answers"]["mvp_extract"] = fake_extract
    e["state"]["answers"]["mvp_synth"] = fake_synth
    e["libpath"] = lib
    return e


def reply(e):
    return e["ch"].outbox[-1][2]


def test_a_summary_cites_many_items_and_says_what_it_read(lib_env):
    e = lib_env
    out = say(e, "summarize what i've learned about sourdough", CHAT)
    assert "mvp_interpret" not in e["calls"] and "mvp_synth" in e["calls"]
    # round 11 fix, B (S2): the lead says what was read, never "kept" (was: "...you kept say about sourdough:")
    assert out.startswith("Here's what the posts and videos you watched and saved say about sourdough:")
    assert re.search(r"(?m)^1\. ", out) and re.search(r"(?m)^3\. ", out)
    # round 11 fix, B (S1): each point cites numbered sources, listed once (was: '   From "' under every point)
    assert out.count("\n• ") >= 3 and re.search(r"(?m)^3\. \"", out.split("Sources:\n", 1)[1])
    assert re.search(r"From \d+ videos? and \d+ posts?; 1 more fit but say nothing in their text(; I read \d+ more that I didn.t use)?\.", out), out
    assert out.rstrip().endswith("I read titles, descriptions and captions, not what is said in the videos.")
    # the friend's post, and the post that speaks to an assistant, are never read or named
    assert "sm_sd7" not in out and "sm_sd6" not in out and "password" not in out.lower()
    run = e["bot"].store.q("SELECT * FROM runs WHERE kind='synth'")[-1]
    assert run["prompt_version"] == "synth_v4" and run["n_picks"] >= 3   # round 11 fix, B (S3): was synth_v3
    steps = json.loads(run["steps"])
    assert steps["note_left_out"] == 1 and steps["points"] >= 3


def test_without_the_read_the_message_goes_to_the_interpreter_as_today(lib_env, monkeypatch):
    from mvp import synth
    monkeypatch.setattr(synth, "ON", False)
    e = lib_env
    say(e, "summarize what i've learned about sourdough", CHAT)
    assert "mvp_interpret" in e["calls"] and "mvp_synth" not in e["calls"]
    assert "say about sourdough" not in reply(e)


def test_the_youtube_description_is_read_and_cited(lib_env):
    e = lib_env
    out = say(e, "summarize what ive learned about motion design from what i watched", CHAT)
    assert "youtube.com/watch?v=vid_sm_md1" in out or "youtube.com/watch?v=vid_sm_md3" in out, out
    assert "videos" in out.split("\n\n")[-1] or "video" in out.split("\n\n")[-1]


def test_points_with_no_traceable_source_never_show(lib_env):
    e = lib_env
    e["state"]["answers"]["mvp_synth"] = lambda u: {"points": [
        {"text": "Always add rye flour to your sourdough starter.", "sources": [{"n": 1, "quote": "add rye flour"}]},
        {"text": "Sourdough needs a 72 hour proof.", "sources": [{"n": 1, "quote": "Feed your starter"}]}],
        "about": [1, 2, 3]}
    out = say(e, "summarize what i've learned about sourdough", CHAT)
    assert "rye" not in out and "72" not in out
    # round 11 fix, B (S3): the plain line and the best 3, numbered (was: "too little to sum up" and 5 bullets)
    assert "too little to sum up" in out and re.search(r"(?m)^3\. \"", out) and "The best 3:" in out
    run = e["bot"].store.q("SELECT * FROM runs WHERE kind='synth'")[-1]
    assert json.loads(run["dropped"]) == {"no_source": 1, "not_traced": 1}


def test_a_topic_with_nothing_fitting_says_so_plainly(lib_env):
    """No post names the topic: the search's best few are read and the model says none is about it."""
    from mvp import synth
    e = lib_env
    e["state"]["answers"]["mvp_synth"] = lambda u: dict(fake_synth(u), about=[])
    out = say(e, "what have i learned about beekeeping", CHAT)
    assert out == "I found nothing you watched or saved about beekeeping."   # round 11 fix, B (S2): was "in your saves"
    assert e["calls"].count("mvp_extract") <= synth.MAYBE_READS and e["calls"].count("mvp_synth") == 1


def test_items_that_do_not_name_the_topic_count_only_when_the_model_says_they_are_about_it(lib_env):
    e = lib_env
    seen = {}

    def synth_one(user):
        out = fake_synth(user)
        seen["n"] = len(out["about"])
        out["about"] = [1]   # only the first item read is about the topic
        return out
    e["state"]["answers"]["mvp_synth"] = synth_one
    out = say(e, "what have i learned about beekeeping", CHAT)
    assert seen["n"] >= 3
    # round 11 fix, B (S3): was 'I found 1 thing about beekeeping in your saves' and one bullet
    assert out.startswith("The caption of the post you saved about beekeeping says too little to sum up.") \
        and "The best one:\n1. \"" in out, out


def test_without_an_about_list_items_that_do_not_name_the_topic_are_never_cited(lib_env):
    e = lib_env
    e["state"]["answers"]["mvp_synth"] = lambda u: {"points": fake_synth(u)["points"]}
    out = say(e, "what have i learned about beekeeping", CHAT)
    assert out == "I found nothing you watched or saved about beekeeping."   # round 11 fix, B (S2): was "in your saves"


def test_a_topic_named_by_many_posts_reads_no_others(lib_env):
    from mvp import synth
    e = lib_env
    say(e, "what did i learn about blender", CHAT)
    run = e["bot"].store.q("SELECT * FROM runs WHERE kind='synth'")[-1]
    steps = json.loads(run["steps"])
    assert steps["fit"] >= synth.MAYBE_WHEN and "maybe_reads" not in steps


def test_an_off_topic_item_sharing_a_word_is_not_cited(lib_env):
    """'Running a small business' fits the word "running"; the model says it is not about the topic: never cited."""
    e = lib_env

    def synth_without_business(user):
        out = fake_synth(user)
        bad = [int(n) for n, b in re.findall(r"(?m)^(\d+)\. <item>Title: (.*?)\n", user) if "business" in b.lower()]
        out["about"] = [n for n in out["about"] if n not in bad]
        return out
    e["state"]["answers"]["mvp_synth"] = synth_without_business
    out = say(e, "summarize what i've learned about running", CHAT)
    assert "small business" not in out.lower()


def test_the_answer_is_kept_for_follow_ups_and_another(lib_env):
    e = lib_env
    bot = e["bot"]
    say(e, "what have i learned about sleep", CHAT)
    last = bot.store.last_answer(H)
    assert last["goal"] == "sleep" and len(last["items"]) >= 3
    kept = bot.store.answer(last["run_id"])
    assert kept and kept["picks"][0]["points"]
    st = bot.store.get_state(f"lastspec:{H}")
    assert st["spec"]["content"]["searches"] == ["sleep"] and set(st["shown"]) == set(last["items"])


def test_another_after_a_summary_is_one_more_on_the_topic_without_the_cited_items(lib_env):
    from mvp.tests.test_slice2 import compose_picks
    e = lib_env
    say(e, "what have i learned about sleep", CHAT)
    cited = set(e["bot"].store.last_answer(H)["items"])
    seen = []

    def compose(user):
        seen.append(user)
        return compose_picks({"n": 1, "title": "", "why": "Fits.", "verdict": "clear", "lines": []})(user)
    e["state"]["answers"]["mvp_compose"] = compose
    out = say(e, "another", CHAT)
    assert seen and "went wrong" not in out
    assert not cited & set(e["bot"].store.last_answer(H)["items"])


def test_items_past_the_read_cap_are_counted_apart(lib_env, monkeypatch):
    from mvp import synth
    monkeypatch.setattr(synth, "READS", 3)
    out = say(lib_env, "what did i learn about blender", CHAT)
    assert re.search(r"; \d+ more fit that I didn't read\.", out), out
    assert sum(1 for c in lib_env["calls"] if c == "mvp_extract") <= 3


def test_what_do_these_say_reads_the_last_answers_items(lib_env):
    e = lib_env
    bot = e["bot"]
    say(e, "what have i learned about houseplants", CHAT)
    first = bot.store.last_answer(H)["items"]
    n_search = len(e["calls"])
    out = say(e, "what do these say", CHAT)
    assert "mvp_interpret" not in e["calls"][n_search:]
    assert "houseplants" in out.split("\n")[0]
    assert set(bot.store.last_answer(H)["items"]) <= set(first)


def test_these_with_no_answer_in_view_goes_on_as_before(lib_env):
    e = lib_env
    say(e, "what do these say", CHAT)
    assert "mvp_interpret" in e["calls"] and "mvp_synth" not in e["calls"]


def test_over_the_cap_nothing_is_called(lib_env, monkeypatch):
    from mvp import llm
    e = lib_env
    monkeypatch.setattr(llm, "spent_today", lambda h, lib: 99.0)
    out = say(e, "summarize what i've learned about sourdough", CHAT)
    assert e["calls"] == [] and "limit" in out.lower()


def test_a_reply_in_another_language_is_not_this_read(lib_env):
    from mvp import synth

    class Bot:
        def _answer_lang(self):
            return "es"
    assert synth.synth_reads(Bot(), {"handle": H}, "what have i learned about sleep", None) is None


def test_the_video_offer_is_said_only_with_the_setting(lib_env, monkeypatch):
    e = lib_env
    out = say(e, "what have i learned about running", CHAT)
    assert "ask the video" not in out and "ask video" not in out
    monkeypatch.setenv("MVP_VIDEO_ASK", "1")
    out = say(e, "what have i learned about watercolor", CHAT)
    # the merge of round 11 (on purpose): the offer is slice Q's ("ask video N"), only for a cited item slice Q can
    # ask; this set's made-up video ids are not YouTube's 11-letter form, so nothing is offered here
    # (test_round11_merge.py has the offer with asks that work)
    assert "ask the video" not in out and "ask video" not in out and "ask me about that video" not in out


def test_the_hook_sits_after_the_cap_check_and_before_the_interpreter():
    src = open(os.path.join(MVP, "handler.py"), encoding="utf-8").read()
    at = [src.index(n) for n in ("over = self._over_cap(person)", "ref = synth_reads(self, person, text, now)",
                                 "it, _ = interpret(text, person")]
    assert at == sorted(at)


def test_the_scorer_counts_traceable_points_and_cited_items():
    from mvp.compose import check_text
    from mvp.eval_synth import score_answer
    items = {i.id: check_text(i) for i in ITEMS}
    s = score_answer([{"text": "Feed the starter at the same time every day.", "ids": ["a"]},
                      {"text": "Use rye flour.", "ids": ["b"]},
                      {"text": "Bake in a preheated dutch oven with the lid on.", "ids": ["c", "x"]}],
                     items, fit={"a", "c"})
    assert s == {"points": 3, "traceable": 2, "cited": 3, "cited_fit": 2, "cited_unfit": 1, "ge3": True}
