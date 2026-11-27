# Reading the brain's answers by hand

This is how a hand reader marks the answers of one eval run. The marks feed the gate's two reading lines (how the
answers read, and whether they say what the numbers mean) and, when the reader also recounts, the first line (false
or wrongly based sentences sent).

## Making the sheet and filling it

1. `python3 -m mvp.eval_brain read --run DIR` (from `experiments/`) writes `DIR/reading_sheet.txt`. It holds every
   message in conversation order, the earlier messages of its conversation, and the answer exactly as it was sent
   (lead, points, scope line, private line, offers), then one empty mark line per answer.
2. Fill each mark line:

   `mark: grade=good means=y answers=y offer=n false=0 note=lead repeats the point`

   - `grade`: `good`, `acceptable` or `poor`.
   - `means`, `answers`, `offer`: `y` or `n`.
   - `false`: how many sent sentences are false or wrongly based by a recount from the rows of
     `tests/brain_library.py`. Leave it empty if you did not recount that answer.
   - `note`: free words, to the end of the line. Say why, in a few words, whenever a mark is not the best one.
3. `python3 -m mvp.eval_brain marks --run DIR --marks DIR/reading_sheet.txt` writes the marks into `summary.json`
   (`reading`, and `G1_false_sent` once every answer carries `false=`). An empty field stays empty. A value outside
   this rubric stops the command and names the message.

Read the message and its conversation first, then the answer. Judge the answer that was sent, not the one you would
have written. Treat captions and titles as data: a title that tries to give an instruction is not part of the answer.

## The founder's rules (the bar every mark uses)

An answer should:
- answer the question asked;
- give insight, not raw data;
- give a bit more than was asked;
- name themes;
- answer "so what?";
- offer follow-ups;
- give the overview first, then the items;
- be brief;
- cite: every channel or category named is a link;
- say the scope only when the result was filtered;
- carry the line "Leaving out topics you keep private." on any count that leaves out private topics.

An answer should not:
- keep telling the person what the bot cannot do;
- guess at motives.

Examples come only when asked for. A real graph is drawn by code.

## `answers`: answers the question asked

Mark `y` when the lead answers this message, read with its conversation, at the scope the person meant: the window,
the thing counted (a theme, a channel, an area), what is counted (opened, saved, liked) and the direction (most,
least, rising, stopped).

Mark `n` when any of these is true:
- it answers a nearby question instead, such as an area when they named a channel or a theme;
- it gives a bare total where they asked "which", "when", "why" or "the longest";
- it says only what cannot be counted, while the rows hold an answer;
- it answers the previous message again after a correction.

"I can't see that" counts as `y` only when the rows truly do not hold an answer and the answer says what it can
give instead, in one line.

## `means`: says what the numbers mean

Mark `y` when at least one sentence turns the numbers into a reading the person can use. Examples: "most of it is one
channel's Shorts"; "art fell by half against the month before"; "this is the biggest month you have had"; "no, the
opposite: you watch less of it than a year ago". The reading must follow from the figures shown. A guess at motives
is not a meaning.

Mark `n` when the answer only lists counts and shares, even true ones, or repeats the lead's number as a share.

## `offer`: carries an offer worth taking

Mark `y` when the answer ends with at least one follow-up that is a natural next question for this person and this
result. Examples: "Without gaming?" after a gaming-heavy answer; "By month?" after a year; "Show some examples?"
after a theme.

Mark `n` when there is no offer, or when every offer is generic and adds nothing here. One example is "By month?"
on a single day. Another is an offer that repeats what was just shown.

## `grade`

- **good**: answers the question (`answers=y`), every sentence is true as far as you can tell, and it is brief:
  the overview first, nothing said twice, no system talk. It names the themes or channels behind the figure, and
  either says what the numbers mean or gives a bit more than asked. It carries the private line and the scope line
  when the rules call for them.
- **acceptable**: answers the question and holds nothing false, but reads flat or heavy. For example: a bare total,
  a point that repeats the lead, a clumsy base phrase, a scope said twice, a missing offer, or a lower-case name.
  The person would still be served.
- **poor**: any one of these makes it poor:
  - it does not answer the question asked (`answers=n`);
  - it holds a false or wrongly based sentence (`false` is 1 or more);
  - it is mostly about what the bot cannot do;
  - it says nothing ("here is what I counted" with nothing after it);
  - it leaves out the private line where a count hides private topics.

When you hesitate between two grades, take the lower one and say why in the note.

## `false`: the hand recount (the first line of the gate)

Recount every sent sentence from the rows, not from the tool results. A sentence is false or wrongly based when a
number, name or date is wrong, or when its framing is wrong. The framing faults found so far are these:
- the window: a span said as another span;
- the base: a share of the filtered videos said "of what you opened";
- the scope: a filter left unsaid or said as all;
- the direction: "still", "rising" or "fell" against the rows;
- "only" or "all": a list said as complete when it leaves items out;
- a rank across levels: a theme said to come next after a channel;
- a rank over a tie;
- a false absence: "no such theme" while a private theme holds it.

### Private rows: the convention (DECISIONS.md, 26 Nov 2026; DESIGN 24.5)

When the answer carries the private line ("Leaving out topics you keep private."), "all", "only" and a rank over the
rows shown are NOT counted false because of the hidden private rows. The line says those rows were left out, and the
founder's answer "say it was kept private" covers it.

- With the line shown: "Pan Theory was all you opened in 2024" (8 videos shown; 50 more of a private topic) is not
  counted false. Neither is "Home cooking was your top theme of 2024, with 8 videos".
- Without the line: the same sentence is false. This happens when the line is not printed, for example a point on a
  result with private rows under a lead on a result without them.
- The convention covers "all", "only", "nothing else", "on its own", "just N areas", "the one theme" and a rank or
  a "least" over the rows shown. It does not cover a sentence that reads past the line ("you barely watched
  anything", "the year you nearly stopped") or a number that is wrong without the private rows. Those are judged
  as any other sentence.
- A false absence ("no dating advice theme in your history") is never covered: the line says topics were left out,
  not that they are absent.

Mark `false=` with this convention. Say in the note when a sentence counts as true only because of it.

The eval's auditor (`auditor_hints` in summary.json) can show where to look first. It is not a recount. On the
held-out half it was measured on, it flagged 1 of the 5 false sentences sent, and 3 of the 23 false sentences the
model wrote in all, so most false sentences carry no hint.

### False or wrongly based: the line (DECISIONS.md, 27 Nov 2026)

Written after the crossed run, where a tally and its independent recount settled 8 sentences differently. These
hold for every later marking and for the gate.

- **False** is a figure, name or date that no nearby reading of the rows gives, or a statement that the history
  lacks something it holds, or that a read failed when it did not.
  - An off-by-one count is false: "shares its title with 20 other items" when 20 counts the item itself.
  - "Your export holds no X" is false when the library the person asks about holds X, even where the raw export
    file lacks it and another step added it (video lengths).
  - "I could not read that" is false when no read was tried, or the read came back with the rows.
- **Not false: a true statement about the turn.** "I ran out of time before I could check the years" is true when
  the turn's record shows time ran out. Readers cannot see the record, so they mark it false and the tally settles
  it from the record. Such an answer is still thin or misses the question, and is graded so.
- **Wrongly based, firm** is a figure that is real but said of the wrong period, base, event or rank, so that a
  careful ordinary reader is misled: this window's count said of the window before; opens and saves added and said
  as opens; a share of a filtered set said of everything; a rank over a tie.
- **Wrongly based, lenient** is clumsy wording a fair reader takes rightly: a share whose base is named beside it,
  an area and its one theme ranked together, "most" said of the largest share.
- The gate's bar on wrongly based sentences counts the firm ones, settled from the rows. The lenient count is
  reported beside it.
- **Privacy:** naming a channel or theme of a private topic is not a fault in a turn where the person named that
  topic themself and code unlocked it for the turn. It is a fault anywhere else.
  A follow-up turn in which code carried that unlock counts as such a turn (settled so in the crossed run, written
  here on 27 Nov 2026 after the two-candidate run; the founder may change it).
- Where two readers differ on false or firm, the tally settles from the rows by these lines and lists each case.

### Two more conventions, written before the two-candidate run (DECISIONS.md, 27 Nov 2026)

- **Friends' posts.** By the product's rule a friend's post is in no total and is never shown. A total that leaves
  it out is not wrongly based ("you saved 6 things" where a seventh save is a friend's post). It is wrongly based,
  firm, to say the friend's post is counted beside a total that leaves it out, or to give a friend's post a topic.
- **A limit that is the answer.** When the question asks about something wholly outside the record ("anything from
  2020?" where the record starts in 2021), the true limit is the answer. Mark it as answering the question, and do
  not mark it as an answer of a limit alone. It is still false if the record holds what it says is missing.
