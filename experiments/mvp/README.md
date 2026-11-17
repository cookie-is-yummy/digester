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
- **Round 10, Todoist by its own connector** (DESIGN.md section 17.C, slice C, the operator only): with no
  `MVP_TODOIST_TOKEN` set, "connect my todoist" sends a sign-in link; open it on the computer the bot runs on and press
  Allow (the page comes back to `http://127.0.0.1:8799/callback`; `MVP_CONNECT_PORT` changes the port). Then "add it
  to my todoist" shows the tasks and adds them after your yes through Todoist's MCP server; "undo" takes them out.
  Only the tools pinned at the sign-in are ever called; if Todoist changes one, the bot stops and asks "yes todoist".
  "check my todoist" tests it; "disconnect todoist" cancels the bot's access there. A personal token, when set, is
  used first. The daily check `python -m mvp.mcp_client --discover` needs no sign-in and no model.
  Tests: `tests/test_round10_mcp.py`.

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
| `captionmark.py`, `browser.py`, `phrasing.py`, `yt_auth.py` | Round 10, slice K: stubs (`STUB = True`) giving today's behaviour until slices S, V, W and Y replace them |
| `tests/fakes/` | Round 10, slice K: in-process fakes for tests and the self-test: `fake_llm`, `fake_mcp`, `fake_oauth`, `fake_google`, `fake_merchant` |
| `mcp_client.py`, `mcp_mappings.py`, `oauth.py`, `actions/mcp.py` | Round 10, slice C: the bot as an MCP client (pinned tools, codes only, the SDK as transport), the servers and mappings in code (Todoist `add-tasks` / `delete-object`), our own OAuth sign-in and refresh, and the `todoist.mcp_add` action with connect / check / disconnect |
| `followup.py` | Round 8, slice B: export, "email it to me" after one, share and "what did my agent ask", read by code before the model (`IntegrationReadsMixin`). A follow-up that changes the request becomes a new search (round 7); what code reads without the model: plain commands ("stop 2", "pause 1", "resume all", "skip 3", "run 1", "done 2", "remove 3", "my rules", "undo", "help"), "another" / "more" / "next" (the last request, unchanged), round 8's rule phrasings ("remind me 3 days before it closes", "until I've done it", "don't text me if there's nothing", a bare "done", "tomorrow" / "drop it" after a nudge, "no overdue nudges"), "only new stuff, not from my saves" (outside only, same topic); a question about a shown pick's details ("what are the steps for the first one?") answered directly from its own text, or one honest line and its link |
| `compose.py`, `prompts/compose_v5.md` | The model chooses (verdicts clear / close / no, a backed "because" given as a bare clause, must-haves, the person's level); code checks it (a finished-result must-have is "no" for tips-only text, though such a pick can still be the closest when nothing else is; a reason may name a level only when one may be used; an unbacked reason is left out; "mini" / "short" / "quick" is a length bound checked against YouTube's length); the composer's opening line only when its words are the request's (else one built by code); a cached answer per spec and candidates, kept no longer than it can be reused |
| `lang.py` | The answer's fixed phrases in Spanish (with the outside block and the level note that ride on it); any other language gets an all-English answer, and the composer is told to write English. A rule's preview, start line and timed sends are English only for now (their timing words have no Spanish yet), so a rule made in Spanish is set up and sent in English, never in two languages at once |
| `extract.py`, `prompts/extract_v4.md` | The named things a pick's text lists (items: name, its words, its date; round 7; what an item is, enforced in code, and which posts list things: round 8; the kind asked for on its own line and "fit" yes only for a thing that is itself of that kind: round 9, slice U), ingredients, steps and key points from a pick's whole text, checked line by line, cached in the `facts` table (a line is never shown cut off: a step or key point is kept whole up to 260 characters, a sentence that only describes the video is not a step, and steps are shown only when two or more remain); a recipe, workout or make-or-build tutorial gets its details for the recommended pick even when none were asked for (a talk, a list of habits or an opinion gets none, unless its text writes out a recipe or a workout); when details are asked for, the best of the top 3 that has them all is recommended |
| `dates.py`, `answers.py` | Round 7: posted dates (the Instagram link's shortcode, YouTube's publishedAt), time-sensitive requests, dates read from a post's text (passed, old, ahead), no stale claims; the date order of picks and the choice of the items answer |
| `attention.py`, `digest.py` | Round 8: what they have been into lately (windows, shares, labels, the live count script) and the theme check's messages; the recap and its one suggested rule (DESIGN.md section 14) |
| `render.py` | What the person reads, as parts (text and link), the items answer among them: a channel that shows link previews sends each link alone; the same answer as an email (plain text and simple HTML) |
| `schedule.py` | Every date and time (every timing form, seeded random moments, quiet hours), in the person's zone |
| `scheduler.py` | Timed sends and their guards: skips, snooze, quiet hours, daily limit, retries and holds |
| `store.py`, `llm.py` | Records (including each answer as shown, the action log, the outbox, outside searches and imports); model calls, the cost ledger (an import's build is written there too) and the caps |
| `channels/` | Test page (`web.py`, `web_page.html`: thread, Profile, rules, To-dos, Outbox and Exports panels with the upload box, "Start over" through the setup), terminal, Mac Messages, Sendblue |
| `trace.py`, `run_requests.py` | What happened to a message; a batch of test requests |
| `tests/` | 2086 offline tests (`test_round9_fixcheck.py`: the check of round 9's live fix pass: a Spanish request for a kind of thing, a run-together word of any topic in the posts read, a title or a full name before a typed address, a waiting send said after an unchanged rewrite, the save words after a newer answer, the date question kept with the apply menu, no card for a brief that says it is untrue; `test_round9_live.py`: round 9's live fix pass, group A, findings 104 to 108: a typed address after the role word, a rewrite with the same words, "put this in my email" with a card open, an apply menu with no date, draft_v2's checks; `test_round9_kinds3.py`: round 9's live fix (kinds), finding 103: a run-together spelling read as its parts, a purpose that is not a must-have, the kind phrase searched too; `test_round9_checks_acts.py`: the adversarial check of round 9's acting on posts, connectors, receipts and routing: "book me a table" and "handle it" go the old way, a newer list replaces an offer menu, things numbered post by post make the bot ask, no payment or ask to the reader in a checklist, only a place name in the Maps search, a time-out said to be uncertain and a repeat warned, a refused send never "you haven't said send", a hold time never from a post's title, and what held; `test_round9_checks_email.py`: the adversarial check of round 9's email and cancelling: a question is never "send", one send waits at a time, a newer card stays open, an unknown send is never "sent", a to-do from a post never names the recipient or the merchant, no added day, number or "already" in a model draft, the cancel helper's questions never take a rule command, a stale notice address, the receipts' "you sent", the IMAP fake's allow-list, and what held; `test_round9_tokens.py`: round 9, E: TickTick, Todoist and a webhook by a setting in the environment, with a fake HTTP opener: the request shapes, the preview and yes, every status, the breaker, all or nothing, undo, the cap, operator only, connect / check / disconnect, the narrow secret guard and the guard during onboarding, no token or address in any reply, row or error; `test_round9_receipts.py`: round 9, W9: "what did you do for me" from every kind of row, honest words, newest first, waiting and undo; `test_round9_doit.py`: round 9, W10: "do 2 for me" handing a to-do to the draft, the cancel helper or a menu, ticked off only on a real outcome; `test_round9_merge.py`: the round 9 merge: the hook order in `handler.py`, and no rule-eval text or earlier stop, pause or change phrasing taken by a round 9 read, end to end; `test_round9_drafts.py`, `test_round9_mailbox.py`: round 9, slice A: emails to other people as a card with a tap-to-send link, the model-written draft and its checks, the operator's mailbox sending only after "send", Drafts over IMAP; `test_round9_cancel.py`: slice B: the rule-stop guard, the cancel helper, the notice as a draft card; `test_round9_postacts.py`, `test_round9_things.py`: slice C: numbered offers, apply, book and buy menus, "add them all"; `test_round9_registry.py`, `test_round9_mac.py`: slice D: the registry fields, the operator, app-named lists, Reminders and Calendar on the Mac, "what are you connected to", the export of connections; `test_round9_checks2.py`: the check of round 9, slice U2: with the judge an old round never leads a fresher post, the opening and closest lines count the kind the things were judged against, a number the judge's form leaves out is asked again; `test_round9_judge.py`: round 9, slice U2: the batched judge of "is it the kind" (off, on, failed, invalid, cached, the list as data), its verdicts deciding which posts count as the kind, a name written only as a handle, a thing two posts name shown once, the kind read from the request's grammar, the creator said once; `test_round9_checks.py`: the check of round 9, slice U: a title naming the request's year read first among the candidates again, the singular of each kind in "places or cafes", "what <kind> should i" only with the kind right after "what" and every asking verb left out of the goal; `test_round9_kinds.py`: round 9, slice U: the counts the kinds evaluation reads, the kind asked for in the details call and its cache key, clear picks that name nothing leading with the named things of other posts after them, the slides line only for a promised list, a post naming the kind read before lists and before the composer's other picks, a clear list with no thing of the kind not counted as the kind, "what <kind> should i" as an ask; `test_round8_live.py`: the live fix pass of round 8, findings 98 to 102: the composer's verdict leads an items answer, site names listed on lines of their own, an earlier year's post, a request for deadlines, the change in every opening line, the refilled window, a title naming the request's season year; `test_round8_checks.py`: the checker's near-variants of the live fix pass (an old round or an earlier year's post is never a clear source, deadline words alone make a request time-sensitive, an items answer with no date ahead says so, the refilled window and its counts, "this summer" said in summer, a video's names) and of round 8's answers and rules slices (lower-case names, one topic with two kind words, app questions, days counted from the send, one nudge at a time, the two live misreadings) and of its understanding and integrations slices (a label on a topic stored with another spelling, a topic starting with a digit, no "rising" with nothing kept before, no suggestion from personal or kind-word asks or while a preview waits, what is not the recap rule, a trends rule's timing in "my rules"); `test_round8_merge.py`: where the round 8 slices meet: the recap's counts of quiet days, past-due to-dos and dated reminders, labels in the suggestion and the export, the agent's trends answer, deletion of what the slices store, and each code-read phrase in and out of its own context; `test_mcp.py`: round 8 slice B, I1: each MCP tool's shape, friends never, personal topics left out and counted, the data line, the daily cap, nothing written but `action_log`, refusals, "what did my agent ask", the server over stdio in a subprocess; `test_round8_integrations.py`: I2 and I3: the export's files and phrasings, the email of them, deletion, the message to forward by pick, number and name, Spanish, what is not a share; `test_round8_understanding.py`: round 8, slice B: trends, the theme check, the recap and its suggestion; `test_round8_answers.py`: round 8 slice A2, findings 93 to 97: real named things, the posts that are read, several asks in one message, a passed-on series, a question read as small talk; `test_round8_rules.py`: round 8, slice B, rules beyond timing (a reminder counted back from a thing's date, quiet empty days, reminders until done, overdue nudges) and what code does with any form the model may return for the new phrasings; `test_round7.py`: round 7, findings 90 to 92: the items answer, dates, changed requests; `test_round7_checks.py`: the checker's near-variants of round 7 (an item's words, loose dates, reminders counted back from a thing's date, follow-ups that ask, add a creator or refine; the live donut case read as "more"); `test_fixpass6.py`: one or more per finding of the sixth live run, 88 and 89 (a message changing lasting state it never asked to change), their near-variants, the builder's audit and its checker's (one-time limits, settings carried with a request, the avoid list, styles, dropped topics, confirmations, all rules, resume, a stated kit or time); `test_fixpass5.py`: one or more per finding of the fifth live run, 84 to 87, their near-variants, and the checker's; `test_fixpass4.py`: one or more per finding of the fourth live run, 74 to 83, after a full setup, and the checker's near-variants; `test_fixpass3.py`: one or more per finding of the third live run, 65 to 73, and the checker's near-variants; `test_final_check.py`: where two review fixes met; `test_review_experience.py`: one or more per finding of the experience review; `test_review_cost_failure.py`: one or more per finding of the cost-failure review; `test_review_privacy.py`: one or more per finding of the privacy review; `test_review_reliability.py`: one or more per finding of the reliability review; `test_interpret_round.py`: the interpreter's improvement round, one or more per kind of misreading; `test_fixpass.py`: one or more per finding of the fix pass after the live run of 12 Nov; `test_fixpass_checks.py`: the checker's near-variants of those findings; `test_fixpass2.py`: one or more per finding of
the second live run, 38 to 64) |
