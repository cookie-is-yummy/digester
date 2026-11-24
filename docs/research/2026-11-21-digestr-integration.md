# The digestr spec against what already exists

*21 Nov 2026 · written by the coding agent for Eason · read from `main`, `research/search-storage` and `experiments/search-loop` at `4a2dd26`. Nothing here was run: it is a reading of the docs and the prototype code, with file names so each claim can be checked.*

**In one line:** most of the [digestr spec](2026-11-21-digestr-spec.md) is already designed in `docs/` or built in the prototype under `experiments/mvp/`. The new parts are forwarded links from any platform, reading the video itself, plans built from a cluster, and a per-user web view. Five lines of the spec conflict with agreed docs and need an amendment before they are built.

## How the three branches relate

| Branch | Holds | Commits |
| --- | --- | --- |
| `main` | The design docs and `AGENTS.md` | 1 |
| `research/search-storage` | `main` plus the search-storage and enrichment research and A-001, A-002 | 3 |
| `experiments/search-loop` | Both of the above plus eleven rounds of search experiments and the bot prototype | 467 |

`experiments/search-loop` contains the other two in full, so working from it loses nothing.

## How data is stored with vectors

There are three versions of the answer. They disagree, and only the third one runs.

| | Agreed in the data contract | Proposed (A-001, A-003, A-006) | What the prototype runs (Q8) |
| --- | --- | --- | --- |
| Where | Postgres with `pgvector`, table `item_embeddings` | Same | Files on disk under `data/<library>/corpus/emb/`: `ids.json`, `q8.npy`, `scale.npy` |
| Model | `bge-small-en-v1.5`, 384 dimensions, run locally | bge-small kept as the one model | OpenAI `text-embedding-3-large` cut to 1,024 dimensions |
| Stored as | `vector(384)` | Half precision | int8 with one scale per dimension, about 1 KB an item |
| Text embedded | `caption[:600]` plus up to 15 hashtags | A versioned `search_text`, and a second vector for the AI text pass, never joined into the caption | Item text (title, caption, creator, collection names); a second set over the AI text pass for Instagram only |
| Vectors per item | One | One item vector, chunk vectors for long text, and a `view` column (caption or enrichment) | One, or two for Instagram posts |
| Index | HNSW, cosine | Exact search per user for now | Exact search: 0.04 to 0.07 s over 20,000 vectors |
| Who owns a vector | One row per user per item | A shared `content` row per public post, with a thin `user_items` row per person | One library per person |

What the experiments found, and what to carry over:

- **Vectors alone are not enough.** Meaning search scored 0.22 to 0.34 (nDCG@10). Keywords, vectors and a query rewrite merged by rank scored 0.47 to 0.51 (`2026-10-30-search-storage.md`).
- **Search is several lists merged.** Q8 merges a vector list and a BM25 keyword list by reciprocal rank fusion (k = 60), and adds two more lists over the AI text pass for Instagram posts.
- **Keep the AI summary in its own vector.** Appending it to the caption hurt some searches; indexing it separately gained +0.059 (A-003).
- **Thin captions stay out of vector search** until enriched. About a quarter of Instagram items have almost no caption and sit near every vague query.
- **Small vectors are fine.** 512 dimensions at half precision matched full size; int8 is the current store.
- **Quality came from what is embedded,** not from smarter query rewriting. The rewrite was about 92% of search cost.
- **Every vector set records its model** (`AGENTS.md` rule 10). Vectors from two models cannot be mixed, so a model change writes a new set beside the old one.

For the spec's lines:

- **"Store: Postgres with pgvector"** matches the 15 Oct decision. Nothing is in Postgres yet: porting Q8 behind the data contract is step 7 of the 9 Nov next steps, after A-006 is accepted.
- **"Cluster: embeddings group related items into collections"** is the themes stage in `05-processor.md`: centre the vectors, reduce to 20 dimensions, Ward clustering, then incremental assignment so themes stay stable. The person confirms each theme. Collections are saved searches, not stored clusters (18 Oct decision).
- **"Deduplicate: hash the URL"** is `dedup_key` (`instagram:<shortcode>`, `youtube:<video id>`), which survives the same post arriving under different URLs.
- **"Cached for all users"** is agreed for enrichment (18 Oct). Sharing the item and its vector across users is A-001, still Proposed.

**The open decision:** the contract says bge-small at 384 dimensions and the prototype uses 3-large at 1,024. The founders have not chosen. Do not write the `item_embeddings` migration until they do.

## Step 1 of the spec: the bot

| Spec line | Status | Where |
| --- | --- | --- |
| Channel behind an adapter | Built | `experiments/mvp/channels/base.py`, with `web.py`, `console.py`, `imessage_mac.py`, `sendblue.py` |
| iMessage and SMS through Sendblue, Linq or Photon | Sendblue adapter built, never run on a real line. Vendors compared, with prices | `BRIEF-10.md` section 6 |
| Telegram for development | Not built. The test page and the console do this job | `python3 -m mvp.bot --channel web` |
| Phone number is the account | Built in the prototype (`data/mvp/people.json`). The agreed stack says Supabase Auth with Google sign-in | `02-tech-stack.md` |
| Onboarding in three messages | Built differently: consent, then a five-message setup from a profile guessed from the library | `onboarding.py`, `profile.py` |
| Forwarded links from any platform | **Not built.** A link alone carries no caption, so the bot would ask for a word or two | `BRIEF-10.md` section 6b |
| YouTube by OAuth, synced daily | Sign-in built (device flow). The API gives likes, playlists and subscriptions, **never watch history** | `yt_auth.py`, `ytreads.py`, `04-intake.md` |
| Reels shared to our Instagram account | Designed, an agreed MVP input, not built. Needs Meta app review; replies only within 24 hours | `04-intake.md` › Live capture |
| Linked by a one-time code | New. The docs mention only "sign up by DM" from an earlier prototype | |
| Instagram export to Google Drive | The bot already words this route for testers. Pick-up from Drive is by hand | `refresh.py` |
| Plain-language commands | Built: the model fills a form, code checks it and acts | `interpret.py`, `schema.py`, `followup.py` |
| "pause", "delete my data" | Built. Deletion leaves traces that A-018 lists | `handler.py`, `store.py`, `export.py` |

## Step 2 of the spec: ingestion

| Spec line | Status | Where |
| --- | --- | --- |
| Normalize to one record | Agreed: `raw_records`, then `items` and `interactions` | `03-data-contract.md` |
| Signal type | Agreed: interaction kinds with weights | Same |
| Weight: forwarded and saved high, liked medium, watched low | Agreed, with numbers: share to self 1.0, save 0.8, share to a friend 0.6, like 0.3, watch 0.1 | Same |
| Fetch caption first, video only when thin | Agreed as tiered enrichment and the information gate. No enricher is built | `04-intake.md` › Enrichment, `2026-10-30-enrichment-cascade.md` |
| Transcribe, and sample frames for on-screen text | **Conflict**, see below. One route exists, off by default: asking a YouTube video through Gemini's link input | `videoask.py`, A-017, A-002 |
| Extract structured JSON | Agreed as `ItemCard` facets; built in the prototype for named things, ingredients and steps | `03-data-contract.md`, `extract.py` |
| Types | Contract has recipe, place, opportunity, tutorial, idea, product, workout, advice, news. Spec adds event, book and entertainment | Contract change |
| Confidence score and a flag for shaky claims | New fields | Contract change |
| Stored within about fifteen seconds | The roadmap's gate is 30 seconds (M2) | `09-roadmap-and-ownership.md` |
| A 500-item export in the background | Designed as queues; the prototype imports in a background worker | `01-architecture.md`, `refresh.py` |

## Step 3 of the spec: output

| Spec line | Status | Where |
| --- | --- | --- |
| Instant receipt | Designed as optional | `01-architecture.md` › flow B |
| Weekly digest, three actions | The prototype moved away from a weekly digest on 12 Nov: it answers on request, at a named time, or on repeat. A recap exists | `digest.py`, A-010 |
| Low-intent items as a pattern only | Built as trends: the last 8 weeks against the 26 before | `attention.py` |
| Recall with the original link | Built, the most tested part | `history.py`, `retrieve.py`, `compose.py` |
| Collections into plans | Grocery list from a recipe is built. Itinerary, weekly split and learning sequence are new | `outputs.py`, `actions/todo.py` |
| Actions only after a yes | Built, and the prototype's main rule: show, then wait for yes | `drafts.py`, `grants.py`, `actions/` |
| Calendar, reminders, Maps | Built: calendar link and `.ics`, reminders, to-dos, Maps link. A shopping cart is new | `actions/calendar.py`, `todos.py` |
| Follow through | Built: deadline reminders and one nudge for an overdue to-do | `todos.py`, `scheduler.py` |
| Monthly consumption mirror | Designed as "direction" (goals against attention); the monthly note is new | `05-processor.md` › Direction |
| Web view by magic link | **Not built.** Frontend is deferred (Agreed). The test page has no per-person login | A-018, conditions 3 and 4 |
| Quiet hours, frequency | Built | `schedule.py`, `scheduler.py` |
| Mute a topic | Not found in the prototype | |

## What needs an amendment before it is built

`AGENTS.md` says a request that conflicts with the docs is written into `docs/amendments.md` as Proposed first. These lines of the spec conflict:

1. **Pulling the video, transcribing it and sampling frames.** Rule 7 limits intake to data the user hands over, official APIs and providers with clear terms. Rule 8 and the 15 Oct decision say transcripts, audio and video are never stored. How to get the media lawfully is A-002, still Proposed, and the Gemini route (A-017) is waiting on a legal read.
2. **Links from any platform.** The agreed MVP is two inputs, Instagram and YouTube.
3. **Text messages as the product's front door.** `00-vision.md` lists text messages as out of scope. A-008 and A-009 cover the texting bot and are still Proposed.
4. **The phone number as the account, and a magic-link web view.** The agreed stack is Supabase Auth with Google sign-in, and the frontend is deferred.
5. **New item types, a confidence score and a shaky-claim flag.** These change the data contract, which needs both founders.

A-018 also proposes freezing features until 20 answers are graded. If it is accepted, it comes before any of this.

## What was brought into this folder

- **The whole history of all three branches,** on a local branch `digestr/integration` made from `experiments/search-loop`. No file was copied by hand and nothing was ported into product code: `src/scrolldigest/` does not exist yet, and `AGENTS.md` says to port ideas, not prototype files.
- **Kept from the earlier local setup:** the skills and agents under `.claude/`, and the spec, now marked as a proposal.
- **Dropped from the earlier local setup:** the first `CLAUDE.md`, which said nothing was built and listed rules taken from the spec alone, and the `redis-patterns` skill, since queues here are `pgmq`.
