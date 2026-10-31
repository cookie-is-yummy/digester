"""PROTOTYPE ONLY - EVALUATOR SIDE. Round 2 Q4: how far to trust the AI judge.

Two steps (see experiments/BRIEF-2.md, Q4):

1. `build` (seed 2026) writes a 60-line blind sheet for Derrick:
   - 40 pairs graded by an AI judge (judge starts with "claude-evaluator"; latest grade per pair wins),
     stratified 15 x grade 2, 10 x grade 1, 15 x grade 0, at most 4 per search where possible;
   - 20 pairs labelled by Muse in the hand-over labels (evalset.pre_r1.jsonl: `relevant` 1|2 and
     `hard_negatives` = 0) that no AI judge ever graded: 8 x 2, 6 x 1, 6 x 0, spread across searches;
   - items from mutual follows and items with no link are excluded; each item appears once;
   - shuffled, with source and grade kept only in the hidden key.
   Outputs data/eval_work/human_check/sheet.md and key.json.

2. `score` (default) reads data/eval_work/human_check/derrick_grades.json (60 ints, sheet order) and
   prints aggregates only: exact agreement, Cohen's kappa on relevant (>=1) vs not, confusion matrices
   (Derrick vs AI on the 40 AI lines, Derrick vs Muse on the 20 Muse lines), and a "leans toward text"
   check on the AI lines: agreement by caption richness (common.info_class, caption-length terciles)
   and the direction of disagreements (AI graded higher vs lower than Derrick).

usage:
  python experiments/eval/human_check.py build
  python experiments/eval/human_check.py [score] [--grades PATH]
"""
import json
import os
import random
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
from corpus import DATA  # noqa: E402
from common import info_class  # noqa: E402

LAB = os.path.join(DATA, "evals", "labels")
OUT = os.path.join(DATA, "eval_work", "human_check")
SEED = 2026
AI_STRATA = {2: 15, 1: 10, 0: 15}
MUSE_STRATA = {2: 8, 1: 6, 0: 6}
AI_CAP, MUSE_CAP = 4, 2
INSTRUCTION = ("Grade each line 0 / 1 / 2 (2 = clearly what the search wants, 1 = borderline, "
               "0 = not relevant). Open the link if the caption isn't enough.")


def items_by_code():
    out = {}
    for line in open(os.path.join(DATA, "corpus", "items.jsonl"), encoding="utf-8"):
        it = json.loads(line)
        out[it["dedup_key"].split(":", 1)[1]] = it
    return out


def link(code, it):
    kind = it.get("platform_data", {}).get("media_kind")
    if not code or not it.get("source_url") or kind not in ("reel", "post"):
        return None
    return f"https://www.instagram.com/{'reel' if kind == 'reel' else 'p'}/{code}/"


def search_text(q, items):
    if q.get("query"):
        return " ".join(q["query"].split())
    ex = (q.get("examples") or [""])[0]
    it = items.get(ex, {})
    cap = " ".join((it.get("caption") or "").split())[:120]
    return f"MORE LIKE: {cap} ({link(ex, it) or ex})"


def pick(cands, strata, cap, rng, used_codes, per_query):
    """Greedy stratified pick: scarcest stratum first, least-used search first, random tie-breaks."""
    chosen = []
    by_grade = defaultdict(list)
    for c in cands:
        by_grade[c["grade"]].append(c)
    for g in sorted(strata, key=lambda g: len(by_grade[g])):
        pool = by_grade[g][:]
        rng.shuffle(pool)
        for _ in range(strata[g]):
            ok = [c for c in pool if c["code"] not in used_codes]
            if not ok:
                break
            under = [c for c in ok if per_query[c["query"]] < cap] or ok  # relax the cap only if forced
            least = min(per_query[c["query"]] for c in under)
            qs = sorted({c["query"] for c in under if per_query[c["query"]] == least})
            q = rng.choice(qs)
            c = rng.choice([c for c in under if c["query"] == q])
            chosen.append(c)
            used_codes.add(c["code"])
            per_query[q] += 1
            pool.remove(c)
    return chosen


def build():
    rng = random.Random(SEED)
    items = items_by_code()
    queries = {json.loads(l)["id"]: json.loads(l) for l in open(os.path.join(DATA, "evals", "queries.jsonl"))}

    def eligible(code):
        it = items.get(code)
        return bool(it) and it["platform_data"].get("owner_relation") != "mutual" and link(code, it) is not None

    latest, ever_ai = {}, set()
    for line in open(os.path.join(LAB, "judgments_log.jsonl")):
        r = json.loads(line)
        if not str(r.get("judge", "")).startswith("claude-evaluator"):
            continue
        ever_ai.add((r["query"], r["code"]))
        latest[(r["query"], r["code"])] = r  # file order = chronological; later rows win
    ai = [{"query": q, "code": c, "grade": int(r["grade"]), "judge": r["judge"], "source": "ai"}
          for (q, c), r in latest.items() if q in queries and eligible(c)]

    muse = []
    for line in open(os.path.join(LAB, "evalset.pre_r1.jsonl")):
        q = json.loads(line)
        pairs = [(c, int(g)) for c, g in (q.get("relevant") or {}).items()]
        pairs += [(c, 0) for c in (q.get("hard_negatives") or [])]
        for c, g in pairs:
            if (q["id"], c) not in ever_ai and q["id"] in queries and eligible(c):
                muse.append({"query": q["id"], "code": c, "grade": g, "judge": "muse", "source": "muse"})

    used = set()
    ai_pick = pick(ai, AI_STRATA, AI_CAP, rng, used, Counter())
    muse_pick = pick(muse, MUSE_STRATA, MUSE_CAP, rng, used, Counter())
    rows = ai_pick + muse_pick
    rng.shuffle(rows)

    os.makedirs(OUT, exist_ok=True)
    lines, key = [INSTRUCTION, ""], []
    for n, r in enumerate(rows, 1):
        it = items[r["code"]]
        cap = " ".join((it.get("caption") or "").split())[:160]
        lines.append(f"{n:02d} | SEARCH: {search_text(queries[r['query']], items)} | ITEM: {cap} | "
                     f"@{it['platform_data'].get('owner_handle', '')} | {link(r['code'], it)}")
        key.append({"n": n, "query": r["query"], "code": r["code"], "source": r["source"],
                    "grade": r["grade"], "judge": r["judge"]})
    open(os.path.join(OUT, "sheet.md"), "w", encoding="utf-8").write("\n\n".join(lines[:1] + lines[2:]) + "\n")
    json.dump(key, open(os.path.join(OUT, "key.json"), "w"), indent=1)

    def summary(sel, strata):
        got = Counter(r["grade"] for r in sel)
        per_q = Counter(r["query"] for r in sel)
        return {f"grade {g}": f"{got[g]}/{strata[g]}" for g in strata} | {
            "searches": len(per_q), "max per search": max(per_q.values()) if per_q else 0}

    print(f"candidates: ai={len(ai)} {dict(Counter(c['grade'] for c in ai))}, "
          f"muse={len(muse)} {dict(Counter(c['grade'] for c in muse))}")
    print("AI:", summary(ai_pick, AI_STRATA))
    print("Muse:", summary(muse_pick, MUSE_STRATA))
    print(f"{len(rows)} lines -> {os.path.join(OUT, 'sheet.md')} (key: key.json)")


# ---------- scoring ----------

def kappa(a, b):
    n = len(a)
    if n == 0:
        return float("nan")
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(v) / n) * (b.count(v) / n) for v in set(a) | set(b))
    return float("nan") if pe == 1 else (po - pe) / (1 - pe)


def confusion(d, o, other):
    m = [[0] * 3 for _ in range(3)]
    for x, y in zip(d, o):
        m[x][y] += 1
    out = [f"    rows = Derrick, cols = {other}", "            0   1   2"]
    out += [f"    D={g}   {m[g][0]:3d} {m[g][1]:3d} {m[g][2]:3d}" for g in range(3)]
    return "\n".join(out)


def agree_block(name, d, o):
    rel_d, rel_o = [int(x >= 1) for x in d], [int(x >= 1) for x in o]
    exact = sum(x == y for x, y in zip(d, o)) / len(d)
    binary = sum(x == y for x, y in zip(rel_d, rel_o)) / len(d)
    print(f"\n== Derrick vs {name} (n={len(d)}) ==")
    print(f"  exact agreement (0/1/2): {exact:.0%}   relevant-vs-not agreement: {binary:.0%}   "
          f"kappa (relevant vs not): {kappa(rel_d, rel_o):.2f}")
    print(confusion(d, o, name))


def score(grades_path):
    key = json.load(open(os.path.join(OUT, "key.json")))
    grades = json.load(open(grades_path))
    assert len(grades) == len(key), f"need {len(key)} grades in sheet order, got {len(grades)}"
    assert all(g in (0, 1, 2) for g in grades), "grades must be 0, 1 or 2"
    items = items_by_code()
    for k, g in zip(key, grades):
        k["derrick"] = int(g)
    ai = [k for k in key if k["source"] == "ai"]
    mu = [k for k in key if k["source"] == "muse"]

    agree_block("AI judge", [k["derrick"] for k in ai], [k["grade"] for k in ai])
    agree_block("Muse", [k["derrick"] for k in mu], [k["grade"] for k in mu])

    print("\n== Does the AI judge lean toward text? (AI lines only) ==")
    for k in ai:
        it = items[k["code"]]
        k["info"] = info_class(it)
        k["caplen"] = len(" ".join((it.get("caption") or "").split()))
    lens = sorted(k["caplen"] for k in ai)
    t1, t2 = lens[len(lens) // 3], lens[2 * len(lens) // 3]
    for k in ai:
        k["tercile"] = "short" if k["caplen"] < t1 else ("medium" if k["caplen"] < t2 else "long")

    def split(field, order):
        print(f"  by {field}:")
        for v in order:
            g = [k for k in ai if k[field] == v]
            if not g:
                continue
            ex = sum(k["derrick"] == k["grade"] for k in g) / len(g)
            rel = sum((k["derrick"] >= 1) == (k["grade"] >= 1) for k in g) / len(g)
            hi = sum(k["grade"] > k["derrick"] for k in g)
            print(f"    {v:<12} n={len(g):2d}  exact {ex:.0%}  relevant-vs-not {rel:.0%}  AI higher on {hi}")

    split("info", ["ok", "low", "non_english"])
    print(f"  (caption-length terciles: short < {t1} chars <= medium < {t2} chars <= long)")
    split("tercile", ["short", "medium", "long"])
    dis = [k for k in ai if k["grade"] != k["derrick"]]
    up = sum(k["grade"] > k["derrick"] for k in dis)
    bdis = [k for k in ai if (k["grade"] >= 1) != (k["derrick"] >= 1)]
    bup = sum(k["grade"] >= 1 for k in bdis)
    print(f"  disagreements (0/1/2): {len(dis)}; AI graded higher than Derrick on {up} "
          f"({up / len(dis):.0%})" if dis else "  no 0/1/2 disagreements")
    print(f"  relevant-vs-not flips: {len(bdis)}; AI said relevant, Derrick not: {bup}"
          + (f" ({bup / len(bdis):.0%})" if bdis else ""))
    mean_ai = sum(k["grade"] for k in ai) / len(ai)
    mean_d = sum(k["derrick"] for k in ai) / len(ai)
    print(f"  mean grade on AI lines: AI {mean_ai:.2f} vs Derrick {mean_d:.2f}")
    print("  Reading: the AI judge saw captions only. If it leans toward text, agreement drops on 'low' /"
          " short captions and most disagreements are AI-higher on text-rich items or AI-lower where the"
          " caption is thin but the video is on topic.")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "build":
        build()
    else:
        gp = args[args.index("--grades") + 1] if "--grades" in args else os.path.join(OUT, "derrick_grades.json")
        score(gp)
