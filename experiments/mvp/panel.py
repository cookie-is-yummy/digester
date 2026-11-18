"""PROTOTYPE ONLY - the Connections panel of the test page (round 10, slice D; DESIGN.md section 17.D; the addendum's
section 2).

The founder tests on the web page. Typing a mailbox app password or an API token into a settings file was one reason
"it doesn't do it for me". The panel (beside the chat, never in it) takes those values and seals them with tokens.py
(settings.seal). A saved value is never shown again: the panel says only "set" or "not set". It is never logged, never
in a reply, a store table, an export, an error or an exception (errors carry a code). It can be removed.

    rows()                 -> [{name, label, secret, optional, state, words}] for the panel (no value, ever)
    save(name, value)      -> state word; raises PanelError(code) (codes in texts.PANEL_ERRORS)
    remove(name)           -> True when a sealed value was removed
    sending_state()        -> "on" | "need_both" | "outlook" | "host" | "nobody"

The values are the settings of the computer the bot runs on (the operator's), not any one person's: they are not in
"export my data" and "delete my data" leaves them (the panel's Remove does that). The chat still refuses secrets
(cancel.secret_reads); on the test page its line adds "On the test page, use the Connections panel."
"""
import re

from . import settings
from . import texts as T

MAX_LEN = 500
# (name, label, secret, optional, help) in the panel's order; every name is in settings.SEALABLE
FIELDS = (
    ("MVP_MAILBOX_ADDRESS", "Your email address (sending)", False, False,
     "The address I send from after you say \"send\". Gmail, iCloud or Fastmail."),
    ("MVP_MAILBOX_APP_PASSWORD", "Its app password", True, False,
     "Gmail: myaccount.google.com/apppasswords. Not your normal password."),
    ("MVP_TICKTICK_TOKEN", "TickTick API token", True, False, "TickTick › Settings › Account › API Token."),
    ("MVP_TICKTICK_PROJECT", "TickTick project id", False, True, "Optional. Empty: your Inbox."),
    ("MVP_TODOIST_TOKEN", "Todoist API token", True, False, "Todoist › Settings › Integrations › Developer."),
    ("MVP_TODOIST_PROJECT", "Todoist project id", False, True, "Optional. Empty: your Inbox."),
    ("MVP_WEBHOOK_URL", "Webhook address", True, False, "An https address from IFTTT, Make, Zapier or n8n."),
    ("MVP_YT_CLIENT_ID", "YouTube client id", False, False, "From your Google Cloud project (TVs and devices)."),
    ("MVP_YT_CLIENT_SECRET", "YouTube client secret", True, False, "From the same client."),
)
NAMES = tuple(f[0] for f in FIELDS)
_ADDR = re.compile(r"^[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")


class PanelError(Exception):
    """A value the panel would not keep. `code` only (texts.PANEL_ERRORS); never the value."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def rows():
    """The panel's rows: names, labels and states only."""
    out = []
    for name, label, secret, optional, help_ in FIELDS:
        try:
            state = settings.where(name)
        except Exception:  # noqa: BLE001 - the panel never breaks the page
            state = "unreadable"
        out.append({"name": name, "label": label, "secret": secret, "optional": optional, "help": help_,
                    "state": state or "unset", "words": T.PANEL_STATE.get(state, T.PANEL_STATE[None]),
                    "removable": state in ("sealed", "unreadable")})
    return out


def _clean(name, value):
    v = (value or "").strip()
    if not v:
        raise PanelError("empty")
    if len(v) > MAX_LEN:
        raise PanelError("too_long")
    if name == "MVP_MAILBOX_APP_PASSWORD":
        v = re.sub(r"\s+", "", v)   # Gmail shows app passwords in four groups of four
    elif re.search(r"\s", v):
        raise PanelError("spaces")
    if name == "MVP_MAILBOX_ADDRESS":
        if not _ADDR.match(v):
            raise PanelError("address")
        from .actions.mailbox import REFUSED
        if v.rsplit("@", 1)[1].lower() in REFUSED:
            raise PanelError("outlook")
        v = v.lower()
    if name == "MVP_WEBHOOK_URL" and not v.lower().startswith("https://"):
        raise PanelError("https")
    return v


def save(name, value):
    """Seals one value. Returns the new state word. Raises PanelError(code); nothing is kept on an error."""
    from . import tokens
    if name not in NAMES:
        raise PanelError("name")
    if settings.where(name) == "setting":
        raise PanelError("in_setting")   # the environment wins over a sealed value: saving here would do nothing
    v = _clean(name, value)
    if tokens.key_source() is None and not tokens.can_make_key():
        raise PanelError("no_key")
    try:
        settings.seal(name, v)
    except tokens.TokenKeyMissing:
        raise PanelError("no_key") from None
    except Exception:  # noqa: BLE001 - never the value in an error
        raise PanelError("failed") from None
    return settings.where(name) or "unset"


def remove(name):
    if name not in NAMES:
        raise PanelError("name")
    try:
        return settings.unseal(name)
    except Exception:  # noqa: BLE001
        raise PanelError("failed") from None


def sending_state():
    """Whether "send" sends from the operator's own address now, and if not, the one thing missing."""
    from . import config
    from .actions import mailbox
    if config.operator_source() is None and (config.OPERATOR or "").strip().lower() == "none":
        return "nobody"
    if mailbox.refused_domain():
        return "outlook"
    if not (settings.secret("MVP_MAILBOX_ADDRESS") and settings.secret("MVP_MAILBOX_APP_PASSWORD")):
        return "need_both"
    if mailbox.settings() is None:
        return "host"
    return "on"


def key_words():
    """Where the sealing key is, in words for the panel."""
    from . import tokens
    src = tokens.key_source()
    if src == "setting":
        return "Saved values are sealed with MVP_TOKEN_KEY."
    if src == "file":
        return "Saved values are sealed with a key kept in a file on this computer (only you can read it)."
    if tokens.can_make_key():
        return "The first value you save makes a key in a file on this computer (only you can read it)."
    return "No key: set MVP_TOKEN_KEY on this computer before saving anything here."


def state():
    """Everything the panel draws: rows, the sending line and the key line. No value, ever."""
    return {"rows": rows(), "sending": T.panel_sending(sending_state()), "key": key_words(),
            "youtube": youtube_words(), "browser": browser_words()}   # second merge of round 10 (seam e)


# ---------- second merge of round 10 (seam e): YouTube and the browser setting, in words, never a value ----------
def youtube_words():
    from .actions import youtube
    try:
        return T.PANEL_YT_ON if youtube.reachable() else T.PANEL_YT_OFF
    except Exception:  # noqa: BLE001 - the panel never breaks the page
        return T.PANEL_YT_OFF


def browser_words(chat=False):
    from . import browser
    try:
        return T.browser_setting(browser.mode(), browser.for_all(), browser.merchants(),
                                 practice=("streamly",) if browser.demo() else (), chat=chat)
    except Exception:  # noqa: BLE001
        return T.browser_setting("off", False, ())
# ---------- end second merge of round 10 ----------
