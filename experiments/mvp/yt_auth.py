"""PROTOTYPE ONLY - each person's own YouTube sign-in by Google's device flow (round 10, slice Y2; DESIGN.md section
17.Y; amendment A-015, Proposed).

No web page of ours is needed: "connect youtube" asks Google for a code (scope `https://www.googleapis.com/auth/youtube`
only, never `youtube.force-ssl`), the person types it at google.com/device on any phone or computer and presses Allow,
and the scheduler's tick asks Google for the tokens every `interval` seconds while the code lives (30 minutes). The
device code is sealed with tokens.py (connector "youtube_device"); state `ytdevice:<handle>` holds only the times and
the code the person types. The tokens are sealed per person (connector "youtube", issuer "google"); an access token is
renewed from the refresh token under tokens.lock, so two runs never refresh at once. A refresh Google refuses
(`invalid_grant`: the person removed our access) deletes the sign-in.

The client id and secret ("TVs and Limited Input devices" client of the founders' Google project) come only through
settings.secret: MVP_YT_CLIENT_ID, MVP_YT_CLIENT_SECRET. Nothing here logs or returns a token.
"""
from datetime import datetime, timedelta, timezone

from . import tokens
from .store import now_iso

SCOPE = "https://www.googleapis.com/auth/youtube"
DEVICE_URL = "https://oauth2.googleapis.com/device/code"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
CONNECTOR = "youtube"
DEVICE = "youtube_device"
ISSUER = "google"
EARLY = timedelta(seconds=60)   # an access token this close to its end is renewed first


def _err(code):
    from .actions.youtube import YtError
    return YtError(code)


def client():
    """(client id, client secret), or None when this bot has no Google client for YouTube."""
    from .settings import secret
    cid, sec = secret("MVP_YT_CLIENT_ID"), secret("MVP_YT_CLIENT_SECRET")
    return (cid, sec) if cid and sec else None


def connectable(store, handle):
    """True when this person could connect YouTube now (a client id and secret are set)."""
    return client() is not None


def connected(store, handle):
    """True when this person's YouTube sign-in is kept."""
    try:
        return tokens.exists(handle, CONNECTOR)
    except tokens.TokenError:
        return False


def _aware(now):
    now = now or datetime.now(timezone.utc)
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


# ---------- the device flow ----------
def start(store, handle, now):
    """Asks Google for a code. {"user_code", "minutes"}; raises YtError("not_set_up" | "no_key" | a request code)."""
    from .actions.youtube import request
    now = _aware(now)
    c = client()
    if c is None:
        raise _err("not_set_up")
    if tokens.key_source() is None and not tokens.can_make_key():
        raise _err("no_key")
    got = request("POST", DEVICE_URL, form={"client_id": c[0], "scope": SCOPE})
    dc, uc = got.get("device_code"), str(got.get("user_code") or "")
    if not dc or not uc or len(uc) > 20 or not all(ch.isalnum() or ch == "-" for ch in uc):
        raise _err("failed")
    life = min(int(got.get("expires_in") or 1800), 1800)
    interval = max(5, int(got.get("interval") or 5))
    try:
        tokens.save(handle, DEVICE, {"device_code": str(dc)}, issuer=ISSUER)
    except tokens.TokenKeyMissing:
        raise _err("no_key") from None
    store.set_state(f"ytdevice:{handle}", {"at": now_iso(now), "expires_at": now_iso(now + timedelta(seconds=life)),
                                           "interval": interval, "user_code": uc,
                                           "next_poll": now_iso(now + timedelta(seconds=interval))})
    return {"user_code": uc, "minutes": life // 60}


def waiting(store, handle, now):
    """The open device code's state, or None (an expired one is cleared)."""
    st = store.get_state(f"ytdevice:{handle}")
    if not st:
        return None
    if _aware(now) > datetime.fromisoformat(st["expires_at"]):
        end_device(store, handle)
        return None
    return st


def end_device(store, handle):
    store.set_state(f"ytdevice:{handle}", None)
    try:
        tokens.delete(handle, DEVICE)
    except tokens.TokenError:
        pass


def poll(store, handle, now, force=False):
    """One question to Google about the open code: "pending" | "connected" | "denied" | "expired" | "failed", or None
    when no code is open. Not before `next_poll` unless force (the person said "done")."""
    from .actions.youtube import YtError, request
    now = _aware(now)
    st = store.get_state(f"ytdevice:{handle}")
    if not st:
        return None
    if now > datetime.fromisoformat(st["expires_at"]):
        end_device(store, handle)
        return "expired"
    if not force and now < datetime.fromisoformat(st["next_poll"]):
        return "pending"
    c = client()
    try:
        dc = tokens.load(handle, DEVICE, issuer=ISSUER)["device_code"]
    except (tokens.TokenError, KeyError):
        end_device(store, handle)
        return "failed"
    if c is None:
        end_device(store, handle)
        return "failed"
    try:
        got = request("POST", TOKEN_URL, form={"client_id": c[0], "client_secret": c[1], "device_code": dc,
                                               "grant_type": DEVICE_GRANT})
    except YtError as e:
        if e.code in ("pending", "slow_down", "rate", "timeout", "server", "failed"):
            gap = st["interval"] + (5 if e.code == "slow_down" else 0)   # Google: slow_down adds 5 seconds
            store.set_state(f"ytdevice:{handle}", dict(st, interval=gap,
                                                       next_poll=now_iso(now + timedelta(seconds=gap))))
            return "pending"
        end_device(store, handle)
        return {"denied": "denied", "expired": "expired"}.get(e.code, "failed")
    granted = set(str(got.get("scope") or SCOPE).split())
    # exactly the one scope asked: never youtube.force-ssl or any wider grant kept, never a read-only one that would
    # fail at the first change
    if not got.get("access_token") or not got.get("refresh_token") or granted != {SCOPE}:
        end_device(store, handle)
        t = got.get("refresh_token") or got.get("access_token")
        if t:   # not kept: Google is asked to end it too (best effort)
            try:
                request("POST", REVOKE_URL, form={"token": t})
            except YtError:
                pass
        return "scope" if got.get("access_token") and granted != {SCOPE} else "failed"
    tokens.save(handle, CONNECTOR, {"access_token": got["access_token"], "refresh_token": got["refresh_token"],
                                    "expires_at": now_iso(now + timedelta(seconds=int(got.get("expires_in") or 3600))),
                                    "scope": SCOPE}, issuer=ISSUER)
    end_device(store, handle)
    return "connected"


# ---------- tokens ----------
def access_token(handle, now=None, force=False):
    """A live access token for this person (renewed from the refresh token when it is near its end, or `force`).
    Raises YtError("needs_signin") when there is no sign-in or Google refuses the refresh (the sign-in is deleted)."""
    from .actions.youtube import YtError, request
    now = _aware(now)
    try:
        with tokens.lock(handle, CONNECTOR):
            try:
                t = tokens.load(handle, CONNECTOR, issuer=ISSUER)
            except tokens.TokenError:
                raise _err("needs_signin") from None
            if not force and t.get("access_token") and \
                    datetime.fromisoformat(t["expires_at"]) - EARLY > now:
                return t["access_token"]
            c = client()
            if c is None:
                raise _err("needs_signin")
            try:
                got = request("POST", TOKEN_URL, form={"client_id": c[0], "client_secret": c[1],
                                                       "refresh_token": t["refresh_token"],
                                                       "grant_type": "refresh_token"})
            except YtError as e:
                if e.code in ("needs_signin", "refused", "client"):
                    tokens.delete(handle, CONNECTOR)
                    raise _err("needs_signin") from None
                raise
            if not got.get("access_token"):
                raise _err("failed")
            t = dict(t, access_token=got["access_token"],
                     expires_at=now_iso(now + timedelta(seconds=int(got.get("expires_in") or 3600))))
            if got.get("refresh_token"):   # Google may rotate it: the new one is written before anyone reads
                t["refresh_token"] = got["refresh_token"]
            tokens.save(handle, CONNECTOR, t, issuer=ISSUER)
            return t["access_token"]
    except tokens.TokenError:
        raise _err("needs_signin") from None


def disconnect(handle):
    """Asks Google to end our access and deletes the sign-in. True when Google confirmed (or nothing was kept)."""
    from .actions.youtube import YtError, request
    try:
        t = tokens.load(handle, CONNECTOR, issuer=ISSUER)
    except tokens.TokenError:
        t = None
    ok = True
    if t and (t.get("refresh_token") or t.get("access_token")):
        try:
            request("POST", REVOKE_URL, form={"token": t.get("refresh_token") or t.get("access_token")})
        except YtError:
            ok = False
    try:
        tokens.delete(handle, CONNECTOR)
        tokens.delete(handle, DEVICE)
    except tokens.TokenError:
        pass
    return ok


def forget(handle):
    """'delete my data': end Google's access too when it can (best effort; the files go with tokens.delete_all)."""
    try:
        if tokens.exists(handle, CONNECTOR):
            disconnect(handle)
    except Exception:  # noqa: BLE001 - deleting the person's data never stops on Google
        pass
