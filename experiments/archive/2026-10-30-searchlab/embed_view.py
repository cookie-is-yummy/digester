"""PROTOTYPE ONLY - re-embed the corpus with a different text view (resumable, chunked).

usage: venv/bin/python -I searchlab/embed_view.py <view> <out_dir>
"""
import os
import sys
import time

import numpy as np
from sklearn.preprocessing import normalize

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lab import Corpus  # noqa: E402

VIEW, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
C = Corpus()
from fastembed import TextEmbedding  # noqa: E402
model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5", threads=os.cpu_count())
N, CH = len(C.ids), 1000
t0 = time.time()
for c, s in enumerate(range(0, N, CH)):
    p = f"{OUT}/chunk_{c:03d}.npy"
    if os.path.exists(p):
        continue
    texts = [C.text(n, VIEW) for n in range(s, min(s + CH, N))]
    np.save(p, normalize(np.array(list(model.embed(texts, batch_size=64)))).astype(np.float32))
    done = min(s + CH, N)
    print(f"{done}/{N} {done / (time.time() - t0):.1f}/s", flush=True)
V = np.vstack([np.load(f"{OUT}/chunk_{c:03d}.npy") for c in range((N + CH - 1) // CH)])
np.save(f"{OUT}/emb.npy", V)
import json  # noqa: E402
json.dump(C.ids, open(f"{OUT}/ids.json", "w"))
print("done", V.shape)
