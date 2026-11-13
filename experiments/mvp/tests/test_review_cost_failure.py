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
