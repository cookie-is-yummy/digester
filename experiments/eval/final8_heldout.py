"""PROTOTYPE ONLY - round-8 final held-out runner (orchestrator side; LOG.md "Orchestrator decision, end of the
round-8 loop"). Produces frozen run files for H0r8 (runs/r8.1/h0r8), B8.5 = Q8 (runs/r8.5/q8) and B8.8 = FM
(runs/r8.8/fm) on `known_test` and `ig_known_test`, with no change to any method's logic or parameters.

Thin wrapper: every ranking comes from the builders' own functions (c81_search.search_one for h0r8 and
c88_search.search_one for q8 / fm, on their own Env classes). Only the data sources are swapped:
  queries      evals/labels/{known_test,ig_known_test}_queries.jsonl (ids, texts; nothing else under labels/ is read)
  qr-v1        c6_rewrite.run (same messages, schema, post-validation, gpt-5-nano minimal, 1,200 tokens, salt = repeat)
               with its call cache moved to runs/rewrites/<split>/cache_r<k>/ (never cache/r6/)
  3-large      query / phrase / HyDE vectors: dev store corpus/emb/oai3l_1024_queries (read only, wins on overlap) +
               held-out stores runs/rewrites/<split>/qvec_3l/ (float16 on disk, like the dev store)
  3-small te   dev store corpus/emb/c4_queries (read only) + runs/rewrites/<split>/qvec_te/
  refine       rf-v1 nano / mini responses for held-out searches in final8/cache/ (never cache/r8.*/)
  timing       live 3-large / 3-small timing calls in final8/timing/
Mode `dev` runs the same loop on the dev query set, dev rewrites and dev caches (no calls) to prove the wrapper
reproduces runs/r8.1/h0r8_r*, runs/r8.5/q8_r*, runs/r8.8/fm_r* exactly.
Prints aggregates only (never query or item text).

usage: python experiments/eval/final8_heldout.py rewrite --split known_test --rep 1
       python experiments/eval/final8_heldout.py prefetch
       python experiments/eval/final8_heldout.py timing --kind 3l|te
       python experiments/eval/final8_heldout.py refine [--workers 4]
       python experiments/eval/final8_heldout.py run --mode dev|heldout --configs h0r8 | q8,fm [--outdir DIR]
       python experiments/eval/final8_heldout.py compare --a DIR --b DIR
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
M = os.path.join(os.path.dirname(HERE), "methods")
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, M)
import ai  # noqa: E402
import c4_lib as L  # noqa: E402
import c5_lib as F  # noqa: E402
import c6_lib as G  # noqa: E402
import c6_rewrite as C6  # noqa: E402
import c81_lib as R  # noqa: E402
import c81_search as S81  # noqa: E402
import c82_lib as P  # noqa: E402
import c88_lib as K  # noqa: E402
import c88_search as S88  # noqa: E402
import yt_lib as Y  # noqa: E402
from corpus import DATA, write_run  # noqa: E402

HSPLITS = ["known_test", "ig_known_test"]
QFILE = {s: os.path.join(DATA, "evals", "labels", f"{s}_queries.jsonl") for s in HSPLITS}
RW = {s: os.path.join(DATA, "runs", "rewrites", s) for s in HSPLITS}
QV3L = {s: os.path.join(RW[s], "qvec_3l") for s in HSPLITS}
QVTE = {s: os.path.join(RW[s], "qvec_te") for s in HSPLITS}
WORK = os.path.join(DATA, "final8")
TIMING = os.path.join(WORK, "timing")
RCACHE = {K.NANO: os.path.join(WORK, "cache", "rf-v1.jsonl"), K.MINI: os.path.join(WORK, "cache", "rfm-v1.jsonl")}
OUT = os.path.join(DATA, "runs", "final8")
CHECK = os.path.join(DATA, "tmp", "final8_checks")
DEV_REF = {"h0r8": os.path.join(DATA, "runs", "r8.1", "h0r8_r{rep}.json"),
           "q8": os.path.join(DATA, "runs", "r8.5", "q8_r{rep}.json"),
           "fm": os.path.join(DATA, "runs", "r8.8", "fm_r{rep}.json")}
NAME = {"h0r8": "H0r8 (runs/r8.1/h0r8 definition)", "q8": "B8.5 = Q8 (runs/r8.5/q8 definition)",
        "fm": "B8.8 = FM (runs/r8.8/fm definition)"}
MODE = {"m": "heldout"}
pct = S81.pct


# ---------------- data sources ----------------
def queries():
    if MODE["m"] == "dev":
        return S81.queries()
    out, split_of = [], {}
    for s in HSPLITS:
        for line in open(QFILE[s]):
            if line.strip():
                q = json.loads(line)
                out.append(q)
                split_of[q["id"]] = s
    return out, split_of


def splits():
    return S81.SPLITS if MODE["m"] == "dev" else HSPLITS


def rewrites(rep):
    if MODE["m"] == "dev":
        return S81.rewrites("qr-v1", rep)
    out, per, src = {}, {}, []
    for s in HSPLITS:
        p = os.path.join(RW[s], f"qr-v1_gpt-5-nano_r{rep}.json")
        d = json.load(open(p))
        ks = [k for k in d if not k.startswith("_")]
        assert not set(ks) & set(out)
        out.update({k: d[k] for k in ks})
        per.update(d["_meta"]["per_query"])
        src.append(os.path.relpath(p, DATA))
    out["_meta"] = {"per_query": per, "sources": src}
    return out


class UnionQV:
    """Read-only query-vector lookup: the dev store first (wins on overlap), then the held-out stores. Never embeds."""

    def __init__(self, base_vec, paths):
        self.vec = dict(base_vec)
        self.n_base, self.n_added = len(self.vec), 0
        for p in paths:
            ids, V = L.load_store(p)
            for k, s in enumerate(ids):
                if s not in self.vec:
                    self.vec[s] = V[k]
                    self.n_added += 1

    def get(self, texts):
        miss = [t for t in texts if t not in self.vec]
        assert not miss, f"{len(miss)} query strings not prefetched"
        return np.array([self.vec[t] for t in texts], dtype=np.float32)


def load_rcache(rf, path, tag):
    if os.path.exists(path):
        for line in open(path):
            r = json.loads(line)
            if r["key"] not in rf.cache:
                rf.cache[r["key"]] = r
                rf.source[r["key"]] = tag


def env_h0():
    env = S81.Env(need_h5=False)
    env.S.QV = UnionQV(env.S.QV.vec, [QV3L[s] for s in HSPLITS])
    return env


def env_88():
    env = S88.Env()
    env.S.QV = UnionQV(env.S.QV.vec, [QV3L[s] for s in HSPLITS])
    env.te.QVs = UnionQV(env.te.QVs.vec, [QVTE[s] for s in HSPLITS])
    if MODE["m"] == "heldout":  # new refine responses go to final8/cache only (dev caches stay read-only, unused)
        te_rows = F.te_meta_rows()
        env.refiners = {}
        for m, pur, tag in ((K.NANO, "final8_refine", "final8"), (K.MINI, "final8_refine_mini", "final8-mini")):
            rf = K.Refiner88(env.S, te_rows, model=m, purpose=pur)
            rf.cache, rf.source = {}, {}
            load_rcache(rf, RCACHE[m], tag)
            rf.out_path, rf.tag = RCACHE[m], tag
            env.refiners[m] = rf
    return env


# ---------------- rewrites (paid) ----------------
def rewrite(split, rep):
    G.CACHE = os.path.join(RW[split], f"cache_r{rep}")
    C6.ALT.update({"queries": QFILE[split], "outdir": RW[split], "splits": [split]})
    C6.run("gpt-5-nano", [rep])


# ---------------- query vectors (paid) ----------------
def te_strings(q, parse, path):
    texts, caps, _ = S88.plan(q, parse, path)
    return texts + caps


def held_jobs():
    """Per split: 3-large strings (every typed search, all repeats: query + phrases + HyDE) and 3-small te strings
    (as c83_search.te_jobs: instant-routed raw query once, rewrite-routed plan strings per repeat), plus routes."""
    MODE["m"] = "heldout"
    qs, split_of = queries()
    S = L.Combined("all", items=L.jl(os.path.join(DATA, "corpus", "items.jsonl")))
    router = R.ShapeRouter(S)
    paths = {q["id"]: router.route(q["query"])["path"] for q in qs if not q["examples"]}
    s3l, ste = collections.defaultdict(list), collections.defaultdict(list)
    te_t, l3_t = [], []
    for q in qs:
        if not q["examples"] and paths[q["id"]] == "instant":
            ste[split_of[q["id"]]] += te_strings(q, None, "instant")
            te_t.append((0, q, te_strings(q, None, "instant")))
        if not q["examples"]:
            l3_t.append((0, q, [q["query"]]))
    for rep in (1, 2, 3):
        Pqr = rewrites(rep)
        for q in qs:
            if q["examples"]:
                continue
            pr = Pqr[q["id"]]
            ss = [q["query"]] + pr["phrases"] + (pr.get("hypothetical_captions") or [])
            s3l[split_of[q["id"]]] += ss
            l3_t.append((rep, q, ss))
            if paths[q["id"]] == "rewrite":
                ste[split_of[q["id"]]] += te_strings(q, pr, "rewrite")
                te_t.append((rep, q, te_strings(q, pr, "rewrite")))
    return qs, split_of, paths, s3l, ste, l3_t, te_t


def prefetch():
    from sklearn.preprocessing import normalize
    qs, split_of, paths, s3l, ste, _, _ = held_jobs()
    n_inst = collections.Counter(split_of[k] for k, v in paths.items() if v == "instant")
    print(f"routes (instant / typed): { {s: (n_inst[s], sum(1 for q in qs if split_of[q['id']] == s)) for s in HSPLITS} }",
          flush=True)
    for kind, need, base, stores in (("3l", s3l, G.QueryVecs3L().vec, QV3L), ("te", ste, L.QueryVecs("c4_queries").vec,
                                                                                QVTE)):
        have = set(base)
        for s in HSPLITS:
            ids, V = L.load_store(stores[s])
            have |= set(ids)
            miss = sorted({t for t in need[s] if t not in have})
            n0 = len(L.ledger())
            t0 = time.time()
            if miss:
                if kind == "3l":
                    Vn = G.embed_3l(miss, "final8_query_vectors_3l", batch=500, workers=1)
                else:
                    Vn = normalize(Y.embed_texts(miss, "final8_te_query_vectors", batch=500, workers=1))
                allids = list(ids) + miss
                L.save_store(stores[s], allids, np.vstack([V, Vn]) if len(ids) else Vn)
                have |= set(miss)
            wall = time.time() - t0
            cost = sum(r["cost_usd"] for r in L.ledger()[n0:])
            print(f"prefetch {kind} {s}: {len(set(need[s]))} distinct strings, {len(miss)} embedded in {wall:.1f} s "
                  f"({len(miss) / max(wall, 1e-9):.0f}/s), ${cost:.5f}", flush=True)


def _timed(texts, model, dim, purpose):
    n0 = len(L.ledger())
    for att in range(6):
        try:
            t = time.time()
            ai.openai_embed(texts, model=model, dimensions=dim, purpose=purpose)
            sec = time.time() - t
            # Take the cost from this call's own ledger row (same purpose and model), not the last row written:
            # other jobs (e.g. refine passes) may append rows concurrently. Fixed after the round-8 final scoring,
            # where the race misattributed 40 timing entries (results/r8-final.md, verifier note).
            mine = [r for r in L.ledger()[n0:] if r.get("purpose") == purpose and r.get("model") == model]
            return {"seconds": round(sec, 3), "cost_usd": mine[-1]["cost_usd"] if mine else None, "attempts": att + 1}
        except Exception as e:  # noqa: BLE001 - transient network errors: retry, keep only the successful call's time
            if "budget stop" in str(e) or att == 5:
                raise
            time.sleep(2 * (att + 1))


def timing(kind):
    """c81_search.timing (3-large: raw query once per typed search; query + phrases + HyDE per search and repeat) and
    c83_search.timing (3-small te: instant-routed raw query once; rewrite-routed plan strings per repeat)."""
    _, _, _, _, _, l3_t, te_t = held_jobs()
    os.makedirs(TIMING, exist_ok=True)
    jobs = l3_t if kind == "3l" else te_t
    model, dim, pur = ((G.EMB3L_MODEL, G.EMB3L_DIM, "final8_query_embed_timing") if kind == "3l"
                       else (Y.EMB_MODEL, Y.EMB_DIM, "final8_te_embed_timing"))
    fname = (lambda r: "embed_timing_inst.json" if r == 0 else f"embed_timing_h0_r{r}.json") if kind == "3l" else \
        (lambda r: "embed_timing_te_inst.json" if r == 0 else f"embed_timing_te_r{r}.json")
    out = {}
    for r in (0, 1, 2, 3):
        p = os.path.join(TIMING, fname(r))
        out[r] = json.load(open(p)) if os.path.exists(p) else {}
    t0, n = time.time(), 0
    for rep, q, ss in jobs:
        if q["id"] in out[rep]:
            continue
        out[rep][q["id"]] = _timed(ss, model, dim, pur)
        n += 1
        if n % 200 == 0:
            for r, d in out.items():
                json.dump(d, open(os.path.join(TIMING, fname(r)), "w"))
    for r, d in out.items():
        json.dump(d, open(os.path.join(TIMING, fname(r)), "w"))
    wall = time.time() - t0
    print(f"timing {kind}: {n} live calls in {wall:.1f} s ({n / max(wall, 1e-9):.2f} items/s)", flush=True)


# ---------------- refine (paid, held-out only) ----------------
def refine(workers):
    MODE["m"] = "heldout"
    qs, _ = queries()
    env = env_88()
    jobs = {K.NANO: {}, K.MINI: {}}
    src = collections.Counter()
    t0 = time.time()
    for rep in (1, 2, 3):
        Pqr = rewrites(rep)
        for q in qs:
            if q["examples"]:
                continue
            for cfg in ("q8", "fm"):
                order, g = S88.search_one(env, cfg, q, Pqr[q["id"]], rep, stop_before_refine=True)
                if not g["gate"]:
                    continue
                rf = env.refiners[S88.MODEL[cfg]]
                key = rf.key(rep, q["id"], order)
                src[(cfg, g["path"], rf.source.get(key, "new"))] += 1
                if key not in rf.cache:
                    jobs[S88.MODEL[cfg]].setdefault(key, (rep, q, order))
    pre = time.time() - t0
    print(f"refine: gated by (config, path, source) {dict(src)}; new inputs { {m: len(v) for m, v in jobs.items()} } "
          f"(pre-refine pass {pre:.1f} s, {3 * sum(1 for q in qs if not q['examples']) / max(pre, 1e-9):.1f} items/s)",
          flush=True)
    for model, uniq in jobs.items():
        if not uniq:
            continue
        rf = env.refiners[model]
        n0 = len(L.ledger())
        t1 = time.time()
        with cf.ThreadPoolExecutor(workers) as ex:
            res = list(ex.map(lambda j: rf.get(j[0], j[1]["id"], j[1]["query"], j[2], allow_call=True)[1],
                              list(uniq.values())))
        wall = time.time() - t1
        new = [r for r in L.ledger()[n0:] if r.get("purpose") == rf.purpose]
        print(f"refine {model}: {len(uniq)} calls in {wall:.1f} s ({len(uniq) / max(wall, 1e-9):.2f} items/s), "
              f"{len(new)} ledger rows, ${sum(r['cost_usd'] for r in new):.4f}; ok {sum(r['ok'] for r in res)}, "
              f"failed {sum(not r['ok'] for r in res)}; call s p50 {pct([r['seconds'] for r in res], 50)} "
              f"p95 {pct([r['seconds'] for r in res], 95)}", flush=True)


# ---------------- runs ----------------
def _lat(d, k):
    return {"p50_s": pct(d[k], 50), "p95_s": pct(d[k], 95), "n": len(d[k])}


def timing_files():
    if MODE["m"] == "dev":
        return S81.WORK, S88.T83
    return TIMING, TIMING


def search(env, cfg, q, parse, rep):
    if cfg == "h0r8":
        return S81.search_one(env, "h0r8", q, parse, None)
    return S88.search_one(env, cfg, q, parse, rep)


def run_rep(env, cfg, rep, qs, split_of):
    """One repeat over every search: c81_search.run_config's (h0r8) / c88_search.run_config's (q8, fm) loop and
    latency / cost model, unchanged; returns (rankings, per_search, per_split aggregates, wall)."""
    S = env.S
    plat = {c: it["platform"] for it, c in zip(S.items, S.codes)}
    t81, t83 = timing_files()
    t_inst = json.load(open(os.path.join(t81, "embed_timing_inst.json")))
    t_h0 = json.load(open(os.path.join(t81, f"embed_timing_h0_r{rep}.json")))
    if cfg != "h0r8":
        te_inst = json.load(open(os.path.join(t83, "embed_timing_te_inst.json")))
        te_rw = json.load(open(os.path.join(t83, f"embed_timing_te_r{rep}.json")))
    Pqr = rewrites(rep)
    typed = [x for x in qs if not x["examples"]]
    for q in typed[:5]:  # warm-up (not timed, not written)
        search(env, cfg, q, Pqr[q["id"]], rep)
    out, per = {}, {}
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    agg = collections.Counter()
    t_run = time.time()
    for q in qs:
        sp = split_of[q["id"]]
        parse = None if q["examples"] else Pqr[q["id"]]
        t = time.time()
        order, info = search(env, cfg, q, parse, rep)
        local = time.time() - t
        out[q["id"]] = order
        if q["examples"]:
            continue
        d = by[sp]
        rq = Pqr["_meta"]["per_query"][q["id"]]
        if cfg == "h0r8":  # c81_search.run_config, cfg h0r8 (always the rewrite path)
            path = "rewrite"
            e = t_h0[q["id"]]
            rw_s, rw_c = rq["seconds"], rq["cost_usd"]
            d["local"].append(local)
            d["total"].append(local + rw_s + e["seconds"])
            d["embed_s"].append(e["seconds"])
            d["cost"].append(rw_c + e["cost_usd"])
            d["cost_rw"].append(rw_c)
            d["cost_emb"].append(e["cost_usd"])
            d["rewrite_s"].append(rw_s)
            d["yt_share_top10"].append(sum(plat.get(c) == "youtube" for c in order[:10]) / max(len(order[:10]), 1))
            agg[f"{sp}:{path}"] += 1
            per[q["id"]] = {**info, "path": path, "latency_local_s": round(local, 4),
                            "latency_total_s": round(d["total"][-1], 3)}
            continue
        # c88_search.run_config
        path = info["route"]["path"]
        rf_s = rf_c = 0.0
        if path == "instant":
            e, rw_s, rw_c = t_inst[q["id"]], 0.0, 0.0
        else:
            e, rw_s, rw_c = t_h0[q["id"]], rq["seconds"], rq["cost_usd"]
        es = (te_inst if path == "instant" else te_rw)[q["id"]]
        e_s, e_c = max(e["seconds"], es["seconds"]), e["cost_usd"] + es["cost_usd"]
        first = local + rw_s + e_s
        if "refine" in info:
            rf_s, rf_c = info["refine"]["seconds"], info["refine"]["cost_usd"]
            d["refine_s"].append(rf_s)
            d["refine_cost"].append(rf_c)
            d[f"refine_s_{path}"].append(rf_s)
            d["refined_screen"].append(first + rf_s)
            d[f"refined_screen_{path}"].append(first + rf_s)
        tot = first + rf_s
        d["local"].append(local)
        d["first_screen"].append(first)
        d[f"first_screen_{path}"].append(first)
        d["total"].append(tot)
        d["cost"].append(rw_c + e_c + rf_c)
        d["cost_rw"].append(rw_c)
        d["cost_emb"].append(e_c)
        d[f"total_{path}_path"].append(tot)
        d["yt_share_top10"].append(sum(plat.get(c) == "youtube" for c in order[:10]) / max(len(order[:10]), 1))
        d["q_ig"].append(info["prior"]["q_ig"])
        agg[f"{sp}:{path}"] += 1
        if "refine" in info:
            ri = info["refine"]
            agg[f"{sp}:refined_{path}"] += 1
            agg[f"{sp}:refine_ok"] += ri["ok"]
            agg[f"{sp}:refine_failed"] += not ri["ok"]
            agg[f"{sp}:refine_cache_{ri['cache']}"] += 1
            for k in ("n_sent", "n_friends_kept", "n_invalid", "n_dup", "n_missing", "moved"):
                agg[f"{sp}:refine_{k}"] += ri[k]
            agg[f"{sp}:refine_moved_any"] += ri["moved"] > 0
        per[q["id"]] = {**info, "path": path, "latency_local_s": round(local, 4),
                        "latency_first_screen_s": round(first, 3), "latency_total_s": round(tot, 3)}
    wall = time.time() - t_run
    allv = collections.defaultdict(list)
    for sp in splits():
        for k, v in by[sp].items():
            allv[k] += v
    rows = {}
    for sp, d in [(s, by[s]) for s in splits()] + [("all_typed", allv)]:
        n = len(d["local"])
        row = {"n_typed": n, "local_p50_s": pct(d["local"], 50), "local_p95_s": pct(d["local"], 95),
               "total_p50_s": pct(d["total"], 50), "total_p95_s": pct(d["total"], 95),
               "cost_per_1k_searches_usd": round(1000 * float(np.mean(d["cost"])), 4) if n else None,
               "cost_per_1k_rewrite_usd": round(1000 * float(np.mean(d["cost_rw"])), 4) if n else None,
               "cost_per_1k_embed_usd": round(1000 * float(np.mean(d["cost_emb"])), 4) if n else None,
               "yt_share_top10_mean": round(float(np.mean(d["yt_share_top10"])), 4) if n else None}
        if cfg == "h0r8":
            row.update({"rewrite_p50_s": pct(d["rewrite_s"], 50), "rewrite_p95_s": pct(d["rewrite_s"], 95),
                        "embed_call_p50_s": pct(d["embed_s"], 50), "embed_call_p95_s": pct(d["embed_s"], 95)})
        else:
            row.update({
                "total_rewrite_path_p50_s": pct(d["total_rewrite_path"], 50),
                "total_rewrite_path_p95_s": pct(d["total_rewrite_path"], 95),
                "total_instant_path_p50_s": pct(d["total_instant_path"], 50),
                "total_instant_path_p95_s": pct(d["total_instant_path"], 95),
                "first_screen": _lat(d, "first_screen"), "first_screen_instant": _lat(d, "first_screen_instant"),
                "first_screen_rewrite": _lat(d, "first_screen_rewrite"), "refined_screen": _lat(d, "refined_screen"),
                "refined_screen_instant": _lat(d, "refined_screen_instant"),
                "refined_screen_rewrite": _lat(d, "refined_screen_rewrite"),
                "instant_share": round(len(d["total_instant_path"]) / n, 4) if n else None,
                "refine_cost_per_1k_refined_usd": round(1000 * float(np.mean(d["refine_cost"])), 4)
                if d["refine_cost"] else None,
                "refined": len(d["refine_s"]), "refined_share": round(len(d["refine_s"]) / n, 4) if n else None,
                "refine_p50_s": pct(d["refine_s"], 50), "refine_p95_s": pct(d["refine_s"], 95),
                "refine_instant": _lat(d, "refine_s_instant"), "refine_rewrite": _lat(d, "refine_s_rewrite"),
                "q_ig_lt_0.5": int(sum(x < 0.5 for x in d["q_ig"])), "q_ig_median": pct(d["q_ig"], 50)})
        rows[sp] = row
    return out, per, rows, dict(agg), wall, Pqr["_meta"]["sources"]


def common_meta(env, cfg, rep, wall, n, sources):
    m = {"config": cfg, "definition": NAME[cfg], "round": "8 final (held-out)", "repeat": rep,
         "embedding": f"{G.EMB3L_MODEL}@{G.EMB3L_DIM}", "route_version": R.ROUTE_VERSION,
         "rewrites": {"qr-v1": sources}, "index_build_s": round(env.build_s, 1),
         "run_wall_s": round(wall, 1), "searches_per_s": round(n / max(wall, 1e-9), 2),
         "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
         "query_vectors": {"3l": "corpus/emb/oai3l_1024_queries (dev, read only) + runs/rewrites/<split>/qvec_3l",
                           "te": None if cfg == "h0r8" else "corpus/emb/c4_queries (dev, read only) + "
                                                            "runs/rewrites/<split>/qvec_te"},
         "runner": "experiments/eval/final8_heldout.py (calls " +
                   ("c81_search.search_one h0r8" if cfg == "h0r8" else f"c88_search.search_one {cfg}") + ")"}
    if cfg == "h0r8":
        m.update({"hyde_alpha": L.HYDE_ALPHA,
                  "latency_model": "local search (warm) + rewrite call's original uncached seconds + one live "
                                   "3-large query-embedding call (query + phrases + HyDE captions)"})
    else:
        m.update({"version": S88.VERSION[cfg], "vector_mode": "int8", "refine_model": S88.MODEL[cfg],
                  "refine_prompt": P.REFINE_VERSION, "refine_reasoning_effort": "minimal",
                  "refine_gate": f"rewrite-routed and q_ig < {K.REFINE_Q_IG_MAX}",
                  "latency_model": "local (warm) + rewrite call's original uncached seconds where used + max(live "
                                   "3-large call, live 3-small te call) + refine call; first screen = all but the "
                                   "refine, refined screen = first screen + refine (refined searches)"})
    m["cost_note"] = "ledger list prices; per 1k typed searches; rewrite at the original call's cost"
    return m


def run(mode, cfgs, reps, outdir):
    MODE["m"] = mode
    qs, split_of = queries()
    t0 = time.time()
    env = env_h0() if cfgs == ["h0r8"] else env_88()
    print(f"[{mode}] index built in {env.build_s:.1f} s; 3-large query vectors {env.S.QV.n_base} dev + "
          f"{env.S.QV.n_added} held-out", flush=True)
    for cfg in cfgs:
        for rep in reps:
            out, per, rows, agg, wall, sources = run_rep(env, cfg, rep, qs, split_of)
            meta = common_meta(env, cfg, rep, wall, len(qs), sources)
            meta["counts"] = agg
            sa = rows["all_typed"]
            if mode == "dev":
                meta.update({"mode": "dev reproduction", "per_split": rows, "per_search": per})
                path = write_run(os.path.join(outdir, f"{cfg}_r{rep}.json"), f"final8:{cfg}",
                                 L.CodeIds(meta["embedding"]), out, meta)
                ref = json.load(open(DEV_REF[cfg].format(rep=rep)))["queries"]
                same = sum(out[k][:1000] == ref[k] for k in ref)
                print(f"[dev] {cfg} r{rep}: {same} of {len(ref)} rankings identical to "
                      f"{os.path.relpath(DEV_REF[cfg].format(rep=rep), DATA)} (1,000 deep; run has {len(out)}); "
                      f"wall {wall:.1f} s", flush=True)
                continue
            for sp in HSPLITS:
                ks = [k for k in out if split_of[k] == sp]
                m = {**meta, "split": sp, "n_searches": len(ks),
                     "file_layout": "one file per method, split and repeat",
                     "counts": {k: v for k, v in agg.items() if k.startswith(sp + ":")},
                     "per_split": {sp: rows[sp], "both_splits_all_typed": sa},
                     "per_search": {k: per[k] for k in ks if k in per}}
                path = write_run(os.path.join(outdir, f"{cfg}_{sp}_r{rep}.json"), f"final8:{cfg}",
                                 L.CodeIds(meta["embedding"]), {k: out[k] for k in ks}, m)
                r = rows[sp]
                extra = "" if cfg == "h0r8" else (f"; first p50 {r['first_screen']['p50_s']}; refined {r['refined']} "
                                                  f"(screen p50 {r['refined_screen']['p50_s']}); instant share "
                                                  f"{r['instant_share']}")
                print(f"wrote {os.path.relpath(path, DATA)}: {len(ks)} searches; local p50 {r['local_p50_s']} / "
                      f"p95 {r['local_p95_s']}; total p50 {r['total_p50_s']} / p95 {r['total_p95_s']}; "
                      f"$/1k {r['cost_per_1k_searches_usd']}{extra}", flush=True)
    print(f"total wall {time.time() - t0:.1f} s", flush=True)


def compare(a, b):
    for f in sorted(os.listdir(a)):
        if not f.endswith(".json"):
            continue
        pb = os.path.join(b, f)
        if not os.path.exists(pb):
            print(f"{f}: missing in b", flush=True)
            continue
        x, y = json.load(open(os.path.join(a, f)))["queries"], json.load(open(pb))["queries"]
        same = sum(x[k] == y.get(k) for k in x)
        print(f"{f}: {same} of {len(x)} rankings identical (1,000 deep)", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["rewrite", "prefetch", "timing", "refine", "run", "compare"])
    ap.add_argument("--split")
    ap.add_argument("--rep", type=int)
    ap.add_argument("--kind", choices=["3l", "te"])
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--mode", choices=["dev", "heldout"], default="heldout")
    ap.add_argument("--configs", default="q8,fm")
    ap.add_argument("--reps", default="1,2,3")
    ap.add_argument("--outdir")
    ap.add_argument("--a")
    ap.add_argument("--b")
    a = ap.parse_args()
    if a.cmd == "rewrite":
        assert a.split in HSPLITS
        return rewrite(a.split, a.rep)
    if a.cmd == "prefetch":
        return prefetch()
    if a.cmd == "timing":
        return timing(a.kind)
    if a.cmd == "refine":
        return refine(a.workers)
    if a.cmd == "compare":
        return compare(a.a, a.b)
    cfgs = a.configs.split(",")
    assert cfgs == ["h0r8"] or set(cfgs) <= {"q8", "fm"}, "h0r8 runs alone (float store); q8 / fm share int8"
    outdir = a.outdir or (CHECK if a.mode == "dev" else OUT)
    run(a.mode, cfgs, [int(x) for x in a.reps.split(",")], outdir)


if __name__ == "__main__":
    main()
