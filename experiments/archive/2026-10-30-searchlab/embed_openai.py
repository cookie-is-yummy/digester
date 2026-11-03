"""PROTOTYPE ONLY - embed corpus (+ all eval query phrases) with an OpenAI embedding model.

Key is read from the OPENAI_API_KEY environment variable only; never written anywhere.
usage: venv/bin/python -I searchlab/embed_openai.py <view> <out_dir> [model]
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lab import Corpus  # noqa: E402

VIEW, OUT = sys.argv[1], sys.argv[2]
MODEL = sys.argv[3] if len(sys.argv) > 3 else "text-embedding-3-small"
KEY = os.environ["OPENAI_API_KEY"]
os.makedirs(OUT, exist_ok=True)
usage = {"tokens": 0}


def embed(texts):
    body = json.dumps({"model": MODEL, "input": [t if t.strip() else "." for t in texts]}).encode()
    for attempt in range(6):
        req = urllib.request.Request("https://api.openai.com/v1/embeddings", data=body,
                                     headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.load(r)
            usage["tokens"] += d["usage"]["total_tokens"]
            V = np.array([e["embedding"] for e in sorted(d["data"], key=lambda e: e["index"])], dtype=np.float32)
            return V / np.linalg.norm(V, axis=1, keepdims=True)
        except urllib.error.HTTPError as e:
            msg = e.read().decode()[:300]
            if e.code in (429, 500, 502, 503) and attempt < 5:
                time.sleep(2 ** attempt)
                continue
            sys.exit(f"HTTP {e.code}: {msg}")


C = Corpus()
N, CH = len(C.ids), 500
t0 = time.time()
for c, s in enumerate(range(0, N, CH)):
    p = f"{OUT}/chunk_{c:03d}.npy"
    if os.path.exists(p):
        continue
    np.save(p, embed([C.text(n, VIEW)[:2000] for n in range(s, min(s + CH, N))]))
    if c % 5 == 0:
        print(f"{min(s + CH, N)}/{N} {time.time() - t0:.0f}s tokens {usage['tokens']}", flush=True)
V = np.vstack([np.load(f"{OUT}/chunk_{c:03d}.npy") for c in range((N + CH - 1) // CH)])
np.save(f"{OUT}/emb.npy", V)
json.dump(C.ids, open(f"{OUT}/ids.json", "w"))

# query phrases used by the eval (raw queries + parsed phrases)
HERE = os.path.dirname(os.path.abspath(__file__))
P = json.load(open(f"{HERE}/query_parses.json"))
phrases = set()
for l in open(f"{HERE}/evalset.jsonl"):
    q = json.loads(l)
    if q["query"]:
        phrases.add(q["query"])
        phrases.update(P.get(q["id"], {}).get("phrases", []))
phrases = sorted(phrases)
QV = embed(phrases)
json.dump({p: v.tolist() for p, v in zip(phrases, QV)}, open(f"{OUT}/queries.json", "w"))
print("done", V.shape, "tokens", usage["tokens"], f"wall {time.time() - t0:.0f}s")
