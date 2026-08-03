from __future__ import annotations

import json
import logging
import pathlib

import httpx
import reflex as rx

logger = logging.getLogger("web")
WEB = pathlib.Path("/web")
OLLAMA_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL = "gemma4:latest"
FALLBACK = (
    "I couldn't formulate a reliable answer right now. "
    "The site is still a work in progress - ask again later."
)

BG = "radial-gradient(ellipse at top, #1c2333, #0b0e14)"
CARD = {
    "padding": "2rem",
    "borderRadius": "0.9rem",
    "background": "#131826",
    "border": "1px solid #2a3247",
    "boxShadow": "0 12px 40px rgb(0 0 0 / .5)",
}
ACCENT = "#4ade80"
MUTED = "#66708a"


def read_doc(name: str) -> str:
    try:
        return (WEB / name).read_text()
    except OSError:
        return f"<!-- missing {name} -->"


def build_failed_marker() -> str | None:
    marker = WEB / ".last_build_failed"
    try:
        if marker.exists():
            return "ai build failed last " + marker.read_text().strip()
    except OSError:
        return "ai build failed last <unknown>"
    return None


def _system_message() -> dict[str, str]:
    return {
        "role": "system",
        "content": read_doc("prompt.md") + "\n\nKNOWLEDGE:\n" + read_doc("knowledge.md"),
    }


async def _ai_call(messages: list[dict[str, str]]) -> str:
    async with httpx.AsyncClient(base_url=OLLAMA_URL, timeout=httpx.Timeout(300.0)) as client:
        resp = await client.post(
            "/v1/chat/completions",
            json={"model": OLLAMA_MODEL, "messages": messages, "temperature": 0.4},
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


async def filter_draft(draft: str) -> tuple[bool, str]:
    system = (
        "You are a strict quality filter. Apply the requirements below to the "
        'draft answer and reply with JSON only: {"pass": true} or '
        '{"pass": false, "reason": "..."}.\n\nREQUIREMENTS:\n'
        + read_doc("filter.md")
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Draft answer to review:\n\n{draft}"},
    ]
    try:
        raw = await _ai_call(messages)
        start = raw.find("{")
        data = json.loads(raw[start : raw.find("}", start) + 1])
        return bool(data.get("pass")), str(data.get("reason", ""))
    except Exception as exc:  # noqa: BLE001
        logger.warning("filter parse failed (%s), passing draft", exc)
        return True, ""


class State(rx.State):
    messages: list[dict[str, str]] = []
    question: str = ""
    busy: bool = False

    def set_question(self, value: str):
        self.question = value

    async def handle_submit(self):
        q = self.question.strip()
        if not q or self.busy:
            return
        self.messages.append({"role": "user", "content": q})
        self.question = ""
        self.busy = True
        yield
        try:
            history = [_system_message(), *self.messages[-10:]]
            draft = await _ai_call(history)
            ok, reason = await filter_draft(draft)
            if not ok:
                logger.warning("answer filtered out: %s", reason)
            reply = draft if ok else FALLBACK
        except Exception as exc:  # noqa: BLE001
            logger.exception("chat backend failure")
            reply = f"(chat backend error: {exc.__class__.__name__})"
        self.messages.append({"role": "assistant", "content": reply})
        self.busy = False
        yield


def banner() -> rx.Component | None:
    text = build_failed_marker()
    if text is None:
        return None
    return rx.box(
        text,
        color="#fca5a5",
        background="#3f1214",
        border="1px solid #7f1d1d",
        padding="0.6rem 1rem",
        borderRadius="0.5rem",
        marginBottom="1rem",
        fontFamily="monospace",
    )


def chat_message(item: dict[str, str]) -> rx.Component:
    is_user = item["role"] == "user"
    return rx.box(
        rx.text(item["content"]),
        alignSelf=rx.cond(is_user, "flex-end", "flex-start"),
        background=rx.cond(is_user, "#1f2937", "#182032"),
        color="#e8ecf4",
        border="1px solid #2f3b52",
        borderRadius="0.8rem",
        padding="0.6rem 0.9rem",
        maxWidth="85%",
        whiteSpace="pre-wrap",
    )


def chat_panel() -> rx.Component:
    return rx.box(
        rx.heading("Ask the site", size="2", color="#e8ecf4", marginBottom="1rem"),
        rx.vstack(
            rx.foreach(State.messages, chat_message),
            spacing="3",
            width="100%",
            overflowY="auto",
            maxHeight="45vh",
        ),
        rx.el.form(
            rx.hstack(
                rx.el.input(
                    name="question",
                    value=State.question,
                    on_change=State.set_question,
                    placeholder="Ask something about this site...",
                    disabled=State.busy,
                    style={
                        "flex": "1",
                        "background": "#0d1117",
                        "color": "#e8ecf4",
                        "border": "1px solid #2a3247",
                        "borderRadius": "0.5rem",
                        "padding": "0.6rem 0.8rem",
                        "fontFamily": "inherit",
                    },
                ),
                rx.button(
                    "Send",
                    type="submit",
                    disabled=State.busy,
                    background=ACCENT,
                    color="#0b0e14",
                    fontWeight="600",
                ),
                spacing="2",
                width="100%",
            ),
            on_submit=State.handle_submit,
            width="100%",
            marginTop="1rem",
        ),
        **CARD,
        width="min(720px, 92vw)",
    )


def index() -> rx.Component:
    return rx.center(
        rx.vstack(
            rx.heading("web", size="5", color="#e8ecf4"),
            rx.text("this is a work in progress...", color=ACCENT),
            banner(),
            chat_panel(),
            rx.hstack(
                rx.link("About me", href="/about", color=ACCENT),
                rx.text("cv", color=MUTED),
                spacing="4",
                fontSize="0.85rem",
            ),
            spacing="5",
            width="100%",
            padding="2.5rem 1rem",
            align="center",
        ),
        width="100%",
        minHeight="100vh",
        background=BG,
        fontFamily="ui-monospace, Menlo, monospace",
    )


def about() -> rx.Component:
    body = read_doc("knowledge.md")
    return rx.center(
        rx.vstack(
            rx.heading("About me", size="4", color="#e8ecf4"),
            rx.link("Back to main", href="/", color=ACCENT, fontSize="0.85rem"),
            rx.markdown(body, color="#c9d2e3"),
            spacing="4",
            width="min(860px, 92vw)",
            padding="2.5rem 1rem",
        ),
        width="100%",
        minHeight="100vh",
        background=BG,
        fontFamily="ui-monospace, Menlo, monospace",
    )


app = rx.App()
app.add_page(index, route="/", title="web")
app.add_page(about, route="/about", title="About me")
