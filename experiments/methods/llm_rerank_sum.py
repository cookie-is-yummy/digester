"""PROTOTYPE ONLY - experiment 24: LLM graded rerank of B3's top 30, with the enrichment summary.

Same method as experiment 14 (methods/llm_rerank.py, reused unedited: gpt-5-nano, reasoning_effort minimal,
strict JSON schema, grades 0-3, non-friends re-sorted by (-grade, fused rank) into the slots not held by
friends, ranks 31+ unchanged, a failed call leaves the top 30 as is, more-like-this searches copied).
The one variable: what each candidate shows. Prompt `rerank-grade-v1s`:
  caption[:200] | hashtags | creator | summary (te-v1c one-sentence enrichment summary) | kind (te-v1c kind,
  omitted when unknown/other)
The system prompt gains one sentence: the summary and kind are an automatic reading of the same caption and
may be wrong.

Privacy and safety (AGENTS.md rule 8, docs/07-privacy-and-safety.md): friends (owner_relation == "mutual") are
never sent and keep their slots (llm_rerank.main). Caption, hashtags, creator and the summary (LLM output over
third-party text) are all cleaned of `<`, `>` and backticks and sent only inside the <candidates> data block.

usage: python experiments/methods/llm_rerank_sum.py --base data/runs/e20_hyde_b2_r1.json \
         --out data/runs/e24_rerank_sum_r1.json
Prints aggregate stats only (no query text, no items).
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
import llm_rerank as R  # noqa: E402
from corpus import DATA  # noqa: E402

ENRICH = "te-v1c_gemini-3.1-flash-lite"
PROMPT_VERSION = "rerank-grade-v1s"
SYSTEM = R.SYSTEM.replace(
    "don't describe what the video shows or says. Use them as clues.",
    "don't describe what the video shows or says. Use them as clues.\n"
    "Some candidates also show a summary and kind: an automatic one-sentence reading of the same caption,\n"
    "hashtags and creator. It may be wrong or guess too much; treat it as a hint, not as fact.")
assert SYSTEM != R.SYSTEM

_ENR = {}


def load_enrichment():
    for line in open(os.path.join(DATA, "enrich", f"{ENRICH}.jsonl")):
        r = json.loads(line)
        if r["ok"]:  # last ok row wins (same row choice as e9_enrich_search.build)
            _ENR[r["code"]] = (r.get("summary") or "", r.get("kind") or "")


def cand_line(cid, it):
    pd = it["platform_data"]
    cap = R.clean(it.get("caption"))[:200]
    low = (it.get("caption") or "").lower()
    tags = [R.clean(t) for t in (pd.get("hashtags") or []) if "#" + t.lower() not in low][:10]
    tags = " ".join("#" + t for t in tags if t)
    cre = f"@{R.clean(pd.get('owner_handle'))}"
    if pd.get("owner_name"):
        cre += f" ({R.clean(pd.get('owner_name'))})"
    from corpus import code_of
    summ, kind = _ENR.get(code_of(it), ("", ""))
    line = f'<c id="{cid}">caption: {cap or "(none)"} | hashtags: {tags or "(none)"} | creator: {cre}'
    line += f" | summary: {R.clean(summ) or '(none)'}"
    if kind and kind not in ("unknown", "other"):
        line += f" | kind: {R.clean(kind.replace('_', ' '))}"
    return line + "</c>"


def main():
    load_enrichment()
    R.SYSTEM, R.PROMPT_VERSION, R.cand_line = SYSTEM, PROMPT_VERSION, cand_line
    R.main()
    out = sys.argv[sys.argv.index("--out") + 1]
    run = json.load(open(out))
    m = run["meta"]
    m["rerank_enrich"] = ENRICH
    m["rerank_candidate_fields"] = "caption[:200] | hashtags | creator | te-v1c summary | te-v1c kind (if known)"
    if m.get("typed_query_plus_rewrite_p50_s") is not None and m.get("rerank_p50_s") is not None:
        m["typed_query_plus_rewrite_plus_rerank_p50_s"] = round(m["typed_query_plus_rewrite_p50_s"]
                                                                + m["rerank_p50_s"], 3)
    secs = [v["seconds"] for v in m["per_query_rerank"].values() if v.get("n_sent")]
    m["rerank_mean_s"] = round(float(np.mean(secs)), 3) if secs else None
    json.dump(run, open(out, "w"))
    print(f"meta: typed total p50 (query+rewrite+rerank) {m.get('typed_query_plus_rewrite_plus_rerank_p50_s')} s")


if __name__ == "__main__":
    main()
