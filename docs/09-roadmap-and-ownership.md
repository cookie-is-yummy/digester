# 09 · Roadmap and ownership

We prove the core on real data first, then build a thin version of every backend layer end to end, then thicken it. **Gates, not dates:** each milestone ends with a check on real behaviour, and we move on when it passes.

## Ownership (Agreed, 28 Oct)

| Area | Owner | Docs |
| --- | --- | --- |
| Processor 1 (adapters) and processor 2 (core), query API, first report | Derrick | `05-processor.md` |
| Interpreter (natural language → RuleSpec) | Derrick | `06-rules-and-actions.md` |
| Data contract, migrations, `schema/` | Derrick owns; both review changes | `03-data-contract.md` |
| Intake: Instagram and YouTube fetchers, DM webhook, Takeout, enrichers and benchmark | Eason | `04-intake.md` |
| Triggers, scheduler, executor, output actions (email, Google Calendar), action registry | Eason (after intake) | `06-rules-and-actions.md` |
| Frontend | Later | — |
| Marketing, positioning, recruiting testers | Eason leads; Derrick learns alongside | — |

**Working agreements:** a weekly demo on real data (15–30 minutes); contract changes go through a PR both review; Derrick reviews Eason's UX decisions in the actions layer (bot replies, preview card, email layout) against a fixed checklist, and Eason reviews Derrick's marketing attempts the same way; done means the definition in `08-evals-and-quality.md`.

## Milestones

| # | Milestone | Scope | Owner(s) | Gate |
| --- | --- | --- | --- | --- |
| M0 | Repo and contract | Repo layout, `schema/` models for the contract, first migrations, CI, fixtures | Derrick (+ Eason review) | CI green; both can run tests locally |
| M1 | History → first report (walking skeleton) | Instagram export reader → raw → adapters → clean, embed, filter, themes, trends → first report JSON | Eason (reader), Derrick (rest) | A founder's real export produces a report they recognise; upload → first report measured |
| M2 | Live capture + YouTube | DM webhook in dev mode, live share → processed item; Takeout reader; playlist poller | Eason, Derrick (adapters) | A shared reel is searchable within 30 s; YouTube history appears in themes |
| M3 | Gate 1: the processor is good enough | Search (hybrid), theme check + candidate themes + own-account questions, direction, opportunities, enrichment benchmark | Derrick, Eason (benchmark) | Each founder recognises ≥ 4 of their top 5 themes; right item in top 5 for ≥ 16 of 20 real queries; cost per item and per user per month known from real runs |
| M4 | Rules end to end | Interpreter, RuleSpec, registry, executor, scheduler, `email.send`, then `calendar.create_event`; preview + confirm; delivery dedupe | Derrick (interpreter), Eason (actions) | 3 real rules running for both founders for 2 weeks without a wrong or duplicate send |
| M5 | Friendly testers | 5–10 testers upload exports and use capture + rules; hardening: deletion, export, cost caps, error handling | Both | Week-3 retention and actions marked done measured |
| Later | Frontend hub with semantic search and vision boards (related-media suggestions across platforms), MCP server, visual embeddings, more platforms, desktop/local-first | | | |

## Long-lead items (start now; they wait on others)

- [ ] Meta app with Instagram messaging permissions; submit for review once DM capture works in development mode.
- [ ] Google OAuth verification for Calendar (and YouTube read-only), narrowest scopes.
- [ ] Domain and sending address for email, with SPF/DKIM/DMARC set up early.
- [ ] Privacy policy and terms that honestly describe what we store, for how long, and real deletion (both reviews ask for them).

## Open questions

- [ ] Product direction: the founders agree to stay with social-media input for the MVP; revisit the business-data idea after Gate 1?
- [ ] Transcript source for Instagram reels at scale, under platform terms and at an affordable cost (answered by the enrichment benchmark).
- [ ] Exact Takeout file names for YouTube likes and playlists (verify on a real Takeout).
- [ ] How long can a user wait for on-demand enrichment during a search?
- [ ] Re-importing exports periodically: Pro-only, or a fixed number for Free users?
- [ ] Final interaction weights, tuned against what users act on.
- [ ] When and how "someday" themes resurface without feeling like guilt.
- [ ] Local-first desktop app: when, and how scheduled rules run when the machine is off.
