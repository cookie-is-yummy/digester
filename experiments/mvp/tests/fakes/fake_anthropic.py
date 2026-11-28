"""A fake Anthropic (Claude) client for tests and eval_models.py --dry (DESIGN.md section 20). No network, no money.

Two levels:

    from mvp.tests.fakes.fake_anthropic import FakeAnthropic, sdk_transport
    fake = FakeAnthropic(['{"intent": "chat"}'])      # replies in order: a str (the text), a dict (see reply()),
    fake.install(monkeypatch)                         # or a callable(body) -> one of those
    ... fake.calls -> [the keyword arguments of each messages.create]; fake.keys / fake.base_urls -> what it was built with

    transport, seen = sdk_transport([{"status": 200, "json": message_json("{...}")}])
    monkeypatch.setattr(ai, "ANTHROPIC_TRANSPORT", transport)   # the real SDK client over a fake transport
    ... seen -> [{"url", "headers", "body"}]

FakeAnthropic stands where the SDK client stands (ai.ANTHROPIC_CLIENT): `.beta.messages.create(**body)` returns an
object shaped like the SDK's BetaMessage (stop_reason, content blocks, usage, model, stop_details). sdk_transport
answers the SDK's own HTTP requests, so the SDK's request building, its response types and its errors run for real.
"""
import json
from types import SimpleNamespace


def reply(text="{}", stop_reason="end_turn", input_tokens=120, output_tokens=40, model=None, cache_read=0,
          cache_write=0, category=None, iterations=None):
    """One fake answer as a dict (FakeAnthropic turns it into the message object)."""
    return {"text": text, "stop_reason": stop_reason, "input_tokens": input_tokens, "output_tokens": output_tokens,
            "model": model, "cache_read": cache_read, "cache_write": cache_write, "category": category,
            "iterations": iterations}


class FakeAnthropic:
    def __init__(self, answers=None, default=None):
        self.answers = list(answers or [])
        self.default = default          # used once the list is empty (None: a call past the list fails the test)
        self.calls, self.keys, self.base_urls = [], [], []
        outer = self

        class _Messages:
            def create(self, **body):
                return outer._create(body)

        self.beta = SimpleNamespace(messages=_Messages())
        self.messages = self.beta.messages

    # ai.anthropic_client calls ANTHROPIC_CLIENT(api_key=..., base_url=...)
    def __call__(self, api_key=None, base_url=None, **_kw):
        self.keys.append(api_key)
        self.base_urls.append(base_url)
        return self

    def _create(self, body):
        self.calls.append(body)
        if self.answers:
            a = self.answers.pop(0)
        elif self.default is not None:
            a = self.default
        else:
            raise AssertionError("FakeAnthropic: a call past the answers given")
        if callable(a):
            a = a(body)
        if isinstance(a, BaseException):
            raise a
        if isinstance(a, str):
            a = reply(a)
        a = {**reply(), **a}
        content = [SimpleNamespace(type="text", text=a["text"])] if a["text"] is not None else []
        usage = SimpleNamespace(input_tokens=a["input_tokens"], output_tokens=a["output_tokens"],
                                cache_read_input_tokens=a["cache_read"], cache_creation_input_tokens=a["cache_write"],
                                iterations=[SimpleNamespace(**i) for i in a["iterations"]] if a["iterations"] else None)
        details = SimpleNamespace(type="refusal", category=a["category"], explanation=None) \
            if a["stop_reason"] == "refusal" else None
        return SimpleNamespace(id="msg_fake", type="message", role="assistant", model=a["model"] or body.get("model"),
                               content=content, stop_reason=a["stop_reason"], stop_details=details, usage=usage)

    def install(self, monkeypatch):
        from mvp import llm
        monkeypatch.setattr(llm.ai, "ANTHROPIC_CLIENT", self)
        return self


# ---------- the real SDK over a fake transport ----------
def message_json(text, stop_reason="end_turn", model="claude-haiku-5-5", input_tokens=120, output_tokens=40,
                 category=None):
    """The JSON body of one Messages API answer."""
    body = {"id": "msg_fake", "type": "message", "role": "assistant", "model": model,
            "content": [{"type": "text", "text": text}] if text is not None else [],
            "stop_reason": stop_reason, "stop_sequence": None,
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens,
                      "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}
    if stop_reason == "refusal":
        body["stop_details"] = {"type": "refusal", "category": category, "explanation": None}
    return body


def error_json(kind="authentication_error", message="invalid x-api-key"):
    return {"type": "error", "error": {"type": kind, "message": message}}


def sdk_transport(answers):
    """(httpx2.MockTransport, seen): each request the SDK sends is kept in `seen` (url, headers, body) and answered
    with the next of `answers` ({"status", "json"}, or an exception instance to raise)."""
    import httpx2
    seen, queue = [], list(answers)

    def handler(request):
        seen.append({"url": str(request.url), "headers": dict(request.headers),
                     "body": json.loads(request.content or b"{}")})
        a = queue.pop(0) if queue else {"status": 500, "json": error_json("api_error", "no answer left")}
        if isinstance(a, BaseException):
            raise a
        return httpx2.Response(a.get("status", 200), json=a.get("json"), headers={"request-id": "req_fake"})
    return httpx2.MockTransport(handler), seen
