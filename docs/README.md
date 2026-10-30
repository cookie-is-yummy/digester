# Docs

The project's design, written for the people and coding agents building it. Start with `../AGENTS.md`.

| # | Doc | What it covers |
| --- | --- | --- |
| 00 | [Vision](00-vision.md) | The idea, who it is for, the core loop, MVP scope, what is out of scope |
| 01 | [Architecture](01-architecture.md) | Layers, data flow, the two processors, queues, deployment |
| 02 | [Tech stack](02-tech-stack.md) | Languages, libraries, services, repo layout, conventions |
| 03 | [Data contract](03-data-contract.md) | Every table and JSON shape, enums, storage rules |
| 04 | [Intake](04-intake.md) | Getting data in: Instagram, YouTube, enrichers, the raw-record boundary |
| 05 | [Processor](05-processor.md) | Adapters (processor 1), core pipeline (processor 2), query API, prototype parameters |
| 06 | [Rules and actions](06-rules-and-actions.md) | Natural language → rules, triggers, action registry, executor, email and calendar |
| 07 | [Privacy and safety](07-privacy-and-safety.md) | Personal data, friends, third-party text, platform terms, deletion |
| 08 | [Evals and quality](08-evals-and-quality.md) | Tests, eval sets, benchmarks, what blocks a merge |
| 09 | [Roadmap and ownership](09-roadmap-and-ownership.md) | Milestones, gates, who owns what, open questions |
| 10 | [Decisions](10-decisions.md) | Decision log with reasons |
| — | [Glossary](glossary.md) | Terms used everywhere |
| — | [Research](research/) | Experiments and their results, e.g. [search storage (30 Oct)](research/2026-10-30-search-storage.md), [when an item needs enriching (30 Oct)](research/2026-10-30-enrichment-cascade.md) |
| — | [Amendments](amendments.md) | Requested changes that don't fit these docs: the reason, why it's better, and the decision |

**Status labels used in these docs:** *Agreed* means the founders decided it. *Proposed* means it is the current best plan but has not been confirmed; build it, but keep it easy to change.

**Updating docs:** a change in behaviour or shape updates the matching doc in the same pull request. New decisions are added to `10-decisions.md` with a date and reason. A change that goes against these docs starts as an entry in `amendments.md`.
