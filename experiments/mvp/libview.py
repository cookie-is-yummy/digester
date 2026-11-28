"""PROTOTYPE ONLY - read one library's own files: full captions, interaction kinds and the date of each kind.

The search engine returns item IDs; everything shown to the model or checked against comes from here, never from the
260-character display rows. Friends' posts are dropped (rule 5). Nothing here prints item text.
"""
import json
import os
import sys

from . import config

sys.path.insert(0, config.DEMO)
import library as LIB  # noqa: E402

KIND_LABEL = {"save": "saved", "collection": "in a collection", "share_self": "sent to yourself",
              "playlist": "in a playlist", "like": "liked", "watch": "watched", "view": "viewed",
              "share_friend": "sent to someone"}


class Item:
    __slots__ = ("id", "platform", "url", "caption", "first_line", "creator", "media", "kinds", "dates", "collections",
                 "watch_count", "video_id", "duration_s", "raw_caption",
                 # ---------- round 10, slice S: the derived caption mark (captionmark.py; None until its file exists)
                 "caption_mark", "caption_reasons", "caption_fp",
                 # the brain's read tools (toolfix 7): an Instagram account's display name, beside its handle
                 "display")

    def __init__(self, raw):
        pd = raw.get("platform_data") or {}
        self.id = raw["id"]
        self.platform = raw.get("platform")
        self.url = raw.get("source_url")
        self.caption = " ".join((raw.get("caption") or "").split())
        self.first_line = next((" ".join(l.split()) for l in (raw.get("caption") or "").splitlines() if l.strip()), "")
        handle = (pd.get("owner_handle") or "").strip().lstrip("@")
        name = (pd.get("owner_name") or "").strip()
        self.creator = ("@" + handle if handle and self.platform == "instagram" else (name or handle)) or None
        # toolfix 7: an Instagram row is named by its handle (`creator`, its key everywhere); the account's own name,
        # when the export has one, is kept beside it for the brain's channel rows
        self.display = name if self.platform == "instagram" and handle and name else None
        self.media = pd.get("media_kind")
        self.kinds = set(raw.get("interaction_kinds") or [])
        self.dates = {}  # kind -> latest ISO date of that kind
        self.collections = [c for c in pd.get("collections") or [] if c]
        self.watch_count = pd.get("watch_count") or 0
        self.video_id = pd.get("video_id") if self.platform == "youtube" else None
        self.duration_s = pd.get("duration_s") if isinstance(pd.get("duration_s"), (int, float)) else None
        # the caption with its line breaks, for the details step (lists are lines); `caption` is one line
        self.raw_caption = raw.get("caption") or ""
        # ---------- round 10, slice S: filled from <library>/marks/ by captionmark.load_into ----------
        self.caption_mark, self.caption_reasons, self.caption_fp = None, (), None
        # ---------- end round 10, slice S ----------

    def how(self):
        order = ["save", "collection", "share_self", "playlist", "like", "watch", "view"]
        return [KIND_LABEL[k] for k in order if k in self.kinds]

    def kept_on(self):
        """The date the person kept it: the latest save-like action, else the latest of any action."""
        for k in ("save", "collection", "share_self", "playlist", "like", "watch", "view"):
            if self.dates.get(k):
                return self.dates[k][:10]
        return None


class LibraryView:
    def __init__(self, lib):
        self.lib = os.path.abspath(lib)
        manifest = LIB.read_json(LIB.p(self.lib, "library.json"), {}) or {}
        if any("followers" in str(w).lower() for w in manifest.get("warnings") or []):
            raise RuntimeError("this library was imported without the followers and following lists, so friends' "
                               "posts cannot be left out (rule 5); redo the Instagram export with them")
        self.items = {}
        self.friends = 0
        # toolfix 8: a friend's post is never in the view (rule 5); only its id, platform and media kind are kept, and
        # its interactions' kinds and times below, so a result can say how many it left out in its own window
        friend = {}
        self.friend_events = []   # (friend post id, kind, ISO time, platform, media kind)
        with open(LIB.p(self.lib, "corpus", "items.jsonl"), encoding="utf-8") as f:
            for line in f:
                raw = json.loads(line)
                if LIB.is_friend(raw):
                    self.friends += 1
                    friend[raw.get("id")] = (raw.get("platform"), (raw.get("platform_data") or {}).get("media_kind"))
                    continue
                self.items[raw["id"]] = Item(raw)
        path = LIB.p(self.lib, "corpus", "interactions.jsonl")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    r = json.loads(line)
                    it = self.items.get(r.get("item_id"))
                    if it is None and r.get("item_id") in friend and r.get("at"):
                        pf = friend[r["item_id"]]
                        self.friend_events.append((r["item_id"], r.get("kind"), r["at"], pf[0], pf[1]))
                        continue
                    if it is None or not r.get("at"):
                        continue
                    k = r.get("kind")
                    if r["at"] > it.dates.get(k, ""):
                        it.dates[k] = r["at"]
        # ---------- round 10, slice S: the caption marks of this build, when their file exists (never built here:
        # a miss would hold up the first answer; refresh and the bot's start build it) ----------
        from . import captionmark
        captionmark.load_into(self)
        # ---------- end round 10, slice S ----------

    def get(self, item_id):
        return self.items.get(item_id)

    def platforms(self):
        return {it.platform for it in self.items.values()}
