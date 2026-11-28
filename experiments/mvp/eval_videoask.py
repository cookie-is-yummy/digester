"""PROTOTYPE ONLY - the evaluation of asking a video (round 11, slice Q's prompt; DESIGN.md sections 18.Q and 18.L2).

    python3 -m mvp.eval_videoask --list <file outside git> --prompt video_ask_v1 --out <file outside git> [--dry]
    python3 -m mvp.eval_videoask --rescore <out file of a run> --out <file outside git>

from `experiments/`. Live Gemini calls (GEMINI_API_KEY, MVP_LEDGER_HOME and MVP_TOTAL_CAP_USD must be set); nothing is
fetched by this computer but the model's answer (Google fetches the video). The list ships with no real ids: it is a
file outside git, one JSON object per line:

    {"id": "c1", "video_id": "<11 characters>", "length_s": 293, "question": "...", "covers": true}

`covers` is the evaluator's own reading (true: the video answers the question; false: it does not cover it). Each line
is asked once through slice Q's own request (videoask.request_for: the link and "Question: ..." only), the prompt
version given, and its answer goes through slice Q's own code checks (videoask.check_points, the same as a person's
ask). --rescore applies the code checks of this tree again to the model answers kept by an earlier run (no call).

Scored by code (`score`): of the lines that the video does not cover, how many were answered "doesn't cover" (no
point shown); of the covered ones, how many answered, the points shown, the timestamps inside the video, and what the
checks left out. Whether each point answers the question is the evaluator's own reading of the out file (it is kept
for that, outside git); this script never judges it.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(HERE)


def load(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def checked(row, out):
    """(kept points, dropped counts, answered) for one model answer, by slice Q's code checks."""
    from . import videoask as V
    clip = V.max_seconds() if (not row.get("length_s") or row["length_s"] > V.max_seconds()) else None
    kept, dropped = V.check_points(out, row.get("length_s"), clip, None, question=row["question"])
    answered = isinstance(out, dict) and out.get("answered") is True
    if not answered:
        kept, dropped = [], {k: 0 for k in dropped}
    return kept, dropped, answered


def score(results):
    cov = [r for r in results if r["covers"]]
    not_cov = [r for r in results if not r["covers"]]
    pts = [p for r in cov for p in r["kept"]]
    return {
        "covered": len(cov),
        "covered_answered": sum(1 for r in cov if r["kept"]),
        "covered_points": len(pts),
        "covered_points_per_answer": [len(r["kept"]) for r in cov],
        "timestamps_inside": sum(1 for r in cov for s, _ in r["kept"] if not r.get("length_s") or s <= r["length_s"]),
        "not_covered": len(not_cov),
        "not_covered_said_so": sum(1 for r in not_cov if not r["kept"]),
        "not_covered_points_shown": sum(len(r["kept"]) for r in not_cov),
        "left_out": {k: sum(r["dropped"].get(k, 0) for r in results) for k in sorted({k for r in results
                                                                                         for k in r["dropped"]})},
        "errors": sum(1 for r in results if r.get("error")),
        "cost_usd": round(sum(r.get("cost") or 0 for r in results), 6),
        "seconds": [r.get("seconds") for r in results],
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--list")
    ap.add_argument("--prompt", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--rescore")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)
    sys.path.insert(0, EXP)
    from mvp import config, llm
    from mvp import videoask as V
    if a.rescore:
        runs = load(a.rescore)
        res = []
        for r in runs:
            kept, dropped, _ = checked(r, r.get("raw"))
            res.append(dict(r, kept=kept, dropped=dropped))
        with open(a.out, "w", encoding="utf-8") as f:
            for r in res:
                f.write(json.dumps(r) + "\n")
        print(json.dumps(score(res), indent=1))
        return 0
    rows = load(a.list)
    version = a.prompt or V.PROMPT_VERSION
    V.prompt(version)   # the file must exist before anything is sent
    est_all = sum(V.estimate_usd(min(r.get("length_s") or V.max_seconds(), V.max_seconds())) for r in rows)
    print(f"{len(rows)} questions, prompt {version}, model {V.model()}, worst case ${est_all:.3f}")
    if a.dry:
        return 0
    for need in ("GEMINI_API_KEY", "MVP_LEDGER_HOME", "MVP_TOTAL_CAP_USD"):
        if not os.environ.get(need):
            print(f"{need} is not set")
            return 2
    res = []
    for r in rows:
        cap = V.max_seconds()
        clip = cap if (not r.get("length_s") or r["length_s"] > cap) else None
        secs = min(r.get("length_s") or cap, cap)
        est = V.estimate_usd(secs)
        if llm.spent_total([]) + est + config.TOTAL_CAP_MARGIN_USD >= config.TOTAL_CAP_USD:
            print("stopped: the total cap")
            break
        req = V.request_for(r["question"], r["video_id"], clip, version=version)
        t0 = time.time()
        err, out, cost = None, None, 0.0
        try:
            out, cost, _raw = V.call_model(V.model(), req, int(secs * (V.VIDEO_TPS + V.AUDIO_TPS) + V.TEXT_TOKENS),
                                           "eval:videoask", version=version)
        except Exception as e:  # noqa: BLE001 - counted, the others still run
            err = type(e).__name__ + (f" {e.code}" if hasattr(e, "code") else "")
        row = dict(r, prompt=version, raw=out, cost=cost, seconds=round(time.time() - t0, 2), error=err)
        kept, dropped, _ = checked(row, out)
        row.update(kept=kept, dropped=dropped)
        res.append(row)
        print(r["id"], "covers" if r["covers"] else "not", len(kept), "points", err or "", f"${cost:.4f}")
    with open(a.out, "w", encoding="utf-8") as f:
        for r in res:
            f.write(json.dumps(r) + "\n")
    print(json.dumps(score(res), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
