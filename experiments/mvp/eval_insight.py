"""PROTOTYPE ONLY - round 12, builder W (DESIGN.md section 19.W): scores the history writer (insight.py, prompt
insight_v1) on the made-up fact sheets of eval/insight_cases.json. Every title, channel and theme there is invented.

Modes:
- before: today's code reply for the same facts, in today's words (history.py's templates, written out here from the
  sheet: the reply the founder graded, emulated, because a made-up sheet has no library behind it);
- fake:   each case's true form plus its planted false sentences, through the code check: every planted sentence
          must be dropped, every true one kept (no model call);
- live:   one model call per sheet (llm.chat_json, so every call lands in the ledger), the code check, the layout.

Scores per case: `answers` (every answer_has string in the answer and one string of each has_any group anywhere),
`violations` (a `not` string present), observations kept and dropped, planted sentences caught (fake), characters,
cost and seconds. Run from experiments/:  python3 -m mvp.eval_insight --mode live [--cases id,id] [--out file]
"""
import argparse
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from mvp import insight as I  # noqa: E402

CASES = os.path.join(HERE, "eval", "insight_cases.json")


def load(ids=None):
    with open(CASES, encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    return [c for c in cases if not ids or c["id"] in ids]


# ---------------------------------------------------------------- today's code reply, from the sheet's facts
def _fmt(n):
    return f"{int(n):,}"


def before_reply(sheet):
    """Today's code reply in today's words (history.py, 18.H and 18.LA), for the sheet's facts: a count, a top 5 by
    count, the export-end and friends paragraph when the window passes the export's end. Answer first line."""
    k = sheet.get("kind")
    w = (sheet.get("window") or {}).get("words") or "In all your history I can see,"
    W = w.split(",")[0].split(" (")[0].strip() if "export" in w else w.rstrip(",")
    tot = sheet.get("totals") or {}
    es = sheet.get("lang") == "es"
    tail = []
    if (sheet.get("window") or {}).get("clipped"):
        tail = ["Your YouTube export ends on 30 October 2026, so I can't see after that.",
                "For newer history, send me a new export (ask \"how do I send you a new export?\" for the steps).",
                "Posts from friends are not counted."]
    if es:
        tail = ["Tu exportación de YouTube termina el 30 de octubre de 2026, así que no veo nada después."] if tail else []
    lines = []
    if k in ("top", "channels"):
        chans = sheet.get("channels") or [c for t in sheet.get("themes") or [] for c in t.get("channels") or []]
        chans = sorted(chans, key=lambda c: -c.get("items", 0))[:5]
        lines.append(f"{W} you watched {_fmt(tot.get('items', 0))} videos. Most from:" if not es else
                     f"{W} viste {_fmt(tot.get('items', 0)).replace(',', '.')} videos. Más de:")
        lines += [f"{i}. {c['name']}: {_fmt(c['items'])}" for i, c in enumerate(chans, 1)]
    elif k == "count":
        t = (sheet.get("topics") or [{}])[0]
        lines.append(f"{W} you watched {_fmt(t.get('items', 0))} videos that mention \"{t.get('name')}\" (of "
                     f"{_fmt(tot.get('items', 0))} you watched then).")
    elif k in ("first", "last"):
        items = sheet.get("items") or []
        topic = (sheet.get("filters") or {}).get("topic") or ""
        if items:
            d = I._as_date(items[0].get("at"))
            lines.append(f"The {'first' if k == 'first' else 'last'} video you watched that mentions \"{topic}\" was on "
                         f"{d.day} {I.MONTHS[d.month - 1].capitalize()} {d.year}:")
            lines += [I._item_line(i, it, "en") for i, it in enumerate(items[:3], 1)]
            lines.append(f"({_fmt(tot.get('items', len(items)))} in all.)")
        tail = ["Your YouTube history here runs from 19 September 2015 to 30 October 2026."]
    elif k == "day":
        lines.append(f"{W} you watched {_fmt(tot.get('items', 0))} videos:")
        lines += [I._item_line(i, it, "en") for i, it in enumerate((sheet.get("items") or [])[:8], 1)]
        rest = tot.get("items", 0) - len(sheet.get("items") or [])
        if rest > 0:
            lines.append(f"And {rest} more (say \"more\" to see them).")
    elif k == "changed":
        ps = sheet.get("periods") or []
        lines.append(f"Videos you watched, by {'month' if any(c.isalpha() for c in str(ps[0]['label'])) else 'year'}:"
                     if ps else "Videos you watched:")
        lines.append(", ".join(f"{p['label']}: {_fmt(p['items'])}" for p in ps) + ".")
        if ps:
            top = max(ps, key=lambda p: p["items"])
            lines.append(f"The most: {top['label']}, with {_fmt(top['items'])}.")
        lines.append(f"{_fmt(sum(p['items'] for p in ps))} in all.")
    elif k == "compare_windows":
        prev = sheet.get("previous") or {}
        a, b = tot.get("items", 0), prev.get("items", 0)
        la = (sheet.get("window") or {}).get("label") or W
        lb = prev.get("label") or prev.get("words") or ""
        hi, lo = ((la, a), (lb, b)) if a >= b else ((lb, b), (la, a))
        lines.append(f"More in {hi[0]}: {_fmt(hi[1])} videos, against {_fmt(lo[1])} in {lo[0]} "
                     f"({_fmt(abs(a - b))} more).")
    elif k == "compare_topics":
        ts = sheet.get("topics") or []
        n = sum(t.get("items", 0) for t in ts)
        words = " or ".join(f"\"{t['name']}\"" for t in ts)
        lines.append(f"In all your history I can see, you watched {_fmt(n)} videos that mention {words}.")
    text = "\n".join(lines)
    return text + ("\n\n" + " ".join(tail) if tail else "")


# ---------------------------------------------------------------- scoring
def score(case, answer, full):
    e = case["expect"]
    low_a, low = (answer or "").lower(), (full or "").lower()
    has = all(x.lower() in low_a for x in e.get("answer_has") or [])
    any_ok = all(any(x.lower() in low for x in grp) for grp in e.get("has_any") or [])
    own = "\n".join(x for x in low.split("\n") if not re.match(r"^\d+\. |^\[card\]", x))   # not the items listed
    viol = [x for x in e.get("not") or [] if x.lower() in own]
    run = re.search(r"\b(?:[A-Z][a-z]{2} )?\d{4}: [\d,.]+, (?:[A-Z][a-z]{2} )?\d{4}: [\d,.]+", full or "")
    return {"answers": bool(has and any_ok), "answer_keys": has, "context_keys": any_ok, "violations": viol,
            "run_of_counts": bool(run), "chars": len(full or "")}


def text_of(parts):
    return "\n".join(p.get("text") or ("[card] " + str(p.get("title"))) for p in parts)


def run(mode, cases, out=None):
    rows = []
    for c in cases:
        s = c["sheet"]
        t0 = time.time()
        row = {"id": c["id"], "kind": s.get("kind"), "lang": s.get("lang") or "en", "cost": 0.0}
        if mode == "before":
            full = before_reply(s)
            ans = full.split("\n")[0]
            row.update(score(c, ans, full), kept=0, dropped=0)
        else:
            if mode == "fake":
                raw = dict(c["fake"])
                raw["observations"] = list(raw["observations"]) + list(c["plants"])
            else:
                try:
                    raw, cost = I.call(s)
                except Exception as e:  # noqa: BLE001 - counted as a failed case (the code reply would go out)
                    raw, cost = {}, 0.0
                    row["error"] = type(e).__name__
                row["cost"] = round(cost, 6)
            _, cv = I.chart(s)
            form = I.check(raw, s, chart_vals=cv)
            ok = bool(form["answer"]) and len(form["observations"]) >= I.OBS_MIN
            if ok:
                parts = I.layout(form, s, [{"type": "link", "title": it.get("title"), "url": "https://example.com/v"}
                                           for it in (s.get("items") or [])] if s.get("kind") in I.ITEM_KINDS else [])
                full = text_of(parts)
                ans = I.window_lead(form["answer"], s)
            else:
                full = before_reply(s)   # the fallback: today's code reply
                ans = full.split("\n")[0]
            row.update(score(c, ans, full), used=ok, kept=len(form["observations"]),
                       dropped=len([d for d in form["dropped"] if d[0] == "observation"]),
                       dropped_why=[d[1] for d in form["dropped"]], so_what=bool(form["so_what"]),
                       offers=form["offers"])
            if mode == "fake":
                facts = I.Facts(I.shown(s))
                caught = [I.check_sentence(p["text"], facts, uses=p["uses"], chart_vals=cv) is not None
                          for p in c["plants"]]
                true_kept = sum(1 for o in c["fake"]["observations"] if o["text"] in form["observations"])
                row.update(planted=len(caught), caught=sum(caught), true_obs=len(c["fake"]["observations"]),
                           true_kept=true_kept)
            row["raw"] = raw if mode == "live" else None
        row["seconds"] = round(time.time() - t0, 2)
        row["text"] = full
        rows.append(row)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return rows


def summary(rows, mode):
    n = len(rows)
    s = {"mode": mode, "cases": n, "answers": sum(r["answers"] for r in rows),
         "violations": sum(1 for r in rows if r["violations"]), "run_of_counts": sum(r["run_of_counts"] for r in rows),
         "chars_mean": round(sum(r["chars"] for r in rows) / max(n, 1)),
         "cost": round(sum(r["cost"] for r in rows), 4), "seconds_max": max((r["seconds"] for r in rows), default=0)}
    if mode != "before":
        s.update(used=sum(1 for r in rows if r.get("used")), kept=sum(r["kept"] for r in rows),
                 dropped=sum(r["dropped"] for r in rows), so_what=sum(1 for r in rows if r.get("so_what")))
    if mode == "fake":
        s.update(planted=sum(r["planted"] for r in rows), caught=sum(r["caught"] for r in rows),
                 true_obs=sum(r["true_obs"] for r in rows), true_kept=sum(r["true_kept"] for r in rows))
    return s


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("before", "fake", "live"), default="fake")
    ap.add_argument("--cases", default="")
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    ids = [x for x in a.cases.split(",") if x]
    t0 = time.time()
    rows = run(a.mode, load(ids), a.out or None)
    s = summary(rows, a.mode)
    wall = time.time() - t0
    s.update(wall_seconds=round(wall, 2), items_per_second=round(len(rows) / wall, 2) if wall else None)
    print(json.dumps(s))
    return rows, s


if __name__ == "__main__":
    main()
