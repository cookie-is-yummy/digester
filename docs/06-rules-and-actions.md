# 06 · Rules and actions

Users say what they want in plain language. We turn it into a **rule**: *when* something happens, get some *content* from the processor, and *do* something with it. The LLM fills in the form; code validates it and acts.

| Part | Owner |
| --- | --- |
| Interpreter (natural language → RuleSpec) | Derrick |
| Content (processor query requests) | Derrick |
| Triggers, scheduler, executor, output actions, action registry | Eason |
| RuleSpec schema | Both (contract change = both review) |

## RuleSpec (Proposed, v1)

```json
{
  "v": 1,
  "when":    { "type": "schedule", "cron": "0 9 * * MON", "timezone": "America/New_York" },
  "content": { "op": "search", "params": { "types": ["product"], "query": "gift ideas", "limit": 5 },
               "new_since_last_run": true },
  "do":      [ { "action": "email.send", "params": { "to": "self", "subject": "5 gift ideas for this week", "layout": "list" } } ]
}
```

### `when` (trigger)

| `type` | Fields | Example |
| --- | --- | --- |
| `now` | — | One-off request answered immediately |
| `once` | `at` (local datetime), `timezone` | "next Monday at 9" |
| `schedule` | `cron`, `timezone` | "every Monday" |
| `input_event` | `event` (`item.processed`), `filter` (types, themes, platforms, `share_text_contains`) | "when I share a recipe…" |
| `deadline` | `facet_field` (e.g. `opportunity.deadline`), `offset` (ISO 8601, e.g. `-P3D`) | "remind me 3 days before deadlines" |

### `content`

Any query API request (`05-processor.md` › Query API), plus:
- `new_since_last_run: true` → the executor excludes items already in this rule's `deliveries`. Without it, "5 gift ideas every Monday" sends the same five every week.
- `summarize: { style }` → pass the results through `summarize`.

### `do`

A list of actions from the **action registry**. Nothing outside the registry can run.

## Action registry

Each output action is declared once in `actions/registry.py`:

```python
ActionDef(
    name="calendar.create_event",
    integration="google_calendar",
    params_model=CreateEventParams,        # Pydantic: title, start, end?, all_day, description_template, reminders
    side_effects=True,
    needs_confirmation=True,               # first run of a rule always needs a confirmed preview
    supports_sync=True,                    # we can read back done/deleted
    tier_required="pro",
    max_per_day=10,
)
```

**MVP actions (Proposed):**

| Action | Integration | Notes |
| --- | --- | --- |
| `email.send` | Transactional email provider | Build first: no OAuth. Subject line carries the top action. One-click "done" / "not interested" links update state |
| `calendar.create_event` | Google Calendar (OAuth) | All-day events for deadlines, timed blocks in free slots later. Deleting the event dismisses the action |
| `instagram.reply` | Instagram messaging | Short confirmation after a DM share, inside the 24-hour window only |
| `document.append` | Our own Document (hub) | The default output once the hub exists; until then, stored and returned as JSON |

Later: Google Tasks (same Google sign-in), Notion, Apple Reminders (native app only), push notifications. Not possible via public APIs: Amazon wishlist (offer links instead). Avoid SMS for now (US carrier registration, per-message cost).

## Interpreter

1. Input: the user's text, their timezone, goals, theme names, connected integrations.
2. The LLM gets the RuleSpec JSON Schema, the action registry (names, params schemas, descriptions) and the query API vocabulary, and must return a RuleSpec. Prompt versioned in `ai/prompts/interpreter_v*.md`; call logged to `ai_runs`.
3. Validate with Pydantic. Check every action exists, the user has the integration connected and the tier allows it. Resolve relative dates ("next week") in the user's timezone in code, not in the LLM.
4. If something is ambiguous or unsupported, return a clarifying question or the closest supported alternative ("I can't add to your Amazon wishlist, but I can email you the links"). Log unsupported requests; they are the feature backlog.
5. **Preview:** the executor dry-runs the rule now (query only, no side effects) and shows what it would send. The rule becomes `active` only after the user confirms.

### Worked examples

| Request | when | content | do |
| --- | --- | --- | --- |
| "Email me the top 5 things to do in Berlin next week" | `once`, next Monday 09:00 local | `search {types: [place, idea], query: "things to do Berlin", limit: 5}` | `email.send` |
| "Text me 5 gift ideas every Monday" | `schedule`, `0 9 * * MON` | `search {types: [product], query: "gift ideas", limit: 5}`, `new_since_last_run` | `email.send` (offered instead of SMS) |
| "Based on what I watched recently, what do I know in physics?" | `now` | `search {query: "physics", since: -2 months, limit: 30}` + `summarize {style: "what you know + gaps"}` | `document.append` (returned in-app for now) |
| "When I share a recipe, add the ingredients to my calendar for Sunday" | `input_event`, `item.processed`, `types: [recipe]` | `get_items {ids: [trigger item]}` (recipe facet) | `calendar.create_event` |

## Executor

For each `rules.fire` message:

1. Load the rule; skip if paused. Create a `rule_run`.
2. Build the query request (exclude delivered items if `new_since_last_run`) and call the query API.
3. Nothing found → record and stop (no empty emails).
4. Render with the action's template (results always cite their source items).
5. Call the action with an **idempotency key** (`rule_id + trigger_ref`), so a retry never sends twice.
6. Record `deliveries` and, where an object was created, a `placement`.
7. On failure: retry with backoff; after N failures pause the rule and tell the user.

**Sync ("checked everywhere"):** placements are polled (or webhooked) for changes. Done or deleted in any connected tool → the item or action is marked done or dismissed everywhere we placed it.

## Safety limits

- Per-user caps on deliveries per day and actions per rule run.
- No recurring rule becomes active without a confirmed preview.
- An LLM never calls an action directly; only the executor does, with validated params.
- Third-party text (captions) is quoted as data in outputs, never followed as instructions.
- Every created object is reversible: "undo last run" deletes what that run created; disconnecting an integration offers to remove everything we created.

## UX questions in this area (for review rounds)

The bot's reply after a share (what it says, how fast, whether at all), the rule preview card ("Every Monday · 5 gift ideas · email. Look right?"), email layout and subject lines, and what "done everywhere" feels like. Each change is tested with 3 people before review.
