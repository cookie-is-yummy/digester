# Experiment 9b: tier-1 text enrichment on the full corpus (method note)

*30 Oct 2026 · Experimenter · aggregate numbers only, no content. Scores are for the evaluator.*

Experiment 9 was adopted provisionally on a 4,979-item sample. Experiment 9b enriches every remaining non-friend item with the same prompt, model, generation config and validation, and reruns experiment 9's two arms unchanged on the full index.

## What changed (transport and build only)

- **`methods/enrich_batch.py`** (new). This is the same request as `enrich_items.py` (`te-v1c`, gemini-3.1-flash-lite, `thinkingBudget` 0, strict `responseJsonSchema`, max output 450, same `validate()`). The only change is the transport: it is sent through the **Gemini Batch API** (`batchGenerateContent`, inline requests, 3,000 per job, item code as `metadata.key`).
  - Rows are appended to the same `data/enrich/te-v1c_gemini-3.1-flash-lite.jsonl` in the same format, plus a `batch` field.
  - It is resumable. Jobs are kept in `data/enrich/batch_jobs_te-v1c_gemini-3.1-flash-lite.json`, and a rerun polls pending jobs and never resubmits them.
  - Before each submit it checks the worst-case estimate (input from chars / 3.5, output at the full 450 cap, batch prices) against the cap minus a $1 reserve.
- **`lib/ai.py`** gained `gemini_batch_create()`, which refuses a job unless `spent + estimate <= budget`, and `gemini_batch_get()`. Existing functions are unchanged. Usage of each completed job is logged with `ai.log_batch` at the `batch_*` prices (purpose `enrich_all_batch`).
- **`methods/e9_enrich_search.py`:**
  - `--build --full` builds over every valid row; the default is still the sample.
  - Embedding runs in length-sorted order, in resumable 1,024-item chunks.
  - Run `meta` now says `coverage` (full) instead of `provisional`, and gives the batch-row cost separately.
  - The search code is unchanged.
- **Backups:** `text_te-v1c_gemini-3.1-flash-lite_sample.json` and `emb_te-v1c_gemini-3.1-flash-lite_sample/`.

## Privacy

- **Friends excluded: 463 items.** These are items whose creator is a mutual follow. They were removed by `select("all")` before anything else, and never sent.
- **Fields sent:** the same delimited data block as experiment 9 (caption ≤ 1,000 chars, extra hashtags, creator handle/name, media kind, collection names).
  - Collection names are the user's own data. Sending them is the product deviation already noted for experiment 9.

## Enrichment

| | Value |
| --- | --- |
| Non-friend items | 20,830 (21,293 minus 463 friends) |
| Already enriched (exp 9 sample + 40 compact pilot) | 5,007 rows |
| Sent through Batch | **15,823**: a 100-item pilot job, then 6 jobs (5 × 3,000 + 723) |
| Valid on first attempt (batch) | **15,794 / 15,823 = 99.82%** |
| Batch failures | 29, none truncated (out tokens 93–151). 28 omitted `queries` despite the schema requiring it; 1 had its summary emptied by the validator. |
| Sync retries (max output 450) | 32 calls, 2 rounds, **$0.0139**. These were the 29 above plus the 1 sample failure; the 2nd round retried the 2 still failing. |
| **Enriched in total** | **20,829 / 20,830 (99.995%)**. The 1 left is the sample's item that never returns a candidate (probably a safety block); it stays unenriched. |
| Items without text, enriched | 1,061 |
| Strings dropped by the validator | 6 batch rows |

**Batch pilot (100 items).**
- 100/100 valid.
- 644 input and 134 output tokens per item, the same as the synchronous sample (647 / 130).
- `usageMetadata` is returned per response, and responses come back in request order with `metadata.key` echoed.
- Job wall time was 165 s.

**Main batch (15,723 items, 6 jobs submitted together).**
- Wall time from the first submit to the last collection: **309 s (51 items/s)**.
- Single job wall times ranged from 106 s to 262 s (11–28 items/s per job); the queue never took hours.
- Polling every 60 s; requests were 12.4–12.8 MB inline per 3,000-item job, under the 20 MB limit.

**Facet coverage, all 20,829 items** (the sample was biased toward the base's top results):
- `kind` known (not other or unknown): 64% (sample 75%).
- Share of items with text whose `unknown` lists each facet:

  | shown | said | audio | place | people | vibe | use | kind | topics |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | 0.43 | 0.34 | 0.96 | 0.73 | 0.29 | 0.64 | 0.63 | 0.62 | 0.15 |

- Sensitive tag: health 480, relationships 241, money 167 (4.3% of items).

## Cost (ledger)

| | Items | In / out tokens | Cost | Per 1,000 items |
| --- | --- | --- | --- | --- |
| **9b batch** (pilot + 6 jobs) | 15,823 | 10.11M / 2.10M (639 / 133 per item) | **$2.841** | **$0.180** |
| 9b sync retries | 32 calls | 28k / 4.5k | $0.014 | — |
| **9b total** | | | **$2.855** | |
| Same tokens at standard price | | | $5.68 | $0.359 |
| Exp 9 sample, synchronous (for reference) | 4,968 | 3.21M / 0.64M | $1.770 | $0.356 |

- **Batch halves the cost exactly**, as listed. The preregistered estimate was about $2.8.
- **Whole corpus, as done:** $1.77 sample (sync) + $2.86 (batch) ≈ **$4.6**.
- **All batch** would cost about **$3.75** for 20,830 items. At 100k items that is about $18 in batch and about $36 at standard price.
- The ledger is a list-price estimate and has not yet been checked against the Gemini billing page.

## Index build (local, $0)

- **Enrichment text:** 20,829 items, mean 312 chars.
- **bge-small** (fastembed, 4 CPU threads), length-sorted: **17.7 items/s, 1,175 s** for 20,829 texts. The sample build ran unsorted at 12.7 items/s.
- **Vectors check:** for the 4,978 sample items, the vectors match the old sample build exactly (cosine 1.000), and the texts are identical.

## Storage per item

| | Bytes |
| --- | --- |
| Enrichment search text (UTF-8, mean) | 326 (399 in the JSON file, with its key) |
| bge-small vector, 384 d, f16 | 768 (1,536 as f32) |
| **Text + vector** | **≈ 1.1 KB** (about 23 MB for this corpus, about 110 MB at 100k items) |
| Full enrichment row (all facets, tokens, raw model object; rebuild source) | 1,388 |

## Runs (dev, 16 searches, 3 rewrite repeats)

| Run file | Arm |
| --- | --- |
| `data/runs/e9b_full_r{1,2,3}.json` | Main arm of experiment 9 (base + enrichment BM25 + enrichment dense), full index |
| `data/runs/e9b_full_bm25only_r{1,2,3}.json` | Base + enrichment BM25 only |

- **Base reproduced.** With the extras off (`--arms none`), all 16 dev searches in all 3 repeats are identical to `e1_rewrite_r{1,2,3}`, 1,000 deep.
- **Query latency p50:**

  | Arm | p50 |
  | --- | --- |
  | Main | 0.23–0.29 s |
  | BM25 only | 0.15–0.18 s |
  | Base, same machine | 0.18–0.21 s |

- **Mean overlap, label-free:**

  | Arm | Top 10 with base | Top 100 with base | Top 10 with the sample-index run |
  | --- | --- | --- | --- |
  | Main | 0.59–0.63 | 0.66–0.68 | 0.89–0.92 |
  | BM25 only | 0.63–0.68 | 0.73 | 0.94–0.96 |

  - Some new items will need judging: expect `unjudged10` to be up to about 0.1 above the r4 runs.
- **Items without a caption vector** in the fused top 100: mean 0.56–1.12 per search for the main arm and 0–0.25 for BM25 only, against 0.06 on the sample index.

## Deviations

1. **Container restart.** The first full embedding build was killed by a container restart, and about 15–20 min of CPU was lost.
   - All batch jobs had already been collected, so nothing was resubmitted or paid twice.
   - The build is now resumable in chunks and was rerun once.
2. **The 29 batch outputs that failed validation were not truncated.** They were schema violations: a missing `queries` key or an empty summary. The brief expected truncation. They were retried synchronously at 450 as asked.
3. **`e9_enrich_search.py` now writes the full build** to the same `text_`/`emb_` names, so rerunning the experiment 9 sample runs would now use the full index. To reproduce the sample runs, use the `_sample` backups.
4. **`enrich_cost_per_1k_items_usd` in the run meta** averages sample (standard-price) and batch rows, so it reads $0.222. Use the table above for the batch versus standard comparison.
