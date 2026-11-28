# Round 10, MVP version 2: every kind of rule, answers in the founder's format, a profile, outputs (counts only)

12 to 13 Nov 2026. Derrick's library (`data/all`, 136,908 items), `gpt-5.4-mini`, prompts `interpret_v5`,
`compose_v4`, `extract_v1`, `profile_guess_v3`, `profile_merge_v3`, `first_requests_v1`. The design is
`experiments/mvp/DESIGN.md` (section 11 wins). Conversations from the live checks are outside git.

## What was asked, and what was built

| Asked (12 Nov) | Built |
| --- | --- |
| "Every 2 days", "randomly", every possible rule | Rule = when × what × do. All forms in the next table |
| An answer, not a list with "Why" | Opening line, one recommended pick with a reason, its ingredients or steps, "Or try these" |
| Picks that lead to a finished result | A must-have added by code for make/cook/build/practise requests; tips-only posts are a "no" |
| Based on the person's own context | A profile guessed from the library, corrected by the person in the setup, used as preferences |
| Email and "a bunch of output things" | A registry of actions: message, email, calendar, to-do and grocery lists |
| Reminders and to-dos | Free-text reminders, lists with due times, "remind me of the second one tonight" |
| Related picks from outside the history | Up to 3 YouTube videos from YouTube's own search, shown apart, only when asked or when under 3 saves fit |
| An automatic export routine | Reminder rules with the steps, an upload box and an inbox folder; the bot imports and switches library |
| "Can't find it, then finds it" | Three causes fixed (below) |
| As much as possible from onboarding | The setup takes at most five bot messages and ends with three first requests written for the person |

## Every kind of rule

| Part | Forms |
| --- | --- |
| When | now; once; weekly on named days; every N days; days of the month; "first Monday"; every N months; every N hours; several times a day; a random moment in a window; N random times a day or week (also every N weeks); only when asked, by a trigger word; when new saves arrive |
| Limits | start, end, a number of sends, dates to skip, quiet hours, snooze, pause until a date |
| What | saves, likes or watch history; must-haves in the person's words; things to leave out; order; count; named picks from an earlier answer; outside the saves: none, some or only |
| Do | message; email; calendar; to-do or grocery list |

## Why it sometimes found nothing

| Cause | Fix |
| --- | --- |
| A fit score near a fixed cutoff flipped between runs | Three verdicts (clear, close, no) replace the score; temperature 0 and a fixed seed |
| A failed search looked like an empty result, and was cached | A failure is an error; an empty ranking is retried once and never cached |
| The test page dropped messages after a restart | Page and console message references carry a per-process stamp; a dropped duplicate leaves a journal row |

## Measured

| Measure | Result |
| --- | --- |
| Offline tests (`experiments/mvp/tests`) | 755 pass (40 at the end of day 2). The demo's 10 still pass |
| Held-out rule phrasings (118, never shown to builders) | 100 right (84.7%) on the first run; 111 right (94.1%) after one improvement round. Target 90% |
| Development files, whole live runs (`interpret_v5`) | timing 58 of 59, content 58 of 59 |
| Four reviews, each checked by a skeptic | 48 findings, 46 confirmed, 8 of them high |
| Live checks on the real library | 6 rounds, 89 defects written down; all fixed except those under "Left as is" |
| Code size | about 17,100 lines of Python and about 12,200 lines of tests (3,700 at the end of day 1) |
| Spend on the MVP ledger | $8.62 of the $10 cap |

Two cautions on these numbers. The held-out set has now been used twice, and the improvement round saw the general
kinds of failure (never the cases), so 94.1% is no longer a fully blind figure. The development files measure the
model's form only; the code guards added in the last three rounds run after the model and are covered by offline
tests and live checks, not by those files.

## Reviews

Four lenses (privacy, reliability, cost and failure, experience), each followed by a skeptic who rebuilt the probes:
48 findings, 46 confirmed (8 high). All fixed with tests except the list under "Left as is".

## Live checks on the real library (the founder's assistant, through the test page)

Six rounds: 89 defects written down, each fixed with a test that fails without the fix, then checked by a second
agent with near-variants. The last full run (fresh store, whole setup, then the founder's own examples):

| Step | Result |
| --- | --- |
| Setup | Four bot messages after consent; each reply got exactly one answer; export reminders started as rules 1 and 2 |
| "convenient chicken and rice recipes" | Opening line, "I recommend … because …", 15 ingredients, 12 steps, one different dish under "Or try these", one under "Or these, which are close too" |
| "what should I cook tonight?" | A recommendation with a reason, ingredients, steps, two alternatives |
| "mini blender tutorials to start doing daily" | Preview says nothing is under 10 minutes and shows the closest; "no, any length" lifts the limit; YES starts rule 3; rules 1 and 2 untouched |
| "find me new blender tutorials on YouTube that I haven't seen" | Three YouTube videos, none from the library; the profile unchanged |
| "every 2 days … at a random time", "randomly … a couple of times a week" | Stored as every 2 days in a window, and as 2 random times a week |
| Settings and commands | Quiet hours, a new kit, pause, resume, stop, a dated reminder, "my rules", "what do you know about me": all as expected |

What the six rounds found, by kind: lost or doubled messages after a restart; timing phrasings the first prompt
missed; profile preferences that turned into must-haves; YouTube picks nobody asked for; a false "will run dry"
warning; a full recipe introduced as "couldn't confirm"; thin answers (copies of one post used up the places); and
two cases where a message changed lasting state it was not about (a request rewrote standing preferences; a reply to
a preview overwrote an export reminder). The last kind led to an audit of all 20 places a message can write lasting
state; 10 got a new or narrower check in code.

## Left as is

Product limits:
- A fully automatic export cannot be promised for US accounts. The bot reminds, and imports what the person uploads.
- Picks from outside the saves are YouTube only. The product needs terms and privacy pages that name YouTube before
  outsiders use this.
- Images: YouTube thumbnails and players, and Instagram's own embed on the test page. No Instagram media is fetched.
- Lists and calendar events live in the bot (a link and an `.ics` file), not in Apple Reminders, TickTick or a
  signed-in calendar.
- Only Spanish has a phrase table, and only for answers; rules made in Spanish are confirmed in English.

Never run for real: the Mac channel, the self-chat mode, Sendblue, real SMTP (a fake server only), the calendar link
on a phone. No person has graded the answers yet.

Known defects left:
- Alternatives vary in quality from run to run (the same request gave "Or try these" lines that were strong in one
  run and "the recipe is in the video" in another). The setup's guessed topics also vary between runs.
- "mini" means under 10 minutes by a fixed rule; a daily rule on a topic with nothing that short shows the closest
  until the person says "any length" or "include YouTube".
- A message whose whole topic is the time zone, quiet hours or a snooze is not checked against its words (the same
  settings carried inside another request are). With exactly one rule, a misread change needs no rule name; "undo"
  restores it. To-do numbers filled by the model are not re-checked.
- From the reviews: to-do and profile lines in the interpreter's context are not wrapped as data; search words stay
  in the library engine's rewrite cache after "delete my data"; the answer-email wording on Messages still names the
  outbox folder; loading a library can hold that person's lock for up to 10 minutes; over the cap, a second ask gets
  no reply that day; on a shared library one person's search spend counts toward everyone's daily cap.
- Rules stored before fix pass 4 keep the must-haves they were saved with until they are changed or remade.

For the founders to decide: A-009 (this scope, Proposed); whether a level from the profile should ever narrow a
request (now it only steers); whether a preview's pick counts as sent (still open from day 2).

## Tests, size and spend

- 755 offline tests; the demo's 10 pass.
- About 17,100 lines of Python under `experiments/mvp` and about 12,200 lines of tests. It is prototype code written
  and checked by agents; nobody has read all of it by hand.
- MVP ledger: $8.62 of the $10 cap. A normal answer costs about 1 cent; a thin answer's second look adds 0.4 cents.
