# Glossary

| Term | Meaning |
| --- | --- |
| **Intake** | Getting data in from platforms and providers, exactly as received, into `raw_records`. Not to be confused with *search*, which finds things for the user. |
| **Raw record** | One payload exactly as received (an export entry, a webhook body, a DM share object, an API response). Append-only. |
| **Processor 1 / adapters** | Platform-specific code that turns raw records into Items and Interactions. |
| **Processor 2 / core** | Everything after the adapters: clean, understand, filter, index, organize, personalize, and the query API. Platform-agnostic. |
| **Item** | One piece of content (a reel, post, video), stored once per user. |
| **Interaction** | Something the user did with an item: share, save, collection, like, comment, watch, view. |
| **Self-share** | Sending content to yourself (another of your own accounts, or our product account). Save-strength signal (1.0). |
| **Friend share** | Sending content to someone else. Interest plus a social reason (0.6). |
| **Own account** | An account that belongs to the user, used to detect self-shares. Suggested by the processor, confirmed by the user. |
| **Enrichment / tier** | Extra understanding of an item. Tier 0 metadata, 1 embedding and filter, 2 transcript, 3 visual/on-screen text and entity extraction. Higher tiers only when worth it. |
| **Information gate** | Check that a caption has enough real text to place (`ok`), else `low` (too thin) or `non_english`. |
| **Filter** | Classifier: content vs entertainment vs social (friends). |
| **Item card** | The processor's structured view of an item: filter result, type, facets, summary, theme, goals. |
| **Facet** | Structured fields for a type: recipe ingredients, place name and city, opportunity deadline… |
| **Theme / sub-theme** | Stable groups of related content (two levels). IDs never change once created. |
| **Theme space** | The frozen transform (mean, PCA) used to place new items into existing themes. |
| **Candidate theme** | A cluster of leftover items not fitting existing themes, waiting for the user to confirm. |
| **Relation** | What a theme means to the user: pursue, practise, someday, enjoy, mute. |
| **Pinned** | A theme the user named, labelled, or a rule depends on; never changed automatically. |
| **Trend** | rising, steady, fading, dormant: recent 6 months vs 6–18 months ago. |
| **Direction** | The user's goals and theme relations, compared with where attention actually goes. |
| **Theme check** | The onboarding/verification screen where users label themes. |
| **Verification question** | A one-tap question chosen for how much it teaches us. |
| **First report** | The output right after upload: summary, useful-share reality check, highlights, themes, opportunities, questions. |
| **Query API** | The processor's JSON-in / JSON-out interface. Read-only. |
| **Interpreter** | LLM step that turns a natural-language request into a validated RuleSpec. |
| **Rule / RuleSpec** | when (trigger) + content (query) + do (actions). |
| **Action registry** | The list of output actions that exist, with parameters and side effects. Nothing else can run. |
| **Executor** | Runs rules: queries the processor, dedupes, renders, calls actions, records deliveries and placements. |
| **Delivery** | A record of what a rule sent, used to avoid repeats. |
| **Placement** | Something we created in a user's tool (email, calendar event), tracked for sync and undo. |
| **Digest** | Periodic summary: what rules did, suggested actions, suggested rules. |
| **Hub** | The future web app. Not being built yet. |
| **Board / vision board** | A Pinterest-style collection of media from any platform, curated by hand with related-item suggestions. Later (frontend). |
| **Similar / related items** | Items closest in meaning (embedding space) to a set of items, across all platforms and interaction kinds. |
| **MCP** | Model Context Protocol: how the user's own AI agent connects to their data. Paid core; built after the query API. |
