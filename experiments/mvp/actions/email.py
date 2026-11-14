"""PROTOTYPE ONLY - email.send (DESIGN.md sections 6 and 11; the checked research note on outputs, section 3).

Only to the person's own address, and only once they confirmed it with the 6-digit code sent to it (outputs.py). The
body is the same checked answer as the chat reply, as plain text plus simple HTML (render.email_bodies), with the
calendar link and the .ics file when calendar.add ran before it.

SMTP settings come from the environment (MVP_SMTP_HOST, MVP_SMTP_PORT, MVP_SMTP_USER, MVP_SMTP_PASSWORD,
MVP_SMTP_FROM), read at each send and never printed. Port 465 is SSL; any other port uses STARTTLS. Without SMTP, or
when sending fails (a revoked app password, a timeout), the email is written as an .eml file to MVP_HOME/outbox/ and
the reply says plainly where it is. Every answer email is also kept there as an .eml file, so the Outbox panel can
show it; a code email that SMTP sent is only listed (the code is not left in a file).
"""
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from .. import config
from ..render import email_bodies, pick_parts
from .base import Outcome, outbox_reachable, where_outbox, write_outbox

DOMAIN = "digest-bot.invalid"


def smtp_settings():
    """The SMTP settings from the environment, or None when no host is set."""
    host = os.environ.get("MVP_SMTP_HOST")
    if not host:
        return None
    return {"host": host, "port": int(os.environ.get("MVP_SMTP_PORT") or 587),
            "user": os.environ.get("MVP_SMTP_USER") or None, "password": os.environ.get("MVP_SMTP_PASSWORD") or None,
            "from": os.environ.get("MVP_SMTP_FROM") or os.environ.get("MVP_SMTP_USER") or f"bot@{DOMAIN}"}


def _sender():
    s = smtp_settings()
    return (s or {}).get("from") or os.environ.get("MVP_SMTP_FROM") or f"bot@{DOMAIN}"


def build_message(to, subject, text, html=None, attach=()):
    m = EmailMessage()
    m["Subject"] = " ".join(str(subject).split())[:150]   # a title with a line break never breaks the header
    m["From"] = formataddr((config.BOT_NAME, _sender()))
    m["To"] = to
    m["Date"] = formatdate(localtime=False)
    m["Message-ID"] = make_msgid(domain=DOMAIN)
    m.set_content(text)
    if html:
        m.add_alternative(html, subtype="html")
    for filename, path, maintype, subtype in attach:
        with open(path, "rb") as f:
            m.add_attachment(f.read(), maintype=maintype, subtype=subtype, filename=filename)
    return m


def _smtp_send(s, m):
    if s["port"] == 465:
        conn = smtplib.SMTP_SSL(s["host"], s["port"], timeout=config.SMTP_TIMEOUT, context=ssl.create_default_context())
    else:
        conn = smtplib.SMTP(s["host"], s["port"], timeout=config.SMTP_TIMEOUT)
        conn.starttls(context=ssl.create_default_context())
    try:
        if s["user"] and s["password"]:
            conn.login(s["user"], s["password"])
        conn.send_message(m)
    finally:
        try:
            conn.quit()
        except Exception:  # noqa: BLE001 - the message is out or it is not; closing is a nicety
            pass


def send(bot, handle, to, subject, text, html=None, attach=(), run_id=None, now=None, keep_sent=True,
         keep_unsent=True):
    """Sends one email (SMTP when configured) and keeps it in the outbox. Returns (via, path, error): via is "smtp"
    or "outbox"; error is the exception's type name when SMTP failed (nothing else of it is logged). With
    keep_sent=False an email that SMTP sent is only listed (subject "Sent"), not kept: a code that went out is not
    left in a file. With keep_unsent=False an email that was not sent is not written either, and via is "none"
    (review fix X8: a code email on a channel whose person cannot open the outbox)."""
    now = now or bot.clock()
    m = build_message(to, subject, text, html, attach)
    via, err = "outbox", None
    s = smtp_settings()
    if s:
        try:
            _smtp_send(s, m)
            via = "smtp"
        except Exception as e:  # noqa: BLE001 - e.g. an app password revoked by a password change: fall back
            err = type(e).__name__
            print(f"email: SMTP send failed ({err}); written to the outbox instead", file=sys.stderr)
    if via == "smtp" and not keep_sent:
        bot.store.add_outbox(handle, "email", "Your code (sent)", None, via, run_id=run_id, at=now)
        return via, None, err
    if via != "smtp" and not keep_unsent:
        return "none", None, err
    try:
        path = write_outbox(handle, subject, "eml", m.as_bytes(), now)
    except OSError as e:
        if via != "smtp":
            raise
        # review fix X9: the email went out; a copy that could not be kept (a full disk) never makes it "failed",
        # which would send it again
        print(f"email: sent, but the outbox copy failed ({type(e).__name__})", file=sys.stderr)
        path = None
    bot.store.add_outbox(handle, "email", m["Subject"], path, via, run_id=run_id, at=now)
    return via, path, err


def content(ctx):
    """The email for this answer: {subject, text, html, attach}. The same checked answer as the chat reply."""
    a = ctx.answer or {}
    if a.get("kind") == "picks" and not ctx.whole and ctx.picks:
        parts = []
        for p in ctx.picks:
            parts += pick_parts(p)
        subject = ctx.picks[0]["title"] if len(ctx.picks) == 1 else f"From your saves: {a.get('goal') or 'your picks'}"
    else:
        parts = a.get("parts") or []
        subject = {"note": f"Reminder: {a.get('goal') or ''}".strip(), "todos": "Your to-do list"}.get(
            a.get("kind"), f"From your saves: {a.get('goal') or 'your picks'}")
    links = [x for _, o in ctx.done for x in o.email_links]
    attach = [x for _, o in ctx.done for x in o.attach]
    footer = f"Sent by {config.BOT_NAME} because you asked for it, to your own address."
    text, html = email_bodies(parts, links, footer)
    return {"subject": subject[:150], "text": text, "html": html, "attach": attach}


def sent_line(bot, to, via, err, with_file=False):
    if via == "smtp":
        return f"I emailed this to you at {to}" + (", with a calendar file." if with_file else ".")
    where = where_outbox(bot)
    if err:
        return f"I couldn't send the email just now, so I put it {where} instead."
    return f"Email isn't connected here, so I didn't send it. The email is {where}."


def run(ctx, params):
    c = content(ctx)
    to, confirmed = ctx.store.email_of(ctx.handle)
    if not confirmed:
        return ctx.bot.email_waiting(ctx.person, c, ctx.run_id, ctx.now)
    via, path, err = send(ctx.bot, ctx.handle, to, c["subject"], c["text"], c["html"], c["attach"], ctx.run_id, ctx.now)
    return Outcome("done" if via == "smtp" else "outbox", line=sent_line(ctx.bot, to, via, err, bool(c["attach"])),
                   ref=path, detail={"via": via, "error": err})


def send_code(bot, handle, to, code, now):
    """The 6-digit code that confirms an address, sent to that address."""
    text = (f"Your code is {code}.\n\nText it to {config.BOT_NAME} to confirm this is your email address. It works for "
            f"{config.CODE_MINUTES} minutes.\n\nIf you didn't ask for this, you can ignore this email.")
    # review fix X8: a code that was not sent is left in a file only where the person can open it (the test page)
    return send(bot, handle, to, f"Your code: {code}", text, now=now, keep_sent=False,
                keep_unsent=outbox_reachable(bot))
