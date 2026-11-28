# Experiment 23: enrichment prompt te-v2 (hedging and missing kind)

*30 Oct 2026 · Experimenter · aggregates only. No captions, item codes, query texts or scores. Scoring is the evaluator's job.*

## What changed (one variable: the enrichment prompt and its response schema)

te-v2 = te-v1c with three rule changes:

- **(a) `unknown`** names only list fields left as an empty list. kind and vibe are never unknown. audio stays unknown unless a song or sound is named.
- **(b) `kind`** is always picked from the fixed list. `unknown` is removed from the enum, and `other` is for "nothing comes close". A new boolean `kind_uncertain` allows a best guess. A one-line purpose→kind guide was added (the revision below).
- **(c) `vibe`** is always given: 1–3 short mood words (schema `minItems: 1`).

**Unchanged:**
- gemini-3.1-flash-lite, thinkingBudget 0, strict JSON schema, compact one-line JSON, max output 450;
- the te-v1 delimited data block and post-validation;
- friends (`owner_relation == "mutual"`) are never sent;
- every call goes through `lib/ai.py`.

Code: `experiments/methods/enrich_v2.py`. Search: `stack.py --opt hyde=1 --enrich te-v2bh_gemini-3.1-flash-lite`. `stack.py` gained an `--enrich` flag. With the default it still reproduces B2 and B3 exactly (16/16, 1000 deep).

## Deviation: one prompt revision after the first pilot

- **The first draft (`te-v2`) failed its own rule (b).** Kind-known was 0.67 vs te-v1c's 0.65, and `other` rose from 0.285 to 0.33.
- **I revised it once, using pilot output statistics only (no labels), into `te-v2b`.** The revision adds the purpose→kind guide, words `unknown` as "the list fields you left as []", and restores te-v1's audio sentence and "listed in unknown" rule.
- **The sample and the e23 runs use te-v2b.** The draft's 200 pilot rows are kept in `data/enrich/te-v2_*.jsonl`.

## Pilot: 200 items (seed 7, items with text, friends excluded), synchronous, same items for all three

| | te-v1c | te-v2 (draft) | **te-v2b** |
| --- | --- | --- | --- |
| Valid rows | 200/200 | 200/200 | 200/200 |
| Mean output tokens | 130.6 | 125.3 | 127.5 |
| Mean input tokens | 647 | 736 | 896 |
| Cost per 1k items, sync | $0.356* | $0.372 | $0.415 |
| **kind known** (not other/unknown) | 0.650 | 0.670 | **0.885** |
| kind = other / unknown | 0.285 / 0.065 | 0.330 / 0.000 | 0.115 / 0.000 |
| kind_uncertain = true | — | 0.285 | 0.180 |
| vibe filled | 0.895 | 1.000 | 0.995 |
| Any hedge (facet in `unknown` while its field has a value) | 0.655 | 0.475 | 0.495 |
| Hedge: kind / vibe | 0.255 / 0.500 | 0 / 0 | **0 / 0** |
| Hedge: topics / use | 0.140 / 0.295 | 0.365 / 0.130 | 0.330 / 0.190 |
| Hedge: shown / said / people | 0.085 / 0.070 / 0.125 | 0.005 / 0.015 / 0.010 | 0.005 / 0.045 / 0.015 |
| Filled: shown / said / use | 0.640 / 0.605 / 0.640 | 0.365 / 0.580 / 0.365 | 0.385 / 0.690 / 0.330 |
| Unknown rate: kind / vibe / audio | 0.570 / 0.605 / 0.965 | 0 / 0 / 0.995 | 0 / 0 / 1.000 |
| Mean enrichment text (chars) | 317 | 290 | 300 |

\*te-v1c's sync price per 1k items is from experiment 9. Most of its rows were made through the Batch API at half price, so their own row costs average $0.248/1k.

**Spot check for unsupported facts.** 20 pilot items (seed 23), te-v2b vs te-v1c.
- **Blinding:** shown as A/B in random order per item, and the key was revealed after counting.
- **One reader:** the experimenter, so this is not an independent check.
- **What counted as unsupported:** a named thing, person, place or event that the metadata neither states nor clearly implies; a kind the metadata contradicts; or a vibe that contradicts the caption.
- **What did not count:** caption text copied into `said`, and one-level place generalisations.
- **Result: te-v2b 2 facts (2 items); te-v1c 4 facts (4 items).**
  - te-v2b: one kind contradicted (a real sports clip called a skit) and one invented causal claim in a summary.
  - te-v1c: four `shown` details that the metadata does not describe.
- The stop rule (te-v2b > te-v1c + 2) was not triggered.

## Label-independent sample (Gemini Batch API)

**The sample: 5,020 items.**
- The union of B3's top 200 for every dev search over `e20_hyde_b2_r{1,2,3}` is 3,342 items. The experiment-9 set of 2,000 random items (seed 11) adds the rest; 315 items are in both.
- 7 friends were removed.
- The more-like-this example items were **not** added, which follows the experiment definition. Their query-side enrichment text stays te-v1c.
- 43 sample items already had te-v2b rows from the sync pilot. These were reused; same prompt and config.

| | Value |
| --- | --- |
| Jobs | 2 (3,000 + 1,977 requests); job wall 135 s and 125 s; script wall 155 s |
| Valid | 4,959 / 4,977 (99.6%). All 18 invalid rows have an empty `queries` list after validation; those items fall back to te-v1c |
| Tokens per item | 891 in / 132.9 out |
| Cost | **$1.0506** batch = **$0.211 per 1k items** (te-v1c $0.178/1k batch: +19%, from the longer system prompt) |
| Projected full corpus (≈20.8k non-friend items) | ≈ $4.4 batch / ≈ $8.6 sync |

**Sample aggregates** (5,002 items with an ok row in both te-v2b and te-v1c):

| | te-v1c | te-v2b |
| --- | --- | --- |
| kind known | 0.712 | **0.894** |
| kind other / unknown | 0.225 / 0.063 | 0.106 / 0.000 |
| kind_uncertain = true | — | 0.115 |
| vibe filled | 0.846 | 0.995 |
| Any hedge | 0.576 | 0.593 |
| Hedge: kind / vibe | 0.213 / 0.423 | **0 / 0** |
| Hedge: topics / use | 0.079 / 0.289 | 0.271 / 0.362 |
| Hedge: shown / said / people | 0.051 / 0.067 / 0.083 | 0.012 / 0.055 / 0.047 |
| Filled: shown / said / use | 0.509 / 0.581 / 0.692 | 0.678 / 0.660 / 0.551 |
| Unknown rate: audio / place | 0.892 / 0.751 | 0.943 / 0.777 |
| Mean enrichment text (chars) | 322 | 323 |

**Reading the aggregates:**
- **(b) kind and (c) vibe are fixed.** Kind is known on 89% of items instead of 71%, and vibe is present on 99.5%. Kind and vibe are no longer hedged.
- **(a) is only partly met.** The model still lists `topics`, and more often `use`, in `unknown` while also filling them. Overall hedging is flat (0.59 vs 0.58). This affects only the `unknown` field, which search does not use (`enrich_text` indexes the summary, a known kind and the list fields).
- **Other side effects:**
  - On the sample, shown and said are filled more often and `use` less often.
  - On the pilot, shown and use were filled less often.
  - The text length is unchanged.

## Hybrid index and runs

- **Index `te-v2bh_gemini-3.1-flash-lite`: 20,829 items.**
  - 5,002 sample items have te-v2b text and new bge-small vectors (embedded at 17.2 items/s, 291 s).
  - The 18 invalid sample items keep te-v1c.
  - All others keep their te-v1c text and the te-v1c vectors byte for byte. Checked: 0 text or vector differences outside the sample, and the same id set.
- **Runs:** `data/runs/e23_tev2_r{1,2,3}.json` = B3 (`--opt hyde=1`, qr-v1 r{k}) with that index. Query cost and latency are unchanged: p50 0.42–0.47 s, rewrite cost as B3.
- **Top-10 overlap with B3:** a mean of 0.73 / 0.71 / 0.69 per repeat (a check on the ranking only, not a score).

## Caveats for the evaluator

- **Only the sample changed.** Items outside B3's top 200 cannot gain from te-v2b text, so a full-corpus te-v2b pass could differ in either direction.
- **The sample is defined from B3's own top 200.** The rankings it touches are the ones the dev searches already retrieve.
- **A wider kind vocabulary has a cost.** Experiment 9's reference check found that when te-v1c gave a kind, it contradicted MU 8% of the time. te-v2b now guesses a kind on 18 more items in 100, 11.5% of them flagged uncertain. Uncertain kinds are indexed like certain ones.
- **The spot check is small and not independent.** It has one reader (the builder) and n = 20.

## Cost (ledger, this experiment)

| Item | Cost |
| --- | --- |
| Pilot te-v2 (draft), sync | $0.0744 |
| Pilot te-v2b, sync | $0.0831 |
| Sample te-v2b, batch | $1.0506 |
| **Total** | **$1.208 (Gemini)** |
| OpenAI | $0 |
