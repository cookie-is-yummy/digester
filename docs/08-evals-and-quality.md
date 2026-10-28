# 08 · Evals and quality

AI and ML output can't be checked by unit tests alone. Every learned or generated step has a fixed eval set built from real use, and a change ships only if it scores at least as well.

## Test layers

| Layer | What | When |
| --- | --- | --- |
| Unit tests | Parsers, adapters, schema validation, trend maths, rule validation, executor idempotency | Every PR |
| Fixture tests | Synthetic export zip, Takeout folder and webhook bodies run end to end into items | Every PR |
| Eval smoke test | Small eval subset on a synthetic user | Every PR touching `processor/`, `interpreter/` or prompts |
| Full evals | All eval sets on consenting founders'/testers' data, locally | Before changing `processor_version`, model or prompt version |

## Eval sets

Stored in `evals/` as JSONL. Sets built from real people's data stay outside git (in `data/evals/`); only the schema and runners are committed.

| Set | Contents | Metric | Bar |
| --- | --- | --- | --- |
| **Filter labels** | ~200+ items labelled U/I/E/S/X per user | Accuracy; content recall | ≥ 0.84 accuracy; content recall ≥ 0.90 |
| **Search set** | 15–20 real queries per person with the right item(s), e.g. "tomato recipes I saved", "the guy making chai" | Right item in top 5 | ≥ 16 of 20 (Gate 1) |
| **Theme check answers** | The user's labels on themes and candidate themes | % themes the user recognises; mixed-theme count | ≥ 4 of top 5 recognised (Gate 1) |
| **Collections match** | Users' own Instagram collections as ground truth | Balanced accuracy of theme ↔ collection | Report; no regression |
| **Stability** | Build themes on older data, add newer data | Themes keeping ID and name | 100% of pinned; ≥ 90% overall |
| **Enrichment benchmark** | ~100 reels + ~30 videos | Coverage, cost per 1,000, latency, downstream search gain | Cheapest method meeting the need |
| **Interpreter set** | 50+ natural-language requests with expected RuleSpecs (incl. unsupported ones) | Exact-valid rate, action accuracy, correct refusals | ≥ 90% valid; 100% no unregistered actions |
| **Report / digest rubric** | Generated reports/digests scored: specific, cited, actionable, honest, short | Must-pass on first four | All pass |

## Benchmarks

`job_runs` records items, items/s and wall time for every batch. Track against `05-processor.md` › Performance targets: upload → first report, full export, live share latency, search p95.

## Cost

Every AI call logs cost to `ai_runs`; billable enrichment logs cost per item. A weekly script reports cost per active user per month by tier. A prompt or tier change that raises cost must say so in the PR.

## Definition of done

Works on real data, has tests (and an eval run if it touches learned or generated output), logs its timing and cost, updates the relevant doc, and has been shown in the weekly demo.
