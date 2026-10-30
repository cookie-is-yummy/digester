"""PROTOTYPE ONLY - EVALUATOR SIDE. The MU ceiling: the baseline search with Muse's video descriptions (MU)
appended to each item's search text.

THIS IS AN INFLATED CEILING, NEVER A METHOD. The eval answers were found by Muse matching words in this
same MU text, and ~95% of the labelled answers are items that have MU text while only ~5% of the corpus does.
It bounds what a perfect description pass could add per search kind; nothing here may be adopted, and MU must
never feed a method or the query rewrite (experiments/BRIEF.md, "The Muse export").

Reproduces experiments/methods/baseline.py (variant hybrid_prf, bge_full) exactly, then:
  base      no MU (sanity check: must equal data/runs/baseline.json)
  bm25      MU appended to the BM25 'full' text view only (dense unchanged)
  both      MU appended to BM25 and to the dense text: items with MU are re-embedded with bge-small
            ('full' view + MU, truncated) and treated as info-ok
  presence  diagnostic only: the baseline ranking with every item that has MU moved ahead of those without
            (order otherwise kept). Measures how much the label set leaks through MU *presence* alone.
Items in the corpus with no vector (no caption) that have MU get rows, so they become rankable.

--mu full|desc: append the whole MU record (description + Searches / Media Pivots / Author & Community /
Cultural/Humor/Temporal sections) or only the free-text description. The dense side always embeds the
description (bge-small reads 512 tokens at most).

usage: python experiments/eval/muse_ceiling.py --variant both --mu full --out data/runs/ceiling_both.json
"""
import argparse
import json
import os
import sys
import time

import numpy as np
from sklearn.preprocessing import normalize

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
from corpus import DATA, Corpus, code_of, fix_ws, load_queries, rank, rrf, write_run  # noqa: E402
from muse import load_records, mu_description  # noqa: E402

EMB_DIR = os.path.join(DATA, "eval_work", "emb_mu")
DENSE_MU_CHARS = 1500  # description chars appended to the 'full' view before embedding; the model cuts at 512 tokens


def full_view(it):
    """Same text as experiments/methods/build_embeddings.py."""
    import wordninja
    pd = it["platform_data"]
    tags = pd.get("hashtags") or []
    h = pd.get("owner_handle") or ""
    return fix_ws(" ".join([(it.get("caption") or "")[:600], " ".join("#" + t for t in tags[:15]),
                            f"by @{h} {pd.get('owner_name') or ''}",
                            " ".join(" ".join(wordninja.split(t)) for t in tags[:15]), " ".join(wordninja.split(h))]))


def mu_vectors(C, codes, desc):
    """bge-small vectors of 'full' view + MU description for `codes`; cached in resumable chunks."""
    os.makedirs(os.path.join(EMB_DIR, "chunks"), exist_ok=True)
    codes = sorted(codes)
    idx_path = os.path.join(EMB_DIR, "codes.json")
    if os.path.exists(idx_path) and json.load(open(idx_path)) != codes:
        raise SystemExit(f"{idx_path} holds a different item set; delete {EMB_DIR} to rebuild")
    json.dump(codes, open(idx_path, "w"))
    by_code_item = {code_of(it): it for it in C.items.values()}
    texts = [fix_ws(full_view(by_code_item[c]) + " " + desc[c][:DENSE_MU_CHARS]) for c in codes]
    model, t0, CH, done_now = None, time.time(), 100, 0
    for s in range(0, len(texts), CH):
        p = os.path.join(EMB_DIR, "chunks", f"chunk_{s // CH:03d}.npy")
        if os.path.exists(p):
            continue
        if model is None:
            from fastembed import TextEmbedding
            model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5", threads=os.cpu_count())
        np.save(p, np.array(list(model.embed(texts[s:s + CH])), dtype=np.float32))
        done_now += len(texts[s:s + CH])
        print(f"emb_mu {min(s + CH, len(texts))}/{len(texts)} items, {done_now / (time.time() - t0):.1f} items/s",
              flush=True)
    wall = time.time() - t0
    print(f"emb_mu: {done_now} items embedded now ({len(texts)} total) in {wall:.1f}s"
          + (f", {done_now / wall:.1f} items/s" if done_now else " (all cached)"), flush=True)
    V = np.concatenate([np.load(os.path.join(EMB_DIR, "chunks", f"chunk_{s // CH:03d}.npy"))
                        for s in range(0, len(texts), CH)])
    return dict(zip(codes, normalize(V.astype(np.float32))))


def add_rows(C, codes):
    """Give corpus items that have no vector a row (zero vector, so dense never ranks them unless replaced)."""
    item_by_code = {code_of(it): k for k, it in C.items.items()}
    new = [c for c in sorted(codes) if c not in C.by_code and c in item_by_code]
    if not new:
        return 0
    from common import info_class
    ids = [item_by_code[c] for c in new]
    C.ids = list(C.ids) + ids
    C.V = np.vstack([C.V, np.zeros((len(ids), C.V.shape[1]), np.float32)])
    C.code = list(C.code) + new
    C.by_code = {c: n for n, c in enumerate(C.code)}
    C.first = np.concatenate([C.first, np.array([C.items[k].get("first_seen_at") or "9999" for k in ids])])
    C.kinds = list(C.kinds) + [set(C.items[k]["interaction_kinds"]) for k in ids]
    C.info = np.concatenate([C.info, np.array([info_class(C.items[k]) for k in ids])])
    return len(new)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=["base", "bm25", "both", "presence"], required=True)
    ap.add_argument("--mu", choices=["full", "desc"], default="full")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    t0 = time.time()
    recs = load_records()
    mu_full = {c: r["mu"] for c, r in recs.items() if r["mu"]}
    mu_desc = {c: mu_description(r["mu"]) for c, r in recs.items() if r["mu"]}
    bm25_extra = (mu_full if a.mu == "full" else mu_desc) if a.variant in ("bm25", "both") else None
    C = Corpus("bge_full", extra_text=bm25_extra)
    added = 0
    if a.variant in ("bm25", "both"):
        added = add_rows(C, mu_full)
    if a.variant == "both":
        vecs = mu_vectors(C, [c for c in mu_full if c in C.by_code], mu_desc)
        for c, v in vecs.items():
            n = C.by_code[c]
            C.V[n] = v
            C.info[n] = "ok"
    print(f"rows {len(C.ids)} (+{added} without a caption vector), MU items in corpus "
          f"{sum(1 for c in mu_full if c in C.by_code)}", flush=True)

    P = json.load(open(os.path.join(DATA, "evals", "query_parses.json")))
    ok = C.info == "ok"

    def dense(phrases, m, prf=True):
        Qv = C.qvecs(phrases)
        s = (C.V @ Qv.T).max(axis=1)
        if prf:
            top = np.argsort(-np.where(m, s, -9))[:5]
            q2 = Qv.mean(0) + C.V[top].mean(0)
            q2 /= np.linalg.norm(q2)
            s = np.maximum(s, C.V @ q2)
        return s

    out, lat = {}, []
    has_mu = np.array([c in mu_full for c in C.code])
    for q in load_queries(a.split):
        t = time.time()
        m = C.mask(q["filters"])
        if q["examples"]:
            ex = [C.by_code[c] for c in q["examples"] if c in C.by_code]
            cen = C.V[ex].mean(0)
            cen /= np.linalg.norm(cen)
            d = rank(C.V @ cen, m & ok, ex)
            b = rank(C.bm25(" ".join(C.text(n, "full") for n in ex), "full"), m, ex)
        else:
            p = P[q["id"]]
            phrases = [q["query"]] + p["phrases"]
            d = rank(dense(phrases, m & ok), m & ok)
            b = rank(C.bm25(" ".join([q["query"]] + p["keywords"]), "full"), m)
        r = rrf(d, b)
        if a.variant == "presence":
            r = [n for n in r if has_mu[n]] + [n for n in r if not has_mu[n]]
        out[q["id"]] = r
        lat.append(time.time() - t)
    write_run(a.out, f"muse_ceiling:{a.variant}:{a.mu}", C, out,
              {"wall_s": round(time.time() - t0, 1), "query_p50_s": round(float(np.median(lat)), 3), "cost_usd": 0,
               "note": "EVALUATOR-SIDE INFLATED CEILING; never a method"})
    print(f"wrote {a.out}; {len(out)} queries; wall {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
