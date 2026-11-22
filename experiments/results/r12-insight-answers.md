# Round 12, MVP version 7: history answers that give insight, not data (counts only)

22 Nov 2026. Branch `experiments/search-loop`, code at 1c5b77a. The design is `experiments/mvp/DESIGN.md` section 19.
The round's brief, the judges' notes and every live conversation are kept outside git.
The second pass, code at d7aa507, is the part "The second pass". The third pass, code at dd2b1b0, is the last part.
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
- Recorded as amendment A-019 (Proposed) in `docs/amendments.md`, with the second pass's conflicts added.

## Spend

- Ledger: about $22.37 at the round's start, $23.30 now. This round: about $0.92.
- By purpose: the writer $0.73 (208 calls), theme naming $0.12 (57 calls), the rest about $0.09.
- Lengths cost nothing (the free YouTube quota). The cap is $30: $6.70 is left, $2.70 under the $26 ceiling.

## The second pass

22 Nov 2026. Code at d7aa507. The design is DESIGN 19.P2 and 19.P2 fix.
The pass's scope (T1 to T15) and the judges' notes are kept outside git.
No titles, channel, theme or field names of the real library appear here. Counts are fine.

### What it was for

The first pass's last judge, on ace4be2, gave 3 useful and 5 partly, with 6 of 8 half slop.
All 8 answered the question. But a number could stand next to the wrong thing, and length totals read as watch time.
The lead was often the biggest of many small slivers. The so-what was mostly "you saved N".
The orchestrator listed fifteen things still wrong, T1 to T15. The founder's words stayed the bar.

How it was built:
- A first fixer, code at 2257352: T1 to T15, a new prompt `insight_v5`, 74 tests.
- Two judges read it live. A graded as the founder. B recounted claims and attacked the check with a fake model.
- A second fixer, code at d7aa507: every must-fix of both judges, 83 tests.
- A final judge read d7aa507 live on the real library, as the founder would.

### Grades, row by row

The judges are not the founder. They read the live answers on the real library as he would.

| # | Question | Founder, before (1f9cde0) | Judge A (2257352) | Final judge (d7aa507) |
| --- | --- | --- | --- | --- |
| 1 | what have i been watching the most lately | Partly, slop | Partly, half slop | Partly, half slop |
| 2 | which channels did i watch the most in 2025 | Partly, slop | Partly, half slop | Partly, half slop |
| 3 | how many minecraft videos did i watch this year | Useful, not slop | Useful, half slop | Useful, not slop |
| 4 | when did i first start watching blender videos | Partly, not slop | Useful, half slop | Useful, half slop |
| 5 | did i watch more gaming or more art videos this year | Not useful, slop | Partly, half slop | Useful, half slop |
| 6 | what did i watch on october 30 | Partly, half slop | Useful, half slop | Useful, half slop |
| 7 | how has what i watch changed since 2020 | Not useful, slop | Partly, half slop | Useful, not slop |
| 8 | what was i into in the summer of 2023 | Not useful, slop | Partly, half slop | Partly, half slop |

- Founder, before: 1 useful, 4 partly, 3 not useful. 5 of 8 slop.
- First pass, last judge (ace4be2): 3 useful, 5 partly, 0 not useful. 6 of 8 half slop.
- Judge A (2257352): 3 useful, 5 partly, 0 not useful. All 8 half slop.
- Judge A also found four false or wrongly bound sentences that the check let through.
- Judge B gave no grades. It found a channel's Shorts share said as 46% that is 29%, among other claims.
- Final judge (d7aa507): 5 useful, 3 partly, 0 not useful. 2 not slop, 6 half slop.
- Every judge said every row answers the question asked.
- The final judge found every number it recounted true.

Four follow-ups the final judge typed after the 8:
- "without shorts" after row 8: not right. It says a channel was almost all Shorts, inside a without-Shorts answer.
- The same answer leads by area but charts by theme, eight slivers of 2 to 4%.
- "most watched channels in math this year" (his own wish): right. One off-topic channel sits in the top 8.
- In that answer the Shorts move is four raw counts where two shares belong.
- A "last 3 months" wording of row 1: not read as a history question. It went to picks and gave one video.
- A change between two years: the judge's note did not reach these notes.
- My own reading of it: told year by year, volume bars with a theme per year. That is the shape T4 replaced.

### What the final judge still wants, by row

1. Lead with what changed about him, not three shares. Say what a fall is measured against.
   There is no so-what. The offers name themes the answer never said.
2. "1 points from 2024" is garbled and has no direction. The so-what is about Shorts, not about the channels.
3. The month bars add up to 1,107; the lead says about 1,094. A video opened in two months counts in each.
   Two shares do not say whose they are. "by month" is offered under a chart by month. No so-what.
4. The first three videos are printed as a list and then again as cards. The so-what makes no offer.
   One Shorts bullet is filler next to the "it has faded" story.
5. The so-what is about saved entertainment episodes. Never-twice had removed the art side's saved tutorials.
   Say what the narrowing gap means for him: one side grew much faster than the other.
6. The day's items are printed as a list and again as cards: 6,390 px tall at 430 px.
   The bullet on which themes the day's few videos fell into is filler.
7. "One area led every year" hides that its share went from about 22% to nearly half, then to about 16%.
   The lead turns to how he watches (Shorts), where the question was what he watches.
8. The Shorts shift is said twice, in a bullet and in the so-what. A fall is said without its base.
   The top theme sits after two area names and reads as part of them; it belongs to a third.
   Nothing says what made that summer his, against the year around it.

### T1 to T15: what changed

| | What was wrong | Now | Status |
| --- | --- | --- | --- |
| T1 | A number next to the wrong thing passed | The writer names sheet paths; code fills them and checks binding, rank and amount words | Fixed in the final judge's rows. One contradiction in a follow-up |
| T2 | Length totals read as watch time | No total of length anywhere. Shorts against long, and the typical long video's minutes | Fixed |
| T3 | Leads were small slivers | Areas first (broad categories), then the themes inside. Field names not renamed | Partly: rows 1 and 8 are still lists of shares |
| T4 | Row 7 was a shift between slivers | Eras by area, what rose and fell, Shorts per year | Partly: misses the leader's share halving; a two-year change is still year by year |
| T5 | The so-what was "you saved N" | Code proposes candidates; the writer picks one; never twice in a row | Partly: none on rows 1 and 3, off topic on 5, a repeat on 8 |
| T6 | The export hint on answers | Gone from history answers; only the "I can't see" answer says it | Fixed |
| T7 | Filler passed the check | Repeats, names-only bullets, "new" over a year, the usual weekday are dropped | Partly: some filler remains on rows 4 and 6 |
| T8 | A topic's count too high | A theme counts only if 25% of its titles say the topic; said with "about" | Fixed. New: month bars sum above the lead |
| T9 | Row 5 did not name each side | The ratio in words, what is inside each side, the balance against last year | Fixed. Row 5 is useful |
| T10 | Row 6 said nothing only his record knows | Against his usual day: count, Shorts, busiest hour, new channels | Fixed. New: items printed twice |
| T11 | Row 2 did not say what each channel is | What most of the top 5 are, which are all Shorts | Partly: not yet what the ranking says about him |
| T12 | Chart labels wrapped at 430 px | Bars of 8 cells, labels cut at a word | Fixed (checked on real screenshots) |
| T13 | His page found no themes | Found by the library's real path or content; a status command; loud at start-up | Fixed here. Not yet seen on his Mac |
| T14 | Twice no reply for minutes | A 20-second deadline, then code's reply | Partly: bounded, never reproduced |
| T15 | Spanish row 7 was a run of counts | More Spanish tenses read as a change; eras in Spanish | Fixed. Spanish so-whats are saved items only |

### What was measured

The writer's eval: 20 made-up sheets, the same before and after (`eval_insight.py`).

| Run | Answers the question | Writer used | Observations kept | So-what said | Limits line | Run of counts |
| --- | --- | --- | --- | --- | --- | --- |
| `insight_v4`, code at ace4be2 | 17 of 20 | 19 | 53 | - | 0 | 0 |
| `insight_v5`, code at 2257352 | 18 | 19 | 52 | 5 | 0 | 0 |
| `insight_v5`, code at d7aa507 | 18 | 19 | 51 | 7 | 0 | 0 |

- The live eval runs cost $0.050 (v4) and $0.063 (v5). The second fixer ran only the 2 day sheets again ($0.006).
- A first v5 run answered 9 of 20. The binding rules were then tuned on its forms.
- The made-up sheets lack the new keys (areas, eras, the usual day). Real sheets give the writer more to say.

Planted falsehoods (made-up sheets):
- The older typed sentences: 89 of 89 false ones dropped, 43 of 43 true ones kept, at both fixes.
- The first fixer's path-form set: 31 of 31 false dropped, 13 of 13 true kept.
- The second fixer added 14 false and 6 true ones shaped like the real sheets. Before its fix, 0 of the 14 were caught.
- After it: 45 of 45 false dropped, 19 of 19 true kept.

Themes and topics (real library, counts only):
- The topic mapping eval: minecraft went from 8 themes to 5. The 3 left out had 0 to 16% of titles saying it.
- Its all-time count went from 13,902 to 8,220; 5,323 of them say it in their own words.
- gaming, art, math and blender mapped as before. The made-up library's 10 mappings were unchanged.
- The theme naming eval was not run: no theme was rebuilt and the naming prompt did not change.
- Field names read once: 15 of 19 are named, about 9 of the 15 are names a person would use. Not renamed.

Checks at d7aa507:
- Full suite, 4 shards: 5,175 passed, 0 failed (5,018 before the pass; 5,093 after the first fixer).
- Demo: 10 passed. Dry self-test: 67 conversations, 164 of 164 steps.
- `probe_same`: byte-equal with `same_head.json` (the final judge's capture, compared again for these notes).
- Dev phrasing set by code: 73 helper lines right, 1 wrong (d007), 1 of 40 none lines taken (d132). Unchanged.
- The 159 rule texts and 123 phrasings: taken by no new read. Round 11 and round 12 traps: not taken.
- Pictures at 430 px: every chart row on one line, on rows 1, 5 and 7, then 1 and 7 again.
- No reply of picks, recalls, summaries, asking videos, rules, emails, cancels or connectors changed.

Seconds and cost per answer (the final judge's live run):

| Answer | Seconds | Model calls | Cost |
| --- | --- | --- | --- |
| The 8 questions | 2.8 to 8.8 | 1 each | $0.0038 to $0.0059 each, $0.042 for all 8 |
| 3 history follow-ups | about 4 | 1 each | $0.0051 to $0.0060 each |

The "last 3 months" follow-up went to picks and cost $0.013.

### What changed on purpose in earlier tests

Each changed line is marked "round 12, pass 2" in place. The full list is in DESIGN 19.P2 and 19.P2 fix.
- No length total (T2): lines in `test_round12_w.py`, `test_round12_fix.py` and `test_round12_merge.py`.
- No export hint on a history answer with a window (T6): lines in `test_round12_w.py`, `test_round12_merge.py` and six round 11 files.
- The self-test step c40.1 moved the hint from "has" to "not" (T6).
- Bars of 8 cells (T12), "mostly" with a second share (T1), a comparison's ratio lead (T7, T9), a day's lead (T10).
- The history state may keep the so-what said (T5).
- `test_round12_pass2.py` T11: the channels line is said by code, whatever the writer chose.
- `eval/insight_cases.json`: 13 sentences moved from true to planted (T2, T7); the v5 sets added.
- These notes changed no test.

### Still wrong or unproven

- Rows 1 and 8 still read as lists of shares. They do not say what he is drifting toward.
- The so-what is still uneven: none on rows 1 and 3, off topic on row 5, said twice on row 8.
- Never-twice can push the best so-what out of the next answer and leave a weak one.
- A day's or a first's items are printed as a list and then as cards. On a phone that doubles the length.
- Row 7 hides the leading area's rise and fall behind "led every year".
- A change between two years is still told year by year, with volume bars.
- "what have i been into the last 3 months" is not read as a history question.
- One garbled phrase ("1 points") and one contradiction (Shorts in a without-Shorts answer) passed the check.
- Each judge round found false or garbled sentences the check let through. The check catches what it was built for.
- The same question asked twice can lead differently.
- The writer is measured on 20 made-up sheets, not on real ones.
- Theme and field names are not confirmed by him. Field names were not renamed.
- The builds were never run on his Mac. T13 is fixed here, not seen there.
- The long wait of T14 was never reproduced; it is only bounded by the deadline.
- Spanish so-whats and most code-written lines are English only. iMessage was not seen.

### Spend of the pass

- Ledger: $23.31 before the pass, $24.22 after. This pass: about $0.91.
- First fixer $0.36, the two judges about $0.21, second fixer $0.26, final judge about $0.08.
- These notes made no model call.
- The cap is $30: $5.78 is left, $1.38 under the $25.60 ceiling for this pass.

## The third pass

22 Nov 2026. Code at dd2b1b0. The design is DESIGN 19.P3 and 19.P3 fix.
The pass's scope (U1 to U10) and the judges' notes are kept outside git.
No titles, channel, theme or field names of the real library appear here. Counts are fine.

### What it was for

The second pass's final judge, on d7aa507, gave 5 useful and 3 partly (rows 1, 2, 8), with 6 of 8 half slop.
The orchestrator typed all 8 on the founder's page and listed ten things still wrong, U1 to U10.
- A word of direction with no number could be false and still pass the check.
- "what have i been into lately" went to picks: one video, his own row 8 complaint.
- Facts were said twice, and a day's items were printed twice (6,400 px tall on a phone).
- The so-what was off topic or missing. Offers named things the answer never showed.
- Row 7 hid the leading area's rise and fall. Row 8 did not say what set that summer apart.

How it was built:
- A first fixer, code at a0e0010: U1 to U10, 99 tests. The prompt did not change (`insight_v5`).
- Two judges read it live. A graded as the founder. B recounted every claim.
- A second fixer, code at dd2b1b0: the must-fixes of both judges, 28 tests, each failing on a0e0010.
- A final judge read dd2b1b0 live on the real library, as the founder would.

### Grades, row by row

The judges are not the founder. They read the live answers on the real library as he would.

| # | Question | Founder, before (1f9cde0) | Pass 2, final judge (d7aa507) | Pass 3, judge A (a0e0010) | Pass 3, final judge (dd2b1b0) |
| --- | --- | --- | --- | --- | --- |
| 1 | what have i been watching the most lately | Partly, slop | Partly, half slop | Partly, half slop | Useful, not slop |
| 2 | which channels did i watch the most in 2025 | Partly, slop | Partly, half slop | Partly, half slop | Useful, half slop |
| 3 | how many minecraft videos did i watch this year | Useful, not slop | Useful, not slop | Useful, not slop | Useful, half slop |
| 4 | when did i first start watching blender videos | Partly, not slop | Useful, half slop | Useful, not slop | Useful, not slop |
| 5 | did i watch more gaming or more art videos this year | Not useful, slop | Useful, half slop | Useful, not slop | Useful, not slop |
| 6 | what did i watch on october 30 | Partly, half slop | Useful, half slop | Partly, half slop | Useful, half slop |
| 7 | how has what i watch changed since 2020 | Not useful, slop | Useful, not slop | Useful | Useful, half slop |
| 8 | what was i into in the summer of 2023 | Not useful, slop | Partly, half slop | Partly | Partly, half slop |

- Founder, before: 1 useful, 4 partly, 3 not useful. 5 of 8 slop.
- First pass, last judge (ace4be2): 3 useful, 5 partly. 6 of 8 half slop.
- Second pass, final judge (d7aa507): 5 useful, 3 partly. 6 of 8 half slop.
- Third pass, judge A (a0e0010): 4 useful, 4 partly. Its slop marks for rows 7 and 8 did not reach these notes.
- Third pass, judge B gave no grades. It found a topic's Shorts share said as a share of all his YouTube videos.
- Third pass, final judge (dd2b1b0): 7 useful, 1 partly, 0 not useful. 3 not slop, 5 half slop.
- The final judge said rows 1 to 7 answer the question asked. Row 8 does not quite.
- Every number it recounted in the 8 rows was true. One follow-up held a false sentence (below).

Four follow-ups the final judge typed after the 8:
- "most watched channels in math" (his own wish): not right. One sentence is false as worded.
- It says a topic's Shorts were 22% of "your YouTube videos". They are 22% of that topic's videos.
- The same answer's first bullet repeats the lead's three channels.
- "without shorts" after it: right. Nothing about Shorts is said, and the chart drops them.
- But its lead repeats the previous lead word for word, and one bullet skips the second channel.
- "what have i been into the last 3 months": right. Read as history, not a pick (U2 holds).
- It covers the last 90 days the record holds, against the 90 days before. No so-what.
- "how did my watching change from 2023 to 2025": right. Told by areas, not a timeline of counts.
- Every share in it recounted true (U1 holds). No so-what.

### What the final judge still wants, by row

1. Nothing. It leads with the change and ends with what fell, with a step to take.
2. The so-what offers saved videos on one theme but never ties them to the channel it names.
   The text says "top 5" over a chart of 8 bars.
3. The lead and a bullet say the same two themes. The so-what is one more share, not a step.
   A 10-row month chart is long on a phone.
4. Nothing. It does not say what kind of videos the topic was, and the fade comes only after the cards.
5. Nothing. It has no so-what, which the judge called honest: nothing fitting was found.
6. Do not offer "only <theme>" when that theme is 3 of the day's 10 videos.
7. Drop or ground one stray theme bullet (no share, no change, "was driven by" grammar).
   The so-what should offer something code can do. The lead is one long dense sentence.
8. Lead with what he was into that summer (what peaked or was new), with the move to Shorts second.
   The leading area is said twice, and Shorts twice. Drop the "little else set it apart" bullet. No so-what.

### U1 to U10: what changed

| | What was wrong | Now | Status |
| --- | --- | --- | --- |
| U1 | A word of direction with no number passed unchecked | Each word of direction or comparison needs a path whose two values support it, else the sentence goes. A change between two years is told by areas | Fixed. 15 new planted cases: 9 caught before, 15 after |
| U2 | "what have i been into lately" went to picks | Read as the history "top" answer over the window, where the library has a watch history and themes | Fixed. "saving lately" goes where it went |
| U3 | Shorts named inside a "without Shorts" answer; lead and chart at two levels | Nothing about Shorts with Shorts left out; the chart follows the level the answer names | Fixed in the final judge's follow-up |
| U4 | Repeats; items printed as a list and again as cards | Two sentences on the same facts: the first stands. Lists are an overview, then cards with one caption line. Row 6 about 2,900 px tall, from 6,400 | Partly: a fact said again in other words still passes (rows 3, 8, and a repeated lead) |
| U5 | The so-what off topic or missing | Tied to the question's subject; none rather than an unrelated one. "The most lately" says what moved, with a step | Partly: rows 3 and 7 give a statistic, row 2's is not tied to its channel, rows 5 and 8 have none |
| U6 | Offers of things never shown | Only what the answer, bullets, chart or so-what showed; never "by month" under a month chart | Partly: row 6 offers a theme of 3 videos |
| U7 | A move with no base; "1 points" | Every change with its direction, both values and its base in his words; "1 point" | Fixed. New: two theme bullets with "was led by" grammar |
| U8 | Rows 7, 8 and 2 about the wrong thing | Row 7: the leading area's weight over the years and the year of the turn. Row 8: what set the season apart. Row 2: clip channels he grazed against long-form ones he kept coming back to | Partly: rows 7 and 2 fixed; row 8 leads with how he watched, not what |
| U9 | Month bars summed above the count; "N% were Shorts" of whom | A caption says what the bars count; the Shorts share names whose | Partly: row 3 fixed; one topic answer still says its Shorts share as of all his videos |
| U10 | The daily cap silently stopped the writer | README step 4 shows the setting; the trace says "daily cap reached" | Fixed. Not yet seen by him |

In all: 5 fixed (U1, U2, U3, U7, U10), 5 partly (U4, U5, U6, U8, U9), 0 not done.

What the second fixer changed after judge A and judge B, in short:
- Row 1 leads with the area that moved most; what fell is the so-what, with "only <area>" as its step.
- Asked again right after itself, row 1 keeps the same lead and repeats nothing.
- One fall is never said at two levels. A span's dates are said once.
- "The last 3 months" covers the last 90 days the record holds, against the 90 days before.
- A day's leader is a count. The export's last day is never set against a usual day.
- Row 4 says what its Shorts and long split is of, and its fade names its subject and the part of the year.
- Row 5's chart has four bars: each side this year and in the same part of last year.
- Row 2 leads in words, and the chart carries the counts. Both filters are said after two follow-ups.

### What was measured

The writer's eval: the same 20 made-up sheets, rescored from the saved `insight_v5` forms (no model call).

| Code | Answers the question | Writer used | Observations kept | So-what said | Limits line | Run of counts |
| --- | --- | --- | --- | --- | --- | --- |
| a490cdd (before the pass) | 18 of 20 | 19 | 51 | 7 | 0 | 0 |
| a0e0010 (first fixer) | 19 | 20 | 52 | 6 | 0 | 0 |
| dd2b1b0 (second fixer) | 19 | 20 | 52 | 6 | 0 | 0 |

- One so-what fewer is on purpose: a Shorts shift under a channels answer is no longer said (U5).
- Each fixer's own rules regressed this eval on the way. Each regression was found by the rescore and fixed.
- The prompt did not change, so no new live eval run was needed.

Planted falsehoods (made-up sheets):
- The older typed sentences: 89 of 89 false dropped, 43 of 43 true kept, before and after.
- The path-form set: 60 of 60 false dropped, 27 of 27 true kept (45 and 19 before the new case).
- The new case: 15 false directions with no number, 8 true ones. At a490cdd 9 of the 15 were caught; now 15.
- All 8 true ones are kept, before and after.

Themes and topics: no theme was rebuilt, and no naming prompt or topic mapping changed.
So the naming eval and the topic mapping eval were not due.

Checks at dd2b1b0 (run by the final judge):
- Full suite, 4 shards: 5,301 passed, 0 failed (5,175 before the pass; 5,273 after the first fixer).
- Demo: 10 passed. Dry self-test: 67 conversations, 164 of 164 steps.
- `probe_same`: byte-equal with `same_head.json`.
- Dev phrasing set by code: 73 helper lines right, 1 wrong (d007), 1 of 40 none lines taken (d132). Unchanged.
- The 159 rule texts and 123 phrasings: taken by no new read. Round 11 and round 12 traps: not taken.
- Two trap lines changed on purpose (U2, below).
- Row 6 at 430 px: about 2,900 px tall (6,400 before the pass). Row 4: about 1,400 px, every item once.
- No reply of picks, recalls, summaries, asking videos, rules, emails, cancels or connectors changed.

Seconds and cost per answer (the final judge's live run):

| Answer | The writer's call | At the page | Model calls | Cost |
| --- | --- | --- | --- | --- |
| The 8 questions | 2.4 to 5.6 s | 9 to 13 s | 1 each | $0.0040 to $0.0062 each, $0.042 for all 8 |
| 4 follow-ups | - | 10 to 11 s | 1 each | $0.0045 to $0.0054 each |

### What changed on purpose in earlier tests

The full list, with each line, is in DESIGN 19.P3 and 19.P3 fix.
- Two traps changed (U2): "what have i been into lately" left the round 12 D trap list.
- In the round 11 trap list it became "what have i been saving lately".
- A first's parts are the overview, then a caption line and a card per item (U4): `test_round12_w.py`, `test_round12_merge.py`.
- The self-test step c62.1 reads the caption line in place of the numbered title (U4).
- `test_round12_pass2_fix.py`: the saved order without the new "moving" candidate (U5).
- In it too: "leaned less on Shorts" may go as an unbound direction (U1); the change's so-what no longer says what grew.
- The second fixer: row 1's lead and so-what and row 7's turn year (`test_round12_pass3.py`).
- A top answer over 4 weeks leads with the move; a count without "about" (`test_round12_pass2.py`, `_pass2_fix.py`).
- The export's last day is not set against a usual day (the same two files).
- A first's path names its subject and part of the year; a channels lead in words (`test_round12_fix.py`).
- Both filters said after "without Shorts" then "only X" (`test_round12_merge.py`).
- `eval/insight_cases.json`: the v5 set gets the direction case.
- These notes changed no test.

### Still wrong or unproven

- Row 8 leads with how he watched (the move to Shorts), not what he was into that summer.
- One false sentence passed in a follow-up: a topic's Shorts share said as of all his YouTube videos.
- The second fixer had fixed one wording of it; a count with "made up" still gets through.
- A fact said again in other words passes the repeat rule (rows 3 and 8, a repeated lead after "without shorts").
- Some so-whats are one more share, with no step (rows 3, 7). Row 2's is not tied to its channel.
- Two theme bullets have bad grammar ("<themes> was led by", "was driven by").
- Row 6 is still mostly what anyone could look up. Its offer of a theme of 3 videos is pointless.
- The writer's own bullets vary from run to run.
- The writer is measured on 20 made-up sheets. Real sheets were replayed offline but not scored as an eval.
- Theme and field names are not confirmed by him. The builds were never run on his Mac. iMessage was not seen.
- Spanish so-whats are saved items only. Most code-written lines are English only.

### Spend of the pass

- Ledger: $24.26 before the pass, $24.89 after. This pass: $0.63.
- First fixer $0.14, the two judges $0.21, second fixer $0.20, final judge $0.07.
- These notes made no model call.
- The whole round: about $2.52. The cap is $30: $5.11 is left, $0.51 under the $25.40 ceiling for this pass.
