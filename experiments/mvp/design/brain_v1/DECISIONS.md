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
