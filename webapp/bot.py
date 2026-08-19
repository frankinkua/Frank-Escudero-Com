"""The site's assistant: chat + aggressive proactive engagement.

Behind the scenes a normal /v1 OpenAI-compatible call to the olla proxy
(100.100.1.10:40114). Front of house it is a persistent, friendly, knowing
assistant that:
  - opens the chat itself once per session (aggressive engagement)
  - nudges the visitor if they hang around without typing
  - personalizes its greeting from the learned client profile
  - can restyle the site live (theme) and attach per-client CSS/HTML/JS blocks
"""

from __future__ import annotations

import asyncio
import os
import re

import httpx
from openai import AsyncOpenAI

from . import db

CHAT_URL = os.environ.get("CHAT_URL", "http://100.100.1.10:40114/olla/proxy/v1")
CHAT_API_KEY = os.environ.get("CHAT_API_KEY", "olla")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "prism-ml/bonsai-27b")
CHAT_ENABLED = os.environ.get("CHAT_ENABLED", "1") == "1"

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI | None:
    global _client
    if not CHAT_ENABLED:
        return None
    if _client is None:
        _client = AsyncOpenAI(
            base_url=CHAT_URL,
            api_key=CHAT_API_KEY,
            timeout=httpx.Timeout(90.0, connect=5.0),
        )
    return _client


_ROOT = "/web"


def _read(name: str) -> str:
    try:
        return open(os.path.join(_ROOT, name), encoding="utf-8").read()
    except Exception:
        return ""


def _cv_text() -> str:
    return _read("cv.md")


def system_prompt(profile: dict, device_name: str, history_count: int) -> str:
    cv = _cv_text()[:4000]
    timeline = _read("timeline.md")[:1200]
    return (
        "You are the assistant living on Frank Escudero's CV site (frank-escudero.com).\n"
        "You are warm, curious and lightly persistent: you may open the chat yourself, "
        "greet the visitor personally, and gently nudge them if they idle.\n\n"
        "KNOWLEDGE / CV:\n"
        f"{cv}\n\n"
        "SITE HISTORY (timeline):\n"
        f"{timeline}\n\n"
        "ABOUT THIS VISITOR (learned device profile):\n"
        f"- profile: {profile}\n"
        f"- device: {device_name}\n"
        f"- visit count (this device): {history_count}\n"
        "Use the device/profile naturally: if they are on an Android phone, say so. "
        "Feel free to remark on their timezone/screen/GPU without being creepy.\n\n"
        "RULES:\n"
        "1. Answer in the visitor's language when you can identify it.\n"
        "2. Be concise (3-6 sentences) unless asked for depth.\n"
        "3. You may ask which theme they'd like and explain you can restyle the site "
        "for them in real time.\n"
        "4. The site is self-updating; describe live edits only when relevant.\n"
        "5. Never claim to be a human. You're the site's intelligence."
    )


async def chat(messages: list[dict], profile: dict, device_name: str, history_count: int) -> str:
    """One assistant turn over the olla proxy. Returns assistant text."""
    client = get_client()
    if client is None:
        return "Chat is disabled right now."
    history = messages[-24:]
    if not any(m.get("role") == "system" for m in history):
        history = [{"role": "system", "content": system_prompt(profile, device_name, history_count)}] + history
    try:
        resp = await client.chat.completions.create(model=CHAT_MODEL, messages=history, max_tokens=700)
        return (resp.choices[0].message.content or "").strip() or "…"
    except Exception as exc:  # noqa: BLE001
        return f"Sorry, the model hiccuped. ({type(exc).__name__})"


# --- live restyle helpers -----------------------------------------------

ACCENT = "#5eead4"
BG = "#0d1117"
MUTED = "#9aa4bb"
CARD = {"background": "#0d1117", "border": "1px solid #2a3247", "borderRadius": "0.75rem"}


def extract_theme(device_id: str, reply: str, profile: dict) -> None:
    """If the assistant's reply suggests a color/theme keyword, attach a CSS
    block to this client and log it, so next render keeps it."""
    low = reply.lower()
    for keyword, accent, grad in [
        ("dark", "#5eead4", "#0d1117"),
        ("night", "#818cf8", "#0f172a"),
        ("space", "#c4b5fd", "#0b1020"),
        ("fire", "#fb923c", "#241410"),
        ("forest", "#4ade80", "#0c1f14"),
        ("rose", "#fb7185", "#2a0f1a"),
        ("amber", "#facc15", "#1d1505"),
    ]:
        if keyword in low:
            db.save_block(
                device_id,
                "theme:" + keyword,
                "css",
                f"html,body{{background:{grad};background-attachment:fixed;}}"
                f"a{{color:{accent};}}",
            )
            break