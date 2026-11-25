"""PROTOTYPE ONLY - the brain's model provider (design/brain_v1/SPEC.md 3.2), the thin live slice of step 2.

One small interface: `send(system, tools, messages, max_tokens=None) -> Reply` (the content blocks, the stop reason,
the usage, the seconds, the cost). Two implementations:

- `AnthropicProvider`: one Messages request through lib/ai.py's client (`ai.anthropic_client()`: the key by name,
  no ambient settings, no SDK retries). Settings for claude-haiku-5-5 from the claude-api skill (cached 2026-11-03):
  adaptive thinking with an explicit `output_config.effort` (Haiku 5.5 defaults to medium; the effort is held
  constant for a whole run, since a change invalidates the messages cache); `tool_choice` auto (a forced call skips
  thinking on Haiku 5.5); `strict: true` on the nine read tools (not on give_answer: ten strict tools are a 400,
  "compiled grammar is too large"); no temperature / top_p / top_k (non-default values are a 400);
  no `fallbacks` (Haiku 5.5 has no server-side fallback); no prefill. Caching: one 5-minute breakpoint on the system
  block (it covers the tool schemas before it and the system text: the stable prefix) and the top-level automatic
  breakpoint on the growing tail, so round 2 of a turn reads round 1. Haiku 5.5 caches a prefix of 512 tokens or more;
  the 5-minute TTL only (lib/ai_prices.json holds the 5-minute write rate). Every request is checked against the
  Claude cap first (`ai._guard`, with this process's requests still waiting) and logged with `ai.log_batch`
  (provider "anthropic", purpose "brain_eval", the prompt version). A rate-limit or overloaded answer is retried
  after a back-off (2 s, 5 s), then raised.
- `FakeProvider`: replays scripted turns (each a list of content blocks as dicts, or a callable of the messages so
  far); no network, no money. Every test of the loop uses it.

Replay: the content of a reply is appended to the conversation unchanged (`Reply.raw`: the SDK's own block objects,
thinking blocks with their empty text and signature included), so the turn stays append-only; `Reply.blocks` is a
JSON copy for the record.
"""
import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

MODEL = os.environ.get("MVP_BRAIN_MODEL", "claude-haiku-5-5")
EFFORT = os.environ.get("MVP_BRAIN_EFFORT", "low")
THINKING = os.environ.get("MVP_BRAIN_THINKING", "adaptive")   # "adaptive" (the skill's advice) or "disabled" (Haiku
#                                                               5.5 takes it at effort high or below): a tuner's knob
MAX_TOKENS = int(os.environ.get("MVP_BRAIN_MAX_TOKENS", "4000"))
PURPOSE = "brain_eval"
RETRY_STATUS = (429, 500, 503, 529)
BACKOFF_S = (2.0, 5.0)
# strict on the nine read tools; give_answer is sent without it: with all ten strict the API answers 400 "The compiled
# grammar is too large" (first live request, 26 Nov 2026). The loop validates the form with Pydantic anyway.
LOOSE = ("give_answer",)


class ProviderError(RuntimeError):
    """No usable reply: `kind` is the reason in code's words (no request or reply text in it)."""

    def __init__(self, kind, retries=0, seconds=0.0):
        self.kind, self.retries, self.seconds = kind, retries, seconds
        super().__init__(f"provider failed: {kind}")


@dataclass
class Reply:
    blocks: list                    # JSON copy of the content blocks ({"type": ...}), for the record
    raw: Any                        # what is appended to the conversation (SDK blocks, or the dicts of a fake)
    stop_reason: str
    usage: dict                     # input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens
    seconds: float
    cost_usd: float = 0.0
    model: str = ""
    retries: int = 0

    def tool_uses(self):
        return [b for b in self.blocks if b.get("type") == "tool_use"]

    def text(self):
        return "".join(b.get("text") or "" for b in self.blocks if b.get("type") == "text")


def _usage_of(u):
    def g(k):
        return (u.get(k) if isinstance(u, dict) else getattr(u, k, None)) or 0
    return {"input_tokens": g("input_tokens"), "output_tokens": g("output_tokens"),
            "cache_read_input_tokens": g("cache_read_input_tokens"),
            "cache_creation_input_tokens": g("cache_creation_input_tokens")}


def _block_json(b):
    if isinstance(b, dict):
        return dict(b)
    d = b.model_dump(mode="json", exclude_none=True) if hasattr(b, "model_dump") else dict(vars(b))
    return d


def tool_defs(tools, strict=True, loose=()):
    """The tools as sent: name, description, input_schema, and `strict` (left off for names in `loose`)."""
    out = []
    for t in tools:
        d = {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
        if strict and t["name"] not in loose:
            d["strict"] = True
        out.append(d)
    return out


class AnthropicProvider:
    """claude-haiku-5-5 (or MVP_BRAIN_MODEL) through lib/ai.py's client. Thread-safe: requests may run in parallel."""

    def __init__(self, model=MODEL, effort=EFFORT, max_tokens=MAX_TOKENS, prompt_version="", purpose=PURPOSE,
                 thinking=THINKING,
                 strict=True, loose=LOOSE, cache=True, timeout=30.0, log=True):
        from .. import llm   # sets the ledger home (MVP_LEDGER_HOME) and the Claude cap before lib/ai.py is used
        self.ai = llm.ai
        self.model, self.effort, self.max_tokens = model, effort, max_tokens
        if thinking not in ("adaptive", "disabled"):
            raise ValueError(f"thinking is adaptive or disabled, not {thinking!r}")
        self.thinking = thinking
        self.prompt_version, self.purpose = prompt_version, purpose
        self.strict, self.loose, self.cache, self.timeout, self.log = strict, tuple(loose), cache, timeout, log
        self.spent = 0.0
        self.requests = 0
        self._lock = threading.Lock()

    def settings(self):
        return {"model": self.model, "thinking": {"type": self.thinking}, "effort": self.effort,
                "max_tokens": self.max_tokens, "tool_choice": "auto", "strict": self.strict,
                "strict_off_for": list(self.loose), "cache": "5m on the system block + automatic tail" if self.cache
                else "off", "fallbacks": None, "sampling": None}

    def body(self, system, tools, messages, max_tokens=None):
        sysb = {"type": "text", "text": system}
        if self.cache:
            sysb["cache_control"] = {"type": "ephemeral"}
        b = {"model": self.model, "max_tokens": max_tokens or self.max_tokens, "system": [sysb],
             "tools": tool_defs(tools, self.strict, self.loose), "tool_choice": {"type": "auto"},
             "thinking": {"type": self.thinking}, "output_config": {"effort": self.effort}, "messages": messages}
        if self.cache:
            b["cache_control"] = {"type": "ephemeral"}
        return b

    def send(self, system, tools, messages, max_tokens=None, timeout=None):
        ai = self.ai
        body = self.body(system, tools, messages, max_tokens)
        est_in = len(json.dumps([system, body["tools"], messages], default=str)) / 3.5
        with ai._pending_lock:
            p = ai._guard("anthropic", self.model, est_in, body["max_tokens"], pending=ai._pending["usd"])
            hold = est_in / 1e6 * p["input_per_m"] + body["max_tokens"] / 1e6 * p.get("output_per_m", 0)
            ai._pending["usd"] += hold
        t0 = time.time()
        retries = 0
        try:
            client = ai.anthropic_client()
            while True:
                try:
                    r = client.beta.messages.create(**body, timeout=timeout or self.timeout)
                    break
                except Exception as e:  # noqa: BLE001 - the SDK's errors become ours, without the request
                    mine = ai._sdk_error(e) if not isinstance(e, (ai.ClaudeHTTPError, ai.ClaudeTimeout,
                                                                  ai.ClaudeConnection)) else e
                    if mine is None:
                        raise
                    if isinstance(mine, ai.ClaudeHTTPError) and mine.status in RETRY_STATUS and \
                            retries < len(BACKOFF_S):
                        time.sleep(BACKOFF_S[retries])
                        retries += 1
                        continue
                    kind = (f"http {mine.status} {mine.kind}" if isinstance(mine, ai.ClaudeHTTPError)
                            else type(mine).__name__)
                    raise ProviderError(kind, retries, round(time.time() - t0, 2)) from None
        finally:
            with ai._pending_lock:
                ai._pending["usd"] = max(0.0, ai._pending["usd"] - hold)
        secs = round(time.time() - t0, 2)
        cost, _assumed, _served = ai.claude_cost(self.model, r.usage)
        usage = _usage_of(r.usage)
        if self.log:
            # in_tokens: the whole prompt (uncached + cache read + cache write); the cost prices each part
            ai.log_batch("anthropic", self.model, self.purpose, 1,
                         usage["input_tokens"] + usage["cache_read_input_tokens"] + usage["cache_creation_input_tokens"],
                         usage["output_tokens"], cost, secs, prompt_version=self.prompt_version)
        with self._lock:
            self.spent += cost
            self.requests += 1
        return Reply(blocks=[_block_json(b) for b in r.content], raw=list(r.content), stop_reason=r.stop_reason,
                     usage=usage, seconds=secs, cost_usd=cost, model=getattr(r, "model", self.model),
                     retries=retries)

    def count_tokens(self, system, tools, messages):
        """Input tokens of a request (free; nothing is billed or logged)."""
        b = self.body(system, tools, messages)
        b.pop("max_tokens", None)
        b.pop("cache_control", None)
        r = self.ai.anthropic_client().beta.messages.count_tokens(**b)
        return r.input_tokens


@dataclass
class FakeProvider:
    """Replays scripted turns. Each script entry is a list of content blocks (dicts), a dict
    {"blocks": [...], "stop_reason": ..., "usage": {...}, "seconds": s, "cost_usd": c}, a callable
    (messages) -> either of those, or an Exception instance (raised as that request's failure)."""
    script: list
    sent: list = field(default_factory=list)      # (system, tools, messages copy) of each request
    clock: Optional[Callable] = None

    def settings(self):
        return {"model": "fake"}

    def send(self, system, tools, messages, max_tokens=None, timeout=None):
        self.sent.append((system, tools, json.loads(json.dumps(messages, default=str))))
        if not self.script:
            raise ProviderError("fake script ended")
        step = self.script.pop(0)
        if callable(step):
            step = step(messages)
        if isinstance(step, Exception):
            raise step
        if isinstance(step, list):
            step = {"blocks": step}
        blocks = [dict(b) for b in step["blocks"]]
        stop = step.get("stop_reason") or ("tool_use" if any(b.get("type") == "tool_use" for b in blocks)
                                           else "end_turn")
        usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
                 "cache_creation_input_tokens": 0, **(step.get("usage") or {})}
        secs = float(step.get("seconds", 0.0))
        if self.clock is not None:
            self.clock(secs)
        return Reply(blocks=blocks, raw=[dict(b) for b in blocks], stop_reason=stop, usage=usage, seconds=secs,
                     cost_usd=float(step.get("cost_usd", 0.0)), model="fake")


_ids = {"n": 0}
_ids_lock = threading.Lock()


def tool_use(name, args, id_=None):
    """A tool_use block for a fake script."""
    with _ids_lock:
        _ids["n"] += 1
        n = _ids["n"]
    return {"type": "tool_use", "id": id_ or f"toolu_fake{n:04d}", "name": name, "input": args}


def text(t):
    return {"type": "text", "text": t}
