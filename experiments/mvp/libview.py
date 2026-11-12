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
                 "watch_count")

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
        self.media = pd.get("media_kind")
        self.kinds = set(raw.get("interaction_kinds") or [])
        self.dates = {}  # kind -> latest ISO date of that kind
        self.collections = [c for c in pd.get("collections") or [] if c]
        self.watch_count = pd.get("watch_count") or 0

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
        with open(LIB.p(self.lib, "corpus", "items.jsonl"), encoding="utf-8") as f:
            for line in f:
                raw = json.loads(line)
                if LIB.is_friend(raw):
                    self.friends += 1
                    continue
                self.items[raw["id"]] = Item(raw)
        path = LIB.p(self.lib, "corpus", "interactions.jsonl")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    r = json.loads(line)
                    it = self.items.get(r.get("item_id"))
                    if it is None or not r.get("at"):
                        continue
                    k = r.get("kind")
                    if r["at"] > it.dates.get(k, ""):
                        it.dates[k] = r["at"]

    def get(self, item_id):
        return self.items.get(item_id)

    def platforms(self):
        return {it.platform for it in self.items.values()}
