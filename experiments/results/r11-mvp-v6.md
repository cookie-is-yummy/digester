# Round 11, MVP version 6: ask your watch history anything (counts only)

19 Nov 2026. Branch `experiments/search-loop`, code at 0a72c66. The design is `experiments/mvp/DESIGN.md` section 18.
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
