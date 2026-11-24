"""PROTOTYPE ONLY - every paid AI call in experiments goes through here.

- Keys come from environment variables only: OPENAI_API_KEY, GEMINI_API_KEY, and for Claude
  DIGESTER_ANTHROPIC_API_KEY (then ANTHROPIC_API_KEY). Never write, print or log them.
- Each call is logged to $DIGESTER_DATA/ai_runs.jsonl: provider, model, purpose, tokens, cost, seconds
  (AGENTS.md rule 11).
- Hard budget per provider: a call is refused if that provider's spend so far, plus a worst-case
  estimate for the call, would pass its cap. Spend is read back from the ledger, so caps hold across
  processes and sessions. Caps:
    DIGESTER_OPENAI_BUDGET_USD  (default 4.00)
    DIGESTER_GEMINI_BUDGET_USD  (default 4.00)
    DIGESTER_ANTHROPIC_BUDGET_USD  (default 4.00)
- Prices come from lib/ai_prices.json. Check them against the provider's pricing page before the first
  paid run and record the date. A model with no price entry is refused.
- Ledger costs are estimates from list prices. Compare them with the provider's billing page now and
  then, and note any gap in STATE.md.
"""
import base64
import json
import os
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("DIGESTER_DATA", os.path.join(os.path.dirname(os.path.dirname(HERE)), "data"))
LEDGER = os.path.join(DATA, "ai_runs.jsonl")
GEMINI = "https://generativelanguage.googleapis.com/v1beta"


def budget(provider):
    return float(os.environ.get(f"DIGESTER_{provider.upper()}_BUDGET_USD", "4.00"))


def prices():
    return json.load(open(os.path.join(HERE, "ai_prices.json")))["models"]


def spent(provider=None):
    if not os.path.exists(LEDGER):
        return 0.0
    rows = [json.loads(l) for l in open(LEDGER)]
    return sum(r.get("cost_usd", 0) for r in rows if provider is None or r.get("provider") == provider)


def _guard(provider, model, est_in_tokens, max_out_tokens, pending=0.0):
    """pending (Claude only, section 20 review): the worst case of this process's calls still waiting for an answer,
    so two calls at the cap cannot both pass it."""
    p = prices().get(model)
    if p is None:
        raise RuntimeError(f"no verified price for {model}; add it to lib/ai_prices.json first")
    est = est_in_tokens / 1e6 * p["input_per_m"] + max_out_tokens / 1e6 * p.get("output_per_m", 0)
    if spent(provider) + pending + est > budget(provider):
        raise RuntimeError(f"budget stop ({provider}): spent ${spent(provider):.3f} + est ${est:.3f} > ${budget(provider):.2f}"
                           + (f" (${pending:.3f} of it on calls still waiting)" if pending else ""))
    return p


def _log(row):
    os.makedirs(DATA, exist_ok=True)
    row = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **row}
    with open(LEDGER, "a") as f:
        f.write(json.dumps(row) + "\n")


TIMEOUT = 300  # seconds for one call; a caller that answers people in real time lowers it


def _post(url, body, headers):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


# ---------------- OpenAI ----------------
def _oa():
    return {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}


def openai_embed(texts, model="text-embedding-3-small", dimensions=None, purpose=""):
    p = _guard("openai", model, sum(len(t) for t in texts) / 3.5, 0)
    t = time.time()
    body = {"model": model, "input": texts}
    if dimensions:
        body["dimensions"] = dimensions
    r = _post("https://api.openai.com/v1/embeddings", body, _oa())
    tok = r["usage"]["total_tokens"]
    _log({"provider": "openai", "model": model, "purpose": purpose, "n": len(texts), "in_tokens": tok,
          "out_tokens": 0, "cost_usd": tok / 1e6 * p["input_per_m"], "seconds": round(time.time() - t, 2)})
    return [d["embedding"] for d in r["data"]]


def openai_chat_json(model, system, user, max_tokens=400, purpose="", prompt_version="", **extra):
    """One chat call that must return a JSON object. Returns (parsed_json, usage)."""
    p = _guard("openai", model, (len(system) + len(user)) / 3.5, max_tokens)
    t = time.time()
    body = {"model": model, "response_format": {"type": "json_object"}, "max_completion_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], **extra}
    r = _post("https://api.openai.com/v1/chat/completions", body, _oa())
    u = r["usage"]
    cost = u["prompt_tokens"] / 1e6 * p["input_per_m"] + u["completion_tokens"] / 1e6 * p["output_per_m"]
    row = {"provider": "openai", "model": model, "purpose": purpose, "prompt_version": prompt_version, "n": 1,
           "in_tokens": u["prompt_tokens"], "out_tokens": u["completion_tokens"], "cost_usd": cost,
           "seconds": round(time.time() - t, 2)}
    cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens")
    if cached is not None:  # optional: prompt-cache hits (cost_usd above stays at the uncached list price)
        row["cached_tokens"] = cached
    _log(row)
    return json.loads(r["choices"][0]["message"]["content"]), u


# ---------------- Anthropic (Claude) ----------------
# Text calls only, through the official SDK (`anthropic`, imported on the first Claude call, so the OpenAI and Gemini
# paths work without it). The key is read from DIGESTER_ANTHROPIC_API_KEY, then ANTHROPIC_API_KEY, by name; it is
# never printed, logged or put in an error. The client is built with an explicit base URL and the explicit key, so
# nothing of the ambient ANTHROPIC_* settings (a base URL, an auth token, a profile, extra headers, the SDK's own
# logging) reaches it. No retries (as the OpenAI path) and TIMEOUT per call. A refusal, a cut by max_tokens or a reply
# with no JSON object raises ClaudeStop (a ValueError, as a JSON parse failure is on the OpenAI path), after the
# call's row is in the ledger (it was billed).
ANTHROPIC_URL = "https://api.anthropic.com"
ANTHROPIC_KEY_NAMES = ("DIGESTER_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY")
ANTHROPIC_FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Ambient names the SDK would read while a client is built; they are hidden for that moment (a lock keeps two builds
# from racing). The bot's own two key names are read here, never by the SDK.
_SDK_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "ANTHROPIC_CUSTOM_HEADERS",
            "ANTHROPIC_PROFILE", "ANTHROPIC_CONFIG_DIR", "ANTHROPIC_WEBHOOK_SIGNING_KEY", "ANTHROPIC_IDENTITY_TOKEN",
            "ANTHROPIC_IDENTITY_TOKEN_FILE", "ANTHROPIC_FEDERATION_RULE_ID", "ANTHROPIC_ORGANIZATION_ID",
            "ANTHROPIC_SERVICE_ACCOUNT_ID", "ANTHROPIC_WORKSPACE_ID", "ANTHROPIC_LOG")
JSON_LINE = "Reply with one JSON object only: no other text before or after it, no code fence."
ANTHROPIC_CLIENT = None    # tests put a fake here (tests/fakes/fake_anthropic.py); None: the SDK client, built once
ANTHROPIC_TRANSPORT = None  # tests: an httpx2 transport under the real SDK client (nothing leaves the process)
_client_cache = {}
_client_lock = threading.Lock()


class MissingKey(RuntimeError):
    """No Claude key in the environment. Never falls back to another provider."""


class ClaudeStop(ValueError):
    """The reply holds no usable JSON: a refusal, a cut by max_tokens, no text, or text that is not one JSON object.
    `stop_reason` says which; the message never holds the reply's text."""

    def __init__(self, stop_reason, detail=""):
        self.stop_reason = stop_reason
        super().__init__(f"claude stopped: {stop_reason}" + (f" ({detail})" if detail else ""))


class ClaudeHTTPError(RuntimeError):
    """The API answered with an error (nothing billed). Only the status, the error type and the host are kept."""

    def __init__(self, status, kind, host):
        self.status, self.kind, self.host = status, kind, host
        super().__init__(f"anthropic http {status} {kind} from {host}")


class ClaudeTimeout(TimeoutError):
    """Sent, but no answer in TIMEOUT seconds: the server may still finish and bill it."""


class ClaudeConnection(ConnectionError):
    """No answer for a network reason. `maybe_sent` is False only when the connection was never made."""

    def __init__(self, maybe_sent, kind):
        self.maybe_sent = maybe_sent
        super().__init__(f"anthropic connection failed: {kind}")


def anthropic_key():
    """(name, value) of the first of ANTHROPIC_KEY_NAMES that is set. Raises MissingKey naming both variables.
    Read under the client lock: a client being built hides ANTHROPIC_API_KEY for a moment."""
    with _client_lock:
        found = [(n, (os.environ.get(n) or "").strip()) for n in ANTHROPIC_KEY_NAMES]
    for name, v in found:
        if v:
            return name, v
    raise MissingKey(f"no Claude key: set {ANTHROPIC_KEY_NAMES[0]} (or {ANTHROPIC_KEY_NAMES[1]}) in the environment "
                     f"to use a claude- model; nothing was sent")


def anthropic_client(key=None):
    """The client for the key now in the environment (or `key`, for the path test: never cached): a fake when
    ANTHROPIC_CLIENT is set, else the SDK's own."""
    explicit = key is not None
    if not explicit:
        _name, key = anthropic_key()
    if ANTHROPIC_CLIENT is not None:
        return ANTHROPIC_CLIENT(api_key=key, base_url=ANTHROPIC_URL)
    with _client_lock:
        c = _client_cache.get("client")
        if (c is not None and _client_cache.get("key") == key and not explicit
                and _client_cache.get("transport") is ANTHROPIC_TRANSPORT):
            return c
        import logging
        hidden = {n: os.environ.pop(n) for n in _SDK_ENV if n in os.environ}
        try:
            import anthropic
            kw = {}
            if ANTHROPIC_TRANSPORT is not None:   # tests: the real SDK over a fake transport (no network)
                kw["http_client"] = anthropic.DefaultHttpxClient(transport=ANTHROPIC_TRANSPORT)
            c = anthropic.Anthropic(api_key=key, base_url=ANTHROPIC_URL, max_retries=0, webhook_key="",
                                    open_telemetry=False, **kw)
        finally:
            os.environ.update(hidden)
        # the SDK reads ANTHROPIC_LOG once, at import: whatever it said, its request logs stay off here
        for n in ("anthropic", "httpx2", "httpcore2", "httpx", "httpcore"):
            logging.getLogger(n).setLevel(logging.WARNING)
        if not explicit:
            _client_cache.update(client=c, key=key, transport=ANTHROPIC_TRANSPORT)
        return c


PATH_TEST_KEY = "invalid-key-for-path-test"


def anthropic_path_test(model="claude-haiku-5-5"):
    """One request with an obviously invalid key, through the same client the bot builds: an authentication error
    from api.anthropic.com shows that DNS, the proxy, TLS and the base URL are right. Nothing is billed or logged.
    Returns {"ok", "status", "kind", "host"} (ok: the answer was 401 authentication_error from that host)."""
    client = anthropic_client(key=PATH_TEST_KEY)
    try:
        client.beta.messages.create(model=model, max_tokens=1, messages=[{"role": "user", "content": "ping"}],
                                    timeout=30)
    except Exception as e:  # noqa: BLE001
        mine = _sdk_error(e) or e
        if isinstance(mine, ClaudeHTTPError):
            return {"ok": mine.status == 401 and mine.kind == "authentication_error"
                    and mine.host == ANTHROPIC_URL.split("//")[1], "status": mine.status, "kind": mine.kind,
                    "host": mine.host}
        return {"ok": False, "status": None, "kind": type(mine).__name__, "host": None, "detail": str(mine)[:200]}
    return {"ok": False, "status": 200, "kind": "accepted an invalid key", "host": None}


def claude_thinking(model, mode, effort):
    """(thinking, effort) to send. mode "adaptive": {"type": "adaptive"}. mode "off" (the default for the small form
    calls): Haiku 5.5 takes {"type": "disabled"} and Sonnet 5.5 {"type": "between_tools"}, each only at effort high or
    below (a higher effort is lowered to high); Opus 5.5 cannot turn thinking off, so nothing is sent and the effort
    is the only control. None means "send no thinking field"."""
    if mode == "adaptive":
        return {"type": "adaptive"}, effort
    off = {"claude-haiku-5-5": {"type": "disabled"}, "claude-sonnet-5-5": {"type": "between_tools"}}.get(model)
    if off and effort in ("xhigh", "max"):
        effort = "high"
    return off, effort


def claude_price(p, in_tokens):
    """(input, output, cache read, cache write) per M tokens; a long-prompt rate card when the entry has one."""
    long_ = p.get("long_prompt_over_tokens")
    if long_ and in_tokens > long_:
        li = p["long_input_per_m"]
        return (li, p["long_output_per_m"], p.get("long_cache_read_per_m", 0.1 * li),
                p.get("long_cache_write_per_m", 1.25 * li))
    return (p["input_per_m"], p["output_per_m"], p.get("cache_read_per_m", 0.1 * p["input_per_m"]),
            p.get("cache_write_per_m", 1.25 * p["input_per_m"]))


def claude_cost(model, usage):
    """Cost of one reply from its usage. With a server-side fallback, `usage.iterations` holds every attempt, each
    priced at its own model (a model with no price entry at the requested model's price, marked in the row)."""
    table = prices()
    req = table[model]
    its = [i for i in (_field(usage, "iterations") or []) if _field(i, "type") in ("message", "fallback_message")]
    parts = its or [usage]
    cost, assumed, served = 0.0, False, []
    for it in parts:
        m = _field(it, "model") or model
        p = table.get(m)
        if p is None or p.get("provider") != "anthropic":
            p, assumed = req, True
        tin = _field(it, "input_tokens") or 0
        cr, cw = _field(it, "cache_read_input_tokens") or 0, _field(it, "cache_creation_input_tokens") or 0
        pi, po, pr, pw = claude_price(p, tin + cr + cw)
        cost += (tin * pi + (_field(it, "output_tokens") or 0) * po + cr * pr + cw * pw) / 1e6
        served.append(m)
    return cost, assumed, served


def _field(o, k):
    return o.get(k) if isinstance(o, dict) else getattr(o, k, None)


def parse_json_object(text):
    """The first complete JSON object of a reply, read strictly: only white space (or a ```json fence) may come before
    it. Raises ClaudeStop("not_json") otherwise; anything after the object is ignored."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
    t = t.lstrip()
    if not t.startswith("{"):
        raise ClaudeStop("not_json", "no object at the start")
    try:
        obj, _end = json.JSONDecoder().raw_decode(t)
    except ValueError:
        raise ClaudeStop("not_json", "the object does not parse") from None
    if not isinstance(obj, dict):
        raise ClaudeStop("not_json", "not an object")
    return obj


def _sdk_error(e):
    """The SDK's exception as one of ours, with nothing of the request (headers, key) or the reply's body text."""
    import anthropic
    if isinstance(e, anthropic.APIStatusError):
        body = e.body if isinstance(e.body, dict) else {}
        kind = ((body.get("error") or {}) if isinstance(body.get("error"), dict) else {}).get("type") or "error"
        host = getattr(getattr(e.response, "request", None), "url", None)
        return ClaudeHTTPError(e.status_code, str(kind)[:40], getattr(host, "host", "?"))
    if isinstance(e, anthropic.APITimeoutError):
        return ClaudeTimeout(f"no answer from {ANTHROPIC_URL} in {TIMEOUT} s")
    if isinstance(e, anthropic.APIConnectionError):
        cause = type(e.__cause__).__name__ if e.__cause__ is not None else "unknown"
        return ClaudeConnection(cause not in ("ConnectError", "ConnectTimeout", "ProxyError"), cause)
    return None


def anthropic_chat_json(model, system, user, max_tokens=400, purpose="", prompt_version="", schema=None,
                        thinking=None, effort=None, fallbacks=False, dropped=()):
    """One Messages call that must return a JSON object. Returns (parsed_json, usage dict), as openai_chat_json.
    schema: a JSON schema for structured outputs (output_config.format); without one the system prompt gains
    JSON_LINE and the reply is read by parse_json_object. thinking / effort: sent as given (claude_thinking).
    fallbacks: the server-side fallback ("default") on a policy decline (Sonnet 5.5 and Opus 5.5 only).
    dropped: the caller's settings this API does not take (temperature, seed), named in the row."""
    est_in = (len(system) + len(user)) / 3.5
    with _pending_lock:   # review: two calls at the cap; the second sees the first's worst case until it answers
        p = _guard("anthropic", model, est_in, max_tokens, pending=_pending["usd"])
        if p.get("provider") != "anthropic":
            raise RuntimeError(f"{model} is not a Claude model in lib/ai_prices.json")
        hold = est_in / 1e6 * p["input_per_m"] + max_tokens / 1e6 * p.get("output_per_m", 0)
        _pending["usd"] += hold
    try:
        return _anthropic_call(model, system, user, max_tokens, purpose, prompt_version, schema, thinking, effort,
                               fallbacks, dropped)
    finally:
        with _pending_lock:
            _pending["usd"] = max(0.0, _pending["usd"] - hold)


_pending_lock = threading.Lock()
_pending = {"usd": 0.0}


def _anthropic_call(model, system, user, max_tokens, purpose, prompt_version, schema, thinking, effort, fallbacks,
                    dropped):
    client = anthropic_client()
    oc = {}
    if effort:
        oc["effort"] = effort
    if schema:
        oc["format"] = {"type": "json_schema", "schema": schema}
    body = {"model": model, "max_tokens": max_tokens, "system": system if schema else f"{system}\n\n{JSON_LINE}",
            "messages": [{"role": "user", "content": user}]}
    if oc:
        body["output_config"] = oc
    if thinking:
        body["thinking"] = thinking
    if fallbacks:
        body["betas"] = [ANTHROPIC_FALLBACK_BETA]
        body["fallbacks"] = "default"
    t = time.time()
    try:
        r = client.beta.messages.create(**body, timeout=TIMEOUT)
    except Exception as e:  # noqa: BLE001 - the SDK's errors become ours, without the request in them
        mine = _sdk_error(e) if not isinstance(e, (ClaudeHTTPError, ClaudeTimeout, ClaudeConnection)) else e
        if mine is None:
            raise
        raise mine from None
    u = r.usage
    cost, assumed, _served = claude_cost(model, u)
    tin, tout = _field(u, "input_tokens") or 0, _field(u, "output_tokens") or 0
    its = [i for i in (_field(u, "iterations") or []) if _field(i, "type") in ("message", "fallback_message")]
    if its:   # every attempt's tokens (top-level usage covers only the one that answered)
        tin = sum(_field(i, "input_tokens") or 0 for i in its)
        tout = sum(_field(i, "output_tokens") or 0 for i in its)
    row = {"provider": "anthropic", "model": model, "purpose": purpose, "prompt_version": prompt_version, "n": 1,
           "in_tokens": tin, "out_tokens": tout, "cost_usd": cost, "seconds": round(time.time() - t, 2)}
    parts = its or [u]
    cr = sum(_field(i, "cache_read_input_tokens") or 0 for i in parts)
    cw = sum(_field(i, "cache_creation_input_tokens") or 0 for i in parts)
    if cr:
        row["cache_read_tokens"] = cr
    if cw:
        row["cache_write_tokens"] = cw
    if getattr(r, "model", model) != model:
        row["served_model"] = r.model
    if any(_field(i, "type") == "fallback_message" for i in its):
        row["fallback"] = True
    if assumed:
        row["price_assumed"] = True
    if r.stop_reason != "end_turn":
        row["stop_reason"] = r.stop_reason
    if dropped:
        row["not_sent"] = sorted(dropped)
    _log(row)
    if r.stop_reason == "refusal":
        cat = _field(getattr(r, "stop_details", None), "category")
        raise ClaudeStop("refusal", f"category {cat}" if cat else "")
    if r.stop_reason == "max_tokens":
        raise ClaudeStop("max_tokens", f"max_tokens {max_tokens}")
    text = "".join(_field(b, "text") or "" for b in r.content if _field(b, "type") == "text")
    if not text.strip():
        raise ClaudeStop("no_text", f"stop_reason {r.stop_reason}")
    usage = {"input_tokens": tin, "output_tokens": tout, "cache_read_input_tokens": cr,
             "cache_creation_input_tokens": cw}
    return parse_json_object(text), usage


# ---------------- Gemini ----------------
def _gk():
    return {"x-goog-api-key": os.environ["GEMINI_API_KEY"]}


def gemini_json(model, system, parts, max_tokens=400, purpose="", prompt_version="", est_media_tokens=0,
                generation_config=None):
    """One generateContent call that returns JSON. `parts` is a list of str, or
    {"mime": "image/jpeg", "bytes": b"..."} for inline media (images, short audio).
    est_media_tokens: your estimate for the media (e.g. 258 per small image, 32/s audio) for the budget guard.
    generation_config: optional extra generationConfig keys (e.g. thinkingConfig, responseSchema).
    Returns (parsed_json, usage)."""
    text_len = len(system) + sum(len(p) for p in parts if isinstance(p, str))
    pr = _guard("gemini", model, text_len / 3.5 + est_media_tokens, max_tokens)
    body_parts = []
    for p in parts:
        if isinstance(p, str):
            body_parts.append({"text": p})
        else:
            body_parts.append({"inline_data": {"mime_type": p["mime"], "data": base64.b64encode(p["bytes"]).decode()}})
    body = {"system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": body_parts}],
            "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": max_tokens,
                                 **(generation_config or {})}}
    t = time.time()
    r = _post(f"{GEMINI}/models/{model}:generateContent", body, _gk())
    u = r.get("usageMetadata", {})
    tin = u.get("promptTokenCount", 0)
    tout = u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)
    cost = tin / 1e6 * pr["input_per_m"] + tout / 1e6 * pr["output_per_m"]
    _log({"provider": "gemini", "model": model, "purpose": purpose, "prompt_version": prompt_version, "n": 1,
          "in_tokens": tin, "out_tokens": tout, "cost_usd": cost, "seconds": round(time.time() - t, 2)})
    text = "".join(p.get("text", "") for p in r["candidates"][0]["content"]["parts"])
    return json.loads(text), u


def gemini_embed(texts, model, dimensions=None, task_type=None, purpose=""):
    """Batch text embeddings (batchEmbedContents). The API doesn't return token counts, so cost is
    estimated at ~4 chars per token and marked estimated in the ledger."""
    est_tok = sum(len(t) for t in texts) / 4
    pr = _guard("gemini", model, est_tok, 0)
    reqs = []
    for t in texts:
        q = {"model": f"models/{model}", "content": {"parts": [{"text": t}]}}
        if dimensions:
            q["outputDimensionality"] = dimensions
        if task_type:
            q["taskType"] = task_type  # e.g. RETRIEVAL_DOCUMENT / RETRIEVAL_QUERY, if the model supports it
        reqs.append(q)
    t0 = time.time()
    r = _post(f"{GEMINI}/models/{model}:batchEmbedContents", {"requests": reqs}, _gk())
    _log({"provider": "gemini", "model": model, "purpose": purpose, "n": len(texts), "in_tokens": int(est_tok),
          "out_tokens": 0, "cost_usd": est_tok / 1e6 * pr["input_per_m"], "estimated": True,
          "seconds": round(time.time() - t0, 2)})
    return [e["values"] for e in r["embeddings"]]


def log_batch(provider, model, purpose, n, in_tokens, out_tokens, cost_usd, seconds, prompt_version=""):
    """For Batch API jobs run outside the helpers above: log the job's usage when it completes.
    Check the budget yourself before submitting: spent(provider) + estimate <= budget(provider)."""
    _log({"provider": provider, "model": model, "purpose": purpose, "prompt_version": prompt_version, "n": n,
          "in_tokens": in_tokens, "out_tokens": out_tokens, "cost_usd": cost_usd, "seconds": seconds, "batch": True})


# ---------------- Gemini Batch API ----------------
def _get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())


def gemini_batch_create(model, requests, est_cost_usd, display_name=""):
    """Submit one Batch API job with inline requests ([{"request": GenerateContentRequest, "metadata": {"key": ..}}]).
    Refused unless spent("gemini") + est_cost_usd <= budget("gemini"). Nothing is logged here: when the job is
    done, log its real usage with log_batch() at the batch_* prices. Returns the job name (batches/...)."""
    if prices().get(model) is None:
        raise RuntimeError(f"no verified price for {model}; add it to lib/ai_prices.json first")
    if spent("gemini") + est_cost_usd > budget("gemini"):
        raise RuntimeError(f"budget stop (gemini): spent ${spent('gemini'):.3f} + est ${est_cost_usd:.3f} "
                           f"> ${budget('gemini'):.2f}")
    body = {"batch": {"display_name": display_name or "batch",
                      "input_config": {"requests": {"requests": requests}}}}
    r = _post(f"{GEMINI}/models/{model}:batchGenerateContent", body, _gk())
    return r["name"]


def gemini_batch_get(name):
    """Poll a Batch API job (batches/...). Returns the operation JSON (metadata.state, done, response)."""
    return _get(f"{GEMINI}/{name}", _gk())


# ---------------- Gemini: public YouTube video by URL (round 3) ----------------
def gemini_modality_cost(model, usage, batch=False):
    """Cost of one response from usageMetadata, priced per input modality (promptTokensDetails):
    TEXT at input_per_m, VIDEO/IMAGE at media_input_per_m, AUDIO at audio_input_per_m; batch_* prices halve
    every rate (the Batch API is half price for all modalities). Returns (cost_usd, {modality: tokens}, tin, tout)."""
    pr = prices()[model]
    half = 0.5 if batch else 1.0
    det = {d.get("modality", "TEXT"): d.get("tokenCount", 0) for d in usage.get("promptTokensDetails") or []}
    tin = usage.get("promptTokenCount", 0)
    tout = usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0)
    if not det:
        det = {"TEXT": tin}
    rate = {"TEXT": pr["input_per_m"], "VIDEO": pr.get("media_input_per_m", pr["input_per_m"]),
            "IMAGE": pr.get("media_input_per_m", pr["input_per_m"]),
            "AUDIO": pr.get("audio_input_per_m", pr["input_per_m"])}
    cost = sum(n / 1e6 * rate.get(m, pr["input_per_m"]) for m, n in det.items()) + tout / 1e6 * pr["output_per_m"]
    return cost * half, det, tin, tout


def youtube_video_request(system, prompt, video_url, start_s=None, end_s=None, fps=None, media_resolution=None,
                          max_tokens=1500, response_schema=None, thinking_budget=0):
    """A GenerateContentRequest body for one public YouTube URL (Gemini's documented YouTube-URL input; no
    download, nothing stored but the model's text output). Clipping/fps go in videoMetadata."""
    vm = {}
    if start_s is not None:
        vm["start_offset"] = f"{int(start_s)}s"
    if end_s is not None:
        vm["end_offset"] = f"{int(end_s)}s"
    if fps is not None:
        vm["fps"] = fps
    part = {"file_data": {"file_uri": video_url}}
    if vm:
        part["video_metadata"] = vm
    gc = {"responseMimeType": "application/json", "maxOutputTokens": max_tokens}
    if thinking_budget is not None:
        gc["thinkingConfig"] = {"thinkingBudget": thinking_budget}
    if response_schema:
        gc["responseJsonSchema"] = response_schema
    if media_resolution:
        gc["mediaResolution"] = media_resolution
    return {"system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [part, {"text": prompt}]}],
            "generationConfig": gc}


def gemini_youtube_json(model, request, est_media_tokens, purpose="", prompt_version="", code=""):
    """One synchronous generateContent call on a request from youtube_video_request(). Guarded by a worst-case
    estimate (est_media_tokens at the audio rate + max output); logged per call with the modality breakdown.
    Returns (parsed_json_or_None, usage, raw_text)."""
    max_out = request["generationConfig"].get("maxOutputTokens", 1500)
    p = prices().get(model)
    if p is None:
        raise RuntimeError(f"no verified price for {model}; add it to lib/ai_prices.json first")
    est = est_media_tokens / 1e6 * p.get("audio_input_per_m", p["input_per_m"]) + max_out / 1e6 * p["output_per_m"]
    if spent("gemini") + est > budget("gemini"):
        raise RuntimeError(f"budget stop (gemini): spent ${spent('gemini'):.3f} + est ${est:.3f} > ${budget('gemini'):.2f}")
    t = time.time()
    r = _post(f"{GEMINI}/models/{model}:generateContent", request, _gk())
    u = r.get("usageMetadata", {})
    cost, det, tin, tout = gemini_modality_cost(model, u)
    _log({"provider": "gemini", "model": model, "purpose": purpose, "prompt_version": prompt_version, "n": 1,
          "in_tokens": tin, "out_tokens": tout, "in_by_modality": det, "cost_usd": cost,
          "seconds": round(time.time() - t, 2)})
    text = ""
    try:
        text = "".join(pp.get("text", "") for pp in r["candidates"][0]["content"]["parts"])
        return json.loads(text), u, text
    except Exception:  # noqa: BLE001 - blocked / truncated / no candidate
        return None, u, text or json.dumps(r.get("candidates", [{}])[0].get("finishReason", "no candidate"))
