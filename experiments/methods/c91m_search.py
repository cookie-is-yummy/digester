"""PROTOTYPE ONLY - round 9.1 Track 2 (media pilot) run files (LOG.md "Round 9.1 (BRIEF-9 Track 2: YouTube media
pilot) fixed parameters", row Y9.1-M).

Configs (every config on the int8 item store, c88_search's Env and logic):
  q8   Q8 from this runner: must equal runs/r8.5/q8_r{k} (586 dev-side searches) and runs/r9/q8_facet_dev_r{k}
       (16 facet_dev searches) exactly (reproduction gate). Written as q8ref_r{k} (both sources in one file).
  m2   Y9.1-M2 (m2-v1): Q8's fused scores + the same two media lists' RRF for described items only (no
       imputation), re-sorted; isolates the media evidence from M's coverage-fair reweighting of own vs te.
  m    Y9.1-M (m-v1): Q8 with one extra coverage-fair list group over the md-v1 media descriptions (RESEARCH-ONLY,
       media_pilot/): BM25 over the description texts (own BM25 query) + dense over their text-embedding-3-large
       vectors (own dense query rows incl. the HyDE blend, max over rows); only described items are eligible.
Searches: dev + yt_holdout + known_dev + ig_known_dev + facet_dev (602; one run file per repeat).
facet_dev's qr-v1 rewrites, query vectors, refine responses and timing are read (only) from runs/rewrites/facet_dev/,
where the round-9 runner put them; no other runs/rewrites/<split>/ folder is read. Method side only: never opens
evals/labels/ or eval_work/. Prints aggregates only.

usage: python experiments/methods/c91m_search.py index                 # embed the descriptions (paid, tiny)
       python experiments/methods/c91m_search.py refine --configs m    # new rf-v1 nano calls (paid if uncached)
       python experiments/methods/c91m_search.py run --configs q8,m [--outdir DIR]
       python experiments/methods/c91m_search.py compare --a DIR --b DIR --configs m
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
import c4_lib as L  # noqa: E402
import c5_lib as F  # noqa: E402
import c6_lib as G  # noqa: E402
import c81_lib as R  # noqa: E402
import c81_search as S81  # noqa: E402
import c82_search as S82  # noqa: E402
import c85_lib as X  # noqa: E402
import c87_lib as C  # noqa: E402
import c88_lib as K  # noqa: E402
import c88_search as S88  # noqa: E402
import c91_describe as D  # noqa: E402
import yt_lib as Y  # noqa: E402
from corpus import DATA, load_queries, write_run  # noqa: E402

M_VERSION = "m-v1"
OUT = os.path.join(DATA, "runs", "r9.1")
TMP = os.path.join(DATA, "tmp", "r9.1_media_checks")
FD = os.path.join(DATA, "runs", "rewrites", "facet_dev")
EMB = os.path.join(D.DIR, f"emb_{D.PV}")
CACHE = os.path.join(DATA, "cache", "r9.1-media", "rf-v1.jsonl")
SPLITS = S81.SPLITS + ["facet_dev"]
CONFIGS = ["q8", "m", "m2"]
FILE = {"q8": "q8ref", "m": "m", "m2": "m2"}
M2_VERSION = "m2-v1"
REF = {"dev_side": os.path.join(DATA, "runs", "r8.5", "q8_r{rep}.json"),
       "facet_dev": os.path.join(DATA, "runs", "r9", "q8_facet_dev_r{rep}.json")}
pct = S82.pct


# ---------------- media index ----------------
def described():
    """{code: md-v1 text} for status-ok rows (validated fields only)."""
    return {c: D.text_of(r) for c, r in sorted(D.done_rows().items()) if r["status"] == "ok"}


def index():
    t = described()
    ids = sorted(t)
    t0 = time.time()
    V = G.embed_3l([t[c] for c in ids], "r9.1_media_desc_vectors", batch=500, workers=1)
    L.save_store(EMB, ids, np.asarray(V, np.float32))
    w = time.time() - t0
    print(f"index: {len(ids)} descriptions embedded in {w:.1f} s ({len(ids) / max(w, 1e-9):.1f} items/s) -> "
          f"{os.path.relpath(EMB, DATA)}", flush=True)


class MediaIdx:
    def __init__(self, S):
        text = described()
        ids, V = L.load_store(EMB)
        assert sorted(ids) == sorted(text), "description vectors out of date (run `index`)"
        vec = dict(zip(ids, V))
        self.codes = [c for c in sorted(text) if c in S.pos]
        self.codeset = set(self.codes)
        self.n_rows, self.n_rankable = len(text), len(self.codes)
        self.V = np.array([vec[c] for c in self.codes], np.float32).reshape(-1, G.EMB3L_DIM)
        self.bm = Y.BM25({c: text[c] for c in self.codes})

    def dense(self, Qv, keep):
        s = (self.V @ Qv.T).max(axis=1)
        return [self.codes[n] for n in np.argsort(-s, kind="stable") if keep is None or keep(self.codes[n])][:1000]

    def group(self, Qv, bq, keep):
        return ([self.bm.rank(bq, keep=keep) if bq.strip() else [], self.dense(Qv, keep)], self.codeset)


# ---------------- data sources (dev side as c88_search; facet_dev from runs/rewrites/facet_dev, read only) ------
class UnionQV:
    """Read-only lookup: the dev store first (wins on overlap), then extra stores. Never embeds."""

    def __init__(self, base_vec, paths):
        self.vec = dict(base_vec)
        for p in paths:
            ids, V = L.load_store(p)
            for k, s in enumerate(ids):
                self.vec.setdefault(s, V[k])

    def get(self, texts):
        miss = [t for t in texts if t not in self.vec]
        assert not miss, f"{len(miss)} query strings not in the stores"
        return np.array([self.vec[t] for t in texts], dtype=np.float32)


def queries():
    qs, split_of = S81.queries()
    for q in load_queries("facet_dev"):
        qs.append(q)
        split_of[q["id"]] = "facet_dev"
    return qs, split_of


def rewrites(rep):
    a = S81.rewrites("qr-v1", rep)
    p = os.path.join(FD, f"qr-v1_gpt-5-nano_r{rep}.json")
    b = json.load(open(p))
    ks = [k for k in b if not k.startswith("_")]
    assert not set(ks) & set(a)
    a.update({k: b[k] for k in ks})
    a["_meta"]["per_query"].update(b["_meta"]["per_query"])
    a["_meta"]["sources"] = list(a["_meta"]["sources"]) + [os.path.relpath(p, DATA)]
    return a


def timing(name):
    out = json.load(open(os.path.join(S88.T83 if "_te_" in name else S88.T81, name)))
    fd = json.load(open(os.path.join(FD, "timing", name)))
    assert not set(fd) & set(out)
    out.update(fd)
    return out


def make_env(media=True):
    env = S88.Env()
    env.S.QV = UnionQV(env.S.QV.vec, [os.path.join(FD, "qvec_3l")])
    env.te.QVs = UnionQV(env.te.QVs.vec, [os.path.join(FD, "qvec_te")])
    rf = env.refiners[K.NANO]
    for path, tag in ((os.path.join(FD, "refine", "rf-v1.jsonl"), "r9-facet_dev"), (CACHE, "r9.1-media")):
        if os.path.exists(path):
            for line in open(path):
                r = json.loads(line)
                if r["key"] not in rf.cache:
                    rf.cache[r["key"]] = r
                    rf.source[r["key"]] = tag
    rf.out_path, rf.tag, rf.purpose = CACHE, "r9.1-media", "c91m_refine"
    env.media = MediaIdx(env.S) if media else None
    return env


def search_one(env, cfg, q, parse, rep, stop_before_refine=False):
    """c88_search.search_one (q8), with the media group added to the te fusion for cfg m."""
    S = env.S
    if q["examples"]:
        return S.mlt(q)[:1000], {}
    r = env.router_shape.route(q["query"])
    path = r["path"]
    info = {"route": r}
    keep = S.keep_fn(q.get("filters"))
    texts, caps, bq = S88.plan(q, parse, path)
    own, Qv, _ = C.own_lists_s(S, texts, caps, bq, keep)
    order, sc = F.fair_fuse(own, [])
    q_ig, pinfo = env.prior.read(q["query"], S.QV.get([q["query"]])[0], order)
    info["prior"] = pinfo
    groups = [env.te.group(texts, caps, bq, keep)]
    if cfg == "m":
        mg = env.media.group(Qv, bq, keep)
        groups.append(mg)
        info["media"] = {"bm25_len": len(mg[0][0]), "dense_len": len(mg[0][1])}
    order, sc = F.fair_fuse(own, groups)
    if cfg == "m2":  # media RRF added for described items only; no imputation for anyone else
        mg = env.media.group(Qv, bq, keep)
        info["media"] = {"bm25_len": len(mg[0][0]), "dense_len": len(mg[0][1])}
        sc = dict(sc)
        for lst in mg[0]:
            for r, c in enumerate(lst[:F.DEPTH]):
                sc[c] = sc.get(c, 0.0) + 1.0 / (F.K_RRF + r + 1)
        pos = {c: n for n, c in enumerate(order)}
        order = sorted(sc, key=lambda c: (-sc[c], pos.get(c, len(pos))))
    info["te_used"] = True
    order, sc = env.prior.apply(order, sc, q_ig)
    order = order[:1000]
    g = K.gate("q8", path, q_ig)
    if stop_before_refine:
        return order, {"gate": g, "path": path}
    if g:
        rf = env.refiners[K.NANO]
        (order, rinfo), rr = rf.get(rep, q["id"], q["query"], order)
        order = order[:1000]
        info["refine"] = {**rinfo, "seconds": rr["seconds"], "cost_usd": rr["cost_usd"], "tries": rr["tries"],
                          "in_tokens": rr.get("in_tokens", 0), "out_tokens": rr.get("out_tokens", 0),
                          "cache": rf.source.get(rr["key"]), "model": K.NANO}
    return order, info


# ---------------- refine calls ----------------
def refine(cfgs, reps, workers):
    qs, _ = queries()
    env = make_env()
    rf = env.refiners[K.NANO]
    jobs, src = {}, collections.Counter()
    t0 = time.time()
    for cfg in cfgs:
        for rep in reps:
            Pqr = rewrites(rep)
            for q in qs:
                if q["examples"]:
                    continue
                order, g = search_one(env, cfg, q, Pqr[q["id"]], rep, stop_before_refine=True)
                if not g["gate"]:
                    continue
                key = rf.key(rep, q["id"], order)
                src[(cfg, g["path"], rf.source.get(key, "new"))] += 1
                if key not in rf.cache:
                    jobs.setdefault(key, (rep, q, order))
    print(f"refine: gated by (config, path, source) {dict(src)}; {len(jobs)} new inputs "
          f"(pre-refine pass {time.time() - t0:.1f} s)", flush=True)
    if not jobs:
        return
    n0 = len(L.ledger())
    t0 = time.time()
    with cf.ThreadPoolExecutor(workers) as ex:
        res = list(ex.map(lambda j: rf.get(j[0], j[1]["id"], j[1]["query"], j[2], allow_call=True)[1],
                          list(jobs.values())))
    wall = time.time() - t0
    new = [r for r in L.ledger()[n0:] if r.get("purpose") == rf.purpose]
    print(f"refine: {len(jobs)} calls in {wall:.1f} s ({len(jobs) / max(wall, 1e-9):.2f} items/s), {len(new)} ledger "
          f"rows, ${sum(r['cost_usd'] for r in new):.4f}; ok {sum(r['ok'] for r in res)}, "
          f"failed {sum(not r['ok'] for r in res)}", flush=True)


# ---------------- runs ----------------
def _lat(d, k):
    return {"p50_s": pct(d[k], 50), "p95_s": pct(d[k], 95), "n": len(d[k])}


def reference(rep):
    a = json.load(open(REF["dev_side"].format(rep=rep)))["queries"]
    b = json.load(open(REF["facet_dev"].format(rep=rep)))["queries"]
    assert not set(a) & set(b)
    return {**a, **b}


def run_config(env, cfg, reps, outdir):
    qs, split_of = queries()
    S = env.S
    plat = {c: it["platform"] for it, c in zip(S.items, S.codes)}
    mset = env.media.codeset if env.media else set()
    t_inst, te_inst = timing("embed_timing_inst.json"), timing("embed_timing_te_inst.json")
    for rep in reps:
        Pqr = rewrites(rep)
        t_h0, te_rw = timing(f"embed_timing_h0_r{rep}.json"), timing(f"embed_timing_te_r{rep}.json")
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
            order, info = search_one(env, cfg, q, parse, rep)
            local = time.time() - t
            out[q["id"]] = order
            if q["examples"]:
                continue
            d = by[sp]
            path = info["route"]["path"]
            rq = Pqr["_meta"]["per_query"][q["id"]]
            if path == "instant":
                e, rw_s, rw_c = t_inst[q["id"]], 0.0, 0.0
            else:
                e, rw_s, rw_c = t_h0[q["id"]], rq["seconds"], rq["cost_usd"]
            es = (te_inst if path == "instant" else te_rw)[q["id"]]
            e_s, e_c = max(e["seconds"], es["seconds"]), e["cost_usd"] + es["cost_usd"]
            first = local + rw_s + e_s
            rf_s = rf_c = 0.0
            if "refine" in info:
                rf_s, rf_c = info["refine"]["seconds"], info["refine"]["cost_usd"]
                d["refine_s"].append(rf_s)
                d["refine_cost"].append(rf_c)
                agg[f"{sp}:refine_cache_{info['refine']['cache']}"] += 1
            d["local"].append(local)
            d["first_screen"].append(first)
            d["total"].append(first + rf_s)
            d["cost"].append(rw_c + e_c + rf_c)
            d["described_top10"].append(sum(c in mset for c in order[:10]))
            d["yt_share_top10"].append(sum(plat.get(c) == "youtube" for c in order[:10]) / max(len(order[:10]), 1))
            agg[f"{sp}:{path}"] += 1
            per[q["id"]] = {**info, "path": path, "latency_local_s": round(local, 4),
                            "latency_first_screen_s": round(first, 3), "latency_total_s": round(first + rf_s, 3)}
        wall = time.time() - t_run
        allv = collections.defaultdict(list)
        for sp in SPLITS:
            for k, v in by[sp].items():
                allv[k] += v
        rows = {}
        for sp, d in [(s, by[s]) for s in SPLITS] + [("all_typed", allv)]:
            n = len(d["local"])
            rows[sp] = {"n_typed": n, "local_p50_s": pct(d["local"], 50), "local_p95_s": pct(d["local"], 95),
                        "first_screen": _lat(d, "first_screen"), "total_p50_s": pct(d["total"], 50),
                        "total_p95_s": pct(d["total"], 95),
                        "cost_per_1k_searches_usd": round(1000 * float(np.mean(d["cost"])), 4) if n else None,
                        "refined": len(d["refine_s"]),
                        "described_in_top10_mean": round(float(np.mean(d["described_top10"])), 4) if n else None,
                        "searches_with_described_in_top10": int(sum(x > 0 for x in d["described_top10"])),
                        "yt_share_top10_mean": round(float(np.mean(d["yt_share_top10"])), 4) if n else None}
        ref = reference(rep)
        same = {sp: sum(out[k] == ref[k] for k in out if split_of[k] == sp) for sp in SPLITS}
        same_top10 = {sp: sum(out[k][:10] == ref[k][:10] for k in out if split_of[k] == sp) for sp in SPLITS}
        meta = {"config": cfg, "round": "9.1 (Track 2 media pilot)", "repeat": rep, "splits": SPLITS,
                "n_searches": len(qs), "base": "Q8 (q8-v1) = runs/r8.5/q8_r{k} + runs/r9/q8_facet_dev_r{k}",
                "version": {"q8": X.Q8_VERSION, "m": M_VERSION, "m2": M2_VERSION}[cfg], "vector_mode": "int8",
                "rewrites": {"qr-v1": Pqr["_meta"]["sources"]}, "refine_model": K.NANO,
                "refine_gate": f"rewrite-routed and q_ig < {K.REFINE_Q_IG_MAX}",
                "media": {"research_only": True, "descriptions": os.path.relpath(D.OUT, DATA),
                          "prompt_version": D.PV, "model": D.MODEL, "rows_ok": env.media.n_rows,
                          "rankable": env.media.n_rankable, "vectors": f"{G.EMB3L_MODEL}@{G.EMB3L_DIM} float",
                          "lists": "BM25 (own BM25 query) + dense (own query rows incl. HyDE blend, max)",
                          "fusion": "coverage-fair (c5_lib.fair_fuse), eligible = described items" if cfg == "m"
                          else "Q8 fused score + media-list RRF for described items only (no imputation)"}
                if cfg in ("m", "m2") else None,
                "embedding": f"{G.EMB3L_MODEL}@{G.EMB3L_DIM}", "route_version": R.ROUTE_VERSION,
                "counts": dict(agg), "per_split": rows, "identical_to_q8_base_by_split": same,
                "top10_identical_to_q8_base_by_split": same_top10,
                "index_build_s": round(env.build_s, 1), "run_wall_s": round(wall, 1),
                "searches_per_s": round(len(qs) / max(wall, 1e-9), 2),
                "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
                "latency_model": "c88_search's: local (warm) + rewrite call's original seconds where used + max(live "
                                 "3-large, live 3-small te call) + refine call",
                "per_search": per}
        p = write_run(os.path.join(outdir, f"{FILE[cfg]}_r{rep}.json"), f"c91m:{cfg}", L.CodeIds(meta["embedding"]),
                      out, meta)
        sa = rows["all_typed"]
        print(f"wrote {os.path.relpath(p, DATA)}: {len(qs)} searches in {wall:.1f} s ({len(qs) / max(wall, 1e-9):.1f} "
              f"items/s); local p50 {sa['local_p50_s']} p95 {sa['local_p95_s']} s; $/1k {sa['cost_per_1k_searches_usd']}; "
              f"identical to Q8 base {same}; top 10 identical {same_top10}; searches with a described item in top 10 "
              f"{ {sp: rows[sp]['searches_with_described_in_top10'] for sp in SPLITS} }", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["index", "refine", "run", "compare"])
    ap.add_argument("--configs", default="m")
    ap.add_argument("--reps", default="1,2,3")
    ap.add_argument("--outdir", default=OUT)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--a")
    ap.add_argument("--b")
    a = ap.parse_args()
    reps = [int(x) for x in a.reps.split(",")]
    cfgs = a.configs.split(",")
    assert all(c in CONFIGS for c in cfgs), cfgs
    if a.cmd == "index":
        return index()
    if a.cmd == "refine":
        return refine(cfgs, reps, a.workers)
    if a.cmd == "compare":
        for cfg in cfgs:
            for rep in reps:
                x = json.load(open(os.path.join(a.a, f"{FILE[cfg]}_r{rep}.json")))["queries"]
                y = json.load(open(os.path.join(a.b, f"{FILE[cfg]}_r{rep}.json")))["queries"]
                print(f"{cfg} r{rep}: {sum(x[k] == y.get(k) for k in x)} of {len(x)} rankings identical", flush=True)
        return
    t0 = time.time()
    env = make_env(media=os.path.exists(os.path.join(EMB, "ids.json")))
    print(f"index built in {env.build_s:.1f} s; media rankable {env.media.n_rankable if env.media else None}",
          flush=True)
    for cfg in cfgs:
        run_config(env, cfg, reps, a.outdir)
    print(f"total wall {time.time() - t0:.1f} s", flush=True)


if __name__ == "__main__":
    main()
