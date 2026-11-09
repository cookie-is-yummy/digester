# Derrick's labelling sheet (8 Nov 2026): real Instagram searches and judge calibration

Aggregates only. The per-item answers live in `data/all/evals/labels/ig_real.jsonl` and in `derrick-labels-2026-11-08.json`, which the orchestrator hands to the next cloud run.

## 1. Judge calibration (72 pooled dev items: 36 Instagram, 36 YouTube; AI grades hidden from Derrick)

| | Derrick 2 | Derrick 1 | Derrick 0 |
| --- | --- | --- | --- |
| **AI 2** | 15 | 7 | 2 |
| **AI 1** | 7 | 13 | 4 |
| **AI 0** | 1 | 7 | 16 |

- **Agreement:** exact 61%. Cohen's κ (3 grades) is 0.42, linearly weighted κ 0.51, and κ on relevant vs not 0.55 (Instagram 0.47, YouTube 0.60).
- **No overall lean:** the mean grade is 1.00 for the AI and 1.01 for Derrick. The round-8 audit's "AI slightly stricter" does not show here.
- **Most disagreements are one step apart** (2↔1, 1↔0). Only 3 of 72 are two steps apart.
- **This matches the audit's κ 0.39–0.49,** so the AI judge is a usable but noisy proxy for Derrick, especially on Instagram.

**Derrick's notes on why grades differ:**
1. **The scale is too coarse.** Several items sit "between partly and right". A 4-point scale (wrong / related / good / exactly what I meant) would capture this.
2. **Instance vs about.** For some searches he wants *instances* of a genre, not content *about* it:
   - "viral SaaS marketing videos" means viral videos that market a SaaS product, not advice on SaaS marketing;
   - a "top videos for deep knowledge" search means the deep-knowledge videos themselves, not a video listing them.

   Content about the genre is at most partly right. Neither the rewrite nor the judge rubric separates these today. It is a candidate query slot ("instance" vs "about"), and a rubric line for judges.

The two dev searches where he gave this clarification have it added to their `intent` (evaluator side).

## 2. Real Instagram searches (`ig_real`, 31 searches over 32 target posts)

- **Source:** 40 sampled posts (22 saved, 8 shared to self, 10 liked; friends' posts excluded). Derrick opened each post and wrote how he would search for it later.
- **Yield:** 8 skipped ("I wouldn't search for this"). One search covers two posts.
- **Captions:** they were hidden by default and revealed for 9 posts (6 of the kept searches are flagged).

**Three kinds of search, which need different scoring:**

| Kind | Count | What the target is | Scoring |
| --- | --- | --- | --- |
| Known item | 8 | the specific post he remembers | `mrr2` / `s10_2` on the target |
| Topic | 22 | one good answer among many ("pencil shading tips") | target = 2, **pool-judge** the other top-10 items; nDCG@10 |
| Meta / instance | 1 | an *example* of a quality (a reel with a great hook), whose content is about something else | target = 2, pool-judge; the intent says instances, not advice |

**Implications:**
- **Most real searches for saved posts are topical, not known-item.** Synthetic known-item sets (`ig_known`) measure the minority case. The te-bias question should be settled on `ig_real`'s known-item and topic slices separately.
- **"Meta" searches need the instance-vs-about distinction above,** and the target can share no topic words with the search. This is the hardest kind for text retrieval.
- **Small set:** at 31 searches the MDE is about 0.08–0.10. It is a first real check on the Instagram claims, not a final one.
