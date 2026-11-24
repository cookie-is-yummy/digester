"""Offline tests for the Claude text path (DESIGN.md section 20). Fakes only (tests/fakes/fake_anthropic.py: a fake
client, or the real SDK over a fake transport); no network, no money, no real data. Each test fails on the commit
before section 20 (b745cfd): the path, the settings and the texts did not exist there."""
import json
import logging
import os
import sys
import traceback

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, EXP)

from mvp.tests.fakes.fake_anthropic import (  # noqa: E402
    FakeAnthropic,
    error_json,
    message_json,
    reply,
    sdk_transport,
)
from mvp.tests.test_mvp import env, last  # noqa: E402,F401  (env is a fixture)

H = "+15550001"
MARK = "sk-ant-test-MARKER-7f3a9c1e5b"          # a planted key: it must never appear anywhere the run writes
MARK2 = "sk-ant-test-SECOND-2d4b6f8a0c"


@pytest.fixture
def cl(tmp_path, monkeypatch):
    """A fresh import of the mvp modules on temporary folders, a Claude key planted, the ambient ANTHROPIC_*
    settings this machine's own tools use set to values that must not reach the bot's client."""
    monkeypatch.setenv("MVP_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MVP_LEDGER_HOME", str(tmp_path / "ledger"))
    monkeypatch.setenv("MVP_INBOX", str(tmp_path / "inbox"))
    monkeypatch.setenv("MVP_DERIVED_HOME", str(tmp_path / "derived"))
    monkeypatch.setenv("DIGESTER_ANTHROPIC_API_KEY", MARK)
    monkeypatch.setenv("ANTHROPIC_API_KEY", MARK2)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://ambient.example.invalid")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "ambient-token-should-not-be-sent")
    monkeypatch.setenv("ANTHROPIC_CUSTOM_HEADERS", "X-Ambient: yes")
    for k in ("MVP_MODEL", "MVP_JUDGE_MODEL", "MVP_ERRAND_MODEL", "MVP_CLAUDE_THINKING", "MVP_CLAUDE_EFFORT",
              "MVP_CLAUDE_FALLBACKS", "MVP_RUN_TAG", "MVP_RUN_MAX_USD"):
        monkeypatch.delenv(k, raising=False)
    for m in [m for m in sys.modules if m.startswith("mvp") and not m.startswith("mvp.tests")]:
        del sys.modules[m]
    from mvp import config, llm
    monkeypatch.setattr(llm.ai, "ANTHROPIC_CLIENT", None)
    monkeypatch.setattr(llm.ai, "ANTHROPIC_TRANSPORT", None)
    llm.ai._client_cache.clear()
    yield {"llm": llm, "config": config, "ai": llm.ai, "tmp": tmp_path}
    llm.ai._client_cache.clear()


def rows(cl):
    p = cl["ai"].LEDGER
    return [json.loads(x) for x in open(p)] if os.path.exists(p) else []


def no_openai(monkeypatch, llm):
    def boom(*a, **k):
        raise AssertionError("an OpenAI call on the Claude path")
    monkeypatch.setattr(llm.ai, "openai_chat_json", boom)


# ---------- routing ----------
def test_a_claude_model_id_goes_to_anthropic_and_any_other_to_openai(cl, monkeypatch):
    llm, ai = cl["llm"], cl["ai"]
    seen = []
    monkeypatch.setattr(ai, "openai_chat_json", lambda model, *a, **k: (seen.append(("openai", model)) or {"x": 1}, {}))
    monkeypatch.setattr(ai, "anthropic_chat_json",
                        lambda model, *a, **k: (seen.append(("anthropic", model)) or {"y": 2}, {}))
    assert llm.chat_json("s", "u", "mvp_extract", "extract_v4")[0] == {"x": 1}
    assert llm.chat_json("s", "u", "mvp_extract", "extract_v4", model="claude-haiku-5-5")[0] == {"y": 2}
    assert llm.chat_json("s", "u", "mvp_judge", "judge_kind_v2", model="gpt-5.5")[0] == {"x": 1}
    monkeypatch.setattr(cl["config"], "MODEL", "claude-sonnet-5-5")   # MVP_MODEL=claude-... is the whole switch
    llm.chat_json("s", "u", "mvp_compose", "compose_v5")
    llm.chat_json("s", "u", "mvp_judge", "judge_kind_v2", model="gpt-5.5")   # a per-call override still wins
    assert seen == [("openai", "gpt-5.4-mini"), ("anthropic", "claude-haiku-5-5"), ("openai", "gpt-5.5"),
                    ("anthropic", "claude-sonnet-5-5"), ("openai", "gpt-5.5")]
    assert cl["config"].claude_models() == ["claude-sonnet-5-5"]


def test_the_setting_read_from_the_environment_routes_every_text_call(tmp_path, monkeypatch):
    monkeypatch.setenv("MVP_LEDGER_HOME", str(tmp_path / "ledger"))
    monkeypatch.setenv("MVP_MODEL", "claude-haiku-5-5")
    monkeypatch.setenv("MVP_JUDGE_MODEL", "claude-opus-5-5")
    for m in [m for m in sys.modules if m.startswith("mvp") and not m.startswith("mvp.tests")]:
        del sys.modules[m]
    from mvp import config
    assert config.MODEL == "claude-haiku-5-5" and config.claude_models() == ["claude-haiku-5-5", "claude-opus-5-5"]
    monkeypatch.setenv("MVP_ERRAND_MODEL", "claude-sonnet-5-5")
    assert config.claude_models() == ["claude-haiku-5-5", "claude-opus-5-5", "claude-sonnet-5-5"]


def test_with_no_claude_model_nothing_of_the_claude_path_is_used(cl, monkeypatch):
    llm = cl["llm"]
    fake = FakeAnthropic([]).install(monkeypatch)   # any Claude call would fail the test
    seen = []
    monkeypatch.setattr(llm.ai, "openai_chat_json",
                        lambda model, system, user, **k: (seen.append((model, system, user, k)) or {"ok": 1}, {}))
    llm.chat_json("sys", "usr", "mvp_insight", "insight_v5", max_tokens=700, temperature=0, seed=7)
    assert seen == [("gpt-5.4-mini", "sys", "usr", {"max_tokens": 700, "purpose": "mvp_insight",
                                                    "prompt_version": "insight_v5", "temperature": 0, "seed": 7})]
    assert fake.calls == [] and cl["config"].claude_models() == [] and llm.cap_reached([]) is None


# ---------- the client: explicit base URL, the key from our two names only ----------
def test_ambient_anthropic_settings_never_reach_the_client_and_the_key_comes_from_our_names(cl, monkeypatch):
    llm, ai = cl["llm"], cl["ai"]
    no_openai(monkeypatch, llm)
    tr, seen = sdk_transport([{"json": message_json('{"a": 1}')}, {"json": message_json('{"b": 2}')}])
    monkeypatch.setattr(ai, "ANTHROPIC_TRANSPORT", tr)
    assert llm.chat_json("s", "u", "mvp_extract", "extract_v4", model="claude-haiku-5-5")[0] == {"a": 1}
    h = seen[0]["headers"]
    assert seen[0]["url"] == "https://api.anthropic.com/v1/messages"
    assert h.get("authorization") == f"Bearer {MARK}"          # DIGESTER_ANTHROPIC_API_KEY first
    assert "x-ambient" not in h and "ambient-token" not in json.dumps(h)
    assert os.environ["ANTHROPIC_BASE_URL"] == "https://ambient.example.invalid"   # put back after the build
    assert os.environ["ANTHROPIC_CUSTOM_HEADERS"] == "X-Ambient: yes"
    monkeypatch.delenv("DIGESTER_ANTHROPIC_API_KEY")
    llm.chat_json("s", "u", "mvp_extract", "extract_v4", model="claude-haiku-5-5")
    assert seen[1]["headers"].get("authorization") == f"Bearer {MARK2}"   # then ANTHROPIC_API_KEY
    c = ai.anthropic_client()
    assert str(c.base_url).rstrip("/") == "https://api.anthropic.com" and c.auth_token is None and c.max_retries == 0


def test_no_key_is_a_clear_error_naming_the_variable_and_never_falls_back_to_openai(cl, monkeypatch):
    llm, ai = cl["llm"], cl["ai"]
    monkeypatch.delenv("DIGESTER_ANTHROPIC_API_KEY")
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    no_openai(monkeypatch, llm)
    tr, seen = sdk_transport([])
    monkeypatch.setattr(ai, "ANTHROPIC_TRANSPORT", tr)
    with pytest.raises(ai.MissingKey) as e:
        llm.chat_json("s", "u", "mvp_extract", "extract_v4", model="claude-haiku-5-5")
    assert "DIGESTER_ANTHROPIC_API_KEY" in str(e.value) and "ANTHROPIC_API_KEY" in str(e.value)
    assert seen == [] and rows(cl) == []
    assert llm.smoke(["claude-haiku-5-5"], out=lambda s: None) == 2


# ---------- the request: thinking, effort, fallbacks, JSON ----------
@pytest.mark.parametrize("model,thinking,effort,fallbacks", [
    ("claude-haiku-5-5", {"type": "disabled"}, "low", False),
    ("claude-sonnet-5-5", {"type": "between_tools"}, "low", True),
    ("claude-opus-5-5", None, "low", True),     # Opus 5.5 cannot turn thinking off: effort is the control
])
def test_the_knobs_sent_for_each_model_with_thinking_off(cl, monkeypatch, model, thinking, effort, fallbacks):
    llm = cl["llm"]
    fake = FakeAnthropic(['{"ok": true}']).install(monkeypatch)
    llm.chat_json("sys", "usr", "mvp_interpret", "interpret_v5", max_tokens=900, temperature=0, seed=7, model=model)
    b = fake.calls[0]
    assert b.get("thinking") == thinking and b["output_config"] == {"effort": effort}
    assert ("fallbacks" in b) is fallbacks and (b.get("betas") == ["server-side-fallback-2026-07-01"]) is fallbacks
    assert "temperature" not in b and "seed" not in b and b["max_tokens"] == 900
    assert b["system"].startswith("sys") and b["system"].endswith(cl["ai"].JSON_LINE)
    assert b["messages"] == [{"role": "user", "content": "usr"}] and b["timeout"] == cl["ai"].TIMEOUT
    assert fake.base_urls == ["https://api.anthropic.com"] and fake.keys == [MARK]
    assert rows(cl)[-1]["not_sent"] == ["seed", "temperature"]


def test_adaptive_thinking_and_a_callers_effort(cl, monkeypatch):
    llm, config = cl["llm"], cl["config"]
    monkeypatch.setattr(config, "CLAUDE_THINKING", "adaptive")
    fake = FakeAnthropic(['{"ok": 1}', '{"ok": 2}']).install(monkeypatch)
    llm.chat_json("s", "u", "mvp_judge", "judge_kind_v2", model="claude-haiku-5-5", reasoning_effort="none")
    monkeypatch.setattr(config, "CLAUDE_THINKING", "off")
    llm.chat_json("s", "u", "mvp_judge", "judge_kind_v2", model="claude-sonnet-5-5", reasoning_effort="xhigh")
    assert fake.calls[0]["thinking"] == {"type": "adaptive"} and fake.calls[0]["output_config"] == {"effort": "low"}
    # between_tools is taken only at effort high or below
    assert fake.calls[1]["thinking"] == {"type": "between_tools"} and fake.calls[1]["output_config"]["effort"] == "high"


def test_a_schema_is_sent_as_structured_output(cl, monkeypatch):
    llm = cl["llm"]
    fake = FakeAnthropic(['{"name": "x"}']).install(monkeypatch)
    schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"],
              "additionalProperties": False}
    assert llm.chat_json("sys", "u", "mvp_x", "x_v1", model="claude-haiku-5-5", schema=schema)[0] == {"name": "x"}
    b = fake.calls[0]
    assert b["output_config"]["format"] == {"type": "json_schema", "schema": schema} and b["system"] == "sys"


@pytest.mark.parametrize("text,want", [
    ('{"a": 1}', {"a": 1}),
    ('  ```json\n{"a": {"b": [1, 2]}}\n```', {"a": {"b": [1, 2]}}),
    ('{"a": 1}\n\nI hope this helps.', {"a": 1}),      # the first complete object; the rest is not read
])
def test_json_is_read_strictly_as_the_first_object(cl, monkeypatch, text, want):
    FakeAnthropic([text]).install(monkeypatch)
    assert cl["llm"].chat_json("s", "u", "mvp_x", "x_v1", model="claude-haiku-5-5")[0] == want


@pytest.mark.parametrize("text", ['Here you go: {"a": 1}', '[1, 2]', '{"a": 1', 'no json here'])
def test_a_reply_that_is_not_one_object_fails_as_a_parse_failure_does_and_is_still_billed(cl, monkeypatch, text):
    FakeAnthropic([reply(text, input_tokens=1000, output_tokens=100)]).install(monkeypatch)
    with pytest.raises(ValueError) as e:
        cl["llm"].chat_json("s", "u", "mvp_x", "x_v1", model="claude-haiku-5-5")
    assert e.value.stop_reason == "not_json" and text not in str(e.value)
    r = rows(cl)[-1]
    assert r["provider"] == "anthropic" and r["cost_usd"] == pytest.approx((1000 * 0.10 + 100 * 0.50) / 1e6)


@pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
def test_a_refusal_or_a_cut_is_handled_never_parsed(cl, monkeypatch, stop):
    FakeAnthropic([reply('{"half": ', stop_reason=stop, category="cyber" if stop == "refusal" else None)]
                  ).install(monkeypatch)
    with pytest.raises(cl["ai"].ClaudeStop) as e:
        cl["llm"].chat_json("s", "u", "mvp_x", "x_v1", model="claude-sonnet-5-5")
    assert e.value.stop_reason == stop and isinstance(e.value, ValueError)
    assert rows(cl)[-1]["stop_reason"] == stop


def test_the_real_sdk_reads_a_refusal_and_an_empty_reply(cl, monkeypatch):
    ai = cl["ai"]
    tr, _ = sdk_transport([{"json": message_json(None, stop_reason="refusal", category="bio")},
                           {"json": message_json("   ")}])
    monkeypatch.setattr(ai, "ANTHROPIC_TRANSPORT", tr)
    with pytest.raises(ai.ClaudeStop, match="refusal"):
        cl["llm"].chat_json("s", "u", "mvp_x", "x_v1", model="claude-opus-5-5")
    with pytest.raises(ai.ClaudeStop, match="no_text"):
        cl["llm"].chat_json("s", "u", "mvp_x", "x_v1", model="claude-opus-5-5")


# ---------- the ledger ----------
def test_the_ledger_row_of_a_claude_call(cl, monkeypatch):
    llm = cl["llm"]
    FakeAnthropic([reply('{"ok": 1}', input_tokens=2000, output_tokens=300, cache_read=1000, cache_write=400)]
                  ).install(monkeypatch)
    out, cost = llm.chat_json("s", "u", "mvp_compose", "compose_v5", person=H, model="claude-sonnet-5-5")
    r = rows(cl)[-1]
    want = (2000 * 2 + 300 * 10 + 1000 * 0.10 + 400 * 2.5) / 1e6
    assert out == {"ok": 1} and cost == pytest.approx(want) and r["cost_usd"] == pytest.approx(want)
    assert {k: r[k] for k in ("provider", "model", "purpose", "prompt_version", "n", "in_tokens", "out_tokens",
                              "cache_read_tokens", "cache_write_tokens")} == {
        "provider": "anthropic", "model": "claude-sonnet-5-5", "purpose": "mvp_compose", "prompt_version": "compose_v5",
        "n": 1, "in_tokens": 2000, "out_tokens": 300, "cache_read_tokens": 1000, "cache_write_tokens": 400}
    assert r["person"].startswith("p-") and H not in json.dumps(r) and "seconds" in r and "at" in r


def test_a_rescued_call_is_priced_per_attempt_at_each_models_own_rate(cl, monkeypatch):
    its = [{"type": "message", "model": "claude-opus-5-5", "input_tokens": 500, "output_tokens": 0,
            "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
           {"type": "fallback_message", "model": "claude-opus-4-8", "input_tokens": 500, "output_tokens": 100,
            "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}]
    FakeAnthropic([reply('{"ok": 1}', model="claude-opus-4-8", iterations=its)]).install(monkeypatch)
    cl["llm"].chat_json("s", "u", "mvp_x", "x_v1", model="claude-opus-5-5")
    r = rows(cl)[-1]
    assert r["cost_usd"] == pytest.approx((500 * 4 + 500 * 5 + 100 * 25) / 1e6)
    assert r["served_model"] == "claude-opus-4-8" and r["fallback"] is True and r["in_tokens"] == 1000


def test_a_long_haiku_prompt_takes_the_long_rate_card(cl):
    p = cl["ai"].prices()["claude-haiku-5-5"]
    assert cl["ai"].claude_price(p, 100_000)[:2] == (0.1, 0.5) and cl["ai"].claude_price(p, 100_001)[:2] == (0.5, 2.5)


def test_a_timeout_writes_the_worst_case_as_anthropic_and_a_refused_connection_writes_nothing(cl, monkeypatch):
    import httpx2
    ai, llm = cl["ai"], cl["llm"]
    tr, _ = sdk_transport([httpx2.ReadTimeout("slow"), httpx2.ConnectError("refused")])
    monkeypatch.setattr(ai, "ANTHROPIC_TRANSPORT", tr)
    with pytest.raises(TimeoutError):
        llm.chat_json("s" * 350, "u", "mvp_insight", "insight_v5", max_tokens=700, model="claude-haiku-5-5")
    r = rows(cl)[-1]
    assert r["provider"] == "anthropic" and r["estimated"] is True and r["error"] == "ClaudeTimeout"
    assert r["cost_usd"] == pytest.approx(llm.estimate_usd("s" * 350, "u", 700, "claude-haiku-5-5"))
    n = len(rows(cl))
    with pytest.raises(ConnectionError):
        llm.chat_json("s", "u", "mvp_insight", "insight_v5", model="claude-haiku-5-5")
    assert len(rows(cl)) == n


def test_an_http_error_comes_back_with_its_status_and_type_only(cl, monkeypatch):
    ai = cl["ai"]
    tr, _ = sdk_transport([{"status": 401, "json": error_json()}])
    monkeypatch.setattr(ai, "ANTHROPIC_TRANSPORT", tr)
    with pytest.raises(ai.ClaudeHTTPError) as e:
        cl["llm"].chat_json("s", "u", "mvp_x", "x_v1", model="claude-haiku-5-5")
    assert (e.value.status, e.value.kind, e.value.host) == (401, "authentication_error", "api.anthropic.com")
    assert rows(cl) == []   # an error answer is not billed


# ---------- the caps ----------
def _write(cl, *rs):
    os.makedirs(os.path.dirname(cl["ai"].LEDGER), exist_ok=True)
    with open(cl["ai"].LEDGER, "a") as f:
        for r in rs:
            f.write(json.dumps({"at": "2026-01-02T10:00:00", **r}) + "\n")


def test_claude_spend_has_its_own_cap_and_the_other_cap_counts_only_openai_and_gemini(cl, monkeypatch):
    llm, config = cl["llm"], cl["config"]
    llm.started_at()
    _write(cl, {"provider": "openai", "cost_usd": 2.0}, {"provider": "gemini", "cost_usd": 1.0},
           {"provider": "anthropic", "cost_usd": 9.99})
    assert llm.spent_total([]) == pytest.approx(3.0) and llm.spent_claude() == pytest.approx(9.99)
    monkeypatch.setattr(config, "TOTAL_CAP_USD", 30.0)
    monkeypatch.setattr(config, "CLAUDE_CAP_USD", 10.0)
    assert llm.cap_reached([]) is None                       # no Claude model set: its cap is not read
    monkeypatch.setattr(config, "MODEL", "claude-haiku-5-5")
    assert llm.cap_reached([]) == "claude"                   # 9.99 + the margin passes 10
    monkeypatch.setattr(config, "CLAUDE_CAP_USD", 20.0)
    assert llm.cap_reached([]) is None
    monkeypatch.setattr(config, "TOTAL_CAP_USD", 3.0)
    assert llm.cap_reached([]) == "total"


def test_the_executor_and_the_daily_cap_read_the_caps_in_one_place(cl, monkeypatch):
    llm, config = cl["llm"], cl["config"]
    from mvp.executor import ExecutorMixin

    class B(ExecutorMixin):
        class store:
            @staticmethod
            def q(sql):
                return []
    monkeypatch.setattr(config, "MODEL", "claude-haiku-5-5")
    monkeypatch.setattr(config, "CLAUDE_CAP_USD", 1.0)
    llm.person_ref(H)
    _write(cl, {"at": "2026-01-02T10:00:00", "provider": "anthropic", "cost_usd": 0.99, "person": llm.person_ref(H)})
    from datetime import datetime
    day = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    _write(cl, {"at": day, "provider": "anthropic", "cost_usd": 0.4, "person": llm.person_ref(H)},
           {"at": day, "provider": "openai", "cost_usd": 0.7, "person": llm.person_ref(H)})
    assert B()._over_cap({"handle": H, "library": str(cl["tmp"])}) == "total"   # the Claude cap: no paid call
    monkeypatch.setattr(config, "CLAUDE_CAP_USD", 10.0)
    assert llm.spent_today(H, str(cl["tmp"])) == pytest.approx(1.1)             # the daily cap counts both
    assert B()._over_cap({"handle": H, "library": str(cl["tmp"])}) == "daily"


def test_the_per_call_guard_refuses_a_claude_call_past_its_cap_before_sending(cl, monkeypatch):
    llm = cl["llm"]
    fake = FakeAnthropic([]).install(monkeypatch)
    monkeypatch.setenv("DIGESTER_ANTHROPIC_BUDGET_USD", "0.0001")
    with pytest.raises(RuntimeError) as e:
        llm.chat_json("s" * 4000, "u", "mvp_x", "x_v1", max_tokens=2000, model="claude-opus-5-5")
    assert llm.budget_stop(e.value) and "anthropic" in str(e.value) and fake.calls == []
    assert os.environ.get("DIGESTER_ANTHROPIC_BUDGET_USD")   # llm.py sets it from MVP_CLAUDE_CAP_USD at import


def test_a_run_ceiling_stops_an_eval_mid_way(cl, monkeypatch):
    llm = cl["llm"]
    fake = FakeAnthropic(default=reply('{"ok": 1}', input_tokens=100_000, output_tokens=0)).install(monkeypatch)
    monkeypatch.setenv("MVP_RUN_MAX_USD", "0.025")
    monkeypatch.setenv("MVP_RUN_TAG", "evalmodels-test")
    llm.chat_json("s", "u", "mvp_x", "x_v1", max_tokens=100, model="claude-haiku-5-5")      # $0.01
    llm.chat_json("s", "u", "mvp_x", "x_v1", max_tokens=100, model="claude-haiku-5-5")      # $0.02
    with pytest.raises(RuntimeError) as e:
        llm.chat_json("s", "u", "mvp_x", "x_v1", max_tokens=100_000, model="claude-haiku-5-5")
    assert llm.budget_stop(e.value) and len(fake.calls) == 2
    assert [r["run"] for r in rows(cl)] == ["evalmodels-test"] * 2


# ---------- what the person is told ----------
def test_the_consent_and_what_leaves_name_anthropic_only_while_a_claude_model_is_set(cl, monkeypatch):
    config = cl["config"]
    from mvp import texts as T
    from mvp import videoask as V
    assert T.consent() == T.CONSENT and "Anthropic" not in T.consent() and T.consent_version() == T.CONSENT_VERSION
    assert "Anthropic" not in V.leaves_text() and "• OpenAI: your messages" in V.leaves_text()
    monkeypatch.setattr(config, "JUDGE_MODEL", "claude-opus-5-5")
    assert "go to OpenAI and Anthropic (Claude) to understand them" in T.consent()
    assert "• OpenAI and Anthropic (Claude): your messages" in V.leaves_text()
    assert T.consent_version() == "mvp-consent-v1+anthropic"
    assert V.LEAVES.match("what do you send to anthropic") and V.LEAVES.match("what do you send to claude")


def test_a_new_person_is_shown_the_anthropic_consent_and_agrees_to_that_version(env, monkeypatch):
    bot, ch = env["bot"], env["ch"]
    from mvp import config, texts as T
    bot.store.x("UPDATE people SET consent_version=NULL WHERE handle=?", (H,))
    bot.on_message(H, "hello?")
    assert last(ch) == T.CONSENT
    bot.store.x("DELETE FROM state")
    monkeypatch.setattr(config, "MODEL", "claude-haiku-5-5")
    bot.on_message(H, "hello?")
    assert "OpenAI and Anthropic (Claude)" in last(ch) and last(ch) != T.CONSENT
    bot.on_message(H, "I agree")
    assert bot.store.person(H)["consent_version"] == "mvp-consent-v1+anthropic"


# ---------- the key never shows ----------
def test_the_key_appears_in_no_log_trace_error_or_ledger_row(env, monkeypatch, capsys, caplog, tmp_path):
    """A planted key, a whole bot message on Claude (the real SDK over a fake transport), then a refusal, an error
    answer, a timeout and a smoke run: the key is in nothing the run wrote."""
    import httpx2
    from mvp import config, llm
    caplog.set_level(logging.DEBUG)
    monkeypatch.setenv("DIGESTER_ANTHROPIC_API_KEY", MARK)
    monkeypatch.setenv("ANTHROPIC_LOG", "debug")
    real = next(v for _o, a, v in monkeypatch._setattr if a == "chat_json")   # the env fixture's swap, undone
    monkeypatch.setattr(llm, "chat_json", real)
    monkeypatch.setattr(config, "MODEL", "claude-haiku-5-5")
    llm.ai._client_cache.clear()
    chat = message_json('{"intent": "chat", "reply": "Hello! Ask me for something from your saves."}')
    tr, seen = sdk_transport([{"json": chat}, {"json": message_json(None, stop_reason="refusal")},
                              {"status": 401, "json": error_json()}, httpx2.ReadTimeout("slow"),
                              {"json": message_json('{"sum": 5, "sky": "blue"}')}])
    monkeypatch.setattr(llm.ai, "ANTHROPIC_TRANSPORT", tr)
    texts = []
    env["bot"].on_message(H, "hi there, how does this work?")
    texts.append(json.dumps(env["ch"].outbox))
    for _ in range(3):
        try:
            llm.chat_json("s", "u", "mvp_x", "x_v1", person=H)
        except Exception as e:  # noqa: BLE001
            texts += [str(e), repr(e), "".join(traceback.format_exception(e))]
    assert llm.smoke(["claude-haiku-5-5"], out=texts.append) == 0
    assert len(seen) == 5 and seen[0]["headers"]["authorization"] == f"Bearer {MARK}"   # it was used, then
    out = capsys.readouterr()
    texts += [out.out, out.err, caplog.text]
    for root in (os.environ["MVP_HOME"], os.environ["MVP_LEDGER_HOME"], str(tmp_path)):
        for d, _dirs, files in os.walk(root):
            for f in files:
                with open(os.path.join(d, f), "rb") as fh:
                    texts.append(fh.read().decode("utf-8", "replace"))
    blob = "\n".join(texts)
    assert "anthropic" in blob and MARK not in blob and MARK[8:] not in blob and MARK[-12:] not in blob


# ---------- the smoke command and the path test ----------
def test_smoke_runs_one_call_per_configured_claude_model_and_prints_no_key(cl, monkeypatch):
    llm, config = cl["llm"], cl["config"]
    FakeAnthropic(['{"sum": 5, "sky": "blue"}', '{"sum": 4, "sky": "blue"}']).install(monkeypatch)
    monkeypatch.setattr(config, "MODEL", "claude-haiku-5-5")
    monkeypatch.setattr(config, "JUDGE_MODEL", "claude-sonnet-5-5")
    lines = []
    assert llm.smoke(out=lines.append) == 1      # the second form is wrong: not zero
    assert lines[0].startswith("key: from DIGESTER_ANTHROPIC_API_KEY (value not shown)")
    assert lines[1].startswith("claude-haiku-5-5: ok") and "$0.0000" in lines[1]
    assert lines[2].startswith("claude-sonnet-5-5: FORM WRONG") and MARK not in "\n".join(lines)
    assert [r["purpose"] for r in rows(cl)] == ["mvp_smoke", "mvp_smoke"]
    monkeypatch.setattr(config, "MODEL", "gpt-5.4-mini")
    monkeypatch.setattr(config, "JUDGE_MODEL", "gpt-5.5")
    assert llm.smoke(out=lines.append) == 2 and "No Claude model is set" in lines[-1]


def test_the_path_test_sends_the_invalid_key_and_reads_the_authentication_error(cl, monkeypatch):
    ai = cl["ai"]
    tr, seen = sdk_transport([{"status": 401, "json": error_json()}])
    monkeypatch.setattr(ai, "ANTHROPIC_TRANSPORT", tr)
    assert ai.anthropic_path_test() == {"ok": True, "status": 401, "kind": "authentication_error",
                                        "host": "api.anthropic.com"}
    assert seen[0]["headers"]["authorization"] == "Bearer invalid-key-for-path-test"
    assert seen[0]["url"] == "https://api.anthropic.com/v1/messages" and rows(cl) == []


# ---------- eval_models.py ----------
def _args(tmp_path, **kw):
    from types import SimpleNamespace
    a = dict(models="claude-haiku-5-5,gpt-5.4-mini", out=str(tmp_path / "cmp"), evals="insight,drafts", library="",
             max_usd=3.0, judge_model="", quick=True, dry=True, timeout=600.0)
    a.update(kw)
    return SimpleNamespace(**a)


def test_eval_models_without_a_key_stops_at_once_naming_the_variable(cl, monkeypatch, tmp_path):
    from mvp import eval_models as EM
    monkeypatch.delenv("DIGESTER_ANTHROPIC_API_KEY")
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    ran = []
    monkeypatch.setattr(EM.subprocess, "run", lambda *a, **k: ran.append(a))
    said = []
    rc, table = EM.run_all(_args(tmp_path, dry=False), out=said.append)
    assert rc == 2 and table is None and ran == [] and "DIGESTER_ANTHROPIC_API_KEY" in said[0]
    assert not os.path.exists(tmp_path / "cmp" / "claude-haiku-5-5")


def test_eval_models_dry_runs_each_model_in_its_own_folder_and_writes_one_table(cl, tmp_path):
    from mvp import eval_models as EM
    said = []
    rc, table = EM.run_all(_args(tmp_path), out=said.append)
    out = tmp_path / "cmp"
    assert rc == 0 and (out / "comparison.md").exists() and (out / "comparison.json").exists()
    rows_ = {(r["model"], r["eval"]): r for r in table["rows"]}
    assert set(rows_) == {(m, e) for m in ("claude-haiku-5-5", "gpt-5.4-mini") for e in ("insight", "drafts")}
    for (m, e), r in rows_.items():
        assert r["dir"] == str(out / m / e) and os.path.isdir(r["dir"]) and r["status"].startswith("ok"), r
        assert r["calls"] >= 1 and r["median_s"] is not None and r["worst_s"] is not None
    assert rows_[("claude-haiku-5-5", "insight")]["cost_usd"] > 0          # the fake's tokens at Haiku's price
    led = [json.loads(x) for x in open(out / "dry_ledger" / "ai_runs.jsonl")]
    assert {r["provider"] for r in led if r["model"] == "claude-haiku-5-5"} == {"anthropic"}
    assert all(r["run"].startswith("eval_models:") for r in led)
    md = (out / "comparison.md").read_text()
    assert "| insight | claude-haiku-5-5 |" in md and "| drafts | gpt-5.4-mini |" in md and "dry run" in md


def test_eval_models_stops_a_model_at_its_ceiling(cl, tmp_path):
    from mvp import eval_models as EM
    rc, table = EM.run_all(_args(tmp_path, models="claude-opus-5-5", max_usd=0.004, quick=False), out=lambda s: None)
    by = {r["eval"]: r for r in table["rows"]}
    assert rc == 0 and "ceiling reached" in by["insight"]["status"]
    assert by["insight"]["cost_usd"] <= 0.004 + 1e-9
    assert by["drafts"]["status"].startswith("stopped") or "ceiling" in by["drafts"]["status"]


def test_eval_models_dry_children_get_no_real_key_and_a_new_home_each(cl, monkeypatch, tmp_path):
    import subprocess
    from mvp import eval_models as EM
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test-marker")
    envs = []

    def fake_run(cmd, cwd=None, env=None, **k):
        envs.append((cmd, env))
        return subprocess.CompletedProcess(cmd, 0, stdout='{"cases": 1, "answers": 1}\n', stderr="")
    monkeypatch.setattr(EM.subprocess, "run", fake_run)
    EM.run_all(_args(tmp_path, evals="insight,rules", models="claude-sonnet-5-5"), out=lambda s: None)
    assert len(envs) == 4   # insight, then the 3 rules files
    for cmd, env in envs:
        assert cmd[1:5] == ["-m", "mvp.eval_models", "--child", "--"]
        assert "OPENAI_API_KEY" not in env and env["DIGESTER_ANTHROPIC_API_KEY"] == "dry-run-not-a-key"
        # section 20 review: the judge is fixed (the bot's own, gpt-5.5 here), not the model under test
        assert env["MVP_MODEL"] == "claude-sonnet-5-5" and env["MVP_JUDGE_MODEL"] == "gpt-5.5"
        assert env["MVP_EVAL_DRY"] == "1"
    assert len({env["MVP_HOME"] for _c, env in envs}) == 4


def test_last_json_reads_one_line_or_an_indented_block():
    from mvp.eval_models import last_json
    assert last_json('noise\n{"a": 1}\nTranscript: x') == {"a": 1}
    assert last_json('x\n{\n "a": {\n  "b": 2\n }\n}\n') == {"a": {"b": 2}}
    assert last_json("nothing") is None
