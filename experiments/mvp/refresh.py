"""PROTOTYPE ONLY - keeping the library fresh (DESIGN.md section 11 "Keeping the library fresh", which replaces the
routine in section 9; research note export_routine.md, "Corrected recommendation").

What is automatic and what is not. A fully automatic routine is not available to a US account today (Google's Data
Portability API is not offered in the US; Meta's repeating export to outside storage is documented for the EU only).
So the person still asks Instagram and Google for each export and puts the file in their inbox (the upload box on the
test page). From there everything happens without anyone typing a command:

- An inbox folder per person: <MVP_INBOX>/<person>/ (default data/inbox/, outside git). The scheduler looks at the
  inboxes every few minutes (MVP_INBOX_MINUTES). A file there that has not changed for a minute (or that the upload box
  finished writing) is taken: an Instagram export (JSON, a zip or a folder) or a Google Takeout zip (or folder) with
  YouTube in it. Anything else is refused with a plain message.
- It is imported by the demo's own importer (experiments/demo/ingest.create_library, called, not copied) into a new
  library folder beside the old one. Nothing in an export's messages folder is read: the Instagram input handed to the
  importer is a copy holding only the export's .json files outside any "messages" folder (the importer itself would
  open DM files to find shared posts). Send-to-self shares and the other platform's items already in the old library
  are carried over, since the new export cannot hold them.
- Building the library's search vectors calls the embedding model and costs money: the cost is estimated in code from
  the items' text, and an import above MVP_IMPORT_CAP_USD (default $1.50), or one the build budget has no room for,
  is refused with a plain message. The build runs the demo engine's `prepare` (embeddings only, no te pass) with that
  cap as its own hard budget; what it spent is written to the MVP ledger with the person's handle.
- Only when the build succeeded is the person's library switched to the new folder (the old one is kept); then they
  get one message with counts (new items, by source), and their new_items rules run once, on the new items only, with
  "nothing new matched" said at most once per import. A failed build leaves the old library in use and says so.
- library_status: when the last export came in, items by source, how old the newest item is, when the next export is
  due, and the export links.
- export_routine() / offer_export_routine(): the export steps per platform and the reminder rules (for the onboarding
  slice).

Counts only are logged; no captions, titles or names. Exports are raw personal data: a file that was imported is
deleted, one that was refused or failed is moved to <inbox>/<person>/.failed/ for a founder to look at.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import config, llm
from . import texts as T
from .schema import RuleSpec
from .store import now_iso

sys.path.insert(0, config.DEMO)
import ig_import  # noqa: E402
import ingest  # noqa: E402
import library as LIB  # noqa: E402

PREPARE_PURPOSES = ("demo_item_vectors_3l", "demo_key_check")   # the ledger rows of a library build
IG_JSON = [suf for suf, _, _ in ig_import.SOURCES] + [ig_import.COLLECTIONS]
IG_HTML = ("saved_posts.html", "liked_posts.html")
SHARE_KINDS = ("share_self", "share_friend")
PRICES = os.path.join(config.EXP, "lib", "ai_prices.json")
EMBED_MODEL = "text-embedding-3-large"
EXPORT_LINKS = {"instagram": "https://accountscenter.instagram.com/info_and_permissions/dyi",
                "youtube": "https://takeout.google.com"}
# the reminder rules' own words (source note); library_status finds them by these openings
REMINDER_OPENING = {"instagram": "Time for a fresh Instagram export", "youtube": "Time for a fresh YouTube export"}


# ---------- inboxes ----------
def inbox_name(handle):
    """One folder name per person: the handle's letters and digits ('+15551234567' -> '15551234567')."""
    return re.sub(r"[^A-Za-z0-9]+", "_", handle or "").strip("_").lower() or "person"


def inbox_dir(handle):
    return os.path.join(config.INBOX, inbox_name(handle))


def shared_inboxes(store):
    """Inbox folder names that two or more people map to ('a.b@x.com' and 'a_b@x.com'). Such a folder is never
    imported from and the upload box refuses it: an export there could be either person's."""
    names = Counter(inbox_name(p["handle"]) for p in store.q("SELECT handle FROM people"))
    return {n for n, k in names.items() if k > 1}


def safe_filename(name):
    base = os.path.basename((name or "").replace("\\", "/"))
    # no leading "." or "_": the inbox check skips such names (its own working folders), so the file would wait forever
    base = re.sub(r"[^A-Za-z0-9._ -]+", "_", base).lstrip("._ ").rstrip(" .")
    return base[:120] or "export.zip"


def save_upload(handle, filename, stream, length, chunk=1 << 20):
    """The test page's upload box: the file goes to the person's inbox, written as .part and renamed when complete,
    so the scheduler never takes half a file. Returns the final path."""
    d = inbox_dir(handle)
    os.makedirs(d, exist_ok=True)
    name = safe_filename(filename)
    stem, ext = os.path.splitext(name)
    final, k = os.path.join(d, name), 2
    while os.path.exists(final):
        final, k = os.path.join(d, f"{stem}-{k}{ext}"), k + 1
    part = final + ".part"
    left = length
    with open(part, "wb") as f:
        while left > 0:
            buf = stream.read(min(chunk, left))
            if not buf:
                break
            f.write(buf)
            left -= len(buf)
    if left:
        os.remove(part)
        raise ValueError("the upload was cut off")
    os.replace(part, final)
    return final


# ---------- what a file is ----------
def _member_names(path):
    """Posix paths of the files inside a zip or a folder (names only; no file is opened)."""
    if os.path.isdir(path):
        out = []
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            out += [os.path.relpath(os.path.join(root, f), path).replace(os.sep, "/") for f in files]
        return out
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            return [n.replace("\\", "/") for n in z.namelist() if not n.endswith("/")]
    return None


def classify(path):
    """('instagram' | 'takeout' | None, why). Only member names are looked at."""
    names = _member_names(path)
    if names is None:
        return None, "not_export"
    norm = [n.lstrip("./") for n in names]
    if any(n == s or n.endswith("/" + s) for n in norm for s in IG_JSON) or \
            any(ig_import.FOLLOWERS.search(n) or ig_import.FOLLOWING.search(n) for n in norm):
        return "instagram", None
    if any(ingest.YT_KEEP.search(n) for n in norm):
        return "takeout", None
    if any(n.lower().endswith(IG_HTML) for n in norm):
        return None, "html"
    return None, "not_export"


def _in_messages(name):
    return "messages" in [p.lower() for p in name.split("/")[:-1]]


def _unsafe(name):
    return name.startswith("/") or ".." in name.split("/")


def instagram_input(src, dest):
    """A zip for the importer with only the export's .json files outside any messages folder: DM files are never
    opened, and media are never copied. Returns {"files": n, "messages_left_out": m}."""
    kept = skipped = 0
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as out:
        if os.path.isdir(src):
            for root, dirs, files in os.walk(src):
                rel_root = os.path.relpath(root, src).replace(os.sep, "/")
                for d in list(dirs):
                    if d.lower() == "messages" or d.startswith("."):
                        dirs.remove(d)
                        skipped += d.lower() == "messages"
                for f in files:
                    name = f if rel_root == "." else f"{rel_root}/{f}"
                    if f.lower().endswith(".json"):
                        out.write(os.path.join(root, f), name)
                        kept += 1
        else:
            with zipfile.ZipFile(src) as z:
                for info in z.infolist():
                    name = info.filename.replace("\\", "/")
                    if name.endswith("/") or _unsafe(name):
                        continue
                    if _in_messages(name):
                        skipped += 1
                        continue
                    if name.lower().endswith(".json"):
                        out.writestr(name, z.read(info))
                        kept += 1
    return {"files": kept, "messages_left_out": skipped}


def takeout_input(src, dest):
    """A Takeout zip is passed as it is (the importer extracts only the YouTube history, playlists, subscriptions and
    My Activity files). A Takeout folder is zipped with only those files."""
    if not os.path.isdir(src):
        return src
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as out:
        for name in _member_names(src):
            if ingest.YT_KEEP.search(name) and not _unsafe(name):
                out.write(os.path.join(src, *name.split("/")), name)
    return dest


# ---------- the library's files ----------
def _jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _write_jsonl(path, rows):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def kept_counts(lib):
    """{platform: items} of a library, friends' posts left out, and the set of ids."""
    ids, counts = set(), Counter()
    for it in _jsonl(LIB.p(lib, "corpus", "items.jsonl")):
        if LIB.is_friend(it):
            continue
        ids.add(it["id"])
        counts[it.get("platform") or "other"] += 1
    return dict(counts), ids


def carry_over(old_lib, new_lib, imported):
    """Items the new export cannot hold come over from the old library: every item of a platform this import did not
    bring (a YouTube-only Takeout keeps the Instagram items, and the other way round), and, when Instagram was
    imported, the send-to-self and sent-to-someone shares (the export's messages are never read). Friends' posts never
    come over. Returns counts."""
    if not old_lib or not os.path.isfile(LIB.p(old_lib, "corpus", "items.jsonl")):
        return {"items": 0, "shares": 0}
    items = _jsonl(LIB.p(new_lib, "corpus", "items.jsonl"))
    inter = _jsonl(LIB.p(new_lib, "corpus", "interactions.jsonl"))
    by_id = {it["id"]: it for it in items}
    old_items = {it["id"]: it for it in _jsonl(LIB.p(old_lib, "corpus", "items.jsonl")) if not LIB.is_friend(it)}
    old_inter = _jsonl(LIB.p(old_lib, "corpus", "interactions.jsonl"))
    moved, shares = set(), 0
    for iid, it in old_items.items():
        if it.get("platform") not in imported and iid not in by_id:
            items.append(it)
            by_id[iid] = it
            moved.add(iid)
    for r in old_inter:
        iid = r.get("item_id")
        if iid in moved:
            inter.append(r)
        elif "instagram" in imported and r.get("kind") in SHARE_KINDS and iid in old_items \
                and old_items[iid].get("platform") == "instagram":
            if iid not in by_id:
                items.append(dict(old_items[iid]))
                by_id[iid] = items[-1]
            it = by_id[iid]
            it["interaction_kinds"] = sorted(set(it.get("interaction_kinds") or []) | {r["kind"]})
            inter.append(r)
            shares += 1
    if moved or shares:
        _write_jsonl(LIB.p(new_lib, "corpus", "items.jsonl"), items)
        _write_jsonl(LIB.p(new_lib, "corpus", "interactions.jsonl"), inter)
    man = LIB.read_json(LIB.p(new_lib, "library.json"), {}) or {}
    plat = Counter(it.get("platform") for it in items)
    man["counts"] = {"items": len(items), "instagram": plat.get("instagram", 0), "youtube": plat.get("youtube", 0),
                     "interactions": len(inter)}
    man["carried_over"] = {"items": len(moved), "shares": shares}
    LIB.write_json(LIB.p(new_lib, "library.json"), man)
    return {"items": len(moved), "shares": shares}


# ---------- cost ----------
def _price_per_m():
    with open(PRICES, encoding="utf-8") as f:
        return json.load(f)["models"][EMBED_MODEL]["input_per_m"]


def estimate_usd(lib):
    """What embedding every item of the library would cost, worked out in code: the text the engine embeds is the
    caption, the creator, hashtags and collections (at most 6,000 characters an item, about 4 characters a token), at
    the verified price of text-embedding-3-large, with half again as a margin, plus the key check."""
    chars = 0
    for it in _jsonl(LIB.p(lib, "corpus", "items.jsonl")):
        pd = it.get("platform_data") or {}
        text = " ".join(str(x) for x in [it.get("caption") or "", pd.get("owner_handle") or "", pd.get("owner_name") or "",
                                         " ".join(pd.get("hashtags") or []), " ".join(pd.get("collections") or [])])
        chars += min(len(text) + 40, 6000)
    return round(chars / 4 / 1e6 * _price_per_m() * 1.5 + 0.0005, 4)


def library_spend(lib):
    return round(sum(r.get("cost_usd") or 0.0 for r in _jsonl(os.path.join(lib, "ai_runs.jsonl"))), 6)


def prepare_library(lib, cap_usd, timeout=3600):
    """The demo engine's prepare (3-large item vectors; no te pass), in its own process, with `cap_usd` as its hard
    budget (its ledger is the new library's own, so it starts at zero). Its output is not kept: it can hold errors
    only. Returns {"ok": bool, "message": str}."""
    env = os.environ.copy()
    env.pop("DIGESTER_DATA", None)
    env["DIGESTER_OPENAI_BUDGET_USD"] = f"{cap_usd:.4f}"
    try:
        p = subprocess.run([sys.executable, config.ENGINE, "prepare", lib, "--te", "0", "--workers", "2"], env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout)
        code = p.returncode
    except subprocess.TimeoutExpired:
        code = "timeout"
    st = LIB.read_json(LIB.p(lib, "prepare_status.json"), {}) or {}
    ok = code == 0 and st.get("state") == "done"
    return {"ok": ok, "message": "" if ok else str(st.get("message") or f"prepare ended ({code})")[:200]}


PART = re.compile(r"^(.+?)-(\d{3})\.zip$", re.I)


# ---------- the import ----------
class Refresher:
    """Looks at the inboxes (poll), imports what it finds (import_files), switches the library, tells the person and
    runs their new_items rules. `prepare` and `estimate` are replaced in tests; `background=False` runs an import in
    the calling thread."""

    def __init__(self, bot, prepare=None, estimate=None, background=True, settle_seconds=None):
        self.bot = bot
        self.prepare = prepare or prepare_library
        self.estimate = estimate or estimate_usd
        self.background = background
        self.settle = config.INBOX_SETTLE_SECONDS if settle_seconds is None else settle_seconds
        self.lock = threading.Lock()
        self.busy = set()         # handles with an import running
        self.ready = set()        # files the upload box finished writing (no need to wait for them to settle)
        self.last_poll = 0.0
        self.threads = []
        self.recovered = False    # recover() runs at the first look
        self.warned = set()

    def nudge(self, path=None):
        """The upload box wrote a whole file: look at the inboxes at the next scheduler turn."""
        if path:
            self.ready.add(os.path.abspath(path))
        self.last_poll = 0.0

    def waiting(self, handle):
        d = inbox_dir(handle)
        if not os.path.isdir(d):
            return []
        out = []
        for name in sorted(os.listdir(d)):
            path = os.path.join(d, name)
            if name.startswith((".", "_")) or name.endswith((".part", ".tmp")):
                continue
            if not (os.path.isfile(path) or os.path.isdir(path)):
                continue
            if os.path.abspath(path) not in self.ready and time.time() - _mtime(path) < self.settle:
                continue   # still being copied in
            out.append(path)
        # fix pass, finding 31: a Takeout export in parts (-001.zip, -002.zip) is imported in one go, once no new part
        # of it has come for MVP_INBOX_PARTS_MINUTES; otherwise a second import would replace the first part's items
        groups = {}
        for path in out:
            m = PART.match(os.path.basename(path))
            if m:
                groups.setdefault(m.group(1).lower(), []).append(path)
        wait = config.INBOX_PARTS_MINUTES * 60
        for name in os.listdir(d):   # parts still being copied count as new parts too
            m = PART.match(name) or PART.match(re.sub(r"\.(part|tmp)$", "", name))
            if m and m.group(1).lower() in groups:
                p = os.path.join(d, name)
                if time.time() - _mtime(p) < wait:
                    out = [x for x in out if x not in groups[m.group(1).lower()]]
        return out

    def poll(self, now=None, force=False):
        """Every MVP_INBOX_MINUTES (real time): start an import for each person with a new file. Returns the number
        started."""
        if not force and time.time() - self.last_poll < config.INBOX_MINUTES * 60:
            return 0
        self.last_poll = time.time()
        if not self.recovered:
            self.recovered = True
            self.recover()
        if not os.path.isdir(config.INBOX):
            return 0
        started = 0
        shared = shared_inboxes(self.bot.store)
        for p in self.bot.store.q("SELECT handle FROM people WHERE consent_version IS NOT NULL AND paused=0"):
            h = p["handle"]
            if inbox_name(h) in shared:   # two people, one folder: whose export it is can't be told, so nobody's
                if h not in self.warned:
                    self.warned.add(h)
                    print("inbox check: two people share one inbox folder; it is left alone", file=sys.stderr)
                continue
            with self.lock:
                if h in self.busy:
                    continue
                files = self.waiting(h)
                if not files:
                    continue
                self.busy.add(h)
            started += 1
            if self.background:
                t = threading.Thread(target=self._job, args=(h, files), daemon=True, name=f"import-{inbox_name(h)}")
                self.threads.append(t)
                t.start()
            else:
                self._job(h, files)
        return started

    def _job(self, handle, files):
        try:
            self.import_files(handle, files)
        except Exception as e:  # noqa: BLE001 - the type only; never the file's content
            print(f"import error: {type(e).__name__}", file=sys.stderr)
        finally:
            with self.lock:
                self.busy.discard(handle)

    def import_files(self, handle, files, now=None):
        """One import of the files given (moved out of the inbox first). Returns the imports row as a dict."""
        bot, store = self.bot, self.bot.store
        t0 = time.time()
        person = store.person(handle)
        if person is None:
            return None
        old_lib = person["library"]
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        work = os.path.join(inbox_dir(handle), ".working", stamp)
        os.makedirs(os.path.join(work, "in"), exist_ok=True)
        claimed = []
        for f in files:   # taken out of the inbox at once, so no second look picks them up
            dest = os.path.join(work, os.path.basename(f))
            os.replace(f, dest)
            self.ready.discard(os.path.abspath(f))
            claimed.append(dest)
        # recorded at once as "running", with its working folder: a restart in the middle finds it (recover())
        row = {"handle": handle, "at": now_iso(now or bot.clock()), "old_library": old_lib, "status": "running",
               "work": work}
        row["id"] = _add_import(store, row)

        def finish(status, message, error=None):
            row.update(status=status, error=error, seconds=round(time.time() - t0, 1))
            new_lib = row.get("library")
            if new_lib and status != "done" and os.path.isdir(new_lib) and \
                    os.path.abspath(new_lib) != os.path.abspath(old_lib):
                shutil.rmtree(new_lib, ignore_errors=True)   # a failed build is derived data: removed, old kept
            row["id"] = _add_import(store, row)
            for f in claimed:
                if status == "done":
                    _remove(f)   # raw export, imported: not kept
                else:
                    failed = os.path.join(inbox_dir(handle), ".failed")
                    os.makedirs(failed, exist_ok=True)
                    os.replace(f, os.path.join(failed, f"{stamp}-{os.path.basename(f)}"))
            shutil.rmtree(work, ignore_errors=True)
            if message is not None:
                with bot.lock_for(handle):
                    bot.send(handle, message)
            print(f"import: {status}, {row.get('n_new', 0)} new items, {row['seconds']} s", file=sys.stderr)
            return row

        try:
            return self._import_claimed(handle, claimed, work, row, old_lib, t0, finish)
        except Exception as e:  # noqa: BLE001 - any crash of the importer or the build: the type only, never content
            if row.get("status") == "done":   # switched already: the new library stays; the imported files go
                row["error"] = type(e).__name__
                _add_import(store, row)
                for f in claimed:
                    _remove(f)
                shutil.rmtree(work, ignore_errors=True)
                print(f"import: done, then {type(e).__name__}", file=sys.stderr)
                return row
            return finish("failed", T.IMPORT_FAILED, error=type(e).__name__)

    def recover(self):
        """At the first look after a start: an import this store recorded as running was cut off by a stop. Its
        half-built library is removed (the person never switched to it) and its files go back into the inbox, so the
        import starts again; the row says "interrupted". Only folders named in this store's rows are touched, so a
        second process sharing the inbox keeps its own imports."""
        n = 0
        for r in self.bot.store.q("SELECT * FROM imports WHERE status='running'"):
            if r["handle"] in self.busy:
                continue
            person = self.bot.store.person(r["handle"])
            lib = r.get("library")
            if lib and os.path.isdir(lib) and (person is None or os.path.abspath(lib) != os.path.abspath(
                    person["library"])) and os.path.abspath(lib) != os.path.abspath(r.get("old_library") or ""):
                shutil.rmtree(lib, ignore_errors=True)
            work = r.get("work")
            if work and os.path.isdir(work) and person is not None:
                d = inbox_dir(r["handle"])
                for name in os.listdir(work):
                    if name == "in":
                        continue
                    dest, k = os.path.join(d, name), 2
                    while os.path.exists(dest):
                        dest, k = os.path.join(d, f"{k}-{name}"), k + 1
                    os.replace(os.path.join(work, name), dest)
                    self.ready.add(os.path.abspath(dest))
                    n += 1
            if work:
                shutil.rmtree(work, ignore_errors=True)
            self.bot.store.x("UPDATE imports SET status='interrupted' WHERE id=?", (r["id"],))
        return n

    def _import_claimed(self, handle, claimed, work, row, old_lib, t0, finish):
        bot, store = self.bot, self.bot.store
        ig, yt, refused, html = [], [], 0, False
        for i, f in enumerate(claimed):
            kind, why = classify(f)
            if kind == "instagram":
                dest = os.path.join(work, "in", f"instagram-{i}.zip")
                info = instagram_input(f, dest)
                row.setdefault("messages_left_out", 0)
                row["messages_left_out"] += info["messages_left_out"]
                ig.append(dest)
            elif kind == "takeout":
                yt.append(takeout_input(f, os.path.join(work, "in", f"takeout-{i}.zip")))
            else:
                refused += 1
                html = html or why == "html"
        sources = (["instagram"] if ig else []) + (["youtube"] if yt else [])
        row["sources"] = json.dumps({"instagram": len(ig), "youtube": len(yt), "refused": refused})
        if not sources:
            return finish("refused", T.IMPORT_HTML if html else T.IMPORT_NOT_EXPORT)
        root = config.LIBRARY_ROOT or os.path.dirname(os.path.abspath(old_lib))
        routers = [old_lib, os.path.join(config.REPO, "data", "all")]
        try:
            new_lib = ingest.create_library(root, f"{inbox_name(handle)}-{datetime.now().strftime('%Y%m%d')}",
                                            ig, yt, own_names=(), router_from=routers)
        except ValueError as e:
            return finish("refused", T.IMPORT_HTML if "HTML" in str(e) else T.IMPORT_NOT_EXPORT, error="ValueError")
        row["library"] = new_lib
        _add_import(store, row)   # recorded now: a stop during the build leaves a folder recover() must remove
        man = LIB.read_json(LIB.p(new_lib, "library.json"), {}) or {}
        if ig and any("followers" in str(w).lower() for w in man.get("warnings") or []):
            return finish("refused", T.IMPORT_NO_FOLLOWERS)
        man["mvp_import"] = True   # its build rows are mirrored in the MVP ledger (llm.py counts them once)
        LIB.write_json(LIB.p(new_lib, "library.json"), man)
        carried = carry_over(old_lib, new_lib, set(sources))
        row["carried"] = carried
        est = self.estimate(new_lib)
        row["estimate_usd"] = est
        if est > config.IMPORT_CAP_USD:
            return finish("too_costly", T.import_too_costly(est, config.IMPORT_CAP_USD))
        libs = [p["library"] for p in store.q("SELECT library FROM people")]
        if llm.spent_total(libs) + est > config.TOTAL_CAP_USD:
            return finish("over_budget", T.import_over_budget())
        try:
            res = self.prepare(new_lib, config.IMPORT_CAP_USD)
        except Exception as e:  # noqa: BLE001
            res = {"ok": False, "message": type(e).__name__}
        cost = library_spend(new_lib)
        row["cost_usd"] = cost
        if cost:
            llm.log_spend(handle, "mvp_import", cost, model=EMBED_MODEL, n=man.get("counts", {}).get("items"))
        if not res.get("ok"):
            return finish("failed", T.IMPORT_FAILED, error=(res.get("message") or "")[:200])
        totals, new_ids = kept_counts(new_lib)
        _, old_ids = kept_counts(old_lib)
        fresh = new_ids - old_ids
        by_source = Counter()
        for it in _jsonl(LIB.p(new_lib, "corpus", "items.jsonl")):
            if it["id"] in fresh:
                by_source[it.get("platform") or "other"] += 1
        row.update(counts=json.dumps(totals), new_counts=json.dumps(dict(by_source)), n_new=len(fresh))
        with bot.lock_for(handle):
            store.switch_library(handle, new_lib)
            row.update(status="done", seconds=round(time.time() - t0, 1))
            row["id"] = _add_import(store, row)
            person = store.person(handle)
            held = {"fresh": sorted(fresh), "by_source": dict(by_source), "totals": totals, "refused": refused}
            now = bot.clock()
            if bot._held_now(person, now):
                # fix pass, finding 32: in quiet hours or a snooze, the import's message and its new_items answers
                # wait; the scheduler sends them when the quiet block (and the snooze) ends
                prev = store.get_state(f"heldimport:{handle}") or {}
                if prev:   # two imports in one night: one message, with every new item
                    held["fresh"] = sorted(set(prev.get("fresh") or []) | set(held["fresh"]))
                    for k, v in (prev.get("by_source") or {}).items():
                        held["by_source"][k] = held["by_source"].get(k, 0) + v
                    held["refused"] += prev.get("refused") or 0
                store.set_state(f"heldimport:{handle}", held)
            else:
                announce_import(bot, person, held, now)
        for f in claimed:
            _remove(f)
        shutil.rmtree(work, ignore_errors=True)
        print(f"import: done, {len(fresh)} new items, {row['seconds']} s, "
              f"{len(new_ids) / max(row['seconds'], 1e-9):.0f} items/s", file=sys.stderr)
        return row


def _mtime(path):
    if os.path.isdir(path):
        times = [os.path.getmtime(path)]
        for root, _, files in os.walk(path):
            times += [os.path.getmtime(os.path.join(root, f)) for f in files]
        return max(times)
    return os.path.getmtime(path)


def _remove(path):
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    elif os.path.exists(path):
        os.remove(path)


IMPORT_COLS = ("handle", "at", "status", "sources", "library", "old_library", "counts", "new_counts", "estimate_usd",
               "cost_usd", "error", "seconds", "work")


def _add_import(store, row):
    vals = {k: row.get(k) for k in IMPORT_COLS}
    if row.get("id"):
        sets = ", ".join(f"{k}=?" for k in vals)
        store.x(f"UPDATE imports SET {sets} WHERE id=?", (*vals.values(), row["id"]))
        return row["id"]
    return store.x(f"INSERT INTO imports({','.join(vals)}) VALUES({','.join('?' * len(vals))})",
                   tuple(vals.values())).lastrowid


def announce_import(bot, person, held, now):
    """The import's one message (counts) and the new_items answers on the items it added."""
    h = person["handle"]
    answers, nothing, ended = run_new_items(bot, person, set(held.get("fresh") or []), now)
    msg = T.import_done(dict(held.get("by_source") or {}), held.get("totals") or {}, refused=held.get("refused") or 0)
    if nothing:   # at most once per import
        msg += "\n" + T.nothing_new_matched(nothing)
    if ended:
        msg += "\n" + T.new_items_ended(ended)
    bot.send(h, msg)
    for r, spec, m, run_id, after in answers:
        _deliver_new(bot, person, r, spec, m, run_id, after)


# ---------- new_items rules ----------
def run_new_items(bot, person, new_ids, now):
    """Each active new_items rule of the person runs once, on the items the import added. Returns (answers to send,
    goals of the rules where nothing new matched, goals of the rules that ended because their end date passed). Snooze
    and the budget are respected and recorded."""
    from .texts import LAST_SEND
    h = person["handle"]
    answers, nothing, ended = [], [], []
    if person.get("paused"):
        return answers, nothing, ended
    for r in bot.store.rules(h, statuses=("active",)):
        spec = RuleSpec.model_validate(r["spec"])
        if spec.when.type != "new_items" or spec.content.source not in ("library", "recent"):
            continue
        if spec.when.until and now.astimezone(ZoneInfo(person["timezone"])).date().isoformat() > spec.when.until:
            bot.store.set_slot(r["id"], None, "done")
            ended.append(spec.content.goal)   # the import message says so
            continue
        snooze = person.get("snooze_until")
        if snooze and now < datetime.fromisoformat(snooze):
            bot.store.add_run(handle=h, rule_id=r["id"], kind="scheduled", status="snoozed", at=now_iso(now))
            continue
        if not new_ids:
            nothing.append(spec.content.goal)
            continue
        if bot._over_cap(person):
            bot.store.add_run(handle=h, rule_id=r["id"], kind="scheduled", status="over_cap", at=now_iso(now))
            continue
        msg, run_id, n = bot.run(person, spec, "scheduled", rule_id=r["id"], request_text=r.get("text"),
                                 only_ids=set(new_ids))
        bot.store.update_rule(r["id"], last_run_at=now_iso(now))
        if bot._run_failed(run_id):
            continue
        if not n:
            bot.store.x("UPDATE runs SET status='none' WHERE id=?", (run_id,))
            nothing.append(spec.content.goal)
            continue
        after = ""
        if spec.when.max_sends:
            sent = bot.store.one("SELECT COUNT(*) n FROM runs WHERE rule_id=? AND kind='scheduled' AND status IN "
                                 "('sent','none_sent','unknown')", (r["id"],))["n"] + 1
            if sent >= spec.when.max_sends:
                bot.store.set_slot(r["id"], None, "done")
                after = "\n" + LAST_SEND
        answers.append((r, spec, msg, run_id, after))
    return answers, nothing, ended


def _deliver_new(bot, person, r, spec, msg, run_id, after):
    try:
        bot.deliver(person, spec, msg, run_id, kind="scheduled", rule_id=r["id"], slot=now_iso(bot.clock()),
                    request_text=r.get("text"), after=after)
    except Exception as e:  # noqa: BLE001
        bot.store.x("DELETE FROM deliveries WHERE run_id=?", (run_id,))
        bot.store.x("UPDATE runs SET status='send_failed', error=? WHERE id=?", (type(e).__name__, run_id))
        return
    bot.store.x("UPDATE runs SET status='sent' WHERE id=?", (run_id,))


# ---------- library_status ----------
def _day(dt, tz):
    return dt.astimezone(ZoneInfo(tz)).strftime("%A %-d %B")


def _ago(days):
    return "today" if days == 0 else "yesterday" if days == 1 else f"{days} days ago" if days > 0 else \
        f"in {-days} days"


def library_status(bot, person, now):
    """The reply to "did my export come in?": when the last export came in, items by source, how old the newest item
    is, when the next export is due (the reminder rule, else the last import plus the platform's interval), and the
    export links. Code works out every number."""
    h, tz = person["handle"], person["timezone"]
    today = now.astimezone(ZoneInfo(tz)).date()
    imp = bot.store.one("SELECT * FROM imports WHERE handle=? AND status='done' ORDER BY id DESC LIMIT 1", (h,))
    last = None
    last_at = None
    if imp:
        last_at = datetime.fromisoformat(imp["at"])
        new = json.loads(imp["new_counts"] or "{}")
        n = sum(new.values())
        days = (today - last_at.astimezone(ZoneInfo(tz)).date()).days
        last = (f"Your last export came in on {_day(last_at, tz)} ({_ago(days)}), with {n} new "
                f"{'item' if n == 1 else 'items'}.")
    view = bot.view(person["library"])
    counts = Counter(it.platform for it in view.items.values())
    counts = {p: counts[p] for p in ("instagram", "youtube") if counts.get(p)}
    dates = [max(it.dates.values())[:10] for it in view.items.values() if it.dates]
    newest = None
    if dates:
        d = datetime.fromisoformat(max(dates)).date()
        newest = f"The newest thing in it is from {d.strftime('%-d %B %Y')} ({_ago((today - d).days)})."
    due = []
    for platform in counts:
        rule = next((r for r in bot.store.rules(h, statuses=("active",))
                     if (r["spec"].get("content") or {}).get("source") == "note"
                     and str((r["spec"].get("content") or {}).get("text") or "").startswith(REMINDER_OPENING[platform])),
                    None)
        if rule and rule.get("next_run_at"):
            at = datetime.fromisoformat(rule["next_run_at"])
            due.append(f"your next {T.PLATFORM_NAMES[platform]} export is due {_day(at, tz)}, and I'll remind you")
            continue
        base = last_at.astimezone(ZoneInfo(tz)).date() if last_at else \
            (datetime.fromisoformat(max(dates)).date() if dates else today)
        when = base + timedelta(days=config.EXPORT_EVERY_DAYS[platform])
        word = "was due" if when < today else "is due"
        due.append(f"your next {T.PLATFORM_NAMES[platform]} export {word} around {when.strftime('%A %-d %B')}")
    next_due = (T.cap_first("; ".join(due)) + ".") if due else "Send me a new export whenever you like."
    links = [(p, EXPORT_LINKS[p]) for p in counts]
    return T.library_status_message(last, counts, newest, next_due, links)


# ---------- the export routine (for onboarding) ----------
def export_routine(platforms=("instagram", "youtube"), tester=False):
    """The export steps, per platform, for the person to follow once and then whenever they are reminded.

    Returns {platform: {"name", "link", "steps": [str], "tick": [str], "never": [str], "where": str, "every": str,
    "every_days": int, "automatic": str, "not_automatic": str}}. Official links only (Instagram's Accounts Center
    export page, Google Takeout); the choices to tick, never Messages; where the file must go: the upload box on the test
    page, or for a real tester (tester=True) the route the research note recommends, a Google Drive folder shared with
    the bot's inbox account, which a founder still moves into the inbox by hand. No step needs a password from us, no
    logged-in automation. Some menu labels come from community guides, not Google's or Meta's own pages."""
    inbox = config.INBOX_EMAIL or "the bot's inbox account (the founders give you the address)"
    upload = "Put the zip in the upload box on the test page. I add it by myself within a few minutes."
    drive = (f"Share that Google Drive folder with {inbox} as a Viewer. Picking files up from Drive isn't automatic "
             "yet: a founder moves each new file into your inbox, and I add it from there.")
    automatic = ("Once the file is in your inbox, I add it, switch to your updated library, tell you what's new and run "
                 "your \"when I save something new\" rules. Nobody types a command.")
    out = {}
    if "instagram" in platforms:
        out["instagram"] = {
            "name": "Instagram", "link": EXPORT_LINKS["instagram"],
            "tick": ["Saved", "Likes", "Followers and following", "Ads and topics"],
            "never": ["Messages"],
            "steps": [
                f"Open {EXPORT_LINKS['instagram']} (Instagram's own export page, in Accounts Center).",
                "Choose to download your information, pick your Instagram account, and choose only some of it.",
                "Tick Saved, Likes, Followers and following, and Ads and topics. Leave Messages unticked.",
                ("Choose Google Drive as where it goes, " if tester else "Choose to download it to your device, ")
                + "with date range All time, format JSON (not HTML) and media quality Low.",
                "Submit. Instagram tells you when the file is ready; it can take a while."
                + ("" if tester else " Then download the zip."),
            ],
            "where": drive if tester else upload,
            "every": "every 4 weeks", "every_days": config.EXPORT_EVERY_DAYS["instagram"],
            "automatic": automatic,
            "not_automatic": ("Asking Instagram for the export and putting the file in your inbox. A repeating "
                              "Instagram export isn't confirmed for US accounts, so I remind you every 4 weeks."),
        }
    if "youtube" in platforms:
        out["youtube"] = {
            "name": "YouTube", "link": EXPORT_LINKS["youtube"],
            "tick": ["YouTube and YouTube Music: history, playlists and subscriptions", "history as JSON"],
            "never": ["every other Google product"],
            "steps": [
                "Check that YouTube watch history is on for the Google account you watch on: without it the export "
                "is empty.",
                f"On a computer, open {EXPORT_LINKS['youtube']} (Google Takeout).",
                "Click Deselect all, then tick YouTube and YouTube Music.",
                "Under All YouTube data included, keep only history, playlists and subscriptions. Under Multiple "
                "formats, set history to JSON.",
                ("Next step: choose Add to Drive, " if tester else "Next step: choose to get a download link by email, ")
                + "Export every 2 months for 1 year, file type .zip, and the largest size.",
                "Create the export. Google emails you when it's ready" + ("." if tester else "; download the zip."),
            ],
            "where": drive if tester else upload,
            "every": "every 2 months", "every_days": config.EXPORT_EVERY_DAYS["youtube"],
            "automatic": automatic,
            "not_automatic": ("Google repeats the export every 2 months for a year, but the file still has to reach "
                              "your inbox, so I remind you when each one is due."),
        }
    return out


def routine_text(routine):
    """The routine as one message: per platform its steps, where the file goes, then what is automatic and what not."""
    lines = []
    for p in ("instagram", "youtube"):
        r = routine.get(p)
        if not r:
            continue
        lines.append(f"{r['name']}, {r['every']}:")
        lines += [f"{i}. {s}" for i, s in enumerate(r["steps"], 1)]
        lines.append(f"{len(r['steps']) + 1}. {r['where']}")
        lines.append("")
    any_r = next(iter(routine.values()), None)
    if any_r:
        low = lambda x: x[0].lower() + x[1:]   # noqa: E731
        lines.append("What happens by itself: " + low(any_r["automatic"]))
        lines.append("What doesn't: " + " ".join(low(r["not_automatic"]) if i == 0 else r["not_automatic"]
                                                 for i, r in enumerate(routine.values())))
    return "\n".join(lines).strip()


def reminder_spec(platform, now, tz, tester=False):
    """A repeating plain reminder (source note) for one platform: every 4 weeks for Instagram (on today's weekday),
    every 2 months for YouTube (on today's day of the month, 28 at most), at 10am, the first one an interval from now."""
    local = now.astimezone(ZoneInfo(tz)).date()
    where = "put it in the Drive folder you shared" if tester else "put the zip in the upload box"
    if platform == "instagram":
        text = (f"{REMINDER_OPENING['instagram']}: open {EXPORT_LINKS['instagram']}, ask for Saved, Likes, Followers "
                f"and following, and Ads and topics as JSON, all time, no Messages. Then {where}.")
        when = {"type": "schedule", "days": [local.strftime("%a").upper()[:3]], "every_weeks": 4, "times": ["10:00"],
                "start": (local + timedelta(days=28)).isoformat()}
    else:
        text = (f"{REMINDER_OPENING['youtube']}: open {EXPORT_LINKS['youtube']} on a computer, pick only YouTube "
                f"(history, playlists, subscriptions; history as JSON) and make a .zip. Then {where}.")
        day = min(local.day, 28)
        y, m = (local.year, local.month + 2) if local.month <= 10 else (local.year + 1, local.month - 10)
        when = {"type": "schedule", "every_months": 2, "month_days": [day], "times": ["10:00"],
                "start": local.replace(year=y, month=m, day=day).isoformat()}
    return RuleSpec.model_validate({"when": when, "content": {"source": "note", "text": text}})


def offer_export_routine(bot, handle, platforms=None, tester=False, now=None):
    """For onboarding: the export steps for the person's platforms (default: the ones in their library) and an offer
    of the reminder rules, which they confirm like any rule (a pending preview; "yes" starts them all, "no" none).
    Returns the message text; the caller sends it. Nothing starts until they say yes."""
    person = bot.store.person(handle)
    now = now or bot.clock()
    if platforms is None:
        platforms = sorted(bot.view(person["library"]).platforms() & {"instagram", "youtube"})
    platforms = [p for p in (platforms or ()) if p in EXPORT_LINKS] or ["instagram", "youtube"]   # only these two
    routine = export_routine(platforms, tester=tester)
    specs = [(p, reminder_spec(p, now, person["timezone"], tester=tester)) for p in ("instagram", "youtube")
             if p in routine]
    first, *more = specs
    bot.store.set_pending(handle, "confirm_rule", {
        "text": f"export reminders ({first[0]})", "spec": first[1].stored(), "run_id": None,
        "more": [{"text": f"export reminders ({p})", "spec": s.stored()} for p, s in more]}, at=now)
    every = T._and([f"every {'4 weeks' if p == 'instagram' else '2 months'} for {T.PLATFORM_NAMES[p]}"
                    for p, _ in specs])
    return (routine_text(routine) + f"\n\nShall I remind you when the next export is due, {every}? Reply YES to "
            "start the reminders, or tell me what to change.")
