"""PROTOTYPE ONLY - round 7 run files (LOG.md "Round 7 fixed parameters", Y7-H0 ... Y7-H6) over the combined index.

Configs (one variable each vs H0 = G4; H5 / H5b / H6 fixed in LOG.md before any run):
  h0chk  H0 from this runner (3-large, cached nano qr-v1): must reproduce r6/g4 exactly; written to tmp/r7_checks/.
  h0     the same as h0chk, written to runs/r7/ (H0's run file: r6/g4 is not reproducible, see LOG.md).
  h1     H0 + qr-v1's own filters with E1's guards (widen only) + soft old / new time boost.
  h2     H0 + facet boost (format / tone classifiers) where the cached guarded qs-v1 slots ask for a format or tone.
  h3     H0 + router: platform-share calibration + creator search (3-large profiles, no pick) on router-creator searches.
  h4     H0 + creator search with era / affinity / channel-type profiles on qs-v1 creator_lookup searches.
  h5     H0 + H1 + H2 + H3 + H4 (composition in LOG.md).
  h5b    h5 + F0's te lists (caption-type / untitled items) under coverage-fair fusion.
  h6     h5 + cross-encoder rerank of the top 50 (optional; needs sentence-transformers).
Searches: dev + yt_holdout (or --queries FILE). Repeat k uses qr-v1 / qs-v1 repeat k (cached, round 4.1 / 5).
Latency per typed search = local search (router, boosts, creators, CE included; facet probabilities precomputed) +
max(qr-v1, qs-v1 seconds where read; original uncached call times, in parallel) + one live 3-large query-embedding
call (timing only, measured once per search and repeat and shared by every arm). Prints aggregates only.

usage: python experiments/methods/c7_search.py --configs h0chk,h1,h2,h3,h4,h5,h5b[,h6] [--reps 1,2,3]
       python experiments/methods/c7_search.py --stats     # fire counts per queries.jsonl kind, from the run files
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
import c4_intent as I  # noqa: E402
import c4_lib as L  # noqa: E402
import c5_lib as F  # noqa: E402
import c6_lib as G  # noqa: E402
import c7_lib as H  # noqa: E402
from corpus import DATA, load_queries, rrf, write_run  # noqa: E402

CONFIGS = ["h0chk", "h0", "h1", "h2", "h3", "h4", "h5", "h5b", "h6"]
PART = {"h1": {"h1"}, "h2": {"h2"}, "h3": {"h3"}, "h4": {"h4"}, "h5": {"h1", "h2", "h3", "h4"},
        "h5b": {"h1", "h2", "h3", "h4", "te"}, "h6": {"h1", "h2", "h3", "h4", "ce"}, "h0chk": set(), "h0": set()}
USES_QS = {"h2", "h4", "h5", "h5b", "h6"}
ALT = {"queries": None, "rewrites": None, "outdir": None, "suffix": "", "splits": None, "ref": "r7/h0_r{rep}.json"}
CE_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
CE_TOP = 50


def queries():
    if ALT["queries"]:
        return [json.loads(line) for line in open(ALT["queries"]) if line.strip()]
    return load_queries("dev") + load_queries("yt_holdout")


def rw(prefix, rep):
    d = ALT["rewrites"] or os.path.join(DATA, "runs", "rewrites")
    return json.load(open(os.path.join(d, f"{prefix}_gpt-5-nano_r{rep}.json")))


def pct(xs, p):
    return round(float(np.percentile(xs, p)), 3) if xs else None


class Env:
    def __init__(self):
        t0 = time.time()
        items = L.jl(os.path.join(DATA, "corpus", "items.jsonl"))
        self.S = L.Combined("all", items=items)
        G.swap_to_3l(self.S)
        self.h0_build_s = time.time() - t0
        S = self.S
        I.prepare(S)
        self.QVs = L.QueryVecs()  # 3-small query vectors, only for te dense (H5b)
        self.te_rows = F.te_meta_rows()
        self.facets = H.Facets7()
        self.router = H.Router()
        self.tp = H.TimePct(S)
        src = {"instagram": "ig", "youtube": "yt"}  # adapter source -> group label used by the router's head
        self.group = {c: src.get(it["platform"]) for it, c in zip(S.items, S.codes)}
        t1 = time.time()
        self.CR3 = H.Creators7(S, self.te_rows, enriched=False)
        self.CR4 = H.Creators7(S, self.te_rows, self.facets, enriched=True)
        self.creator_build_s = time.time() - t1
        self.CR_elig = set(self.CR3.of)
        self.E_f0 = L.EnrichIdx(L.te_sources(), set(S.pos), F.te_active_f0(S))
        self.ce = None
        self.build_s = time.time() - t0

    def need_ce(self):
        if self.ce is None:
            from sentence_transformers import CrossEncoder
            self.ce = CrossEncoder(CE_MODEL, max_length=256, device="cpu")
        return self.ce


def small_qv(env, q, parse):
    """3-small query + phrase + HyDE vectors (as c5_lib.own_lists builds Qv), for te dense only."""
    texts, caps, _ = F.plan_c0(q, parse)
    Qv = env.QVs.get(texts)
    if caps:
        Hh = env.QVs.get(caps)
        v = (1 - L.HYDE_ALPHA) * Qv[0] + L.HYDE_ALPHA * Hh.mean(0)
        Qv = np.vstack([Qv, (v / np.linalg.norm(v))[None, :]])
    return Qv


def search_one(env, cfg, q, parse, slots):
    S = env.S
    parts = PART[cfg]
    info = {}
    if q["examples"]:
        if "te" in parts:
            S.E, S.fusion = [env.E_f0], "fair"
        out = S.mlt(q)
        S.E, S.fusion = [], "rrf"
        return out, info
    keep = S.keep_fn(q.get("filters"))
    texts, caps, bq = F.plan_c0(q, parse)
    own, Qv = F.own_lists(S, texts, caps, bq, keep)
    groups = []
    if "te" in parts:
        groups.append(([env.E_f0.bm25(bq, keep), env.E_f0.dense(small_qv(env, q, parse), keep)], env.E_f0.codeset))
    order, sc = F.fair_fuse(own, groups)
    # router (H3)
    rt = None
    if "h3" in parts:
        rt = env.router.predict(S.QV.get([q["query"]])[0])
        info["router"] = rt
    # creator search (H3: router; H4: qs-v1; H5: either)
    trig = []
    if "h3" in parts and rt["type"] == "creator":
        trig.append("router")
    if "h4" in parts and slots["creator_lookup"]["is"]:
        trig.append("qs-v1")
    if trig:
        enriched = "h4" in parts
        CR = env.CR4 if enriched else env.CR3
        desc = (slots["creator_lookup"]["description"] or "").strip() if (enriched and slots) else ""
        dtexts = ([desc] if desc else []) + [q["query"]] + list(parse["phrases"])
        bmq = " ".join(([desc] if desc else []) + [q["query"]] + list(parse["keywords"]))
        direction = H.lexicon_dir(q["query"]) if enriched else None
        ranking = CR.rank(S.QV, dtexts, bmq, order, direction=direction)
        clist = CR.item_list(S, ranking, order, Qv, keep)
        order, sc = F.fair_fuse(own, groups + [([clist], env.CR_elig)])
        info["creator"] = {"trigger": trig, "profiles": "h4" if enriched else "h3", "listed": len(clist),
                           "era_direction": direction}
    # platform-share calibration (H3)
    if "h3" in parts:
        order, sc, cinfo = H.calibrate(order, sc, env.group, rt["p_platform"])
        info["calibration"] = cinfo
    # boosts on the top 300 (H2 facets, H1 soft time)
    add = np.zeros(min(len(order), H.BOOST_DEPTH), np.float32)
    head = order[:H.BOOST_DEPTH]
    boosted = False
    if "h2" in parts:
        act = H.active_facets(slots)
        if act:
            d = np.mean([H.centred(env.facets.score(head, a)) for a in act], axis=0)
            add += H.BOOST * d
            boosted = True
        info["facets"] = [a[0] + ":" + (a[1] if isinstance(a[1], str) else "+".join(a[1])) for a in act]
    gi = None
    if "h1" in parts:
        raw = H.qr_intent(parse)
        gi, dropped = I.guard_v43(raw, q["query"], parse.get("kind"))
        direction, src = H.time_dir(q["query"], raw, gi)
        info["time"] = {"direction": direction, "source": src, "raw": I.describe(raw), "guarded": I.describe(gi),
                        "dropped_by_guard": dropped}
        if direction:
            add += H.BOOST * H.centred(env.tp.u(S, head, direction))
            boosted = True
    if boosted:
        order, sc = H.boost_top(order, sc, add)
    if gi is not None:
        order, iinfo = I.apply(S, order, gi, unknown_watch=True, widen_only=True)
        info["intent"] = {"mode": iinfo["mode"], "pool": iinfo["pool"]}
    # cross-encoder (H6)
    if "ce" in parts:
        top = order[:CE_TOP]
        ce = env.need_ce()
        pairs = [(q["query"], S.text.get(c) or "") for c in top]
        s = ce.predict(pairs, batch_size=25, show_progress_bar=False)
        ce_rank = [top[n] for n in np.argsort(-np.asarray(s), kind="stable")]
        new = rrf(top, ce_rank)  # ties keep H5's order (H5 ranks are inserted first)
        order = new + order[CE_TOP:]
        info["ce"] = {"moved": sum(1 for a, b in zip(top, new) if a != b)}
    return order[:1000], info


def embed_timing(qs, plans, rep):
    """One live 3-large call per typed search with its strings; cached per repeat so every arm shares the same."""
    p = os.path.join(DATA, "r7", f"embed_timing_r{rep}.json")
    if os.path.exists(p):
        return json.load(open(p))
    out = {}
    for q in qs:
        if q["examples"]:
            continue
        parse = plans[q["id"]]
        texts = [q["query"]] + parse["phrases"] + (parse.get("hypothetical_captions") or [])
        n0 = len(L.ledger())
        t = time.time()
        ai.openai_embed(texts, model=G.EMB3L_MODEL, dimensions=G.EMB3L_DIM, purpose="c7_query_embed_timing")
        sec = time.time() - t
        row = L.ledger()[n0:][-1]
        out[q["id"]] = {"seconds": round(sec, 3), "cost_usd": row["cost_usd"]}
    H.jdump(out, p)
    return out


def top10_diag(out, ref, plat):
    diff, ovl, cross = 0, [], {"ig_": [], "yt_": []}
    for qid, lst in out.items():
        a, b = lst[:10], ref["queries"].get(qid, [])[:10]
        diff += a != b
        ovl.append(len(set(a) & set(b)) / 10)
        pre = qid[:3]
        if pre in cross and a:
            own = "instagram" if pre == "ig_" else "youtube"
            cross[pre].append(sum(plat.get(c) != own for c in a) / len(a))
    return {"top10_differs_from_h0": diff, "mean_top10_overlap_with_h0": round(float(np.mean(ovl)), 3),
            "other_platform_share_top10": {k: round(float(np.mean(v)), 3) for k, v in cross.items() if v}}


def run_config(env, cfg, reps):
    qs = queries()
    written = []
    plat = {c: it["platform"] for it, c in zip(env.S.items, env.S.codes)}
    for rep in reps:
        Pqr = rw("qr-v1", rep)
        Pqs = rw("qs-v1", rep) if cfg in USES_QS else None
        env.S.QV.get([s for q in qs if not q["examples"] for s in
                      [q["query"]] + Pqr[q["id"]]["phrases"] + (Pqr[q["id"]].get("hypothetical_captions") or [])
                      + ([Pqs[q["id"]]["creator_lookup"]["description"]] if Pqs and
                         Pqs[q["id"]]["creator_lookup"]["description"].strip() else [])])
        if cfg == "h5b":
            env.QVs.get([s for q in qs if not q["examples"] for s in
                         [q["query"]] + Pqr[q["id"]]["phrases"] + (Pqr[q["id"]].get("hypothetical_captions") or [])])
        timing = embed_timing(qs, Pqr, rep)
        spent0 = len(L.ledger())
        out, per = {}, {}
        lat_local, lat_total, lat_all = [], [], []
        cost_qr = cost_qs = cost_emb = 0.0
        agg = collections.Counter()
        for q in qs:
            t = time.time()
            parse = None if q["examples"] else Pqr[q["id"]]
            slots = Pqs[q["id"]] if (Pqs and not q["examples"]) else None
            order, info = search_one(env, cfg, q, parse, slots)
            local = time.time() - t
            out[q["id"]] = order
            lat_all.append(local)
            if q["examples"]:
                continue
            rq = Pqr["_meta"]["per_query"][q["id"]]
            rs = Pqs["_meta"]["per_query"][q["id"]] if Pqs else None
            e = timing[q["id"]]
            pre = max(rq["seconds"], rs["seconds"] if rs else 0.0)
            lat_local.append(local)
            lat_total.append(local + pre + e["seconds"])
            cost_qr += rq["cost_usd"]
            cost_qs += rs["cost_usd"] if rs else 0.0
            cost_emb += e["cost_usd"]
            agg["router_creator"] += bool(info.get("router") and info["router"]["type"] == "creator")
            agg["creator_fired"] += "creator" in info
            agg["facet_active"] += bool(info.get("facets"))
            agg["time_soft"] += bool((info.get("time") or {}).get("direction"))
            agg["intent_active"] += (info.get("intent") or {}).get("mode", "unchanged") != "unchanged"
            per[q["id"]] = {**info, "latency_total_s": round(lat_total[-1], 3), "latency_local_s": round(local, 4)}
        n = len(lat_total)
        new_spend = sum(r["cost_usd"] for r in L.ledger()[spent0:])
        parts = sorted(PART[cfg])
        meta = {"config": cfg, "round": "7", "repeat": rep, "splits": ALT["splits"] or ["dev", "yt_holdout"],
                "n_searches": len(qs), "n_typed": n, "parts": parts, "base": "H0 = G4 (r6/g4)",
                "rewrites": {"qr-v1": f"qr-v1_gpt-5-nano_r{rep}",
                             "qs-v1": f"qs-v1_gpt-5-nano_r{rep}" if cfg in USES_QS else None},
                "embedding": f"{G.EMB3L_MODEL}@{G.EMB3L_DIM}", "hyde_alpha": L.HYDE_ALPHA,
                "fusion": "coverage-fair RRF k=60" if ("te" in parts or agg["creator_fired"]) else "RRF k=60",
                "boost": H.BOOST, "boost_depth": H.BOOST_DEPTH, "calibration_beta": H.CAL_BETA if "h3" in parts else None,
                "te": {"rule": "F0 (caption-type / untitled)", "rankable": len(env.E_f0.codes),
                       "te_dense_query_vectors": "text-embedding-3-small@512"} if "te" in parts else None,
                "cross_encoder": CE_MODEL if "ce" in parts else None,
                "counts": dict(agg),
                "index_build_s": round(env.build_s, 1), "h0_index_build_s": round(env.h0_build_s, 1),
                "creator_profiles_build_s": round(env.creator_build_s, 1), "n_creators": len(env.CR3.keys),
                "query_local_p50_s": pct(lat_all, 50), "query_local_p95_s": pct(lat_all, 95),
                "typed_local_p50_s": pct(lat_local, 50), "typed_local_p95_s": pct(lat_local, 95),
                "typed_total_p50_s": pct(lat_total, 50), "typed_total_p95_s": pct(lat_total, 95),
                "latency_model": "local search + max(qr-v1, qs-v1 where read; original uncached seconds, parallel) + "
                                 "one live 3-large query-embedding call (shared per search and repeat)",
                "cost_usd_by_call": {"qr-v1": round(cost_qr, 6), "qs-v1": round(cost_qs, 6),
                                     "query_embed_3l": round(cost_emb, 6)},
                "cost_per_1k_searches_usd": round(1000 * (cost_qr + cost_qs + cost_emb) / max(n, 1), 4),
                "cost_per_1k_searches_if_qs_merged_usd": round(1000 * (cost_qr + cost_emb) / max(n, 1), 4)
                if cfg in USES_QS else None,
                "cost_note": "ledger list prices, uncached input price; per 1k typed searches; classifiers, router "
                             "and cross-encoder run locally ($0)",
                "new_spend_this_run_usd": round(new_spend, 6), "per_search": per}
        ref_name = ("r6/g4_r{rep}.json" if cfg in ("h0chk", "h0") else ALT["ref"]).format(rep=rep)
        ref = json.load(open(os.path.join(DATA, "runs", ref_name)))
        meta["diagnostics"] = top10_diag(out, ref, plat)
        if ALT["queries"]:
            meta["queries_file"] = os.path.basename(ALT["queries"])
            meta["rewrites_dir"] = ALT["rewrites"]
        outdir = ALT["outdir"] or (os.path.join(DATA, "tmp", "r7_checks") if cfg == "h0chk"
                                   else os.path.join(DATA, "runs", "r7"))
        path = write_run(os.path.join(outdir, f"{cfg}{ALT['suffix']}_r{rep}.json"), f"c7:{cfg}",
                         L.CodeIds(meta["embedding"]), out, meta)
        if cfg == "h0chk":
            same = sum(out[k] == ref["queries"][k][:1000] for k in out)
            print(f"h0chk r{rep}: {same} of {len(out)} rankings identical to {ref_name} (1,000 deep)", flush=True)
        written.append(path)
        print(f"wrote {os.path.basename(path)}: local p50 {meta['typed_local_p50_s']} / p95 {meta['typed_local_p95_s']} s;"
              f" total p50 {meta['typed_total_p50_s']} / p95 {meta['typed_total_p95_s']} s; "
              f"cost/1k ${meta['cost_per_1k_searches_usd']}; {json.dumps(dict(agg))}; "
              f"{json.dumps(meta['diagnostics'])}", flush=True)
    return written


def stats():
    """Fire counts per queries.jsonl kind (reporting only) from the r7 run files. Aggregates only."""
    qs = {q["id"]: q for q in queries()}
    d = os.path.join(DATA, "runs", "r7")
    res = {}
    for cfg in CONFIGS[2:]:
        tab = collections.defaultdict(collections.Counter)
        for rep in (1, 2, 3):
            p = os.path.join(d, f"{cfg}_r{rep}.json")
            if not os.path.exists(p):
                continue
            per = json.load(open(p))["meta"]["per_search"]
            for qid, info in per.items():
                kinds = qs[qid]["kinds"] + ["ALL"]
                fired = {"cells": True,
                         "router_creator": bool(info.get("router") and info["router"]["type"] == "creator"),
                         "creator": "creator" in info,
                         "calibration_strong": bool(info.get("calibration")) and
                         abs(info["calibration"]["q_ig"] - 0.5) >= 0.25,
                         "facet": bool(info.get("facets")), "facet_format": any(
                             f.startswith("format") for f in info.get("facets") or []),
                         "facet_tone": any(f.startswith("tone") for f in info.get("facets") or []),
                         "time_soft": bool((info.get("time") or {}).get("direction")),
                         "time_soft_lexicon": (info.get("time") or {}).get("source") == "lexicon"
                         and bool(info["time"]["direction"]),
                         "filter_active": (info.get("intent") or {}).get("mode", "unchanged") != "unchanged"}
                if info.get("router"):
                    fired["router_type_" + info["router"]["type"]] = True
                for k in kinds:
                    for f, v in fired.items():
                        tab[k][f] += int(v)
        if tab:
            res[cfg] = {k: dict(v) for k, v in tab.items()}
    print(json.dumps(res, indent=1))
    H.jdump(res, os.path.join(DATA, "r7", "fire_counts.json"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", default="")
    ap.add_argument("--reps", default="1,2,3")
    ap.add_argument("--queries", default=None)
    ap.add_argument("--rewrites-dir", default=None)
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--suffix", default="")
    ap.add_argument("--splits", default=None)
    ap.add_argument("--ref", default=ALT["ref"])
    ap.add_argument("--stats", action="store_true")
    a = ap.parse_args()
    ALT.update({"queries": a.queries, "rewrites": a.rewrites_dir, "outdir": a.outdir, "suffix": a.suffix,
                "splits": a.splits.split(",") if a.splits else None, "ref": a.ref})
    if a.stats:
        stats()
        return
    t0 = time.time()
    env = Env()
    print(f"index built in {env.build_s:.1f} s (H0 {env.h0_build_s:.1f} s; creators {env.creator_build_s:.1f} s; "
          f"H4 profiles with channel words {env.CR4.n_typed}, era words {env.CR4.n_era}; "
          f"te rankable {len(env.E_f0.codes)})", flush=True)
    reps = [int(x) for x in a.reps.split(",")]
    for cfg in a.configs.split(","):
        assert cfg in CONFIGS, cfg
        run_config(env, cfg, reps)
    print(f"total wall {time.time() - t0:.1f} s", flush=True)


if __name__ == "__main__":
    main()
