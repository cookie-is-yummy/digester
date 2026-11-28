"""PROTOTYPE ONLY - build one user's library profile (lp-v1) for the library-aware rewrite (round 2, Q2).

Method-side only. Reads exactly three files and nothing else:
  $DIGESTER_DATA/corpus/items.jsonl, $DIGESTER_DATA/corpus/interactions.jsonl,
  $DIGESTER_DATA/enrich/<enrich>.jsonl (B3's tier-1 enrichment rows, default te-v1c_gemini-3.1-flash-lite).
It never opens the eval queries, the labels or any run file.

Friends' items (platform_data.owner_relation == "mutual") contribute nothing: their interactions, hashtags,
creators, collections and enrichment rows are skipped.

Contents (rule-based, no AI call):
  - collection names (the user's own; by item count, at most 30);
  - top 40 creators by interaction weight (sum over the creator's items of each item's summed interaction weights);
  - top 60 hashtags by interaction weight (same weight; generic tags such as fyp/viral dropped);
  - enrichment `kind` values by count (unknown/other dropped) and the top 40 enrichment `topics` by item count.
Rendered as one compact text block of at most ~600 tokens (estimated at 4 chars/token; tails are trimmed if over).

Output: $DIGESTER_DATA/profile/library_profile_v1.json  (gitignored; never copy its contents into experiments/)
usage: python experiments/methods/library_profile.py [--enrich te-v1c_gemini-3.1-flash-lite]
Prints counts and sizes only.
"""
import argparse
import collections
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
from common import GENERIC, letters  # noqa: E402

DATA = os.environ.get("DIGESTER_DATA", os.path.join(os.path.dirname(os.path.dirname(HERE)), "data"))
VERSION = "lp-v1"
MAX_TOKENS = 600
N_COLL, N_CREATORS, N_TAGS, N_TOPICS = 30, 40, 60, 40


def est_tokens(s):
    return (len(s) + 3) // 4


def render(collections_, creators, tags, kinds, topics):
    lines = ["LIBRARY PROFILE (built from this person's own saved, liked and shared items; most-used first):"]
    if collections_:
        lines.append("collections they made: " + "; ".join(collections_))
    lines.append("creators they interact with most: " + " ".join("@" + h for h in creators))
    lines.append("hashtags on their items: " + " ".join("#" + t for t in tags))
    lines.append("kinds of items: " + ", ".join(f"{k} {p}%" for k, p in kinds))
    lines.append("common topics: " + "; ".join(topics))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--enrich", default="te-v1c_gemini-3.1-flash-lite")
    ap.add_argument("--out", default=os.path.join(DATA, "profile", "library_profile_v1.json"))
    a = ap.parse_args()
    t0 = time.time()

    items, friends = {}, set()
    for line in open(os.path.join(DATA, "corpus", "items.jsonl"), encoding="utf-8"):
        it = json.loads(line)
        if (it["platform_data"].get("owner_relation") or "") == "mutual":
            friends.add(it["id"])
            continue
        items[it["id"]] = it

    weight = collections.Counter()
    coll = collections.Counter()
    n_inter = n_inter_friend = 0
    for line in open(os.path.join(DATA, "corpus", "interactions.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        if r["item_id"] not in items:
            n_inter_friend += r["item_id"] in friends
            continue
        n_inter += 1
        weight[r["item_id"]] += float(r.get("weight") or 0)
        if r.get("collection_name"):
            coll[(r["collection_name"] or "").strip()] += 1
    for iid, it in items.items():  # collection names also sit on the item
        for c in it["platform_data"].get("collections") or []:
            if c and c.strip() not in coll:
                coll[c.strip()] += 1

    creators, tags = collections.Counter(), collections.Counter()
    for iid, it in items.items():
        w = weight.get(iid, 0.0)
        if w <= 0:
            continue
        pd = it["platform_data"]
        h = (pd.get("owner_handle") or "").strip().lstrip("@")
        if h:
            creators[h] += w
        for t in {(x or "").lower().lstrip("#") for x in pd.get("hashtags") or []}:
            if t and t not in GENERIC and letters(t)[0] >= 3:
                tags[t] += w

    code_ok = {it["dedup_key"].split(":", 1)[1] for it in items.values()}
    rows = {}
    for line in open(os.path.join(DATA, "enrich", f"{a.enrich}.jsonl"), encoding="utf-8"):
        r = json.loads(line)
        if r.get("ok") and r["code"] in code_ok:
            rows[r["code"]] = r  # last ok row wins (same choice as e9_enrich_search.build)
    kinds, topics = collections.Counter(), collections.Counter()
    for r in rows.values():
        k = (r.get("kind") or "").strip().lower()
        if k and k not in ("unknown", "other"):
            kinds[k.replace("_", " ")] += 1
        for t in {" ".join((x or "").lower().split()) for x in r.get("topics") or []}:
            if t:
                topics[t] += 1

    n_rows = max(1, len(rows))
    sel = {"collections": [c for c, _ in coll.most_common(N_COLL)],
           "creators": [h for h, _ in creators.most_common(N_CREATORS)],
           "hashtags": [t for t, _ in tags.most_common(N_TAGS)],
           "kinds": [(k, round(100 * n / n_rows)) for k, n in kinds.most_common() if 100 * n / n_rows >= 0.5],
           "topics": [t for t, _ in topics.most_common(N_TOPICS)]}
    text = render(sel["collections"], sel["creators"], sel["hashtags"], sel["kinds"], sel["topics"])
    trimmed = 0
    while est_tokens(text) > MAX_TOKENS:  # trim the longest tail first, one entry at a time
        key = max(("hashtags", "creators", "topics", "collections"), key=lambda k: len(sel[k]))
        sel[key].pop()
        trimmed += 1
        text = render(sel["collections"], sel["creators"], sel["hashtags"], sel["kinds"], sel["topics"])

    out = {"version": VERSION, "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "sources": ["corpus/items.jsonl", "corpus/interactions.jsonl", f"enrich/{a.enrich}.jsonl"],
           "excluded": "items with platform_data.owner_relation == 'mutual' (friends) and their interactions",
           "counts": {"items_used": len(items), "friend_items_skipped": len(friends), "interactions_used": n_inter,
                      "friend_interactions_skipped": n_inter_friend, "enrichment_rows_used": len(rows),
                      "collections": len(sel["collections"]), "creators": len(sel["creators"]),
                      "hashtags": len(sel["hashtags"]), "kinds": len(sel["kinds"]), "topics": len(sel["topics"]),
                      "trimmed_entries": trimmed},
           **sel, "text": text, "chars": len(text), "est_tokens": est_tokens(text)}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)
    wall = time.time() - t0
    print(f"wrote {a.out}")
    print(f"items processed {len(items)} (+{len(friends)} friend items skipped), "
          f"{len(items) / wall:.0f} items/s, wall {wall:.1f} s")
    print("counts", json.dumps(out["counts"]), f"chars {len(text)}, est tokens {out['est_tokens']}")


if __name__ == "__main__":
    main()
