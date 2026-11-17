"""PROTOTYPE ONLY - mailbox.send: the operator's own mailbox sends one draft after the word "send" (round 9, slice A,
W4; DESIGN.md section 16.A; amendment A-013, Proposed).

SMTP only: this module never imports imaplib, so it cannot open a folder or read a message. Settings come from the
environment only, read at each send and never printed or logged: MVP_MAILBOX_ADDRESS, MVP_MAILBOX_APP_PASSWORD,
MVP_MAILBOX_SMTP_HOST and MVP_MAILBOX_SMTP_PORT (defaults by the address's domain). Off unless the address and the app
password are both set; only for config.is_operator(handle) (the registry's who="operator").
"""
import os

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
