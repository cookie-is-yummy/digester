"""PROTOTYPE ONLY - parity check: the demo engine against the round-8 runner, top 10 (and 1,000 deep) per search.

The frozen round-8 run files (runs/r8.5/q8_r*, runs/r8.8/fm_r*) and refine caches are not in this data root, so
the round-8 side is recomputed with the round-8 runner's own code, unchanged:
  runner  (process 1, research root data/all): c88_search.Env() (float 3-large store quantised by c85_lib.QMat) and
          c88_search.search_one for q8 / fm; (process 2) c81_search.Env + search_one "h0r8" (float vectors) for H0.
  demo    (process 3, a library built by make_pack.py): engine.Engine, i.e. the int8 store read from disk through
          Combined(vectors=...) / c88_search.Env(S=...), routing first, the refine proxy, the display filter.
Inputs are cached only: qr-v1 gpt-5-nano repeat 1 (runs/rewrites/qr-v1_gpt-5-nano_r1.json), query vectors from
corpus/emb/oai3l_1024_queries and c4_queries (read-only). No refine response is cached for these searches, so for
every gated search both sides get the same synthetic rf-v1 response (the sent candidates reversed) injected into
their refine cache: that exercises the refine's reorder path identically and makes no call.
Searches: typed dev searches (evals/queries.jsonl + split.json; never evals/labels/ or eval_work/) whose strings are
all cached; picks 5 (2 instant, 1 rewrite unrefined, 2 rewrite refined), --all reports every eligible one too.
The parity library keeps friends' posts (as the round-8 index did); --pack also scores the shipped pack (friends
removed, so small differences are expected) and checks its int8 rows equal round 8's QMat rows. Counts only.

usage: python experiments/demo/parity.py --lib <parity library> [--pack <pack library>] [--all]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DATA = os.path.join(REPO, "data", "all")
sys.path.insert(0, HERE)
CFG_MODEL = {"q8": "gpt-5-nano", "fm": "gpt-5-mini"}


def synthetic(K, cfg, rep, qid, send):
    ids = [f"c{i + 1:02d}" for i in range(len(send))][::-1]
    key = K.cache_key(CFG_MODEL[cfg], rep, qid, send)
    return key, {"key": key, "rep": rep, "qid": qid, "n_sent": len(send), "ok": True, "ids": ids, "tries": 1,
                 "seconds": 0.0, "cost_usd": 0.0, "in_tokens": 0, "out_tokens": 0, "synthetic": True}


def dev_queries(data):
    with open(os.path.join(data, "evals", "split.json")) as f:
        dev = set(json.load(f)["dev"])
    with open(os.path.join(data, "evals", "queries.jsonl")) as f:
        qs = [json.loads(line) for line in f if line.strip()]
    return sorted((q for q in qs if q["id"] in dev and not q["examples"]), key=lambda q: q["id"])


def side_runner(out):
    import engine as EN
    EN.configure(DATA)
    import c4_lib as L
    import c88_lib as K
    import c88_search as S88
    env = S88.Env()
    parses = L.load_parses("qr-v1", 1)
    eligible, shape = [], {}
    for q in dev_queries(DATA):
        if q["id"] not in parses:
            continue
        path = env.router_shape.route(q["query"])["path"]
        texts, caps, _ = S88.plan(q, parses[q["id"]], path)
        if any(s not in env.S.QV.vec for s in [q["query"]] + texts + caps) or env.te.missing(texts + caps):
            continue
        _, g = S88.search_one(env, "q8", q, parses[q["id"]], 1, stop_before_refine=True)
        shape[q["id"]] = "refined" if g["gate"] else path
        eligible.append(q)
    want = {"instant": 2, "rewrite": 1, "refined": 2}
    picks = []
    for k, n in want.items():
        picks += [q["id"] for q in eligible if shape[q["id"]] == k][:n]
    res = {"picks": picks, "eligible": [q["id"] for q in eligible], "shape": shape, "orders": {}, "synthetic": {}}
    for q in eligible:
        for cfg in ("q8", "fm"):
            rf = env.refiners[CFG_MODEL[cfg]]
            order0, g = S88.search_one(env, cfg, q, parses[q["id"]], 1, stop_before_refine=True)
            if g["gate"]:
                key, r = synthetic(K, cfg, 1, q["id"], rf.split_top(order0)[2])
                rf.cache[key] = r
                res["synthetic"][key] = r
            order, _ = S88.search_one(env, cfg, q, parses[q["id"]], 1)
            res["orders"][f"{cfg}:{q['id']}"] = order[:1000]
            res["orders"][f"pre:{cfg}:{q['id']}"] = order0[:1000]
    json.dump(res, open(out, "w"))


def side_runner_h0(ref, out):
    import engine as EN
    EN.configure(DATA)
    import c4_lib as L
    import c81_search as S81
    env = S81.Env(need_h5=False)
    parses = L.load_parses("qr-v1", 1)
    qs = {q["id"]: q for q in dev_queries(DATA)}
    res = json.load(open(ref))
    for qid in res["eligible"]:
        order, _ = S81.search_one(env, "h0r8", qs[qid], parses[qid], None)
        res["orders"][f"h0:{qid}"] = order[:1000]
    json.dump(res, open(out, "w"))


def side_demo(lib, ref, out, pack=False):
    """pack=True: the shipped pack has no friends' posts, so the runner's list is compared with friends removed,
    and before the refine (the synthetic response is keyed on the runner's candidates, which include friends)."""
    import engine as EN
    eng = EN.Engine(lib)
    L = EN.M["L"]
    for store, name in ((eng.env.S.QV, "oai3l_1024_queries"), (eng.env.te.QVs, "c4_queries")):
        ids, V = L.load_store(os.path.join(DATA, "corpus", "emb", name))  # read-only, never saved here
        store.vec.update({s: V[k] for k, s in enumerate(ids)})
    res = json.load(open(ref))
    for rf in eng.env.refiners.values():  # the pack is compared before the refine, so it gets no responses
        for key, r in ({} if pack else res["synthetic"]).items():
            rf._rf.cache[key] = r
    with open(os.path.join(DATA, "runs", "rewrites", "qr-v1_gpt-5-nano_r1.json")) as f:
        parses = json.load(f)
    qs = {q["id"]: q for q in dev_queries(DATA)}
    friends = set()
    if pack:
        import library as LIB
        friends = {it["dedup_key"].split(":", 1)[1] for it in L.jl(os.path.join(DATA, "corpus", "items.jsonl"))
                   if LIB.is_friend(it)}
    rep = {}
    groups = {"picked": res["picks"], "all_eligible": res["eligible"]}
    for gname, ids in groups.items():
        for p in ("q8", "fm", "h0"):
            n10 = deep = 0
            ov = []
            for qid in ids:
                par = {"qid": qid, "rep": 1, "parse": parses[qid], "filters": qs[qid].get("filters")}
                r = eng.search(qs[qid]["query"], [p], parity=par)[p]
                mine = r["order"]
                if pack:
                    theirs = res["orders"].get(f"pre:{p}:{qid}") or res["orders"][f"{p}:{qid}"]
                    theirs = [c for c in theirs if c not in friends]
                    mine = mine[:len(theirs)]
                else:
                    theirs = res["orders"][f"{p}:{qid}"]
                n10 += mine[:10] == theirs[:10]
                deep += mine == theirs
                ov.append(len(set(mine[:10]) & set(theirs[:10])) / 10)
            rep.setdefault(gname, {})[p] = {"n": len(ids), "top10_identical": n10, "1000_deep_identical": deep,
                                            "mean_top10_overlap": round(sum(ov) / max(len(ov), 1), 4)}
    rep["shapes_picked"] = [res["shape"][q] for q in res["picks"]]
    rep["refined_searches_with_synthetic_response"] = len(res["synthetic"])
    json.dump(rep, open(out, "w"))


def pack_int8(pack, out):
    """The pack's int8 rows and scales against c88_search.Env's QMat on the research root, for every kept item."""
    import numpy as np

    import engine as EN
    EN.configure(DATA)
    import c88_search as S88
    env = S88.Env()
    S = env.S
    ids, q, s = EN.load_q8_store(pack)
    row = {S.items[n]["id"]: k for k, n in enumerate(S.vpos)}
    rows = [row[i] for i in ids]
    json.dump({"items": len(ids), "scales_equal": bool(np.array_equal(s, S.V.s)),
               "rows_equal": bool(np.array_equal(q, S.V.q[rows]))}, open(out, "w"))


def run(args):
    r = subprocess.run([sys.executable, os.path.abspath(__file__), *args], stdout=subprocess.DEVNULL)
    if r.returncode:
        raise SystemExit(f"parity step failed: {args[0]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib")
    ap.add_argument("--pack")
    ap.add_argument("--side", choices=["runner", "runner_h0", "demo", "pack_int8"])
    ap.add_argument("--ref")
    ap.add_argument("--out")
    ap.add_argument("--friendless", action="store_true")
    a = ap.parse_args()
    if a.side == "runner":
        return side_runner(a.out)
    if a.side == "runner_h0":
        return side_runner_h0(a.ref, a.out)
    if a.side == "demo":
        return side_demo(a.lib, a.ref, a.out, pack=a.friendless)
    if a.side == "pack_int8":
        return pack_int8(a.pack, a.out)
    tmp = tempfile.mkdtemp(prefix="parity_")
    f = {k: os.path.join(tmp, k + ".json") for k in ("r", "r2", "demo", "pack", "int8")}
    run(["--side", "runner", "--out", f["r"]])
    run(["--side", "runner_h0", "--ref", f["r"], "--out", f["r2"]])
    run(["--side", "demo", "--lib", a.lib, "--ref", f["r2"], "--out", f["demo"]])
    report = {"parity_library_vs_round8_runner": json.load(open(f["demo"]))}
    if a.pack:
        run(["--side", "demo", "--lib", a.pack, "--ref", f["r2"], "--out", f["pack"], "--friendless"])
        run(["--side", "pack_int8", "--pack", a.pack, "--out", f["int8"]])
        report["shipped_pack_vs_round8_runner"] = json.load(open(f["pack"]))
        report["shipped_pack_int8_vs_round8_qmat"] = json.load(open(f["int8"]))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
