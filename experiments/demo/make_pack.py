"""PROTOTYPE ONLY - build Derrick's preloaded library pack for the search demo from the research data root.

  python experiments/demo/make_pack.py --src data/all --out <dir> [--name derrick] [--zip]

Writes <out>/<name>/ in the demo library layout (library.py) with only what Q8 reads:
  - items and interactions, friends' posts (owner_relation mutual / friend) and their interactions removed;
  - Instagram te-v1c rows (content fields only), their texts and 3-small vectors (float16 rows copied as stored);
  - YouTube te summaries only (the refine's candidate lines show them; Q8 ranks no YouTube te, so no texts/vectors);
  - 3-large item vectors as per-dimension int8 (q8-v1): round 8's QMat computed over the full research index (so
    every kept row and the scales are bit-identical to round 8's), then the friends' rows dropped; plus the id order;
  - r7/router.npz (the platform head prior-p1 reads; weights over query vectors only).
Never copied: evals/, eval_work/, runs/, caches, the ledger, yt_ref / ref (research-only), 3-small item vectors,
query-vector stores, synthetic search sets. Nothing is printed but counts and sizes.
--keep-friends is for the parity check only (a library comparable with the round-8 index); never ship it.
"""
import argparse
import json
import os
import shutil
import sys
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import library as LIB  # noqa: E402

INTER_KEYS = {"item_id", "kind", "at", "capture_method", "weight", "collection_name", "sent_by_owner_account"}
TE_KEYS = ["code", "ok", "summary", "kind", "topics", "shown", "said", "place", "people", "vibe", "use", "queries",
           "prompt_version", "model"]
TE_YT_KEYS = ["code", "ok", "summary", "kind", "topics", "vibe", "prompt_version", "model"]


def jl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def wl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def code_of(it):
    return it["dedup_key"].split(":", 1)[1]


def q8_rows(src, items):
    """Round 8's int8 store over the research index: c6_lib.swap_to_3l's S.V (3-large rows of the items, float16
    store read as normalised float32) through c85_lib.QMat. Returns (ids in store order, QMat)."""
    import numpy as np
    from sklearn.preprocessing import normalize

    import engine as EN
    EN.configure(src)
    d = os.path.join(src, "corpus", "emb", "oai3l_1024")
    ids = json.load(open(os.path.join(d, "ids.json")))
    small = json.load(open(os.path.join(src, "corpus", "emb", "oai512", "ids.json")))
    assert ids == small, "3-large store must have oai512's ids in oai512's order"
    pos = {it["id"] for it in items}
    keep = [k for k, i in enumerate(ids) if i in pos]
    V = normalize(np.load(os.path.join(d, "emb.npy")).astype(np.float32))[keep]
    return [ids[k] for k in keep], EN.M["X"].QMat(V)


def build(src, out_root, name="derrick", keep_friends=False):
    import numpy as np
    t0 = time.time()
    out = os.path.join(out_root, name)
    if os.path.exists(out):
        shutil.rmtree(out)
    items = jl(os.path.join(src, "corpus", "items.jsonl"))
    friends = set() if keep_friends else {it["id"] for it in items if LIB.is_friend(it)}
    kept = [it for it in items if it["id"] not in friends]
    kept_ids = {it["id"] for it in kept}
    kept_codes = {code_of(it) for it in kept}
    wl(os.path.join(out, "corpus", "items.jsonl"), kept)
    inter = [{k: v for k, v in r.items() if k in INTER_KEYS}
             for r in jl(os.path.join(src, "corpus", "interactions.jsonl")) if r["item_id"] in kept_ids]
    wl(os.path.join(out, "corpus", "interactions.jsonl"), inter)

    ids, Qm = q8_rows(src, items)
    rows = [r for r, i in enumerate(ids) if i not in friends]
    import engine as EN
    EN.save_q8_store(out, [ids[r] for r in rows], Qm.q[rows], Qm.s)

    te_rows = [{k: r[k] for k in TE_KEYS if k in r}
               for r in jl(os.path.join(src, "enrich", f"{LIB.TE_IG}.jsonl")) if r["code"] in kept_codes]
    wl(os.path.join(out, "enrich", f"{LIB.TE_IG}.jsonl"), te_rows)
    texts = json.load(open(os.path.join(src, "enrich", f"text_{LIB.TE_IG}.json"), encoding="utf-8"))
    with open(os.path.join(out, "enrich", f"text_{LIB.TE_IG}.json"), "w", encoding="utf-8") as f:
        json.dump({c: t for c, t in texts.items() if c in kept_codes}, f, ensure_ascii=False)
    sd = os.path.join(src, "corpus", "emb", f"emb_{LIB.TE_IG}")
    te_ids = json.load(open(os.path.join(sd, "ids.json")))
    te_V = np.load(os.path.join(sd, "emb.npy"))  # float16 as stored; load_store normalises it on read
    keep_te = [k for k, c in enumerate(te_ids) if c in kept_codes]
    dd = os.path.join(out, "corpus", "emb", f"emb_{LIB.TE_IG}")
    os.makedirs(dd, exist_ok=True)
    json.dump([te_ids[k] for k in keep_te], open(os.path.join(dd, "ids.json"), "w"))
    np.save(os.path.join(dd, "emb.npy"), te_V[keep_te])

    yt = [{k: r[k] for k in TE_YT_KEYS if k in r}
          for r in jl(os.path.join(src, "yt_enrich", f"{LIB.TE_YT}.jsonl")) if r["code"] in kept_codes]
    wl(os.path.join(out, "yt_enrich", f"{LIB.TE_YT}.jsonl"), yt)
    with open(os.path.join(out, "yt_enrich", f"text_{LIB.TE_YT}.json"), "w") as f:
        f.write("{}")
    os.makedirs(os.path.join(out, "r7"), exist_ok=True)
    shutil.copyfile(os.path.join(src, "r7", "router.npz"), os.path.join(out, "r7", "router.npz"))

    plat = [it["platform"] for it in kept]
    counts = {"items": len(kept), "instagram": plat.count("instagram"), "youtube": plat.count("youtube"),
              "interactions": len(inter), "item_vectors": len(rows), "te_ig_rows": len(te_rows),
              "te_ig_vectors": len(keep_te), "te_yt_summaries": len(yt)}
    man = {"name": "Derrick (preloaded)" if not keep_friends else f"{name} (parity only, not for sharing)",
           "source": "preloaded pack built from the round-8 research library",
           "built": time.strftime("%Y-%m-%dT%H:%M:%S"), "counts": counts,
           "friends_removed": len(friends), "friends_kept": keep_friends,
           "processor_version": "q8-v1", "embedding_model": "text-embedding-3-large@1024, per-dimension int8",
           "te": {"prompt_version": "te-v1c", "model": "gemini-3.1-flash-lite", "platforms": ["instagram"]},
           "excludes": ["evals", "eval_work", "runs", "caches", "ledger", "yt_ref/ref", "query vectors"]}
    LIB.write_json(os.path.join(out, "library.json"), man)
    size = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(out) for f in fs)
    print(json.dumps({"out": out, "counts": counts, "friends_removed": len(friends), "bytes": size,
                      "mb": round(size / 1e6, 1), "wall_s": round(time.time() - t0, 1)}), flush=True)
    return out, size


def zip_dir(d, path):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for root, _, files in os.walk(d):
            for f in sorted(files):
                full = os.path.join(root, f)
                z.write(full, os.path.relpath(full, os.path.dirname(d)))
    return os.path.getsize(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(REPO, "data", "all"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="derrick")
    ap.add_argument("--zip", action="store_true", help="also write <out>/<name>.zip")
    ap.add_argument("--keep-friends", action="store_true", help="parity check only; never share this output")
    a = ap.parse_args()
    out, _ = build(os.path.abspath(a.src), os.path.abspath(a.out), a.name, a.keep_friends)
    if a.zip:
        zp = os.path.join(os.path.abspath(a.out), a.name + ".zip")
        print(json.dumps({"zip": zp, "mb": round(zip_dir(out, zp) / 1e6, 1)}), flush=True)


if __name__ == "__main__":
    main()
