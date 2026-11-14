# Brief, round 7: cheap classifiers plus the combined package

The data root (`data/all/`), roles, rules and adoption rule are the same as in `BRIEF-4.md`.

**Budget for the round:** OpenAI about $2. The total cap is $9.50, and about $6.9 is left. **No Gemini** (about $1.72 left on its cap).

## Why this round

Rounds 4–6 stopped producing gains from swapping parts of the LLM pipeline. The remaining failures are **missing signals**: tone and format for most YouTube items, what kind of channel a creator runs and when the user watched them, and which app a search is about. Classifiers can create those signals cheaply and deterministically. Round 6 also showed that:
- the rewrite already extracts date and behaviour filters that C0 ignores;
- text-embedding-3-large (G4) is a cheap gain: dev +0.022, test2 +0.053, not yet adopted.

## Arms (preregister Y7-* rows in LOG.md before running; one variable each against H0, then the package)

| Arm | What changes |
| --- | --- |
| **H0** | G4: C0 with 3-large 1,024-d vectors (the new base for this round). Compare it against C0 too. |
| **H1** | H0 + the rewrite's own date and behaviour filters, with E1's guards. Filters may only widen. A vague time phrase becomes a **soft** boost toward older or newer interactions, never a hard window. |
| **H2** | H0 + **facet classifiers** for `kind` (format) and `vibe` (tone). See the training rules below. They are soft boosts where the query asks for a format or tone. |
| **H3** | H0 + **query router**: a classifier over the query vector that predicts the search type (topic, creator recall, behaviour/time, format, vibe) and the likely platform (ig / yt / both). It drives platform-share calibration in fusion, and turns creator search on only for creator-recall searches. |
| **H4** | H0 + **creator profiles** that include the user's era (first and last watch or save), affinity (how many interactions), and channel type (the majority facet from H2's classifier). Used on creator-recall searches. |
| **H5** | The package: H0 + H1 + H2 + H3 + H4. A variant **H5b** adds round 5's te lists for Instagram items under coverage-fair fusion. Fix both in LOG.md before any run. |
| **H6** (optional, only if it installs cleanly) | H5 + an off-the-shelf cross-encoder reranker over the top 50 (e.g. a MiniLM ms-marco model, CPU). **No fine-tuning on eval labels.** |

## Training rules (no leakage)

- **Facet classifiers** train only on **te-v1c outputs** (the AI summaries): about 20.8k Instagram rows and 6.5k YouTube rows.
  - Optionally add a few thousand **new LLM labels** for a random sample of titled YouTube items, using gpt-5-nano with a fixed prompt, logged.
  - Hold out 20% of the labels to report each classifier's accuracy and calibration.
  - Never train or tune on eval labels or eval queries.
- **Query router** trains on **synthetic searches** an LLM writes from a fixed prompt (about 2–3k, covering every type and platform), never on eval queries. Report its held-out accuracy on the synthetic set.
- **Off-the-shelf models only for the reranker.** Our graded pairs are evaluation answers.

## Held-out

- **`test2`** has **1 scoring left**. It is spent once, at the end of this round, on the package (the better of H5 and H5b on dev), with C0 and H0 as references.
- **`yt_holdout`** has 1 scoring left, for the same package.
