"""PROTOTYPE ONLY - every paid AI call in experiments goes through here.

- Keys come from environment variables only (OPENAI_API_KEY, GEMINI_API_KEY). Never write, print or log them.
- Each call is logged to $DIGESTER_DATA/ai_runs.jsonl: model, purpose, tokens, cost, seconds (AGENTS.md rule 11).
- Hard budget: a call is refused if spend so far plus a worst-case estimate for the call would pass
  $DIGESTER_AI_BUDGET_USD (default 4.00). Spend is read back from the ledger, so it holds across processes and sessions.
- Prices come from lib/ai_prices.json. Check them against the provider's pricing page before the first
  paid run and record the date there. A model with no price entry is refused.
"""
import json
import os
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("DIGESTER_DATA", os.path.join(os.path.dirname(os.path.dirname(HERE)), "data"))
LEDGER = os.path.join(DATA, "ai_runs.jsonl")
BUDGET = float(os.environ.get("DIGESTER_AI_BUDGET_USD", "4.00"))


def prices():
    return json.load(open(os.path.join(HERE, "ai_prices.json")))["models"]


def spent():
    if not os.path.exists(LEDGER):
        return 0.0
    return sum(json.loads(l).get("cost_usd", 0) for l in open(LEDGER))


def _guard(model, est_in_tokens, max_out_tokens):
    p = prices().get(model)
    if p is None:
        raise RuntimeError(f"no verified price for {model}; add it to lib/ai_prices.json first")
    est = est_in_tokens / 1e6 * p["input_per_m"] + max_out_tokens / 1e6 * p.get("output_per_m", 0)
    if spent() + est > BUDGET:
        raise RuntimeError(f"budget stop: spent ${spent():.3f} + est ${est:.3f} > ${BUDGET:.2f}")
    return p


def _log(row):
    os.makedirs(DATA, exist_ok=True)
    with open(LEDGER, "a") as f:
        f.write(json.dumps(row) + "\n")


def _post(url, body, headers):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())


def openai_embed(texts, model="text-embedding-3-small", dimensions=None, purpose=""):
    p = _guard(model, sum(len(t) for t in texts) / 3.5, 0)
    t = time.time()
    body = {"model": model, "input": texts}
    if dimensions:
        body["dimensions"] = dimensions
    r = _post("https://api.openai.com/v1/embeddings", body, {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"})
    tok = r["usage"]["total_tokens"]
    _log({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "provider": "openai", "model": model, "purpose": purpose,
          "n": len(texts), "in_tokens": tok, "out_tokens": 0, "cost_usd": tok / 1e6 * p["input_per_m"],
          "seconds": round(time.time() - t, 2)})
    return [d["embedding"] for d in r["data"]]


def openai_chat_json(model, system, user, max_tokens=400, purpose="", prompt_version="", **extra):
    """One chat call that must return a JSON object. Returns (parsed_json, usage)."""
    p = _guard(model, (len(system) + len(user)) / 3.5, max_tokens)
    t = time.time()
    body = {"model": model, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], **extra}
    body["max_completion_tokens"] = max_tokens
    r = _post("https://api.openai.com/v1/chat/completions", body, {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"})
    u = r["usage"]
    cost = u["prompt_tokens"] / 1e6 * p["input_per_m"] + u["completion_tokens"] / 1e6 * p["output_per_m"]
    _log({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "provider": "openai", "model": model, "purpose": purpose,
          "prompt_version": prompt_version, "n": 1, "in_tokens": u["prompt_tokens"],
          "out_tokens": u["completion_tokens"], "cost_usd": cost, "seconds": round(time.time() - t, 2)})
    return json.loads(r["choices"][0]["message"]["content"]), u


def log_batch(provider, model, purpose, n, in_tokens, out_tokens, cost_usd, seconds, prompt_version=""):
    """For Batch API jobs run outside the helpers above: log the job's usage when it completes."""
    _log({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "provider": provider, "model": model, "purpose": purpose,
          "prompt_version": prompt_version, "n": n, "in_tokens": in_tokens, "out_tokens": out_tokens,
          "cost_usd": cost_usd, "seconds": seconds, "batch": True})
