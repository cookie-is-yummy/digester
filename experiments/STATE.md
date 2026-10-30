# State

- **Phase:** 5 (experiment). Phases 1–4 done: baseline reproduced, benchmark written, flaws ranked (`results/flaws-ranked.md`), research notes in `research/`.
- **Budget (caps from env; ledger `data/ai_runs.jsonl`):**
  - OpenAI: cap $18; spent ~$0.00001 in this loop (key check).
  - Gemini: cap $18; spent ~$0.00005 (key check).
  - Earlier work spent about $0.04 on OpenAI embeddings.
- **Done:**
  - Data zips unzipped at the repo root (`data/`, gitignored); Muse export at `data/evals/labels/muse_export/caption-mu/` (25 text files, one per Muse report).
  - `.venv` (Python 3.12, uv) with numpy, scipy, scikit-learn, fastembed, wordninja.
  - Baseline run file `data/runs/baseline.json` built (27 s wall incl. model download).
  - `lib/ai_prices.json` filled in from both pricing pages, verified 2026-10-30.
  - Key checks through `lib/ai.py`: OpenAI chat (gpt-5-nano) + embeddings, Gemini generateContent (gemini-3.1-flash-lite) + gemini-embedding-2. Ledger works.
  - Evaluator round 1: repro matches (dev 0.508, all 0.486); Muse inventory; MU ceiling (mostly presence leakage: +0.156 from presence alone); baseline 0.585 on r1 labels.
  - Experiment 1 (evaluator round 2): real gpt-5-nano rewrite 0.496 (mean of 3 repeats, r2 labels) vs hand rewrite 0.578 vs none 0.411. The real rewrite is now the **honest base**.
  - Phase 2 benchmark: `results/benchmark-baseline.md`.
  - Experiments 2–8 (round r3): none adopted. Best: rewrite union +0.028 (CI spans 0, 3× rewrite cost).
  - Experiment 9 (round r4/r5): tier-1 enrichment (gemini-3.1-flash-lite, prompt te-v1c) as a separate BM25 field + vector, on a 4,979-item sample: **+0.059 [+0.019, +0.103]**, 13/2/1 — adopted provisionally.
  - Reference vs MU (200 items): ours misses ≥1 MU facet on 94% of items; text-reachable facets 70%; conflicts 9%.
  - Experiments 13–16 (round r5): none adopted. Near misses: qr-v2 rewrite +0.025; MLT plan +0.109 on the MLT kind (+0.020 overall).
  - Experiments 10–12 (round r6): not adopted. EmbeddingGemma +0.043 (CI spans 0), Gemini Embedding 2 +0.069 [−0.004, +0.136], ColBERT +0.020.
  - **Experiment 9b (round r7): adopted.** Full-corpus enrichment (20,829 items, Gemini Batch, $2.86) → dev nDCG@10 **0.549**, +0.059 [+0.016, +0.108], 13/3/0. This is **base B2**.
- **In flight:** experiments 17–20 on B2 (qr-v2 rewrite, MLT plan, info gate with enrichment, HyDE) — `methods/stack.py`.
- **Next:** evaluate 17–20 (round r8); maybe EmbeddingGemma on B2; then phase 6 (test split: 2 scorings left; write-up; amendment; draft PR).
- **Labels:** round r7 is current. Test-split scorings used: 1 of 3.
- **Budget (ledger):** OpenAI ~$0.08 of $18; Gemini ~$5.14 of $18.

## Assumptions (open)

1. **No `YOUTUBE_API_KEY`** in the environment, so no YouTube media experiments; YouTube/podcast/article fit is assessed by design and cost estimate only.
2. **`gemini-2.5-flash-lite` is unavailable** to this key ("no longer available to new users", 404). The cheapest Gemini text model used is `gemini-3.1-flash-lite` ($0.25 / $1.50 per M).
3. **Gemini Embedding 2's model ID is `gemini-embedding-2`** (GA; `gemini-embedding-2-preview` also listed), $0.20/M text input standard, $0.10 batch.
4. **The "all 22" repro scoring counts as test-split scoring #1 of 3**, to be conservative (the brief asks to match the all-22 number in phase 1; it includes the 6 test queries).
5. **The MU ceiling and the Muse parser are evaluator-side code** (`experiments/eval/muse*.py`): they read MU text, so builders never run or read them.
6. **One experimenter may run a small batch of independent one-variable experiments** (each preregistered as its own LOG row, each with its own runs), to avoid several agents editing the same pipeline file at once. Evaluation stays per experiment.
7. **Experiments run on all three cached rewrite sets** and report the mean paired Δ against the same-repeat base, because the LLM rewrite varies a lot between calls. In production the rewrite would be cached per query.
8. **Rule slip, recorded:** one Gemini diagnostic call was made with curl outside `lib/ai.py` while diagnosing the 404 (~20 tokens, <$0.0001). It was logged by hand in the ledger. All later paid calls go through `lib/ai.py`.
