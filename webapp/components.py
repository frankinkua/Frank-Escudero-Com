"""Presentational Reflex components for the CV site."""

from __future__ import annotations

import reflex as rx

from . import bot, js
from .state import State
from .device import normalize_device_name


def _seconds(t: float) -> str:
    import datetime
    try:
        return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return ""


NAV_LINKS = [
    ("Home", "/"),
    ("CV", "/cv"),
    ("Timeline", "/timeline"),
]


def nav() -> rx.Component:
    return rx.flex(
        rx.hstack(
            rx.foreach(
                NAV_LINKS,
                lambda item: rx.link(item[0], href=item[1], color=bot.MUTED, fontSize="0.9rem",
                                     _hover={"color": bot.ACCENT}),
            ),
            spacing="5",
        ),
        justify="between",
        width="100%",
        padding="0.75rem 1rem",
        borderBottom="1px solid rgba(255,255,255,0.06)",
    )


def footer() -> rx.Component:
    return rx.text(
        "Frank Escudero · frank-escudero.com · self-hosted on the story-tegu tailnet",
        color=bot.MUTED, fontSize="0.8rem", textAlign="center", padding="2rem 1rem 1rem",
    )


def chat_panel() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text("Ask the site", fontWeight="700", color="#e8ecf4", fontSize="0.95rem"),
                rx.spacer(),
                rx.button("✕", on_click=State.close_chat_popup, size="1", variant="ghost",
                          color=bot.MUTED, _hover={"color": "#fff"}),
            ),
            rx.vstack(
                rx.foreach(State.messages, lambda m: _message_bubble(m)),
                id="chat-log",
                width="100%",
                overflowY="auto",
                spacing="2",
                maxHeight="40vh",
            ),
            rx.el.form(
                rx.hstack(
                    rx.el.input(
                        name="text",
                        id="chat-input",
                        placeholder="Message the site…",
                        auto_complete="off",
                        style={
                            "flex": "1",
                            "background": "#0d1117",
                            "color": "#e8ecf4",
                            "border": "1px solid #2a3247",
                            "borderRadius": "0.5rem",
                            "padding": "0.55rem 0.75rem",
                            "fontFamily": "inherit",
                        },
                        on_change=State.on_idle,
                    ),
                    rx.button(
                        "Send", type="submit",
                        disabled=State.busy,
                        background=bot.ACCENT, color="#0b0e14", fontWeight="600",
                    ),
                    spacing="2",
                    width="100%",
                ),
                on_submit=[State.handle_submit, rx.call_script(js.focus_js("chat-input"))],
                auto_complete="off",
                reset_on_submit=True,
                width="100%",
                marginTop="0.75rem",
            ),
            width="100%",
        ),
        id="chat-panel",
        background="#0d1117",
        border="1px solid #2a3247",
        borderRadius="0.75rem",
        width="min(340px, 90vw)",
        padding="1rem",
        boxShadow="0 24px 60px rgba(0,0,0,0.5)",
    )


def _message_bubble(m) -> rx.Component:
    return rx.box(
        rx.text(
            m["content"],
            color=rx.cond(m["role"] == "user", "#0b0e14", "#e8ecf4"),
            fontSize="0.86rem",
            whiteSpace="pre-wrap",
        ),
        background=rx.cond(m["role"] == "user", bot.ACCENT, "#1b2333"),
        alignSelf=rx.cond(m["role"] == "user", "flex-end", "flex-start"),
        maxWidth="85%",
        borderRadius="0.6rem",
        padding="0.5rem 0.7rem",
        width="auto",
    )


def chat_widget() -> rx.Component:
    return rx.box(
        rx.cond(
            State.chat_open,
            rx.box(chat_panel(), position="fixed", right="1.5rem", bottom="5.5rem", zIndex=1000),
        ),
        rx.button(
            rx.icon(tag="message-circle", size=20),
            rx.text("Chat", fontSize="0.85rem"),
            on_click=State.toggle_chat,
            background=bot.ACCENT, color="#0b0e14", fontWeight="600",
            style={"position": "fixed", "right": "1.5rem", "bottom": "1.5rem",
                   "zIndex": 1001, "borderRadius": "9999px", "padding": "0.65rem 1rem",
                   "boxShadow": "0 8px 24px rgba(0,0,0,0.4)"},
        ),
        position="fixed",
        inset="0",
        pointerEvents="none",
    )


def cv_body(md: str) -> rx.Component:
    return rx.container(
        rx.markdown(md, color="#c9d2e3", fontSize="0.95rem"),
        maxWidth="760px",
        padding="2rem 1rem",
    )


def timeline_body() -> rx.Component:
    from . import timeline
    return rx.container(
        rx.heading("Timeline", size="4", color="#e8ecf4", marginBottom="1rem"),
        rx.markdown(State.timeline_md, color="#c9d2e3", fontSize="0.9rem"),
        maxWidth="760px",
        padding="2rem 1rem",
    )


def block_injectors(device_id: str) -> list[rx.Component]:
    """Render a client's CSS/HTML/JS blocks from DB into the page."""
    from . import blocks, theme
    parts: list[rx.Component] = []

    # base per-client theme
    profile = State.get_profile_for(device_id)
    parts.append(rx.style(theme.theme_css(profile)))

    for kind, rows in blocks.for_client(device_id).items():
        for row in rows:
            content = row.get("content") or ""
            if kind == "css":
                parts.append(rx.style(content))
            elif kind == "html":
                parts.append(rx.html(content))
            elif kind == "js":
                parts.append(rx.script(content))
    return parts


def page_shell(inner: rx.Component, device_id: str = "") -> rx.Component:
    return rx.vstack(
        nav(),
        rx.cond(
            State.block_injected,
            rx.fragment(*block_injectors(device_id)),
        ),
        inner,
        footer(),
        chat_widget(),
        width="100%",
        minHeight="100vh",
    )