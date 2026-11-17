"""PROTOTYPE ONLY - the live eval of draft_v1 (round 9, slice A, A6; DESIGN.md section 16.A).

Runs every synthetic case of evalset/drafts_dev.jsonl through the same call and the same checks the bot uses
(drafts.model_write: one call, one retry when a check fails, else the code-built words), and counts: forms that
passed the checks, passed on the first try, fell back to code, and the case's own must / must-not words. Writes each
case's draft to --out (a folder outside git) so a person can read whether it says what the brief asked. Stops before a
call once --max-usd has been spent in this run. Every call is logged to the MVP ledger with its cost (llm.py).

    MVP_TOTAL_CAP_USD=20 MVP_LEDGER_HOME=... MVP_HOME=... python3 -m mvp.eval_drafts --out DIR [--max-usd 0.6]
"""
import argparse
import json
import os
import re
import sys

from . import llm
from .drafts import model_write

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = os.path.join(HERE, "evalset", "drafts_dev.jsonl")


def load(path=CASES):
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def parts_of(case):
    """The draft parts the bot would hold for this brief (a name in "to" is a greeting name, a word is a role)."""
    to = case.get("to") or ""
    is_name = bool(to) and to[:1].isupper()
    return {"text": case["message"], "greet_name": to if is_name else None,
            "to_word": None if is_name else (to or None), "post": case.get("post"), "request": None}


def word_checks(case, form):
    text = "\n".join(str(form.get(k) or "") for k in ("subject", "greeting", "body", "closing")) if form else ""
    missing = [w for w in case.get("must") or [] if not re.search(re.escape(w), text, re.I)]
    hits = [w for w in case.get("must_not") or [] if re.search(w, text, re.I)]
    return missing, hits


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-usd", type=float, default=0.60)
    ap.add_argument("--only", default=None)
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    spent = 0.0
    real = llm.chat_json

    def counted(*args, **kw):
        nonlocal spent
        if spent >= a.max_usd:
            raise RuntimeError("eval budget used up")
        out, cost = real(*args, **kw)
        spent += cost or 0.0
        return out, cost
    llm.chat_json = counted
    n = {"cases": 0, "passed": 0, "first_try": 0, "fell_back": 0, "must_missing": 0, "must_not_hits": 0}
    rows = []
    for case in load():
        if a.only and case["id"] != a.only:
            continue
        n["cases"] += 1
        form, attempts, first = model_write(parts_of(case), case.get("sign_as") or "", "eval-drafts",
                                            change=case.get("change"), current=case.get("current"))
        missing, hits = word_checks(case, form)
        n["passed"] += bool(form)
        n["first_try"] += bool(form) and not first
        n["fell_back"] += not form
        n["must_missing"] += bool(missing)
        n["must_not_hits"] += bool(hits)
        rows.append({"id": case["id"], "tags": case["tags"], "attempts": attempts, "first_problems": first,
                     "form": form, "missing": missing, "must_not_hits": hits})
    with open(os.path.join(a.out, "drafts_eval.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    n["spent_usd"] = round(spent, 4)
    print(json.dumps(n))
    return 0


if __name__ == "__main__":
    sys.exit(main())


