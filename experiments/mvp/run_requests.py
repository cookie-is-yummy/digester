"""PROTOTYPE ONLY - run a set of test requests through the bot on one library, as a fresh test person.

    python -m mvp.run_requests data/mvp/requests.jsonl data/all [--out data/mvp/eval/NAME]

Writes the full conversation (it holds item text) to the output folder under data/, outside git, plus a grading sheet
for a founder. Prints counts only (no request or item text), for results/.
"""
import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("requests")
    ap.add_argument("library")
    ap.add_argument("--out", default=None)
    ap.add_argument("--timezone", default="America/New_York")
    a = ap.parse_args()
    out = os.path.abspath(a.out or os.path.join(os.path.dirname(os.path.abspath(a.requests)), "eval",
                                                datetime.now().strftime("%Y%m%d-%H%M%S")))
    os.makedirs(out, exist_ok=True)
    os.environ["MVP_HOME"] = out
    sys.path.insert(0, os.path.dirname(HERE))
    from mvp.channels.console import ConsoleChannel
    from mvp.core import Bot
    from mvp.store import Store
    from mvp import config
    reqs = [json.loads(l) for l in open(a.requests, encoding="utf-8") if l.strip()]
    follow = [r for r in reqs if r.get("after")]  # a follow-up runs right after the request it follows
    order = []
    for r in [r for r in reqs if not r.get("after")]:
        order.append(r)
        order.extend(f for f in follow if f["after"] == r["n"])
    reqs = order + [f for f in follow if f not in order]
    ch = ConsoleChannel(printer=None)
    clock = [datetime(2026, 11, 13, 17, 0, tzinfo=timezone.utc)]
    bot = Bot(ch, store=Store(config.DB), clock=lambda: clock[0])
    handle = "tester"
    bot.store.upsert_person(handle, "Tester", os.path.abspath(a.library), a.timezone)
    bot.store.set_consent(handle, "eval")
    bot.pool.get(os.path.abspath(a.library))  # load the engine before timing anything
    rows, transcript = [], []
    for r in reqs:
        n0 = len(ch.outbox)
        runs0 = bot.store.one("SELECT COALESCE(MAX(id),0) m FROM runs")["m"]
        t0 = time.time()
        bot.on_message(handle, r["text"])
        secs = time.time() - t0
        replies = [t for _, _, t in ch.outbox[n0:]]
        runs = bot.store.q("SELECT * FROM runs WHERE id>?", (runs0,))
        pending = bot.store.pending(handle)
        kind = runs[-1]["kind"] if runs else ("reply")
        rows.append({"n": r["n"], "type": r.get("type"), "kind": kind, "seconds": round(secs, 1),
                     "picks": sum(x["n_picks"] or 0 for x in runs), "candidates": sum(x["n_candidates"] or 0 for x in runs),
                     "dropped": sum(x["n_dropped"] or 0 for x in runs), "cost": sum(x["cost_usd"] or 0 for x in runs),
                     "error": any(x["status"] == "error" for x in runs), "preview": bool(pending)})
        transcript.append(f"### {r['n']} ({r.get('type')})\n>>> {r['text']}\n\n" + "\n\n".join(replies) + "\n")
        if pending:  # previews are not activated during the run
            bot.store.clear_pending(handle)
    with open(os.path.join(out, "transcript.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(transcript))
    with open(os.path.join(out, "grades.csv"), "w", encoding="utf-8") as f:
        f.write("n,type,grade (send as is / small edit / not sendable),reason\n")
        for r in reqs:
            f.write(f"{r['n']},{r.get('type')},,\n")
    with open(os.path.join(out, "counts.json"), "w") as f:
        json.dump(rows, f, indent=1)
    by_kind = Counter(r["kind"] for r in rows)
    print(json.dumps({"requests": len(rows), "by_kind": by_kind, "errors": sum(r["error"] for r in rows),
                      "with_picks": sum(r["picks"] > 0 for r in rows), "no_pick_answers": sum(r["kind"] in ("ask", "preview", "follow_up") and r["picks"] == 0 for r in rows),
                      "dropped_by_checks": sum(r["dropped"] for r in rows), "cost_usd": round(sum(r["cost"] for r in rows), 4),
                      "seconds_median": sorted(r["seconds"] for r in rows)[len(rows) // 2],
                      "seconds_max": max(r["seconds"] for r in rows), "out": out}, indent=1))
    bot.pool.stop_all()


if __name__ == "__main__":
    main()
