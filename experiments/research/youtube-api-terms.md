# YouTube API terms: what the search loop may do

*31 Oct 2026 · read from the YouTube API Services Developer Policies (fetched 30 Oct 2026) for round 3. This is not legal advice. Before product code depends on it, the founders should get a proper legal read.*

## The clauses that matter

| Clause | What it says (paraphrased) | Effect on us |
| --- | --- | --- |
| III.E.4, item 03 | API data must be refreshed or deleted within 30 days of being fetched. | `refresh_by` = fetched + 30 days on anything stored from the API. The research copy (`data/yt/ref/`) must be deleted by **2026-11-29**. |
| III.E.4, item 08 | API clients must not "access or use API Data to create new or derived data or metrics". | LLM summaries, facet slots and embeddings of API descriptions, tags and chapters appear to be derived data. Same for anything built from them. |
| III.E.1.a | No caching or storing of audiovisual content. | No thumbnail analysis tier. No downloading video. |
| III.E.6 | No scraping of YouTube pages. | Read watch pages only through the API or Takeout. |

## Decision for round 3 (Derrick, 30 Oct: "research-only reference arm")

- **Allowed track (counts):**
  - the user's own Takeout: titles, channels, playlist names, watch, like and save dates;
  - Gemini API YouTube-URL video understanding. This is a Google Gemini feature that reads a public URL; no YouTube API data is involved and nothing is downloaded.
- **API data:** used only for display and filtering (duration, availability).
- **Reference arm, research only:** API descriptions, tags and chapters were indexed (R0) and enriched (R1). This measures what the policy costs. It is labelled `ref_`, never adopted, and deleted by 2026-11-29.

## What the terms cost, measured (`results/r3-eval.md`)

- **Overall: nothing measurable.**
  - R0 vs A0: −0.005 [−0.088, +0.077] nDCG@10 on dev.
  - R1 vs A1: +0.007.
- **On specific kinds the cost is real.**
  - Moment searches: R0 reaches 0.69 on the one moment search, against 0.30 on the allowed track, because chapters and descriptions carry what Takeout titles lack.
  - Named-video searches: +0.19 with API text.
  - API text adds noise to topic and task searches.

## Open questions for the founders

1. **Does item 08 cover the user's own Takeout titles?** We assume not. Takeout is the user's data export, not API data.
2. **Is the Gemini YouTube-URL feature allowed for a commercial product at scale?** It is a preview feature, limited to public videos. Check Gemini API terms and the preview status before relying on it.
3. **Is showing API descriptions in the UI enough to make them searchable?** That is, does matching against stored, refreshed API text without LLM processing count as "derived data"? A keyword index over refreshed text might be allowed; LLM summaries probably are not. This needs a legal read.
