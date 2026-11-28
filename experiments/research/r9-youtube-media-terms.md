# YouTube media through Gemini: terms check for the round-9 pilot

*9 Nov 2026 · Researcher, round 9, Track 2 (BRIEF-9 "media pilot"). All pages fetched 9 Nov 2026. This is not legal advice. It follows `youtube-api-terms.md` (round 3), which left open whether the Gemini YouTube-URL route is allowed. Before product code depends on this route, the founders should get a proper legal read.*

## Question

Do the terms allow a research pilot that:

- sends ≤ 150 **public** YouTube URLs from the user's own library (video IDs from Takeout, not from the YouTube Data API) to the Gemini API, at low media resolution;
- asks for a ≤ 40-word description of what is shown, the music or sound, and what is said, with no transcript and no quotes longer than a few words;
- stores those descriptions under `data/` only, marked research-only, and deletes them at round end?

## Conclusion: ALLOWED for the pilot (yes, with the conditions below). UNCLEAR for the product.

**Why yes for the pilot:**

1. **Google documents this exact use.** The Gemini API video-understanding page says "You can pass YouTube URLs directly to Gemini API". Its code sample prompt is "Please summarize the video in 3 sentences." Our request is a shorter version of Google's own example.
2. **No term we read forbids it.** The Gemini API Additional Terms, the Google APIs Terms and the Generative AI Prohibited Use Policy have no YouTube-specific clause. The only YouTube rules attached to the feature are "public videos only" and the volume limits.
3. **We never touch YouTube.** Google's servers fetch the video, so we do not access the YouTube Service by automated means, download anything, or scrape it. We also make no YouTube Data API call, so none of the content in this route is YouTube "API Data".
4. **The output is ours to use, and it is small.** Google "won't claim ownership" of generated content, and we are "responsible for [our] use" of it. A ≤ 40-word factual description with no long quotes, deleted at round end, is a low-risk use.

**Why unclear for the product:**

- **The feature is in Preview.** The page says it is "in preview and is available at no charge" and that "pricing and rate limits are likely to change". Vertex AI puts the same feature under its "Pre-GA Offerings Terms". The 2024 Gemini Additional Terms said "You may not use any Services identified as 'Preview' for production use". The version effective 23 Mar 2026 no longer has that sentence, but the label is still there.
- **Who needs rights in the video is not settled.** Google APIs Terms §5(b) says that before you submit content you must "have the necessary rights" to it. Whether a URL counts as submitted content is open. On a Google AI developer forum thread (15 Oct 2026) a developer asked exactly this for a commercial app. The one reply (23 Oct 2026) said "We can't provide specific legal guidance on this forum", and no official answer has been given.
- **YouTube's terms limit viewing to personal use.** The YouTube ToS (US version, dated 15 Dec 2023) bars using the Service "to view or listen to Content other than for personal, non-commercial use". A paid product that processes users' libraries is a different case from one user's own research pilot.
- **Stored derived descriptions at product scale** may be read as building a database of content descriptions. Google APIs Terms §5(e) bars you from "scrape, build databases, or otherwise create permanent copies" of content returned from the APIs. That needs a legal read before descriptions are kept in the product.

## Conditions for running the pilot

1. **Paid tier only.** The video IDs reveal the user's watch history. The Unpaid Services terms say "Do not submit sensitive, confidential, or personal information", and on unpaid tiers "human reviewers may read, annotate, and process your API input and output". Confirm the Gemini key is on a billed project before any call.
2. **Public videos only.** Skip any video the API rejects. Never retry through a download or the File API (that would mean downloading YouTube audiovisual content, which YouTube ToS item 1 and Developer Policies III.E.1 forbid).
3. **No identification of people.** YouTube ToS item 4 bars collecting "any information that might identify a person (for example, usernames or faces)". Prohibited Use Policy 1.6 bars using "personal data or biometrics without legally-required consent". The prompt must ask for a generic description ("a person cooking"), not who appears. We already hold channel names from Takeout.
4. **No transcript, audio or frames** are requested or kept (AGENTS.md rule 8). Quotes stay at a few words. Whether a "what is said" summary may be kept in the product is a founders' decision, so it is flagged.
5. **Storage and deletion.** Store under `data/` only (rule 9), in a file marked research-only, with nothing in git. Delete at round end unless the founders approve keeping it, and in any case within 30 days. The 30-day rule in Developer Policies III.E.4 does not formally apply, because this is not API Data, but we keep it as a safe default.
6. **Volume.** ≤ 150 videos, one URL per request (simpler cost attribution; Gemini 2.5+ allows up to 10), low media resolution (about 100 tokens per second), sequential calls, and no attempt to get around rate limits or errors. The paid tier has "no limit based on video length". The free tier is capped at 8 hours of video per day. Every call goes through `experiments/lib/ai.py` and is logged, with the BRIEF-9 $2 cap.
7. **Don't count on it being free.** Budget at normal token pricing even though the docs say "no charge".

## How the YouTube API Developer Policies bear on this

These policies govern the "YouTube API Services" (Data API, embedded player). "API Data" means content "provided to" an API Client through those services. The Gemini route uses none of them, so:

| Clause | Applies? | Note |
| --- | --- | --- |
| III.E.4: refresh or delete after 30 days | Not formally | Round-end deletion meets it anyway. |
| III.E.4: no "new or derived data or metrics" from API Data | No, if inputs are Takeout IDs plus Gemini output | Do **not** feed API descriptions, tags or chapters (the `ref_` copy) into the Gemini prompt. That would make the output derived from API Data. |
| III.E.1: no download/cache/store of audiovisual content | Respected | Nothing is downloaded; only text is stored. |
| III.I.7: no separating audio or video components | Respected in spirit | We don't request audio or transcript. |
| III.E.6: no scraping | Respected | No page fetches. |

## Related, not binding here

- YouTube's creator "third-party training" setting (Dec 2024, off by default) controls **AI model training** by third parties. The pilot does no training, so it does not apply. It does show that YouTube distinguishes training from other machine reading.

## Sources (all fetched 9 Nov 2026)

1. Gemini API, Video understanding (YouTube URL section, Preview note, limits, example prompt): https://ai.google.dev/gemini-api/docs/video-understanding, which redirects to aistudio.google.com/docs/video-understanding. No page date shown.
2. Gemini API Additional Terms of Service, effective 23 Mar 2026: https://ai.google.dev/gemini-api/terms, which redirects to aistudio.google.com/docs/terms. Earlier version effective 13 Dec 2024, with the "Preview not for production" sentence: https://ai.google.dev/gemini-api/terms_preview
3. Google APIs Terms of Service, last modified 9 Nov 2021, §§2(b), 5(a)–(e): https://developers.google.com/terms
4. Generative AI Prohibited Use Policy, last modified 17 Dec 2024, items 1.6 and 1.7: https://policies.google.com/terms/generative-ai/use-policy
5. YouTube Terms of Service (US), dated and effective 15 Dec 2023, Permissions and Restrictions items 1, 3, 4 and 9: https://www.youtube.com/static?template=terms&gl=US
6. YouTube API Services Developer Policies, III.E.1, III.E.4, III.E.6 and III.I.7 (no date on page): https://developers.google.com/youtube/terms/developer-policies
7. Vertex AI video understanding ("owned or public", Pre-GA Offerings Terms): https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/video-understanding
8. Google AI Developers Forum, "Terms for passing public YouTube URLs to Gemini API in a commercial app" (asked 15 Oct 2026, reply 23 Oct 2026, no official answer): https://discuss.ai.google.dev/t/terms-for-passing-public-youtube-urls-to-gemini-api-in-a-commercial-app-which-document-governs-this/189597
9. YouTube Help, "Your content & third-party training": https://support.google.com/youtube/answer/15509945

## For the founders

- **Product use of this route needs a legal read.** It is Preview, it carries the §5(b) rights question, and YouTube limits viewing to personal, non-commercial use. A written answer from Google would settle it.
- **A "what is said" summary in the product** is a rule-8 decision.
- **Keeping descriptions past round end** needs approval. Without it they are deleted.
