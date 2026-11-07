"""PROTOTYPE ONLY - round 6 run files (LOG.md Y6-G1 ... Y6-G5) over the combined index, one variable each vs C0.

Configs:
  c0chk  C0 from this runner (cached gpt-5-nano qr-v1 + 3-small 512 d): must reproduce r4.2/c0x exactly; also gives
         C0's latency row on the same footing. Written to tmp/r6_checks/, not for scoring.
  g1     qr-v1 on gpt-5.4-mini (reasoning none); everything else C0.
  g2     qr-v1 on gpt-5.5 (reasoning low); everything else C0.
  g3     escalation: gpt-5-nano parse (C0's), or gpt-5.4-mini's parse (G1's) when c6_lib.hard(query).
  g4     C0's nano parses + text-embedding-3-large @ 1,024 d for item, query, phrase, HyDE and outside-example vectors.
  g5     g4 + G1's gpt-5.4-mini parses.
Search code is c4_lib.Combined (typed + more-like-this) unchanged. Repeat k uses repeat k of every parse file.

Latency per typed search = local search (query vectors cached first) + the rewrite call(s) (original, uncached call
seconds) + one live query-embedding call for all of that search's strings (timing only; its vectors are not used).
Writes $DIGESTER_DATA/runs/r6/<cfg>_r<k>.json (lib/corpus.write_run). Prints aggregates only (no query text, no items).

usage: python experiments/methods/c6_search.py --configs c0chk,g1,g2,g3,g4,g5 [--reps 1,2,3] [--no-timing]
       python experiments/methods/c6_search.py --variability
"""
import argparse
import collections
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
import ai  # noqa: E402
import c4_lib as L  # noqa: E402
import c6_lib as G  # noqa: E402
from corpus import DATA, load_queries, write_run  # noqa: E402

RW_DIR = os.path.join(DATA, "runs", "rewrites")
NANO, MINI, FLAG = "gpt-5-nano", "gpt-5.4-mini", "gpt-5.5"
PARSE = {"c0chk": NANO, "g1": MINI, "g2": FLAG, "g3": "escalate", "g4": NANO, "g5": MINI}
LARGE = {"g4", "g5"}
CONFIGS = list(PARSE)


def rw(model, rep):
    return json.load(open(os.path.join(RW_DIR, f"qr-v1_{model}_r{rep}.json")))


def queries():
    return load_queries("dev") + load_queries("yt_holdout")


def pct(xs, p):
    return round(float(np.percentile(xs, p)), 3) if xs else None


def plan_for(cfg, q, rep, P):
    """(parse, rewrite calls as [(model, per_query row)] booked as specified, routed calls, escalated?)"""
    qid = q["id"]
    if cfg != "g3":
        m = PARSE[cfg]
        row = P[m]["_meta"]["per_query"][qid]
        return P[m][qid], [(m, row)], [(m, row)], False
    is_hard, _ = G.hard(q["query"])
    nrow = P[NANO]["_meta"]["per_query"][qid]
    if not is_hard:
        return P[NANO][qid], [(NANO, nrow)], [(NANO, nrow)], False
    mrow = P[MINI]["_meta"]["per_query"][qid]
    return P[MINI][qid], [(NANO, nrow), (MINI, mrow)], [(MINI, mrow)], True


def strings(q, parse):
    return [q["query"]] + parse["phrases"] + (parse.get("hypothetical_captions") or [])


def time_embed(texts, large):
    """One live embedding call for one search's strings (timing only). Returns (seconds, tokens, cost)."""
    n0 = len(L.ledger())
    t = time.time()
    if large:
        ai.openai_embed(texts, model=G.EMB3L_MODEL, dimensions=G.EMB3L_DIM, purpose="c6_query_embed_timing")
    else:
        ai.openai_embed(texts, model="text-embedding-3-small", dimensions=512, purpose="c6_query_embed_timing")
    sec = time.time() - t
    row = L.ledger()[n0:][-1]
    return sec, row["in_tokens"], row["cost_usd"]


def top10_diag(out, ref):
    diff, ovl, cross = 0, [], {"ig_": [], "yt_": []}
    plat = REF_PLAT
    for qid, lst in out.items():
        a, b = lst[:10], ref["queries"].get(qid, [])[:10]
        diff += a != b
        ovl.append(len(set(a) & set(b)) / 10)
        pre = qid[:3]
        if pre in cross and a:
            own = "instagram" if pre == "ig_" else "youtube"
            cross[pre].append(sum(plat.get(c) != own for c in a) / len(a))
    return {"top10_differs_from_c0x": diff, "mean_top10_overlap_with_c0x": round(float(np.mean(ovl)), 3),
            "other_platform_share_top10": {k: round(float(np.mean(v)), 3) for k, v in cross.items() if v}}


REF_PLAT = {}


def run_config(S, cfg, reps, timing, item_emb):
    qs = queries()
    written = []
    large = cfg in LARGE
    for rep in reps:
        P = {m: rw(m, rep) for m in {NANO, MINI, FLAG} if os.path.exists(os.path.join(RW_DIR, f"qr-v1_{m}_r{rep}.json"))}
        plans = {q["id"]: plan_for(cfg, q, rep, P) for q in qs if not q["examples"]}
        S.QV.get([s for q in qs if not q["examples"] for s in strings(q, plans[q["id"]][0])])  # cache first
        out, per = {}, {}
        lat_local, lat_total, lat_routed, lat_all = [], [], [], []
        cost_rw, cost_rw_routed, cost_emb, n_esc = 0.0, 0.0, 0.0, 0
        emb_secs = []
        by_model = collections.Counter()
        spent0 = len(L.ledger())
        for q in qs:
            t = time.time()
            parse = None if q["examples"] else plans[q["id"]][0]
            fused = S.search(q, parse)
            local = time.time() - t
            out[q["id"]] = fused[:1000]
            lat_all.append(local)
            if q["examples"]:
                continue
            _, calls, routed, esc = plans[q["id"]]
            n_esc += esc
            rsec = sum(r["seconds"] for _, r in calls)
            rsec_routed = sum(r["seconds"] for _, r in routed)
            cost_rw += sum(r["cost_usd"] for _, r in calls)
            cost_rw_routed += sum(r["cost_usd"] for _, r in routed)
            for m, r in calls:
                by_model[m] += r["cost_usd"]
            esec, etok, ecost = time_embed(strings(q, parse), large) if timing else (0.0, 0, 0.0)
            emb_secs.append(esec)
            cost_emb += ecost
            lat_local.append(local)
            lat_total.append(local + rsec + esec)
            lat_routed.append(local + rsec_routed + esec)
            per[q["id"]] = {"latency_total_s": round(lat_total[-1], 3), "latency_local_s": round(local, 4),
                            "rewrite_s": round(rsec, 3), "query_embed_s": round(esec, 3),
                            "rewrite_models": [m for m, _ in calls], "escalated": esc}
        n = len(lat_total)
        new_spend = sum(r["cost_usd"] for r in L.ledger()[spent0:])
        models = sorted({m for v in plans.values() for m, _ in v[1]})
        meta = {"config": cfg, "round": "6", "repeat": rep, "splits": ["dev", "yt_holdout"], "n_searches": len(qs),
                "n_typed": n, "plan": "qr-v1 (prompt unchanged)",
                "rewrite_models": {m: G.REASONING[m] for m in models},
                "rewrites": [f"qr-v1_{m}_r{rep}" for m in models],
                "embedding": f"{G.EMB3L_MODEL}@{G.EMB3L_DIM}" if large else "text-embedding-3-small@512",
                "hyde_alpha": L.HYDE_ALPHA, "fusion": "RRF k=60", **S.counts(),
                "index_build_s": round(S.build_s, 1),
                "query_local_p50_s": pct(lat_all, 50), "query_local_p95_s": pct(lat_all, 95),
                "typed_local_p50_s": pct(lat_local, 50), "typed_local_p95_s": pct(lat_local, 95),
                "query_embed_call_p50_s": pct(emb_secs, 50) if timing else None,
                "query_embed_call_p95_s": pct(emb_secs, 95) if timing else None,
                "typed_total_p50_s": pct(lat_total, 50), "typed_total_p95_s": pct(lat_total, 95),
                "latency_model": "local search (vectors cached) + rewrite call(s) at their original uncached seconds "
                                 "(G3: nano then mini on hard searches, sequential) + one live query-embedding call "
                                 "per search (timing only)" if timing else "local + rewrite only (no embed timing)",
                "rewrite_cost_usd": round(cost_rw, 6), "rewrite_cost_by_model_usd": {k: round(v, 6) for k, v in by_model.items()},
                "rewrite_cost_per_1k_searches_usd": round(1000 * cost_rw / max(n, 1), 4),
                "query_embed_cost_per_1k_searches_usd": round(1000 * cost_emb / max(n, 1), 5) if timing else None,
                "cost_per_1k_searches_usd": round(1000 * (cost_rw + cost_emb) / max(n, 1), 4),
                "cost_note": "ledger list prices, uncached input price; per 1k typed searches",
                "item_embedding_one_off": item_emb if large else
                {"model": "text-embedding-3-small@512", "note": "existing store corpus/emb/oai512 (round 4)"},
                "new_spend_this_run_usd": round(new_spend, 6), "per_search": per}
        if cfg == "g3":
            meta["escalation"] = {"rule": "c6_lib.hard (LOG.md Round 6 block)", "escalated": n_esc, "typed": n,
                                  "rate": round(n_esc / max(n, 1), 3),
                                  "reasons": dict(collections.Counter(r for q in qs if not q["examples"]
                                                                      for r in G.hard(q["query"])[1]))}
            meta["routed_variant"] = {"note": "same rankings; mini only on hard searches, nano only on the rest",
                                      "typed_total_p50_s": pct(lat_routed, 50), "typed_total_p95_s": pct(lat_routed, 95),
                                      "rewrite_cost_per_1k_searches_usd": round(1000 * cost_rw_routed / max(n, 1), 4),
                                      "cost_per_1k_searches_usd": round(1000 * (cost_rw_routed + cost_emb) / max(n, 1), 4)}
        ref = json.load(open(os.path.join(DATA, "runs", "r4.2", f"c0x_r{rep}.json")))
        meta["diagnostics"] = top10_diag(out, ref)
        outdir = os.path.join(DATA, "tmp", "r6_checks") if cfg == "c0chk" else os.path.join(DATA, "runs", "r6")
        path = write_run(os.path.join(outdir, f"{cfg}_r{rep}.json"), f"c6:{cfg}+qr-v1:{'+'.join(models)}",
                         L.CodeIds(meta["embedding"]), out, meta)
        if cfg == "c0chk":
            same = sum(out[k] == ref["queries"][k][:1000] for k in out)
            print(f"c0chk r{rep}: {same} of {len(out)} rankings identical to r4.2/c0x_r{rep} (1,000 deep)", flush=True)
        written.append(path)
        print(f"wrote {os.path.basename(path)}: local p50 {meta['typed_local_p50_s']} s; total p50 "
              f"{meta['typed_total_p50_s']} / p95 {meta['typed_total_p95_s']} s; cost/1k ${meta['cost_per_1k_searches_usd']}; "
              f"esc {n_esc}; new spend ${new_spend:.4f}; {json.dumps(meta['diagnostics'])}", flush=True)
    return written


def variability():
    qs = [q for q in queries() if not q["examples"]]
    out = {}
    for m in (NANO, MINI, FLAG):
        sets = [rw(m, k) for k in (1, 2, 3)]
        out[m] = {"keywords": G.keyword_jaccard(sets), "phrase_words": G.phrase_jaccard(sets)}
    esc = [rw(NANO, k) for k in (1, 2, 3)]
    mini = [rw(MINI, k) for k in (1, 2, 3)]
    comp = []
    for k in range(3):
        d = {}
        for q in qs:
            d[q["id"]] = (mini[k] if G.hard(q["query"])[0] else esc[k])[q["id"]]
        comp.append(d)
    out["g3_escalation"] = {"keywords": G.keyword_jaccard(comp), "phrase_words": G.phrase_jaccard(comp)}
    hard = [q for q in qs if G.hard(q["query"])[0]]
    out["g3_rate"] = {"hard": len(hard), "typed": len(qs), "rate": round(len(hard) / len(qs), 3),
                      "reasons": dict(collections.Counter(r for q in qs for r in G.hard(q["query"])[1]))}
    for name, ids in (("hard_only", {q["id"] for q in hard}), ("not_hard", {q["id"] for q in qs} - {q["id"] for q in hard})):
        for m in (NANO, MINI, FLAG):
            sets = [{k: v for k, v in rw(m, r).items() if k in ids} for r in (1, 2, 3)]
            out.setdefault(name, {})[m] = G.keyword_jaccard(sets)["mean"]
    # agreement between models (same repeat): how far each stronger model's keywords are from nano's
    for m in (MINI, FLAG):
        vals = []
        for k in (1, 2, 3):
            a, b = rw(NANO, k), rw(m, k)
            vals += [G.jaccard(a[q["id"]]["keywords"], b[q["id"]]["keywords"]) for q in qs]
        out.setdefault("vs_nano_same_repeat_keyword_jaccard", {})[m] = round(float(np.mean(vals)), 4)
    stats = {}
    for m in (NANO, MINI, FLAG):
        ps = [rw(m, k) for k in (1, 2, 3)]
        stats[m] = {"mean_keywords": round(float(np.mean([len(P[q["id"]]["keywords"]) for P in ps for q in qs])), 2),
                    "mean_phrases": round(float(np.mean([len(P[q["id"]]["phrases"]) for P in ps for q in qs])), 2),
                    "filters_nonempty": sum(bool(P[q["id"]]["filters"]["before"] or P[q["id"]]["filters"]["after"]
                                                 or P[q["id"]]["filters"]["interactions"]) for P in ps for q in qs)}
    out["parse_stats"] = stats
    print(json.dumps(out, indent=1))
    json.dump(out, open(os.path.join(DATA, "runs", "r6", "variability.json"), "w"), indent=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", default="")
    ap.add_argument("--reps", default="1,2,3")
    ap.add_argument("--no-timing", action="store_true")
    ap.add_argument("--variability", action="store_true")
    a = ap.parse_args()
    if a.variability:
        variability()
        return
    cfgs = a.configs.split(",")
    assert all(c in CONFIGS for c in cfgs), cfgs
    reps = [int(x) for x in a.reps.split(",")]
    t0 = time.time()
    S = L.Combined("all", items=L.jl(os.path.join(DATA, "corpus", "items.jsonl")))
    REF_PLAT.update({c: it["platform"] for it, c in zip(S.items, S.codes)})
    print(f"index built in {S.build_s:.1f} s", flush=True)
    for cfg in [c for c in cfgs if c not in LARGE]:
        run_config(S, cfg, reps, not a.no_timing, None)
    big = [c for c in cfgs if c in LARGE]
    if big:
        t1 = time.time()
        G.swap_to_3l(S)
        S.build_s += time.time() - t1
        summ = os.path.join(L.EMB, G.STORE_3L, "build_summary.json")
        item_emb = json.load(open(summ)) if os.path.exists(summ) else None
        if item_emb:
            item_emb["per_1k_items_usd"] = round(1000 * item_emb["cost_usd"] / item_emb["items"], 5)
        print(f"swapped to {G.EMB3L_MODEL}@{G.EMB3L_DIM} in {time.time() - t1:.1f} s", flush=True)
        for cfg in big:
            run_config(S, cfg, reps, not a.no_timing, item_emb)
    print(f"total wall {time.time() - t0:.1f} s", flush=True)


if __name__ == "__main__":
    main()
