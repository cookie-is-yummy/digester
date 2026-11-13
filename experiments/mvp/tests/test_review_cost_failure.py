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
