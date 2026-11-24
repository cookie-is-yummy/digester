# digestr product spec (proposal)

*21 Nov 2026 · written by Eason · **Status: a proposal, not accepted.** It has not been through `docs/amendments.md`. What already exists for each line, and where it conflicts with the agreed docs, is in [2026-11-21-digestr-integration.md](2026-11-21-digestr-integration.md).*

digestr is a text message agent that takes in what you watch, like and save on social media, turns each item into a structured takeaway, and sends back digests, plans and one-tap actions so your feed becomes things you do.

## Step 1: The bot (input and initiation)

Goal: a user texts a number, gets set up in under two minutes, and has an easy way to send content.

- **Channel:** iMessage and SMS through a hosted provider (Sendblue, Linq or Photon), with Telegram for development. Put the channel behind an adapter so the agent logic stays the same everywhere.
- **Identity:** the phone number is the account. There are no passwords, and the first text creates the user record.
- **Onboarding:** three messages at most. Ask what they want out of their feed (goals), then offer the connections, then prompt them to forward one video so they see value immediately.
- **Inputs, in order of priority:**
  1. Forwarded links from any platform to the number
  2. YouTube through an OAuth link sent in the thread, synced daily
  3. Reels shared to the digestr Instagram account, linked to the user by a one-time code
  4. Instagram export sent to Google Drive for likes and saves history
- **Commands in plain language:** "connect youtube", "pause", "what did I save about Tokyo", "delete my data". The model routes intent, so users never learn syntax.

Done when: a new user can text the number, connect YouTube, forward a Reel, and every item lands in a queue tagged with their user ID and source.

## Step 2: The ingestion (processing the data)

Goal: turn each raw link or file into one clean, structured, searchable item.

- **Normalize:** every input becomes the same record (user, source, URL, timestamp, signal type such as forwarded, liked, saved or watched).
- **Deduplicate:** hash the URL so a video processed once is cached for all users.
- **Fetch:** caption, creator and metadata first. Pull the video only when the caption is thin.
- **Transcribe and read:** speech to text for audio, and frame sampling for text shown on screen such as ingredients or addresses.
- **Extract:** a small model returns structured JSON with:
  - Type: recipe, place, product, workout, idea, event, book, tutorial or entertainment
  - A two-line summary
  - Entities: names, locations, prices, dates
  - The concrete action, if one exists
  - A confidence score and a flag for shaky claims
- **Weight:** forwarded and saved items count as high intent, liked as medium, watched as low. This decides what reaches the digest.
- **Cluster:** embeddings group related items into collections and link them to the goals stated at onboarding.
- **Store:** Postgres with pgvector, with every item keeping its source link.

Done when: a forwarded Reel becomes a stored, typed item within about fifteen seconds, and a 500-item export processes in the background without blocking the thread.

## Step 3: The output (making it actionable and useful)

Goal: every message from the bot should save the user time or prompt a decision.

- **Instant receipt:** two lines per forwarded item with the takeaway and one suggested action. Entertainment gets a quiet acknowledgment and nothing more.
- **Scheduled digest:** weekly by default, grouped by theme, limited to three actions. Low-intent items appear only as a pattern ("you watched 14 videos on fundraising this week").
- **Recall:** questions answered from the store with the original link attached.
- **Collections into plans:** once a cluster reaches a threshold, the bot offers to convert it. Places become an itinerary, recipes become a grocery list, workouts become a weekly split, and tutorials become a learning sequence.
- **Actions with confirmation:** calendar events, reminders, a Maps list or a shopping cart, each executed only after the user replies yes.
- **Follow through:** a nudge when a saved event is close or a saved item sits untouched for weeks, with an option to drop it.
- **Consumption mirror:** a monthly note comparing what they consumed with the goals they gave.
- **Web view:** one page per user for browsing collections, opened by a magic link from the thread.
- **Controls:** digest frequency, quiet hours, mute a topic.

Done when: a test user acts on at least one suggestion a week without being asked to. That is the metric to watch.
