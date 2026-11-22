# Round 12, MVP version 7: history answers that give insight, not data (counts only)

22 Nov 2026. Branch `experiments/search-loop`, code at 1c5b77a. The design is `experiments/mvp/DESIGN.md` section 19.
The round's brief, the judges' notes and every live conversation are kept outside git.
No titles, channel names, theme names of the real library, handles or captions appear here. Counts are fine.

## What was asked

The founder graded the first 8 rows of his sheet on build 1f9cde0, on his own library.
He wrote: "it doesn't really answer the question properly. can we please refine this so that it does before i judge
again?"

His rules for every history answer, in short:
- R-A answer the question asked. R-B insight, not raw data; a small chart is welcome.
- R-C give more than was asked. R-D name themes; judge by how much was watched, not only by counts.
- R-E answer "so what?". R-F offer a follow-up: without Shorts, only one topic.
- R-G an overview first, then the items. R-H no closing line about limits.
- R-I say what only his own history can say.

Scope was history answers only. Picks, recalls, summaries, asking videos, rules, emails and cancels are unchanged.

## Grades, row by row

Before is the founder's own grade. The merge judge read build 2bbed61. The final judge read build 1c5b77a, after the
fix pass. Both judges read the live answers on the real library as the founder would. They are not the founder.

| # | Question | Founder, before (1f9cde0) | Merge judge (2bbed61) | Final judge (1c5b77a) |
| --- | --- | --- | --- | --- |
| 1 | what have i been watching the most lately | Partly, slop | Partly, half slop | Partly, half slop |
| 2 | which channels did i watch the most in 2025 | Partly, slop | Partly, slop | Partly, half slop |
| 3 | how many minecraft videos did i watch this year | Useful, not slop | Useful, not slop | Useful, not slop |
| 4 | when did i first start watching blender videos | Partly, not slop | Partly, not slop | Useful, not slop |
| 5 | did i watch more gaming or more art videos this year | Not useful, slop | Partly, half slop | Useful, half slop |
| 6 | what did i watch on october 30 | Partly, half slop | Partly, half slop | Partly, half slop |
| 7 | how has what i watch changed since 2020 | Not useful, slop | Useful, half slop | Partly, half slop |
| 8 | what was i into in the summer of 2023 | Not useful, slop | not received | not received |

- Founder, before: 1 useful, 4 partly, 3 not useful. 5 of 8 slop, 1 half slop.
- Merge judge, rows 1 to 7: 2 useful, 5 partly, 0 not useful. 1 slop, 4 half slop.
- Final judge, rows 1 to 7: 3 useful, 4 partly, 0 not useful. 0 slop, 5 half slop.
- Both judges said every row they graded answers the question asked.
- Row 8 of both judges, and the second merge judge's rows, did not reach these notes. They are not guessed here.

My own reading of row 8 at 1c5b77a (the note writer's, not a judge's grade):
- It answers the question: the season's dates, then "a wide mix", led by three themes at 5 to 6% each.
- It says which themes grew against the spring, the channels behind the leader, and the length leader.
- Its weak spot is row 1's: the lead is the biggest of many small slivers, so no overall picture is said.

### What the final judge still wants, by row

1. Lead with the broad picture (the build already has fields), not "one theme led with 6.5%". Drop the export hint.
   The so-what (one unopened saved video) gives nothing to learn or do.
2. Drop the yearly length total: about 3,356 hours in 2025 reads as 9 hours a day of watching. Say what each top
   channel is. Offer "only <topic>". There is no so-what.
3. The headline count is not trustworthy. Of 1,711, only 842 carry the topic's word in the title. The largest
   sub-theme, 540 openings, has the word in none. Compare the count with all he opened and with last year.
4. Say the count once. Offer "show the saved tutorials" instead of "by month". Turn the path into a next step.
5. Name the themes inside each side. Replace the "first appeared in" line with the change against last year. Add a
   so-what.
6. No "mostly" for 3 of 10. Drop bullets that repeat the overview, and the "each account for 1" filler. Say how the
   day compares with his usual day. No offer about something else.
7. The shift is between slivers (7% down to 1%, 0.1% up to 6%). The answer skips years its own chart says were led by
   another theme.

## What was built

### Lengths and Shorts (`lengths.py`, `lengths-v1`)

- The official length of every watched YouTube video, from the YouTube Data API's videos.list. Nothing else is fetched.
- Kept under `data/mvp/derived/lengths-v1/`, one row per video id, refreshed after 30 days. Runs resume.
- The export has no watch time. So "how much" means how often, on how many days, or the length of what was opened.
- The Short rule, chosen from the data: at most 61 s; or at most 180 s if published from 15 Oct 2024.
- With no publish date, a Short is at most 180 s with a #shorts-style mark in the title.
- Videos over 3 hours (streams, loops) are left out of every length sum and counted apart.

### Themes (`themes.py`, `themes-v2`, prompt `theme_name_v2`)

- Clustering ported from docs/05: centre, PCA to 24, a Ward tree on a 6,000 sample, then spherical k-means.
- Two levels: fields, and themes inside each field. One naming call per field, never one per item.
- Each theme gets a fixed category, so "gaming" or "art" maps to the right themes by code.
- A sensitive theme keeps no name and no words. Its items fall under no theme.
- Every row carries the version and the embedding model. Builds run only by command, never while a person waits.
- A named topic maps to themes by code (`themes.for_topic`).

### The fact sheet (`facts.py`)

- One plain dict per history question, built by code only. It is the only source of facts for the writer.
- It holds the window in a person's words, totals, the window before, themes with share and change, channels, periods.
- It also holds Shorts against long videos, what is new and what stopped, and things saved but never opened.
- The window's own words carry where the export ends ("the 4 weeks up to 30 October 2026, where your export ends").

### Questions that were misread, now read by code (`history.py`)

- "did i watch more X or Y", "how has what i watch changed", "what was i into in <a season or year>".
- "most watched channels in <topic>", "... without shorts", and "back in 2021" (no longer a topic "back").
- Spanish "how has what I watch changed" was added in the fix pass.

### The checked writer (`insight.py`, prompt `insight_v4`)

- One model call per answer fills a form: the answer, 2 to 4 observations, a so-what and up to 3 offers.
- Code checks every sentence against the sheet: numbers, dates, names, ranks, "grew" and "new".
- A sentence that fails is dropped. Watch-time words, limits lines and lines true for anyone are dropped too.
- The fix pass added a rank check, "mostly" only for a fifth or more, and a cap on runs of numbers and names.
- When the model's form is well formed, code fills what was dropped from the same sheet, through the same check.
- Today's code reply is still the fallback: writer off, cap reached, call failed, fake model with no script.

### Charts, layout, offers and quiet limits

- A small chart of whole block cells, drawn by code, at most 8 rows (12 for a year by month).
- The answer first, then observations, the chart, the so-what and one line of offers.
- For a day, a first or a last: the overview first, then the items with their cards.
- Offers are taken by code in their own words for 6 hours: "without Shorts", "only <theme>", "by month", "by theme".
- "yes" to the so-what lists the saved videos never opened, with cards, by code.
- No closing paragraph on limits. The export hint is said at most once in 6 hours, only about a time past the export.
- The friends line is said only when the question is about friends.

## What was measured

### Lengths and Shorts

| Measured | Result |
| --- | --- |
| Watched YouTube videos asked | 108,685, in 2,174 calls (= quota units), 0 errors, 318 s, 342 items/s |
| With a length | 98,086; 10,599 got no answer (deleted or private) |
| Agree with the corpus's own `duration_s` | 97,986 of 98,086 |
| Called Short by the chosen rule | 53,184 of 98,086 |
| Called Short by other rules tried | 46,895 (at most 60 s), 58,044 (at most 180 s), 8,819 (title mark only) |
| Estimated long videos wrongly called Short | about 320 |

Why that rule: for videos published since 15 Oct 2024, each 15-second bin from 60 to 180 s holds 270 to 2,970 videos.
Bins from 195 to 300 s hold 37 to 46. That cliff at 180 s is absent for older videos.

### Themes

| Measured | Result |
| --- | --- |
| Real library | 98,677 watched items clustered, 19 fields, 50 themes, 75 s a build |
| Dropped as sensitive | 7 themes and 4 field names |
| Made-up library | 8 of 8 non-sensitive themes recovered exactly; the sensitive one has no name |
| 12 real themes x 10 items, read by D | 93 of 120 items belong |
| Names that fit, of 12 | v2 8 (2 more partly), v1 8, the code's own typical words 7 |
| Watched items with a topic | 3,086 of 108,997 before (2.8%); 84,344 after (77.4%) |

k is chosen by silhouette, not docs/05's biggest gap: the gap rule merged four made-up themes into one.

### Claims recounted

- D: 12 sheet numbers recounted by a script sharing no code with the bot. 12 of 12 the same.
- The final judge's own recount found the Minecraft headline count unsupported (842 of 1,711 carry the word).
- The fix pass left that mapping alone. It needs a change to the topic mapping and its own evaluation.

### Made-up facts caught (20 made-up sheets, `eval_insight.py`)

| Run | Answers the question | Limits line | Run of yearly counts | Writer used | Observations kept |
| --- | --- | --- | --- | --- | --- |
| Before (today's code reply, emulated) | 4 of 20 | 7 | 2 | - | - |
| `insight_v1` | 7 | 1 | 2 | 7 | 29 |
| `insight_v4`, merge check | 17 to 18 | 0 | 0 | 18 | 51 to 52 |
| `insight_v4`, fix check and fill | 18 | 0 | 0 | 20 | 57 |

- Planted false sentences: 76 of 76 dropped. True sentences: 56 of 56 kept.
- The prompt did not change in the fix pass. Only the check and the fill did.

### Falling back to the old reply

- Merge judge: 6 of 19 writer calls fell back to the old reply the founder graded.
- After the fix, offline on captured forms: 4 of 13 fell back before, 0 of 54 after.
- Last live run of the fix pass: 11 of 11 answers were the writer's.

### Traps and things that must stay true

- D's tests: 23 readings, 43 traps and 12 follow-up traps.
- The 159 rule texts and 123 phrasings: taken by no new read. Round 11's traps: not taken.
- Dev phrasing set by code: 73 helper lines right, 1 wrong (d007), 1 of 40 none lines taken (d132). Unchanged.
- `probe_same`: byte-equal with `same_head.json` (checked again at 1c5b77a).
- Full suite, 4 shards: 5,018 passed, 0 failed (4,713 before the round).
- New tests: 125 (D), 71 (W), 64 (merge), 45 (fix).
- Demo: 10 passed. Dry self-test: 67 conversations, 164 of 164 steps (59 and 152 before; c59 to c66 are the 8).

### Cost and seconds per answer (final judge's live run, 1c5b77a)

| Answer | Seconds | Model calls | Cost |
| --- | --- | --- | --- |
| The 8 questions | 2.8 to 5.3 | 1 each | $0.0044 to $0.0051 each, $0.037 for all 8 |
| 4 variants | 2.9 to 4.5 | 1 each | $0.0041 to $0.0045 each |

- A first sheet on the real library takes 4.4 s (building the index). Later sheets take 0.05 to 1.1 s.
- No call is made for a list, a next page, the saved list or "the first one".

## What changed on purpose in earlier tests

Rule R-H changes closing lines, so some earlier expected replies changed. Each is marked in place.
- W: lines in `test_round11_h.py`, `test_round11_fix_a.py`, `test_round11_checks.py`, `test_round11_fix2.py`,
  `test_round11_fix2_checks.py` and `test_round11_fix_checks.py` (the window's own words, the hint once, no friends
  line). Self-test lines c40.1, c40.2, c54.1, c54.2.
- Fix: `test_round11_fix2.py` p4_10 and p4_11, `test_round11_fix2_checks.py` n27 and n28, `test_round11_fix_checks.py`
  m45. Spanish "how has what I watch changed" is now read as changed, not as a timeline.
- D: `test_round9_merge.rule_phrasings` skips round 12 test files. The `test_mvp.py` fixture sets its own derived home.
- The full list is in DESIGN 19.W and 19.F.

## Still wrong or unproven

- The lead is often the biggest of many 5 to 6% slivers (rows 1 and 8). No broad picture by field is said.
- Length totals over long windows read as watch time: about 3,356 hours in 2025, about 13,894 hours since 2020.
- They are the summed lengths of the distinct videos opened. The median video is about a minute long.
- A topic's count includes themes matched by their name, even where most items lack the word. Row 3 may be far too high.
- The export hint still appears on the first answer, once in 6 hours, as the brief allows. He asked for no limits.
- The so-what is still mostly "you saved N and never opened them". Row 4's path ("it has faded") is the exception.
- Rows 2 and 5 had no so-what in the final run. Row 6's so-what was unrelated to the day.
- "mostly" passes for 3 of 10 on a small day. Some filler still gets through ("each account for 1 of the 3").
- A model sentence can be true and garbled: a share of length said as a share of videos.
- The writer is measured on 20 made-up sheets and a few live readings. There is no evaluation on real sheets.
- Theme names are not confirmed by the person. 4 of 12 read did not fit. One theme of 12 was a mixed bag.
- Only theme names are checked for sensitivity. 1 of 120 items read in a non-sensitive theme was about health.
- "more X or Y" is read in English only. Seasons follow the northern hemisphere.
- One live question once gave no reply for 300 s, then answered in 9 s. Not reproduced.
- iMessage was not seen. The page at 430 px was not screenshotted after the fix pass.

## Conflicts with docs/ (for an amendment; docs/ not edited)

- docs/05 stage 3 picks k at the biggest gap in merge heights. Here k is picked by silhouette.
- docs/05 clusters saves, likes and shares after the content filter. Here the watched items are clustered.
- docs/03 keeps themes in a `themes` table with a 20-dimension frozen space. Here PCA is 24, kept in derived files.
- These are on the prototype branch only.

## Spend

- Ledger: about $22.37 at the round's start, $23.30 now. This round: about $0.92.
- By purpose: the writer $0.73 (208 calls), theme naming $0.12 (57 calls), the rest about $0.09.
- Lengths cost nothing (the free YouTube quota). The cap is $30: $6.70 is left, $2.70 under the $26 ceiling.
