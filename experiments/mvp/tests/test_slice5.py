"""Offline tests for slice 5 (DESIGN.md section 11 "Outside picks" and "Keeping the library fresh"): the YouTube block
with a fake HTTP layer (the block, the sensitive-topic stop, the limits, the cache, removal of library items, no key),
and the inbox, import, switch, cap, new_items rules, library_status and the export routine with a synthetic export
(the demo's fixtures) and a fake library build. No network, no real data, no model calls."""
import json
import os
import shutil
import sqlite3
import sys
import urllib.error
import urllib.request
import zipfile
from urllib.parse import quote
from datetime import datetime, timedelta, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, EXP)

from mvp.tests.test_mvp import compose_picks, env, last, pasta_spec  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice2 import H, ask_pasta, lemon_pick, say  # noqa: E402

UTC = timezone.utc
FIX_IG = os.path.join(EXP, "demo", "fixtures", "ig_export_json")
FIX_YT = os.path.join(EXP, "youtube", "fixtures", "takeout_current")
KEY = "test-key-not-real"


# ---------- a fake YouTube API ----------
def video(vid, title, channel="Chan", dur="PT9M40S", public=True, embeddable=True, kids=False, live="none",
          blocked=None):
    v = {"id": vid, "snippet": {"title": title, "channelTitle": channel, "liveBroadcastContent": live},
         "status": {"privacyStatus": "public" if public else "private", "embeddable": embeddable, "madeForKids": kids},
         "contentDetails": {"duration": dur}}
    if blocked:
        v["contentDetails"]["regionRestriction"] = {"blocked": blocked}
    return v


class FakeYouTube:
    """search.list returns `order`; videos.list returns the `videos` it knows (others are simply left out)."""

    def __init__(self, order, videos, fail=False):
        self.order, self.videos, self.fail = order, {v["id"]: v for v in videos}, fail
        self.calls = []

    def __call__(self, url, params, key, timeout=None):
        self.calls.append((url.rsplit("/", 1)[-1], dict(params), key))
        if self.fail:
            raise OSError("quota")
        if url.endswith("/search"):
            return {"items": [{"id": {"kind": "youtube#video", "videoId": v}} for v in self.order]}
        ids = params["id"].split(",")
        return {"items": [self.videos[i] for i in ids if i in self.videos]}

    def searches(self):
        return [c for c in self.calls if c[0] == "search"]


def standard_fake():
    order = ["VIDaaaaaa01", "LIBVID00001", "VIDaaaaaa02", "VIDprivate1", "VIDkids0001", "VIDlive0001",
             "VIDblocked1", "VIDaaaaaa03", "VIDaaaaaa04"]
    vids = [video("VIDaaaaaa01", "One Pot Chicken & Rice (Easy!)", "Cook &amp; Co", "PT9M40S"),
            video("LIBVID00001", "Already Saved", "Chan"),
            video("VIDaaaaaa02", "Lemon Pasta in 15 Minutes", "Pasta Place", "PT15M"),
            video("VIDprivate1", "Private", public=False),
            video("VIDkids0001", "For kids", kids=True),
            video("VIDlive0001", "Live now", live="live", dur="P0D"),
            video("VIDblocked1", "Blocked", blocked=["US"]),
            video("VIDaaaaaa03", "Garlic Butter Pasta", "Third", "PT1H5M"),
            video("VIDaaaaaa04", "Fourth one", "Fourth", "PT3M")]
    return FakeYouTube(order, vids)


@pytest.fixture()
def yt(env, monkeypatch):
    """The env bot with a YouTube key set (a fake value) and a fake HTTP layer; its library holds one YouTube video
    (LIBVID00001) so removal of library items can be checked."""
    lib = env["lib"]
    with open(lib / "corpus" / "items.jsonl", "a") as f:
        f.write(json.dumps({"id": "itm_y", "platform": "youtube", "source_url": "https://www.youtube.com/watch?v=LIBVID00001",
                            "caption": "Already saved video", "interaction_kinds": ["like"],
                            "platform_data": {"video_id": "LIBVID00001", "owner_relation": "none"}}) + "\n")
    monkeypatch.setenv("YOUTUBE_API_KEY", KEY)
    fake = standard_fake()
    from mvp import outside as _outside
    # this fake returns the same videos for every search; the topic check on results (fix pass 3, finding 67 d) has its
    # own tests in test_fixpass3.py, which switch it back on
    monkeypatch.setattr(_outside, "shares_topic", lambda video, topic: True)
    from mvp.outside import Outside
    env["bot"].outside = Outside(env["bot"].store, http=fake)
    from mvp import ytinfo   # the library candidates' own videos.list (slice 3) stays offline too
    monkeypatch.setattr(ytinfo, "fetch_batch", lambda ids, key, timeout=None: {"items": []})
    env["yt"] = fake
    bot, replies = env["bot"], []
    orig = bot.send

    def send(handle, text, run_id=None):   # the reply as the bot made it (its parts), before the channel joins it
        replies.append(text)
        return orig(handle, text, run_id)
    bot.send = send
    env["replies"] = replies
    return env


def outside_ask(text_spec=None, outside="some", **content):
    a = ask_pasta()
    a["spec"]["content"]["outside"] = outside
    a["spec"]["content"].update(content)
    return a


def parts_of(env):
    return env["ch"].outbox[-1][2]


# ---------- the search words ----------
def test_query_words_are_the_persons_own_words_only():
    from mvp.outside import query_words, search_text, sensitive_topic
    from mvp.schema import RuleSpec
    spec = RuleSpec.model_validate({"when": {"type": "now"}, "content": {
        "goal": "quick chicken rice dinners like @chef_anna makes", "searches": ["one pot chicken rice recipe",
                                                                                 "Anna's Kitchen chicken"],
        "creators": ["anna"], "avoid": ["cream"], "outside": "some"}})
    msg = "Find me chicken and rice recipes, one pot, no cream, and some new ones from outside my saves @chef_anna"
    words = query_words(spec, [msg])
    assert words == ["pot", "chicken", "rice"]          # "one" is a function word; spec order; own spelling
    # fix pass 3, finding 67: words that only say the kind are not topic words; code adds one fixed kind word
    assert search_text(spec, [msg]) == "pot chicken rice recipe"
    # a word the model added ("dinners", "kitchen") is not in the message: never sent; nor the creator or avoided word
    spec2 = RuleSpec.model_validate({"when": {"type": "now"}, "content": {
        "goal": "cozy dinners", "searches": ["Sam birthday party ideas 555-123-4567 sam@x.co"], "outside": "some"}})
    assert search_text(spec2, ["ideas for a cozy dinner, new ones please"]) == "cozy dinner recipe"
    assert search_text(spec2, ["something new"]) is None
    assert sensitive_topic(["workouts for my anxiety"]) == "health"
    assert sensitive_topic(["date night with my girlfriend"]) == "relationships"
    assert sensitive_topic(["how to invest in crypto"]) == "money"
    assert sensitive_topic(["healthy pasta with chicken stock"]) is None   # ordinary food words are not personal
    assert sensitive_topic(["pain au chocolat", "budget meals"]) is None


# ---------- the block ----------
def test_outside_block_after_the_library_picks_with_youtube_titles_as_returned(yt):
    bot, fake = yt["bot"], yt["yt"]
    yt["state"]["answers"]["mvp_compose"] = lemon_pick()
    msg = say(yt, "pasta recipes, and show me a few new ones from outside my saves", outside_ask())
    text = str(msg)
    assert text.index("I recommend Lemon garlic pasta") < text.index("Not from your saves, but close to them:")
    # YouTube's order, the first 3 that pass, the library's own video removed; titles and channels exactly as returned
    assert "• One Pot Chicken & Rice (Easy!) by Cook &amp; Co (9 minutes 40 seconds), on YouTube" in text
    assert "• Lemon Pasta in 15 Minutes by Pasta Place (15 minutes), on YouTube" in text
    assert "• Garlic Butter Pasta by Third (1 hour 5 minutes), on YouTube" in text
    assert "Already Saved" not in text and "Fourth one" not in text
    for gone in ("Private", "For kids", "Live now", "Blocked"):
        assert gone not in text
    links = [p for p in yt["replies"][-1].parts if p["type"] == "link" and p.get("outside")]
    assert [p["video_id"] for p in links] == ["VIDaaaaaa01", "VIDaaaaaa02", "VIDaaaaaa03"]
    assert links[0]["url"] == "https://www.youtube.com/watch?v=VIDaaaaaa01" and links[0]["platform"] == "youtube"
    # one search, one check; the key only in the header argument; the words only the person's own
    (_, params, key), = fake.searches()
    assert key == KEY and KEY not in json.dumps(params) and params["q"] == "pasta recipe"   # finding 67: code's kind word
    assert params["safeSearch"] == "strict" and params["videoEmbeddable"] == "true" and params["type"] == "video"
    assert [c[0] for c in fake.calls] == ["search", "videos"]
    # no model read them: the compose prompt never holds an outside title; nothing became a delivery or the last answer
    assert all("One Pot Chicken" not in str(x) for x in yt["state"].get("last_compose", {}).values())
    items = [d["item_id"] for d in bot.store.q("SELECT item_id FROM deliveries")]
    assert items == ["itm_a"] and bot.store.last_answer(H)["items"] == ["itm_a"]
    run = bot.store.one("SELECT steps FROM runs WHERE kind='ask' ORDER BY id DESC LIMIT 1")
    assert json.loads(run["steps"])["outside"] == {"status": "shown", "shown": 3, "searched": True, "cached": False}
    # the kept answer (for email, sending again) holds no outside block
    kept = bot.store.answer(bot.store.last_answer(H)["run_id"])
    assert "Not from your saves" not in json.dumps(kept["parts"])


def test_outside_only_shows_just_the_block_and_no_model_or_delivery(yt):
    bot = yt["bot"]
    n_compose = sum(1 for c in yt["calls"] if c == "mvp_compose")
    msg = say(yt, "only new pasta stuff, not from my saves", outside_ask(outside="only"))
    assert str(msg).startswith("Here are some new ")   # fix pass 5, finding 85: an opening line that fits
    assert "from YouTube, not from your saves:\n• One Pot Chicken & Rice" in str(msg)
    assert sum(1 for c in yt["calls"] if c == "mvp_compose") == n_compose      # no library search, no model
    assert not bot.store.q("SELECT * FROM deliveries") and bot.store.last_answer(H) is None
    assert say(yt, "👎", {"intent": "chat"}) == "Thanks! Nothing to attach that to yet."   # feedback never lands on them
    # "another" repeats the request without the videos already shown (the 4th passes the checks)
    msg = say(yt, "another", {"intent": "more"})
    assert "Fourth one" in str(msg) and "One Pot Chicken" not in str(msg)
    assert len(yt["yt"].searches()) == 1                                         # the cached search was reused


def test_sensitive_topic_no_key_off_and_instagram_only_say_so_in_one_line(yt, monkeypatch):
    fake = yt["yt"]
    yt["state"]["answers"]["mvp_compose"] = lemon_pick()
    a = outside_ask()
    a["spec"]["content"]["goal"] = "pasta for my anxiety"
    msg = str(say(yt, "pasta that helps my anxiety, and some new ones", a))
    assert msg.endswith("\n\nI didn't look for new things on YouTube for this: I keep personal topics like health, "
                        "money and relationships to your own saves.")
    assert "I recommend Lemon garlic pasta" in msg and not fake.calls           # nothing was sent to YouTube
    only = outside_ask(outside="only")
    assert say(yt, "only new stuff about my divorce", only) == (
        "I didn't look for new things on YouTube for this: I keep personal topics like health, money and "
        "relationships to your own saves. Ask without \"new\" and I'll look in your own saves.")
    ig = outside_ask(platforms=["instagram"])
    assert str(say(yt, "new pasta reels", ig)).endswith("I can only look for new things on YouTube, not on Instagram.")
    monkeypatch.delenv("YOUTUBE_API_KEY")
    assert str(say(yt, "new pasta recipes", outside_ask())).endswith(
        "I can't look for new things outside your saves right now.")
    monkeypatch.setenv("YOUTUBE_API_KEY", KEY)
    from mvp import config
    monkeypatch.setattr(config, "OUTSIDE_ON", False)                            # MVP_OUTSIDE=0
    assert str(say(yt, "new pasta recipes", outside_ask())).endswith(
        "I can't look for new things outside your saves right now.")
    assert not fake.calls
    monkeypatch.setattr(config, "OUTSIDE_ON", True)
    yt["bot"].store.set_state(f"lastspec:{H}", None)   # after an answer this is "more" with its topic (finding 27)
    assert say(yt, "only new stuff, not from my saves", outside_ask(outside="only")) == \
        "Tell me what kind of thing you want, and I'll look for new ones on YouTube."
    assert not fake.calls


def test_limits_per_person_and_for_everyone_and_the_cache(yt):
    bot, fake, clock = yt["bot"], yt["yt"], yt["clock"]
    from mvp import config
    yt["state"]["answers"]["mvp_compose"] = lemon_pick()
    words = ["pasta", "noodles", "spaghetti", "penne", "lasagna"]
    for w in words:                                                              # 5 different searches
        spec = outside_ask(goal=f"a {w} recipe", searches=[f"{w} recipe"])
        assert "Not from your saves" in str(say(yt, f"new {w} recipe", spec))
    assert len(fake.searches()) == 5
    spec = outside_ask(goal="a ravioli recipe", searches=["ravioli recipe"])
    assert str(say(yt, "new ravioli recipe", spec)).endswith(
        "You've had today's 5 searches for new things on YouTube. Ask me again tomorrow.")
    assert len(fake.searches()) == 5
    # a search made before is served from the cache without counting
    spec = outside_ask(goal="a pasta recipe", searches=["pasta recipe"])
    assert "Not from your saves" in str(say(yt, "new pasta recipe", spec)) and len(fake.searches()) == 5
    # after 24 hours the cached results are dropped; a new Pacific day has a fresh count (the real day, never the
    # bot's clock: review fix X10; here the day's rows are moved to yesterday)
    clock[0] += timedelta(hours=25)
    bot.store.x("UPDATE outside_searches SET day='2000-01-01'")
    assert "Not from your saves" in str(say(yt, "new pasta recipe", spec)) and len(fake.searches()) == 6
    assert bot.store.one("SELECT COUNT(*) n FROM outside_cache")["n"] == 1
    # everyone's daily total: 80
    day = bot.outside._day(clock[0])
    for _ in range(config.OUTSIDE_PER_DAY - 1):
        bot.store.x("INSERT INTO outside_searches(handle,day,at,status) VALUES('someone',?,'x','ok')", (day,))
    spec = outside_ask(goal="a gnocchi recipe", searches=["gnocchi recipe"])
    assert str(say(yt, "new gnocchi recipe", spec)).endswith(
        "I've used up today's searches for new things on YouTube. Ask me again tomorrow.")
    assert len(fake.searches()) == 6


def test_a_failed_search_and_nothing_new_say_so(yt):
    bot = yt["bot"]
    from mvp.outside import Outside
    yt["state"]["answers"]["mvp_compose"] = lemon_pick()
    bot.outside = Outside(bot.store, http=FakeYouTube([], [], fail=True))
    assert str(say(yt, "new pasta recipes", outside_ask())).endswith(
        "I couldn't reach YouTube just now, so I couldn't look for new things.")
    assert bot.store.one("SELECT status FROM outside_searches")["status"] == "error:OSError"   # it used quota
    bot.outside = Outside(bot.store, http=FakeYouTube(["LIBVID00001"], [video("LIBVID00001", "Already Saved")]))
    spec = outside_ask(goal="a penne recipe", searches=["penne recipe"])
    assert str(say(yt, "new penne recipe", spec)).endswith(
        "I didn't find anything new on YouTube for this that isn't already in your saves.")


def test_a_rule_does_not_show_the_same_outside_video_twice(yt):
    bot, clock = yt["bot"], yt["clock"]
    yt["state"]["answers"]["mvp_compose"] = lambda u: {"picks": [{"n": 1, "title": "Pasta", "why": "Fits.",
                                                                  "verdict": "clear"}]}
    spec = pasta_spec({"type": "schedule", "days": ["FRI"], "time": "19:00"})
    spec["content"]["outside"] = "some"
    say(yt, "a pasta recipe every friday at 7pm, plus some new ones", {"intent": "new_rule", "spec": spec})
    preview = [p["video_id"] for p in yt["replies"][-1].parts if p.get("outside")]
    say(yt, "yes", {"intent": "confirm"})
    rule = bot.store.rules(H)[0]
    clock[0] = datetime.fromisoformat(rule["next_run_at"]) + timedelta(minutes=1)
    assert bot.tick() == 1
    one = [p["video_id"] for p in yt["replies"][-1].parts if p.get("outside")]
    # fix pass, finding 33: the preview's videos count as shown by the rule, so its first send has only new ones
    assert preview == ["VIDaaaaaa01", "VIDaaaaaa02", "VIDaaaaaa03"] and one == ["VIDaaaaaa04"]


# ---------- keeping the library fresh ----------
def zip_dir(src, path):
    with zipfile.ZipFile(path, "w") as z:
        for root, _, files in os.walk(src):
            for f in files:
                full = os.path.join(root, f)
                z.write(full, os.path.relpath(full, src))
    return path


def fake_prepare(cost=0.0123, ok=True):
    def prep(lib, cap):
        assert cap == 1.50
        with open(os.path.join(lib, "ai_runs.jsonl"), "a") as f:
            f.write(json.dumps({"at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), "provider": "openai",
                                "purpose": "demo_item_vectors_3l", "cost_usd": cost}) + "\n")
        with open(os.path.join(lib, "prepare_status.json"), "w") as f:
            json.dump({"state": "done" if ok else "error"}, f)
        return {"ok": ok, "message": "" if ok else "budget stop"}
    return prep


@pytest.fixture()
def fresh(env, tmp_path):
    """The env bot with a router file in its old library (so nothing is copied from real data) and a Refresher that
    runs in the test's thread with a fake library build."""
    (env["lib"] / "r7").mkdir()
    (env["lib"] / "r7" / "router.npz").write_bytes(b"synthetic")
    from mvp.refresh import Refresher, inbox_dir
    from mvp import config
    config.INBOX_PARTS_MINUTES = 0   # a Takeout in parts waits for its last part: test_fixpass.py
    env["bot"].refresher = Refresher(env["bot"], prepare=fake_prepare(), background=False, settle_seconds=0)
    env["inbox"] = inbox_dir(H)
    os.makedirs(env["inbox"])
    env["ig_zip"] = zip_dir(FIX_IG, str(tmp_path / "instagram-synthetic.zip"))
    env["yt_zip"] = zip_dir(FIX_YT, str(tmp_path / "takeout-synthetic-001.zip"))
    return env


def drop(env, *paths):
    for p in paths:
        shutil.copy(p, env["inbox"])


def test_upload_box_puts_the_file_in_the_persons_inbox(fresh):
    from mvp.channels.web import WebChannel
    ch = WebChannel(port=0)
    try:
        ch.attach(fresh["bot"])
        with open(fresh["ig_zip"], "rb") as f:
            data = f.read()
        req = urllib.request.Request(f"http://127.0.0.1:{ch.port}/api/upload?as={quote(H)}&name=../../my%20export.zip",
                                     data=data, headers={"X-Test-Token": ch.token}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            assert json.loads(r.read())["name"] == "my export.zip"
        path = os.path.join(fresh["inbox"], "my export.zip")
        with open(path, "rb") as f:
            assert f.read() == data and os.path.dirname(path) == fresh["inbox"]
        assert os.path.abspath(path) in fresh["bot"].refresher.ready and fresh["bot"].refresher.last_poll == 0.0
        bad = urllib.request.Request(f"http://127.0.0.1:{ch.port}/api/upload?as={quote(H)}&name=x.zip", data=b"x",
                                     method="POST")
        with pytest.raises(urllib.error.HTTPError):                              # the token is needed
            urllib.request.urlopen(bad, timeout=10)
        assert not [f for f in os.listdir(fresh["inbox"]) if f.endswith(".part")]
    finally:
        ch.close()


def test_a_synthetic_export_is_imported_and_the_library_switched(fresh, monkeypatch):
    bot, ch = fresh["bot"], fresh["ch"]
    from mvp import refresh
    seen = {}
    real = refresh.ingest.create_library

    def spy(root, name, ig_zips=(), yt_zips=(), own_names=(), router_from=()):
        seen["ig_names"] = [n for z in ig_zips for n in zipfile.ZipFile(z).namelist()]
        return real(root, name, ig_zips, yt_zips, own_names, router_from)
    monkeypatch.setattr(refresh.ingest, "create_library", spy)
    old = bot.store.person(H)["library"]
    drop(fresh, fresh["ig_zip"], fresh["yt_zip"])
    assert bot.refresher.poll(force=True) == 1
    new = bot.store.person(H)["library"]
    assert new != old and os.path.dirname(new) == os.path.dirname(old)          # beside the old one
    assert os.path.isfile(os.path.join(old, "corpus", "items.jsonl"))           # the old one is kept
    msg = last(ch)
    assert msg.startswith("Your new export is in: ") and "from Instagram" in msg and "from YouTube" in msg
    assert msg.endswith("and I'm using it from now on.")
    # nothing in the export's messages folder was read: the importer got only .json files outside it
    assert seen["ig_names"] and all("messages" not in n.split("/") and n.endswith(".json") for n in seen["ig_names"])
    corpus = open(os.path.join(new, "corpus", "items.jsonl")).read()
    assert "SYNTHreel007" not in corpus and "SYNTHETIC-DM-TEXT" not in corpus   # the share-only item never came in
    assert "SYNTHreel009" not in corpus                                          # nor the friend's post
    imp = bot.store.one("SELECT * FROM imports WHERE handle=?", (H,))
    assert imp["status"] == "done" and imp["cost_usd"] == 0.0123 and imp["library"] == new
    new_counts = json.loads(imp["new_counts"])
    assert msg.startswith(f"Your new export is in: {sum(new_counts.values())} new items")
    assert not [f for f in os.listdir(fresh["inbox"]) if not f.startswith(".")]   # the raw export is gone
    assert not os.path.exists(os.path.join(fresh["inbox"], ".working")) or \
        not os.listdir(os.path.join(fresh["inbox"], ".working"))
    # the build's cost is in the MVP ledger with the person (a hashed ref, review fix PRIV-5), and counted once
    from mvp import llm
    # this test's own ledger, never the real data/mvp one (ai.py is imported once per session; llm.py re-points it)
    assert llm.ai.LEDGER == os.path.join(llm.LEDGER_HOME, "ai_runs.jsonl")
    assert llm.LEDGER_HOME.startswith(str(fresh["lib"].parent))
    with open(llm.ai.LEDGER) as f:
        rows = [json.loads(line) for line in f if '"mvp_import"' in line]
    assert [(r["purpose"], r["person"], r["cost_usd"]) for r in rows] == [("mvp_import", llm.person_ref(H), 0.0123)]
    assert llm._lib_rows(new) == []
    # the search now reads the new library; a restart keeps it (people.json still names the old one)
    assert bot.view(new).get("itm_a") is None
    people = os.path.join(os.path.dirname(os.path.dirname(old)), "people.json")
    bot.load_people(people)
    assert bot.store.person(H)["library"] == new
    with open(people, "w") as f:   # a founder points people.json at another library: theirs wins
        json.dump({H: {"name": "T", "library": str(fresh["lib"]), "timezone": "America/New_York"}}, f)
    other = os.path.join(os.path.dirname(old), "other-lib")
    shutil.copytree(old, other)
    with open(people, "w") as f:
        json.dump({H: {"name": "T", "library": other, "timezone": "America/New_York"}}, f)
    bot.load_people(people)
    assert bot.store.person(H)["library"] == other


def test_a_failed_build_leaves_the_old_library_in_use(fresh):
    bot, ch = fresh["bot"], fresh["ch"]
    bot.refresher.prepare = fake_prepare(cost=0.004, ok=False)
    old = bot.store.person(H)["library"]
    before = set(os.listdir(os.path.dirname(old)))
    drop(fresh, fresh["ig_zip"])
    bot.refresher.poll(force=True)
    assert bot.store.person(H)["library"] == old
    assert last(ch) == ("Something went wrong while I was adding your new export, so I'm still using your library as "
                        "it was. The founders will look into it.")
    # the failed build was removed (the test's own ledger folder, beside the library here, is new: its spend is logged)
    assert set(os.listdir(os.path.dirname(old))) - {"ledger"} == before - {"ledger"}
    assert os.listdir(os.path.join(fresh["inbox"], ".failed"))                    # the file is kept for a founder
    imp = bot.store.one("SELECT * FROM imports")
    assert imp["status"] == "failed" and imp["cost_usd"] == 0.004                 # what it spent is still recorded


def test_the_cost_cap_and_files_that_are_not_exports(fresh, monkeypatch):
    bot, ch = fresh["bot"], fresh["ch"]
    from mvp import refresh
    lib = refresh.ingest.create_library(str(fresh["lib"].parent / "est"), "x", [fresh["ig_zip"]], [fresh["yt_zip"]])
    est = refresh.estimate_usd(lib)
    assert 0 < est < 0.01                                                         # a small export costs little
    called = []
    bot.refresher.estimate = lambda lib: 2.0
    bot.refresher.prepare = lambda lib, cap: called.append(lib)
    old = bot.store.person(H)["library"]
    drop(fresh, fresh["ig_zip"])
    bot.refresher.poll(force=True)
    assert last(ch) == ("Your new export is big: adding it would cost about $2.00, and I can only spend $1.50 on one "
                        "import. I'm still using your library as it was. The founders can raise the limit.")
    assert not called and bot.store.person(H)["library"] == old
    # not an export
    with open(os.path.join(fresh["inbox"], "holiday.zip"), "wb") as f:
        with zipfile.ZipFile(f, "w") as z:
            z.writestr("photos/a.txt", "x")
    with open(os.path.join(fresh["inbox"], "notes.txt"), "w") as f:
        f.write("hello")
    bot.refresher.poll(force=True)
    assert last(ch).startswith("I couldn't use the file you sent: it isn't an Instagram export (JSON)")
    # an Instagram export in HTML
    with zipfile.ZipFile(os.path.join(fresh["inbox"], "ig-html.zip"), "w") as z:
        z.writestr("your_instagram_activity/saved/saved_posts.html", "<html></html>")
    bot.refresher.poll(force=True)
    assert last(ch).startswith("Your Instagram export is in HTML format")
    # an Instagram export without followers and following
    no_f = str(fresh["lib"].parent / "nofollow.zip")
    with zipfile.ZipFile(fresh["ig_zip"]) as src, zipfile.ZipFile(no_f, "w") as z:
        for n in src.namelist():
            if "followers_and_following" not in n:
                z.writestr(n, src.read(n))
    drop(fresh, no_f)
    bot.refresher.poll(force=True)
    assert last(ch).startswith("Your Instagram export is missing \"Followers and following\"")
    assert bot.store.person(H)["library"] == old
    assert [r["status"] for r in bot.store.q("SELECT status FROM imports ORDER BY id")] == \
        ["too_costly", "refused", "refused", "refused"]


def test_a_file_still_being_copied_waits(fresh):
    bot = fresh["bot"]
    bot.refresher.settle = 3600
    drop(fresh, fresh["ig_zip"])
    assert bot.refresher.poll(force=True) == 0
    with open(os.path.join(fresh["inbox"], "upload.zip.part"), "w") as f:
        f.write("x")
    bot.refresher.settle = 0
    assert bot.refresher.waiting(H) == [os.path.join(fresh["inbox"], "instagram-synthetic.zip")]


def test_new_items_rules_run_once_on_the_new_items(fresh, monkeypatch, tmp_path):
    bot, ch, st = fresh["bot"], fresh["ch"], fresh["state"]
    from mvp import config
    from mvp.schema import RuleSpec
    monkeypatch.setattr(config, "IMPORTS_PER_DAY", 10)   # three builds in this test (review fix X2 limits them a day)
    for goal in ("a sourdough recipe", "a tiny house tour"):
        spec = RuleSpec.model_validate({"when": {"type": "new_items"}, "content": {"goal": goal, "searches": [goal]}})
        bot.store.add_rule(H, f"when I save {goal}", spec.stored(), "active", None)
    prompts = []

    def compose(user):
        prompts.append(user)
        return {"picks": [{"n": 1, "title": "A new pick", "why": "Fits.", "verdict": "clear"}]}
    st["answers"]["mvp_compose"] = compose

    class Pool:   # the new library's search: every id it holds, the old library's first
        max_resident = 4

        def search(self, lib, q, depth=300):
            ids = [json.loads(line)["id"] for line in open(os.path.join(lib, "corpus", "items.jsonl"))]
            return {"ids": ["itm_a", "itm_b"] + ids, "mode": "normal", "cost_usd": 0.0}

        def warm(self, lib):
            pass

        def stop_all(self):
            pass
    bot.pool = Pool()
    drop(fresh, fresh["ig_zip"])
    n_out = len(ch.outbox)
    bot.refresher.poll(force=True)
    sent = [m[2] for m in ch.outbox[n_out:]]
    assert sent[0].startswith("Your new export is in:") and "Nothing new matched" not in sent[0]
    assert len(sent) == 3 and all("I recommend " in str(m) and "SYNTH" in str(m) for m in sent[1:])
    assert sent[0] == ("Your new export is in: 5 new items (5 from Instagram). Your library now has 6 items, and I'm "
                       "using it from now on.")   # 5 Instagram items (the friend's and the DM-only one never come in)
    #                                               plus the old library's YouTube item, carried over
    assert len(prompts) == 2 and all("Lemon garlic pasta" not in p for p in prompts)   # only the new items
    runs = bot.store.q("SELECT status, rule_id FROM runs WHERE kind='scheduled' ORDER BY id")
    assert [r["status"] for r in runs] == ["sent", "sent"]
    new_ids = {d["item_id"] for d in bot.store.q("SELECT item_id FROM deliveries")}
    assert not new_ids & {"itm_a", "itm_b", "itm_c", "itm_e"}
    # an export with nothing new in it (the same items; review fix X2: the very same file is not built again):
    # nothing is new, and that is said once for both rules
    def again(k):
        src = tmp_path / f"ig-again-{k}"
        shutil.copytree(FIX_IG, src)
        (src / f"extra{k}.json").write_text("{}")
        return zip_dir(str(src), str(tmp_path / f"instagram-again-{k}.zip"))
    drop(fresh, again(1))
    n_out = len(ch.outbox)
    bot.refresher.poll(force=True)
    sent = [m[2] for m in ch.outbox[n_out:]]
    assert len(sent) == 1 and sent[0].startswith("Your new export is in, with nothing new in it.")
    assert sent[0].endswith("\nNothing new matched your rules \"a sourdough recipe\", \"a tiny house tour\".")
    assert len(prompts) == 2
    # a new_items rule whose end date has passed ends, and the message says so
    first = bot.store.rules(H)[0]
    spec = dict(first["spec"], when={"type": "new_items", "until": "2026-11-01"})
    bot.store.update_rule(first["id"], spec=spec)
    drop(fresh, again(2))
    bot.refresher.poll(force=True)
    assert last(ch).endswith("\nYour rule \"a sourdough recipe\" has ended: its end date has passed.")
    assert bot.store.rule(first["id"])["status"] == "done"


def test_library_status_counts_and_the_next_export(fresh):
    bot, clock = fresh["bot"], fresh["clock"]
    msg = say(fresh, "did my export come in?", {"intent": "library_status"})
    assert msg.splitlines()[:2] == ["I haven't added an export for you yet: your library is the one the founders set up.",
                                    "It has 4 items: 3 from Instagram and 1 from YouTube."]
    assert "The newest thing in it is from 1 March 2026" in msg
    assert "Your next Instagram export was due around" in msg
    assert msg.endswith("To export again: Instagram: https://accountscenter.instagram.com/info_and_permissions/dyi; "
                        "YouTube: https://takeout.google.com.")
    drop(fresh, fresh["ig_zip"], fresh["yt_zip"])
    bot.refresher.poll(force=True)
    imp = bot.store.one("SELECT * FROM imports WHERE status='done'")
    new = sum(json.loads(imp["new_counts"]).values())
    from mvp.refresh import kept_counts
    totals, _ = kept_counts(bot.store.person(H)["library"])
    clock[0] += timedelta(days=2)
    msg = say(fresh, "when did my library last update", {"intent": "library_status"})
    lines = msg.splitlines()
    assert lines[0] == f"Your last export came in on Thursday 12 November (2 days ago), with {new} new items."
    assert lines[1] == (f"It has {sum(totals.values())} items: {totals['instagram']} from Instagram and "
                        f"{totals['youtube']} from YouTube.")
    assert "Your next Instagram export is due around Thursday 10 December" in msg
    assert "your next YouTube export is due around Tuesday 12 January" in msg


def test_the_export_routine_and_its_reminders(fresh):
    bot, ch = fresh["bot"], fresh["ch"]
    from mvp.refresh import export_routine, offer_export_routine, routine_text
    for tester in (False, True):
        r = export_routine(tester=tester)
        text = routine_text(r).lower()
        assert "password" not in text and "log in" not in text and "sign in" not in text
        assert r["instagram"]["never"] == ["Messages"] and "Messages" not in r["instagram"]["tick"]
        assert "leave messages unticked" in text
        assert r["instagram"]["link"].startswith("https://accountscenter.instagram.com/")
        assert r["youtube"]["link"] == "https://takeout.google.com"
        assert "nobody types a command" in text and "isn't confirmed for us accounts" in text
    assert "upload box on the test page" in routine_text(export_routine())
    assert "google drive folder" in routine_text(export_routine(tester=True)).lower()
    msg = offer_export_routine(bot, H)
    # fix pass 2, findings 43 and 44: one line at setup, one line when the YES starts them, the steps with each send
    assert msg == ("I'll remind you when a fresh export is due (Instagram every 4 weeks, YouTube every 2 months) and "
                   "send the steps then. OK?")
    assert not bot.store.rules(H)                                                 # nothing starts before the yes
    n0 = len(ch.outbox)
    bot.on_message(H, "yes")
    rules = bot.store.rules(H)
    assert len(rules) == 2 and all(r["spec"]["content"]["source"] == "note" for r in rules)
    assert [m[2] for m in ch.outbox[n0:]] == ["Done. Next Instagram reminder 10 December, next YouTube one 12 January."]
    msg = say(fresh, "when is my next export due", {"intent": "library_status"})
    assert "Your next Instagram export is due Thursday 10 December, and I'll remind you" in msg
    # a platform it has no steps for is left out (both are offered) rather than failing
    assert "Instagram every 4 weeks" in offer_export_routine(bot, H, platforms=["tiktok"])


def test_old_stores_load_and_deleting_data_clears_the_new_tables(tmp_path):
    path = tmp_path / "old.sqlite"
    db = sqlite3.connect(path)
    db.executescript("CREATE TABLE people (handle TEXT PRIMARY KEY, name TEXT, library TEXT NOT NULL, timezone TEXT "
                     "NOT NULL, consent_version TEXT, consent_at TEXT, paused INTEGER DEFAULT 0, created_at TEXT);"
                     "INSERT INTO people(handle,library,timezone) VALUES('+1555','lib','UTC');")
    db.commit()
    db.close()
    from mvp.store import Store
    s = Store(str(path))
    assert s.person("+1555")["imported_from"] is None
    s.switch_library("+1555", "lib2")
    assert s.person("+1555")["library"] == "lib2" and s.person("+1555")["imported_from"] == "lib"
    s.x("INSERT INTO outside_searches(handle,day,at,status) VALUES('+1555','d','a','ok')")
    s.x("INSERT INTO imports(handle,status,work) VALUES('+1555','done',NULL)")
    s.delete_person_data("+1555")
    assert not s.q("SELECT * FROM outside_searches") and not s.q("SELECT * FROM imports")


def test_a_build_ledger_is_counted_once(tmp_path, monkeypatch):
    lib = tmp_path / "lib"
    lib.mkdir()
    rows = [{"at": "2026-11-12T10:00:00", "purpose": "demo_item_vectors_3l", "cost_usd": 0.5},
            {"at": "2026-11-12T10:00:00", "purpose": "demo_q8_search", "cost_usd": 0.01}]
    (lib / "ai_runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    from mvp import llm
    assert [r["cost_usd"] for r in llm._lib_rows(str(lib))] == [0.5, 0.01]      # a library the demo built: counted
    (lib / "library.json").write_text(json.dumps({"mvp_import": True}))
    assert [r["cost_usd"] for r in llm._lib_rows(str(lib))] == [0.01]           # built by an import: in the MVP ledger


# ---------- checker fixes (slice 5) ----------
def test_an_importer_crash_tells_the_person_and_keeps_the_file(fresh, monkeypatch):
    bot, ch = fresh["bot"], fresh["ch"]
    from mvp import refresh

    def boom(*a, **k):   # not a ValueError: an export the importer did not expect
        raise KeyError("x")
    monkeypatch.setattr(refresh.ingest, "create_library", boom)
    old = bot.store.person(H)["library"]
    drop(fresh, fresh["ig_zip"])
    bot.refresher.poll(force=True)
    assert bot.store.person(H)["library"] == old
    assert last(ch) == ("Something went wrong while I was adding your new export, so I'm still using your library as "
                        "it was. The founders will look into it.")
    assert os.listdir(os.path.join(fresh["inbox"], ".failed"))
    assert not os.listdir(os.path.join(fresh["inbox"], ".working"))
    imp = bot.store.one("SELECT status, error FROM imports")
    assert (imp["status"], imp["error"]) == ("failed", "KeyError")


def test_an_import_cut_off_by_a_stop_starts_again_after_the_restart(fresh):
    bot, ch = fresh["bot"], fresh["ch"]
    from mvp import refresh
    built = []

    def die(lib, cap):   # the process stops in the middle of the build
        built.append(lib)
        raise SystemExit("stopped")
    bot.refresher.prepare = die
    old = bot.store.person(H)["library"]
    drop(fresh, fresh["ig_zip"])
    with pytest.raises(SystemExit):
        bot.refresher.import_files(H, bot.refresher.waiting(H))
    assert bot.store.one("SELECT status FROM imports")["status"] == "running"
    assert os.path.isdir(built[0]) and bot.store.person(H)["library"] == old
    with open(os.path.join(built[0], "half-built.marker"), "w") as f:
        f.write("x")
    # restart: the half-built library is removed, the file goes back to the inbox and is imported again (the new
    # build may take the same folder name, so the marker shows the half-built one is gone)
    bot.refresher = refresh.Refresher(bot, prepare=fake_prepare(), background=False, settle_seconds=0)
    assert bot.refresher.poll(force=True) == 1
    assert not os.path.exists(os.path.join(built[0], "half-built.marker"))
    assert [r["status"] for r in bot.store.q("SELECT status FROM imports ORDER BY id")] == ["interrupted", "done"]
    assert bot.store.person(H)["library"] != old
    assert last(ch).startswith("Your new export is in: ")
    assert not os.listdir(os.path.join(fresh["inbox"], ".working"))


def test_two_people_with_one_inbox_folder_are_left_alone(fresh):
    bot = fresh["bot"]
    from mvp.refresh import inbox_dir, safe_filename
    for h in ("john.doe@example.com", "john_doe@example.com"):   # both map to john_doe_example_com
        bot.store.upsert_person(h, "x", str(fresh["lib"]), "UTC")
        bot.store.set_consent(h, "test")
    os.makedirs(inbox_dir("john.doe@example.com"), exist_ok=True)
    shutil.copy(fresh["ig_zip"], inbox_dir("john.doe@example.com"))
    assert bot.refresher.poll(force=True) == 0 and not bot.store.q("SELECT * FROM imports")
    from mvp.channels.web import WebChannel
    ch = WebChannel(port=0)
    ch.bot = bot
    with pytest.raises(ValueError):
        ch.upload("john_doe@example.com", "x.zip", None, 10)
    # a name the inbox check would skip (its own "." and "_" folders) is changed so the file is not stranded
    assert safe_filename("_my export.zip") == "my export.zip" and safe_filename(".x.zip") == "x.zip"


def test_the_daily_search_count_is_shared_and_survives_a_deletion(yt, tmp_path):
    bot = yt["bot"]
    from mvp.outside import Outside
    from mvp.store import Store
    yt["state"]["answers"]["mvp_compose"] = lemon_pick()
    for w in ("pasta", "noodles", "penne"):
        say(yt, f"new {w} recipe", outside_ask(goal=f"a {w} recipe", searches=[f"{w} recipe"]))
    now = yt["clock"][0]
    other = Outside(Store(str(tmp_path / "web.sqlite")), http=standard_fake())   # the test page's own store
    assert other.used_today(now) == 3 and other.used_today(now, H) == 0           # one quota, one key
    bot.store.delete_person_data(H)
    assert bot.outside.used_today(now) == 3                                       # not handed back by a deletion


def test_outside_only_with_an_email_says_it_was_not_emailed(yt):
    a = outside_ask(outside="only")
    a["spec"]["do"] = [{"action": "email.send"}, {"action": "todo.add"}]
    msg = str(say(yt, "email me only new pasta videos, not from my saves, and add them to my list", a))
    assert msg.startswith("Here are some new ") and "from YouTube, not from your saves:" in msg   # (finding 85)
    assert msg.endswith("\nNew finds from YouTube only come here in the chat, so I didn't email them or add them to "
                        "your list.")
    assert not yt["bot"].store.q("SELECT * FROM todos") and not yt["bot"].store.outbox(H)


def test_an_emailed_answer_still_shows_the_outside_block_in_the_thread(yt):
    bot, ch = yt["bot"], yt["ch"]
    bot.store.x("UPDATE people SET email='a@b.co', email_verified_at='2026-11-01T00:00:00+00:00' WHERE handle=?", (H,))
    ch.outbox_place = "in the Outbox panel"   # as on the test page: the email reaches the person
    yt["state"]["answers"]["mvp_compose"] = lemon_pick()
    a = outside_ask()
    a["spec"]["do"] = [{"action": "email.send"}]
    n = len(ch.outbox)
    say(yt, "email me pasta recipes and some new ones from outside my saves", a)
    thread = "\n".join(str(m[2]) for m in ch.outbox[n:])
    assert thread.startswith("For \"a pasta recipe\": ")
    assert "Not from your saves, but close to them:\n• One Pot Chicken & Rice (Easy!)" in thread
    email = open(bot.store.outbox(H)[0]["path"], encoding="utf-8").read()
    assert "One Pot Chicken" not in email                                         # never emailed (never kept)
