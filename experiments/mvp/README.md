# MVP skeleton (prototype)

Text a request and get cited answers from your own saved and watched posts: now, at a time you name, whenever you ask
again, or on repeat. Build plan and rules: `experiments/BRIEF-10.md`. How it works, in full: the document "Digest bot
MVP: how it works" (link in `experiments/STATE.md`). This is prototype code; it is rewritten after the first tester
sessions.

## Set up (once)

1. Python 3.12+ and the packages: `python3 -m pip install -r experiments/demo/requirements.txt -r experiments/mvp/requirements.txt`
2. Put the library folder under `data/` (your `data/all`, or a library the demo built from exports).
3. Create `data/mvp/people.json` (outside git):
   ```json
   {"+15551234567": {"name": "Derrick", "library": "data/all", "timezone": "America/New_York"}}
   ```
   The key is the phone number (with country code) or the Apple Account email the person texts from. For the test page
   any name works as the key. `library` is read from the repo root. The bot checks every entry when it starts and
   stops with a clear message if a library or a time zone is wrong.
4. `export OPENAI_API_KEY=...` in the terminal that runs the bot. Never put keys in files.

## Test it without a phone

From `experiments/`:

```bash
python3 -m mvp.bot --channel web
```

Then open `http://127.0.0.1:8765`. It is a message thread with the bot, on this computer only:

- Type as any person in `people.json`. Replies appear as they would in Messages.
- Tap 👍 or 👎 under a reply: that is a tapback. A 👍 on a preview starts the rule.
- **The bot's clock**: "Jump to the next timed send" fires the next rule now. "Forward 1 hour" and "Forward 1 day" move
  time on. A jump of more than 2 hours past a send skips it, exactly as if the bot had been switched off.
- "Start over" clears that person's rules, history and thread.

It is the same handler, search, checks and scheduler as the iMessage channels; only the transport differs. It keeps its
own store (`data/mvp/webtest.sqlite`), so nothing you do there touches real testers' rules. The first reply after a
start can take about a minute while a large library loads; the page says so.

Other ways to test:

- **In the terminal**: `python3 -m mvp.bot --channel console`. Type a message; an empty line runs due rules.
- **Real iMessage, alone, on your Mac**: `python3 -m mvp.bot --channel mac --self-chat +15551234567` (your own number
  or Apple Account email, also a key in `people.json`). Open Messages, text yourself, and the bot answers in that same
  thread. Its replies start with 🤖 so that it never answers itself. This mode has been tested against a fake database
  only, not on a real Mac: watch the first few messages.
- **Offline tests** (no API calls): `python3 -m pytest -q mvp/tests`
- **A set of test requests on a library**: `python3 -m mvp.run_requests ../data/mvp/requests.jsonl ../data/all`
  writes the conversation and a grading sheet to `data/mvp/eval/...` (outside git) and prints counts only.
- **The interpreter on the rule evaluation set** (live model calls, about $0.003 a case at list price):
  `python3 -m mvp.eval_rules mvp/evalset/rules_dev_timing.jsonl [--limit N] [--ids t-dev-001,...] [--debug F]`
  prints one line per failed case and a total, and writes counts to `MVP_HOME/eval_rules/<file>.json`. The case texts
  are invented. The held-out half is run only by an evaluator who did not build the interpreter.

## Run it for real

- **This Mac's Messages app** (founders only): `python3 -m mvp.bot --channel mac`
  - System Settings › Privacy & Security › Full Disk Access: add the terminal app (to read `~/Library/Messages/chat.db`).
  - The first send asks to let the terminal control Messages: allow it.
  - Only people in `people.json` get answers. Group chats are ignored.
  - Use an Apple Account made for the bot if you can: a block by Apple would then not hit your own iMessage.
- **Sendblue** (outside testers): set `SENDBLUE_API_KEY_ID`, `SENDBLUE_API_SECRET_KEY`, `SENDBLUE_FROM_NUMBER`,
  `SENDBLUE_WEBHOOK_SECRET`, run `python3 -m mvp.bot --channel sendblue`, and expose `127.0.0.1:8787` with a tunnel
  (`cloudflared tunnel --url http://127.0.0.1:8787`). Register `https://<tunnel>/sendblue/receive` as the `receive`
  webhook with the same secret in Sendblue's dashboard. Start the tunnel in its own terminal and leave it running: a
  quick tunnel gets a new address each time it starts, and the webhook must then be registered again. The channel has
  never run against a real Sendblue line: check the first send, and set `SENDBLUE_API_URL` if the address is wrong.

## See what happened to a message

```bash
python3 -m mvp.trace            # the last 15 messages: status, intent, time taken, the run behind the reply
python3 -m mvp.trace 4567       # one person, by the end of their number
python3 -m mvp.trace --sends    # timed sends: sent, missed, held, failed
python3 -m mvp.trace --web      # the same for the test page's store
```

It prints no message text and only the last 4 characters of a handle.

## Kill switch

Stop the bot with Ctrl+C. A timed send that was going out at that moment is marked `unknown` and is not sent again.
To pause one person: `UPDATE people SET paused=1 WHERE handle=...` in `data/mvp/mvp.sqlite`. "delete my data" requests
are listed in `data/mvp/deletions.jsonl`; a founder removes that person's library folder and message thread, then
confirms to them. A person listed there is not added back from `people.json`.

## What is where

| File | Job |
| --- | --- |
| `bot.py` | Start-up: channel, store, people, engines |
| `runtime.py` | The run loop: message log, workers (one person at a time per person), joining quick texts, scheduler thread |
| `core.py` | Message handler, executor, scheduler rules. The only code that sends |
| `interpret.py`, `prompts/interpret_v3.md`, `schema.py` | Message to a validated form for every intent (RuleSpec v 2); temperature 0, a seed, a 6-hour cache |
| `eval_rules.py`, `evalset/` | The rule evaluation runner and the development half of the set |
| `todos.py` | To-do lists, due reminders, undo records, library counts |
| `actions/` | The action registry: what a rule's `do` may name, and its params |
| `retrieve.py`, `engines.py`, `libview.py` | Candidates from the person's own library (Q8 search, filters) |
| `compose.py`, `prompts/compose_v1.md` | The model picks; code enforces the reliability rules (BRIEF-10 section 5) |
| `render.py` | The message text |
| `schedule.py` | Every date and time (every timing form, seeded random moments, quiet hours), in the person's zone |
| `scheduler.py` | Timed sends and their guards: skips, snooze, quiet hours, daily limit, retries and holds |
| `store.py`, `llm.py` | Records; model calls, the cost ledger and the caps |
| `channels/` | Test page (`web.py`, `web_page.html`), terminal, Mac Messages, Sendblue |
| `trace.py`, `run_requests.py` | What happened to a message; a batch of test requests |
| `tests/` | 102 offline tests |
