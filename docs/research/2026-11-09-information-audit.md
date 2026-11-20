# Round 9 Phase A: what each kind of media tells us, what people search for, and where Q8 falls short

*9 Nov 2026 · one founder's library (21,293 Instagram items, 115,615 YouTube videos) · BRIEF-9 Phase A parts 1–3 and the Track 1 item 6 trap tags · evaluator side (built no method). Aggregates only: no captions, titles, item codes or search texts. Per-search tags, presence checks and scores are in `data/all/eval_work/r9_audit/` (gitignored). Script: `experiments/eval/audit_r9.py` (`inventory`, `tag`, `presence`, `gap`).*

- **Spend:** $0.157 on OpenAI (gpt-5.4-nano, 711 calls: tagging $0.085 in two passes, presence checks $0.072). Gemini $0. The second tagging pass replaced prompt examples that echoed search wording with generic ones (`r9t-v2`); every number below is from that pass.
- **Method-side files** (tagger output only, no labels, no human ticks): `data/all/evals/facet_tags.json` (160 searches: dev, a 100-search `known_dev` sample drawn with seed 9, facet_dev) and `data/all/evals/trap_tags.json` (60 searches: dev and facet_dev). The `ig_real` tags stay evaluator-side.

## Bottom line

1. **On dev and YouTube, most of Q8's loss is on information we already have.** On these searches the target's own text holds what the search asks for ("present but not used"). Share of the lost score in each class:

   | Set | Present but not used | Information missing | Doubtful auto-label |
   | --- | --- | --- | --- |
   | dev | 70% | 30% | — |
   | `known_dev` | 41% | 27% | 31% |
   | facet_dev | 34% | 66% | — |
   | facet_dev, Instagram | 12% | 88% | — |

   In `known_dev`, the next video watched is often not what was searched, hence the doubtful-label share.
   - **The largest present-but-not-used gaps:** plain subject matching, then named creators (YouTube), then time and behaviour (YouTube), then content type.
   - **These are query-understanding and routing problems.** They are Track 1's job.
2. **Information missing is concentrated on Instagram, and on how things look and what makes them good.**
   - On facet_dev's Instagram half, 7 of 8 searches miss information. Half of the 8 targets are low-text items (round-1 info class "low").
   - On real Instagram searches, about a third ask how something looks and a quarter ask for "examples of" a quality.
   - For the targets of looks searches we checked, our text shows the look only 18% of the time (32% counting hints). On Instagram alone it is 29% (36%).
   - te `shown` cannot fill this gap: it is written from the caption, not from the media.
3. **The mix of searches decides the ranking.**
   - Dev and `known_dev` are mostly topic and creator searches, so visual and quality gaps rank low there.
   - Real Instagram searches (`ig_real`, tagger) ask for type 55%, looks 32%, examples 26% and a named creator 0%. That is close to facet_dev and far from dev.
   - Real Instagram searches ask for looks about 4× and examples about 2.5× as often as dev, so on real Instagram use those gaps weigh correspondingly more.
4. **Specificity cannot be read from the search text.** The tagger marks 1 of 8 real Instagram known-item searches as "this exact item", and 59% of `known_dev`. People search for a remembered item with topic-like words.
   - The intent frame (`qi-v1`) should treat `specificity` as uncertain. It should not decide routing on it.
5. **Rules beat the small model at tagging facets the way Derrick ticks them.** Agreement (micro-F1): rules 0.74 / 0.74 (facet_dev / facet_test), gpt-5.4-nano 0.63 / 0.68, and the final hybrid (rules plus the model for creator) 0.76 / 0.77.
   - Derrick's ticks are a floor for `when` and `tone`: across 31 searches he never ticked `when` and ticked `tone` once.

## 1. Information audit: what text exists, and how often it is empty or thin

### Instagram (21,293 items; the export has no media)

| Source | Present | Thin or empty |
| --- | --- | --- |
| Caption | 94.9% non-empty | 45.0% have < 4 content words; only 25.5% have ≥ 15. Round-1 info class: ok 70.3%, low 28.0%, non-English 1.7% |
| Hashtags | 64.3% | |
| Creator | handle 98.4%; display name 89.5% | |
| Collection names | 5.2% of items (16 names) | |
| Signals | like 89.6%; DM share 16.4% (to self 11.6%, from or to friends 5.2%); save 3.6%; collection 5.2%; watch/view 1.5% | DM message text is never read (rule 8) |
| Date | 98.5% have a timestamped interaction | Collection membership has no timestamp |
| Media kind | reel 82.9%, post 17.1% | The only "type" signal not derived from the caption |
| Friends' posts (mutual) | 2.2% | Never sent to an LLM; counts only |
| te-v1c row | 97.8% of items (100% of non-friends) | Made from caption, hashtags, creator, kind and collection names only. It re-expresses that text and adds no new information. On thin input it can invent a subject. |
| te fields (share of rows with the field filled) | topics 96.0, people 84.3, vibe 86.6, shown 68.2, kind specific (not "other") 63.8, use 62.4, said 58.7, place 25.4 | `audio` is listed as unknown on 98.5% of rows |

### YouTube (115,615 videos)

| Source | Present | Thin or empty |
| --- | --- | --- |
| Title (Takeout) | 87.3% | 12.7% empty or placeholder. Only 47.2% have ≥ 4 content words; 20.8% have ≤ 2 |
| Channel | 87.3% | |
| Playlist names | 0.2% named; Watch later 4.3% (31 names) | |
| Watch count | 94.0% watched ≥ 1 | rewatched ≥ 2: 5.4%; ≥ 5: 0.1% |
| Like | 4.4% | |
| Date | 100% (watch or playlist timestamps) | |
| Duration | known for 90.9% (median 85 s) | Of those: ≤ 60 s 45.7%, ≤ 180 s 56.8%, ≥ 20 min 14.7%. `media_kind` is always "video", so Shorts are known only from duration |
| Hashtags | 0% | |
| Text not used by Q8 | te-v1c allowed rows for 5.6% of videos; tv-v1 video-pass rows 1.0% (research-only, round 3) | |

### Which sources could answer each facet today (share of items)

| Facet | Instagram | YouTube |
| --- | --- | --- |
| **creator**, named | handle 98.4% | channel 87.3% |
| **creator**, described | No creator profile text. It could only come from pooling that creator's items; not built. | same |
| **topic** | own text ok 70.3%; own text or te topics 94.9% (te inherits thin captions) | title with any content word 85.7%; descriptive title (≥ 4 words) 47.2% |
| **type** | reel/post 100%; te kind 62.4% (from the caption); a format word in the caption 25.7% | duration 90.9% (Shorts vs long); a format word in the title 18.7% |
| **looks** | te `shown` 66.7%, but **written from the caption, not the media**; a visual word in the caption 23.9%. Media: none | a visual word in the title 4.8%; te `shown` 3.7% (not in Q8); video pass 1.0% (research). Media: Gemini URL route (Track 2) |
| **sound** | an audio word in the caption or hashtags 9.2%. No audio or track name in the export; te says audio unknown on 98.5% | an audio word in the title 3.1%; video-pass music 0.8% (research) |
| **said** | te `said` 57.5% (quotes and claims from the caption, not speech) | a quote mark or "says" in the title 2.7%. Transcripts are never stored (rule 8) |
| **tone** | te `vibe` 84.7% (inferred from the caption); a tone word in the caption 11.7% | a tone word in the title 3.4%; te `vibe` 5.0% (not in Q8) |
| **examples** | No direct field. A judgement over the same text as topic, tone and looks, so bounded by those | same |
| **when** | timestamps 98.5%; like/save/share signals | timestamps 100%; watch count, rewatches, likes, playlists |
| **platform** | 100% | 100% |

The keyword shares ("a visual word", "a format word") come from small curated regexes. Read them as rough indicators, not exact measures.

## 2. Query taxonomy: what the searches ask for

### Tagger

| Tagger | What it is |
| --- | --- |
| **Rule tagger `r9r-v1`** | Curated regexes for each facet. A creator gazetteer built from the user's own library: creator names with ≥ 2 items, no common English words. Exact-item phrases for specificity. |
| **Small model** | gpt-5.4-nano with reasoning low, prompt `r9t-v2`. No current method uses this model. It sees the gazetteer's hits as a hint. |
| **Final hybrid `r9c-v2`** | Rules for every facet except creator, which comes from the model. Specificity is exact if either the rules or the model says exact. |

The hybrid was chosen facet by facet on facet_dev. The facet_test numbers had already been seen at that point, so facet_test is not a clean held-out check of the choice.

**Agreement with Derrick's `based_on` ticks** (16 facet_dev and 15 facet_test searches; ticks per facet: true / predicted / both):

| Tagger | facet_dev: micro P / R / F1 | facet_test: micro P / R / F1 | Specificity agrees (dev / test) |
| --- | --- | --- | --- |
| Rules | 0.73 / 0.74 / 0.74 | 0.78 / 0.71 / 0.74 | 0.88 / 0.87 |
| gpt-5.4-nano | 0.54 / 0.77 / 0.63 | 0.60 / 0.78 / 0.68 | 0.75 / 1.00 |
| **Final hybrid** | **0.74 / 0.79 / 0.76** | **0.81 / 0.73 / 0.77** | 0.81 / 0.93 |

Per facet, final tagger (both sets together):
- **creator:** 8 ticks; 8 predicted, 6 agree.
- **looks:** 13 ticks; 12 predicted, 10 agree.
- **type:** 24 ticks; 21 predicted, 17 agree.
- **examples:** 11 ticks; 7 predicted, 5 agree. Derrick ticks this inconsistently for similar wording.
- **sound:** 2 ticks; 1 agrees.
- **tone, said and when** are almost never ticked.

The model over-tags `tone` and `when`, mostly on words that do carry them (mood adjectives; "old", "used to"). That is partly the floor in Derrick's ticks rather than an error. Exact-set agreement is low for every tagger (0.06–0.20), because Derrick usually ticks 2–4 facets.

**Specificity in real searches:**
- `ig_real`: of 8 known-item searches, the tagger calls 1 exact.
- `known_dev` sample: 59% exact, although every search there has one target by construction.

### Facet mix (share of tagged searches; more-like-this searches excluded: dev 6)

| Set (n) | creator (named / described) | topic | type | looks | sound | said | tone | examples | when | platform | exact |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dev, all (38) | 8 (3 / 5) | 100 | 63 | 8 | 8 | 3 | 8 | 11 | 26 | 16 | 18 |
| dev, Instagram (18) | 6 (0 / 6) | 100 | 39 | 11 | 11 | 0 | 6 | 17 | 17 | 33 | 11 |
| dev, YouTube (20) | 10 (5 / 5) | 100 | 85 | 5 | 5 | 5 | 10 | 5 | 35 | 0 | 25 |
| known_dev sample, YouTube (100) | 46 (46 / 0) | 91 | 8 | 4 | 3 | 2 | 4 | 1 | 2 | 1 | 59 |
| facet_dev, all (16) | 31 (19 / 13) | 100 | 81 | 31 | 6 | 0 | 6 | 25 | 6 | 0 | 13 |
| facet_dev, Instagram (8) | 13 (0 / 13) | 100 | 75 | 50 | 13 | 0 | 0 | 38 | 0 | 0 | 0 |
| facet_dev, YouTube (8) | 50 (38 / 13) | 100 | 88 | 13 | 0 | 0 | 13 | 13 | 13 | 0 | 25 |
| ig_real, Instagram (31; evaluator-side tags) | 3 (3 / 0) | 100 | 55 | 32 | 6 | 0 | 6 | 26 | 3 | 3 | 3 |
| *Derrick's ticks, facet_dev (16)* | 31 | 81 | 69 | 44 | 6 | 0 | 0 | 38 | 0 | — | 19 |
| *Derrick's ticks, facet_test (15)* | 20 | 80 | 87 | 40 | 7 | 0 | 7 | 33 | 0 | — | 20 |

Reading:
- `known_dev` is creator-and-topic keyword search: 46% name a creator, 1.6 facets per search.
- Real Instagram searches are about type, looks and quality, and almost never name a creator.
- `said` is close to absent everywhere: 1 dev and 2 `known_dev` searches.
- `when` (time or behaviour) is a YouTube dev phenomenon: 35% of dev YouTube searches.

## 3. Info gap: does our text hold what each facet needs, and how does Q8 do?

### Method

**Targets checked:**
- dev: up to 5 top-grade targets per search, seeded sample (163 pairs);
- `known_dev` sample: up to 3 grade-2 targets (108);
- facet_dev: the grade-3 target (16).

**How presence was judged:**
- gpt-5.4-nano (prompt `r9p-v2`) read the search and the item's indexed text: own view, te-v1c row, dates and signals. For each needed facet it wrote what the search asks for, then answered yes, partial or no.
- One dev target was a friend's post. It was not sent; field rules were used instead.
- `when` and `platform` were judged by rule: the data exists. That does not mean the target falls in the window the person meant.

**Q8 score** (mean of 3 repeats):
- dev: nDCG@10 on current labels (3-point, gains 2^g − 1);
- `known_dev`: mrr2;
- facet_dev: MRR of the target. For its 13 "like" searches this is a **floor**: other good items in the top 10 are not judged yet. In most repeats, the target is in the top 10 for 2 of 16 searches and in the top 100 for 7. It is not in the top 1,000 for 6.

**Loss partition:** each search's loss (1 − score) goes to one class.
- **Information missing:** the facets for which most of its checked targets' text says nothing. The loss is split equally over them.
- **Present but not used:** otherwise. The loss is split over the search's distinctive facets:
  - `type` only when a format word is present, not just "videos";
  - `platform` only when a platform is named;
  - `topic` when nothing else is left.
- **Doubtful auto-label:** `known_dev` searches whose targets lack the information *and* share no word with the search. These are most likely labels that are not what was searched for (round 8 found 62.5% of targets clean).
- **Priority** = the cell's share of the set's searches × their mean loss. The ranking averages dev and `known_dev`, the two sets fully labelled for Q8's metric. facet_dev is shown beside it.

### Per facet

| Facet | Targets whose text shows it: yes / yes+partial (Instagram; YouTube) | Q8 on searches needing it: dev nDCG@10 (n) · known_dev mrr2 (n) · facet_dev target MRR (n) | Q8 on searches without it (dev · known_dev) | Failed: information missing / present not used (dev · known_dev · facet_dev) |
| --- | --- | --- | --- | --- |
| creator | IG n<5; YT 40% / 68% (62) | 0.575 (3) · **0.197** (46) · 0.163 (5) | 0.522 · 0.323 | 0/1 · 11/16 · 2/1 |
| topic | IG 33% / 75% (88); YT 37% / 68% (187) | 0.526 (38) · 0.284 (91) · 0.059 (16) | – · 0.076 | 2/13 · 31/18 · 6/8 |
| type | IG 37% / 97% (38); YT 70% / 87% (86) | 0.586 (24) · 0.514 (8) · 0.072 (13) | 0.425 · 0.244 | 0/8 · 0/2 · 0/11 |
| looks | IG 29% / 36% (14); YT 0% / 25% (8) | 0.669 (3) · 0.256 (4) · 0.010 (5) | 0.514 · 0.266 | 1/0 · 3/0 · 4/1 |
| sound | IG 38% / 63% (8); YT 0% / 33% (6) | **0.183** (3) · **0.005** (3) · – (1) | 0.556 · 0.273 | 2/1 · 2/1 · – |
| said | YT n<5 | – (1) · – (2) · none | | too few |
| tone | IG 60% / 80% (5); YT 13% / 47% (15) | 0.385 (3) · 0.183 (4) · – (1) | 0.539 · 0.269 | 1/0 · 1/1 · – |
| examples | IG 33% / 61% (18); YT 17% / 33% (6) | 0.450 (4) · – (1) · **0.000** (4) | 0.535 · – | 1/1 · – · 4/0 |
| when | 100% (rule: data exists) | **0.400** (10) · – (2) · – (1) | 0.572 · – | 0/5 · – · – |
| platform | 100% (rule) | 0.499 (6) · – (1) · none | 0.532 · – | 0/2 · – · – |

Notes:
- Cells under 3 searches are suppressed (–).
- "Failed" means dev nDCG@10 < 0.5; for `known_dev` and facet_dev, the target is outside the top 10 in most repeats.
- Every per-facet cell is descriptive. At the median sd_d, the MDE is about 0.12 for 10 searches and about 0.3 for 3. Some `known_dev` "information missing" failures are the doubtful labels above.

Where present-but-not-used failures sit:
- **Type:** wholly present but not used. Our text names the format 90% of the time (yes + partial).
- **When** (dev): also wholly present but not used. The dates, watch counts and likes exist, but Q8 does not use them as signals; round 3's intent filters did.

Where information-missing failures sit:
- **Looks and examples** on facet_dev: information is missing in 4 of 5 looks failures and 4 of 4 examples failures.
- **Instagram topic:** for 6 of 8 facet_dev Instagram targets, the text does not show the search's subject. 4 of the 8 are low-text items. Derrick's sheet over-samples visual-, audio- and type-heavy items, so it shows this more than an average item would.

### Gap ranking (priority = share of searches × mean loss; mean of dev and known_dev)

| # | Facet: class | Priority | dev (searches) | known_dev (searches) | facet_dev floor (searches) | Fix |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | topic: present but not used | 0.124 | 0.101 (9) | 0.147 (27) | 0.062 (1) | query understanding: subject + `item_language`, wrapper drop |
| 2 | topic: information missing | 0.086 | 0.051 (5) | 0.122 (14) | 0.249 (6) | media or better item text (thin Instagram captions, untitled YouTube) |
| 3 | creator: present but not used | 0.070 | 0.016 (2) | 0.123 (21) | 0.048 (2) | creator lookup used only when the frame has a creator (Track 1 item 2) |
| 4 | when: present but not used | 0.052 | 0.105 (8) | 0.000 (1) | 0.031 (1) | time window + behaviour filters from the frame (round-3 intent filters) |
| 5 | type: present but not used | 0.042 | 0.064 (7) | 0.020 (7) | 0.118 (3) | type slot → te `kind` / duration; format word not treated as topic |
| 6 | creator: information missing | 0.029 | 0.000 (0) | 0.059 (8) | 0.123 (2) | described creators need creator profiles; nicknames need personal vocabulary (item 7) |
| 7 | examples: information missing | 0.019 | 0.037 (2) | 0.000 (0) | 0.125 (4) | quality is rarely in text: media descriptions, or a learned quality signal |
| 8 | tone: present but not used | 0.012 | 0.017 (2) | 0.007 (2) | 0.031 (1) | tone slot → te `vibe` |

Not product gaps:
- **Doubtful auto-label** (`known_dev`, 23 searches) has priority 0.115. It is a measurement problem, not a product gap: `known_dev` labels are the next video watched.

Next in the ranking:
- sound, information missing 0.011;
- sound, present but not used 0.010;
- tone, information missing 0.009;
- looks, information missing 0.009, but 0.124 on the facet_dev floor.

**With facet_dev given equal weight**, the order becomes:
1. topic, missing (0.140)
2. topic, present but not used (0.103)
3. type, present but not used (0.067)
4. creator, present but not used (0.063)
5. creator, missing (0.061)
6. examples, missing (0.054)
7. looks, missing (0.047)
8. when, present but not used (0.045)

**On the platforms' own mixes:**
- **Dev YouTube:** the order is when (0.160), then topic present but not used (0.071), topic missing (0.071) and examples missing (0.048).
- **Dev Instagram:** topic present but not used (0.133) leads, then type present but not used (0.087).
- Real Instagram searches carry about 4× dev's share of looks searches and about 2.5× its share of examples searches. On that mix, looks and examples, information missing, are the leading Instagram gaps after general topic matching.

### Instagram looks and sound (for Track 2)

- **Looks:** 64–71% of the targets of Instagram looks searches have nothing in our text about the look (yes 29%, partial 7%). te `shown` cannot close this, because it restates the caption.
- **Sound:** Instagram sound targets fare better (38% / 63%), because music reels name the song or the instrument in the caption. There is no audio-only cue in the export.
- **What an approved media route would need to deliver to matter:** a short description of what is shown (subject, style, setting, on-screen text) and of the music or sound, indexed as one coverage-fair list. It must cover the thin-caption items: the round-1 "low" info class is 28% of Instagram, and these targets are where the information is missing.

## 4. Literal traps (Track 1 item 6)

| Trap | dev (38) | facet_dev (16) | ig_real (31, evaluator-side) | known_dev sample (100) |
| --- | --- | --- | --- | --- |
| wrapper words ("videos", "reels", …) | 58% | 31% | 10% | 2% |
| count words | 5% | 0% | 0% | 1% |
| examples-of / instance | 24% | 38% | 19% | 5% |
| described creator | 5% | 13% | 0% | 0% |
| format word used as topic | 29% | 56% | 52% | 7% |
| negation | 5% | 0% | 0% | 2% |
| personal shorthand | 3% | 13% | 6% | 14% |
| any trap | 92% | 94% | 71% | 24% |

How the traps are tagged:
- **Rules:** wrapper, count, negation and format-as-topic.
- **gpt-5.4-nano:** examples-of and shorthand.
- **Final creator mode:** described creator.

Q8's level with and without each trap (groups of ≥ 3 only):

| Set | Trap | n | Q8 with | Q8 without |
| --- | --- | --- | --- | --- |
| dev (nDCG@10) | wrapper | 22 | 0.572 | 0.464 |
| dev | format word | 11 | 0.585 | 0.503 |
| dev | examples-of | 9 | 0.550 | 0.519 |
| facet_dev (target MRR, floor) | format word | 9 | 0.028 | 0.098 |
| facet_dev | examples-of | 6 | 0.002 | 0.093 |
| facet_dev | wrapper | 5 | 0.142 | 0.021 |

Traps are not failures by themselves:
- **Dev:** wrapper and format-word searches score above the rest. 14 of dev's 22 wrapper searches are YouTube searches.
- **facet_dev:** examples-of and format-word searches are the ones that score worst.

Every Track 1 arm should report its Δ per trap from `trap_tags.json`.

## Caveats

- **Small sets.** Every facet cell is small. facet_dev and facet_test have 16 and 15 searches, and dev has 38 tagged. Treat the ranking as an agenda, not a measurement. The MDE on a 10-search cell is about 0.12.
- **Unchecked presence judge.** One small model made the presence calls and no human checked them. `when` and `platform` presence is by rule. The dev targets are a sample of the top-grade items.
- **`ig_real` is not scored here.** Phase 0 scores it. Only its facet and trap mix is used.
- **The tagger was chosen with both facet sets visible.** facet_test agreement had been seen before the hybrid was chosen.
- **The small model is not stable between passes.** The `r9t-v1` and `r9t-v2` passes differ on creator mode, examples-of and shorthand for a few searches. The hybrid's facets depend on the model only for creator, so they barely moved: `known_dev` named creators went from 43% to 46%.
- **Derrick's ticks are a floor.** He rarely ticks `when` or `tone`, so agreement on those facets cannot be measured.
