# Search processor and data: where things stand

*As of 9 Nov 2026, after search-loop round 9. Branch `experiments/search-loop` of `cookie-is-yummy/digester`. This document collects the round write-ups in `docs/research/` and `experiments/results/` into one place. Aggregates only: no search texts, captions or per-item data.*

## In one paragraph

- **What exists.** We have a working search over one founder's whole library: 136,908 saved, liked, shared and watched items from Instagram and YouTube, searched together in one index. The current best pipeline is **Q8**:
  - it skips the LLM for short keyword searches;
  - it rewrites longer searches with gpt-5-nano;
  - it ranks with dense vectors, keyword matching and an AI text summary of each Instagram post;
  - it leans softly toward the platform the search seems to be about.
- **Cost and speed.** It costs about $0.05 per 1,000 searches, and the first screen shows in about 0.6 s.
- **Where it stands on quality:**
  - **Topic searches** ("anything like this") look good on AI grades. They have not yet been checked against Derrick's own grades, and the AI judges agree with him only moderately.
  - **Finding one exact post you remember** works only about 30–45% of the time.
  - **Named-creator searches** work about 40% of the time.
  - **Searches about how a post looks, its sound, or "examples of" a quality** mostly need information our text doesn't have.
- **Status.** All of this lives in `experiments/`. None of it is merged into the product code (`scrolldigest/`); the architecture is still Proposed (A-006).

## 1. The data

### 1.1 The library

| | Instagram | YouTube | Total |
| --- | --- | --- | --- |
| Items | 21,293 | 115,615 | 136,908 |
| Source | Instagram data export (JSON) | Google Takeout (watch history, likes, playlists, My Activity) | |

- **The demo library** has 136,445 items: friends' and mutual-follow posts are removed.
- **Interactions** (152,904 rows):
  - watch 116,790;
  - like 24,106;
  - playlist 5,703;
  - share to self 2,696;
  - share to a friend 1,479;
  - collection 1,146;
  - save 772;
  - view 212.
- **One item per post or video,** deduplicated by `dedup_key` (`instagram:<shortcode>`, `youtube:<video id>`). Each item records which interaction kinds it has and when it was first seen.
- **Platform-specific fields live in `platform_data`:**
  - Instagram: media kind (reel or post), owner handle and name, hashtags, collection names, owner relation (following, friend, mutual…);
  - YouTube: channel, playlist names, watch count, duration where known.
- **YouTube My Activity search history** (searches typed on YouTube, 2019–21) is in the export. It supplies the real known-item test sets (search → video watched next).

### 1.2 What our text can and can't answer (round-9 information audit)

| What a search asks about | Instagram | YouTube |
| --- | --- | --- |
| Subject | caption usable for 70% of items, but 45% have fewer than 4 content words | title for 87%, but only 47% have 4 or more content words |
| Creator | handle 98% | channel 87% |
| Type / format | reel or post 100%; te `kind` 62% | duration 91% |
| How it looks | te `shown` 67%, but written from the caption, so it adds little; no media | almost none (5% of titles) |
| Sound | an audio word in 9%; no track names | 3% |
| Tone | te `vibe` 85% (from the caption) | 3–5% |
| When / behaviour | dates 98.5%; like, save, share | dates 100%; watch counts 94% |

**What real searches ask for.** Derrick's real Instagram searches are about:
- type, about 55%;
- how a post looks, about 32%;
- "examples of" a quality, about 26%;
- a named creator: almost none.

Roughly **1 real Instagram search in 5 needs visual information we don't have.** On his Instagram sheet searches, 88% of the lost score is "information missing", not "information present but unused".

### 1.3 Derived data (all rebuildable; nothing here is user-created)

- **te-v1c text pass:** one cheap Gemini Flash-Lite call per item. It writes a short summary, kind, topics, `shown`, `said`, `vibe`, `use` and a few likely search phrases.
  - It costs about $0.18 per 1,000 items through the Batch API.
  - It is run on all Instagram items.
  - A YouTube te set exists for part of the library, but Q8 does not use it (round 4: no gain on YouTube).
  - te reads the caption, not the media, so it cannot see what a post looks like.
- **Vectors:**
  - **text-embedding-3-large at 1,024 dimensions, stored as int8:** about 1 KB per item. This is the current set (H0 and Q8).
  - **text-embedding-3-small at 512 dimensions:** the older C0 baseline.
  - Each vector set records its embedding model, as AGENTS.md rule 10 requires.
- **Keyword index:** BM25 over item text, and over te text for Instagram items.
- **Caches:** rewrite and refine results are cached per library, so a repeated search is free.
- **AI call ledger:** every paid call is logged to `ai_runs.jsonl` with model, prompt version, tokens and cost.

### 1.4 Where data lives and what must be deleted

- **All real data is under `data/` (gitignored), never in git:** `data/all/` is the combined library, and `data/all/evals/` holds the labels.
- **YouTube Data API reference data** (`data/yt/ref`, `data/all/yt_ref`) is research-only. It is never shipped, never caches thumbnails, and must be **deleted by 2026-11-29**.
- **Round-9 media pilot descriptions** (150 YouTube videos) were research-only and were deleted at the end of round 9.
- **No transcripts, audio, video or frames are stored** (AGENTS.md rule 8).
- **DM message text is never read.** Only shared-post objects are kept. Friends' posts appear as counts only.

## 2. The processor today: Q8

Q8 was recommended in round 8 as configuration B8.5. It runs these steps for one typed search.

1. **Planner (route-r1, code only, no LLM).** It decides the path from the shape of the search:
   - **Instant path:** short keyword-like searches go straight to retrieval. Most real YouTube searches take this path.
   - **Rewrite path:** longer or descriptive searches go to **qr-v1** (gpt-5-nano). It writes search phrases, keywords and a few imagined captions (HyDE).
2. **Retrieval lists:**
   - dense search with 3-large int8 vectors over item text (title, caption, creator, collection names);
   - BM25 keyword search;
   - **for Instagram items only,** dense and BM25 lists over the te text. On YouTube they crowded out better items.
   - **Fusion is coverage-fair:** an item missing from a list gets its own score from another list in that place, so being in more lists does not by itself push an item up.
3. **Fusion:** reciprocal-rank fusion, k = 60.
4. **Platform prior (prior-p1):** a soft weight toward Instagram or YouTube. It combines a guess from the search text with the platform share of the first top 20. It never filters.
5. **Refine (rewrite path only, only when the prior reads the search as YouTube):** gpt-5-nano reorders the top 20.
6. **Output:** a ranked list, plus a "why" record: the path, the rewrite, the prior, whether the refine ran, the time per stage and the cost.

**Cost and speed** (round-8 held-out, corrected):

| | H0 (old base) | Q8 | FM |
| --- | --- | --- | --- |
| $ per 1,000 typed searches | $0.127 | **$0.049** (varies with the search mix: $0.029 on YouTube searches, $0.10 on Instagram) | $0.092 |
| First screen, p50 | 1.97 s | **0.58 s** | 0.58 s |
| Refined screen, p50 | — | 3.5 s | 3.8 s |

- On real Instagram searches the saving is smaller (−23%), because they are longer and fewer take the instant path.
- **Variants kept for comparison:**
  - **H0:** rewrites every search; 3-large; no te, prior or refine.
  - **FM:** Q8 with a gpt-5-mini refine. Not the default: on real searches it adds +0.000 to +0.010 at about +90% cost.

## 3. How good it is: the scorecard

"Q8 now" is the best reading on real or held-out searches. The proposed targets come from the round-9 loop. **Derrick's targets (9 Nov) are his stated position, pending Eason.**

| Kind of search | Q8 now | Loop's proposed target | Derrick's target |
| --- | --- | --- | --- |
| Topic / "anything like it": a good item in the top 5 | AI grades 86–92%; on Derrick's own targets only 8–17% (a floor, not a measurement) | ≥ 80% on Derrick's grades | **every search** has at least one good item in the top 5; ideally **4 of the top 5** good |
| Content type | ~80% (AI grades) | ≥ 80% | as above |
| One exact post you remember: in the first screen (top 10) | 30% on 11 real searches; 45% on real YouTube (216); 69% on synthetic Instagram | 80% | 80% |
| Named creator | ~40% | 90% | **≥ 80% works, or at least 80% of the top results are that creator's posts** |
| Time / behaviour ("when I…", "that I liked") | ~53% (10 searches) | 80% | — |
| How it looks, sound, "examples of" | can't be measured with text-only judges | — | — |

**Reading the numbers:**
- **Topic searches.** The cloud's estimate, corrected to Derrick's calibration grades, is that about 4 in 10 first-screen results are good. That is about 2 of 5 against his 4 of 5 bar.
- **Instagram judging is unreliable.** The AI judges agree with Derrick no better than chance on Instagram items (κ ≈ 0). No AI-graded Instagram quality claim should be read as settled.
- **The precision caveat.** "4 of 5 good" assumes the library holds at least 5 relevant items. For niche topics the bar is "every relevant item you have".

**Q8 against H0 on real searches:**
- **Instagram:** +0.041 nDCG@10 over 35 real "like it" searches. Every reading is positive, but none is significant (Holm 0.047). It rests on AI grades; on Derrick's own targets Q8 is level.
- **YouTube:** flat (+0.003 mrr on 216 real known-item searches).
- **The synthetic gain did not transfer at this size.** The +0.110 on synthetic Instagram searches is partly because those searches were written from the same te text that Q8 indexes.

## 4. What has been tried

| Round | Question | Result |
| --- | --- | --- |
| Before 3 | Prototype on one Instagram export | Importer, filter, themes and report; search baseline. Logic recorded in `docs/05-processor.md` |
| 3 | YouTube intake and search | YouTube items and interactions (A-004); te per platform; research-only YouTube API reference arm |
| 4 | One index for both platforms | One index barely hurts (−0.007 IG, −0.017 YT). The text pass helps Instagram only. **Fusion must be coverage-fair.** Base C0 |
| 5 | Read the search in typed parts (topic, format, tone, creator) | Nothing passed. Tone was a lead; format words were read too literally; creator search works only when the creator is named |
| 6 | Stronger models | **3-large embeddings adopted (H0: +0.055 over C0 on held-out).** Stronger rewrite models were more consistent but no better |
| 7 | Cheap classifiers, combined package (H5) | Beat C0 on held-out, not H0. Instagram te lists helped Instagram and hurt YouTube (crowding) |
| 8 | Cost- and performance-optimal architecture; validation audit | **Q8 adopted:** −61% cost, faster first screen, YouTube flat, synthetic Instagram +0.110. The audit found most past dev wins were inside the noise |
| 9 | Is it good enough, and where not? Intent-first query reading; media pilot | Nothing adopted in 9 arms (stop rule). Info audit and scorecard; YouTube media pilot; the "direction" input designed |

### Lessons that hold across rounds

1. **Never drop the words the user typed.** Replacing the search with an AI paraphrase lost most on exactly the searches it was meant to fix (round 9: −0.043).
2. **Explicit signals don't work as one more ranking list.** Creator lists, the time window, personal vocabulary and the media list each failed or did nothing when mixed into the fusion:
   - the creator index (round 8);
   - the creator lookup, time window and personal vocabulary (round 9);
   - the media list (round 9).

   When the user names a creator or a behaviour, use it as a **filter or a separate group**, not a blended list. This is untested so far.
3. **Most "when" searches are about behaviour** (liked, saved, rewatched), not dates.
4. **Quality has come from item representation** (better embeddings, the te text pass), not from smarter query rewriting.
5. **The LLM rewrite was about 92% of the cost and most of the latency.** Skipping it for keyword searches was free on quality.
6. **Synthetic searches flatter text-matching methods.** Real searches are longer, vaguer and harder: known-item mrr is 0.12–0.15 on real Instagram searches, against 0.37–0.48 on synthetic ones.
7. **Most of the remaining Instagram loss is missing information** (looks, quality, thin captions). Query-side work can't fix it.

### Media (round-9 pilot)

- **YouTube.** Gemini can read a public YouTube URL and write a short description.
  - **Terms:** allowed for a research pilot; unclear for the product. It needs a legal read.
  - **Cost:** $8.51 per 1,000 videos at the pilot mix, $382–1,460 for the whole library, depending on how much of each video is read.
  - **Result:** the pilot's apparent gain was mostly a coverage artefact: described items rose whether or not they were relevant.
  - **A fair test** describes every candidate (Q8's top 50 for about 20 real "looks" searches; about $4–9).
- **Instagram:** the export has no media. Getting it needs an approved route (A-002, Proposed).
- **Recommended approach if media goes ahead:** describe-then-embed (a short text description indexed in the same text index), not a separate multimodal vector space.

## 5. How we measure

### 5.1 Protocol

Defined in `experiments/eval/PROTOCOL.md`, with A-005 accepted for round 9 only.
- **Roles:** builders never see labels or held-out search texts. Fresh evaluators pool and judge blind.
- **Preregistration:** every round is preregistered in `experiments/LOG.md`.
- **Statistics:** every comparison reports paired 95% CIs, the MDE and a Holm correction across the round's arms.
  - Adopt: gain ≥ 0.03 with CI > 0 on a primary set, and non-inferior on the others.
  - Or "cheaper-equivalent": ≥ 30% cheaper and non-inferior everywhere.
- **The noise floor:** the median per-search sd is 0.12, so the MDE is about 0.12 at 10 searches, 0.075 at 21 and 0.05 at 44. Small sets can only show large effects.
- **Grades:** 4-point (0 wrong, 1 related, 2 good, 3 exactly what was meant). An "instance vs about" rule applies: when someone asks for examples of a quality, content *about* that quality is at most "related".
- **AI judges:**
  - Two judges from different model families (gpt-5.4-mini and gemini-3-flash-preview).
  - Against Derrick's 72 calibration grades they reach κ ≈ 0.55 on relevant vs not.
  - Both are more lenient than he is.
  - On Instagram they are near chance.
  - **Derrick's grades are the binding anchor.**

### 5.2 Search sets

| Set | What it is | Size | Scorings left |
| --- | --- | --- | --- |
| `dev` | Graded searches, IG + YT, open to builders | 44 | unlimited |
| `known_dev` / `known_test` | Real YouTube searches from My Activity; target = the video watched next | 381 / 381 | test: 2 |
| `known_test_clean` | Session-disjoint subset of `known_test`, the primary YouTube held-out set | 216 | 2 |
| `ig_known_dev` / `ig_known_test` | Synthetic Instagram searches written by an LLM from a post's caption and te; biased toward te | 150 / 150 | test: 2 |
| `ig_real` | Derrick's real Instagram searches (22 topic, 8 known-item, 1 "examples of") | 31 | 2 |
| `facet_dev` / `facet_test` | Derrick's searches for sampled items, with his own "based on" ticks | 16 / 15 | test: 2 |
| `test`, `test2`, `yt_holdout` | Earlier held-out sets | 13 / 10 / 11 | used up or contaminated |

### 5.3 Grading by hand (from 9 Nov)

- **The demo app** (`experiments/demo/`) runs locally with Derrick's library preloaded. It now has:
  - grade buttons on every result;
  - a **blind grading sheet:** each queued search runs through Q8 and H0, and their top 5 are mixed and shuffled;
  - a local scorecard: at least 1 good in the top 5, 4 of 5 good, share of the top 5 that is good, exact item in the top 5;
  - a "Download grades" export (search text, item IDs and grades; no captions).
- **Plan:** about 40 graded searches.
  - The 23 real Instagram "like it" searches in the task file, plus 15–20 new ones.
  - Mix in about 4 named-creator, 4 exact-post, 3 looks/sound and 3 "examples of" searches.
  - The downloads go to the next loop round as the human anchor.
- **Eason** can grade his own library the same way.

## 6. Decisions waiting on the founders

1. **Scorecard targets:** Derrick's position is above. Eason to agree or change it.
2. **A-005:** make the stricter evaluation permanent, with Derrick's grades as the binding part and a 20-search top-5 grading each round. Recommended.
3. **A-006 (one index, planner, per-platform lists, agent tool surface):**
   - accept items 1–2 (planner, Instagram te lists) in direction;
   - defer item 3 (creator index as a list);
   - keep the nano refine optional and FM off by default.
4. **A-007:** an optional, soft **direction** input. The user writes a few lines about their current goal; it nudges searches but never filters or overrides typed words, and it lives in the private vault. It is designed only, and is a contract change. Related question: is a direction the same thing as an active **goal** (the existing `goals` table)? One concept is better than two.
5. **Media route:**
   - YouTube via Gemini URL needs a legal read before any product use.
   - Instagram media needs A-002.
   - Next media spend: the coverage-fair pilot (about $4–9), not the whole library.
6. **Rule 8 and "what is said" summaries:** real searches almost never ask for speech content. Recommended: don't keep a "said" summary in the product for now.
7. **Privacy design** (from the processor doc review): a revocable key on the user→content link, and a full-privacy setting for technical users. The advertiser-access free tier is kept only as an idea.

## 7. Recommended next steps

Ordered by payoff per effort. Most of them are free.

1. **Get Derrick's grades** (about 40 searches through the demo). Until then, every "like it" number is AI-only.
2. **Named creator as a filter or group:** match a handle, channel or known alias in code, show that creator's items first, and rank them by the rest of the search. Costs $0 and should reach the 80% target by design. Test it on `known_test_clean`'s creator searches (94).
3. **Behaviour words as filters:** liked, saved, shared, rewatched, "last summer". The data is present for 94–100% of items.
4. **A reranker for top-5 precision:** an intent-aware refine (round 9's C2: +0.025, 7 better and 0 worse, on AI grades) or a local cross-encoder over the top 30–50. Re-test on real searches with Derrick's grades.
5. **Known-item recall:**
   - closer title and phrase matching, and a properly tested behaviour boost on YouTube;
   - real search → click pairs (the full My Activity history, or the demo's "exactly what I meant" grades) for learned ranking.
6. **Coverage-fair media pilot** on about 20 real "looks" searches, once the legal question is answered.
7. **Before any product merge:** port Q8 into `scrolldigest/` behind the data contract (A-006 accepted first), with `processor_version` and `embedding_model` pinned.

## 8. Money and keys

- **API ledger after round 9** (excludes demo use since):
  - OpenAI $5.69 spent of $9.70, about **$4.0 left**;
  - Gemini $5.41 spent of $6.88, about **$1.5 left**.
- **Total research spend on the ledger** is about $11 (rounds 4–9), plus round 3 and earlier.
- **Keys** are supplied by Derrick per session. They live in the environment only and are never printed, logged or committed. Rotate any key pasted into a chat.

## 9. Where things are

| What | Where |
| --- | --- |
| Round write-ups | `docs/research/2026-10-31-youtube-round.md`, `2026-11-03-combined-loop.md`, `2026-11-03-query-understanding.md`, `2026-11-07-models-and-classifiers.md`, `2026-11-08-round8.md`, `2026-11-08-architecture-review.md`, `2026-11-09-information-audit.md`, `2026-11-09-round9.md` |
| Founders' summary (latest round) | top of `experiments/STATE.md` |
| Briefs for each loop round | `experiments/BRIEF*.md` |
| Per-round results | `experiments/results/r*.md` (scorecard: `r9-scorecard.md`; judge audit: `validation-audit.md`; Derrick's calibration: `derrick-calibration-2026-11-08.md`) |
| Preregistration log | `experiments/LOG.md` |
| Search code (experimental) | `experiments/methods/` (Q8 = `c88_search.py` and its libs), `experiments/lib/` |
| Demo app | `experiments/demo/` (README has setup and grading steps) |
| Proposed changes | `docs/amendments.md` (A-001 to A-007) |
| Product code (not yet using any of this) | `scrolldigest/` |
