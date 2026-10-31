# Brief, round 2: gap flags, a library-aware rewrite, speed

Round 1 (`BRIEF.md`, `STATE.md`, `docs/research/2026-10-30-search-loop.md`) ended with finalist **B3**:

- real rewrite (qr-v1);
- bge-small dense + BM25 + RRF;
- tier-1 text enrichment indexed as its own BM25 and vector lists;
- HyDE.

This round answers four questions the founders raised. **All of `BRIEF.md`'s rules still apply:** roles (who evaluates never builds), preregistration in `LOG.md`, the adoption rule, `lib/ai.py` for every paid call, nothing personal in git. Work unattended.

## Setup

- `git pull` first.
- If `data/enrich/` and `data/runs/rewrites/` are missing (for example after a container restart):
  - re-attach the data zips;
  - rebuild with `methods/enrich_batch.py` (~$2.9, Batch) and `methods/llm_rewrite.py`;
  - confirm B3 reproduces on dev (r10/t1 labels) before anything else.
- **Budget:**
  - Spend so far is in `data/ai_runs.jsonl` (round 1: OpenAI $0.09, Gemini $6.70). The caps are unchanged.
  - Plan this round at **under $3 total**, and stop paid work at $5.
- **Test split:** 1 scoring left. Use it only if a change is adopted on dev, and score all finalists together once.

## Q1 · Do the per-facet gap flags predict what search misses? (evaluator-side; ~$0)

Every item now has an `unknown` facet list. The founders' idea is to check each item's information and enrich further only where it's missing. Round 1 built the check but never validated it.

1. **Map search kinds to facets:**

   | Search kind | Facet(s) |
   | --- | --- |
   | place | place |
   | said_shown | said, shown |
   | audio | audio |
   | vibe | vibe |
   | people | people |
   | task | use |
   | topic, name | topics, kind |
   | more_like_this | shown, vibe |

2. **Measure.** Take every (search, right answer) pair under B3. Count the answer as *found* if it ranks within max(50, 2 × the number of answers). Report the AUC for predicting a miss, overall and per kind, from:
   - (a) the matching facet listed as `unknown`;
   - (b) the facet *empty* (hedges count as filled);
   - (c) the hedge flag (listed unknown but filled);
   - (d) the caption-richness score from round 0 (`archive/.../info_bench.py`, AUC 0.67), as the bar to beat.
3. **Flag accuracy against Muse** (evaluator only). For items Muse described, per facet:
   - recall of the flag: Muse states the facet → we say unknown;
   - precision: we say known → Muse agrees.
4. **Where the misses sit.** For each missed answer, its rank under B3: in the top 200, 201–1,000, or beyond. The docs plan "on-demand" enrichment of a weak search's nearest candidates. This shows how many misses that could ever reach, against background enrichment.
5. **Design the media gate (no media spend).** Propose a rule for which items get each next rung:
   - one image (shown, vibe, on-screen text);
   - audio (said, song);
   - full video.

   Combine: facet unknown × facet relevant to the item's `kind` (audio for music, dance and trend; said for tutorials and talking heads) × interaction weight (self-share, save, collection > like) × search demand. For each rung, estimate the share of the corpus it selects, its cost per 1,000 items at the verified prices, and the share of current misses it covers (from step 2). Compare with "everything" and with "on-demand only".

Write `experiments/results/r2-q1-gap-flags.md`. Builders get only this aggregate note.

## Q2 · A library-aware rewrite (query-side only)

The leaked hand rewrite beat the real one partly because it "knew the library". Test a legitimate version.

- **Content stays user-independent.** Items, enrichment and vectors are unchanged. Only the rewrite step changes.
- **Library profile**, built once per user from method-side data only. Its builder must not open `queries.jsonl`, the labels or any run file. Contents:
  - the user's collection names;
  - the top ~40 creators and ~60 hashtags by interaction weight;
  - the top ~40 enrichment `topics`/`kind` values by count.

  At most ~600 tokens. Put it at the start of the prompt so the provider's prompt caching applies, and record cached-token usage.
- **Arms**, each on B3 with all three repeats, against B3:
  - **qr-p1:** qr-v1 plus the profile. Changes the rewrite only; HyDE captions come from the same call.
  - **qr-l1, "look first":**
    1. Run B3's caption + enrichment search on the raw query (no rewrite).
    2. Give the rewriter the top 20 results' hashtags, creators and enrichment topics.
    3. Rewrite and search.

    Record the added latency.
- Same model as qr-v1 unless the pilot shows it can't use the context; then one bigger model as a separate arm.
- Report the change against B3, per kind (especially place and vibe, where the leaked rewrite led), cost per 1,000 searches, and p50/p95 latency.

## Q3 · Speed against the 0.5 s target

`docs/05-processor.md` targets search p95 ≤ 500 ms. B3's p50 is ~2.6 s, almost all of it the rewrite. Measure quality against **p95 latency** (20+ timed calls per arm; note the container's network variance) for:

- **(a) Instant path:** B3 with no rewrite, which also means no HyDE. This is the quality of a first screen shown immediately.
- **(b) Two-stage:** the instant first screen, then the refined B3 list. Report both screens' nDCG@10 and time to each. Also report how many of the refined top 10 were already in the instant top 10 (how much the screen would visibly change).
- **(c) Faster rewrite:**
  - qr-v1 on the fastest cheap models available, checking at least one Gemini Flash-Lite and one OpenAI nano;
  - a shorter prompt and output (phrases + keywords + 2 captions, no extras).
- **(d) Routing:** skip the rewrite when an LLM-free check says the query is a name or keyword lookup. Examples: it matches a creator handle, a collection name, or a hashtag with high weight in the user's index. Report routing accuracy by search kind and the quality and latency of the mix.
- **(e) Rewrite cache:** identical and near-identical searches reuse the stored rewrite (latency ≈ instant path). Estimate only; no eval change.

Write `experiments/results/r2-q3-speed.md` with a quality-against-p95 chart (any simple HTML or PNG is fine; aggregate only) and a recommendation for the product flow.

## Q4 · How far to trust the AI judge (needs Derrick, non-blocking, last)

Round 1's labels now include ~655 AI judgments, graded from captions only.

- The evaluator builds a **60-line blind sheet** in `data/eval_work/human_check/`:
  - 40 AI-judged items, stratified 15 × grade 2, 10 × grade 1, 15 × grade 0;
  - 20 Muse-labelled items;
  - shuffled, source hidden, same format as `eval/judge.py` sheets: search text + caption + creator + the reel's link, so Derrick can open it.
- Do this **at the end**. Present the sheet in the chat with a one-line instruction (grade each 0/1/2 by opening the link) and stop.
- When Derrick replies with grades, compute agreement (exact, and the kappa for "relevant vs not") between him, the AI judge and Muse. Report whether the AI judge leans toward text.

## Q5 · YouTube readiness (synthetic only; no personal data yet)

Derrick is requesting a Google Takeout (YouTube) and will write YouTube searches. Prepare so the next round can start immediately:

- **A prototype Takeout importer** for watch history, search history, likes/playlists and subscriptions (JSON and the CSV variants). Use **synthetic fixtures** shaped like Google's documented format. It writes `items.jsonl` and `interactions.jsonl` in the same shapes as Instagram.
  - Interaction kinds: watch (0.1), like (0.3), playlist (0.8), share if present.
  - Note what Takeout lacks: no descriptions, no durations, sometimes no titles for removed videos.
- **A prototype official-API enricher** (`YOUTUBE_API_KEY`; skip the live call if the key is unset): `videos.list` for snippet (title, description, tags, channel), contentDetails (duration), topicDetails, and thumbnails. Batches of 50 IDs at 1 quota unit each; give the quota estimate for 20k videos. Parse chapters from descriptions. Thumbnails come from the URLs the API returns.
- **The eval format** for YouTube searches: queries file (method side) and answers file (evaluator side), the same shapes as Instagram's. Add a "moment" kind for "the part where…" searches, whose answers carry a timestamp range.
- A short plan for the YouTube round: tier 0 = title + description + chapters + tags; tier 1 = the same text pass; tier 2 = thumbnail. Transcripts only where terms allow; a video's captions via the API require the owner's permission.

## Finish

- Update `STATE.md` (round 2 summary: answers to Q1–Q3, spend, what's next) and `LOG.md`.
- Where a result changes A-003 or the docs, amend the **Proposed** A-003 text, or add a new Proposed amendment.
- Commit and push to the same branch; the draft pull request updates itself.
- End by presenting the Q4 sheet and waiting.
