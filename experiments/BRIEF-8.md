# Brief, round 8: a processor for each platform, run as a loop

The roles, preregistration, adoption rule, `lib/ai.py` ledger and privacy rules are the same as in `BRIEF.md` and `BRIEF-4.md`. Work unattended.

## Setup

1. **Data.** Derrick uploads `digester-data-all.zip` plus `.z01`–`.z03` (a split zip).
   - Rebuild it: `zip -s 0 digester-data-all.zip --out full.zip && unzip full.zip -d data/`. That gives `data/all/`; set `DIGESTER_DATA=$PWD/data/all`.
   - The upload limit dropped the big vector files. **Rebuild them first**, then check that `r7/h0_r1` reproduces exactly:
     - `oai3l_1024` with `c6_embed.py`, about $0.52;
     - optionally `oai512` for C0, about $0.4.
   - `yt_ref/` (research-only YouTube API text) is deliberately left out.
2. **Keys** come from Derrick and go in the environment only. The caps in `lib/ai.py` follow what he says is left on each account.

## Where we are (see `docs/research/2026-11-07-models-and-classifiers.md`)

- **New base, H0:** C0 with text-embedding-3-large 1,024 d. Confirmed over C0 on held-out: +0.055 over 21 searches, 15/4.
- **H5:** H0 + guarded filters + format/tone classifiers + router + creator era profiles. It beats C0, but its gain over H0 is not established.
- **The platforms behave differently:**
  - The te text pass helps Instagram (+0.06 to +0.09) and both-app searches, and hurts YouTube (−0.02 to −0.05).
  - The router's app guess is 55% accurate; its misreads cost YouTube searches 0.06–0.08.
- **Known bug:** creator search is non-deterministic, because it depends on Python string hashing.

## Searches

All held-out sets so far are used up or biased. Two new sets replace them:

- **`known_dev` / `known_test`** (381 + 381):
  - These are **real YouTube searches Derrick typed in 2019–21**, from My Activity. Each is auto-labelled with the video he watched within 10 minutes afterwards: first video = 2, later ones = 1.
  - **Use MRR and success@10 as the main metrics,** since only the watched video is known. Other relevant items are unjudged, so don't pool-judge these.
  - `known_test` query texts are hidden in `labels/known_test_queries.jsonl`. Score it at most 3 times.
- **`ig_known` (new; the evaluator builds it in setup, before any method runs).** Instagram has no search history in the export, so make known-item searches from saved posts:
  - Sample 300 saved or collected Instagram items, stratified by info class and collection.
  - For each, a model **different from any the builder uses** writes how a person would half-remember and search for it months later. Give it the caption, creator and te summary. Write the prompt generically.
  - Label = that item (2). Split 150 / 150 into `ig_known_dev` / `ig_known_test`, with test texts hidden.
  - Spot-check 30 by eye for searches that copy the caption word for word, and rewrite those.
- `dev` (44 searches) stays for kind coverage. `test` is biased for round-5+ ideas; `test2` and `yt_holdout` are used up.

## The loop

Rounds 8.1, 8.2, … run as in `BRIEF-4.md`: a fresh experimenter, then a fresh evaluator, then commit and push.

**Stop rule:** spend reaches the cap, or 3 rounds in a row adopt nothing. At the end, score the finalist, H0 and the best rival once on `known_test` and `ig_known_test`.

## Agenda: platform-specific processing (ordered by expected value per dollar)

1. **Fix creator search determinism** (sort ties, no hash order). Re-run H5 to get a stable baseline. Free.
2. **Platform-aware fusion.** Each platform's own lists are used only for its own items, and coverage-fair fusion stays.
   - **Instagram:** te lists, the creator handle, hashtag splits, collection names as user labels, DM shares as a strong signal.
   - **YouTube:** titles + channel, playlist names, watch count and rewatches, duration and Shorts flags, channel profiles (type, era, affinity). No te for titled videos.
3. **A better platform guess.**
   - Combine the router's text guess with **the user's own priors**: which platform the matched creators or topics live on, and how the user's saves split by platform.
   - Use it as a soft balance, never a hard filter.
   - Measure the misread cost on `dev` + `known_dev` + `ig_known_dev`.
4. **YouTube known-item path.** Real YouTube searches are short keyword queries. Test an instant path (no LLM rewrite) against the rewrite on `known_dev`, in quality and latency, and route by query shape.
5. **Instagram half-remembered path.** Tone and format classifiers, creator recall, and te on every item. Test on `ig_known_dev` + `dev` Instagram searches.
6. **Drop or fix the parts that hurt in round 7.** The soft "new" time boost without time words, and the format boost.

## Budget

Rebuilding the vectors is about $1. Each round should stay under $2 unless the brief for that round says otherwise.
