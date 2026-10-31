# Round 2 · Q3: speed against the 0.5 s target

*30 Oct 2026 · orchestrator summary of `r2-q3-speed-methods.md` (experimenter, timings) and `2026-10-30-r11-q2-q3.md` (evaluator, quality on r11 labels). Dev, 16 searches; timings per typed search over 39+ calls from this cloud container. Chart: [r2-q3-speed-chart.html](r2-q3-speed-chart.html).*

## Quality against p95 latency

| Arm | dev nDCG@10 | Δ vs B3 [CI] | p50 / p95 | $ / 1k searches |
| --- | --- | --- | --- | --- |
| B3 (qr-v1 on gpt-5-nano) | 0.570 | — | 2.18 / 3.05 s | 0.118 |
| **(a) 30 · instant path** (no rewrite, no HyDE) | 0.493 | −0.077 [−0.140, −0.026] | **0.12 / 0.17 s** | 0 |
| (c) 31 · qr-v1 on gemini-3.1-flash-lite | 0.561 | −0.009 [−0.047, +0.020] | 1.97 / 2.25 s | 0.566 |
| (c) 32 · qr-v1 on gpt-5.4-nano | 0.580 | +0.010 [−0.013, +0.036] | 2.14 / 2.57 s | 0.429 |
| (c) 33 · short prompt qr-s1 on flash-lite | 0.559 | −0.011 [−0.045, +0.014] | 1.70 / 2.15 s | 0.337 |
| (d) 34 · routing (2 of 13 typed searches skip the rewrite) | 0.568 | −0.002 [−0.012, +0.007] | 2.26 / 3.06 s | 0.100 |
| Q2 · 26 · look-first rewrite (**B4**) | 0.594 | +0.024 [−0.006, +0.055] | 2.46 / 2.78 s | 0.106 cached (0.145 list) |

## What it shows

1. **Only the instant path meets the target.** Everything that calls an LLM sits at 2.1–3.1 s p95. A trivial call to either provider already takes ~0.9 s p50 (up to 1.35 s p95) from this container, so no rewrite model can get a single-shot search under 0.5 s here. Faster or shorter models save 0.2–0.5 s and cost 3–5× more, with no quality gain.
2. **(b) Two-stage works.** The instant screen (0.493) arrives in 0.12 / 0.17 s; the refined list (B3 0.570, or B4 0.594) arrives ~2 s later. On average 6.5 of the refined top 10 were already on the first screen, so about 3–4 results change when the refined list lands; the top result stays the same in about half the typed searches.
3. **(d) Routing barely fires.** An LLM-free "is this a lookup?" check (creator handle, collection name, high-weight hashtag) routed 2 of 13 typed searches, with precision 1/2 and recall 1/3 against the name kind. It saves nothing at p95.
4. **(e) A rewrite cache helps the median, not p95.** It brings p50 to instant speed only above ~50% hit rate and p95 under 0.5 s only above ~96%.
5. **Look-first would fit the two-stage flow for free** (its first pass is the instant screen), but it did not hold up on test, so it is not recommended yet.
6. **Held-out check (test, 6 searches):** instant 0.528 vs B3 0.565 (−0.037 [−0.10, +0.05]); over all 22 searches instant is −0.066 [−0.117, −0.023] below B3 and level with the honest caption-only base.

## Recommendation for the product flow

- **Search returns in two steps:** instant list (≤ 0.2 s p95) → refined list (~2–3 s), with a subtle "refining" state and stable positions for items that stay. The `search` op in the query API should allow a `stage: instant | refined` response, or stream both.
- Refined list = **B3**. The look-first rewrite (B4) won on dev (+0.024) but lost on the held-out test searches (−0.038 [−0.095, +0.010]) and tied B3 over all 22 (+0.007), so it was withdrawn.
- Cache rewrites per user and query (cost and median), and run the rewrite with warm connections close to the provider. Measure p95 again from production infrastructure before choosing a faster model.
- Interpret `05-processor.md`'s "search p95 ≤ 500 ms" as **time to first screen**; add a second target for the refined list (e.g. p95 ≤ 3 s).
- Filters: the instant path can't parse "before May" or "that I sent to friends" without the LLM; the first screen needs rule-based filter parsing or filter chips.
