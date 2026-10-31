# Brief, round 4: one library, two platforms, as a loop

This round searches Instagram and YouTube together, as the product would. Unlike rounds 1–3 it runs as an **autonomous loop of small rounds** until a stop rule fires.

**All of `BRIEF.md`'s rules apply:**
- who evaluates never builds;
- preregistration in `LOG.md` before any run;
- the adoption rule (Δ ≥ 0.03 with CI > 0, or Δ ≥ 0.02 with more wins than losses at no extra cost);
- every paid call through `lib/ai.py`;
- nothing personal in git.

`RUN-3.md`'s YouTube terms decision still holds: the API text is a never-ship reference only, and there is no thumbnail tier.

## Data: `data/all/` (gitignored)

Set `DIGESTER_DATA=$PWD/data/all`. Built by `experiments/combined/build_root.py`.

- **`corpus/items.jsonl`:** 136,908 items in the same shape as before; `platform` is `instagram` or `youtube`.
  - Instagram: 21,293 items, caption = post caption.
  - YouTube: 115,615 items, caption = Takeout title, channel in `owner_name`, playlists in `collections`.
- **`corpus/emb/oai512`:** OpenAI text-embedding-3-small at 512d for 121,169 items. Both platforms used the same model.
  - Instagram: the round-1 caption view.
  - YouTube: Takeout title + channel + playlists.
  - Items without text have no vector.
- **`evals/queries.jsonl`:** 55 searches. Instagram ids start `ig_`, YouTube ids start `yt_`. **Methods are not told which platform a search targets.**
- **`evals/labels/evalset.jsonl`:** EVALUATOR ONLY. Each search has a `scope` (ig | yt).
  - Instagram labels are the round-0 seeds. The grown labels from rounds 1–2 were lost with the cloud session, so expect heavy pooling early.
  - YouTube labels are round 3's pooled labels.
  - The judging rule for scoped searches is under "Labels across platforms" below.
- **`evals/split.json`:**
  - `dev` (44): all 22 Instagram searches (their test split is used up) plus YouTube dev.
  - `yt_holdout` (11): YouTube test, **2 scorings left**.
  - `test`: **Derrick's fresh searches**, written before any round-4 result. Scored at most 3 times, by an evaluator only.
- **Reusable outputs, free:**
  - `yt_enrich/`: YouTube te-v1c text pass over Takeout text, plus the reference API pass;
  - `yt_video/`: Gemini video pass, 1,168 videos, gated + random arms;
  - `yt_ref/`: research-only API text.
  - Instagram's te-v1c pass must be redone (~$3.7 Gemini Batch, `methods/enrich_batch.py`).
- **Budget:** $15 for the whole loop. Caps in `lib/ai.py`: Gemini $10, OpenAI $5. The ledger is `data/all/ai_runs.jsonl`.

## Labels across platforms

A search written for one platform may have right answers on the other: for example, a Blender search on Instagram finds Blender tutorials on YouTube.

- Pool and judge cross-platform items in the top 10 like any other unjudged item.
- Grade them against the search's meaning, not against its platform.
- Report every metric overall and per `scope`.

## The loop

The orchestrator (main session) runs rounds 4.1, 4.2, … Each round:

1. **Experimenter:** a fresh agent, never shown labels.
   - Reads `STATE.md`, the last round's evaluator report and the agenda below.
   - Picks 1–3 hypotheses, each changing one variable.
   - Preregisters them in `LOG.md`, then builds them and writes run files for **dev and yt_holdout** to `data/all/runs/r4.N/`. It does not score them.
   - Reports spend and what was run.
2. **Evaluator:** a fresh agent, which did not build anything.
   - Scores dev, pools and blind-judges new top-10 items, and applies the adoption rule against the current finalist.
   - Writes `results/r4.N-eval.md`, updates the finalist line in `STATE.md` and fills `LOG.md`'s result column.
   - It may not score `test` or `yt_holdout`, except as described under "Finish".
3. **Orchestrator:**
   - checks spend against the stop rule;
   - checks that nothing personal is staged;
   - commits and pushes;
   - starts the next round with the evaluator's report as input.

**Stop rule:** total spend reaches $15 (stop paid work at $14.25), **or** three consecutive rounds adopt nothing.

**Finish:** a fresh evaluator scores the finalist, the round-4.1 combined baseline and the best rival once on `test`, and once on `yt_holdout`. It writes `docs/research/<date>-combined-loop.md` and updates the amendments the results touch (A-003, A-004).

## Agenda (the experimenter picks in order of expected value per dollar)

1. **Combined baseline, round 4.1 (must come first).** Run B3 without enrichment (A0 recipe: real rewrite, dense, BM25, PRF, RRF, HyDE) over the combined index, platform-blind. Measure interference: score each scope against the same method run on its own platform alone.
2. **Rebuild Instagram's te-v1c pass, then route enrichment by information sufficiency.** Round 1: the text pass helps thin Instagram captions (+0.059). Round 3: it hurts descriptive YouTube titles (−0.046). Test letting an item's enrichment lists vote only when its own text is insufficient: short or empty caption, untitled, or low info class. This is the original cascade idea, tested across platforms.
3. **Intent step v3.** Start from qi-v2 filters only.
   - Drop guessed date windows for vague life-era phrases.
   - Remove eval-specific phrases from the prompt examples.
   - Add `platform` as an inferred filter, used only when the user says it.
   - Behaviour filters work on both platforms' interactions: saved, liked, shared, rewatched.
4. **Cross-platform score balance.** YouTube has 5× the items, and titles and captions differ in length. Try per-platform BM25 normalisation, or platform-interleaved fusion, if 4.1 shows interference.
5. **Video-pass reach.** Use the existing YouTube video outputs as a list only for untitled items, as in the cascade.
6. **Two-stage search on the combined index:** the instant path (no rewrite) vs refined, with quality and p95 latency.

Do **not** spend on an Instagram image or video tier. There is no permitted media route for saved posts yet (A-002).
