# Scroll Digest search demo

A small app that runs on your own laptop. It opens a web page where you can search a library of saved, liked and watched posts with the round-8 search processor (**Q8**, see `docs/research/2026-11-08-round8.md`). It comes with Derrick's library preloaded, and it can build a library from your own Instagram and YouTube exports.

This is a prototype for trying the search, not product code.

## What you need

- A Mac or a Windows PC with about 4 GB of free memory. Derrick's library uses about 2.5 GB while the app runs.
- **Python 3.12 or newer**, from [python.org/downloads](https://www.python.org/downloads/).
  - On Windows, tick **"Add python.exe to PATH"** on the installer's first screen.
- The `digester` code folder (Derrick will send it, or use the `experiments/search-loop` branch).
- The data pack `derrick.zip` (Derrick will send it; about 220 MB).
- An **OpenAI API key** for real searches. A **Gemini key** is optional; it is only needed to run the te pass on your own Instagram export.

## Set it up (once)

1. **Unzip the data pack** into a folder of its own, for example `Documents/scroll-digest-libraries`. You should then have `Documents/scroll-digest-libraries/derrick/`.
2. **Open a terminal.**
   - Mac: open the *Terminal* app.
   - Windows: open *PowerShell*.
3. **Go to the code folder.** Type `cd ` (with a space), drag the `digester` folder into the window, and press Enter.
4. **Install the four Python packages the app uses.**
   - Mac: `python3 -m pip install -r experiments/demo/requirements.txt`
   - Windows: `py -m pip install -r experiments\demo\requirements.txt`

## Run it

1. **Set your OpenAI key** in the same terminal. You can skip this and paste the key into the page instead.
   - Mac: `export OPENAI_API_KEY="sk-..."`
   - Windows: `$env:OPENAI_API_KEY="sk-..."`
2. **Start the app.**
   - Mac: `python3 experiments/demo/app.py --library ~/Documents/scroll-digest-libraries`
   - Windows: `py experiments\demo\app.py --library $HOME\Documents\scroll-digest-libraries`

Your browser opens at `http://127.0.0.1:8765/`. Loading Derrick's library takes about a minute; the page shows "ready" when it's done. To stop the app, press `Ctrl+C` in the terminal.

## Searching

- **Type a search** and press Enter.
- **Pick a processor:**
  - **Q8 (recommended):** short keyword searches go straight to search. Longer, descriptive searches are first rewritten by gpt-5-nano. A soft platform weight is applied, Instagram items also match their AI summaries (the "te" pass), and searches read as YouTube get a gpt-5-nano reordering of the top 20.
  - **H0:** the older baseline. It rewrites every search and has no te, no platform weight and no reordering.
  - **FM:** Q8, but with the stronger gpt-5-mini doing the reordering.
- **Compare with** shows two processors side by side and how many of their top 10 results are the same.
- **The "why" panel** shows:
  - which path the search took, and the rewrite's phrases and keywords;
  - how the platform weight read the search (Instagram or YouTube);
  - whether the reordering ran;
  - how long each stage took;
  - what this search cost.

**Cost.** In round 8, Q8 cost about $0.05 per 1,000 searches (FM about $0.09, H0 about $0.13). Searching the same thing again is free, because the results of earlier calls are cached in the library folder.

**Spending cap.** Each library has its own cost ledger (`ai_runs.jsonl`). By default, spending stops at $4 per provider per library. To change the cap, set `DIGESTER_OPENAI_BUDGET_USD` before starting the app.

### With and without a key

| | No OpenAI key | With an OpenAI key |
| --- | --- | --- |
| Search | Keyword-only fallback (BM25), clearly labelled. Not the real processor. | Q8, H0 and FM as tested in round 8. |
| Rewrite, refine | Skipped. The page says so. | Run when the processor asks for them. |
| Add a library | Import only. | Import and Prepare. The te pass also needs a Gemini key. |

## Add your own library

1. **Request your exports.**
   - **Instagram:** Accounts Center → *Your information and permissions* → *Download your information*. Choose **JSON** format and *All time*. Include saved posts, likes, messages, followers and following.
   - **YouTube:** go to [takeout.google.com](https://takeout.google.com) and select *YouTube and YouTube Music*. Optionally also select *My Activity*, which can hold extra watch history. Takeout may split the export into several zips; add them all.
2. In the app, click **Libraries & uploads**.
3. **Add the zips.** Either choose the files, or paste each zip's path on your computer. Pasting the path avoids copying a large file.
4. **Import.** The app reads the exports and creates a new library folder next to Derrick's.
5. **Prepare.**
   - The app first shows the estimated cost and time.
   - Embedding the items with OpenAI costs well under $1 for most libraries.
   - The **te pass** is optional. It writes short AI summaries of Instagram posts with Gemini, which makes Instagram search better. Expect about $0.36 per 1,000 Instagram posts, and roughly 5 to 10 minutes per 1,000 posts.
   - You can set a spending cap for the te pass, or choose **Skip te**: that's cheaper, but Instagram search will be weaker.
   - Prepare can be stopped. Running it again carries on where it left off.

## Privacy

- **Everything stays on your computer:** the exports, the library folders, the cost ledger, and the cache of past searches and their vectors.
- **Only text goes out:**
  - **To OpenAI:** what you type in the search box, and the item captions and titles. These are used for embeddings, the rewrite and the reordering.
  - **To Gemini:** Instagram captions, and only if you run the te pass.
- **Friends' posts** (accounts you follow that also follow you) are removed when a library is imported and never shown.
- **DM message text** is never read or stored. Only posts you shared in DMs are used.
- **API keys** typed into the page are kept in memory only. They are never written to disk or logged.

## If something goes wrong

- **"keyword fallback" on every search:** the app has no OpenAI key. Add one under **API keys**.
- **The page doesn't open:** copy the address printed in the terminal into your browser. If port 8765 is busy, the app picks the next free one.
- **The library is slow to load or the computer runs out of memory:** close other apps. Derrick's library needs about 2.5 GB.

## For developers

- **Files:**
  - `app.py`: the server.
  - `engine.py`: the round-8 processors, run in one process per library.
  - `ig_import.py`, `ingest.py`: the importers.
  - `make_pack.py`: builds the data pack.
  - `parity.py`: compares the demo's rankings with the round-8 runner's.
  - `test_demo.py`: the tests.
- **Build the pack:** `python experiments/demo/make_pack.py --src data/all --out <dir> --zip`
- **Run the tests:** `python -m pytest experiments/demo/test_demo.py -q`
