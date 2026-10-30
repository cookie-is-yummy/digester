# Brief, round 3: YouTube

Run this when Derrick has provided:
- the Takeout zip;
- `YOUTUBE_API_KEY` in the environment;
- his YouTube searches, as two files: `yt_queries.jsonl` (method side) and `yt_answers.jsonl` (evaluator side).

**All of `BRIEF.md`'s rules apply:** roles (who evaluates never builds), preregistration, the adoption rule, `lib/ai.py` for every paid call, nothing personal in git. Work unattended.

Read first:
- `experiments/results/youtube-takeout-inventory.md` (what the real export contains);
- `experiments/youtube/PLAN.md`, `eval_format.md`;
- `results/r2-q1-gap-flags.md` (media gate);
- A-003 and A-004 in `docs/amendments.md`.

## Setup

1. **Unzip the files.**
   - Unzip the Takeout into `data/youtube/raw/`.
   - Run `python experiments/youtube/takeout_import.py data/youtube/raw --out data/youtube/corpus`; check the stats match the inventory note.
   - Put Derrick's search files in `data/youtube/evals/`: queries → `queries.jsonl`; answers → `labels/answers.jsonl` (evaluator only).
   - Convert both to the shapes in `eval_format.md` (an evaluator does the answer side).
   - Split the searches into dev (about two thirds) and test (about one third, covering every kind) **before** any run. Test may be scored at most 3 times.
2. **YouTube API terms.** Before storing API data, read the YouTube API Services Terms and Developer Policies. Covered: how long API data may be stored and refreshed; whether it may be sent to another provider's model; whether thumbnails may be analysed. Write `experiments/research/youtube-api-terms.md`. If a use isn't clearly allowed, don't do it; record it as a question for the founders.
3. **Tier 0.** Run `api_enrich.py` on all items: title, description, chapters, tags, duration, category, topicDetails, thumbnail URLs.
   - Log quota used.
   - Mark unavailable videos.
   - Shorts are videos ≤ 3 min that are vertical, where that can be known. Record how you decided.

## Questions

**Q1 · Baseline on YouTube.** Run the Instagram finalist B3 on the YouTube corpus with tier-0 text only:
- caption view = title + description (first ~600 chars) + chapters + tags + channel;
- same rewrite, BM25, bge-small and fusion.

Score on dev, per kind. Separately report the `moment` searches (no transcripts yet, so expect near zero) and searches over watch-only items against saved items.

**Q2 · Tier 1 text pass.** Run the te-v1c pass on YouTube items (Batch), with a YouTube-aware prompt variant only if the pilot shows it's needed. Index it separately, as on Instagram. Measure the gain against Q1 and the cost per 1,000 videos.

**Q3 · The cascade with real media, gated.**
- **Tier 2: thumbnail.** One image per video to a Flash-Lite model, for shown, on-screen text and vibe; ~258 tokens per image, if the terms allow it. Indexed as its own field.
- **Tier 3: the video itself,** via Gemini's YouTube-URL input at default resolution. Public videos only; use clipping or fps settings only if they work for URLs. It writes:
  - a description;
  - spoken-content summary with timestamps, so `moment` searches become answerable;
  - on-screen text;
  - music if recognisable.

  Indexed as its own field, with chunk entries carrying start/end seconds for moments.
- **Gate.** Apply round 2's proposed media gate (facet gap × facet relevant to the kind × interaction weight × search demand) to choose items for tiers 2–3. Compare against random selection at the same budget, so the gate itself is tested.
- **Budget.** Tier 3 at most ~400 videos (expected ≤ $5 at Batch prices; check with a 20-video pilot). Tier 2 can cover all saved videos if the terms allow.
- **Report.** The gain per tier and per kind, against cost per 1,000 items, and whether gated selection beats random. This is the test of "enrich only where the information isn't enough" with real media.

**Q4 · One library, two platforms (if time).** Search Instagram + YouTube together, as the product would: one index, the same pipeline, platform as a filter. Check that cross-platform searches (topic searches that have answers on both) don't get worse on either platform's searches.

## Finish

- Write `docs/research/<date>-youtube-round.md`.
- Update A-004 (YouTube contract gaps) and the Proposed amendments where the results change them. Update `STATE.md` and `LOG.md`.
- Commit and push.

**Budget for the round:** under $10 in total; stop paid work at $12.
