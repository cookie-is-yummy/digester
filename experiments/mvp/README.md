# MVP skeleton (prototype)

Text a request, get cited answers from your own saved and watched posts, now or on a schedule. Build plan and rules:
`experiments/BRIEF-10.md`. This is prototype code; it is rewritten after the first tester sessions.

## Set up on the Mac (once)

1. Python 3.12+ and the demo's packages: `python3 -m pip install -r experiments/demo/requirements.txt -r experiments/mvp/requirements.txt`
2. Put the library folder somewhere under `data/` (your `data/all`, or a library the demo built from exports).
3. Create `data/mvp/people.json` (outside git):
   ```json
   {"+15551234567": {"name": "Derrick", "library": "data/all", "timezone": "America/New_York"}}
   ```
   The key is the phone number (E.164) or Apple Account email the person texts from.
4. `export OPENAI_API_KEY=...` in the terminal that runs the bot. Never put keys in files.

## Run

From `experiments/`:

- **Console** (type as a test person): `python3 -m mvp.bot --channel console`
- **This Mac's Messages app** (founders, build days): `python3 -m mvp.bot --channel mac`
  - System Settings › Privacy & Security › Full Disk Access: add the terminal app (to read `~/Library/Messages/chat.db`).
  - The first send asks to let the terminal control Messages: allow it.
  - Text the Mac's iMessage account from another phone (Eason's) to start.
- **Sendblue** (testers): set `SENDBLUE_API_KEY_ID`, `SENDBLUE_API_SECRET_KEY`, `SENDBLUE_FROM_NUMBER`,
  `SENDBLUE_WEBHOOK_SECRET`, run `python3 -m mvp.bot --channel sendblue`, expose `127.0.0.1:8787` with a tunnel
  (`cloudflared tunnel --url http://127.0.0.1:8787`), and register `https://<tunnel>/sendblue/receive` as the
  `receive` webhook with the same secret in Sendblue's dashboard.

The first reply after a start can take about a minute while the search engine loads a large library.

## Test

- Offline tests (no API calls): `python3 -m pytest -q mvp/tests`
- The test requests on a library: `python3 -m mvp.run_requests ../data/mvp/requests.jsonl ../data/all`
  Writes the conversation and a grading sheet to `data/mvp/eval/...` (outside git) and prints counts only.

## Kill switch

Stop the bot with Ctrl+C. To pause one person: `UPDATE people SET paused=1 WHERE handle=...` in `data/mvp/mvp.sqlite`.
"delete my data" requests are listed in `data/mvp/deletions.jsonl`; a founder removes that person's library folder and
message thread, then confirms to them.

## What is where

| File | Job |
| --- | --- |
| `core.py` | Message handler, executor, scheduler. The only code that sends |
| `interpret.py`, `prompts/interpret_v1.md` | Message to a validated rule spec or intent |
| `retrieve.py`, `engines.py`, `libview.py` | Candidates from the person's own library (Q8 search, filters) |
| `compose.py`, `prompts/compose_v1.md` | The model picks; code enforces the reliability rules (BRIEF-10 section 5) |
| `render.py` | The message text |
| `schedule.py`, `schema.py`, `store.py`, `llm.py` | Times, forms, records, model calls and cost caps |
| `channels/` | Console, Mac Messages, Sendblue |
