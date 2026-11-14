# Rule evaluation set

Cases for scoring the interpreter of the MVP bot (`experiments/mvp/DESIGN.md`, sections 1, 2, 5, 10 and 11). Each case
is one message a person sends, the situation the bot is in when it arrives, and the interpretation the bot should
produce. The set checks the form the interpreter returns, not the reply text.

## Files

| File | What it covers | Ids |
| --- | --- | --- |
| `rules_dev_timing.jsonl` | when and how often: once, schedules, random, windows, limits, pause, skip, snooze, quiet hours, time zones, clarify, two requests in one message | `t-dev-001` to `t-dev-059` |
| `rules_dev_content.jsonl` | what and where: filters, must-haves, details, outputs, acting on an answer, to-dos, profile, library status and statistics, feedback, refusals | `t-dev-001` to `t-dev-059` |
| `rules_dev_extra.jsonl` | added by the builders in the interpreter's improvement round, one or more cases per kind of misreading the evaluator reported: rule targets and scope, nested month weeks, two requests in one message, "twice a day", a one-time surprise, "this week" as an end, clarify keeping its days, running a rule now, a due time for an open to-do, finding things for the list, outputs of a new ask, things to avoid, a fact inside an ask; then fix pass 2 (x-dev-035 to 041): a level word as a must-have, a random pick, "too hard", another language, getting new saves in, "every day" with a routine, a to-do and a request together | `x-dev-001` to `x-dev-041` |

This is the development half: builders may read it. A held-out half in the same format, with the same context
names, is kept outside git and is run only by an evaluator who did not build the interpreter. Do not try to obtain it.

Ids are unique within a file, not across files (both files start at `t-dev-001`). Key results by file name and id.

All texts are invented. None comes from a real person's library or messages.

## Case format

One JSON object per line, UTF-8:

```json
{"id": "t-dev-021", "text": "put the first one on my calendar for saturday 6pm", "ctx": "after_ask",
 "expect": {"intent": "act_on_last",
            "fields": {"actions": ["calendar.add"], "pick_number": 1,
                       "params": {"time": "18:00", "date": "2026-11-14"}}},
 "accept_also": [],
 "note": "Calendar on a pick; Saturday is 14 Nov (calendar.add takes date, section 11)."}
```

| Key | Meaning |
| --- | --- |
| `id` | Case id. |
| `text` | The message the person sends, exactly as given. Pass it unchanged. |
| `ctx` | The situation the bot is in when the message arrives. One of the names in "Contexts" below. |
| `expect` | The expected interpretation, as a partial form (see "Matching"). |
| `accept_also` | A list of other partial forms that also count as right. Often empty. |
| `note` | What the case tests, for people. The runner ignores it. |

An expect object (in `expect`, in `accept_also`, or nested under `fields.also`) has up to five keys:

| Key | Compared with |
| --- | --- |
| `intent` | The interpretation's `intent`. Always present. |
| `when` | `spec.when` of the interpretation. |
| `content` | `spec.content` of the interpretation. |
| `do` | The action names in `spec.do` (the spec holds `{action, params}` objects; compare their `action`). |
| `fields` | Every other top-level key of the interpretation (`rule_number`, `pick_number`, `actions`, `until`, `also`, ...). |

For `clarify`, `spec` is the half-built form the bot keeps; `when` and `content` are compared with it as returned.

## Matching

A case passes when `expect` matches, or when any one object in `accept_also` matches. Apply these rules to every
expect object, including nested ones.

1. **Subset.** Every key listed must be present and match. Keys left out are free. Nested objects (`params`,
   `fields.when`, `fields.also`) also match by subset.
2. **After validation.** Compare against the interpretation after it has been validated and completed by code
   (defaults filled in, relative times resolved). So `content.source: "library"` matches a spec that left the
   default. Exception: the partial spec of `clarify`, which is compared as returned.
3. **Scalars** (strings, numbers, booleans) match exactly, except the stem fields in rule 7.
4. **`time` alias.** In every `when` object (`expect.when`, `fields.when`, and inside `also`), on both sides, turn
   `time: X` into `times: [X]` when `times` is absent or empty, then drop `time`.
5. **Sets.** These lists are compared as sets (order ignored, same members): `days`, `times`, `month_days`,
   `month_weeks`, `except_dates`, `kinds`, `platforms`, `extract`, `do`, `actions`, `todo_number`.
   `window` is `[from, to]` and is compared in order.
6. **Actions.**
   - `do`: `message.send` is implied. Add it to both sides before comparing, so `["email.send"]` means "email, plus
     the normal reply".
   - `fields.actions` (act_on_last): compared as a set of action names, with nothing implied. If the returned
     entries are objects, compare their `action` names.
   - `fields.params`: matched by subset against the interpretation's top-level `params`; if it has none, against the
     `params` of the `calendar.add` entry in `actions`.
7. **Stem fields.** For these, each expected string is one or more lowercase stems joined by `|`. A returned string
   matches when it contains any of the stems, case-insensitively.
   - Lists: `criteria`, `avoid`, `avoid_creators`, `avoid_collections`, `creators`, `collections` (in `content` or in
     `fields`). Each expected entry must be matched by some returned entry. Extra returned entries are allowed.
     Example: `"finish|complete|final"` matches "ends with a finished model".
   - Scalars: `lang`, `list`, `profile_note`, `todo_text`. Example: `"es|span"` matches `"es"`, `"es-MX"` and
     `"Spanish"`; `"grocer"` matches `"groceries"`.
8. **Empty list.** An empty list in an expect object means the returned list must be empty (or absent). Used for
   "tips" requests, which must get no criteria.
9. **`more` deltas.** For intent `more`, `fields.avoid`, `fields.criteria` and `fields.outside` match either the
   top-level key of the interpretation or the same key in its `spec.content`, whichever is present.
10. **`also`.** `fields.also` is a whole expect object for the second interpretation the first one carries. Match it
    against the interpretation's `also` with all of these rules. When two independent requests can run in either order,
    both orders are listed (one in `accept_also`).
11. **Never expected.** Search texts (`searches`), `goal`, the `text` of a note or a new to-do, `reply`, `question`
    and `item_ids` never appear in an expect object. They are free.

Score = share of cases that pass. Report it per file and per expected intent. The target in DESIGN.md section 10 is
90% on the held-out half.

## Clock and person (all contexts)

Unless a context says otherwise:

- Time zone `America/New_York`. Local now is **Thursday 12 Nov 2026, 14:07**.
- Quiet hours: one block, 22:00 to 08:00, every day. No snooze. Consent given, onboarding finished.
- Email: a verified address is on file, so `email.send` and calendar `.ics` files can run.
- Profile (given to the interpreter, section 5):
  - interests: cooking (level: comfortable home cook), Blender (beginner), home workouts (beginner), drawing and
    watercolor (beginner); none confirmed as advanced;
  - direction: "get good enough at Blender to finish a small scene each week";
  - prefs: none (no avoid words, no tools listed, no `exclude_kinds` or `exclude_platforms`).
- Library: Instagram and YouTube items, last import 2 Nov 2026. The interpreter is not given a list of items, creators
  or collections; names in the cases are invented.
- No rules, no to-dos, no waiting preview, no last answer, no open question.

Defaults the cases assume when a person names a part of the day: morning 08:00, lunch or noon 12:00, afternoon
15:00, evening or night 19:00. Section 11 defaults: "twice a day" 08:00 and 20:00; three times 08:00, 13:00, 19:00;
"once a month" with no day is today's day (the 12th); "a couple of times a week" is 2 and "a few" is 3.

## Contexts

Each context is the clock and person above plus exactly what is listed. Rules are numbered as the bot lists them to
the person (the interpreter sees them with their numbers, goals, described timing, status and spec).

### `none`
Nothing more.

### `late_evening`
As `none`, but local now is **Thursday 12 Nov 2026, 21:40**.

### `one_rule`
One active rule:
1. "a pasta recipe for Friday dinner": `when {type: schedule, days: [FRI], times: ["19:00"], every_weeks: 1}`,
   `content {source: library, count: 1}`, `do [message.send]`. Created 1 Nov 2026. Last sent Fri 6 Nov 2026 19:00.

No last answer in the thread.

### `two_rules`
Two active rules:
1. The pasta rule of `one_rule`, unchanged.
2. "a short home workout": `when {type: schedule, days: [MON, TUE, WED, THU, FRI], times: ["08:00"], every_weeks: 1}`,
   `content {source: library, count: 1}`, `do [message.send]`. Created 3 Nov 2026.

No last answer in the thread (the interpreter is not told about earlier sends).

### `after_ask`
No rules. The bot's last answer, sent at 14:02 today in reply to the person's ask "quick chicken and rice dinner
ideas", was about "quick chicken and rice dinners", with 3 picks numbered 1 to 3, not sent by a rule:
1. One Pot Chicken Rice (an Instagram reel the person saved)
2. Hainanese Chicken Rice (a YouTube video in a playlist)
3. Chicken Fried Rice in 15 Minutes (an Instagram reel sent to self)

### `after_rule_send`
The rule of `one_rule` (rule 1, pasta, Fridays 19:00). The bot's last answer is the send of rule 1 on
Fri 6 Nov 2026 19:00: 1 pick, "Lemon Garlic Spaghetti" (an Instagram reel). The interpreter is told the last answer
was sent by rule 1. Nothing has been said in the thread since.

### `preview_open`
No active rules. The person wrote at 14:05 "send me a pasta recipe every friday at 7pm". The bot showed a preview of
that new rule and asked them to reply YES to start it. The waiting spec:
`when {type: schedule, days: [FRI], times: ["19:00"], every_weeks: 1}`, `content {source: library, count: 1}`,
`do [message.send]`. A message that changes this rule returns `new_rule` with the whole changed spec and
`edits_pending: true`.

### `has_todos`
No rules. Three open to-dos in the default list ("todo"), no due times, numbered as the bot shows them:
1. buy basil
2. call the landlord
3. book dentist appointment

### `after_write`
As `has_todos`, plus one write 2 minutes ago: at 14:05 the person sent "add pick up dry cleaning to my list" and the
bot replied that it added to-do 4, "pick up dry cleaning", to the default list. That add is the last write, inside the
10-minute undo window (section 11).

### `clarify_open`
No rules. At 14:05 the person sent "every sunday send me a study tip until the end of the semester". The bot answered
with intent `clarify`: it kept the half-built form
`when {type: schedule, days: [SUN], times: ["09:00"], every_weeks: 1}`, `content {source: library, count: 1}`,
`do [message.send]`, with `when.until` missing, and asked one question: "When does your semester end?". The next
message is expected to complete that form.

## Vocabulary the cases use

All names come from DESIGN.md sections 1, 2 and 11, plus the `Interpretation` fields in `schema.py` that the design
keeps (`rule_number`, `timezone`, `all_rules`, `edits_pending`, `feedback`, `pick_number`, `question`, `avoid`,
`reply`).

- Intents: `new_rule`, `ask`, `follow_up`, `more`, `change_rule`, `run_rule`, `skip`, `list_rules`, `pause`, `resume`,
  `stop`, `feedback`, `set_timezone`, `delete_data`, `help`, `confirm`, `decline`, `unsupported`, `chat`, `todo_add`,
  `todo_list`, `todo_done`, `todo_remove`, `todo_due`, `act_on_last`, `profile_show`, `profile_update`,
  `set_quiet_hours`, `snooze`, `set_email`, `clarify`, `undo`, `library_status`, `library_stats`.
- `when` keys: `type` (`now`, `once`, `schedule`, `random`, `on_request`, `new_items`), `date`, `time`, `times`,
  `in_minutes`, `days`, `every_weeks`, `every_days`, `every_months`, `every_hours`, `month_days`, `month_weeks`,
  `window`, `per`, `count`, `start`, `until`, `max_sends`, `except_dates`, `tz`.
- `content` keys: `source` (`library`, `note`, `todos`, `recent`, `items`), `kinds`, `platforms`, `creators`,
  `collections`, `avoid_creators`, `avoid_collections`, `count`, `extract`, `criteria`, `avoid`, `since_days`,
  `saved_after`, `saved_before` (exclusive), `order`, `outside` (`none`, `some`, `only`), `exclude_sent`, `style`.
- Actions: `message.send`, `email.send`, `calendar.add` (params `date`, `time`, `duration_min`, `title`), `todo.add`.
- Top-level fields: `rule_number`, `all_rules`, `edits_pending`, `timezone`, `until`, `in_minutes`, `clear`, `start`,
  `end`, `count` and `date` (skip), `skip_next` (run_rule), `feedback` (`up`, `down`, `more`, `less`, `harder`,
  `easier`, `done`, `hide`), `pick_number`, `avoid`, `criteria`, `outside` (more), `actions`, `params`,
  `answer_ref`, `when` (act_on_last, type `once`), `todo_text`, `todo_number`, `due`, `list`, `what` (`pick`,
  `ingredients`), `also`, `lang`, `profile_note`.

Formats left open by the design are not tested: `due` of a to-do, `snooze.until`, `answer_ref` when it is "last".
Quiet-hour bounds are `"HH:MM"` strings.
