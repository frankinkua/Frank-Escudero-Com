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

    # Implicit Guest Login: If the user doesn't exist, create a guest account on the fly.
    if not user:
        with _LOCK:
            # Re-read inside lock
            users = _read("users.json", {})
            if email not in users:
                users[email] = {
                    "name": email.split("@")[0],
                    "role": "guest",
                    "salt": "",
                    "password_hash": "",
                    "created_at": _iso(),
                    "subscribed": False,
                    "guest": True,
                }
                _write("users.json", users)
            user = users[email]

    # If the user has a password set (not a guest), verify it
    if user.get("password_hash"):
        if not _verify_password(password or "", user.get("salt", ""), user.get("password_hash", "")):
            return False, "Incorrect email or password.", {}

    return True, "", user


def get_user(email: str) -> dict:
    if not email:
        return {}
    users = _read("users.json", {})
    return users.get(email, {})


def update_user_profile(email: str, updates: dict) -> bool:
    if not email:
        return False
    with _LOCK:
        users = _read("users.json", {})
        if email not in users:
            return False
        users[email].update(updates)
        _write("users.json", users)
    return True



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


def log_conv_message(conv_id: str, role: str, content: str, ip: str = "", geo: dict | None = None, email: str = "", visitor_id: str = "", device: str = "", owner: bool = False) -> None:
    """Append a message to a conversation transcript (creates it on first use).

    `owner` marks this message as coming from the person the thread belongs to
    (their own greeting/ask). Ownership/identity fields are updated ONLY then,
    so an admin takeover reply (owner=False) never claims a visitor's thread.
    """
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
                "email": "",
                "owner_email": "",
                "visitor_id": "",
                "device": (device or ""),
                "location": ", ".join(
                    x for x in ((geo or {}).get("city", ""), (geo or {}).get("country", "")) if x
                ) or "unknown",
                "ai_paused": False,
                "messages": [],
            }
            convs.append(conv)
        # A visitor may identify themselves mid-thread or log in; but only the
        # thread OWNER's own messages update the identity fields. Admin
        # takeover replies must not stamp the visitor's thread with the
        # admin's email (that hijacks it into the admin's history).
        if owner:
            if email:
                conv["email"] = (email or "").strip().lower()
                conv["owner_email"] = (email or "").strip().lower()
            if visitor_id:
                conv["visitor_id"] = (visitor_id or "").strip().lower()
            if device:
                conv["device"] = device
        conv.setdefault("messages", []).append({"role": role, "content": content, "ts": _iso()})
        conv["last_activity_epoch"] = time.time()
        if role == "user":
            conv["last_user_msg_epoch"] = time.time()
        if len(convs) > CONVS_CAP:
            convs = convs[-CONVS_CAP:]
        _write("conversations.json", convs)


def get_user_conversations(email: str) -> list[dict]:
    """Return a user's OWN conversations, newest first, for history restore.

    Matches `owner_email` (stamped only by the user's own greeting/ask), so a
    visitor thread the admin merely replied to via takeover is never returned.
    """
    email = (email or "").strip().lower()
    if not email:
        return []
    with _LOCK:
        convs = _read("conversations.json", [])
        return [c for c in reversed(convs) if (c.get("owner_email") or "").strip().lower() == email]


def toggle_ai_for_conv(conv_id: str, paused: bool) -> bool:
    with _LOCK:
        convs = _read("conversations.json", [])
        for c in convs:
            if c.get("id") == conv_id:
                c["ai_paused"] = paused
                _write("conversations.json", convs)
                return True
    return False

def get_full_conversations() -> list[dict]:
    with _LOCK:
        return _read("conversations.json", [])


def get_conv_messages(conv_id: str) -> list[dict]:
    """Return a single conversation's transcript (copy), or [] if unknown."""
    if not conv_id:
        return []
    with _LOCK:
        convs = _read("conversations.json", [])
        for c in convs:
            if c.get("id") == conv_id:
                return list(c.get("messages", []))
    return []


def set_conv_messages(conv_id: str, messages: list[dict], extra: dict | None = None) -> bool:
    """Replace a conversation's transcript (used by the compactor)."""
    if not conv_id:
        return False
    with _LOCK:
        convs = _read("conversations.json", [])
        for c in convs:
            if c.get("id") == conv_id:
                c["messages"] = list(messages)
                if extra:
                    c.update(extra)
                _write("conversations.json", convs)
                return True
    return False


def archive_compact(conv_id: str, messages: list[dict]) -> None:
    """Sidecar audit log of compacted threads (capped; never fed to the LLM)."""
    if not conv_id:
        return
    with _LOCK:
        arch = _read("conversations.archive.json", [])
        arch.append({"id": conv_id, "at": _iso(), "from_msgs": len(messages), "messages": messages})
        if len(arch) > 20:
            arch = arch[-20:]
        _write("conversations.archive.json", arch)


def toggle_ai_pause(conv_id: str, pause: bool) -> None:
    with _LOCK:
        convs = _read("conversations.json", [])
        for c in convs:
            if c.get("id") == conv_id:
                c["ai_paused"] = pause
                break
        _write("conversations.json", convs)

def is_ai_paused(conv_id: str) -> bool:
    convs = _read("conversations.json", [])
    for c in convs:
        if c.get("id") == conv_id:
            return c.get("ai_paused", False)
    return False


def message_count() -> int:
    """Total chat messages across all conversations (cheap poll sentinel)."""
    convs = _read("conversations.json", [])
    return sum(len(c.get("messages", [])) for c in convs)


def edit_conv_message(conv_id: str, index: int, content: str) -> bool:
    """Replace a message in a conversation transcript (admin edits)."""
    if not conv_id or not content:
        return False
    with _LOCK:
        convs = _read("conversations.json", [])
        for c in convs:
            if c.get("id") == conv_id:
                msgs = c.get("messages", [])
                if 0 <= index < len(msgs):
                    msgs[index]["content"] = content
                    msgs[index]["ts"] = _iso()
                    msgs[index]["edited"] = True
                    c["last_activity_epoch"] = time.time()  # "last modified" re-sorts it
                    _write("conversations.json", convs)
                    return True
                return False
    return False


def touch_typing(conv_id: str) -> None:
    """Stamp a 'typing' heartbeat on a conversation (throttled server-side)."""
    if not conv_id:
        return
    now = time.time()
    with _LOCK:
        convs = _read("conversations.json", [])
        for c in convs:
            if c.get("id") == conv_id:
                last = c.get("last_typing_epoch", 0) or 0
                if now - last < 2.0:
                    return
                c["last_typing_epoch"] = now
                c["last_activity_epoch"] = now
                _write("conversations.json", convs)
                return


def _conv_status(c: dict) -> str:
    """Derive a human presence status for a conversation from heartbeat stamps.

    `typing…` while the visitor is mid-composition (<8s), then `active` while
    their last activity is fresh (<2min), then `away`.
    """
    now = time.time()
    last_typing = c.get("last_typing_epoch", 0) or 0
    last_act = c.get("last_activity_epoch", 0) or 0
    last_user = c.get("last_user_msg_epoch", 0) or 0
    if last_typing and now - last_typing < 8:
        return "typing…"
    latest = max(last_act, last_user)
    if not latest:
        return "away"
    age = now - latest
    if age < 120:
        secs = int(age)
        return f"active {secs}s ago" if secs < 60 else f"active {secs // 60}m ago"
    return "away"


def _clamp(text: str, max_chars: int = 120, max_lines: int = 4) -> str:
    """Truncate a message preview: at most `max_lines` lines, each <= `max_chars`."""
    text = (text or "").replace("\r", "")
    if not text:
        return ""
    lines = text.split("\n")
    out: list[str] = []
    for ln in lines[:max_lines]:
        if len(ln) > max_chars:
            ln = ln[: max_chars - 1].rstrip() + "…"
        out.append(ln)
    if len(lines) > max_lines:
        last = out[-1]
        out[-1] = (last[: max_chars - 1].rstrip() + "…") if not last.endswith("…") else last
    return "\n".join(out)


def _last_msg_epoch(c: dict) -> float:
    """Sort key: timestamp of the newest message (edits bump the ts too)."""
    msgs = c.get("messages") or []
    if msgs:
        ts = msgs[-1].get("ts", "")
        if ts:
            try:
                return datetime.fromisoformat(ts).timestamp()
            except (ValueError, TypeError):
                pass
    try:
        return float(c.get("last_activity_epoch") or 0)
    except (TypeError, ValueError):
        pass
    return 0.0


def _thread_preview(msgs: list[dict]) -> str:
    """Last 4 messages as a clamped text block (120 chars/line, 4 lines each)."""
    parts = []
    for m in (msgs or [])[-4:]:
        tag = "YOU: " if m.get("role") == "user" else "AI: "
        parts.append(tag + _clamp(m.get("content", "")))
    return "\n\n".join(parts)


def admin_data() -> dict:
    """Aggregate everything the dashboard needs in one lock-protected pass."""
    with _LOCK:
        visits = _read("visits.json", [])
        convs = _read("conversations.json", [])
        users_db = _read("users.json", {})

    total = len(visits)
    unique = len({v.get("ip") for v in visits if v.get("ip")})
    msg_count = sum(len(c.get("messages", [])) for c in convs)

    # Newest-activity-first ordering (per conversation), so "recently updated"
    # threads surface at the top. Used for both the thread list and the people
    # aggregation below.
    ordered = sorted(convs, key=_last_msg_epoch, reverse=True)

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
    # One thread card per conversation (no flattening — that was the source of
    # the "gaps" in Live Chats). Each carries the last 4 messages, clamped to
    # 120 chars / line and 4 lines, as a single pre-joined preview string.
    threads: list[dict[str, str]] = []
    for c in ordered:
        msgs = c.get("messages") or []
        if not msgs:
            continue
        last = msgs[-1]
        email = (c.get("email") or "").strip()
        vid = (c.get("visitor_id") or "").strip()
        owner = email or ("Guest " + (vid or c.get("id") or "?")[:8])
        threads.append(
            {
                "id": c.get("id", ""),
                "created": c.get("created", ""),
                "owner": owner,
                "email": email,
                "visitor_id": vid,
                "identity": ", ".join(
                    x for x in (c.get("location", ""), c.get("ip", ""), c.get("device", "")) if x
                ) or "unknown",
                "status": _conv_status(c),
                "ai_paused": str(bool(c.get("ai_paused"))).lower(),
                "msg_count": str(len(msgs)),
                "last_msg": _clamp(last.get("content", "")),
                "last_seen": last.get("ts", "") or c.get("created", ""),
                "preview": _thread_preview(msgs),
            }
        )

    # Group conversations by person: logged-in users key on email, anonymous
    # visitors on their stable localStorage visitor_id. Newest activity first.
    people: dict[str, dict[str, object]] = {}
    for c in ordered:
        msgs = c.get("messages") or []
        if not msgs:
            continue
        email = (c.get("email") or "").strip().lower()
        vid = (c.get("visitor_id") or "").strip().lower()
        key = email if email else (vid or c.get("id", ""))
        last = msgs[-1]
        if key not in people:
            people[key] = {
                "label": email or ("Guest " + vid[:8] if vid else "Guest"),
                "email": email,
                "visitor_id": vid,
                "ip": c.get("ip", "") or "",
                "location": c.get("location", "") or "unknown",
                "device": c.get("device", "") or "",
                "msgs": 0,
                "convs": 0,
                "last_seen": last.get("ts", "") or c.get("created", ""),
                "conv_id": c.get("id", ""),
                "description": _clamp(last.get("content", "")),
                "thread": _thread_preview(msgs),
            }
        row = people[key]
        row["msgs"] = int(row["msgs"]) + len(msgs)
        row["convs"] = int(row["convs"]) + 1
        if not row["ip"] and c.get("ip"):
            row["ip"] = c["ip"]
        if not row["location"] or row["location"] == "unknown":
            row["location"] = c.get("location", "") or "unknown"
        if not row["device"] and c.get("device"):
            row["device"] = c["device"]
        if not row["description"]:
            row["description"] = _clamp(last.get("content", ""))
        if not row["thread"]:
            row["thread"] = _thread_preview(msgs)

    # Overlay registered users (users.json) onto the per-person rows, then add
    # any registered-but-silent accounts so the Users tab always lists them.
    for email, udata in users_db.items():
        base = {
            "name": udata.get("name", "") or email.split("@")[0],
            "role": udata.get("role", "guest"),
            "guest": str(bool(udata.get("guest", False))),
        }
        if email in people:
            people[email].update(base)
        else:
            people[email] = {
                "label": base["name"],
                "email": email,
                "visitor_id": "",
                "ip": "",
                "location": "unknown",
                "device": "",
                "msgs": 0,
                "convs": 0,
                "last_seen": udata.get("created_at", ""),
                "conv_id": "",
                "description": "",
                "thread": "",
                **base,
            }

    users_list = []
    for key, p in people.items():
        email = str(p.get("email", ""))
        users_list.append(
            {
                "name": str(p.get("name") or "") or (email or str(p.get("label", "Guest"))),
                "email": email,
                "role": str(p.get("role", "guest")),
                "guest": str(p.get("guest", "True")),
                "location": str(p.get("location", "")) or "unknown",
                "description": str(p.get("description", "")),
                "msgs": str(p.get("msgs", 0)),
                "convs": str(p.get("convs", 0)),
                "last_seen": str(p.get("last_seen", "")),
                "conv_id": str(p.get("conv_id", "")),
                "thread": str(p.get("thread", "")),
            }
        )
    users_list.sort(key=lambda d: d["last_seen"], reverse=True)

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
        "threads": threads,
        "users": users_list,
    }
