"""PROTOTYPE ONLY - mailbox.draft: a real draft in the operator's own Drafts folder (round 9, slice A, A5; DESIGN.md
section 16.A; amendment A-013, Proposed).

A draft sends nothing, so it needs no "send" (confirm="never"); it is still operator only, off unless the same
environment settings as mailbox.send are set (MVP_MAILBOX_ADDRESS, MVP_MAILBOX_APP_PASSWORD; MVP_MAILBOX_IMAP_HOST and
_PORT override the defaults by domain). The mailbox is never read: this module only ever does LOGIN, LIST (to find the
folder flagged \\Drafts), APPEND to that folder with the \\Draft flag, and, for "undo", SELECT of that one folder, UID
STORE \\Deleted and UID EXPUNGE of the one UID the server gave back (UIDPLUS APPENDUID), then LOGOUT. It never
FETCHes, SEARCHes or EXAMINEs, and never SELECTs any other folder. A test records every command against this list.
"""
import imaplib
import re
import ssl
import time

from . import mailbox
from .base import Outcome

IMAP_DEFAULTS = {"gmail.com": ("imap.gmail.com", 993), "googlemail.com": ("imap.gmail.com", 993),
                 "icloud.com": ("imap.mail.me.com", 993), "me.com": ("imap.mail.me.com", 993),
                 "mac.com": ("imap.mail.me.com", 993), "fastmail.com": ("imap.fastmail.com", 993)}
FALLBACK_NAMES = ("Drafts", "[Gmail]/Drafts", "INBOX.Drafts", "Draft", "INBOX/Drafts")
TIMEOUT = 20
_LIST_LINE = re.compile(rb'^\((?P<flags>[^)]*)\)\s+(?:"[^"]*"|NIL)\s+(?P<name>"(?:[^"\\]|\\.)*"|\S+)\s*$')


class DraftError(Exception):
    """kind: "auth" (sign-in refused), "reach" (no connection), "folder" (no Drafts folder), "server" (the server
    said no). Never carries the password."""

    def __init__(self, kind):
        super().__init__(kind)
        self.kind = kind


def settings():
    import os
    s = mailbox.settings()
    if s is None or mailbox.refused_domain():
        return None
    host, port = IMAP_DEFAULTS.get(mailbox._domain(s["address"]), (None, None))
    host = os.environ.get("MVP_MAILBOX_IMAP_HOST") or host
    port = int(os.environ.get("MVP_MAILBOX_IMAP_PORT") or port or 993)
    if not host:
        return None
    return dict(s, imap_host=host, imap_port=port)


def _quote(name):
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _connect(s):
    try:
        conn = imaplib.IMAP4_SSL(s["imap_host"], s["imap_port"], ssl_context=ssl.create_default_context(),
                                 timeout=TIMEOUT)
    except (OSError, imaplib.IMAP4.error):
        raise DraftError("reach") from None
    try:
        conn.login(s["address"], s["password"])
    except imaplib.IMAP4.error:
        _bye(conn)
        raise DraftError("auth") from None
    except OSError:
        raise DraftError("reach") from None
    return conn


def _bye(conn):
    try:
        conn.logout()
    except Exception:  # noqa: BLE001 - closing is a nicety
        pass


def drafts_folder(lines):
    """The folder the server flags \\Drafts in a LIST answer, else the first usual name it lists, else None."""
    names = []
    for raw in lines or []:
        if not isinstance(raw, bytes):
            continue
        m = _LIST_LINE.match(raw.strip())
        if not m:
            continue
        name = m.group("name")
        if name.startswith(b'"'):
            name = re.sub(rb'\\(.)', rb'\1', name[1:-1])
        name = name.decode("utf-8", "replace")
        if b"\\drafts" in m.group("flags").lower():
            return name
        names.append(name)
    return next((n for n in FALLBACK_NAMES if n in names), None)


def append_draft(s, msg_bytes):
    """APPENDs one message with the \\Draft flag to the Drafts folder. Returns (folder, uid or None)."""
    conn = _connect(s)
    try:
        typ, lines = conn.list()
        folder = drafts_folder(lines if typ == "OK" else [])
        if not folder:
            raise DraftError("folder")
        typ, data = conn.append(_quote(folder), r"(\Draft)", imaplib.Time2Internaldate(time.time()), msg_bytes)
        if typ != "OK":
            raise DraftError("server")
        m = re.search(rb"APPENDUID\s+\d+\s+(\d+)", b" ".join(x for x in data or [] if isinstance(x, bytes)))
        return folder, (m.group(1).decode() if m else None)
    except OSError:
        raise DraftError("reach") from None
    finally:
        _bye(conn)


def delete_draft(s, folder, uid):
    """'undo': marks the one message the bot appended as deleted and expunges that UID only, in that folder only."""
    conn = _connect(s)
    try:
        typ, _ = conn.select(_quote(folder))
        if typ != "OK":
            raise DraftError("folder")
        typ, _ = conn.uid("STORE", uid, "+FLAGS", r"(\Deleted)")
        if typ != "OK":
            raise DraftError("server")
        typ, _ = conn.uid("EXPUNGE", uid)
        if typ != "OK":
            raise DraftError("server")
    except OSError:
        raise DraftError("reach") from None
    finally:
        _bye(conn)


def run(ctx, params):
    """An open draft card (params.draft_id) as it was last shown, or the answer (an email to the operator)."""
    from email.message import EmailMessage
    from email.utils import formatdate, make_msgid
    s = settings()
    if s is None:
        raise DraftError("reach")
    if params.draft_id is not None:
        row = ctx.store.draft(params.draft_id)
        if row is None or row["handle"] != ctx.handle:
            raise DraftError("server")
        to, subject, body = row.get("to_addr") or "", row.get("subject") or "", row.get("body") or ""
    else:
        from .email import content
        c = content(ctx)
        footer = "because you asked for it, to your own address."
        to, subject = s["address"], c["subject"]
        body = "\n".join(x for x in c["text"].split("\n") if not x.endswith(footer)).rstrip()
    m = EmailMessage()
    m["Subject"] = " ".join(subject.split())[:150]
    m["From"] = s["address"]
    if to:
        m["To"] = to
    m["Date"] = formatdate(localtime=False)
    m["Message-ID"] = make_msgid(domain=mailbox._domain(s["address"]) or "localhost")
    m.set_content(body)
    import email.policy
    folder, uid = append_draft(s, m.as_bytes(policy=email.policy.SMTP))
    return Outcome("done", detail={"folder": folder, "uid": uid, "to": to})
