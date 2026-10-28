# 03 · Data contract

The shared shapes that intake, the processor, rules, actions and (later) the hub and MCP all read and write. In code they live in `src/scrolldigest/schema/` as Pydantic models; tables live in `supabase/migrations/`. **This doc and those models must agree.** Change both in the same pull request.

## Conventions

- **IDs:** prefixed ULIDs (`itm_01J9…`). Prefixes: `raw_` raw record, `upl_` upload, `brd_` board, `itm_` item, `int_` interaction, `enr_` enrichment, `ses_` session, `mom_` moment, `thm_` theme, `gol_` goal, `qst_` question, `oac_` own account, `rul_` rule, `run_` rule run, `dlv_` delivery, `act_` action, `plc_` placement, `dig_` digest, `rep_` report, `not_` note, `air_` AI run.
- **Time:** ISO 8601 UTC. The user's `timezone` is applied only for display and scheduling.
- **Ownership:** every user row carries `user_id`; row-level security; deleting a user cascades everywhere (except the shared enrichment cache, which holds no user data).
- **Evidence:** every generated claim cites item IDs: `evidence: ["itm_…"]`.
- **Provenance:** facts about the user are `stated` (they said it), `inferred` (we concluded it, with `confidence`) or `agent` (their AI wrote it).
- **Versioning:** derived rows carry `processor_version`; embeddings carry `embedding_model`; LLM outputs carry `ai_run_id` and `prompt_version`.
- **Third-party text** (captions, transcripts, comments) lives in clearly named fields and is never mixed into generated text.
- **Global model, platform extensions:** every platform maps into the same Item and Interaction shapes. Platform-only data lives in typed `platform_data`.
- **Enums** are text columns validated by Pydantic `StrEnum`s.

## Storage layers

| Layer | Holds | Rebuildable? |
| --- | --- | --- |
| **Raw** (append-only) | Payloads exactly as received: export entries, webhook bodies, extracted DM share objects, API responses, enricher responses | No. Deleted only on user deletion or retention rules |
| **Core** | Items, interactions, uploads, own accounts, goals, answers, notes, confirmed theme labels, rules, actions, placements, deliveries | Partly. User-created rows are never regenerated |
| **Derived** | Item cards, facets, embeddings, filter scores, themes (unconfirmed parts), trends, reports, digests, profiles | Yes, by re-running the processor |

New processor versions write derived rows **beside** the old ones; we compare on eval sets, switch `active_processor_version`, then delete the old set.

## Shared values

| Name | Values |
| --- | --- |
| `Platform` | instagram, youtube *(later: tiktok, reddit, x, linkedin, article, bluesky, facebook)* |
| `RawSource` | instagram_export, instagram_dm, youtube_takeout, youtube_api, enricher |
| `CaptureMethod` | export_import, dm_share, playlist, share_sheet, email_forward |
| `InteractionKind` | share, save, collection, like, comment, watch, view |
| `ShareAudience` | self, friend |
| `ItemType` | recipe, tutorial, place, opportunity, idea, product, workout, advice, news, entertainment, other |
| `FilterClass` | content, entertainment, social |
| `InfoClass` | ok, low, non_english |
| `ItemStatus` | pending, enriched, processed, failed |
| `ItemState` | saved, reviewed, tried, done, dismissed |
| `ThemeStatus` | candidate, active, archived |
| `ThemeRelation` | pursue, practise, someday, enjoy, mute |
| `Trend` | new, rising, steady, fading, dormant |
| `Provenance` | stated, inferred, agent |
| `ActionState` | suggested, accepted, done, dismissed |
| `RuleStatus` | draft, active, paused |
| `TriggerType` | now, once, schedule, input_event, deadline *(later: location, calendar_context)* |

## Capture

### RawRecord — `raw_records`

| Field | Type | Notes |
| --- | --- | --- |
| `id` | str | `raw_` |
| `user_id` | str | |
| `source` | RawSource | |
| `kind` | str | Source-specific, e.g. `saved_post`, `liked_post`, `collection_entry`, `dm_share`, `video_watched`, `post_viewed`, `comment`, `followers`, `following`, `watch_history`, `playlist_item`, `enrichment` |
| `format_version` | int | Bumped when the platform's format changes |
| `payload` | jsonb | Exactly as received (for DMs: the share object only, see `04-intake.md`) |
| `upload_id` | str? | When from an export/Takeout |
| `received_at` | timestamp | |
| `refresh_by` | timestamp? | For API data with retention limits |
| `adapted_at` | timestamp? | Set by processor 1 |

### Upload — `uploads`

`{ id, user_id, source: instagram_export | youtube_takeout, storage_path, status: received | extracting | adapted | processed | failed, counts: {raw, items, interactions}, timings: {extract_s, adapt_s, first_report_s, full_s}, created_at }`

### Item — `items`

One piece of content, stored once per user however many times they touch it.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | str | `itm_` |
| `user_id` | str | |
| `platform` | Platform | |
| `source_url` | str | As received |
| `dedup_key` | str | `{platform}:{content_id}` (e.g. `instagram:DZFqkwJASjJ`). Unique per user |
| `first_seen_at` | timestamp | Earliest interaction |
| `caption` | str? | Third-party text (from export, DM payload or enrichment) |
| `creator` | object? | `{ handle, name?, url? }` |
| `creator_relation` | str | mutual, following, none |
| `importance` | float | 0–1, `min(1, Σ interaction weights)` |
| `processing_depth` | str | full, light, count_only (by strongest interaction) |
| `status` | ItemStatus | |
| `interaction_kinds` | str[] | Denormalized for fast filtering |
| `platform_data` | jsonb (v) | See Platform extensions |
| `content_cache_key` | str? | Key into the shared enrichment cache (public content only) |

### Interaction — `interactions`

| Field | Type | Notes |
| --- | --- | --- |
| `id` | str | `int_` |
| `item_id` | str | |
| `kind` | InteractionKind | |
| `at` | timestamp? | Collections from the Instagram export have no time |
| `capture_method` | CaptureMethod | |
| `weight` | float | From the table below, stored for reproducibility |
| `share_audience` | ShareAudience? | Shares only |
| `sent_by_own_account` | bool? | Shares only: sent from the main account vs one of the user's other accounts |
| `collection_name` | str? | Instagram collections |
| `comment_class` | str? | Comments only: support, social, question, other |
| `session_id` | str? | Live captures |
| `raw_record_id` | str | Traceability |

**Weights (Agreed starting values; tune against what users act on):**

| Kind | Weight | Processing depth |
| --- | --- | --- |
| share, audience self | 1.0 | full |
| save, collection | 0.8 | full |
| share, audience friend | 0.6 | full |
| like | 0.3 | light |
| comment, class question | 0.8 | full |
| comment, class support/social | 0 (bias signal only) | light |
| watch, view | 0.1 | count_only |

Received shares (someone sent the user a post) are **not** interactions. They are counted only, and become an item only if the user then likes, saves or reshares it.

### OwnAccount — `own_accounts`

Accounts that belong to the user (for detecting self-shares). The processor **suggests**, the user **confirms**.

`{ id, user_id, platform, display_name, handle?, status: suggested | confirmed | rejected, evidence: {threads, share_ratio, replies_ratio}, confirmed_at? }`

### Enrichment — `enrichments`

One row per item per provider. Public-content enrichment is cached once in `content_cache` (no user data) and linked from items.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | str | `enr_` |
| `item_id` | str | |
| `provider` | str | e.g. export, instagram_dm, youtube_api, apify_instagram, transcript_<provider> |
| `tier` | int | 0–3 |
| `creator`, `caption`, `hashtags`, `top_comments`, `thumbnail_url`, `duration_s`, `posted_at` | various, optional | |
| `transcript_summary` | str? | Written during processing |
| `transcript_ref` | str? | How to refetch the full transcript on demand (transcripts are not stored) |
| `on_screen_text` | str? | Tier 3 |
| `cost_usd` | float | 0 for free sources |
| `fetched_at`, `refresh_by` | timestamp | |

### Session and Moment

- `sessions`: `{ id, user_id, started_at, ended_at, item_count, summary? }`; new session after a 30-minute gap between captures (tunable).
- `moments` (long videos): `{ id, item_id, start_s, end_s, summary, score, deep_link }`.

## Platform extensions (`platform_data`, versioned)

| Platform | Fields |
| --- | --- |
| instagram | `media_kind` (reel, post, carousel), `owner_handle`, `owner_name?`, `hashtags[]`, `collections[]` |
| youtube | `video_id`, `channel_id?`, `channel_title?`, `duration_s?`, `playlist_id?`, `chapters?[]` (`{start_s, title}`), `watch_count?` |

## Understanding (derived)

### ItemCard — `item_cards`

| Field | Type | Notes |
| --- | --- | --- |
| `item_id` | str | One active card per item per `processor_version` |
| `filter` | object | `{ class: FilterClass, p: {content, entertainment, social} }` |
| `info_class` | InfoClass | Information gate result |
| `primary_type` | ItemType? | |
| `facets` | Facet[] | One per type, see below |
| `summary` | str? | 1–2 lines (LLM; full-depth items only) |
| `theme_id`, `subtheme_id` | str? | |
| `goal_ids` | str[] | |
| `relevance` | float | 0–1 against goals and themes |
| `sensitive_category` | str? | health, relationships, money; hidden from agents unless opted in |
| `state` | ItemState | User-controlled; survives reprocessing |
| `user_note` | str? | User-created; survives reprocessing |
| `processor_version` | str | |

**Facets** (`{ type, ... }`): recipe `{ingredients[{name, qty?, unit?}], steps[], time_min?, weeknight}`; place `{name, city?, country?, category?, price_level?, maps_url?}`; opportunity `{title, organization?, deadline?, link?, eligibility?}`; tutorial `{steps[], tools[], skill_level?}`; idea `{idea, hook?}`; product `{name, price?, currency?, link?}`; workout `{exercises[{name, sets?, reps?, duration_s?}], total_min?}`; advice/news/other `{claim}`.

### Embedding — `item_embeddings`

`{ item_id, embedding_model, text_hash, vector vector(384), created_at }`. Text embedded: `caption[:600] + "\n" + up to 15 hashtags as #tag` (plus transcript summary when present). Index with HNSW (cosine).

### Theme — `themes`

| Field | Type | Notes |
| --- | --- | --- |
| `id` | str | `thm_`; **stable across runs** |
| `parent_id` | str? | Set for sub-themes (one level) |
| `status` | ThemeStatus | candidate (leftover cluster awaiting confirmation), active, archived |
| `name`, `description` | str | |
| `name_provenance` | Provenance | |
| `relation` | ThemeRelation? | User's label; null until asked |
| `relation_provenance` | Provenance? | |
| `pinned` | bool | True once the user named/labelled it or a rule depends on it; never removed or renamed automatically |
| `mixed` | bool | Flagged for splitting |
| `auto_terms` | str[] | Distinctive terms |
| `centroid` | vector | In the frozen theme space |
| `cohesion` | float | Mean member similarity to centroid |
| `item_count` | int | |
| `trend` | Trend | |
| `share_recent`, `share_before` | float | Weighted share, last 6 months vs 6–18 months ago |
| `share_by_period` | object | `{ "2026-H1": 0.13, ... }` |
| `first_seen`, `last_seen` | timestamp | |
| `evidence` | str[] | 3–5 most typical item IDs |
| `agent_visible` | bool | Privacy scope |
| `theme_space_id` | str | Which frozen transform it lives in |

### ThemeSpace — `theme_spaces`

The frozen transform used to place items into themes, so new items can be assigned without re-clustering: `{ id, user_id, embedding_model, mean[384], pca_components[20×384], pca_center[20], params, created_at }`.

### Report — `reports`

The first report and later refreshes. `{ id, user_id, kind: first | refresh, processor_version, built_from: {upload_ids, item_count}, sections: {...}, created_at }`. Sections are defined in `05-processor.md` › First report.

## User model

- **Goal** `goals`: `{ id, user_id, text, keywords[], priority: high|medium|low, provenance, status: active|paused|achieved|dropped, target_date?, source: onboarding|question|request|agent }`.
- **Onboarding answers** `onboarding`: `{ user_id, platforms[], useful_share_guess (0–1), goal_text?, created_at }`.
- **Question** `questions`: `{ id, user_id, type: confirm_theme | label_theme | merge_themes | own_account | borderline_item | search_check | link_goal | sensitive_opt_in, text, why, options[{label, effect}], subject{kind, id}, info_value, status: open|answered|skipped, answer?, comment?, ask_after? }`.
- **WorkflowProfile** `workflow_profiles`: `{ user_id, todo_home, notes_home, calendar_home, planning_rhythm?, conventions{}, channel_performance{} }`.
- **Profile** `profiles` (for agents, later): versioned snapshot `{ stated, revealed{active, emerging, fading}, gaps[], patterns[], open_loops[], rendering{brief, standard} }`.

## Doing

### Rule — `rules`

| Field | Type | Notes |
| --- | --- | --- |
| `id` | str | `rul_` |
| `original_text` | str | The user's words |
| `compiled` | RuleSpec (v) | See `06-rules-and-actions.md` |
| `status` | RuleStatus | draft until the user confirms the preview |
| `tier_required` | str | free, pro, max |
| `created_by` | str | user, interpreter, agent, suggestion |

- `rule_runs`: `{ id, rule_id, fired_at, trigger_ref, query_request, result_item_ids[], status, error? }`
- `deliveries`: `{ id, rule_id?, run_id?, action, item_ids[], external_ref?, delivered_at }`; used to avoid sending the same items twice.

### Action — `actions` (suggested to-dos)

`{ id, user_id, title, why, evidence[], theme_id?, goal_id?, due_at?, state: ActionState, origin: suggestion|rule|user|agent, rule_id? }`

### Placement — `placements`

Anything we put into a user's tool, so we update instead of duplicating and sync "done" back.

`{ id, subject{kind: action|item|digest, id}, integration: email|google_calendar|document, mode: create|enrich_existing, external_id, approval: pending|approved|auto, sync_state: synced|changed_by_user|deleted_by_user|error, synced_at }`

## Delivery

- **Digest** `digests`: `{ id, user_id, period{start,end}, style: briefing|one_thing|theme_cards|custom, blocks[{type, text, evidence[], action_ids[]}], validation{passed, failures[]}, delivered_via[], metrics{} }`. Block types: one_liner, do_this, done_for_you, worth_noticing, from_archive, theme_card, question, suggested_rule, custom.
- **Note** `notes`: `{ id, subject{kind, id}, text, author{kind: user|agent, client?} }`.

## Boards (Later: frontend; shapes defined now)

Vision boards are Pinterest-style collections of media across platforms. The backend serves them; layout is the frontend's job.

- **Board** `boards`: `{ id (brd_), user_id, name, description?, theme_id?, goal_id?, query?: SearchParams (optional saved search that keeps the board fresh), cover_item_id?, created_at }`
- **BoardItem** `board_items`: `{ board_id, item_id, added_by: user | suggestion | rule, added_at, note?, layout?: jsonb (v) — frontend-owned position/size }`
- **BoardSuggestion feedback** `board_feedback`: `{ board_id, item_id, verdict: added | dismissed, at }`; dismissed items are never suggested to that board again, and verdicts tune suggestions.

Boards are core data (user-created): never regenerated. A rule can add to a board (`board.add` action, later).

## System

| Table | Purpose | Key fields |
| --- | --- | --- |
| `users` | Account and settings | `timezone`, `plan`, `active_processor_version`, `digest_style`, `digest_frequency` |
| `connections` | Linked accounts and integrations | `kind`, `scopes`, `encrypted_tokens`, `status` |
| `ai_runs` | Every model call | `purpose`, `model`, `prompt_version`, `input_refs`, `output_refs`, `tokens_in`, `tokens_out`, `cost_usd`, `latency_ms` |
| `job_runs` | Every batch job | `job`, `items`, `items_per_s`, `wall_s`, `status` |
| `events` | Audit and triggers | `type`, `subject`, `created_at` |

## Example: one item, end to end

```json
{
  "raw_record": { "id": "raw_01JB…", "source": "instagram_dm", "kind": "dm_share", "format_version": 1,
                  "payload": { "link": "https://www.instagram.com/reel/ABC123/", "share_text": "…", "original_content_owner": "creator" } },
  "item": { "id": "itm_01JB…", "platform": "instagram", "dedup_key": "instagram:ABC123", "caption": "…",
            "importance": 1.0, "processing_depth": "full", "status": "processed",
            "platform_data": { "v": 1, "media_kind": "reel", "owner_handle": "creator", "hashtags": [], "collections": [] } },
  "interactions": [ { "kind": "share", "share_audience": "self", "weight": 1.0, "capture_method": "dm_share", "at": "2026-10-12T22:40:00Z" } ],
  "card": { "filter": { "class": "content", "p": { "content": 0.91, "entertainment": 0.06, "social": 0.03 } }, "info_class": "ok",
            "primary_type": "opportunity", "summary": "Student founder grant, up to $5k, closes 21 Oct.",
            "facets": [ { "type": "opportunity", "title": "Student founder grant", "deadline": "2026-10-21T23:59:00Z" } ],
            "theme_id": "thm_…", "goal_ids": ["gol_…"], "state": "saved", "processor_version": "0.9.0" }
}
```
