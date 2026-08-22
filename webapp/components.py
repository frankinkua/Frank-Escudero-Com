"""Presentational Reflex components for the CV site."""

from __future__ import annotations

import reflex as rx

from . import bot, js, theme
from .state import State
from .device import normalize_device_name


def _seconds(t: float) -> str:
    import datetime
    try:
        return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%H:%M UTC")
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
            rx.link(
                "Frank Escudero",
                href="/",
                color="#e8ecf4",
                fontWeight="700",
                fontSize="1rem",
                _hover={"color": bot.ACCENT},
            ),
            rx.spacer(),
            rx.foreach(
                NAV_LINKS,
                lambda item: rx.link(item[0], href=item[1], color=bot.MUTED, fontSize="0.9rem",
                                     _hover={"color": bot.ACCENT}),
            ),
            width="100%",
            spacing="5",
        ),
        justify="between",
        width="100%",
        padding="0.9rem 1.5rem",
        borderBottom="1px solid rgba(255,255,255,0.06)",
    )


def footer() -> rx.Component:
    return rx.text(
        "Frank Escudero · frank-escudero.com · self-hosted on a private tailnet",
        color=bot.MUTED, fontSize="0.8rem", textAlign="center", padding="2rem 1rem 1rem",
    )


def _message_bubble(m: dict) -> rx.Component:
    is_user = m.get("role") == "user"
    return rx.flex(
        rx.cond(
            is_user,
            rx.hstack(
                rx.text(m["content"], color="#0b0e14", fontSize="0.86rem", whiteSpace="pre-wrap"),
                background=bot.ACCENT,
                borderRadius="0.6rem 0.6rem 0.2rem 0.6rem",
                padding="0.5rem 0.7rem",
                maxWidth="85%",
                width="auto",
            ),
            rx.flex(
                rx.vstack(
                    rx.box(),
                    rx.text(m["content"], color="#e8ecf4", fontSize="0.86rem", whiteSpace="pre-wrap"),
                    spacing="1",
                    alignItems="start",
                ),
                background="#1b2333",
                borderRadius="0.6rem 0.6rem 0.6rem 0.2rem",
                padding="0.5rem 0.7rem",
                maxWidth="85%",
                width="auto",
            ),
        ),
        justify=rx.cond(is_user, "end", "start"),
        width="100%",
    )


def chat_panel() -> rx.Component:
    return rx.box(
        rx.el.style(js.CHAT_CSS),
        rx.el.script(js.CHAT_SETUP_JS),
        rx.flex(
            rx.hstack(
                rx.box(
                    width="0.55rem", height="0.55rem", borderRadius="9999px",
                    background=bot.ACCENT,
                ),
                rx.vstack(
                    rx.text("Frank's site assistant", fontWeight="700", color="#e8ecf4", fontSize="0.92rem"),
                    rx.text(
                        rx.cond(State.busy, "thinking…", f"asks about {State.device_name}"),
                        color=bot.MUTED, fontSize="0.72rem",
                    ),
                    spacing="0",
                    alignItems="start",
                ),
                spacing="3",
            ),
            rx.hstack(
                rx.el.button(
                    rx.el.span(rx.icon(tag="maximize", size=15), class_name="cv-icon-max"),
                    rx.el.span(rx.icon(tag="minimize", size=15), class_name="cv-icon-restore"),
                    id="chat-max",
                    type="button",
                    aria_label="Maximize / restore chat",
                    background="transparent", border="none", color=bot.MUTED,
                    cursor="pointer", padding="0.2rem", borderRadius="0.35rem",
                    _hover={"color": "#fff", "background": "rgba(255,255,255,0.08)"},
                ),
                rx.button(
                    "✕", on_click=State.close_chat_popup, size="1", variant="ghost",
                    color=bot.MUTED, _hover={"color": "#fff"},
                    aria_label="Close chat",
                ),
                spacing="1",
            ),
            id="chat-header",
            justify="between",
            width="100%",
            paddingBottom="0.6rem",
            borderBottom="1px solid rgba(255,255,255,0.08)",
        ),
        rx.vstack(
            rx.foreach(State.messages, lambda m: _message_bubble(m)),
            rx.cond(
                State.busy,
                rx.text("typing…", color=bot.MUTED, fontSize="0.75rem", fontStyle="italic"),
            ),
            id="chat-log",
            width="100%",
            overflowY="auto",
            flexGrow="1",
            spacing="2",
            minHeight="180px",
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
                    disabled=State.busy,
                ),
                rx.button(
                    rx.cond(State.busy, rx.spinner(size="1"), rx.text("Send", fontSize="0.85rem")),
                    type="submit",
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
        rx.box(
            id="chat-resize",
            aria_label="Resize chat",
            title="Drag to resize",
        ),
        id="chat-window",
        background="#0d1117",
        border="1px solid #2a3247",
        borderRadius="0.9rem",
        padding="0.9rem",
        boxShadow="0 24px 60px rgba(0,0,0,0.5)",
        display="flex",
        flexDirection="column",
        gap="0.75rem",
        pointerEvents="auto",
    )


def chat_widget() -> rx.Component:
    """Floating chat FAB + panel. The outer wrapper is a transparent
    full-viewport layer with pointer-events:none so it never blocks the page;
    the FAB and the panel opt back in via pointer-events:auto."""
    return rx.box(
        rx.cond(
            State.chat_open,
            chat_panel(),
        ),
        rx.button(
            rx.icon(tag="message-circle", size=20),
            rx.text("Chat", fontSize="0.85rem"),
            on_click=State.toggle_chat,
            background=bot.ACCENT, color="#0b0e14", fontWeight="600",
            style={
                "position": "fixed", "right": "1.5rem", "bottom": "1.5rem",
                "zIndex": 1001, "borderRadius": "9999px", "padding": "0.65rem 1.1rem",
                "boxShadow": "0 8px 24px rgba(0,0,0,0.4)",
                "pointerEvents": "auto",
            },
        ),
        position="fixed",
        inset="0",
        pointerEvents="none",
    )


def cv_body(md: str) -> rx.Component:
    return rx.container(
        rx.heading("Curriculum Vitae", size="5", color="#e8ecf4", marginBottom="1rem"),
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
    from . import blocks
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