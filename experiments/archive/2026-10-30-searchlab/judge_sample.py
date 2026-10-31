"""PROTOTYPE ONLY - blind sample of relevant items (found and missed) for an 'aboutness' judgement."""
import json, os, random, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lab import Corpus, load_eval, rank, rrf
a = sys.argv[1:]; K = 50
C = Corpus(a[0], a[1]); Q = load_eval(C, a[a.index("--eval") + 1])
P = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "query_parses.json")))
ok = C.info == "ok"
def prf(ph, m):
    Qv = C.qvecs(ph); s = (C.V @ Qv.T).max(1)
    top = np.argsort(-np.where(m, s, -9))[:5]
    q2 = Qv.mean(0) + C.V[top].mean(0); q2 /= np.linalg.norm(q2)
    return np.maximum(s, C.V @ q2)
found = {}
for q in Q:
    if q["examples"]: continue
    p = P[q["id"]]; m = q["mask"]
    d = rank(prf([q["query"]] + p["phrases"], m & ok), m & ok)
    b = rank(C.bm25(" ".join([q["query"]] + p["keywords"]), "full"), m)
    pos = {n: i for i, n in enumerate(rrf(d, b))}
    for n in q["rel_rows"]:
        f = pos.get(n, 10**9) < max(K, 2 * len(q["rel_rows"]))
        found[n] = found.get(n, False) or f
random.seed(7)
F = [n for n, f in found.items() if f and ok[n]]; M = [n for n, f in found.items() if not f and ok[n]]
pick = random.sample(F, 60) + random.sample(M, 60); random.shuffle(pick)
key, out = [], []
for i, n in enumerate(pick):
    it = C.items[C.ids[n]]
    cap = " ".join((it.get("caption") or "").split())[:280]
    tags = " ".join("#" + t for t in (it["platform_data"].get("hashtags") or [])[:8])
    out.append(f"{i:03d} | {cap} {tags}".strip())
    key.append({"i": i, "id": C.ids[n], "found": bool(found[n])})
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "judge_blind.txt"), "w").write("\n".join(out))
json.dump(key, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "judge_key.json"), "w"))
print(len(F), len(M))
