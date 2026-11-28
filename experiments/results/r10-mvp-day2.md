# Round 10, MVP day 2: any-time sends, a phone-free test page, and fixes from three reviews (counts only)

12 Nov 2026 (late). Derrick's library (`data/all`, 136,908 items), `gpt-5.4-mini`, prompts `interpret_v2` and
`compose_v1`. Conversations and grading sheets are in `data/mvp/eval/` (outside git). The request set is still the
agent's draft; Derrick has not yet replaced or graded it.

## The 20 draft requests, before and after

| Measure | Day 1 (`draft-4`, `interpret_v1`) | Now (`draft-6`, `interpret_v2`) |
| --- | --- | --- |
| Handled (a valid rule, an answer, or a sensible question back) | 20 of 20 | 20 of 20 |
| Errors | 0 | 0 |
| Answers with picks | 16 | 18 |
| Honest "nothing found" | 1 | 1 |
| Replies without a search | 3 | 1 |
| Picks, lines or titles removed or replaced by the code checks | 5 | 13 (titles are now checked too) |
| Cost for all 20 | $0.067 | $0.071 |
| Reply time, median and slowest | 4.1 s and 21.9 s | 4.5 s and 12.9 s |

No regression on the day-1 bar (18 of 20 handled). "Sendable as is" still waits for Derrick's grades.

## Timing: 24 ways to say when (live interpreter calls, the same 24 phrasings)

| | `interpret_v1` | `interpret_v2` |
| --- | --- | --- |
| Right or acceptable | 13 | 24 |
| Turned into a repeating push nobody asked for | 5 | 0 |
| Ended or changed an existing rule wrongly | 3 | 0 |

The phrasings cover: now; in N minutes or hours; tonight; tomorrow; a named day; a date; daily; weekdays; twice a
day; weekly; every other week; monthly; every N days; a saved request; "send it now"; "skip this week"; "not before
10am"; "stop after three times"; "when I save something new"; a time zone change; "when I need them". The seven that
the bot cannot do are answered as unsupported with the nearest offer. Cost of one pass: about 5 cents.

## What changed (each from a failure seen in a run or a reproduced probe)

- **Not a weekly digest.** One-off sends at any time (code works out "in two hours"), saved requests run whenever the
  person asks, "another", "run 1", "skip 1", "stop after N times", and a time zone change by text. One-off and saved
  requests need no preview; a repeating rule still needs a preview and a YES.
- **A test page** (`--channel web`): a message thread in the browser with a clock that moves forward, its own store,
  and a per-page token. A founder tests alone, without a second phone. On a Mac, `--self-chat` lets a founder text
  their own number (tested against a fake database only).
- **Run loop:** every inbound message is journalled (no text kept once handled) and deduplicated across restarts;
  people are handled in parallel and each in order; quick double texts are joined; the scheduler has its own thread.
- **Timed sends:** recorded before they go out (a crash cannot send a slot twice); a timed-out send is not retried; a
  send more than 2 hours late is skipped; after 3 unanswered sends the bot asks, after 5 it pauses.
- **Previews:** stay open 24 hours and through small talk; a yes with nothing waiting says so; the preview's pick
  counts as sent by the rule; praise alone is not a yes.
- **Checks:** titles must come from the post's text (numbers too); decimal amounts are kept ("1.5 cups" was shown as
  "5 cups"); avoided words match whole words, plurals and compounds, not parts of other words ("nut" matched
  "minutes"); follow-ups keep earlier details and recheck avoided things; dates use the action asked about.
- **Set-up and safety:** `people.json` is checked at start; deleted people are not added back; the per-person pause
  stops replies as well as sends; strangers get one reply a day with no names; a per-person flood guard.
- **Daylight saving:** times are compared in UTC, so a rule in the repeated hour does not fire again and again.
- `python -m mvp.trace` shows what happened to a message without printing text.

## Reviews

Three reviewers (design, bugs, timing), each followed by a verifier who rebuilt the probes. 36 findings: the
verifiers confirmed 26, rejected 10, and added 6 that the reviewers had missed. All 32 confirmed points are fixed, with
tests where behaviour changed. Six of the 10 rejected ones were fixed or built anyway, because they were cheap or
matched the founder's ask: the daylight-saving repeat, a read error stopping the bot, the Mac tapback race, "in N
minutes" worked out by code, the saved request (`on_request`), and the preview pick counting as sent. The last is
recorded as a founders' call in BRIEF-10 section 12. Not done: splitting `core.py` (745 lines) into handler, executor
and scheduler files.

## Channel re-check

Sendblue is not the cheapest; it is the only vendor found with a written rule for sends more than 24 hours after the
person's last text. Nothing needs buying for founder testing. The stage plan, prices and sources are in BRIEF-10
section 6 and the MVP document.

## Tests and spend

- 40 offline tests in `experiments/mvp/tests` (17 on day 1). The demo's 10 tests still pass.
- Spend so far on the MVP ledger: about $0.53 of the $10 build cap, plus under 1 cent of search calls.
