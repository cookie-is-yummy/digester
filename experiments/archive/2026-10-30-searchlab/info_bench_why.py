"""PROTOTYPE ONLY - why are relevant items missed? breakdown by item richness and by query kind."""
import collections, json, os, re, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lab import Corpus, load_eval, rank, rrf
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prototype"))
from common import STOP, strip_tags
a = sys.argv[1:]; K = 50
C = Corpus(a[0], a[1]); Q = load_eval(C, a[a.index("--eval") + 1])
P = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "query_parses.json")))
ok = C.info == "ok"
def cw(k):
    t = re.findall(r"[a-z]{3,}", strip_tags(C.items[k].get("caption") or "").lower())
    return len({x for x in t if x not in STOP})
words = np.array([cw(k) for k in C.ids])
def prf(ph, m):
    Qv = C.qvecs(ph); s = (C.V @ Qv.T).max(1)
    top = np.argsort(-np.where(m, s, -9))[:5]
    q2 = Qv.mean(0) + C.V[top].mean(0); q2 /= np.linalg.norm(q2)
    return np.maximum(s, C.V @ q2)
def band(n):
    if not ok[n]: return "1 thin (fails gate)"
    if words[n] < 8: return "2 short (<8 content words)"
    if words[n] < 25: return "3 medium (8-24)"
    return "4 rich (25+)"
tab = collections.defaultdict(lambda: [0, 0]); kind = collections.defaultdict(lambda: [0, 0])
overlap = collections.defaultdict(lambda: [0, 0])
for q in Q:
    if q["examples"]: continue
    p = P[q["id"]]; m = q["mask"]
    d = rank(prf([q["query"]] + p["phrases"], m & ok), m & ok)
    b = rank(C.bm25(" ".join([q["query"]] + p["keywords"]), "full"), m)
    pos = {n: i for i, n in enumerate(rrf(d, b))}
    qw = {w for w in re.findall(r"[a-z]{3,}", " ".join([q["query"]] + p["keywords"]).lower()) if w not in STOP}
    for n in q["rel_rows"]:
        f = pos.get(n, 10**9) < max(K, 2 * len(q["rel_rows"]))
        tab[band(n)][f] += 1; kind[q["kinds"][0] + " / " + q["id"]][f] += 1
        txt = C.text(n, "full").lower()
        has = any(w in txt for w in qw)
        overlap[(band(n)[0] in "34", has)][f] += 1
print(f"{'item richness':30s} {'answers':>8s} {'found@50':>9s}")
for k in sorted(tab):
    m, f = tab[k]; print(f"{k:30s} {m+f:8d} {f/(m+f):9.0%}")
print("\nmedium/rich captions: found rate by whether the caption shares any query word")
for (rich, has), (m, f) in sorted(overlap.items()):
    if rich: print(f"  shares query word={has!s:5s} answers {m+f:4d} found {f/(m+f):.0%}")
print(f"\n{'query':40s} {'answers':>8s} {'found@50':>9s}")
for k in sorted(kind, key=lambda k: sum(kind[k][1:]) / sum(kind[k])):
    m, f = kind[k]; print(f"{k:40s} {m+f:8d} {f/(m+f):9.0%}")
