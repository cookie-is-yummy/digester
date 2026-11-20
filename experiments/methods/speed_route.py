"""PROTOTYPE ONLY - Q3 (d) LLM-free routing, round 2 (experiment 34).

Skip the rewrite (instant path, exp 30) when the query is a lookup of something in the user's own library; else B3.
The rule was fixed (LOG.md row 34) before any routing output was computed; thresholds come from the corpus only
(items.jsonl, interactions.jsonl), never from queries, labels or scores.

Entities (built once per user):
  - creator handles: owner_handle lowercased with '.' and '_' removed, >= 4 chars, >= 2 items in the corpus
  - creator names: owner_name with >= 2 words, >= 2 items, normalised to lowercase letters/digits without spaces
  - collections: every collection name, normalised the same way (>= 3 chars)
  - high-weight hashtags: not in common.GENERIC, >= 4 chars, >= 10 items, and in the top 1% of distinct hashtags by
    summed interaction weight (item weight = sum of its interaction weights)
Query: lowercase word tokens (\\w+). Content tokens = tokens not in common.STOP and not in llm_rewrite.BANNED.
An entity matches a run of 1-3 adjacent query tokens whose concatenation equals it, or an @handle / #tag token.
Route (instant path) when >= 1 entity matches and at most 1 content token is left uncovered by the matches.
More-like-this searches never rewrite, so they are unchanged (B3 = instant for them).

Runs: data/runs/e34_route_r{k}.json = routed searches from the instant path, the others from B3 on the cached
qr-v1 gpt-5-nano r{k} rewrite (same rankings as e20_hyde_b2_r{k}, re-computed here). Latency per search:
routed = rule check + instant search; others = rule check + rewrite + B3 search. Rewrite seconds come from
(i) the r{k} file's recorded calls (round 1) and (ii) this session's fresh gpt-5-nano calls (qr-v1_gpt-5-nano_t_r{k}).

usage: python experiments/methods/speed_route.py
Prints routing decisions by search id and kind (method side) and aggregates. No query text.
"""
import collections
import json
import os
import re
import time

import numpy as np

from speed_common import EMPTY, REWRITES, RUNS, dev_queries, load_b3, summary, timed_search, warm, write_run
from common import GENERIC, STOP  # noqa: E402  (speed_common put lib/ on sys.path)
from corpus import DATA  # noqa: E402
from llm_rewrite import BANNED  # noqa: E402

TOP_TAG_SHARE, TAG_MIN_ITEMS, MIN_ITEMS, TOL = 0.01, 10, 2, 1


def norm(s):
    return re.sub(r"[^0-9a-z]", "", (s or "").lower())


def build_entities():
    t = time.time()
    items = [json.loads(l) for l in open(os.path.join(DATA, "corpus", "items.jsonl"), encoding="utf-8")]
    w = collections.defaultdict(float)
    for l in open(os.path.join(DATA, "corpus", "interactions.jsonl")):
        r = json.loads(l)
        w[r["item_id"]] += float(r.get("weight") or 0)
    handles, names, tag_n, tag_w, colls = collections.Counter(), collections.Counter(), collections.Counter(), \
        collections.defaultdict(float), set()
    for it in items:
        pd = it["platform_data"]
        h = norm(pd.get("owner_handle"))
        if h:
            handles[h] += 1
        nm = pd.get("owner_name") or ""
        if len(nm.split()) >= 2 and norm(nm):
            names[norm(nm)] += 1
        for tg in set(x.lower() for x in pd.get("hashtags") or []):
            tag_n[tg] += 1
            tag_w[tg] += w[it["id"]]
        for c in pd.get("collections") or []:
            if len(norm(c)) >= 3:
                colls.add(norm(c))
    order = sorted(tag_w, key=lambda x: -tag_w[x])
    cut = tag_w[order[max(0, int(round(TOP_TAG_SHARE * len(order))) - 1)]]
    tags = {norm(x) for x in order if tag_w[x] >= cut and tag_n[x] >= TAG_MIN_ITEMS and x not in GENERIC
            and len(norm(x)) >= 4}
    ent = {"handle": {h for h, n in handles.items() if n >= MIN_ITEMS and len(h) >= 4},
           "name": {h for h, n in names.items() if n >= MIN_ITEMS},
           "collection": colls, "hashtag": tags}
    stats = {"items": len(items), "distinct_hashtags": len(tag_w), "hashtag_weight_cutoff": round(cut, 2),
             **{f"n_{k}": len(v) for k, v in ent.items()}, "build_s": round(time.time() - t, 2)}
    return ent, stats


def route(query, ent):
    """Returns (routed: bool, matched entity types). Pure string work; no model."""
    toks = re.findall(r"[@#]?\w+", (query or "").lower())
    bare = [t.lstrip("@#") for t in toks]
    content = [i for i, t in enumerate(bare) if t not in STOP and t not in BANNED]
    covered, types = set(), []
    for i, t in enumerate(toks):
        if t.startswith("@") and norm(t) in ent["handle"] | ent["name"]:
            covered.add(i)
            types.append("handle")
        if t.startswith("#") and len(norm(t)) >= 3:
            covered.add(i)
            types.append("hashtag")
    for n in (3, 2, 1):
        for i in range(len(bare) - n + 1):
            span = "".join(norm(x) for x in bare[i:i + n])
            if not span:
                continue
            for kind in ("handle", "name", "collection", "hashtag"):
                if span in ent[kind]:
                    covered.update(range(i, i + n))
                    types.append(kind)
                    break
    uncovered = [i for i in content if i not in covered]
    return bool(types) and len(uncovered) <= TOL and len(content) >= 1, sorted(set(types))


def main():
    t0 = time.time()
    ent, est = build_entities()
    S, C = load_b3()
    qs = dev_queries()
    P = {k: json.load(open(os.path.join(REWRITES, f"qr-v1_gpt-5-nano_r{k}.json"))) for k in (1, 2, 3)}
    T = {k: json.load(open(os.path.join(REWRITES, f"qr-v1_gpt-5-nano_t_r{k}.json")))["_meta"]["per_query"]
         for k in (1, 2, 3)}
    warm(S, qs)
    warm(S, qs, lambda q: P[1][q["id"]])

    decisions, check_s = {}, []
    for q in qs:
        if q["examples"]:
            decisions[q["id"]] = {"routed": None, "types": [], "kinds": q["kinds"]}
            continue
        t = time.perf_counter()
        r, types = route(q["query"], ent)
        check_s.append(time.perf_counter() - t)
        decisions[q["id"]] = {"routed": r, "types": types, "kinds": q["kinds"]}

    by_kind = collections.defaultdict(lambda: [0, 0])
    for d in decisions.values():
        if d["routed"] is None:
            continue
        for kd in d["kinds"]:
            by_kind[kd][0] += int(d["routed"])
            by_kind[kd][1] += 1
    lat = {"recorded": [], "fresh": []}
    lat_b3 = {"recorded": [], "fresh": []}
    typed_mix = {"recorded": [], "fresh": []}
    for k in (1, 2, 3):
        out, l_rec, l_fr = {}, [], []
        for q in qs:
            d = decisions[q["id"]]
            if q["examples"]:
                fused, s = timed_search(S, q, None)
                out[q["id"]] = fused[:1000]
                for L in (l_rec, l_fr):
                    L.append(s)
                for L in (lat_b3["recorded"], lat_b3["fresh"]):
                    L.append(s)
                continue
            c = float(np.median(check_s))
            fi, si = timed_search(S, q, EMPTY)
            fb, sb = timed_search(S, q, P[k][q["id"]])
            rec, fr = P[k]["_meta"]["per_query"][q["id"]]["seconds"], T[k][q["id"]]["seconds"]
            lat_b3["recorded"].append(rec + sb)
            lat_b3["fresh"].append(fr + sb)
            if d["routed"]:
                out[q["id"]] = fi[:1000]
                l_rec.append(c + si)
                l_fr.append(c + si)
            else:
                out[q["id"]] = fb[:1000]
                l_rec.append(c + rec + sb)
                l_fr.append(c + fr + sb)
            typed_mix["recorded"].append(l_rec[-1])
            typed_mix["fresh"].append(l_fr[-1])
        n_routed = sum(1 for d in decisions.values() if d["routed"])
        meta = {"base": "routing: instant path (exp 30) for library lookups, else B3 (qr-v1 gpt-5-nano r{k})",
                "experiment": 34, "repeat": k, "routed_typed_searches": n_routed,
                "typed_searches": sum(1 for q in qs if not q["examples"]),
                "cost_usd": round(sum(P[k]["_meta"]["per_query"][q["id"]]["cost_usd"] for q in qs
                                      if not q["examples"] and not decisions[q["id"]]["routed"]), 6),
                "mix_p50_s_recorded_rewrite": summary(l_rec)["p50_s"],
                "mix_p95_s_recorded_rewrite": summary(l_rec)["p95_s"],
                "mix_p50_s_fresh_rewrite": summary(l_fr)["p50_s"], "mix_p95_s_fresh_rewrite": summary(l_fr)["p95_s"],
                "rule_check_p50_ms": round(1000 * float(np.median(check_s)), 3),
                "rule": "LOG.md row 34; methods/speed_route.py", "entities": est}
        write_run(os.path.join(RUNS, f"e34_route_r{k}.json"), f"route_instant_or_b3+qr-v1_gpt-5-nano_r{k}",
                  C.emb_name, meta, out)
        lat["recorded"] += l_rec
        lat["fresh"] += l_fr
    res = {"entities": est, "decisions": decisions,
           "routed_by_kind": {k: f"{v[0]}/{v[1]}" for k, v in sorted(by_kind.items())},
           "rule_check_ms": {"p50": round(1000 * float(np.median(check_s)), 3),
                             "max": round(1000 * float(np.max(check_s)), 3)},
           "mix_all16_recorded_rewrite": summary(lat["recorded"]), "mix_all16_fresh_rewrite": summary(lat["fresh"]),
           "mix_typed_recorded_rewrite": summary(typed_mix["recorded"]),
           "mix_typed_fresh_rewrite": summary(typed_mix["fresh"]),
           "b3_all16_recorded_rewrite": summary(lat_b3["recorded"]), "b3_all16_fresh_rewrite": summary(lat_b3["fresh"]),
           "wall_s": round(time.time() - t0, 1)}
    json.dump(res, open(os.path.join(RUNS, "speed", "route.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in res.items()}, indent=1))


if __name__ == "__main__":
    main()
