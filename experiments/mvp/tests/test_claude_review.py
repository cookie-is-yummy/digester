"""Review of the Claude text path (DESIGN.md section 20.10). Fakes only: no network, no money, no real data. Each test
fails on 1f2a601 (the build under review) or, where noted, checks a promise that held there and must keep holding."""
import json
import logging
import os
import sys
import threading
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, EXP)

from mvp.tests.fakes.fake_anthropic import FakeAnthropic, reply  # noqa: E402
from mvp.tests.test_claude_backend import _args, cl, rows  # noqa: E402,F401  (cl is a fixture)
from mvp.tests.test_mvp import env  # noqa: E402,F401  (env is a fixture)

H = "+15550001"


def _ledger(cl, *rows_):
    os.makedirs(os.path.dirname(cl["ai"].LEDGER), exist_ok=True)
    with open(cl["ai"].LEDGER, "w") as f:
        for r in rows_:
            f.write(json.dumps({"at": "2026-01-01T00:00:00", **r}) + "\n")


# ---------- caps ----------
def test_two_claude_calls_at_the_cap_cannot_both_pass_the_guard(cl, monkeypatch):
    """1f2a601: both calls read the ledger before either answered, both passed, and the cap was overspent."""
    llm, ai = cl["llm"], cl["ai"]
    monkeypatch.setenv("DIGESTER_ANTHROPIC_BUDGET_USD", "0.01")
    _ledger(cl, {"provider": "anthropic", "cost_usd": 0.0093})
    entered, release = threading.Event(), threading.Event()

    def slow(body):
        entered.set()
        release.wait(5)
        return reply('{"a": 1}', input_tokens=1000, output_tokens=1200)
    FakeAnthropic(default=slow).install(monkeypatch)
    out = []

    def go():
        try:
            out.append(llm.chat_json("s", "u", "p", "v", model="claude-haiku-5-5", max_tokens=1200))
        except Exception as e:  # noqa: BLE001
            out.append(e)
    first = threading.Thread(target=go)
    first.start()
    assert entered.wait(5)
    go()                                   # the second call, while the first is still waiting for its answer
    release.set()
    first.join(5)
    refused = [o for o in out if isinstance(o, Exception)]
    assert len(refused) == 1 and llm.budget_stop(refused[0]) and "still waiting" in str(refused[0])
    assert ai.spent("anthropic") <= 0.01 and ai._pending["usd"] == 0.0


def test_the_run_ceiling_counts_the_calls_still_waiting(cl, monkeypatch):
    """1f2a601: eval_rules runs 4 calls at once and each saw only what had come back, so a ceiling was passed."""
    llm = cl["llm"]
    est = llm.estimate_usd("s", "u", 1000, "claude-opus-5-5")
    monkeypatch.setenv("MVP_RUN_MAX_USD", f"{est * 1.5:.6f}")
    entered, release = threading.Event(), threading.Event()

    def slow(body):
        entered.set()
        release.wait(5)
        return reply('{"a": 1}', input_tokens=1, output_tokens=1)
    FakeAnthropic(default=slow).install(monkeypatch)
    out = []

    def go():
        try:
            out.append(llm.chat_json("s", "u", "p", "v", model="claude-opus-5-5", max_tokens=1000))
        except Exception as e:  # noqa: BLE001
            out.append(e)
    first = threading.Thread(target=go)
    first.start()
    assert entered.wait(5)
    go()
    release.set()
    first.join(5)
    # (the words of the refusal are not written here: test_round9_merge.rule_phrasings reads every test file's strings)
    assert sum(isinstance(o, Exception) and llm.budget_stop(o) and "(run)" in str(o) for o in out) == 1
    assert llm._RUN["pending"] == 0.0


def test_old_rows_with_no_provider_still_count_toward_the_openai_and_gemini_cap(cl):
    """Held on 1f2a601; kept: a row from before the provider field is OpenAI or Gemini spend, never Claude's."""
    llm = cl["llm"]
    _ledger(cl, {"cost_usd": 5.0}, {"provider": "openai", "cost_usd": 1.0}, {"provider": "gemini", "cost_usd": 0.5},
            {"provider": "anthropic", "cost_usd": 3.0})
    assert llm.spent_total([]) == 6.5 and llm.spent_claude() == 3.0


# ---------- the writer's deadline ----------
def test_the_writers_20_s_deadline_holds_when_a_claude_call_hangs(cl, monkeypatch):
    """Held on 1f2a601 (the deadline is history._write's thread join, whatever the provider); kept."""
    llm = cl["llm"]
    from mvp import history
    release = threading.Event()

    def hang(body):
        release.wait(10)
        return reply('{"a": 1}')
    FakeAnthropic(default=hang).install(monkeypatch)
    monkeypatch.setattr(history, "WRITE_TIMEOUT_S", 0.4)
    monkeypatch.setattr(history, "_write_now", lambda *a, **k: (
        llm.chat_json("s", "u", "mvp_insight", "insight_v5", model="claude-haiku-5-5"), {}, None))
    t0 = time.time()
    parts, info, _sheet = history._write(None, {"handle": H}, None, None, False, "", [])
    took = time.time() - t0
    release.set()
    assert parts is None and info.get("error") == "late" and took < 1.5


# ---------- the key ----------
def test_the_http_librarys_own_debug_log_is_off_too(cl, monkeypatch):
    """1f2a601 turned off "httpcore", but the SDK's HTTP library logs as "httpcore2"."""
    ai = cl["ai"]
    ai._client_cache.clear()   # a new client is built (no request is sent)
    logging.getLogger("httpcore2").setLevel(logging.DEBUG)
    ai.anthropic_client()
    assert logging.getLogger("httpcore2").level == logging.WARNING


# ---------- what the person agreed to ----------
def test_start_over_on_the_test_page_keeps_the_consent_version_the_person_agreed_to(env, monkeypatch):
    """1f2a601: a person who agreed to the OpenAI-only text was stored as "+anthropic" after a start over while a
    Claude model was set, though they never saw that text."""
    from mvp import config
    from mvp.channels.web import WebChannel
    bot = env["bot"]
    bot.store.set_consent(H, "mvp-consent-v1")     # agreed to the OpenAI-only text
    monkeypatch.setattr(config, "MODEL", "claude-haiku-5-5")
    web = WebChannel(port=0, host="127.0.0.1")
    try:
        web.attach(bot)
        web._control({"op": "start_over", "handle": H})
        assert bot.store.person(H)["consent_version"] == "mvp-consent-v1"
    finally:
        web.close()


# ---------- eval_models: a fixed judge, no wiped results, keys checked first ----------
def test_eval_models_puts_one_fixed_judge_on_every_model_and_names_it(cl, monkeypatch, tmp_path):
    """1f2a601: the judge was the model under test by default, so kinds and the self-test compared two changes."""
    import subprocess
    from mvp import eval_models as EM
    envs = []

    def fake_run(cmd, cwd=None, env=None, **k):
        envs.append(env)
        return subprocess.CompletedProcess(cmd, 0, stdout='{"cases": 1, "answers": 1}\n', stderr="")
    monkeypatch.setattr(EM.subprocess, "run", fake_run)
    rc, table = EM.run_all(_args(tmp_path, evals="insight", judge_model=""), out=lambda s: None)
    assert rc == 0 and {e["MVP_JUDGE_MODEL"] for e in envs} == {"gpt-5.5"}
    assert {e["MVP_MODEL"] for e in envs} == {"claude-haiku-5-5", "gpt-5.4-mini"}
    assert table["judge_model"] == "gpt-5.5"
    md = open(tmp_path / "cmp" / "comparison.md").read()
    assert "Judge (kinds and the self-test): gpt-5.5, the same for every model." in md
    assert "--judge-model" in EM.__doc__ and "the same model for every model compared" in EM.__doc__.replace("\n", " ")


def test_eval_models_says_when_the_judge_moves_with_the_model(cl, monkeypatch, tmp_path):
    import subprocess
    from mvp import eval_models as EM
    monkeypatch.setattr(EM.subprocess, "run", lambda cmd, env=None, **k: subprocess.CompletedProcess(
        cmd, 0, stdout="{}\n", stderr=""))
    rc, table = EM.run_all(_args(tmp_path, evals="insight", judge_model="same"), out=lambda s: None)
    assert rc == 0 and table["judge_model"].startswith("same")
    assert "do not compare them across models" in open(tmp_path / "cmp" / "comparison.md").read()


def test_eval_models_never_wipes_an_earlier_runs_results(cl, monkeypatch, tmp_path):
    """1f2a601: a second run into the same --out deleted the first run's folder (paid for) before it started."""
    from mvp import eval_models as EM
    old = tmp_path / "cmp" / "claude-haiku-5-5" / "insight"
    old.mkdir(parents=True)
    (old / "rows.jsonl").write_text("paid for\n")
    ran, said = [], []
    monkeypatch.setattr(EM.subprocess, "run", lambda *a, **k: ran.append(a))
    rc, table = EM.run_all(_args(tmp_path, evals="insight"), out=said.append)
    assert rc == 2 and table is None and ran == [] and "--overwrite" in said[0]
    assert (old / "rows.jsonl").read_text() == "paid for\n"


def test_eval_models_checks_the_judges_and_the_searchs_keys_before_sending(cl, monkeypatch, tmp_path):
    """1f2a601 checked only the models' own keys: a Claude-only run with a gpt-5.5 judge, or one that searches
    (query embeddings stay on OpenAI), failed inside the evaluation after some calls were paid for."""
    from mvp import eval_models as EM
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MVP_LEDGER_HOME", str(tmp_path / "led"))
    monkeypatch.setenv("MVP_TOTAL_CAP_USD", "1")
    assert EM.key_problem(["claude-haiku-5-5"], dict(os.environ), "gpt-5.5", ["insight", "rules"]) is None
    why = EM.key_problem(["claude-haiku-5-5"], dict(os.environ), "gpt-5.5", ["kinds"])
    assert why and "OPENAI_API_KEY" in why and "judge" in why
    why = EM.key_problem(["claude-haiku-5-5"], dict(os.environ), "claude-haiku-5-5", ["synth"])
    assert why and "OPENAI_API_KEY" in why and "embeddings" in why
    monkeypatch.delenv("DIGESTER_ANTHROPIC_API_KEY")
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    why = EM.key_problem(["gpt-5.4-mini"], dict(os.environ), "claude-opus-5-5", ["selftest"])
    assert why and "DIGESTER_ANTHROPIC_API_KEY" in why
