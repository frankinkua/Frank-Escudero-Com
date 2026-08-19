"""Device fingerprint decode + human-readable device naming.

Turns the raw client probe (UA + browser signals) into a normalized profile:
a stable device_id (hash), a readable device name ("Samsung Galaxy S7 Ultra",
"Apple iPhone 15 Pro", "Windows 11 laptop", ...), and capability flags.
"""

from __future__ import annotations

import hashlib
import re

# Ordered Samsung Galaxy S-style model tables. The UA puts the marketing name
# of most phones directly in it (e.g. "SM-G988B Build/..."), so we map common
# model codes -> friendly names. Falls back to the raw model token otherwise.
_SAMSUNG_S = {
    "SM-G988": "S20 Ultra", "SM-G981": "S20", "SM-G980": "S20",
    "SM-G9810": "S20", "SM-G986": "S20+",
    "SM-G991": "S21", "SM-G996": "S21+", "SM-G998": "S21 Ultra",
    "SM-S901": "S22", "SM-S906": "S22+", "SM-S908": "S22 Ultra",
    "SM-S911": "S23", "SM-S916": "S23+", "SM-S918": "S23 Ultra",
    "SM-S711": "S23 FE", "SM-S921": "S24", "SM-S926": "S24+",
    "SM-S928": "S24 Ultra", "SM-S931": "S25", "SM-S936": "S25+",
    "SM-S938": "S25 Ultra", "SM-S911C": "S23",
    "SM-N981": "Note 20", "SM-N986": "Note 20 Ultra", "SM-N970": "Note 10",
    "SM-N976": "Note 10+", "SM-N975": "Note 10+", "SM-N960": "Note 9",
    "SM-A51": "Galaxy A51", "SM-A52": "A52", "SM-A53": "A53",
    "SM-A54": "A54", "SM-A55": "A55", "SM-A71": "A71", "SM-A72": "A72",
    "SM-A73": "A73", "SM-A34": "A34", "SM-A35": "A35", "SM-A05": "A05",
    "SM-A15": "A15", "SM-A25": "A25", "SM-A12": "A12", "SM-A13": "A13",
    "SM-A14": "A14", "SM-A22": "A22", "SM-A23": "A23", "SM-A24": "A24",
    "SM-A32": "A32", "SM-A33": "A33", "SM-A42": "A42", "SM-A51":
    "A51", "SM-A50": "A50", "SM-A40": "A40", "SM-A41": "A41",
    "SM-A10": "A10", "SM-A11": "A11", "SM-A20": "A20", "SM-A21": "A21",
    "SM-A30": "A30", "SM-A31": "A31",
    "SM-ZFlip": "Z Flip", "SM-ZFold": "Z Fold",
}
_APPLE = {
    "iPhone": "iPhone",
}


def _tokenize_tablet(ua: str) -> str | None:
    m = re.search(r"iPad[^\s;]*", ua, re.I)
    if m:
        return "Apple iPad"
    m = re.search(r"(SM-|GT-)[A-Z][A-Z0-9]{2,5}", ua)
    if m:
        return "Samsung Galaxy Tab"
    return None


def normalize_device_name(ua: str, via_js: dict[str, str] | None = None) -> str:
    """Best-effort human device name from a raw UA string."""
    ua = ua or ""
    via_js = via_js or {}

    # Apple
    m = re.search(r"iPhone[^\s;\)]*", ua)
    if m:
        return "Apple " + m.group(0)
    if re.search(r"iPad", ua, re.I):
        return "Apple iPad"
    if re.search(r"Macintosh|Mac OS X|MacBook", ua, re.I):
        return "Apple Mac"

    # Windows
    if re.search(r"Windows NT|Windows 11|Windows 10|Windows 8|Windows 7", ua, re.I):
        ver = re.search(r"Windows (\d+(?:\.\d+)?)", ua, re.I)
        nam = "Windows 11" if (ver and ver.group(1).startswith("10") and "Windows 11" in ua) else (ver.group(1) if ver else "10")
        if nam == "10" and "Windows 11" in ua:
            nam = "11"
        if "X64" in ua or "x86_64" in ua:
            arch = " 64-bit"
        else:
            arch = " 32-bit"
        return f"Windows {nam} PC{arch}"

    # Linux / generic desktop
    if re.search(r"X11; Linux|x86_64.*Linux|Intel.*Linux", ua, re.I):
        return "Linux Desktop"

    # Android — phone vs tablet, Samsung marketing names
    if re.search(r"Android|Linux; Android", ua, re.I):
        # Samsung S/Note/A models
        m = re.search(r"SM-[A-Z0-9]{3,5}", ua)
        if m:
            code = m.group(0)
            brand = "Galaxy S" if re.match(r"SM-S9|SM-G9", code) else "Galaxy"
            for prefix, friendly in _SAMSUNG_S.items():
                if code.startswith(prefix):
                    return f"Samsung Galaxy {friendly}"
            return "Samsung " + code.replace("SM-", "")
        if re.search(r"Pixel", ua, re.I):
            return "Google Pixel"
        if via_js.get("platform") and "linux aarch64" in (via_js["platform"] or "").lower():
            return "Android tablet"
        return "Android phone"

    # Alternative mobile UAs sometimes arrive with no platform match
    if via_js.get("touch") and via_js.get("screen"):
        return "Touch device"

    return "Desktop / unknown"


def fingerprint_id(ua: str, probe: dict) -> str:
    """Stable per-device id: hash of the signals we can read. Intent: same
    device returns the same id across visits; a new/reinstalled browser will
    differ. Sent to the client as its loaded `visitor` key."""
    blob = (
        f"{ua};{probe.get('lang','')};{probe.get('langs','')};"
        f"{probe.get('tz','')};{probe.get('platform','')};"
        f"{probe.get('cores','')};{probe.get('mem','')};{probe.get('screen','')};"
        f"{probe.get('touch','')};{probe.get('gpu','')};{probe.get('devicePixelRatio','')}"
    )
    return "d_" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def build_profile(probe: dict, ua: str, device_name: str) -> dict:
    """Assemble the stored per-client profile dict."""
    return {
        "device_name": device_name,
        "device_id": fingerprint_id(ua, probe),
        "lang": probe.get("lang", ""),
        "langs": probe.get("langs", ""),
        "tz": probe.get("tz", ""),
        "platform": probe.get("platform", ""),
        "cores": probe.get("cores", 0),
        "mem_gb": probe.get("mem", 0),
        "screen": probe.get("screen", ""),
        "dpr": probe.get("devicePixelRatio", "1"),
        "touch": probe.get("touch", "0"),
        "gpu": probe.get("gpu", ""),
        "online": probe.get("online", True),
        "devicememory": probe.get("mem", 0),
        "hardwareconcurrency": probe.get("cores", 0),
    }


def local_ip_list(probe: dict) -> str:
    """Comma-joined local IPs the WebRTC STUN probe hoped to observe. On open
    WAN, this is usually empty (that is expected); on many private setups it
    exposes the client's NAT/private address."""
    raw = probe.get("webrtc", "")
    if isinstance(raw, list):
        return ",".join(raw)
    if raw and isinstance(raw, str):
        return raw
    return ""