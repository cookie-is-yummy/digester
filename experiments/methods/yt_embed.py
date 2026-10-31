"""PROTOTYPE ONLY - round 3: OpenAI text-embedding-3-small (512 d) vector stores for the YouTube corpus.

  --view allowed  -> corpus/emb/oai512_allowed/       items with a Takeout title (allowed view text)
                     corpus/emb/oai512_allowed_ext/   more-like-this examples outside the library (given title)
  --view api      -> corpus/emb/ref_oai512_api/       RESEARCH-ONLY: items with an API row or a Takeout title
                                                      (API view text; Takeout fallback when no API row)
  --enrich NAME   -> corpus/emb/emb_NAME/             enrichment texts ($DIGESTER_DATA/enrich/text_NAME.json,
                                                      built here from NAME.jsonl), keyed by content code
Each batch of 1,000 texts is one ai.openai_embed call (ledger + budget). Prints aggregate numbers only.
"""
import argparse
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
import yt_lib as Y
from corpus import DATA, fix_ws

TE_FIELDS = ["topics", "shown", "said", "place", "people", "vibe", "use", "queries"]


def te_text(r):
    """Same enrichment text as e9_enrich_search.enrich_text (round 1)."""
    from e9_enrich_search import enrich_text
    return enrich_text(r)


def tv_text(r):
    """Video-pass (tv-v1) text: description, kind, topics, people, place, vibe, on-screen text, music, segment
    summaries, likely searches."""
    parts = [r.get("description") or ""]
    k = r.get("kind") or ""
    if k not in ("", "other"):
        parts.append(k.replace("_", " "))
    for f in ["topics", "people", "place", "vibe", "on_screen_text", "music", "queries"]:
        parts.append(" · ".join(r.get(f) or []))
    parts.append(" · ".join(s["summary"] for s in r.get("segments") or []))
    return fix_ws(" · ".join(p for p in parts if p))


def enrich_texts(name):
    rows = {}
    for l in open(os.path.join(DATA, "enrich" if not name.startswith("tv-") else "video", f"{name}.jsonl")):
        r = json.loads(l)
        if r.get("ok"):
            rows[r["code"]] = r  # last ok row wins
    f = tv_text if name.startswith("tv-") else te_text
    return {c: f(r) for c, r in sorted(rows.items())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--view", choices=["allowed", "api"])
    ap.add_argument("--enrich")
    a = ap.parse_args()
    t0 = time.time()
    if a.view:
        D = Y.YT()
        if a.view == "allowed":
            idx = [n for n in range(len(D.items)) if D.title[n]]
            texts = [D.allowed_text(n) for n in idx]
            name = "oai512_allowed"
        else:
            api = Y.load_api_rows()
            idx = [n for n in range(len(D.items)) if D.title[n] or (api.get(D.codes[n]) or {}).get("ok")]
            texts = [D.api_text(n, api.get(D.codes[n])) for n in idx]
            name = "ref_oai512_api"
        print(f"{name}: {len(idx)} items, mean {np.mean([len(t) for t in texts]):.0f} chars", flush=True)
        V = Y.embed_texts(texts, f"yt_embed_{name}", batch=1000 if a.view == "allowed" else 400, workers=4 if a.view == "allowed" else 2)
        Y.save_store(name, [D.items[n]["id"] for n in idx], V)
        if a.view == "allowed":
            ext = Y.outside_examples()
            Y.save_store("oai512_allowed_ext", list(ext), Y.embed_texts(list(ext.values()), "yt_embed_ext"))
    if a.enrich:
        texts = enrich_texts(a.enrich)
        json.dump(texts, open(os.path.join(DATA, "enrich", f"text_{a.enrich}.json"), "w"))
        codes = list(texts)
        print(f"emb_{a.enrich}: {len(codes)} rows, mean {np.mean([len(texts[c]) for c in codes]):.0f} chars", flush=True)
        V = Y.embed_texts([texts[c] for c in codes], f"yt_embed_{a.enrich}", batch=500)
        Y.save_store(f"emb_{a.enrich}", codes, V)
    print(f"wall {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
