# Experiment 9, part 1: tier-1 text enrichment, pilot and sample (method note)

*30 Oct 2026 · Experimenter · aggregate numbers only, no content. Scores are for the evaluator.*

## What was built

- `methods/enrich_items.py`. One LLM call per item. Input: the caption (cut at 1,000 chars), hashtags not already in the caption, creator handle and name, media kind and the user's collection names. Each is a delimited data field, with `<` and `>` escaped, and the system prompt says to treat them as data.
- Output: strict JSON. OpenAI uses `json_schema` with `strict: true`; Gemini uses `responseJsonSchema`.
  - Fields: summary, kind, topics, shown, said, place, people, vibe, use, `unknown` facets, 3–5 likely searches, a sensitive tag and the language.
- Post-validation in plain Python, applied to every row:
  - lists are capped and lowercased;
  - `#` and `@` are stripped;
  - strings with URLs, emails or instruction-like text are dropped;
  - filler values ("unknown", "not specified", "… context") are dropped.
- Other behaviour:
  - Concurrency: 8 threads.
  - Resumable.
  - Every call goes through `lib/ai.py`.
  - The raw model object is kept in the output row, so rows can be re-validated without new calls.
- `methods/e9_enrich_search.py` runs the honest base plus two extra RRF lists:
  - BM25 over the enrichment text only, as a separate index;
  - bge-small over the enrichment text only, as a separate vector, taking the max over the base's query phrases.
  - More-like-this searches use the examples' enrichment text and the centroid of their enrichment vectors.
  - With the extras off, it reproduces `e1_rewrite_r{1,2,3}` **exactly**: identical 1,000-deep lists for all 16 dev searches in all 3 repeats.
- `lib/ai.py`: `gemini_json` gained an optional `generation_config` passthrough, used for `thinkingConfig` and `responseJsonSchema`. It is backwards compatible, and the ledger and budget logic are unchanged.
- **Search text** per item: summary · kind (unless other or unknown) · topics · shown · said · place · people · vibe · use · likely searches. Mean length 329 chars. Not indexed: `unknown`, `sensitive`, `lang`.

## Privacy

- **Friends excluded:** the 463 items whose creator is a mutual follow (`platform_data.owner_relation == "mutual"`) are never sent to an LLM.
  - They are removed from the pilot pool, the random draws and the sample.
  - 34 of them were in the base's top-200 union; they stay in the base lists, unenriched.
- **Fields sent:** only those listed above. Collection names (the user's own data) are included in this experiment. A shared content-level cache must not hold them; that is a product deviation, as the research note says.

## Pilot: 200 random items with text (seed 7), same prompt `te-v1`

| | gpt-5-nano (`reasoning_effort` minimal) | gemini-3.1-flash-lite (`thinkingBudget` 0, accepted) | nano, 8 items per call | flash-lite, compact JSON (`te-v1c`, 40 items) |
| --- | --- | --- | --- | --- |
| JSON valid, first attempt | 1.000 (0.985 before a validator fix, see deviations) | 0.935: 13 cut off at the 300-token cap; 13/13 fine at 450 | 1.000 | 1.000 |
| Input / output tokens per item | 868 / 170 | 631 / 218 | 231 / 147 | 642 / 134 |
| Real cost per 1,000 items (ledger) | $0.112 | $0.49 (plus retries) | $0.070 | **$0.361** |
| Call latency p50 / p95 | 2.0 s / 3.2 s | 1.3 s / 1.7 s | 12.9 s / 16.5 s per call | 1.4 s / 1.8 s |
| Throughput, 8 threads | 3–5 items/s | 6 items/s | 4 items/s | 5–7 items/s |
| `unknown` lists shown / said / audio | 0.56 / 0.58 / 0.96 | 0.51 / 0.42 / 0.91 | 0.60 / 0.44 / 0.98 | — |
| Facet both filled and listed as unknown | 98% of items | 47% | 96% | — |
| **Spot check, 20 items** (I read input and output) | **3/20** assert unsupported facts; **6/20** wrong `kind`; about 10/20 contain filler values | **1/20** unsupported; 0/20 wrong `kind` (but `other` on 38% of items); 2/20 filler | 9/20 wrong `kind`; about 8/20 copy the caption as the summary; 1 garbled entity, possible cross-talk | 10 items re-checked: 0 unsupported, same facets as `te-v1` |

**Cross-talk check for packing.** Words in a packed output that occur only in a neighbour's input: 4.3%, against a 3.7% chance baseline (single-call outputs measured against the same neighbours). The difference is small, but quality fell, so **one item per call**.

**Model choice: gemini-3.1-flash-lite with prompt `te-v1c`.** `te-v1c` is `te-v1` plus one line asking for single-line JSON.
- **Why not nano.** gpt-5-nano is 3–4× cheaper but clearly worse. Its wrong `kind` labels inject false category words: "travel" or "review" on unrelated items, which become BM25 bridge terms to the wrong searches. It invents more, and its `unknown` list contradicts its own fields on almost every item. The brief's rule is to use the cheaper model only if it is not clearly worse, so it was not chosen.
- **Compact JSON.** It cut Gemini output tokens by 38% (217 → 134) with the same facet volume and validity, which brought the cost from $0.49 to $0.36 per 1,000 items.

## Label-independent sample

- **Composition:**
  - the union of the honest base's top 200 for every dev search, across the 3 rewrite repeats (3,321 items);
  - 2,000 random items with or without text (seed 11);
  - the 3 dev more-like-this example items (query inputs, not labels);
  - minus friends.
- **Total: 4,979 items**, 100 of them with no text.
- **Result:** 4,978 enriched (validity 99.98%). One item returned no candidate twice, probably a safety block, and stays unenriched. Strings dropped by the validator: 2 rows.
- **Wall time and cost:** 740 s at 6.7 items/s (8 threads), call p50 1.14 s, p95 1.44 s. Ledger cost **$1.770, which is $0.356 per 1,000 items** standard. Batch API equivalent: **$0.178 per 1,000**, recomputed from the token counts at batch prices. Batch was not used.
- **Mean tokens per item:** 647 in, 130 out.
- **Share of items whose `unknown` lists each facet** (items with text):

  | Facet | shown | said | audio | place | people | vibe | use | kind | topics |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | Share | 0.53 | 0.33 | 0.87 | 0.74 | 0.24 | 0.53 | 0.58 | 0.37 | 0.08 |

  - `kind` is known (not other or unknown) for 75% of items.
- **No-text items:** shown, said, place and vibe are unknown for 99–100%, and `kind` for 97%. topics is filled for 30% and people for 58% (from the handle or display name). The prompt does not invent content for them, as intended.
- **Sensitive tag:** money 70, health 68, relationships 44 (3.7% of items).
- **Embedding:** bge-small, fastembed, 4 threads: 12.7 items/s, 392 s for 4,978 texts. A full corpus would take about 28 min on CPU.

## Runs (dev, 16 searches, 3 rewrite repeats)

| Run file | Arm |
| --- | --- |
| `data/runs/e9_enrich_r{1,2,3}.json` | base + enrichment BM25 + enrichment dense |
| `data/runs/e9_enrich_bm25only_r{1,2,3}.json` | base + enrichment BM25 only (secondary arm) |

- **Query latency** p50 is 0.22–0.34 s, against 0.16–0.19 s for the reproduced base on the same machine. The index covers only the sample.
- **Overlap with the base:** mean top-10 overlap 0.61–0.64, top-100 overlap about 0.70. Expect `unjudged10` above 0.15, so pooled judging will be needed.
- **No-text items** do reach the fused top 100 through the new lists (mean 0.06 per search, both arms). They are rankable, but rare.
- **Provisional.** Only the sample is enriched, and it contains the base's top 200, so the new lists can only promote base candidates plus 2,000 random items. Confirm on the full corpus before adopting.

## Projected cost (gemini-3.1-flash-lite, `te-v1c`, one item per call)

| | Standard | Batch API (−50%) | Sync wall time at 8 threads |
| --- | --- | --- | --- |
| Per 1,000 items | $0.356 | $0.178 | 2.5 min |
| Corpus, 20,830 items (21k minus friends) | **$7.4** | **$3.7** | 52 min |
| 100k items | $35.6 | $17.8 | 4.1 h |

For reference, gpt-5-nano with the same prompt costs $0.112 per 1,000 items standard and about $0.056 with Batch. At 21k items that is $2.3 standard and $1.2 batch. It is cheaper, but rejected on quality, as above.

## Deviations from the preregistration and the plan

1. **Pilot spend was $0.18, not ≤ $0.10.**
   - Gemini $0.119: the 200-item pilot, 13 retries at a higher cap, and 40 compact items.
   - Nano $0.059: the pilot was run twice, plus the 8-items-per-call pilot. The first nano run used a validator that dropped strings containing `@handles` (3 rows invalid, 83 strings lost) and did not store raw output. I fixed the validator and re-ran instead of re-validating.
2. **Sample spend was $1.77, not about $0.3.** The preregistered estimate assumed gpt-5-nano with Batch. The chosen model is about 3× nano's price, and the calls were synchronous rather than Batch (halving it would give about $0.89).
3. **The prompt is `te-v1c`, not `te-v1`.** One added line asks for compact JSON. The pilot statistics above are for `te-v1`; `te-v1c` was checked on 40 items: same validity and facet volume, 38% fewer output tokens.
4. **The Gemini output cap is 450 tokens, not 300,** because 5.5% of `te-v1` outputs were cut off at 300.
5. **The sample includes the 3 dev more-like-this example items,** so that the more-like-this enrichment lists have a query.
6. **Extra lists list only items with a positive BM25 score.** The base BM25 lists every item. Dense extra lists are cut at 1,000.
7. **`lib/ai.py`** gained an optional `generation_config` argument on `gemini_json`.
8. **Ledger note.** Another session spent about $0.40 on Gemini while the sample ran. Per-run costs above are filtered by `purpose` and `prompt_version`, not taken from the provider total.
