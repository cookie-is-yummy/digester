"""PROTOTYPE ONLY - experiment 9b: tier-1 enrichment of the remaining corpus through the Gemini Batch API.

Same prompt (te-v1c = te-v1 + compact-JSON line), model, generation config (thinkingBudget 0, strict
responseJsonSchema, max output 450) and post-validation as methods/enrich_items.py; only the transport differs
(batchGenerateContent with inline requests, half price). Rows are appended to the same output file
$DIGESTER_DATA/enrich/te-v1c_<model>.jsonl in the same row format (plus "batch": job name), so
e9_enrich_search.py and enrich_items.py --retry-failed work unchanged.

Privacy: the item set is enrich_items.select("all"), which removes friends (owner_relation == "mutual") before
anything else; only the te-v1 delimited data block is sent. Every job is budget-checked in lib/ai.py
(gemini_batch_create) and its real usage logged with ai.log_batch at batch prices.

Resumable: submitted jobs are kept in $DIGESTER_DATA/enrich/batch_jobs_<pv>_<model>.json; re-running polls
pending jobs first and never resubmits codes that are in a pending job or already in the output file.

usage:
  python experiments/methods/enrich_batch.py --limit 100            (pilot: one small job)
  python experiments/methods/enrich_batch.py --chunk 3000 [--max-jobs 6]
"""
import argparse
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
import ai  # noqa: E402
import enrich_items as E  # noqa: E402
from corpus import DATA, code_of  # noqa: E402

PV = "te-v1c"
SYSTEM = E.SYSTEM + E.COMPACT
MAX_OUT = 450


def request_for(it):
    gc = {"responseMimeType": "application/json", "maxOutputTokens": MAX_OUT,
          "responseJsonSchema": E.item_schema(1), "thinkingConfig": {"thinkingBudget": 0}}
    return {"system_instruction": {"parts": [{"text": SYSTEM}]},
            "contents": [{"role": "user", "parts": [{"text": E.block(it)}]}],
            "generationConfig": gc}


def parse(resp, model, pr):
    """One inlined response -> (fields, ok, dropped, err, tin, tout)."""
    if "error" in resp:
        return {}, False, 0, ("error: " + json.dumps(resp["error"])[:280]), 0, 0, None
    r = resp.get("response", {})
    u = r.get("usageMetadata", {})
    tin = u.get("promptTokenCount", 0)
    tout = u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)
    try:
        cand = r["candidates"][0]
        text = "".join(p.get("text", "") for p in cand["content"]["parts"])
        o = json.loads(text)
    except Exception as e:  # noqa: BLE001 - truncated / blocked / missing candidate
        fr = (r.get("candidates") or [{}])[0].get("finishReason", "") if r.get("candidates") else "no candidate"
        return {}, False, 0, f"parse: {fr} {type(e).__name__}"[:300], tin, tout, None
    f, ok, dropped = E.validate(o)
    return f, ok, dropped, None if ok else "invalid", tin, tout, o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemini-3.1-flash-lite")
    ap.add_argument("--chunk", type=int, default=3000)
    ap.add_argument("--limit", type=int, default=None, help="only this many new items (pilot)")
    ap.add_argument("--max-jobs", type=int, default=6, help="jobs submitted per invocation")
    ap.add_argument("--poll", type=int, default=30)
    a = ap.parse_args()
    pr = ai.prices()[a.model]
    out = os.path.join(DATA, "enrich", f"{PV}_{a.model}.jsonl")
    state_f = os.path.join(DATA, "enrich", f"batch_jobs_{PV}_{a.model}.json")
    state = json.load(open(state_f)) if os.path.exists(state_f) else {"jobs": []}

    def save():
        json.dump(state, open(state_f, "w"), indent=1)

    items = E.load_items()
    by_code = {code_of(it): it for it in items}
    codes, excluded = E.select("all", items)
    done = set()
    if os.path.exists(out):
        for line in open(out):
            done.add(json.loads(line)["code"])
    pending = {c for j in state["jobs"] if not j.get("collected") for c in j["codes"]}
    todo = [c for c in codes if c not in done and c not in pending]
    if a.limit:
        todo = todo[:a.limit]
    print(f"all: {len(codes)} non-friend items, friends excluded {excluded}, already in output {len(done)}, "
          f"in pending jobs {len(pending)}, to submit {len(todo)}", flush=True)

    t0 = time.time()
    # ---- submit ----
    chunks = [todo[i:i + a.chunk] for i in range(0, len(todo), a.chunk)][:a.max_jobs]
    for ch in chunks:
        if ai.budget("gemini") - ai.spent("gemini") < 1.0:
            print("stop: less than $1 of the gemini cap left", flush=True)
            break
        reqs = [{"request": request_for(by_code[c]), "metadata": {"key": c}} for c in ch]
        chars = sum(len(SYSTEM) + len(E.block(by_code[c])) for c in ch)
        est = chars / 3.5 / 1e6 * pr["batch_input_per_m"] + len(ch) * MAX_OUT / 1e6 * pr["batch_output_per_m"]
        # keep $1 of the cap in reserve (stop rule) on top of the worst-case estimate
        if ai.spent("gemini") + est + sum(j["est"] for j in state["jobs"] if not j.get("collected")) > \
                ai.budget("gemini") - 1.0:
            print(f"stop: submitting {len(ch)} more (est ${est:.2f}) would leave < $1 of the gemini cap", flush=True)
            break
        size = len(json.dumps(reqs))
        name = ai.gemini_batch_create(a.model, reqs, est, display_name=f"enrich-{PV}-{len(state['jobs'])}")
        state["jobs"].append({"name": name, "codes": ch, "est": round(est, 4), "submitted": time.time(),
                              "bytes": size})
        save()
        print(f"submitted {name}: {len(ch)} requests, {size / 1e6:.1f} MB, worst-case est ${est:.3f}", flush=True)

    # ---- poll + collect ----
    n_items, n_ok = 0, 0
    while True:
        open_jobs = [j for j in state["jobs"] if not j.get("collected")]
        if not open_jobs:
            break
        for j in open_jobs:
            try:
                op = ai.gemini_batch_get(j["name"])
            except Exception as e:  # noqa: BLE001 - transient network error, poll again
                print(f"  poll error {j['name']}: {str(e)[:120]}", flush=True)
                continue
            st = op.get("metadata", {}).get("state", "?")
            j["state"] = st
            if st in ("JOB_STATE_PENDING", "JOB_STATE_RUNNING", "BATCH_STATE_PENDING", "BATCH_STATE_RUNNING") \
                    or not op.get("done"):
                continue
            wall = time.time() - j["submitted"]
            if st not in ("JOB_STATE_SUCCEEDED", "BATCH_STATE_SUCCEEDED"):
                print(f"  {j['name']} ended {st}: {json.dumps(op.get('error', {}))[:200]}", flush=True)
                j.update({"collected": True, "wall_s": round(wall, 1), "n_ok": 0})
                save()
                continue
            if len(j["codes"]) <= 200:  # pilot: keep the raw operation for inspection (data/, gitignored)
                json.dump(op, open(os.path.join(DATA, "enrich", "tmp", j["name"].replace("/", "_") + ".json"), "w"))
            resp = op.get("response", {}).get("inlinedResponses", {})
            resp = resp.get("inlinedResponses", resp) if isinstance(resp, dict) else resp
            rows, tin_all, tout_all = [], 0, 0
            seen = set()
            for k, rr in enumerate(resp):
                c = (rr.get("metadata") or {}).get("key") or j["codes"][k]
                f, ok, dropped, err, tin, tout, raw = parse(rr, a.model, pr)
                tin_all += tin
                tout_all += tout
                cost = tin / 1e6 * pr["batch_input_per_m"] + tout / 1e6 * pr["batch_output_per_m"]
                rows.append({"code": c, "ok": ok, **f, "dropped": dropped, "err": err, "raw": raw,
                             "in_tokens": tin, "out_tokens": tout, "cost_usd": cost, "prompt_version": PV,
                             "model": a.model, "seconds": round(wall, 1), "n_in_call": 1, "batch": j["name"],
                             "input_hash": hashlib.sha256(E.block(by_code[c]).encode()).hexdigest()[:16]})
                seen.add(c)
            for c in j["codes"]:  # requests with no response at all
                if c not in seen:
                    rows.append({"code": c, "ok": False, "err": "no response in batch", "in_tokens": 0,
                                 "out_tokens": 0, "cost_usd": 0, "prompt_version": PV, "model": a.model,
                                 "seconds": round(wall, 1), "n_in_call": 1, "batch": j["name"]})
            cost = tin_all / 1e6 * pr["batch_input_per_m"] + tout_all / 1e6 * pr["batch_output_per_m"]
            ai.log_batch("gemini", a.model, "enrich_all_batch", len(resp), tin_all, tout_all, cost,
                         round(wall, 1), prompt_version=PV)
            with open(out, "a") as fo:
                for r in rows:
                    fo.write(json.dumps(r) + "\n")
            ok = sum(r["ok"] for r in rows)
            n_items += len(rows)
            n_ok += ok
            j.update({"collected": True, "wall_s": round(wall, 1), "n": len(rows), "n_ok": ok, "in_tokens": tin_all,
                      "out_tokens": tout_all, "cost_usd": round(cost, 5)})
            save()
            print(f"  collected {j['name']}: {len(rows)} rows, ok {ok}, in {tin_all} out {tout_all} tokens, "
                  f"${cost:.4f}, job wall {wall:.0f}s ({len(rows) / wall:.1f} items/s)", flush=True)
        if any(not j.get("collected") for j in state["jobs"]):
            el = time.time() - t0
            print(f"  waiting: {[j.get('state') for j in state['jobs'] if not j.get('collected')]} {el:.0f}s",
                  flush=True)
            time.sleep(a.poll)
    wall = time.time() - t0
    print(f"done: {n_items} items collected, ok {n_ok}, {n_items / max(wall, 1e-9):.2f} items/s, wall {wall:.1f}s "
          f"(gemini total ${ai.spent('gemini'):.4f})", flush=True)


if __name__ == "__main__":
    main()
