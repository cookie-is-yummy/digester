# MU ceiling (dev, 30 Oct 2026)

> **INFLATED CEILING. NEVER ADOPT ANY OF THIS AS A METHOD.**
> The eval answers were found by Muse matching words in this same MU text. About 95% of the labelled answers have MU text, but only about 5% of the corpus does (1,105 of 21,293 items). So MU leaks the labels in two ways: through its words and through its **presence**. These numbers bound what a perfect description pass could add. They do not estimate what one would add. MU must never feed a method or the query rewrite.

- **Who ran it:** the evaluator.
- **Script:** `experiments/eval/muse_ceiling.py`. Data: `data/runs/ceiling_*.json` (gitignored).
- **Labels:** dev split, 16 searches, evalset before the pooled round r1.
- **Raw numbers:** `muse-ceiling.json`.
- **Base check:** the script's `base` variant reproduces `data/runs/baseline.json` exactly on all 16 dev searches. The method is hybrid_prf with bge_full.

## Variants

| | What changes |
| --- | --- |
| (a) | Baseline, for reference. |
| (b) | MU appended to the BM25 `full` text. Dense is unchanged. The 9 MU items with no caption vector get rows, so BM25 can rank them. |
| (c) | As (b), and each MU item is re-embedded with bge-small: the `full` view plus the first 1,500 characters of the MU description. The model cuts at 512 tokens. All MU items are treated as info-ok. |
| (b′), (c′) | As (b) and (c), but only the free-text description is appended. The full MU record also has Searches, Media Pivots, Author & Community and Cultural/Humor/Temporal sections. |
| (d), (d′) | MU as **separate fields**: BM25 over the MU text alone plus dense over the MU vectors from (c), fused 4-way by RRF with the unchanged baseline rankings. |
| (p) | Diagnostic, using no MU text: the baseline ranking with every MU item moved ahead of the rest, order otherwise kept. It measures leakage through presence alone. |

The re-embedding took 466.9 s on 4 CPUs at 2.4 items/s. Long texts make bge-small slow. Vectors are cached in `data/eval_work/emb_mu/`.

## Overall (dev, 16 searches)

"Condensed" is nDCG@10 over judged items only, with unjudged items dropped from the ranking. Variants push new, unjudged items into the top 10, so plain nDCG@10 understates them a little.

| Variant | nDCG@10 | Δ vs baseline [95% CI], W/L/T | P@10 | MRR | R@100 | unjudged10 | Condensed nDCG@10 | MU share of top 10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| (a) baseline | 0.508 | — | 0.581 | 0.856 | 0.434 | 0.194 | 0.599 | 0.56 |
| (b) MU → BM25 | 0.521 | +0.013 [−0.031, +0.047] 10/3/3 | 0.550 | 0.857 | 0.557 | 0.250 | 0.624 | 0.54 |
| (c) MU → BM25 + dense | 0.551 | +0.042 [−0.071, +0.152] 10/5/1 | 0.544 | 0.884 | 0.615 | 0.244 | 0.657 | 0.52 |
| (b′) description → BM25 | 0.500 | −0.009 [−0.045, +0.032] 3/8/5 | 0.556 | 0.828 | 0.540 | 0.237 | 0.591 | 0.53 |
| (c′) description → BM25 + dense | 0.522 | +0.013 [−0.111, +0.121] 7/8/1 | 0.544 | 0.853 | 0.580 | 0.237 | 0.596 | 0.51 |
| (d) MU as separate fields | 0.711 | +0.203 [+0.106, +0.302] 13/3/0 | 0.706 | 0.927 | 0.769 | 0.225 | 0.797 | 0.99 |
| (d′) description as separate fields | 0.685 | +0.176 [+0.078, +0.277] 12/4/0 | 0.681 | 0.919 | 0.742 | 0.250 | 0.782 | 0.99 |
| (p) presence oracle, no text | 0.664 | +0.156 [+0.074, +0.241] 11/1/4 | 0.663 | 0.909 | 0.637 | 0.263 | 0.786 | 1.00 |

What the text adds beyond presence, as paired Δ nDCG@10 against (p):

| Variant | Δ vs (p) [95% CI] | W/L/T |
| --- | --- | --- |
| (d) | +0.047 [+0.001, +0.100] | 9/6/1 |
| (d′) | +0.021 [−0.022, +0.065] | 8/7/1 |
| (c) | −0.114 [−0.25, +0.025] | 5/10/1 |
| (b) | −0.143 [−0.23, −0.058] | 2/11/3 |

## By search kind

Kinds marked n=1 are a single search, so read them as anecdotes.

nDCG@10:

| Variant | audio (n=1) | more_like_this (n=3) | name (n=3) | people (n=1) | place (n=1) | said_shown (n=1) | topic (n=5) | vibe (n=1) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| (a) baseline | 0.00 | 0.43 | 0.56 | 0.31 | 0.84 | 0.77 | 0.48 | 0.86 |
| (b) MU → BM25 | 0.00 | 0.47 | 0.59 | 0.34 | 0.60 | 0.77 | 0.52 | 0.84 |
| (c) MU → BM25 + dense | 0.00 | 0.62 | 0.63 | 0.15 | 0.58 | 1.00 | 0.59 | 0.39 |
| (b′) | 0.00 | 0.48 | 0.61 | 0.27 | 0.68 | 0.77 | 0.45 | 0.79 |
| (c′) | 0.00 | 0.59 | 0.66 | 0.18 | 0.55 | 1.00 | 0.53 | 0.24 |
| (d) fields | 0.31 | 0.74 | 0.78 | 0.85 | 0.89 | 0.64 | 0.66 | 0.84 |
| (d′) fields, description only | 0.24 | 0.70 | 0.79 | 0.84 | 0.86 | 0.64 | 0.62 | 0.84 |
| (p) presence | 0.00 | 0.70 | 0.74 | 0.74 | 0.91 | 0.77 | 0.60 | 0.91 |

R@100:

| Variant | audio | more_like_this | name | people | place | said_shown | topic | vibe |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| (a) baseline | 0.00 | 0.37 | 0.59 | 0.33 | 0.29 | 0.67 | 0.49 | 0.35 |
| (b) | 0.50 | 0.40 | 0.72 | 0.33 | 0.32 | 0.67 | 0.67 | 0.39 |
| (c) | 0.50 | 0.45 | 0.77 | 0.39 | 0.30 | 1.00 | 0.73 | 0.34 |
| (d) | 0.50 | 0.63 | 0.83 | 0.80 | 0.52 | 1.00 | 0.86 | 0.84 |
| (p) | 0.50 | 0.57 | 0.82 | 0.49 | 0.54 | 1.00 | 0.59 | 0.55 |

Share of each kind's labelled answers that have MU text: audio 1.00, more_like_this 1.00, name 0.98, people 0.82, place 0.98, said_shown 1.00, topic 0.85, vibe 0.95.

## Interpretation

1. **Most of the apparent ceiling is label leakage through MU presence.** Moving MU items to the front, with no text at all, gives +0.156 nDCG@10. The best text variant (d) beats that by only +0.047 (CI just above 0). Any future method that tends to surface "the kind of items Muse described" will look good on this eval set for the same reason. Treat the eval set as biased toward Muse's 1,105 items: judged pools, which are not MU-derived, are the fix.
2. **Appending long MU text to the caption barely helps and can hurt.**
   - (b) and (c) gain +0.01 to +0.04 nDCG@10, with CIs spanning 0.
   - R@100 rises clearly: 0.43 → 0.56 for (b) and 0.62 for (c).
   - MU records are about 4,400 characters, against short captions. BM25 length normalisation and a 512-token dense window dilute the match.
   - Re-embedding caption + description hurt **vibe** (0.86 → 0.39) and **people** (0.31 → 0.15), and helped more_like_this, name, topic and said_shown.
   - **Design implication for a real description pass:** index enrichment as its **own field and its own vector**, fused by RRF, not concatenated into the caption text. Keep it short; a summary plus facets beats a long description.
3. **Headroom by kind:**
   - These are (d) minus (p), so the presence share is removed, plus R@100 gains. With n=1 kinds this is indicative only.
   - **Audio** is the only kind where text matters beyond presence. Baseline and presence both score 0 nDCG@10, (d) scores 0.31, and every MU variant lifts R@100 from 0 to 0.5. Audio needs song/track information, which is in the export's `Music:` header line on 36% of items. The caption has no such information.
   - **people** (R@100 0.33 → 0.80) and **vibe** (R@100 0.35 → 0.84) gain most in recall from separate MU fields; topic gains too (0.49 → 0.86). These need what is shown, which only a description provides.
   - **name** and **more_like_this** gain in nDCG mostly through presence.
   - **said_shown** is already near its ceiling.
   - **place** gains only in recall, mostly through presence.
   - Full MU (with Searches, Community and Cultural sections) beats description-only by about 0.03 nDCG@10 and 0.03 R@100. The extra sections are partly comment-derived ("Community Discussion", "Main Discussion Themes & Quotes"), and we cannot reproduce those, because the export has no comments.
4. **Order for phases 3–5 suggested by this ceiling:** (i) index enrichment as separate fields with RRF, which costs nothing and is a design choice; (ii) audio/music identity (song title and artist) for the audio kind; (iii) a "what is shown" description for people, vibe and topic recall. The ceiling cannot say how much of this a real enrichment pass recovers. Only a method run plus pooled judging can.
