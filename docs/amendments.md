# Amendments

Proposed changes that **don't fit the current docs**: a request to build something differently from what `docs/` says. They are recorded here before or alongside the code, so the reasoning isn't lost and the docs stay the source of truth.

## When to add one

A coding agent (or a person) adds an amendment when someone asks for a change that would:

- contradict a rule in `AGENTS.md` or a decision in `10-decisions.md`,
- change the data contract (`03-data-contract.md`) or the RuleSpec / query API shapes,
- change the stack, the architecture boundaries (raw records, query API, action registry) or ownership,
- or otherwise do something the docs describe differently.

Small changes that fit the docs don't need one. Fixing a bug, or doing what a doc already describes, is just a normal PR.

## How it works

1. **Stop and say so.** The agent tells the person which doc and section the request conflicts with, quoting it briefly. It does not silently implement the change.
2. **Get the reason.** The person requesting it must explain *why* they want it. If they haven't, the agent asks: what problem does the current approach cause, and what does the new one fix?
3. **Make the case.** The agent writes down why the change is better than what the docs say now, *and* what it costs or risks. If the agent thinks it is not better, it says so plainly and records that too; the requester can still go ahead, but the disagreement is on record.
4. **Record it** as a new entry at the top of the log below, with status **Proposed**.
5. **Decide.**
   - Changes to the data contract, `schema/`, migrations, architecture boundaries, stack or ownership need **both founders** to accept them (in the PR or here).
   - Other changes can be accepted by the requester, noted with their name.
6. **When accepted:** update the affected docs in the same PR as the code, add a row to `10-decisions.md` that points to the amendment, and set the status to **Accepted** with the date. When rejected: set **Rejected** with the reason, and don't merge the code.
7. **Code may be written while Proposed** (e.g. on a branch to try it), but it isn't merged until the amendment is Accepted.

## Template

Copy this block to the top of the log:

```markdown
### A-NNN · Short title
- **Date:** YYYY-MM-DD
- **Requested by:** name
- **Status:** Proposed | Accepted (date, by whom) | Rejected (date, reason) | Superseded by A-NNN
- **Conflicts with:** doc and section (quote the line)

**What is requested**
One or two sentences.

**Why the requester wants it**
Their explanation, in their words where possible: the problem with the current approach.

**Why it is better than the current approach**
The concrete improvement (speed, cost, simplicity, accuracy, user value), with evidence if there is any: a measurement, an eval result, a failing case.

**Costs and risks**
What gets worse or harder: migrations, rework, lost guarantees (privacy, stability, terms), effect on the other founder's area.

**Agent's assessment**
Agree / agree with changes / disagree, and why.

**Affected**
Docs: … · Code: … · Contract change: yes/no · Needs both founders: yes/no
```

## Log

### A-004 · YouTube items, interactions and search history in the data contract
- **Date:** 2026-10-30
- **Requested by:** the search loop, round 2 (`experiments/BRIEF-2.md` › Q5), for the founders
- **Status:** Proposed
- **Conflicts with:** `03-data-contract.md` › InteractionKind (no `playlist`), › Item (`caption` described as third-party caption text; no title field), › Enrichment (`enrichments` fields), and AGENTS.md rule 1 ("Do not invent fields ad hoc").

**What is requested**
The prototype YouTube importer and API enricher (`experiments/youtube/`, synthetic fixtures only) need contract decisions before product code:
1. A YouTube playlist add maps to `collection` with `collection_name` (weight 0.8), not a new `playlist` kind; the user's capture playlist maps to `share` with `share_audience=self`.
2. For YouTube, `items.caption` holds the video **title**; the description goes to enrichment.
3. `enrichments` gains optional `title`, `description`, `tags[]`, `topic_categories[]`, `category_id`, `default_audio_language`, `live`, `chapters[]` (`{start_s, title}`), with `refresh_by` = fetched + 30 days (YouTube API terms).
4. YouTube search history stays in `raw_records` only (no table); it is a signal for later, not an item.
5. The eval format adds a `moment` search kind whose answers carry `{start_s, end_s}` (`experiments/youtube/eval_format.md`).

**Why the requester wants it**
Derrick is preparing a Takeout and YouTube searches; the next round should start without contract questions.

**Why it is better than the current approach**
The current contract has the `platform_data.youtube` fields but no place for API metadata, chapters or search history, and no interaction kind for playlists. Mapping onto existing kinds keeps rule 4 (only adapters know the platform).

**Costs and risks**
- YouTube Developer Policies III.E.4.h ("no derived data") may cover tier-1 summaries and embeddings of API text: needs a legal read before the product stores them.
- Takeout field names and file layouts were checked against Google's documentation and community sources, not a real export; verify on Derrick's Takeout.
- Captions via the API need edit permission on the video (only the user's own uploads).

**Agent's assessment**
Agree with 1–5; verify the formats on a real Takeout first.

**Affected**
Docs: 03-data-contract (InteractionKind, Item, Enrichment), 04-intake (YouTube), 08-evals-and-quality (moment kind) · Code: none in `scrolldigest/` (prototype in `experiments/youtube/`) · Contract change: yes · Needs both founders: yes

### A-003 · Enrich every item with one cheap text pass, index it separately, and add HyDE to search
- **Date:** 2026-10-30
- **Requested by:** the search loop (`experiments/BRIEF.md`), for the founders
- **Status:** Proposed
- **Conflicts with:**
  - `10-decisions.md` › 18 Oct: "Tiered, on-demand enrichment with a shared cache for public content · Enriching everything is too expensive."
  - `05-processor.md` › Stage 1 tiers: tier 1 = "Embedding, filter, info gate, simple facets"; LLM summaries only for "High value … or on demand".
  - `03-data-contract.md` › ItemCard: "`summary` … 1–2 lines (LLM; full-depth items only)"; › Embedding: one `item_embeddings` row per item, text = "`caption[:600]` + … hashtags".
  - `05-processor.md` › Stage 2 Index ("Keyword index: Postgres full-text search over caption, hashtags, transcript summary, facets") and › Query API `search` ("Hybrid: vectors + keywords + facet filters, reranked").

**What is requested**
1. **Tier 1 becomes an LLM text pass for every item** (except friends' posts): from caption, hashtags, creator, media kind and the user's collection names, a cheap model writes a one-line summary, facet slots (kind, topics, shown, said, place, people, vibe, use), the facets it can't know (`unknown`) and 3–5 likely searches. Run in Batch for history imports; per item for new captures.
2. **Index it separately:** its own keyword field/index and its **own vector** (same model as the caption vector), each fused into search by rank fusion as extra lists. Never concatenated into the caption text.
3. **Search adds HyDE:** the AI rewrite also writes three short invented captions for a matching post; their mean vector, mixed 0.3 query / 0.7 captions, joins the query phrases in both dense lists.
4. Keep bge-small as the one embedding model (A-001); the swap experiments did not justify a change.

**Why the requester wants it**
The brief asks to find what Muse finds, faster and cheaper, and to run later processing on the desktop. Captions alone top out: 37% of right answers share no word with the search.

**Why it is better than the current approach**
Measured with a fresh, blind evaluator per round on 16 dev searches over one 21k-item history (`research/2026-10-30-search-loop.md`):
- Honest caption-only search with a real AI rewrite: nDCG@10 0.49.
- + text pass indexed separately: **+0.059 [+0.016, +0.108]**, 13 searches better, 3 worse.
- + HyDE: **+0.022 [+0.008, +0.037]**, 10/1. Total **0.57, +0.080 [+0.036, +0.133]**.
- Held-out test (6 searches): **+0.023 [−0.010, +0.053]**, 4/1/1, recall@100 **+0.060 [+0.007, +0.107]**; HyDE alone not confirmed (+0.009, 2/3/1). All 22 searches: **+0.065 [+0.028, +0.103]**, 17/4/1.
- Appending descriptions to the caption instead of indexing them separately *hurt* vibe and people searches in the Muse ceiling test.
- Cost: **$0.18 per 1,000 items** with Gemini Flash-Lite Batch ($3.7 for a 21k history; ~15.8k items done in ~5 minutes), ~1.1 KB per item, +0.05 s per search. HyDE costs nothing extra (same rewrite call), +0.1 s.
- "Too expensive" in the 18 Oct decision assumed transcripts and video; a text pass is ~100× cheaper than a video description pass.

**Costs and risks**
- **Contract change:** ItemCard gains `facet_slots`, `unknown_facets`, `likely_searches`, `prompt_version`, `ai_run_id` for every item; `item_embeddings` gains a `view` (caption | enrichment), so two rows per item.
- **Privacy:** the user's collection names go to the LLM with the item. They must stay out of the shared content cache (cache the caption-only part per content, add collection names per user, or drop them). Friends' posts are never sent (463 items here). Queries already go to a cloud LLM for the rewrite.
- **Hallucination:** a reference check against Muse on 200 items found our text pass contradicts Muse on 9% of items, mostly the item kind; it misses 96% of audio, 60% of place and 50% of speech, which needs media.
- **Local fit:** the pass and the rewrite need a cloud LLM (or the user's agent over MCP); a local 1–4B model would take days of CPU for a backfill. Search itself stays local (bge-small + keyword index).
- **Evidence limits:** one person, 16 dev + 6 test searches; place searches got worse (one search); labels were partly grown by one judge per round.

**Round 2 update (2026-10-30, `experiments/BRIEF-2.md`)**
- **Search flow becomes two-stage.** No LLM rewrite can meet `05-processor.md`'s "search p95 ≤ 500 ms" from our infrastructure (a bare provider call is ~0.9 s p50). An instant first screen (no rewrite: 0.12 / 0.17 s p50 / p95) followed by the refined list (~2–3 s) keeps the target as **time to first screen**; add a second target for the refined list (proposed p95 ≤ 3 s) and a `stage: instant | refined` field (or streaming) on the `search` op. The instant screen scores ~0.07 below the refined list over all 22 searches.
- **Enrichment is background, not on demand.** Under the finalist, 52% of missed answers rank beyond 1,000 and only 12% sit in the top 200, so "enrich a weak search's nearest candidates" (`05-processor.md` › Tiers, "On demand") can reach at most ~12% of misses. Keep on-demand only as a supplement.
- **Gap flags pick facets, not items.** The per-item `unknown` facets predict a search miss only weakly (AUC 0.60, below a caption-richness score's 0.67), and no item-level gate selected misses better than chance. Use the flags to choose *which* facet a selected item's next media rung should fill, with the rule "unknown OR empty". Proposed media gate (no spend yet): one image for everything (~$0.30 / 1k items, Batch); audio for music/dance/trend and how-to/talking-head reels with an audio or said gap (~25% of items); full video for reels with weight ≥ 0.8 (~15%). Details: `experiments/results/r2-q1-gap-flags.md`.
- **Not adopted in round 2:** a library profile in the rewrite prompt (+0.006), a "look first" rewrite (+0.024 on dev, −0.038 on the held-out test, +0.007 over all 22), faster or shorter rewrite models (−0.011 to +0.010 at 3–5× the cost), and routing lookups past the rewrite (fires on 2 of 13 searches).

**Agent's assessment**
Agree. It is the only change in 24 experiments that clearly cleared the bar, it is cheap and fully batchable, and it fits the derived-data rules (rebuildable, versioned by prompt and model). Recommend accepting 1, 2 and 4 now, with collection names kept per user; accept 3 (HyDE) as an optional extra, since it is free but was not confirmed on the test split; and revisiting when media arrives (the same separate-field pattern should carry a media description pass).

**Affected**
Docs: 03-data-contract (ItemCard, Embedding), 05-processor (Stage 1 incl. › On demand, Stage 2, Query API › search, Performance targets), 07-privacy-and-safety (collection names to the LLM), 10-decisions (18 Oct row) · Code: none in `scrolldigest/` yet (prototype in `experiments/methods/`) · Contract change: yes · Needs both founders: yes

### A-002 · Getting thumbnails, keyframes and audio for each reel
- **Date:** 2026-10-30
- **Requested by:** Derrick
- **Status:** Proposed
- **Conflicts with:**
  - `AGENTS.md` › rule 7: "Preference order: data the user hands us (exports, DM shares, Takeout) → official APIs → paid providers with clear terms. No logged-in bot accounts, no evading rate limits or blocks."
  - `04-intake.md` › Rules of the road, and `10-decisions.md` › Sep: "Official Instagram API only for capture; no logged-in automation."

**What is requested**
Get visual and audio content for each reel without depending on a scraping vendor, ideally with "microdownloads": fetch only the streaming manifest, the audio track and a few keyframes instead of whole videos, and feed those to the description pass and to multimodal embeddings.

**Why the requester wants it**
Thumbnails and frames likely carry the most information about a reel, and search results show captions are the ceiling (37% of right answers share no words with the query). Meta's oEmbed stopped returning thumbnails in Nov 2025. Relying on a third-party scraper (Apify) is fragile and outside our control.

**Why it is better than the current approach**
The docs give no route to images or audio at all, so the visual/audio searches (vibe, said/shown, audio, more-like-this) stay capped. Partial downloads cut bandwidth and model cost: a few keyframes plus audio costs roughly 2–4× fewer Gemini tokens than the full video (video ~100–300 tokens/s; audio 32 tokens/s; an image ≤384 px 258 tokens, per Google's token docs).

**Options considered**

| Route | What it gives | Platform-terms risk | Verdict |
| --- | --- | --- | --- |
| A. Official DM-share webhook, then partial (HTTP range) reads of the media we receive | Ongoing captures. Meta's docs only say "the URL for the shared media or post" is included; whether it's a media file must be confirmed with a real webhook | Low: official API, user-initiated | **Do first:** capture one real webhook as a fixture |
| B. On-device capture in the desktop app / browser extension (the user's own client already loads the media they view or share) | History and ongoing; data stays local; fits local-first | Low–medium: the user's own session on their own device; no bots | **Plan with the desktop app** |
| C. Public post-page metadata (og:image) fetched logged-out, rate-limited, only for items in the user's import | Thumbnails for history imports | Medium: Meta's terms forbid automated collection without permission; a 2024 ruling (Meta v. Bright Data) didn't find logged-out scraping of public data breached them on that record, but it is not a green light, and Meta could revoke the app we need for DM capture | **Only after legal review**, thumbnails only |
| D. Private streaming manifests (DASH) via Instagram's internal web/app APIs | Audio + keyframes, cheapest bandwidth | High: private endpoints, usually logged-in sessions, actively blocked, fragile; conflicts with rule 7 | **Not recommended** |
| E. Third-party providers (Apify etc.) | Metadata incl. song title/artist, thumbnails | Medium; vendor dependency | Fallback only, behind the enricher interface |

**Costs and risks**
Routes B–E carry platform risk to the one Meta relationship we depend on (DM capture). Partial reads of official media (A) still need the media URL to be a file; if it's only a post link, A gives no media.

**Agent's assessment**
Agree with the goal; disagree with D. Recommend A now, B as the main route for history once the desktop app exists, C only after a legal check, E as fallback. The microdownload idea itself is good and applies to A and B: range reads of keyframes + audio instead of whole files.

**Affected**
Docs: AGENTS.md (rule 7 wording if C is accepted), 04-intake, 07-privacy-and-safety, 10-decisions · Code: intake enrichers · Contract change: no (new enrichment fields covered by A-001) · Needs both founders: yes

### A-001 · How reels are stored and searched
- **Date:** 2026-10-30
- **Requested by:** Derrick
- **Status:** Proposed
- **Conflicts with:**
  - `03-data-contract.md` › Item: "One piece of content, stored once per user however many times they touch it." (proposes shared content + per-user items)
  - `03-data-contract.md` › Embedding: one vector per item, "Index with HNSW (cosine)". (proposes item + chunk vectors, a versioned search text, exact search per user for now)
  - `02-tech-stack.md` › Embeddings: bge-small only. (confirms bge-small as the single model for cloud and desktop; adds OpenAI 512d as a tested fallback)
  - `07-privacy-and-safety.md` › Friends: "The recipient of a friend share is not stored on the interaction." (proposes opt-in storage)
  - `10-decisions.md` › 15 Oct: "Transcripts not stored." (proposes a per-source rule)

**What is requested**
Adopt the storage and search design in [research/2026-10-30-search-storage.md](research/2026-10-30-search-storage.md): shared `content` rows with an assembled, versioned `search_text`; item and chunk vectors; a weighted keyword index; facets; audio title/artist; and a search flow of AI rewrite + meaning + keyword search, rank fusion and pseudo-relevance feedback, with thin items held out of meaning search until enriched.

**Why the requester wants it**
Search is the part every later feature uses (rules, boards, digests, MCP). Captions-only, one-vector-per-item search found the right reel in the top 10 well under half the time on real searches, and failed outright on audio and on content that is only said or shown.

**Why it is better than the current approach**
Measured on 22 real searches over a 20k-item history: meaning search alone 0.22–0.34 nDCG@10; the proposed flow 0.50–0.51, with ~57% of the top 10 correct and the first right answer usually near the top (MRR ~0.9). Sharing content means each public reel is enriched and embedded once for every user. One open model everywhere lets the cloud's first report hand vectors straight to the desktop app.

**Costs and risks**
A data contract change before any production data exists (cheap now, expensive later). More derived tables (chunk vectors, search text versions). Storing share counterparts, even opt-in, weakens a privacy default and needs clear consent. Per-source transcript rules need a terms check per platform. Results come from one person's data and 22 searches.

**Agent's assessment**
Agree. The measured gains are large compared with the noise, the changes are additive to the existing raw/core/derived rules, and the riskiest part (share counterparts) is opt-in. Recommend accepting items 1, 2 and 5 now, and 3 and 4 after the privacy and terms checks.

**Affected**
Docs: 03-data-contract, 02-tech-stack, 05-processor (Index, Query API, Search), 04-intake (audio metadata, description pass in the benchmark), 07-privacy-and-safety, 10-decisions · Code: none yet · Contract change: yes · Needs both founders: yes
