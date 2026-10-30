"""PROTOTYPE ONLY - every paid AI call in experiments goes through here.

- Keys come from environment variables only: OPENAI_API_KEY, GEMINI_API_KEY. Never write, print or log them.
- Each call is logged to $DIGESTER_DATA/ai_runs.jsonl: provider, model, purpose, tokens, cost, seconds
  (AGENTS.md rule 11).
- Hard budget per provider: a call is refused if that provider's spend so far, plus a worst-case
  estimate for the call, would pass its cap. Spend is read back from the ledger, so caps hold across
  processes and sessions. Caps:
    DIGESTER_OPENAI_BUDGET_USD  (default 4.00)
    DIGESTER_GEMINI_BUDGET_USD  (default 4.00)
- Prices come from lib/ai_prices.json. Check them against the provider's pricing page before the first
  paid run and record the date. A model with no price entry is refused.
- Ledger costs are estimates from list prices. Compare them with the provider's billing page now and
  then, and note any gap in STATE.md.
"""
import base64
import json
import os
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


def _guard(provider, model, est_in_tokens, max_out_tokens):
    p = prices().get(model)
    if p is None:
        raise RuntimeError(f"no verified price for {model}; add it to lib/ai_prices.json first")
    est = est_in_tokens / 1e6 * p["input_per_m"] + max_out_tokens / 1e6 * p.get("output_per_m", 0)
    if spent(provider) + est > budget(provider):
        raise RuntimeError(f"budget stop ({provider}): spent ${spent(provider):.3f} + est ${est:.3f} > ${budget(provider):.2f}")
    return p


def _log(row):
    os.makedirs(DATA, exist_ok=True)
    row = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), **row}
    with open(LEDGER, "a") as f:
        f.write(json.dumps(row) + "\n")


def _post(url, body, headers):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=300) as r:
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
