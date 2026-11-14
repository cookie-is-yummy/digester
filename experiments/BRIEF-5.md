# Brief, round 5: understand the query in parts

Same data root (`data/all/`), roles, rules and adoption rule as `BRIEF-4.md`.

**Budget:** OpenAI about $2 (cap $9.50 in total); **no Gemini** (about $1.72 left on its cap).

## Why this round

The 4.x loop plus a diagnosis of failed searches (3 Nov) show that one query vector averages several different kinds of meaning, and the topic nouns drown out the rest:

| Part of the query | Example | How it fails today |
| --- | --- | --- |
| **Topic** | the subject | dominates the vector |
| **Format** | review, tutorial, compilation, clips, list ("top 10") | weak; "reviews of X" lands next to "X tips" |
| **Tone** | funny, cute, serious, motivational | averaged away. On YouTube there is almost no signal: of 763 speedrun videos, 49 have te and 1 is tagged funny. |
| **Creator lookup** | "that one channel / guy / creator who…" | the answer is a *creator*. Their posts often don't describe what the user remembers about them. |
| **Request words** | "videos on", "should … next" | noise, but BM25 matches them |
| **Behaviour / time** | saved, liked, "a long time ago", "last summer" | needs interaction data |

Also observed:
- the rewrite sometimes keeps the topic word but misses the user's vocabulary (a "CV" can be a portfolio or personal site);
- te's `kind` has no review, reaction, compilation or list category ("other" holds 7.9k items).

## Hypotheses (one variable each, against C0; preregister in LOG.md)

- **F0 · te lists for Instagram + untitled YouTube only,** under coverage-fair fusion (round 4's per-platform finding as a rule).
- **F1 · typed-slot rewrite (qs-v1).** The rewrite returns `topic`, `format`, `tone`, `creator_lookup` (bool + description), `request_words` and `behaviour_time`.
  - Lexical lists use only topic and format terms plus per-slot vocabulary expansions. The raw query and request words leave BM25.
  - Dense uses topic + format phrases.
- **F2 · creator search.**
  - Build a profile per creator: the mean of their items' own and te vectors, plus a short text profile (BM25 over creator name, handle and their items' te topics/kind/vibe).
  - When F1 says `creator_lookup`, rank creators, then their items. Optionally an LLM picks the best 1–3 of the top-50 creators from the creator text profiles.
  - Fuse with coverage-fair RRF.
- **F3 · facet matching.**
  - The F1 `format` and `tone` slots act as boosts on te `kind`/`vibe` (with a mapping table) and on title cues for items without te (for example compilation/fails/😂/"top N"/review/tutorial).
  - Use soft boosts, not hard filters.
- **F4 · per-property checker.** A cheap LLM answers yes/no per top-20 item for each format and tone slot, from the item's allowed text and te. Rerank by the answers. Log the cost.
- **F5 · the stack** the experimenter's design reasoning favours, fixed in LOG.md before any run.

## Held-out

- **`test` (13 searches):** the round-4 searches are now **contaminated** for this round's ideas, because the diagnosis was done on their failures. Score them only as a secondary check.
- **`test2` (10 new searches from Derrick, 3 Nov):** the clean held-out set. Its labels are vetted by Derrick before scoring. The orchestrator adds them; builders never see them.
- **`yt_holdout`:** 1 scoring left.
