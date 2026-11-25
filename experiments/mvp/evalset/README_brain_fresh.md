# brain_fresh.jsonl: the fresh eval set of the chat core

Made-up messages over the made-up library of `tests/brain_library.py` (clock Sunday 22 November 2026, New York;
YouTube ends 30 October 2026, Instagram 15 October 2026). Written before any new prompt or design, so the next gate
has messages nobody has tuned on. 87 conversations, 123 messages, 122 of them plan tier. 35 of those are follow-ups
or corrections.

- Source: `eval/brain_fresh_a.py` (half A), `eval/brain_fresh_b.py` (half B), `eval/brain_fresh_dsl.py`.
- Build and check: `python3 -m mvp.eval.build_brain_fresh --write --report OUT.json` (from `experiments/`). It
  replays every reading through `brain.tools.call`. It recounts every fact from `rows()` with its own rules. It sets
  the tools' figures and windows against that recount (each difference is a finding), and checks the counts, the
  halves and the distance to `brain_plans.jsonl`.
- Test: `python3 -m pytest mvp/tests/test_brain_fresh.py -q`.

## Lock rule

Half A holds the ids where `int(sha1(id).hexdigest(), 16) % 2 == 0`. Half B holds the rest.

**Half B is locked.** It was written and checked once. After that, no builder, tuner or prompt writer reads it.
That means half B's lines of `brain_fresh.jsonl`, `eval/brain_fresh_b.py`, and any report or run output that quotes
half B messages. Only a run and its independent readers (judges, recounts) may open it. Anyone who tunes a prompt or
a design uses half A only.

`test_brain_fresh.py` pins the sha256 of half B's lines. If that test fails, half B was edited. Do not re-pin it.
Write a new fresh set, because an edited half B is no longer unseen. Half A may change, for example to fix a reading
after a tool change. The facts stay recounted by the build script, never copied from a tool.

- `--write` keeps half B's stored lines byte for byte, whatever the tools now give, and names by id only the half B
  conversations whose rebuilt line would differ. `--rewrite-half-b` exists only for the first write of a new set.
- The report and the printout give half B findings as id, kind, call and path only.
- If a tool learns to read something half B expects it to refuse (a part of a period, likes), add that id to
  `LAPSED_B` in the test. Do not edit the line.
- Messages tagged `tool_gap` have no reading that reaches their facts today. Score them apart.

## A line

`{"id": "N001", "half": "A", "messages": [{"n", "text", "tier", "tags", "readings", "facts", "good", "refuses"?}]}`

- `readings`: 1 to 3 acceptable readings, the preferred one first. Each is
  `{"rounds": [[{"tool", "args"}]], "window": {"r1": [start, end]}, "note"}`. The window is each result's own, as the
  tools resolved it.
- `facts`: `{"say", "value", "how"}`, counted from the rows by the build script.
- `good`: `{"means", "offer"}`.
- `refuses` (some messages): calls the tools must refuse today, with the error they gave: a part of a period, likes,
  a comparison after the export end.
- A follow-up runs with the window of the preferred reading of the message before (`same_as: "last"`), and with that
  reading's window words as the screen.
- Non-plan messages (tier `step2`) have a `why` and no readings.
