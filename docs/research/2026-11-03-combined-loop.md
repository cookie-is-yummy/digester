# One library, two platforms: the round-4 loop

*3 Nov 2026 · one founder's Instagram (21,293 items) and YouTube (115,615 videos) in one index.*

- **Method:** 3 loop rounds (4.1–4.3), then one held-out milestone. Each round had a fresh experimenter that never saw labels, and a separate fresh evaluator that pooled and judged blind.
- **Searches:** dev is 44 searches (22 Instagram, 22 YouTube). Held-out is 11 YouTube searches plus Derrick's 13 fresh searches, written before any round-4 result and vetted by him.
- **Spend:** $3.88. That is $3.78 Gemini, almost all of it rebuilding the Instagram text pass, plus $0.10 OpenAI.
- **Details:** `experiments/BRIEF-4.md`, `results/r4.1-*`, `r4.2-*`, `r4.3-*`, `r4-milestone.md`.

## Bottom line

1. **One index for both platforms barely hurts.**
   - The platform-blind baseline (C0, round 3's A0 recipe) loses only 0.007 on Instagram searches and 0.017 on YouTube searches, compared with searching each platform alone.
   - About half the other platform's items that reach a top 10 are relevant (54% for Instagram searches, 38% for YouTube).
   - The product can search everything at once and use platform only as a filter.
2. **Only Instagram gains from the text pass, and that holds on unseen searches.**
   - It improves Instagram and both-platform searches on dev (+0.07) and on Derrick's fresh searches (+0.05; +0.051 [+0.012, +0.100] on the Instagram ones).
   - It does not improve YouTube searches. Titles are already descriptive, and enriched Instagram items compete for YouTube searches' top slots at lower precision (34–42% relevant, against 53–81% for the YouTube items they push out).
3. **Fusion must be coverage-fair.** If enrichment is extra RRF lists, an item ranks higher just for being in more lists.
   - In round 4.1, 98% of Instagram items had those lists and 6% of YouTube items did, so Instagram took about half of YouTube's top 10.
   - Fix: an item outside a list gets its own-list score in that list's place. This brought the share down to 24% and gained +0.059 over plain fusion.
4. **The round's dev winner was not confirmed.**
   - E1 (coverage-fair fusion + text pass + guarded intent filters) scored 0.538 vs 0.483 on dev, +0.056 [+0.010, +0.105].
   - On held-out it was +0.030 on the fresh searches and −0.024 on YouTube's held-out set; +0.005 over all 24.
   - **E1 is withdrawn.** Under the stop rule, 4.1–4.3 count as three rounds without a confirmed win, so the loop stopped.
5. **The intent step is still unproven on unseen searches.**
   - Guarded filters only fire when the search says a time or behaviour word. "Saved OR shared" must only ever widen.
   - On dev they won on behaviour and time searches with no losers.
   - None of the held-out searches contains such a word, so held-out could not test them.
   - Round 3 and 4.1's unguarded versions lost by guessing date windows and by treating "watched" as a YouTube-only filter.

## What this means for the product

- **Enrich by platform, not everywhere.** Run the text pass on Instagram items and on YouTube items with no Takeout title. Skip titled YouTube videos.
  - This saves about half the text-pass cost on a YouTube-heavy library.
  - It is the "enrich only where the information isn't enough" idea at the level where it measurably holds.
- **Use coverage-fair fusion** whenever lists cover different shares of items.
- **Keep intent filters behind word guards.** Never let a guard narrow a filter. Never treat missing watch data as "not watched". Collect behaviour and time searches from users to test them.

## Limits

- One person.
- About 74% of the relevant top-10 items on the fresh searches were graded by evaluator agents, calibrated on Derrick's marks, not by Derrick.
- The Instagram labels from rounds 1–2 were lost and rebuilt by pooling.
- One of the 13 fresh searches (`f01`) has no confirmed answer.

## Remaining held-out scorings

Fresh `test`: 2 of 3 left. `yt_holdout`: 1 of 3 left.

## Next experiments (not run)

1. **Text-pass lists only for Instagram items and untitled YouTube items,** under coverage-fair fusion. This tests the per-platform rule directly. Cost: free.
2. **Platform-share calibration in fusion,** so one platform's lists can't take the other's top slots.
3. **Held-out behaviour and time searches from Derrick,** to test the guarded intent step.
