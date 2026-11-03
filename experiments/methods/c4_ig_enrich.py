"""PROTOTYPE ONLY - round 4.1 (Y4.1-TE): rebuild Instagram's te-v1c text pass on the combined data root.

Same prompt (te-v1c), model, generation config and validation as round 1 (methods/enrich_batch.py: request_for,
parse); only the item set changes: Instagram items of $DIGESTER_DATA/corpus/items.jsonl minus friends
(owner_relation == "mutual"; never sent), selected with enrich_items.select("all") exactly as round 1 did.
Only te-v1's delimited data block (kind, creator, collection names, caption, hashtags) is sent.

Output: $DIGESTER_DATA/enrich/te-v1c_ig_<model>.jsonl (round-1 row format). Resumable: jobs in
enrich/te-v1c_ig_<model>_jobs.json; re-running polls pending jobs and never resubmits codes that are pending or
already written. Each job is budget-checked (lib/ai.gemini_batch_create) and logged with ai.log_batch at
batch prices. A submit is refused if Gemini spend + pending estimates + this chunk would pass --max-total.
Prints aggregate numbers only.

usage: python experiments/methods/c4_ig_enrich.py [--chunk 3000] [--max-total 4.75] [--est-out 160]
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
import enrich_batch as EB  # noqa: E402
import enrich_items as E  # noqa: E402
from corpus import DATA, code_of  # noqa: E402

MODEL = "gemini-3.1-flash-lite"
OUT = os.path.join(DATA, "enrich", f"te-v1c_ig_{MODEL}.jsonl")
STATE = OUT.replace(".jsonl", "_jobs.json")


def ig_items():
    return [it for it in E.load_items() if it["platform"] == "instagram"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk", type=int, default=3000)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--max-total", type=float, default=4.75, help="Gemini ledger total a submit may not pass")
    ap.add_argument("--est-out", type=int, default=160, help="output tokens per item for the submit estimate")
    ap.add_argument("--poll", type=int, default=30)
    ap.add_argument("--count-only", action="store_true")
    a = ap.parse_args()
    pr = ai.prices()[MODEL]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    state = json.load(open(STATE)) if os.path.exists(STATE) else {"jobs": []}

    def save():
        json.dump(state, open(STATE, "w"), indent=1)

    items = ig_items()
    by_code = {code_of(it): it for it in items}
    codes, excluded = E.select("all", items)
    chars = sum(len(EB.SYSTEM) + len(E.block(by_code[c])) for c in codes)
    est_all = chars / 3.5 / 1e6 * pr["batch_input_per_m"] + len(codes) * a.est_out / 1e6 * pr["batch_output_per_m"]
    done = {json.loads(l)["code"] for l in open(OUT)} if os.path.exists(OUT) else set()
    pending = {c for j in state["jobs"] if not j.get("collected") for c in j["codes"]}
    todo = [c for c in codes if c not in done and c not in pending]
    if a.limit:
        todo = todo[:a.limit]
    print(f"instagram non-friend items {len(codes)}, friends excluded {excluded}, est all ${est_all:.2f}; "
          f"done {len(done)}, pending {len(pending)}, to submit {len(todo)}; gemini spent ${ai.spent('gemini'):.4f}",
          flush=True)
    if a.count_only:
        return

    for i in range(0, len(todo), a.chunk):
        ch = todo[i:i + a.chunk]
        est = sum(len(EB.SYSTEM) + len(E.block(by_code[c])) for c in ch) / 3.5 / 1e6 * pr["batch_input_per_m"] + \
            len(ch) * a.est_out / 1e6 * pr["batch_output_per_m"]
        if ai.spent("gemini") + est + sum(j["est"] for j in state["jobs"] if not j.get("collected")) > a.max_total:
            print(f"stop: chunk est ${est:.2f} would pass ${a.max_total}", flush=True)
            break
        reqs = [{"request": EB.request_for(by_code[c]), "metadata": {"key": c}} for c in ch]
        try:
            name = ai.gemini_batch_create(MODEL, reqs, est, display_name=f"ig-te-v1c-{len(state['jobs'])}")
        except Exception as e:  # noqa: BLE001 - e.g. 429 too many enqueued tokens: poll, re-run later
            print(f"submit refused ({str(e)[:80]}); polling pending jobs; re-run to submit the rest", flush=True)
            break
        state["jobs"].append({"name": name, "codes": ch, "est": round(est, 4), "submitted": time.time()})
        save()
        print(f"submitted job {len(state['jobs'])}: {len(ch)} requests, est ${est:.3f}", flush=True)

    t0 = time.time()
    while any(not j.get("collected") for j in state["jobs"]):
        for j in [j for j in state["jobs"] if not j.get("collected")]:
            try:
                op = ai.gemini_batch_get(j["name"])
            except Exception as e:  # noqa: BLE001 - transient
                print(f"  poll error {str(e)[:100]}", flush=True)
                continue
            st = op.get("metadata", {}).get("state", "?")
            j["state"] = st
            if not op.get("done"):
                continue
            wall = time.time() - j["submitted"]
            if st not in ("JOB_STATE_SUCCEEDED", "BATCH_STATE_SUCCEEDED"):
                print(f"  job ended {st}", flush=True)
                j.update({"collected": True, "failed": st})
                continue
            resp = op.get("response", {}).get("inlinedResponses", {})
            resp = resp.get("inlinedResponses", resp) if isinstance(resp, dict) else resp
            rows, seen, tin_all, tout_all = [], set(), 0, 0
            for k, rr in enumerate(resp):
                c = (rr.get("metadata") or {}).get("key") or j["codes"][k]
                f, ok, dropped, err, tin, tout, raw = EB.parse(rr, MODEL, pr)
                tin_all += tin
                tout_all += tout
                rows.append({"code": c, "ok": ok, **f, "dropped": dropped, "err": err, "in_tokens": tin,
                             "out_tokens": tout, "cost_usd": tin / 1e6 * pr["batch_input_per_m"] +
                             tout / 1e6 * pr["batch_output_per_m"], "prompt_version": EB.PV, "model": MODEL,
                             "seconds": round(wall, 1), "batch": j["name"],
                             "input_hash": hashlib.sha256(E.block(by_code[c]).encode()).hexdigest()[:16]})
                seen.add(c)
            for c in j["codes"]:
                if c not in seen:
                    rows.append({"code": c, "ok": False, "err": "no response in batch", "cost_usd": 0,
                                 "in_tokens": 0, "out_tokens": 0, "batch": j["name"]})
            cost = tin_all / 1e6 * pr["batch_input_per_m"] + tout_all / 1e6 * pr["batch_output_per_m"]
            ai.log_batch("gemini", MODEL, "ig_enrich_te-v1c_batch", len(resp), tin_all, tout_all, cost,
                         round(wall, 1), prompt_version=EB.PV)
            with open(OUT, "a") as fo:
                fo.writelines(json.dumps(r) + "\n" for r in rows)
            j.update({"collected": True, "wall_s": round(wall, 1), "n": len(rows), "n_ok": sum(r["ok"] for r in rows),
                      "cost_usd": round(cost, 5), "in_tokens": tin_all, "out_tokens": tout_all})
            print(f"  collected: {len(rows)} rows ok {j['n_ok']}, in {tin_all} out {tout_all} tokens, ${cost:.4f}, "
                  f"job wall {wall:.0f}s ({len(rows) / max(wall, 1e-9):.1f} items/s)", flush=True)
        save()
        if any(not j.get("collected") for j in state["jobs"]):
            print(f"  waiting {[j.get('state') for j in state['jobs'] if not j.get('collected')]} "
                  f"{time.time() - t0:.0f}s", flush=True)
            time.sleep(a.poll)
    print(f"done; gemini total ${ai.spent('gemini'):.4f}", flush=True)


if __name__ == "__main__":
    main()
