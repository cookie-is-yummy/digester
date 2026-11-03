# YouTube search eval: file format

PROTOTYPE. Same two-file split as the Instagram set, so `lib/corpus.py` and `eval/score_run.py` keep working with small
additions. Synthetic examples: [`fixtures/queries_example.jsonl`](fixtures/queries_example.jsonl) (method side),
[`fixtures/answers_example.jsonl`](fixtures/answers_example.jsonl) (evaluator side),
[`fixtures/run_example.json`](fixtures/run_example.json) (a run file with moments).

Real files live in `data/` only: `data/evals/youtube/queries.jsonl` (method side) and
`data/evals/youtube/labels/evalset.jsonl` (evaluator only), plus `data/evals/youtube/split.json`. A search someone
wrote about their own history is personal data; nothing real goes in git.

## Content codes

As on Instagram, items are identified by their content code, the part of `dedup_key` after the colon. For YouTube that
is the 11-character video ID (`youtube:SYNvid00001` → `SYNvid00001`). Run files and labels use codes, so any corpus
build or embedding can be scored.

## Method side: `queries.jsonl`

Exactly the Instagram keys, nothing that gives the answer away:

| Key | Type | Notes |
| --- | --- | --- |
| `id` | str | e.g. `yt_q03` |
| `query` | str or null | null only for `more_like_this` |
| `kinds` | str[] | first kind is the primary one (per-kind reports group on it) |
| `examples` | str[] | video IDs for `more_like_this` |
| `filters` | object | `before` (ISO date, compared with `first_seen_at`), `kinds` (interaction kinds: `watch`, `like`, `playlist`, `share_self`) |

Kinds: the Instagram ones (topic, name, more_like_this, structure, task, said_shown, place, vibe, audio, time, people)
plus **`moment`**: "the part where…" searches. A moment search wants a place inside a video, not just the video. It
may carry a second kind for what identifies the moment (`["moment", "said_shown"]`).

## Evaluator side: `labels/evalset.jsonl`

The Instagram label keys, plus `moments` on moment searches:

| Key | Type | Notes |
| --- | --- | --- |
| `id`, `query`, `kinds`, `filters` | | copied from the method side |
| `relevant` | {code: grade} | 2 = right answer, 1 = borderline. For a moment search: the videos that contain the moment |
| `hard_negatives` | str[] | judged wrong but close (same channel, same topic) |
| `judged_not_relevant` | str[] | judged wrong |
| `moments` | {code: [{start_s, end_s, grade}]} | moment searches only. Seconds from the start of the video; a video may have several spans; `grade` as above |

Labelling a span: the labeller watches the video (on YouTube, not a download) and writes the start and end of the
part the search describes, rounded to 5 s. If the search could fit several parts, list each one.

## Run files

Unchanged (`{"method", "embedding", "meta", "queries": {qid: [code, ...]}}`), plus an optional ranked `moments` block
for moment searches:

```json
"moments": {"yt_q03": [{"code": "SYNvid00001", "start_s": 45, "end_s": 190}, ...]}
```

A method that returns only videos for a moment search is scored on videos and gets no moment credit, with one
exception: a video no longer than 60 s (a Short) counts as the segment `{0, duration}`.

## Scoring

**Video level, every search (moment searches included):** the existing metrics on `queries` against `relevant`
(ndcg10, p10, success5, mrr, r100, unjudged10). Filters apply as on Instagram.

**Moment level, moment searches only.** A product moment is a deep link that jumps to `start_s`. So a returned segment
`s` is a **hit** for a labelled span `a` of the same video when the link lands usefully:

```
hit(s, a) = a.start_s - LEAD <= s.start_s <= a.end_s          # lands at most LEAD seconds early, never after the end
LEAD = 30                                                      # seconds of lead-in a person tolerates
```

Reported per moment search, then averaged:

| Metric | Definition |
| --- | --- |
| `moment_success5` | any hit among the first 5 returned segments (the moment version of the Gate 1 metric) |
| `moment_mrr` | 1 / rank of the first hit |
| `moment_ndcg10` | graded by the hit span's `grade`, each labelled span credited once |
| `overlap_success5` | looser: any of the first 5 segments overlaps a span at all (`s.start_s < a.end_s and s.end_s > a.start_s`) |
| `r1_tiou30` | stricter, the temporal-grounding convention: top segment's temporal IoU with a span ≥ 0.3 |
| `start_error_s` | median of abs(s.start_s - a.start_s) over first hits (how far the deep link lands from the start) |

Why the "lands" rule is primary: chapter-sized segments (often minutes) overlap almost anything, so plain overlap
overstates quality, while IoU punishes a correct deep link inside a long chapter. Overlap and IoU are reported beside it
so the choice can be revisited with real labels.

The evaluator implements these in `eval/score_run.py` (a `--moments` flag); builders do not, per the role split.

## Worked example (synthetic)

`yt_q03` labels `SYNvid00001` span 45–190 s. The example run returns 45–190 first (hit at rank 1: lands exactly at the
start; IoU 1.0) and 0–45 second (lands 45 s early, more than LEAD, so no hit; it overlaps nothing). `yt_q04` labels
`SYNvid00005` 280–330 s (grade 2) and 545–560 s (grade 1). The run's first segment, 75–280 s, starts 205 s early and
ends where the span begins: no hit, no overlap. Its second, 280–545 s, lands at the start: hit at rank 2, mrr 0.5.
