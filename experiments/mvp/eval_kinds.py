"""PROTOTYPE ONLY - a small evaluation for requests that ask for a kind of thing (round 9, slice U; DESIGN.md section 12,
"Round 9, slice U").

    python3 -m mvp.eval_kinds mvp/evalset/kinds_dev.jsonl ../data/all --out <folder outside git> [--tag NAME]
                              [--only 1,4] [--profile-from STORE:HANDLE]

Runs each request through the real bot on the real library, each as a fresh test person (one handle per request, so
no state carries over and each has its own daily cap), with a fixed clock. For each request it records counts only:
the named things shown, how many the details model returned and marked "yes", how many code left out and why, the
sources (or picks) the composer judged clear and close, the kind of answer (items, recommend, recommend with named
things after it, closest, none, other), whether the answer says "Nothing I found is a clear fit" beside a clear pick,
and the cost (the ledger rows of that person). It also records a short hash of the candidate list and of each
composer call's verdicts, so two runs can be compared for steady picks.

Writes to the output folder: counts.json (counts only; may be copied into the repo), transcript.md (the replies: they
hold item text, so they stay outside git) and judge.csv (one row per request, for a person to count how many shown
things are truly of the kind asked for). Prints a summary of counts. --profile-from copies one person's profile from a
store into each test person (for a run that should see the person's context); nothing of it is printed.
"""
import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))

CLOSEST_WORDS = ("The closest I have is", "Nothing I found is a clear fit", "These come closest:",
                 "None of what I found", "I couldn't confirm any of these")
NOTHING_CLEAR = "Nothing I found is a clear fit"


def _h(x):
    return hashlib.sha1(json.dumps(x, sort_keys=True, default=str).encode()).hexdigest()[:10]


def answer_kind(text, steps_list, run_kinds, n_picks):
    """The kind of answer a person read, from the reply text and the run's steps (counts and fixed phrases only)."""
    if "I recommend" in text and "Named in other saves" in text:
        return "recommend_named"
    if any((s or {}).get("items") for s in steps_list):
        return "items"
    if "I recommend" in text:
        return "recommend"
    if any(w in text for w in CLOSEST_WORDS):
        return "closest"
    if not n_picks:
        return "none" if any(k in ("ask", "preview") for k in run_kinds) else "other"
    return "other"


def profile_rows(spec):
    """(people columns, profile notes) of one person in a store, read-only."""
    path, _, handle = spec.rpartition(":")
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    row = db.execute("SELECT direction, prefs, profile FROM people WHERE handle=?", (handle,)).fetchone()
    notes = [r["text"] for r in db.execute("SELECT text FROM profile_notes WHERE handle=? ORDER BY id", (handle,))]
    db.close()
    return (dict(row) if row else {}), notes


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("requests")
    ap.add_argument("library")
    ap.add_argument("--out", required=True)
    ap.add_argument("--tag", default="k")
    ap.add_argument("--only", default="")
    ap.add_argument("--timezone", default="America/New_York")
    ap.add_argument("--profile-from", default=None)
    # round 9, slice U2 (point 3): each request several times as the same person, the composer called afresh each time
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--fresh-composer", action="store_true")
    a = ap.parse_args(argv)
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    os.environ["MVP_HOME"] = out
    sys.path.insert(0, os.path.dirname(HERE))
    from mvp import config, llm
    from mvp import executor as ex
    from mvp.channels.console import ConsoleChannel
    from mvp.core import Bot
    from mvp.store import Store
    reqs = [json.loads(line) for line in open(a.requests, encoding="utf-8") if line.strip()]
    if a.only:
        keep = {int(x) for x in a.only.split(",")}
        reqs = [r for r in reqs if r["n"] in keep]
    prof = profile_rows(a.profile_from) if a.profile_from else None

    seen = {"calls": []}   # what each composer call was given and judged (hashes and verdicts only)
    _compose = ex.compose

    def compose(cands, spec, h, **k):
        r, c = _compose(cands, spec, h, **k)
        seen["calls"].append({"handle": h, "cands": _h([x.id for x in cands]), "n_cands": len(cands),
                              "once": bool(k.get("once")), "cached": bool(r.get("cached")),
                              "verdicts": _h([(p["item"].id, p["verdict"]) for p in r.get("picks") or []]),
                              "fits": [p["verdict"] for p in r.get("picks") or []],
                              "clear": _h(sorted(p["item"].id for p in r.get("picks") or [] if p["verdict"] == "clear"))})
        return r, c
    ex.compose = compose
    if a.fresh_composer:
        config.ANSWER_CACHE_HOURS = 0
    from mvp import answers as A
    _choose = A.choose_items

    def choose_items(result, *args, **kw):
        """Round 9, slice U2 (point 3): the posts read, each with the composer's verdict and the judge's "yes" count,
        and the clear sources, as hashes (for steady answers between runs)."""
        out = _choose(result, *args, **kw)
        reads = result.get("items_reads") or []
        seen["sources"].append({
            "reads": [[_h(p["item"].id), p.get("verdict") if not p.get("read_for_items") else "read",
                       sum(1 for x in (p.get("facts") or {}).get("items") or [] if x.get("judge") == "yes")]
                      for p in reads],
            "clear_sources": _h(sorted(p["item"].id for p, _, _ in out or [] if A.is_clear_source(p))),
            "judge_sources": _h(sorted(p["item"].id for p in reads if any(
                x.get("judge") == "yes" for x in (p.get("facts") or {}).get("items") or []))),
            "things": _h(sorted(x["name"] for _, its, _ in out or [] for x in its))})
        return out
    A.choose_items = choose_items
    seen["sources"] = []

    ch = ConsoleChannel(printer=None)
    clock = [datetime.now(timezone.utc).replace(microsecond=0)]
    bot = Bot(ch, store=Store(config.DB), clock=lambda: clock[0])
    bot.max_per_minute = None
    lib = os.path.abspath(a.library)
    bot.pool.get(lib)   # load the engine before timing anything
    rows, transcript = [], []
    reqs = [dict(r, run=i) for r in reqs for i in range(a.repeat)]
    for r in reqs:
        h = f"{a.tag}-{r['n']}"
        bot.store.upsert_person(h, "Tester", lib, a.timezone)
        bot.store.set_consent(h, "eval")
        if prof:
            cols, notes = prof
            bot.store.x("UPDATE people SET direction=?, prefs=?, profile=? WHERE handle=?",
                        (cols.get("direction"), cols.get("prefs"), cols.get("profile"), h))
            for note in notes:
                bot.store.x("INSERT INTO profile_notes(handle,text,at) VALUES(?,?,?)", (h, note, clock[0].isoformat()))
        ref = llm.person_ref(h)
        with open(llm.ai.LEDGER, encoding="utf-8") as f:
            n_ledger = sum(1 for _ in f)
        n0, c0, s0 = len(ch.outbox), len(seen["calls"]), len(seen["sources"])
        run0 = bot.store.one("SELECT COALESCE(MAX(id), 0) m FROM runs")["m"]   # this message's runs only
        t0 = time.time()
        bot.on_message(h, r["text"])
        secs = round(time.time() - t0, 1)
        with open(llm.ai.LEDGER, encoding="utf-8") as f:
            new = [json.loads(line) for i, line in enumerate(f) if i >= n_ledger and line.strip()]
        cost = sum(x.get("cost_usd") or 0 for x in new if x.get("person") == ref)
        by_purpose = Counter()
        for x in new:
            if x.get("person") == ref:
                by_purpose[x.get("purpose")] += x.get("cost_usd") or 0
        replies = [str(t) for _, _, t in ch.outbox[n0:]]
        text = "\n".join(replies)
        runs = bot.store.q("SELECT * FROM runs WHERE handle=? AND id>? ORDER BY id", (h, run0))
        steps = [json.loads(x["steps"] or "{}") for x in runs]
        dropped = Counter()
        for x in runs:
            for k, v in json.loads(x["dropped"] or "{}").items():
                dropped[k] += v
        why = Counter()
        model = Counter()
        for s in steps:
            for k, v in (s.get("items_why") or {}).items():
                why[k] += v
            for k, v in (s.get("items_model") or {}).items():
                model[k] += v
        fits = [f for x in runs for f in json.loads(x["fits"] or "[]")]
        srcs = Counter()
        for s in steps:
            for k, v in (s.get("items_sources") or {}).items():
                srcs[k] += v
        n_picks = sum(x["n_picks"] or 0 for x in runs)
        kind = answer_kind(text, steps, [x["kind"] for x in runs], n_picks)
        lastspec = bot.store.get_state(f"lastspec:{h}") or {}
        content = ((lastspec.get("spec") or {}).get("content") or {})
        rows.append({
            "n": r["n"], "kind_asked": r.get("kind"), "answer": kind, "run_kinds": [x["kind"] for x in runs],
            "errors": sum(1 for x in runs if x["status"] == "error"),
            "shown_things": sum(s.get("items") or 0 for s in steps),
            "model_items": model.get("raw", 0), "model_yes": model.get("yes", 0),
            "dropped_by_check": {k: v for k, v in model.items() if k not in ("raw", "yes")},
            "dropped_as_junk": dict(why), "dropped_not_the_kind": dropped.get("items_not_the_kind", 0),
            "sources_clear": srcs.get("clear", 0), "sources_close": srcs.get("close", 0),
            "picks_clear": fits.count("clear"), "picks_close": fits.count("close"),
            "nothing_clear_beside_clear": NOTHING_CLEAR in text and "clear" in fits,
            "slides_line": ("slides, not its text" in text) or ("video, not its text" in text),
            "items_reads": sum(s.get("items_reads") or 0 for s in steps),
            "details_calls": sum(s.get("extract_calls") or 0 for s in steps),
            "searches": _h(content.get("searches") or []), "goal_words": len((content.get("goal") or "").split()),
            "composer": [{k: v for k, v in c.items() if k != "handle"} for c in seen["calls"][c0:]],
            "run": r.get("run", 0), "sources": seen["sources"][s0:],
            "cost_usd": round(cost, 6), "cost_by_purpose": {k: round(v, 6) for k, v in by_purpose.items()},
            # round 9, slice U2: the stronger model's judgement of each thing (judge.py), counted
            "judge": _judge_counts(steps),
            "seconds": secs})
        transcript.append(f"### {r['n']} ({r.get('kind')})\n>>> {r['text']}\n\n" + "\n---\n".join(replies) + "\n")
        bot.store.clear_pending(h)
    with open(os.path.join(out, "transcript.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(transcript))
    with open(os.path.join(out, "counts.json"), "w", encoding="utf-8") as f:
        json.dump({"prompt_extract": config.PROMPT_EXTRACT, "model": config.MODEL, "rows": rows}, f, indent=1)
    with open(os.path.join(out, "judge.csv"), "w", encoding="utf-8") as f:
        f.write("n,kind_asked,answer,shown_things,truly_of_the_kind\n")
        for x in rows:
            f.write(f"{x['n']},{x['kind_asked']},{x['answer']},{x['shown_things']},\n")
    print(json.dumps(summary(rows), indent=1))
    bot.pool.stop_all()


def _judge_counts(steps_list):
    """The judge's counts over a request's runs: things, yes, no, unsure, cached, calls, errors, seconds."""
    out = Counter()
    for s in steps_list:
        j = (s or {}).get("judge") or {}
        for k in ("things", "yes", "no", "unsure", "cached", "calls"):
            out[k] += j.get(k) or 0
        out["errors"] += 1 if j.get("error") else 0
        out["seconds"] += j.get("seconds") or 0
    out["seconds"] = round(out["seconds"], 2)
    return dict(out)


def summary(rows):
    """Totals over one run (counts only)."""
    why, check = Counter(), Counter()
    for x in rows:
        why.update(x["dropped_as_junk"])
        check.update(x["dropped_by_check"])
    costs = [x["cost_usd"] for x in rows]
    return {"requests": len(rows), "answers": Counter(x["answer"] for x in rows),
            "errors": sum(x["errors"] for x in rows), "shown_things": sum(x["shown_things"] for x in rows),
            "model_items": sum(x["model_items"] for x in rows), "model_yes": sum(x["model_yes"] for x in rows),
            "dropped_by_check": dict(check), "dropped_as_junk": dict(why),
            "dropped_not_the_kind": sum(x["dropped_not_the_kind"] for x in rows),
            "sources_clear": sum(x["sources_clear"] for x in rows), "sources_close": sum(x["sources_close"] for x in rows),
            "nothing_clear_beside_clear": sum(bool(x["nothing_clear_beside_clear"]) for x in rows),
            "cost_usd": round(sum(costs), 4), "cost_per_request": round(sum(costs) / max(1, len(rows)), 5),
            # round 9, slice U2: the judge's calls, verdicts, cost and seconds (rows of an older run hold none)
            "judge": {k: round(sum((x.get("judge") or {}).get(k) or 0 for x in rows), 2)
                      for k in ("things", "yes", "no", "unsure", "cached", "calls", "errors", "seconds")},
            "judge_cost_usd": round(sum((x.get("cost_by_purpose") or {}).get("mvp_judge", 0) for x in rows), 4),
            "seconds_per_request": round(sum(x.get("seconds") or 0 for x in rows) / max(1, len(rows)), 2)}


if __name__ == "__main__":
    main()
