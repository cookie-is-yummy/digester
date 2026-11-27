# Decisions on the draft spec (the requesting founder, 25 Nov 2026, after reading SPEC.md)

These override SPEC.md wherever the two differ. The spec's text is not rewritten; builders read both.

## Answers to the open questions (SPEC.md 16.2)

| # | Question | Answer | What it changes in the spec |
|---|---|---|---|
| 1 | A learned routine answers alone at once, or after the same plan was chosen twice | the default (after two) | none; see "Routines" below: step 3 is decided again after step 2 is measured |
| 2, 10 | Speed, and which model is the brain | under 10 seconds is fine; **Claude Haiku 5.5 is the brain**. Sonnet 5.5 is tried later only if Haiku is not good enough | `MVP_BRAIN_MODEL` default `claude-haiku-5-5` (section 11.1); every Sonnet-only setting (thinking mode, effort, fallbacks, the cache layout) is checked again for Haiku against the claude-api skill before step 2 ships, not taken from the spec; cost table: the Haiku column |
| 3 | The scope line | only when something was guessed, filtered or clipped | `MVP_SCOPE_LINE` default `when_guessed` |
| 4 | A private topic that would outrank what is shown | say that topics kept private were left out | `MVP_PRIVATE_LINE` stays `line` |
| 5 | Memory | yes: the last few messages are kept 6 hours for the founder with no "remember" step; and a **personal context document** is kept (below) | `MVP_BRAIN_MEMORY` default on for the operator; testers keep the spec's gate (consent v2 and "remember") |
| 6 | Training terms | do not say "(not used for training)" | the line leaves today's consent text and is not in consent v2 |
| 7 | Web lookups | the founder consents | on for the founder at step 4; off for testers until consent v2 |
| 8 | The Claude cap for this phase | $25 | `MVP_CLAUDE_CAP_USD` default stays 10 in code; the founder's start script sets 25 |
| 9 | The amendment | accepted by the requesting founder | A-021 is filed as Proposed: **accepted by the requester, the other founder's decision pending** (it needs both) |
| 11 | The person's own agent through MCP | not tested by the founder yet | unchanged in the first version, as specced |
| 12 | Who words a routine's answer | a small model | none until step 3 |

## The personal context document (new; step 2)

The founder asked for "a context document for their personal query context and understanding", appended over
time, and reachable by a tool call when it is needed. It is how the assistant learns a person's way of asking
(their words for things, what they usually mean), grouped into categories.

A notes file that enters later prompts would break the spec's defence against injected text (nothing a model
wrote is ever replayed). So it has rules:

1. A note is saved only with a verbatim quote from the person's own message of that turn. Code checks the quote
   against the message. Text from a tool result (a title, a caption, a web page) can never be the source.
2. Code stores it (category, the quote, the reading in a fixed form such as "by <their word> they mean <ref>").
   The reading's ref must resolve through `find`. No free model prose is stored.
3. The person can see it ("what do you know about how I ask", "my notes") and delete any line or all of it;
   "delete my data" removes it.
4. It sits in its own block after the cached context, small (a size cap), and a `notes` read tool returns the
   rest when the block is clipped.
5. The planted set gains cases where a caption or title tries to write a note, and where a note tries to carry
   an instruction.

## Routines (step 3): to be decided again after step 2 is measured

The founder's later thought: with Haiku this cheap (about a tenth of a cent a question), code-matched routines
that answer with no model may cost more in answer quality than they save. "Might as well just use Haiku for
everything", and keep only the personal notes above, which tune understanding to the person's way of asking.
General rules that work for everyone (the built-in modifiers such as "without X", "only the long ones") are
still wanted where they are exact.

This does not change steps 1 and 2 (neither builds a routine). Step 3 is planned again from step 2's measured
cost, speed and understanding on Haiku. Scheduled rules ("every Sunday ...") are not in question: they stay.

## Build order changes

- Step 1 starts with the spec's least sure assumption (16.1 item 3): that `insight.render` and
  `insight.check_sentence` can check one marked sentence at a time against a tool result. It is proven on the
  existing insight cases and planted sets before the tools are finished.
- The step 2 gate adds an independent hand recount of about 20 live answers (the auditor passing is not
  enough: the sixth pass's hand check found about 20 false sentences the auditor had passed).
- No live model call in step 1. The build session has no Claude key; the OpenAI ledger has about $3.7 left.

## Not in this build (recorded as a separate Proposed amendment, A-022, with its own design round)

The founder also asked for: recommendations of new things from what a person likes; connectors that help carry
out goals (Gmail, the calendar, the to-do app, push notifications); plans for a goal (a time block on the
calendar, places on a map, to-dos, inspiration from their own history, suggestions added to a rule); being
proactive when the person is not; linking Instagram and Google during setup so exports arrive without manual
steps; and a model cheaper than Haiku for trivial reads. Much of the doing side exists already under
`actions/` behind today's bot. None of it is built in steps 1 and 2.

## After step 1 (26 Nov 2026)

Step 1 (tools and verifier, offline) is merged. It missed its own bar on one line that matters: an independent
auditor's true sentences were kept 42 of 61 (bar 97%), and the fixed verifier has not been attacked again. So the
full step 2 waits for a thin live slice on Haiku (the loop, the prompt, the verifier with one repair) with a gate
fixed before the run: nothing false sent, 90% understood, 85% of answers led by the model's own sentence, at most
15% of its sentences dropped, median 6 s, 0.5 cents a message; tuned on half the eval set and judged on the other
half by a hand recount and a fresh attack. Only the made-up test library is sent to the model.

The founder's answers to step 1's questions:
- A count from a result that leaves out private topics is sent with the line "Leaving out topics you keep
  private." Accepted.
- A part of a period ("late October") is refused for now; the bot asks for the days. A reader may come later.
- Scheduled Takeout is accepted as a route for recurring exports. If a more frequent official route exists for
  Instagram, the same is wanted for YouTube and Google. Being researched against official sources; the result goes
  to A-022 (part 5), which stays Proposed.

## After the thin live slice (25 Nov 2026)

The slice is merged (DESIGN.md section 22). Nothing in the message path changed. **The gate was missed.** On the
held-out half, first look (53 messages, the only fresh figures):

| Line | Bar | Measured |
|---|---|---|
| False or wrongly based sentences sent | 0 | 5 of 110, by an independent recount |
| Understood | 90% | 79% by the eval's hand plans; 91% to 94% by the independent reader |
| Answers led by the model's own sentence | 85% | 68% |
| Model sentences missing after one repair | 15% | 32% |
| Speed, median and p90 | 6 s and 10 s | 7.6 s and 11.0 s |
| Cost, mean | 0.5 cents | 0.16 cents |

What the figures say:
- The checker costs more truth than it protects. Of the dropped sentences that were sampled and recounted, 27 of
  33 were true. All 5 false sentences went out in answers where code's own lead had replaced
  the model's.
- Rules on free English do not converge. The tuning pass made 16 more true sentences pass and opened 24 new false
  passes. The fix pass closed them and still drops about a third of true sentences (19 of 60 and 12 of 61).
- The cell checks held: no wrong number or wrong calculation passed in the attack. Every pass class and the main
  wrongful drops are framing words: the window, the base, the scope, the direction, "only" and "all".
- A code lead reads badly: 0 of 17 read as good, none carried an offer, and many gave a bare total.
- About 3 of 53 answers said what the numbers mean. The gate never measured that.
- The speed is structural: two or three model requests a message, plus a repair in about a fifth.
- The eval's automatic auditor is not a source for the first line: 1 of its 24 findings was true and it missed 4
  of the 5 false sentences.

Decided by the build session, pending the founder:
- No more rules are added to the free-English checker, and step 2 proper is not built on it.
- Next, before any replacement is built: recount every sentence the model wrote on the held-out half (its raw
  false rate), fix the tool faults the checkers found, repair or retire the auditor, and write and lock a fresh
  set of messages. Both halves of the present set have been read.
- The next gate adds two lines: how the answers read to the founder's rules, and whether an answer says what the
  numbers mean. The hand recount stays.

Questions for the founder:
- Is a median of 7 to 8 seconds acceptable for a history answer?
- May code word the framing of a sentence (window, base, scope) from fields the model fills, with the model
  writing the rest? This sits beside the earlier answer "small model words it".

The run records and the recount are in `eval/runs/brain_slice_2026-11-25.tgz` (made-up library and messages only).

## The founder's answers after the slice (26 Nov 2026)

| Question | Answer | What it changes |
|---|---|---|
| Is a median of 7 to 8 seconds acceptable? | Yes. | The speed bar becomes 8 s median and 11 s at the slow end. |
| May code word the framing of a sentence? | No: "not a good choice". | The model words every sentence in full. "Small model words it" stands. |

What the second answer removes:
- Code writing the period, the base or the filter inside the model's sentence.
- Code rendering the claims with the model adding only the meaning.
- A frame line printed by code under every answer. The scope line when a filter is on stays, as decided earlier.

What it leaves open, and what is tested next on paper at no model cost:
- Cells only: code checks numbers, names, dates and calculations, and nothing else.
- Cells plus a small typed record for rank, list and change, which code checks against the rows. Code refuses a
  word the record cannot back and the model rewords it.
- A second small-model reader. It adds about 1.6 seconds and is above the new speed bar.

The raw recount of the model's own sentences on the held-out half (both looks, 272 sentences with a claim):

| Kind | Count |
|---|---|
| A wrong number, name, date or calculation | 0 |
| Wrongly based, catchable by a record checked against the rows (rank, tie, list, "new", "the other") | 9 |
| Wrongly based on period, base or scope words | 5 |
| Wrongly based because a tool gave a wrong picture | 3 |

Whatever design is chosen keeps three changes: a code lead never carries a model's points, the model's lead is
kept more often, and the marker bookkeeping stops dropping true sentences.

## Two model-worded checks, measured (26 Nov 2026)

Both keep the founder's rule: the model words every sentence and code words none. Each result was attacked by
an independent checker. Only the made-up library was used. Claude spend for this round: $1.21.

| | Cells only | Cells plus a typed record | Cells plus a second-model reader |
|---|---|---|---|
| What checks the framing | Nothing | A closed list of 98 words needs a record, checked against rows | A second Haiku request reads the answer against the tool results |
| The model's own 17 faults | 7 to 9 caught by cell and name checks | 4 more caught by the record | of the 8 that pass cells, 5 flagged; 3 of those 5 on the set its prompt was written on |
| The same 48 new false sentences (the skeptic's set) | about 40 out | 27 to 30 out | 3 to 5 out |
| False sentences aimed at that check itself | not run | 35 of 37 out | 0 to 2 of 29 out |
| True sentences refused or flagged | 10 to 21%, by which doubtful checks stay on | 10 to 17% with the doubtful checks off | beyond cells: 7 to 10 of 107, 4 to 5 of 28, 3 of 19, and 5 to 6 of 13 on the hardest set |
| Reasons given for a flag | none | a code name | right in 29 of 30 read by hand |
| Typical answer time | about 7 s | 7 to 7.5 s if the model fills the record; 8.7 s if it does not | 11 to 12.5 s (the reader takes about 4 s) |
| Cost per answer | 0.16 cents | about the same | 0.25 cents |
| Obeys an instruction hidden in a title | not applicable | not applicable | 0 of 34 tries |

What the figures say:
- The typed record repeats the old problem one level down. It catches a fault only when the sentence uses a
  listed word. A small rewording gets out: 6 of 6 of its own catches, reworded, passed. It is not built.
- The reader does catch framing faults it has never seen, in every class, with usable reasons. Its weak spots
  are base and scope, and "all" and "only" when something is hidden. It is far over the 8 second bar as measured.
  Its flags on true sentences are unsteady from run to run.
- Neither was tested on fresh answers from the model. The model's own real faults are few (17), so no rate can
  be given for them. The reword step after a flag was not run, so "out" for the reader is a best case.
- "Cells only" is not yet one pinned checker. With every doubtful check on, the model's lead is kept in 38 to 44
  of 53 answers; with them off, in 44 to 50. Which checks stay is pinned and hashed before any live run.

Convention taken as the default: when the private line is shown, "all", "only" and a rank over the rows shown
are not counted false because of the hidden private rows. The founder's answer "say it was kept private" covers it.

Next, whichever way the founder decides: one live run on half A of the fresh set, with the present prompt, the
pinned cells-only checker and the fixed tools, and a hand recount of what was sent. Half B stays locked.

Still the founder's to decide: whether an answer may go out with a sentence whose framing is unchecked (about 1
sentence in 17 was wrongly based, never a wrong number), or pay more seconds for the reader, or use the reader
only after sending or only in testing.

The evidence of both rounds is in `eval/runs/brain_after_slice_2026-11-26.tgz` (made-up library only).

## The first live run on fresh messages, numbers and names checked only (26 Nov 2026)

One live run on half A of the fresh set: 65 messages, the present prompt (v3), the pinned check of numbers, names,
dates and calculations ("cells mode"), and the fixed tools. Every sentence was recounted by hand from the library
rows by a reader who had not seen the run. Only the made-up library was used. Claude spend for the round: $1.29
($0.11 for the run, $1.19 for the reader's speed tests).

| What | Result |
|---|---|
| Wrong number, name, date or calculation | 0 written in 171 sentences; 0 sent |
| Wrongly based sentences sent | 13 of 150 (6 on every reading; 22 on the strictest) |
| Answers with at least one | 10 of 65 (6 on every reading; 17 on the strictest) |
| Where the 13 came from | 8 the model's own framing; 4 a tool's wrong or thin picture; 1 a dropped neighbour sentence |
| The model's own lead kept | 61 of 65 (51 first pass, 10 after one reword); 4 fell to a code lead |
| True sentences the check refused | 27 of 155 first forms (17%); 38 over all forms |
| Seconds | 7.97 median, 10.56 at the slow end; 3 turns ran out of time |
| Cost per answer | 0.15 cents |
| Answers as read | 9 good, 31 acceptable, 25 poor (22 poor before any truth count) |
| Answers the question asked | 43 of 65 |
| Says what the numbers mean | 16 of 65 |
| Worthwhile offer | 39 of 65 |
| Read calls that returned an error | 11 of 95, and 5 more refused at time up |

The two sent sentences closest to a plain wrong fact:
- "Pixel Pencil and Clip Factory were the channels that started in it [October]." One of them started in August.
  The tool said "new this year"; the model said "started in October".
- "The closest match is ..., opened on 5 October 2026." It was saved that day and never opened. The search result
  gave a date and no event kind.

What the figures say:
- The model's numbers held again. Over three looks it wrote about 440 sentences with a claim and no wrong number,
  name, date or calculation.
- The check is no longer the main problem. Most poor answers are poor for other reasons: a tool gap (7), thin or
  beside-the-point wording (8), a code lead (4, all poor), a true sentence refused (4), planning (2).
- The pinned check is not closed. An independent attacker wrote 131 new false sentences; 24 got out, 19 of them
  only in this mode. Most are a right number under the wrong year or period. The claim "every wrong number is
  stopped" is withdrawn until these are closed. The two loosenings that let a wrong channel name out are removed.
- Checking only numbers and names roughly halves the true sentences lost (17%, against 34 to 44% before).

The second-model reader, made faster:

| Variant | Seconds per request | Planted faults caught | The model's own faults caught | True sentences flagged |
|---|---|---|---|---|
| As first measured | 4.0 | 75 of 86 | 5 of 8 | 31 of 303 |
| Flags only, with the two prompt fixes | 3.4 | 73 of 86 | 4 of 8 | 20 of 303 |
| Flags only, thinking off | 1.4 | 80 of 86 | 5 of 8 | 130 of 303 |

- Three quarters of its time is thinking, and thinking is what keeps it from flagging true sentences.
- Inline it puts answers at about 11 s median and 15 s at the slow end, over the 8 s bar.
- Of its flags on sentences that would be sent, about 1 in 4 is right.
- The tool fix removed its main false alarm (friends' posts counted library-wide).

Taken as the working decision, unless the founder objects: answers go out with numbers, names, dates and
calculations checked by code and the framing unchecked. The reader is not put in the answer path. It stays as a
test tool that reads saved answers after the fact.

Next: close the leaks in the check, fix the tool gaps and the code leads, then run half A again and recount.
Prompt changes come after that, one per run. Half B stays locked for the final gate.

Open, parked:
- "limits" and "repeat" were switched off in this mode by the wrong test. They enforce the founder's own rules
  (never keep saying what the bot cannot do; be brief). They are being decided by a replay on this run.
- A no-match result now carries a count of items holding the words. This reverses SPEC 2.5.
- The understood score reads 37 to 65% against a 0.90 bar while a hand reading finds 43 of 65 answers on the
  question. The scorer and the bar need another look before the final gate.
- Scope lines and private lines are worded by code and are not in the sentence counts.
- One reader marked the answers. There was no second hand.

The evidence of this round is in `eval/runs/brain_cells_run_a_2026-11-26.tgz` (made-up library only).

## The second live run: the leak fixes did not hold and cost good sentences (26 Nov 2026)

The same 65 messages (half A), prompt v3, after this round's changes: nine new checker rules against the leaks, six
loosenings for true sentences, the tool gaps fixed, item cards and ask-backs shown, code leads that follow the tool.
Again every sentence was recounted by hand from the library rows. Claude spend for the round: $0.11.
Everything here is in sample: the fixes were made on these messages. Each round is one run.

| What | Run 1 | Run 2 |
|---|---|---|
| Wrong number, name, date or calculation written | 0 of 170 | 0 of 170 |
| Sent with a wrong number as shown | 0 | 1, if "Here are 5" over 4 cards counts (see below) |
| Wrongly based sentences sent | 13 of 150 (6 firm) | 5 of 149 (1 firm) |
| Answers with at least one | 10 of 65 | 5 of 65 |
| True first-form sentences the check refused | 27 of 155 | 40 of 165 |
| The model's own lead kept | 61 of 65 | 56 of 65 |
| Rewords asked for | 14 | 22 |
| Seconds, median and slow end | 7.97 and 10.56 | 8.14 and 13.27 (both bars missed) |
| Read calls that returned an error | 11 of 95 | 6 of 88 |
| Answers good / acceptable / poor | 9 / 31 / 25 | 9 / 37 / 19 |
| Answers the question asked | 43 | 50 |
| Says what the numbers mean | 16 | 12 |
| Worthwhile offer | 39 | 44 |

What happened:
- The tool fixes worked. All 13 of run 1's wrongly based sentences are gone from what was sent, and 12 of its 25
  poor answers are now acceptable or good. 23 item cards went out, none wrong.
- The leak fixes did not hold. They closed 24 of 24 of the first attacker's leaks. A second attacker then got 47
  of 113 new false sentences out, 31 of them a wrong number, date or measure by the repo's own rule.
- The checker is now the largest cause of poor answers: 9 of the 19 are a refused true sentence or the bare code
  lead that replaces one. Six answers got worse, all for that reason or for a new wording fault.
- Examples of true sentences refused: "Pan Theory is the one that shows up in every year of your history, from 8
  videos in 2021 to 32 in 2026." "Across all your history, the evening, 5pm to 9pm, is when you opened the most."
- "Here are 5 of the 72 food and cooking items you opened" went out over 4 cards. The model left out an item whose
  title was written as an attack on the bot. The five rows are real. It is filed as wrongly based, and reported
  here plainly as the nearest thing to a wrong number sent in either run.
- The model has written no wrong number, name, date or calculation in about 610 sentences over four live runs.
  With none seen in 610, the true rate is very likely under 1 in 200 (the 95% bound is 0.5%).
- "Good" has not moved from 9 in two rounds of checker and tool work, and "says what it means" fell. The prompt
  has not been touched yet.

What changes:
- Stop closing leak families rule by rule. It does not converge, and a replay on saved sentences cannot show what
  a rule costs on sentences the model has not written yet.
- A check keeps the power to refuse a sentence only when it fails on values, with no reading of words: a marker
  whose cell does not hold the written value, a path that does not exist, a number or name found nowhere in the
  turn's results. Everything else becomes a logged flag for testing, and refuses nothing.
- That is measured first on the 610 hand-judged sentences, then confirmed with live runs that change the checker
  only, run twice to learn how much one run differs from the next.
- After that the next change is the first prompt change.

Still open from this round: the tool defects in DESIGN 25.15; `percent` unclassed; the season rule's thin evidence.

## A check that refuses on values only: measured, and run live twice (26 Nov 2026)

The decision of the last section was built as a third checker mode ("values") and measured. The same 65 messages
(half A) were then run live twice with it, changing the checker only against run 2: the same tools, the same
prompt v3. Each run was recounted by hand by a reader who did not see the other. Claude spend: $0.19.
All of it is in sample. Marks are one reader's per run.

What the mode refuses: a marker whose cell does not hold the written value; a marker with no such cell; a
calculation that does not give the written value; a number, date, time or name found nowhere in the turn's tool
results or the user's message; and the privacy and safety codes (a sensitive topic named, motive guessing, an
outcome promised, another language, a made-up link, watch time on a length cell). Every other code still runs
and is logged as a flag. A flag refuses nothing and asks for no reword.

On the 574 hand-judged first-form sentences of the four earlier live runs:

| Checker | True sentences refused | Model's lead kept first pass | Rewords asked |
|---|---|---|---|
| Full (today's default) | 279 of 574 | 107 of 236 | 144 |
| Numbers and names, as first pinned | 99 | 189 | 52 |
| Numbers and names, with the leak rules | 88 | 192 | 47 |
| Values only | 4 | 231 | 4 |

The rise in refused true sentences in run 2 came from old rules meeting new sentence shapes (43 of 48), not from
the new leak rules (5 of 48).

Live, the same 65 messages:

| What | Run 2 (numbers and names) | Run A (values) | Run B (values) |
|---|---|---|---|
| Wrong number, name, date or calculation sent | 0 | 0 | 1 |
| Wrongly based sentences sent | 5 of 149 | 6 of 181 | 4 of 171 |
| True sentences refused | 48 | 4 | 3 |
| Faulty sentences refused | 9 | 0 | 0 |
| Rewords asked | 22 | 3 | 1 |
| The model's own lead sent | 56 of 65 | 65 | 63 (2 provider timeouts) |
| Seconds, median and slow end | 8.14 and 13.27 | 6.9 and 10.92 | 7.08 and 10.08 |
| Answers good / acceptable / poor | 9 / 37 / 19 | 17 / 36 / 12 | 20 / 33 / 12 |
| Answers the question asked | 50 | 57 | 54 |
| Says what the numbers mean | 12 | 20 | 17 |
| Cost per answer, cents | 0.157 | 0.143 | 0.127 |

What the figures say:
- Good answers about doubled and both speed bars are met again. Of run 2's 9 answers made poor by the checker, 7
  (run A) and 6 (run B) are now acceptable or good.
- The check now catches almost nothing the model actually writes: 0 faulty sentences refused in either run. What
  it holds is the made-up value. On the attack sets it stops 147 of 157 made-up values, and lets out 626 of 643
  real values said of the wrong period, row, measure or event. That second figure is the price, stated plainly.
- The first false sentence sent in any run: "Your newest save is Watercolor portrait lesson 3" (run B). The newest
  save is another post. The title was written without quotes beside another row's marker, and the mode counted
  it as found because some result of the turn holds it. This is a hole in a values rule, and it is being closed:
  a name beside a row marker must be that row's name.
- No flag earns its power back. Sentences with a flag from the old rules were true 33 to 40 times in 41 to 44.
  Sentences with no flag held no primary fault in run B and one in run A.
- Noise between two runs of the same build: the lead source differs on 4 of 65 messages, the tools called on 11,
  and 53 of 65 answers differ in substance somewhere. Grades moved by 3 good between A and B with nothing
  changed. A change must beat that to count.
- What is poor now (12 of 65 in each run): the model does not say a limit the tool already told it (no likes, no
  rows after the export's end, a friend's save shown only as a count) in 4 to 5 answers; its own framing in 3 to
  5; a provider timeout in 2 (run B); a quoted post's own numbers refused in 1.

Decisions taken, open to the founder's objection:
- Values mode is the working checker for the chat core. Full and numbers-and-names modes stay in the code, pinned
  and unchanged, and their codes run as flags for testing.
- "Be brief" (a fourth point, a two-sentence point), watch time said in words, outside knowledge and limits talk
  are no longer refused by code. They are flags. The prompt has to carry them.

The tool defects of DESIGN 25.15 are fixed (DESIGN 27): the window before a part of a period, cards and scope
lines only from what the answer cites, a next step on every refusal, titles quoted in code leads, the timeline's
52 periods back, weekday ties, a count of rows sharing one title. Sent answers do not re-enter the model's
context; the plan line and scope line do, and their library names are now neutralised.

The first prompt change is drafted, not run: each point says what its number means (what it is made of, how it
stands against the whole, or how it moved) instead of "X came next with N videos". "No meaning" is the cause in
68 of the 76 answers that the prompt could have made better.

Open: `meta.hidden` counts (a friend's save, private rows) cannot be cited, so two kinds of answer cannot be
given in a checked sentence; the model's own tool arguments re-enter the next turn unmarked; `new.channels`
still holds 5 at most (shared with today's bot; now noted in the result); the half B gate has not been run.

### Corrections and notes to the section above (26 Nov 2026)

- The grades (9 / 37 / 19 against 17 / 36 / 12 and 20 / 33 / 12) came from a different reader for each run, and
  one reader named five of their grade moves as a reader difference. Treat the rise in good answers as unproven
  until the blind re-marking of the next round: every run's answers for the same message, shuffled, the run
  hidden, two readers each. What no reader can move: true sentences refused 48 to 3 or 4, rewords 22 to 1 to 3,
  code leads 9 to 0 to 2, median 8.14 s to about 7 s, slow end 13.27 s to 10 to 11 s.
- Run A's "2 channels were new to you" can be read as a wrong count: a third channel was first opened in the
  window, and the tool's list of new channels holds 5 items at most by its own rule. It was filed as wrongly
  based. Read strictly, runs A and B each sent one false sentence.
- The pushed tip (values mode plus the second tool-fix round) had not been run live when this was written. The
  merge widened what counts as "found" to figures inside notes that code writes. Both are dealt with next round.
- Half B lock: during the tool-fix round one grep printed a single line of `eval/brain_fresh_b.py` (a cell path
  inside an id tuple). The file was not opened and nothing from it was used. Earlier notes: half B was re-pinned
  twice, 22 of its lines were written by a checker after tool results were seen, and one id's plan lapsed.

### The gate on half B, fixed before it is run

One live run of half B with the final build, marked blind by two readers. It passes if all of these hold:

| What | Bar |
|---|---|
| Wrong number, name, date or calculation sent | at most 1 sentence in the run |
| Wrongly based sentences sent (primary reading, readers' average) | at most 6 in 100 sentences |
| Privacy faults (a private topic named unasked, a friend's post shown, an instruction in a title obeyed) | 0 |
| Seconds | median at most 8, slow end (p90) at most 11 |
| Answers the question asked | at least 80 in 100 |
| Poor answers | at most 20 in 100 |
| Good answers | at least 25 in 100 |

The eval's "understood" score is not part of the gate. It reads 38 to 45% where a hand reading finds 54 to 57 of 65
answers on the question, so it measures agreement with one stored plan, not understanding.
These bars are proposed by the builder and stand unless the founder changes them before the run.

## Seven runs marked blind; the first prompt change (26 Nov 2026)

The baseline was fixed first (DESIGN 29): a name beside a row marker must be that row's own; a figure counts as
found only in a cell, not in a note code wrote; motive guessing no longer fires on a bare "because"; the prompt no
longer says code adds the limits line, and tells the model to say once, in the lead, what the export does not
hold (prompt `brain_v3b`); hidden counts (private rows, friends' posts) can be cited as a count; the screen that
re-enters the next turn is marked as data. Then two prompts were run live twice each on half A: the baseline
`brain_v3b`, and `brain_v4_meaning` (the baseline plus one change: each point says what its number means).
`brain_v3` is still the default in the code. Claude spend: $0.42.

Seven runs of the same 65 messages were then marked blind: the answers shuffled, the run hidden, three message
groups, two readers per group who each built the facts from the library rows. Readers agree on the grade in 77%
of answers (kappa 0.64). Figures are the average of the two readers.

| Run | Good | Acceptable | Poor | Answers the question | Says what it means | False sentences (settled) |
|---|---|---|---|---|---|---|
| Run 2: numbers-and-names check | 11 | 30.5 | 23.5 | 49.5 | 18.5 | 2 |
| Run A: values check | 17.5 | 34 | 13.5 | 56.5 | 28.5 | 1 |
| Run B: values check | 13.5 | 35 | 16.5 | 52 | 24 | 1 |
| Baseline fixed, run 1 | 23 | 29 | 13 | 59 | 31 | 2 |
| Baseline fixed, run 2 | 18.5 | 33 | 12.5 | 57 | 26.5 | 3 |
| Meaning prompt, run 1 | 28 | 24.5 | 11.5 | 58 | 34 | 1 |
| Meaning prompt, run 2 | 23.5 | 32.5 | 8 | 60 | 40 | 0 |

What the blind marks say:
- Values check against the numbers-and-names check: poor answers fall by 8.5 of 65 (interval 2.5 to 14.75), and
  "says what it means" rises by 7.75. The rise in good answers (+4.5) is inside the noise. One set of three
  readers sees it and the other set does not, so the earlier "9 to 17 or 20" is not confirmed as stated.
- The baseline fixes did what they aimed at: on the 11 messages they targeted, poor falls from about 7 to 1 to 2.5.
  Over all messages the change is inside the noise.
- The meaning prompt: "says what it means" rises by 8.75 of 64 (interval 4.25 to 13.5; 26 answers up, 6 down).
  All four run pairs are positive. Good +5 and poor -2.5 are inside the noise. No rise in false or wrongly based
  sentences, in length or in seconds.
- The rule written before the marks were read asked for a rise of 8 on both readers' marks. One reader set gives
  10.5 and the other 7.0. By that rule the prompt is not adopted on this run alone. It goes forward as the arm of
  the next round and is tested again.

What went wrong or is still wrong:
- Limits talk tripled: about 27 sentences per 65 answers against 7. The new limits text and the citable hidden
  counts are used where nobody asked ("Your export ends on 30 October 2026, so ..." as an opener; "50 more videos
  sit in topics you keep private" beside the private line code already prints). This breaks the rule "never keep
  telling the user what the bot cannot do" and has to be cut back to the questions that are about the missing thing.
- Speed: all 4 new runs miss a bar (median 7.6 to 8.8 s, slow end 10.9 to 12.2 s; the one run that meets the
  slow end misses the median at 8.13 s). The runs had up to 3
  provider timeouts of 15 s each and wrote more output (about 700 tokens a request against 620). Not yet explained.
- False sentences sent, 6 in 4 runs. Three are one message: "Here are 5 of the 72 ..." over 0, 3 or 4 cards. The
  model leaves out an item whose title is written as an attack, and still cites the count 5. One "next 5" with no
  cards. One "two of your saves mention flour" (one does). One first-open date of a channel said of a title.
  The values check stops none of them.
- A true sentence that quotes a saved post's own numbers ("50 g flour", "day 3") is refused in every run.
- The eval's auditor crashes on one message (a date compared as a number), so three runs hold 64 of 65 messages.
- Readers disagree widely on "wrongly based" (3 to 30 per reader group). Those counts are not settled between
  readers and should be read as ranges.

### Where the build stands against the half B gate, and the rule for the retest (26 Nov 2026)

The build would fail its own gate today, so half B is not run yet:
- False sentences: the bar is at most 1 per run. The four new runs gave 2, 3, 1 and 0.
- Speed: all four new runs miss a bar. The timeouts recur on the same messages (N004.0 in three runs; N005.0,
  N007.0 and N032.0 in two each), and output grew from about 620 to 700 tokens a request, which alone predicts
  about 0.7 s. So it looks like the build, not the session.
- Wrongly based: reader groups counted between 3 and 30, so the bar cannot be decided as written. The bar stays.
  Before the gate run, disputed sentences are settled from the library rows, as false sentences already are, and
  the readers get written conventions for the cases they split on.

The retest of the meaning prompt, rule written before the runs:
- Two runs of each prompt on half A, and one run of each on the 53 held-out messages of the earlier set (the
  prompt was drafted from half A answers, so half A alone is in sample for it). Marked blind as before.
- It is adopted if all of these hold. On half A, the paired per-message difference in "says what it means"
  (both readers, both runs) has a 95% interval above 0. On the held-out messages the difference is above 0.
  Good answers do not fall. Settled false sentences do not rise. Settled wrongly based sentences rise by no more
  than 2 per 65 answers. Median seconds rise by no more than 0.5 on the paired difference.
- This round's result is not pooled in. The first rule ("a rise of 8 on both readers") split six readers into
  two sets arbitrarily; one of the four possible splits passes it.

To do in the baseline before those runs: fix the auditor crash; cut limits talk back to the questions that are
about the missing thing, and count it mechanically; check a cited item count against the cards sent (4 of the 6
false sentences); let a figure in the cited row's own text count as found; check the kept safety codes and the
cells-only "found" rule against their live refusals (the safety code `outcome` refused the plain true sentence
"You saved it on 5 October 2026"; "found only in cells" refused 2 to 3 sentences a run and caught no live fault);
find why the same messages time out.

### The build round before the retest, and the rule for the crossed run (26 Nov 2026)

What the build round gave (branch brain-r28-local, DESIGN section 30 when merged):
- Two prompt files, brain_v3c (limits talk cut back, the form's items field explained) and brain_v4c (v3c plus the
  same meaning hunks). On a fixed 52-message sample of half A, unwanted limit sentences fell from 12 to 1 under v3c
  and to 5 under v4c, and a stated count above the cards shown from 1 to 0. v3c was revised once on that sample, so
  these figures are in sample.
- The eval's auditor no longer crashes on a date cell.
- Speed. The loss against the earlier runs is mostly the session, not the prompt: the old prompt was as slow that
  day. The 15 s timeouts are long thinking on the request that fills the form, not stalls. One setting moves the
  bars: the strict tool grammar on the nine read tools costs about 1 s before the first token of most requests.
  With it off, one run of half A gave a median of 6.46 s and a slow end of 9.46 s. Requests are now streamed with an
  exact wall clock; that alone moves nothing.
- New values rules for a stated item count against the cards, a figure quoted from the cited row's own text, and
  narrowings of two older codes.

What was decided after it:
- The new values rules do not go into the run switched on. On the v3c and v4c sample runs they changed no verdict:
  the prompt fixed those cases. An independent attack showed false sentences getting out more often with them
  (2 to 15 of 42 on one set, 4 to 8 of 39 on another) and 11 of 12 honest counts refused. A repair written against
  the attacker's own sets is in sample. This is the pattern of the cells mode again. The rules stay in the code
  behind a switch, off by default. After the run each is replayed alone on the saved forms and kept only if it
  flips a sentence the readers settled as true or false. My advice to build these two rules was wrong for the
  prompts going forward.
- A new fault blocks the run until fixed: three sample turns answered with a limit alone after a tool error and
  the 7 s soft deadline, and one of them said a read had failed when no read was tried.
- Strict off is safe only if code refuses a tool argument outside the schema, so that is built first.

The crossed run, rule written before the runs (it replaces the run plan of the section above; the adoption rule for
the meaning prompt stays as written there):
- Four runs on half A, one per cell: v3c or v4c, strict on or off. The same four on the held-out half of the plans
  set (62 conversations by the eval's loader; I wrote "53 messages" above from memory). That half is out of sample
  for the prompt only: it was run live in an earlier round and builders have seen those runs.
- The prompt is compared within each strict setting (two pairs on half A), strict within each prompt (two pairs).
- Strict off is adopted if all of these hold on half A, with the held-out half not contradicting them. Median
  seconds fall by at least 0.5 on the paired difference with a 95% interval above 0. Good answers do not fall and
  poor answers do not rise beyond the noise between same-arm runs seen so far (about 4 of 65). Settled false
  sentences do not rise. Answers given from a wrong scope (a window, a platform or a topic the message did not
  ask for) do not rise: the readers mark this, and every tool call whose arguments code refused is counted.
- The gate on half B is then run once on the chosen cell. If no cell meets the speed bars on half A, the gate is
  not run and the founder is asked whether the bars or the build should move.

### The prep round, and the settings of the crossed run (27 Nov 2026)

- The build of the run is the merged branch of this round (DESIGN section 30, parts 30.8 and 30.9). Its default
  values check equals last round's on every saved form (1,786 verdicts, 0 differ). This round's 16 rules are in the
  code, off, behind MVP_BRAIN_VALUES_RULES.
- Limit-only answers: the cause was the loop, not the prompt. All three turns had no read result in hand when code
  told the model "time is up, answer with the results you already have". Across 595 saved turns those were the only
  turns with no result. Now a turn with no answer in hand runs its read past the soft deadline (never past the hard
  stop), and a turn that ends with none sends code's plain line with its limit lines. On the 52-message sample: 0
  limit-only answers in four runs after the fix (in sample, and a rare fault, so the fake-provider tests carry it).
  The late round costs time on those turns: 13.7 s and 15.1 s were seen.
- Tool arguments: code now holds every call of the model to the schema that is sent, strict on or off. Before, 72
  of 358 bad-argument cases were silently defaulted or coerced. In 1,188 saved calls the model left the schema 3
  times, all with strict off, all a missing `order`; each got the scope that was asked. A refusal says only the
  schema's own words back.
- One fault older than this round was found by the independent check: the values check read the tool's clock
  (took_ms) as a value found in the turn, so a figure could pass when it happened to equal the milliseconds a tool
  took. It flips 22 saved sentences when the clock is varied. A timing field is not data. The rule `timing_out`
  leaves it out. It is on in all eight runs of the crossed run (MVP_BRAIN_VALUES_RULES=timing_out) and becomes
  the default if nothing in the run speaks against it. Its known cost: the true class "the four areas" (a count
  that stands in no cell) is refused every time, where before it passed only when the clock happened to match.
- The pinned friends note ("Posts from friends are not counted") contradicts the hidden-count cells (counted, not
  shown). It is left as it is for this run and listed for the next change of the tools.
- Limit sentences on the sample after the last wording: unwanted in 4 of 52 answers under each prompt (12 under the
  prompt before); the difference between the two new prompts is inside the noise.
- Claude spend to here: about $5.05 of $25.

### The crossed run: results, and why the gate on half B is not run yet (27 Nov 2026)

Eight live runs, one per cell: prompt (v3c, v4c) by strict tools (on, off), on set A (65 messages) and on the
held-out half of the plans set (set H: 53 messages in 42 conversations; I wrote 62 above, which is the half before
its filter). Six blind readers, two per answer; a tally; an independent recount whose mechanical counts match the
tally in all eight cells. Reader agreement on grade: 78%, kappa 0.61. Evidence: eval/runs/brain_crossed_runs_2026-11-27.tgz.

| Cell | Good / acceptable / poor | Answers | Means | False (two settlements) | Median / p90 s |
|---|---|---|---|---|---|
| A v3c on | 12 / 43 / 10 | 61.5 | 18.5 | 3 to 4 | 8.13 / 11.55 |
| A v3c off | 14 / 43 / 8 | 62 | 20.5 | 0 to 2 | 6.72 / 9.65 |
| A v4c on | 21.5 / 32.5 / 11 | 59.5 | 22.5 | 2 to 3 | 7.31 / 10.67 |
| A v4c off | 16 / 42.5 / 6.5 | 62 | 19 | 2 | 6.42 / 9.56 |
| H v3c on | 11.5 / 32.5 / 9 | 48 | 10.5 | 2 to 5 | 8.02 / 11.02 |
| H v3c off | 10.5 / 33.5 / 9 | 47.5 | 12 | 2 to 3 | 5.88 / 8.63 |
| H v4c on | 19.5 / 23 / 10.5 | 45 | 17 | 1 | 6.96 / 10.40 |
| H v4c off | 20.5 / 22.5 / 10 | 47 | 18 | 3 to 5 | 6.07 / 9.37 |

Wrongly based firm: 1.6 to 2.8 per 100 sentences in every cell. Wrong scope: 0 in every cell. Privacy faults
settled: 0. Limit-only answers: 1 on set A in all, and one held-out message in every cell.

The two rules, applied as written:
- The meaning prompt is NOT adopted. On set A "says what it means" rose by 1.25 of 65, interval -3.0 to +5.25: not
  above 0. On set H it rose by 6.25 (2.0 to 10.5). Tally and recount agree under every settlement.
- Strict off, per prompt as the rule says. Speed: 0.9 to 2.2 s faster on the paired difference in all four pairs,
  every interval clear of 0. Under v3c it passes on both sets (good +2, poor -2, false not up). Under v4c it fails
  on set A (good -5.5 of 65; set H shows +1) and false sentences rise on set H. With one run per cell this cannot
  be told from the noise between two runs of one build (about 3 good, 4 poor of 65). Crossing two questions in
  eight runs was my choice, on advice; it left no repeat. Next time each candidate is run twice.
- The model left a tool's schema 6 times, all with strict off, all a `breakdown` call without `order`. Code
  refused each and the model called again.

What the rule did not see:
- My rule for the prompt tested "says what it means". The gate tests the grade. On the grade the prompt does
  better on both sets: good answers +5.75 of 65 on set A (0.5 to 11.25) and +9 of 53 on set H (3.75 to 14.5).
  All four v3c cells miss the gate's bar on good answers (18.5 to 21.7% against 25%); the v4c cells sit at 24.6 to
  38.7%. The prompt's one measured cost: "answers the question" fell by 1.75 of 53 on set H, interval clear of 0.
- So the next rule is written on the gate's own marks (below), not on one mark of my choosing.

Deviation from the rule above, and why: the rule said to run half B once if a cell met the speed bars on set A.
Three cells do. I am not running it. Six of the eight cells are over the bar of one false sentence, so the locked
half would be spent on a fail that is already known.

Where the false sentences come from: 12 of the 16 that both readers confirm say that data is missing or that a
read failed, when the rows hold the answer ("your export holds no video lengths", "I can't isolate late October",
"no Instagram history before 12 October"). No value check can see these: they hold no wrong value. Three held-out
messages fault in every cell, whatever the prompt or the setting, so their cause is in what the tools returned.
The next round sorts each by cause and fixes it at the source (a tool's note, a narrow error the model widened, the
time-up message), not with a phrase rule.

The switched-off checker rules, replayed on these runs (out of sample for them): 10 sentences flip, all rightly by
the tally's reading (9 true sentences released, 1 false count over the cards caught); none wrongly. Six rules flip
on their own. They are switched on next round together with the guards that were built for them, after the attack
sets are rerun on exactly that set. `timing_out` is a bug fix and becomes the default; its declared cost showed
once (a true "these four areas" refused).

Marking: the tally and the recount drew the line between false and wrongly based differently on 8 sentences, which
moves a cell by up to 3 against a bar of 1. The line is now written in eval/brain_reading_rubric.md ("False or
wrongly based: the line"), with the privacy call the reader groups split on. The gate's bar on wrongly based
sentences counts the firm ones; I decided that after seeing these marks, and the lenient count is reported beside
it (with lenient included only one cell is under 6 per 100).

The rule for the next run, written before it:
- Strict off is the setting (speed is settled; code holds the arguments).
- Two candidates, v3c and v4c, each with the fixes of the next round, each run twice on set A and twice on set H.
- The candidate for the gate is the one with more good answers on set A (both runs, both readers), provided that
  against the other it has no more settled false sentences, no more poor answers beyond 4 of 65, and "answers the
  question" does not fall on either set with an interval clear of 0. If v4c fails a proviso, v3c is the candidate.
- The gate on half B is run once on that candidate only if both of its set A runs and both of its set H runs meet
  every bar but one at most, and none has more than 2 settled false sentences. Otherwise another round.

Claude spend to here: about $5.75 of $25.

## The fix round: false "it is missing" sentences fixed where they start (27 Nov 2026)

What it was: every false, wrongly based, limit-only and wrongly refused sentence of the crossed run was traced to
a cause, the causes were fixed at the source by three builders, merged, attacked by an independent agent, and the
attack's faults repaired. DESIGN.md section 31 holds the detail; this is what was decided and what it cost.

The causes, by class (DESIGN 31.1). Most false sentences began in what a tool told the model:
- Item rows said only "long", with no minutes, so the model said the export holds no lengths.
- A note said "there is no ranking by times opened", and the model repeated it as "no rewatch counts".
- Under a platform scope the first day of that platform's opens was labelled "your history starts on".
- A result cut to size lost the cells that held the answer, and meta said only "truncated".
- The prompt still said "late October" cannot be read, though code reads it.
- A title lost its episode number, so 20 different videos read as one title, and `same_title` counted the row itself.
- The rest: the time-up message, a follow-up that needs the last answer's values, misleading cells, and 9 faults
  of the model alone with no general fix.

What was fixed (DESIGN 31.2 and 31.3): the tools now carry the cell or say the true thing for each class (minutes
and a `lengths` cell, `opened_more_than_once`, the scope's own start and the record's start, `meta.cut` and every
period kept, numbered titles, `other_items_same_title`, per-weekday opens, `last_watched`). The loop says a call
"was not run" when its own clock ends a turn. Two new prompt files, brain_v3d and brain_v4d, drop the stale line
and say that a limit covers only its own words. A doing part of a message ("every Sunday send me...") gets one
line written by code; the model says nothing of it.

Two defaults I set, both the founder's to change:
- A friend's post stays out of every total, as before. The tool note and the new prompts now say "in no total".
- A period that holds private items is never marked sparse.

The live check, in sample (the 73 turns the faults were traced on, each prompt once, one reader): of 27 fault keys,
v3d has 23 gone, 2 still, 2 unchanged by the friends rule; v4d has 25 gone and the same 2 unchanged. The three
held-out messages that faulted in every cell are true in both. New faults in the same check: 1 false and 3 wrongly
based sentences under v4d, and one regression in both prompts (below). This is not evidence for the gate: the
fixes were written against these messages.

The independent attack found nine faults in the merged build (DESIGN 31.8). All nine were repaired:
- The new per-item minutes cell let watch-time sentences through. A new rule, `length_cells`, is in the default.
- A code-written line on the timeout path dropped a private topic's scope. Fixed in the code lead.
- Three new cells ignored the call's scope. They are counted in scope now and the auditor recounts them.
- A learned result carried a friends count that invited a false sentence. Removed.
- Three checker rules switched on this round let out made-up sentences under attack. They are off again.
- Code's doing line could be set off by words in a title. It now needs the words to be the person's own.
- A note named a cell the sheet did not carry. The sheet carries it.
- One test copied an eval message and one docstring quoted its answer. Both replaced.
- The eval put a marking hint on the blind reading sheet. Removed; the convention is in the rubric instead.

The values check's default for the run, as code now holds it: last round's four rules (row_name, cell_found,
day_typed, motive_you) plus timing_out, cards_found, item_count_free, screen_window, screen_uncited, rows_before,
page_cited, rows_kept, shown_said and length_cells. Off, behind the switch: item_count, rows_shown, cited_rows,
outcome_you, outcome_cited, row_text, row_quote, quote_at_row, row_group.
- Why three came back off: taken out one at a time on the attacker's sets, outcome_you let out 4 false sentences
  for 1 true one released, row_text 2 for 0, row_group 1 for 0.
- The cost, declared: 13 true sentences of the saved runs that those three released are refused again.
- item_count stays off: it refuses 11 of 12 honest page counts. So "5[r1.items.count]" over fewer cards still passes.
- This is the third round in which checker rules were switched on and then off again. The rules are not reopened
  before the blind run: the source fixes moved the faults, the checker rules did not.

Checks on the merged tip: whole suite 6406 passed, 2 skipped, 0 failed. The checker's full and cells modes and
both answer builders: 5,984 verdicts and 4,209 answers, 0 differ from the last pushed tip. Planted cases byte-same
in three modes. Dry self-test of today's bot 164 of 164. Privacy scan of the round's diff: generic words only.

What stays open, said before the run:
- Results are about 20% larger, so each call reads more tokens. A month timeline of all history is about 7,500
  characters against a cap of 6,000, and drops the parts-of-day cells to keep every month (`meta.cut` says so).
- Faults no value check sees: "all from one channel" over a row that lists two; one row's cell said of another row.
- A count written with a marker over fewer cards; "you watched X for N minutes" with a marker on the length.
- The code lead after a provider timeout is true but answers one part of the question.
- The eval set's lock: the repair agent ran two recursive greps over experiments/mvp without the exclude flags.
  Neither printed a line of the locked file. Noted with the earlier slips.

Claude spend to here: about $6.45 of $25.

## The last fix before the two-candidate run, and the freeze (27 Nov 2026)

A live check of the pushed tip (10 conversations, each prompt once) showed three faults at the seam between the
tools and the checker:
1. A true length sentence was refused twice and a code lead that does not answer went out. The model writes
   "10 minutes[cell]"; the checker reads a length only as "10[cell] minutes".
2. The model cited a copy of the window's dates that no marker reaches (the result's meta). Refused; code lead.
3. A marker alone in brackets went out as "()".

What was built, and what was taken back:
- The first build accepted the natural forms: the unit word before the marker, markers on meta, a marker on a group
  of cells. Two independent checkers then wrote sentences by hand. Of 64 false ones, 7 got out before the build
  and 40 after it. Most were plain wrong values: "Yes, there are videos from 2020", an end date said as a start,
  a window's days said as a count of videos, one video given another video's length.
- The repair took all three loosenings out. Its rule: nothing in this round lets out a sentence the last pushed
  tip refused. On the same 64 sentences 4 get out now, the same 4 as before the round.
- What is left of the round:
  - A refused length, meta or group citation now gets a reword message that names the form that passes
    ("10[r1.lengths.longest_minutes] minutes"; "cite the sheet's own cell, as r1.window.start"). The message
    names cells by path, never by value.
  - "N days[cell]" on a cell of days is checked exactly; a day cell's figure followed by a count noun is refused.
  - A hedge of direction on a length ("under", "over") is held strictly.
  - A bracket that held only markers is dropped from the sentence sent. Brackets the model typed stay.
  - Two tool notes no longer name cells that their own result does not carry. A dead note constant is removed.
  - A test walks every path the tool texts and both prompts name and fails if no marker reaches it.
- No prompt file changed. brain_v3d and brain_v4d are byte-same as at the last pushed tip.

Said plainly: only the third fault is closed in code. The first two are not closed in the checker. A true sentence
in the natural form is still refused as often as before (29 of 34 hand-written true sentences, 16 of 19 on the
watch-time probe). They now rest on one reword each, and a reword is only asked for when the lead fails or more
than half the sentences fail. Otherwise the true sentence is dropped and the rest of the answer goes out.

Live check of the repaired build, by me (in sample, one reader, each prompt once; 12 conversations, 28 turns):
- No answer fell to a code lead.
- Both reword messages fired once each, under v4d, and both rewords passed and are true ("each has the same
  official length of 10 minutes"; "it starts on 5 January 2021").
- Under v3d the same two messages passed on their first form. The prompts did not change, so that is run-to-run
  variance, not the fix.
- Two true points were dropped with no reword (a group citation, a window citation). Both answers still answer.
- The two messages that reach the changed no-match note answer as before.

Checks on the frozen build, rerun by me on clean worktrees:
- Saved forms of 32 run folders (1,286 forms, 3,674 sentences), default values check against the last pushed tip:
  0 sentences released, 0 refused, 1 text change (the "()" gone). With this round's rules off: 0 differ.
- Full and cells modes, code lead and both answer builds: 9,591 verdicts and 4,084 answers over 3,197 forms.
  One differs, in a logged note of cells mode, not in a verdict. That note depends on Python's hash seed and
  flips the same way on the last pushed tip (4 seeds tried on each). Nothing else differs.
- Whole suite: 6416 passed, 2 skipped, 0 failed.
- Privacy scan of the round's diff: generic words only.
- One test is order-dependent: test_brain_r28_checks::test_a_figure_of_another_rows_text_is_not_found failed
  three times in partial runs across this round and passed alone and in every full run. Not fixed.

Frozen for the run:
- Code: the tree of local commit 232c21e, squash-merged here. Run from a detached worktree of 232c21e.
- Model claude-haiku-5-5. Strict tool grammar off. Check: values, default rules, no switch set.
- The default rules, 18: row_name, cell_found, day_typed, motive_you, timing_out, cards_found, item_count_free,
  screen_window, screen_uncited, rows_before, page_cited, rows_kept, shown_said, length_cells, and this round's
  length_unit, days_unit, cite_hint, paren_tidy.
- Candidates: brain_v3d and brain_v4d. Each twice on set A (65 messages) and twice on set H (53 messages).
  Order: A v3d, A v4d, A v4d, A v3d, H v4d, H v3d, H v3d, H v4d. One run at a time, nothing else on the machine.
- Marking: blind packets by script (seed 31031), six readers (three groups, two each), a tally that settles from
  the rows, an independent recount. The rule written above ("The rule for the next run") decides; nothing is
  added to it.

Open, said before the run:
- The marker-before-unit form keeps the holes it had: another row's length said of a named video, time spent
  said in words no check reads, a window's end said as its start through the sheet cell.
- A meta value with no sheet twin (the start and end of the window before) can only be written with no marker.
- "(see [m])" still goes out as "(see)".
- A tool's window words for saves give the scope's span, not the last save's day ("your saves: 3 to 30 October"
  when the last save is on 10 October). A sentence that repeats it is wrongly based. Not fixed before the run.
- Both sets are in sample for every fix of the last two rounds. Only half B is not.

The eval set's lock, this round:
- The fix builder ran one `git grep` from experiments/mvp without the exclude paths. The output was filtered and
  no line of the locked files was printed.
- One checker used two set H message wordings (quoted in the round's brief) for offline probes in its own scratch
  files. Nothing of it is in the repo.

Claude spend to here: about $6.55 of $25.

## The two-candidate run, marked blind: every quality bar met, the gate not run yet (27 Nov 2026)

Eight runs on the frozen build, as written above. Six blind readers, a tally that settles from the rows, an
independent recount. The blind was sound and every measured count matches between tally and recount. Both sets are
in sample for the last two rounds' fixes. Cost of the runs: $0.69.

| Run | Good | Poor | Answers the question | Settled false | Wrongly based firm, per 100 | Median s | p90 s |
|---|---|---|---|---|---|---|---|
| A v3d 1 | 48% | 15% | 98% | 2 | 3.3 | 5.95 | 9.01 |
| A v3d 2 | 52% | 4% | 100% | 0 | 1.6 | 6.40 | 9.06 |
| A v4d 1 | 54% | 5% | 100% | 2 | 0.0 | 6.19 | 9.21 |
| A v4d 2 | 55% | 6% | 98% | 0 | 1.7 | 6.32 | 9.37 |
| H v3d 1 | 38% | 11% | 92% | 0 | 1.3 | 5.87 | 9.11 |
| H v3d 2 | 38% | 11% | 94% | 0 | 2.0 | 5.95 | 8.95 |
| H v4d 1 | 51% | 8% | 94% | 1 | 0.0 | 5.62 | 9.10 |
| H v4d 2 | 62% | 9% | 94% | 0 | 0.7 | 6.09 | 8.61 |

Rates are the two readers' average. Bars: good at least 25%, poor at most 20%, answers at least 80%, false at most
1 a run, firm at most 6 per 100, median 8 s, p90 11 s, privacy 0.

Against the crossed run of the round before (same sets, same method): good was 18 to 39%, now 38 to 62%. Six of
eight runs then sent more than one false sentence; now two of eight send 2 and none sends more. The false "it is
missing" class fell from 12 sentences to 3. Speed, wrongly based, answers, poor and good pass in every run.

Reader agreement: grade 81% (kappa 0.67), answers 99.8%, false 98.9% (kappa 0.61).

The candidate, by the rule: v4d. It has more good answers on set A (142 against 129 of 260 marks), and the poor
and "answers" provisos pass on both sets. On set H it is clearly better: good +10 of 53 a run (interval 4.75 to
15.5). On set A the lead (+3.25 a run) is inside the run-to-run noise.
- The proviso "no more settled false sentences" names no set. On set A it is 2 against 2. Over all eight runs it
  is 3 against 2, which would make v3d the candidate. I read it on set A, where the rule picks. A difference of
  one false sentence is inside the noise between two runs of one build (0 and 2).

The condition to run the gate on half B: not met beyond doubt, so I am not running it. It rests on three calls in
one run (A v4d 1), and the tally and the recount settle them differently:
- "about one a week" for 50 opens in 28 weeks. One reader of two marked it false. Tally: lenient. Recount: false.
- "Your Instagram export only covers 12 to 15 October" when it also holds saves from 5 October. Both readers
  marked it wrongly based. Tally and recount: false, as the same message was settled last round.
- A channel of a private topic named in a follow-up turn, where code carried the unlock from the turn before.
  It appears in all four set A runs, both builds. Last round's tally settled the same answers as no fault. The
  rubric line I wrote from that settlement says "in a turn where the person named that topic", which read by the
  letter makes it a fault.
- With the tally's settlement and last round's privacy reading the condition is met. With the recount's it is not
  (3 false sentences in that run). I do not pick the reading that passes after seeing the marks.
- The gate allows 1 false sentence a run. These runs sent 2, 0, 1 and 0. Run now, the gate is close to a coin
  flip, and half B can be used once.

What the remaining faults are (23 settled false and firm sentences in eight runs: model 20, tool 2, code 1):
- The model says the opposite of a tool note: "the title is cut short in your history" (2 of 4 set A runs).
- A scope's own span read as the whole record: "Instagram export only covers"; saves said to run to 30 October.
- "My last answer was wrong to leave it out" when it had not left it out.
- "All five of these" over fewer cards; a rank or a "first" said over a page of results.
- A true point dropped by the checker, which left a limit alone (the topic's name cited on its group of cells,
  3 of 4 set H runs).
- A private line missing when the one point that would set it off was refused (code).
- "Which channels did I drop" answered over the last 4 weeks only (all runs); "gaming daily" read as the area.
- Of 48 refused sentences, 7 sit in poor answers and all 7 are true.

Decided:
- v4d is the build that goes on. v3d is dropped. The next runs are v4d alone.
- One more short round on the classes above, fixed where they start. Then v4d twice on each set, marked blind.
- The gate on half B is run once if both set A runs and both set H runs meet every bar but one at most, none has
  more than 2 settled false sentences, and tally and recount agree on that. If they split again on close calls,
  I report it and ask the founder rather than pick.
- For the founder: when a person asks about a private topic and then asks a follow-up without naming it, may the
  answer name that topic's channels? Today code carries the unlock, so it does. Until told otherwise I keep that
  and the rubric says so from now on.

Claude spend to here: about $7.25 of $25.

## The fix round after the blind marks, and the freeze for four runs (27 Nov 2026)

The round fixed only faults that start in a tool result or in code, each where it starts. The model's own
judgement over a right result was left alone. No prompt file changed. Details: DESIGN 32.

What was built, and how each fix is known:

| Class | What changed | How it is known |
|---|---|---|
| Span words | A scope window's words say each end for what it is. | Live: a bare saves span was said in 4 of 16 answers before, 0 of 16 after. |
| Cut title | A title cut to fit carries the item's whole line beside it, for the model only. | Live: "its title is cut short" in 5 of 16 answers before, 0 of 32 after. |
| Topic's name | The topic is a one-row list, so its name on its row passes the row-name rule. | By mechanism. Too rare for eight repeats to show. |
| Private line | The line follows what the results behind the sent answer left out. | By mechanism. Too rare for eight repeats to show. |
| Scope line | The line a person sees is short; beside a filter it says no start day. | Offline, over 68 made-up results. |

All live figures are in sample (sets A and H were used to find these faults).

The cut title took two attempts and one follow-up:
- The first build put the whole title in the row's one title cell. Code's own lead and the full and cells checks
  read the same cell, so true lines were refused. It was taken back.
- The second build leaves the title cell as it was and adds a second cell that only the model and one values rule
  read. An independent checker then found three faults (a long line cut under a note that called it whole; a start
  day beside a filter; a marked clock refused). All three were repaired.
- Measured cost of the second build: on one follow-up ("what did it say about ..."), code's own lead went out in
  3 of 16 answers, where it never had. The model answered from the title's own figures, the check refused them, and
  the reword named one figure at a time.
- The follow-up: the reword now names every such figure at once and the two forms that pass. It changes the text
  of a reword only; no verdict moves. After it: 0 of 16 code leads. Only two rewords were asked in those 16, so
  this is what the change aims at, not proof.
- I had set a rule before reading the repeats: take the whole line out if code leads rose. I did not follow it.
  The gate's bars, written before this data, weigh a settled false sentence far above one poor answer, and the
  false sentence went from 5 of 16 to 0. The founder is told both numbers.

Exceptions to the round's own rule ("nothing lets out a sentence the tip refused"), each counted:
- 26 false sentences that name an item by its whole title now pass. Each passes at the old tip too when written
  with the cut title. Values mode never read what is said about a named item beyond its figures and days.
- 13 false sentences on the topic's row now pass. Their unmarked twins passed at the old tip.
- Among the 26: a sentence that claims an action was done, worded after a title that reads like an instruction.
  No mode refuses it, before or after. Step 2 (rules and sends) must close this before any action is wired.
- Time spent said through a marker on the title cell passes, as it did at the old tip through the same marker.
- Full and cells answers built from today's tools differ from the old tip in the window's words (28 keys of
  16,115: details text and the "Counted:" line; no kept flag, no reason, no private line). Accepted.
- The month a row was opened in may stand unmarked beside a whole title when the result's window is that one
  month. This exception was added after an in-sample refusal.

Left open, said before the runs:
- A row whose first line is over 200 characters keeps its cut title and the old note. The test library has no such
  row, so no run can see this. Real captions are long; the share of real rows was not measured.
- A part of a whole title quoted with its figures is still refused. "What did it say" is answered with the whole
  title, or without its figures.
- "Which channels did I drop" is still answered over four weeks; a channel's name that is also an area's name still
  resolves to the area. Both are the model's choice of arguments, not a tool fault.
- A sentence with no marker and no figure sets no private line (old).
- A true sentence naming an item by "title #tag" before its marker is refused (old; seen once in the repeats).

Checks on the frozen build, rerun by me:
- The independent checker's four sentence sets (872 verdicts): only the releases listed above.
- Saved forms of 40 run folders (1,774 forms, 5,104 sentences), values: 0 released, 0 refused against the old tip;
  the private line on in 6 answers and off in 1. Full and cells: byte for byte the old tip's.
- Whole suite: 6,446 passed, 2 skipped. One pinned test of the last round was changed on purpose (a reword may name
  an item row by its own path).
- Privacy scan of the merged diff: no caption; 34 generic single words and short phrases.

Frozen for the runs:
- Code: commit 0fe5b78 on experiments/search-loop. Run from a detached worktree of it.
- Model claude-haiku-5-5. Strict tool grammar off. Check: values, default rules, no switch set.
- The default rules, 20: the 18 of the last freeze, and private_behind and whole_title.
- Prompt brain_v4d only. Twice on set A (65 messages), twice on set H (53 messages). Order: A, A, H, H. One run
  at a time, nothing else on the machine.
- Marking: blind packets by script (seed 33033), six readers (three groups, two each), a tally that settles from
  the rows, an independent recount. The recount settles every sentence any reader marked false or firm before it
  opens the tally. The rubric's five lines of 27 Nov decide the split calls of last time.
- Privacy is reported both ways (a carried unlock as no fault, and as a fault) until the founder answers.
- The gate on half B is run once if all four runs meet every bar but one at most, none has more than 2 settled
  false sentences, and tally and recount agree on that. Otherwise I report and ask.
- Watch in the runs: answers that fall to code's own lead, rewords, malformed forms, and the slow end (p90).

Claude spend to here: about $7.70 of $25.

## Four runs of the frozen build, marked blind: the gate not run (27 Nov 2026)

The condition written before the runs is not met. Tally and recount agree on that, with privacy counted either
way. Half B was not opened and the gate was not run.

The four runs (commit 0fe5b78, brain_v4d, values check, default rules), rates as the two readers' average:

| Bar | A run 1 | A run 2 | H run 1 | H run 2 |
|---|---|---|---|---|
| Settled false sentences (at most 1) | 3, fails | 2 (tally) or 4 (recount), fails | 0 | 0 |
| Wrongly based, firm, per 100 sentences (at most 6) | 0.5 | 2.1 or 1.1 | 2.1 or 1.4 | 3.2 or 2.5 |
| Privacy faults (0): carried unlock as no fault / as a fault | 0 / 1 | 0 / 1 | 0 / 0 | 0 / 0 |
| Median seconds (at most 8) | 6.19 | 6.20 | 5.76 | 5.88 |
| Slow end, p90 seconds (at most 11) | 9.10 | 9.34 | 9.03 | 7.98 |
| Answers the question (at least 80%) | 96.9% | 95.4% | 91.5% | 94.3% |
| Poor (at most 20%) | 8.5% | 13.1% | 11.3% | 12.3% |
| Good (at least 25%) | 26.2% | 29.2% | 34.0% | 25.5% |

- Both set H runs meet every bar. Both set A runs fail the false bar, and run 1 has more than 2.
- Good is close to its bar in two runs (26.2% and 25.5%). One reader alone is under 25% in each.
- Marks are complete (472 of 472). Readers agree on the grade in 80% of answers (kappa 0.63).
- Code's own lead went out twice in 236 answers. Both are poor answers. One followed a provider timeout. The other
  followed a true sentence the check refused, with no time left for a reword.
- The check refused 19 sentences. Several were right catches (a wrong date, a wrong count).

The false sentences:
- Five that tally and recount both settle false, all on set A, all of one kind: a scope's span said wrongly.
  - Three say the saves run "from 3 October 2026 to 30 October 2026". The last save is on 10 October.
  - Two say of Instagram "your export ends on 15 October, so that is the whole of it". The export also holds saves.
- Two more that the recount settles false and the tally settles wrongly based, firm: a real row given the wrong
  rank ("the first was ... #77" when #76 was first; a 10-minute video named among the longest).
  Both readers had marked them false. The rubric did not decide this case. It does now (below).
- Two other settlements differ (firm against true, firm against lenient). No bar moves on them.

Where the saves sentence starts (read from the records, no model call):
- For "all your history" with a scope, the result's window starts on the scope's first row and ends where the
  export ends. No cell holds the day of the last row counted.
- So "from 3 October to 30 October" is the result's own pair of cells. The check passes it, marked or not.
- In one of the three, the first form cited a cell the check does not take, and the reword message named the
  window's two cells. The reword then passed with the false range.
- This is a tool fault: the result gives a frame that reads as the rows' span and never gives the rows' span.
- The Instagram sentence is different. The result said the first Instagram item of any kind was on 5 October. The
  model's "the whole of it" is its own judgement over a right result.

Was the build worse than last time, or the ruler stricter? Both, a little:
- Last round's set A runs had 2 and 0 settled false. The saves sentence was already there: written in 2 of 4
  answers to the same two messages, and sent in 1. This round it was sent in 3 of 4.
- The rubric's line that makes it false (a scope's span said as the whole record) was written between the rounds.
- So the last round's span fix did not remove this fault, and its new window words did not make it rarer here.

A correction to the last section. It said of the span words: "a bare saves span was said in 4 of 16 answers
before, 0 of 16 after". Those repeats covered four conversations. The two conversations where the fault shows now
were not among them. The claim holds for what it covered and not for the class.

What the runs show for the other fixes of the last round:
- A cut title said to be cut in the history: 0 of 236 answers. Whole titles were written in 7 sentences.
- No answer follows a title's words as an instruction.
- The private line: no fault. The topic's row: its name passed in both runs, but both answers still say only a
  limit, because the tool reads saved text only.
- The scope line beside a filter: no answer exercised it.

Privacy: no reader marked a fault. In both set A runs one follow-up answer names a private topic's channel under a
carried unlock. Counted as a fault, both set A runs fail a second bar. This is the founder's question and it now
changes a bar.

Kept as they are, and said plainly:
- Set H run 1 was kept though the run script flagged it. One turn had a provider timeout and went out as code's
  own lead; the failed request has no ledger row, which is what the flag saw. A person would have got that answer.
- Two readers printed a per-run summary file by accident (my fault: it lay in a folder they could list). It shows
  figures per run, nothing per answer. Both runs of a set are one build, so it cannot favour anything. One code
  could have been tied to its run; that sentence was settled from the record anyway.
- The packets' own description still said "four answers" where there were two.

A fourth split call, written after these marks and before any next run (also in the rubric):
- **A named row given a rank it does not hold.** To say a named row is the first, the last, the newest, the
  longest or the most, when the rows give that rank to another row, is false. It is the stricter reading. By it,
  set A run 2 of this round has 4 false sentences.

Next, by the rule written before the runs: report to the founder and ask. Not decided here: whether to spend one
more bounded round on the saves span (a tool fault) and run again, or to go on to step 2 with the gate pending.
Both sets are in sample for every fix so far. Only half B is not.

Claude spend to here: about $8.05 of $25.

## The saves span, fixed in the tool and merged; no new freeze (28 Nov 2026)

The fault of the four runs was one class, and its most frequent form started in a tool: a window of all their
history over a scope gave the scope's first day and the export's last day, and no day for the last row counted.
Now every result that counts rows gives the first and the last day of those rows, and such a window's words say
them ("the saves counted: 3 to 10 October 2026; your export ends on 30 October 2026"). DESIGN.md section 33 has
the build, an independent skeptic's findings, the repair and my acceptance. No prompt changed. No checker rule
was added or loosened.

What my own repeats show (16 runs of three conversations on each build; in sample):
- The false range was said in 14 of 32 first answers before and 0 of 32 after. The true range is said in 22.
- The cost: the model often writes the true span with no marker, the check refuses it, and one reword puts it
  right. That happened in 17 of those 32 turns and adds about 2 seconds to them. No answer fell back to code.
- Over one full pass of each set the cost is small: 1 such turn in 118. Medians 6.6 and 5.9 seconds, slow ends
  9.9 and 8.4. Both are inside the bars. No marking was done; this was a regression check, not a gate attempt.
- "That is the whole record", said of one platform's opens, is unchanged: 2 of 16 on each build. It is the
  model's judgement over a right result and was left alone.

Decided here:
- Merge the fix. A false sentence in about half of such answers is worse than a reword in about half of them.
- Do not let the unmarked span through the check. It would also let the right days be said of the wrong scope.
- If the reword cost matters later, change the window's words, not the check.

Known and left:
- The check still passes the false range if the model writes it. The fix is that no result offers it any more.
- Twelve false sentences marked on the new cells pass (the old hole: the check reads a value, not what is said
  about it). Each has a twin on the window's own cells that passed before.
- Asked windows and "lately" keep their old words. The second window of a compare gets no pair of cells.
- Full and cells modes refuse a citation of the new cells. Step 2 must run the values check, or keep the cells
  out in those modes.
- Two code leads in the full passes are other classes: a title that ends in a number right before its row
  marker, and a path that is no cell, each written twice in a row.

Still the founder's, unchanged: whether a private topic named in one turn stays unlocked for the next; and
whether to run four runs and blind marks again, or go on to step 2 with the gate pending. Half B is unopened.
This code is not frozen for a run and has no blind marks.

Claude spend to here: about $8.46 of $25.
