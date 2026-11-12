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
4. `export OPENAI_API_KEY=...` in the terminal that runs the bot. Never put keys in files. Optional:
   `export YOUTUBE_API_KEY=...` for YouTube lengths and descriptions and for new picks from outside the saves.

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
- **To-dos** and **Outbox** panels beside the thread: the person's lists (open and done), and every email and calendar
  file the bot wrote for them. Click one to read it (an email's HTML opens in a sandboxed frame). Without email settings
  nothing leaves the computer: try "email it to me" after an answer, give any address, then type the 6-digit code from
  the code email in the Outbox panel.
- **Exports** panel: an upload box that puts an Instagram export (JSON zip) or a Google Takeout zip into that person's
  inbox (`data/inbox/<person>/`); the bot adds it within a few minutes and says what's new. The panel lists the last
  imports.
- "Start over" clears that person's rules, history, thread, to-dos, email address and outbox (not their imports or
  library).

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
  Links are sent alone in their own message, but Messages only shows a preview for a sender in the person's contacts:
  put the bot's contact card (a `.vcf` file of our own) at a public https address and set `MVP_CONTACT_CARD_URL`; it
  is sent once, after the person agrees.

## Email, calendar and to-dos (outputs)

What an answer or a rule can do besides the chat message is the spec's `do` list, run once per answer after composing
(`outputs.py`): `todo.add`, `calendar.add`, `email.send`, then `message.send`. The reply says in one line per action
what was done; a failed action is said in the reply and never loses the answer; every action is recorded in the
`action_log` table. When `do` has no `message.send`, the thread gets one line saying where the answer went, unless the
email could not reach the person (no confirmed address yet, a failure, or an outbox they cannot open because the
channel has no Outbox panel): then the answer comes in the thread too, with that line.

- **Email** goes only to the person's own address, confirmed with a 6-digit code sent to it (15 minutes, 5 wrong tries,
  "new code" for another, at most 5 codes a day). Set `MVP_SMTP_HOST`, `MVP_SMTP_PORT` (587 STARTTLS, or 465 SSL),
  `MVP_SMTP_USER`, `MVP_SMTP_PASSWORD` and `MVP_SMTP_FROM` in the terminal that runs the bot (for example a separate
  Gmail account with an app password). Without them, or when a send fails, each email is written as an `.eml` file under
  `MVP_HOME/outbox/` and the reply says so. Every answer email is kept there; a code email that SMTP sent is only
  listed, so the code is not left in a file. The address must be typed by the person (the model never supplies one),
  and "email this to my mom" gets the offer to email it to them so they can forward it.
- **Calendar**: a Google Calendar "add event" link in the reply (no sign-in) and an `.ics` file in the outbox, attached
  when the answer is emailed. One event per send, in the person's zone, 30 minutes unless they say otherwise.
- **Acting on an answer**: "email it to me", "add the first one to my calendar for Saturday at 10", "add its
  ingredients to my grocery list", "remind me of the second one tonight at 8" (a one-time rule that sends that pick
  again, with no new search).
- **The bot's contact card** for Messages link previews: `python3 -m mvp.contact_card --out bot.vcf` (name from
  `MVP_BOT_NAME`, number from `SENDBLUE_FROM_NUMBER`, or `--name` and `--number`). Host the file at a public https
  address ending in `.vcf` and set `MVP_CONTACT_CARD_URL`.
- **A new output** (Apple Reminders, Notion, …) is one new module in `actions/` with a `run(ctx, params)` function
  that returns an `Outcome` (`actions/base.py`), plus one entry in `REGISTRY` in `actions/__init__.py` (its params
  model, what it needs, its module name and its order). Nothing else changes: specs are validated against the registry
  and the executor runs whatever the registry names.

## New picks from outside the saves, and keeping the library fresh

- **Outside picks** (`outside.py`): when someone asks for new things ("…and show me a few new ones from outside my
  saves", "only new stuff, not from my saves: sourdough"), the answer gets a block "Not from your saves, but close to
  them:" after the library picks (or only that block). YouTube only: one official `search.list` call with the
  person's own words (code keeps only words from their message), checked by one `videos.list` call; the first 3 that
  are public, embeddable, not for kids, not live and not already in their library, in YouTube's order, with YouTube's
  own title and channel and the length. No model reads or rewords them; they are never kept with the answer or counted
  as sent picks. Never for personal topics (health, relationships, money, religion, politics, sexuality). Limits: 80
  searches a day for everyone, 5 per person, a search text reused for 24 hours. Needs `YOUTUBE_API_KEY`;
  `MVP_OUTSIDE=0` switches it off. When it cannot serve a request, the reply says why in one line.
  Before anyone outside the founders gets these: a terms page linking YouTube's Terms of Service and a privacy note
  naming YouTube API Services (DESIGN.md section 11).
- **The inbox** (`refresh.py`): `MVP_INBOX` (default `data/inbox/`) holds one folder per person (the handle's letters
  and digits, e.g. `data/inbox/15551234567/`). Every `MVP_INBOX_MINUTES` (3) the scheduler takes any file there that
  has not changed for a minute: an Instagram export (JSON, zip or folder) or a Google Takeout zip with YouTube. It is
  imported with the demo's importer into a new library beside the old one (`MVP_LIBRARY_ROOT` to put it elsewhere),
  with the export's `messages` folder left out unread. The search vectors are built by the demo engine's `prepare`
  (embeddings only); an import whose estimated cost is over `MVP_IMPORT_CAP_USD` (default $1.50) is refused. Only
  when the build succeeded is the person switched to the new library (the old folder is kept; a restart keeps the
  switch while `people.json` still names the old one); they get one message with the counts, and their "when I save
  something new" rules run once on the new items. An imported file is deleted; a refused or failed one goes to
  `<inbox>/<person>/.failed/`. Do not drop a real export there before the founders agree.
- **"Did my export come in?"** answers with the last import, items by source, how old the newest item is, when the
  next export is due and the export links. `refresh.offer_export_routine()` gives the export steps and offers the
  reminder rules (every 4 weeks for Instagram, every 2 months for YouTube); the onboarding slice sends it. A fully
  automatic export is not available for US accounts: the person still requests each export and puts the file in
  the inbox.

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
| `actions/` | The action registry (`__init__.py`: names, params, needs, module, order) and one module per action: `message.py`, `email.py` (SMTP or the outbox), `calendar.py` (Google link and `.ics`), `todo.py` (picks or ingredient lines on a list); `base.py` holds what each action gets and returns |
| `outputs.py` | Runs a spec's `do` after composing (once per answer, logged, one line each in the reply); acting on the last answer now or later; the email address and its 6-digit code |
| `contact_card.py` | Writes the bot's `.vcf` contact card, for the founders to host |
| `retrieve.py`, `engines.py`, `libview.py` | Candidates from the person's own library (Q8 search, cached ranked lists, filters, orders, recent and fixed items) |
| `ytinfo.py` | A YouTube candidate's length and description from the official `videos.list` (`YOUTUBE_API_KEY`), kept at most 30 days |
| `outside.py` | New picks from outside the library: YouTube `search.list` with the person's own words, checked by `videos.list`; the sensitive-topic stop, the daily limits and the 24-hour cache |
| `refresh.py` | The inbox per person, the import (demo importer, without the messages folder), the cost cap, the library switch, new_items rules, library_status, and the export routine with its reminders |
| `compose.py`, `prompts/compose_v2.md` | The model chooses (verdicts clear / close / no, a backed "because", must-haves); code checks it; a cached answer per spec and candidates |
| `extract.py`, `prompts/extract_v1.md` | Ingredients, steps and key points from a pick's whole text, checked line by line, cached in the `facts` table |
| `render.py` | What the person reads, as parts (text and link): a channel that shows link previews sends each link alone; the same answer as an email (plain text and simple HTML) |
| `schedule.py` | Every date and time (every timing form, seeded random moments, quiet hours), in the person's zone |
| `scheduler.py` | Timed sends and their guards: skips, snooze, quiet hours, daily limit, retries and holds |
| `store.py`, `llm.py` | Records (including each answer as shown, the action log, the outbox, outside searches and imports); model calls, the cost ledger (an import's build is written there too) and the caps |
| `channels/` | Test page (`web.py`, `web_page.html`: thread, rules, To-dos, Outbox and Exports panels with the upload box), terminal, Mac Messages, Sendblue |
| `trace.py`, `run_requests.py` | What happened to a message; a batch of test requests |
| `tests/` | 220 offline tests |
