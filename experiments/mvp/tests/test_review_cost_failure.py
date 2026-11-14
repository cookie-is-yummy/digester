"""Offline tests for the cost-failure review (findings X1 to X12): one or more per finding, each failing without its
fix. Fakes only: the fake model, the fake search pool, the synthetic library and export, the fake clock. No network,
no real data, no model calls."""
import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, EXP)

from mvp.tests.test_mvp import env, last, pasta_spec  # noqa: E402,F401  (env is a fixture)
from mvp.tests.test_slice5 import FIX_IG, drop, fake_prepare, fresh, zip_dir  # noqa: E402,F401

H = "+15550001"
UTC = timezone.utc


def _orig(monkeypatch, name):
    """The real function a fixture replaced (the env fixture fakes the caps and the model)."""
    for _obj, attr, value in monkeypatch._setattr:
        if attr == name:
            return value
    raise KeyError(name)


def _ledger_rows():
    from mvp import llm
    if not os.path.exists(llm.ai.LEDGER):
        return []
    with open(llm.ai.LEDGER) as f:
        return [json.loads(line) for line in f if line.strip()]


# ---------- X1: "run 1" over the cap ----------
def test_x1_run_command_over_the_cap_sends_the_limit_and_makes_no_paid_call(env, monkeypatch):
    bot, ch, st, calls = env["bot"], env["ch"], env["state"], env["calls"]
    from mvp import llm, texts as T
    from mvp.schema import RuleSpec
    spec = RuleSpec.model_validate({"when": {"type": "on_request"}, "content": pasta_spec()["content"]})
    bot.store.add_rule(H, "pasta when I ask", spec.stored(), "active", None)
    st["answers"]["mvp_compose"] = lambda u: {"picks": [{"n": 1, "title": "Lemon garlic pasta", "verdict": "clear"}]}
    monkeypatch.setattr(llm, "spent_today", lambda h, lib: 99.0)
    n_out, n_calls = len(ch.outbox), len(calls)
    bot.on_message(H, "run 1")
    assert calls[n_calls:] == [] and last(ch) == T.LIMIT and len(ch.outbox) == n_out + 1
    bot.on_message(H, "run 1")   # the limit is said once a day; still no paid call
    assert calls[n_calls:] == [] and len(ch.outbox) == n_out + 1
    # a reminder in the person's own words costs nothing: "run 2" still sends it over the cap
    note = RuleSpec.model_validate({"when": {"type": "on_request"}, "content": {"source": "note", "text": "Stretch"}})
    bot.store.add_rule(H, "stretch", note.stored(), "active", None)
    bot.on_message(H, "run 2")
    assert calls[n_calls:] == [] and "Stretch" in str(last(ch))
    # under the cap it runs as before
    monkeypatch.setattr(llm, "spent_today", lambda h, lib: 0.0)
    bot.on_message(H, "run 1")
    assert "mvp_compose" in calls[n_calls:]


# ---------- X2: the same export again, and builds a day ----------
def _variant_zip(tmp_path, k):
    """The synthetic Instagram export with one more harmless file, so its fingerprint differs."""
    src = tmp_path / f"ig{k}"
    shutil.copytree(FIX_IG, src)
    (src / f"note{k}.json").write_text(json.dumps({"k": k}))
    return zip_dir(str(src), str(tmp_path / f"instagram-{k}.zip"))


def test_x2_the_same_export_again_is_not_built_again(fresh):
    bot, ch = fresh["bot"], fresh["ch"]
    from mvp import texts as T
    from mvp.refresh import Refresher
    builds = []
    prep = fake_prepare(cost=0.63)
    bot.refresher = Refresher(bot, prepare=lambda lib, cap: builds.append(lib) or prep(lib, cap), background=False,
                              settle_seconds=0)
    for _ in range(3):
        drop(fresh, fresh["ig_zip"])
        bot.refresher.poll(force=True)
    assert len(builds) == 1
    assert last(ch) == T.IMPORT_SAME
    rows = [r["status"] for r in bot.store.q("SELECT status FROM imports ORDER BY id")]
    assert rows == ["done", "same", "same"]
    assert not [f for f in os.listdir(fresh["inbox"]) if not f.startswith(".")]   # the copies are not kept
    assert not os.path.isdir(os.path.join(fresh["inbox"], ".failed"))


def test_x2_builds_a_day_are_limited_and_the_last_import_library_is_removed(fresh, tmp_path):
    bot, ch = fresh["bot"], fresh["ch"]
    from mvp import config, texts as T
    from mvp.refresh import Refresher
    builds = []
    prep = fake_prepare(cost=0.2)
    bot.refresher = Refresher(bot, prepare=lambda lib, cap: builds.append(lib) or prep(lib, cap), background=False,
                              settle_seconds=0)
    original = bot.store.person(H)["library"]
    for k in range(config.IMPORTS_PER_DAY + 1):
        drop(fresh, _variant_zip(tmp_path, k))
        bot.refresher.poll(force=True)
    assert len(builds) == config.IMPORTS_PER_DAY
    assert last(ch) == T.import_too_many(config.IMPORTS_PER_DAY)
    now = bot.store.person(H)["library"]
    assert now == builds[-1] and os.path.isdir(now)
    assert os.path.isdir(original)                         # the founders' library is never removed
    assert not any(os.path.isdir(b) for b in builds[:-1])  # a library an earlier import built is removed


def test_x2_an_earlier_import_library_someone_else_uses_is_kept(fresh, tmp_path):
    bot = fresh["bot"]
    from mvp.refresh import Refresher
    builds = []
    prep = fake_prepare(cost=0.01)
    bot.refresher = Refresher(bot, prepare=lambda lib, cap: builds.append(lib) or prep(lib, cap), background=False,
                              settle_seconds=0)
    drop(fresh, _variant_zip(tmp_path, 0))
    bot.refresher.poll(force=True)
    bot.store.x("INSERT INTO people(handle, name, library, timezone) VALUES(?,?,?,?)",
                ("+15550002", "U", builds[0], "America/New_York"))
    drop(fresh, _variant_zip(tmp_path, 1))
    bot.refresher.poll(force=True)
    assert len(builds) == 2 and os.path.isdir(builds[0])


# ---------- X3: a build's cost is not the person's chat spend; a held rule is said ----------
def test_x3_a_build_does_not_use_up_the_daily_cap(fresh, monkeypatch):
    bot, ch, st = fresh["bot"], fresh["ch"], fresh["state"]
    from mvp import llm, texts as T
    from mvp.refresh import Refresher
    monkeypatch.setattr(llm, "spent_today", _orig(monkeypatch, "spent_today"))
    llm.log_spend(H, "mvp_interpret", 0.30)
    bot.refresher = Refresher(bot, prepare=fake_prepare(cost=0.72), background=False, settle_seconds=0)
    drop(fresh, fresh["ig_zip"])
    bot.refresher.poll(force=True)
    lib = bot.store.person(H)["library"]
    assert abs(llm.spent_today(H, lib) - 0.30) < 1e-9
    assert any(r.get("purpose") == "mvp_import" and r.get("in_tokens") is not None for r in _ledger_rows())
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "ask", "spec": pasta_spec({"type": "now"})}
    st["answers"]["mvp_compose"] = lambda u: {"picks": [{"n": 1, "title": "Lemon garlic pasta", "verdict": "clear"}]}
    bot.on_message(H, "pasta ideas?")
    assert last(ch) != T.LIMIT


def test_x3_a_new_items_rule_held_for_the_cap_is_said_and_runs_later(fresh, monkeypatch):
    bot, ch, st = fresh["bot"], fresh["ch"], fresh["state"]
    from mvp import llm
    from mvp.refresh import Refresher
    from mvp.schema import RuleSpec
    spent = [1.5]
    monkeypatch.setattr(llm, "spent_today", lambda h, lib: spent[0])
    bot.refresher = Refresher(bot, prepare=fake_prepare(cost=0.01), background=False, settle_seconds=0)
    spec = RuleSpec.model_validate({"when": {"type": "new_items"},
                                    "content": {"goal": "a sourdough recipe", "searches": ["sourdough"]}})
    rid = bot.store.add_rule(H, "when I save sourdough", spec.stored(), "active", None)
    st["answers"]["mvp_compose"] = lambda u: {"picks": [{"n": 1, "title": "A new pick", "verdict": "clear"}]}

    class Pool:
        max_resident = 4

        def search(self, lib, q, depth=300):
            ids = [json.loads(line)["id"] for line in open(os.path.join(lib, "corpus", "items.jsonl"))]
            return {"ids": ids, "mode": "normal", "cost_usd": 0.0}

        def warm(self, lib):
            pass

        def stop_all(self):
            pass
    bot.pool = Pool()
    drop(fresh, fresh["ig_zip"])
    n = len(ch.outbox)
    bot.refresher.poll(force=True)
    sent = [str(m[2]) for m in ch.outbox[n:]]
    assert len(sent) == 1 and "today's limit" in sent[0] and "a sourdough recipe" in sent[0]
    assert bot.store.get_state(f"heldnew:{H}")["rules"] == [rid]
    bot._release_held(bot.clock())   # still over the cap: it waits
    assert len(ch.outbox) == n + 1
    spent[0] = 0.0                   # the next day
    bot._release_held(bot.clock())
    runs = [r["status"] for r in bot.store.q("SELECT status FROM runs WHERE rule_id=? ORDER BY id", (rid,))]
    assert runs[0] == "over_cap" and runs[-1] == "sent"
    assert len(ch.outbox) > n + 1 and bot.store.get_state(f"heldnew:{H}") is None


# ---------- X4: a call we stopped waiting for is still counted; every engine purpose counts ----------
def test_x4_a_timed_out_call_writes_an_estimated_ledger_row(env, monkeypatch):
    from mvp import llm
    monkeypatch.setattr(llm, "chat_json", _orig(monkeypatch, "chat_json"))
    monkeypatch.setattr(llm, "spent_today", _orig(monkeypatch, "spent_today"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")

    def slow(*a, **k):
        raise TimeoutError("timed out")
    monkeypatch.setattr(llm.ai, "_post", slow)
    with pytest.raises(TimeoutError):
        llm.chat_json("s" * 350, "u" * 350, purpose="mvp_compose", prompt_version="compose_v4", person=H,
                      max_tokens=1600)
    rows = _ledger_rows()
    assert len(rows) == 1 and rows[0]["estimated"] and rows[0]["person"] == llm.person_ref(H)
    assert rows[0]["cost_usd"] == llm.estimate_usd("s" * 350, "u" * 350, 1600) > 0
    assert abs(llm.spent_today(H, str(env["lib"])) - rows[0]["cost_usd"]) < 1e-9
    # an HTTP error answer came back (not billed) and a refused connection never sent: no row
    import urllib.error
    for err in (urllib.error.HTTPError("u", 429, "slow down", {}, None),
                urllib.error.URLError(ConnectionRefusedError(111, "refused"))):
        monkeypatch.setattr(llm.ai, "_post", lambda *a, err=err, **k: (_ for _ in ()).throw(err))
        with pytest.raises(Exception):
            llm.chat_json("s", "u", purpose="mvp_compose", prompt_version="compose_v4", person=H, max_tokens=100)
    assert len(_ledger_rows()) == 1


def test_x4_every_library_ledger_purpose_counts(env, monkeypatch, tmp_path):
    from mvp import llm
    monkeypatch.setattr(llm, "spent_today", _orig(monkeypatch, "spent_today"))
    monkeypatch.setattr(llm, "spent_total", _orig(monkeypatch, "spent_total"))
    lib = tmp_path / "libx"
    lib.mkdir()
    llm.started_at()
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    with open(lib / "ai_runs.jsonl", "w") as f:
        f.write(json.dumps({"at": now, "purpose": "c88_refine", "cost_usd": 0.5}) + "\n")
        f.write(json.dumps({"at": now, "purpose": "demo_query_rewrite", "cost_usd": 0.01}) + "\n")
    assert abs(llm.spent_today("+1nobody", str(lib)) - 0.51) < 1e-9
    assert abs(llm.spent_total([str(lib)]) - 0.51) < 1e-9


# ---------- X5: a stand-in ranking is never cached ----------
def test_x5_a_keyword_fallback_or_a_skipped_rewrite_is_not_cached(env, monkeypatch):
    from mvp import config, retrieve
    monkeypatch.setattr(config, "RANKED_CACHE_HOURS", 24 * 7)
    replies = [{"ids": ["itm_c"], "mode": "keyword_fallback", "cost_usd": 0.0},
               {"ids": ["itm_c", "itm_a"], "mode": "normal", "degraded": True, "cost_usd": 0.0},
               {"ids": ["itm_a", "itm_b", "itm_c", "itm_e"], "mode": "normal", "cost_usd": 0.0}]
    calls = []

    class Pool:
        def search(self, lib, q, depth=300):
            calls.append(q)
            return replies[min(len(calls), len(replies)) - 1]
    now = datetime(2026, 11, 12, 18, 0, tzinfo=UTC)
    store, lib = env["bot"].store, str(env["lib"])
    assert retrieve.ranked(Pool(), lib, "pasta recipe", store=store, now=now)["ids"] == ["itm_c"]
    assert retrieve.ranked(Pool(), lib, "pasta recipe", store=store, now=now + timedelta(days=1))["ids"] == \
        ["itm_c", "itm_a"]
    r = retrieve.ranked(Pool(), lib, "pasta recipe", store=store, now=now + timedelta(days=2))
    assert r["ids"] == ["itm_a", "itm_b", "itm_c", "itm_e"] and len(calls) == 3
    r = retrieve.ranked(Pool(), lib, "pasta recipe", store=store, now=now + timedelta(days=3))
    assert r.get("cached") and len(calls) == 3          # a real ranking is kept as before


def test_x5_the_engine_pool_marks_a_search_whose_rewrite_failed():
    from mvp import engines as EN

    class Eng:
        def __init__(self, why):
            self.why = why

        def request(self, obj):
            return {"ok": True, "result": {"q8": {"ids": ["a"], "why": self.why}}}
    pool = EN.EnginePool()
    for why, want in [({"mode": "normal", "path": "rewrite", "rewrite": {"used": False, "skipped": "HTTPError"}}, True),
                      ({"mode": "normal", "path": "rewrite", "rewrite": {"used": True}}, False),
                      ({"mode": "normal", "path": "instant", "rewrite": {"used": False, "skipped": "instant path"}},
                       False)]:
        pool.get = lambda lib, why=why: Eng(why)
        assert pool.search("/x", "q")["degraded"] is want


# ---------- X6: the last cent below the total cap ----------
def _real_calls(monkeypatch):
    from mvp import llm
    for name in ("chat_json", "spent_total", "spent_today"):
        monkeypatch.setattr(llm, name, _orig(monkeypatch, name))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    posted = []
    monkeypatch.setattr(llm.ai, "_post", lambda *a, **k: posted.append(1) or {})
    return posted


def test_x6_just_below_the_total_cap_reads_as_the_budget_message(env, monkeypatch):
    bot, ch = env["bot"], env["ch"]
    from mvp import llm, config, texts as T
    posted = _real_calls(monkeypatch)
    os.makedirs(os.path.dirname(llm.ai.LEDGER), exist_ok=True)
    with open(llm.ai.LEDGER, "w") as f:
        f.write(json.dumps({"at": "2026-11-12T10:00:00", "provider": "openai", "purpose": "mvp_compose",
                            "cost_usd": config.TOTAL_CAP_USD - 0.005, "person": "p-other"}) + "\n")
    assert bot._over_cap(bot.store.person(H)) == "total"
    bot.on_message(H, "pasta ideas?")
    assert last(ch) == T.LIMIT_TOTAL and not posted


def test_x6_a_budget_stop_from_the_guard_is_the_budget_message(env, monkeypatch):
    bot, ch, st = env["bot"], env["ch"], env["state"]
    from mvp import llm, config, texts as T
    posted = _real_calls(monkeypatch)
    monkeypatch.setattr(config, "TOTAL_CAP_MARGIN_USD", 0.0)
    os.makedirs(os.path.dirname(llm.ai.LEDGER), exist_ok=True)
    with open(llm.ai.LEDGER, "w") as f:
        f.write(json.dumps({"at": "2026-11-12T10:00:00", "provider": "openai", "purpose": "mvp_compose",
                            "cost_usd": config.TOTAL_CAP_USD - 0.0001, "person": "p-other"}) + "\n")
    bot.on_message(H, "pasta ideas?")      # the interpreter's call is refused by ai.py's guard
    assert last(ch) == T.LIMIT_TOTAL and not posted
    # a run whose compose call is refused the same way says the budget text too
    from mvp.schema import RuleSpec
    bot.store.set_state(f"cap_notice:{H}", None)
    msg, run_id, n = bot.run(bot.store.person(H), RuleSpec.model_validate(pasta_spec({"type": "now"})), "ask")
    assert msg == T.LIMIT_TOTAL and n == 0 and not posted


# ---------- X7: a compose reply cut off at its token limit ----------
def _real_model(monkeypatch, replies):
    """The real llm.chat_json with a fake HTTP post: `replies(body)` gives each reply; returns the bodies sent."""
    from mvp import llm
    monkeypatch.setattr(llm, "chat_json", _orig(monkeypatch, "chat_json"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    bodies = []

    def post(url, body, headers):
        bodies.append(body)
        content, reason = replies(body)
        return {"usage": {"prompt_tokens": 3000, "completion_tokens": 100},
                "choices": [{"finish_reason": reason, "message": {"content": content}}]}
    monkeypatch.setattr(llm.ai, "_post", post)
    return bodies


CUT = ('{"picks": [{"n": 1, "verdict": "clear", "title": "Lem', "length")
GOOD = (json.dumps({"picks": [{"n": 1, "verdict": "clear", "title": "Lemon garlic pasta"}]}), "stop")


def _ask_of(body):
    user = body["messages"][1]["content"]
    return json.loads(user.split("\n", 1)[0][len("Request: "):])


def test_x7_max_tokens_follow_the_picks_and_must_haves_asked_for():
    from mvp.compose import max_tokens_for
    assert max_tokens_for(1, 0) == 1600                     # never less than before
    assert max_tokens_for(13, 5) > 1919                     # 13 picks, 5 quoted must-haves (about 1,919 tokens)
    assert max_tokens_for(13, 5) <= 4000


def test_x7_a_cut_reply_is_tried_once_with_fewer_picks(env, monkeypatch):
    bot, ch, st = env["bot"], env["ch"], env["state"]
    spec = pasta_spec({"type": "now"})
    spec["content"].update(count=3, criteria=["one pot", "under 20 minutes"])
    seen = []

    def replies(body):
        if "Candidates:" not in body["messages"][1]["content"]:   # the interpreter
            return json.dumps({"intent": "ask", "spec": spec}), "stop"
        seen.append(1)
        return CUT if len(seen) == 1 else GOOD
    bodies = _real_model(monkeypatch, replies)
    bot.on_message(H, "three one-pot pastas under 20 minutes")
    compose = [b for b in bodies if "Candidates:" in b["messages"][1]["content"]]
    assert len(compose) == 2
    first, second = _ask_of(compose[0]), _ask_of(compose[1])
    assert first["max_picks"] > 3 and second["max_picks"] == 3
    assert compose[0]["max_completion_tokens"] >= 1600
    assert compose[1]["max_completion_tokens"] >= compose[0]["max_completion_tokens"]
    from mvp import texts as T
    reply = str(last(ch))
    assert T.RUN_ERROR not in reply and T.COMPOSE_CUT_ASK not in reply and "pasta" in reply.lower()


def test_x7_a_timed_send_cut_twice_is_not_retried_and_the_person_is_told(env, monkeypatch):
    bot, ch, clock = env["bot"], env["ch"], env["clock"]
    from mvp.schema import RuleSpec
    bodies = _real_model(monkeypatch, lambda body: CUT)
    rid = bot.store.add_rule(H, "pasta every friday", RuleSpec.model_validate(pasta_spec()).stored(), "active", None)
    start = clock[0]
    bot.store.set_slot(rid, start.isoformat(), "active")
    n0 = len(ch.outbox)
    for k in range(6):
        clock[0] = start + timedelta(minutes=15 * k + 1)
        bot.tick()
    assert len(bodies) == 2                                 # one try and one with more room: no paid retries
    runs = [r["status"] for r in bot.store.q("SELECT status FROM runs WHERE rule_id=?", (rid,))]
    assert runs == ["error"]
    msgs = [str(m[2]) for m in ch.outbox[n0:]]
    assert len(msgs) == 1 and "a pasta recipe" in msgs[0] and "skipped" in msgs[0]
    assert bot.store.rule(rid)["next_run_at"] > (start + timedelta(days=1)).isoformat()   # next Friday


def test_x7_an_ask_cut_twice_says_so_without_try_again(env, monkeypatch):
    bot, ch, st = env["bot"], env["ch"], env["state"]
    from mvp import texts as T
    _real_model(monkeypatch, lambda body: (None, "content_filter") if "Candidates:" in body["messages"][1]["content"]
                else (json.dumps({"intent": "ask", "spec": pasta_spec({"type": "now"})}), "stop"))
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "ask", "spec": pasta_spec({"type": "now"})}
    bot.on_message(H, "pasta ideas?")
    assert str(last(ch)).startswith(T.COMPOSE_CUT_ASK)


# ---------- X8: the code email where the person cannot open the outbox ----------
def test_x8_a_code_email_that_was_not_sent_is_not_kept_or_counted(env, monkeypatch):
    bot, ch, clock = env["bot"], env["ch"], env["clock"]
    from mvp import texts as T
    from mvp.actions import email as E
    from mvp.channels.imessage_mac import MacMessagesChannel
    from mvp.channels.sendblue import SendblueChannel
    assert not any(getattr(c, "outbox_place", None) or getattr(c, "outbox_reachable", False)
                   for c in (MacMessagesChannel, SendblueChannel))
    ch.outbox_reachable = False   # as on Messages or Sendblue
    monkeypatch.setenv("MVP_SMTP_HOST", "smtp.example.invalid")

    def refused(s, m):
        raise ConnectionRefusedError(111, "refused")
    monkeypatch.setattr(E, "_smtp_send", refused)
    bot._set_email(bot.store.person(H), "tester@example.com", clock[0])
    assert last(ch) == T.code_not_sent("tester@example.com")
    assert "outbox" not in last(ch) and "sent a 6-digit code" not in last(ch)
    assert bot.store.q("SELECT path FROM outbox WHERE handle=?", (H,)) == []
    assert not (bot.store.get_state(f"emailcodes:{H}") or [])           # not one of the day's codes
    assert bot.store.get_state(f"emailcode:{H}") is None
    assert bot.store.email_of(H) == ("tester@example.com", False)
    # "new code" tries again; once SMTP works the code goes out as before
    monkeypatch.setattr(E, "_smtp_send", lambda s, m: None)
    bot.on_message(H, "new code")
    assert last(ch).startswith("I sent a new 6-digit code to tester@example.com.")
    assert len(bot.store.get_state(f"emailcodes:{H}")) == 1


def test_x8_without_email_set_up_the_address_is_not_asked_for_a_code(env, monkeypatch):
    bot, ch, clock = env["bot"], env["ch"], env["clock"]
    from mvp import texts as T
    monkeypatch.delenv("MVP_SMTP_HOST", raising=False)
    ch.outbox_reachable = False
    bot._set_email(bot.store.person(H), "tester@example.com", clock[0])
    assert last(ch) == T.EMAIL_NOT_SET_UP
    assert bot.store.email_of(H)[0] is None and bot.store.q("SELECT path FROM outbox WHERE handle=?", (H,)) == []


def test_x8_the_setup_does_not_ask_for_an_address_email_cannot_reach(env, tmp_path, monkeypatch):
    from mvp.tests import test_slice6 as S6
    monkeypatch.delenv("MVP_SMTP_HOST", raising=False)
    lib = S6.write_library(tmp_path / "richlib")   # the slice-6 "rich" fixture's library
    env["bot"].store.x("UPDATE people SET library=? WHERE handle=?", (str(lib), H))
    env["bot"].pool = S6.AllPool(str(lib))
    env["state"]["answers"]["mvp_profile_guess"] = S6.fake_guess
    env["lib"] = lib
    env["ch"].outbox_reachable = False   # as on Messages or Sendblue
    S6.start(env)
    env["state"]["answers"]["mvp_profile_merge"] = lambda u: {"kind": "about_me", "confirm_topics": ["Home cooking"]}
    third = S6.say(env, "Mostly right.", {"intent": "chat", "reply": "unused"})
    assert "I have you on New York time" in third and "What's your email address?" not in third


# ---------- low: X9 to X12 ----------
def test_x9_an_email_smtp_sent_stays_done_when_its_copy_cannot_be_kept(env, monkeypatch):
    import errno
    bot, ch, st, clock = env["bot"], env["ch"], env["state"], env["clock"]
    from mvp.actions import email as E
    monkeypatch.setenv("MVP_SMTP_HOST", "smtp.example.invalid")
    sent = []
    monkeypatch.setattr(E, "_smtp_send", lambda s, m: sent.append(m["To"]))

    def full(*a, **k):
        raise OSError(errno.ENOSPC, "No space left on device")
    monkeypatch.setattr(E, "write_outbox", full)
    bot.store.set_email(H, "tester@example.com", verified=True, at=clock[0])
    spec = pasta_spec({"type": "now"})
    spec["do"] = [{"action": "email.send"}]
    st["answers"]["mvp_interpret"] = lambda u: {"intent": "ask", "spec": spec}
    st["answers"]["mvp_compose"] = lambda u: {"picks": [{"n": 1, "title": "Lemon garlic pasta", "verdict": "clear"}]}
    bot.on_message(H, "email me a pasta recipe")
    msg = str(last(ch))
    assert sent == ["tester@example.com"] and "couldn't email this" not in msg and "I emailed this to you" in msg
    assert [r["status"] for r in bot.store.q("SELECT status FROM action_log WHERE action='email.send'")] == ["done"]


def test_x10_the_test_pages_clock_does_not_open_a_new_quota_day(env, monkeypatch):
    from mvp import config, outside as O
    from mvp.schema import RuleSpec
    monkeypatch.setenv("YOUTUBE_API_KEY", "dummy")
    monkeypatch.setattr(config, "OUTSIDE_ON", True)
    store = env["bot"].store
    real = datetime.now(UTC)
    day = real.astimezone(O.ZoneInfo(config.OUTSIDE_DAY_TZ)).date().isoformat()
    for i in range(config.OUTSIDE_PER_DAY):
        store.x("INSERT INTO outside_searches(handle,day,at,status) VALUES(?,?,?,?)", (f"p{i}", day, "x", "ok"))
    hits = []
    o = O.Outside(store, http=lambda url, params, key, timeout=None: hits.append(url) or {"items": []})
    spec = RuleSpec.model_validate({"when": {"type": "now"}, "content": {"goal": "sourdough bread",
                                                                         "searches": ["sourdough bread"],
                                                                         "outside": "some"}})
    assert o.find(H, spec, ["new sourdough bread videos"], now=real)["status"] == "limit_all"
    assert o.find(H, spec, ["new sourdough bread videos"], now=real + timedelta(days=1))["status"] == "limit_all"
    assert hits == []


def test_x10_codes_a_day_are_counted_in_real_time(env, monkeypatch):
    bot, ch, clock = env["bot"], env["ch"], env["clock"]
    from mvp import config, texts as T
    for i in range(config.CODES_PER_DAY):
        bot._set_email(bot.store.person(H), f"x{i}@example.com", clock[0])
    clock[0] += timedelta(days=2)    # "Forward 1 day" twice on the test page
    bot._set_email(bot.store.person(H), "z@example.com", clock[0])
    assert last(ch) == T.CODE_LIMIT


def test_x11_an_empty_guess_is_tried_twice_before_it_is_kept(env):
    bot, st, calls = env["bot"], env["state"], env["calls"]
    from mvp import profile as P
    answers = [{}, {"topics": []}]
    st["answers"]["mvp_profile_guess"] = lambda u: answers.pop(0) if answers else {}
    r1, _ = P.guess(bot.view(str(env["lib"])), store=bot.store, handle=H)
    assert r1["sample"] >= 3 and r1["interests"] == [] and calls.count("mvp_profile_guess") == 2


def test_x12_a_late_engine_reply_is_dropped():
    import io
    import threading
    from mvp import engines as EN
    e = EN.EngineProcess.__new__(EN.EngineProcess)
    e.lib, e.state, e.message = "x", "ready", ""
    e.cond, e.replies, e.waiting, e.wlock = threading.Condition(), {}, set(), threading.Lock()
    e.next_id, e.busy, e.last_used = 0, 0, 0

    class P:
        stdin = io.StringIO()
        stdout = io.StringIO('{"id": 1, "ok": true}\n')
    e.proc = P
    assert e.request({"cmd": "search"}, timeout=0)["ok"] is False   # timed out
    e._read()                                                       # the reply comes after its time-out
    assert e.replies == {}


def test_x12_an_engine_that_failed_to_load_is_not_restarted_at_once(env, monkeypatch):
    from mvp import engines as EN
    starts = []

    class Fake:
        def __init__(self, lib, budget):
            starts.append(lib)
            self.lib, self.state, self.message, self.busy, self.last_used = lib, "error", "boom", 0, 0

        def wait_ready(self, timeout=600):
            return False

        def stop(self):
            pass
    monkeypatch.setattr(EN, "EngineProcess", Fake)
    pool = EN.EnginePool()
    for _ in range(3):
        with pytest.raises(RuntimeError):
            pool.get(str(env["lib"]))
    assert len(starts) == 1
    pool.failed_at[os.path.abspath(str(env["lib"]))] -= pool.RETRY_S + 1   # later: one more try
    with pytest.raises(RuntimeError):
        pool.get(str(env["lib"]))
    assert len(starts) == 2


def test_x12_ranked_lists_past_their_use_are_removed(env, monkeypatch):
    from mvp import config, retrieve
    monkeypatch.setattr(config, "RANKED_CACHE_HOURS", 24)
    st = env["bot"].store
    st.cache_put("ranked_cache", "old", {"ids": ["a"]}, at=datetime(2026, 1, 1, tzinfo=UTC), library="L",
                 mode="normal")

    class Pool:
        def search(self, lib, q, depth=300):
            return {"ids": ["itm_a"], "mode": "normal", "cost_usd": 0.0}
    retrieve.ranked(Pool(), str(env["lib"]), "pasta", store=st, now=datetime(2026, 11, 12, tzinfo=UTC))
    assert st.one("SELECT COUNT(*) n FROM ranked_cache WHERE key='old'")["n"] == 0
    assert st.one("SELECT COUNT(*) n FROM ranked_cache")["n"] == 1
