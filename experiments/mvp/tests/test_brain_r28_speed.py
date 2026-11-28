"""mvp28 speed: the brain provider's transport (streamed request, exact wall clock, timing, warm-up) and the switches
that wait for the blind run (strict off, thinking off). The real SDK over a fake transport (tests/fakes/fake_anthropic):
no network, no money. All but the thinking-switch test fail on 8b9440e (the provider had no stream, no warm, no
timing, no strict switch); that one pins a default that did not change.
"""
import json
import os
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from mvp.tests.fakes.fake_anthropic import sdk_transport  # noqa: E402
from mvp.tests.test_claude_backend import cl, rows  # noqa: E402,F401  (cl is a fixture)

USAGE = {"input_tokens": 3, "output_tokens": 42, "cache_read_input_tokens": 13000, "cache_creation_input_tokens": 120}
ARGS = {"by": "area", "top": 5}
SYSTEM = "system text"
TOOLS = [{"name": "breakdown", "description": "d", "input_schema": {"type": "object", "properties": {
    "by": {"type": "string"}, "top": {"type": "integer"}}, "required": ["by", "top"], "additionalProperties": False}},
    {"name": "give_answer", "description": "d", "input_schema": {"type": "object"}}]
MSGS = [{"role": "user", "content": "q"}]


def message_body():
    """The created (non-streamed) answer: a thinking block and one read call."""
    return {"id": "msg_fake", "type": "message", "role": "assistant", "model": "claude-haiku-5-5",
            "content": [{"type": "thinking", "thinking": "", "signature": "sig-1"},
                        {"type": "tool_use", "id": "toolu_1", "name": "breakdown", "input": ARGS}],
            "stop_reason": "tool_use", "stop_sequence": None, "usage": dict(USAGE)}


def sse(stall_after_start=0.0):
    """The same answer as server-sent events; optionally silent for `stall_after_start` s after the thinking block
    starts (a long think streams as silence)."""
    start = dict(USAGE, output_tokens=1)
    evs = [("message_start", {"type": "message_start", "message": {
        "id": "msg_fake", "type": "message", "role": "assistant", "model": "claude-haiku-5-5", "content": [],
        "stop_reason": None, "stop_sequence": None, "usage": start}}),
        ("content_block_start", {"type": "content_block_start", "index": 0,
                                 "content_block": {"type": "thinking", "thinking": "", "signature": ""}}),
        ("STALL", None),
        ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                 "delta": {"type": "signature_delta", "signature": "sig-1"}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("content_block_start", {"type": "content_block_start", "index": 1, "content_block": {
            "type": "tool_use", "id": "toolu_1", "name": "breakdown", "input": {}}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 1,
                                 "delta": {"type": "input_json_delta", "partial_json": json.dumps(ARGS)}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 1}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "tool_use", "stop_sequence": None},
                           "usage": {"output_tokens": USAGE["output_tokens"]}}),
        ("message_stop", {"type": "message_stop"})]

    def gen():
        for name, data in evs:
            if name == "STALL":
                if stall_after_start:
                    time.sleep(stall_after_start)
                continue
            yield f"event: {name}\ndata: {json.dumps(data)}\n\n".encode()
    return gen


def transport(answers):
    """sdk_transport, plus streamed answers: {"sse": gen} is answered as text/event-stream."""
    import httpx2
    seen, queue = [], list(answers)

    def handler(request):
        seen.append({"url": str(request.url), "body": json.loads(request.content or b"{}")})
        a = queue.pop(0)
        if "sse" in a:
            return httpx2.Response(200, content=a["sse"](), headers={"content-type": "text/event-stream",
                                                                       "request-id": "req_fake"})
        return httpx2.Response(a.get("status", 200), json=a.get("json"), headers={"request-id": "req_fake"})
    return httpx2.MockTransport(handler), seen


def provider(cl, monkeypatch, answers, **kw):
    tr, seen = transport(answers)
    monkeypatch.setattr(cl["ai"], "ANTHROPIC_TRANSPORT", tr)
    from mvp.brain import provider as P
    return P, P.AnthropicProvider(prompt_version="t28", **kw), seen


def test_streamed_request_sends_the_same_body_and_gives_the_same_reply_with_its_timing(cl, monkeypatch):
    P, created, seen = provider(cl, monkeypatch, [{"json": message_body()}], stream=False)
    a = created.send(SYSTEM, TOOLS, MSGS, timeout=10)
    _, streamed, seen2 = provider(cl, monkeypatch, [{"sse": sse()}], stream=True)
    b = streamed.send(SYSTEM, TOOLS, MSGS, timeout=10)
    body1, body2 = seen[0]["body"], dict(seen2[0]["body"])
    assert body2.pop("stream") is True and body1 == body2          # what the model reads: byte for byte the same
    assert a.timing is None and b.timing is not None
    assert (a.stop_reason, a.usage) == (b.stop_reason, b.usage) == ("tool_use", USAGE)
    key = lambda bl: [(x["type"], x.get("signature"), x.get("id"), x.get("name"), x.get("input")) for x in bl]
    assert key(a.blocks) == key(b.blocks)
    # the conversation gets plain blocks with only the fields the API takes back
    assert b.raw == [{"type": "thinking", "thinking": "", "signature": "sig-1"},
                     {"type": "tool_use", "id": "toolu_1", "name": "breakdown", "input": ARGS}]
    t = b.timing
    assert t["message_start"] is not None and t["events"] >= 8 and [x["type"] for x in t["blocks"]] == [
        "thinking", "tool_use"] and t["end"] >= t["message_start"]
    assert [r["prompt_version"] for r in rows(cl)] == ["t28", "t28"]   # each billed request logged once


def test_the_wall_clock_holds_during_a_silent_think_and_the_timing_so_far_is_kept(cl, monkeypatch):
    P, prov, _ = provider(cl, monkeypatch, [{"sse": sse(stall_after_start=3.0)}], stream=True)
    t0 = time.monotonic()
    with pytest.raises(P.ProviderError) as e:
        prov.send(SYSTEM, TOOLS, MSGS, timeout=1.0)
    took = time.monotonic() - t0
    assert e.value.kind == "ClaudeTimeout" and took < 1.6          # not the 3 s of silence, not 2 x the limit
    t = e.value.timing
    assert t["message_start"] is not None and t["blocks"][0]["type"] == "thinking" and "stop" not in t["blocks"][0]
    est = rows(cl)
    assert len(est) == 1 and est[0]["prompt_version"] == "t28+estimate"   # sent, maybe billed: the cap counts it


def test_the_loop_keeps_a_failed_requests_timing_in_the_turn_record(cl, monkeypatch):
    from mvp.brain import loop as BL, provider as P

    class Failing:
        max_tokens = 4000

        def send(self, *a, **k):
            raise P.ProviderError("ClaudeTimeout", 0, 9.5, timing={"message_start": 0.6, "blocks": []})

    class T:
        message, screen, results, unlock, carried_unlock, limits, windows = "q", "", {}, None, None, [], {}

    monkeypatch.setattr(BL.V.Turn, "of", staticmethod(lambda t: None))
    monkeypatch.setattr(BL, "_finish", lambda *a, **k: None)
    rec = BL.run_turn(Failing(), T(), "q", {}, system="s", tools=[], check="values")
    assert rec["error"] == "ClaudeTimeout" and rec["failed_request"] == {
        "seconds": 9.5, "timing": {"message_start": 0.6, "blocks": []}}


def test_a_created_request_records_no_timing_key(cl, monkeypatch):
    from mvp.brain import loop as BL, provider as P
    fake = P.FakeProvider(script=[[P.text("hi")], [P.text("hi")]])
    rec = {"requests": []}
    r = fake.send("s", [], [])
    assert r.timing is None
    # loop.send's record of a request without timing has exactly the mvp27 keys
    q = {"stop_reason": r.stop_reason, "usage": r.usage, "seconds": r.seconds, "cost_usd": r.cost_usd,
         "retries": r.retries, "blocks": r.blocks}
    assert "timing" not in q and rec["requests"] == []
    src = open(BL.__file__, encoding="utf-8").read()
    assert 'if getattr(r, "timing", None):' in src


def test_warm_opens_one_connection_per_worker_with_free_count_tokens_and_logs_nothing(cl, monkeypatch):
    answers = [{"json": {"input_tokens": 50}} for _ in range(3)]
    P, prov, seen = provider(cl, monkeypatch, answers)
    secs = prov.warm(SYSTEM, TOOLS, connections=3)
    assert secs >= 0 and len(seen) == 3 and all(s["url"].endswith("/v1/messages/count_tokens") for s in seen)
    assert rows(cl) == [] and prov.spent == 0 and prov.requests == 0


def test_stream_is_on_by_default_and_the_created_request_stays_one_switch_away(cl, monkeypatch):
    from mvp.brain import provider as P
    assert P.STREAM is True and P.AnthropicProvider(prompt_version="x").stream is True
    assert P.AnthropicProvider(prompt_version="x", stream=False).stream is False
    assert P.AnthropicProvider(prompt_version="x").settings()["stream"] is True


def test_strict_off_waits_behind_a_switch_that_is_off_by_default(cl, monkeypatch):
    from mvp.brain import provider as P
    on = P.AnthropicProvider(prompt_version="x")
    assert P.STRICT is True and [("strict" in d) for d in on.body("s", TOOLS, MSGS)["tools"]] == [True, False]
    for m in [m for m in sys.modules if m.startswith("mvp.brain")]:
        del sys.modules[m]
    monkeypatch.setenv("MVP_BRAIN_STRICT", "0")
    from mvp.brain import provider as P2
    off = P2.AnthropicProvider(prompt_version="x")
    assert P2.STRICT is False and all("strict" not in d for d in off.body("s", TOOLS, MSGS)["tools"])
    # what the model reads is otherwise the same body
    a, b = on.body("s", TOOLS, MSGS), off.body("s", TOOLS, MSGS)
    a["tools"] = [{k: v for k, v in d.items() if k != "strict"} for d in a["tools"]]
    assert a == b


def test_thinking_off_is_still_only_the_tuners_switch(cl, monkeypatch):
    from mvp.brain import provider as P
    assert P.THINKING == "adaptive" and P.AnthropicProvider(prompt_version="x").body("s", TOOLS, MSGS)[
        "thinking"] == {"type": "adaptive"}


def test_the_eval_warms_the_client_before_the_first_timed_turn_unless_switched_off():
    src = open(os.path.join(os.path.dirname(HERE), "eval_brain.py"), encoding="utf-8").read()
    i, j = src.index('os.environ.get("MVP_BRAIN_WARM", "1") == "1"'), src.index("with ThreadPoolExecutor(max_workers")
    assert i < j and "prov.warm(" in src[i:j] and "warm_s=warm_s" in src
