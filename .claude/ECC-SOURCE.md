# Where the skills and agents came from

The contents of `skills/` and `agents/` in this folder were copied from the ECC project, which is MIT licensed. The licence text is in [ECC-LICENSE](ECC-LICENSE).

- **Source:** https://github.com/affaan-m/ECC
- **Commit:** `4adeee6732a12d1540f49a4d50a38ce8c97f9a53`
- **Copied on:** 2026-11-21
- **What was copied:** 17 skills and 6 agents, unmodified. They are Markdown plus two example SQL files.
- **What was left out:** the ECC plugin itself, its hooks, commands, rules, memory system and AgentShield. Nothing from ECC runs automatically in this project.

## Skills

agent-harness-construction, api-connector-builder, blueprint, cost-aware-llm-pipeline, database-migrations, error-handling, eval-harness, fastapi-patterns, hexagonal-architecture, postgres-patterns, prompt-caching-strategy, python-patterns, python-testing, recsys-pipeline-architect, security-review, tdd-workflow, verification-loop

## Agents

database-reviewer, planner, python-reviewer, rag-pipeline-reviewer, security-reviewer, silent-failure-hunter

`redis-patterns` was copied at first and removed: this project's queues are Postgres-based (`pgmq`), per `docs/02-tech-stack.md`.

## Updating

These copies do not update themselves. To update one, read the new version in the ECC repo, copy it over the old file, and change the commit above.

To add another skill, copy `skills/<name>/` from the ECC repo into `.claude/skills/` after reading it.
