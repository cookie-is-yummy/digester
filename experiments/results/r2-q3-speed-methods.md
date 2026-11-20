# Round 2 · Q3 speed: methods, timings and costs (experimenter note, no scores)

Experiments 30–34 (preregistered in `LOG.md` before any run). This note covers method details, latency, cost and label-free overlap only. Quality (dev nDCG@10) comes from the evaluator. The chart is drawn by `methods/speed_chart.py` from `results/r2-q3-speed-p95.json` once `ndcg10` is filled in.

**Setup.** A 4-vCPU container shared with the Q2 experimenter, so the 1-minute load was 1–4 during timing and the search timings are slightly pessimistic. Searches were timed warm in one process after an untimed pass. Rewrite calls were timed end to end through `lib/ai.py`, including retries (there were no retries). Each call opens a new HTTPS connection through the agent proxy. **Spend for all of Q3: $0.083** (Gemini $0.058, OpenAI $0.025).

## Network floor

A trivial JSON call ("ping", ≤ 32 output tokens) from this container, interleaved with the rewrite calls:

| Provider (ping model) | n | p50 | p95 |
| --- | --- | --- | --- |
| Gemini (gemini-3.1-flash-lite) | 30 | 0.88–0.90 s | 1.12–1.31 s |
| OpenAI (gpt-6-luna, reasoning none) | 15 | 1.01 s | 1.35 s |

**About 0.9 s of every rewrite call here is connection and provider overhead, not generation.** From this container, no synchronous LLM call can meet a 0.5 s p95. A production server with warm keep-alive connections in the provider's region would have a lower floor. We did not measure it; it is the next thing to measure before ruling out a fast rewrite.

## Arms and timings (typed dev searches; 13 per repeat × 3 = 39 rewrite calls per arm)

| Arm | Rewrite p50 / p95 | Total per typed search p50 / p95 (rewrite + search) | Rewrite cost per 1k typed searches | Mean tokens in / out | Run files |
| --- | --- | --- | --- | --- | --- |
| **B3**, qr-v1 gpt-5-nano, round-1 calls | 2.34 / 3.44 s | 2.56 / 3.69 s | $0.118 | 1,064 / 162 | `e20_hyde_b2_r{1,2,3}` (existing) |
| **B3**, qr-v1 gpt-5-nano, fresh calls this session (timing only) | 1.95 / 2.68 s | 2.18 / 3.05 s | $0.119 | 1,064 / 163 | — (`rewrites/qr-v1_gpt-5-nano_t_r{k}`) |
| **30** instant (no rewrite, no HyDE) | — | **0.12 / 0.17 s** | $0 | — | `e30_instant` (deterministic) |
| **31** qr-v1 on gemini-3.1-flash-lite | 1.76 / 2.01 s | 1.97 / 2.25 s | $0.566 | 981 / 214 | `e31_qrv1_flashlite_r{1,2,3}` |
| **32** qr-v1 on gpt-5.4-nano | 1.90 / 2.39 s | 2.14 / 2.57 s | $0.429 | 1,064 / 173 | `e32_qrv1_gpt-5.4-nano_r{1,2,3}` |
| **33** qr-s1 on gemini-3.1-flash-lite | **1.49 / 1.70 s** | **1.70 / 2.15 s** | $0.337 | 358 / 165 | `e33_qrs1_r{1,2,3}` |
| flash-lite qr-v1, re-timed interleaved with 33 (timing only) | 1.60 / 1.94 s | — | $0.559 | 981 / 209 | — (`rewrites/qr-v1_gemini-3.1-flash-lite_t_r{k}`) |
| **34** routing (2/13 typed searches skip the rewrite) | — | 2.26 / 3.06 s (fresh calls); 2.64 / 3.46 s (round-1 calls) | $0.100 | — | `e34_route_r{1,2,3}` |

**Search only, warm (78 typed calls each, interleaved):**

| | p50 | p95 |
| --- | --- | --- |
| Instant search | 0.121 s | 0.166 s |
| B3 search | 0.206 s | 0.279 s |
| All 16 dev searches, 96 calls each: instant | 0.120 s | 0.163 s |
| All 16 dev searches, 96 calls each: B3 | 0.198 s | 0.278 s |

- **How totals are computed.**
  - Arms 31–33 and 34 are paired: each search was timed right after its rewrite.
  - The B3 rows are the convolution of every rewrite call with every warm B3 search time (`methods/speed_report.py`), which assumes the two are independent.
  - The B3 search re-run here reproduces `e20_hyde_b2_r{1,2,3}` exactly (16/16 rankings, 1,000 deep, per repeat).
- **Same-session comparison** (the fair one, because round-1 calls ran on a different day's network):
  - gpt-5-nano p50 1.95 s, gpt-5.4-nano 1.90 s, flash-lite 1.76 s, all interleaved call by call.
  - The fastest model saves about 0.2 s at p50 and 0.7 s at p95. That is 10–25% of the total, not 5×.
- **The shorter prompt (33 against flash-lite qr-v1, interleaved):**
  - p50 −0.11 s (1.49 against 1.60 s) and p95 −0.24 s.
  - Input tokens −64% (358 against 981) and output −21% (165 against 209).
  - Cost −40% against the same model's qr-v1. It is still 2.8× gpt-5-nano's qr-v1, because flash-lite's output price is 3.75× higher.
- **Generation share.** Subtracting the ~0.9 s ping leaves about 0.6 s of generation for qr-s1 and about 0.9 s for qr-v1 on flash-lite. Generation time scales with output tokens. The two captions dominate qr-s1's output.
- **Output shape** (label-free, 39 parses each).
  - Every arm returned 3 phrases (qr-s1: 2.97), 7.0–7.4 keywords and its full caption count (qr-v1: 3; qr-s1: 2).
  - There were no empty or invalid parses.
  - No arm reported cached prompt tokens: OpenAI cached 0 of 1,064 input tokens, and Gemini reported none.

### c2 model choice (pilot)

gpt-4.1-nano returns 404 `model_not_found` ("has been deprecated") on chat completions, although `/v1/models` still lists it. I marked it unavailable in `ai_prices.json`.

The 5-call pilot used 5 synthetic searches, interleaved across models (`data/runs/speed/pilot_c2.json`):

| Model | Reasoning setting | p50 | p95 | Valid | Mean out tokens | Cost (5 calls) |
| --- | --- | --- | --- | --- | --- | --- |
| gpt-6-luna | none | 2.55 s | 2.84 s | 5/5 | 163 | $0.0009 |
| gpt-5.4-nano | none (rejects minimal) | **1.87 s** | 1.97 s | 5/5 | 182 | $0.0022 |
| gpt-5-nano (reference) | minimal | 1.89 s | 2.05 s | 5/5 | 174 | $0.0006 |

I chose gpt-5.4-nano. It is no faster than gpt-5-nano and costs 3.6× more, so it is mainly a negative data point: there is no faster cheap OpenAI model for this prompt.

## Two-stage (b): instant screen, then refined B3

- **Time to first screen:** the instant search, p50 0.12 s / p95 0.17 s. This meets the 0.5 s target.
- **Time to refined:** the rewrite starts in parallel with the instant search, so the refined list arrives at rewrite + B3 search.
  - p50 2.18 s / p95 3.05 s with fresh gpt-5-nano calls.
  - 2.56 / 3.69 s with round-1 calls.
  - It would be 1.70 / 2.15 s with flash-lite qr-s1, if 33 holds quality.
- **How much the screen visibly changes** (label-free). Of the refined (B3 r{k}) top 10, this many were already in the instant top 10:

| Repeat | Typed searches (13): mean overlap of 10 | min–max | Top-1 unchanged | All 16 (MLT identical): mean |
| --- | --- | --- | --- | --- |
| r1 | 5.5 | 1–9 | 7/13 | 6.4 |
| r2 | 5.3 | 0–10 | 8/13 | 6.2 |
| r3 | 6.2 | 3–9 | 8/13 | 6.9 |

On a typed search about 4–5 of the 10 visible results change when the refined list lands, and the top result changes in about 5 of 13 typed searches. More-like-this searches don't change: they never use the rewrite. The screen would visibly reshuffle, so the UI should insert the new items below what the user is looking at, or mark them, rather than reorder the whole list in place.

## Routing (d)

The rule is fixed in `LOG.md` row 34 and implemented in `methods/speed_route.py`. All its entities and thresholds come from the corpus only:

| Entity set | Size |
| --- | --- |
| Creator handles (≥ 2 items) | 2,592 |
| Creator names (≥ 2 words, ≥ 2 items) | 1,719 |
| Collections | 15 |
| High-weight hashtags | 339 |

High-weight hashtags are those with ≥ 10 items in the top 1% of 39,304 distinct hashtags by summed interaction weight (cut-off 16.9), excluding generic tags. The check takes 0.03 ms (p50) and needs no model.

- **2 of 13 typed dev searches route** to the instant path, both through a high-weight hashtag match. 11 run B3.

| Search kind (n searches carrying the kind) | Routed |
| --- | --- |
| name (3) | 1 |
| topic (7) | 2 |
| said_shown (2) | 0 |
| structure (2) | 0 |
| audio, people, place, task, time, vibe (1 each) | 0 |

- **Accuracy against the "name" kind** (a method-side proxy for "is a lookup"): precision 1/2, recall 1/3.
  - One routed search is topic-only.
  - Two name searches did not route. One matched a hashtag but left more than one content word uncovered. The other's product name is not a high-weight hashtag in this library.
- **Latency.** The mix barely moves (p50 2.26 against 2.18 s for B3, p95 3.06 against 3.05 s, fresh calls; within noise), because 85% of typed searches still wait for the rewrite.
- **Cost.** $0.100 per 1k typed searches, against $0.118 for B3.
- **Bias note.** I wrote the rule after reading the dev query texts, which are method-side and allowed. I evaluated only one rule and did not tune it on any outcome. Still, its behaviour on these 13 searches is not independent of having seen them.

## Rewrite cache (e): estimate only, no run

- **Hit and miss costs.**
  - Hit: the instant-path search time, 0.12 / 0.17 s. Cache lookup is < 1 ms.
    - The exact key is the normalised query (lowercase, punctuation and stopwords removed, tokens sorted).
    - The near-identical key is the raw-query bge vector, which the search computes anyway, at cosine ≥ 0.95. The threshold is an assumption and was not tuned.
  - Miss: rewrite + B3 search, using the fresh gpt-5-nano samples.

| Assumed hit rate | p50 | p95 | Rewrite cost per 1k typed searches |
| --- | --- | --- | --- |
| 0.10 | 2.13 s | 2.90 s | $0.106 |
| 0.30 | 2.01 s | 2.85 s | $0.083 |
| 0.50 | 1.64 s | 2.73 s | $0.059 |
| 0.80 | 0.13 s | 2.33 s | $0.024 |
| 0.90 | 0.12 s | 2.18 s | $0.012 |
| 0.95 | 0.12 s | 1.64 s | $0.006 |
| 0.97 | 0.12 s | 0.20 s | $0.004 |

- **What the table shows.** A cache improves the median once more than half of searches hit. It meets the p95 target only when **≥ ~96%** of searches hit, because p95 is set by the misses.
- **Plausible hit rates.** Published web-search log studies report that roughly a third to 40% of queries are repeats or re-finding (Teevan et al., "Information re-retrieval", SIGIR 2007). Searches over one's own saved library may repeat more, but nothing here measures it.
- **Verdict.** A cache is a cost and median saving, not a p95 fix. It pairs naturally with the two-stage flow: a hit shows the refined list at once.
- **Pre-warming.** Rewriting suggested searches (theme names, recent searches) in the background raises the hit rate at about $0.12 per 1k pre-warmed searches.

## Caveats the evaluator and orchestrator should know

1. **Filters are gold in every arm.** `stack.py` reads `before` and interaction-kind filters from `queries.jsonl`, not from the rewrite.
   - So the instant path (30), routing (34) and qr-s1 (33, which has no filter output) lose nothing on the two filtered dev searches.
   - In production, a no-rewrite path needs filters from a rule parser or UI chips. The instant path's quality on filtered searches is therefore optimistic.
2. **HyDE strength differs by arm.** Arm 33 gives HyDE 2 captions instead of 3, so it is weaker by construction. Arm 30 has no HyDE at all.
3. **Gemini transport.** For flash-lite (31, 33), the few-shot pairs are rendered inside the system instruction, because `ai.gemini_json` sends one user turn. The prompt content is unchanged; only the transport differs.
4. **Diagnostic calls outside `lib/ai.py`.** Three direct probes went out while diagnosing the gpt-4.1-nano 404. Two were 404s with no charge. One gpt-6-luna call (32 tokens, $0.00001) was logged by hand in `ai_runs.jsonl` with a note.
5. **e30 is a single deterministic run.** Compare it with the mean of `e20_hyde_b2_r{1,2,3}`. The `e34_route_r{k}` runs equal `e20_hyde_b2_r{k}` except on the 2 routed searches, where they equal `e30_instant`.

## Files

- **Code** (`experiments/methods/`; `stack.py` imported, not edited):
  - `speed_common.py`
  - `speed_instant.py` (30, two-stage)
  - `speed_rewrite.py` (pilot, 31–33 rewrites, pings)
  - `speed_runs.py` (B3 on the 31–33 rewrites)
  - `speed_route.py` (34)
  - `speed_report.py` (aggregates)
  - `speed_chart.py` (chart)
- **Rewrite sets** (`data/runs/rewrites/`):
  - `qr-v1_gemini-3.1-flash-lite_r{k}`
  - `qr-v1_gpt-5.4-nano_r{k}`
  - `qr-s1_gemini-3.1-flash-lite_r{k}`
  - timing-only references `qr-v1_gpt-5-nano_t_r{k}` and `qr-v1_gemini-3.1-flash-lite_t_r{k}`
- **Timing details:** `data/runs/speed/` (`summary.json`, `instant_timing.json`, `route.json`, `pings_*.json`, `pilot_c2.json`, `*_timing.json`).
- **Chart input template:** `experiments/results/r2-q3-speed-p95.json`.
  - p95 = the typed-search total, with the B3 row from fresh calls.
  - The evaluator fills `ndcg10` and runs `python experiments/methods/speed_chart.py experiments/results/r2-q3-speed-p95.json`, which writes `experiments/results/r2-q3-speed-chart.html`.
  - The two-stage flow's two screens are the `30 instant` and `B3` points.
