"""PROTOTYPE ONLY - mailbox.send: the operator's own mailbox sends one draft after the word "send" (round 9, slice A,
W4; DESIGN.md section 16.A; amendment A-013, Proposed).

SMTP only: this module never imports an IMAP library, so it cannot open a folder or read a message. Settings come from the
environment only, read at each send and never printed or logged: MVP_MAILBOX_ADDRESS, MVP_MAILBOX_APP_PASSWORD,
MVP_MAILBOX_SMTP_HOST and MVP_MAILBOX_SMTP_PORT (defaults by the address's domain). Off unless the address and the app
password are both set; only for config.is_operator(handle) (the registry's who="operator").
"""
import email.policy
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from .base import Outcome

SMTP_DEFAULTS = {"gmail.com": ("smtp.gmail.com", 465), "googlemail.com": ("smtp.gmail.com", 465),
                 "icloud.com": ("smtp.mail.me.com", 587), "me.com": ("smtp.mail.me.com", 587),
                 "mac.com": ("smtp.mail.me.com", 587), "fastmail.com": ("smtp.fastmail.com", 465)}
# Outlook.com dropped app passwords (basic sign-in): refused at the start, never tried
REFUSED = ("outlook.com", "hotmail.com", "live.com", "msn.com")


def _domain(addr):
    return addr.rsplit("@", 1)[1].lower() if addr and "@" in addr else ""


def settings():
    """{address, password, host, port} from the environment, or None when the address or the app password is not
    set, or no host is known for the address's domain."""
    addr = (os.environ.get("MVP_MAILBOX_ADDRESS") or "").strip()
    pw = os.environ.get("MVP_MAILBOX_APP_PASSWORD") or ""
    if not addr or not pw or "@" not in addr:
        return None
    host, port = SMTP_DEFAULTS.get(_domain(addr), (None, None))
    host = os.environ.get("MVP_MAILBOX_SMTP_HOST") or host
    port = int(os.environ.get("MVP_MAILBOX_SMTP_PORT") or port or 465)
    if not host:
        return None
    return {"address": addr, "password": pw, "host": host, "port": port}


def refused_domain():
    """The address's domain when it is one that cannot be used (Outlook.com and friends), else None."""
    d = _domain(os.environ.get("MVP_MAILBOX_ADDRESS") or "")
    return d if d in REFUSED else None


TIMEOUT = 20   # seconds for each step with the mail server


class SendError(Exception):
    """A send that did not happen, or may have: `kind` is "auth" (535), "address" (550), "reach" (no connection,
    or a time-out before the message was handed over: nothing was sent) or "unknown" (a time-out or a dropped
    connection after the message was handed over: it may have gone). Never carries the password or the address."""

    def __init__(self, kind, code=None):
        super().__init__(kind)
        self.kind, self.code = kind, code


def build(row, sender):
    """The email exactly as the card showed it: From the operator's address, To the one recipient, the subject and
    the body of the version last shown."""
    m = EmailMessage()
    m["Subject"] = " ".join(str(row["subject"] or "").split())[:150]
    m["From"] = sender
    m["To"] = row["to_addr"]
    m["Date"] = formatdate(localtime=False)
    m["Message-ID"] = make_msgid(domain=_domain(sender) or "localhost")
    m.set_content(row["body"] or "")
    return m


def yes_token(ctx, params):
    """The token of what is about to leave: the draft's id, its version and the hash of its exact text now. A yes
    given to any other version (or text) does not match, so perform refuses it."""
    from ..drafts import exact_text
    from . import make_yes_token, text_hash
    row = ctx.store.draft(params.draft_id)
    if row is None or row["handle"] != ctx.handle:
        return "none"
    return make_yes_token(row["id"], row["version"], text_hash(exact_text(row["to_addr"], row["subject"],
                                                                          row["body"])))


def _send(s, m):
    """SMTP, step by step, so a failure before the message is handed over (nothing sent) is told apart from one
    after it (it may have gone)."""
    try:
        if s["port"] == 465:
            conn = smtplib.SMTP_SSL(s["host"], s["port"], timeout=TIMEOUT, context=ssl.create_default_context())
        else:
            conn = smtplib.SMTP(s["host"], s["port"], timeout=TIMEOUT)
            conn.starttls(context=ssl.create_default_context())
    except (OSError, smtplib.SMTPException):
        raise SendError("reach") from None
    try:
        try:
            conn.login(s["address"], s["password"])
        except smtplib.SMTPAuthenticationError as e:
            raise SendError("auth", getattr(e, "smtp_code", 535)) from None
        except (OSError, smtplib.SMTPException):
            raise SendError("reach") from None
        try:
            code, _ = conn.mail(s["address"])
            if code >= 400:
                raise SendError("reach", code)
            code, _ = conn.rcpt(m["To"])
            if code >= 400:
                raise SendError("address", code)
        except SendError:
            raise
        except (OSError, smtplib.SMTPException):
            raise SendError("reach") from None
        # DATA by hand (as smtplib.data does it): until the server says 354 nothing has been handed over
        try:
            conn.putcmd("data")
            code, _ = conn.getreply()
        except (OSError, smtplib.SMTPException):
            raise SendError("reach") from None
        if code != 354:
            raise SendError("reach", code)
        q = re.sub(rb"(?m)^\.", b"..", m.as_bytes(policy=email.policy.SMTP))
        if not q.endswith(b"\r\n"):
            q += b"\r\n"
        try:
            conn.send(q + b".\r\n")
            code, _ = conn.getreply()
        except (OSError, smtplib.SMTPException):
            raise SendError("unknown") from None   # handed over: it may have gone
        if code != 250:
            raise SendError("address" if 550 <= code < 560 else "reach", code)
    finally:
        try:
            conn.quit()
        except Exception:  # noqa: BLE001 - the message went or it did not; closing is a nicety
            pass


def run(ctx, params):
    """Sends the draft from the operator's own address. Reached only through perform, which has already checked
    that this is the operator and that the yes token matches this exact version. Returns Outcome("done") only once
    the server accepted the message (250 after DATA); a failure raises SendError."""
    s = settings()
    if s is None or refused_domain():
        raise SendError("reach")
    row = ctx.store.draft(params.draft_id)
    if row is None or row["handle"] != ctx.handle or not row["to_addr"]:
        raise SendError("address")
    _send(s, build(row, s["address"]))
    return Outcome("done", detail={"via": "mailbox"})
