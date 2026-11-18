"""PROTOTYPE ONLY - the one way any module reads a secret (round 10, slice K; DESIGN.md section 17.K).

    from .settings import secret
    token = secret("MVP_TODOIST_TOKEN")      # the environment first, then the sealed store (tokens.py); else None

Only names in SEALABLE are ever looked up in the sealed store, and only they can be sealed (by the test page's
Connections panel, slice D, through seal()). Every other name is read from the environment only. A value is never
printed, logged, stored in the store's tables or put in an error: callers keep it in a local variable for one call.

page_status() is the line under the test page: the build, who the operator is, and whether sending, each connector,
the browser and the sign-in key are on (names and on/off only, never a value).
"""
import os

from . import config

# what the Connections panel may seal (slice D); anything else is the environment's alone
SEALABLE = ("MVP_MAILBOX_ADDRESS", "MVP_MAILBOX_APP_PASSWORD", "MVP_TICKTICK_TOKEN", "MVP_TICKTICK_PROJECT",
            "MVP_TODOIST_TOKEN", "MVP_TODOIST_PROJECT", "MVP_WEBHOOK_URL", "MVP_YT_CLIENT_ID", "MVP_YT_CLIENT_SECRET")


def secret(name):
    """The setting's value, stripped: the environment first, then (for SEALABLE names) the sealed store. None when
    unset, empty, or sealed but unreadable (a wrong or missing key): the caller then works as without it."""
    v = (os.environ.get(name) or "").strip()
    if v:
        return v
    if name not in SEALABLE:
        return None
    from . import tokens
    try:
        if not tokens.setting_sealed(name):
            return None
        return tokens.load_setting(name).strip() or None
    except tokens.TokenError:
        return None


def where(name):
    """'setting' (the environment), 'sealed', 'unreadable' (sealed, but the key does not open it), or None."""
    if (os.environ.get(name) or "").strip():
        return "setting"
    if name not in SEALABLE:
        return None
    from . import tokens
    if not tokens.setting_sealed(name):
        return None
    try:
        tokens.load_setting(name)
        return "sealed"
    except tokens.TokenError:
        return "unreadable"


def seal(name, value):
    """Seals one value for the Connections panel (slice D). Raises ValueError for a name outside SEALABLE or an empty
    value, tokens.TokenKeyMissing when no key can be had. The value is never returned again by anything but secret()."""
    if name not in SEALABLE:
        raise ValueError("name")
    v = (value or "").strip()
    if not v:
        raise ValueError("empty")
    from . import tokens
    tokens.save_setting(name, v)


def unseal(name):
    """Removes a sealed value (the panel's "remove"). True when there was one."""
    if name not in SEALABLE:
        raise ValueError("name")
    from . import tokens
    return tokens.delete_setting(name)


# ---------- the line under the test page ----------
def switches():
    """{name: on/off word} for the page footer: names and states only, never a value."""
    from . import connectors as C
    from . import tokens
    out = {"operator": {"setting": "set by MVP_OPERATOR", "page": "you, on this page"}.get(config.operator_source(),
                                                                                          "nobody")}
    try:
        from .actions import mailbox
        out["sending"] = "on" if mailbox.settings() is not None and config.operator_source() else "off"
    except Exception:  # noqa: BLE001 - the footer never breaks the page
        out["sending"] = "off"
    for key, con in C.CONNECTORS.items():
        label = {"mac": "Mac", "webhook": "webhook"}.get(key, con.name)
        try:
            out[label] = "on" if C.module(key).reachable() else "off"
        except Exception:  # noqa: BLE001
            out[label] = "off"
    b = (os.environ.get("MVP_BROWSER") or "").strip().lower()
    out["browser"] = b if b in ("operator", "vm") else "off"
    src = tokens.key_source()
    out["sign-in key"] = {"setting": "set", "file": "in a file here"}.get(src) or \
        ("made at the first sign-in" if tokens.can_make_key() else "not set")
    return out


def page_status():
    """'Build 1a2b3c4 (17 Nov 2026) · operator: you, on this page · sending: off · TickTick: off · ...'."""
    from . import texts as T
    return T.page_status_line(config.BUILD, switches())
