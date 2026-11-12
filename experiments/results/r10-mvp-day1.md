# Round 10, MVP day 1: the answer works (counts only)

Run on 12 Nov 2026 on Derrick's library (`data/all`, 136,908 items), console channel, `gpt-5.4-mini`, prompts
`interpret_v1` and `compose_v1`. Conversations and the grading sheet are in `data/mvp/eval/draft-3/` (outside git).

**The request set is a draft.** The agent wrote 20 requests from the topics in the library (8 recurring rules,
8 one-off questions, 4 hard cases). Derrick's own set replaces it before the marks in BRIEF-10 day 1 are read; the
grades below are the agent's, not his.

| Measure | Result | BRIEF-10 day-1 mark |
| --- | --- | --- |
| Requests that gave a valid rule, an answer, or a sensible question back | 20 of 20 | 18 of 20 |
| Errors | 0 | |
| Answers with picks | 15 (7 rule previews, 8 one-off questions or follow-ups) | |
| Honest "nothing found" | 1 (a date limit with nothing in it) | |
| Replies without a search | 4 (two unsupported requests, one question back on a vague request, one partly unsupported) | |
| Picks or lines removed by the code checks (section 5) | 10 | |
| Cited items outside the candidate list, extracted lines not in the post's text | 0 sent (removed by code) | 0 |
| Cost for all 20 | $0.061 | |
| Reply time, median and slowest (engine already loaded) | 4.1 s and 12.6 s | |
| Sendable as is (Derrick's grade) | not yet graded | 15 of 20 |

**Changes made during the day, each from a failure seen in a run:** ingredient lines are cleaned of headers,
promotions, links and hashtags before counting; an avoided word is checked against the model's title as well as the
post's text, and matches word stems ("cream" catches "creamy"); a follow-up sees the details already found, with counts
computed by code; a vague request gets one question back; workouts and recipes are ordinary topics, not health advice;
"details in the video" is shown only for recipes and how-tos.

**Engine load.** A cold start on this library takes about 45 s; the bot now loads engines when it starts.

**Tests.** 11 offline tests (`experiments/mvp/tests`) cover the reliability rules, the schedule across the end of
summer time, no repeats over a simulated month, feedback, deletion, the Mac reader (text in `attributedBody`,
tapbacks, own messages skipped) and the Sendblue webhook (secret check, retries deduped, outbound echoes ignored).
The demo's own tests still pass after the engine's `depth` option was added.
