# 10 · Decisions

Newest first. Don't reopen a decision without new evidence. To change one, propose it in [amendments.md](amendments.md); once accepted, add a new row here that supersedes the old one and links the amendment (e.g. "see A-003").

| Date (2026) | Decision | Why | Status |
| --- | --- | --- | --- |
| 28 Oct | Vision boards (Pinterest of all media) and semantic search come later in the frontend; the backend embeds every item and exposes `similar` / `suggest_for_board` so boards need no backend redesign | Boards are a core part of the vision; groundwork is cheap now and expensive later | Agreed |
| 28 Oct | Backend first; frontend deferred | Prove the processor and the data flow before designing screens | Agreed |
| 28 Oct | Python for the whole backend (FastAPI + workers); Supabase for database, vectors, auth, storage and queues | Processor is ML work; intake needs media/parsing tools; one language for both founders | Agreed |
| 28 Oct | Supabase Edge Functions are not used for intake | Time/memory limits; intake jobs are long and heavy | Agreed |
| 28 Oct | Split: Derrick owns both processors (adapters + core) and the interpreter; Eason owns intake, then triggers/executor/output actions | Each owns something that works end to end; they meet at `raw_records`, the query API and the action registry | Agreed |
| 28 Oct | MVP: 2 inputs (Instagram, YouTube), 2 outputs (email, then Google Calendar), basic processor | Smallest scope that exercises every layer | Agreed |
| 28 Oct | Local database / desktop app (Electron) is a future direction, not MVP; all storage behind `db/` so it can move | Scheduled rules, shared cache and phone capture need a server now | Agreed |
| 28 Oct | Processor is read-only (query API, JSON in/out); side effects only in the executor | A query bug can never send email; processor testable alone | Proposed |
| 28 Oct | Every request compiles to a RuleSpec: when + content + do, using only registered actions; preview before activation | The LLM fills a form; code acts; safe and testable | Proposed |
| 28 Oct | Onboarding asks only platforms, a guess at how much is useful, and an optional goal; the rest comes from the theme check | Low friction; "your guess vs your data" is a strong first-report moment | Proposed |
| 20 Oct | Add a fourth theme relation, *someday*: wanted but parked, never nagged, resurfaced when time frees up | 4 of 12 answers in the first test were "want it, no time" | Agreed |
| 20 Oct | Merge overlapping candidate themes and fold them into existing themes before asking | Overlapping pairs got identical answers | Agreed |
| 19 Oct | Themes update by incremental assignment with a frozen transform; leftovers become candidate themes the user confirms | Re-clustering kept 9 of 23 themes after a 9% data change; incremental kept all | Agreed |
| 19 Oct | Own accounts are suggested by the processor and confirmed by the user | Reply-based and share-ratio rules both misfired on real data | Agreed |
| 18 Oct | DM shares are interactions: to self = save strength (1.0), to a friend = 0.6, received = only if acted on | Shares outnumber saves ~5:1; self-shares barely overlap with saves | Agreed |
| 18 Oct | One processing path for all platforms; only adapters differ | No per-platform processors | Agreed |
| 18 Oct | Embeddings are the backbone for search, themes and direction | Keyword search alone misses meaning | Agreed |
| 18 Oct | Search runs over all items; themes filter or boost, never gate | A misfiled item would be unfindable | Agreed |
| 18 Oct | Tiered, on-demand enrichment with a shared cache for public content | Enriching everything is too expensive | Agreed |
| 18 Oct | Collections are saved searches evaluated lazily; a rule is a collection with a trigger and an action | One cheap mechanism | Agreed |
| 18 Oct | Interaction intent defaults to interest; only friend/support biases get rules | Per-interaction intent models cost more than they add | Agreed |
| 18 Oct | Theme IDs and embedding versions stable across runs; pinned themes never auto-changed | Names, rules and agents depend on them | Agreed |
| 18 Oct | Questions are chosen by the LLM layer by information value | Template questions were shallow | Agreed |
| 18 Oct | Personalization via lightweight per-user layers, not per-user model training | Cheap, fast, reversible | Agreed |
| 18 Oct | Match goals against items, not theme averages | Theme-level matching gave wrong results | Agreed |
| 17 Oct | History export backfills once; ongoing data arrives through shares | Shares are the user's own filter | Agreed |
| 17 Oct | Center embeddings and reduce to 20 dims (PCA) before Ward clustering | Raw vectors were too similar to cluster | Agreed |
| 17 Oct | Information gate holds back captions with too little text | Thin captions were pulled into random themes | Agreed |
| 15 Oct | Raw / core / derived storage layers; versioned JSON; new processor versions beside old ones | Change processing without migrations; safe rollouts | Agreed |
| 15 Oct | One global Item/Interaction model; platform extras in typed `platform_data` | No per-platform columns | Agreed |
| 15 Oct | pgvector inside Postgres; hybrid search | No separate vector database | Agreed |
| 15 Oct | Transcripts not stored; summaries and moments kept | Platform terms and privacy | Agreed |
| Sep | Official Instagram API only for capture; no logged-in automation | Avoids bans and platform risk | Agreed |
| Sep | Real deletion; no ads; no selling data | Trust is the positioning | Agreed |
| Sep | MCP access for the user's own agent is a first-class output and the paid core | Defends against commoditisation of the AI layer | Agreed |
