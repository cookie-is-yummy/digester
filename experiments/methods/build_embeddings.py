"""PROTOTYPE ONLY - (re)build data/corpus/emb/bge_full from items.jsonl when the embeddings zip is missing.

Embeds the 'full' text view (caption + hashtags + creator + split hashtags) of every item with any text,
using bge-small-en-v1.5 via fastembed (local, free). It's resumable: chunks are cached in <out>/chunks/.
Takes ~50 min on 2 CPU cores for 20k items; logs items/s.

usage: python experiments/methods/build_embeddings.py [--limit N]
"""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
from corpus import DATA, fix_ws  # noqa: E402

limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
out = os.path.join(DATA, "corpus", "emb", "bge_full")
os.makedirs(os.path.join(out, "chunks"), exist_ok=True)


def text(it):
    import wordninja
    pd = it["platform_data"]
    tags = pd.get("hashtags") or []
    h = pd.get("owner_handle") or ""
    return fix_ws(" ".join([(it.get("caption") or "")[:600], " ".join("#" + t for t in tags[:15]),
                            f"by @{h} {pd.get('owner_name') or ''}",
                            " ".join(" ".join(wordninja.split(t)) for t in tags[:15]), " ".join(wordninja.split(h))]))


items = [json.loads(l) for l in open(os.path.join(DATA, "corpus", "items.jsonl"), encoding="utf-8")]
items = [it for it in items if (it.get("caption") or "").strip() or it["platform_data"].get("hashtags")][:limit]
ids, texts = [it["id"] for it in items], [text(it) for it in items]
from fastembed import TextEmbedding  # noqa: E402

model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5", threads=os.cpu_count())
t0, CH = time.time(), 1000
for c in range(0, len(texts), CH):
    p = os.path.join(out, "chunks", f"chunk_{c // CH:03d}.npy")
    if not os.path.exists(p):
        np.save(p, np.array(list(model.embed(texts[c:c + CH])), dtype=np.float32))
        done = min(c + CH, len(texts))
        print(f"{done}/{len(texts)} items, {done / (time.time() - t0):.1f} items/s", flush=True)
V = np.concatenate([np.load(os.path.join(out, "chunks", f"chunk_{c // CH:03d}.npy")) for c in range(0, len(texts), CH)])
np.save(os.path.join(out, "emb.npy"), V.astype(np.float16))
json.dump(ids, open(os.path.join(out, "ids.json"), "w"))
print(f"done: {len(ids)} items in {time.time() - t0:.0f}s")
