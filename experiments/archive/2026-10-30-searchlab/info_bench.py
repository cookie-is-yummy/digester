"""PROTOTYPE ONLY - information-sufficiency benchmark.

Question: can a cheap per-item score predict which items search can't find from their text alone,
so enrichment (thumbnail -> audio -> keyframes -> video) is spent only where text is insufficient?

Ground truth: each relevant (item, query) pair from the eval set is 'found' if the item ranks in the
top K for its query under the best caption-only setup (rewrite + bge dense + keywords, RRF, + PRF).
Scores are query-independent properties of the item text.

usage: venv/bin/python -I searchlab/info_bench.py <ids.json> <emb.npy> --eval <evalset>
"""
import collections
import json
import os
import re
import sys

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import cross_val_predict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lab import Corpus, load_eval, rank, rrf  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prototype"))
from common import STOP, strip_tags  # noqa: E402

a = sys.argv[1:]
K = 50
C = Corpus(a[0], a[1])
Q = load_eval(C, a[a.index("--eval") + 1])
P = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "query_parses.json")))
ok = C.info == "ok"
N = len(C.ids)

# ---------- per-item information features (query independent) ----------
cv, W = C.bm25_index("full")
vocab_idf = None
docs_tf = cv.transform([C.text(n, "cap_tags").lower() for n in range(N)])
df = np.asarray((docs_tf > 0).sum(axis=0)).ravel()
idf = np.log((N + 1) / (df + 1))
caption_only = cv.transform([strip_tags(C.items[k].get("caption") or "").lower() for k in C.ids])
caption_only.data[:] = 1
idf_info = np.asarray(caption_only @ idf).ravel()  # sum of IDF over distinct caption terms (no tags)
words = []
for k in C.ids:
    toks = re.findall(r"[a-z]{3,}", strip_tags(C.items[k].get("caption") or "").lower())
    words.append(len({t for t in toks if t not in STOP}))
words = np.array(words)
tags = np.array([len([t for t in (C.items[k]["platform_data"].get("hashtags") or []) if t.lower() not in STOP])
                 for k in C.ids])
mean = C.V.mean(0)
mean /= np.linalg.norm(mean)
specific = 1 - C.V @ mean  # far from the 'average caption' = more specific
# hubness: how often an item lands in the top 20 for random other items' vectors (generic items are hubs)
rng = np.random.default_rng(0)
probe = C.V[rng.choice(N, 400, replace=False)]
hub = np.zeros(N)
for row in probe @ C.V.T:
    hub[np.argpartition(-row, 20)[:20]] += 1
F = {"gate_ok": ok.astype(float), "content_words": np.log1p(words), "idf_info": np.log1p(idf_info),
     "topical_tags": np.log1p(tags), "specificity": specific, "neg_hubness": -hub}

# ---------- ground truth from retrieval ----------
def prf_dense(phrases, mask):
    Qv = C.qvecs(phrases)
    s = (C.V @ Qv.T).max(axis=1)
    top = np.argsort(-np.where(mask, s, -9))[:5]
    q2 = Qv.mean(0) + C.V[top].mean(0)
    q2 /= np.linalg.norm(q2)
    return np.maximum(s, C.V @ q2)

pairs = []  # (row, found)
for q in Q:
    if q["examples"]:
        continue
    p = P[q["id"]]
    m = q["mask"]
    d = rank(prf_dense([q["query"]] + p["phrases"], m & ok), m & ok)
    b = rank(C.bm25(" ".join([q["query"]] + p["keywords"]), "full"), m)
    pos = {n: i for i, n in enumerate(rrf(d, b))}
    for n in q["rel_rows"]:
        pairs.append((n, pos.get(n, 10 ** 9) < K))
rows = np.array([r for r, _ in pairs])
y = np.array([f for _, f in pairs]).astype(int)
print(f"relevant pairs {len(y)} | found in top {K}: {y.mean():.0%}")

print("\nsingle-feature AUC for predicting 'found' (0.5 = useless):")
for name, f in F.items():
    print(f"  {name:14s} {roc_auc_score(y, f[rows]):.3f}")
X = np.column_stack([F[k] for k in F])
Xs = (X - X.mean(0)) / (X.std(0) + 1e-9)
clf = LogisticRegression(max_iter=2000, class_weight="balanced")
pred = cross_val_predict(clf, Xs[rows], y, cv=5, method="predict_proba")[:, 1]
print(f"  {'combined (5-fold CV)':14s} {roc_auc_score(y, pred):.3f}")
clf.fit(Xs[rows], y)
score = clf.predict_proba(Xs)[:, 1]  # information score for every item
print("  weights:", {k: round(float(w), 2) for k, w in zip(F, clf.coef_[0])})

# ---------- cascade simulation ----------
print("\nenrich items whose information score is below a threshold:")
print(f"  {'enrich share of corpus':>24s} {'share of missed answers targeted':>34s} {'share of found answers enriched':>32s}")
miss_rows, found_rows = rows[y == 0], rows[y == 1]
for frac in (0.1, 0.2, 0.3, 0.4, 0.5):
    t = np.quantile(score, frac)
    print(f"  {frac:24.0%} {np.mean(score[miss_rows] < t):34.0%} {np.mean(score[found_rows] < t):32.0%}")
np.save(os.path.join(os.path.dirname(os.path.abspath(__file__)), "info_score.npy"), score)
