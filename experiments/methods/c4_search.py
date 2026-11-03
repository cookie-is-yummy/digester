"""PROTOTYPE ONLY - round 4.1 run files over the combined Instagram + YouTube index (c4_lib.Combined).

Configs (one variable each; LOG.md rows Y4.1-*):
  c0    combined baseline, platform-blind: qr-v1 rewrite (cached, 3 repeats) -> 3-small 512 d dense (max over query +
        phrases + HyDE, per-item gate, Rocchio PRF top 5) + BM25 over the view text (query + keywords) -> RRF k=60.
        More-like-this: example centroid dense + BM25 on the examples' text.
  c0ig  control: c0's method over Instagram items only, for ig_ searches only.
  c0yt  control: c0's method over YouTube items only, for yt_ searches only.
  c1    c0 + one combined te-v1c index (Instagram Y4.1-TE rows + YouTube round-3 allowed rows): te BM25 + te dense.
  c2    c1 with te rows rankable only for items whose own text is insufficient (c4_lib.insufficient).
  c3    c0 + qi-v3 intent, filters only (c4_intent.apply on c0's fused list; qr-v1 text plan unchanged).
Searches: load_queries('dev') + load_queries('yt_holdout') (controls: their platform's searches only).
Writes $DIGESTER_DATA/runs/r4.1/<config>_r<k>.json with lib/corpus.write_run; cost and latency in meta.
Prints aggregate timing and counts only (no query text, no items).

usage: python experiments/methods/c4_search.py --configs c0,c1,c2 [--reps 1,2,3]
       python experiments/methods/c4_search.py --configs c0ig
"""
import argparse
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
import c4_lib as L
from corpus import DATA, load_queries, write_run

OUT = os.path.join(DATA, "runs", "r4.1")
PLATFORM = {"c0": "all", "c1": "all", "c2": "all", "c3": "all", "c0ig": "instagram", "c0yt": "youtube"}
ENRICH = {"c1": "te", "c2": "te"}


def queries_for(cfg):
    qs = load_queries("dev") + load_queries("yt_holdout")
    if cfg == "c0ig":
        qs = [q for q in qs if q["id"].startswith("ig_")]
    elif cfg == "c0yt":
        qs = [q for q in qs if q["id"].startswith("yt_")]
    return qs


def te_cost_per_1k():
    """Mean te-v1c row cost (Batch, list prices) per platform, from the stored rows."""
    out = {}
    for name, p in (("instagram", os.path.join(DATA, "enrich", f"{L.TE_IG}.jsonl")),
                    ("youtube", os.path.join(DATA, "yt_enrich", f"{L.TE_YT}.jsonl"))):
        if os.path.exists(p):
            rows = [r for r in L.jl(p) if r.get("cost_usd") is not None]
            out[name] = {"rows": len(rows), "cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
                         "per_1k_items_usd": round(1000 * float(np.mean([r["cost_usd"] for r in rows])), 4)}
    return out


def run_config(S, cfg, reps, intent_mod=None):
    qs = queries_for(cfg)
    costs = {}
    for r in L.ledger():
        costs[r.get("purpose", "")] = costs.get(r.get("purpose", ""), 0) + r["cost_usd"]
    written = []
    for rep in reps:
        P = L.load_parses("qr-v1", rep)
        RW = P["_meta"]
        PI = L.load_parses("qi-v3", rep) if cfg == "c3" else None
        out, lat, lat_typed, intents = {}, [], [], {}
        S.QV.get([s for q in qs if not q["examples"] for s in [q["query"]] + P[q["id"]]["phrases"] +
                  (P[q["id"]].get("hypothetical_captions") or [])])  # cache first: latency = local search only
        for q in qs:
            t = time.time()
            fused = S.search(q, None if q["examples"] else P[q["id"]])
            if cfg == "c3" and not q["examples"]:
                raw_i = PI[q["id"]]["intent"]
                fused, info = intent_mod.apply(S, fused, intent_mod.guard_platform(raw_i, q["query"]))
                info["platform_dropped_by_guard"] = bool(raw_i.get("platform")) and \
                    not intent_mod.guard_platform(raw_i, q["query"]).get("platform")
                intents[q["id"]] = info
            out[q["id"]] = fused[:1000]
            dt = time.time() - t
            lat.append(dt)
            if not q["examples"]:
                lat_typed.append(dt)
        typed = [q["id"] for q in qs if not q["examples"]]
        pq = [RW["per_query"][k] for k in typed]
        meta = {"config": cfg, "round": "4.1", "platform_subset": S.platform,
                "rewrite": f"{RW['prompt_version']}_{RW['model']}_r{rep}", "hyde_alpha": L.HYDE_ALPHA,
                "embedding": "text-embedding-3-small@512", "splits": ["dev", "yt_holdout"], "n_searches": len(qs),
                **S.counts(), "index_build_s": round(S.build_s, 1),
                "query_p50_s": round(float(np.median(lat)), 3), "query_p95_s": round(float(np.percentile(lat, 95)), 3),
                "typed_query_p50_s": round(float(np.median(lat_typed)), 3),
                "rewrite_cost_usd": round(sum(v["cost_usd"] for v in pq), 6),
                "rewrite_cost_per_1k_searches_usd": round(1000 * float(np.mean([v["cost_usd"] for v in pq])), 4),
                "rewrite_p50_s": round(float(np.median([v["seconds"] for v in pq])), 3),
                "rewrite_p95_s": round(float(np.percentile([v["seconds"] for v in pq], 95)), 3),
                "offline_cost_usd_by_purpose": {k: round(v, 4) for k, v in costs.items()}}
        meta["typed_query_plus_rewrite_p50_s"] = round(meta["typed_query_p50_s"] + meta["rewrite_p50_s"], 3)
        if S.E:
            meta["enrichment"] = {"prompt": "te-v1c", "model": "gemini-3.1-flash-lite (Batch)",
                                  "routed_by_sufficiency": cfg == "c2",
                                  "insufficient_rule": "no own text | info class non_english | < 4 content words"
                                  if cfg == "c2" else None, "cost": te_cost_per_1k()}
        if cfg == "c3":
            pi = [PI["_meta"]["per_query"][k] for k in typed]
            meta.update({"intent_prompt": f"qi-v3_gpt-5-nano_r{rep}",
                         "intent_call_cost_usd": round(sum(v["cost_usd"] for v in pi), 6),
                         "intent_cost_per_1k_searches_usd": round(1000 * float(np.mean([v["cost_usd"] for v in pi])), 4),
                         "intent_p50_s": round(float(np.median([v["seconds"] for v in pi])), 3),
                         "intent_per_search": intents,
                         "searches_with_active_intent": sum(1 for v in intents.values() if v["intent"] != "none"),
                         "platform_filters_dropped_by_guard": sum(v["platform_dropped_by_guard"]
                                                                  for v in intents.values())})
        name = f"{cfg}_r{rep}"
        path = write_run(os.path.join(OUT, f"{name}.json"), f"c4:{cfg}+{meta['rewrite']}+hyde", L.CodeIds("oai512"),
                         out, meta)
        written.append(path)
        print(f"wrote {os.path.basename(path)}: {len(out)} searches, query p50 {meta['query_p50_s']} s, "
              f"p95 {meta['query_p95_s']} s", flush=True)
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", required=True)
    ap.add_argument("--reps", default="1,2,3")
    a = ap.parse_args()
    reps = [int(x) for x in a.reps.split(",")]
    cfgs = a.configs.split(",")
    plats = {PLATFORM[c] for c in cfgs}
    assert len(plats) == 1, "one platform subset per invocation"
    t0 = time.time()
    items = L.jl(os.path.join(DATA, "corpus", "items.jsonl"))
    S = L.Combined(plats.pop(), items=items)
    base_build = S.build_s
    print(f"index built in {base_build:.1f} s: {json.dumps(S.counts())}", flush=True)
    intent_mod = None
    for cfg in cfgs:
        t1 = time.time()
        S.E = []
        if cfg in ENRICH:
            active = {c for it, c in zip(S.items, S.codes) if L.insufficient(it)} if cfg == "c2" else None
            S.E = [L.EnrichIdx(L.te_sources(), set(S.pos), active)]
        S.build_s = base_build + (time.time() - t1)
        if cfg == "c3" and intent_mod is None:
            import c4_intent as intent_mod
            intent_mod.prepare(S)
        run_config(S, cfg, reps, intent_mod)
    print(f"total wall {time.time() - t0:.1f} s", flush=True)


if __name__ == "__main__":
    main()
