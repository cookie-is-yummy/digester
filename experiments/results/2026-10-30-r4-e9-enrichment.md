# Round r4: experiment 9, tier-1 LLM text enrichment

Evaluator round r4, 2026-10-30. Split: **dev** (16 searches). Aggregates only.

The base is the honest base: the real gpt-5-nano rewrite (qr-v1), three repeats `e1_rewrite_r{1,2,3}`. Experiment 9 has two arms with three runs each, and repeat k is scored against base repeat k.

- **Main arm** (`e9_enrich_r{1,2,3}`): the base plus two extra RRF lists, one BM25 over the enrichment text and one bge-small vector over the enrichment text.
- **Secondary arm** (`e9_enrich_bm25only_r{1,2,3}`): the base plus the enrichment BM25 list only.

**Provisional result.** Only a label-independent sample of **4,979 items** is enriched. The sample is:

- the union of the base's top 200 for every dev search, across the three rewrite repeats;
- 2,000 random items;
- the 3 more-like-this example items;
- minus friends' items.

So the new lists can mostly promote items the base already retrieves, plus random items. On the full corpus, every item would carry enrichment text, which could add both new finds and new false matches. **A full-corpus run is needed to confirm.**

## How to read these numbers

- **nDCG@10** is the mean over the three repeats. Its CI is a bootstrap over searches of each search's repeat-averaged nDCG@10.
- **Δ** is computed per search: the paired difference is averaged over the three repeats first, then the mean is taken over searches. Its CI is a 2,000-sample bootstrap over searches.
- **W/L/T** counts searches whose Δ is above +0.005, below −0.005, or in between.
- The scores come from `experiments/eval/score_multi.py`.

## Labels

- **Before pooling (r3 labels), the main arm was over the threshold.** Its `unjudged10` was 0.150 / 0.163 / 0.144 across the repeats (repeat 2 > 0.15). The secondary arm was at 0.138 / 0.144 / 0.113.
- **I pooled all six runs into one pool** (every unjudged top-10 item): **60 items**, 7 of them on more-like-this lines.
- **Judging was blind and saw no enrichment text.** I built the sheet without `--extra`, so every item was judged from its caption, hashtags and creator only, and the LLM-written enrichment could not sway a grade.
  - For more-like-this lines, I judged against the example items in `queries.jsonl`.
  - Conventions from earlier rounds were kept. Stovetop recipes are 0 for "instant pot", graduation-only and non-European travel items are 0 for the Europe search, and sound-design and novelty-music items are 1 for "musical ear scratchers".
- **Grades 2 / 1 / 0 = 2 / 16 / 42.** They were merged as **r4** (judge `claude-evaluator-r4`), and the backup is `data/evals/labels/evalset.pre_r4.jsonl`.
  - One grade was changed after the first merge to match the ear-scratchers convention. I did this by restoring the backup, removing the 60 log lines and merging again, so each r4 judgment appears once.
- **After the merge, `unjudged10` is 0.00** for all six runs and for the three base repeats.
- I did not read the Muse export, the Muse reports, the Muse eval scripts, the method code or the method note before judging.

## Base on r4 labels

**Honest base: nDCG@10 0.491** [0.386, 0.600], repeats 0.497 / 0.507 / 0.470. This is unchanged from r3.

| P@10 | MRR | R@100 | success@5 | unjudged10 |
| --- | --- | --- | --- | --- |
| 0.617 | 0.821 | **0.496** (0.495–0.499) | 0.896 | 0.00 |

Single-answer group:

| nDCG@10 | MRR | R@100 |
| --- | --- | --- |
| 0.333 | 0.470 | 0.667 |

R@100 rises from 0.491 to 0.496 because some newly judged relevant items sit inside the base's top 100.

## Experiment 9 (r4 labels)

| Arm | nDCG@10 mean (range) [CI] | Δ vs base [paired 95% CI] | W/L/T | Δ per repeat | P@10 | MRR | R@100 | success@5 | unjudged10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Base | 0.491 (0.470–0.507) [0.386, 0.600] | — | — | — | 0.617 | 0.821 | 0.496 | 0.896 | 0.00 |
| **Main (BM25 + dense)** | **0.551** (0.536–0.564) [0.431, 0.666] | **+0.060 [+0.019, +0.103]** | **13/2/1** | +0.056 / +0.057 / +0.065 | 0.673 | 0.852 | 0.509 | 0.979 | 0.00 |
| BM25 only | 0.538 (0.522–0.551) [0.418, 0.651] | +0.046 [+0.016, +0.084] | 12/3/1 | +0.054 / +0.033 / +0.051 | 0.650 | 0.841 | 0.514 | 0.938 | 0.00 |

R@100 Δ vs base:

| Arm | Δ R@100 [95% CI] | W/L/T | Δ per repeat |
| --- | --- | --- | --- |
| Main | +0.013 [−0.003, +0.029] | 8/4/4 | +0.024 / +0.005 / +0.009 |
| BM25 only | +0.017 [+0.004, +0.032] | 9/1/6 | +0.018 / +0.017 / +0.017 |

The preregistered expectation was +0.02..+0.05 nDCG@10 and +0.03..+0.08 R@100. nDCG@10 lands above that range. R@100 lands below it, which fits a sample that mostly contains items the base already retrieves.

**Head to head, main minus BM25-only:** Δ nDCG@10 +0.013 [−0.011, +0.036], 10/6/0; Δ R@100 −0.004 [−0.013, +0.005]. The dense enrichment list adds a little precision, but the CI includes 0.

**Before pooling (r3 labels):** the per-repeat Δ was +0.036 / +0.032 / +0.045 for the main arm and +0.039 / +0.019 / +0.040 for BM25-only. Pooling raised both arms: of the new items, 18 of 60 were relevant, and the enrichment arms rank them in their top 10.

## By search kind (r4 labels, mean over repeats)

Counts are in brackets. Kinds with n = 1 are anecdotes. Searches can have several kinds.

| Kind | Base nDCG@10 | Main | BM25 only | Base R@100 | Main | BM25 only |
| --- | --- | --- | --- | --- | --- | --- |
| topic (5) | 0.439 | **0.544** | 0.493 | 0.537 | 0.568 | 0.570 |
| name (3) | 0.556 | **0.600** | 0.585 | 0.625 | 0.629 | 0.625 |
| more_like_this (3) | 0.645 | 0.693 | **0.696** | 0.433 | 0.425 | 0.440 |
| audio (1) | 0.058 | 0.057 | 0.017 | 0.500 | 0.500 | 0.500 |
| people (1) | 0.620 | 0.835 | 0.840 | 0.381 | 0.415 | 0.442 |
| place (1) | **0.513** | 0.374 | 0.491 | 0.173 | 0.190 | 0.194 |
| said_shown (1) | 0.662 | 0.717 | 0.669 | 0.750 | 0.750 | 0.750 |
| vibe (1) | 0.210 | 0.236 | 0.275 | 0.279 | 0.286 | 0.286 |

- **The gain is broad.** It shows in the topic, name and more-like-this kinds (≥ 3 searches each). Experiments 2–8 left more-like-this unchanged; this one moves it.
- **The one place search drops** in the main arm (−0.14), and less in BM25-only. With n = 1 this is an anecdote, but it is worth checking on the full corpus. Place facets were `unknown` for 74% of enriched items.
- **Audio does not improve.** That is expected: enrichment is text-only and has no audio input.

## Single-answer group (r4 labels)

The group is three searches, scored as one group.

| | nDCG@10 | MRR | R@100 |
| --- | --- | --- | --- |
| Base | 0.333 | 0.470 | 0.667 |
| Main | **0.376** | **0.542** | 0.667 |
| BM25 only | 0.343 | 0.488 | 0.667 |

Unlike experiments 2–8, which all lowered this group, enrichment **raises** it.

## Cost and latency (from run `meta` and the method note)

| | Main | BM25 only |
| --- | --- | --- |
| Enrichment model | gemini-3.1-flash-lite, `te-v1c`, one item per call | same |
| Per 1,000 items | $0.356 standard / $0.178 Batch | same |
| Full corpus (20,830 items, excluding friends) | ~$7.4 standard / ~$3.7 Batch, one-off, plus new items as they arrive | same |
| Dense embedding of enrichment | local bge-small, ~28 min CPU for the corpus, $0 | — |
| Query p50 (base 0.22–0.24 s) | 0.27–0.34 s (**+~0.1 s**) | 0.22–0.27 s (+~0.01 s) |
| Per-search cost | as base (~$0.12 per 1k searches for the rewrite) | as base |
| Sample spend in this experiment | $1.77 (4,978 items) | shared |

**Gain per dollar per 1,000 items** is Δ nDCG@10 divided by the enrichment cost per 1,000 items:

| Arm | Standard | Batch |
| --- | --- | --- |
| Main | +0.060 / $0.356 = **0.17 nDCG@10 per $ per 1k items** | 0.34 |
| BM25 only | +0.046 / $0.356 = 0.13 | 0.26 |

Per corpus dollar, the main arm gives about +0.008 nDCG@10 per $1 at standard prices ($7.4) and about +0.016 per $1 with Batch ($3.7). Both arms pay the same enrichment cost. The dense list costs only local CPU and about 0.1 s of query time.

## Verdict

The adoption rule: Δ ≥ 0.03 with the paired 95% CI above 0, or Δ ≥ 0.02 with W > L and no extra cost. This experiment has an extra per-item cost, so only the first clause applies.

| Arm | Verdict | Reason |
| --- | --- | --- |
| **Main (BM25 + dense)** | **Adopt, provisionally** | Δ +0.060 ≥ 0.03, CI [+0.019, +0.103] above 0, 13 W / 2 L, positive in all three repeats. Confirm with a full-corpus enrichment run before it becomes the new base. |
| BM25 only | Passes the rule, not preferred | Δ +0.046 [+0.016, +0.084], 12 W / 3 L. Lower than the main arm (head-to-head +0.013, CI includes 0), but it is the fallback if the +0.1 s or the second index is unwelcome. It has the better R@100 and place score. |

**Caveats.**

- **The sample is biased toward the base's candidates.** Only 4,979 items are enriched, and they include the base's top 200 for every dev search. On the full corpus, about 16k more items get enrichment text, which can bring both new relevant items and new false bridges. The Δ could shrink or grow, so the result is provisional until a full-corpus run.
- **Small label set.** 16 dev searches; per-kind rows with n = 1 are anecdotes.
- **Pooling raised the Δ.** Of the 60 pooled items, 18 were judged relevant. The pre-pool Δ on r3 labels was about +0.03 to +0.04.
- **Product deviation (from the method note).** Collection names, which are the user's own data, are sent to the LLM in this experiment. A shared content-level enrichment cache must not hold them. Friends' items are never sent.
