# 00 · Vision

## The idea

AI makes content effectively infinite, so attention becomes the bottleneck. Scrolling is inevitable, and every saved reel or video encodes a desire: a recipe to cook, a place to go, a skill to learn, an opportunity to apply for. Today that consumption ends at the save button. Saved folders become graveyards.

**We help people reclaim control of their media.** Content people save or share flows into one funnel, gets understood, and comes back as:

- **Understanding:** what their attention keeps returning to, what is rising or fading, and how that compares with what they say they want.
- **Action:** concrete next steps, placed in the tools they already use, at the moment they matter.
- **Control:** rules in plain language ("email me 5 gift ideas every Monday") that make their media work for them.

We are not a screen-time blocker and not another AI planner. We are the layer that remembers what you were drawn to across every app and helps you do something about it.

## Who it is for

People who scroll Instagram and YouTube heavily and feel that useful content vanishes once watched. Launch persona: founders, builders and students who save marketing ideas, opportunities, tutorials and recipes and never act on them.

What people want from saved media, in order of how often it comes up:

1. **Remember it:** find it again by what it was about.
2. **Get the gist:** the useful part without rewatching.
3. **Act on it:** the recipe, place, deadline, technique or product inside it.
4. **Understand themselves:** what their attention returns to, and how it changes.
5. **Share it with the right person.**

## The core loop

1. **Onboarding** asks very little: which platforms they use, how much of it they think is useful, an optional goal in their own words. It then guides them through downloading their data export (only the parts we need).
2. **Upload and first report.** We process the export in the background. The first report is the moment of value: their media summarised like a chess game report (key moves only), themes, trends, "you guessed 40% useful, your data says 31%", and opportunities they could act on.
3. **Theme check.** One screen of detected themes. The user labels each: *pursue*, *practise*, *someday*, *enjoy* or *not me*. This is how we learn direction without a long form.
4. **Ongoing capture.** From then on they share content to our account (DM a reel on Instagram, add to a playlist on YouTube). Shares are the user's own filter and our strongest signal.
5. **Requests and rules.** A text box: "email me the top 5 things to do in Berlin next week", "text me 5 gift ideas every Monday", "what do I know about physics from the last 2 months?". Each request is compiled into a rule: *when* + *content* + *do*.
6. **Digest.** A periodic summary that reports what rules did, suggests actions no rule covers, and suggests new rules.

## Principles

- **Value on day one** from the history export, not after weeks of capture.
- **Ask little, learn through easy questions.** A few high-information taps beat setup forms.
- **Watching is not wanting.** Big interests can be hobbies. Nothing is called "misaligned" until the user has said what a theme means to them.
- **Our platform works alone; the user's agent makes it powerful.** No AI of their own required, but MCP access is the paid core.
- **Deliver into existing tools**, at the moment of intent, not into another inbox.
- **Pay for understanding only when it earns its keep.** Cheap processing for everything, expensive enrichment only where it matters.
- **Trust is the positioning.** Real deletion, no ads, no selling data, the user's data is theirs.

## MVP scope (Agreed, 28 Oct)

Backend first. Two inputs, two outputs, a basic but real processor.

| Area | In the MVP |
| --- | --- |
| Inputs | **Instagram**: data export import + live DM-share capture. **YouTube**: Google Takeout import + a dedicated playlist via the YouTube Data API |
| Processor | Adapters, cleaning, filter, embeddings, themes and trends, search, first report, theme check data, direction |
| Requests | Natural language → rule compiler for a small action set |
| Outputs | **Email** (first, no OAuth needed) and **Google Calendar** (second). The first report is produced as JSON for whatever renders it |
| Speed | First report within minutes of upload (see `05-processor.md` › Performance targets) |

## Out of scope for now

- **Frontend** (hub, boards, onboarding screens). Backend endpoints and JSON outputs come first.
- **Desktop app and local-first storage.** A real future direction ("your data stays on your machine", local MCP server). Keep all storage behind `scrolldigest/db/` so it can move later; do not build for it now.
- **MCP server.** Designed (`01-architecture.md`), built after the query API is stable.
- **More platforms** (TikTok, Reddit, X, LinkedIn, articles). The adapter design must make them additive.
- **Recommendations from outside the user's own data, habits, screen-time measurement.**

## Planned later: boards and related-media search (frontend)

**Vision boards: the Pinterest of all your media.** Boards for different interests, mixing content from every platform (reels, videos, posts, later articles). Users add items by hand, and the board suggests related items from everything they have ever saved, shared, liked or watched, found by meaning rather than keywords. A board can also be the default visual output of a theme or a goal.

The frontend comes later, but the backend is designed for it now:
- **Every item is embedded**, including likes and views, so related-item search covers the user's whole history.
- The query API has **`similar`** (more like these items) and **`suggest_for_board`** (related items not yet on a board).
- **Boards are a saved search plus a hand-picked set**: suggestions come from the board's own items, so boards improve as the user curates.
- Boards and board items are in the data contract (marked *Later*), so adding them is a frontend job plus a migration, not a redesign.
- **Later still:** visual embeddings of thumbnails, so items can be matched by how they look as well as what they say (useful for art, design, fashion, travel boards).
- **Text messages** as an output (US carrier registration and per-message cost); use email, push later.

## Business model (for context)

Free, Pro and Max tiers. Free: Instagram and YouTube intake, weekly digest, limited history and one output integration. Pro: all outputs, read-only MCP. Max: everything, custom digest formats, custom rules, model choice. Prices tested with the beta cohort. No ads.
