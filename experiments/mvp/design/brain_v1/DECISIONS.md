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
