# Round 6 · what the experimenter built and ran

*7 Nov 2026 · Experimenter (builder) · no scores. The experimenter saw no labels, no `eval_work/`, no `runs/final*/`, no `runs/rewrites/test*/` and no per-search scores. This note has no captions, titles, search texts or search ids. Preregistration: the "Round 6 fixed parameters" block and rows Y6-G1 … Y6-G5 in `LOG.md`, committed in `0f964a6` before any paid call or run.*

Code:
- `experiments/methods/c6_lib.py`: cached qr-v1 calls (`cached_chat`, `rewrite_one`), G3's text-only `hard` rule, 3-large vectors (`embed_3l`, `QueryVecs3L`, `swap_to_3l`), and the keyword-Jaccard variability measure;
- `c6_rewrite.py`: the pilot and the 3-repeat rewrite runs;
- `c6_embed.py`: the view check and the 3-large re-embedding of every item;
- `c6_search.py`: configs `c0chk` and `g1`–`g5`, run files with cost and latency in `meta`, plus `--variability`.

**Reproduction.** The round-6 runner, given C0's inputs (cached gpt-5-nano qr-v1, 3-small 512 d), reproduces `r4.2/c0x_r{1,2,3}` exactly: 55 of 55 rankings, 1,000 deep, in all three repeats. These control files are in `data/all/tmp/r6_checks/` and are not for scoring. They supply the C0 latency row below.

## Runs written (`data/all/runs/r6/`, 15 files)

All runs cover `dev` (44) + `yt_holdout` (11) = 55 searches (47 typed, 8 more-like-this), with 3 repeats each. Repeat k of a new model is an independent sample (cache salt = k). The qr-v1 prompt, its few-shot pairs, its strict schema and `post_validate` are identical in every arm.

| Runs | Variable vs C0 | Rewrite | Vectors |
| --- | --- | --- | --- |
| `g1_r*` | rewrite model | gpt-5.4-mini, reasoning `none` (its lowest) | 3-small 512 d |
| `g2_r*` | rewrite model | gpt-5.5, reasoning `low` | 3-small 512 d |
| `g3_r*` | escalation | gpt-5-nano (C0's), or gpt-5.4-mini (G1's call) on hard searches | 3-small 512 d |
| `g4_r*` | embedding model | gpt-5-nano (C0's) | **3-large 1,024 d** |
| `g5_r*` | G4 + G1 (fixed in LOG before any run) | gpt-5.4-mini (G1's) | 3-large 1,024 d |

More-like-this searches never use the rewrite, so in G1–G3 they equal C0. In G4/G5 they use the 3-large item vectors, and outside-library examples are embedded with 3-large too.

The paired base is `runs/r4.2/c0x_r*`.

## Models and prices

All prices are list prices per million tokens, checked on 7 Nov 2026 and recorded in `lib/ai_prices.json` with their sources.

| Model | Input | Cached input | Output | Source | Reasoning setting used |
| --- | --- | --- | --- | --- | --- |
| gpt-5-nano (C0) | $0.05 | $0.005 | $0.40 | entry from 30 Oct | `minimal` |
| gpt-5.4-mini | $0.75 | $0.075 | $4.50 | developers.openai.com/api/docs/models/gpt-5.4-mini | `none` ("none (default), low, medium, high, xhigh") |
| gpt-5.5 | $5.00 | $0.50 | $30.00 | developers.openai.com/api/docs/models/gpt-5.5 (no batch price listed; > 272K-token prompts cost more, never reached here) | `low` |
| text-embedding-3-large | $0.13 | — | — | developers.openai.com/api/docs/models/text-embedding-3-large | `dimensions=1024` |
| text-embedding-3-small (C0) | $0.02 | — | — | entry from 30 Oct | `dimensions=512` |

- gpt-5.5 is not in the main pricing page's Flagship table any more (that table lists the gpt-6.x models), but it is available on this account, and its model page calls it "a flagship model".
- **G2 rule.** The pilot (4 invented searches; outputs unused) projected $1.68 for 141 gpt-5.5 calls. Together with the rest of the plan, the projected round total was ≈ $2.5, under the preregistered $2.85, so gpt-5.5 ran. gpt-6.1-sol, the fallback, was not needed.
- The ledger books every call at the uncached input price. Both stronger models report prompt-cache hits on the shared ~1,000-token system + few-shot prefix (`cached_tokens` is logged in `cache/r6/qr-v1.jsonl`), so real billing is lower than the figures here.

## Rewrite calls

| Model | Calls (3 × 47) | Cost | Per call p50 / p95 | Mean tokens in / out (reasoning) |
| --- | --- | --- | --- | --- |
| gpt-5-nano (C0, cached from round 4.1) | 141 | $0.0167 | 1.45–1.49 / 2.04–2.37 s | 1,068 / 163 (0) |
| gpt-5.4-mini | 141 | $0.2081 | 1.37–1.52 / 1.52–1.92 s | 1,068 / 150 (0) |
| gpt-5.5 | 141 | $1.5993 | 3.63–3.98 / 5.35–5.60 s | 1,068 / ~200 (30–32) |

## Escalation (G3)

- The rule is H1 (≤ 2 content words), H2 (vague-reference words) or H3 (wrapper or request words). It was fixed in LOG.md before it was computed on any eval search.
- **It marks 26 of 47 typed searches as hard: an escalation rate of 55%.** The rule reads only the query text, so the rate is the same in every repeat.
- Reasons fired (a search can match several): H1 12, H2 11, H3 11.
- **Booked as specified** (nano always, then mini on hard searches, in sequence): $0.94 per 1k searches; latency p50 3.07–3.18 s, p95 3.86–4.18 s.
- **Routed variant** (mini only on hard searches, nano on the rest): the rankings are identical, because the decision does not need nano's output. It costs $0.87 per 1k; latency p50 1.85–1.94 s, p95 2.20–2.43 s. Both are in each `g3` run's meta (`escalation`, `routed_variant`).

## Embedding job (G4)

**View check.** I re-embedded 200 random items' views with 3-small 512 d and compared them with the stored `oai512` vectors: cosine min 0.9998, mean 1.0000. This confirms the 3-large vectors are of the same texts.

**Dimension: 1,024.** The API price does not depend on dimension, so the choice is about memory and speed:
- the float16 store is 248 MB, and about 0.5 GB in float32 in memory;
- 3,072 d would be about 1.5 GB in float32, plus transient copies, on a 7 GB machine;
- local search time rises by only about 0.05 s (table below).

**Build:**

| | Value |
| --- | --- |
| Items | 121,169 (same ids and order as `oai512`) |
| Tokens | 4,012,574 |
| Cost | **$0.5216** ($0.0043 per 1k items) |
| Calls | 243 × 500 texts, synchronous, 2 workers |
| Wall time | **171.5 s** (709 items/s overall) |
| Store | `corpus/emb/oai3l_1024/` (emb.npy 248 MB float16; resumable chunks kept beside it) |
| Query vectors | `corpus/emb/oai3l_1024_queries/` (1,701 strings, $0.003) |

The Batch API was not used: OpenAI's pages state no batch price for text-embedding-3-large, and the rules forbid guessing a price.

## Latency and cost per arm

Typed searches only; ranges are over the 3 repeats.
- **Total** = local search + the rewrite call(s), at their original uncached seconds, + one live query-embedding call for that search's strings.
- The embedding call is timing only; its vectors are not used. Because of it, the C0 row here (≈ 1.9 s p50) is about 0.3 s slower than round 4's figure, which left the embedding out.

| Arm | Local p50 / p95 | Query-embed call p50 / p95 | **Total p50 / p95** | Rewrite $/1k | Query-embed $/1k | **Total $/1k searches** |
| --- | --- | --- | --- | --- | --- | --- |
| C0 (control) | 0.12 / 0.16 s | 0.30–0.32 / 0.39–0.41 s | **1.91 / 2.52–2.84 s** | $0.119 | $0.0019 | **$0.120** |
| G1 mini | 0.12 / 0.14–0.15 s | 0.30–0.32 / 0.39–0.44 s | **1.80–1.99 / 2.07–2.33 s** | $1.476 | $0.0018 | **$1.48** |
| G2 gpt-5.5 | 0.12–0.13 / 0.15–0.16 s | 0.32–0.34 / 0.39–0.54 s | **4.18–4.40 / 5.81–6.04 s** | $11.34 | $0.0021 | **$11.34** |
| G3 escalation (as specified) | 0.12 / 0.15–0.16 s | 0.32 / 0.39–0.41 s | **3.07–3.18 / 3.86–4.18 s** | $0.938 | $0.0018 | **$0.94** |
| G3 routed (same rankings) | — | — | 1.85–1.94 / 2.20–2.43 s | $0.872 | $0.0018 | $0.87 |
| G4 3-large | **0.18 / 0.21–0.24 s** | 0.33–0.34 / 0.39–0.46 s | **1.98–2.02 / 2.78–2.89 s** | $0.119 | $0.0121 | **$0.131** (+ $0.0043 / 1k items once) |
| G5 3-large + mini | 0.17–0.18 / 0.20–0.21 s | 0.32–0.34 / 0.39–0.41 s | **1.87–2.02 / 2.07–2.55 s** | $1.476 | $0.0119 | **$1.49** |

Building the combined index takes 10.8 s. Swapping in the 3-large store takes 1.6 s more.

## How much the rewrites vary across repeats

The measure: for each search, the Jaccard of the post-validated keyword sets between each pair of repeats (3 pairs), averaged over the pairs; then the mean over the 47 typed searches. The phrase-words row is the same statistic over the non-stopword words of all phrases.

| Rewrite | **Keyword Jaccard, mean** (p25–p75) | Hard searches only (26) | Other searches (21) | Phrase-words Jaccard |
| --- | --- | --- | --- | --- |
| gpt-5-nano (C0, G4) | **0.280** (0.20–0.34) | 0.282 | 0.278 | 0.358 |
| gpt-5.4-mini (G1, G5) | **0.469** (0.36–0.56) | 0.487 | 0.447 | 0.442 |
| gpt-5.5 (G2) | **0.556** (0.44–0.65) | 0.498 | 0.627 | 0.496 |
| G3 composite | **0.393** (0.28–0.54) | (mini) | (nano) | 0.426 |

- No search has identical keyword sets across all three repeats in any arm.
- Both stronger models agree with nano's keywords only weakly in the same repeat: Jaccard 0.23 for mini and 0.20 for gpt-5.5. Their parses are substantively different, not just more stable.
- Mean keywords per parse after post-validation: nano 7.6, mini 6.8, gpt-5.5 7.6. Every parse has 3 phrases.
- Nano sets a date or interaction filter in 52 of 141 parses, mini in 15 and gpt-5.5 in 12. This has **no effect on any ranking**: the C0 search applies the search's own `filters` from `queries.jsonl`, never the rewrite's.

## Label-free diagnostics (method side only)

| Arm | Searches whose top 10 differs from `c0x` (per repeat) | Mean top-10 overlap with `c0x` | Other platform's share of top 10: `ig_` / `yt_` searches |
| --- | --- | --- | --- |
| C0 | 0 | 1.00 | 0.45–0.47 / 0.24–0.26 |
| G1 | 47 | 0.65–0.68 | 0.41–0.47 / 0.24–0.27 |
| G2 | 47 | 0.61–0.64 | 0.47–0.50 / 0.25–0.29 |
| G3 | 26 | 0.82–0.85 | 0.44–0.49 / 0.23–0.28 |
| G4 | 55 | 0.66 | 0.46–0.47 / **0.19–0.21** |
| G5 | 55 | 0.50–0.54 | 0.41–0.49 / 0.22–0.23 |

- G4 changes every search's top 10, the more-like-this searches included.
- G4 puts fewer Instagram items into `yt_` searches than C0 does. This is a property of the vectors, not a quality claim.
- G1–G3 leave the more-like-this searches exactly as C0.
- Expect a sizeable pool of unjudged top-10 items: about a third of each top 10 is new in G1, G2 and G4, and about half in G5.

## Spend (ledger `data/all/ai_runs.jsonl`, OpenAI only, no Gemini)

| Step | Calls / items | Cost |
| --- | --- | --- |
| Pilot (4 invented searches × 2 models) | 8 | $0.047 |
| gpt-5.4-mini rewrites | 141 | $0.208 |
| gpt-5.5 rewrites | 141 | $1.599 |
| 3-large item vectors | 121,169 items | $0.522 |
| 3-large query / HyDE / outside-example vectors | 1,701 strings | $0.003 |
| 3-small vectors of new rewrite strings | 1,613 strings | $0.0005 |
| Latency timing calls (both embedding models) | 846 calls | $0.0045 |
| View check | 200 | $0.0002 |
| **Round 6 total** | | **$2.385** (under the $3 round cap) |

OpenAI total is now **$2.578 of $9.50**, leaving $6.92. Gemini is unchanged at $3.776. The ledger total is $6.354.

## Deviations and rule notes (honest record)

1. **gpt-5.5 connection reset.** One gpt-5.5 call (repeat 1) died with a connection reset mid-response. It was never logged, so the ledger may undercount by one call (≤ about $0.012). A retry on network errors was added to `cached_chat`, and the run resumed from the cache (3 new calls in repeat 1). No parse differs from what a clean run would have written.
2. **gpt-5.5 reasoning tokens.** The pilot showed 0 reasoning tokens at `low`; the real runs used 30–32 on average. `max_completion_tokens` was 4,000 for gpt-5.5 (transport only, preregistered), and no output was truncated.
3. **Latency now includes a live query-embedding call.** That makes these totals not directly comparable with earlier rounds' `typed_query_plus_rewrite`. The C0 control row is the comparison.
4. **G3 booking.** G3's main cost and latency are booked as specified (nano, then mini). The routed figures give the same rankings at lower cost and latency.
5. **Concurrent jobs.** The rewrite and embedding jobs ran at the same time. Only an early reproduction check overlapped them, and its files were overwritten. The final run files were written after both jobs had ended, so their `new_spend_this_run_usd` is clean (timing calls only).
6. **No eval text was read or printed.** The hard rule was run over query texts (counts only). The pilot searches were invented and written into LOG.md before any call.
