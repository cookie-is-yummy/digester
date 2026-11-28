"""PROTOTYPE ONLY - round 3 A1 / R1: tier-1 text pass (te-v1c prompt, gemini-3.1-flash-lite, Batch API).

The prompt, schema, generation config and validation are round 1's te-v1c unchanged (methods/enrich_batch.py);
only the item set and the text it reads change:
  --view allowed : Takeout title, channel and the user's playlist names, for gated items with a Takeout title
                   (gate: processing depth light/full or watched >= 3 times) + every more-like-this example
                   (outside-library examples from their given 'Channel - Title').
                   -> $DIGESTER_DATA/enrich/te-v1c_allowed_<model>.jsonl
  --view api     : RESEARCH-ONLY reference. API title + description (URLs and chapter lines removed, 600 chars)
                   + chapter titles as the caption, API tags as hashtags, API channel, the same playlist names,
                   for gated items with an API row (same gate) + the in-library example.
                   -> $DIGESTER_DATA/enrich/ref_te-v1c_api_<model>.jsonl
Resumable like enrich_batch.py (jobs file per view). Logs each job with ai.log_batch at batch prices.
Prints aggregate numbers only.

usage: python yt_enrich_text.py --view allowed [--limit 50] [--chunk 3000]
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
import ai
import enrich_batch as EB
import enrich_items as E
import yt_lib as Y
from corpus import DATA

MODEL = "gemini-3.1-flash-lite"


def out_path(view):
    return os.path.join(DATA, "enrich", ("te-v1c_allowed" if view == "allowed" else "ref_te-v1c_api") + f"_{MODEL}.jsonl")


def pseudo(caption, channel, collections, tags=()):
    return {"caption": caption, "platform_data": {"media_kind": "video", "owner_handle": "", "owner_name": channel,
                                                  "collections": collections, "hashtags": list(tags)}}


def build_set(view):
    D = Y.YT()
    g = D.gated()
    ex_in = {c for q in Y.load_queries() for c in q.get("examples") or [] if c in D.pos}
    items = {}
    if view == "allowed":
        for n in range(len(D.items)):
            if (g[n] or D.codes[n] in ex_in) and D.title[n]:
                it = D.items[n]
                items[D.codes[n]] = pseudo(D.title[n], D.channel[n], it["platform_data"].get("collections") or [])
        for c, t in Y.outside_examples().items():
            ti, _, ch = t.rpartition(" by ")
            items[c] = pseudo(ti or t, ch if ti else "", [])
    else:
        api = Y.load_api_rows()
        for n in range(len(D.items)):
            r = api.get(D.codes[n])
            if (g[n] or D.codes[n] in ex_in) and r and r.get("ok"):
                desc = Y.clean_description(r.get("caption"), r.get("chapters"))[:600]
                cap = (r.get("title") or "") + ". " + desc
                if r.get("chapters"):
                    cap += " chapters: " + " · ".join(c["title"] for c in r["chapters"])
                items[D.codes[n]] = pseudo(cap, (r.get("creator") or {}).get("name") or D.channel[n],
                                           D.items[n]["platform_data"].get("collections") or [], r.get("hashtags") or [])
    return items, int(g.sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--view", choices=["allowed", "api"], required=True)
    ap.add_argument("--chunk", type=int, default=3000)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--max-total", type=float, default=7.25, help="gemini total (USD) a submit may not pass")
    ap.add_argument("--count-only", action="store_true")
    ap.add_argument("--est-out", type=int, default=EB.MAX_OUT, help="output tokens per item for the submit check "
                    "(A1 measured 130)")
    ap.add_argument("--poll", type=int, default=30)
    a = ap.parse_args()
    pr = ai.prices()[MODEL]
    out = out_path(a.view)
    state_f = out.replace(".jsonl", "_jobs.json")
    state = json.load(open(state_f)) if os.path.exists(state_f) else {"jobs": []}
    items, n_gated = build_set(a.view)
    chars = [len(EB.SYSTEM) + len(E.block(it)) for it in items.values()]
    est_all = sum(chars) / 3.5 / 1e6 * pr["batch_input_per_m"] + len(items) * 150 / 1e6 * pr["batch_output_per_m"]
    print(f"view {a.view}: gated {n_gated}, set {len(items)} (with text), mean block {sum(chars) / len(chars):.0f} "
          f"chars, est ${est_all:.2f} (150 out tok/item)", flush=True)
    if a.count_only:
        return
    done = {json.loads(l)["code"] for l in open(out)} if os.path.exists(out) else set()
    pending = {c for j in state["jobs"] if not j.get("collected") for c in j["codes"]}
    todo = [c for c in items if c not in done and c not in pending]
    if a.limit:
        todo = todo[:a.limit]
    for i in range(0, len(todo), a.chunk):
        ch = todo[i:i + a.chunk]
        est = sum(len(EB.SYSTEM) + len(E.block(items[c])) for c in ch) / 3.5 / 1e6 * pr["batch_input_per_m"] + \
            len(ch) * a.est_out / 1e6 * pr["batch_output_per_m"]
        if ai.spent("gemini") + est + sum(j["est"] for j in state["jobs"] if not j.get("collected")) > a.max_total:
            print(f"stop: chunk est ${est:.2f} would pass ${a.max_total}", flush=True)
            break
        reqs = [{"request": EB.request_for(items[c]), "metadata": {"key": c}} for c in ch]
        try:
            name = ai.gemini_batch_create(MODEL, reqs, est, display_name=f"yt-te-{a.view}-{len(state['jobs'])}")
        except Exception as e:  # noqa: BLE001 - 429: too many enqueued batch tokens; poll first, re-run later
            print(f"submit refused ({str(e)[:60]}); polling pending jobs, re-run to submit the rest", flush=True)
            break
        state["jobs"].append({"name": name, "codes": ch, "est": round(est, 4), "submitted": time.time()})
        json.dump(state, open(state_f, "w"), indent=1)
        print(f"submitted {name}: {len(ch)} requests, worst-case est ${est:.3f}", flush=True)

    t0 = time.time()
    while any(not j.get("collected") for j in state["jobs"]):
        for j in [j for j in state["jobs"] if not j.get("collected")]:
            try:
                op = ai.gemini_batch_get(j["name"])
            except Exception as e:  # noqa: BLE001
                print(f"  poll error {str(e)[:100]}", flush=True)
                continue
            st = op.get("metadata", {}).get("state", "?")
            j["state"] = st
            if not op.get("done"):
                continue
            wall = time.time() - j["submitted"]
            if st not in ("JOB_STATE_SUCCEEDED", "BATCH_STATE_SUCCEEDED"):
                print(f"  {j['name']} ended {st}", flush=True)
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
                             "view": a.view, "seconds": round(wall, 1), "batch": j["name"],
                             "input_hash": hashlib.sha256(E.block(items[c]).encode()).hexdigest()[:16]})
                seen.add(c)
            for c in j["codes"]:
                if c not in seen:
                    rows.append({"code": c, "ok": False, "err": "no response in batch", "cost_usd": 0,
                                 "in_tokens": 0, "out_tokens": 0, "view": a.view, "batch": j["name"]})
            cost = tin_all / 1e6 * pr["batch_input_per_m"] + tout_all / 1e6 * pr["batch_output_per_m"]
            ai.log_batch("gemini", MODEL, f"yt_enrich_{a.view}_batch", len(resp), tin_all, tout_all, cost,
                         round(wall, 1), prompt_version=EB.PV)
            with open(out, "a") as fo:
                fo.writelines(json.dumps(r) + "\n" for r in rows)
            j.update({"collected": True, "wall_s": round(wall, 1), "n": len(rows), "n_ok": sum(r["ok"] for r in rows),
                      "cost_usd": round(cost, 5), "in_tokens": tin_all, "out_tokens": tout_all})
            print(f"  collected {j['name']}: {len(rows)} rows ok {j['n_ok']}, in {tin_all} out {tout_all}, "
                  f"${cost:.4f}, wall {wall:.0f}s", flush=True)
        json.dump(state, open(state_f, "w"), indent=1)
        if any(not j.get("collected") for j in state["jobs"]):
            print(f"  waiting {[j.get('state') for j in state['jobs'] if not j.get('collected')]} "
                  f"{time.time() - t0:.0f}s", flush=True)
            time.sleep(a.poll)
    print(f"done; gemini total ${ai.spent('gemini'):.4f}", flush=True)


if __name__ == "__main__":
    main()
