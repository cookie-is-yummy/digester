# Experiment 9: tier-1 enrichment vs Muse MU, reference comparison

*30 Oct 2026 · Evaluator (reference role) · aggregate rates only. This file holds no MU text, captions, item codes or examples. Numbers: `e9-reference-vs-mu.json`. Helper: `experiments/eval/reference_compare.py` (evaluator side).*

**Read this first.** The two sources had different inputs:
- **MU** was made from the video, the audio and the comments.
- **Ours** (`te-v1c`, gemini-3.1-flash-lite) had text only: caption, hashtags, creator, media kind and collection names.

So a large gap on shown, said and audio is expected. The aim here is to size that gap, not to judge the prompt for having it. MU is itself model output, so it is a reference, not ground truth.

## Population and method

- **Items:** 5,006 items are enriched (ok). 578 of them are in the Muse export, and 500 of those have real MU text (78 say "no MU text"). That gives an **intersection of 500**.
- **Sample:** 200 items, seed 5, drawn from the intersection. By our information gate, 190 are ok and 10 are low (thin).
- **Reading:** I read 112 of the 200 by hand: the first 106 in sample order, plus the other 6 thin items.
  - I also read every thin item in the intersection that was outside the sample (14 more), so the thin split covers **all 24 thin items** in the intersection.
  - What I read of MU: the free-text description, or the Social Context / Overall Synthesis section when the description is empty, up to 1,800 characters, plus whether a `Music:` header is present.
  - Left out: Searches, Media Pivots and the comment-derived Author & Community section.
- **Regex first pass:** run over all 200 items as a cross-check (tables below).

**When ours "covers" a facet:**
- In general, the field is non-empty and the facet is not listed in `unknown`.
- **kind:** not `other` or `unknown`.
- **audio** (there is no audio field): `audio` is not in `unknown`, and some field names music or a sound.

**When MU "covers" a facet:**

| Facet | Counts as covered | Does not count |
| --- | --- | --- |
| kind, topic | Always stated | — |
| shown | Visual content | — |
| said | Speech or on-screen text, with its content described | Only "no dialogue" |
| audio | Music, a song or a sound effect, or a `Music:` header | Speech alone |
| place | Any setting, generic or named, including a rendered scene | — |
| people | Any person shown or named | Hands or body parts alone, characters, objects |
| vibe | A stated tone or mood | — |

**Definitions:**
- **Conflict:** both sources cover the facet and ours contradicts MU. Examples: a wrong kind, a wrong main topic, a vibe that contradicts MU's.
- **Unsupported:** ours asserts a shown, said or audio fact that MU contradicts. This includes caption lines placed in `said` when MU says no one speaks and there is no on-screen text.

## Per facet (read sample, n = 112)

| Facet | Ours covers | MU covers | **Miss** (MU has it, ours doesn't) | Miss 95% CI | Miss \| MU covers | Conflict (of all items) | Conflict \| both cover | Unsupported (of all) | Unsupported \| ours covers |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| kind | 0.75 | 1.00 | **0.25** | 0.18–0.34 | 0.25 | 0.062 | 0.083 | — | — |
| topic / entities | 0.96 | 1.00 | **0.04** | 0.02–0.10 | 0.04 | 0.018 | 0.019 | — | — |
| shown | 0.66 | 1.00 | **0.34** | 0.26–0.43 | 0.34 | 0 | 0 | 0.027 | 0.041 |
| said (speech / on-screen text) | 0.51 | 0.79 | **0.39** | 0.31–0.49 | 0.50 | 0 | 0 | 0.036 | 0.070 |
| audio (music / song / sound) | 0.03 | 0.71 | **0.68** | 0.59–0.76 | 0.96 | 0 | 0 | 0 | 0 |
| place | 0.28 | 0.60 | **0.36** | 0.27–0.45 | 0.60 | 0 | 0 | — | — |
| people | 0.80 | 0.76 | **0.13** | 0.08–0.20 | 0.17 | 0 | 0 | — | — |
| vibe | 0.50 | 0.82 | **0.39** | 0.31–0.49 | 0.48 | 0.018 | 0.042 | — | — |

**Overall, read sample (n = 112):**

| | Rate | 95% CI |
| --- | --- | --- |
| Ours misses ≥ 1 facet that MU has | **0.94** | 0.88–0.97 |
| … not counting audio | 0.83 | 0.75–0.89 |
| … text-reachable facets only (kind, topic, place, people, vibe) | 0.70 | 0.61–0.77 |
| Any conflict | 0.089 | 0.05–0.16 |
| Any unsupported shown/said fact | 0.062 | 0.03–0.12 |

Mean facets per item: MU 6.67 of 8; ours 4.47; ours misses 2.58.

## By our information gate (read)

| Facet miss rate | ok (n = 102, read sample) | thin (n = 24, every thin item in the intersection) |
| --- | --- | --- |
| kind | 0.23 | 0.50 |
| topic | 0.03 | 0.13 |
| shown | 0.32 | 0.46 |
| said | 0.38 | 0.38 |
| audio | 0.68 | 0.54 (MU covers audio less often here: 0.54) |
| place | 0.35 | 0.46 |
| people | 0.12 | 0.29 |
| vibe | 0.40 | 0.38 |
| **≥ 1 facet missed** | **0.93** (0.86–0.97) | **0.96** (0.80–0.99) |
| … not counting audio | 0.82 | 0.88 |
| … text-reachable facets only | 0.70 | 0.71 |
| Mean facets missed | 2.51 | 3.12 |
| Ours: mean facets covered | 4.53 | 3.71 |
| Any conflict / any unsupported | 0.078 / 0.059 | 0.083 / 0.042 |

- The thin CIs are wide, with only 24 items.
- Thin items miss more facets per item (3.1 against 2.5), mostly kind, shown, place and people.
- The share of items with at least one miss is high in both groups, because audio, said and vibe are missed regardless of the gate.

## Lenient variant: count our value even when the facet is listed `unknown` (read, n = 112)

| Facet | Ours covers (strict → lenient) | Miss (strict → lenient) |
| --- | --- | --- |
| kind | 0.75 → 0.88 | 0.25 → 0.13 |
| topic | 0.96 → 1.00 | 0.04 → 0.00 |
| vibe | 0.50 → 0.93 | 0.39 → 0.05 |
| audio | 0.03 → 0.12 | 0.68 → 0.59 |
| said | 0.51 → 0.55 | 0.39 → 0.37 |
| ≥ 1 missed | 0.94 → 0.88 | |
| text-reachable facets only | 0.70 → 0.50 | |

- The model often fills `vibe`, and sometimes `kind`, while also listing the facet as unknown. In those cases the value is a hedged guess.
- Read strictly, vibe is half covered. Read leniently, it is nearly always present, and its conflict rate stays low (0.018).

## Regex cross-check (all 200)

| Facet | MU covers: core regex | MU covers: full MU regex (upper bound) | Miss: core regex | Regex vs reading agreement (n = 112) |
| --- | --- | --- | --- | --- |
| shown | 0.93 | 0.96 | 0.33 | 0.92 |
| said | 0.76 | 0.89 | 0.33 | 0.75 |
| audio | 0.75 | 0.79 | 0.72 | 0.95 |
| place | 0.64 | 0.69 | 0.42 | 0.75 |
| people | 0.85 | 0.98 | 0.16 | 0.77 |
| vibe | 0.86 | 0.94 | 0.42 | 0.95 |
| ≥ 1 missed | 0.945 | 0.965 | | |

- The regex miss rates over all 200 sit within about 0.06 of the read rates.
- Per item, though, the regex agrees with reading only 75–77% of the time on said, place and people. It over-counts generic words such as "room" and "he", and misses quoted on-screen text. The read rates are the headline.
- The "full MU" column also counts the comment-derived and community sections. It is an upper bound on what MU states anywhere.

## What this sizes (for builders)

- **Text gets topic and people right.**
  - Topic is missed on 4% of items and contradicted on 2%.
  - People is missed on 13% of items. Ours names creators more often than MU does, so its people coverage is slightly higher.
- **Kind is the main text-reachable gap.**
  - 25% of items get `other` or `unknown` where MU states the kind.
  - When ours does give a kind, it contradicts MU 8% of the time. Most of these are a joke or meme read as tips, tutorial or product ad, because the caption describes the purpose and the video is a gag.
- **Media-only facets are where the gap is:**
  - audio: 96% of MU's audio is missed;
  - said: 50% of MU's said is missed;
  - place: 60% of MU's place is missed, mostly generic settings such as kitchen, studio or street, which captions rarely state;
  - shown: 34% of items are missed;
  - vibe: 48% missed when read strictly.
- **Text alone cannot close these.** Even counting only the facets text could in principle reach, 70% of items miss at least one facet (50% read leniently).
- **What ours asserts is mostly not contradicted.**
  - Unsupported shown or said: 6% of items.
  - Most of these are caption lines placed in `said` when the video has no speech.
  - No audio claims were contradicted (ours makes almost none).

## Caveats

- **One reader.** The facet boundaries in the table above are judgement calls. A stricter reading of place and vibe would lower MU's coverage and the miss rates.
- **Reading cut-off.** MU text was read up to 1,800 characters (the median description is about 1,900). Facets mentioned only near the end, mostly audio and vibe, may be slightly undercounted for MU.
- **Not a random draw of the corpus.**
  - The intersection depends on which items Muse surfaced and on the enrichment sample, which includes the base's top 200.
  - It is 95% info-ok, almost all reels, and topically skewed toward the eval searches.
  - Rates for the whole corpus may differ.
- **MU is not ground truth.** Conflicts are counted against MU. In a few cases MU's reading of the video and the caption's reading disagree, and neither can be checked without the media.
