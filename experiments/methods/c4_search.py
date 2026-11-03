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
Round 4.2 (LOG.md Y4.2-*; written to runs/r4.2/):
  d1    c1's lists with coverage-fair fusion (c4_lib.Combined.fuse, fusion="fair").
  d1p   d1 with te-list ranks scaled to the corpus (fusion="fair_scaled").
  d2    c0's lists; insufficient items with a te row get te text merged into their own view (merge_te=True).
  d3    c0 + the cached qi-v3 intent under code-side guards (c4_intent.guard_v42, unknown_watch=True).
  d4    d1 + d3's guarded intent (fixed in Y4.2-D4).
  c0x   control, not a hypothesis: c0 re-run with the cached (float16) query vectors the d* runs use. The r4.1 c0
        files were written with fresh float32 query vectors; top-100 sets match, order within them can differ.
Round 4.3 (LOG.md Y4.3-*; written to runs/r4.3/):
  e1    d4 with guards that only widen (c4_intent.guard_v43, widen_only=True).
  e2    d1 with te rows rankable only for items that are not descriptive (c4_lib.descriptive); fusion "fair".
  e3    e2 + e1's guarded intent.
  e4    e3 with per-group own BM25 statistics (c4_lib.Combined.use_group_bm25).
Searches: load_queries('dev') + load_queries('yt_holdout') (controls: their platform's searches only).
Writes $DIGESTER_DATA/runs/r4.1/<config>_r<k>.json with lib/corpus.write_run; cost and latency in meta.
Prints aggregate timing and counts only (no query text, no items).

usage: python experiments/methods/c4_search.py --configs c0,c1,c2 [--reps 1,2,3]
       python experiments/methods/c4_search.py --configs d1,d1p,d3,d4   then   --configs d2
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

PLATFORM = {"c0": "all", "c1": "all", "c2": "all", "c3": "all", "c0ig": "instagram", "c0yt": "youtube",
            "d1": "all", "d1p": "all", "d2": "all", "d3": "all", "d4": "all", "c0x": "all",
            "e1": "all", "e2": "all", "e3": "all", "e4": "all"}
ENRICH = {"c1": "te", "c2": "te", "d1": "te", "d1p": "te", "d4": "te", "e1": "te", "e2": "te", "e3": "te", "e4": "te"}
FUSION = {"d1": "fair", "d1p": "fair_scaled", "d4": "fair", "e1": "fair", "e2": "fair", "e3": "fair", "e4": "fair"}
MERGE = {"d2"}
INTENT = {"c3", "d3", "d4", "e1", "e3", "e4"}
GUARDED = {"d3", "d4", "e1", "e3", "e4"}
WIDEN = {"e1", "e3", "e4"}          # guard_v43 + widen_only
NONDESC = {"e2", "e3", "e4"}        # te rows rankable only for non-descriptive items
GROUP_BM25 = {"e4"}


# Alternative query file (e.g. the frozen test searches): set from the CLI; defaults keep the dev + yt_holdout runs.
ALT = {"queries": None, "rewrites": None, "outdir": None, "suffix": "", "splits": None}


def round_of(cfg):
    return "4.3" if cfg.startswith("e") else "4.2" if cfg.startswith("d") or cfg == "c0x" else "4.1"


def out_dir(cfg):
    return ALT["outdir"] or os.path.join(DATA, "runs", "r" + round_of(cfg))


def queries_for(cfg):
    if ALT["queries"]:
        qs = [json.loads(line) for line in open(ALT["queries"]) if line.strip()]
    else:
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
        P = L.load_parses("qr-v1", rep, ALT["rewrites"])
        RW = P["_meta"]
        PI = L.load_parses("qi-v3", rep, ALT["rewrites"]) if cfg in INTENT else None
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
            elif cfg in GUARDED and not q["examples"]:
                raw_i = PI[q["id"]]["intent"]
                guard = intent_mod.guard_v43 if cfg in WIDEN else intent_mod.guard_v42
                gi, dropped = guard(raw_i, q["query"], PI[q["id"]].get("kind"))
                fused, info = intent_mod.apply(S, fused, gi, unknown_watch=True, widen_only=cfg in WIDEN)
                info.update({"raw_intent": intent_mod.describe(raw_i), "dropped_by_guard": dropped,
                             "platform_dropped_by_guard": "platform" in dropped})
                intents[q["id"]] = info
            out[q["id"]] = fused[:1000]
            dt = time.time() - t
            lat.append(dt)
            if not q["examples"]:
                lat_typed.append(dt)
        typed = [q["id"] for q in qs if not q["examples"]]
        pq = [RW["per_query"][k] for k in typed]
        meta = {"config": cfg, "round": round_of(cfg), "platform_subset": S.platform,
                "rewrite": f"{RW['prompt_version']}_{RW['model']}_r{rep}", "hyde_alpha": L.HYDE_ALPHA,
                "embedding": "text-embedding-3-small@512", "splits": ALT["splits"] or ["dev", "yt_holdout"],
                "n_searches": len(qs),
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
                                  "routed_by_sufficiency": cfg == "c2", "fusion": S.fusion,
                                  "te_rankable_only_non_descriptive": cfg in NONDESC,
                                  "descriptive_rule": "own text kind title AND >= 4 content words AND not non_english "
                                                      "AND not a placeholder title" if cfg in NONDESC else None,
                                  "insufficient_rule": "no own text | info class non_english | < 4 content words"
                                  if cfg == "c2" else None, "cost": te_cost_per_1k()}
        if cfg in MERGE:
            meta["merge_te"] = {"rule": "insufficient (Y4.1-C2 rule) AND has a rankable te-v1c row: own view + te text "
                                        "as BM25 text and a 3-small 512 d vector of it; gated in",
                                "embedding_store": L.D2_STORE, "te_cost": te_cost_per_1k(),
                                "merged_embed_cost_usd": round(costs.get("c4_d2_merged_embed", 0.0), 5)}
        if cfg in INTENT:
            pi = [PI["_meta"]["per_query"][k] for k in typed]
            meta.update({"intent_prompt": f"qi-v3_gpt-5-nano_r{rep}",
                         "intent_call_cost_usd": round(sum(v["cost_usd"] for v in pi), 6),
                         "intent_cost_per_1k_searches_usd": round(1000 * float(np.mean([v["cost_usd"] for v in pi])), 4),
                         "intent_p50_s": round(float(np.median([v["seconds"] for v in pi])), 3),
                         "intent_per_search": intents,
                         "searches_with_active_intent": sum(1 for v in intents.values() if v["intent"] != "none"),
                         "platform_filters_dropped_by_guard": sum(v["platform_dropped_by_guard"]
                                                                  for v in intents.values())})
            if cfg in GUARDED:
                meta["intent_guard"] = ("c4_intent.guard_v43 (LOG.md Y4.3-E1); unknown_watch=True, widen_only=True"
                                        if cfg in WIDEN else "c4_intent.guard_v42 (LOG.md Y4.2-D3); unknown_watch=True")
                meta["intent_note"] = ("cached round-4.1 qi-v3 outputs reused: no new intent calls this round"
                                       if not ALT["rewrites"] else
                                       f"qi-v3 outputs from {ALT['rewrites']} (same prompt, model and settings)")
                meta["searches_with_any_field_dropped"] = sum(1 for v in intents.values() if v["dropped_by_guard"])
                meta["searches_with_raw_intent"] = sum(1 for v in intents.values() if v["raw_intent"] != "none")
                meta["watch_data_platforms"] = S.watch_platforms
                meta["watch_coverage_by_platform"] = S.watch_coverage
        name = f"{cfg}{ALT['suffix']}_r{rep}"
        if ALT["queries"]:
            meta["queries_file"] = os.path.basename(ALT["queries"])
            meta["rewrites_dir"] = ALT["rewrites"]
        if cfg in NONDESC:
            meta["descriptive_counts"] = S.desc_counts
        path = write_run(os.path.join(out_dir(cfg), f"{name}.json"), f"c4:{cfg}+{meta['rewrite']}+hyde", L.CodeIds("oai512"),
                         out, meta)
        written.append(path)
        print(f"wrote {os.path.basename(path)}: {len(out)} searches, query p50 {meta['query_p50_s']} s, "
              f"p95 {meta['query_p95_s']} s", flush=True)
    return written


def descriptive_counts(S):
    """Aggregate counts for the E2 rule: items marked descriptive, and te rows kept / removed, per platform."""
    te = set(L.te_rows())
    out = {}
    for it, c in zip(S.items, S.codes):
        p = it["platform"]
        d = out.setdefault(p, {"items": 0, "descriptive": 0, "placeholder_title": 0, "te_rows": 0,
                               "te_rows_rankable": 0, "te_rows_removed_descriptive": 0})
        d["items"] += 1
        desc = L.descriptive(it)
        d["descriptive"] += desc
        d["placeholder_title"] += L.own_text_kind(it) == "title" and L.placeholder_title(it)
        if c in te:
            d["te_rows"] += 1
            d["te_rows_removed_descriptive" if desc else "te_rows_rankable"] += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", required=True)
    ap.add_argument("--reps", default="1,2,3")
    ap.add_argument("--queries", default=None, help="alternative query file (same format as evals/queries.jsonl)")
    ap.add_argument("--rewrites-dir", default=None, help="qr-v1 / qi-v3 cache dir (default runs/rewrites)")
    ap.add_argument("--outdir", default=None, help="run file dir (default runs/r<round>)")
    ap.add_argument("--suffix", default="", help="run name suffix, e.g. _test -> <cfg>_test_r<k>.json")
    ap.add_argument("--splits", default=None, help="comma list recorded in meta.splits")
    a = ap.parse_args()
    ALT.update({"queries": a.queries, "rewrites": a.rewrites_dir, "outdir": a.outdir, "suffix": a.suffix,
                "splits": a.splits.split(",") if a.splits else None})
    reps = [int(x) for x in a.reps.split(",")]
    cfgs = a.configs.split(",")
    plats = {PLATFORM[c] for c in cfgs}
    assert len(plats) == 1, "one platform subset per invocation"
    assert len({c in MERGE for c in cfgs}) == 1, "merged-view configs (d2) need their own invocation"
    t0 = time.time()
    items = L.jl(os.path.join(DATA, "corpus", "items.jsonl"))
    S = L.Combined(plats.pop(), items=items, merge_te=cfgs[0] in MERGE)
    base_build = S.build_s
    print(f"index built in {base_build:.1f} s: {json.dumps(S.counts())}", flush=True)
    if any(c in NONDESC for c in cfgs):
        S.desc_counts = descriptive_counts(S)
        print(f"descriptive: {json.dumps(S.desc_counts)}", flush=True)
    intent_mod = None
    for cfg in cfgs:
        t1 = time.time()
        S.E = []
        if cfg in ENRICH:
            active = None
            if cfg == "c2":
                active = {c for it, c in zip(S.items, S.codes) if L.insufficient(it)}
            elif cfg in NONDESC:
                active = {c for it, c in zip(S.items, S.codes) if not L.descriptive(it)}
            S.E = [L.EnrichIdx(L.te_sources(), set(S.pos), active)]
        S.fusion = FUSION.get(cfg, "rrf")
        S.use_group_bm25(cfg in GROUP_BM25)
        S.build_s = base_build + (time.time() - t1)
        if cfg in INTENT and intent_mod is None:
            import c4_intent as intent_mod
            intent_mod.prepare(S)
        run_config(S, cfg, reps, intent_mod)
    print(f"total wall {time.time() - t0:.1f} s", flush=True)


if __name__ == "__main__":
    main()
