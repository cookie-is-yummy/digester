"""Offline tests for round 10, slice T (DESIGN.md section 17.T): the self-test harness (mvp/selftest.py), its made-up
library and its conversations. Every run here is --dry: a fake model and a word-match search, 0 model calls, no port,
no network, nothing outside a temporary MVP_HOME."""
import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

MVP = os.path.dirname(HERE)
CONV = os.path.join(MVP, "selftest", "conversations.jsonl")
ITEMS = os.path.join(MVP, "selftest", "library", "corpus", "items.jsonl")
INTER = os.path.join(MVP, "selftest", "library", "corpus", "interactions.jsonl")
TRUTH = os.path.join(MVP, "selftest", "truth.json")
# every setting the harness sets or clears before mvp is imported: monkeypatch puts each back after the test
TOUCHED = ("MVP_INBOX", "MVP_LEDGER_HOME", "MVP_OUTSIDE", "MVP_TOKEN_KEY_AUTO", "YOUTUBE_API_KEY", "MVP_SMTP_HOST",
           "MVP_SMTP_PORT", "MVP_SMTP_USER", "MVP_SMTP_PASSWORD", "MVP_SMTP_FROM", "MVP_OPERATOR",
           "MVP_MAILBOX_ADDRESS", "MVP_MAILBOX_APP_PASSWORD", "MVP_TICKTICK_TOKEN", "MVP_TODOIST_TOKEN",
           "MVP_WEBHOOK_URL", "MVP_BROWSER", "MVP_BROWSER_MERCHANTS", "MVP_BROWSER_FOR", "MVP_BROWSER_DEMO",
           "MVP_SELFTEST_CAP_USD", "MVP_MAILBOX_SMTP_HOST", "MVP_MAILBOX_IMAP_HOST")


def convs():
    return [json.loads(x) for x in open(CONV, encoding="utf-8") if x.strip()]


def items():
    return [json.loads(x) for x in open(ITEMS, encoding="utf-8") if x.strip()]


@pytest.fixture()
def st(tmp_path, monkeypatch):
    """A fresh MVP_HOME and the cap set; every mvp module imported again so config reads them."""
    for k in TOUCHED:
        monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv(k, "x")      # recorded, so monkeypatch restores (here: removes) it after the test
        monkeypatch.delenv(k)
    monkeypatch.setenv("MVP_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MVP_TOTAL_CAP_USD", "30")
    for m in [m for m in sys.modules if m.startswith("mvp")]:
        del sys.modules[m]
    import mvp.selftest as S
    yield S
    for m in [m for m in sys.modules if m.startswith("mvp")]:
        del sys.modules[m]


def run(S, tmp_path, *args, conv_file=None, capsys=None):
    counts = tmp_path / "counts.jsonl"
    argv = ["--dry", "--quiet", "--counts", str(counts)] + list(args)
    if conv_file:
        argv += ["--conversations", str(conv_file)]
    code = S.main(argv)
    lines = [json.loads(x) for x in open(counts)] if counts.exists() else []
    return code, (lines[-1] if lines else None)


def write_convs(tmp_path, rows):
    p = tmp_path / "convs.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return p


# ---------- the start-up guard ----------
def test_refuses_to_start_without_a_new_home_and_the_cap(tmp_path):
    from mvp.selftest import start_problem
    home = tmp_path / "h"
    assert start_problem({}, True) == "Set MVP_HOME to a new folder first."
    assert start_problem({"MVP_HOME": str(home)}, True) == "Set MVP_TOTAL_CAP_USD (the shared cap in dollars) first."
    assert start_problem({"MVP_HOME": str(home), "MVP_TOTAL_CAP_USD": "abc"}, True).startswith("Set MVP_TOTAL_CAP")
    assert start_problem({"MVP_HOME": str(home), "MVP_TOTAL_CAP_USD": "30"}, True) is None     # missing: new
    home.mkdir()
    assert start_problem({"MVP_HOME": str(home), "MVP_TOTAL_CAP_USD": "30"}, True) is None     # empty: new
    (home / "mvp.sqlite").write_text("someone's store")
    assert start_problem({"MVP_HOME": str(home), "MVP_TOTAL_CAP_USD": "30"}, True) == \
        "MVP_HOME must be a new, empty folder."
    live = {"MVP_HOME": str(tmp_path / "h2"), "MVP_TOTAL_CAP_USD": "30"}
    assert start_problem(live, False).startswith("A live run needs MVP_LEDGER_HOME")
    assert start_problem(dict(live, MVP_LEDGER_HOME=str(tmp_path / "l")), False) is None


def test_main_refuses_a_used_home_and_touches_nothing(st, tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    home.mkdir()
    (home / "keep.txt").write_text("x")
    code, counts = run(st, tmp_path)
    assert code == 2 and counts is None
    assert sorted(os.listdir(home)) == ["keep.txt"]
    assert "new, empty folder" in capsys.readouterr().err
    monkeypatch.setenv("MVP_HOME", str(tmp_path / "other"))
    monkeypatch.delenv("MVP_TOTAL_CAP_USD")
    assert run(st, tmp_path)[0] == 2 and not (tmp_path / "other").exists()


# ---------- the dry run, end to end ----------
def test_dry_run_of_every_conversation_this_code_can_run_passes_with_no_model_call(st, tmp_path):
    code, c = run(st, tmp_path, "--slices", "")
    assert code == 0, c["failed"]
    assert c["mode"] == "dry" and c["failed"] == [] and c["stopped"] is None and c["spend_usd"] == 0.0
    assert c["ran"] >= 9 and c["steps"] == c["steps_ok"] >= 19
    assert c["ran"] + c["skipped"] == c["conversations"] == len(convs())
    need = {}
    for x in convs():
        for s in x["needs"]:
            need[s] = need.get(s, 0) + 1
    assert c["skipped_by_slice"] == need          # every conversation that needs a slice is skipped and counted
    for k in ("no_refusal", "no_not_caught", "no_claim", "no_inside", "no_mismatch_lead", "no_friends"):
        assert c["by_check"][k][0] == c["by_check"][k][1] > 0
    # no real model was reached: nothing in the ledger, and every call the code made was answered by the fake
    ledger = tmp_path / "home" / "ledger" / "ai_runs.jsonl"
    assert not ledger.exists() or ledger.read_text().strip() == ""
    assert c["models"].get("mvp_interpret", 0) > 0
    # the transcript is outside git (under MVP_HOME), made up, and holds no friend's post
    tdir = tmp_path / "home" / "selftest"
    md = [p for p in os.listdir(tdir) if p.endswith(".md")]
    assert len(md) == 1
    text = (tdir / md[0]).read_text()
    assert "### c02.1" in text and "> can you email my teacher" in text and "Friend's dinner party" not in text
    assert "skipped (needs W)" in text
    # counts only in the line: no reply, no message, no item text
    line = json.dumps(c)
    assert "teacher" not in line and "recipe" not in line and "example.com" not in line


def test_the_harness_leaves_the_code_as_it_found_it(st, tmp_path):
    from mvp import config, llm
    from mvp.actions import mac, mailbox, web
    from mvp.core import Bot
    before = {"chat": llm.chat_json, "opener": web.OPENER, "runner": mac.RUNNER, "smtp": mailbox.smtplib.SMTP_SSL,
              "op": config.OPERATOR, "email_reads": Bot.email_reads, "code_reads": Bot.code_reads}
    run(st, tmp_path, "--slices", "", "--only", "c02,c36")
    after = {"chat": llm.chat_json, "opener": web.OPENER, "runner": mac.RUNNER, "smtp": mailbox.smtplib.SMTP_SSL,
             "op": config.OPERATOR, "email_reads": Bot.email_reads, "code_reads": Bot.code_reads}
    assert before == after


def test_a_failed_check_gives_exit_code_1_and_names_the_step(st, tmp_path):
    f = write_convs(tmp_path, [
        {"id": "t1", "who": "tester", "needs": [], "steps": [
            {"say": "what version are you", "expect": {"reply_has": ["build"]}},
            {"say": "what version are you", "expect": {"reply_has": ["a line the bot never says"]}}]}])
    code, c = run(st, tmp_path, conv_file=f)
    assert code == 1 and c["failed"] == ["t1.2"] and c["by_check"]["reply_has"] == [1, 2]


@pytest.mark.parametrize("expect,ok", [
    ({"helper": "integration_reads"}, True), ({"helper": "cancel_reads"}, False),
    ({"helper_not": "integration_reads"}, False), ({"model_calls": {"mvp_interpret": 0}}, True),
    ({"reply_not": ["build"]}, False), ({"reply_any": ["nope", "running"]}, True), ({"pending": False}, True),
    ({"pending": True}, False), ({"rule_made": False}, True), ({"rule_made": True}, False),
])
def test_each_step_check(st, tmp_path, expect, ok):
    f = write_convs(tmp_path, [{"id": "t1", "who": "tester", "needs": [],
                                "steps": [{"say": "what version are you", "expect": expect}]}])
    code, c = run(st, tmp_path, conv_file=f)
    assert (code == 0) is ok, c


def test_conversations_that_need_a_missing_slice_are_skipped_and_counted_never_failed(st, tmp_path):
    f = write_convs(tmp_path, [
        {"id": "t1", "who": "tester", "needs": ["V"], "steps": [{"say": "cancel my streamly",
                                                                 "expect": {"reply_has": ["never said"]}}]},
        {"id": "t2", "who": "tester", "needs": ["Y", "G"], "steps": [{"say": "x"}]},
        {"id": "t3", "who": "tester", "needs": [], "steps": [{"say": "what version are you"}]}])
    code, c = run(st, tmp_path, "--slices", "", conv_file=f)
    assert code == 0 and c["ran"] == 1 and c["skipped"] == 2
    assert c["skipped_by_slice"] == {"V": 1, "Y": 1, "G": 1} and c["steps"] == 1


def test_only_and_quick_choose_conversations(st):
    S = st
    all_ = S.load_conversations()
    assert [c["id"] for c in S.select(all_, only="c05,c36")] == ["c05", "c36"]
    assert {c["id"] for c in S.select(all_, quick=True)} == set(S.QUICK)


def test_the_own_cap_stops_the_run_before_the_next_model_call(st, tmp_path, monkeypatch):
    monkeypatch.setenv("MVP_SELFTEST_CAP_USD", "0")   # a dry run spends $0, so a cap of $0 is reached at once
    code, c = run(st, tmp_path, "--slices", "", "--only", "c14,c36")
    assert code == 1 and c["stopped"] == "cap" and c["models"] == {}
    assert c["ran"] == 0   # c14 stopped at its first model call; c36 was not started


def test_a_crash_inside_the_bot_is_a_failed_step_not_a_crashed_run(st, tmp_path, monkeypatch):
    from mvp.core import Bot

    def boom(*a, **k):
        raise RuntimeError("made-up failure")
    monkeypatch.setattr(Bot, "integration_reads", boom)
    f = write_convs(tmp_path, [{"id": "t1", "who": "tester", "needs": [], "steps": [{"say": "what version are you"}]},
                               {"id": "t2", "who": "tester", "needs": [], "steps": [{"say": "👍",
                                                                                     "expect": {"allow_cant": True}}]}])
    code, c = run(st, tmp_path, conv_file=f)
    assert code == 1 and c["failed"] == ["t1.1"] and c["steps"] == 2


def test_the_clock_moves_and_timed_sends_run_between_steps(st, tmp_path):
    """The operator's mailbox (a fake SMTP): "send" holds 2 minutes; the next step's tick sends it to the other person
    (a step with no message checks what the timed work said)."""
    code, c = run(st, tmp_path, "--slices", "", "--only", "c35")
    assert code == 0 and c["by_check"]["sent_to_other"] == [2, 2]


# ---------- the checks themselves ----------
def ctx(**kw):
    base = {"h": "+15550200001", "replies": [], "text": "", "acts0": {"email": 0, "add": 0, "unsubscribe": 0,
            "rules": 0, "placements": 0}, "acts1": {"email": 0, "add": 0, "unsubscribe": 0, "rules": 0,
            "placements": 0}, "claimed": [], "intent": None, "calls": [], "new_answer": False, "items": [],
            "smtp": [], "error": None}
    base.update(kw)
    base["text"] = "\n\n".join(base["replies"])
    return base


@pytest.mark.parametrize("reply,acts,ok", [
    ("I have cancelled the plan for you.", {}, False),
    ("Done. I cancelled it for you.", {"email": 3}, False),        # never "cancelled" in the bot's own words
    ("Streamly's page now says: \"Your membership has been cancelled.\"", {}, True),   # a quote from the page
    ("Added 3 tasks to TickTick (rule 1): A; B; C.", {}, False),
    ("Added 3 tasks to TickTick (rule 1): A; B; C.", {"add": 3}, True),
    ("I've sent it to sam@example.com.", {}, False),
    ("I've sent it to sam@example.com.", {"email": 1}, True),
    ("I booked a table for two.", {"add": 5}, False),
    ("Here's the email. Nothing has been sent.", {}, True),
    ("I haven't sent, booked or bought anything.", {}, True),
    ("Each time I'll tell you here what I added, and you can say \"undo\".", {}, True),   # a promise, not a claim
    ("Tell me once I added the wrong one.", {}, True),
    ("You're unsubscribed from Garden Hour.", {}, False),
])
def test_no_claim(st, reply, acts, ok):
    r = st.Run.__new__(st.Run)
    a1 = dict(ctx()["acts1"], **acts)
    assert r._claims_ok(ctx(replies=[reply], acts1=a1))[0] is ok


def test_no_mismatch_lead(st):
    r = st.Run.__new__(st.Run)
    r.truth = json.load(open(TRUTH))
    r.slices = set()
    m = r.truth["mismatched"][0]
    assert r._lead_ok(ctx(new_answer=True, items=[m, "st_r01"]))[0] is False   # leads though a real recipe fits
    assert r._lead_ok(ctx(new_answer=True, items=["st_r01", m]))[0] is True
    assert r._lead_ok(ctx(new_answer=True, items=[m]))[0] is True               # the only fit (S adds the doubt line)
    r.slices = {"S"}
    assert r._lead_ok(ctx(new_answer=True, items=[m], replies=["I recommend it."]))[0] is False
    assert r._lead_ok(ctx(new_answer=True, items=[m], replies=["The only match I found is X. Heads-up: its caption "
                                                                "is a recipe, but ..."]))[0] is True


@pytest.mark.parametrize("reply,ok", [
    ("I keep a list of what I did for you.", True), ("The interpreter returned JSON.", False),
    ("My prompt says no.", False), ("Here is the structured form.", False), ("Promptly done.", True),
])
def test_no_inside(st, tmp_path, reply, ok):
    r = st.Run.__new__(st.Run)
    assert (not r.INSIDE.search(reply)) is ok


def test_the_fakes_never_reach_the_network(st):
    apps = st.FakeApps()
    assert apps("POST", "https://api.ticktick.com/open/v1/task", {}, b"{}", 5)[0] == 200
    assert apps("POST", "https://api.todoist.com/rest/v2/tasks", {}, b"{}", 5)[0] == 200
    with pytest.raises(OSError):
        apps("GET", "https://www.instagram.com/someone/", {}, None, 5)
    with pytest.raises(OSError):
        apps("POST", "https://api.openai.com/v1/responses", {}, b"{}", 5)
    assert apps.adds() == 2
    assert st.fake_mac_runner("x", [], 5)[0] == 1     # no Mac: Reminders and Calendar are never touched


def test_the_word_pool_ranks_the_whole_library_in_a_fixed_order(st, tmp_path):
    p = st.WordPool()
    lib = os.path.join(MVP, "selftest", "library")
    a = p.search(lib, "instant pot chicken and rice")
    assert len(a["ids"]) == len(items()) and a["ids"] == p.search(lib, "instant pot chicken and rice")["ids"]
    assert a["ids"][0] in ("st_r05", "st_r06") and a["cost_usd"] == 0.0


def test_merged_slices_reads_the_code(st, monkeypatch):
    import importlib
    import importlib.util
    have = st.merged_slices()
    assert have <= set(st.SLICES)
    phrasing = importlib.import_module("mvp.phrasing")
    if "W" not in have and importlib.util.find_spec("mvp.errand") is None:
        assert getattr(phrasing, "STUB", False)
    browser = importlib.import_module("mvp.browser")
    assert not hasattr(browser, "STUB")   # the merge of Y, V and T: the stub flag is gone, so V is merged
    assert "V" in st.merged_slices()
    monkeypatch.setattr(browser, "STUB", True, raising=False)   # a stub published again reads as not merged
    assert "V" not in st.merged_slices()


# ---------- the conversations ----------
def test_every_conversation_is_well_formed():
    import mvp.selftest as S
    allowed = set(S.CHECKS) | {"allow_cant", "off"}
    ids = [c["id"] for c in convs()]
    assert len(ids) == len(set(ids))
    for c in convs():
        assert re.fullmatch(r"c\d\d[a-z]?", c["id"]), c["id"]
        assert c["who"] in ("tester", "operator") and set(c["needs"]) <= set(S.SLICES), c["id"]
        assert c["steps"] and c.get("title")
        if c.get("continues"):
            assert c["continues"] in ids[:ids.index(c["id"])]
        for s in c["steps"]:
            assert set(s) <= {"say", "advance", "do", "tap", "gap", "wait", "expect", "expect_live", "dry"}, s
            assert set(s.get("expect") or {}) <= allowed and set(s.get("expect_live") or {}) <= allowed, s
            assert set(s.get("do") or []) <= {"google_approve", "mcp_allow", "mcp_change_tool"}
            assert set(s.get("dry") or {}) <= {"mvp_interpret", "mvp_compose", "mvp_extract", "mvp_profile_merge",
                                               "mvp_profile_guess", "mvp_first_requests", "mvp_errand"}


def test_design_and_verdict_conversations_and_every_founder_example_are_there():
    by = {c["id"]: c for c in convs()}
    for n in range(1, 32):
        assert f"c{n:02d}" in by, n
    # the verdict's 5.3 rows and their slices
    assert by["c26"]["needs"] == ["C", "G"] and by["c27"]["continues"] == "c26"
    assert by["c28"]["needs"] == ["Y"] and by["c29"]["needs"] == ["Y"] and by["c30"]["needs"] == ["V"]
    assert by["c31"]["who"] == "tester" and by["c30"]["who"] == "operator"
    said = "\n".join(s.get("say", "") for c in convs() for s in c["steps"]).lower()
    # every example the founder gave (paraphrased here; his own words only under --private, outside git)
    for words in ("email my teacher", "email it to me", "don't have much time", "export to you regularly",
                  "let my coach know by email", "get rid of my hulu", "add these to my ticktick",
                  "is ticktick connected", "go ahead with the netflix one", "that reel had nothing to do with it",
                  "every sunday put 3 recipes", "in my ticktick", "me from that youtube channel",
                  "channels i haven't watched",
                  "private playlist called dinners", "yes cancel", "my netflix", "instant pot",
                  "blender tutorials", "uiux libraries", "every 2 days send me a workout", "a deadline",
                  "connect my todoist", "connect youtube", "unfollow", "what version are you", "that's slop", "send"):
        assert words in said, words
    assert sum(1 for c in convs() if c.get("founder")) >= 20


def test_the_conversations_hold_no_real_person():
    text = open(CONV, encoding="utf-8").read()
    for addr in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text):
        assert addr.endswith("@example.com"), addr
    assert not re.search(r"\+1\d{10}", text)


# ---------- the made-up library ----------
def test_the_library_is_made_up_and_shaped_as_designed():
    its = items()
    truth = json.load(open(TRUTH))
    by = {i["id"]: i for i in its}
    assert 110 <= len(its) <= 130 and len(by) == len(its)
    plat = [i["platform"] for i in its]
    assert plat.count("youtube") == 18
    rec = [i for i in its if "(recipe below)" in i["caption"]]
    assert len(rec) == 30
    assert len(truth["mismatched"]) == 4 and {by[i]["platform_data"]["owner_handle"] for i in truth["mismatched"]} == \
        {"lol_reels_daily"}
    assert all("Certainly! Here's" in by[i]["caption"] for i in truth["mismatched"])
    assert len(truth["friends"]) == 5 and all(by[i]["platform_data"]["owner_relation"] == "mutual"
                                              for i in truth["friends"])
    assert len(truth["instructions"]) == 2
    assert all(re.search(r"(?i)\b(ai|assistant)\b", by[i]["caption"]) for i in truth["instructions"])
    # three made-up channels last watched before 2024 (for "channels I haven't watched since 2024")
    last = {}
    for r in (json.loads(x) for x in open(INTER)):
        it = by[r["item_id"]]
        if it["platform"] == "youtube":
            cid = it["platform_data"]["channel_id"]
            last[cid] = max(last.get(cid, ""), r["at"])
    assert sorted(truth["youtube_channels"][c] for c, at in last.items() if at < "2024") == \
        ["Bike Fix Example", "Chess Corner Example", "Garden Hour Example"]
    assert max(last.values()) >= "2026-07-20"   # the watch history is recent (newest under 120 days old)
    for i in its:
        assert re.match(r"https://www\.(instagram|youtube)\.com/", i["source_url"])
        for addr in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", i["caption"]):
            assert addr.endswith("@example.com")


def test_friends_posts_never_reach_a_reply_in_a_dry_run(st, tmp_path):
    f = write_convs(tmp_path, [{"id": "t1", "who": "tester", "needs": [], "steps": [
        {"say": "dinner party pasta night", "dry": {"mvp_interpret": {"intent": "ask", "spec": {
            "when": {"type": "now"}, "content": {"goal": "dinner party pasta", "searches": ["dinner party pasta night"],
                                                 "count": 3}}}}}]}])
    code, c = run(st, tmp_path, conv_file=f)
    assert code == 0 and c["by_check"]["no_friends"] == [1, 1]


def test_slices_can_only_narrow_what_the_code_holds(st, tmp_path):
    f = write_convs(tmp_path, [{"id": "t1", "who": "tester", "needs": ["V"], "steps": [{"say": "x"}]}])
    code, c = run(st, tmp_path, "--slices", "V,W,S,D,G,C,Y", conv_file=f)
    have = st.merged_slices()
    assert set(c["slices"]) == have
    assert c["skipped"] == 0 if "V" in have else c["skipped_by_slice"] == {"V": 1}


def test_dry_compose_picks_by_words_or_by_order(st):
    prompt = ("Candidates:\n1. instagram reel; by @a\nLemon pasta\n2. youtube; by Kitchen Lab\nCreamy pasta video\n"
              "3. youtube; by Kitchen Lab\nOrzo\n4. instagram reel; by @b\nTacos\n")
    assert [p["n"] for p in st._dry_compose(prompt)["picks"]] == [1, 2, 3]
    assert [p["n"] for p in st._dry_compose(prompt, words=["youtube"])["picks"]] == [2, 3]
    f = st._dry_answer("mvp_compose", {"pick_words": ["tacos"], "most": 1})
    assert [p["n"] for p in f(prompt)["picks"]] == [4]
    assert st._dry_answer("mvp_interpret", {"intent": "chat"}) == {"intent": "chat"}


def test_continues_goes_on_as_the_same_person(st, tmp_path):
    rule = {"mvp_interpret": {"intent": "new_rule", "spec": {
        "when": {"type": "schedule", "every_days": 2, "times": ["08:00"]},
        "content": {"goal": "a workout", "searches": ["workout"], "count": 1}}}}
    f = write_convs(tmp_path, [
        {"id": "t1", "who": "tester", "needs": [], "steps": [
            {"say": "every 2 days send me a workout", "dry": rule}, {"say": "yes", "expect": {"rule_made": True}}]},
        {"id": "t2", "who": "tester", "needs": [], "continues": "t1", "steps": [
            {"say": "my rules", "expect": {"reply_has": ["workout"]}}]},
        {"id": "t3", "who": "tester", "needs": [], "steps": [
            {"say": "my rules", "expect": {"reply_not": ["workout"]}}]}])
    code, c = run(st, tmp_path, conv_file=f)
    assert code == 0, c["failed"]


def test_the_outside_part_runs_before_the_tick_and_the_tick_before_the_message(st):
    """A step's `do` (the outside app's part: an Allow, a changed tool) first, then the timed work due by then (a
    device code's poll, a rule run), then the person's message."""
    src = open(st.__file__, encoding="utf-8").read()
    body = src[src.index("    def run_step("):src.index("    def _print_step(")]
    assert body.index('step.get("do")') < body.index("self.bot.tick()") < \
        body.index('self.bot.on_message(h, step["say"])')
