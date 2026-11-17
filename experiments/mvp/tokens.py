"""PROTOTYPE ONLY - sealed sign-ins and sealed settings (round 10, slice K; DESIGN.md section 17.K).

One AES-256-GCM file per (person, connector) at MVP_HOME/tokens/<sha256(handle)[:12]>/<connector>.json.enc (folder
0700, file 0600, written atomically). The additional data binds a file to its person, its connector and the issuer
that gave the token ("<handle hash>|<connector>|<issuer>"), so a file copied to another person or connector does not
open. Settings the test page's Connections panel keeps (an app password, a task app's token) are sealed the same way
under MVP_HOME/tokens/_settings/<NAME>.json.enc; settings.secret() reads them after the environment.

The key: MVP_TOKEN_KEY (32 random bytes, base64) when set. Otherwise a key is made once, the first time something is
sealed, in MVP_HOME/token.key (0600); a key file anyone else can read is refused. MVP_TOKEN_KEY_AUTO=0 never makes one
(then sealing refuses with TokenKeyMissing). Reading never makes a key.

Errors carry a code only, never a token, a value, a path or a handle:
  TokenKeyMissing(code)  unset (no key and none may be made) | bad (not 32 bytes of base64) | file_mode (the key file
                         can be read by others)
  TokenNotFound          nothing sealed for this person and connector
  TokenError(code)       unreadable (wrong key, a copied or changed file) | issuer (sealed for another issuer) |
                         name (a connector or setting name that is not a plain word)
"""
import base64
import binascii
import contextlib
import fcntl
import hashlib
import json
import os
import re
import shutil
import tempfile

from . import config

KEY_ENV = "MVP_TOKEN_KEY"
AUTO_ENV = "MVP_TOKEN_KEY_AUTO"
KEY_FILE = "token.key"
FORMAT = 1
SETTINGS_DIR = "_settings"
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class TokenError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class TokenKeyMissing(TokenError):
    pass


class TokenNotFound(TokenError):
    def __init__(self, code="not_found"):
        super().__init__(code)


# ---------- the key ----------
def key_path():
    return os.path.join(config.HOME, KEY_FILE)


def _decode_key(text):
    t = (text or "").strip()
    for dec in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            k = dec(t + "=" * (-len(t) % 4))
        except (binascii.Error, ValueError):
            continue
        if len(k) == 32:
            return k
    raise TokenKeyMissing("bad")


def key_source():
    """Where the key comes from now, without making one: 'setting' (MVP_TOKEN_KEY), 'file' (made here before), or
    None (none yet: one is made at the first seal unless MVP_TOKEN_KEY_AUTO=0)."""
    if (os.environ.get(KEY_ENV) or "").strip():
        return "setting"
    return "file" if os.path.exists(key_path()) else None


def can_make_key():
    return (os.environ.get(AUTO_ENV) or "1").strip() != "0"


def key(create=False):
    """The 32-byte key. create=True makes the key file when there is no key (once, 0600, never overwritten)."""
    v = (os.environ.get(KEY_ENV) or "").strip()
    if v:
        return _decode_key(v)
    p = key_path()
    if not os.path.exists(p):
        if not create or not can_make_key():
            raise TokenKeyMissing("unset")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        try:
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            fd = None   # made by another thread or process just now: read theirs
        if fd is not None:
            with os.fdopen(fd, "w") as f:
                f.write(base64.b64encode(os.urandom(32)).decode() + "\n")
                f.flush()
                os.fsync(f.fileno())
    if os.stat(p).st_mode & 0o077:
        raise TokenKeyMissing("file_mode")
    with open(p, encoding="ascii", errors="replace") as f:
        return _decode_key(f.read())


# ---------- where files go ----------
def handle_hash(handle):
    from .handler import norm_handle  # here, not at the top: handler imports a lot
    return hashlib.sha256(norm_handle(str(handle or "")).encode("utf-8")).hexdigest()


def root():
    return os.path.join(config.HOME, "tokens")


def _folder_of(handle):
    return os.path.join(root(), handle_hash(handle)[:12])


def _check_name(name):
    if not isinstance(name, str) or not _NAME.match(name):
        raise TokenError("name")
    return name


def _make_folder(folder):
    for d in (root(), folder):
        os.makedirs(d, mode=0o700, exist_ok=True)
        os.chmod(d, 0o700)


def _seal(folder, name, aad_owner, data, issuer):
    k = key(create=True)
    _make_folder(folder)
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    aad = f"{aad_owner}|{name}|{issuer}".encode()
    ct = AESGCM(k).encrypt(nonce, json.dumps(data, ensure_ascii=False).encode("utf-8"), aad)
    blob = json.dumps({"v": FORMAT, "iss": issuer, "n": base64.b64encode(nonce).decode(),
                       "c": base64.b64encode(ct).decode()})
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".seal-", suffix=".tmp")   # mkstemp makes it 0600
    try:
        with os.fdopen(fd, "w") as f:
            f.write(blob)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, os.path.join(folder, f"{name}.json.enc"))
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise


def _open(folder, name, aad_owner, issuer=None):
    p = os.path.join(folder, f"{name}.json.enc")
    if not os.path.exists(p):
        raise TokenNotFound()
    k = key(create=False)
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    try:
        with open(p, encoding="utf-8") as f:
            blob = json.load(f)
        iss = str(blob.get("iss") or "")
        nonce, ct = base64.b64decode(blob["n"]), base64.b64decode(blob["c"])
    except (OSError, ValueError, KeyError, TypeError, binascii.Error):
        raise TokenError("unreadable") from None
    if issuer is not None and issuer != iss:
        raise TokenError("issuer")
    try:
        raw = AESGCM(k).decrypt(nonce, ct, f"{aad_owner}|{name}|{iss}".encode())
    except (InvalidTag, ValueError):
        raise TokenError("unreadable") from None
    return json.loads(raw.decode("utf-8"))


# ---------- a person's sign-ins ----------
def save(handle, connector, data, issuer=""):
    """Seals `data` (a JSON-able dict: access and refresh tokens, expiry, client id) for this person and connector."""
    _check_name(connector)
    _seal(_folder_of(handle), connector, handle_hash(handle), data, str(issuer or ""))


def load(handle, connector, issuer=None):
    """The dict sealed for this person and connector. `issuer` given: it must be the one it was sealed with."""
    _check_name(connector)
    return _open(_folder_of(handle), connector, handle_hash(handle), issuer)


def exists(handle, connector):
    _check_name(connector)
    return os.path.exists(os.path.join(_folder_of(handle), f"{connector}.json.enc"))


def connectors_of(handle):
    """The connectors this person has a sealed sign-in for (names only, for "export my data")."""
    folder = _folder_of(handle)
    if not os.path.isdir(folder):
        return []
    return sorted(n[:-len(".json.enc")] for n in os.listdir(folder) if n.endswith(".json.enc"))


def delete(handle, connector):
    """Removes one sealed sign-in. True when there was one."""
    _check_name(connector)
    try:
        os.remove(os.path.join(_folder_of(handle), f"{connector}.json.enc"))
        return True
    except FileNotFoundError:
        return False


def delete_all(handle):
    """'delete my data': every sealed sign-in of this person, and their folder. Returns how many files went."""
    folder = _folder_of(handle)
    if not os.path.isdir(folder):
        return 0
    n = len([x for x in os.listdir(folder) if x.endswith(".json.enc")])
    shutil.rmtree(folder, ignore_errors=True)
    return n


@contextlib.contextmanager
def lock(handle, connector):
    """One holder at a time for this person's connector (a token refresh writes the new token before anyone reads)."""
    _check_name(connector)
    folder = _folder_of(handle)
    _make_folder(folder)
    fd = os.open(os.path.join(folder, f"{connector}.lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


# ---------- sealed settings (the Connections panel; read by settings.secret) ----------
def _settings_folder():
    return os.path.join(root(), SETTINGS_DIR)


def save_setting(name, value):
    _check_name(name)
    _seal(_settings_folder(), name, "settings", {"value": str(value)}, "settings")


def load_setting(name):
    """The sealed value, or raises TokenNotFound / TokenError / TokenKeyMissing."""
    _check_name(name)
    return str(_open(_settings_folder(), name, "settings", "settings").get("value") or "")


def setting_sealed(name):
    _check_name(name)
    return os.path.exists(os.path.join(_settings_folder(), f"{name}.json.enc"))


def delete_setting(name):
    _check_name(name)
    try:
        os.remove(os.path.join(_settings_folder(), f"{name}.json.enc"))
        return True
    except FileNotFoundError:
        return False
