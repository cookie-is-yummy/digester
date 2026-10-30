"""PROTOTYPE ONLY - experiments 21-22: swap the embedding model of BOTH dense lists of base B2 (experiment 9b main arm).

B2 = e9_enrich_search.py --arms both --enrich te-v1c_gemini-3.1-flash-lite (caption dense + PRF, BM25 'full',
enrichment BM25, enrichment dense; MLT: caption centroid, BM25 on examples, enrichment BM25 on examples, enrichment
centroid). This module runs that exact code (e9_enrich_search.main, not edited) with two substitutions:
  - the caption corpus vectors + query embedder  (emb_variants.GemmaCorpus / GeminiCorpus, not edited);
  - the enrichment vectors (EnrichIndex.V), re-embedded here with the same model.
The query vectors of a search (one embedding call for [query] + rewrite phrases) feed both dense lists, as in B2.
The BM25 lists are untouched. With --variant none it is B2 itself (checked with --verify against e9b_full_r{k}).

  21  EmbeddingGemma-300M (local, fastembed ONNX): enrichment index data/enrich/emb_embgemma_te-v1c/
  22  Gemini Embedding 2, 768d (paid, lib/ai.py): enrichment index data/enrich/emb_gemini2_768_te-v1c/

Prefixes are emb_variants.py's (model cards / docs): document "title: none | text: <enrichment text>",
query "task: search result | query: <phrase>". Enrichment texts = data/enrich/text_te-v1c_gemini-3.1-flash-lite.json
(20,829 items, same text the B2 bge-small enrichment index embedded). Builds sort by text length, embed in resumable
chunks under <out>/chunks/, log items processed, items/s and wall time, and write <out>/info.json.

usage:
  python experiments/methods/emb_b2.py build-gemma [--threads 3]
  python experiments/methods/emb_b2.py pilot-gemini        # 200 random enrichment texts; prints ledger cost/item
  python experiments/methods/emb_b2.py build-gemini
  python experiments/methods/emb_b2.py run --variant none|gemma|gemini --rep 1 --out data/runs/x.json [--verify B2.json]
Prints aggregate numbers only (no captions, no query text, no item codes).
"""
import json
import os
import random
import sys
import time

import numpy as np
from sklearn.preprocessing import normalize

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
import e9_enrich_search as e9  # noqa: E402
import emb_variants as ev  # noqa: E402
from corpus import DATA, code_of  # noqa: E402

ENRICH = "te-v1c_gemini-3.1-flash-lite"
OUT = {"gemma": os.path.join(DATA, "enrich", "emb_embgemma_te-v1c"),
       "gemini": os.path.join(DATA, "enrich", "emb_gemini2_768_te-v1c")}
CAP = {"gemma": "embgemma_full", "gemini": "gemini2_768_full"}
NAME = {"none": "e9b_b2_repro", "gemma": "e21_b2_embgemma", "gemini": "e22_b2_gemini2"}
arg, load_avg = ev.arg, ev.load_avg


# ---------------------------------------------------------------- enrichment index builds
def enrich_docs():
    """Codes in text-file order (as e9 build), item ids for ids.json, prefixed document texts."""
    texts = json.load(open(os.path.join(DATA, "enrich", f"text_{ENRICH}.json")))
    codes = list(texts)
    items = {code_of(json.loads(l)): json.loads(l)["id"]
             for l in open(os.path.join(DATA, "corpus", "items.jsonl"), encoding="utf-8")}
    return codes, [items[c] for c in codes], [ev.PREFIX_D + texts[c] for c in codes]


def build(variant, embed_fn, model_id, chunk=500, extra_info=None):
    out = OUT[variant]
    cdir = os.path.join(out, "chunks")
    os.makedirs(cdir, exist_ok=True)
    codes, ids, texts = enrich_docs()
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
        np.save(p + ".tmp.npy", V)
        os.replace(p + ".tmp.npy", p)
        dt = time.time() - t
        done_now += len(sel)
        with open(stats_p, "a") as f:
            f.write(json.dumps({"chunk": c, "n": len(sel), "seconds": round(dt, 2),
                                "chars": sum(len(texts[i]) for i in sel), "load1": load_avg()}) + "\n")
        el = time.time() - t0
        print(f"chunk {c + 1}/{nchunks}: {done_now} items this session, {done_now / el:.2f} items/s, "
              f"wall {el:.0f} s, load {load_avg()}", flush=True)
    V = np.concatenate([np.load(os.path.join(cdir, f"chunk_{c:03d}.npy")) for c in range(nchunks)])
    full = np.zeros_like(V)
    full[np.array(order)] = V
    norms = np.linalg.norm(full, axis=1)
    np.save(os.path.join(out, "emb.npy"), full.astype(np.float16))
    json.dump(ids, open(os.path.join(out, "ids.json"), "w"))
    st = list({s["chunk"]: s for s in map(json.loads, open(stats_p))}.values())
    secs = sum(s["seconds"] for s in st)
    info = {"model": model_id, "dims": int(full.shape[1]), "items": len(ids), "source": f"text_{ENRICH}.json",
            "doc_prefix": ev.PREFIX_D, "query_prefix": ev.PREFIX_Q, "stored": "float16",
            "bytes_per_item": int(full.shape[1] * 2), "embed_seconds_total": round(secs, 1),
            "items_per_s": round(len(ids) / secs, 2), "norm_min": float(norms.min()), "norm_max": float(norms.max()),
            "load1_mean": round(float(np.mean([s["load1"] for s in st if s["load1"] is not None] or [0])), 2),
            "sorted_by_length": True, "chunk": chunk, **(extra_info or {})}
    json.dump(info, open(os.path.join(out, "info.json"), "w"), indent=1)
    print(f"done: {len(ids)} items, embed time {secs:.0f} s, {info['items_per_s']} items/s; wrote {out}", flush=True)


def cmd_build_gemma():
    threads = int(arg("--threads", 3))
    m = ev.gemma_model(threads)
    build("gemma", lambda ts: list(m.embed(ts, batch_size=32)), ev.GEMMA,
          extra_info={"runtime": "fastembed ONNX fp32 (onnx-community/embeddinggemma-300m-ONNX)", "threads": threads,
                      "cpu_count": os.cpu_count(), "model_size_gb": ev.model_size_gb("embeddinggemma"),
                      "note": "machine shared with another experimenter's jobs; see load1_mean"})


def cmd_pilot_gemini():
    _, _, texts = enrich_docs()
    random.seed(0)
    sel = random.sample(range(len(texts)), 200)
    t = time.time()
    V = np.asarray(ev.gemini_docs([texts[i] for i in sel], "e22_gemini2_enrich_pilot"), dtype=np.float32)
    cost, tok, _, calls = ev.ledger_cost("e22_gemini2_enrich_pilot")
    print(f"pilot: 200 items, {calls} calls, {time.time() - t:.1f} s, ledger ${cost:.5f} (${cost / 200 * 1000:.4f}/1k), "
          f"est tokens/item {tok / 200:.0f}, dims {V.shape[1]}, norm {np.linalg.norm(V, axis=1).mean():.3f}; "
          f"projected for {len(texts)} items ${cost / 200 * len(texts):.3f}")


def cmd_build_gemini():
    build("gemini", lambda ts: ev.gemini_docs(ts, "e22_gemini2_enrich_docs"), ev.GEMINI,
          extra_info={"runtime": "Gemini API batchEmbedContents, outputDimensionality 768 (auto-normalized)",
                      "batch": 100})
    cost, tok, secs, calls = ev.ledger_cost("e22_gemini2_enrich_docs")
    info_p = os.path.join(OUT["gemini"], "info.json")
    info = json.load(open(info_p))
    info.update({"index_cost_usd_ledger": round(cost, 5), "index_est_tokens": tok, "api_calls": calls,
                 "cost_note": "ledger estimate at ~4 chars/token (the API returns no token counts); standard price"})
    json.dump(info, open(info_p, "w"), indent=1)
    print(f"gemini enrichment index cost (ledger) ${cost:.4f} over {calls} calls")


# ---------------------------------------------------------------- runs
def cmd_run():
    variant, out, rep, ver = arg("--variant"), arg("--out"), int(arg("--rep", 1)), arg("--verify")
    threads = int(arg("--threads", 4))
    if variant not in NAME:
        raise SystemExit("--variant none|gemma|gemini")
    state = {}
    if variant != "none":
        enr_info = json.load(open(os.path.join(OUT[variant], "info.json")))
        enr_ids = json.load(open(os.path.join(OUT[variant], "ids.json")))
        enr_V = np.load(os.path.join(OUT[variant], "emb.npy")).astype(np.float32)

        def mk_corpus(emb):
            assert emb == "bge_full"
            state["C"] = (ev.GemmaCorpus(CAP["gemma"], threads=threads) if variant == "gemma"
                          else ev.GeminiCorpus(CAP["gemini"]))
            return state["C"]

        class SwapIndex(e9.EnrichIndex):
            def __init__(self, enrich, items_by_code):
                super().__init__(enrich, items_by_code)  # BM25 + masks unchanged; bge vectors replaced below
                code_by_id = {it["id"]: c for c, it in items_by_code.items()}
                pos = {code_by_id[i]: n for n, i in enumerate(enr_ids)}
                assert set(pos) == set(self.codes) and len(pos) == len(self.codes)
                self.V = normalize(enr_V[[pos[c] for c in self.codes]])

        e9.Corpus = mk_corpus
        e9.EnrichIndex = SwapIndex
    sys.argv = [sys.argv[0], "--enrich", ENRICH, "--arms", "both", "--rep", str(rep), "--split", "dev", "--out", out]
    e9.main()
    run = json.load(open(out))
    m = run["meta"]
    if variant != "none":
        run["method"] = f"{NAME[variant]}:" + run["method"]
        run["embedding"] = CAP[variant]
        cap_info = json.load(open(os.path.join(ev.EMB_DIR, CAP[variant], "info.json")))
        m.update({"swap": "embedding model of both dense lists (caption + enrichment); BM25 lists unchanged",
                  "caption_embedding_info": cap_info, "enrich_embedding_info": enr_info,
                  "enrich_embedding_dir": os.path.relpath(OUT[variant], DATA)})
    if variant == "gemma":
        lat = state["C"].q_lat
        m.update({"query_embed_p50_s": round(float(np.median(lat)), 4), "query_embed_calls": len(lat),
                  "note": "query_p50_s includes local query embedding (all phrases of a search in one call, "
                          "shared by both dense lists); $0 embedding cost"})
    if variant == "gemini":
        qc = json.load(open(ev.GEMINI_QCACHE))["_meta"]["calls"]
        calls = [c for c in qc if c["rewrite"] == m["rewrite"]]
        api = float(np.median([c["seconds"] for c in calls]))
        qcost = sum(c["cost_usd"] for c in calls)
        m.update({"query_embed_api_p50_s": round(api, 3), "query_embed_cost_usd": round(qcost, 7),
                  "query_plus_embed_p50_s": round(m["query_p50_s"] + api, 3),
                  "index_cost_usd_caption": cap_info.get("index_cost_usd_ledger"),
                  "index_cost_usd_enrich": enr_info.get("index_cost_usd_ledger"),
                  "note": "query vectors from cache (evals/qcache/gemini2_768.json, filled in exp 11 with one live "
                          "API call per search, latency measured then); one vector set feeds both dense lists; "
                          "cost_usd = rewrite + query embedding (index costs separate)"})
        m["cost_usd"] = round(m.get("cost_usd", 0) + qcost, 6)
    m["load1_at_end"] = load_avg()
    json.dump(run, open(out, "w"))
    if ver:
        ref = json.load(open(ver))["queries"]
        same = sum(ref[k] == run["queries"].get(k) for k in ref)
        depth = min(len(v) for v in run["queries"].values())
        print(f"verify vs {os.path.basename(ver)}: {same}/{len(ref)} queries identical (min depth {depth})"
              + ("" if set(ref) == set(run["queries"]) else "; query sets differ"))
    print(f"meta added to {out}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"build-gemma": cmd_build_gemma, "pilot-gemini": cmd_pilot_gemini, "build-gemini": cmd_build_gemini,
     "run": cmd_run}.get(cmd, lambda: print(__doc__))()
