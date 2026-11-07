"""PROTOTYPE ONLY - round 7: train the facet classifiers (H2) and the query router (H3) on training-side data only.

  facets  te-v1c kind / vibe labels over 3-large item vectors, 80 / 20 hash split (c7_lib.train_facets)
  router  syn-v1 synthetic searches (c7_synth.py) over 3-large search vectors, 80 / 20 by cell (c7_lib.train_router)
Never reads eval labels or eval queries. Writes $DIGESTER_DATA/r7/{facets,router}_quality.json and the model files.

usage: python experiments/methods/c7_train.py [--facets] [--router]
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
import c4_lib as L  # noqa: E402
import c6_lib as G  # noqa: E402
import c7_lib as H  # noqa: E402
from corpus import DATA  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--facets", action="store_true")
    ap.add_argument("--router", action="store_true")
    a = ap.parse_args()
    G.CACHE = os.path.join(DATA, "cache", "r7")
    if a.facets:
        q = H.train_facets(L.jl(os.path.join(DATA, "corpus", "items.jsonl")), log=lambda s: print(s, flush=True))
        print(json.dumps({k: q[k] for k in ("format", "tone")}, indent=1)[:6000])
    if a.router:
        q = H.train_router(log=lambda s: print(s, flush=True))
        print(json.dumps(q, indent=1))


if __name__ == "__main__":
    main()
