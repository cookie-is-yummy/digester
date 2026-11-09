"""PROTOTYPE ONLY - tests for the search demo. Synthetic data only; no API key is used (none is passed on).

  python -m pytest experiments/demo/test_demo.py -q

  - the Instagram importer on the committed synthetic export (fixtures/ig_export_json, zipped here);
  - library creation from Instagram + Takeout zips (experiments/youtube/fixtures);
  - make_pack.py on a tiny synthetic research root (friends removed, int8 store, nothing research-only copied);
  - the server's search endpoint on that pack with cached (synthetic) query vectors: Q8 / FM / H0 run without a key,
    compare mode, the keyword fallback when a vector is missing, the friend filter, the token check.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import zipfile

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ig_import  # noqa: E402
import ingest  # noqa: E402
import library as LIB  # noqa: E402

FIX_IG = os.path.join(HERE, "fixtures", "ig_export_json")
FIX_YT = os.path.join(os.path.dirname(HERE), "youtube", "fixtures", "takeout_current")
ITEM_KEYS = {"id", "platform", "source_url", "dedup_key", "first_seen_at", "caption", "platform_data", "importance",
             "processing_depth", "interaction_kinds"}
NO_KEYS = {k: v for k, v in os.environ.items() if k not in ("OPENAI_API_KEY", "GEMINI_API_KEY")}


def zip_dir(src, path, prefix=""):
    with zipfile.ZipFile(path, "w") as z:
        for root, _, files in os.walk(src):
            for f in files:
                full = os.path.join(root, f)
                z.write(full, os.path.join(prefix, os.path.relpath(full, src)))
    return path


@pytest.fixture(scope="module")
def ig_zip(tmp_path_factory):
    return zip_dir(FIX_IG, str(tmp_path_factory.mktemp("ig") / "instagram-synthetic.zip"))


@pytest.fixture(scope="module")
def yt_zip(tmp_path_factory):
    return zip_dir(FIX_YT, str(tmp_path_factory.mktemp("yt") / "takeout-synthetic-001.zip"))


# ---------------- Instagram importer ----------------
def test_ig_import_shapes_shares_and_friends(ig_zip):
    items, inter, stats = ig_import.import_export([ig_zip])
    by = {it["dedup_key"].split(":", 1)[1]: it for it in items}
    assert set(by) == {"SYNTHreel001", "SYNTHpost002", "SYNTHreel004", "SYNTHpost005", "SYNTHpost006", "SYNTHreel007"}
    for it in items:
        assert set(it) == ITEM_KEYS
        assert set(it["platform_data"]) == {"media_kind", "owner_handle", "owner_name", "hashtags", "collections",
                                            "owner_relation"}
        assert it["platform_data"]["owner_relation"] != "mutual"
    assert stats["friends_posts_removed"] == 1  # the mutual follow's post (SYNTHreel009) never enters the library
    assert set(by["SYNTHreel001"]["interaction_kinds"]) == {"save", "like", "collection"}
    assert by["SYNTHreel001"]["platform_data"]["collections"] == ["Synthetic Recipes"]
    assert by["SYNTHreel001"]["platform_data"]["owner_relation"] == "following"
    assert by["SYNTHreel001"]["platform_data"]["hashtags"] == ["baking", "sourdough"]
    assert "share_friend" in by["SYNTHpost002"]["interaction_kinds"]
    assert by["SYNTHreel007"]["interaction_kinds"] == ["share_self"]  # new item from a share to self
    assert by["SYNTHreel007"]["caption"].startswith("Synthetic tiny house")  # the share object's caption
    assert stats["received_not_added"] == 1
    assert {r["kind"] for r in inter} == {"save", "like", "collection", "view", "share_self", "share_friend"}
    ids = {it["id"] for it in items}
    assert all(r["item_id"] in ids for r in inter)
    blob = json.dumps([items, inter, stats])
    assert "SYNTHETIC-DM-TEXT" not in blob and "Sample Pal" not in blob  # no message text, no recipients


def test_ig_import_rejects_html_export(tmp_path):
    p = tmp_path / "html.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("your_instagram_activity/saved/saved_posts.html", "<html></html>")
    with pytest.raises(ValueError, match="JSON format"):
        ig_import.import_export([str(p)])


def test_create_library_from_both_exports(ig_zip, yt_zip, tmp_path):
    lib = ingest.create_library(str(tmp_path), "Synthetic Person", [ig_zip], [yt_zip], router_from=[])
    st = LIB.status(lib)
    assert st["state"] == "needs_prepare"
    items = [json.loads(line) for line in open(os.path.join(lib, "corpus", "items.jsonl"))]
    yt = [it for it in items if it["platform"] == "youtube"]
    assert yt and all(set(it) == ITEM_KEYS for it in items)
    assert all(it["platform_data"]["media_kind"] == "video" for it in yt)
    assert any("Watch later" in it["platform_data"]["collections"] for it in yt)
    assert any(it["platform_data"]["owner_relation"] == "following" for it in yt)
    assert os.path.exists(os.path.join(lib, "enrich", f"{LIB.TE_IG}.jsonl"))
    man = json.load(open(os.path.join(lib, "library.json")))
    assert man["counts"]["instagram"] == 6 and man["counts"]["youtube"] == len(yt)
    assert not [f for f in os.listdir(tmp_path) if f.startswith("takeout_")]  # temporary extraction removed
    assert not os.path.exists(os.path.join(lib, "corpus", "searches.jsonl"))  # search history is not kept


# ---------------- pack building ----------------
def tiny_src(root):
    """A tiny research data root shaped like data/all (synthetic text, random vectors)."""
    rng = np.random.RandomState(0)
    items = []
    ig = [("SYNIG01", "Synthetic sourdough starter guide: feed the starter twice a day #baking", "synth_baker",
           "following"),
          ("SYNIG02", "Synthetic standing desk setup with a cable tray and a monitor arm #desksetup", "synth_desks",
           "none"),
          ("SYNIG03", "Synthetic bodyweight warm up routine in three minutes flat #fitness", "synth_coach",
           "following"),
          ("SYNIG04", "Synthetic picnic photo from last weekend by the lake with friends", "synth_pal", "mutual"),
          ("SYNIG05", "Synthetic sourdough scoring patterns for a crusty country loaf #bread", "synth_baker",
           "following")]
    for k, (code, cap, h, rel) in enumerate(ig):
        items.append({"id": f"itm_ig{k}", "platform": "instagram", "source_url": f"https://www.instagram.com/p/{code}/",
                      "dedup_key": f"instagram:{code}", "first_seen_at": f"2026-0{k + 1}-01T00:00:00+00:00",
                      "caption": cap, "platform_data": {"media_kind": "post", "owner_handle": h, "owner_name": h.upper(),
                                                        "hashtags": [], "collections": [], "owner_relation": rel},
                      "importance": 0.8, "processing_depth": "full", "interaction_kinds": ["save"]})
    yt = [("SYNyt000001", "Synthetic sourdough shaping walkthrough", "Synth Bread Channel"),
          ("SYNyt000002", "Synthetic home office tour", "Synth Desk Channel"),
          ("SYNyt000003", "Synthetic morning stretch routine", "Synth Fitness Channel"),
          ("SYNyt000004", "Synthetic bread scoring for beginners", "Synth Bread Channel"),
          ("SYNyt000005", "", "")]
    for k, (vid, title, ch) in enumerate(yt):
        items.append({"id": f"itm_yt{k}", "platform": "youtube", "source_url": f"https://www.youtube.com/watch?v={vid}",
                      "dedup_key": f"youtube:{vid}", "first_seen_at": "2025-05-01T00:00:00+00:00", "caption": title,
                      "platform_data": {"video_id": vid, "media_kind": "video", "owner_handle": "", "owner_name": ch,
                                        "hashtags": [], "collections": ["Watch later"] if k == 1 else [],
                                        "owner_relation": "none", "watch_count": k + 1, "duration_s": 300,
                                        "available": True},
                      "importance": 0.1, "processing_depth": "count_only", "interaction_kinds": ["watch"]})
    os.makedirs(f"{root}/corpus/emb", exist_ok=True)
    with open(f"{root}/corpus/items.jsonl", "w") as f:
        for it in items:
            f.write(json.dumps(it) + "\n")
    with open(f"{root}/corpus/interactions.jsonl", "w") as f:
        for it in items:
            f.write(json.dumps({"item_id": it["id"], "kind": it["interaction_kinds"][0], "at": it["first_seen_at"],
                                "capture_method": "export_import", "weight": 0.5, "secret_extra": "x"}) + "\n")
    vids = [it["id"] for it in items if it["caption"]]
    for name, dim in (("oai512", 512), ("oai3l_1024", 1024)):
        os.makedirs(f"{root}/corpus/emb/{name}")
        json.dump(vids, open(f"{root}/corpus/emb/{name}/ids.json", "w"))
        np.save(f"{root}/corpus/emb/{name}/emb.npy", rng.randn(len(vids), dim).astype(np.float16))
    codes = [c for c, _, _, rel in ig if rel != "mutual"]
    os.makedirs(f"{root}/enrich")
    with open(f"{root}/enrich/{LIB.TE_IG}.jsonl", "w") as f:
        for c in codes:
            f.write(json.dumps({"code": c, "ok": True, "summary": f"synthetic summary {c}", "kind": "tips",
                                "topics": ["synthetic"], "shown": [], "said": [], "place": [], "people": [],
                                "vibe": ["calm"], "use": [], "queries": [], "in_tokens": 1, "batch": "b/x"}) + "\n")
    json.dump({c: f"synthetic summary {c} tips synthetic" for c in codes}, open(f"{root}/enrich/text_{LIB.TE_IG}.json", "w"))
    os.makedirs(f"{root}/corpus/emb/emb_{LIB.TE_IG}")
    json.dump(codes, open(f"{root}/corpus/emb/emb_{LIB.TE_IG}/ids.json", "w"))
    np.save(f"{root}/corpus/emb/emb_{LIB.TE_IG}/emb.npy", rng.randn(len(codes), 512).astype(np.float16))
    os.makedirs(f"{root}/yt_enrich")
    with open(f"{root}/yt_enrich/{LIB.TE_YT}.jsonl", "w") as f:
        f.write(json.dumps({"code": "SYNyt000001", "ok": True, "summary": "synthetic yt summary", "kind": "tutorial",
                            "topics": [], "vibe": [], "queries": ["x"]}) + "\n")
    json.dump({"SYNyt000001": "synthetic yt text"}, open(f"{root}/yt_enrich/text_{LIB.TE_YT}.json", "w"))
    os.makedirs(f"{root}/r7")
    np.savez(f"{root}/r7/router.npz", Wt=rng.randn(5, 1024) * 0.01, bt=np.zeros(5), Wp=rng.randn(3, 1024) * 0.01,
             bp=np.zeros(3))
    for d in ("evals", "eval_work", "yt_ref", "runs", "cache"):  # research-only: must never be packed
        os.makedirs(f"{root}/{d}")
        open(f"{root}/{d}/do_not_copy.json", "w").write("{}")
    open(f"{root}/ai_runs.jsonl", "w").write("{}\n")
    return items


def make_pack(src, out, *extra):
    r = subprocess.run([sys.executable, os.path.join(HERE, "make_pack.py"), "--src", src, "--out", out, "--name",
                        "tiny", *extra], capture_output=True, text=True, env=NO_KEYS)
    assert r.returncode == 0, r.stderr[-2000:]
    return os.path.join(out, "tiny")


@pytest.fixture(scope="module")
def packed(tmp_path_factory):
    base = tmp_path_factory.mktemp("pack")
    src = str(base / "src")
    items = tiny_src(src)
    return src, make_pack(src, str(base / "out")), items


def test_make_pack_contents(packed):
    src, lib, items = packed
    assert LIB.status(lib)["state"] == "ready"
    got = [json.loads(line) for line in open(os.path.join(lib, "corpus", "items.jsonl"))]
    assert len(got) == len(items) - 1 and not any(LIB.is_friend(it) for it in got)
    inter = [json.loads(line) for line in open(os.path.join(lib, "corpus", "interactions.jsonl"))]
    assert {r["item_id"] for r in inter} == {it["id"] for it in got}
    assert not any("secret_extra" in r for r in inter)
    files = {os.path.relpath(os.path.join(d, f), lib) for d, _, fs in os.walk(lib) for f in fs}
    assert not [f for f in files if f.split(os.sep)[0] in ("evals", "eval_work", "yt_ref", "runs", "cache")]
    assert "ai_runs.jsonl" not in files and not any("oai512" in f for f in files)
    ids = json.load(open(os.path.join(lib, "corpus", "emb", LIB.Q8_STORE, "ids.json")))
    q = np.load(os.path.join(lib, "corpus", "emb", LIB.Q8_STORE, "q8.npy"))
    s = np.load(os.path.join(lib, "corpus", "emb", LIB.Q8_STORE, "scale.npy"))
    assert q.dtype == np.int8 and q.shape == (len(ids), 1024) and "itm_ig3" not in ids
    # q8-v1 over the whole source index (scales from all rows), then the friend's row dropped
    sids = json.load(open(os.path.join(src, "corpus", "emb", "oai3l_1024", "ids.json")))
    from sklearn.preprocessing import normalize
    V = normalize(np.load(os.path.join(src, "corpus", "emb", "oai3l_1024", "emb.npy")).astype(np.float32))
    exp_s = (np.abs(V).max(axis=0) / 127).astype(np.float32)
    exp_q = np.clip(np.rint(V / exp_s), -127, 127).astype(np.int8)
    assert np.array_equal(s, exp_s)
    assert np.array_equal(q, exp_q[[sids.index(i) for i in ids]])
    te = [json.loads(line) for line in open(os.path.join(lib, "enrich", f"{LIB.TE_IG}.jsonl"))]
    assert te and not any("batch" in r or "in_tokens" in r for r in te)
    yt = [json.loads(line) for line in open(os.path.join(lib, "yt_enrich", f"{LIB.TE_YT}.jsonl"))]
    assert yt[0]["summary"] and "queries" not in yt[0]
    assert json.load(open(os.path.join(lib, "yt_enrich", f"text_{LIB.TE_YT}.json"))) == {}


# ---------------- server search endpoint ----------------
def cache_query_vectors(lib, src, strings_to_item):
    """Synthetic 'cached query vectors': each query string gets an item's own vector (3-large and te 3-small)."""
    sids = json.load(open(os.path.join(src, "corpus", "emb", "oai3l_1024", "ids.json")))
    V = np.load(os.path.join(src, "corpus", "emb", "oai3l_1024", "emb.npy"))
    T = np.load(os.path.join(src, "corpus", "emb", f"emb_{LIB.TE_IG}", "emb.npy"))
    for name, rows in (("oai3l_1024_queries", [V[sids.index(i)] for i in strings_to_item.values()]),
                       ("c4_queries", [T[0] for _ in strings_to_item])):
        d = os.path.join(lib, "corpus", "emb", name)
        os.makedirs(d, exist_ok=True)
        json.dump(list(strings_to_item), open(os.path.join(d, "ids.json"), "w"))
        np.save(os.path.join(d, "emb.npy"), np.array(rows, np.float16))


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    def __init__(self, lib):
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.p = subprocess.Popen([sys.executable, os.path.join(HERE, "app.py"), "--library", lib, "--port",
                                   str(self.port), "--no-browser"], env=NO_KEYS, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True)
        self.p.stdout.readline()
        html = self.get("/", raw=True)
        self.token = html.split('const TOKEN = "', 1)[1].split('"', 1)[0]
        t0 = time.time()
        while self.get("/api/state")["engine"]["state"] != "ready":
            assert time.time() - t0 < 180, "engine did not load"
            time.sleep(0.5)

    def get(self, path, raw=False):
        with urllib.request.urlopen(self.base + path, timeout=30) as r:
            body = r.read().decode()
        return body if raw else json.loads(body)

    def post(self, path, body, token=True):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json",
                                              **({"X-Demo-Token": self.token} if token else {})})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def close(self):
        self.p.terminate()
        self.p.wait(10)


@pytest.fixture(scope="module")
def server(packed):
    src, lib, _ = packed
    cache_query_vectors(lib, src, {"sourdough": "itm_ig0", "office tour": "itm_yt1"})
    s = Server(lib)
    yield s
    s.close()


def test_search_q8_with_cached_vectors(server):
    st = server.get("/api/state")
    assert st["keys"] == {"openai": None, "gemini": None} and st["engine"]["info"]["counts"]["items"] == 9
    code, r = server.post("/api/search", {"query": "sourdough", "processors": ["q8"]})
    assert code == 200
    q8 = r["q8"]
    w = q8["why"]
    assert w["mode"] == "normal" and w["path"] == "instant" and w["embed_cached"]
    assert w["cost"]["usd"] == 0 and w["cost"]["calls"] == []
    assert w["prior"]["reads"] in ("Instagram", "YouTube") and 0 <= w["prior"]["q_ig"] <= 1
    assert w["te"]["available"] and w["refine"]["gated"] is False
    assert set(w["latency"]) >= {"route_s", "embed_s", "local_s", "first_screen_s", "total_s"}
    res = q8["results"]
    assert any(x["url"].endswith("/SYNIG01/") for x in res[:3])  # the item whose vector the query has
    assert len(res) <= 20 and all(set(x) >= {"platform", "creator", "text", "date", "how", "url"} for x in res)
    assert not any("SYNIG04" in x["url"] for x in res)  # the friend's post is not in the pack


def test_compare_and_h0_without_key(server):
    code, r = server.post("/api/search", {"query": "office tour", "processors": ["q8", "h0"]})
    assert code == 200 and set(r) == {"q8", "h0"}
    h0 = r["h0"]["why"]
    assert h0["path"] == "rewrite" and h0["rewrite"]["used"] is False and "no OpenAI key" in h0["rewrite"]["skipped"]
    assert h0["mode"] == "normal" and any("raw query" in n for n in h0["notes"])
    assert r["q8"]["results"][0]["url"].endswith("SYNyt000002")
    code, r = server.post("/api/search", {"query": "office tour", "processors": ["fm"]})
    assert code == 200 and r["fm"]["why"]["refine"]["model"] == "gpt-5-mini"


def test_keyword_fallback_when_vectors_missing(server):
    code, r = server.post("/api/search", {"query": "standing desk cable tray", "processors": ["q8"]})
    assert code == 200
    w = r["q8"]["why"]
    assert w["mode"] == "keyword_fallback" and any("no OpenAI key" in n for n in w["notes"])
    assert r["q8"]["results"][0]["url"].endswith("/SYNIG02/")


def test_api_needs_token_and_query(server):
    code, _ = server.post("/api/search", {"query": "sourdough"}, token=False)
    assert code == 403
    code, r = server.post("/api/search", {"query": "   "})
    assert code == 400


def test_display_filter_hides_friends(packed, tmp_path):
    """A library that still holds a friend's post (e.g. an older import) never shows it."""
    src, _, _ = packed
    lib = make_pack(src, str(tmp_path / "out"), "--keep-friends")
    cache_query_vectors(lib, src, {"picnic": "itm_ig3"})  # the query vector IS the friend's post's vector
    s = Server(lib)
    try:
        code, r = s.post("/api/search", {"query": "picnic", "processors": ["q8"]})
        assert code == 200
        assert not any("SYNIG04" in x["url"] for x in r["q8"]["results"])
        assert any("friends' posts were left out" in n for n in r["q8"]["why"]["notes"])
    finally:
        s.close()
        shutil.rmtree(lib, ignore_errors=True)
