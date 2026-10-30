"""PROTOTYPE ONLY - EVALUATOR SIDE. Reference comparison of our tier-1 text enrichment against Muse's MU.

BRIEF "The Muse export", use 3 ("Reference"). Only the evaluator role may run this: it reads MU text.
Builders get only the aggregate rates written to experiments/results/e9-reference-vs-mu.{md,json}.

Steps:
    sample   draw 200 items (seed 5) from enriched ∩ MU; write the sample + first-pass flags to the
             evaluator work dir (data/eval_work/refcmp/, gitignored). First pass = our coverage from the
             enrichment fields (mechanical) and MU coverage from crude regexes over the MU description.
    show     print items of the sample (ours compact + MU description, truncated) for reading.
    score    merge the evaluator's reading judgements (data/eval_work/refcmp/judged.jsonl) with the first
             pass and print/write aggregate rates only.

Coverage rule for ours: a facet is covered if its field is non-empty and the facet is not listed in `unknown`.
kind: covered if not other/unknown. audio has no field: covered if "audio" is not listed in `unknown`
(the prompt says to list audio as unknown unless a song or sound is named).

usage:
    python experiments/eval/reference_compare.py sample
    python experiments/eval/reference_compare.py show 0 10
    python experiments/eval/reference_compare.py score
"""
import json
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
from common import info_class  # noqa: E402
from corpus import DATA, code_of  # noqa: E402
from muse import load_records, mu_description  # noqa: E402

ENRICH = os.path.join(DATA, "enrich", "te-v1c_gemini-3.1-flash-lite.jsonl")
WORK = os.path.join(DATA, "eval_work", "refcmp")
SAMPLE = os.path.join(WORK, "sample.jsonl")
JUDGED = os.path.join(WORK, "judged.jsonl")
FACETS = ["kind", "topic", "shown", "said", "audio", "place", "people", "vibe"]
OUR_FIELD = {"topic": "topics", "shown": "shown", "said": "said", "place": "place", "people": "people", "vibe": "vibe"}
OUR_UNK = {"topic": "topics"}

# crude first-pass regexes over the MU description (+ the Music: header for audio)
RX = {
    "shown": r"\b(shows?|showing|depicts?|features?|we see|visible|frame|scene|camera|close-up|footage|video (opens|begins|starts)|image|photo|wearing|holding)\b",
    "said": r"\b(says?|said|saying|speaks?|speaking|explains?|narrat\w*|voice-?over|interview\w*|transcript|on-screen text|text overlay|overlay|caption reads|reads ['\"]|subtitles?|text (on screen|appears)|asks?|tells?)\b",
    "audio": r"\b(music|song|track|beat|lyrics|sound|audio|soundtrack|singing|sings|melody|tune)\b",
    "place": r"\b(street|restaurant|beach|kitchen|studio|city|room|outdoor\w*|indoor\w*|park|cafe|shop|store|office|home|house|apartment|bedroom|bathroom|car|gym|stage|mountain\w*|forest|lake|ocean|market|airport|hotel|bar|in [A-Z][a-z]+)\b",
    "people": r"\b(man|woman|men|women|person|people|guy|girl|boy|child|children|kids?|couple|friends?|group|individual|creator|chef|host|he|she)\b",
    "vibe": r"\b(tone|mood|vibe|atmosphere|cozy|playful|nostalgic|humou?r\w*|funny|comedic|lighthearted|serene|calm|energetic|dramatic|wholesome|aesthetic|emotional|heartwarming|satirical|ironic)\b",
}


LISTS = ["topics", "shown", "said", "place", "people", "vibe", "use", "queries"]
AUDIO_OURS = r"\b(music\w*|songs?|track|beat|lyrics|sounds?|audio|soundtrack|sing\w*|melod\w*|tune|asmr|music_dance|remix|album|band|rapper|dj)\b"


def mu_core(mu):
    """MU text read for coverage: the free-text description, or, when that is empty (older format), the
    '## Social Context & Synthesis' / '## Overall Synthesis' section. Searches, Media Pivots and the
    comment-derived Author & Community Breakdown are left out."""
    d = mu_description(mu)
    if d:
        return d
    m = re.search(r"^#+ (Social Context & Synthesis|Overall Synthesis)\s*$(.*?)(?=^#+ |\Z)", mu, re.M | re.S)
    return m.group(2).strip() if m else ""


def mu_rest(mu):
    """Full MU minus the suggested '## Searches' and '## Media Pivots' sections (for an upper-bound regex)."""
    return re.sub(r"^#+ (Searches|Media Pivots)\s*$.*?(?=^#+ |\Z)", "", mu, flags=re.M | re.S)


def has_mu(mu):
    return bool(mu) and not mu.startswith("(no MU text")


def our_cover(e, facet):
    unk = set(e.get("unknown") or [])
    if facet == "kind":
        return e.get("kind") not in ("other", "unknown", None, "") and "kind" not in unk
    if facet == "audio":
        # no audio field: covered only if audio is not listed unknown AND some field names music or a sound
        txt = " ".join([e.get("summary") or "", e.get("kind") or ""] + [x for f in LISTS for x in (e.get(f) or [])])
        return "audio" not in unk and bool(re.search(AUDIO_OURS, txt, re.I))
    f = OUR_FIELD[facet]
    return bool(e.get(f)) and OUR_UNK.get(facet, facet) not in unk


def mu_regex(desc, music):
    out = {"kind": True, "topic": True}
    for f, rx in RX.items():
        out[f] = bool(re.search(rx, desc, re.IGNORECASE if f != "place" else 0)) or (
            f == "place" and bool(re.search(RX["place"], desc.lower())))
    if music:
        out["audio"] = True
    return out


def cmd_sample():
    enr = {}
    for ln in open(ENRICH, encoding="utf-8"):
        r = json.loads(ln)
        if r.get("ok"):
            enr[r["code"]] = r
    recs = load_records()
    items = {}
    for ln in open(os.path.join(DATA, "corpus", "items.jsonl"), encoding="utf-8"):
        it = json.loads(ln)
        items[code_of(it)] = it
    inter = sorted(c for c in enr if c in recs and has_mu(recs[c]["mu"]) and mu_core(recs[c]["mu"]) and c in items)
    n_any = sum(1 for c in enr if c in recs)
    rng = random.Random(5)
    samp = rng.sample(inter, 200)
    os.makedirs(WORK, exist_ok=True)
    with open(SAMPLE, "w", encoding="utf-8") as f:
        for i, c in enumerate(samp):
            e, r = enr[c], recs[c]
            desc = mu_core(r["mu"])
            f.write(json.dumps({
                "i": i, "code": c, "info": info_class(items[c]),
                "ours": {k: e.get(k) for k in ["summary", "kind", "topics", "shown", "said", "place", "people",
                                                 "vibe", "use", "unknown"]},
                "our_cover": {fa: our_cover(e, fa) for fa in FACETS},
                "our_audio_not_unknown": "audio" not in (e.get("unknown") or []),
                "mu_regex": mu_regex(desc, r["music"]),
                "mu_regex_full": mu_regex(mu_rest(r["mu"]), r["music"]),
            }, ensure_ascii=False) + "\n")
    print(json.dumps({"enriched_ok": len(enr), "mu_items": len(recs), "enriched_in_muse_any": n_any, "intersection": len(inter),
                      "sample": len(samp)}))


def load_sample():
    return [json.loads(ln) for ln in open(SAMPLE, encoding="utf-8")]


def cmd_show(a, b, width=1800):
    recs = load_records()
    for s in load_sample()[int(a):int(b)]:
        r = recs[s["code"]]
        o = s["ours"]
        print(f"=== #{s['i']} info={s['info']}")
        print("OURS kind=%s | topics=%s | shown=%s | said=%s | place=%s | people=%s | vibe=%s | unknown=%s" % (
            o["kind"], o["topics"], o["shown"], o["said"], o["place"], o["people"], o["vibe"], o["unknown"]))
        print("OURS summary:", o["summary"])
        print("MUSIC:", bool(r["music"]))
        print("MU:", " ".join(mu_core(r["mu"]).split())[:width])


def rate(n, d):
    return round(n / d, 3) if d else None


def cmd_score():
    samp = load_sample()
    judged = {}
    if os.path.exists(JUDGED):
        for ln in open(JUDGED, encoding="utf-8"):
            if ln.strip():
                j = json.loads(ln)
                judged[j["i"]] = j
    res = {"n_sample": len(samp), "n_read": len(judged), "facets": {}}

    def block(rows, mu_key):
        out = {}
        for fa in FACETS:
            n = len(rows)
            oc = sum(1 for s, j in rows if s["our_cover"][fa])
            mc = sum(1 for s, j in rows if mu_key(s, j)[fa])
            miss = sum(1 for s, j in rows if mu_key(s, j)[fa] and not s["our_cover"][fa])
            both = sum(1 for s, j in rows if mu_key(s, j)[fa] and s["our_cover"][fa])
            d = {"n": n, "ours_cov": rate(oc, n), "mu_cov": rate(mc, n), "miss": rate(miss, n),
                 "miss_given_mu": rate(miss, mc), "both": both}
            if j_rows := [j for s, j in rows if j]:
                conf = sum(1 for s, j in rows if fa in j.get("conflict", []))
                uns = sum(1 for s, j in rows if fa in j.get("unsupported", []))
                d.update({"conflict": rate(conf, n), "conflict_given_both": rate(conf, both),
                          "unsupported": rate(uns, n), "unsupported_given_ours": rate(uns, oc)})
            out[fa] = d
        anymiss = [any(mu_key(s, j)[fa] and not s["our_cover"][fa] for fa in FACETS) for s, j in rows]
        out["_any_miss"] = rate(sum(anymiss), len(rows))
        for g in ("ok", "thin"):
            sub = [m for (s, j), m in zip(rows, anymiss) if (s["info"] == "ok") == (g == "ok")]
            out[f"_any_miss_{g}"] = rate(sum(sub), len(sub))
            out[f"_n_{g}"] = len(sub)
        return out

    all_rows = [(s, None) for s in samp]
    res["regex_all200"] = block(all_rows, lambda s, j: s["mu_regex"])
    res["regex_full_all200"] = block(all_rows, lambda s, j: s["mu_regex_full"])
    read_rows = [(s, judged[s["i"]]) for s in samp if s["i"] in judged]
    if read_rows:
        res["read"] = block(read_rows, lambda s, j: {fa: fa in j["mu_cov"] for fa in FACETS})
        # regex vs reading agreement on MU coverage
        agree = {}
        for fa in FACETS:
            a = sum(1 for s, j in read_rows if s["mu_regex"][fa] == (fa in j["mu_cov"]))
            agree[fa] = rate(a, len(read_rows))
        res["regex_vs_read_agreement"] = agree
        # per-gate facet rates on read rows
        for g in ("ok", "thin"):
            sub = [(s, j) for s, j in read_rows if (s["info"] == "ok") == (g == "ok")]
            if sub:
                res[f"read_{g}"] = block(sub, lambda s, j: {fa: fa in j["mu_cov"] for fa in FACETS})
    res["info_counts"] = {k: sum(1 for s in samp if s["info"] == k) for k in ("ok", "low", "non_english")}
    print(json.dumps(res, indent=1))
    return res


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "sample":
        cmd_sample()
    elif cmd == "show":
        cmd_show(*sys.argv[2:4])
    elif cmd == "score":
        json.dump(cmd_score(), open(os.path.join(WORK, "score.json"), "w"), indent=1)
