"""JSON-file data layer for the CV site: users, sessions, visits, conversations.

Self-contained, no network, single-process safe (Reflex prod runs one backend
worker here — no Redis). All reads/writes go through a threading lock and an
atomic temp-file replace so a crash never leaves a half-written store.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pathlib
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("web.site_store")

DATA = pathlib.Path("/web/data")
DATA.mkdir(parents=True, exist_ok=True)

_LOCK = threading.Lock()
SESSION_TTL = timedelta(days=30)
VISITS_CAP = 5000
CONVS_CAP = 500

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "frank@inkua.eu").lower()

_PBKDF2_ITERS = 200_000


def _read(name: str, default):
    p = DATA / name
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def _write(name: str, obj) -> None:
    p = DATA / name
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False))
    os.replace(tmp, p)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso() -> str:
    return _now().strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------- #
# Passwords (pbkdf2-sha256, 200k iters, per-user random salt)
# --------------------------------------------------------------------------- #
def _hash_password(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _PBKDF2_ITERS)
    return salt, dk.hex()


def _verify_password(password: str, salt: str, expected: str) -> bool:
    try:
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _PBKDF2_ITERS)
    except (TypeError, ValueError):
        return False
    return secrets.compare_digest(dk.hex(), expected or "")


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #
def ensure_admin() -> str:
    """Create the bootstrap admin on first run. Returns the generated password ("" if existed)."""
    with _LOCK:
        users = _read("users.json", {})
        if any(u.get("role") == "admin" for u in users.values()):
            return ""
        password = secrets.token_urlsafe(12)
        salt, pw_hash = _hash_password(password)
        users[ADMIN_EMAIL] = {
            "name": "Frank",
            "role": "admin",
            "salt": salt,
            "password_hash": pw_hash,
            "created_at": _iso(),
            "subscribed": True,
        }
        _write("users.json", users)
        try:
            b = DATA / ".admin-bootstrap"
            b.write_text(f"email: {ADMIN_EMAIL}\npassword: {password}\n")
            b.chmod(0o600)
        except OSError:  # pragma: no cover
            pass
        logger.warning("admin bootstrap created for %s (password in /web/data/.admin-bootstrap)", ADMIN_EMAIL)
        return password


def create_user(name: str, email: str, password: str) -> tuple[bool, str]:
    """Register a normal (subscribed) user. Returns (ok, error_msg)."""
    email = (email or "").strip().lower()
    password = password or ""
    if "@" not in email or "." not in email:
        return False, "Enter a valid email address."
    if len(password) < 8:
        return False, "Password must be at least 8 characters."
    with _LOCK:
        users = _read("users.json", {})
        if email in users:
            return False, "That email is already registered."
        salt, pw_hash = _hash_password(password)
        users[email] = {
            "name": (name or "").strip() or email.split("@")[0],
            "role": "user",
            "salt": salt,
            "password_hash": pw_hash,
            "created_at": _iso(),
            "subscribed": True,
        }
        _write("users.json", users)
    return True, ""


def authenticate(email: str, password: str) -> tuple[bool, str, dict]:
    email = (email or "").strip().lower()
    users = _read("users.json", {})
    user = users.get(email)
    if not user or not _verify_password(password or "", user.get("salt", ""), user.get("password_hash", "")):
        return False, "Incorrect email or password.", {}
    return True, "", user


# --------------------------------------------------------------------------- #
# Sessions (opaque random tokens, 30-day expiry, persisted across restarts)
# --------------------------------------------------------------------------- #
def create_session(email: str, role: str, name: str = "") -> str:
    token = secrets.token_hex(32)
    with _LOCK:
        sessions = _read("sessions.json", {})
        now = _now()
        for t, s in list(sessions.items()):
            try:
                if datetime.fromisoformat(s["expires_at"]) < now:
                    sessions.pop(t, None)
            except (KeyError, ValueError, TypeError):
                sessions.pop(t, None)
        sessions[token] = {
            "email": email,
            "role": role,
            "name": name,
            "created_at": _iso(),
            "expires_at": (now + SESSION_TTL).isoformat(),
        }
        _write("sessions.json", sessions)
    return token


def validate_session(token: str) -> dict | None:
    if not token:
        return None
    sessions = _read("sessions.json", {})
    s = sessions.get(token)
    if not s:
        return None
    try:
        if datetime.fromisoformat(s["expires_at"]) < _now():
            return None
    except (KeyError, ValueError, TypeError):
        return None
    return s


def destroy_session(token: str) -> None:
    if not token:
        return
    with _LOCK:
        sessions = _read("sessions.json", {})
        sessions.pop(token, None)
        _write("sessions.json", sessions)


# --------------------------------------------------------------------------- #
# Analytics: visits + conversations
# --------------------------------------------------------------------------- #
def log_visit(path: str, ip: str, geo: dict, lang: str = "", ua: str = "", ref: str = "") -> None:
    rec = {
        "ts": _iso(),
        "epoch": time.time(),
        "path": path or "/",
        "ip": ip,
        "country": (geo or {}).get("country", ""),
        "country_code": (geo or {}).get("country_code", ""),
        "region": (geo or {}).get("region", ""),
        "city": (geo or {}).get("city", ""),
        "lang": lang,
        "ua": ua,
        "ref": ref,
    }
    with _LOCK:
        visits = _read("visits.json", [])
        visits.append(rec)
        if len(visits) > VISITS_CAP:
            visits = visits[-VISITS_CAP:]
        _write("visits.json", visits)


def backfill_geo(ip: str, geo: dict) -> None:
    """Attach geo to earlier visits of the same IP once it is resolved."""
    if not ip or not geo:
        return
    with _LOCK:
        visits = _read("visits.json", [])
        changed = False
        for v in visits:
            if v.get("ip") == ip and not v.get("country"):
                v["country"] = geo.get("country", "")
                v["country_code"] = geo.get("country_code", "")
                v["region"] = geo.get("region", "")
                v["city"] = geo.get("city", "")
                changed = True
        if changed:
            _write("visits.json", visits)


def log_conv_message(conv_id: str, role: str, content: str, ip: str = "", geo: dict | None = None) -> None:
    """Append a message to a conversation transcript (creates it on first use)."""
    if not conv_id or not content:
        return
    with _LOCK:
        convs = _read("conversations.json", [])
        conv = next((c for c in convs if c.get("id") == conv_id), None)
        if conv is None:
            conv = {
                "id": conv_id,
                "created": _iso(),
                "ip": ip,
                "location": ", ".join(
                    x for x in ((geo or {}).get("city", ""), (geo or {}).get("country", "")) if x
                ) or "unknown",
                "messages": [],
            }
            convs.append(conv)
        conv.setdefault("messages", []).append({"role": role, "content": content, "ts": _iso()})
        if len(convs) > CONVS_CAP:
            convs = convs[-CONVS_CAP:]
        _write("conversations.json", convs)


def admin_data() -> dict:
    """Aggregate everything the dashboard needs in one lock-protected pass."""
    with _LOCK:
        visits = _read("visits.json", [])
        convs = _read("conversations.json", [])
    total = len(visits)
    unique = len({v.get("ip") for v in visits if v.get("ip")})
    msg_count = sum(len(c.get("messages", [])) for c in convs)

    locations: dict[str, int] = {}
    pages: dict[str, int] = {}
    for v in visits:
        where = ", ".join(x for x in (v.get("city"), v.get("country")) if x) or "unknown"
        locations[where] = locations.get(where, 0) + 1
        p = v.get("path") or "/"
        pages[p] = pages.get(p, 0) + 1

    recent = [
        {
            "ts": v.get("ts", ""),
            "path": v.get("path", "/"),
            "ip": v.get("ip", ""),
            "where": ", ".join(x for x in (v.get("city"), v.get("country")) if x) or "unknown",
            "country_code": v.get("country_code", ""),
            "lang": v.get("lang", ""),
        }
        for v in reversed(visits[-20:])
    ]
    # Flatten conversations into a single list of rows (all-string values so
    # the dashboard can foreach them without nested-dict typing problems):
    # a "header" row per conversation, then one "msg" row per turn.
    conv_rows: list[dict[str, str]] = []
    for c in reversed(convs[-30:]):
        conv_rows.append(
            {
                "kind": "header",
                "id": c.get("id", ""),
                "created": c.get("created", ""),
                "location": c.get("location", "") or "unknown",
                "role": "",
                "content": "",
            }
        )
        for m in c.get("messages", []):
            conv_rows.append(
                {
                    "kind": "msg",
                    "id": "",
                    "created": "",
                    "location": "",
                    "role": m.get("role", ""),
                    "content": m.get("content", ""),
                }
            )
    return {
        "total": total,
        "unique": unique,
        "convs": len(convs),
        "messages": msg_count,
        "locations": sorted(
            ({"location": k, "count": c} for k, c in locations.items()),
            key=lambda d: -d["count"],
        ),
        "pages": sorted(({"path": k, "count": c} for k, c in pages.items()), key=lambda d: -d["count"]),
        "recent": recent,
        "convs_list": conv_rows,
    }
