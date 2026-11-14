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
  and "email this to my mom" gets the offer to email it to them so they can forward it.
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
- **A plain question about the saves** ("what other opportunities might I have missed ...") that the interpreter reads
  as small talk is searched (`interpret.chat_guard`).

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
  (once that is merged). **Never**: friends' posts, anyone else's data, posts and lines on personal topics (health,
  money, religion, politics, relationships, sexuality) unless started with `--include-sensitive`. Every result starts
  with a line telling the agent that post text is data, not instructions.
- **What it can do**: read. It cannot send, schedule, run a rule, add a to-do or change anything; the store is opened
  read-only. Each call adds one row to `action_log` (the tool and counts, never the query), and "what did my agent ask"
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
| `todos.py` | To-do lists, due reminders, undo records, library counts |
| `actions/` | The action registry (`__init__.py`: names, params, needs, module, order) and one module per action: `message.py`, `email.py` (SMTP or the outbox), `calendar.py` (Google link and `.ics`), `todo.py` (picks or ingredient lines on a list); `base.py` holds what each action gets and returns |
| `outputs.py` | Runs a spec's `do` after composing (once per answer, logged, one line each in the reply); acting on the last answer now or later; the email address and its 6-digit code |
| `contact_card.py` | Writes the bot's `.vcf` contact card, for the founders to host |
| `retrieve.py`, `engines.py`, `libview.py` | Candidates from the person's own library (Q8 search, cached ranked lists, filters, orders, recent and fixed items) |
| `ytinfo.py` | A YouTube candidate's length and description from the official `videos.list` (`YOUTUBE_API_KEY`), kept at most 30 days (the scheduler purges once a day: the cache, details read from descriptions, cached composed answers, and kept answers and emails with a YouTube pick) |
| `outside.py` | New picks from outside the library: YouTube `search.list` with the person's own words, checked by `videos.list`; the sensitive-topic stop, the daily limits (with the shared count file) and the 24-hour cache |
| `refresh.py` | The inbox per person, the import (demo importer, without the messages folder), the cost cap, the library switch, recovery of an import cut off by a stop, new_items rules, library_status, and the export routine with its reminders |
| `mcp_server.py` | Round 8, slice B: the read-only MCP server for the person's own agent (stdio, one person, seven tools, the store opened read-only, the data line, personal topics left out and counted, one `action_log` row per call); "what did my agent ask" |
| `export.py`, `share.py` | Round 8, slice B: "export my data" / "export my lists" (the files, the email of them, removal on deletion); the message to forward for "share it" / "send this to <someone>" |
| `followup.py` | Round 8, slice B: export, "email it to me" after one, share and "what did my agent ask", read by code before the model (`IntegrationReadsMixin`). A follow-up that changes the request becomes a new search (round 7); what code reads without the model: plain commands ("stop 2", "pause 1", "resume all", "skip 3", "run 1", "done 2", "remove 3", "my rules", "undo", "help"), "another" / "more" / "next" (the last request, unchanged), "only new stuff, not from my saves" (outside only, same topic); a question about a shown pick's details ("what are the steps for the first one?") answered directly from its own text, or one honest line and its link |
| `compose.py`, `prompts/compose_v5.md` | The model chooses (verdicts clear / close / no, a backed "because" given as a bare clause, must-haves, the person's level); code checks it (a finished-result must-have is "no" for tips-only text, though such a pick can still be the closest when nothing else is; a reason may name a level only when one may be used; an unbacked reason is left out; "mini" / "short" / "quick" is a length bound checked against YouTube's length); the composer's opening line only when its words are the request's (else one built by code); a cached answer per spec and candidates, kept no longer than it can be reused |
| `lang.py` | The answer's fixed phrases in Spanish (with the outside block and the level note that ride on it); any other language gets an all-English answer, and the composer is told to write English. A rule's preview, start line and timed sends are English only for now (their timing words have no Spanish yet), so a rule made in Spanish is set up and sent in English, never in two languages at once |
| `extract.py`, `prompts/extract_v3.md` | The named things a pick's text lists (items: name, its words, its date; round 7; what an item is, enforced in code, and which posts list things: round 8), ingredients, steps and key points from a pick's whole text, checked line by line, cached in the `facts` table (a line is never shown cut off: a step or key point is kept whole up to 260 characters, a sentence that only describes the video is not a step, and steps are shown only when two or more remain); a recipe, workout or make-or-build tutorial gets its details for the recommended pick even when none were asked for (a talk, a list of habits or an opinion gets none, unless its text writes out a recipe or a workout); when details are asked for, the best of the top 3 that has them all is recommended |
| `dates.py`, `answers.py` | Round 7: posted dates (the Instagram link's shortcode, YouTube's publishedAt), time-sensitive requests, dates read from a post's text (passed, old, ahead), no stale claims; the date order of picks and the choice of the items answer |
| `render.py` | What the person reads, as parts (text and link), the items answer among them: a channel that shows link previews sends each link alone; the same answer as an email (plain text and simple HTML) |
| `schedule.py` | Every date and time (every timing form, seeded random moments, quiet hours), in the person's zone |
| `scheduler.py` | Timed sends and their guards: skips, snooze, quiet hours, daily limit, retries and holds |
| `store.py`, `llm.py` | Records (including each answer as shown, the action log, the outbox, outside searches and imports); model calls, the cost ledger (an import's build is written there too) and the caps |
| `channels/` | Test page (`web.py`, `web_page.html`: thread, Profile, rules, To-dos, Outbox and Exports panels with the upload box, "Start over" through the setup), terminal, Mac Messages, Sendblue |
| `trace.py`, `run_requests.py` | What happened to a message; a batch of test requests |
| `tests/` | 858 offline tests (`test_mcp.py`: round 8 slice B, I1: each MCP tool's shape, friends never, personal topics left out and counted, the data line, the daily cap, nothing written but `action_log`, refusals, "what did my agent ask", the server over stdio in a subprocess; `test_round8_integrations.py`: I2 and I3: the export's files and phrasings, the email of them, deletion, the message to forward by pick, number and name, Spanish, what is not a share; `test_round8_answers.py`: round 8 slice A2, findings 93 to 97: real named things, the posts that are read, several asks in one message, a passed-on series, a question read as small talk; `test_round7.py`: round 7, findings 90 to 92: the items answer, dates, changed requests; `test_round7_checks.py`: the checker's near-variants of round 7 (an item's words, loose dates, reminders counted back from a thing's date, follow-ups that ask, add a creator or refine; the live donut case read as "more"); `test_fixpass6.py`: one or more per finding of the sixth live run, 88 and 89 (a message changing lasting state it never asked to change), their near-variants, the builder's audit and its checker's (one-time limits, settings carried with a request, the avoid list, styles, dropped topics, confirmations, all rules, resume, a stated kit or time); `test_fixpass5.py`: one or more per finding of the fifth live run, 84 to 87, their near-variants, and the checker's; `test_fixpass4.py`: one or more per finding of the fourth live run, 74 to 83, after a full setup, and the checker's near-variants; `test_fixpass3.py`: one or more per finding of the third live run, 65 to 73, and the checker's near-variants; `test_final_check.py`: where two review fixes met; `test_review_experience.py`: one or more per finding of the experience review; `test_review_cost_failure.py`: one or more per finding of the cost-failure review; `test_review_privacy.py`: one or more per finding of the privacy review; `test_review_reliability.py`: one or more per finding of the reliability review; `test_interpret_round.py`: the interpreter's improvement round, one or more per kind of misreading; `test_fixpass.py`: one or more per finding of the fix pass after the live run of 12 Nov; `test_fixpass_checks.py`: the checker's near-variants of those findings; `test_fixpass2.py`: one or more per finding of
the second live run, 38 to 64) |
