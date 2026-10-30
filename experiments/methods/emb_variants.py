"""PROTOTYPE ONLY - embedding variants for experiments 10-12, wrapped around methods/pipeline.py (not edited).

  10  EmbeddingGemma-300M (local, fastembed ONNX) replaces bge-small in the dense leg.
  11  Gemini Embedding 2 (gemini-embedding-2, 768d, paid, through lib/ai.py) replaces bge-small in the dense leg.
  12  answerai-colbert-small-v1 MaxSim re-score of the base's fused top 100, added as a third RRF list.

Both document-embedding models get the retrieval prefixes from their model cards / docs (gemini-embedding-2
does not accept task_type):
  query:    "task: search result | query: <phrase>"
  document: "title: none | text: <'full' text view>"

Index builds embed the same 20,202 items as corpus/emb/bge_full (its ids.json), sorted by text length before
batching (padding cut, ~1.7x faster), in resumable chunks under <out>/chunks/, then restore the original order.
Each build logs items processed, items/s and wall time, and writes <out>/info.json (model, prefix, dims, speed).

usage:
  python experiments/methods/emb_variants.py build-gemma [--threads 2]
  python experiments/methods/emb_variants.py pilot-gemini            # 200 random items, prints ledger cost/item
  python experiments/methods/emb_variants.py build-gemini
  python experiments/methods/emb_variants.py qcache-gemini --parses R1.json --parses R2.json ...
  python experiments/methods/emb_variants.py run --variant gemma|gemini|colbert --parses R.json --out data/runs/x.json
Prints aggregate numbers only (no captions, no query text, no item codes).
"""
import json
import os
import pickle
import random
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
import pipeline  # noqa: E402
from corpus import DATA, Corpus, load_queries  # noqa: E402

PREFIX_Q = "task: search result | query: "
PREFIX_D = "title: none | text: "
GEMMA = "google/embeddinggemma-300m"
GEMINI = "gemini-embedding-2"
COLBERT = "answerdotai/answerai-colbert-small-v1"
EMB_DIR = os.path.join(DATA, "corpus", "emb")
GEMINI_QCACHE = os.path.join(DATA, "evals", "qcache", "gemini2_768.json")


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def args_all(name):
    return [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == name]


def load_avg():
    try:
        return round(os.getloadavg()[0], 2)
    except OSError:
        return None


# ---------------------------------------------------------------- index builds
def doc_texts():
    """Same items and 'full' view as bge_full, with the document prefix."""
    C = Corpus("bge_full")
    return C.ids, [PREFIX_D + C.text(n, "full") for n in range(len(C.ids))]


def build(name, embed_fn, model_id, chunk=500, extra_info=None):
    out = os.path.join(EMB_DIR, name)
    cdir = os.path.join(out, "chunks")
    os.makedirs(cdir, exist_ok=True)
    ids, texts = doc_texts()
    order = sorted(range(len(texts)), key=lambda i: (len(texts[i]), i))
    op = os.path.join(cdir, "order.json")
    if os.path.exists(op):
        if json.load(open(op)) != order:
            raise SystemExit("chunk order changed; delete the chunks folder to rebuild")
    else:
        json.dump(order, open(op, "w"))
    stats_p = os.path.join(cdir, "stats.jsonl")
    t0, done_now = time.time(), 0
    nchunks = (len(order) + chunk - 1) // chunk
    for c in range(nchunks):
        p = os.path.join(cdir, f"chunk_{c:03d}.npy")
        if os.path.exists(p):
            continue
        sel = order[c * chunk:(c + 1) * chunk]
        t = time.time()
        V = np.asarray(embed_fn([texts[i] for i in sel]), dtype=np.float32)
        np.save(p, V)
        dt = time.time() - t
        done_now += len(sel)
        with open(stats_p, "a") as f:
            f.write(json.dumps({"chunk": c, "n": len(sel), "seconds": round(dt, 2), "chars": sum(len(texts[i]) for i in sel),
                                "load1": load_avg()}) + "\n")
        el = time.time() - t0
        print(f"chunk {c + 1}/{nchunks}: {done_now} items this session, {done_now / el:.1f} items/s, "
              f"wall {el:.0f} s, load {load_avg()}", flush=True)
    V = np.concatenate([np.load(os.path.join(cdir, f"chunk_{c:03d}.npy")) for c in range(nchunks)])
    full = np.zeros_like(V)
    full[np.array(order)] = V
    norms = np.linalg.norm(full, axis=1)
    np.save(os.path.join(out, "emb.npy"), full.astype(np.float16))
    json.dump(ids, open(os.path.join(out, "ids.json"), "w"))
    st = [json.loads(l) for l in open(stats_p)]
    secs = sum(s["seconds"] for s in st)
    info = {"model": model_id, "dims": int(full.shape[1]), "items": len(ids), "doc_prefix": PREFIX_D, "query_prefix": PREFIX_Q,
            "text_view": "full", "stored": "float16", "bytes_per_item": int(full.shape[1] * 2),
            "embed_seconds_total": round(secs, 1), "items_per_s": round(len(ids) / secs, 2),
            "norm_min": float(norms.min()), "norm_max": float(norms.max()),
            "load1_mean": round(float(np.mean([s["load1"] for s in st if s["load1"] is not None] or [0])), 2),
            "sorted_by_length": True, "chunk": chunk, **(extra_info or {})}
    json.dump(info, open(os.path.join(out, "info.json"), "w"), indent=1)
    print(f"done: {len(ids)} items, embed time {secs:.0f} s, {info['items_per_s']} items/s; wrote {out}", flush=True)


def gemma_model(threads):
    from fastembed import TextEmbedding
    return TextEmbedding(model_name=GEMMA, threads=threads)


def model_size_gb(fragment):
    tot = 0
    for root in sorted({os.path.realpath(r) for r in ["/tmp/fastembed_cache", os.path.expanduser("~/.cache/fastembed")]}):
        for dp, _, fs in os.walk(root):
            if fragment in dp and "/snapshots" in dp:  # snapshot files link to blobs; getsize follows the link
                for f in fs:
                    tot += os.path.getsize(os.path.join(dp, f))
    return round(tot / 1e9, 3)


def cmd_build_gemma():
    threads = int(arg("--threads", 2))
    m = gemma_model(threads)
    build("embgemma_full", lambda ts: list(m.embed(ts, batch_size=32)), GEMMA,
          extra_info={"runtime": "fastembed 0.9.1 ONNX fp32 (onnx-community/embeddinggemma-300m-ONNX)", "threads": threads,
                      "model_size_gb": model_size_gb("embeddinggemma"), "license": "Gemma Terms of Use"})


def gemini_embed_retry(texts, purpose):
    from ai import gemini_embed
    for attempt in range(8):
        try:
            return gemini_embed(texts, GEMINI, dimensions=768, purpose=purpose)
        except Exception as e:  # noqa: BLE001  (HTTP 429/5xx: back off; budget stop: re-raise)
            if "budget stop" in str(e) or attempt == 7:
                raise
            code = getattr(e, "code", None)
            print(f"  retry {attempt + 1} after error {code or type(e).__name__}", flush=True)
            time.sleep(min(60, 4 * 2 ** attempt))


def gemini_docs(texts, purpose):
    out = []
    for i in range(0, len(texts), 100):
        out.extend(gemini_embed_retry(texts[i:i + 100], purpose))
    return out


def ledger_cost(purpose):
    p = os.path.join(DATA, "ai_runs.jsonl")
    rows = [json.loads(l) for l in open(p)] if os.path.exists(p) else []
    rows = [r for r in rows if r.get("purpose") == purpose]
    return sum(r["cost_usd"] for r in rows), sum(r["in_tokens"] for r in rows), sum(r["seconds"] for r in rows), len(rows)


def cmd_pilot_gemini():
    _, texts = doc_texts()
    random.seed(0)
    sel = random.sample(range(len(texts)), 200)
    t = time.time()
    V = np.asarray(gemini_docs([texts[i] for i in sel], "e11_gemini2_pilot"), dtype=np.float32)
    cost, tok, _, calls = ledger_cost("e11_gemini2_pilot")
    print(f"pilot: 200 items, {calls} calls, {time.time() - t:.1f} s, ledger ${cost:.5f} (${cost / 200 * 1000:.4f}/1k items), "
          f"est tokens/item {tok / 200:.0f}, dims {V.shape[1]}, norm {np.linalg.norm(V, axis=1).mean():.3f}; "
          f"projected for {len(texts)} items ${cost / 200 * len(texts):.3f}")


def cmd_build_gemini():
    build("gemini2_768_full", lambda ts: gemini_docs(ts, "e11_gemini2_docs"), GEMINI,
          extra_info={"runtime": "Gemini API batchEmbedContents, outputDimensionality 768 (auto-normalized)",
                      "batch": 100})
    cost, tok, secs, calls = ledger_cost("e11_gemini2_docs")
    info_p = os.path.join(EMB_DIR, "gemini2_768_full", "info.json")
    info = json.load(open(info_p))
    info.update({"index_cost_usd_ledger": round(cost, 5), "index_est_tokens": tok, "api_calls": calls,
                 "cost_note": "ledger estimate at ~4 chars/token (the API returns no token counts); standard price, not batch"})
    json.dump(info, open(info_p, "w"), indent=1)
    print(f"gemini index cost (ledger) ${cost:.4f} over {calls} calls")


# ---------------------------------------------------------------- query embedding
class GemmaCorpus(Corpus):
    def __init__(self, emb="embgemma_full", threads=4):
        super().__init__(emb)
        self._gm = gemma_model(threads)
        self.q_lat = []

    def qvecs(self, phrases):
        from sklearn.preprocessing import normalize
        t = time.time()
        V = np.array(list(self._gm.embed([PREFIX_Q + p for p in phrases])), dtype=np.float32)
        self.q_lat.append(time.time() - t)
        return normalize(V)


class GeminiCorpus(Corpus):
    def __init__(self, emb="gemini2_768_full"):
        super().__init__(emb)
        self.qcache = json.load(open(GEMINI_QCACHE))

    def qvecs(self, phrases):
        from sklearn.preprocessing import normalize
        missing = [p for p in phrases if p not in self.qcache]
        if missing:
            raise SystemExit(f"{len(missing)} phrases missing from the Gemini query cache; run qcache-gemini first")
        return normalize(np.array([self.qcache[p] for p in phrases], dtype=np.float32))


def cmd_qcache_gemini():
    """One API call per typed dev search per rewrite file (its phrases), as a live search would make. Latency logged."""
    cache = json.load(open(GEMINI_QCACHE)) if os.path.exists(GEMINI_QCACHE) else {}
    meta = cache.pop("_meta", {"model": GEMINI, "dims": 768, "query_prefix": PREFIX_Q, "calls": []})
    from ai import gemini_embed
    for path in args_all("--parses"):
        P = json.load(open(path))
        for q in load_queries("dev"):
            if q["examples"]:
                continue
            phrases = [q["query"]] + P[q["id"]]["phrases"]
            t = time.time()
            cost0 = ledger_cost("e11_gemini2_query")[0]
            V = gemini_embed([PREFIX_Q + p for p in phrases], GEMINI, dimensions=768, purpose="e11_gemini2_query")
            meta["calls"].append({"rewrite": os.path.basename(path), "qid": q["id"], "n": len(phrases),
                                  "seconds": round(time.time() - t, 3),
                                  "cost_usd": ledger_cost("e11_gemini2_query")[0] - cost0})
            for p, v in zip(phrases, V):
                cache[p] = v
    cache["_meta"] = meta
    os.makedirs(os.path.dirname(GEMINI_QCACHE), exist_ok=True)
    json.dump(cache, open(GEMINI_QCACHE, "w"))
    lat = [c["seconds"] for c in meta["calls"]]
    print(f"query cache: {len(cache) - 1} phrases, {len(lat)} calls, call p50 {np.median(lat):.3f} s")


# ---------------------------------------------------------------- ColBERT re-score leg
COLBERT_DIR = os.path.join(EMB_DIR, "colbert_small_full")


class ColbertSearch(pipeline.Search):
    """Base search, then MaxSim re-score of its fused top `depth` as an extra RRF list (typed searches only)."""
    depth = 100

    def __init__(self, C, opts):
        super().__init__(C, opts)
        from fastembed import LateInteractionTextEmbedding
        self.cb = LateInteractionTextEmbedding(model_name=COLBERT, threads=int(arg("--threads", 2)))
        os.makedirs(COLBERT_DIR, exist_ok=True)
        self.cache_p = os.path.join(COLBERT_DIR, "doc_cache.pkl")
        self.cache = pickle.load(open(self.cache_p, "rb")) if os.path.exists(self.cache_p) else {}
        self.q_lat, self.doc_secs, self.doc_n = [], 0.0, 0

    def run(self, q, parse):
        if q["examples"]:
            return super().run(q, parse)
        cap, orig = {}, pipeline.rrf_scores

        def spy(lists, weights=None, k=60, depth=1000):
            cap["last"] = (lists, weights, k)
            return orig(lists, weights, k=k, depth=depth)

        pipeline.rrf_scores = spy
        try:
            base = super().run(q, parse)
        finally:
            pipeline.rrf_scores = orig
        lists, weights, k = cap["last"]
        top = base[:self.depth]
        need = [c for c in top if c not in self.cache]
        if need:
            need.sort(key=lambda c: len(self.C.text(self.C.by_code[c], "full")))
            t = time.time()
            for c, v in zip(need, self.cb.embed([self.C.text(self.C.by_code[c], "full") for c in need], batch_size=32)):
                self.cache[c] = np.asarray(v, dtype=np.float16)
            self.doc_secs += time.time() - t
            self.doc_n += len(need)
        t = time.time()
        Q = np.asarray(next(iter(self.cb.query_embed([q["query"]]))), dtype=np.float32)
        s = np.array([float((self.cache[c].astype(np.float32) @ Q.T).max(axis=0).sum()) for c in top])
        self.q_lat.append(time.time() - t)
        cl = [top[i] for i in np.argsort(-s, kind="stable")]
        w = list(weights) if weights is not None else [1.0] * len(lists)
        return pipeline.order(orig(list(lists) + [cl], w + [1.0], k=k))

    def save(self):
        pickle.dump(self.cache, open(self.cache_p, "wb"))


# ---------------------------------------------------------------- runs
def cmd_run():
    variant = arg("--variant")
    out = arg("--out")
    extra = {}
    state = {}
    if variant == "gemma":
        def mk(emb):
            state["C"] = GemmaCorpus("embgemma_full", threads=int(arg("--threads", 4)))
            return state["C"]
        pipeline.Corpus = mk
        emb_info = json.load(open(os.path.join(EMB_DIR, "embgemma_full", "info.json")))
        name = "e10_embgemma"
    elif variant == "gemini":
        pipeline.Corpus = lambda emb: GeminiCorpus("gemini2_768_full")
        emb_info = json.load(open(os.path.join(EMB_DIR, "gemini2_768_full", "info.json")))
        name = "e11_gemini2"
    elif variant == "colbert":
        class S(ColbertSearch):
            def __init__(self, C, opts):
                super().__init__(C, opts)
                state["S"] = self
        pipeline.Search = S
        emb_info = None
        name = "e12_colbert"
    else:
        raise SystemExit("--variant gemma|gemini|colbert")
    argv = [sys.argv[0], "--out", out, "--split", "dev", "--name", name]
    for p in args_all("--parses"):
        argv += ["--parses", p]
    sys.argv = argv
    pipeline.main()
    run = json.load(open(out))
    m = run["meta"]
    if emb_info:
        extra["embedding_info"] = emb_info
    if variant == "gemma":
        lat = state["C"].q_lat
        extra.update({"query_embed_p50_s": round(float(np.median(lat)), 4), "query_embed_calls": len(lat),
                      "note": "query_p50_s includes local query embedding (all phrases of a search in one call)"})
    if variant == "gemini":
        qc = json.load(open(GEMINI_QCACHE))["_meta"]["calls"]
        rw = set(m.get("rewrite", []))
        calls = [c for c in qc if c["rewrite"] in rw]
        api = float(np.median([c["seconds"] for c in calls]))
        qcost = sum(c["cost_usd"] for c in calls)
        extra.update({"query_embed_api_p50_s": round(api, 3), "query_embed_cost_usd": round(qcost, 7),
                      "query_plus_embed_p50_s": round(m["query_p50_s"] + api, 3),
                      "index_cost_usd": emb_info.get("index_cost_usd_ledger"),
                      "note": "query vectors from cache (evals/qcache/gemini2_768.json); one live API call per search "
                              "measured when the cache was filled; cost_usd = rewrite + query embedding (index cost separate)"})
        m["cost_usd"] = round(m.get("cost_usd", 0) + qcost, 6)
    if variant == "colbert":
        S_ = state["S"]
        S_.save()
        toks = [v.shape[0] for v in S_.cache.values()]
        extra.update({"colbert_model": COLBERT, "rescore_depth": ColbertSearch.depth, "colbert_query": "raw query text",
                      "colbert_query_p50_s": round(float(np.median(S_.q_lat)), 4) if S_.q_lat else None,
                      "colbert_doc_encoded_this_run": S_.doc_n,
                      "colbert_doc_items_per_s": round(S_.doc_n / S_.doc_secs, 2) if S_.doc_secs else None,
                      "colbert_cached_docs": len(toks), "colbert_tokens_per_doc_mean": round(float(np.mean(toks)), 1),
                      "colbert_bytes_per_doc_fp16": int(np.mean(toks) * 96 * 2),
                      "model_size_gb": model_size_gb("colbert-small"),
                      "note": "query_p50_s includes MaxSim and query encoding plus candidate doc encoding when not cached; "
                              "colbert_query_p50_s = query encode + MaxSim over 100 precomputed docs"})
    extra["load1_at_end"] = load_avg()
    m.update(extra)
    json.dump(run, open(out, "w"))
    print(f"meta added to {out}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"build-gemma": cmd_build_gemma, "pilot-gemini": cmd_pilot_gemini, "build-gemini": cmd_build_gemini,
     "qcache-gemini": cmd_qcache_gemini, "run": cmd_run}.get(cmd, lambda: print(__doc__))()
