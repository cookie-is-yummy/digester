# 02 · Tech stack

**Python for the whole backend (Agreed, 28 Oct).** The processor is machine-learning work (embeddings, clustering, classifiers, later transcription), and intake needs media and parsing tools; Python is strongest at both, and one language lets both founders share models, tests and deployment. TypeScript appears only later, for the web frontend.

## Stack

| Concern | Choice | Notes |
| --- | --- | --- |
| Language / runtime | Python 3.12 | |
| Packaging | `uv` (one project, lockfile committed) | `uv run pytest`, `uv run ruff check` |
| Web framework | FastAPI | Webhooks, upload endpoints, query API |
| Data models / validation | Pydantic v2 | The data contract in code. Also validates every LLM output |
| Settings | `pydantic-settings` | Env vars only; `.env` for local, never committed |
| Database | Supabase Postgres + `pgvector` | One database for rows and vectors |
| DB access | `psycopg` 3 (+ thin repository functions in `scrolldigest/db/`) | No ORM required; SQL lives only in `db/` |
| Migrations | SQL files in `supabase/migrations/` (Supabase CLI) | Source of truth for tables |
| Queues | Supabase Queues (`pgmq`) | Postgres-native; no extra service |
| File storage | Supabase Storage | Export zips, uploaded via signed URLs |
| Auth | Supabase Auth (Google sign-in) | Row-level security on every user table |
| Embeddings | `fastembed` with `BAAI/bge-small-en-v1.5` (384-d, ONNX, CPU) | Pinned; ~7.5 items/s on 2 CPU cores in the prototype. Multilingual model is a later experiment |
| Classic ML | `scikit-learn`, `scipy`, `numpy` | Filter (logistic regression), PCA, Ward clustering |
| LLM calls | One wrapper `scrolldigest/ai/` around the provider SDK(s) | Logs every call to `ai_runs`; prompts versioned in `ai/prompts/` |
| HTTP clients | `httpx` | Timeouts and retries on every external call |
| Scheduling | APScheduler (single scheduler process) | Only enqueues; workers do the work |
| Email | A transactional provider (e.g. Resend or Postmark) | SPF/DKIM/DMARC set up on our domain |
| Google APIs | `google-api-python-client` + OAuth | Calendar (and Tasks later), YouTube Data API |
| Lint / format / types | `ruff`, `pyright` | Strict typing in `schema/` and `db/` |
| Tests | `pytest`, `pytest-asyncio` | Fixtures are synthetic; real exports never committed |
| Logging | `structlog` (JSON logs) | Every batch logs counts, items/s, wall time |
| CI | GitHub Actions | Lint, type-check, tests, migration check, eval smoke test |
| Hosting | Container host (Railway / Fly.io / Render) + Supabase | One image, several entrypoints |

## Repository layout (Proposed)

```
scroll-digest/
├─ AGENTS.md                 read first
├─ CLAUDE.md                 points to AGENTS.md
├─ docs/                     this design
├─ pyproject.toml            uv project
├─ src/scrolldigest/
│  ├─ schema/                Pydantic models = the data contract (shared by everyone)
│  ├─ db/                    the ONLY module that talks to Postgres
│  ├─ ai/                    LLM wrapper, prompts (versioned), cost logging
│  ├─ api/                   FastAPI app: webhooks, uploads, query API routes
│  ├─ intake/                fetchers + enrichers (owner: Eason)
│  │  ├─ instagram/          export reader, DM webhook handler
│  │  ├─ youtube/            Takeout reader, playlist poller, Data API client
│  │  └─ enrich/             enricher interface + providers
│  ├─ processor/             (owner: Derrick)
│  │  ├─ adapters/           processor 1: raw → items/interactions, per platform
│  │  ├─ clean/  embed/  filter/  themes/  trends/  direction/  search/  report/
│  │  └─ query.py            query API dispatcher (JSON in, JSON out)
│  ├─ interpreter/           natural language → validated request/rule (owner: Derrick)
│  ├─ actions/               (owner: Eason)
│  │  ├─ registry.py         every output action, its params schema and side effects
│  │  ├─ triggers.py  scheduler.py  executor.py
│  │  └─ outputs/            email.py, google_calendar.py, document.py
│  └─ workers/               queue consumer entrypoints
├─ supabase/migrations/      SQL
├─ evals/                    eval sets and runners (no real personal data)
├─ tests/                    mirrors src/
└─ data/                     gitignored: real exports, local outputs
```

Suggested `CODEOWNERS`: `src/scrolldigest/intake/` and `actions/` → Eason; `processor/`, `interpreter/`, `schema/`, `supabase/migrations/` → Derrick. Changes to `schema/` or migrations need both to review.

## Conventions

- **IDs:** prefixed, sortable (ULID): `itm_`, `int_`, `raw_`, `thm_`, `rul_`, `act_`… Generate in Python, store as text.
- **Time:** timezone-aware `datetime` in UTC everywhere; convert only for display or scheduling with the user's `timezone`.
- **Enums:** Python `StrEnum` in `schema/`, stored as text in Postgres (no Postgres enum types; they are hard to change).
- **Versioned JSON columns:** every JSON blob has `"v": <int>` and a Pydantic model; old versions are upgraded on read by small functions in `schema/upgrades.py`.
- **External calls:** always with timeout, retry with backoff, and a recorded cost when billable.
- **Errors:** a failed item is marked `status=failed` with a reason and retried later; a batch never fails because one item failed.
- **Text encoding:** Instagram export JSON stores UTF-8 text mis-decoded as Latin-1. Fix with `s.encode("latin-1").decode("utf-8")` (fall back to the original on error) in the adapter, once.

## Later (not now)

- **Frontend:** Next.js on Vercel reading database views and calling the query API. TypeScript types generated from the Pydantic models' JSON Schema.
- **MCP server:** Python MCP SDK in the same codebase, calling the query API in-process.
- **Desktop app:** Electron or Tauri, with a local database behind the same `db/` interface.
