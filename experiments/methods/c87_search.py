"""PROTOTYPE ONLY - round 8.7 run files (LOG.md "Round 8.7 fixed parameters", rows Y8.7-CI, Y8.7-R2).

Configs (one variable each vs B8.5 = Q8, q8-v1 = runs/r8.5/q8_r{k}); every config runs on the int8 item store:
  q8   B8.5 from this runner: must equal runs/r8.5/q8_r{k} exactly (reproduction gate; written to tmp/ only).
  ci   Y8.7-CI: creator-level index; the top 5 creators' items (ordered by item dense score) as one extra RRF list
       at weight 0.5, on every typed search (both routes).
  r2   Y8.7-R2: route-r2 (wider instant routing); everything else B8.5.
q_ig is read from the search's own-list fusion (B8.5's rule), so in ci the multiplier and refine gate equal B8.5's.
Searches: dev + yt_holdout + known_dev + ig_known_dev (586; one run file per repeat).

Latency per typed search = local search (warm) + the rewrite call's original uncached seconds where a rewrite is used
+ max(round 8.1's live 3-large call, the live 3-small te call (round 8.3; round 8.7 for searches only r2 routes
instant)) (parallel) + the refine call's seconds.

usage: python experiments/methods/c87_search.py embed                       # creator documents -> 3-large (paid once)
       python experiments/methods/c87_search.py timing                      # live 3-small calls, r2-only instant
       python experiments/methods/c87_search.py refine --configs ci,r2 [--reps 1,2,3] [--workers 4]  # paid if new
       python experiments/methods/c87_search.py run --configs q8,ci,r2 [--reps 1,2,3] [--outdir DIR]
       python experiments/methods/c87_search.py compare --a DIR --b DIR --configs ...
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
import c87_lib as C  # noqa: E402
from corpus import DATA, write_run  # noqa: E402

OUT = os.path.join(DATA, "runs", "r8.7")
TMP = os.path.join(DATA, "tmp", "r8.7_checks")
WORK = os.path.join(DATA, "r8.7")
T81 = os.path.join(DATA, "r8.1")
T83 = os.path.join(DATA, "r8.3")
BASE = os.path.join(DATA, "runs", "r8.5")
CONFIGS = ["q8", "ci", "r2"]
SPLITS = S81.SPLITS
VERSION = {"q8": X.Q8_VERSION, "ci": C.CI_VERSION, "r2": C.R2_VERSION}
pct = S82.pct
TE_INST_R2 = os.path.join(WORK, "embed_timing_te_inst_r2.json")


class Env:
    def __init__(self, allow_embed=False):
        t0 = time.time()
        items = L.jl(os.path.join(DATA, "corpus", "items.jsonl"))
        self.S = L.Combined("all", items=items)
        G.swap_to_3l(self.S)
        S = self.S
        t1 = time.time()
        S.V = X.QMat(S.V)
        self.quant_s = round(time.time() - t1, 1)
        self.h0_build_s = time.time() - t0
        I.prepare(S)
        t1 = time.time()
        self.router_shape = R.ShapeRouter(S)
        self.route_build_s = time.time() - t1
        self.extra_build_s = {}
        t2 = time.time()
        self.router_r2 = C.ShapeRouter2(S)
        self.extra_build_s["route_r2"] = round(time.time() - t2, 1)
        t2 = time.time()
        self.prior = P.PlatformPrior(S, H.Router())
        self.extra_build_s["prior"] = round(time.time() - t2, 1)
        t2 = time.time()
        self.te = Q.TeIG(S)
        self.extra_build_s["te_ig"] = round(time.time() - t2, 1)
        t2 = time.time()
        self.ci = C.CreatorIndex(S, allow_embed=allow_embed)
        self.extra_build_s["creator_index"] = round(time.time() - t2, 1)
        self.refiner = C.Refiner87(S, F.te_meta_rows())
        self.build_s = time.time() - t0


def plan(q, parse, path):
    return R.plan_instant(q) if path == "instant" else F.plan_c0(q, parse)


def search_one(env, cfg, q, parse, rep, stop_before_refine=False):
    """Returns (order, info, diag_seconds). With stop_before_refine, returns the pre-refine order and the gate."""
    S = env.S
    if q["examples"]:
        return S.mlt(q)[:1000], {}, 0.0
    r = (env.router_r2 if cfg == "r2" else env.router_shape).route(q["query"])
    path = r["path"]
    info = {"route": r}
    keep = S.keep_fn(q.get("filters"))
    texts, caps, bq = plan(q, parse, path)
    own, Qv, s = C.own_lists_s(S, texts, caps, bq, keep)
    order, sc = F.fair_fuse(own, [])
    q_ig, pinfo = env.prior.read(q["query"], S.QV.get([q["query"]])[0], order)  # B8.5 own-list fusion
    info["prior"] = pinfo
    group = env.te.group(texts, caps, bq, keep)
    order, sc = F.fair_fuse(own, [group])
    info["te_used"] = True
    diag_s = 0.0
    if cfg == "ci":
        top_c, cl = env.ci.search(Qv, bq, s, keep)
        t = time.time()  # diagnostic only (not part of the arm): B8.5's pre-refine top 10 for this search
        base10 = env.prior.apply(order, sc, q_ig)[0][:10]
        diag_s = time.time() - t
        order, sc = C.ci_fuse(order, sc, cl)
        matched = set(env.prior.matched_creators(q["query"]))
        info["ci"] = {"list_len": len(cl), "n_creators": len(top_c),
                      "top_platform": env.ci.plat[top_c[0]] if top_c else None,
                      "top_name_matched": bool(top_c) and top_c[0] in matched,
                      "any_name_matched": any(k in matched for k in top_c)}
    order, sc = env.prior.apply(order, sc, q_ig)
    order = order[:1000]
    if cfg == "ci":
        cs = set(cl)
        b10 = set(base10)
        info["ci"]["new_in_top10_pre_refine"] = sum(1 for c in order[:10] if c in cs and c not in b10)
        info["ci"]["list_items_in_top10_pre_refine"] = sum(1 for c in order[:10] if c in cs)
    gate = path == "rewrite" and q_ig < C.REFINE_Q_IG_MAX
    if stop_before_refine:
        return order, {"gate": gate}, diag_s
    if gate:
        (order, rinfo), rr = env.refiner.get(rep, q["id"], q["query"], order)
        order = order[:1000]
        info["refine"] = {**rinfo, "seconds": rr["seconds"], "cost_usd": rr["cost_usd"], "tries": rr["tries"],
                          "cache": env.refiner.source.get(rr["key"])}
    if cfg == "ci":
        info["ci"]["list_items_in_top10_final"] = sum(1 for c in order[:10] if c in cs)
    return order, info, diag_s


# ---------------- creator documents -> 3-large (paid once) ----------------
def embed():
    n0 = len(L.ledger())
    t0 = time.time()
    env_items = L.jl(os.path.join(DATA, "corpus", "items.jsonl"))
    S = L.Combined("all", items=env_items)
    G.swap_to_3l(S)
    ci = C.CreatorIndex(S, allow_embed=True)
    new = [r for r in L.ledger()[n0:] if r.get("purpose") == "c87_creator_embed"]
    cost = sum(r["cost_usd"] for r in new)
    toks = sum(r.get("in_tokens", 0) for r in new)
    n_items = len(S.items)
    os.makedirs(WORK, exist_ok=True)
    rep = {"version": C.CI_VERSION, "creators": len(ci.keys), "creators_by_platform": dict(collections.Counter(
        ci.plat.values())), "member_items": ci.n_member_items, "library_items": n_items,
        "friend_creators_excluded": ci.n_friend_excluded, "doc_chars_p50": pct(ci.doc_chars, 50),
        "doc_chars_p95": pct(ci.doc_chars, 95), "embedded_now": ci.embed_info["embedded_now"],
        "embed_seconds": ci.embed_info["seconds"], "embed_calls": len(new), "embed_in_tokens": toks,
        "embed_cost_usd": round(cost, 6), "embed_cost_per_1k_library_items_usd": round(1000 * cost / n_items, 6),
        "build_s": round(ci.build_s, 1), "wall_s": round(time.time() - t0, 1)}
    if ci.embed_info["embedded_now"]:
        rep["docs_per_s"] = round(ci.embed_info["embedded_now"] / max(ci.embed_info["seconds"], 1e-9), 1)
        H.jdump(rep, os.path.join(WORK, "creator_index.json"))
    print(json.dumps(rep), flush=True)


# ---------------- live 3-small timing for searches only route-r2 sends to the instant path ----------------
def _timed_embed_small(texts):
    """Round 8.3's timed 3-small call (same model, dims, retries), this round's ledger purpose."""
    n0 = len(L.ledger())
    for att in range(6):
        try:
            t = time.time()
            ai.openai_embed(texts, model=Y.EMB_MODEL, dimensions=Y.EMB_DIM, purpose="c87_te_embed_timing")
            sec = time.time() - t
            return {"seconds": round(sec, 3), "cost_usd": L.ledger()[n0:][-1]["cost_usd"], "attempts": att + 1}
        except Exception as e:  # noqa: BLE001 - transient network errors: retry, keep only the successful call's time
            if "budget stop" in str(e) or att == 5:
                raise
            time.sleep(2 * (att + 1))


def timing():
    qs, _ = S81.queries()
    S = L.Combined("all", items=L.jl(os.path.join(DATA, "corpus", "items.jsonl")))
    r1, r2 = R.ShapeRouter(S), C.ShapeRouter2(S)
    typed = [q for q in qs if not q["examples"]]
    jobs = [q for q in typed if r1.route(q["query"])["path"] == "rewrite" and r2.route(q["query"])["path"] == "instant"]
    os.makedirs(WORK, exist_ok=True)
    out = json.load(open(TE_INST_R2)) if os.path.exists(TE_INST_R2) else {}
    qv = L.QueryVecs(Q.TE_QV_STORE)
    miss = [q for q in jobs if q["query"] not in qv.vec]
    assert not miss, f"{len(miss)} raw queries lack a 3-small vector"
    t0 = time.time()
    n = 0
    for q in jobs:
        if q["id"] in out:
            continue
        out[q["id"]] = _timed_embed_small(R.plan_instant(q)[0])
        n += 1
    H.jdump(out, TE_INST_R2)
    wall = time.time() - t0
    print(f"timing: {n} live 3-small calls in {wall:.1f} s ({n / max(wall, 1e-9):.2f} items/s); {len(jobs)} r2-only "
          f"instant searches", flush=True)


# ---------------- refine calls (cached; paid only where no earlier cache has the exact inputs) ----------------
def refine(cfgs, reps, workers):
    qs, _ = S81.queries()
    env = Env()
    rf = env.refiner
    orig = ai.openai_chat_json

    def tagged(*a, **k):  # this round's ledger purpose; prompt, model and schema are rf-v1's
        k["purpose"] = "c87_refine"
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
                order, g, _ = search_one(env, cfg, q, Pqr[q["id"]], rep, stop_before_refine=True)
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
    new = [r for r in L.ledger()[n0:] if r.get("purpose") == "c87_refine"]
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
    if os.path.exists(TE_INST_R2):
        te_inst = {**json.load(open(TE_INST_R2)), **te_inst}
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
        for q in qs:
            sp = split_of[q["id"]]
            parse = None if q["examples"] else Pqr[q["id"]]
            t = time.time()
            order, info, diag_s = search_one(env, cfg, q, parse, rep)
            local = time.time() - t - diag_s
            out[q["id"]] = order
            if q["examples"]:
                continue
            d = by[sp]
            path = info["route"]["path"]
            rq = Pqr["_meta"]["per_query"][q["id"]]
            rf_s = rf_c = 0.0
            if path == "instant":
                e, rw_s, rw_c = t_inst[q["id"]], 0.0, 0.0
            else:
                e, rw_s, rw_c = t_h0[q["id"]], rq["seconds"], rq["cost_usd"]
            es = (te_inst if path == "instant" else te_rw)[q["id"]]
            e_s, e_c = max(e["seconds"], es["seconds"]), e["cost_usd"] + es["cost_usd"]  # parallel, every search
            if "refine" in info:
                rf_s, rf_c = info["refine"]["seconds"], info["refine"]["cost_usd"]
                d["refine_s"].append(rf_s)
                d["refine_cost"].append(rf_c)
            tot = local + rw_s + e_s + rf_s
            d["local"].append(local)
            d["total"].append(tot)
            d["cost"].append(rw_c + e_c + rf_c)
            d[f"total_{path}_path"].append(tot)
            d[f"local_{path}_path"].append(local)
            d["yt_share_top10"].append(sum(plat.get(c) == "youtube" for c in order[:10]) / max(len(order[:10]), 1))
            agg[f"{sp}:{path}"] += 1
            if cfg == "r2":
                agg[f"{sp}:r2_{info['route'].get('r2')}"] += 1
            if "ci" in info:
                ci = info["ci"]
                d["ci_list_len"].append(ci["list_len"])
                agg[f"{sp}:ci_new_in_top10_pre_refine"] += ci["new_in_top10_pre_refine"] > 0
                agg[f"{sp}:ci_list_item_in_top10_pre_refine"] += ci["list_items_in_top10_pre_refine"] > 0
                agg[f"{sp}:ci_list_item_in_top10_final"] += ci["list_items_in_top10_final"] > 0
                agg[f"{sp}:ci_top_name_matched"] += ci["top_name_matched"]
                agg[f"{sp}:ci_any_name_matched"] += ci["any_name_matched"]
                agg[f"{sp}:ci_top_platform_{ci['top_platform']}"] += 1
                agg[f"{sp}:ci_new_in_top10_pre_refine_{path}"] += ci["new_in_top10_pre_refine"] > 0
                d["ci_new_in_top10_pre_refine_n"].append(ci["new_in_top10_pre_refine"])
            if "refine" in info:
                ri = info["refine"]
                agg[f"{sp}:refine_ok"] += ri["ok"]
                agg[f"{sp}:refine_failed"] += not ri["ok"]
                agg[f"{sp}:refine_cache_{ri['cache']}"] += 1
                for k in ("n_sent", "n_friends_kept", "n_invalid", "n_dup", "n_missing", "moved"):
                    agg[f"{sp}:refine_{k}"] += ri[k]
            per[q["id"]] = {**info, "path": path, "latency_local_s": round(local, 4), "latency_total_s": round(tot, 3)}
        wall = time.time() - t_run
        allv = collections.defaultdict(list)
        for sp in SPLITS:
            for k, v in by[sp].items():
                allv[k] += v
        splits = {}
        for sp, d in [(s, by[s]) for s in SPLITS] + [("all_typed", allv)]:
            n = len(d["local"])
            row = {"n_typed": n,
                   "local_p50_s": pct(d["local"], 50), "local_p95_s": pct(d["local"], 95),
                   "total_p50_s": pct(d["total"], 50), "total_p95_s": pct(d["total"], 95),
                   "total_rewrite_path_p50_s": pct(d["total_rewrite_path"], 50),
                   "total_rewrite_path_p95_s": pct(d["total_rewrite_path"], 95),
                   "total_instant_path_p50_s": pct(d["total_instant_path"], 50),
                   "total_instant_path_p95_s": pct(d["total_instant_path"], 95),
                   "instant_share": round(len(d["total_instant_path"]) / n, 4) if n else None,
                   "cost_per_1k_searches_usd": round(1000 * float(np.mean(d["cost"])), 4) if n else None,
                   "yt_share_top10_mean": round(float(np.mean(d["yt_share_top10"])), 4) if n else None,
                   "refined": len(d["refine_s"]),
                   "refine_p50_s": pct(d["refine_s"], 50), "refine_p95_s": pct(d["refine_s"], 95)}
            for k in [k for k in d if k.startswith("ci_")]:
                row[k] = {"mean": round(float(np.mean(d[k])), 3), "p50": pct(d[k], 50), "p95": pct(d[k], 95)}
            splits[sp] = row
        meta = {"config": cfg, "round": "8.7", "repeat": rep, "splits": SPLITS, "n_searches": len(qs),
                "base": "B8.5 = runs/r8.5/q8_r{k} (q8-v1: TFY with int8 item vectors)",
                "version": VERSION[cfg], "vector_mode": "int8",
                "rewrites": {"qr-v1": Pqr["_meta"]["sources"]},
                "ci": {"k_creators": C.CI_K, "weight": C.CI_W, "min_items": C.CI_MIN_ITEMS,
                       "creators": len(env.ci.keys), "member_items": env.ci.n_member_items,
                       "friend_creators_excluded": env.ci.n_friend_excluded,
                       "store": os.path.relpath(C.CI_STORE, DATA)} if cfg == "ci" else None,
                "r2": {"max_short": C.R2_MAX_SHORT} if cfg == "r2" else None,
                "refine_model": P.REFINE_MODEL, "refine_gate": f"rewrite-routed and q_ig < {C.REFINE_Q_IG_MAX}",
                "embedding": f"{G.EMB3L_MODEL}@{G.EMB3L_DIM}",
                "route_version": C.R2_VERSION if cfg == "r2" else R.ROUTE_VERSION,
                "counts": dict(agg), "per_split": splits,
                "index_build_s": round(env.build_s, 1), "h0_index_build_s": round(env.h0_build_s, 1),
                "quantise_s": env.quant_s, "route_index_build_s": round(env.route_build_s, 1),
                "extra_build_s": env.extra_build_s,
                "run_wall_s": round(wall, 1), "searches_per_s": round(len(qs) / max(wall, 1e-9), 2),
                "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
                "latency_model": "local (warm) + rewrite call's original uncached seconds where used + max(round "
                                 "8.1's live 3-large call, the live 3-small te call) + refine call",
                "per_search": per}
        ref = json.load(open(os.path.join(BASE, f"q8_r{rep}.json")))
        meta["diagnostics_vs_b85"] = S82.top10_diag(out, ref, plat, split_of)
        mlt = [k for k in out if not per.get(k)]
        meta["mlt_identical_to_b85"] = sum(out[k] == ref["queries"][k] for k in mlt)
        path = write_run(os.path.join(outdir, f"{cfg}_r{rep}.json"), f"c87:{cfg}", L.CodeIds(meta["embedding"]),
                         out, meta)
        written.append(path)
        sa = splits["all_typed"]
        print(f"wrote {os.path.relpath(path, DATA)}: {len(qs)} searches in {wall:.1f} s "
              f"({len(qs) / max(wall, 1e-9):.1f}/s); local p50 {sa['local_p50_s']} / p95 {sa['local_p95_s']} s; "
              f"total p50 {sa['total_p50_s']} / p95 {sa['total_p95_s']}; $/1k {sa['cost_per_1k_searches_usd']}",
              flush=True)
        same = sum(out[k] == ref["queries"][k] for k in ref["queries"])
        print(f"{cfg} r{rep}: {same} of {len(ref['queries'])} rankings identical to r8.5/q8 (1,000 deep); "
              f"more-like-this identical {meta['mlt_identical_to_b85']} / {len(mlt)}", flush=True)
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["embed", "timing", "refine", "run", "compare"])
    ap.add_argument("--configs", default="ci,r2")
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
    if a.cmd == "embed":
        return embed()
    if a.cmd == "timing":
        return timing()
    if a.cmd == "refine":
        return refine(cfgs, reps, a.workers)
    if a.cmd == "compare":
        return S82.compare(a.a, a.b, cfgs, reps)
    t0 = time.time()
    env = Env()
    print(f"index built in {env.build_s:.1f} s (H0 {env.h0_build_s:.1f} s; route {env.route_build_s:.1f} s; "
          f"extra {json.dumps(env.extra_build_s)}; quantise {env.quant_s} s)", flush=True)
    for cfg in cfgs:
        run_config(env, cfg, reps, TMP if cfg == "q8" and a.outdir == OUT else a.outdir)
    print(f"total wall {time.time() - t0:.1f} s", flush=True)


if __name__ == "__main__":
    main()
