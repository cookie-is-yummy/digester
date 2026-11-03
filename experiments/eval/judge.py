"""PROTOTYPE ONLY - EVALUATOR SIDE. Blind judging of pooled, unjudged results.

1. `sheet`: turn a pool file ({query_id: [codes]}) into a judging sheet. Items are shuffled across
   queries and carry no method names, so the judge can't tell which method surfaced them. Each line
   has the query text plus the item's caption, hashtags and creator, and any enrichment text given
   with --extra.
2. The judge grades every line: 2 = clearly what the search wants, 1 = borderline, 0 = not relevant.
   The judge is the evaluator agent, never the agent that built the method. Grades go into a JSON
   list in sheet order.
3. `merge`: add the grades to data/evals/labels/evalset.jsonl. Relevant items go into `relevant`;
   0-graded ones into `judged_not_relevant`. Provenance is recorded in labels/judgments_log.jsonl.

usage:
  python experiments/eval/judge.py sheet POOL.json SHEET.txt [--extra extra_text.json]
  python experiments/eval/judge.py merge SHEET.txt GRADES.json --judge "claude-evaluator"
"""
import datetime
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
from corpus import DATA  # noqa: E402

LAB = os.path.join(DATA, "evals", "labels")


def items_by_code():
    out = {}
    for line in open(os.path.join(DATA, "corpus", "items.jsonl"), encoding="utf-8"):
        it = json.loads(line)
        out[it["dedup_key"].split(":", 1)[1]] = it
    return out


def sheet(pool_path, sheet_path, extra_path=None):
    pool = json.load(open(pool_path))
    extra = json.load(open(extra_path)) if extra_path else {}
    labels = {json.loads(l)["id"]: json.loads(l) for l in open(os.path.join(LAB, "evalset.jsonl"))}
    items = items_by_code()
    rows = [(q, c) for q, cs in pool.items() for c in cs]
    random.Random(13).shuffle(rows)
    lines, key = [], []
    for i, (q, c) in enumerate(rows):
        it = items.get(c, {})
        pd = it.get("platform_data", {})
        cap = " ".join((it.get("caption") or "").split())[:400]
        tags = " ".join("#" + t for t in (pd.get("hashtags") or [])[:10])
        ex = (" | ENRICHMENT: " + " ".join(extra[c].split())[:400]) if c in extra else ""
        lines.append(f"{i:04d} | SEARCH: {labels[q]['query']} | ITEM: {cap} {tags} | by @{pd.get('owner_handle', '')}{ex}")
        key.append({"i": i, "query": q, "code": c})
    open(sheet_path, "w").write("\n".join(lines))
    json.dump(key, open(sheet_path + ".key.json", "w"))
    print(f"{len(rows)} lines -> {sheet_path}")


def merge(sheet_path, grades_path, judge):
    key = json.load(open(sheet_path + ".key.json"))
    grades = json.load(open(grades_path))
    assert len(grades) == len(key), "one grade per sheet line"
    path = os.path.join(LAB, "evalset.jsonl")
    qs = [json.loads(l) for l in open(path)]
    byid = {q["id"]: q for q in qs}
    now = datetime.date.today().isoformat()
    with open(os.path.join(LAB, "judgments_log.jsonl"), "a") as log:
        for k, g in zip(key, grades):
            q = byid[k["query"]]
            if g > 0:
                q["relevant"][k["code"]] = int(g)
            else:
                q.setdefault("judged_not_relevant", [])
                if k["code"] not in q["judged_not_relevant"]:
                    q["judged_not_relevant"].append(k["code"])
            log.write(json.dumps({"query": k["query"], "code": k["code"], "grade": int(g), "judge": judge, "date": now}) + "\n")
    with open(path, "w") as f:
        for q in qs:
            f.write(json.dumps(q) + "\n")
    print(f"merged {len(key)} judgments")


if __name__ == "__main__":
    if sys.argv[1] == "sheet":
        sheet(sys.argv[2], sys.argv[3], sys.argv[sys.argv.index("--extra") + 1] if "--extra" in sys.argv else None)
    elif sys.argv[1] == "merge":
        merge(sys.argv[2], sys.argv[3], sys.argv[sys.argv.index("--judge") + 1])
