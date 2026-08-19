"""Per-client theme derivation.

The assistant learns a visitor (device, timezone, language, screen size, GPU,
visit count) and the site restyles itself live for that client: background
gradient, accent, and a greeting header are derived here and emitted as a
short CSS block + inline style values. Everything is data-driven and cheap.
"""

from __future__ import annotations

import difflib

# (name, css_gradient, accent hex) — picked by a light heuristic from profile.
_THEMES: list[tuple[str, str, str]] = [
    ("deep_space", "radial-gradient(1200px 700px at 15% 0%, #0b1020 0%, #0d1117 55%, #151b2d 100%)", "#5eead4"),
    ("ember", "radial-gradient(1200px 700px at 80% 0%, #2a0a0a 0%, #14100f 55%, #241410 100%)", "#fb923c"),
    ("forest", "radial-gradient(1200px 700px at 10% 10%, #0c1f14 0%, #0a0f0d 60%, #12271a 100%)", "#4ade80"),
    ("aurora", "linear-gradient(180deg, #050d21 0%, #0a1028 45%, #140f2b 100%)", "#a78bfa"),
    ("rose", "linear-gradient(180deg, #2a0f1a 0%, #170d15 55%, #0f0b14 100%)", "#fb7185"),
    ("amber", "linear-gradient(180deg, #1d1505 0%, #14120d 55%, #1d160a 100%)", "#facc15"),
]


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _score(profile: dict) -> tuple[int, int]:
    """Score themes; returns (best_index, score)."""
    gpu = (profile.get("gpu") or "").lower()
    tz = (profile.get("tz") or "").lower()
    lang = (profile.get("langs") or profile.get("lang") or "").lower()
    screen = profile.get("screen") or ""
    scores = [0] * len(_THEMES)
    if "nvidia" in gpu:
        scores[1] += 2
        scores[2] += 1
    elif "amd" in gpu:
        scores[0] += 1
        scores[4] += 1
    elif "intel" in gpu:
        scores[3] += 2
    if "night" in tz or tz.startswith("us") or tz.startswith("america"):
        scores[0] += 1
    if "germany" in tz or tz.startswith("europe/berlin"):
        scores[2] += 2
        scores[1] += 1
    if "ar" in lang:
        scores[4] += 2
    try:
        w, h = (int(x) for x in screen.split("x"))
        if h > w:  # portrait phone
            scores[4] += 1
            scores[5] += 1
        else:
            scores[3] += 1
    except (ValueError, AttributeError):
        pass
    best = max(range(len(_THEMES)), key=lambda i: scores[i])
    return best, scores[best]


def pick_theme(profile: dict) -> str:
    """Return the css gradient for this client."""
    idx, _ = _score(profile)
    return _THEMES[idx][1]


def pick_accent(profile: dict) -> str:
    idx, _ = _score(profile)
    return _THEMES[idx][2]


def theme_css(profile: dict) -> str:
    """A tiny CSS block scoped to the body — the 'background the client likes'."""
    idx, _ = _score(profile)
    name, grad, accent = _THEMES[idx]
    return (
        f"html,body{{background:{grad};background-attachment:fixed;}}"
        f"a,cv-accent{{color:{accent};}}"
        f".cv-accent-bg{{background:{accent};color:#0b0e14;}}"
        f".cv-card{{background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);}}"
        f"/* theme:{name} */"
    )


def greeting(profile: dict, device_name: str, first_time: bool) -> str:
    tz = profile.get("tz") or ""
    if "germany" in tz.lower() or "berlin" in tz.lower():
        geo = "Germany"
    elif "america" in tz.lower() or tz.lower().startswith("us"):
        geo = "the Americas"
    else:
        geo = "your corner of the world"
    langs = (profile.get("langs") or profile.get("lang") or "")
    if "en" not in langs.lower():
        lang_hint = " — I can reply in your language"
    else:
        lang_hint = ""
    if first_time:
        return (
            f"First time on my site from {geo} on a {device_name or 'browser'}{lang_hint}. "
            f"I've already tuned the theme for it."
        )
    return (
        f"Welcome back on your {device_name or 'device'} ({geo}). "
        f"The site remembered you and kept your theme."
    )