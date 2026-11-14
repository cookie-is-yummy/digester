"""PROTOTYPE ONLY - round 8.8 shared code (LOG.md "Round 8.8 fixed parameters", rows Y8.8-FK, Y8.8-FM).

Base B8.5 = Q8 (q8-v1: TFY with the per-dimension int8 3-large item store everywhere). Each arm changes one thing:
  FK   Y8.8-FK (fk-v1): the rf-v1 refine (gpt-5-nano, top 20, same prompt) also on instant-routed typed searches with
       q_ig < 0.5. The rewrite-path gate is unchanged, so those refines reuse B8.5's cached responses.
  FM   Y8.8-FM (rfm-v1): gpt-5-mini (reasoning effort minimal) instead of gpt-5-nano in the refine, same gate as B8.5.
The prompt, schema, candidate lines, friend handling, retries and reorder are rf-v1's (c82_lib) exactly.
Nano responses are read from the 8.2 ... 8.7 caches (oldest identical-input response wins); new nano responses go to
cache/r8.8/rf-v1.jsonl, mini responses to cache/r8.8/rfm-v1.jsonl (key includes the model).
Method side only: never opens evals/labels/. Never prints query or item text.
"""
import hashlib
import json
import os
import sys
import threading
import time
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
import ai  # noqa: E402
import c82_lib as P  # noqa: E402
import c87_lib as C  # noqa: E402
from corpus import DATA  # noqa: E402

FK_VERSION, FM_VERSION = "fk-v1", "rfm-v1"
REFINE_Q_IG_MAX = C.REFINE_Q_IG_MAX  # 0.5, strict
NANO, MINI = P.REFINE_MODEL, "gpt-5-mini"
assert NANO == "gpt-5-nano"
CACHE_R88 = os.path.join(DATA, "cache", "r8.8", f"{P.REFINE_VERSION}.jsonl")
CACHE_R88_MINI = os.path.join(DATA, "cache", "r8.8", f"{FM_VERSION}.jsonl")
CACHES_NANO = C.CACHES + ((CACHE_R88, "r8.8"),)
CACHES_MINI = ((CACHE_R88_MINI, "r8.8-mini"),)


def cache_key(model, rep, qid, codes):
    """Nano: c82_lib.cache_key exactly (so earlier caches are reused). Mini: the same fields with the mini model."""
    if model == NANO:
        return P.cache_key(rep, qid, codes)
    return hashlib.sha256(json.dumps([P.REFINE_VERSION, model, rep, qid, codes]).encode()).hexdigest()


class Refiner88(P.Refiner):
    """rf-v1 with the model as a parameter. Same system prompt, candidate lines, schema, retries, reorder."""

    def __init__(self, S, te_rows, model=NANO, purpose="c88_refine"):
        self.S = S
        self.model = model
        self.purpose = purpose
        self.summary = {c: r["summary"] for c, r in te_rows.items() if r.get("summary")}
        self.cache, self.source = {}, {}
        self.out_path = CACHE_R88 if model == NANO else CACHE_R88_MINI
        self.tag = "r8.8" if model == NANO else "r8.8-mini"
        for path, tag in (CACHES_NANO if model == NANO else CACHES_MINI):
            if os.path.exists(path):
                for line in open(path):
                    r = json.loads(line)
                    if r["key"] not in self.cache:  # first (oldest) response with identical inputs wins
                        self.cache[r["key"]] = r
                        self.source[r["key"]] = tag
        self.lock = threading.Lock()

    def key(self, rep, qid, order):
        return cache_key(self.model, rep, qid, self.split_top(order)[2])

    def call(self, query, send):
        """c82_lib.Refiner.call with self.model (identical body otherwise)."""
        ids = [f"c{i + 1:02d}" for i in range(len(send))]
        user = (f'Search: "{P.clean(query)}"\n<candidates>\n'
                + "\n".join(P.cand_line(cid, self.S.items[self.S.pos[c]], self.summary.get(c))
                            for cid, c in zip(ids, send)) + "\n</candidates>")
        out = {"ok": False, "tries": 0, "seconds": 0.0, "cost_usd": 0.0, "in_tokens": 0, "out_tokens": 0,
               "ids": None, "error": None, "model": self.model}
        p = ai.prices()[self.model]
        for attempt in range(3):
            out["tries"] = attempt + 1
            t = time.time()
            try:
                js, u = ai.openai_chat_json(self.model, P.REFINE_SYSTEM, user, max_tokens=P.REFINE_MAX_TOKENS,
                                            purpose=self.purpose, prompt_version=P.REFINE_VERSION,
                                            reasoning_effort="minimal", response_format=P.schema(ids))
            except urllib.error.HTTPError as e:
                out["seconds"] += time.time() - t
                out["error"] = f"http {e.code}"
                if e.code < 500 and e.code != 429:
                    return out
                time.sleep(2 ** attempt)
                continue
            except (json.JSONDecodeError, KeyError, TypeError, IndexError) as e:
                out["seconds"] += time.time() - t
                out["error"] = type(e).__name__
                continue
            out["seconds"] += time.time() - t
            out["cost_usd"] += u["prompt_tokens"] / 1e6 * p["input_per_m"] + u["completion_tokens"] / 1e6 * p["output_per_m"]
            out["in_tokens"] += u["prompt_tokens"]
            out["out_tokens"] += u["completion_tokens"]
            got = js.get("ids") if isinstance(js, dict) else None
            if not isinstance(got, list):
                out["error"] = "no ids"
                continue
            out["ok"], out["ids"], out["error"] = True, [x for x in got if isinstance(x, str)], None
            return out
        return out

    def get(self, rep, qid, query, order, allow_call=False):
        top, friend, send = self.split_top(order)
        key = cache_key(self.model, rep, qid, send)
        r = self.cache.get(key)
        if r is None:
            if not allow_call:
                raise KeyError("refine response not cached (run `refine` first)")
            res = self.call(query, send) if send else {"ok": True, "ids": [], "tries": 0, "seconds": 0.0,
                                                         "cost_usd": 0.0, "in_tokens": 0, "out_tokens": 0}
            r = {"key": key, "rep": rep, "qid": qid, "n_sent": len(send), **res}
            with self.lock:
                self.cache[key] = r
                self.source[key] = self.tag
                os.makedirs(os.path.dirname(self.out_path), exist_ok=True)
                with open(self.out_path, "a") as f:
                    f.write(json.dumps(r) + "\n")
        return self.reorder(order, top, friend, send, r), r


def gate(cfg, path, q_ig):
    """B8.5 / FM: rewrite-routed and q_ig < 0.5. FK: any typed search with q_ig < 0.5 (both routes)."""
    if q_ig >= REFINE_Q_IG_MAX:
        return False
    return True if cfg == "fk" else path == "rewrite"
