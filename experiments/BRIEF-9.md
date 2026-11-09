# Brief, round 9: what each kind of media tells us, intent-first query understanding, and a scorecard for "good enough"

The roles, preregistration, `lib/ai.py` ledger and privacy rules are the same as in `BRIEF.md`, `BRIEF-4.md` and `BRIEF-8.md`. The evaluation protocol is `eval/PROTOCOL.md` as changed in round 8, plus the A-005 parts listed under "Evaluation" below. Work unattended.

**The question for this round is not "which tweak wins on dev" but "is this processor good enough, and where is it not".** People will search by creator, category, content type, what the post looks like, its sound, what is said in it, its tone, "examples of" a quality, and when they saw it. Map which of those the data can answer, measure each one, and fix the biggest gaps first. Query understanding is the main build track, because many failures come from reading the search word by word instead of by what the person means.

## Setup

1. **Data.**
   - **Same cloud session as round 8:** pull `experiments/search-loop` and keep `data/all/` as it is. The `ig_known_*` sets and round-8 runs are already there.
   - **New session:** rebuild from the split zip as in `BRIEF-8.md` setup step 1, including both vector stores. `ig_known_dev` / `ig_known_test` existed only in the round-8 session. Rebuild them with the round-8 builder (`results/r8-ig-known-build.md`) and **reset their scoring counts to 3**: the regenerated texts differ.
   - Check that `r8.5/q8` (Q8) reproduces on dev before anything else.
2. **Derrick's files** (evaluator side only; builders never open them or anything built from them):
   - `derrick-labels-2026-11-08.json`:
     - `ig_real`: 31 real Instagram searches, each tagged `known_item` / `topic` / `meta`.
     - `calibration`: his grades of 72 pooled dev items.
     - `intent_updates`: two dev intents he clarified. These are already in the repo's `evalset.jsonl`; check they are applied.
     - Write `ig_real` to `data/all/evals/labels/ig_real.jsonl` (scope `ig`) and its texts to a hidden queries file, like `known_test`.
     - The aggregates are in `results/derrick-calibration-2026-11-08.md`.
   - `search-sheet-r9-answers.json`: his searches for 40 library items (20 Instagram, 20 YouTube), sampled across visual-, audio-, type- and creator-heavy strata. Each search carries:
     - `searches` (1–2 lines);
     - `based_on`: any of `creator`, `topic`, `type`, `looks`, `sound`, `said`, `tone`, `examples`, `when`, `other`;
     - `want`: `exact` = this item, or `like` = anything like it;
     - `skip` and `caption_revealed`.
     - The evaluator builds **`facet_real`** from it. Target item = grade 3 when `want` is `exact`; when `want` is `like`, the target is one good answer and the other top-10 items are pool-judged.
     - Split it by item, stratified by `based_on`: about half to `facet_dev` (texts visible to builders) and half to `facet_test` (hidden).
     - **If the file is missing, continue without it** and build the taxonomy from `dev` + `ig_real` + a `known_dev` sample.
3. **Keys** come from Derrick and live only in the environment. Set the caps in `lib/ai.py` to what he says is left on each account. Never print, log or commit them.

## Where we are

- **Base, Q8 (B8.5):**
  - route-r1 sends short keyword searches straight to search, without an LLM rewrite;
  - 3-large int8 dense + BM25 + RRF;
  - prior-p1, a soft platform guess from the user's own library;
  - te lists for Instagram items only;
  - a gpt-5-nano refine of the top 20, only for rewrite searches the prior reads as YouTube.
- **How Q8 scores on held-out sets:**
  - YouTube: flat against H0 (`known_test_clean` mrr2 0.301 vs 0.299);
  - Instagram: +0.110 on `ig_known_test`, a synthetic set biased toward te text;
  - cost: −61% per 1,000 searches.
- **FM** (gpt-5-mini refine) is an optional +0.026 on Instagram. The te-bias question is open. See `docs/research/2026-11-08-round8.md`.
- **Derrick's calibration sheet:**
  - The AI judge agrees with him only moderately: κ 0.42 on three grades, 0.55 on relevant vs not.
  - He finds three grades too coarse and wants four: wrong / related / good / exactly what I meant.
  - He separates **instances** from **about**. "Viral SaaS marketing videos" means viral videos that market a SaaS product, not advice on SaaS marketing; "good marketing hooks" means reels with a great hook, whatever their topic.
- **Real Instagram searches (`ig_real`) are mostly topical:** 22 topic, 8 known-item, 1 meta. Synthetic known-item sets measure the minority case.
- **Known literal failures** (rounds 5–8 diagnoses):
  - wrapper words like "videos", "top 10" and "compilations" are read as topic or format;
  - a stated count is read as "list format";
  - a creator described rather than named finds nothing;
  - "examples of X" returns content about X.
- **The data has known gaps:**
  - the Instagram export has no media;
  - about 20% of Derrick's real Instagram searches are about how a post looks, and about 5% are about its sound;
  - transcripts and audio/video are never stored (AGENTS.md rule 8).

## Evaluation (applies to every phase)

- **A-005, as Proposed:**
  - dev screens;
  - large held-out sets confirm;
  - two judges from different model families (say gpt-5-mini and gemini-3.5-flash) grade every new pooled item, and disagreements are reported;
  - Derrick's calibration items anchor the judges.
  - If Derrick has rejected A-005 in the prompt, use the round-8 protocol instead.
- **4-point grades for all new pooled judging:**
  - 0 = wrong, 1 = related, 2 = good, 3 = exactly what was meant.
  - Report nDCG@10 with gains 0/1/2/3, and the collapsed 3-point version (3 and 2 → 2) for comparison with old labels.
  - Old labels keep their 3-point scale.
- **Judge rubric:**
  - Add a line for **instance vs about**: when the search asks for examples of a kind or quality, content *about* that kind is at most 1.
  - Re-run both judges on Derrick's 72 calibration items with the new rubric. Report κ against him (3-point: map his grades as given) before any arm is judged.
  - If a judge falls below κ 0.40 on relevant vs not, fix the rubric before you go on.
- **Held-out budgets:**
  - `ig_real`: 3 scorings. Score the slices separately (known-item: mrr2/s10_2; topic and meta: target = 3, pool-judge the rest).
  - `facet_test`: 3 scorings.
  - `known_test_clean`: 2 scorings left.
  - `ig_known_test`: 2 scorings left.
- **Per-facet reporting:** every arm's result is also broken down by query facet (Phase B) and by literal trap (Track 1, item 6). Report MDE with each.

## Phase 0: the first real Instagram check (free)

Score H0r8, Q8 and FM once on `ig_real` (scoring 1 of 3), with each slice reported separately.
- This is the check round 8 could not make: does the te-list gain hold on real searches, and on the known-item and topic slices?
- Write it up in `results/r9-ig-real.md`. If Q8's Instagram gain does not hold here, say so plainly at the top of the round write-up. The rest of the round builds on Q8 either way.

## Phase A: information audit (what each media type carries)

Aggregates only, never per-item personal content in git. **Output:** `docs/research/<date>-information-audit.md`, with three parts.

1. **Information audit.**
   - For each platform and source, list what text exists and how often it is empty or thin:
     - Instagram: caption, hashtags, creator handle, collection names, DM-share / like / save signals, date, te-v1c fields;
     - YouTube: title, channel, playlist names, watch count, rewatches, like, date, Shorts/duration if known.
   - For each **facet** in item 2, say which sources could answer it today, and for what share of items.
   - Example: "how it looks" is answerable from te `shown` for N% of Instagram items, from YouTube titles almost never, and from media only.
2. **Query taxonomy.** Facets:
   - `creator`: named, or described;
   - `topic` / category;
   - `type`: content type or format;
   - `looks`: visual;
   - `sound`: music or audio;
   - `said`: speech;
   - `tone` / vibe;
   - `examples`: instance-of-a-quality, the meta searches;
   - `when`: time or behaviour;
   - `platform`.

   Also mark each search's **specificity** (this exact item vs anything like it).
   - Tag every search in `dev`, a 100-search `known_dev` sample, and `facet_dev`.
   - For `facet_dev`, Derrick's own `based_on` ticks are ground truth. Build a cheap facet tagger (rules first, then a small model), report its agreement with his ticks, and use it on the rest.
   - Report the facet mix per set and per platform.
3. **Info-gap analysis.** For each facet, compare:
   - the share of searches that need it;
   - the share of their targets where the needed information exists in our text;
   - Q8's score on those searches.

   Then sort each failure into one of two classes:
   - **"information missing":** fixing it needs media or new data;
   - **"present but not used":** fixing it needs query understanding or encoding.

   Rank the gaps by (share of searches × score gap). This ranking sets the agenda below.

## Phase B: a per-facet scorecard

- Propose what "good enough" means for each facet, in user terms. For example: "a known-item search finds the item in the first screen (top 10) X% of the time"; "a topic search shows at least one *good* or *exact* item in the top 5 Y% of the time".
- Anchor the numbers on Derrick's own grades where possible, not on AI grades.
- Fill in Q8's current value with its CI, and the MDE of each set.
- Write it to `results/r9-scorecard.md`. **The targets are proposals for the founders.** Mark them as such, and do not tune arms against them.

## Track 1 (main loop): intent-first query understanding

Run it as `BRIEF-4.md` rounds: a fresh experimenter, then a fresh evaluator; preregister in LOG.md, then commit and push. Rule 6 holds: the LLM fills a validated JSON form and code acts on it.

1. **Intent frame (`qi-v1`)**, which replaces or extends qr-v1 on the rewrite path. It is a JSON object, validated against a schema, with these fields:
   - `deliverable`: what kind of item the person wants back, e.g. an instance of X vs content about X, or a tutorial;
   - `subject`;
   - `qualities`: tone, looks, sound, said;
   - `creator`: named or described;
   - `time`;
   - `specificity`;
   - `drop`: wrapper words to ignore, e.g. "videos", "reels", "that one", "top 10", "good";
   - `item_language`: one or two lines describing how a matching item would describe itself. For "good marketing hooks": "a reel whose first seconds grab attention, any topic".
   - Each field gets a weight or a null.

   Search on `item_language` plus `subject`, not on the raw words. The schema reserves an optional **`direction`** field for later (see Track 3). It is always null this round.
2. **Per-facet routing.** Each frame field goes to the signal that actually holds that information:
   - subject → dense + BM25;
   - type → te `kind` or a type classifier;
   - tone → te `vibe`;
   - looks → te `shown` (Instagram);
   - creator → a creator lookup, used **only when the frame has a creator** (round 8.7's blanket creator list displaced targets);
   - time → a soft time window.

   This is the round-5 typed-slot idea again, with the round-5 lessons applied: a curated, small format vocabulary; tone first; never a hard filter from a soft slot.
3. **Search → look → refine.** After the first retrieval, a cheap model reads the top-20 summaries against the frame and may revise `item_language` or the slot weights **once**. The revised query then runs again.
   - Report the gain, the extra cost and the p95 latency.
   - Gate it, for example to searches whose first top 10 scores low on the frame.
4. **Router fix.** route-r1 sends short searches to the instant path, but some short searches carry intent ("good marketing hooks", "funny cat fails", "viral saas ads").
   - Add a code-only intent-word detector, built from the frame's `drop`/`deliverable`/`examples` vocabulary, that sends those searches to the frame path.
   - Measure how often it fires on `known_dev` (it must not take Q8's YouTube cost saving away).
5. **Intent-aware refine.** Give the refine model the frame (deliverable, instance vs about, qualities) and the 4-point rubric, instead of the raw query alone.
6. **Literal-trap report.** Tag each dev, `facet_dev` and `ig_real` search with any traps it contains:
   - wrapper words;
   - count words;
   - examples-of / instance;
   - a described creator;
   - a format word used as a topic;
   - negation;
   - personal shorthand.

   Every arm reports its Δ per trap.
7. **Personal vocabulary (offline prototype only).** Build a per-user map from the user's words to the library's words (e.g. "geonodes" → "geometry nodes", creator nicknames), using only the user's own library (co-occurrence in their titles, captions, collection names), not search logs.
   - Test it as a query-expansion arm.
   - It is user data: it belongs in the private vault of the privacy design, never in the shared store. Note that in the write-up.

Order the arms by Phase A's gap ranking. A reasonable default: 1 + 5 together as one arm (frame + intent-aware refine), then 4, 2, 3 and 7. Each arm is one variable against the current base.

## Track 2: media pilot (small, research-only, gated)

The question is how much value is locked in media that our text does not have, and what it would cost to unlock it.

- **YouTube.** Gemini can read a public YouTube URL directly.
  - **Before any call,** check the terms that apply to that route (Gemini API terms for YouTube URLs, YouTube Terms of Service) and record the result in `experiments/research/`. If the route is not clearly allowed for this use, do not run it; report instead.
  - **If it is allowed:** run a pilot of ≤ 150 videos, chosen as the targets of `looks` / `sound` / `said` searches in `dev` + `facet_dev` + `known_dev`, plus matched distractors.
  - Ask for a **short description** of what is shown, the music or sound, and a summary of what is said (≤ 40 words, no quotes longer than a few words).
  - **Never request or keep a transcript, audio or frames** (rule 8). Whether even a "what is said" summary can be kept in the product is a founders' decision; flag it.
  - Store the descriptions under `data/` only, mark them research-only, and delete them when the round ends unless the founders approve keeping them.
  - Test the descriptions as one extra coverage-fair list, against Q8, on the facet-tagged searches.
  - Report the per-facet gain, $ per 1,000 items, and the cost of running it over the full YouTube library.
  - Use low media resolution. **Cap: $2.**
- **Instagram:** the export has no media, so **do not fetch Instagram media** (A-002 is still Proposed).
  - Instead, estimate from Phase A how many Instagram `looks`/`sound` failures are "information missing", given te `shown`.
  - Say what an approved route would need to deliver to matter.
- **Visual or audio embeddings vs describe-then-embed:** compare them on paper only (cost, storage, CPU-only feasibility, privacy fit, and whether they fit one index).
  - Recommend one for a later pilot.
  - Do not call a multimodal embedding API this round unless the YouTube pilot shows a facet gain ≥ the MDE.

## Track 3 (design only, not tested): the user's direction as an optional input

Derrick expects searches to read differently once we know where the user is heading, e.g. their current project or goal. "Marketing hooks" from someone building a SaaS product probably means hooks for that kind of product. Design it now and build nothing:

- **Shape.** One optional input to the planner, the user's stated `direction` (a few lines they write and can edit or switch off). It fills the reserved frame field and contributes to each search **softly**: it may sharpen `subject` and `item_language` and add a small boost, but it never filters, and it never overrides words the user typed.
- **Privacy.** It is user data and lives in the private vault. It is never sent to the shared content store and never used for any other user.
- **How to evaluate it later.** We would need searches written with a stated direction and graded with and without it. Say how many searches that takes, given the MDE.
- **Deliverable:** half a page in the round write-up, plus the reserved schema field. If it implies a contract change (a new field in the query request), add a **Proposed** entry to `docs/amendments.md`. Do not merge it.

## Stop rule and final scoring

- **Stop** when spend reaches the cap, after 3 rounds in a row adopt nothing, or after 6 rounds.
- **At the end,** score the finalist, Q8 and FM once each on `ig_real` (scoring 2), `facet_test` (scoring 1), `known_test_clean` (scoring 2) and `ig_known_test` (scoring 2). Report every result per facet and per trap.
- Update the scorecard with the finalist's values.

## Deliverables

- `results/r9-ig-real.md` (Phase 0);
- `docs/research/<date>-information-audit.md` (Phase A);
- `results/r9-scorecard.md` (Phase B);
- `results/r9.N-eval.md` per round;
- `docs/research/<date>-round9.md`, the round write-up, including the media pilot and the direction design;
- a **founders' summary at the top of `STATE.md`**: what is good enough now, what is not, what would fix each gap, and what needs their decision (A-005, A-006, the media route, a "what is said" summary under rule 8).

Commit and push after each round. Personal data stays out of git.

## Budget

- Phase 0 and Phase A tagging: under $0.5.
- Second judge and re-calibration: about $0.5.
- Media pilot: ≤ $2.
- Each loop round: < $1.5.
- **Total cap for the round: $8** (or what Derrick says is left, if lower).
