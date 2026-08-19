"""Reflex State for the CV site.

Responsibilities (thin, async-friendly):
  - fingerprint the visitor on load (rx.call_script promise -> on_probe)
  - record visit + upsert the per-device profile in SQLite
  - aggressive chat: auto-open once, nudge if idle, tagged on_submit
  - per-client live restyle via theme + attached CSS/HTML/JS blocks
"""

from __future__ import annotations

import asyncio

import reflex as rx

from . import bot, db, js, theme
from .device import build_profile, fingerprint_id, normalize_device_name


class State(rx.State):
    # --- identity ---
    visitor_id: str = ""
    probe: dict = {}
    device_id: str = ""
    device_name: str = ""
    first_time: bool = True

    # --- chat ---
    chat_open: bool = False
    messages: list[dict] = []
    busy: bool = False
    auto_opened: bool = False
    last_activity: float = 0.0

    # --- site data ---
    home_md: str = ""
    cv_md: str = ""
    timeline_md: str = ""
    block_injected: bool = False
    server_ts: str = ""

    # ------------------------------------------------------------------
    # init / routing helpers
    # ------------------------------------------------------------------

    @rx.var
    def greeting(self) -> str:
        return theme.greeting(self.probe or {}, self.device_name, self.first_time)

    def get_profile_for(self, device_id: str) -> dict:
        """Used by components while SSR-ing a page for a known device."""
        if device_id == self.device_id:
            return self.probe or {}
        row = db.get_visitor(device_id)
        p = (row or {}).get("profile") or {}
        return p if isinstance(p, dict) else {}

    # ------------------------------------------------------------------
    # on_load chains
    # ------------------------------------------------------------------

    async def load_home(self):
        from . import components, timeline
        self._start()
        self.home_md = _read("/web/home.md")
        self.cv_md = _read("/web/cv.md")
        self.timeline_md = timeline.build()
        self.messages = db.recent_messages(self.device_id, 12)
        # probe the browser, then if nothing else: restyle to the client.
        return [
            rx.call_script(js.PROBE_JS, callback=State.on_probe),
            rx.call_script(js.AUTO_OPEN_JS, callback=State.on_auto_open),
            rx.call_script(js.NUDGE_JS, callback=State.on_nudge),
        ]

    def load_cv(self):
        self._start()
        self.cv_md = _read("/web/cv.md")
        return rx.call_script(js.PROBE_JS, callback=State.on_probe)

    def load_timeline(self):
        from . import timeline
        self._start()
        self.timeline_md = timeline.build()
        return rx.call_script(js.PROBE_JS, callback=State.on_probe)

    def _start(self) -> None:
        import time
        self.last_activity = time.time()
        self.server_ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

    def _client_ip(self) -> str:
        try:
            raw = getattr(getattr(self.router, "headers", None), "raw_headers", None) or []
            for k, v in raw:
                key = getattr(k, "lower", lambda: k)()
                if key == b"x-forwarded-for" or key == "x-forwarded-for":
                    val = getattr(v, "decode", lambda: v)()
                    return str(val).partition(",")[0].strip()
        except Exception:  # noqa: BLE001
            pass
        try:
            return self.router.session.client_ip or ""
        except Exception:  # noqa: BLE001
            return ""

    def _lang(self) -> str:
        try:
            return self.router.headers.get("accept-language", "")[:64]
        except Exception:  # noqa: BLE001
            return ""

    def _ref(self) -> str:
        try:
            return (self.router.headers.get("referer") or "")[:128]
        except Exception:  # noqa: BLE001
            return ""

    # ------------------------------------------------------------------
    # fingerprint callback
    # ------------------------------------------------------------------

    async def on_probe(self, raw: str) -> None:
        """Receives the JSON string resolved by PROBE_JS's promise."""
        import json
        import time
        try:
            probe = json.loads(raw or "{}")
        except Exception:
            probe = {}
        self.probe = probe
        ua = probe.get("ua") or ""
        self.device_name = normalize_device_name(ua, probe)
        self.device_id = fingerprint_id(ua, probe)
        row = db.get_visitor(self.device_id)
        self.first_time = row is None
        profile = build_profile(probe, ua, self.device_name)
        ip = self._client_ip()
        lang = self._lang()
        ref = self._ref()
        geo: dict = {}
        db.upsert_visitor(self.device_id, ip, geo, self.device_name, profile,
                          [b["key"] for b in db.get_blocks(self.device_id)])
        db.log_visit(self.device_id, "/", ip, ua, lang, ref)
        db.log_message(self.device_id, "assistant", self.greeting)
        self.messages = db.recent_messages(self.device_id, 12)
        self.block_injected = True
        # keep the visitor pinned to their device profile
        self.device_id = profile["device_id"]

    # ------------------------------------------------------------------
    # aggressive chat engagement
    # ------------------------------------------------------------------

    def toggle_chat(self):
        self.chat_open = not self.chat_open
        return rx.call_script(js.scroll_js())

    def open_chat(self):
        self.chat_open = True

    def close_chat_popup(self):
        self.chat_open = False

    def on_auto_open(self, _: str = "") -> None:
        """Open the chat by itself, once per device session."""
        if not self.auto_opened:
            self.auto_opened = True
            self.chat_open = True
            if self.device_id and not any(m["role"] == "assistant" for m in self.messages):
                self.messages = db.recent_messages(self.device_id, 12)
            return rx.call_script(js.scroll_js())

    def on_nudge(self, _: str = "") -> None:
        """If the visitor idles without typing, nudge them (aggressive but kind)."""
        import time
        if self.chat_open or time.time() - self.last_activity < 20:
            return
        self.chat_open = True
        self.messages.append({
            "role": "assistant",
            "content": f"Still here on your {self.device_name or 'device'}? "
                        "Ask me anything about Frank, the stack, or the timeline — "
                        "or tell me to change the site's look.",
        })

    def on_idle(self, _: str = "") -> None:
        import time
        self.last_activity = time.time()

    async def handle_submit(self, form: dict):
        import time
        text = (form.get("text") or "").strip()
        if not text or self.busy:
            return
        self.busy = True
        self.chat_open = True
        self.last_activity = time.time()
        self.messages.append({"role": "user", "content": text})
        db.log_message(self.device_id, "user", text)
        history = db.recent_messages(self.device_id, 16)
        as_reply = await bot.chat(
            [{"role": m["role"], "content": m["content"]} for m in history],
            self.probe or {}, self.device_name, self.first_time,
        )
        self.messages.append({"role": "assistant", "content": as_reply})
        db.log_message(self.device_id, "assistant", as_reply)
        # opportunistic live restyle if the assistant chose a theme
        bot.extract_theme(self.device_id, as_reply, self.probe or {})
        self.block_injected = True
        self.busy = False
        return rx.call_script(js.scroll_js())


def _read(path: str) -> str:
    try:
        return open(path, encoding="utf-8").read()
    except Exception:
        return ""