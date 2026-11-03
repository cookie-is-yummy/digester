# Understanding the query in parts (round 5)

*3 Nov 2026 · combined Instagram + YouTube library (136,908 items) · dev 44 searches · clean held-out `test2` = Derrick's 10 searches of 3 Nov, vetted by him.*

- **Brief:** `experiments/BRIEF-5.md`. **Results:** `results/r5-methods.md`, `r5-eval.md`, `r5-test2.md`.
- **Spend:** $0.09 for the round (OpenAI only). The round-4 and round-5 loop total is $3.97.

## Why we tried it

A diagnosis of failed searches showed that one query vector averages different kinds of meaning, and the topic nouns win:
- **format** ("reviews of", "compilations", "top 10");
- **tone** ("funny", "serious");
- **creator lookup** ("that one channel who…");
- **request wording** ("should … next").

So round 5 tested four fixes, one variable each against the baseline C0:
- a typed-slot rewrite (qs-v1), which splits the query into topic, format, tone, creator, request words and behaviour;
- creator search, which ranks creator profiles and lets an LLM pick from the top 50;
- facet boosts from te `kind`/`vibe`;
- a per-property yes/no checker over the top 20.

## Results

- **Nothing passed the adoption rule,** on dev or on held-out. The finalist stays C0 (dev 0.482, test2 0.448).
- **Typed slots:**
  - **Tone** helped wherever it fired (+0.01 to +0.02), but only on 3 dev searches. That is a lead, not a finding.
  - **Format** hurt wherever it fired. One stated count was read as "list format" (−0.71 on that search). The format vocabulary is too literal.
- **Creator search** worked when the search **names** the creator: +0.027 on those test2 searches, with the first right item moving up a little.
  - It failed when the search **describes** the creator. In "that cool toys creator from a long time ago … hide and seek", the target channel's 82 titles mention toys, hide or seek only 5 times.
  - Every method scores 0 on that search, and creator search pushed the target further down (from rank ~60 to ~80).
  - What the user remembers is the channel's identity and era. Its titles don't carry that.
- **Checker:** no effect on dev. It costs ~3–4 s at p95.
- **Text-pass fusion (E1/F0):**
  - On test2, E1 is +0.030 (6/3), but fragile and partly judged by the evaluator, not Derrick.
  - F0 (te for Instagram only) helps both-platform searches (+0.040) but hurts YouTube searches (−0.049). Instagram items fill 2 of each YouTube top 10, and only 4% of them are relevant.
  - Consistent with round 4: the text pass helps Instagram, and its cross-platform crowding still hurts YouTube.

## What we learned

1. **Splitting the query is right, but each slot needs its own signal and its own care.**
   - Tone is promising.
   - Format needs a smaller, curated vocabulary, matched against a `kind` taxonomy that has review, compilation, list and tutorial classes. Today te's largest `kind` is "other" (7.9k items).
2. **Describe-a-creator searches need creator-level evidence beyond titles,** for example:
   - when the user watched them (era);
   - how much the user watched them (affinity);
   - what kind of channel it is overall (a short channel description, from the user's own items or a cheap LLM summary per creator).

   A vague time phrase like "a long time ago" should become a **soft** boost toward old watches, not be dropped. In this case the target channel was watched in 2019–20.
3. **Platform crowding is still the main cost of the text pass.** The next fusion fix should cap or calibrate each platform's share by the query's likely platform.

## Remaining held-out scorings

`test2`: 2 left. `test`: 2 left (contaminated for round-5 ideas). `yt_holdout`: 1 left.
