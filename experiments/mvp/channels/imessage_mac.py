"""PROTOTYPE ONLY - iMessage through the Messages app on a Mac (BRIEF-10 section 6, build days, founders only).

Sending: AppleScript tells Messages to send to a handle; the handle and the text are passed as arguments, never pasted
into the script. Receiving: polls ~/Library/Messages/chat.db (opened read-only) for rows above the last ROWID seen with
is_from_me = 0, so the bot never answers itself. On recent macOS the text is often only in the attributedBody blob,
which is decoded here. Tapbacks are rows with associated_message_type 2000-2005 that point at the message reacted to.
The terminal running the bot needs Full Disk Access (to read chat.db) and permission to control Messages.

Testing alone (self_handle): a founder texts their OWN number or Apple Account email in Messages, from the Mac or their
iPhone, and the bot answers in that same thread. No second phone is needed. In that thread the founder's messages are
rows written as sent (is_from_me = 1), sometimes with a received copy as well, so both are read and the copy is dropped.
Every bot reply there starts with BOT_MARK, and any text that starts with it is never treated as a message to the bot:
that is what stops the bot answering itself. This mode has only been tested against a fake database, not on a Mac.
"""
import os
import sqlite3
import subprocess
import time

from .base import Channel, Inbound, SendUncertain

CHAT_DB = os.path.expanduser("~/Library/Messages/chat.db")
SEND_SCRIPT = """
on run argv
    set theHandle to item 1 of argv
    set theText to item 2 of argv
    tell application "Messages"
        set svc to 1st account whose service type = iMessage
        try
            set target to participant theHandle of svc
        on error
            set target to buddy theHandle of svc
        end try
        send theText to target
    end tell
end run
"""
BOT_MARK = "🤖 "       # the first characters of every bot reply in a self-chat
SAME_TEXT_SECONDS = 20  # a sent row and its received copy arrive within this time
TAPBACK = {2000: "up", 2001: "up", 2002: "down", 2003: "up", 2004: "up"}  # love, like, dislike, laugh, emphasize


def decode_attributed_body(blob):
    """The plain text inside a typedstream NSAttributedString (the attributedBody column)."""
    if not blob:
        return None
    try:
        b = bytes(blob)
        if b"NSString" not in b:
            return None
        b = b.split(b"NSString", 1)[1][5:]
        if b[0] == 0x81:
            n = int.from_bytes(b[1:3], "little")
            b = b[3:3 + n]
        elif b[0] == 0x82:
            n = int.from_bytes(b[1:5], "little")
            b = b[5:5 + n]
        else:
            n = b[0]
            b = b[1:1 + n]
        return b.decode("utf-8", errors="replace")
    except (IndexError, ValueError):
        return None


def _target_guid(associated):
    """'p:0/GUID' or 'bp:GUID' -> GUID."""
    if not associated:
        return None
    return associated.split("/", 1)[1] if "/" in associated else associated.split(":", 1)[-1]


class MacMessagesChannel(Channel):
    name = "imessage_mac"
    link_previews = True    # one link per message, so Messages can show it as a card
    reply_to_unknown = False  # this is a founder's own account: people not set up get no reply at all

    def __init__(self, store, db_path=CHAT_DB, sender=None, self_handle=None):
        self.store = store
        self.db_path = db_path
        self.sender = sender or self._osascript
        self.self_handle = self_handle   # set: this person's messages to themselves are messages to the bot
        self._recent = {}                # text -> time last seen, to drop the received copy of a self-sent message
        if self.store.get_state("mac_last_rowid") is None:  # never answer old history
            self.store.set_state("mac_last_rowid", self._max_rowid())

    def _conn(self):
        return sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=2)

    def _max_rowid(self):
        with self._conn() as c:
            r = c.execute("SELECT MAX(ROWID) FROM message").fetchone()
            return r[0] or 0

    def receive(self):
        last = self.store.get_state("mac_last_rowid", 0)
        with self._conn() as c:
            rows = c.execute(
                "SELECT m.ROWID, m.guid, m.text, m.attributedBody, m.is_from_me, m.associated_message_type, "
                "m.associated_message_guid, h.id, "
                "(SELECT MAX(c.style) FROM chat_message_join j JOIN chat c ON c.ROWID = j.chat_id WHERE j.message_id = m.ROWID) "
                "FROM message m LEFT JOIN handle h ON m.handle_id = h.ROWID "
                "WHERE m.ROWID > ? ORDER BY m.ROWID LIMIT 200", (last,)).fetchall()
        out = []
        now = time.time()
        self._recent = {t: at for t, at in self._recent.items() if now - at < SAME_TEXT_SECONDS}
        for rowid, guid, text, body, from_me, assoc_type, assoc_guid, handle, style in rows:
            last = max(last, rowid)
            if not handle or style == 43:  # 43 = a group chat; only one-to-one chats reach the bot
                continue
            own_thread = bool(self.self_handle) and handle == self.self_handle
            if from_me and not own_thread:  # the bot's own sends, and the founder's ordinary messages to other people
                continue
            assoc_type = assoc_type or 0
            if 2000 <= assoc_type <= 2005:
                if assoc_type in TAPBACK and (guid, "tap") not in self._recent:
                    self._recent[(guid, "tap")] = now
                    out.append(Inbound(handle=handle, tapback=TAPBACK[assoc_type], tapback_ref=_target_guid(assoc_guid), ref=guid))
                continue
            if 3000 <= assoc_type <= 3005:  # a tapback removed
                continue
            body_text = (text if text else decode_attributed_body(body)) or ""
            body_text = body_text.replace("￼", "").strip()
            if not body_text or body_text.startswith(BOT_MARK.strip()):  # never answer a bot reply
                continue
            if own_thread:
                if body_text in self._recent:  # the received copy of a message already taken from its sent row
                    continue
                self._recent[body_text] = now
            out.append(Inbound(handle=handle, text=body_text, ref=guid))
        self.store.set_state("mac_last_rowid", last)
        return out

    def _osascript(self, handle, text):
        try:
            r = subprocess.run(["osascript", "-e", SEND_SCRIPT, handle, text], capture_output=True, timeout=30)
        except subprocess.TimeoutExpired:
            raise SendUncertain("timeout") from None
        if r.returncode != 0:  # never raise with the arguments: they hold the handle and the message
            raise RuntimeError(f"osascript failed with exit status {r.returncode}")

    def send(self, handle, text):
        before = self._max_rowid()
        if self.self_handle and handle == self.self_handle:
            text = BOT_MARK + text
        self.sender(handle, text)
        return self._own_guid(handle, before)

    def _own_guid(self, handle, after_rowid, wait=5.0):
        """The GUID of the row the send just wrote (the first own row to this person above the last row that existed
        before the send), so a later tapback maps to this message and never to an earlier one."""
        end = time.time() + wait
        while time.time() < end:
            with self._conn() as c:
                r = c.execute("SELECT m.guid FROM message m LEFT JOIN handle h ON m.handle_id = h.ROWID WHERE "
                              "m.is_from_me = 1 AND h.id = ? AND m.ROWID > ? ORDER BY m.ROWID LIMIT 1",
                              (handle, after_rowid)).fetchone()
            if r:
                return r[0]
            time.sleep(0.5)
        return None
