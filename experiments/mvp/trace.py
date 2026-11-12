"""PROTOTYPE ONLY - what happened to a message. Answers "what did the bot do with the text I sent at 7:02?"

    python -m mvp.trace                  # the last 15 messages received, all people
    python -m mvp.trace 4567 --last 30   # one person, by the end of their number or email
    python -m mvp.trace --web            # the test page's store instead of the real one
    python -m mvp.trace --sends          # timed sends instead of messages received

Prints times, statuses, intents, counts and error types only: never message text, and only the last 4 characters of a
handle. Run from experiments/.
"""
import argparse
import os
import sys

from . import config
from .store import Store


def tail(handle):
    return "…" + handle[-4:] if handle else "?"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("who", nargs="?", default="", help="the end of a handle; empty for everyone")
    ap.add_argument("--last", type=int, default=15)
    ap.add_argument("--web", action="store_true", help="read the test page's store")
    ap.add_argument("--sends", action="store_true", help="show timed sends")
    a = ap.parse_args()
    path = os.path.join(config.HOME, "webtest.sqlite") if a.web else config.DB
    if not os.path.exists(path):
        raise SystemExit(f"no store at {path}")
    store = Store(path)
    like = f"%{a.who}"
    if a.sends:
        rows = store.q("SELECT r.at, r.handle, r.rule_id, r.status, r.n_candidates, r.n_picks, r.n_dropped, r.cost_usd, "
                       "r.seconds, r.error FROM runs r WHERE r.kind='scheduled' AND r.handle LIKE ? ORDER BY r.id DESC "
                       "LIMIT ?", (like, a.last))
        print("time (UTC)            who    rule  status        candidates picks removed cost    secs  error")
        for r in reversed(rows):
            print(f"{r['at'] or '':<21} {tail(r['handle']):<6} {r['rule_id'] or '':<5} {r['status'] or '':<13} "
                  f"{r['n_candidates'] or 0:<10} {r['n_picks'] or 0:<5} {r['n_dropped'] or 0:<7} "
                  f"{(r['cost_usd'] or 0):<7.4f} {(r['seconds'] or 0):<5} {r['error'] or ''}")
        return
    rows = store.q("SELECT i.received_at, i.channel, i.handle, i.status, i.intent, i.seconds, i.error, i.reply_ref, "
                   "i.tapback, r.kind, r.status AS run_status, r.n_candidates, r.n_picks, r.n_dropped, r.cost_usd "
                   "FROM inbound i LEFT JOIN runs r ON r.id = i.run_id WHERE i.handle LIKE ? ORDER BY i.id DESC LIMIT ?",
                   (like, a.last))
    if not rows:
        print("no messages recorded", file=sys.stderr)
        return
    print("received (UTC)        channel   who    status   intent        secs  replied  run (kind status candidates>picks, removed, cost)")
    for r in reversed(rows):
        run = ""
        if r["kind"]:
            run = (f"{r['kind']} {r['run_status']} {r['n_candidates'] or 0}>{r['n_picks'] or 0}, "
                   f"{r['n_dropped'] or 0} removed, ${(r['cost_usd'] or 0):.4f}")
        intent = r["intent"] or ("tapback" if r["tapback"] else "")
        print(f"{r['received_at'] or '':<21} {r['channel'] or '':<9} {tail(r['handle']):<6} {r['status'] or '':<8} "
              f"{intent:<13} {(r['seconds'] or 0):<5} {'yes' if r['reply_ref'] else 'no':<8} {run}"
              + (f"  ERROR {r['error']}" if r["error"] else ""))


if __name__ == "__main__":
    main()
