"""PROTOTYPE ONLY - round 8.1 run files (LOG.md "Round 8.1 fixed parameters", rows Y8.1-H5d, Y8.1-I, Y8.1-R).

Configs (one variable each vs H0r8 = H0 on the rebuilt round-8 vectors):
  h0r8   H0 (C0 + 3-large 1,024 d, cached gpt-5-nano qr-v1 repeat k). On dev + yt_holdout it must equal
         runs/r8_base/h0r8_r{k} exactly (1,000 deep); on known_dev / ig_known_dev it uses the new qr-v1 repeats.
  h5     round 7's H5 with round 7's Creators7 (hash-order dependent). Only for the determinism check (tmp/).
  h5d    round 7's H5 with Creators7d (deterministic creator profiles and tie-sorted creator rankings).
  inst   instant path: no rewrite, no HyDE; raw query -> 3-large dense (gate, PRF) + BM25 -> RRF. Deterministic, so
         one run, copied to _r1.._r3.
  route  route-r1 (c81_lib.ShapeRouter): instant path for routed searches, H0 (rewrite repeat k) for the rest.
Searches: dev + yt_holdout + known_dev + ig_known_dev (586; one run file per repeat covering all four splits).
More-like-this searches never use a rewrite, so every config gives them H0's ranking.

Latency per typed search = local search (warm; vectors cached, index built) + the rewrite call's original uncached
seconds where a rewrite is used (h5d: max(qr-v1, qs-v1), parallel) + one live 3-large query-embedding call
(h0r8 / h5d / rewrite-routed: query + phrases + HyDE captions, measured once per search and repeat; inst /
instant-routed: the raw query alone, measured once per search). Prints aggregates only.

usage: python experiments/methods/c81_search.py prefetch          # embed every query string into the 3-large store
       python experiments/methods/c81_search.py timing [--reps 1,2,3]
       python experiments/methods/c81_search.py run --configs h0r8,h5d,inst,route [--reps 1,2,3] [--outdir DIR]
       python experiments/methods/c81_search.py compare --a DIR --b DIR --configs ...   # identical rankings?
"""
import argparse
import collections
import json
import os
import shutil
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
import c7_search as C7  # noqa: E402
import c81_lib as R  # noqa: E402
from corpus import DATA, load_queries, write_run  # noqa: E402

SPLITS = ["dev", "yt_holdout", "known_dev", "ig_known_dev"]
RW_BASE = os.path.join(DATA, "runs", "rewrites")
RW_NEW = os.path.join(DATA, "runs", "rewrites", "r8.1")
OUT = os.path.join(DATA, "runs", "r8.1")
WORK = os.path.join(DATA, "r8.1")
CONFIGS = ["h0r8", "h5", "h5d", "inst", "route"]
USES_QS = {"h5", "h5d"}


RUN_SPLITS = list(SPLITS)


def queries():
    out, split_of = [], {}
    for s in RUN_SPLITS:
        for q in load_queries(s):
            out.append(q)
            split_of[q["id"]] = s
    return out, split_of


def rewrites(prefix, rep):
    """Cached repeat k for dev + yt_holdout (rounds 4.1 / 5) merged with the new round-8.1 repeat k (known sets)."""
    a = json.load(open(os.path.join(RW_BASE, f"{prefix}_gpt-5-nano_r{rep}.json")))
    pb = os.path.join(RW_NEW, f"{prefix}_gpt-5-nano_r{rep}.json")
    b = json.load(open(pb)) if set(RUN_SPLITS) & {"known_dev", "ig_known_dev"} else {"_meta": {"per_query": {}}}
    assert not (set(a) - {"_meta", "_note"}) & (set(b) - {"_meta", "_note"})
    out = {k: v for k, v in a.items() if not k.startswith("_")}
    out.update({k: v for k, v in b.items() if not k.startswith("_")})
    out["_meta"] = {"per_query": {**a["_meta"]["per_query"], **b["_meta"]["per_query"]},
                    "sources": [os.path.relpath(p, DATA) for p in
                                (os.path.join(RW_BASE, f"{prefix}_gpt-5-nano_r{rep}.json"),
                                 os.path.join(RW_NEW, f"{prefix}_gpt-5-nano_r{rep}.json"))]}
    return out


def strings(qs, Pqr, Pqs=None):
    out = []
    for q in qs:
        if q["examples"]:
            continue
        p = Pqr[q["id"]]
        out += [q["query"]] + p["phrases"] + (p.get("hypothetical_captions") or [])
        if Pqs is not None:
            d = (Pqs[q["id"]]["creator_lookup"]["description"] or "").strip()
            if d:
                out.append(d)
    return out


def pct(xs, p):
    return round(float(np.percentile(xs, p)), 3) if xs else None


class Env:
    """The parts of c7_search.Env that H0 / H5 need (no te lists, no H3-only profiles), plus round 8.1's parts."""

    def __init__(self, need_h5=True):
        t0 = time.time()
        items = L.jl(os.path.join(DATA, "corpus", "items.jsonl"))
        self.S = L.Combined("all", items=items)
        G.swap_to_3l(self.S)
        self.h0_build_s = time.time() - t0
        S = self.S
        I.prepare(S)
        t1 = time.time()
        self.router_shape = R.ShapeRouter(S)
        self.route_build_s = time.time() - t1
        self.CR4 = self.CR4_orig = self.CR4d = None
        self.creator_build_s = {}
        if need_h5:
            self.te_rows = F.te_meta_rows()
            self.facets = H.Facets7()
            self.router = H.Router()
            self.tp = H.TimePct(S)
            src = {"instagram": "ig", "youtube": "yt"}  # adapter source -> the router head's group label
            self.group = {c: src.get(it["platform"]) for it, c in zip(S.items, S.codes)}
            t2 = time.time()
            self.CR4_orig = H.Creators7(S, self.te_rows, self.facets, enriched=True)
            self.creator_build_s["h5"] = round(time.time() - t2, 1)
            t3 = time.time()
            self.CR4d = R.Creators7d(S, self.te_rows, self.facets, enriched=True)
            self.creator_build_s["h5d"] = round(time.time() - t3, 1)
            self.CR_elig = set(self.CR4d.of)
            assert self.CR_elig == set(self.CR4_orig.of)
        self.ce = None
        self.build_s = time.time() - t0


def instant(env, q):
    S = env.S
    keep = S.keep_fn(q.get("filters"))
    texts, caps, bq = R.plan_instant(q)
    own, _ = F.own_lists(S, texts, caps, bq, keep)
    order, _ = F.fair_fuse(own, [])
    return order[:1000]


def search_one(env, cfg, q, parse, slots):
    if q["examples"]:
        return env.S.mlt(q)[:1000], {}
    if cfg == "h0r8":
        return C7.search_one(env, "h0", q, parse, None)
    if cfg in ("h5", "h5d"):
        env.CR4 = env.CR4_orig if cfg == "h5" else env.CR4d
        return C7.search_one(env, "h5", q, parse, slots)
    if cfg == "inst":
        return instant(env, q), {"path": "instant"}
    if cfg == "route":
        r = env.router_shape.route(q["query"])
        if r["path"] == "instant":
            return instant(env, q), {"route": r}
        order, info = C7.search_one(env, "h0", q, parse, None)
        return order, {**info, "route": r}
    raise ValueError(cfg)


# ---------------- prefetch / timing ----------------
def prefetch(reps):
    qs, _ = queries()
    QV = G.QueryVecs3L()
    allstr = []
    for rep in reps:
        allstr += strings(qs, rewrites("qr-v1", rep), rewrites("qs-v1", rep))
    miss = sorted({s for s in allstr if s not in QV.vec})
    n0 = len(L.ledger())
    t = time.time()
    QV.get(allstr)
    wall = time.time() - t
    cost = sum(r["cost_usd"] for r in L.ledger()[n0:])
    print(f"prefetch: {len(set(allstr))} distinct strings, {len(miss)} embedded in {wall:.1f} s "
          f"({len(miss) / max(wall, 1e-9):.1f} items/s), ${cost:.5f}", flush=True)


def _timed_embed(texts):
    n0 = len(L.ledger())
    for att in range(6):
        try:
            t = time.time()
            ai.openai_embed(texts, model=G.EMB3L_MODEL, dimensions=G.EMB3L_DIM, purpose="c81_query_embed_timing")
            sec = time.time() - t
            return {"seconds": round(sec, 3), "cost_usd": L.ledger()[n0:][-1]["cost_usd"], "attempts": att + 1}
        except Exception as e:  # noqa: BLE001 - transient network errors: retry, keep only the successful call's time
            if "budget stop" in str(e) or att == 5:
                raise
            time.sleep(2 * (att + 1))


def timing(reps):
    """One live 3-large call per typed search: rewrite-path strings per repeat, the raw query once (instant)."""
    qs, _ = queries()
    typed = [q for q in qs if not q["examples"]]
    os.makedirs(WORK, exist_ok=True)
    t0 = time.time()
    n = 0
    p = os.path.join(WORK, "embed_timing_inst.json")
    if not os.path.exists(p):
        out = {q["id"]: _timed_embed([q["query"]]) for q in typed}
        n += len(out)
        H.jdump(out, p)
    for rep in reps:
        p = os.path.join(WORK, f"embed_timing_h0_r{rep}.json")
        if os.path.exists(p):
            continue
        P = rewrites("qr-v1", rep)
        out = {}
        for q in typed:
            pr = P[q["id"]]
            out[q["id"]] = _timed_embed([q["query"]] + pr["phrases"] + (pr.get("hypothetical_captions") or []))
        n += len(out)
        H.jdump(out, p)
    wall = time.time() - t0
    print(f"timing: {n} live calls in {wall:.1f} s ({n / max(wall, 1e-9):.2f} items/s)", flush=True)


# ---------------- runs ----------------
def run_config(env, cfg, reps, outdir):
    qs, split_of = queries()
    S = env.S
    plat = {c: it["platform"] for it, c in zip(S.items, S.codes)}
    def load_t(name):
        p = os.path.join(WORK, name)
        return json.load(open(p)) if os.path.exists(p) else None  # None only in tmp/ determinism checks

    t_inst = load_t("embed_timing_inst.json")
    zero = {"seconds": 0.0, "cost_usd": 0.0}
    written = []
    run_reps = [1] if cfg == "inst" else reps
    for rep in run_reps:
        Pqr = rewrites("qr-v1", rep)
        Pqs = rewrites("qs-v1", rep) if cfg in USES_QS else None
        need = strings(qs, Pqr, Pqs) if cfg != "inst" else [q["query"] for q in qs if not q["examples"]]
        miss = [s for s in need if s not in S.QV.vec]
        assert not miss, f"{len(miss)} query strings not prefetched (run `prefetch` first)"
        t_h0 = load_t(f"embed_timing_h0_r{rep}.json")
        timing_ok = t_inst is not None and t_h0 is not None
        for q in [x for x in qs if not x["examples"]][:5]:  # warm-up (not timed, not written)
            search_one(env, cfg, q, Pqr[q["id"]], Pqs[q["id"]] if Pqs else None)
        out, per = {}, {}
        by = collections.defaultdict(lambda: collections.defaultdict(list))
        agg = collections.Counter()
        t_run = time.time()
        for q in qs:
            sp = split_of[q["id"]]
            parse = None if q["examples"] else Pqr[q["id"]]
            slots = Pqs[q["id"]] if (Pqs and not q["examples"]) else None
            t = time.time()
            order, info = search_one(env, cfg, q, parse, slots)
            local = time.time() - t
            out[q["id"]] = order
            if q["examples"]:
                by[sp]["local_mlt"].append(local)
                continue
            path = "instant" if cfg == "inst" or (info.get("route") or {}).get("path") == "instant" else "rewrite"
            rq = Pqr["_meta"]["per_query"][q["id"]]
            rs = Pqs["_meta"]["per_query"][q["id"]] if Pqs else None
            if path == "instant":
                e = t_inst[q["id"]] if t_inst else zero
                rw_s, rw_c = 0.0, 0.0
            else:
                e = t_h0[q["id"]] if t_h0 else zero
                rw_s = max(rq["seconds"], rs["seconds"] if rs else 0.0)
                rw_c = rq["cost_usd"] + (rs["cost_usd"] if rs else 0.0)
            d = by[sp]
            d["local"].append(local)
            d["total"].append(local + rw_s + e["seconds"])
            d["embed_s"].append(e["seconds"])
            d["cost"].append(rw_c + e["cost_usd"])
            d["cost_rw"].append(rw_c)
            d["cost_emb"].append(e["cost_usd"])
            if path == "rewrite":
                d["rewrite_s"].append(rw_s)
                d["local_rewrite_path"].append(local)
                d["total_rewrite_path"].append(local + rw_s + e["seconds"])
            else:
                d["local_instant_path"].append(local)
                d["total_instant_path"].append(local + e["seconds"])
            d["routed"].append(path == "instant")
            agg[f"{sp}:{path}"] += 1
            if cfg in USES_QS:
                agg[f"{sp}:creator_fired"] += "creator" in info
                agg[f"{sp}:router_creator"] += bool(info.get("router") and info["router"]["type"] == "creator")
                agg[f"{sp}:facet_active"] += bool(info.get("facets"))
                agg[f"{sp}:time_soft"] += bool((info.get("time") or {}).get("direction"))
                agg[f"{sp}:intent_active"] += (info.get("intent") or {}).get("mode", "unchanged") != "unchanged"
            per[q["id"]] = {**info, "path": path, "latency_local_s": round(local, 4),
                            "latency_total_s": round(d["total"][-1], 3)}
        wall = time.time() - t_run
        splits = {}
        allv = collections.defaultdict(list)
        for sp in RUN_SPLITS:
            d = by[sp]
            for k, v in d.items():
                allv[k] += v
        for sp, d in list(by.items()) + [("all_typed", allv)]:
            n = len(d["local"])
            splits[sp] = {"n_typed": n, "n_mlt": len(d["local_mlt"]),
                          "routed_instant": int(sum(d["routed"])), "routed_share": round(float(np.mean(d["routed"])), 4)
                          if n else None,
                          "local_p50_s": pct(d["local"], 50), "local_p95_s": pct(d["local"], 95),
                          "total_p50_s": pct(d["total"], 50), "total_p95_s": pct(d["total"], 95),
                          "rewrite_p50_s": pct(d["rewrite_s"], 50), "rewrite_p95_s": pct(d["rewrite_s"], 95),
                          "embed_call_p50_s": pct(d["embed_s"], 50), "embed_call_p95_s": pct(d["embed_s"], 95),
                          "total_instant_path_p50_s": pct(d["total_instant_path"], 50),
                          "total_instant_path_p95_s": pct(d["total_instant_path"], 95),
                          "total_rewrite_path_p50_s": pct(d["total_rewrite_path"], 50),
                          "total_rewrite_path_p95_s": pct(d["total_rewrite_path"], 95),
                          "cost_per_1k_searches_usd": round(1000 * float(np.mean(d["cost"])), 4) if n else None,
                          "cost_per_1k_rewrite_usd": round(1000 * float(np.mean(d["cost_rw"])), 4) if n else None,
                          "cost_per_1k_embed_usd": round(1000 * float(np.mean(d["cost_emb"])), 4) if n else None}
        meta = {"config": cfg, "round": "8.1", "repeat": rep if cfg != "inst" else "single (deterministic)",
                "splits": RUN_SPLITS, "n_searches": len(qs), "file_layout": "one file per repeat, all four splits",
                "base": "H0r8 (runs/r8_base/h0r8_r{k} on dev + yt_holdout)",
                "rewrites": None if cfg == "inst" else {"qr-v1": Pqr["_meta"]["sources"],
                                                         "qs-v1": Pqs["_meta"]["sources"] if Pqs else None},
                "embedding": f"{G.EMB3L_MODEL}@{G.EMB3L_DIM}", "hyde_alpha": None if cfg == "inst" else L.HYDE_ALPHA,
                "route_version": R.ROUTE_VERSION if cfg == "route" else None,
                "creators": {"h5": "c7_lib.Creators7 (hash-order dependent)",
                             "h5d": "c81_lib.Creators7d (deterministic)"}.get(cfg),
                "counts": dict(agg), "per_split": splits,
                "index_build_s": round(env.build_s, 1), "h0_index_build_s": round(env.h0_build_s, 1),
                "route_index_build_s": round(env.route_build_s, 1), "creator_build_s": env.creator_build_s,
                "run_wall_s": round(wall, 1), "searches_per_s": round(len(qs) / max(wall, 1e-9), 2),
                "pythonhashseed": os.environ.get("PYTHONHASHSEED"), "embed_timing_available": timing_ok,
                "latency_model": "local search (warm) + rewrite call's original uncached seconds where used "
                                 "(h5d: max(qr-v1, qs-v1), parallel) + one live 3-large query-embedding call "
                                 "(rewrite path: query + phrases + HyDE captions; instant path: raw query)",
                "cost_note": "ledger list prices; per 1k typed searches; rewrite cost at the original call's cost",
                "per_search": per}
        ref = os.path.join(DATA, "runs", "r8_base", f"h0r8_r{1 if cfg == 'inst' else rep}.json")
        meta["diagnostics_vs_h0r8_dev_yth"] = C7.top10_diag({k: v for k, v in out.items()
                                                             if split_of[k] in ("dev", "yt_holdout")},
                                                            json.load(open(ref)), plat)
        path = write_run(os.path.join(outdir, f"{cfg}_r{rep}.json"), f"c81:{cfg}", L.CodeIds(meta["embedding"]),
                         out, meta)
        written.append(path)
        sa = splits["all_typed"]
        print(f"wrote {os.path.relpath(path, DATA)}: {len(qs)} searches in {wall:.1f} s "
              f"({len(qs) / max(wall, 1e-9):.1f}/s); local p50 {sa['local_p50_s']} / p95 {sa['local_p95_s']} s; "
              f"routed {json.dumps({s: splits[s]['routed_share'] for s in RUN_SPLITS if s in splits})}; "
              f"{json.dumps(meta['diagnostics_vs_h0r8_dev_yth'])}", flush=True)
        if cfg == "h0r8":
            base = json.load(open(ref))["queries"]
            same = sum(out[k] == base[k][:1000] for k in base)
            print(f"h0r8 r{rep}: {same} of {len(base)} dev + yt_holdout rankings identical to r8_base (1,000 deep)",
                  flush=True)
    if cfg == "inst":
        for rep in reps:
            if rep != 1:
                dst = os.path.join(outdir, f"inst_r{rep}.json")
                shutil.copyfile(written[0], dst)
                written.append(dst)
    return written


def compare(a, b, cfgs, reps):
    for cfg in cfgs:
        for rep in reps:
            pa, pb = os.path.join(a, f"{cfg}_r{rep}.json"), os.path.join(b, f"{cfg}_r{rep}.json")
            if not (os.path.exists(pa) and os.path.exists(pb)):
                continue
            x, y = json.load(open(pa))["queries"], json.load(open(pb))["queries"]
            same = sum(x[k] == y.get(k) for k in x)
            top10 = sum(x[k][:10] == y.get(k, [])[:10] for k in x)
            print(f"{cfg} r{rep}: {same} of {len(x)} rankings identical (1,000 deep), {top10} top-10s identical",
                  flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prefetch", "timing", "run", "compare"])
    ap.add_argument("--configs", default="h0r8,h5d,inst,route")
    ap.add_argument("--reps", default="1,2,3")
    ap.add_argument("--outdir", default=OUT)
    ap.add_argument("--splits", default=",".join(SPLITS))
    ap.add_argument("--a")
    ap.add_argument("--b")
    a = ap.parse_args()
    RUN_SPLITS[:] = a.splits.split(",")
    reps = [int(x) for x in a.reps.split(",")]
    cfgs = a.configs.split(",")
    if a.cmd == "prefetch":
        return prefetch(reps)
    if a.cmd == "timing":
        return timing(reps)
    if a.cmd == "compare":
        return compare(a.a, a.b, cfgs, reps)
    t0 = time.time()
    env = Env(need_h5=bool(set(cfgs) & USES_QS))
    print(f"index built in {env.build_s:.1f} s (H0 {env.h0_build_s:.1f} s; route {env.route_build_s:.1f} s; "
          f"creators {json.dumps(env.creator_build_s)})", flush=True)
    for cfg in cfgs:
        assert cfg in CONFIGS, cfg
        run_config(env, cfg, reps, a.outdir)
    print(f"total wall {time.time() - t0:.1f} s", flush=True)


if __name__ == "__main__":
    main()
