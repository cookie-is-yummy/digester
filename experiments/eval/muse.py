"""PROTOTYPE ONLY - EVALUATOR SIDE. Parser for the Muse export (data/evals/labels/muse_export/).

Only the evaluator role may import this. MU text is the source the eval answers were found with, so it
must never feed a method that could be adopted, nor the query rewrite (experiments/BRIEF.md, "The Muse export").

Format (caption-mu/*.txt, one file per Muse report): a '# ...' header, then records separated by lines of
'=' characters. Each record:
    @handle — https://www.instagram.com/(reel|p|tv)/<shortcode>/
    Type: reel|post | Sources: liked, saved | Date: YYYY-MM-DD HH:MM:SS
    [Music: ...]
    --- CAPTION ---
    <caption>
    --- MU (video description) ---
    <MU text: description, then '## Searches', '## Media Pivots', '## Author & Community Breakdown', ...>

The same item can appear in several files; we keep the longest MU text seen.

usage (as a library):
    from muse import load_mu, load_records
    mu = load_mu()            # {shortcode: mu_text}
    recs = load_records()     # {shortcode: {"handle", "type", "sources", "date", "music", "caption", "mu", "files"}}
"""
import glob
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
from corpus import DATA  # noqa: E402

MUSE_DIR = os.path.join(DATA, "evals", "labels", "muse_export", "caption-mu")
_SEP = re.compile(r"^={20,}\s*$", re.M)
_URL = re.compile(r"instagram\.com/(?:reel|p|tv)/([A-Za-z0-9_-]+)")
CAP_MARK = "--- CAPTION ---"
MU_MARK = "--- MU (video description) ---"


def parse_record(block):
    lines = block.strip("\n").split("\n")
    if not lines or not lines[0].startswith("@"):
        return None
    m = _URL.search(lines[0])
    if not m:
        return None
    rec = {"code": m.group(1), "handle": lines[0].split(" ", 1)[0][1:], "type": None, "sources": [],
           "date": None, "music": None}
    for ln in lines[1:4]:
        if ln.startswith("Type:"):
            for part in ln.split("|"):
                k, _, v = part.partition(":")
                k, v = k.strip(), v.strip()
                if k == "Type":
                    rec["type"] = v
                elif k == "Sources":
                    rec["sources"] = [s.strip() for s in v.split(",") if s.strip()]
                elif k == "Date":
                    rec["date"] = v
        elif ln.startswith("Music:"):
            rec["music"] = ln[len("Music:"):].strip()
    body = "\n".join(lines)
    ci, mi = body.find(CAP_MARK), body.find(MU_MARK)
    rec["caption"] = body[ci + len(CAP_MARK):mi].strip() if ci >= 0 and mi > ci else ""
    rec["mu"] = body[mi + len(MU_MARK):].strip() if mi >= 0 else ""
    return rec


def load_records(muse_dir=MUSE_DIR, skip=()):
    """{shortcode: record}. `skip`: file basenames (without .txt) to ignore."""
    out = {}
    for path in sorted(glob.glob(os.path.join(muse_dir, "*.txt"))):
        name = os.path.basename(path)[:-4]
        if name in skip:
            continue
        for block in _SEP.split(open(path, encoding="utf-8").read()):
            rec = parse_record(block)
            if rec is None:
                continue
            prev = out.get(rec["code"])
            if prev is None:
                rec["files"] = [name]
                out[rec["code"]] = rec
            else:
                prev["files"].append(name)
                if len(rec["mu"]) > len(prev["mu"]):
                    rec["files"] = prev["files"]
                    out[rec["code"]] = rec
    return out


def mu_description(mu):
    """Only the free-text video description: MU text up to its first '## ' / 'Cultural Context'-style subsection."""
    cut = re.search(r"^(## |# |Cultural Context$|Humor Context$|Temporal Context$)", mu, re.M)
    return mu[:cut.start()].strip() if cut else mu.strip()


def load_mu(description_only=False):
    """{shortcode (content code): MU text}. description_only=True drops the Searches/Pivots/Community sections."""
    return {c: (mu_description(r["mu"]) if description_only else r["mu"]) for c, r in load_records().items() if r["mu"]}


def load_captions():
    return {c: r["caption"] for c, r in load_records().items()}


if __name__ == "__main__":
    recs = load_records()
    print(f"{len(recs)} unique items, {sum(1 for r in recs.values() if r['mu'])} with MU text")
