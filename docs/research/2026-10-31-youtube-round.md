# YouTube search round (round 3)

*31 Oct 2026 · one founder's YouTube library (115,615 videos from Takeout's YouTube product and My Activity, 2015–2026) · 33 searches (22 dev, 11 test) · one builder agent, one evaluator agent, each new to the round. Details: `experiments/RUN-3.md`, `experiments/results/r3-methods.md`, `experiments/results/r3-eval.md`, `experiments/research/youtube-api-terms.md`.*

## Bottom line

1. **The plain baseline wins.** A0 is the Instagram recipe on Takeout titles and channels: rewrite, dense, BM25, PRF, RRF and HyDE. It scores nDCG@10 **0.463 on dev and 0.437 on test**. Nothing beat it under the adoption rule. The best dev configuration scored 0.484 but fell to 0.293 on test (−0.144, 2 wins / 8 losses).
2. **The Instagram text pass does not transfer.** On YouTube, the tier-1 text pass (te-v1c, indexed as extra lists) costs **−0.046**.
   - It helps vibe, time and personal searches.
   - It hurts topic, task, name and more-like-this searches.
   - Reason: YouTube titles are already descriptive, so invented summaries add noise more than reach. On Instagram the same pass gained +0.059 because captions were thin.
3. **Understanding intent is the most promising lever.** The intent step reads the search and outputs structured filters: time window, liked/saved/never watched, rewatched, length, Shorts.
   - Filters alone gave **+0.05** with almost no losers.
   - About **+0.6** on the behaviour and time-window searches.
   - It hurt where it guessed a date window for "that era of my life" searches.
   - It was only tested on bases that lose to A0, so it isn't proven on the shipped base yet.
4. **What you type and what you mean differ about 3 times in 10.** The same 247 results were judged once against the literal query and once against the clarified intent. They agree on relevant-vs-not **71%** of the time (κ 0.41). They diverge most where the clarification narrows the meaning.
5. **The gate beats random for video understanding, but video doesn't pay as a general search leg.** At equal spend (~$1.75 per arm), Gemini watching videos by URL chosen by the gate beat random selection by +0.018 (10/5/7). That is under the adoption bar, and both arms scored below A1.
   - The gate's value is **reach**: 10.7 of its 11 new relevant results were saved videos with no title in Takeout, which were unsearchable before.
   - The random arm mostly reshuffled already findable videos.
6. **The YouTube API terms cost nothing measurable overall,** but they do cost on moment and named-video searches.
   - API descriptions, tags and chapters (research-only reference arm, never shipped): R0 vs A0 −0.005.
   - On the one moment search, the reference arm reaches 0.69 against 0.30 on the allowed track.

## Numbers (nDCG@10, pooled labels, mean of 3 rewrite repeats)

| Run | What it adds | Dev | Test |
| --- | --- | --- | --- |
| A0 | Takeout text, B3 recipe | **0.463** | **0.437** |
| A1 | + text pass on 6,485 gated items | 0.417 | |
| A2 gated / random | + Gemini video pass, 377 / 790 videos | 0.402 / 0.383 | |
| A3v2 filters only on A1 | + intent filters | 0.471 | |
| A3v2 full on A1 | + intent filters and topics | 0.484 | 0.293 |
| ref R0 / R1 (research only) | API text instead of Takeout text | 0.458 / 0.424 | |

Labels: 1,015 dev and 265 test top-10 items were pooled and judged blind (seed-only unjudged@10 was 0.56–0.71 for every run).

## Cost

- **Round spend:** Gemini $6.76, OpenAI $0.47, about **$7.23** in total against the $10 plan.
- **Text pass:** $0.17 per 1,000 items (Batch).
- **Video pass, after the pilot:**
  - fps 0.2 at low resolution costs about 38 tokens per second of video, against about 92 at default settings;
  - about **$2.2–4.8 per 1,000 videos** clipped to 20 minutes (gated $4.83 per 1,000 for long videos; random $2.15 per 1,000 with half Shorts);
  - Batch ignored the response schema for YouTube-URL requests; the stored results were re-parsed for free.
- **Embeddings:** OpenAI text-embedding-3-small 512d, $0.39 for the library.

## What this means for the product

- **Search YouTube on Takeout titles and channels first.** It is cheap, allowed and the best performer here. The text pass that wins on Instagram should not run as an always-on leg for YouTube. Route it by search kind, or skip it.
- **Build the intent step into the rewrite.** Users search by behaviour: what they rewatched, saved but never watched, or watched in a given season. Those searches need filters over the user's own interaction data, not better text. Don't guess date windows from vague life-era phrases; ask, or leave the window open.
- **Use video understanding for reach, not ranking.** Spend it on saved videos that have no title or text, chosen by the gate. That is where it adds results nothing else can find.
- **Moments need transcripts or chapters.** The video pass at 20-minute clips found no correct moment; Chapters from the API worked better, but the terms may not allow searching them. This is an open legal question (`experiments/research/youtube-api-terms.md`).
- **Evals must be judged against intent, not query text.** Seed labels and LLM-judged pools disagree with the clarified meaning about 3 in 10 times.

## Limits

- **One person and 33 searches.** Answers were hand-built by Claude from title and channel rules, with Derrick's corrections, which may favour A0.
- **Untitled videos were judged from their video-pass text.** That is the same text A2 searched, which favours A2.
- **Mild leakage in the intent step.** The intent prompts reuse some search wording, and qi-v2 was written after seeing qi-v1's outputs on all 33 searches. It changes no verdict.
- **Test scorings:** 1 of 3 used.

## Next

1. Run the intent step with filters only (qi-v2, with no guessed era windows and no eval-specific phrases) **on A0**. Judge it on fresh searches or test scoring 2.
2. Try routing the text pass by search kind (vibe, time, personal only).
3. Get a legal read on searching refreshed API descriptions and chapters without LLM processing.
