"""PROTOTYPE ONLY - round 6 shared code (LOG.md "Round 6 fixed parameters", rows Y6-G1 ... Y6-G5).

  cached_chat      one qr-v1 call through lib/ai.py, cached in $DIGESTER_DATA/cache/r6/<prompt_version>.jsonl,
                   keyed by (model, messages, response format, reasoning, max tokens, salt). Salt = repeat number.
  rewrite_one      the qr-v1 rewrite of one search with any model: llm_rewrite's messages, schema and post_validate,
                   unchanged. Only the model and its reasoning setting differ between arms.
  hard             G3's text-only "hard search" rule (fixed in LOG.md before it was computed on any eval search).
  embed_3l         text-embedding-3-large at 1,024 d through lib/ai.py (ledger + budget), with retries.
  QueryVecs3L      cached 3-large query / phrase / HyDE / outside-example vectors (corpus/emb/oai3l_1024_queries).
  swap_to_3l       puts the 3-large item store and query vectors into a c4_lib.Combined index (same ids and order as
                   oai512, so the gate and every other array stay as they are).
  keyword_jaccard  rewrite variability across repeats: mean over searches of the mean pairwise Jaccard of the
                   post-validated keyword sets.
Method side only: never opens evals/labels/.
"""
import hashlib
import itertools
import json
import os
import re
import sys
import time
import urllib.error

import numpy as np
from sklearn.preprocessing import normalize

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
import ai  # noqa: E402
import c4_lib as L  # noqa: E402
import llm_rewrite as QR  # noqa: E402
from common import STOP  # noqa: E402
from corpus import DATA  # noqa: E402

CACHE = os.path.join(DATA, "cache", "r6")
PROMPT_VERSION = QR.PROMPT_VERSION  # qr-v1, unchanged
EMB3L_MODEL, EMB3L_DIM = "text-embedding-3-large", 1024
STORE_3L = "oai3l_1024"
QSTORE_3L = "oai3l_1024_queries"

# Lowest reasoning setting each model accepts (official model pages, 7 Nov 2026), and max completion tokens.
REASONING = {"gpt-5-nano": "minimal", "gpt-5.4-mini": "none", "gpt-5.5": "low", "gpt-6.1-sol": "low"}
MAX_TOKENS = {"gpt-5-nano": 1200, "gpt-5.4-mini": 1200, "gpt-5.5": 4000, "gpt-6.1-sol": 4000}


# ---------------- cached calls ----------------
_MEM = {}


def _load(pv):
    if pv not in _MEM:
        p = os.path.join(CACHE, f"{pv}.jsonl")
        d = {}
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                r = json.loads(line)
                d[r["key"]] = r
        _MEM[pv] = d
    return _MEM[pv]


def price(model, u):
    p = ai.prices()[model]
    return u["prompt_tokens"] / 1e6 * p["input_per_m"] + u["completion_tokens"] / 1e6 * p["output_per_m"]


def cached_chat(msgs, response_format, prompt_version, purpose, model, reasoning, max_tokens, salt="", tries=4):
    """Returns {key, out, cost_usd, seconds, in_tokens, out_tokens, reasoning_tokens, cached_tokens, finish, cached}."""
    body = {"model": model, "msgs": msgs, "rf": response_format, "reasoning": reasoning, "max": max_tokens,
            "salt": str(salt)}
    key = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    d = _load(prompt_version)
    if key in d:
        return {**d[key], "cached": True}
    for attempt in range(tries):
        t = time.time()
        try:
            out, u = ai.openai_chat_json(model, msgs[0]["content"], msgs[-1]["content"], max_tokens=max_tokens,
                                         purpose=purpose, prompt_version=prompt_version, reasoning_effort=reasoning,
                                         response_format=response_format, messages=msgs)
            rec = {"key": key, "out": out, "cost_usd": price(model, u), "seconds": round(time.time() - t, 3),
                   "in_tokens": u["prompt_tokens"], "out_tokens": u["completion_tokens"],
                   "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens", 0),
                   "cached_tokens": (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0),
                   "model": model, "reasoning": reasoning, "salt": str(salt),
                   "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
            os.makedirs(CACHE, exist_ok=True)
            with open(os.path.join(CACHE, f"{prompt_version}.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            d[key] = rec
            return {**rec, "cached": False}
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:300]
            print(f"HTTP {e.code} (attempt {attempt + 1}): {msg}", file=sys.stderr)
            if e.code < 500 and e.code != 429:
                raise
            time.sleep(2 ** attempt)
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:  # network reset: retry the same call
            print(f"network error (attempt {attempt + 1}): {type(e).__name__}", file=sys.stderr)
            time.sleep(3 * (attempt + 1))
        except json.JSONDecodeError:
            print(f"bad JSON (attempt {attempt + 1})", file=sys.stderr)
            salt = f"{salt}|retry{attempt + 1}"
            body["salt"] = str(salt)
            key = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    raise RuntimeError(f"{prompt_version} call failed")


def rewrite_one(query, model, repeat, purpose="c6_query_rewrite"):
    """qr-v1 (unchanged prompt, schema, post-validation) on `model` at its REASONING setting. Returns (parse, rec)."""
    rec = cached_chat(QR.messages_for(query), QR.RESPONSE_FORMAT, PROMPT_VERSION, purpose, model,
                      REASONING[model], MAX_TOKENS[model], salt=repeat)
    return QR.post_validate(rec["out"]), rec


# ---------------- G3: text-only hard rule (LOG.md, fixed before use) ----------------
WRAPPER = {"video", "videos", "vid", "vids", "reel", "reels", "post", "posts", "clip", "clips", "short", "shorts",
           "content", "youtube", "instagram", "insta", "channel", "account", "saved", "save", "liked", "watched",
           "show", "find", "give", "looking", "search", "want", "need", "help", "recommend", "suggest", "next",
           "should", "about"}
_TOK = re.compile(r"[a-z0-9']+")
H2 = [re.compile(r"\b(that|this|the|some) (one|guy|girl|man|woman|dude|lady|person|creator|channel|account|video|vid"
                 r"|reel|post|clip|song|show|thing)\b"),
      re.compile(r"\b(thing|things|stuff|something|someone|somebody|whatever|whoever)\b"),
      re.compile(r"\b(kind of|sort of|i think|forgot|forget|remember)\b")]
H3 = [re.compile(r"\b(videos?|vids?|reels?|posts?|clips?|shorts?|content) (about|on|of|with|where|for|that|from)\b"),
      re.compile(r"\bshould\b"), re.compile(r"\bnext\b"), re.compile(r"\b(recommend|suggest)\w*"),
      re.compile(r"\b(find|show|give) me\b"), re.compile(r"\blooking for\b"), re.compile(r"\bhelp me\b"),
      re.compile(r"\bi (want|need) to\b"), re.compile(r"\bwhat (to|should|do)\b")]


def content_words(query):
    toks = _TOK.findall((query or "").lower())
    return {t for t in toks if t.isalpha() and len(t) >= 3 and t not in STOP and t not in QR.BANNED
            and t not in WRAPPER}


def hard(query):
    """(is_hard, reasons) with reasons a subset of {H1, H2, H3}."""
    s = " ".join((query or "").lower().split())
    why = []
    if len(content_words(s)) <= 2:
        why.append("H1")
    if any(r.search(s) for r in H2):
        why.append("H2")
    if any(r.search(s) for r in H3):
        why.append("H3")
    return bool(why), why


# ---------------- 3-large vectors ----------------
def embed_3l(texts, purpose, batch=500, workers=2):
    """text-embedding-3-large @ 1,024 d, one ai.openai_embed call per `batch` texts; returns float32 unit rows."""
    from concurrent.futures import ThreadPoolExecutor
    chunks = [texts[i:i + batch] for i in range(0, len(texts), batch)]

    def one(ch):
        for att in range(10):
            try:
                return ai.openai_embed([t[:6000] or " " for t in ch], model=EMB3L_MODEL, dimensions=EMB3L_DIM,
                                       purpose=purpose)
            except Exception as e:  # noqa: BLE001 - retry rate limits and transient errors
                if "budget stop" in str(e) or att == 9:
                    raise
                time.sleep(min(60, 4 * 2 ** att) if "429" in str(e) else 3 * (att + 1))

    with ThreadPoolExecutor(workers) as ex:
        out = [v for vs in ex.map(one, chunks) for v in vs]
    return normalize(np.array(out, dtype=np.float32)) if out else np.zeros((0, EMB3L_DIM), np.float32)


class QueryVecs3L:
    """Same interface as c4_lib.QueryVecs, for text-embedding-3-large @ 1,024 d."""

    def __init__(self, name=QSTORE_3L):
        self.path = os.path.join(L.EMB, name)
        if os.path.exists(os.path.join(self.path, "ids.json")):
            ids = json.load(open(os.path.join(self.path, "ids.json")))
            V = normalize(np.load(os.path.join(self.path, "emb.npy")).astype(np.float32))
        else:
            ids, V = [], np.zeros((0, EMB3L_DIM), np.float32)
        self.vec = {s: V[k] for k, s in enumerate(ids)}

    def get(self, texts):
        miss = sorted({t for t in texts if t not in self.vec})
        if miss:
            V = embed_3l(miss, "c6_query_vectors_3l", batch=500, workers=1)
            self.vec.update(zip(miss, V))
            ids = list(self.vec)
            L.save_store(self.path, ids, np.array([self.vec[s] for s in ids]))
        return np.array([self.vec[t] for t in texts], dtype=np.float32)


def swap_to_3l(S):
    """Replace a Combined index's 3-small item vectors, query vectors and outside-example vectors by 3-large ones.
    The 3-large store has the same ids in the same order as oai512 (checked), so vpos / gate / row_of are kept."""
    d = os.path.join(L.EMB, STORE_3L)
    ids = json.load(open(os.path.join(d, "ids.json")))
    small_ids = json.load(open(os.path.join(L.EMB, "oai512", "ids.json")))
    assert ids == small_ids, "3-large store must have oai512's ids in oai512's order"
    V = normalize(np.load(os.path.join(d, "emb.npy")).astype(np.float32))
    keep = [k for k, i in enumerate(ids) if i in S.id_pos]
    assert [S.id_pos[ids[k]] for k in keep] == list(S.vpos)
    S.V = V[keep]
    S.QV = QueryVecs3L()
    if S.outside:
        oc = list(S.outside)
        S.ext_vec = dict(zip(oc, S.QV.get([S.outside[c] for c in oc])))
    S.emb_name = f"{EMB3L_MODEL}@{EMB3L_DIM}"
    return S


# ---------------- rewrite variability ----------------
def jaccard(a, b):
    a, b = set(a), set(b)
    return 1.0 if not a and not b else len(a & b) / len(a | b)


def keyword_jaccard(parse_sets):
    """parse_sets: list of {qid: parse} (one per repeat). Mean over searches of the mean pairwise keyword Jaccard."""
    qids = sorted(set.intersection(*[set(k for k in P if not k.startswith("_")) for P in parse_sets]))
    per = []
    for q in qids:
        pairs = [jaccard(a[q]["keywords"], b[q]["keywords"]) for a, b in itertools.combinations(parse_sets, 2)]
        per.append(float(np.mean(pairs)))
    return {"n_searches": len(per), "mean": round(float(np.mean(per)), 4),
            "p25": round(float(np.percentile(per, 25)), 4), "p75": round(float(np.percentile(per, 75)), 4),
            "share_identical": round(float(np.mean([x == 1.0 for x in per])), 4)}


def phrase_jaccard(parse_sets):
    """Same statistic over the lowercased word sets of all phrases (a second, coarser variability view)."""
    def words(p):
        return {w for ph in p["phrases"] for w in _TOK.findall(ph.lower()) if w not in STOP}
    qids = sorted(set.intersection(*[set(k for k in P if not k.startswith("_")) for P in parse_sets]))
    per = [float(np.mean([jaccard(words(a[q]), words(b[q])) for a, b in itertools.combinations(parse_sets, 2)]))
           for q in qids]
    return {"n_searches": len(per), "mean": round(float(np.mean(per)), 4)}
