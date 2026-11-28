"""PROTOTYPE ONLY - round 8.4 shared code (LOG.md "Round 8.4 fixed parameters", rows Y8.4-TG, Y8.4-TFY).

Base B8.3 = TI (ti-v1, c83_lib.TeIG on prior-p1). Each arm changes one thing:
  TG   Y8.4-TG (tg-v1): TI's te lists only on typed searches whose P platform read is Instagram (q_ig >= 0.5,
       unrounded); otherwise the search is exactly P (no te lists).
  TFY  Y8.4-TFY (tfy-v1): TI, then round 8.3's FY refine (rf-v1 unchanged) of TI's top 20 on rewrite-routed typed
       searches with q_ig < 0.5. Responses are read from the round-8.2 / 8.3 caches when the inputs (repeat, search,
       candidate ids in order) are identical; new calls are cached under cache/r8.4/.
Method side only: never opens evals/labels/. Never prints query or item text.
"""
import json
import os
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
import c82_lib as P  # noqa: E402
import c83_lib as Q  # noqa: E402
from corpus import DATA  # noqa: E402

TG_VERSION = "tg-v1"
TFY_VERSION = "tfy-v1"
TG_Q_IG_MIN = 0.5  # te lists iff q_ig >= 0.5 (fixed in LOG.md)
TFY_Q_IG_MAX = Q.FY_Q_IG_MAX  # refine iff rewrite-routed and q_ig < 0.5 (strict), as FY
CACHE_R84 = os.path.join(DATA, "cache", "r8.4", f"{P.REFINE_VERSION}.jsonl")
CACHES = ((Q.CACHE_R82, "r8.2"), (Q.CACHE_R83, "r8.3"), (CACHE_R84, "r8.4"))


class Refiner84(P.Refiner):
    """rf-v1 unchanged; reads the round-8.2, 8.3 and 8.4 caches, writes new responses to round 8.4's only."""

    def __init__(self, S, te_rows):
        self.S = S
        self.summary = {c: r["summary"] for c, r in te_rows.items() if r.get("summary")}
        self.cache, self.source = {}, {}
        for path, tag in CACHES:
            if os.path.exists(path):
                for line in open(path):
                    r = json.loads(line)
                    if r["key"] not in self.cache:  # first (oldest) response with identical inputs wins
                        self.cache[r["key"]] = r
                        self.source[r["key"]] = tag
        self.lock = threading.Lock()

    def get(self, rep, qid, query, order, allow_call=False):
        top, friend, send = self.split_top(order)
        key = P.cache_key(rep, qid, send)
        r = self.cache.get(key)
        if r is None:
            if not allow_call:
                raise KeyError("refine response not cached (run `refine` first)")
            res = self.call(query, send) if send else {"ok": True, "ids": [], "tries": 0, "seconds": 0.0,
                                                         "cost_usd": 0.0, "in_tokens": 0, "out_tokens": 0}
            r = {"key": key, "rep": rep, "qid": qid, "n_sent": len(send), **res}
            with self.lock:
                self.cache[key] = r
                self.source[key] = "r8.4"
                os.makedirs(os.path.dirname(CACHE_R84), exist_ok=True)
                with open(CACHE_R84, "a") as f:
                    f.write(json.dumps(r) + "\n")
        return self.reorder(order, top, friend, send, r), r
