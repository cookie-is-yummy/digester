# 07 · Privacy and safety

Trust is the positioning: the user's data is theirs. These rules are requirements, not preferences.

## Personal data

- **Minimum necessary.** Intake extracts only the export files and fields listed in `04-intake.md`.
- **DM messages:** only shared-post objects (link, share text, original owner, sender, time) and per-thread counts are kept. Message text is never stored, logged or sent to an LLM. Thread identifiers are salted hashes.
- **Friends:** posts by mutual follows and shares received from friends are counts only in every report, digest, log and eval. Their captions are never shown or sent to an LLM. The recipient of a friend share is not stored on the interaction.
- **Sensitive categories** (health, relationships, money) are tagged on item cards and hidden from agents and digests unless the user opts in.
- **No real exports in the repo.** Real data lives in `data/` (gitignored) or in the database. Fixtures are synthetic or sanitized by hand (no real handles, names or captions from private accounts).
- **Logs** carry IDs and counts, never captions, message content or tokens.

## Retention and deletion

- **Real deletion:** deleting an item or an account removes it from our database and from everything we created in their tools (on request), not just from views.
- **Transcripts and audio/video are never stored.** Summaries, moments and facets are kept; full transcripts are fetched on demand.
- **API data with retention limits** (e.g. YouTube) carries `refresh_by`; a job refreshes or deletes it.
- **Shared enrichment cache** holds public content only, keyed by content, with no user IDs; it must never reveal who saved what.
- **Full export** of a user's data in open formats (JSON, CSV, Markdown).

## Third-party text and LLMs

- Captions, transcripts and comments may contain instructions ("ignore previous instructions…"). They are passed to LLMs only inside clearly delimited data fields, with a system instruction to treat them as data.
- LLM outputs are always validated against Pydantic models before use. An LLM never triggers a side effect directly.
- Model providers are used under terms that exclude training on our data.
- Every LLM call is logged (`ai_runs`) with purpose, model, prompt version and cost; no raw personal content in the log beyond IDs.

## Platform terms

- Intake preference order: user-provided data → official APIs → paid providers with clear terms. No logged-in bot accounts, no evading blocks or rate limits, no media downloads where forbidden.
- Before shipping a source, record in its section of `04-intake.md`: what the terms allow us to store, for how long, and for what.
- Open checks: YouTube's derived-data clause before building YouTube summaries; transcript routes for Instagram and YouTube audio; Reddit and X commercial terms before adding them.

## Security

- Supabase row-level security on every user table; service role key only in workers.
- OAuth tokens encrypted at rest; least-privilege scopes (e.g. read-only YouTube, calendar events only); revocable from settings.
- Webhook signatures verified (Meta); upload URLs are short-lived signed URLs.
- Secrets only in environment variables; never in code, logs or fixtures.

## Honesty in outputs

- Inferred statements are labelled as inferred, with evidence; no personality labels or psychological claims.
- Don't overclaim: the Instagram export has engagement, not minutes. "Time spent" requires on-device data (later native app) and must not be estimated as if measured.
- Entertainment is never shamed in outputs; watching is not wanting.
