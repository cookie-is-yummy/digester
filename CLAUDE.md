@AGENTS.md

## Local additions (21 Nov 2026, not yet reviewed by both founders)

- **The digestr spec** is a proposal, not an accepted plan: [docs/research/2026-11-21-digestr-spec.md](docs/research/2026-11-21-digestr-spec.md). Where it and the docs above disagree, the docs win until an amendment is accepted.
- **What already exists for each line of that spec**, how vectors are stored, and which parts need an amendment: [docs/research/2026-11-21-digestr-integration.md](docs/research/2026-11-21-digestr-integration.md). Read it before building anything from the spec.
- **Where the project stands:** [experiments/STATE.md](experiments/STATE.md) (newest summary first) and [docs/research/2026-11-09-current-state.md](docs/research/2026-11-09-current-state.md) for search.

## Skills and agents

These live in [.claude/skills/](.claude/skills/) and [.claude/agents/](.claude/agents/), copied from the ECC project ([.claude/ECC-SOURCE.md](.claude/ECC-SOURCE.md)). They are general advice. `AGENTS.md` and `docs/` take priority wherever a skill says something different (for example: no ORM, SQL only in `db/`, queues on `pgmq`, `uv`, `ruff`, `pyright`).

| Work | Use |
| --- | --- |
| Planning a milestone or a port from `experiments/` | `blueprint` skill, `planner` agent |
| Channel interface, adapters, the `db/` boundary | `hexagonal-architecture` |
| A new enricher, output action or connector | `api-connector-builder` |
| The interpreter's forms and the action registry | `agent-harness-construction` |
| Prompts, model choice, the `ai_runs` ledger and caps | `cost-aware-llm-pipeline`, `prompt-caching-strategy` |
| Eval sets and before/after runs (`docs/08-evals-and-quality.md`) | `eval-harness` |
| Tables, pgvector indexes, row-level security, migrations | `postgres-patterns`, `database-migrations`, `database-reviewer` agent |
| Search and retrieval changes | `rag-pipeline-reviewer` agent |
| Digest and recap selection | `recsys-pipeline-architect` |
| Job retries, failed items, external calls | `error-handling`, `silent-failure-hunter` agent |
| Personal data, tokens, deletion, third-party text | `security-review`, `security-reviewer` agent |
| Python and FastAPI code | `python-patterns`, `fastapi-patterns`, `python-testing`, `python-reviewer` agent |
| Any change | `tdd-workflow`, then `verification-loop` |
