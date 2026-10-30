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
