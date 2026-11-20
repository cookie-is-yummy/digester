# Round 10, MVP version 5: the bot does it for you, with your permission (counts only)

19 Nov 2026. Branch `experiments/search-loop`, code at a3aafab. The founder's library: 136,445 items, of which
20,830 are Instagram items that are not friends' posts. The design is `experiments/mvp/DESIGN.md` section 17. The plan
was a critic's verdict and the main agent's addendum of 17 Nov, kept outside git. Conversations from live runs are
outside git too. The only new prompt is the errand form (`errand_v1`, then `errand_v2`). No other prompt changed.

## What was asked (17 Nov), and how it was built

The founder asked for four things on version 4. Do it for him once he says yes. Cancel for him after he confirms. No
reels whose caption has nothing to do with the video. Rules that call the connectors.

It was built as nine slices, then two merges, two adversarial checks, one live self-test and one live check with its
fix pass. Amendments A-015 (connectors, rules that write, YouTube) and A-016 (the browser) record the scope. Both are
Proposed. Everything in them runs on this prototype branch only, and the browser is off unless a setting turns it on.

## What version 5 does that version 4 did not, by slice

| Slice | What is new | Measured |
| --- | --- | --- |
| K, foundation | The build is shown in the page footer, in the help and for "version". On the test page, its own person is the operator unless `MVP_OPERATOR` says otherwise. Secrets are read in one place and sealed at rest, one file per person and app | 62 tests. $0 |
| W, wording | "email it to me" with a draft open sends the person a copy. A setup answer with a request inside reads as both. Everyday wording is tidied before the code reads. When code misses, one small model call fills a form, and code checks every field | Development set by code: 27 of 100 before, 73 after. 1 wrong helper (a known one), 0 of 40 "none" lines taken. With the form: 25 of the 26 misses reach the right helper. Spanish: 12 of 13. $0.96 |
| S, mismatched reels | A reel whose caption was pasted from elsewhere is marked. It never leads while another fit exists. When it is the only fit, the answer says so and uses a neutral title. "That reel had nothing to do with it" teaches the bot | On the real library: 194 strong and 160 weak marks, built in about 5 s. On the marked set: 9 strong leads in 11 answers before, 0 after while another fit was shown. The doubt line on 9 of 9 only-fit answers. $1.01, over its $0.85 budget |
| D, sending and notices | The way a draft will go is read again at "send". A notice sent to a gym or merchant gets a check-up date, then a second notice if needed. A Connections panel on the test page takes keys, never the chat | 65 tests. The route file now has 16 merchants, with facts read on 17 Nov. $0 |
| G, rules into the person's apps | One yes on a preview that names the app, the list and the caps. Each run says what it added, and "undo" takes it out. Three failures in a row pause it | 77 tests. Six actions may run under a rule's yes: Mac reminders and events, TickTick, Todoist by token and by sign-in, a private YouTube playlist. Of 10 rule phrasings read live: 3 grants, 5 honest lines, 2 with no app to place in. $0.03 |
| C, the MCP client | Todoist by its official MCP server, for the operator, signed in with "Allow". Its tools are pinned at the yes; a changed or new tool is never called. No due times are sent | 79 tests. A live discovery check against Todoist's server, with no token, passed all six of its checks. $0 |
| Y, YouTube and Instagram links | YouTube by Google's own API, connected with a code at google.com/device. Unsubscribe, private playlists, undo, and a daily unit limit. Testers can use it. Instagram gets one-tap links | 80 tests, all against a fake Google. Made-up YouTube and Instagram wordings read by code: 13 of 25 before, 21 of 25 after. $0.03 |
| V, the browser that cancels | Off by default. It opens the merchant's own cancel page, stops before the last button, and presses only after "yes cancel <merchant>". A window on the operator's machine, or a browser inside the bot's machine with a take-over view at `/vm`. A practice merchant, Streamly | 71 tests. On the practice site: 6 of 6 flows that should finish did, 0 wrong presses. 600 random walks: 0 wrong presses. 0 last presses without the yes. One run uses about 410 MB. $0 |
| T, the self-test | 40 made-up conversations, 114 steps, on a made-up library of 118 items, with fake outside apps. A dry mode makes no model call | 51 tests, then 49 more after its first live run. Dry: 114 of 114 steps |

After the live check of 19 Nov, eleven findings were fixed (DESIGN 17.L). "I'm in" never moves the time zone. The
receipts quote the page after the browser pressed. A connector menu is built from the registry. Instagram actions
asked of the bot get the plain line with the pick's own link. Two things to cancel are both said.

## Checks

| Check | What ran | Result |
| --- | --- | --- |
| Offline tests | `experiments/mvp/tests`, in 4 shards | 3,316 pass, 0 fail (2,086 at version 4). The demo's 10 pass |
| First merge (K, W, S, D, G, C) | Six merges, then a review of 14 seams | 5 seam defects fixed at the merge. The review: 11 seams held, 3 broke and were fixed |
| Second merge (Y, V, T) | Three merges, the dry self-test, eight seams | 8 defects fixed, 2 small gaps closed. Dry self-test 114 of 114 |
| Check of acting and secrets | 30 numbered attacks, plus the take-over view, denied sites, the last button, testers, the panel and grants | 7 defects found and fixed, among them a redirect leaving the merchant's site and secrets typed in everyday words. 52 tests |
| Check of reading and answers | 16 attacks | 13 held as attacked. 3 broke on near-variants. 15 kinds of defect fixed. 102 tests |
| Held-out wording set, run once | 70 helper lines, 30 "none" lines | By code 22 of 70 right (31%), against a bar of 70%. With the model, 54 of 70 (77%), against a bar of 85%. Both bars were missed. 0 of 30 "none" lines taken |
| Development wording set, same code | 100 helper lines, 40 "none" lines | 73 of 100 by code, 95 of 100 with the model |
| 60 new made-up messages | 10 of them in Spanish, as a tester | By code 32 right before the fixes, 49 after, 0 wrong. 59 of 60 right in the end. Spanish 9 of 10 |
| Slop marks on the real library | A random sample of 20 strong marks | 17 right, 3 wrong. Unmarked how-to items: 17 of 20 right |
| The 20 draft requests, live | In the check of reading | 20 handled, 0 errors, 19 with picks, "I recommend" 14, 0 strong leads |
| First live self-test | 40 conversations, 114 steps, real models, fake outside apps | 103 of 114. Of the 11 failures, 4 came from the harness clock and 2 were bot defects. 1 check was too exact, and 4 steps were unclear. One more bot defect was found on the way. After the fixes, 31 of 31 on rerun, so 114 of 114. $0.39 |
| Live check of 19 Nov | The founder's flow on the test page, with the practice merchant | 11 findings |
| Live fix pass | F1 to F11 | 121 tests, 83 of them fail without the fixes. $0 |
| Check of the live fixes | 80 new messages in four settings, 50 traps, 32 Instagram attacks, one live run | 7 more breaks fixed. The traps and attacks give replies byte-equal to the code before the live fix pass. 107 tests, 46 fail without the fixes. $0.03 |

The 80 new messages, by code, as a tester with the browser off: 13 right before the live fix pass, 67 after. The same for the
operator: 66 after. None of the remaining "wrong" counts is a real defect, by the checker's reading.

After each merge and each check, these held. The recipe, workout and tutorial answers on the fakes are byte for byte the same. The 159
rule texts and 123 rule phrasings are taken by no new read. Stores made by older code load and keep their rows. With
the browser off, the ten cancel conversations give the same bytes as before.

## What was not built, and why

| Not built | Why |
| --- | --- |
| Acting on Instagram in a browser as the person | Instagram's terms forbid automated access, even when logged in. AGENTS rule 7 forbids logged-in bots. One-tap links instead |
| A real merchant in the browser | It is off by default, and no real merchant was tried. The cloud container has no direct route out. The founder tries it on their own Mac |
| Sending from a tester's own Gmail | It needs Google to approve the app first. Testers get the tap-to-send link |
| Gmail and Calendar through Google's own MCP servers | Google's preview terms forbid giving testers access, and joining the preview is needed |
| Also left out | TickTick's MCP server, Notion, a daily YouTube sync, YouTube likes, a model choosing browser steps, Amazon in the browser, sign-ins kept between browser runs |

## What is still wrong or unproven

Never run for real: sending from the mailbox, the Mac, TickTick, Todoist by token or sign-in, the webhook, YouTube on a
real account, and any real merchant in the browser. Each ran only against a fake.

Reading:
- New wordings are read by code far less well than the development set (22 of 70 against 73 of 100).
- Still sent to the model: Spanish for "connect my gmail", "cancel my netflix and spotify" and "what did you do for me".
- Also still sent to the model: "wat did you do" and "help me".
- A Spanish request to unsubscribe from a YouTube channel is refused, not done.
- In the held-out set, apply, book and buy through the errand form sometimes came back "not taken".
- One live form read "every week" as every day. The preview shows it before any yes.
- "a workout i can do daily" now gets a daily rule's preview. Some people may have wanted one answer.
- "like that reel" or "heart it" alone, a bare "delete that post", and liking a YouTube pick are not read.
- A bare "I'm in" during the setup gets "Nothing is waiting for you to sign in". This is not tested.
- Two asks where the second is a plain add to the bot's list stay one email card.
- "add a new recipe to my reminders" goes to the bot's own list without saying it cannot reach Apple Reminders.

Slop marks:
- The strong mark is right on 17 of 20 sampled items. Its precision on the video needs the founder's labels.
- Genuine pages can be marked: a page name with meme words plus bold headers, or a creator who often opens with a joke.
- A reel the person called fine keeps its neutral title.

Doing:
- "what did you do for me" can say "4 still open" after a run was stopped, handed back, or only given steps.
- Off the test page, with the browser set to `vm`, the steps still say "because I never sign in as you".
- "yes cancel netflix" with no browser open, and "do all of them", repeat steps already shown.
- After "looks right" in the setup, the bot quotes its own guess back as the person's goal.
- A second notice makes a second cancellation row, so the receipts count two.
- A plain "no" answers the check reminder only while it is the bot's newest message.
- "pause N" does not pause a rule's permission to add, though a paused rule does not run.
- A YouTube playlist rule may add 10 a day; a one-off add allows 50.
- With no Google client set up, a playlist rule says "connect youtube", which then says it is not set up.
- The Todoist sign-in works only from a browser on the bot's own computer. The link line does not say so.
- If the person never answers Todoist's REMOVE or KEEP question, the sign-in stays until their next message.
- Rotating a token ends that app's rule permissions, with one line.
- No "offer accepted" page exists among the practice flows; that receipt was checked with a made-up row.

Safety and set-up:
- On the test page, everyone typing is the operator unless `MVP_OPERATOR` is set (`none` shows what a tester sees).
- The sealing key sits in `MVP_HOME` beside the sealed files, unless `MVP_TOKEN_KEY` is set elsewhere.
- The panel's values belong to the computer: "export my data" leaves them out and "delete my data" leaves them.
- The browser ignores any proxy in the environment, so a machine that needs one cannot use it.
- On another address than loopback, anyone who reaches the test page can read it, use `/vm` and save panel values.
- Before the first browser opens `/vm`, the run's key alone opens the view.
- The practice merchant is served by a test module that product code imports. This is for the prototype only.
- "save it as a draft" puts a draft in the operator's mailbox with no separate yes (round 9's design).

Not checked by anyone: whether a US account gets Instagram's repeating export; how Todoist reads a due date; whether
the founder's machine has a screen for the browser window.

Two commits of the live fix pass (c8de218, 9f2bbf8) have their trailer lines run into the subject. They are pushed and
were not rewritten.

## What the founder must do

1. Pull the branch and restart the test page. Check that the footer shows the new build.
2. Open the Connections panel. Add your Gmail address and an app password from myaccount.google.com/apppasswords.
   Optionally add the TickTick token, the Todoist token and the webhook address.
3. For Todoist by sign-in: run the bot on your Mac, leave the Todoist token unset, say "connect my todoist", and press
   "Allow" in a browser on that Mac.
4. For YouTube: make a Google Cloud project. Set the consent screen to External and publish it "In production". Add the
   scope `.../auth/youtube` and a "TVs and Limited Input devices" client. Put its id and secret in the panel.
5. Try the practice merchant on the test page with `MVP_BROWSER=vm` and `MVP_BROWSER_DEMO=1`: "cancel my streamly".
   Then try one real merchant on your own Mac with `MVP_BROWSER=operator` and `MVP_BROWSER_MERCHANTS=<that one>`. Use a
   free trial you started for the test.
6. Label about 150 reels: "does the video show what the caption says?" The bar is 85%. Below it, set
   `MVP_CM_DOUBT_ALL=0`.
7. Write `data/mvp/selftest_private.jsonl` with your exact test messages, in the shape of
   `mvp/selftest/conversations.jsonl`. It stays out of git.
8. Decide A-008 to A-016. A-013 to A-016 need both founders.

Also open: whether the browser should honour a proxy; whether "do all of them" and "yes cancel netflix" with no
browser should stop repeating steps; tapping the Instagram repeating-export link and saying what the screen offers.

## Spend

| Work | Spend |
| --- | --- |
| Slice W (the errand form's evaluation) | $0.96 |
| Slice S (marked set and the 20 requests) | $1.01 |
| Slices G and Y | $0.03 each |
| Slices K, D, C, V, T, both merges, the check of acting | $0 |
| Check of reading (held-out set, 60 messages, 20 requests) | $0.80 |
| First live self-test | $0.39 |
| Live fix pass | $0 |
| Check of the live fixes | $0.03 |
| Not tied to a report: the main agent's live check of 19 Nov, and calls from the running test page | about $0.14 |
| **Since the verdict ($16.31)** | **$3.39** |

The ledger (`data/mvp/ai_runs.jsonl`, sum of cost over 6,877 rows) reads **$19.70 of the $30 cap**. $10.30 is left.

## Size

About 44,400 lines of Python and about 37,700 lines of tests in `experiments/mvp`.
