"""PROTOTYPE ONLY - round 8.5 run files (LOG.md "Round 8.5 fixed parameters", rows Y8.5-TS, Y8.5-Q8, Y8.5-QB).

Configs (one variable each vs B8.4 = TFY, tfy-v1 = runs/r8.4/tfy_r{k}):
  tfy  B8.4 from this runner: must equal runs/r8.4/tfy_r{k} exactly (reproduction gate; written to tmp/ only).
  ts   Y8.5-TS: te group term scaled by w = clip((q_ig - 0.35) / 0.40, 0, 1); then P's multiplier and TFY's refine.
  q8   Y8.5-Q8: per-dimension int8 3-large item vectors everywhere they are read, no rescoring; then as TFY.
  qb   Y8.5-QB: Q8, with typed dense lists from sign-binary Hamming top 400 per query row + int8 rescoring.
tfy / ts run on float item vectors; q8 / qb on the int8 store (one vector mode per process).
Searches: dev + yt_holdout + known_dev + ig_known_dev (586; one run file per repeat).

Latency per typed search = local search (warm) + the rewrite call's original uncached seconds where a rewrite is used
+ max(round 8.1's live 3-large call, round 8.3's live 3-small te call) (parallel) + the refine call's seconds.

usage: python experiments/methods/c85_search.py refine --configs ts [--reps 1,2,3] [--workers 4]  # paid if uncached
       python experiments/methods/c85_search.py run --configs tfy,ts [--reps 1,2,3] [--outdir DIR]
       python experiments/methods/c85_search.py bench            # dense-scan micro-benchmark and storage
       python experiments/methods/c85_search.py compare --a DIR --b DIR --configs ...
"""
import argparse
import collections
import concurrent.futures as cf
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
import c81_lib as R  # noqa: E402
import c81_search as S81  # noqa: E402
import c82_lib as P  # noqa: E402
import c82_search as S82  # noqa: E402
import c83_lib as Q  # noqa: E402
import c85_lib as X  # noqa: E402
import yt_lib as Y  # noqa: E402
from corpus import DATA, write_run  # noqa: E402

OUT = os.path.join(DATA, "runs", "r8.5")
TMP = os.path.join(DATA, "tmp", "r8.5_checks")
T81 = os.path.join(DATA, "r8.1")
T83 = os.path.join(DATA, "r8.3")
BASE = os.path.join(DATA, "runs", "r8.4")
CONFIGS = ["tfy", "ts", "q8", "qb"]
MODE = {"tfy": "float", "ts": "float", "q8": "int8", "qb": "int8"}
SPLITS = S81.SPLITS
VERSION = {"tfy": "tfy-v1", "ts": X.TS_VERSION, "q8": X.Q8_VERSION, "qb": X.QB_VERSION}
pct = S82.pct


class Env:
    def __init__(self, mode):
        t0 = time.time()
        items = L.jl(os.path.join(DATA, "corpus", "items.jsonl"))
        self.S = L.Combined("all", items=items)
        G.swap_to_3l(self.S)
        S = self.S
        self.mode = mode
        self.Vf = S.V  # float32 (diagnostics only in int8 mode)
        self.storage = {"n_items": int(S.V.shape[0]), "dim": int(S.V.shape[1]),
                        "float32_mb": round(S.V.nbytes / 1e6, 1),
                        "float16_file_mb": round(S.V.shape[0] * S.V.shape[1] * 2 / 1e6, 1)}
        self.quant_s = 0.0
        if mode == "int8":
            t1 = time.time()
            S.V = X.QMat(self.Vf)
            self.B = X.BinIdx(self.Vf)
            self.quant_s = round(time.time() - t1, 1)
            self.storage.update({"int8_mb": round(S.V.nbytes() / 1e6, 1),
                                 "int8_bytes_per_item": round(S.V.nbytes() / S.V.shape[0], 2),
                                 "binary_mb": round(self.B.nbytes() / 1e6, 1),
                                 "binary_bytes_per_item": self.B.nbytes() / S.V.shape[0],
                                 "qb_on_disk_mb": round((S.V.nbytes() + self.B.nbytes()) / 1e6, 1)})
            # label-free quantisation error of the item vectors (cosine of dequantised to float)
            idx = np.arange(0, S.V.shape[0], 97)
            D = S.V[idx]
            cos = (D * self.Vf[idx]).sum(1) / np.linalg.norm(D, axis=1)
            self.storage["dequant_cos_p1_p50"] = [round(float(np.percentile(cos, 1)), 5),
                                                  round(float(np.median(cos)), 5)]
            self.storage["dequant_norm_p1_p99"] = [round(float(np.percentile(np.linalg.norm(D, axis=1), p)), 4)
                                                   for p in (1, 99)]
        self.h0_build_s = time.time() - t0
        I.prepare(S)
        t1 = time.time()
        self.router_shape = R.ShapeRouter(S)
        self.route_build_s = time.time() - t1
        self.extra_build_s = {}
        t2 = time.time()
        self.prior = P.PlatformPrior(S, H.Router())
        self.extra_build_s["prior"] = round(time.time() - t2, 1)
        t2 = time.time()
        self.te = Q.TeIG(S)
        self.extra_build_s["te_ig"] = round(time.time() - t2, 1)
        self.refiner = X.Refiner85(S, F.te_meta_rows())
        self.build_s = time.time() - t0


def plan(q, parse, path):
    return R.plan_instant(q) if path == "instant" else F.plan_c0(q, parse)


def search_one(env, cfg, q, parse, rep, stop_before_refine=False):
    """Returns (order, info). With stop_before_refine, returns the pre-refine order and whether the gate fires."""
    S = env.S
    if q["examples"]:
        return S.mlt(q)[:1000], {}
    r = env.router_shape.route(q["query"])
    path = r["path"]
    info = {"route": r}
    keep = S.keep_fn(q.get("filters"))
    texts, caps, bq = plan(q, parse, path)
    if cfg == "qb":
        own, _, cand = X.own_lists_qb(S, env.B, texts, caps, bq, keep)
        info["_cand"] = cand
        info["qb"] = {"n_candidates": int(len(cand)), "dense_len": len(own[0])}
    else:
        own, _ = F.own_lists(S, texts, caps, bq, keep)
    if cfg in ("q8", "qb"):
        info["_dense100"] = own[0][:100]
    order, sc = F.fair_fuse(own, [])
    q_ig, pinfo = env.prior.read(q["query"], S.QV.get([q["query"]])[0], order)  # read from the own-list fusion
    info["prior"] = pinfo
    if cfg == "ts":
        w = X.ts_weight(q_ig)
        info["ts_w"] = round(w, 4)
        info["te_used"] = w > 0
        if w > 0:  # w = 0 is P's fusion exactly (already computed above)
            order, sc = X.fuse_weighted(own, env.te.group(texts, caps, bq, keep), w)
    else:
        order, sc = F.fair_fuse(own, [env.te.group(texts, caps, bq, keep)])
        info["te_used"] = True
    if info["te_used"]:
        info["ti"] = {"te_in_top10": sum(c in env.te.E.codeset for c in order[:10])}
    order, sc = env.prior.apply(order, sc, q_ig)
    order = order[:1000]
    gate = path == "rewrite" and q_ig < X.REFINE_Q_IG_MAX
    if stop_before_refine:
        return order, {"gate": gate}
    if gate:
        (order, rinfo), rr = env.refiner.get(rep, q["id"], q["query"], order)
        order = order[:1000]
        info["refine"] = {**rinfo, "seconds": rr["seconds"], "cost_usd": rr["cost_usd"], "tries": rr["tries"],
                          "cache": env.refiner.source.get(rr["key"])}
    return order, info


def dense_diag(env, q, parse, info):
    """Label-free recall of the float dense top 100 (float vectors, diagnostics only) by the arm's dense lists."""
    S = env.S
    path = info["route"]["path"]
    keep = S.keep_fn(q.get("filters"))
    texts, caps, _ = plan(q, parse, path)
    Qv = S.QV.get(texts)
    if caps:
        Hh = S.QV.get(caps)
        v = (1 - L.HYDE_ALPHA) * Qv[0] + L.HYDE_ALPHA * Hh.mean(0)
        Qv = np.vstack([Qv, (v / np.linalg.norm(v))[None, :]])
    ref = X.float_dense_top(S, env.Vf, Qv, keep, 100)
    if not ref:
        return None
    out = {"top100_recall": len(set(ref) & set(info["_dense100"])) / len(ref),
           "top10_recall": len(set(ref[:10]) & set(info["_dense100"][:10])) / len(ref[:10])}
    if "_cand" in info:
        cset = {S.vcodes[n] for n in info["_cand"]}
        out["cand_recall_top100"] = len(set(ref) & cset) / len(ref)
    return out


# ---------------- refine calls (cached; paid only where no earlier cache has the exact inputs) ----------------
def refine(cfgs, reps, workers):
    qs, _ = S81.queries()
    modes = {MODE[c] for c in cfgs}
    assert len(modes) == 1, "one vector mode per process"
    env = Env(modes.pop())
    rf = env.refiner
    orig = ai.openai_chat_json

    def tagged(*a, **k):  # this round's ledger purpose; prompt, model and schema are rf-v1's
        k["purpose"] = "c85_refine"
        return orig(*a, **k)
    ai.openai_chat_json = tagged
    jobs, src = [], collections.Counter()
    t0 = time.time()
    for cfg in cfgs:
        for rep in reps:
            Pqr = S81.rewrites("qr-v1", rep)
            for q in qs:
                if q["examples"]:
                    continue
                order, g = search_one(env, cfg, q, Pqr[q["id"]], rep, stop_before_refine=True)
                if not g["gate"]:
                    continue
                key = P.cache_key(rep, q["id"], rf.split_top(order)[2])
                src[(cfg, rf.source.get(key, "new"))] += 1
                if key not in rf.cache:
                    jobs.append((rep, q, order))
    uniq = {}
    for rep, q, order in jobs:
        uniq.setdefault(P.cache_key(rep, q["id"], rf.split_top(order)[2]), (rep, q, order))
    print(f"refine: gated searches by (config, source) {dict(src)}; {len(uniq)} distinct new inputs "
          f"(pre-refine pass {time.time() - t0:.1f} s)", flush=True)
    n0 = len(L.ledger())
    t0 = time.time()
    with cf.ThreadPoolExecutor(workers) as ex:
        res = list(ex.map(lambda j: rf.get(j[0], j[1]["id"], j[1]["query"], j[2], allow_call=True)[1],
                          list(uniq.values())))
    wall = time.time() - t0
    new = [r for r in L.ledger()[n0:] if r.get("purpose") == "c85_refine"]
    print(f"refine: {len(uniq)} calls in {wall:.1f} s ({len(uniq) / max(wall, 1e-9):.2f}/s), {len(new)} ledger rows, "
          f"${sum(r['cost_usd'] for r in new):.4f}; ok {sum(r['ok'] for r in res)}, "
          f"failed {sum(not r['ok'] for r in res)}", flush=True)


# ---------------- runs ----------------
def run_config(env, cfg, reps, outdir):
    qs, split_of = S81.queries()
    S = env.S
    plat = {c: it["platform"] for it, c in zip(S.items, S.codes)}
    t_inst = json.load(open(os.path.join(T81, "embed_timing_inst.json")))
    te_inst = json.load(open(os.path.join(T83, "embed_timing_te_inst.json")))
    written = []
    for rep in reps:
        Pqr = S81.rewrites("qr-v1", rep)
        need = S81.strings(qs, Pqr, None)
        miss = [s for s in need if s not in S.QV.vec]
        assert not miss, f"{len(miss)} query strings not in the 3-large query store"
        t_h0 = json.load(open(os.path.join(T81, f"embed_timing_h0_r{rep}.json")))
        te_rw = json.load(open(os.path.join(T83, f"embed_timing_te_r{rep}.json")))
        typed = [x for x in qs if not x["examples"]]
        for q in typed[:5]:  # warm-up (not timed, not written)
            search_one(env, cfg, q, Pqr[q["id"]], rep)
        out, per = {}, {}
        by = collections.defaultdict(lambda: collections.defaultdict(list))
        agg = collections.Counter()
        t_run = time.time()
        diag_s = 0.0
        for q in qs:
            sp = split_of[q["id"]]
            parse = None if q["examples"] else Pqr[q["id"]]
            t = time.time()
            order, info = search_one(env, cfg, q, parse, rep)
            local = time.time() - t
            out[q["id"]] = order
            if q["examples"]:
                continue
            d = by[sp]
            if cfg in ("q8", "qb"):  # diagnostics, outside the timed region
                t = time.time()
                dg = dense_diag(env, q, parse, info)
                diag_s += time.time() - t
                if dg:
                    for k, v in dg.items():
                        d["diag_" + k].append(v)
                info.pop("_dense100", None)
                info.pop("_cand", None)
                if cfg == "qb":
                    d["qb_n_candidates"].append(info["qb"]["n_candidates"])
                    d["qb_dense_len"].append(info["qb"]["dense_len"])
            path = info["route"]["path"]
            rq = Pqr["_meta"]["per_query"][q["id"]]
            rf_s = rf_c = 0.0
            if path == "instant":
                e, rw_s, rw_c = t_inst[q["id"]], 0.0, 0.0
            else:
                e, rw_s, rw_c = t_h0[q["id"]], rq["seconds"], rq["cost_usd"]
            es = (te_inst if path == "instant" else te_rw)[q["id"]]
            e_s, e_c = max(e["seconds"], es["seconds"]), e["cost_usd"] + es["cost_usd"]  # parallel, every search
            d["te_used"].append(info["te_used"])
            if "ts_w" in info:
                d["ts_w"].append(info["ts_w"])
            if info["te_used"]:
                d["te_in_top10"].append(info["ti"]["te_in_top10"])
            if "refine" in info:
                rf_s, rf_c = info["refine"]["seconds"], info["refine"]["cost_usd"]
                d["refine_s"].append(rf_s)
                d["refine_cost"].append(rf_c)
            tot = local + rw_s + e_s + rf_s
            d["local"].append(local)
            d["total"].append(tot)
            d["cost"].append(rw_c + e_c + rf_c)
            d["routed"].append(path == "instant")
            d[f"total_{path}_path"].append(tot)
            d[f"local_{path}_path"].append(local)
            agg[f"{sp}:{path}"] += 1
            agg[f"{sp}:te_used"] += info["te_used"]
            pi = info["prior"]
            for k in ("q_ig", "e_t", "e_k", "e_c", "mult_ig", "mult_yt"):
                d["prior_" + k].append(pi[k])
            agg[f"{sp}:prior_creator_fired"] += pi["n_creators"] > 0
            if path == "rewrite":
                agg[f"{sp}:rewrite_read_yt"] += pi["q_ig"] < X.REFINE_Q_IG_MAX
            if "ts_w" in info:
                w = info["ts_w"]
                agg[f"{sp}:ts_w0"] += w == 0
                agg[f"{sp}:ts_w1"] += w == 1
                agg[f"{sp}:ts_wpartial"] += 0 < w < 1
            if "refine" in info:
                ri = info["refine"]
                agg[f"{sp}:refine_ok"] += ri["ok"]
                agg[f"{sp}:refine_failed"] += not ri["ok"]
                agg[f"{sp}:refine_cache_{ri['cache']}"] += 1
                for k in ("n_sent", "n_friends_kept", "n_invalid", "n_dup", "n_missing", "moved"):
                    agg[f"{sp}:refine_{k}"] += ri[k]
            per[q["id"]] = {**info, "path": path, "latency_local_s": round(local, 4), "latency_total_s": round(tot, 3)}
        wall = time.time() - t_run - diag_s
        allv = collections.defaultdict(list)
        for sp in SPLITS:
            for k, v in by[sp].items():
                allv[k] += v
        splits = {}
        for sp, d in [(s, by[s]) for s in SPLITS] + [("all_typed", allv)]:
            n = len(d["local"])
            row = {"n_typed": n, "routed_instant": int(sum(d["routed"])), "te_used": int(sum(d["te_used"])),
                   "local_p50_s": pct(d["local"], 50), "local_p95_s": pct(d["local"], 95),
                   "total_p50_s": pct(d["total"], 50), "total_p95_s": pct(d["total"], 95),
                   "total_rewrite_path_p50_s": pct(d["total_rewrite_path"], 50),
                   "total_rewrite_path_p95_s": pct(d["total_rewrite_path"], 95),
                   "local_rewrite_path_p50_s": pct(d["local_rewrite_path"], 50),
                   "local_rewrite_path_p95_s": pct(d["local_rewrite_path"], 95),
                   "total_instant_path_p50_s": pct(d["total_instant_path"], 50),
                   "cost_per_1k_searches_usd": round(1000 * float(np.mean(d["cost"])), 4) if n else None,
                   "te_items_in_top10_mean_when_used": round(float(np.mean(d["te_in_top10"])), 3)
                   if d["te_in_top10"] else None,
                   "prior": {k[6:]: {f"p{p}": pct(v, p) for p in (5, 25, 50, 75, 95)}
                             for k, v in d.items() if k.startswith("prior_")}}
            row["refined"] = len(d["refine_s"])
            row["refine_p50_s"], row["refine_p95_s"] = pct(d["refine_s"], 50), pct(d["refine_s"], 95)
            row["refine_cost_per_1k_refined_usd"] = round(1000 * float(np.mean(d["refine_cost"])), 4) \
                if d["refine_cost"] else None
            if d["ts_w"]:
                row["ts_w"] = {f"p{p}": pct(d["ts_w"], p) for p in (5, 25, 50, 75, 95)}
                row["ts_w_mean"] = round(float(np.mean(d["ts_w"])), 4)
            for k in [k for k in d if k.startswith("diag_") or k.startswith("qb_")]:
                row[k] = {"mean": round(float(np.mean(d[k])), 4), "p5": pct(d[k], 5), "p50": pct(d[k], 50),
                          "min": round(float(np.min(d[k])), 4)}
            splits[sp] = row
        meta = {"config": cfg, "round": "8.5", "repeat": rep, "splits": SPLITS, "n_searches": len(qs),
                "base": "B8.4 = runs/r8.4/tfy_r{k} (tfy-v1: TI + rf-v1 refine, rewrite-routed, q_ig < 0.5)",
                "version": VERSION[cfg], "vector_mode": env.mode, "storage": env.storage,
                "rewrites": {"qr-v1": Pqr["_meta"]["sources"]},
                "ts": {"a": X.TS_A, "b": X.TS_B} if cfg == "ts" else None,
                "q8": {"scale": "per-dimension max-abs / 127", "block_rows": X.Q8_BLOCK, "rescoring": None}
                if cfg in ("q8", "qb") else None,
                "qb": {"k_per_row": X.QB_K, "rescore": "int8"} if cfg == "qb" else None,
                "refine_model": P.REFINE_MODEL, "refine_gate": f"rewrite-routed and q_ig < {X.REFINE_Q_IG_MAX}",
                "te": {"rows": "te-v1c Instagram rows only", "rankable": env.te.n_rankable,
                       "dense_query_vectors": f"{Y.EMB_MODEL}@{Y.EMB_DIM}",
                       "fusion": "coverage-fair (c5_lib.fair_fuse)" + (" scaled by ts_w" if cfg == "ts" else "")},
                "embedding": f"{G.EMB3L_MODEL}@{G.EMB3L_DIM}", "route_version": R.ROUTE_VERSION,
                "counts": dict(agg), "per_split": splits,
                "index_build_s": round(env.build_s, 1), "h0_index_build_s": round(env.h0_build_s, 1),
                "quantise_s": env.quant_s,
                "route_index_build_s": round(env.route_build_s, 1), "extra_build_s": env.extra_build_s,
                "run_wall_s": round(wall, 1), "searches_per_s": round(len(qs) / max(wall, 1e-9), 2),
                "diag_wall_s": round(diag_s, 1), "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
                "latency_model": "local (warm) + rewrite call's original uncached seconds where used + max(round "
                                 "8.1's live 3-large call, round 8.3's live 3-small te call) + refine call",
                "per_search": per}
        ref = json.load(open(os.path.join(BASE, f"tfy_r{rep}.json")))
        meta["diagnostics_vs_b84"] = S82.top10_diag(out, ref, plat, split_of)
        mlt = [k for k in out if not per.get(k)]
        meta["mlt_identical_to_b84"] = sum(out[k] == ref["queries"][k] for k in mlt)
        path = write_run(os.path.join(outdir, f"{cfg}_r{rep}.json"), f"c85:{cfg}", L.CodeIds(meta["embedding"]),
                         out, meta)
        written.append(path)
        sa = splits["all_typed"]
        print(f"wrote {os.path.relpath(path, DATA)}: {len(qs)} searches in {wall:.1f} s "
              f"({len(qs) / max(wall, 1e-9):.1f}/s); local p50 {sa['local_p50_s']} / p95 {sa['local_p95_s']} s; "
              f"total p50 {sa['total_p50_s']} / p95 {sa['total_p95_s']}; $/1k {sa['cost_per_1k_searches_usd']}",
              flush=True)
        same = sum(out[k] == ref["queries"][k] for k in ref["queries"])
        print(f"{cfg} r{rep}: {same} of {len(ref['queries'])} rankings identical to r8.4/tfy (1,000 deep); "
              f"more-like-this identical {meta['mlt_identical_to_b84']} / {len(mlt)}", flush=True)
    return written


# ---------------- micro-benchmark: dense scan per query vector, and storage ----------------
def bench():
    S = L.Combined("all", items=L.jl(os.path.join(DATA, "corpus", "items.jsonl")))
    G.swap_to_3l(S)
    Vf = S.V
    t = time.time()
    V8 = X.QMat(Vf)
    B = X.BinIdx(Vf)
    tq = time.time() - t
    ids = sorted(S.QV.vec)[:200]  # 200 stored query vectors (no text used or printed)
    Qs = np.array([S.QV.vec[s] for s in ids], np.float32)
    elig = np.asarray(S.gate)
    res = {}

    def timeit(name, fn, reps=3):
        best = []
        for _ in range(reps):
            t0 = time.perf_counter()
            for qv in Qs:
                fn(qv)
            best.append((time.perf_counter() - t0) / len(Qs))
        res[name] = round(1000 * min(best), 3)

    timeit("float32_full_scan_ms", lambda qv: Vf @ qv)
    timeit("int8_full_scan_ms", lambda qv: V8 @ qv)
    timeit("hamming_full_scan_ms", lambda qv: B.hamming(qv))
    timeit("hamming_topk400_ms", lambda qv: B.topk(qv, elig))
    cand = B.topk(Qs[0], elig, 2000)
    timeit("int8_rescore_2000_ms", lambda qv: V8.rows_dot(cand, qv))
    timeit("float32_matrix_5rows_ms", lambda qv: Vf @ np.tile(qv, (5, 1)).T, reps=2)
    timeit("int8_matrix_5rows_ms", lambda qv: V8 @ np.tile(qv, (5, 1)).T, reps=2)
    out = {"n_items": int(Vf.shape[0]), "dim": int(Vf.shape[1]), "quantise_build_s": round(tq, 2),
           "per_query_vector": res,
           "storage_mb": {"float32": round(Vf.nbytes / 1e6, 1), "float16_file": round(Vf.size * 2 / 1e6, 1),
                          "int8_plus_scales": round(V8.nbytes() / 1e6, 1), "binary": round(B.nbytes() / 1e6, 1),
                          "binary_plus_int8": round((B.nbytes() + V8.nbytes()) / 1e6, 1)},
           "bytes_per_item": {"float32": 4 * Vf.shape[1], "float16": 2 * Vf.shape[1],
                              "int8": round(V8.nbytes() / Vf.shape[0], 2), "binary": B.nbytes() / Vf.shape[0],
                              "binary_plus_int8": round((B.nbytes() + V8.nbytes()) / Vf.shape[0], 2)},
           "threads": os.cpu_count()}
    os.makedirs(TMP, exist_ok=True)
    json.dump(out, open(os.path.join(TMP, "bench.json"), "w"), indent=1)
    print(json.dumps(out, indent=1), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["refine", "run", "compare", "bench"])
    ap.add_argument("--configs", default="ts")
    ap.add_argument("--reps", default="1,2,3")
    ap.add_argument("--outdir", default=OUT)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--a")
    ap.add_argument("--b")
    a = ap.parse_args()
    reps = [int(x) for x in a.reps.split(",")]
    cfgs = a.configs.split(",")
    for cfg in cfgs:
        assert cfg in CONFIGS, cfg
    if a.cmd == "bench":
        return bench()
    if a.cmd == "refine":
        return refine(cfgs, reps, a.workers)
    if a.cmd == "compare":
        return S82.compare(a.a, a.b, cfgs, reps)
    t0 = time.time()
    modes = {MODE[c] for c in cfgs}
    assert len(modes) == 1, "one vector mode per process"
    env = Env(modes.pop())
    print(f"index built in {env.build_s:.1f} s (H0 {env.h0_build_s:.1f} s; route {env.route_build_s:.1f} s; "
          f"extra {json.dumps(env.extra_build_s)}; quantise {env.quant_s} s)", flush=True)
    for cfg in cfgs:
        run_config(env, cfg, reps, TMP if cfg == "tfy" and a.outdir == OUT else a.outdir)
    print(f"total wall {time.time() - t0:.1f} s", flush=True)


if __name__ == "__main__":
    main()
