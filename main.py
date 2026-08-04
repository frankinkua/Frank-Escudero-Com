from __future__ import annotations

import json
import logging
import os
import pathlib
import subprocess
from datetime import datetime, timedelta, timezone

import httpx
import reflex as rx
from openai import AsyncOpenAI

logger = logging.getLogger("web")
WEB = pathlib.Path("/web")
# Remote LM Studio OpenAI-compatible endpoint (self-hosted at frank's LAN).
# Same box/model the cron worker uses; bonsai stays loaded in VRAM.
# NOTE: this is an external service; revoke/invalidate the key if it leaks.
CHAT_URL = "http://192.168.178.120:1234/v1"
CHAT_API_KEY = "lm-studio"  # LM Studio gate; keep as placeholder token
CHAT_MODEL = "prism-ml/bonsai-27b"
chat_client: AsyncOpenAI | None = None


def get_chat_client() -> AsyncOpenAI:
    global chat_client
    if chat_client is None:
        chat_client = AsyncOpenAI(
            base_url=CHAT_URL, api_key=CHAT_API_KEY, timeout=httpx.Timeout(300.0)
        )
    return chat_client
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

# Client-side probe: run once per page load, JSON-encodes what the browser
# tells us so the server can personalise the greeting. Fires via rx.call_script.
BROWSER_INFO_JS = (
    "JSON.stringify({"
    "lang:navigator.language||'',"
    "langs:(navigator.languages||[]).join(','),"
    "tz:(Intl.DateTimeFormat().resolvedOptions().timeZone)||'',"
    "platform:navigator.platform||'',"
    "cores:navigator.hardwareConcurrency||0,"
    "mem:navigator.deviceMemory||0,"
    "online:navigator.onLine,"
    "screen:screen.width+'x'+screen.height"
    "})"
)

# Maps an IETF language tag (en-US, de, fr, nl, es...) to a spoken English name
# so the LLM can address the visitor in the right language even when the tag
# is ambiguous. Best-effort; unknown tags fall back to the raw code.
_LANG_NAMES = {
    "en": "English", "de": "German", "nl": "Dutch", "fr": "French",
    "es": "Spanish", "pt": "Portuguese", "it": "Italian", "pl": "Polish",
    "ru": "Russian", "tr": "Turkish", "sv": "Swedish", "no": "Norwegian",
    "da": "Danish", "fi": "Finnish", "hu": "Hungarian", "cs": "Czech",
    "ro": "Romanian", "bg": "Bulgarian", "uk": "Ukrainian", "el": "Greek",
    "he": "Hebrew", "ar": "Arabic", "fa": "Persian", "hi": "Hindi",
    "bn": "Bengali", "ja": "Japanese", "zh": "Chinese", "ko": "Korean",
    "th": "Thai", "vi": "Vietnamese", "id": "Indonesian", "ms": "Malay",
    "ca": "Catalan", "hr": "Croatian", "sk": "Slovak", "sl": "Slovenian",
    "lt": "Lithuanian", "lv": "Latvian", "et": "Estonian", "is": "Icelandic",
}


def detect_language(prefs: str) -> str:
    """Pick the visitor's best language from an Accept-Language string."""
    for part in prefs.split(","):
        tag = part.split(";")[0].strip().lower()
        if not tag or tag == "*":
            continue
        base = tag.split("-")[0]
        return _LANG_NAMES.get(base, base)
    return "English"


async def _geo_lookup(ip: str) -> dict[str, str]:
    """Best-effort public IP -> country/city/region. Never raises."""
    if not ip or ip in {"127.0.0.1", "::1"}:
        return {}
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(f"http://ip-api.com/json/{ip}", params={"fields": "status,country,regionName,city,timezone"})
            d = r.json()
        if d.get("status") == "success":
            return {
                "country": d.get("country", ""),
                "region": d.get("regionName", ""),
                "city": d.get("city", ""),
                "timezone": d.get("timezone", ""),
            }
    except Exception:  # noqa: BLE001
        pass
    return {}


def _git(cmd: list[str]) -> str:
    try:
        return subprocess.run(
            cmd, cwd=WEB, capture_output=True, text=True, check=True, timeout=3
        ).stdout.strip()
    except Exception:
        return ""


def app_version() -> str:
    """Short deploy version: APP_VERSION env, else '0.1.0 (<7-char git SHA>)' (no leading v)."""
    env_v = os.environ.get("APP_VERSION", "").strip()
    if env_v:
        return env_v.lstrip("v")
    sha = _git(["git", "rev-parse", "--short", "HEAD"])
    return f"0.1.0 ({sha})" if sha else "0.1.0"


def app_updated() -> str:
    """Human-readable date the source last changed (git commit date, fallback file mtime)."""
    ci = _git(["git", "log", "-1", "--format=%ci"])
    if ci:
        try:
            dt = datetime.strptime(ci[:19], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M %Z").replace(" UTC", "")
        except Exception:
            return ci[:19]
    try:
        ts = datetime.fromtimestamp((WEB / "main.py").stat().st_mtime, timezone.utc)
        return ts.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "unknown"


VERSION_LABEL = app_version()
UPDATED_LABEL = app_updated()


def page_footer() -> rx.Component:
    """Persistent footer showing app version + last-updated date on every page."""
    return rx.hstack(
        rx.text(
            f"v{VERSION_LABEL}",
            fontSize="0.75rem",
            color="#64748b",
            fontFamily="ui-monospace, Menlo, monospace",
        ),
        rx.text(
            f"updated {UPDATED_LABEL}",
            fontSize="0.75rem",
            color="#64748b",
            fontFamily="ui-monospace, Menlo, monospace",
        ),
        rx.link(
            "worker log",
            href="/worker-log",
            fontSize="0.75rem",
            color="#64748b",
            fontFamily="ui-monospace, Menlo, monospace",
        ),
        justify="center",
        width="100%",
        padding="0.8rem",
        borderTop="1px solid #2a3247",
        opacity="0.7",
    )


# 48h target the countdown counts down to (UTC).
COUNTDOWN_TARGET = datetime(2026, 8, 5, 16, 0, 0, tzinfo=timezone.utc)


def countdown_label() -> str:
    """Server-side seed (seconds until target) — the browser ticks from here."""
    total = max(0, int((COUNTDOWN_TARGET - datetime.now(timezone.utc)).total_seconds()))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def work_in_progress_banner() -> rx.Component:
    """Big 'work in progress' banner with a simple client-side 48h countdown."""
    js = (
        "if (!window.countdownStarted) {"
        "  window.countdownStarted = true;"
        "  var end=new Date('" + COUNTDOWN_TARGET.isoformat() + "').getTime();"
        "  function fmt(ms){var n=Math.max(0,Math.floor(ms/1000));"
        "  var h=Math.floor(n/3600),m=Math.floor(n%3600/60),s=Math.floor(n%60);"
        "  return (n<=0?'00:00:00':h+'h '+('0'+m).slice(-2)+'m '+('0'+s).slice(-2)+'s');}"
        "  setInterval(function(){"
        "    var el=document.getElementById('cd-countdown');"
        "    if(el) el.textContent=fmt(end-Date.now());"
        "  },1000);"
        "}"
    )
    return rx.hstack(
        rx.text("WORK IN PROGRESS", color="#fca5a5", fontWeight="700", fontSize="1.1rem"),
        rx.spacer(),
        rx.html(
            f'<span id="cd-countdown" style="color:#4ade80;font-size:2rem;font-weight:700;'
            f'font-family:ui-monospace,Menlo,monospace;">Deployment in {countdown_label()}</span>'
        ),
        rx.script(js),
        width="100%",
        background="#0f141f",
        border="1px solid #2a3247",
        borderRadius="0.6rem",
        padding="0.7rem 1rem",
        marginBottom="1.2rem",
    )


# Inline SVG favicon (no /web/assets writes — app-only). A small "FE" monogram.
FAVICON_SVG = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
    "viewBox='0 0 64 64'%3E%3Crect width='64' height='64' fill='%230b0e14'/"
    "%3E%3Ctext x='50%25' y='55' dominant-baseline='middle' text-anchor='middle' "
    "fill='%234ade80' font-family='monospace' font-size='30' font-weight='700'"
    "%3EFE%3C/text%3E%3C/svg%3E"
)


def markdown_page(title: str, doc: str, body: str) -> rx.Component:
    """Shared layout for content pages: heading + markdown body + footer nav."""
    return rx.center(
        rx.vstack(
            rx.heading(title, size="4", color="#e8ecf4"),
            rx.link("Back to main", href="/", color=ACCENT, fontSize="0.85rem"),
            rx.markdown(body, color="#c9d2e3"),
            page_footer(),
            spacing="4",
            width="min(860px, 92vw)",
            padding="2.5rem 1rem",
            align="center",
        ),
        width="100%",
        minHeight="100vh",
        background=BG,
        fontFamily="ui-monospace, Menlo, monospace",
    )


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


WORKER_LOG = pathlib.Path("/var/log/opencode-worker.log")


def worker_run_summary() -> list[dict[str, str]]:
    """Parse per-run lines out of the worker log into a reverse-chron summary."""
    try:
        lines = WORKER_LOG.read_text(errors="replace").splitlines()
    except OSError:
        return []
    runs: dict[int, dict[str, str]] = {}
    order: list[int] = []
    for ln in lines:
        marker = " worker: run "
        if marker not in ln:
            continue
        try:
            pre, rest = ln.split(marker, 1)
            num, _, tail = rest.partition(" ")
            n = int(num)
            ts = pre.strip()
        except (ValueError, IndexError):
            continue
        if n not in runs:
            runs[n] = {"run": num, "ts": ts, "start": tail, "end": "", "rc": "", "status": ""}
            order.append(n)
        d = runs[n]
        if tail.startswith("start"):
            d["start"] = tail[len("start"):].strip().strip("()")
            d["ts"] = ts
        elif tail.startswith("done"):
            d["end"] = ts
            d["status"] = tail[len("done"):].strip()
        elif tail.startswith("committed"):
            d["status"] = d["status"] or "committed"
        elif tail.startswith("SITE DOWN"):
            d["status"] = "SITE DOWN (rolled back)"
        elif tail.startswith("finished"):
            d["status"] = d["status"] or "finished"
    return [runs[n] for n in reversed(order)]


def worker_log_tail(lines: int = 60) -> str:
    try:
        return "\n".join(WORKER_LOG.read_text(errors="replace").splitlines()[-lines:])
    except OSError:
        return "(no worker log yet)"


def worker_log_page() -> rx.Component:
    runs = worker_run_summary()
    summary = [
        rx.text("No worker runs logged yet.", color=MUTED)
        if not runs
        else rx.vstack(
            *[
                rx.box(
                    rx.hstack(
                        rx.text(f"run {d['run']}", color=ACCENT, fontWeight="600"),
                        rx.text(d["ts"], color=MUTED, fontSize="0.8rem"),
                        justify="between",
                        width="100%",
                    ),
                    rx.text(d.get("start", ""), color="#c9d2e3", fontSize="0.85rem"),
                    rx.text(
                        f"{d.get('end', '-')}  {d.get('status', '')}",
                        color=MUTED,
                        fontSize="0.8rem",
                    ),
                    background="#131826",
                    border="1px solid #2a3247",
                    borderRadius="0.5rem",
                    padding="0.7rem 0.9rem",
                    width="100%",
                )
                for d in runs
            ],
            spacing="2",
            width="100%",
        ),
    ]
    return rx.center(
        rx.vstack(
            rx.heading("worker log", size="4", color="#e8ecf4"),
            rx.link("Back to main", href="/", color=ACCENT, fontSize="0.85rem"),
            rx.text("per-run summary (most recent first)", color=MUTED, fontSize="0.8rem"),
            *summary,
            rx.text("raw tail", color=MUTED, fontSize="0.8rem"),
            rx.box(
                rx.text(worker_log_tail(), whiteSpace="pre-wrap", color="#c9d2e3", fontSize="0.75rem"),
                background="#0d1117",
                border="1px solid #2a3247",
                borderRadius="0.5rem",
                padding="0.7rem 0.9rem",
                width="100%",
                overflowX="auto",
            ),
            page_footer(),
            spacing="4",
            width="min(860px, 92vw)",
            padding="2.5rem 1rem",
            align="center",
        ),
        width="100%",
        minHeight="100vh",
        background=BG,
        fontFamily="ui-monospace, Menlo, monospace",
    )


def _system_message() -> dict[str, str]:
    return {
        "role": "system",
        "content": read_doc("prompt.md") + "\n\nKNOWLEDGE:\n" + read_doc("knowledge.md"),
    }


async def _ai_call(messages: list[dict[str, str]]) -> str:
    """Full (non-streamed) completion via the remote LM Studio endpoint."""
    client = get_chat_client()
    resp = await client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        temperature=0.4,
        reasoning_effort="none",
        max_tokens=2048,
    )
    return resp.choices[0].message.content.strip()


async def filter_draft(question: str, draft: str) -> tuple[bool, str]:
    system = (
        "You are a strict quality filter. Apply the requirements below to the "
        'draft answer and reply with JSON only: {"pass": true} or '
        '{"pass": false, "reason": "..."}.\n\nREQUIREMENTS:\n'
        + read_doc("filter.md")
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Visitor question: {question}\n\nDraft answer to review:\n\n{draft}"},
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
    greeted: bool = False

    def set_question(self, value: str):
        self.question = value

    def probe_browser(self):
        """on_load hook: ask the client for its fingerprint, feed on_browser_info."""
        return rx.call_script(BROWSER_INFO_JS, callback=State.on_browser_info)

    async def on_browser_info(self, info: str):
        """First event: browser fingerprint from the client -> personal greeting.

        Runs on page load (via on_load -> rx.call_script callback). Guarded by
        `greeted` so navigating back to `/` doesn't greet twice per session.
        """
        if self.greeted:
            return
        self.greeted = True

        browser: dict[str, str] = {}
        try:
            browser = json.loads(info or "{}")
        except Exception:  # noqa: BLE001
            pass

        header = self.router.headers  # server-side, from the HTTP request
        ip = self.router.session.client_ip
        geo = await _geo_lookup(ip)

        # Language: prefer the browser's reported language, then the header.
        prefs = " ".join(
            str(x) for x in (
                browser.get("lang") or browser.get("langs") or header.accept_language
            ) if x
        )
        lang = detect_language(prefs) if prefs else "English"

        # Assemble the context we pass to the LLM.
        detail: list[str] = []
        if browser.get("platform"):
            detail.append(f"platform: {browser['platform']}")
        if browser.get("screen"):
            detail.append(f"screen: {browser['screen']}")
        if browser.get("cores"):
            detail.append(f"cpu cores: {browser['cores']}")
        if browser.get("tz"):
            detail.append(f"timezone: {browser['tz']}")
        if geo.get("city") and geo.get("country"):
            detail.append(f"likely region: {geo['city']}, {geo['country']}")
        elif geo.get("country"):
            detail.append(f"likely country: {geo['country']}")

        self.messages.append({"role": "assistant", "content": ""})
        yield
        try:
            client = get_chat_client()
            stream = await client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            read_doc("prompt.md")
                            + "\n\nKNOWLEDGE:\n"
                            + read_doc("knowledge.md")
                            + "\n\nNow: you just detected a new visitor. Write a short "
                            f"personal greeting for them in {lang} (the visitor's language - "
                            f"EVERY word you write must be in {lang}, no exceptions). Make it "
                            "warm and relevant using only the visitor details below. It must be "
                            "1-3 sentences, feel natural, and END by asking the visitor who "
                            "they are. Do not mention IP addresses, tokens, or anything "
                            "sensitive. "
                            f"Visitor details: {'; '.join(detail) or 'no browser details available'}."
                        ),
                    },
                    {"role": "user", "content": "Greet me and ask who I am."},
                ],
                temperature=0.7,
                reasoning_effort="none",
                max_tokens=300,
                stream=True,
            )
            chunks: list[str] = []
            async for event in stream:
                if not event.choices:
                    continue
                delta = event.choices[0].delta.content or ""
                if delta:
                    chunks.append(delta)
                    self.messages[-1]["content"] = "".join(chunks)
                    yield
            if not chunks:
                self.messages[-1]["content"] = (
                    f"Hi! I'm Frank's assistant — welcome. I can tell you're in "
                    f"{detail[0] if detail else 'a browser'} right now. Who are you?"
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("greeting generation failed")
            self.messages[-1]["content"] = (
                "Hi! I'm Frank's assistant. Ask me anything about Frank's CV. Who are you?"
            )

    async def handle_submit(self):
        q = self.question.strip()
        if not q or self.busy:
            return
        self.messages.append({"role": "user", "content": q})
        self.question = ""
        self.busy = True
        self.messages.append({"role": "assistant", "content": ""})
        yield
        try:
            history = [_system_message(), *self.messages[:-1][-10:]]
            client = get_chat_client()
            stream = await client.chat.completions.create(
                model=CHAT_MODEL,
                messages=history,
                temperature=0.4,
                reasoning_effort="none",
                max_tokens=2048,
                stream=True,
            )
            chunks: list[str] = []
            async for event in stream:
                if not event.choices:
                    continue
                delta = event.choices[0].delta.content or ""
                if delta:
                    chunks.append(delta)
                    self.messages[-1]["content"] = "".join(chunks)
                    yield
            draft = "".join(chunks).strip()
            ok, reason = await filter_draft(q, draft)
            if not ok:
                logger.warning("answer filtered out: %s", reason)
            self.messages[-1]["content"] = draft if ok else FALLBACK
        except Exception as exc:  # noqa: BLE001
            logger.exception("chat backend failure")
            self.messages[-1]["content"] = (
                f"(chat backend error: {exc.__class__.__name__})"
            )
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
            rx.hstack(
                rx.heading("Agentic Generated Self-Hosted AI Webserver", size="5", color="#e8ecf4"),
                rx.link("timeline", href="/timeline", color=MUTED, fontSize="0.8rem"),
                width="min(720px, 92vw)",
                justify="between",
                alignItems="center",
            ),
            work_in_progress_banner(),
            rx.text("a zero-trust CV site built and maintained by Frank.", color=ACCENT),
            banner(),
            chat_panel(),
            rx.hstack(
                rx.link("About me", href="/about", color=ACCENT),
                rx.link("CV", href="/cv", color=ACCENT),
                rx.link("Deployment", href="/deploy", color=ACCENT),
                rx.link("Stack", href="/stack", color=ACCENT),
                rx.link("Timeline", href="/timeline", color=ACCENT),
                rx.text("cv", color=MUTED),
                spacing="4",
                fontSize="0.85rem",
                width="min(720px, 92vw)",
                justify="center",
            ),
            page_footer(),
            spacing="5",
            width="100%",
            maxWidth="760px",
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
            page_footer(),
            spacing="4",
            width="min(860px, 92vw)",
            padding="2.5rem 1rem",
            align="center",
        ),
        width="100%",
        minHeight="100vh",
        background=BG,
        fontFamily="ui-monospace, Menlo, monospace",
    )


def cv() -> rx.Component:
    return markdown_page("Frank Escudero — CV", "cv.md", read_doc("cv.md"))


def deploy() -> rx.Component:
    body = read_doc("deploy.md") + "\n\n" + countdown_label()
    return markdown_page("Deployment", "deploy.md", body)


def stack() -> rx.Component:
    return markdown_page("Tech stack", "stack.md", read_doc("stack.md"))


def timeline() -> rx.Component:
    return markdown_page(
        "Timeline",
        "timeline.md",
        "# Timeline\n\n" + read_doc("timeline.md"),
    )


app = rx.App(
    head_components=[
        rx.el.link(rel="icon", type="image/svg+xml", href=FAVICON_SVG),
        rx.el.link(rel="apple-touch-icon", href=FAVICON_SVG),
        rx.el.meta(name="description", content="Frank Escudero CV - zero-trust, self-hosted, AI-updated virtual employee."),
    ],
)
app.add_page(index, route="/", title="Frank Escudero — virtual-employee CV", on_load=State.probe_browser)
app.add_page(about, route="/about", title="About — Frank Escudero")
app.add_page(cv, route="/cv", title="CV — Frank Escudero")
app.add_page(deploy, route="/deploy", title="Deployment — Frank Escudero CV")
app.add_page(stack, route="/stack", title="Tech stack — Frank Escudero CV")
app.add_page(timeline, route="/timeline", title="Timeline — Frank Escudero CV")
app.add_page(worker_log_page, route="/worker-log", title="Worker log — Frank Escudero CV")
