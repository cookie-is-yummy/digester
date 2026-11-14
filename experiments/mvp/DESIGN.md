# MVP design, version 2 (13 Nov 2026)

Why this exists: the founder tested the first build and asked for more. This file is the contract for that work.
It is prototype scope under `experiments/BRIEF-10.md` and amendment A-008. Everything personal stays under `data/`.

## 0. What the founder asked for (his words, shortened)

1. "Every 2 days" and "randomly" are missing. "Think of and implement all possible rules." Rules are "not always
   about timing": reminders, to-dos "and more".
2. Outputs beyond the message thread: email, calendar and "a bunch of output things".
3. "Sometimes it says that it can't find something but when I ask it again it finds it. That doesn't make sense."
4. The message must not say "Why". It should read like: "I've found some convenient chicken and rice recipes for
   you. I recommend this one [cite reel] because it only takes 15 minutes and requires just an instant pot. Here are
   the ingredients and the steps: … Alternatively, try these ones: … Or here's a wider selection: …". Images and
   embeds are welcome.
5. Picks "should lead to a final product". A "Beginner Modeling Tips" video sent for "mini Blender tutorials to start
   doing daily" does not.
6. Base answers on the person's own context: "how good are they at Blender?" Guess it from their library, then
   "have them validate it with a brief description of their direction during the setup". Get as much as possible
   during onboarding "so that everything after feels frictionless".
7. Recommendations from outside their history that are strongly related "could be really good too".
8. Onboarding should set up an export routine for Instagram and YouTube / My Activity, so they do not repeat the
   steps by hand.

Standing rules that do not change: the model fills forms and code acts; nothing is invented (every title, detail,
number and count shown must be backed by the item's own text or computed by code); friends' posts are never used;
captions are data, not instructions; no logged-in bot accounts and no scraping; keys only from the environment;
nothing personal in git; a repeating send needs a preview and a YES.

## 1. Rule model (schema.py, RuleSpec v 2)

A rule = when (trigger) × content (what) × do (where it goes), plus limits. Old v1 specs in a store must still load.

### when
```json
{"type": "now | once | schedule | random | on_request | new_items",
 "date": "YYYY-MM-DD", "time": "HH:MM", "in_minutes": 120,
 "days": ["MON"], "every_weeks": 1,
 "every_days": 2,
 "month_days": [1, 15, -1],
 "times": ["08:00", "20:00"],
 "window": ["18:00", "20:00"],
 "per": "day | week | month", "count": 3,
 "start": "YYYY-MM-DD", "until": "YYYY-MM-DD", "max_sends": 3}
```
- `once`: `in_minutes`, or `date` + `time`. Code works out the moment.
- `schedule`: exactly one cadence: weekly (`days`, `every_weeks` 1 to 8), interval (`every_days` 2 to 90, counted from
  `start` or the rule's creation date), or monthly (`month_days`, 1 to 31, -1 = last day; a day past the month's end
  means the last day). `times` holds 1 to 4 clock times (`time` stays as an alias for one). `window` in place of
  `times` means one send a day at a different minute inside the window.
- `random`: `count` sends per `per`, at random moments inside `window` (default 09:00 to 21:00), on `days` if given.
  "Randomly" with nothing else is 3 per week. The moments come from a seeded generator (seed = rule id + period), so
  they are stable across restarts and testable, and they are never shown to the person in advance.
- `on_request`: saved, run when asked. `new_items`: runs when the person's library gains items that fit (section 9).
- Limits on any repeating type: `start`, `until`, `max_sends`.
- `schedule.next_run(when, tz, after, anchor, seed)` stays the single place where times are computed, in UTC
  comparisons. `describe(when)` must read naturally for every form ("every 2 days at 8am", "on the 1st and 15th at
  9am", "about 3 times a week at random times", "twice a day, at 8am and 8pm, until 24 December").

### Person-level timing
- Quiet hours are per person (`people.quiet_start`, `quiet_end`; default 22 and 8), set by text ("don't message me
  before 10am").
- Snooze: "don't message me this weekend", "I'm away until the 20th" sets `people.snooze_until`; timed sends in that
  period are skipped and recorded (status `snoozed`). Asking still works.

### content
```json
{"source": "library | note | todos | recent",
 "text": "Call mum",
 "goal": "...", "searches": ["..."],
 "kinds": [], "platforms": [], "creators": [], "collections": [],
 "count": 1, "extract": ["ingredients", "steps"],
 "criteria": ["ends with a finished result", "suits a beginner"],
 "avoid": [], "since_days": null, "saved_after": null, "saved_before": null,
 "order": "best | newest | oldest | random | easiest_first",
 "outside": "none | some",
 "exclude_sent": true, "style": "full | brief"}
```
- `source`: `library` (search, as now); `note` (a plain reminder: `text` is sent as is, nothing is searched);
  `todos` (the person's open to-dos); `recent` (what they kept in the last `since_days`, newest first, no search).
- `extract` is a list (a v1 string still loads). `criteria`: up to 5 must-haves in plain words; the composer marks
  each yes / no / unknown per item, from the item's text only (section 3).
- `creators`, `collections`: filters matched in code against the item's creator and collection names.
- `order`: `random` is seeded per run; `easiest_first` tells the composer to choose by level, using the profile and
  how many this rule has already sent.
- `outside`: `some` adds a separate, labelled block of related things from outside the library (section 8).

### do (the action registry: actions/)
| Action | Params | What it does | Needs |
| --- | --- | --- | --- |
| `message.send` | none | The reply in the thread | nothing |
| `email.send` | none | The same answer as an email to the person's own verified address | a verified email |
| `calendar.add` | `time` (HH:MM), `duration_min`, `title`, `day_offset` | An "add to calendar" link in the message and an .ics file on the email | nothing (a link); email for the .ics |
| `todo.add` | none | Adds each main pick (title and link) to the person's to-do list | nothing |

Nothing outside the registry can run. A spec is validated against it before it is stored. An action whose need is not
met makes the bot ask for it once (for example the email address, confirmed with a 6-digit code sent to it).

### Intents (interpret prompt v3)
Existing: new_rule, ask, follow_up, more, change_rule, run_rule, skip, list_rules, pause, resume, stop, feedback,
set_timezone, delete_data, help, confirm, decline, unsupported, chat.
New: `todo_add` (text, optional pick_number, optional due), `todo_list`, `todo_done`, `todo_remove`;
`act_on_last` (do something with the last answer: "email me that", "put the first one on my calendar for 7",
"add 2 to my list"; fields: action, pick_number, params); `profile_show`, `profile_update` (free text about
themselves); `set_quiet_hours` (start, end); `snooze` (until date-time or in_minutes; or clear); `set_email`.
If one prompt cannot hold this accurately, split it into a router call and a form call. Accuracy on the rule
evaluation set (section 10) decides, not taste.

Repeating reminders made of the person's own words ("every morning remind me to stretch") start without a preview:
there is nothing to preview. The reply states the schedule and how to stop it. Repeating library rules keep the
preview and the YES.

## 2. To-dos and reminders
- Table `todos(id, handle, text, item_id, url, due_at, reminded_at, done_at, created_at)`.
- "add buy basil to my list", "add the second one to my list", "what's on my list", "done 2", "remove 3".
- A to-do with a due time reminds once at that time (the scheduler checks due to-dos like due rules, same guards).
- A rule with `source: todos` sends the open list ("every morning at 8 send me my list").

## 3. Answers: what the person reads (compose v2, extract v1, render v2)

No "Why:" label. The shape, for an ask with several good fits:

```
I've found some quick chicken and rice recipes in your saves.

I recommend One Pot Chicken Rice by @creator (you sent it to yourself in July), because it takes 15 minutes and
needs only one pot.
[link, as its own bubble so the app shows a preview]

Ingredients:
• …
Steps:
1. …

Alternatively, try these:
• Hainanese Chicken Rice by @creator: the ingredients are written out, with amounts. <link>
• …

Or here's a wider selection:
• Title: <link>
```
- One recommended pick with full details; up to `count - 1` alternatives with one line each; then up to 3 "wider"
  links when more good fits exist (asks only). A timed rule with count 1 sends the recommended pick only.
- `because` is a clause the model writes for this person and this request (their level, their time, their tools),
  but every fact in it must be backed: the model returns `facts: [{label, quote}]` with exact quotes from the item's
  text, and code checks each quote and every number in `because` against that text. A clause that fails becomes a
  plain one built by code ("it matches what you asked for, and you saved it yourself"). No links or handles in it.
- `criteria`: for each of the spec's criteria the model answers yes / no / unknown with a quote when yes. Code drops
  a pick with any "no". If no candidate is a clear yes on a must-have, the reply says so plainly and offers the
  closest ("None of the Blender videos you kept is clearly a start-to-finish project. The closest is …").
- "Leads to a finished result": when the person wants something to do, make, cook, build or practise, the
  interpreter adds the criterion "ends with a finished result" unless they ask for tips or theory.
- Details (ingredients, steps, key points) come from a separate extraction step on the full caption (not the
  600-character cut), verified line by line as now, and cached per item (section 4). Recipes get ingredients and
  steps when both are in the text.
- When details are not in the text: Instagram: "The recipe is in the video, not written in the post." YouTube (we
  hold only the title): say nothing about missing steps.
- Sources line in plain words inside the sentence ("you saved it in March"), not in brackets with a dot.
- Message parts: render returns a list of parts (`text` and `link`). Channels that show link previews send a `link`
  part as its own bubble; others join parts into one text. The test page draws a `link` part as a card: a YouTube
  thumbnail and the official player on click; for Instagram a card that loads Instagram's official embed on click.
  Our server never fetches Instagram or YouTube media.
- Emails are HTML with a plain-text part: the same content, linked titles, lists, and for YouTube picks the
  thumbnail image by URL.

## 4. Consistency (the same question must not flip between "nothing" and an answer)
- `facts` table: `(library, item_id, kind) -> lines, prompt_version, at`. Details found once are reused always. An
  empty result is cached only after two attempts.
- Extraction is its own call per picked item, with the whole caption. If code sees list-like lines in the caption and
  the model returns none, it retries once.
- A compose call that returns no picks while candidates exist is retried once before the bot says "nothing".
- The same request text from the same person, with the same rules, within 6 hours reuses the same interpretation; the
  same search text on the same library reuses the same ranked list; the same spec and candidates reuse the same
  composed answer. "Another" is the way to get something different.
- Use the most deterministic settings the model accepts (measure: run one request 5 times before and after).

## 5. The person's context (profile.py) and onboarding (onboarding.py)
- Profile, stored per person: `interests: [{topic, share, level, why, confirmed}]`, `direction` (their own words),
  `prefs` (things to avoid, tools they have, style), `email`, `email_verified`, quiet hours, snooze.
- The guess: code samples the person's own kept items (saved, sent to self, collections, playlists; recent and
  random) and their most watched channels; one model call groups them into topics with the sample lines that support
  each; code counts the support. Level per topic is a guess from titles, with its reason. Never infer health,
  relationships, money, religion, politics or sexuality (docs/07).
- Onboarding, in at most four bot messages, every step skippable, and a real request at any step is answered:
  1. Consent (as now).
  2. "Here's my read of you: … Did I get that right? In a sentence or two, what are you working toward right now?"
  3. Their answer is merged into the profile by a model call (levels corrected, direction and preferences stored).
     Then: email for emails and calendar files (code by email to confirm), and the time zone check.
  4. The refresh routine (section 9), then three first requests written for this person.
- The profile is given to the interpreter (to fill criteria, avoid and level) and to the composer (to choose and to
  word `because`). "What do you know about me", "I'm vegetarian", "I'm past beginner at Blender now" work any time.

## 6. Outputs
- Email: `actions/email.py`. SMTP from the environment (`MVP_SMTP_HOST`, `_PORT`, `_USER`, `_PASSWORD`, `_FROM`);
  without it, emails are written to `data/mvp/outbox/` and shown on the test page. Only to the person's own verified
  address.
- Calendar: a Google Calendar "add event" link plus an .ics file. No sign-in is needed. Direct creation with Google
  sign-in is later work.
- To-do list: section 2.
- Each further output (Apple Reminders, Notion, a notes app) is one more entry in the registry.

## 7. Test page
Shows link cards and embeds, a Profile panel, a To-dos panel, and an Outbox panel (emails and calendar files that
would be sent). The clock controls stay.

## 8. Related picks from outside the library
- Off unless the spec says `outside: some` (the interpreter sets it when the person asks for "new", "more like
  these", "what else is out there", or when they turned it on in their profile).
- Shown in its own block after the library picks, labelled "Not from your saves, but close to them:". Library picks
  always come first and are never mixed with outside ones.
- Source: only official routes. The method is chosen from the research note (`outside_recs.md`); every outside item
  must be verified by an official endpoint (for YouTube, oEmbed) and shown with the title and channel that endpoint
  returns, never the model's words. If no route is configured, the block is omitted and nothing is said.
- The search text sent out is built from the request, never from captions.

## 9. Keeping the library fresh
- An inbox folder per person (`data/inbox/<person>/`). A new export file there is imported with the demo's importer,
  the library is rebuilt beside the old one, and rules with `when.type = new_items` run on the items that are new.
- Onboarding gives the shortest lawful route to a repeating export (from the research note `export_routine.md`):
  direct links to the right export pages, the exact choices, and where the files must land. No passwords, no
  logged-in automation.

## 10. How it is judged
- Offline tests for every rule form, guard, action and message shape.
- A rule evaluation set: phrasings with the expected form, split into a development half (builders may use it) and a
  held-out half (run only by an evaluator who did not build). Target: 90% on the held-out half.
- The 20 draft requests, before and after. The same request 5 times: same answer.
- Live runs on the founder's library through the test page.

## 11. Additions after the gap review (13 Nov 2026)

Two authors of the rule evaluation set listed what sections 1 to 9 could not express. These are adopted. Where this
section and an earlier one differ, this section wins.

### More timing forms (when)
- `month_weeks: [1..5, -1]` with `days`: "the first Monday of the month", "the last Friday".
- `every_months` (1 to 12) with `month_days` or `month_weeks`: "every 6 months", "each year on 3 March" (12, with
  `start`).
- `every_hours` (1 to 12) inside `window`: "every 2 hours while I'm at my desk". The daily limit of timed sends
  still applies, and the preview says so.
- `except_dates: ["YYYY-MM-DD"]`: "weekdays but not on the 26th".
- `tz`: an IANA zone that pins one rule ("7pm New York time even when I travel").
- Defaults, set by code and shown in the preview: "twice a day" is 08:00 and 20:00; three times is 08:00, 13:00,
  19:00; four adds 16:00; "once a month" with no day is today's day of the month; "a couple of times a week" is 2
  and "a few" is 3 (`random`).
- `when.count` is sends per period; `content.count` is picks per send. The prompt carries an example of both.
- One canonical stored form per meaning (14 days as `every_weeks: 2` when `days` are given; `month_days: 31` as -1),
  so `describe`, duplicates and tests agree.
- "Every other Friday" starts on the first matching day after creation (or `start`); the reply states the first date.
- "Random" with no frequency word means random picks (`order: random`), not random times.
- Quiet hours: a time the person names is honoured. Random moments, windows, `every_hours` and retries never fall
  inside quiet hours; windows are clipped to waking hours. A random moment for the current period is drawn from the
  part of the period that is left.
- Quiet hours are stored as up to 4 blocks `{start: "HH:MM", end: "HH:MM", days: [...]}` ("not during class 9 to 3
  on weekdays").
- Only events the bot can see are triggers. "When I get home" and "when it rains" stay unsupported, with "pick a
  time" as the offer.

### Managing rules
- `pause` takes `until` (date or in_minutes); code resumes the rule. This also covers "no workouts this weekend".
- `skip` takes `count` and `date` ("skip the next two", "no pasta Thanksgiving week").
- `run_rule` takes `skip_next: true` ("send Friday's one now").
- `set_timezone` takes `until`; code switches back.
- `clarify`: when one needed fact is missing ("until the end of the semester"), the bot keeps the half-built form,
  asks one question, and the next message completes it.
- `also`: an interpretation may carry one more interpretation, run in order ("I'm in Chicago now, and move pasta to
  8"; "add milk to my list and find me a pancake recipe").
- `undo`: reverses the last write (a to-do added, a rule started or changed) within 10 minutes.
- `library_status`: last import, item counts, when the next export is expected, and the export links again.
- `library_stats`: counts worked out by code only (totals by platform and kind, by month, top creators, and how many
  kept items mention given words). Friends' items are excluded.

### Content
- `avoid_creators`, `avoid_collections`; YouTube playlist names are matched by `collections`.
- `count`: 1 to 10 for an ask, 1 to 5 for a rule; when cut, the reply says "here are the top N".
- `saved_before` is exclusive.
- `source: items` with `item_ids` (set by code from pick numbers, never by the model): used when an earlier answer
  is sent again or sent elsewhere later.
- `outside`: `none | some | only`. If the person asked for new things and no route can serve it (no key, quota used
  up, an Instagram-only request), the reply says so in one line.
- `more` may carry `avoid`, `criteria` and `outside` ("another but shorter", "more like these but new ones").
- "Ends with a finished result" is worded per topic and added only for making and building ("a finished model", "a
  dish you can eat"); for routines it is "a full routine from start to finish".
- A must-have that is unknown for every candidate (for example a video's length when it is not known) is said in one
  line, not silently ignored.
- `prefs.exclude_kinds`, `prefs.exclude_platforms` ("don't use my likes"): applied in retrieval for every request.
- `lang`: the reply is in the language the person writes in.
- `profile_note` on any intent ("I'm vegetarian now, any dinner ideas?"): merged into the profile.
  (Fix pass 6.) As the side effect of a request it teaches only a level the message states for a topic it names, a
  kit, a usual time, a diet it states and a plain note in its own words; never `outside`, exclusions, style, topics,
  the direction, quiet hours, the time zone or the email. For any message, an exclusion needs the message to negate
  that platform or kind in words, and `outside` as a standing preference needs standing words ("always", "from now
  on"). A note that restates the profile is not merged again and says no "Noted".
- (Fix pass 6.) A change lands only on what the message names: with a preview waiting, a change that edits it or
  names no stored rule changes the preview; with several rules, a rule number the model filled alone is used only
  when the message names that rule or it is the rule just started, changed or sent. A reminder is never turned into
  a library search; only its timing, pause, skip and stop change. "Any length" (and "no limit on length", "longer is
  fine") is never a must-have: it lifts the length bound. A time zone, quiet hours, a snooze or a profile update
  carried with a request needs words for it in the message.
- (Check of fix pass 6.) Words that make a limit one request's only ("no YouTube this time", "just this once") never
  change a standing preference, even read as a profile update: nothing is stored and the reply says so in one plain
  sentence. `outside` changes only when the message is also about new things or their saves. A request keeps a kit or
  a usual time it states ("for my new Instant Pot", "I usually have 30 minutes"), never one it only names ("guitar
  songs", "under 20 minutes"), and never takes a food off the avoid list because it asks for it (the request's own
  words already win for that request; "I eat chicken again" still does). A profile update carried with a request is
  that request's side effect unless it says it is standing. Any profile update drops a topic, sets a style, stops the
  level guessing, adds a thing to avoid or confirms a topic only in the message's words (a diet it states covers
  its avoid entries; the setup's read confirms what it showed). The words for a setting carried with a request are
  read narrowly ("I'm staying in tonight", "before 9", "until golden" say none). "Stop the pasta one" read as all
  rules stops the rule it names; a resume number the model filled alone needs the rule named, in view, or the only
  paused one. An export reminder is named by its short name, never by a word of its steps, and a count ("2 picks",
  "1 a day") never names a rule. "Change 1 to every 6 weeks" moves an export reminder even when the form copies its
  words loosely; its words stay its own. "Any length" with a new preview waiting is about that preview.
- Feedback gains `harder`, `easier` (also moves the profile level for that topic), `done` ("made it") and `hide`.
- A fitness request with an injury is an ordinary topic with avoid words; `because` makes no health claim.

### To-dos and acting on answers
- `todo_add` fields: `todo_text`, `pick_number`, `due`, `list` (a list name, default "todo"), `what: pick |
  ingredients` (one to-do per verified ingredient line). `todo_done`, `todo_remove`, `todo_due` take `todo_number`
  (a list) or `todo_text`.
- `act_on_last`: `actions: [...]` (several at once), `pick_number`, `answer_ref` ("last" or a rule number), and an
  optional `when` of type `once` ("email me these tonight at 8").
- `calendar.add` params: `date` (default: the day of the send), `time`, `duration_min`, `title`.
- Sending to someone else stays out; the reply offers to send it to the person so they can forward it.

### Answers (replaces the 0.6 fit cutoff)
- The composer gives each pick a verdict: `clear`, `close` or `no`, never a number. `clear` picks are shown as
  picks. If there is no `clear` pick but a `close` one, the reply shows it as "the closest I have is …". Only when
  all are `no` does the bot say it found nothing. This removes the flip between "nothing" and an answer that the
  measurement traced to a score hovering around the cutoff.
- The interpreter and the composer run with temperature 0 and a fixed seed.
- Changed after the live runs of 12 and 13 Nov: a pick whose only "no" is the finished-result must-have may still be
  shown as the closest, said as such, when nothing else comes closer. A request to make something then gets a few
  YouTube picks as well when under 3 saves fit (the outside section below).
- What the person has and how much time they usually have are preferences, never must-haves: they help choose among
  picks that fit and may be named in the reason when the post's own text backs it. Only the avoid list is a hard
  limit, and the message's own words win over it.
- (Check of fix pass 4.) The same holds for their notes, their direction and their level from the profile: a level
  must-have comes only from the message's words; the profile's level for the request's own topic goes to the
  composer, which prefers picks that suit it (section 5's "fill ... level" is read this way).
- (Fix pass 5.) Copies of one post (the same creator and the same line its name comes from, at least 3 words, never a
  hook line like "Save this recipe!") take one place among the candidates (the copy that writes out more is kept). An
  ask or a preview that shows fewer picks than asked for (an alternative that is the lead's own dish does not count)
  gets one more composer call on the candidates it did not return that look like the kind asked for; its picks come
  after the first call's and never change the lead (unless the first call had none); a first answer that is only the
  closest is left as it is. With fewer clear picks than asked for, close ones fill the places under their own heading
  ("Or these, which are close too:"), never as the lead; a second-look pick with any "no" is never shown. An
  alternative is the lead's own dish when their title words match once words that only say how it is made or praise it
  are left out ("easy", "rice cooker", "bowl"); "Hainanese chicken rice" is not "Chicken rice". A reason with one
  failing part loses that part when the rest is still a whole clause; a lead whose reason a check removed gets one built
  by code from the details shown under it ("the ingredients are written out").
- (Fix pass 5.) "that I haven't seen", "not from my saves", "that aren't in my library", "I don't already have" make
  `outside` "only", whatever the model filled ("and some new ones too" stays "some"). A repeating rule whose preview is
  the closest only because of its length bound says so when it starts and offers "any length" (added to the rule's
  own words, which lift the bound) and "include YouTube" (`outside` "some"); no field was added.
- YouTube items: titles only is too little for "under 10 minutes" or "ends with a finished model". For candidates
  shown to the composer, code fetches the video's length and description from YouTube's official `videos.list`
  (one call per 50 videos, key from `YOUTUBE_API_KEY`), keeps them at most 30 days (YouTube's rule), and treats the
  description as the item's own text. Without a key the bot works as before.

### Outside picks (replaces the method in section 8)
- YouTube only: one official `search.list` call, checked by one `videos.list` call (public, embeddable, not made
  for kids). The first 3 not already in the library, in YouTube's order, shown with YouTube's own title and channel
  and nothing written by a model. The search words are only words from the person's own message, checked in code;
  never for sensitive topics. Results are kept at most 30 days. All people share 100 searches a day.
- Before anyone outside the founders gets outside picks: a terms page that links YouTube's Terms of Service and a
  privacy note that names YouTube API Services (YouTube's developer policies require both).

### Link previews in Messages
- A link is sent as its own bubble. A contact card for the bot is sent after the person's first reply, because
  Messages does not expand links from senders who are not in the person's contacts.

### Keeping the library fresh (replaces the routine in section 9)
What the research found: Google's Data Portability API is not offered to US users; Takeout can repeat every 2 months
for a year, into the person's Drive; Meta's repeating export to outside storage is documented for the EU and is
unverified for a US account. So a fully automatic routine cannot be promised today. The prototype does this:
- Onboarding step: which accounts, then the shortest steps with direct links, and a rule made for them that reminds
  them when the next export is due (every 4 weeks for Instagram; the Takeout schedule for YouTube).
- An inbox folder per person and an upload box on the test page. A new export there is imported without anyone
  typing a command, and `new_items` rules run.
- A pick-up from a shared Drive folder is later work: it needs its own Google project and a restricted permission.
- Messages are never part of an export we ask for.

## 12. Answers that answer; dates; changed requests (round 7, 14 Nov 2026)

The founder's four cases of 13 Nov (findings 90 to 92). The vision's second and third wants: the gist without
rewatching, and the thing inside a post to act on. Where this section and an earlier one differ, this section wins.

### The items answer (finding 90)
- A details kind `items` (prompt `extract_v2`): the named things a post's own text lists that answer the request, each
  `{name, about, when, fit}`. Code keeps an item only when its name is a whole run of words in the post's text (a site
  named by its address keeps its name alone); `about` and `when` only when they are the text's own words (about: at
  most about 25 words, the key-point checks) and, for `about`, only when they are about that thing: they name no
  other listed thing, and they hold its name or start after it (within 60 words) with no other listed thing between
  (`extract.about_belongs`); `fit` "no" is left out, "yes" before "unknown". At most 12 per post.
  The details call gets the request, the lines about the person, today's date and the post's date. Items are cached
  per post and per request (the facts table's kind `items:<hash>`); a found list is not asked for again for its key
  points.
- Default details: a recipe, a workout or a make-or-build tutorial keep theirs (section 3). Every other ask, preview
  or send gets `items` then `key_points` on its top 3 picks (parallel calls). Code decides from what comes back:
  2 or more items over the shown picks make the items answer; else key points under the lead (an alternative's line is
  its first key point); else the present answer, plus "The details are in the post's slides or video, not in its
  text." only when the request asks for things (libraries, tools, opportunities, programmes, places ...).
- The items answer: the opening line, then per post (at most 3) `From "Title" by @creator (posted May 2024, saved July
  2023):`, its things numbered through the answer (at most 6 per post, then "and N more in the post"), and its link
  alone. Picks with no things follow under "Also in your saves:". No "I recommend ... because".
- Kept with the answer (`answers.picks[].items`, with the line as shown). "add the second one to my list", "remind me
  about <name> tomorrow", "put the NASA one in my calendar" act on that thing (its name, its words, its date and the
  post's link; a calendar entry takes the date code reads in the thing's own words when it is ahead, for any request);
  a number past them says how many there are. The numbers run across the posts as shown. A later reminder is `source:
  items` with `item_names` (set by code, never by the model). "remind me about <name> two days before its deadline"
  ("a week before", "the day before", "on its deadline") is counted back by code from that date, at the time named or
  9am; with no date in its words, a passed one or one too near, one plain line and nothing is set. "email it to me"
  sends the whole answer.
- For a year in the request, a thing whose own words name only earlier years ("Design award 2024" for "for 2026") is
  left out while 2 or more others fit (read by code, not from the model's `fit`).

### Dates (finding 91)
- Posted dates: Instagram from the link's shortcode (`dates.instagram_posted`, any post, reel or tv link, with or
  without a query string; other Instagram links give none; checked on the founder's library: 20,958 of 20,963 items
  with a kept date decode to a date on or before it, and 20,496 of 20,500 leaving friends' items out); YouTube from
  `snippet.publishedAt`
  (`youtube_cache.published_at`). The composer (`compose_v5`) and the details call get today's date and each
  candidate's kept and posted dates.
- Time-sensitive requests are recognised in code (opportunities, deadlines, applications, programmes, events, sales,
  "soon", "this month", "next summer", a year ...). For them, a date written in a post's text (or an item's) is read by
  code, with the posting year when it gives none: a passed date makes it `passed` (never the lead or an alternative
  while something not passed fits, a clear fit past the count taking its place; shown alone it says "its deadline, 14
  February 2025, has passed"); more than 12 months old and speaking of now ("now open", "apply now") with no date is
  `old` (after everything fresher: "from May 2024, so this round has probably closed; check whether it runs again");
  among equal verdicts, newer first; a year in the request first prefers posts that name it or were posted in the year
  before it or in it. A date ahead is said with how far it is: "deadline 1 December (in 19 days)" ("deadline 1
  December, in 19 days" inside a thing's own brackets). An old post that says it stays open ("until further notice",
  "rolling applications", "year-round") is `old` with "from May 2024; check whether it is still open". A lower-case
  "may" with a day and no year is a date only after a deadline word ("3 may surprise you" is not 3 May). Rules' sends
  run the same code.
- No stale claims, for any request: a reason from a post older than 60 days loses a part that says "now open",
  "currently", "this week", "soon", "new" (the reason trimming of fix pass 5; else it goes), and a key point or an
  item's words that say it get "(as of May 2024)" after them. Date phrases are English only: a Spanish answer keeps the
  order and the drops but not the date words.

### Changed requests (finding 92)
- After an answer, a follow-up whose form carries `avoid`, or whose words change the request ("what about", "something
  that isn't", "not from that creator", "shorter", "easier", "more recent", "on Instagram", "anything else",
  "different") is a new search: the last request's content plus the change (avoid words from the form and from the
  words after "isn't", "without", "no"; the shown pick's creator left out; a length bound; an order; a platform). The
  shown picks the change rejects are left out ("anything else": all shown). The opening line is built by code from the
  merged request ("Here's what else I found in your saves for basic Blender tutorials, leaving out anything about
  donut."). With nothing left: "I found nothing else in your saves for ..., leaving out ..." and, when YouTube can
  serve it, the "new ones" offer. A question about the picks shown stays a question: one that points at a pick ("the
  second one", "#2", "is it", "how long", "which one") is a question even with "what about" or "without" in it, unless
  it also has plain change words ("anything else", "instead", "not from", "something that isn't"). Also read by code:
  "what about ones from <creator>" (that creator's, by the name the library holds; none: "I found nothing from that
  creator in your saves."), "ok and for dinner?" (the same request and searches with those words added; the line says
  "what I found", not "what else"), "not on YouTube" (the other platform, never an avoid word), and "the opposite" (no
  search: one line asking what to change). A "more" form that carries a new avoid word gets the same code-built line.
- A message's own words win over an avoid entry only when they ask for the thing: "isn't", "isnt", "aren't", "other
  than", "except", "rather than", "instead of" before it rule it out (`profile._NEGATING`; live, 14 Nov, the donut
  follow-up read as "more" lost its avoid word to this).
- The avoid test reads the item's whole own text, a video's description included, and such a candidate never reaches
  the composer.
- The opening line code builds never echoes a goal of more than 6 words ("Here's what I found in your saves.").

### Not done in this round
- Several asks in one message ("startup motivation reels, opportunities to pursue soon, or things with deadlines")
  still get one answer for the whole message, not one labelled part per ask.
- "add them all" after an items answer adds the source posts; a question about a numbered thing ("how long is the
  second one?") is about the posts shown. A title from an old post that says "now open" is kept as the post's words
  (for a time-sensitive request the date line after it says it is old).
- "what about pasta?" (a new topic in a follow-up form) is not turned into a new request by code.

## 14. Understanding: trends, theme check, recap (round 8, slice B, 14 Nov 2026)

The vision's Understanding promise and core loop steps 3 and 6 (docs/00). Code only: no model call, no interpreter
prompt change, every number counted by code. It adds to sections 5 and 11; where they differ, this section wins.
Stored specs and stores from before load as they were (new sources are optional values; `answers.spec` is an added
column).

### What you have been into lately (BN3, `attention.py`)
- Asked by code, whole message: "what have I been into (lately)", "what am I into lately", "what's rising", "what's
  fading" (`followup.TRENDS_ASK`).
- Kept = a save, collection, share to self or playlist, dated by the latest of those. Likes are counted apart and
  always said as "liked". Watches never count. Friends' posts are never in the view.
- A topic's posts: its guess's support lines plus kept posts whose text has one of its checked words
  (`retrieve.contains_word`). Sensitive topics (`profile.sensitive`) and "not me" topics are never shown.
- Windows end at the newest date of any kind per platform in the library, never today: lately = the 56 days up to it,
  before = the 182 days before that. Compared by share of all kept posts in each window: rising (at least 5 lately and
  at least 2 times the earlier share), fading (at least 10 before and at most 0.4 times), steady (at least 3 lately),
  else "too few to tell" with its likes count.
- The message (`texts.trends_message`, at most 7 lines): the totals with the anchor dates and their years, one line per
  topic ("• Blender 3D is rising: 6 posts that mention it lately, 1 before."), "Parked for someday: ..." and "Just for
  fun: ..." (counts only, no trend word), and the direction against `profile.match_topic` (never an "enjoy" topic):
  its counts, or "Nothing you kept lately mentions it, so I can't tell how that's going from your saves."
- On request it ends with "Reply "every export" ..." while no trends rule exists. "every export" as the next message
  makes a `new_items` rule with content source `trends` (no preview: the answer just shown is what it sends; "undo"
  and "stop N" end it). `refresh.run_new_items` runs it on the library the import switched to, past the cost cap (it
  costs nothing); an import with nothing new sends nothing for it.
- Live check: `python3 -m mvp.attention <library> [--store PATH] [--person N]` prints anchors, totals, and per topic
  number its label and counts and the seconds; no names, captions or handles; the store is opened read-only.

### The theme check (BN4, `profile.py`)
- Profile interests gain `relation` (pursue | practise | someday | enjoy | not_me) and `relation_at`. "delete my data"
  removes them with the profile.
- Asked once (`themecheck_asked:<handle>`), appended to the first trends answer that shows unlabelled topics (at most
  5), never while the setup is open. The list is held in `themecheck:<handle>` for the next message only.
- `profile.parse_labels`: numbers or the topics' names, each with a label in common words ("practise", "for fun",
  "someday", "later", "not me", "nope", "pursue", "goal"), and nothing else but commas and "and"; else None and the
  message goes the normal way (the question ends). A number past the list: "Which one? I listed 4. ..." and the
  question stays open.
- Any time, read by code: "<topic> is <label> now" (a stored topic, a "not me" one too), "what did I park?" (someday
  topics with their saved counts).
- "not me" (also a topic dropped by a profile update) stays as a marker: `profile.get` leaves it out, so the
  interpreter's and composer's lines, "what do you know about me", the setup's read and its first requests never
  hold it, and `adopt_guess` never adds it back. Their own words ("I'm into sourdough again") bring it back. Search
  is never gated: naming the topic still finds those posts.
- "what do you know about me" shows the other labels ("parked for someday", "just for fun").

### The recap (BN5, `digest.py`)
- Never offered at setup and never sent unless asked: on request ("recap", "my week", "how did my rules do",
  `followup.RECAP_ASK`), or as a rule the person makes ("every sunday at 6pm send me a recap": the interpreter's
  timing, then `followup.recap_rule` sets content source `recap`; the preview shows this week's recap and YES starts
  it; on a week with nothing it says "There's nothing to report this week yet. On a week like that I send nothing.").
- The last 7 days, at most 6 lines: "Your recap since Sunday 15 November:", then up to 5 of, by importance: the rules
  (per rule: sent, "stayed quiet twice with nothing new" from run status `empty_quiet` when it exists, skipped, held
  by a snooze, past the daily limit, and 👍, made it, too easy, too hard on its picks); to-dos (ticked off in the
  period, open, past their due date, `todos.overdue_at` when the column exists); coming up in the next 7 days (a
  one-time reminder about a thing, content source `items`, with its date from `deadline:<rule id>` when kept; to-dos
  due); one suggestion; "I gave you N calendar links" (never "you added"); the library (newest kept date and
  `refresh.export_due`'s phrases). The library line alone is not news: with nothing else the recap is empty.
- An empty recap on request: "Nothing to report for the last 7 days: no rule sent anything and no to-do changed." A
  timed one records run status `none` and sends nothing. A recap rule is not the person's own words: it counts as
  unanswered and brings "Still useful?"; quiet hours, snooze, pause and the kill switch apply as to any rule.
- The suggestion: 3 asks or more (runs of kind `ask` with `answers.spec`, kept by `outputs._keep_answer`) whose goals
  share a topic word, on 2 days or more within 21 days, with no active or paused rule on that word, no "not me" or
  "someday" label on it and nothing sensitive; offered once per word per 30 days (`suggested:<handle>`). "yes" as the
  next message builds that ask's spec as a rule every Saturday at 10am (one pick, no outside picks), through the
  standard preview; nothing starts without YES. Rows kept before this round have no spec and are never offered.

### Out
- Vector membership for topics, a model call to name new topics, minutes or time spent, the post-import report line,
  `StatsQuery.by = "trend"` through the interpreter; labels used in `executor._supply` or outside picks; free-text
  labels; a recap offered at setup, an unrequested weekly pick, counts of what was never opened.
