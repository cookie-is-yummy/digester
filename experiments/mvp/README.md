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

## Using a Claude model (DESIGN.md section 20; amendment A-020, Proposed; off by default)

The text calls can go to Claude instead of OpenAI. Nothing changes until you set a Claude model.

- The key: `export DIGESTER_ANTHROPIC_API_KEY=...` (or `ANTHROPIC_API_KEY`; the first one wins). Never in a file. The
  bot reads only these two names; other `ANTHROPIC_*` settings on the machine are ignored.
- The switch: a model name that starts with `claude-` goes to Anthropic. `MVP_MODEL=claude-haiku-5-5` moves every text
  call; `MVP_JUDGE_MODEL` and `MVP_ERRAND_MODEL` move the judge and the errand form on their own. Models priced:
  `claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5`.
- Check it once the key is set (one tiny call per Claude model you set, well under a cent each; prints time, tokens
  and cost, never the key): `python3 -m mvp.llm smoke` (or `python3 -m mvp.llm smoke claude-haiku-5-5`).
  `python3 -m mvp.llm path-test` sends one call with a made-up key and costs nothing: it should say
  `401 authentication_error` from `api.anthropic.com`.
- Compare models on every prompt's evaluation before switching anything (live calls; set the shared ledger and cap):
  `MVP_LEDGER_HOME=../data/mvp MVP_TOTAL_CAP_USD=30 python3 -m mvp.eval_models --models claude-haiku-5-5,gpt-5.4-mini
  --out <folder outside git> [--max-usd 3]`. One table comes out: `<out>/comparison.md`. `--dry` runs it on fakes
  ($0); `--list` shows every prompt and its evaluation. The judge is the same for every model (the bot's own,
  gpt-5.5, unless `--judge-model` names another), and the table names it. A second run needs a new `--out` (or
  `--overwrite`).
- Caps: Claude spend has its own total, `MVP_CLAUDE_CAP_USD` (default $10; the evaluations count toward it, so raise
  it for a run of several models). `MVP_TOTAL_CAP_USD` then counts only OpenAI and Gemini. The daily cap per person (`MVP_DAILY_CAP_USD`) counts all three.
- Optional: `MVP_CLAUDE_THINKING=adaptive` (default `off`), `MVP_CLAUDE_EFFORT` (default `low`),
  `MVP_CLAUDE_FALLBACKS=0` (Sonnet and Opus: no second model on a refusal).
- What stays where it is: search words and the library's vectors stay on OpenAI (`text-embedding-3-large`), and
  "ask the video" stays on Gemini. While a Claude model is set, the consent and "what leaves this computer" name
  Anthropic too.

## Test it without a phone

From `experiments/`:

```bash
python3 -m mvp.bot --channel web
```

Then open `http://127.0.0.1:8765`. It is a message thread with the bot, on this computer only:

- Type as any person in `people.json`. Replies appear as they would in Messages.
- Tap 👍 or 👎 under a reply: that is a tapback. A 👍 on a preview starts the rule.
- **The bot's clock**: "Jump to the next timed send" fires the next rule now. "Forward 1 hour" and "Forward 1 day" move
  time on. A jump of more than 2 hours past a send skips it, exactly as if the bot had been switched off (a one-time
  reminder or a to-do's reminder skipped this way gets one short "I was offline and missed ..." notice).
- **Profile** panel: what the bot knows about the person (interests with the level and whether they confirmed it,
  what they are working toward, preferences, email and whether it is confirmed, time zone, quiet hours, and the setup
  step while one is open).
- **To-dos** and **Outbox** panels beside the thread: the person's lists (open and done), and every email and calendar
  file the bot wrote for them. Click one to read it (an email's HTML opens in a sandboxed frame). Without email settings
  nothing leaves the computer: try "email it to me" after an answer, give any address, then type the 6-digit code from
  the code email in the Outbox panel.
- **Exports** panel: an upload box that puts an Instagram export (JSON zip) or a Google Takeout zip into that person's
  inbox (`data/inbox/<person>/`); the bot adds it within a few minutes and says what's new. The panel lists the last
  imports.
- "Start over" clears everything the bot holds about that person in the test page's store (rules, history, thread,
  profile, to-dos, email address, outbox, the list of imports) and runs the setup from its first message: the consent
  text, then the read of them once they reply "I agree". It leaves the inbox folder and the library folders on disk,
  writes no deletion line, and puts the person back on the library `people.json` names. "Clear rules, thread, to-dos
  and outbox" does the same but keeps the consent, so no setup runs.

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
  (also `rules_dev_content.jsonl` and `rules_dev_extra.jsonl`)
  prints one line per failed case and a total, and writes counts to `MVP_HOME/eval_rules/<file>.json`. The case texts
  are invented. The held-out half is run only by an evaluator who did not build the interpreter.
- **Requests for a kind of thing** (round 9, slice U; live, about $0.016 a request):
  `python3 -m mvp.eval_kinds mvp/evalset/kinds_dev.jsonl ../data/all --out <folder outside git>` runs 16 invented
  requests, each as a fresh test person, and writes counts only to `counts.json` (things shown, what the details model
  returned and marked "yes", what code left out and why, sources by verdict, the kind of answer, cost), the replies to
  `transcript.md` and a sheet to count how many shown things are truly of the kind (both stay outside git).

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
  "new code" for another, at most 5 codes a day). On Messages and Sendblue, where nobody can open the outbox, a code
  email that could not be sent is not kept or counted, and without SMTP the address is not asked for. Set `MVP_SMTP_HOST`, `MVP_SMTP_PORT` (587 STARTTLS, or 465 SSL),
  `MVP_SMTP_USER`, `MVP_SMTP_PASSWORD` and `MVP_SMTP_FROM` in the terminal that runs the bot (for example a separate
  Gmail account with an app password). Without them, or when a send fails, each email is written as an `.eml` file under
  `MVP_HOME/outbox/` and the reply says so. Every answer email is kept there; a code email that SMTP sent is only
  listed, so the code is not left in a file. The address must be typed by the person (the model never supplies one),
  and "email this to my mom" is a draft the person sends themselves (round 9, below), never their own address.
- **Calendar**: a Google Calendar "add event" link in the reply (no sign-in) and an `.ics` file in the outbox, attached
  when the answer is emailed. One event per send, in the person's zone, 30 minutes unless they say otherwise.
- **Acting on an answer**: "email it to me", "add the first one to my calendar for Saturday at 10", "add its
  ingredients to my grocery list" (also "put what I need to buy on my shopping list"), "remind me of the second one
  tonight at 8" (a one-time rule that sends that pick again, with no new search).
- **The bot's contact card** for Messages link previews: `python3 -m mvp.contact_card --out bot.vcf` (name from
  `MVP_BOT_NAME`, number from `SENDBLUE_FROM_NUMBER`, or `--name` and `--number`). Host the file at a public https
  address ending in `.vcf` and set `MVP_CONTACT_CARD_URL`.
- **A new output** (Apple Reminders, Notion, …) is one new module in `actions/` with a `run(ctx, params)` function
  that returns an `Outcome` (`actions/base.py`), plus one entry in `REGISTRY` in `actions/__init__.py` (its params
  model, what it needs, its module name and its order). Nothing else changes: specs are validated against the registry
  and the executor runs whatever the registry names.
- **Round 9, what an outward action may do** (DESIGN.md section 16.D): each registry entry can say whether it reaches
  outside (`outside`), how it is undone, whether it needs the person's "send" on the exact text (`confirm`), a daily
  limit (`max_per_day`), whether a rule or the model may name it (`in_rules`, `from_model`) and whether only the
  operator may run it (`who`). Set `MVP_OPERATOR` to your own handle (as in `people.json`) to be the operator;
  unset, nobody is. Tests: `tests/test_round9_registry.py`.
- **Round 9, emails to other people** (DESIGN.md section 16.A, `drafts.py`): "email my landlord that the kitchen sink
  is broken", "send the second one to sam@example.com", "draft an email to Sam about the second one" are read by code.
  The bot writes the email (the model writes it when `MVP_DRAFT_MODEL` is not `0`, and code checks every name, number,
  date and link against the person's own words and the checked post), shows it whole in three messages, and gives a
  `mailto:` link: the person checks it and presses Send in their own mail app. The recipient is only ever an address
  the person typed. "say ...", "subject: ...", "to: ...", "remove the link", "cancel", "show the draft", "sent".
  With a card the newest thing shown, "put this in my email" means the card (its link again, or the operator's
  Drafts folder); otherwise, with no email set up, it gives a link to yourself. The model's prompt is `draft_v2`
  (`draft_v1` kept); a brief that says its own claim is untrue gets no card.
- **The operator's own mailbox** (amendment A-013, Proposed): set `MVP_OPERATOR`, `MVP_MAILBOX_ADDRESS` and
  `MVP_MAILBOX_APP_PASSWORD` (an app password, in a 0600 file outside git that you source; never in the chat), and
  optionally `MVP_MAILBOX_SMTP_HOST`/`_PORT` and `MVP_MAILBOX_IMAP_HOST`/`_PORT` (Gmail, iCloud and Fastmail are
  known). Then the card says Reply "send": "send" on the version you were shown sends it from your address over SMTP
  after a 2-minute hold (`MVP_SEND_HOLD_MIN`; "undo" stops it), at most 5 a day; any change needs a new "send".
  "save it as a draft" puts it in your Drafts folder (IMAP: only LIST, APPEND, and for "undo" deleting that one
  message). Outlook.com cannot be used. Live eval of the draft prompt: `python3 -m mvp.eval_drafts --out <folder>`.
  Tests: `tests/test_round9_drafts.py`, `tests/test_round9_mailbox.py`.
- **Round 9, cancelling a subscription** (DESIGN.md section 16.B): "cancel my netflix", "I want to cancel my
  duolingo", "how do I get out of my gym membership". Code only (`cancel.py`, no model call): the merchant's own page
  and steps from `cancel_routes.json` (a link only when its help page was read on the date the file records, and for
  60 days after), the Apple or Google Play page, or a written notice as an email draft card (the link, or "send" for the
  operator's mailbox, once the member number is filled in); then a check reminder at the time the
  person names. It never signs in, never takes a password ("here's my password ..." gets a fixed line and the message
  is not kept) and never says it is cancelled. "Cancel my ... subscription" read by the model as "stop" stops no rule.
  To add a merchant, read its own help page and add an entry with `source_url` and `checked_on` (today's date). Tests:
  `tests/test_round9_cancel.py`.
- **Round 9, acting on a saved post** (DESIGN.md section 16.C, read by code, no model call): after an answer, "apply
  to the second one", "book it" (or "book a table at the first one for saturday at 7"), "buy the ingredients for the
  first one", "where can I buy it" give a short numbered menu of what the bot can set up (a deadline on the calendar
  and a reminder, a checklist from the post's own lines, Google Maps, a calendar hold, the shopping list); reply "1",
  "all" or "none". The bot never applies, books or buys, and says so. After a list of things: "add them all", "add
  2, 4 and 5", "remind me about all of them on friday", "put them all in my calendar", "what's number 4?". Tests:
  `tests/test_round9_postacts.py`, `tests/test_round9_things.py`.
- **Round 9, lists named after an app** (DESIGN.md section 16.D, C2): "add this to my Notion" (or Todoist, TickTick,
  Things, Trello, Google Tasks, Google Keep, Apple Notes, Evernote, OneNote, Microsoft To Do) goes on the list here,
  and the reply says plainly that the bot can't reach that app.
- **Round 9, Reminders and Calendar on the operator's Mac** (DESIGN.md section 16.D, C3; amendment A-014, Proposed):
  for the operator only, with the bot running on their Mac from Terminal (not over SSH). Text "connect my mac", make a
  calendar called "Digest" in iCloud, then text "check my mac" and click OK on the Mac's Automation prompts. After
  that "add the ingredients to my apple reminders" or "put it in my mac calendar" shows exactly what will be added and
  adds it only after "yes" (it reaches the phone through iCloud); "undo" within 10 minutes takes it out. "put my lists
  in reminders from now on", "put events straight in my calendar", "what are you connected to", "disconnect my mac".
  No password or token. Not on a Mac, the bot says so and uses the list here or a calendar link. Tests:
  `tests/test_round9_mac.py` (a fake `osascript`; no AppleScript has run on a real Mac yet).
- **Round 9, TickTick, Todoist and a webhook** (DESIGN.md section 16.E; amendment A-014, Proposed): for the operator
  only. Put `MVP_TICKTICK_TOKEN` (TickTick web app: avatar › Settings › Account › API Token), `MVP_TODOIST_TOKEN`
  (Todoist: Settings › Integrations › Developer) and/or `MVP_WEBHOOK_URL` (an https address from IFTTT, Make, Zapier or
  n8n) in a 0600 file outside git that you source before starting the bot; never in the chat (a key typed there gets a
  fixed line and the message is not kept). Then "add the ingredients to my ticktick", "push the second one to my
  automation", "send my list to todoist", "put my to-dos in ticktick from now on": the bot shows exactly what it will
  add (or send) and does it only after "yes"; "undo" within 10 minutes takes tasks out again (a webhook cannot be
  undone, and the bot says so before the yes). "connect my ticktick" gives the steps, "check my ticktick" tests the
  token, "disconnect my ticktick" stops it (REMOVE or KEEP). Tests: `tests/test_round9_tokens.py` (a fake HTTP opener;
  no request has reached the real services yet).
- **Round 9, "what did you do for me" and "do 2 for me"** (DESIGN.md section 16.F, code only): "what did you do for
  me" lists what the bot did in the last 7 days and what it only prepared ("I sent" only when the mail server took the
  email; a link it gave is "I can't see whether you sent it"), what is waiting and what can still be undone; "did you
  send the email to Maria" answers for one. On the to-do list, "do 2 for me" hands a to-do to the helper that fits (an
  email to-do opens the draft, a cancel to-do the cancel helper, a programme or a place from your saves the apply or
  book menu) or says plainly what the bot can't do and offers a reminder; a to-do is ticked off only once it is really
  done. Tests: `tests/test_round9_receipts.py`, `tests/test_round9_doit.py`.
- **Round 10, the foundation** (DESIGN.md section 17.K, slice K): the test page's footer, the end of "help" and the
  reply to "version" say the build the bot runs (`MVP_BUILD`, else the git commit and its date, read once at start;
  restart the bot after an update). On the test page (`--channel web`) with `MVP_OPERATOR` unset, the person typing is
  the operator (`MVP_OPERATOR=none`: nobody, to try what a tester sees); the footer also says whether sending, each
  connector, the browser and the sign-in key are on. Secrets are read through `settings.secret(name)` only: the
  environment first, then the sealed store (`tokens.py`: one AES-256-GCM file per person and connector under
  `MVP_HOME/tokens/`, 0600; the key from `MVP_TOKEN_KEY`, else made once in `MVP_HOME/token.key`, 0600;
  `MVP_TOKEN_KEY_AUTO=0` never makes one). Make a key yourself with
  `python3 -c "import base64,os; print(base64.b64encode(os.urandom(32)).decode())"` and keep it in the 0600 file with
  the other settings. Also: the `grants` table (a rule's standing yes, slice G), `RuleSpec.place` (code only), new app
  words (a YouTube playlist, Gmail, Google Calendar), stubs the other round 10 slices fill, and in-process fakes
  (`tests/fakes/`: the model, an MCP server, an OAuth server, Google and YouTube, a practice merchant).
  Tests: `tests/test_round10_k.py`.
- **Round 10, wording** (DESIGN.md section 17.W, slice W): with an email card open, "email it to me" emails the draft
  to your own confirmed address (when email is set up) or gives a tap-to-open link to yourself; the card stays open and
  nothing goes to the other person. With nothing written, it says so plainly. A setup answer that holds a request ("not
  really, i don't have much time. but can you set it up so my exports come to you regularly") is read part by part:
  the request goes to the helper by code (a yes to the export reminders offered), the rest to the profile, and the
  reply says "Noted: you don't have much time." "where do i upload my new export", "remind me every month to send my
  youtube takeout" and "sync my saves" are read by code. Everyday wording reaches the helpers by code: openers,
  closers and texting shorthand ("hey can u cancel my hulu thx"), "coach dan", "let my professor know by email",
  "looks good, send", "keep it in drafts", "say thursday not wednesday", "get rid of my hulu", "can i buy the first
  one", "is ticktick connected?", "connect my gmail" (an honest line), "go ahead with the netflix one", "do all of them"
  (one at a time, nothing ticked off), and two asks in one message ("cancel my hulu and also email my landlord").
  A model reading that clashes with what is on screen (a draft change read as a reminder, "yes" read as nothing
  waiting, a to-do ticked off with no done word) is settled by code. When code still misses and the model refused or
  chatted, one small form call (`errand.py`, `prompts/errand_v2.md`, about $0.001; `MVP_ERRAND_PER_DAY`, default 30;
  `MVP_ERRAND_MODEL`) names the helper and copies words from the message; code checks every field and the helper acts
  as usual (Spanish works through it: "escríbele a mi jefe que llego tarde", "quiero cancelar netflix"). It never
  sends, never makes a rule and never runs on a message with a time word. Tests: `tests/test_round10_wording.py`,
  `tests/test_round10_errand.py`.
- **Round 10, mismatched reels** (DESIGN.md section 17.S, slice S): a reel whose caption may not match its video (a
  chatbot recipe pasted under a meme clip) is marked from text alone (`captionmark.py`, `cm-v1`; no model, about 5 s
  for a library of 136,000 items). The marks are derived: `<library>/marks/caption_marks-cm-v1.json`, built after an
  import and by a background thread at the bot's start (`MVP_CM_BUILD_AT_START=0` turns that off); until the file
  exists nothing is marked. A strong-marked reel never comes first while something else fits; when it is the only fit
  the answer says "The only match I found is", gives it a neutral name ("A reel from @x") and adds one plain doubt
  line. "That reel had nothing to do with it" (or "yes" to the question after a 👎) takes it out of the picks and
  trusts that account's captions, and the same text under other accounts, less; "that one was fine" undoes it.
  `MVP_CM_DOUBT_ALL=0` names only the two sure reasons in the doubt line (for when the founder's labels put the mark
  under 85%). Tests: `tests/test_round10_slop.py`.
- **Round 10, sending and notices** (DESIGN.md section 17.D, slice D): on the test page, the **Connections** panel
  beside the chat takes your mailbox address and app password (and the TickTick, Todoist, webhook and YouTube keys);
  each is sealed on this computer and never shown again (the panel says "set" or "not set"). With them, "send" on an
  email card sends it from your own address after a 2-minute wait ("undo" stops it). If sending was switched on or off
  after the card was shown, "send" shows the card again first. "can you send it for me" says what "send" would do
  (or how to switch sending on); "send it for me" is the send word. A cancellation notice that went (sent by the bot,
  or "sent" after the link) offers a check date ("yes", another day, or "no"); the check reminder takes "they
  confirmed" or "no", and "no" offers a second notice, written by code, that goes only after its own "send". The
  route file gains the cancel facts read on 17 Nov (Amazon's cancel page, Audible's steps, LA Fitness's notice box,
  Planet Fitness's deadline, the last button's words for slice V). Tests: `tests/test_round10_sending.py`.
- **Round 10, rules that add to your apps** (DESIGN.md section 17.G, slice G; amendment A-015, Proposed): "every
  Sunday at 6pm put 3 pasta recipes in my ticktick" shows a preview that names the app, the kind of thing, the list,
  how often and the most per run and per day; the YES that starts the rule also lets it add (one yes per rule, the
  founder's decision). Each run adds through that standing yes and always says what it added ("Added 3 tasks to
  TickTick (rule 3): …"); "undo" takes them out for 24 hours, "undo rule 3" for 7 days. Routes: TickTick and Todoist by
  the operator's token, Reminders and Calendar on the operator's Mac. A tester, an app not connected, or an app the bot
  can't reach gets one honest line and the picks in the message. "stop adding to ticktick", "use ticktick for rule 3",
  "stop 3", "change 3 …" (asks yes again), "disconnect ticktick", 3 failures in a row (paused until "check my
  ticktick") and "delete my data" end or pause it. Never for a webhook, the mailbox or anything to another person.
  "what did you do for me" counts a rule's adds and lists the standing permissions. Tests:
  `tests/test_round10_grants.py`.
- **Round 10, Todoist by its own connector** (DESIGN.md section 17.C, slice C, the operator only): with no
  `MVP_TODOIST_TOKEN` set, "connect my todoist" sends a sign-in link; open it on the computer the bot runs on and press
  Allow (the page comes back to `http://127.0.0.1:8799/callback`; `MVP_CONNECT_PORT` changes the port). Then "add it
  to my todoist" shows the tasks and adds them after your yes through Todoist's MCP server; "undo" takes them out.
  Only the tools pinned at the sign-in are ever called; if Todoist changes one, the bot stops and asks "yes todoist".
  "check my todoist" tests it; "disconnect todoist" cancels the bot's access there. A personal token, when set, is
  used first. The daily check `python -m mvp.mcp_client --discover` needs no sign-in and no model.
  Tests: `tests/test_round10_mcp.py`.
- **Round 10, the merge of K, W, S, D, G and C** (DESIGN.md section 17, the hook order table and "where the slices
  meet"): a rule that names an app shows one preview with the app's line (slice W's stop-gap line is gone); a rule can
  add to Todoist through the sign-in route under its one yes, and a changed Todoist tool or a sign-in that needs you is
  said in the run's message; "delete my data" cancels the bot's Todoist access at Todoist before deleting the sign-in;
  a reel whose caption may not match its video is never put in your apps by a rule ("1 left out: ..."); the errand
  form's "send it" says what "send" would do, as "can you send it for me" does. Restart the test page after the merge
  and check that its footer shows the build. Tests: `tests/test_round10_merge.py`.
- **Round 10, your YouTube and Instagram links** (DESIGN.md section 17.Y, slice Y; amendment A-015, Proposed): "connect
  youtube" gives a code to type at google.com/device (Google's own sign-in, the `youtube` scope only; the bot keeps
  the sign-in sealed and checks with Google on its own every 30 seconds, or at once on "done"); "disconnect youtube"
  ends it at Google. Then "unsubscribe me from that channel", "unsubscribe from <channel>", "unsubscribe from channels
  I haven't watched since 2024" (only with a YouTube watch history under 120 days old; the whole list, "keep 2, 5",
  "unsubscribe N") and "put these in a playlist called dinners" (always private; only YouTube videos from your saves)
  each show the exact change and run after your yes, with "undo" (7 days for an unsubscribe, 24 hours for a playlist).
  A tester can do this too. YouTube's daily limit for this app stops the run and the rest is done the next morning
  unless you say "stop". Instagram lets no app unfollow or mute, so the bot sends the link and the two taps, one at a
  time ("done" or "next"); also Watch Later, history and the Instagram weekly-export link. Set up once: a Google Cloud
  project with a "TVs and Limited Input devices" client; `MVP_YT_CLIENT_ID` and `MVP_YT_CLIENT_SECRET` in the 0600
  settings file (or the Connections panel); `MVP_YT_UNITS_PER_DAY` (8,000) caps the writes. Tests:
  `tests/test_round10_youtube.py` (a fake Google; no real call).
- **Round 10, the browser that cancels for you** (DESIGN.md section 17.V, slice V; amendment A-016, Proposed; off by
  default): with `MVP_BROWSER=operator` and the merchant named in `MVP_BROWSER_MERCHANTS` (e.g. `netflix`), "cancel
  my netflix" offers "do it for me": after your OK for the site ("allow netflix"), a Chromium window opens on the
  computer that runs the bot, you sign in there yourself, say "I'm in", and the bot follows Netflix's own cancel path,
  stops before the last button and quotes the page; only "yes cancel netflix" presses it. It never types, never
  accepts an offer, stops at any check; "stop" closes it. `MVP_BROWSER=vm` runs the browser inside the bot's machine
  instead: you watch it and take over at the `/vm` link on the test page. `MVP_BROWSER_DEMO=1` adds a made-up practice
  merchant, "Streamly", to try the whole thing safely ("cancel my streamly"). Social media, YouTube and Google
  sign-in are never driven. Tests: `tests/test_round10_browser.py`, `tests/test_round10_vm.py`.
- **The live check of 19 Nov** (DESIGN.md section 17.L): "what can I connect" (or "connect", "integrations", "which
  apps do you work with") lists every connector the build has, its state for you and the words that connect it, never
  a value; "connect netflix", "connect my instagram", "connect my gmail" say plainly what there is; "like that reel for
  me", "comment ... on that reel", "save that reel to my instagram collection called X" get Instagram's "no app may"
  line with the post's own link (and, for a collection, the bot's own list after "yes"); a bare "I'm in" never changes
  the time zone; "cancel my spotify and my gym membership" handles the first and names the second; with the browser on
  but a site not switched on, the reply says so (`MVP_BROWSER_MERCHANTS`, in the round 10 settings below, switches it on). Tests:
  `tests/test_round10_livefix.py`.
- **Round 10, the self-test** (DESIGN.md section 17.T, slice T): `python3 -m mvp.selftest` plays 67 everyday
  conversations (every example a founder gave, paraphrased; c40 to c50 are round 11's, c51 to c58 its fixes, c59 to c66 round 12's; 164 steps) against the bot on a made-up library and checks plain
  things per step: no refusal, no "didn't catch that", no claimed outcome the store does not show, no inside words, no
  meme reel leading, no friend's post, plus each step's own. Set `MVP_HOME` to a new folder, `MVP_TOTAL_CAP_USD=30` and
  `MVP_LEDGER_HOME` first; it stops at `MVP_SELFTEST_CAP_USD` (default $1.00). `--dry` uses a fake model ($0),
  `--quick` 8 conversations, `--only c03,c07` some. Conversations that need a round 10 slice not in the code are
  skipped and counted. Transcripts go under `MVP_HOME/selftest/`; one line of counts goes to
  `evalset/selftest_runs.jsonl`. Tests: `tests/test_round10_selftest.py`. To run it with no model and no cost, from
  `experiments/`: `MVP_HOME=<a new empty folder> MVP_TOTAL_CAP_USD=30 python3 -m mvp.selftest --dry` (prints each
  step and a line of counts; exit 0 when every step passes). In a conversation, `"advance": "next run"` moves the
  clock to just after the person's next rule slot, whatever time the model chose.
- **Round 10, the first live self-test and its fixes** (DESIGN.md section 17.T, "The first live run"): the full set ran
  once with real models (40 conversations, 114 steps, 103 passed, $0.25); after the fixes the 7 conversations that
  failed and 3 whose wording changed ran again (10 conversations, 31 steps, all passed, $0.11). What you now see: "mini blender tutorials to start doing daily" shows the daily rule's
  preview and waits for YES; "every sunday put 3 recipes in my todoist" runs at 9am, never at the minute you said it;
  "email everyone in my class ..." greets everyone and asks for one address at a time; a reel whose caption may not
  match opens with "Here's what I found in your saves." and reads "the only match I found is a reel from @..."; a
  tutorial's alternative says its steps are in the video; a key point never repeats its title; YouTube's lines for a
  tester never name an operator's setting, and a playlist request with no YouTube picks says to ask again "on
  youtube". Tests: `tests/test_round10_selftest_live.py`.
- **Round 10, the second merge: Y, V and T** (DESIGN.md section 17, "The second merge"): a rule can add its YouTube
  picks to your private playlist ("every sunday at 6pm put 3 cooking videos in my recipes playlist"): the preview
  names the playlist and the caps, your YES lets it add, each run says what it added, Instagram picks stay in the
  message, and "undo" takes the videos out. "undo" after a rule's adds through Todoist's sign-in takes them out
  there. "delete my data" ends Google's access and removes the browser's rows; "export my data" lists what the bot
  holds about your YouTube for a moment (never a title). Anyone can connect their own YouTube. "what are you
  connected to", the Connections panel and the footer say whether YouTube is set up and where the browser runs and for
  whom. "Which gym?" answered with how you pay is asked again; "do it for me" after the cancel steps says plainly why
  not. Tests: `tests/test_round10_merge2.py`.
- **Round 10, the check of acting and secrets** (DESIGN.md section 17.X): the browser never follows a merchant's
  redirect to another site (a social site above all): everything but the merchant's own hosts goes to a proxy that
  does not exist; a site in another spelling or a bare IP address in a route is refused. A key, token, client secret,
  app password or sign-in code typed in everyday words is refused before any model sees it. The `/vm` view belongs
  to the first browser that opens it. The test page answers only its own address. A last button that shows an offer
  under a "cancel" label is never pressed. Tests: `tests/test_round10_checks_acting.py`.
- **Round 10, the check of reading and answers** (DESIGN.md section 17.R): "that's ai slop" and its kin ask before
  anything is learned; a mismatch lands on the pick its own words name, never one called fine; a complaint about the
  request is asked about first. "i want to unsubscribe from that channel" is YouTube, never a merchant. Two asks in
  one message reach both helpers. Everyday words for the new helpers are read by code (a copy to myself with a card
  open, "unsub", the regular-export and version questions, "what have you been doing for me", some Spanish), and
  Instagram actions no app may do get one plain line with the person's own way. The held-out phrasing set (run once):
  22 of 70 right by code, 54 of 70 with the model, 0 of 30 "none" lines taken by a helper. Tests:
  `tests/test_round10_checks_reading.py`.
- **Round 10 settings** (each set on the computer that runs the bot: in the environment or the 0600 settings file
  for the browser settings; the YouTube client also in the Connections panel on the test page. Never in the chat:
  the bot refuses keys typed there and does not keep the message):
  - `MVP_BROWSER`: unset (the default) means no browser at all and today's cancel steps. `operator` opens a window on
    the computer that runs the bot (it needs a screen); `vm` runs a browser inside the bot's machine that you watch
    and take over at `/vm` on the test page.
  - `MVP_BROWSER_MERCHANTS`: the merchants the browser may open, by key, comma-separated (`netflix,spotify`). None by
    default. Social media, YouTube and Google sign-in are refused whatever this says.
  - `MVP_BROWSER_FOR=all`: with `MVP_BROWSER=vm` only, testers may use it too. By default only the person who runs the
    bot (on the test page, that is you).
  - `MVP_PAGE_HOSTS`: extra host names the test page answers when it listens on this machine's own address
    (`preview.example,preview.example:443`, or `*` for any). Unset, it answers only `127.0.0.1`, `localhost` and
    `[::1]` with its port. Set it only when the page is reached through a forwarded or preview address, on a
    machine no browser runs on. The page then follows the bot's `/vm` link on the address it was opened on.
  - `MVP_BROWSER_DEMO=1`: adds the made-up practice merchant "Streamly" ("cancel my streamly", then "do it for me") so
    you can watch the whole thing with no real account.
  - `MVP_YT_CLIENT_ID` and `MVP_YT_CLIENT_SECRET`: the "TVs and Limited Input devices" client of your Google Cloud
    project. With both set, anyone says "connect youtube" and signs in to their own account at google.com/device.

<!-- the merge of round 11 -->
## Ask your watch history anything (round 11, DESIGN.md section 18)

The help, "what can you do" and the setup's last message now lead with it: "Ask your watch history anything. I can see
N videos you watched on YouTube ..., up to <date>. Try:" and three questions built from your own counts and topics,
each one the code answers.

- **History questions** (slice H, below): rankings, counts, first and last, a day, a month, a timeline, a comparison,
  by code, with the window said back and where your export ends.
- **Summaries across many posts** (slice M, below), now also inside a window ("summarize what i watched in October
  about X").
- **Asking a video itself** (slice Q, below; `MVP_VIDEO_ASK=1`, off by default): offered after the honest "I can't
  tell that from what <title> says" line or a title-only video's line, after a summary that cites a YouTube video ("ask
  video N"), and after "the first one" picked from a history answer. "what did you do for me" lists each video asked;
  "export my data" writes `history_and_videos.json`; "delete my data" removes it all.
- Offline checks: `python3 -m pytest -q mvp/tests/test_round11_merge.py` (and `_h`, `_m`, `_q`); the self-test's
  conversations c40 to c50.
- The check after the merge (DESIGN.md section 18.X, `tests/test_round11_checks.py`): more windows ("this past
  weekend", "2 weeks ago", "between oct 1 and oct 10", "halloween 2025", "los ultimos 7 dias", 29 February with no
  year); "ok thanks" and other chat after a history answer is never a new topic; "like or save" never counts a watch;
  a summary never passes on an item's own call to act; asking a video never passes on a point that names another
  video of the library.
<!-- end the merge of round 11 -->

<!-- round 11 fix, A -->
## History answers after the live check (round 11 fix, A; DESIGN.md section 18.LA)

- "what was that video i watched about X" (and "what's that video where ...", "which video did i watch about X",
  "find the video i watched on X last month", "that <channel> video about X") is a recall by code: up to 3 videos you
  watched, best match first, each with the day you watched it and its card; the first is in view for "what did it say
  about ..." and "ask the video". Nothing watched fits: said, with the saved one. "find me a video about X" is still a
  pick.
- First, last and list answers with a topic show only what fits it by the library's own vectors and say "about"
  (counts still say "mention"); "did i watch more in X or Y" answers first; timelines start at the first year with a
  count; "accounts and channels" when Instagram is counted; the friends line and the all-time range once every 6
  hours.
- For the offers after an Instagram post in view: `history.best_watched_video(bot, person, topic=None, item=None,
  latest=False)`.
- Offline checks: `python3 -m pytest -q mvp/tests/test_round11_fix_a.py` (93 tests).
<!-- end round 11 fix, A -->

<!-- round 12, D -->
## Lengths, themes and the fact sheet of a history question (round 12, D; DESIGN.md section 19.D)

- `python3 -m mvp.lengths <library>`: the official length of every YouTube video watched (videos.list, 50 ids a call,
  YOUTUBE_API_KEY from the environment), into `data/mvp/derived/lengths-v1/` (kept 30 days, resumable; each run's
  numbers in `runs.jsonl`). A Short: at most 61 s, or at most 180 s for a video published from 15 Oct 2024.
- `python3 -m mvp.themes build <library>`: themes by code from the library's own item vectors, named by one model call
  per field (prompt `theme_name_v2`, about $0.04 for a library of 100,000 watched videos), into
  `data/mvp/derived/themes-v2/<library key>/`. Never built while a person waits; later items get the nearest theme.
- `facts.build(bot, person, q, now)`: the fact sheet of a history question, by code (no model, no network), for the
  writer. New questions read by code: "did i watch more X or more Y this year", "how has what i watch changed since
  2020", "what was i into in the summer of 2023", "what was i watching back in 2021", "most watched channels in X",
  "... without shorts"; and, after a history answer, "without shorts", "only X", "by month", "by theme".
- `MVP_DERIVED_HOME` moves the derived folder (the tests set it to their own).
- Offline checks: `python3 -m pytest -q mvp/tests/test_round12_d.py` (125 tests, the made-up library
  `tests/r12_library.py`).
<!-- end round 12, D -->

<!-- round 11 fix, B -->
## Summaries that say something, and asking several videos (round 11 fix B, DESIGN.md section 18.LB)

- A summary numbers its sources once (`Sources:`), each point cites them (`[1, 3]`), and "ask video N" means the
  number you see. "from what i watched" reads only what you watched, "from my saves" only your saves; the first line
  says which. A point that only says what a video is ("several tutorials are for beginners") is left out (prompt
  `synth_v5`, then code); when too little is left it says so ("The titles and descriptions of the 39 videos you watched
  about after effects don't say much about easing.") and lists the best 3.
- With `MVP_VIDEO_ASK=1`: "ask them" (or "ask those videos", "ask the top 2") asks up to 3 of the YouTube videos just
  shown, one Google request each, counted one by one against the daily cap; the first time it says what it sends.
  The first-time note takes "yes". "email it to me" after a video answer emails that answer. An Instagram post in view
  offers the YouTube video you watched on it ("ask that one"; needs fixer A's `history.best_watched_video`).
- Offline checks: `python3 -m pytest -q mvp/tests/test_round11_fix_b.py`; the eval: `python3 -m mvp.eval_synth
  mvp/evalset/synth --with-thin --out <folder outside git>`.
<!-- end round 11 fix, B -->

<!-- round 11 fixes, the merge -->
## Where the two fixes meet (round 11, the merge of the fixes; DESIGN.md section 18.L)

- With `MVP_VIDEO_ASK=1`: after "what was that video i watched about X", "ask them" asks the recall's own videos (up
  to 3, in its order; with no question, "what does it say about X?"), "ask the video" the first. An Instagram post in
  view offers the YouTube video you watched on it, by the request's words, else by the post's caption. The help has one
  line for "ask them"; "what leaves this computer" and the consent say up to 3 links go to Google, each with your
  question.
- "summarize ... from what i watched" reads what the history answers count as watched, and, where the library has its
  item vectors, leaves out what only mentions the topic. The hint on sending a new export is said once in 6 hours, in
  history answers and summaries alike; where the export ends is always said.
- "export my data" also lists what "ask them" keeps (its topic, a note waiting for "yes") and the notes said.
- Offline checks: `python3 -m pytest -q mvp/tests/test_round11_fix_merge.py` (24 tests); the self-test's c51 to c58
  (`--only c51,c52,c53,c54,c55,c56,c57,c58 --dry`).
<!-- end round 11 fixes, the merge -->

<!-- round 11 fixes, the check -->
## The check of the fixes (round 11; DESIGN.md section 18.L, part "18.L check")

- A summary with a window ("summarize what i watched this month about cooking") is a summary even right after a recall
  (it was the pick's key points), and it leaves out what only mentions the topic, as one without a window does.
- "ask them" with every video failing says so plainly, with no "watched them" line; a step one video says twice in
  other words is shown once. "reels" in a history question means Instagram. A timeline whose months tie names no "most".
- Offline checks: `python3 -m pytest -q mvp/tests/test_round11_fix_checks.py` (329 tests: 70 made-up messages and 50
  traps as tester and operator, the findings by their exact messages, the export end in every answer that reaches it,
  summaries, asking up to 3 videos, what an ask keeps).
<!-- end round 11 fixes, the check -->

<!-- round 11, fix pass 2 -->
## The second fix pass (round 11; DESIGN.md section 18, part "18.L2")

- Asking a video (`MVP_VIDEO_ASK=1`): prompt `video_ask_v2`. Every point answers the question asked, with the names,
  values and steps the video gives; a video that doesn't cover it gets one line naming the thing asked (`This video,
  "...", doesn't seem to cover easing.`); a point that only says what the video is, or repeats its title, is left out
  by code. `python3 -m mvp.eval_videoask --list <file outside git> --prompt video_ask_v2 --out <file>` runs the
  evaluation again on your own list of public videos and questions (the repo ships none).
- The offer of a watched video never names one with no title, and keeps a question already typed: `Say "ask that one"
  and I'll ask it: "..."`. "ask the video" after a recall asks about its topic and says so; "ask them" with nothing
  shown is one plain line.
- Read by code now: "remind me what that video i watched about X was", "whens the first time i watched X", "more
  videos in october or september?", Spanish comparisons without "?" and "como ha cambiado lo que veo", "sum up what my
  watch history says about X", "can you email me that" right after a video's answer or a summary.
- With fewer than 6 watched items holding the words, a recall, first, last or list shows them all and says "mention";
  "reels" for what was watched on Instagram in a summary's lead and last line; the hint on sending a new export once in
  6 hours in history answers too; a summary's other word forms ("cooked") must pass the library's fit.
- Offline checks: `python3 -m pytest -q mvp/tests/test_round11_fix2.py` (139 tests: each finding, with near variants
  that must not be taken).
<!-- end round 11, fix pass 2 -->

<!-- round 11, fix pass 2, the check -->
## The check of the second fix pass (round 11; DESIGN.md section 18, part "18.L2 check")

- "ask the video" never asks on its own the one YouTube video in view that has no title of its own (a list of reels
  and "A video from ..."): it says so and offers the best titled video you watched, keeping your question; "ask video
  N" still asks the one you name. After a recall, "ask video 2" asks the second video the recall listed.
- A YouTube title that holds its own hashtags is its name ("... #shorts" no longer makes it "A video from ..."), and a
  recall lists videos with a title of their own first.
- A topic whose word matches are mostly saves pointing elsewhere no longer says "Nothing you watched fits" while
  watched videos hold the word: they are listed as "mention". "and how many in september?" after a list is a count.
- Offline checks: `python3 -m pytest -q mvp/tests/test_round11_fix2_checks.py` (274 tests).
<!-- end round 11, fix pass 2, the check -->

<!-- round 11, slice Q -->
## Ask the video itself (round 11, slice Q, DESIGN.md section 18.Q; amendment A-017, Proposed; off by default)

- **Off** (the default): nothing changes. A question about a video shown that its title and description do not answer
  gets "I can't tell that from what <title> says. Here it is, so you can check:" and its link, as before.
- **On** (`MVP_VIDEO_ASK=1`, and `GEMINI_API_KEY` set on a billed Google project): that line gains `I can ask the
  video itself: say "ask the video"...`. "ask the video" (or "ask the video what settings it uses", "ask video 2
  ...", "ask the second video ...") sends the video's public link and the question to Google's Gemini, which watches
  it, and the reply is up to 5 points, each with its time and a link to that second, under `From the video (not
  checked against its text), "<title>":`. YouTube only, public videos only. The first time, the bot says what leaves
  this computer and waits for "ask the video" again. Kept: the points, their times, the video id and the ledger row;
  never a transcript, audio or picture.
- **Limits** (checked before the call): `MVP_VIDEO_ASK_MAX_MIN` (default 20; a longer or unknown length is asked
  about its first 20 minutes only, and the reply says so), `MVP_VIDEO_ASK_PER_DAY` (default 5 questions a person a
  day), and the cost's worst case against the person's daily cap and the total cap. `MVP_VIDEO_ASK_MODEL` (default
  `gemini-3.1-flash-lite`). Measured on 19 Nov: 5 to 10 seconds and $0.003 to $0.011 an answer for 2- to 8-minute
  videos.
- **"what leaves this computer"** (also "what do you send to google", "where does my data go"): a short list, read by
  code, setting on or off; the Gemini line only while it is on. The consent message names the flow while it is on.
<!-- end round 11, slice Q -->

<!-- round 12, W -->
## History answers that give insight (round 12, builder W; DESIGN.md section 19.W)

- The writer: `insight.write(bot, person, sheet, now)` turns one fact sheet (built by code for one history question)
  into the answer first, 2 to 4 observations, a small chart of block bars, a "so what" and one line of offers ("Want
  it without Shorts, only Blender 3D, or by theme?"); one model call (prompt `insight_v4`, about $0.0025 and 2 seconds on a made-up sheet; on a real library of 100,000 watched videos about $0.0045 and 3 to 5 seconds)
  fills the form and code checks every number, date and name against the sheet. A failed check, a failed call or the
  cap: today's code reply. `MVP_INSIGHT=0` turns it off (the tests' default). The merge wires it.
- Quiet limits on every history answer: where the window passes an export's end, the window's own words say so ("This
  year (1 January to 30 October 2026, where your YouTube export ends)"); no closing paragraph; the "send me a new
  export" hint once in 6 hours and only about a time after the export's end; the friends line only when you ask about
  friends. `MVP_QUIET_LIMITS=0` gives round 11's replies back.
- Its evaluation: `python3 -m mvp.eval_insight --mode before|fake|live` on the 20 made-up sheets of
  `eval/insight_cases.json`. Offline checks: `python3 -m pytest -q mvp/tests/test_round12_w.py`.
<!-- end round 12, W -->

<!-- round 12, merge -->
## History answers, wired (round 12 merge; DESIGN.md section 19)

- Ask a history question as before ("what have i been watching the most lately", "did i watch more gaming or more art
  videos this year", "how has what i watch changed since 2020", "what did i watch on october 30"): code builds the
  fact sheet and the writer answers from it in one call, checked by code. With the writer off (`MVP_INSIGHT=0`), the
  cap reached or the call failing, the same question gets today's code reply.
- Then type an offer of the last line in its own words, for 6 hours: "without Shorts", "only <theme>", "with the
  videos", "by month", "by theme" (also "yes, by month"). "yes" to "want them as a list?" lists the saved videos you
  never opened, with their cards. "the first one" and "more" work as before.
- The themes and lengths must be built first for the library (`python3 -m mvp.lengths`, `python3 -m mvp.themes
  build`, part D above); without them the sheet has no themes or lengths and the answers say less (how what you
  watch changed is then today's timeline).
- Offline checks: `python3 -m pytest -q mvp/tests/test_round12_merge.py` (the seams, with the made-up writer
  `tests/r12_writer.py`); the dry self-test's c59 to c66 are the brief's eight questions.
<!-- end round 12, merge -->

<!-- round 12, pass 2 -->
## History answers, second pass (round 12, pass 2; DESIGN.md section 19.P2)

**Before you test history answers** (on your Mac; once per library, then every 30 days for the lengths):
1. `python3 -m mvp.lengths <library>`: the official length of every YouTube video you watched, for Shorts against
   long videos. Needs `YOUTUBE_API_KEY` in the environment; costs nothing (one YouTube quota unit per 50 videos: about
   2,200 units for 110,000 videos, under the daily 10,000); about 5 to 6 minutes. Lengths are kept 30 days.
2. `python3 -m mvp.themes build <library>`: the themes and areas, by code from your library's own item vectors, named
   by one model call per field (about 19 calls, about $0.04 in all, with the same `OPENAI_API_KEY` the bot uses);
   about 75 seconds.
3. `python3 -m mvp.themes status <library>` says whether both are ready (and exits 1 when not). The test page prints
   the same lines when it starts, with a WARNING when either is missing or stale; the trace of every history answer
   has the themes version (empty when there were none). The build is found by the library's real path (a `data/`
   folder reached through a symlink is the same library) or, failing that, by its content.
4. The writer stops for a person whose spend today has reached the daily cap (`MVP_DAILY_CAP_USD`, $1.00 by default;
   each history answer costs about $0.003 to $0.006): the code's own reply goes out instead, the shorter one with
   counts. That is right for testers, but when you are grading answers, start the page with a higher cap for the day,
   for example `MVP_DAILY_CAP_USD=8 python3 -m mvp.bot --channel web` (the total cap, `MVP_TOTAL_CAP_USD`, still holds). An
   answer the cap kept from the writer says so in the trace (`python3 -m mvp.trace --web`): "daily cap reached" (or
   "total cap reached") at the end of its run.

What changed (the founder's grades of round 12 and the second judge's findings):
- The writer (prompt `insight_v5`) never types a number: it names sheet paths ("{themes[0].share}") and code fills
  them, so a number stands only next to its own thing; "led", "followed by", "mostly" (half or more), "a wide mix",
  "twice" and "N more" are checked against the sheet's own order and numbers. No total of video length anywhere (it
  read as watch time); Shorts against long videos and the typical long video's minutes instead.
- The broad picture first: areas (gaming, comedy, science, ...) with shares that add up to most of the window, then
  the themes inside; a change is told as eras (which area led which years, what rose and fell, Shorts then and now);
  a day against your usual day; "more X or Y" as a ratio in words with what is inside each side; a ranking of channels
  with what each is.
- The so-what is one of the things code found worth saying (an interest that lapsed while you hold 3 or more unopened
  saves on it, a learning theme that faded against entertainment that grew, Shorts' share moving, a channel newly at
  the top, a theme that comes back each year in the same season), never the same twice in a row, or none.
- No "send me a new export" line on a history answer (only when the whole window you ask about is after your
  export); a history answer that is not ready in 20 seconds sends the code reply (`MVP_INSIGHT_TIMEOUT_S`).
- Offline checks: `python3 -m pytest -q mvp/tests/test_round12_pass2.py`; `python3 -m mvp.eval_insight --mode fake`
  (every planted false sentence dropped, every true one kept, both the typed form and insight_v5's).
<!-- end round 12, pass 2 -->

<!-- round 12, pass 5 -->
**The audit of history answers** (DESIGN.md section 19.A; `eval_claims.py`, an independent recount that imports none of
the answer's code). From `experiments/`, with `MVP_HOME` a scratch folder holding a `people.json`:

    python3 -m mvp.eval_claims capture QUESTIONS.jsonl --out DIR [--live N]   # send; the first N live (paid, ledger)
    python3 -m mvp.eval_claims capture made-up --out DIR                      # the 12 made-up questions in the file
    python3 -m mvp.eval_claims audit DIR [--json OUT]                         # recount every sentence and sheet number
    python3 -m mvp.eval_claims gen --library L --out FILE                     # questions from a record's areas, years

`QUESTIONS.jsonl` lines are `{"id", "msgs": ["question", "without shorts"], "window": {...}, "live": true}`; keep real
questions and the captured answers in scratch (they hold real titles). Without `--live` the made-up writer of the tests
fills the form from the sheet's paths (no model call). The audit prints the mismatches by kind and the worst with codes
only (no names); a case a hand count shows to be the auditor's reading goes in `eval_claims_allow.json` with both counts.
Every sent sentence's sheet paths are in the run's trace (`steps.writer.sentences`).
<!-- end round 12, pass 5 -->

## New picks from outside the saves, and keeping the library fresh

- **Outside picks** (`outside.py`): when someone asks for new things ("…and show me a few new ones from outside my
  saves", "only new stuff, not from my saves: sourdough"), the answer gets a block "Not from your saves, but close to
  them:" after the library picks (or only that block). YouTube only: one official `search.list` call with the
  person's own topic words (code keeps only words from their message, drops words about time, length and words that
  only say the kind, then adds one fixed word for the kind from a small table: recipe, workout or tutorial; a request
  with no topic word left gets no outside search), checked by one `videos.list` call; the first 3 that
  are public, embeddable, not for kids, not live, not in News & Politics (unless they asked for news), with a topic word
  in the title or channel, and not already in their library, in YouTube's order, with YouTube's
  own title and channel and the length. No model reads or rewords them; they are never kept with the answer or counted
  as sent picks. Never for personal topics (health, relationships, money, religion, politics, sexuality). Limits: 80
  searches a day for everyone, 5 per person, a search text reused for 24 hours. Everyone's count is also kept in
  `outside_searches.jsonl` beside the MVP ledger (`MVP_LEDGER_HOME`, day and time only), so the test page and the real
  bot share one quota. Needs `YOUTUBE_API_KEY`; `MVP_OUTSIDE=0` switches it off. When it cannot serve a request, the
  reply says why in one line. These finds are shown in the chat only: an answer that goes by email still shows them
  in the thread, and "email me only new ones" says they were not emailed. When someone wants something to do or make
  and their saves hold fewer than 3 that clearly end with a finished result (and fewer than 3 candidates whose own text
  looks like that kind: a recipe, a workout, a whole tutorial), the answer says so in the request's terms
  ("You only have 2 saved recipes that fit, so here are a few more from YouTube:"), shows the closest from the saves,
  and adds this block without being asked (one search at most, and at most once per topic per day); a rule's preview then offers "Want
  these … from YouTube as well as your saves?", and its YES starts the rule with them.
  Before anyone outside the founders gets these: a terms page linking YouTube's Terms of Service and a privacy note
  naming YouTube API Services (DESIGN.md section 11).
- **The inbox** (`refresh.py`): `MVP_INBOX` (default `data/inbox/`) holds one folder per person (the handle's letters
  and digits, e.g. `data/inbox/15551234567/`). Every `MVP_INBOX_MINUTES` (3) the scheduler takes any file there that
  has not changed for a minute: an Instagram export (JSON, zip or folder) or a Google Takeout zip with YouTube. It is
  imported with the demo's importer into a new library beside the old one (`MVP_LIBRARY_ROOT` to put it elsewhere),
  with the export's `messages` folder left out unread. The search vectors are built by the demo engine's `prepare`
  (embeddings only); an import whose estimated cost is over `MVP_IMPORT_CAP_USD` (default $1.50) is refused. The same
  export dropped again is not built again, and a person gets at most `MVP_IMPORTS_PER_DAY` (2) builds in 24 hours; a
  build's cost counts toward the total budget but not the person's daily limit. Only
  when the build succeeded is the person switched to the new library (the library the founders set up is kept; one an
  earlier import built is removed once nobody uses it; a restart keeps the
  switch while `people.json` still names the old one); they get one message with the counts, and their "when I save
  something new" rules run once on the new items. An imported file is deleted; a refused or failed one goes to
  `<inbox>/<person>/.failed/`, and an importer crash is said to the person like a failed build. A Takeout in parts
  (`-001.zip`, `-002.zip`) waits until no new part has come for `MVP_INBOX_PARTS_MINUTES` (10) and is imported in one
  go. An import that finishes in quiet hours or a snooze is announced (and its new-item rules run) when they end. An import cut off
  by a stop starts again at the next start (its half-built library is removed). If two people's handles give the same
  folder name, that folder is left alone and the upload box refuses it. Do not drop a real export there before the
  founders agree.
- **"Did my export come in?"** answers with the last import, items by source, how old the newest item is, when the
  next export is due and the export links. `refresh.offer_export_routine()` gives the export steps and offers the
  reminder rules (every 4 weeks for Instagram, every 2 months for YouTube); the onboarding slice sends it. A fully
  automatic export is not available for US accounts: the person still requests each export and puts the file in
  the inbox.

## The person's context and the setup (profile and onboarding)

- **The setup** (`onboarding.py`), for anyone who agrees from now on, in at most five bot messages: (1) the consent
  text; (2) the read of them: every guessed topic (up to 8), most saved first, with the level guessed and the counts
  worked out by code ("Blender 3D: new to it (about 45 saved, 3 watched)"), a guessed direction built by code ("It
  looks like you're learning Blender 3D and collecting quick dinners."), then "did I get that right, and what are you
  working toward?"; (3) their answer merged into the profile (one form call; code checks it) in one message: every
  topic with its level, the direction in their words, then the email address (the 6-digit code flow) and the time zone
  check; (4) one line offering the export reminders (the steps go out with each reminder, and on "how do I export?"),
  up to three first requests written for them, each kept only if at least three items of their library mention its
  topic words, and one optional question ("food you avoid, kit you have, how much time you usually have?"); (5) the
  reply to that answer. They reply 1, 2 or 3 to run one now, or "every morning" for a preview of number 1
  as a morning rule (one YES starts it and the export reminders). "skip" skips any step; a real request at any step is
  answered and the setup goes on (the read is asked again once; not when the answer asked a question of its own, which
  the next message answers). Only a bare "yes" / "that's right" counts as one; "yes, but I'm past beginner" goes to the
  form call, and "that's right" confirms only the topics the read showed. A step left unanswered for 24 hours
  (`ONBOARD_STEP_HOURS`) ends the setup quietly. Deleting a person's data also drops the guess of their library
  (unless someone else uses the same library). People already in the store are not set up again; "set me up again"
  restarts it.
- **The guess** (`profile.py`, `prompts/profile_guess_v3.md`): code samples what they chose to keep (saved, in a
  collection, sent to themselves: the 45 newest and 45 more at random, seeded by the library build; never friends'
  items), a smaller set of likes and playlists, and only their 6 most watched YouTube channels; one call groups them
  into topics at the grain a person would say ("Blender 3D", "quick dinners"), with the lines behind each (a broad field
  alone, "Gaming", gets the topic's own checked words: "Gaming, mostly Minecraft"); code checks the line ids, counts the support, works out the
  share and the library-wide counts, keeps a level only with a quote from the topic's own lines, and removes any topic
  about health, relationships, money, religion, politics or sexuality, whatever the model returned. It is cached per
  library build (a new import gets a new guess; what the person confirmed or said is never overwritten by one).
- **Any time**: "what do you know about me" shows the profile and how to correct it; "I'm past beginner at Blender
  now", "I have an air fryer", "I'm not into cooking any more", "stop guessing my level" are merged by the same form call
  (`prompts/profile_merge_v3.md`) and the reply says what changed; their own goals are kept in their words (only a
  stated diagnosis, debt or income figures, religion, politics, sexuality or relationship status is left out, and only
  that clause); a direction is stored only from a stated goal, never from timing words or the request; "I eat meat
  again" removes that avoid entry; what a message asks for wins over the profile's avoid list ("chicken and rice" from
  someone who avoids meat runs as asked); a fact said inside a request ("I'm vegetarian now,
  any dinner ideas?") is merged too, and the answer ends with what changed. "Too easy" / "too hard" after an answer move
  that topic's level one step (and say so); "made it" marks the pick done, so it is never sent again.
- **Requests it will not do** get a sentence picked by code (the model's own wording is never shown).
- **Fix pass 5**: copies of one post take one place before the composer chooses; a thin ask or preview gets one more
  composer call on what it did not return (logged as `second_look` in the run's steps, counted in its cost, cached);
  close picks may follow a clear lead under their own heading; the lead's own dish comes last among the alternatives
  (at most one; the same dish means the same title words once words that only say how it is made or praise it, such
  as "easy", "rice cooker" or "bowl", are left out, so "Chicken fried rice" is not "Chicken rice"); copies are the same
  creator and the same line the post's name comes from (never a "Save this" hook line), with at least 3 words; a
  second-look pick with any "no" is never shown; a reason loses only its failing part when what is left is still a
  whole clause (else it goes), and a lead whose reason was removed gets one code stands behind;
  "new ... that I haven't seen" or "not from my saves" is new picks only, with an opening line of its own, and new
  picks for something to make put whole videos before tips and very short ones; a setup reply ("skip the email, time
  zone is fine", "yes set up the export reminders") gets one message; a daily rule that is only the closest because
  of its length says so when it starts, and "any length" or "include YouTube" changes it.
- **Using it**: the interpreter gets only the profile lines about the message's topic (and no profile level when the
  message names a level itself); the composer gets their level at the request's topic and may say it in the reason only
  when they confirmed it or the guess has a quote behind it; while it is a guess, the answer says once per topic "I'm
  guessing you're new to Blender; tell me if that's wrong." A request to make, cook, build or practise something
  carries a finished-result must-have, and code answers "no" to it for any item whose own text is only tips, and
  "yes" when code has read the whole thing from the item's own text (a recipe's ingredients and two or more steps; a
  workout's or a tutorial's two or more steps).
- **The profile helps and never blocks** (fix pass 4 and its check, `interpret.profile_guard`, run on every form and
  on the setup's first requests): the kit they have (by any of its names: "pressure cooker" for an Instant Pot), how
  much time they usually have (in any unit) and their notes and direction are preferences for the composer, never
  must-haves, unless the message says them (a length the message gives or implies, "mini" or "quick", stays; a diet
  restated from a note, or an avoid entry restated as a must-have, becomes avoid); a level must-have comes only from
  the message (the profile's level for the request's topic goes to the composer, which prefers picks that suit it);
  new picks from YouTube only when the message asks for new things (or their profile says so), and the line saying
  why there are none only after a message that asked; and no limit to some kinds or platforms the message does not
  name ("I'd like", "to watch" name none). A reason or a title names their kit (by any of its names) or their usual
  time only when the post's own text does. A repeating rule with new picks says it won't run dry only while YouTube
  can serve it. "Add it to my list" or "remind me of it" after an answer means the pick it opened with. The export
  reminders are listed to the interpreter, and in "my rules", by short names.

## Answers that answer, and dates (round 7, DESIGN.md section 12)

- **Things, not descriptions**: "what UI/UX libraries should I use" or "what opportunities did I miss" gets the things
  the posts name, each under the post it came from with that post's link: `From "Best design systems" by @creator
  (posted June 2023, saved July 2023):`, then `1. Material UI: <the post's words about it>`. Names and words are the
  post's own, checked by code (`extract.verify_items`); at most 3 posts and 6 things each. Recipes, workouts and
  make-or-build tutorials keep "I recommend ... because" with ingredients and steps. "add the second one to my list",
  "remind me about <name> tomorrow at 9", "put the NASA one in my calendar" act on that thing (the numbers run across
  the posts, as the person read them). "remind me about <name> two days before its deadline" counts back from the date
  in that thing's own words; with none, the bot says so and sets nothing. A thing's words are shown only when they are
  about it (never a sentence under the next thing's name, never a whole one-line list under each of its names). For "for
  2026", a thing whose own words name only an earlier year is left out while others fit.
- **Dates**: the bot knows today's date and when each post was made (Instagram from its link, YouTube from
  `videos.list`). For opportunities, deadlines, events and the like, a passed deadline never leads ("its deadline, 14
  February 2025, has passed" when it is all there is), an old "applications now open" comes last with its month, a
  date ahead says how far it is ("deadline 1 December (in 19 days)"; inside a thing's line "deadline 1 December, in 19
  days"), and newer comes first. An old "open until further notice" says "check whether it is still open", not "probably
  closed". A reason never says "now open", "this week" or "new" about a post older than 60 days.
- **Changing the request**: after an answer, "what about something that isn't a donut", "not from that creator",
  "something shorter", "more recent ones", "anything else?", "not on YouTube" search again with the change (also when
  the interpreter reads it as "more"); "what about ones from <creator>" searches that creator's; "ok and for dinner?"
  searches the same request with those words added; "the opposite" gets a one-line question back. A question about the
  picks shown ("how long is the second one?", "what about the second one, is it long?", "does the first one work
  without a GPU?") is answered from them.

## The items answer holds real named things (round 8, slice A2, DESIGN.md section 12)

- **Only specific named things**: a post's headline, a category ("design systems"), an audience ("underclassmen"), a
  count ("5 tools") or a name paired with words that say nothing about it is never shown as a thing
  (`extract.clean_items`, prompt `extract_v3`). A post about one thing shows that thing with its best one or two key
  points. A post that lists names on lines of their own shows the names, words or not. For a request that names a kind
  of thing ("libraries", "opportunities"), only things the model marked as that kind are shown, unless fewer than 2
  would be left. Fewer than 2 good things: the usual "I recommend ..." answer with the post's key points.
- **The right posts are read**: for such a request the details step reads up to 6 posts: the picks shown, then the
  composer's other fits, then candidates whose own text lists named things on the request's topic (never one with a
  "no", an avoided word or creator). The posts with the most things come first (at most 3), the next two get one line
  each under "More in your saves:", and the opening line counts what was found: "I found 9 UI/UX libraries named in 3
  of your saves." A post whose title promises a list its text does not hold says "the names are in its slides, not its
  text."
- **Several asks in one message**: "send me startup motivation reels, opportunities to pursue soon, or things with
  deadlines" gets one labelled part per ask (2 picks each), or "Nothing in your saves clearly fits this part."; "chicken
  and rice recipes" stays one ask. The numbers run across the parts.
- **"Something that isn't a donut"** also leaves out the rest of that creator's numbered series, and shows that
  creator's other posts only when fewer than 2 from others fit ("same creator as the one you passed on").
- **A plain question about the saves** ("what other opportunities might I have missed ...", "what are some UI/UX
  libraries ...") that the interpreter reads as small talk is searched (`interpret.chat_guard`). A question about the
  app, the person's data or how things work ("who can see my saves", "how many recipes did I save"), a question about
  a pick ("which one should I pick") and a statement ("I saved so many reels") stay small talk.
- **Checker's near-variants** (`tests/test_round8_checks.py`): a real name written in lower case stays a thing when a
  slash or hyphen marks it ("shadcn/ui", "react-hook-form"), when it is a list line's name ("- lucide - clean icons"),
  or when the caption is written without capitals; "tools and resources for designers" and "cafes and restaurants in
  Lisbon" stay one ask (a part that is only its kind word shares the others' topic); the opening line drops "the best",
  "top 5" before the kind; one marked line, a quote or a bracket is not a list.

## Requests for a kind of thing (round 9, slice U, DESIGN.md section 12)

- **The details call is told the kind asked for** (prompt `extract_v4`): "Kind asked for: "UI/UX libraries"" on its
  own line, and a thing is "yes" only when it is itself one of that kind, something to use, install, apply to, visit,
  read or buy as that kind; a part, a term the post explains, a category, a step or a tip is "no".
- **A clear pick whose text names nothing still leads**: "I recommend ..." with its key points and its link, the line
  "The names are in its slides, not its text." when its title promises a list, "Or try these:", then the things other
  posts name under "Named in other saves, close to what you asked:". The answer never says "Nothing I found is a clear
  fit" beside a post the composer judged clear.
- **Steadier reads**: a candidate whose own text names the kind ("library" for "UI/UX libraries") is read for things
  before candidates that only list things.
- **"what apps should i use to edit photos on my phone"** is searched ("apps to edit photos on my phone"), never
  answered with a question back.
- **The kinds evaluation**: `python3 -m mvp.eval_kinds` (see "Test it without a phone").

<!-- round 11, slice H -->
## Ask your watch history (round 11, slice H, DESIGN.md section 18.H)

Read and counted by code, with no model call (`history.py`).

- **"Which channels do I watch the most?"**, "what did I watch last week", "how many videos about blender have I
  watched", "when did I first start watching cooking videos", "what did I watch on October 30", "how has my guitar
  watching changed over time", "did I watch more in October or September", "whats my most rewatched video", and
  the same in Spanish. Watched means watched (likes are "liked"); friends' posts are never counted.
- Every answer says its window back with dates, and says where your export ends when the window reaches it, with
  the words that get the export steps. A window after the export says so and answers for the latest stretch it can
  see.
- Then: "and last month?", "what about youtube", "what about guitar", "show me them", "more", "the first one".
- "Send me my top channels every month" is answered now, with a plain line that a history rule isn't possible yet.
- Offline checks: `python3 -m pytest -q mvp/tests/test_round11_h.py` (a made-up watch history, `tests/h_library.py`).
<!-- end round 11, slice H -->

## Understanding: trends, the theme check, the recap (round 8, DESIGN.md section 14)

All read and counted by code, with no model call.

- **"What have I been into lately?"** (also "what's rising", "what's fading"): what they kept in the 8 weeks up to
  the newest date in their library, against the 6 months before, topic by topic: rising, steady, fading or too few to
  tell, with the counts ("posts that mention it") and how that compares with what they said they are working toward
  (with nothing kept in the 6 months before, every topic is "too few to tell").
  Likes are counted apart; watches and friends' posts never count; personal topics never appear. "every export" right
  after it makes a rule that sends it again with each new export ("my rules" says so).
- **The theme check**, asked once after that first answer (never during the setup): "1 practise, 2 for fun, 3 someday,
  4 not me". "not me" topics are left out of everything the bot says about them and never come back from a new guess,
  but asking for them by name still finds those posts. "climbing is pursue now" changes one; "what did I park?" lists
  the someday ones.
- **"Recap"** (also "my week", "how did my rules do"): the last 7 days in at most 6 lines: what each rule sent or held
  back and what they said about its picks, to-dos, what is coming up, calendar links, the library's newest date and
  the next export, and at most one suggested rule when they asked for the same topic 3 times on 2 days or more ("yes"
  shows the preview first; never for a personal topic or a word like "tools" or "advice", and not while a rule
  preview waits for YES). "every sunday at 6pm send me a recap" makes it a rule (preview, then YES;
  "a recap of new pasta recipes" stays a search and "remind me to recap my week" stays their reminder); a week with
  nothing to report sends nothing. It is never offered at setup.
- Live check of the counts, nothing personal printed: `python3 -m mvp.attention ../data/all --store
  ../data/mvp/mvp.sqlite`.

<!-- round 11, slice M -->
## What have I learned about X (round 11, slice M, DESIGN.md section 18.M)

- **"summarize what I've learned about sourdough"** (also "what have I learned about X", "what do my saves say about
  X", "the main ideas across what I watched on X", "what do these say" after an answer): read by code, no interpreter
  call. Many fitting posts and videos are read (their own text: captions, video descriptions), and the reply gives 3 to
  6 points, each with the posts it came from (title and link), then "From 4 videos and 2 posts; 3 more fit but say
  nothing in their text." and that it read titles, descriptions and captions, not what is said in the videos. Every
  point is checked by code against the text of the posts it cites; one that cannot be traced is never shown. A repeat
  ("every week") or an action ("email me") is never this read. One time window is (the merge of round 11):
  "summarize what i watched last month about X" reads only what was watched then and says the window back.
  `MVP_SYNTH=0` switches it off.
- **The evaluation** (live, about $0.10 a run): `python3 -m mvp.eval_synth mvp/evalset/synth --mode before|after --out
  <folder outside git>` with a new `MVP_HOME`, `MVP_LEDGER_HOME` and `MVP_TOTAL_CAP_USD`: 12 made-up requests on a
  made-up library; counts only to `counts.json`, the made-up replies to `transcript.md`.
<!-- end round 11, slice M -->

## Your own agent (MCP, prototype)

A read-only server that lets the person's own AI agent (a desktop agent app on the same computer) search and read
their saves, profile, rules and lists (DESIGN.md section 15; amendment A-011, Proposed: founders only for now).

- **Start**: nothing starts it but the agent app, which runs `python3 -m mvp.mcp_server --person <handle>` over stdio
  (no port, no network listener, no scheduler). In the app's MCP settings (for example its `mcpServers` config):
  ```json
  {"mcpServers": {"digest-saves": {
    "command": "python3",
    "args": ["-m", "mvp.mcp_server", "--person", "+15551234567"],
    "env": {"PYTHONPATH": "<repo>/experiments", "MVP_HOME": "<repo>/data/mvp", "OPENAI_API_KEY": "<key>"}}}}
  ```
  Environment names it reads: `PYTHONPATH` (the `experiments/` folder), `MVP_HOME` and `MVP_LEDGER_HOME` (as the bot
  uses them), `OPENAI_API_KEY` (only for `search_saves`: the library's engine embeds the query). The key then sits in
  the app's config file: keep that file private, or leave the key out and only the tools that do not search work.
- **What it can see**: the person's own saves (the post text cut to 600 characters in a search, the whole text for one
  save), what the bot knows about them (no email address), their rules and open to-dos, and what they've been into
  (the chat's trends lines). **Never**: friends' posts, anyone else's data, posts and lines on personal topics (health,
  money, religion, politics, relationships, sexuality) unless started with `--include-sensitive`. Every result starts
  with a line telling the agent that post text is data, not instructions.
- **What it can do**: read. It cannot send, schedule, run a rule, add a to-do or change anything; the store is opened
  read-only. Each call adds one row to `action_log` (the tool and counts, never the query); a search also leaves what
  any bot search leaves in the library's folder: a ledger row and the query text with its vector in the engine's query
  cache (`corpus/emb/*_queries/`), which "delete my data" does not clear. "what did my agent ask"
  in the chat shows the counts per tool and day.
- **Where the text goes**: whatever a tool returns goes to the agent app and then to that app's own model provider,
  under that provider's terms, not ours.
- **Cost and memory**: a search costs what any bot search costs (the query's embedding), counts toward the person's
  daily limit, and stops with a plain error over it. The first search starts the server's own engine for the library:
  about a minute and about 2.5 GB of memory for a large library (BRIEF-10), beside the bot's own engine.
- **Turn it off**: remove the entry from the agent app's settings (or quit the app); the server stops with it. To stop
  one person's access at once: `UPDATE people SET paused=1 WHERE handle=...` (every call is refused while paused).

## Export and share

- **"export my data"** ("download my data", "send me everything you have on me") writes one folder
  `MVP_HOME/outbox/<hashed person folder>/export-<date>/`: `rules.json`, `todos.csv` (title, due date, notes, done: a
  to-do app can import it), `todos.md`, `profile.json`, `answers.md` (each answer with its links), `saves.csv` (id,
  link, platform, kept date, how: no post text, no friends' posts) and `README.txt`. **"export my lists"** writes only
  the two to-do files (`lists-<date>/`). Then "email it to me" sends the files to the confirmed address (a file over 5
  MB stays in the folder). "delete my data" removes these folders too.
- **"share it"**, "share the second one", "send this to my sister", "forward this" after an answer: the bot sends one
  message with nothing about the person in it (the post's title and creator, a line of its own words, the link), then
  "Press and hold that message to forward it. I can't send to other people myself." For a thing of an items answer
  ("share the fourth one", "share Iconoir"), that thing's words and its post's link. The bot never sends to anyone
  else, and never keeps or repeats who it is for.

## Rules, as the person sees them

- Each rule has a number of its own, given when it is made and never given again ("stop 3" always means the rule the
  bot called rule 3, even after a one-time reminder before it has finished). "my rules" lists them by that number.
- "every 2 days at a random time", "every other day at 7am", "a few times a month", "randomly, about twice a week":
  code keeps the spacing and the randomness the message states (a random minute inside 9am to 9pm, or the part of the
  day they named, on each due day; never in quiet hours). "Once in a while" asks how often, and "yes" takes the
  default it offers (about once a week at a random time). "Every other week on a random weekday" is one send in every
  second week, on a day drawn at random ("once every other week at a random time on weekdays").
- "when I say boost, send me a motivational video" is saved with their word: "boost" (any case) runs it, read by code
  before any model call. "When I send you a link" or "when I text you" is an event, not a word, and gets no word.
- Reminders in the person's own words and their to-do list are what they asked for: they are not counted as
  unanswered sends, never ask "Still useful?" and are not paused when the person is quiet. A rule that, with their
  other daily rules, needs more than the daily limit of timed sends says so when it starts.
- "not this creator" after an answer leaves that creator out of every later answer (unless a request names them) and
  shows in "what do you know about me".
- **Round 8, rules beyond timing (DESIGN.md section 13)**, all read by code with no model call:
  - "remind me 3 days before the NASA one closes" (no number: 3 days; "a week", "the day") after an answer sets a
    reminder at 9am that many days before the date in that thing's own words, and says both dates and how far away
    they are. Too little time left: the next 9am. A passed date: said, nothing set. No date in the post: one question,
    and the next message ("dec 5") gives it. "... and put it on my calendar" adds an all-day entry on the date. When it
    comes it opens with "Reminder: X's deadline is 30 November (in 3 days)."
  - A new daily (or random) rule that searches the saves stays quiet on a day with nothing new: one line the first
    time ("I'll stay quiet until there is"), then nothing, and those days never count as unanswered. "tell me even if
    there's nothing" keeps the old "Nothing new ... this time" message; rules made before this round keep it too.
  - "remind me every morning at 8 to apply to the NASA internship until I've done it" repeats until a bare "done" (or
    "did it", "applied") after one of its sends: "Rule N is finished."
  - A to-do a day past due gets one nudge ("... was due yesterday. Reply "done 2", "tomorrow" or "drop it".), never in
    quiet hours or a snooze; "no overdue nudges" stops them. Right after the nudge, a bare "done" ticks that to-do off.
    One nudge at a time: the next waits until the person answers (or 12 hours), so "drop it" is about the one asked.
  - A thing sent later (a dated reminder, or "remind me about it on Friday") says how far its date is from the day it
    is sent, and two reminders for two things of one post each send their own thing.
  - The model never sees "until I've done it" (live, it asked a question instead of making the reminder); code reads
    those words from the whole message.

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
To pause one person: `UPDATE people SET paused=1 WHERE handle=...` in `data/mvp/mvp.sqlite`. "delete my data" removes
the person's rows, their inbox folder (waiting, failed and half-imported exports) and what was derived from their
libraries, and lists the request in `data/mvp/deletions.jsonl` with every library folder that was theirs
(`libraries`); a founder removes those folders (never a library someone else still uses) and the message thread,
then confirms to them. A person listed there is not added back from `people.json`. The test page keeps its own list
(`deletions-webtest.jsonl`), so a deletion typed there never touches the real bot. The cost ledger names a person by a
keyed hash of their handle (`person_key.txt` beside the ledger); a deletion line counts any older ledger rows that
still hold the handle (`ledger_rows_with_handle`).

## What is where

| File | Job |
| --- | --- |
| `bot.py` | Start-up: channel, store, people, engines |
| `runtime.py` | The run loop: message log, workers (one person at a time per person), joining quick texts, scheduler thread |
| `core.py` | Message handler, executor, scheduler rules. The only code that sends |
| `interpret.py`, `prompts/interpret_v5.md`, `schema.py` | Message to a validated form for every intent (RuleSpec v 2); temperature 0, a seed, a 6-hour cache. Code completes what the message says in so many words: a target for every rule command (all rules, or the rule whose topic is named; "the next two" is a count), the section 11 times for "twice a day", a one-time surprise as one random moment, "this week" as an end on Sunday, the days a clarify keeps, "this week's pasta now" as run_rule, a time for an open to-do as its due time, "put a few recipes on my list" as an ask with todo.add, an output of a new ask in its own do list, "no mushrooms" as avoid, a fact inside an ask as a profile note, nested month weeks made flat (`interpret_v4.md` was tried in slice 6 and scored worse: not in use) |
| `profile.py`, `prompts/profile_guess_v3.md`, `prompts/profile_merge_v3.md` | The person's profile: the guess from their library (checked and counted by code, the sensitive-topic filter, cached per library build), merging what they say, the lines for the interpreter and the composer, "what do you know about me", level moves |
| `onboarding.py`, `prompts/first_requests_v1.md` | The setup after consent: the read, their answer merged, email and time zone, the export routine, three checked first requests and the morning-rule offer; "set me up again" |
| `eval_rules.py`, `evalset/` | The rule evaluation runner and the development half of the set |
| `eval_kinds.py`, `evalset/kinds_dev.jsonl`, `evalset/kinds_results.json` | The kinds evaluation (round 9, slice U): invented requests for a kind of thing, the runner, and its results as counts |
| `todos.py` | To-do lists, due reminders, the one overdue nudge and its answer (round 8), undo records, library counts |
| `actions/` | The action registry (`__init__.py`: names, params, needs, module, order) and one module per action: `message.py`, `email.py` (SMTP or the outbox), `calendar.py` (Google link and `.ics`), `todo.py` (picks or ingredient lines on a list); `base.py` holds what each action gets and returns |
| `outputs.py` | Runs a spec's `do` after composing (once per answer, logged, one line each in the reply); acting on the last answer now or later; the email address and its 6-digit code |
| `contact_card.py` | Writes the bot's `.vcf` contact card, for the founders to host |
| `retrieve.py`, `engines.py`, `libview.py` | Candidates from the person's own library (Q8 search, cached ranked lists, filters, orders, recent and fixed items) |
| `ytinfo.py` | A YouTube candidate's length and description from the official `videos.list` (`YOUTUBE_API_KEY`), kept at most 30 days (the scheduler purges once a day: the cache, details read from descriptions, cached composed answers, and kept answers and emails with a YouTube pick) |
| `outside.py` | New picks from outside the library: YouTube `search.list` with the person's own words, checked by `videos.list`; the sensitive-topic stop, the daily limits (with the shared count file) and the 24-hour cache |
| `refresh.py` | The inbox per person, the import (demo importer, without the messages folder), the cost cap, the library switch, recovery of an import cut off by a stop, new_items rules, library_status, and the export routine with its reminders |
| `mcp_server.py` | Round 8, slice B: the read-only MCP server for the person's own agent (stdio, one person, seven tools, the store opened read-only, the data line, personal topics left out and counted, one `action_log` row per call); "what did my agent ask" |
| `export.py`, `share.py` | Round 8, slice B: "export my data" / "export my lists" (the files, the email of them, removal on deletion); the message to forward for "share it" / "send this to <someone>" |
| `cancel.py`, `cancel_routes.json` | Round 9, slice B: the cancel helper (the trigger, the guard before a rule stop, the replies, the check reminder, the `cancellations` rows) and the checked ways out per merchant |
| `receipts.py` | Round 9, W9: "what did you do for me", read by code from the bot's own rows |
| `actions/web.py`, `actions/_tasks.py`, `actions/ticktick.py`, `actions/todoist.py`, `actions/webhook.py` | Round 9, E: the one HTTP helper and the connectors by token (TickTick, Todoist) and the webhook, on `places.py` and `connectors.py` |
| `settings.py`, `tokens.py` | Round 10, slice K: `secret(name)` (the environment, then the sealed store), the page's status line; sealed sign-ins and settings (AES-256-GCM, 0600 files, the key) |
| `errand.py`, `prompts/errand_v2.md` | Round 10, slice W7: the errand form: one small model call after the interpreter refused or chatted; code checks the form and hands the person's words to the helper's own entry |
| `phrasing.py` | Round 10, slice W: everyday wording read by code: `normalize` (openers, closers, texting shorthand; a second try for the request reads only, never stored or sent to a model), `parts` / `clauses` (two asks in one message), `TIME_WORDS` |
| `captionmark.py` | Round 10, slice S: the caption mark (`cm-v1`, derived, versioned), what the person said about it (`caption_feedback`), the order rule, the doubt line, `fit_reads` and the thumbs-down question |
| `panel.py` | Round 10, slice D: the test page's Connections panel (seal, remove, states only; whether sending is on) |
| `grants.py` | Round 10, slice G: a rule's place read from the person's words, its standing yes (grant: made, checked by `actions.perform(..., grant=)`, ended), each run's add and its line, undo, "stop adding to X", "use X for rule N", the standing permissions in receipts |
| `yt_auth.py`, `ytreads.py`, `actions/youtube.py`, `actions/link.py` | Round 10, slice Y: the person's YouTube sign-in by a code (device flow), the YouTube and Instagram reads and answers, the YouTube Data API calls with quota counting, and the links the person taps |
| `browser.py`, `browser_guard.py`, `browser_host.py`, `browser_vm.py`, `browser_routes.json`, `actions/browser.py` | Round 10, slice V: the browser that cancels (off by default): the conversation and the runner, what may be pressed, the window on this computer, the browser watched at `/vm`, the merchants' paths, the last press |
| `tests/fakes/` | Round 10, slice K: in-process fakes for tests and the self-test: `fake_llm`, `fake_mcp`, `fake_oauth`, `fake_google`, `fake_merchant` |
| `mcp_client.py`, `mcp_mappings.py`, `oauth.py`, `actions/mcp.py` | Round 10, slice C: the bot as an MCP client (pinned tools, codes only, the SDK as transport), the servers and mappings in code (Todoist `add-tasks` / `delete-object`), our own OAuth sign-in and refresh, and the `todoist.mcp_add` action with connect / check / disconnect |
| `selftest.py`, `selftest/` | Round 10, slice T: the self-test (conversations, checks, fakes, dry mode), its made-up library, `truth.json` and `conversations.jsonl` |
| `followup.py` | Round 8, slice B: export, "email it to me" after one, share and "what did my agent ask", read by code before the model (`IntegrationReadsMixin`). A follow-up that changes the request becomes a new search (round 7); what code reads without the model: plain commands ("stop 2", "pause 1", "resume all", "skip 3", "run 1", "done 2", "remove 3", "my rules", "undo", "help"), "another" / "more" / "next" (the last request, unchanged), round 8's rule phrasings ("remind me 3 days before it closes", "until I've done it", "don't text me if there's nothing", a bare "done", "tomorrow" / "drop it" after a nudge, "no overdue nudges"), "only new stuff, not from my saves" (outside only, same topic); a question about a shown pick's details ("what are the steps for the first one?") answered directly from its own text, or one honest line and its link |
| `compose.py`, `prompts/compose_v5.md` | The model chooses (verdicts clear / close / no, a backed "because" given as a bare clause, must-haves, the person's level); code checks it (a finished-result must-have is "no" for tips-only text, though such a pick can still be the closest when nothing else is; a reason may name a level only when one may be used; an unbacked reason is left out; "mini" / "short" / "quick" is a length bound checked against YouTube's length); the composer's opening line only when its words are the request's (else one built by code); a cached answer per spec and candidates, kept no longer than it can be reused |
| `lang.py` | The answer's fixed phrases in Spanish (with the outside block and the level note that ride on it); any other language gets an all-English answer, and the composer is told to write English. A rule's preview, start line and timed sends are English only for now (their timing words have no Spanish yet), so a rule made in Spanish is set up and sent in English, never in two languages at once |
| `extract.py`, `prompts/extract_v4.md` | The named things a pick's text lists (items: name, its words, its date; round 7; what an item is, enforced in code, and which posts list things: round 8; the kind asked for on its own line and "fit" yes only for a thing that is itself of that kind: round 9, slice U), ingredients, steps and key points from a pick's whole text, checked line by line, cached in the `facts` table (a line is never shown cut off: a step or key point is kept whole up to 260 characters, a sentence that only describes the video is not a step, and steps are shown only when two or more remain); a recipe, workout or make-or-build tutorial gets its details for the recommended pick even when none were asked for (a talk, a list of habits or an opinion gets none, unless its text writes out a recipe or a workout); when details are asked for, the best of the top 3 that has them all is recommended |
| `dates.py`, `answers.py` | Round 7: posted dates (the Instagram link's shortcode, YouTube's publishedAt), time-sensitive requests, dates read from a post's text (passed, old, ahead), no stale claims; the date order of picks and the choice of the items answer |
| `attention.py`, `digest.py` | Round 8: what they have been into lately (windows, shares, labels, the live count script) and the theme check's messages; the recap and its one suggested rule (DESIGN.md section 14) |
| `history.py` | Round 11, slice H: history questions read and answered by code (the form, the record of every event, windows, rankings, first and last, timelines, follow-ups; DESIGN.md 18.H); the merge: the help's and the setup's examples from the person's own counts and topics |
| `lengths.py`, `themes.py`, `facts.py`, `prompts/theme_name_v2.md` | Round 12, D: the official lengths of watched videos and the Short rule; themes by code with names by one call per field, a topic mapped to themes by code; the fact sheet of a history question (DESIGN.md 19.D) |
| `synth.py`, `eval_synth.py`, `evalset/synth/` | Round 11, slice M: summaries across many items, each point traced by code (DESIGN.md 18.M), its made-up evaluation; the merge: one time window by slice H's words |
| `videoask.py`, `eval_videoask.py`, `tests/fakes/fake_gemini.py` | Round 11, slice Q: asking a YouTube video itself through Gemini, off unless `MVP_VIDEO_ASK=1` (DESIGN.md 18.Q; A-017, Proposed), its evaluation (fix pass 2, 18.L2; the list of videos is a file outside git), its fake |
| `brain/` (`tools.py`, `results.py`, `names.py`, `windows.py`, `context.py`, `verify.py`, `fallback.py`, `planted.py`, `provider.py`, `loop.py`, `answer.py`), `prompts/brain_v1.md` to `brain_v3.md`, `eval/brain_planted.json`, `eval/build_brain_planted.py`, `eval/brain_audit_cases.py`, `eval/brain_attack_cases.py`, `eval/convert_insight_cases.py` | The brain (not wired; design/brain_v1/SPEC.md and DECISIONS.md, A-021). Step 1 (offline): the processor's read tools over the fact sheet (the result envelope, names, window words, the saved context), the answer verifier (markers checked one sentence at a time with insight's checks), the code lead, the planted set and its scorer (`python3 -m mvp.brain.planted`; the step 1 audit's and the verifier attack's sentences on frozen real tool results, scored apart). The thin live slice: the Claude provider (Haiku 5.5, every request in the ledger) and a fake, the turn loop with one repair round, the answer code sends (scope line, private line, offers), prompt `brain_v3`, `eval_brain.py run --half tune|heldout` (live, made-up library only) and `count` (count_tokens). After the slice: the read tools' faults fixed, `eval_brain.py run --set fresh --half a|b|all`, `read` and `marks` (readings, the reading sheet, hand marks; the auditor gives hints only), `eval/brain_reading_rubric.md`, and the fresh eval set `evalset/brain_fresh.jsonl` (built by `eval/build_brain_fresh.py`; half B locked). Nothing in the message path calls them. DESIGN.md sections 21 to 23. Tests: `test_brain_tools.py`, `test_brain_verify.py`, `test_brain_seam.py` (the verifier on the tools' real results), `test_brain_eval.py`, `test_brain_step1_fix.py`, `test_brain_slice.py`, `test_brain_tune.py`, `test_brain_fix.py`, `test_brain_toolfix.py`, `test_brain_evaltools.py`, `test_brain_fresh.py`, `test_brain_after_slice.py` |
| `render.py` | What the person reads, as parts (text and link), the items answer among them: a channel that shows link previews sends each link alone; the same answer as an email (plain text and simple HTML) |
| `schedule.py` | Every date and time (every timing form, seeded random moments, quiet hours), in the person's zone |
| `scheduler.py` | Timed sends and their guards: skips, snooze, quiet hours, daily limit, retries and holds |
| `store.py`, `llm.py` | Records (including each answer as shown, the action log, the outbox, outside searches and imports); model calls, the cost ledger (an import's build is written there too) and the caps |
| `channels/` | Test page (`web.py`, `web_page.html`: thread, Profile, rules, To-dos, Outbox and Exports panels with the upload box, "Start over" through the setup), terminal, Mac Messages, Sendblue |
| `trace.py`, `run_requests.py` | What happened to a message; a batch of test requests |
| `tests/` | 5999 offline tests (2 more skipped where Chromium cannot start) (`test_brain_toolfix.py`, `test_brain_evaltools.py`, `test_brain_fresh.py`, `test_brain_after_slice.py`: after the slice (DESIGN.md section 23): the read tools' faults, the eval's readings, rules, hints, reading sheet and marks, the fresh eval set and its half B pin, and the seams of their merge; `test_brain_tools.py`, `test_brain_verify.py`, `test_brain_seam.py`, `test_brain_eval.py`, `test_brain_step1_fix.py`: the brain, step 1, offline and not wired (the row `brain/` above; `test_brain_step1_fix.py` is step 1's close, DESIGN.md section 21: each class two audits found, reproduced and fixed by construction); `test_brain_slice.py`, `test_brain_tune.py`, `test_brain_fix.py`: the brain's thin live slice with the fake provider only (DESIGN.md section 22; `test_brain_fix.py`: each class the hand recount and the verifier attack found, its false sentences dropped and a true twin kept); `test_charts.py`: the chart module, a spec in and SVG, PNG and text out, not wired into answers yet; `test_round12_pass6.py`: round 12's sixth pass (DESIGN.md section 19.P6): the parts of a sentence that can be false worded by code, whoever wrote it, and its second round (a change's subject, saved and never opened on every platform, a channel behind a theme it is not in, a record's own Shorts share, a tie, new videos since a season, long under without Shorts, a weekday, the week of a date, one-value and end-in-base changes, small moves in Spanish, a first's arc after another first): a first or a last by the instant of its open and a day's items in the order opened, an inside share's base in its sentence, Shorts with its capital and base, a count's noun from the filters in force, a change with two values of one measure and no side clause without one, without Shorts as the videos known to be long, a usual day on the day's base, saved and never opened, one fact once at any depth of the sheet, charts that say something and round once, a window after the export, a rare word mapped to no theme it is not about, moves under 3 points not said, a first's arc, a day as compact rows, a past season against its year, one base phrase, a day's new channels over all its channels; `test_claude_backend.py` and `test_claude_review.py`: the Claude text path (DESIGN.md section 20), 49 tests; `test_round12_claims.py`: round 12's fifth pass (DESIGN.md section 19.A): every percent with its base worded by code whoever wrote the sentence (once for the answer's own base, in every sentence under a filter), Shorts shares of all the YouTube videos and never a theme's or a channel's own said of them, a channel under a topic, peaks over every span of the window's length, a topic's row and a first of the sheet's own scope, an area's two-word name, a season not begun, a range's end said once, each value of a change with its year, and the sentence paths in the trace; `test_eval_claims.py`: the auditor (`eval_claims.py`) against hand counts of the made-up library; `test_round12_pass4.py`: round 12's fourth pass (DESIGN.md section 19.P4): a filtered sheet's shares and counts said of its own base (a topic, a channel, without Shorts, one platform) in every sentence, so-what and chart caption, the answer to "what was i into" by its areas and what peaked then with the move to Shorts as a bullet and no filler, one fact once by record and measure (code's lines, the chart's rows, the so-what), a so-what only with a step code takes, offers that fit, words of the next place, a theme's channels with its share, a count that says what it counts, and the live reading's findings; `test_round12_pass3_fix.py`: round 12's third pass, the second fixer (DESIGN.md section 19.P3 fix): the leader's move leading "lately" and what fell as the so-what with its follow-up, one fall never said at two levels nor half again, a span's dates said once, a flat move, the last N days the record holds, a base after the change's last value, the Shorts as one fact, a day in counts and never set against the export's cut-off, a change between two closed years, the year of the turn (Spanish too), a season that moved to Shorts, what a split is of, a first's path by its subject, a comparison's chart against the span before, a count as counted, a channels lead in words, both filters said, and the live reading's findings; `test_round12_pass3.py`: round 12's third pass (DESIGN.md section 19.P3): a word of direction or comparison with no number backed by a path whose two values support it, a change between two years about what was watched, "what have i been into lately" as a history question, nothing about Shorts without Shorts and the chart at the answer's level, one fact once and list answers as captioned cards, the so-what about the question's subject and what is changing, offers only of what the answer showed, every change with its direction and base, the eras by the leading area's share, what set a season apart, the channels he grazes and follows, what the month bars count, the daily cap in the trace, and the live reading's findings; `test_round12_pass2_fix.py`: round 12's second pass, the second fixer (DESIGN.md section 19.P2 fix): a theme said inside an area it is not in, "mostly" with an area's own themes added, the window's median bound to one side, a count said as a share, a Shorts share said as long-form, rank, ordinal, direction and watch-time words, a day never against the day before, a topic of one area not told by area, eras that come back, a change led by the move to Shorts, code's must lines (what the top channels are, the usual day, the balance against last year, Shorts as a share), so-whats worth saying and never twice, bullets that repeat the answer or each other, Shorts shares that count long streams, "new" only with a handful before, and the live reading's findings; `test_round12_pass2.py`: round 12's second pass (DESIGN.md section 19.P2): numbers bound to their thing by sheet paths, rank and amount words against the sheet, the planted-falsehood sets, no total of video length, themes found by real path or content and their status, areas, eras, the so-what candidates, no export hint on a history answer, filler, a topic's count code can defend, a comparison in words, a day against the usual day, what each top channel is, one-line chart rows, the writer's deadline, Spanish "changed", and the live reading's findings; `test_round12_fix.py`: round 12's fix (DESIGN.md section 19.F): a form that loses its answer or observations filled by code from the sheet, rank and order words, 'mostly' for a fifth, the weekday baseline, runs of numbers and names, a day's 'on 1 day', the chart's 12 months, the so-what once and on topic, a first's path, Spanish 'changed'; `test_round12_merge.py`: the merge of round 12 (DESIGN.md section 19): the fact sheet and the writer wired into hook 8h, the seams (the sheet for every kind of the brief, offers taken in their own words, a day's cards, one place for the hint and the friends line, what a run stores, the caps and one call), and the live run's defects; `test_round12_w.py`: round 12, builder W (DESIGN.md section 19.W): the history writer's checks against made-up fact sheets (every planted false sentence dropped, every true one kept), its layout, chart and offers, the hint and the friends line, and the quiet limits of the code replies; `test_round12_d.py`: round 12, D (DESIGN.md section 19.D): lengths, themes, the fact sheet of the 8 questions, the misread questions, their follow-ups and traps; `test_round11_fix2_checks.py`: the check of round 11's second fix pass (DESIGN.md section 18, part "18.L2 check"): 50 made-up messages and 40 traps as tester and operator, setting off and on, a video's answer with no points, several not covering it, orders, no timestamp, the title said again, the caps and what an ask keeps, the export end in every answer, never asking a video with no title unasked, "ask video 2" after a recall, a fit that keeps no watched item, a YouTube title with hashtags; `test_round11_fix2.py`: the second fix pass of round 11 (DESIGN.md section 18, part "18.L2"): a video's answer that answers the question or says it doesn't cover it, a point that only says what the video is, never a video with no title offered or asked, the typed question kept with the offer, "ask the video" after a recall, "ask them" with nothing shown, the six shapes that reached the model, few watched items said as "mention", reels in a watched summary, the export hint once in 6 hours, a summary's other word forms; `test_round11_fix_checks.py`: the check of round 11's fix pass (DESIGN.md section 18.L, part "18.L check"): 70 made-up messages and 50 traps, the findings by their exact messages, the export end in every answer that reaches it, a windowed summary after a recall, summaries' sources and what they read, asking up to 3 videos with failures, orders, caps and other yeses, what an ask keeps; `test_round11_fix_merge.py`: the merge of round 11's fixes (DESIGN.md section 18.L): the offer of a watched YouTube video through fix A's function, "ask them" after a recall, a watched-only summary by the record and the fit, the export hint once in 6 hours, receipts, export and delete after three videos, the help's line, one item left by the fit; `test_round11_fix_a.py`: fix A of round 11's live check (DESIGN.md section 18.LA): a recall of a video watched with its day and card, first, last and list by the library's own fit, comparisons answered first, timelines from the first count, accounts and channels, the footers once in 6 hours;  (`test_round11_fix_b.py`: fix B of round 11's live check (DESIGN.md section 18.LB): numbered sources, what a summary read, points that answer the question asked, "ask them" across 3 videos, one note then "yes", capitals, a video answer emailed, the offer of a watched YouTube video; `test_round11_checks.py`: the check of round 11 (DESIGN.md section 18.X): windows the merge read wrong (29 February with no year, "this yr", Spanish "los ultimos 7 dias", weekends, "N weeks ago", "between X and Y", a holiday with its year), chat after a history answer never a new topic, likes and saves never said as watched, a channel counted as its ranking counts it, the export end of each platform a window reaches, the person's time zone at month and day edges, 60 traps never a history question, summaries dropping every bad point (no source, the wrong item, a caption's order, 30 at a time) with nothing made, and asking a video: orders, other videos' titles, times past the end, a 10,000-word answer, errors, the caps before the call, and what an ask keeps; `test_round11_merge.py`: the merge of round 11: one hook order, a window inside a summary, the summary's offer to ask a video, a history pick put in view and asked, receipts, export and delete of what is kept, the help and the setup leading with the watch history; `test_round11_h.py`, `test_round11_m.py`, `test_round11_q.py`: round 11's slices H, M and Q; `test_round10_livefix_checks.py`: the check of the live fixes (DESIGN.md section 17.L, "17.L check"): "I'm in" with the fillers people text never a time zone, the connector menu and "what r u connected to" in texting words and Spanish, a new connector never told YouTube's Google steps, no value in any connector answer, a tester never told the operator's steps, the help naming only sites the browser can do, Instagram asks in Spanish, a caption's own "like and follow" never read as the person's ask, the practice merchant's nine flows with the receipts line for each outcome, "allow streamly" again while its run is open; `test_round10_livefix.py`: the live check of 19 Nov (DESIGN.md section 17.L): a bare "I'm in" never a time zone, the receipts in the page's own words after the browser pressed, the true reason when the browser is on but not for a site, Instagram actions asked of the bot said plainly with the pick's link and never a list or a feedback row, the connector menu built from the registry, "connect X" for a merchant, Instagram, email and any other app, two things to cancel in one message, the YouTube set-up for the person who runs the bot, the help's apps line; `test_round10_selftest_live.py`: the first full live self-test's fixes: the clock stopping at a rule's slot and "next run", a request to do something daily as a daily rule's preview, a model's "now" minute never a rule's time, an email to a group, a neutral title mid-sentence, a plain opening when every fit is doubted, a tutorial's steps in the video, a key point without its title, YouTube's lines for a tester; `test_round10_checks_reading.py`: the check of round 10's reading and answers: "slop" in everyday words asks first, a mismatch on the pick its own clause names, a complaint about the request asked about first, "i want to unsubscribe from that channel" never a merchant, two asks in one message reaching both helpers, everyday and Spanish words for the new helpers, Instagram actions no app may do said plainly; `test_round10_checks_acting.py`: the check of round 10's acting and secrets: a merchant's redirect to another site never leaves the machine, a denied site or an IP address in any spelling refused, secrets in everyday words refused before any model, the take-over view for the first browser only, the test page answering only its own address, a last button showing an offer under a cancel label never pressed, links with other dots cut from the quote, a tester's operator words acting on nothing; `test_round10_merge2.py`: the second merge of round 10 (Y, V, T): a rule adding its YouTube picks to a private playlist under its yes, "undo" through the route that made the adds, "delete my data" and "export my data" with YouTube and the browser, a tester connecting YouTube, one Instagram export line, YouTube and the browser said the same in the chat, the panel and the footer, the errand form's YouTube connection, and the self-test's findings (how they pay is never the gym's name, "do it for me" after the steps, a title never a note to assistants or a step); `test_round10_youtube.py`, `test_round10_browser.py`, `test_round10_vm.py`, `test_round10_selftest.py`: slices Y, V and T (the browser tests run where Chromium can start, else they are skipped and counted); `test_round10_merge.py`: the merge of round 10: the hook order of DESIGN section 17 in the source, one rule preview with the app's line, a rule adding to Todoist by sign-in under its grant (a changed tool, a sign-in that needs the person, a broken stream), "delete my data" revoking a sign-in first, strong-marked reels left out of a rule's adds, the normalised form only for hooks 5 to 8z, the errand form through code reads only, the panel and the footer agreeing, the three questions after a rule's adds, the stubs; and its review: a reel the person called fine or a mismatch counted that way in a rule's adds, a changed Todoist route ending the grant with one line, a tester never told to connect an app; `test_round10_k.py`, `test_round10_wording.py`, `test_round10_errand.py`, `test_round10_slop.py`, `test_round10_sending.py`, `test_round10_grants.py`, `test_round10_mcp.py`: round 10's slices K, W, S, D, G and C (DESIGN sections 17.K to 17.C); `test_round9_fixcheck.py`: the check of round 9's live fix pass: a Spanish request for a kind of thing, a run-together word of any topic in the posts read, a title or a full name before a typed address, a waiting send said after an unchanged rewrite, the save words after a newer answer, the date question kept with the apply menu, no card for a brief that says it is untrue; `test_round9_live.py`: round 9's live fix pass, group A, findings 104 to 108: a typed address after the role word, a rewrite with the same words, "put this in my email" with a card open, an apply menu with no date, draft_v2's checks; `test_round9_kinds3.py`: round 9's live fix (kinds), finding 103: a run-together spelling read as its parts, a purpose that is not a must-have, the kind phrase searched too; `test_round9_checks_acts.py`: the adversarial check of round 9's acting on posts, connectors, receipts and routing: "book me a table" and "handle it" go the old way, a newer list replaces an offer menu, things numbered post by post make the bot ask, no payment or ask to the reader in a checklist, only a place name in the Maps search, a time-out said to be uncertain and a repeat warned, a refused send never "you haven't said send", a hold time never from a post's title, and what held; `test_round9_checks_email.py`: the adversarial check of round 9's email and cancelling: a question is never "send", one send waits at a time, a newer card stays open, an unknown send is never "sent", a to-do from a post never names the recipient or the merchant, no added day, number or "already" in a model draft, the cancel helper's questions never take a rule command, a stale notice address, the receipts' "you sent", the IMAP fake's allow-list, and what held; `test_round9_tokens.py`: round 9, E: TickTick, Todoist and a webhook by a setting in the environment, with a fake HTTP opener: the request shapes, the preview and yes, every status, the breaker, all or nothing, undo, the cap, operator only, connect / check / disconnect, the narrow secret guard and the guard during onboarding, no token or address in any reply, row or error; `test_round9_receipts.py`: round 9, W9: "what did you do for me" from every kind of row, honest words, newest first, waiting and undo; `test_round9_doit.py`: round 9, W10: "do 2 for me" handing a to-do to the draft, the cancel helper or a menu, ticked off only on a real outcome; `test_round9_merge.py`: the round 9 merge: the hook order in `handler.py`, and no rule-eval text or earlier stop, pause or change phrasing taken by a round 9 read, end to end; `test_round9_drafts.py`, `test_round9_mailbox.py`: round 9, slice A: emails to other people as a card with a tap-to-send link, the model-written draft and its checks, the operator's mailbox sending only after "send", Drafts over IMAP; `test_round9_cancel.py`: slice B: the rule-stop guard, the cancel helper, the notice as a draft card; `test_round9_postacts.py`, `test_round9_things.py`: slice C: numbered offers, apply, book and buy menus, "add them all"; `test_round9_registry.py`, `test_round9_mac.py`: slice D: the registry fields, the operator, app-named lists, Reminders and Calendar on the Mac, "what are you connected to", the export of connections; `test_round9_checks2.py`: the check of round 9, slice U2: with the judge an old round never leads a fresher post, the opening and closest lines count the kind the things were judged against, a number the judge's form leaves out is asked again; `test_round9_judge.py`: round 9, slice U2: the batched judge of "is it the kind" (off, on, failed, invalid, cached, the list as data), its verdicts deciding which posts count as the kind, a name written only as a handle, a thing two posts name shown once, the kind read from the request's grammar, the creator said once; `test_round9_checks.py`: the check of round 9, slice U: a title naming the request's year read first among the candidates again, the singular of each kind in "places or cafes", "what <kind> should i" only with the kind right after "what" and every asking verb left out of the goal; `test_round9_kinds.py`: round 9, slice U: the counts the kinds evaluation reads, the kind asked for in the details call and its cache key, clear picks that name nothing leading with the named things of other posts after them, the slides line only for a promised list, a post naming the kind read before lists and before the composer's other picks, a clear list with no thing of the kind not counted as the kind, "what <kind> should i" as an ask; `test_round8_live.py`: the live fix pass of round 8, findings 98 to 102: the composer's verdict leads an items answer, site names listed on lines of their own, an earlier year's post, a request for deadlines, the change in every opening line, the refilled window, a title naming the request's season year; `test_round8_checks.py`: the checker's near-variants of the live fix pass (an old round or an earlier year's post is never a clear source, deadline words alone make a request time-sensitive, an items answer with no date ahead says so, the refilled window and its counts, "this summer" said in summer, a video's names) and of round 8's answers and rules slices (lower-case names, one topic with two kind words, app questions, days counted from the send, one nudge at a time, the two live misreadings) and of its understanding and integrations slices (a label on a topic stored with another spelling, a topic starting with a digit, no "rising" with nothing kept before, no suggestion from personal or kind-word asks or while a preview waits, what is not the recap rule, a trends rule's timing in "my rules"); `test_round8_merge.py`: where the round 8 slices meet: the recap's counts of quiet days, past-due to-dos and dated reminders, labels in the suggestion and the export, the agent's trends answer, deletion of what the slices store, and each code-read phrase in and out of its own context; `test_mcp.py`: round 8 slice B, I1: each MCP tool's shape, friends never, personal topics left out and counted, the data line, the daily cap, nothing written but `action_log`, refusals, "what did my agent ask", the server over stdio in a subprocess; `test_round8_integrations.py`: I2 and I3: the export's files and phrasings, the email of them, deletion, the message to forward by pick, number and name, Spanish, what is not a share; `test_round8_understanding.py`: round 8, slice B: trends, the theme check, the recap and its suggestion; `test_round8_answers.py`: round 8 slice A2, findings 93 to 97: real named things, the posts that are read, several asks in one message, a passed-on series, a question read as small talk; `test_round8_rules.py`: round 8, slice B, rules beyond timing (a reminder counted back from a thing's date, quiet empty days, reminders until done, overdue nudges) and what code does with any form the model may return for the new phrasings; `test_round7.py`: round 7, findings 90 to 92: the items answer, dates, changed requests; `test_round7_checks.py`: the checker's near-variants of round 7 (an item's words, loose dates, reminders counted back from a thing's date, follow-ups that ask, add a creator or refine; the live donut case read as "more"); `test_fixpass6.py`: one or more per finding of the sixth live run, 88 and 89 (a message changing lasting state it never asked to change), their near-variants, the builder's audit and its checker's (one-time limits, settings carried with a request, the avoid list, styles, dropped topics, confirmations, all rules, resume, a stated kit or time); `test_fixpass5.py`: one or more per finding of the fifth live run, 84 to 87, their near-variants, and the checker's; `test_fixpass4.py`: one or more per finding of the fourth live run, 74 to 83, after a full setup, and the checker's near-variants; `test_fixpass3.py`: one or more per finding of the third live run, 65 to 73, and the checker's near-variants; `test_final_check.py`: where two review fixes met; `test_review_experience.py`: one or more per finding of the experience review; `test_review_cost_failure.py`: one or more per finding of the cost-failure review; `test_review_privacy.py`: one or more per finding of the privacy review; `test_review_reliability.py`: one or more per finding of the reliability review; `test_interpret_round.py`: the interpreter's improvement round, one or more per kind of misreading; `test_fixpass.py`: one or more per finding of the fix pass after the live run of 12 Nov; `test_fixpass_checks.py`: the checker's near-variants of those findings; `test_fixpass2.py`: one or more per finding of
the second live run, 38 to 64) |
