# Stronger models and cheap classifiers (rounds 6–7)

*7 Nov 2026 · combined Instagram + YouTube library (136,908 items). Scored on dev (44 searches), plus the last scorings of both held-out sets: `test2`, Derrick's 10 searches, and `yt_holdout`, 11 YouTube searches.*

**Results:** `experiments/results/r6-*`, `r7-eval.md`, `r7-final.md`. **Spend:** rounds 6–7 cost about $2.7 (OpenAI only); the round-4–7 total is about $6.7.

## Bottom line

1. **Adopt text-embedding-3-large (1,024 d) as the processor's vectors (H0).**
   - Over C0 it gains +0.022 on dev and +0.055 [+0.013, +0.103] over all 21 held-out searches (15 wins, 4 losses), with yt_holdout alone at +0.056 [+0.003, +0.119].
   - It costs $0.52 once to re-embed the library and adds about 0.1 s per search.
2. **Stronger rewrite models don't help.** gpt-5.4-mini and gpt-5.5 make the rewrite about a third more consistent between repeats, but no better (dev −0.012 and +0.005). gpt-5.5 costs about $11 per 1,000 searches.
3. **The classifier package (H5) beats C0 on held-out (+0.076, 15/4)**, but its gain over H0 is not established (+0.021, CI touching 0).
   - **The package is:** 3-large, plus guarded filters, format and tone classifiers, a query router with app balancing, and creator era profiles.
   - **Where each part fired:**
     - filters helped when a search used real time or behaviour words;
     - app balancing helped when the router guessed the right app and hurt when it guessed wrong;
     - the soft "new" time boost hurt;
     - format tags did nothing.
   - **Keep it as a candidate,** not adopted.
4. **Instagram te lists (H5b):**
   - **Helped:** both-app searches (+0.03) and Instagram searches on dev (+0.087).
   - **Hurt:** YouTube searches (−0.02).
   - Not adopted until the crowding is fixed.

## Classifier quality (held-out training-side data)

| Classifier | Trained on | Quality |
| --- | --- | --- |
| Format (`kind`) | te-v1c labels, about 27k items | accuracy 0.73, macro-F1 0.71 (majority-class baseline 0.33) |
| Tone (`vibe`) | same | macro-F1 0.57; AUC 0.91–0.97 |
| Query type | 2,699 LLM-written searches | accuracy 0.68 |
| Query platform | same | accuracy 0.55, **too weak**; its misreads cost YouTube searches 0.06–0.08 |

## Problems to fix before anything ships

- **Creator search is non-deterministic.** Its ranking depends on Python's string hashing. Without those cells, the package's gain over H0 halves to about +0.010.
- **The router's platform head needs better training data,** or should use the user's own history (which app they search more).
- **Drop the soft time boost** for dates the rewrite invented when the search had no time words.

## Held-out sets

`test` (contaminated for round-5+ ideas), `test2` and `yt_holdout` are all used up or biased. To settle the package, we need **about 40–45 fresh searches from Derrick**:
- roughly a third each Instagram, YouTube and both apps;
- including creator-recall and time or behaviour searches.

Creator search must be made deterministic first.
