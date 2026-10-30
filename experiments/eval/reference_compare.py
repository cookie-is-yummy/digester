"""PROTOTYPE ONLY - EVALUATOR SIDE. Reference comparison of our tier-1 text enrichment against Muse's MU.

BRIEF "The Muse export", use 3 ("Reference"). Only the evaluator role may run this: it reads MU text.
Builders get only the aggregate rates written to experiments/results/e9-reference-vs-mu.{md,json}.

The coverage / conflict / unsupported decisions for MU are the evaluator's reading, stored in the gitignored
work dir (data/eval_work/refcmp/judged.jsonl, one row per item: {"i", "mu_cov": [facets],
"conflict": [facets], "unsupported": [facets]}). This script only does the bookkeeping:

    sample       draw 200 items (seed 5) from enriched-ok ∩ MU (MU with real text); write sample.jsonl with
                 our coverage (mechanical, from the enrichment fields) and a crude regex first pass for MU.
    thin_extra   every thin (info_class != ok) item of the intersection outside the sample (numbered from
                 1000), so the gate split has all thin items of the intersection, not 10.
    show A B [extra]   print items A..B (ours compact + MU core text, truncated) for reading.
    score        aggregate rates only -> data/eval_work/refcmp/score.json.

Coverage rule for ours: a facet is covered if its field is non-empty and the facet is not listed in `unknown`.
kind: covered if not other/unknown (and not listed unknown). audio has no field: covered only if "audio" is
not listed unknown AND some field names music or a sound (the prompt lists audio unknown unless a song or
sound is named). A lenient variant ignores `unknown` (any non-empty value counts).

MU core text = the free-text description, or, when that is empty (older format), the Social Context /
Overall Synthesis section. Searches, Media Pivots and the comment-derived Author & Community Breakdown are not
read. Items whose MU is "(no MU text — caption only)" are not MU items.

usage:
    python experiments/eval/reference_compare.py sample
    python experiments/eval/reference_compare.py thin_extra
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
THIN_EXTRA = os.path.join(WORK, "thin_extra.jsonl")
JUDGED = os.path.join(WORK, "judged.jsonl")
FACETS = ["kind", "topic", "shown", "said", "audio", "place", "people", "vibe"]
MEDIA = {"shown", "said", "audio"}
OUR_FIELD = {"topic": "topics", "shown": "shown", "said": "said", "place": "place", "people": "people", "vibe": "vibe"}
OUR_UNK = {"topic": "topics"}
LISTS = ["topics", "shown", "said", "place", "people", "vibe", "use", "queries"]
AUDIO_OURS = r"\b(music\w*|songs?|track|beat|lyrics|sounds?|audio|soundtrack|sing\w*|melod\w*|tune|asmr|music_dance|remix|album|band|rapper|dj)\b"

# crude first-pass regexes over the MU core text (+ the Music: header for audio)
RX = {
    "shown": r"\b(shows?|showing|depicts?|features?|we see|visible|frame|scene|camera|close-up|footage|video (opens|begins|starts)|image|photo|wearing|holding)\b",
    "said": r"\b(says?|said|saying|speaks?|speaking|explains?|narrat\w*|voice-?over|interview\w*|transcript|on-screen text|text overlay|overlay|caption reads|reads ['\"]|subtitles?|text (on screen|appears)|asks?|tells?)\b",
    "audio": r"\b(music|song|track|beat|lyrics|sound|audio|soundtrack|singing|sings|melody|tune)\b",
    "place": r"\b(street|restaurant|beach|kitchen|studio|city|room|outdoors?|indoors?|park|cafe|shop|store|office|home|house|apartment|bedroom|bathroom|car|gym|stage|mountains?|forest|lake|ocean|market|airport|hotel|bar)\b",
    "people": r"\b(man|woman|men|women|person|people|guy|girl|boy|child|children|kids?|couple|friends?|group|individual|creator|chef|host|he|she)\b",
    "vibe": r"\b(tone|mood|vibe|atmosphere|cozy|playful|nostalgic|humou?r\w*|funny|comedic|lighthearted|serene|calm|energetic|dramatic|wholesome|aesthetic|emotional|heartwarming|satirical|ironic)\b",
}


def mu_core(mu):
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


def _audio_named(e):
    txt = " ".join([e.get("summary") or "", e.get("kind") or ""] + [x for f in LISTS for x in (e.get(f) or [])])
    return bool(re.search(AUDIO_OURS, txt, re.I))


def our_cover(e, facet):
    unk = set(e.get("unknown") or [])
    if facet == "kind":
        return e.get("kind") not in ("other", "unknown", None, "") and "kind" not in unk
    if facet == "audio":
        return "audio" not in unk and _audio_named(e)
    return bool(e.get(OUR_FIELD[facet])) and OUR_UNK.get(facet, facet) not in unk


def our_cover_lenient(e, facet):
    if facet == "kind":
        return e.get("kind") not in ("other", "unknown", None, "")
    if facet == "audio":
        return _audio_named(e)
    return bool(e.get(OUR_FIELD[facet]))


def mu_regex(text, music):
    out = {"kind": True, "topic": True}
    for f, rx in RX.items():
        out[f] = bool(re.search(rx, text, re.IGNORECASE))
    if music:
        out["audio"] = True
    return out


def _load_all():
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
    return enr, recs, items, inter


def _row(i, c, e, r, it):
    return {
        "i": i, "code": c, "info": info_class(it),
        "ours": {k: e.get(k) for k in ["summary", "kind", "topics", "shown", "said", "place", "people",
                                         "vibe", "use", "unknown"]},
        "our_cover": {fa: our_cover(e, fa) for fa in FACETS},
        "our_cover_lenient": {fa: our_cover_lenient(e, fa) for fa in FACETS},
        "mu_regex": mu_regex(mu_core(r["mu"]), r["music"]),
        "mu_regex_full": mu_regex(mu_rest(r["mu"]), r["music"]),
    }


def _write(path, rows):
    os.makedirs(WORK, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load(path):
    return [json.loads(ln) for ln in open(path, encoding="utf-8")] if os.path.exists(path) else []


def cmd_sample():
    enr, recs, items, inter = _load_all()
    samp = random.Random(5).sample(inter, 200)
    _write(SAMPLE, [_row(i, c, enr[c], recs[c], items[c]) for i, c in enumerate(samp)])
    print(json.dumps({"enriched_ok": len(enr), "muse_items": len(recs),
                      "enriched_and_in_muse": sum(1 for c in enr if c in recs),
                      "intersection_with_mu_text": len(inter), "sample": len(samp)}))


def cmd_thin_extra():
    enr, recs, items, inter = _load_all()
    insamp = {s["code"] for s in load(SAMPLE)}
    extra = [c for c in inter if c not in insamp and info_class(items[c]) != "ok"]
    _write(THIN_EXTRA, [_row(1000 + n, c, enr[c], recs[c], items[c]) for n, c in enumerate(extra)])
    print(json.dumps({"thin_in_intersection": sum(1 for c in inter if info_class(items[c]) != "ok"),
                      "thin_extra": len(extra)}))


def cmd_show(a, b, which="sample", width=1800):
    recs = load_records()
    for s in load(THIN_EXTRA if which == "extra" else SAMPLE)[int(a):int(b)]:
        r, o = recs[s["code"]], s["ours"]
        print(f"=== #{s['i']} info={s['info']}")
        print("OURS kind=%s | topics=%s | shown=%s | said=%s | place=%s | people=%s | vibe=%s | unknown=%s" % (
            o["kind"], o["topics"], o["shown"], o["said"], o["place"], o["people"], o["vibe"], o["unknown"]))
        print("OURS summary:", o["summary"])
        print("MUSIC:", bool(r["music"]))
        print("MU:", " ".join(mu_core(r["mu"]).split())[:width])


def rate(n, d):
    return round(n / d, 3) if d else None


def block(rows, mu_key, cover="our_cover", judged=True):
    """rows: [(sample_row, judgement or None)]. mu_key(s, j) -> {facet: bool}."""
    n, out = len(rows), {"n": len(rows)}
    for fa in FACETS:
        oc = sum(1 for s, j in rows if s[cover][fa])
        mc = sum(1 for s, j in rows if mu_key(s, j)[fa])
        miss = sum(1 for s, j in rows if mu_key(s, j)[fa] and not s[cover][fa])
        both = sum(1 for s, j in rows if mu_key(s, j)[fa] and s[cover][fa])
        d = {"ours_cov": rate(oc, n), "mu_cov": rate(mc, n), "miss": rate(miss, n),
             "miss_given_mu": rate(miss, mc), "n_both": both}
        if judged:
            conf = sum(1 for s, j in rows if fa in j.get("conflict", []))
            uns = sum(1 for s, j in rows if fa in j.get("unsupported", []))
            d.update({"conflict": rate(conf, n), "conflict_given_both": rate(conf, both)})
            if fa in MEDIA:
                d.update({"unsupported": rate(uns, n), "unsupported_given_ours": rate(uns, oc)})
        out[fa] = d

    def missed(s, j, facets):
        return [fa for fa in facets if mu_key(s, j)[fa] and not s[cover][fa]]

    text_facets = [fa for fa in FACETS if fa not in MEDIA]
    out["any_miss"] = rate(sum(1 for s, j in rows if missed(s, j, FACETS)), n)
    out["any_miss_excl_audio"] = rate(sum(1 for s, j in rows if missed(s, j, [f for f in FACETS if f != "audio"])), n)
    out["any_miss_text_facets"] = rate(sum(1 for s, j in rows if missed(s, j, text_facets)), n)
    out["mean_facets_missed"] = round(sum(len(missed(s, j, FACETS)) for s, j in rows) / n, 2) if n else None
    out["mean_facets_mu"] = round(sum(sum(mu_key(s, j).values()) for s, j in rows) / n, 2) if n else None
    out["mean_facets_ours"] = round(sum(sum(s[cover].values()) for s, j in rows) / n, 2) if n else None
    if judged:
        out["any_conflict"] = rate(sum(1 for s, j in rows if j.get("conflict")), n)
        out["any_unsupported"] = rate(sum(1 for s, j in rows if j.get("unsupported")), n)
    return out


def cmd_score():
    samp, extra = load(SAMPLE), load(THIN_EXTRA)
    judged = {j["i"]: j for j in load(JUDGED)}
    read_key = lambda s, j: {fa: fa in j["mu_cov"] for fa in FACETS}  # noqa: E731
    res = {"n_sample": len(samp), "n_read_in_sample": sum(1 for s in samp if s["i"] in judged),
           "sample_info_counts": {k: sum(1 for s in samp if s["info"] == k) for k in ("ok", "low", "non_english")}}
    read = [(s, judged[s["i"]]) for s in samp if s["i"] in judged]
    res["read"] = block(read, read_key)
    res["read_lenient"] = block(read, read_key, cover="our_cover_lenient")
    res["regex_core_all200"] = block([(s, None) for s in samp], lambda s, j: s["mu_regex"], judged=False)
    res["regex_full_all200"] = block([(s, None) for s in samp], lambda s, j: s["mu_regex_full"], judged=False)
    res["regex_vs_read_agreement"] = {
        fa: rate(sum(1 for s, j in read if s["mu_regex"][fa] == (fa in j["mu_cov"])), len(read)) for fa in FACETS}
    # gate split, read only: ok = read sample items with info ok; thin = every thin item of the intersection
    ok_rows = [(s, j) for s, j in read if s["info"] == "ok"]
    thin_rows = [(s, judged[s["i"]]) for s in samp + extra if s["info"] != "ok" and s["i"] in judged]
    res["gate_ok_read"] = block(ok_rows, read_key)
    res["gate_thin_read_all_intersection"] = block(thin_rows, read_key)
    res["n_thin_in_intersection"] = sum(1 for s in samp if s["info"] != "ok") + len(extra)
    print(json.dumps(res, indent=1))
    json.dump(res, open(os.path.join(WORK, "score.json"), "w"), indent=1)
    return res


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "sample":
        cmd_sample()
    elif cmd == "thin_extra":
        cmd_thin_extra()
    elif cmd == "show":
        cmd_show(*sys.argv[2:5])
    elif cmd == "score":
        cmd_score()
