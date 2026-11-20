# Round 11, MVP version 6: ask your watch history anything (counts only)

19 Nov 2026. Branch `experiments/search-loop`, code at 0a72c66. The design is `experiments/mvp/DESIGN.md` section 18.
Updated 20 Nov: a live check of 02f3581 found 15 things, and a fix pass followed (code at 0484b0e). See the part
"The live check and its fixes". A second live check of 25a1189 found 6 more (P1 to P6). A second fix pass and its
check followed (code at c26c85f). See the last part, "The second live check and its fixes". The parts before those
describe version 6 as first built.
The round's brief and every conversation from live runs are kept outside git. No titles, channels or names appear here.

The founder's watch record: 149,801 dated events, 108,997 watched videos in all (108,685 on YouTube, 312 on
Instagram). The YouTube export ends on 30 October 2026, Instagram's on 15 October 2026.

## What was asked (19 Nov), and how it was built

The founder wrote: "i also think it would be beneficial to treat it like 'ask your watch history anything'". He sent a
screenshot of another project. It searches 1,000+ stored YouTube transcripts and answers with timestamps.

It was built as three slices, one merge and one independent check:
- H: questions about the watch history, answered by code.
- M: a summary across many items.
- Q: asking one YouTube video itself, with timestamps. Off by default.

Amendment A-017 records slice Q. It is Proposed and needs both founders. Nothing in `docs/` changed except that entry.

Two new prompts are in use: `synth_v3` (slice M, after `synth_v1` and `synth_v2`) and `video_ask_v1` (slice Q). Each ran its own evaluation before and after.
Slice H adds no prompt and makes no model call.

## The probe: eight messages, before and after

Before is the orchestrator's live probe of 84a413a. After is the check's live run after the merge, plus each slice's
own live run. Topic words are written as X.

| # | Message | Before (84a413a) | After (version 6) |
| --- | --- | --- | --- |
| H1 | "what have i been watching the most this month" | All-time totals. It searched "watching", "most" and "this month" | By code. The window said back, where the export ends, the latest month's channel ranking and topics |
| H2 | "what did i watch last week" | "nothing you kept since ..." and no word of the export's end | By code. It says it can't see last week, gives the last 7 days it can, and how to refresh |
| H3 | "which channels do i watch the most" | Totals, no ranking | By code. A channel ranking with counts |
| H4 | "how many videos about X have i watched" | Right count, but "kept" for watched | By code. "watched", with the count |
| H5 | "what was that video i watched about X" | The right kind of video, with its card | Unchanged path. Live it brought a saved Instagram post, phrased "I recommend ..., which you saved" |
| H6 | "what did that video say about X" | The honest "I can't tell that from what <title> says" | Setting off: the same line. Live, with it on, H6 landed on that Instagram post, so no offer was made |
| H7 | "summarize what ive learned about X from what i watched" | One recommended post, two bare links | A real summary: 5 points from 3 items, with an "ask video N" offer |
| H8 | "when did i first start watching X videos" | The picks, with one unrelated video | By code. The date and the first three with cards. The first is a talk-show clip whose title says X |

H1 to H4 and H8 now cost nothing and take 0.1 to 2.8 seconds. H8 is right by its words only. H5 is not fixed.
H6 can be answered only for a YouTube pick with the setting on; live, it never reached one.

## What each slice does, and what was measured

### H: history questions answered by code (`history.py`)

Code reads a history question into a small form. It counts from every dated event, in the person's time zone. Fixed
English or Spanish texts say the answer.

- Kinds: top channels, top topics, most rewatched, count, list, a day, first, last, timeline, compare.
- Every answer says its window back with dates. It says where the export ends when the window reaches it.
- A window after the record says so and answers for the latest stretch of the same length.
- A window before the record says where the history starts. It never says "you watched none".
- Friends' posts are never counted. A like is never called a watch. Hours are not counted.
- Follow-ups work for 6 hours: another window, a platform, a new topic, "show me them", "more", "the first one".
- A rule like "send me my top channels every month" is declined plainly, with today's answer once.

| Measured | Result |
| --- | --- |
| The builder's 60 made-up questions and 40 traps | 58 of 60 taken (the other 2 are saves, by design). 0 of 40 traps |
| Numbers on the real library against an independent count | Every number checked matched |
| Live, H1 to H4 and H8 | By code, no model call, $0 |
| Tests | 40 in `tests/test_round11_h.py` |

### M: summaries across many items (`synth.py`, prompt `synth_v3`)

Code reads "summarize what I've learned about X" and its kin. It retrieves 40 candidates and keeps those whose own text
names the topic. It reads up to 12 of them, then makes one summary call.

Code checks every point. Each must quote a cited item's own words, and its numbers must be in that text. A point that
fails is dropped. The reply gives up to 6 points, each with its sources and links. It also says how many items fit and
how many say nothing.

The made-up evaluation, 12 requests, live:

| Run | Points | Items cited | Not truly fitting | Answers citing 3+ items | Cost per answer |
| --- | --- | --- | --- | --- | --- |
| Before (84a413a) | 42 | 13 | 1 | 1 of 12 | $0.011 |
| After (`synth_v3`, final) | 64 | 41 | 0 | 12 of 12 | $0.008 |

Every point shown is traceable by code in both runs. For "after" that is true by construction, since the same test
drops points.

On the real library, 6 requests on the profile's 6 topics were all taken. Each answer had 4 to 6 points and cited 4 to
7 items. Each cost $0.013 to $0.023 and took 6 to 7 seconds (30 to 44 for a run's first). 71 tests.

### Q: asking the video itself (`videoask.py`, prompt `video_ask_v1`; A-017, Proposed)

Off unless `MVP_VIDEO_ASK=1`. Google's documentation says the Gemini API takes a public YouTube link as input. The
feature is in Preview there.

- After the honest can't-tell line about a YouTube pick, the bot offers "ask the video".
- The link and the question go to Gemini. Nothing else about the video goes with them.
- The reply has up to 5 points, each with a time and a link to that second.
- It is labelled "From the video (not checked against its text)".
- Code drops a point with a time outside the video, a point naming another video, or one that reads like an order.
- Kept: the points, their times, the video id and the ledger row. No transcript, audio, video or frame.
- Caps before the call: 20 minutes per video, 5 questions a day, and a worst-case cost against both caps.

Live on 8 public videos of 2 to 8 minutes:

| Run | Answered from the video | Timestamps inside the video | Cost | Seconds per answer |
| --- | --- | --- | --- | --- |
| Before (setting off) | 0 of 8 | - | $0 | - |
| After | 7 of 8, 25 points; the control said it doesn't cover that, which is right | 25 of 25 | $0.061 | 5 to 10 |

Each answer was read against its video's own description. None contradicted one. In 4 of 7 the description confirms something the answer says.
Nobody watched the videos. 64 tests.

### The merge

- One hook order: the history read, then asking a video, then the older code reads, then the summary, then the model.
- A summary can take one time window, using slice H's words. It says the window and the export's end back.
- A summary offers "ask video N" only with the setting on and a YouTube video among its items.
- "The first one" from a history answer puts that video in view, so it can be asked.
- "What did you do for me", "export my data" and "delete my data" cover everything this round keeps.
- The framing: the help, "what can you do" and the setup's last message now lead with "Ask your watch history
  anything". They give the person's counts and three example questions from their own record. Code checks each
  example is one it answers.

36 tests, and 11 new made-up self-test conversations (c40 to c50). Live: the help by code in 2.5 s. A summary inside a
month window cost $0.014 in 7 s.

## Checks

| Check | What ran | Result |
| --- | --- | --- |
| Offline tests | `experiments/mvp/tests`, in 4 shards | 3,718 pass, 0 fail (3,318 at version 5). The demo's 10 pass |
| Dry self-test | 51 conversations, made-up library, no model | 136 of 136 steps |
| Probe of unchanged answers | `probe_same` against round 8's saved bytes | Byte-equal |
| Development wording set | 100 helper lines, 40 "none" lines | 73 right, 1 wrong, as before. 1 "none" line now taken on purpose (below) |
| Rule texts and phrasings | 159 rule texts, 123 rule phrasings | Taken by no new read |
| 95 new made-up history messages | 83 English with typos, 12 Spanish | 86 right at the merge, 95 after the check's fixes. 0 wrong, 0 to the model |
| 60 traps | Picks, rules, reminders, cancels and others that mention watching | Byte-equal with 84a413a, at the merge and after |
| 30 chat messages after a history answer | "ok thanks", "for real?", "y tu?" | 16 of 30 taken as a new topic at the merge, 0 after |
| 22 window edges | Ranges, "2 weeks ago", weekends, leap day | 5 wrong at the merge, 0 after |
| Real-library numbers | 27 history answers against a script that imports nothing of the bot | All matched after one fix ("halloween 2025" had dropped its year) |
| Bad summary answers | 40 runs of a fake model with unsourced, misplaced and injected points | Every bad point dropped. Nothing made or left waiting. Called directly, the check had kept a caption's order (fixed) |
| Asking a video, attacks | Orders in new words, wrong times, long answers, errors, caps | One defect fixed: a point naming another library video was passed on |
| Live check | H1 to H8 and 5 more, as the page operator, setting on | Results are in the probe table above. $0.060 |

The one "none" line taken on purpose is d132, "what did i watch on youtube last week". It is the brief's H2 with a
platform. The founder decides whether it stands.

The time zone matters. In UTC, October 2026 would count 1,486 watches; in the person's time zone it is 1,484.

## What was not built, and why

| Not built | Why |
| --- | --- |
| Searching what every video says, as in the screenshot | It needs stored transcripts and their embeddings. AGENTS rule 8 and the 15 Oct decision forbid that. No official route gives other people's transcripts |
| A history rule sent on a schedule | It needs a new content source in the data contract, so an amendment. It is declined plainly |
| Hours or minutes watched | Only videos are counted; the answer says so |
| Asking an Instagram post itself | Instagram has no such route |
| Asking a video in Spanish, Spanish summaries, Spanish examples in the help | English only this round. History answers do have Spanish |
| A summary over two windows ("compared with ...") | One window only |
| A held-out summary set | The prompts were tuned on one made-up set |

## What is still wrong or unproven

History:
- Topics are matched by their words in titles and captions, not by the search engine's ranking. Live H8's first item
  shows this.
- Spanish topic words match only Spanish titles.
- "what topics do I watch the most" needs the profile's topics. A fresh person gets the channel ranking instead.
- "what is my busiest year", with no word about watching, depends on the model sending it to the history answer.
- "what did I save this month" stays on the older recent-saves answer, on purpose (a rule-eval text).
- The history read does not try the tidied forms of a message; it fixes its own typos.
- When Instagram is in scope, answers end with a longer tail of export, refresh and friends lines.
- Instagram watches exist only for the last 12 days of its export.

Recall and summaries:
- A recall question ("what was that video i watched about X") is still answered as a recommendation. It can bring a
  saved post (live H5).
- On the real library many summary points are thin: grounded, but not deep. Titles and captions hold little.
- A summary topic holding the word "settings" is refused by the summary read, as a word about the bot.

Asking a video:
- Nobody has checked an answer against the video itself. Code checks only that times lie inside the video.
- Its legal footing is unsettled: Preview, YouTube's "personal, non-commercial use", and Google's "necessary rights"
  clause.
- The key must be on a billed Google project. Code cannot check that.
- The offer after the can't-tell line has not run live. Live H6 landed on an Instagram post.
- With no offer shown first, the first ask needs "ask the video" twice, because of the first-time note.
- Gemini's points come in its own casing; one live answer started in lower case.
- The offer follows only a can't-tell line about one pick, not several.
- "email it to me" after a video answer emails the earlier picks, not the video's points.
- A point that happens to repeat a short title of another library video can be left out.
- Only real 11-character YouTube ids get the offer, so slices H and M's made-up tests never see it.

Process:
- The held-out wording set and the 20 draft requests were not run this round.
- Slice Q's live run went through the hook with a last answer set by code. The check's live run asked one video from a real history answer.

## What the founder must do

1. Pull the branch and restart the test page. Type "what can you do" and check it leads with your watch history.
2. Refresh your exports: YouTube ends on 30 Oct and Instagram on 15 Oct. Ask "how do I send you a new export?".
3. To try asking a video: set `MVP_VIDEO_ASK=1` and `GEMINI_API_KEY` from a billed Google project. Ask a YouTube pick
   a question, then say "ask the video".
4. Decide A-017 with the other founder. Its own assessment asks first for a legal read and 20+ answers checked
   against the videos.
5. Decide whether d132, a "none" line of the wording set, should be answered by the history code.
6. Decide whether a history rule on a schedule is wanted. It would need a data-contract amendment.
7. Still open from version 5: A-008 to A-016.

## Spend

| Work | Spend |
| --- | --- |
| The orchestrator's live probe of 84a413a | $0.054 |
| Slice H | $0.010 |
| Slice M (six evaluation runs and the real-library run) | about $0.69 |
| Slice Q (8 live questions) | $0.061 |
| The merge's live run | $0.017 |
| The check's live run | $0.060 |
| **Round 11** | **$0.89 of its $3.00 budget** |

The ledger (`data/mvp/ai_runs.jsonl`, sum of cost over 7,410 rows) reads **$20.61 of the $30 cap**. $9.39 is left.
Slice M's figure is the ledger's rise between the probe and slice H's run.

## Size

About 47,600 lines of Python and about 40,400 lines of tests in `experiments/mvp`.

## The live check and its fixes (19 to 20 Nov)

After version 6 (build 02f3581), the orchestrator used the test page as the founder would. It ran on his library with
`MVP_VIDEO_ASK=1`. It found 15 things: R1 to R8 on history answers, S1 to S3 on summaries, V1 to V4 on asking videos.
Two fixers worked in parallel: A on history answers, B on summaries and videos. A merge joined them, then an independent
check ran. The code is at 0484b0e. The design is `mvp/DESIGN.md` 18.L, 18.LA, 18.LB and "18.L check".

What already read right was left alone: the month and week windows with both export ends, the channel ranking, counts
by topic and year, a day's list, and the help leading with the watch history. Topic words are written as X.

### The findings, before and after

| # | Before (02f3581, live) | After the fix pass | Measured |
| --- | --- | --- | --- |
| R1 | "what was that video i watched about X" got "I recommend <a saved post> ... because ..." | A recall by code: up to 3 watched videos, YouTube first, each "You watched it on <day>." with its card. No "I recommend". If nothing watched fits, it says so and offers the saved one | 30 of 30 made-up recalls by code, 0 of 31 traps. Live: 2 watched videos with their days and cards |
| R2 | On an Instagram post, "ask the video" got "I can only ask YouTube videos." twice | The plain line, then the watched YouTube video on the same topic and "ask that one" | 10 of 12 real saved posts got a watched video on their topic; 2 got one that only shares a word |
| R3 | The first item of "when did i first start watching X videos" was a talk-show clip whose title holds the word | First, last and list keep only items that fit by the library's own item vectors. They say "about" and how many were left out. Counts and timelines keep "mention" | See below. 0.2 s a topic, no model call |
| R4 | The friends line and the all-time range on every answer | Each once in 6 hours. The export-end line stays whenever a window reaches an end | Check: the end line in answers 1 to 10 in a row, after a restart, and for a second person |
| R5 | "...: 10,546 fewer in 2024." | "More in 2025: 24,004 videos, against 13,458 in 2024 (10,546 more)." | Tests; the real counts match an independent script |
| R6 | A timeline with 4 leading years of 0 | It starts at the first year or month with a count and says "None before <when>." | Tests; the first year matches |
| R7 | "(6,884 channels in all)", mostly Instagram accounts | "accounts and channels"; "accounts" for Instagram alone | Tests |
| R8 | After a list of watched reels, "ask the video" got "I haven't shown you a YouTube video" | The honest Instagram line and the latest watched YouTube video on the topic | Tests; live in the check. "the last X reel" was read as any video until the check fixed it |
| S1 | Sources had no numbers, so "ask video N" was unclear; video 1 was an Instagram post | Points end with their source numbers, like [1, 3]. One Sources list. "ask video N" uses the number shown. Only YouTube is offered | Tests; the check: the number shown is the video asked |
| S2 | "from what i watched": 3 of 5 points from one saved post; the lead said "kept" | Watched, saved or liked only when the person says so. The lead says what was read. At most 2 points from one item when 3 or more are cited | The check: no saved-only item reached any model call |
| S3 | 5 points only described the videos | New prompt `synth_v5` and code checks drop points that only say what an item is. Under 2 left: a plain line, the best 3, the offer | See the evaluation below |
| V1 | No way to ask several videos | "ask them" asks up to 3 videos, each through the single-video ask with its own checks and caps | Live: 3 videos in 21.5 s; a recall then "ask them", 2 videos in 15.5 s |
| V2 | The first ask needed "ask the video" twice | The note ends 'Say "yes" to go ahead.' and "yes" asks. No note when the consent already named Google | Tests; self-test |
| V3 | Points in lower case | A capital, by code | Tests |
| V4 | "email it to me" after a video answer emailed the earlier picks | It emails the video answer | Tests; the self-test reads the email's subject and points |

R3 is only partly fixed. Two readings on the real library, counts only:

| Reading | Before | After |
| --- | --- | --- |
| Fixer A: first 5 items shown, 10 topics | 39 of 50 fit the topic | 41 of 50 |
| The check: last 3 and first 2 shown, 8 topics | 26 of 38 | 26 of 37 |

The talk-show clip is gone. Two topics got better and one got worse in the check's reading. A word used mostly for
something else in the record still fails (0 of 5 before and after for one topic).

### The summary prompt's evaluation (S3)

Slice M's 12 made-up requests, plus 5 new made-up topics whose items only say what they are. Live, before and after.

| Run | 12 requests: points, items cited, citing 3+, outside the fit | 5 "what it is" topics: points shown | Cost |
| --- | --- | --- | --- |
| Before (`synth_v3`) | 66, 40, 12 of 12, 0 | 11 (10 only say what the items are) | $0.129 |
| First try (`synth_v4`, limit on) | 55, 37, 7 of 12, 4 | 4 | $0.125 |
| Final (`synth_v5`, limit off) | 62, 41, 12 of 12, 0 | 2 (1 real; the other dropped by a later code check) | $0.118 |

Slice M's bar was 64 points, 12 of 12 citing 3 or more, 0 outside the fit. The 2 points fewer come from the new rule
of at most 2 points from one item (65 without it). With the S2 limit on, the 5 requests that say "watched" or "my
saves" cite 2 items each. The made-up set holds only 2 or 3 such items. That is by design.

### Where the fixes meet (the merge)

- B's offer reaches A's function for the best watched video. If the request's words fit no watched title, the post's caption is tried.
- "ask them" after a recall asks the recall's own list, up to 3. With no question, it asks about the recall's topic.
- A watched-only summary uses A's record of watches and A's fit.
- The hint to send a new export is said once in 6 hours, shared with history answers. Where an export ends is always said.
- The hook order in DESIGN section 17 and in the code now names the new reads.
- "what did you do for me", "export my data" and "delete my data" cover what "ask them" keeps.
- The help has one line for "ask them", only with the setting on.
- Two bugs in A's code were fixed: a two-word topic cut to one word, and a lost line when the fit left one item.

### The check of the fix pass

- 70 new made-up messages (typos, 8 in Spanish), setting on: 64 right, 0 wrong, 6 left to the model.
- Setting off: 54 right and 5 to the model, of the 59 that need no video.
- Read one by one, 1 more reply was wrong in what it said: "how many reels have i liked" counted YouTube likes. Fixed.
- 50 traps against 02f3581, byte for byte, setting off and on: 0 differ except the build line and the help's new line.
- 10 more chat messages after a history answer: 0 differ.
- 12 numbers on the real library, by a script that imports nothing of the bot: 11 match.
- The 12th is 113 against 108. That is the word-boundary difference known since slice H.
- Defects found and fixed, 9 kinds. The main one: after a recall, "summarize what i watched this month about X" got the
  recall's key points. "this" in "this month" was read as the item in view.
- Also fixed: a summary with a window skipped A's fit; a repeated point in one video's answer; a tie in a timeline
  named a "most"; and some singular wording.

Live, as the page operator on the real library, setting on ($0.13). Read as the founder would:
- Right: the recall; the honest line, the offer, then the video asked at once; the first X video by the fit, a recipe.
- Right: the range and friends line once; the comparison first; reels liked counted on Instagram only.
- Thin: a watched-only summary was grounded, but only 2 of its 5 points teach something.
- Thin: "ask them" after the plain line asked the summary's question. One video's points were about its own subject.
- Wrong: a summary listed a clip whose title only uses a form of the topic word as slang.

### Checks that stay true

| Check | Result |
| --- | --- |
| Offline tests, in 4 shards | 4,300 pass, 0 fail (3,718 at 02f3581). 582 new: fix A 93, fix B 135, merge 25 (one of them in slice Q's file), check 329 |
| Demo tests | 10 pass |
| Dry self-test | 59 conversations, 152 of 152 steps (51 and 136 before). c51 to c58 are new |
| Unchanged answers (`probe_same`) | Byte-equal |
| Development wording set by code, setting off and on | 73 helper lines right, 1 wrong (d007). 1 of 40 "none" lines taken (d132, on purpose) |
| 159 rule texts and 123 phrasings | Taken by no new read |
| The 60 traps of the round 11 check | Still not taken |

Tests changed on purpose are listed in DESIGN 18.LA, 18.L and "18.L check". They follow R5, R6, R7, R1, the new
offer on an Instagram pick, and one singular wording.

### What is still wrong or unproven after the fix pass

History and recall:
- The fit uses title and caption vectors. It cannot tell a topic word used another way, such as a gaming video titled after it.
- For a topic whose matches are mostly saved posts, the fit can drop watched videos truly about it (2 of 4 for one topic).
- Its two settings come from small readings on the real library, not from a tuned evaluation.
- Recall is English only. Spanish topic words still match only Spanish titles.
- A recall by a description that shares no word with the title only finds what the search's top 50 holds.
- "what was that video about X", with no "i watched", is left to the model on purpose.
- The first recall waits for the search engine to load: 24 to 38 s live.
- 6 of the check's 70 messages still reach the model, among them "remind me what that video i watched about X was".
- A Spanish comparison without a question mark still goes to the model.

Summaries:
- On the real library, summaries are honest but thin. Titles and descriptions hold little.
- A vague point that names the thing and traces to the text still passes. Code cannot tell it teaches nothing.
- The checks that a point answers the question work only for "X in Y" questions.
- The summary's word match treats a slang form of a word as the topic. Not fixed.
- The fit inside a summary was not measured on the real library.
- The prompts have no held-out set. They were tuned on one made-up set.

Asking videos:
- Nobody has checked an answer against the video itself. Of 7 points read against descriptions, 1 was supported, 0 contradicted.
- "ask the video" with no question after a recall still asks what to ask. "ask them" uses the recall's topic.
- "ask them" with nothing shown goes to the model.
- The legal footing of A-017 is unsettled. The key must be on a billed Google project; code cannot check that.

From version 6 and now fixed: the recall, the offer after the can't-tell line (now run live), the double "ask the
video", lower-case points, the email of a video answer, the tail of footer lines, and asking several videos.

### What the founder must decide or do now

1. Pull the branch and restart the test page. Try "what was that video i watched about X".
2. With `MVP_VIDEO_ASK=1` and a key on a billed Google project, say "ask them" after a recall or a summary.
3. Decide the recall's order: watched first, a save only when nothing watched fits.
4. Decide the "about" wording: keep it where the fit is weak, or say "mention" there.
5. Confirm the summary rule: "from what i watched" reads only watched items, "from my saves" only saves, neither reads everything.
6. Decide A-017 with the other founder. It now covers up to 3 videos per question, each counted against the daily cap.
7. The rest stands: refresh the exports, d132, a history rule on a schedule, A-008 to A-016.

### Spend of the fix pass

| Work | Spend |
| --- | --- |
| The orchestrator's live check of 02f3581 | about $0.07 |
| Fix A (one live run, no new prompt) | $0.006 |
| Fix B (prompt evaluations $0.55, live run $0.126) | about $0.68 |
| The merge's live run | $0.015 |
| The check's live run | $0.13 |
| **The fix pass** | **about $0.90** |
| Writing these notes | $0 |

The ledger (`data/mvp/ai_runs.jsonl`, 7,948 rows) reads **$21.52 of the $30 cap**. $8.48 is left. Round 11 as a
whole spent about $1.80, against its $3.00 budget.

About 49,100 lines of Python and about 43,100 lines of tests are now in `experiments/mvp`.

## The second live check and its fixes (20 Nov)

The orchestrator used the test page again as the founder would, on build 25a1189. It ran on his library with
`MVP_VIDEO_ASK=1`. Twelve replies read right and were left alone. It found 6 things, P1 to P6. One fixer worked
through them (code at f436200). Then an independent check ran, found 7 more defects and fixed them. The code is at
c26c85f. The design is `mvp/DESIGN.md` 18.L2 and "18.L2 check". Topic words are written as X.

What already read right, and still does:
- The month's answer with both export ends, the channel ranking, and counts by topic and by year.
- The recall with days and cards, the honest can't-tell line and its offer, and "ask the video" at once.
- The first X video with its counts, and the timeline from its first year.
- A summary with numbered sources, the plain line with the best 3, and "ask them".

### The findings, before and after

| # | Before (25a1189, live) | After (c26c85f) | Measured |
| --- | --- | --- | --- |
| P1 | In "ask them" about X, one video's only point had nothing to do with X. Another's points were half off. One answer gave two thin points | A new prompt, `video_ask_v2`, names the thing asked and asks for concrete names, values and steps. A video that doesn't cover it gets one plain line by code: 'This video, "...", doesn't seem to cover X.' Code drops a point that only says what the video is, or repeats its title | The evaluation below. Live: one video said it doesn't cover X; two gave 3 and 4 concrete points on X |
| P2 | The offer named "A video from <channel>", a video with no title. The person had to type the question again | Such a video is never offered or asked unless named by its number. The typed question is kept: 'Say "ask that one" and I'll ask it: "..."' | Tests. Live: a titled video offered, the question kept, "ask that one" asked it at once |
| P3 | "ask the video" with no question after a recall asked what to ask. "ask them" with nothing shown went to the model | It asks about the recall's topic and says "I'll ask it about X." "ask them" with nothing shown gets one plain line by code | Tests. Live: "I'll ask it about X." and the answer |
| P4 | 7 shapes reached the model, among them "remind me what that video i watched about X was" | All 7 are read by code, each with traps beside it | 3 wordings per shape. Live: the remind-me recall, the comparison first, "email me that" asking for an address |
| P5a | A summary of watched reels said "the videos you watched" and "From 2 posts." | "the reels you watched" and "From 2 reels."; "videos and reels" for both platforms | Tests |
| P5b | Every history answer repeated the hint to send a new export | Where the export ends is always said. The hint comes once in 6 hours, as in summaries | 10 answers in a row, a restart, a second person, after 6 hours, a window after the record |
| P5c | A clip using a form of X as slang was listed in a summary about X | Another word form counts only if the item also passes the library's fit | With vectors, the slang clip is not cited. Without vectors it still is |
| P6 | For one small topic, the fit showed 2 watched videos and left out 2 that were truly about it | Fewer than 6 watched matches: all are shown and said as "mention". The fit is used only above that | Real library, below |

P1's evaluation ran on 8 public tutorials of 4 to 8 minutes. They were found by a YouTube Data API search, not taken
from the founder's library. Each got questions it covers (9 in all) and questions it doesn't (10). Four of those 10
are on the video's own subject but another thing, the live failure's shape. The list stays outside git.

| Run | Covered: answered, points, timestamps inside | Points on the question (the fixer's reading) | Not covered: said so, points shown | Cost |
| --- | --- | --- | --- | --- |
| Before (`video_ask_v1`) | 9 of 9, 34, 34 of 34 | 32 of 34 | 10 of 10, 0 | $0.155 |
| After (`video_ask_v2`) | 9 of 9, 30, 30 of 30 | 30 of 30 | 10 of 10, 0 | $0.156 |

The old prompt already said "doesn't cover" on all 10, so the live failure did not repeat here. The new prompt's effect
on it is not shown by a number. The new code checks, run on the old answers, dropped nothing that should stay. The
median answer took 3.4 seconds, against 4.8. The new prompt is terser: one "which tools" answer lost two named tools.
The checker re-ran 4 of the cases live and got the same results, including that loss.

P6 on the real library, the same 8 topics as before, counts only:

| Topics | Watched matches | Before | After |
| --- | --- | --- | --- |
| 7 large topics | 74 to 327 each | The fit is used | Unchanged |
| Small topic A | 4 | 2 shown, 2 left out, all 4 about it | 4 shown, 4 about it |
| Small topic B | 4 | 2 shown, neither about it; the 2 about it left out | 4 shown, 2 about it |

The checker counted again with its own script, which imports nothing of the bot. By its reading, 50 of the 66
videos shown across the 8 topics are truly about their topic. One topic shows 2 of 9, because the word mostly means something else there.

### The check of the second fix pass

- 50 new made-up messages (6 in Spanish), as tester and operator, setting on.
- At 25a1189: 6 right, 17 wrong, 27 to the model. After the fixer: 40 right, 8 wrong, 2 to the model.
- After the check's fixes: 48 right, 0 wrong, 2 to the model.
- Setting off, the 34 that need no video: 32 right, 0 wrong, 2 to the model. Nothing about asking videos was offered.
- 40 traps, compared byte for byte with 25a1189 in 160 runs: 0 differ except the build line.
- Video answers with a fake model: no points, all not covering, orders inside an answer, bad timestamps, both caps.
  Each gave the right line, and nothing was made or kept beyond what A-017 says.

Defects the check found and fixed:
- "ask the video" with no number asked the one YouTube video in view, even with no title. It now offers a titled one.
- When the fit kept none of 6 or more watched matches, the reply said nothing watched fits. They are now shown as "mention".
- "and how many videos did i watch this month" after a list gave the list again. It now gives a count.
- "ask video 2" after a recall asked which video. It now asks the second video the recall listed.
- A single video's answer counted points that only say what the video is. The design says they are never counted.
- Found live: any "#" in a YouTube title made it a video with no title. That was 34,560 of 115,615 YouTube items.
- A title's own hashtags are now cut off its name. 19,782 YouTube items still have no title, mostly one word or tags only.
- A recall now lists titled videos before untitled ones at the same match level.

Live, read as the founder would (the fixer's run and the check's two runs, setting on):
- Right: the recall; "ask the video" asked at once about the recall's topic; the plain line, best 3 and offer.
- Right: in "ask them", one video said it doesn't cover X, and two gave concrete steps on X. No padding.
- Right: the titled offer with the question kept; the remind-me recall; the daily limit after 5 asks.
- Thin: one video's only point said what it shows. Two of another's points said what the speaker did, not how.
- Noisy: three clip lines in one answer, from the minute cap set to keep the runs cheap.
- Wrong, now fixed: two recalls led with untitled hashtag videos. The second run showed titled ones.

### Checks that stay true

| Check | Result |
| --- | --- |
| Offline tests, in 4 shards | 4,713 pass, 0 fail (4,300 at 25a1189). 413 new: the fixer 139, the check 274 |
| Demo tests | 10 pass |
| Dry self-test | 59 conversations, 152 of 152 steps |
| Unchanged answers (`probe_same`) | Byte-equal |
| Development wording set by code, setting off and on | 73 helper lines right, 1 wrong (d007). 1 of 40 "none" lines taken (d132, on purpose). All 280 replies byte-equal |
| 159 rule texts and 123 phrasings | Taken by no new read |
| The traps of the round 11 check and of the first fix check | Still not taken |
| `MVP_VIDEO_ASK` unset | Nothing about asking videos is offered or run |

Earlier tests changed on purpose by the fixer are listed in DESIGN 18.L2. They follow P2, P3, P4, P5a, P5b and P6.
Three self-test conversations changed with them. The check changed no earlier test.

### What is still wrong or unproven after the second fix pass

History and recall:
- The fit cannot tell a topic word used another way. On the real library one topic shows 2 of 9 truly about it.
- Above 6 watched matches the fit can still leave out a watched video truly about the topic. This was not measured.
- The threshold of 6 and the fit's two settings come from small readings, not a tuned evaluation.
- Recalls chosen by words alone now say "mention" instead of "about". This is more honest, but reads differently.
- History answers about Instagram watches still say "videos", not "reels".
- A recall drops "and" from the topic it says back.
- Recall is English only. A Spanish topic matches only Spanish titles, and its timeline lists months of zeros.
- Three messages still reach the model: "can you remind me which video i watched about X was" is one.
- The other two are the Spanish "como han cambiado mis videos con el tiempo" and "list the X videos i watched".
- "what was that video about X", with no "i watched", is left to the model on purpose.
- A recall by a description that shares no word with the title only finds what the search's top 50 holds.
- The first recall waits for the search engine to load: 24 to 38 s live.
- A YouTube title of one word still counts as no title. Such a video is offered or asked only by its number.
- Cutting hashtags changes how every reply names such a video, not only video asking.
- The recall's new order was confirmed on the real library offline, not live.

Summaries:
- On the real library, summaries are honest but thin. Titles and descriptions hold little.
- A vague point that names the thing and traces to the text still passes.
- The checks that a point answers the question work only for "X in Y" questions.
- Another word form used as slang is caught only with the library's vectors. The topic's own word as slang still passes.
- The fit inside a summary was not measured on the real library.
- The prompts have no held-out set. They were tuned on one made-up set.

Asking videos:
- Nobody has checked an answer against the video itself. The evaluation read answers against their questions only.
- The new prompt's effect on the live off-question failure is not measured. The old prompt did not repeat it.
- Code cannot tell an off-question point from an on-question one. It checks only what a point is.
- The new prompt gives fewer points (30 against 34). On one "which tools" question it lost two named tools, twice.
- An older check drops a real tutorial step that says "add ... to ...", as if it were an order. Seen once live.
- "ask video N" on a video with no title still asks it, because the person chose it.
- After "what was the last X video i watched" (three YouTube videos), "ask the video" asks which one.
- The first "ask them" after a recall comes as two or three messages.
- Three clip lines in one answer are noise when videos run past the minute cap.
- The legal footing of A-017 is unsettled. The key must be on a billed Google project; code cannot check that.
- The evaluation's list has no held-out part.

From the first fix pass and now fixed:
- "ask the video" after a recall, and "ask them" with nothing shown.
- The remind-me recall, and the Spanish comparison without "?".
- The slang form (with vectors), and watched videos dropped by the fit on small topics.

### What the founder must decide or do now

1. Pull the branch and restart the test page. Try "what was that video i watched about X", then "ask the video".
2. Confirm P6: below 6 watched matches, all are shown and said as "mention". The real-library numbers support it.
3. Confirm the check's extension: when the fit keeps none of the watched matches, they are shown as "mention" too.
4. Read a few replies that name YouTube videos whose titles held hashtags. They are now named by their words.
5. Decide whether to tune `video_ask_v2` again for "which tools" questions. It would need its own evaluation.
6. Decide A-017 with the other founder. It now names `video_ask_v2`. A legal read and 20+ answers checked against videos come first.
7. The rest stands: the recall's order, "about" above 6 matches, and the summary rule.
8. Also still open: refreshing the exports, d132, a history rule on a schedule, and A-008 to A-016.

### Spend of the second fix pass

| Work | Spend |
| --- | --- |
| The orchestrator's second live check of 25a1189 | about $0.13 |
| The fixer (evaluation before $0.155, after $0.156, live run $0.061) | $0.373 |
| The check (4 evaluation cases $0.041, two live runs $0.107) | $0.148 |
| **The second fix pass** | **about $0.65** |
| Writing these notes | $0 |

The ledger (`data/mvp/ai_runs.jsonl`, 8,069 rows) reads **$22.17 of the $30 cap**. $7.83 is left. Round 11 as a
whole spent about $2.45, against its $3.00 budget.

About 49,600 lines of Python and about 44,500 lines of tests are now in `experiments/mvp`.
