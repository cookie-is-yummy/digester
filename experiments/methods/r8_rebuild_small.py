"""PROTOTYPE ONLY - round 8 setup: rebuild corpus/emb/oai512 (text-embedding-3-small @ 512 d) after the upload dropped it.

The combined store was built by combined/build_root.py as [Instagram round-1 store ids] + [YouTube `oai512_allowed`
ids]. Neither id list was uploaded, so the order is reconstructed:
  - Instagram: the round-1 store's ids (data/corpus/emb/openai3s_512/ids.json, 20,202 items), if present; otherwise
    Instagram items with a caption or hashtags, in items.jsonl order;
  - YouTube: items with a Takeout title (caption), in items.jsonl order (yt_embed.py --view allowed).
Text = c4_lib.view_text(item)[:6000] (what c6_embed.py check compares against). Resumable 5,000-item chunks.
Every call goes through lib/ai.py (ledger + budget). Prints aggregates only.

usage: python experiments/methods/r8_rebuild_small.py [--ig-ids PATH] [--workers 2]
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
import ai  # noqa: E402
import c4_lib as L  # noqa: E402
from corpus import DATA  # noqa: E402

OUT = os.path.join(L.EMB, "oai512")
CHUNK = 5000
PURPOSE = "r8_rebuild_oai512"


def ordered_ids(ig_ids_path):
    items = [json.loads(x) for x in open(os.path.join(DATA, "corpus", "items.jsonl"), encoding="utf-8")]
    by_id = {it["id"]: it for it in items}
    if ig_ids_path and os.path.exists(ig_ids_path):
        ig = [i for i in json.load(open(ig_ids_path)) if i in by_id]
    else:
        ig = [it["id"] for it in items if it["platform"] == "instagram"
              and ((it.get("caption") or "").strip() or it["platform_data"].get("hashtags"))]
    yt = [it["id"] for it in items if it["platform"] == "youtube" and (it.get("caption") or "").strip()]
    return ig + yt, by_id, len(ig), len(yt)


def embed(texts, workers):
    from concurrent.futures import ThreadPoolExecutor
    chunks = [texts[i:i + 500] for i in range(0, len(texts), 500)]

    def one(ch):
        for att in range(10):
            try:
                return ai.openai_embed([t or " " for t in ch], model="text-embedding-3-small", dimensions=512,
                                       purpose=PURPOSE)
            except Exception as e:  # noqa: BLE001 - retry transient errors, never the budget stop
                if "budget stop" in str(e) or att == 9:
                    raise
                time.sleep(min(60, 4 * 2 ** att) if "429" in str(e) else 3 * (att + 1))

    with ThreadPoolExecutor(workers) as ex:
        out = [v for vs in ex.map(one, chunks) for v in vs]
    return normalize(np.array(out, dtype=np.float32))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ig-ids", default=os.path.join(os.path.dirname(DATA), "corpus", "emb", "openai3s_512", "ids.json"))
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    ids, by_id, n_ig, n_yt = ordered_ids(a.ig_ids)
    texts = [L.view_text(by_id[i])[:6000] for i in ids]
    print(json.dumps({"items": len(ids), "instagram": n_ig, "youtube": n_yt, "empty_text": sum(not t for t in texts)}),
          flush=True)
    os.makedirs(os.path.join(OUT, "chunks"), exist_ok=True)
    t0, done = time.time(), 0
    for c in range(0, len(texts), CHUNK):
        p = os.path.join(OUT, "chunks", f"chunk_{c // CHUNK:03d}.npy")
        if not os.path.exists(p):
            np.save(p, embed(texts[c:c + CHUNK], a.workers).astype(np.float16))
        done += min(CHUNK, len(texts) - c)
        print(f"{done}/{len(texts)} items, {done / max(time.time() - t0, 1e-9):.0f} items/s", flush=True)
    V = np.concatenate([np.load(os.path.join(OUT, "chunks", f"chunk_{c // CHUNK:03d}.npy"))
                        for c in range(0, len(texts), CHUNK)])
    np.save(os.path.join(OUT, "emb.npy"), V.astype(np.float16))
    json.dump(ids, open(os.path.join(OUT, "ids.json"), "w"))
    cost = sum(r["cost_usd"] for r in L.ledger() if r.get("purpose") == PURPOSE)
    print(json.dumps({"done": len(ids), "wall_s": round(time.time() - t0, 1), "cost_usd": round(cost, 4)}), flush=True)


if __name__ == "__main__":
    main()
