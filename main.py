from __future__ import annotations

import json
import logging
import os
import pathlib
import subprocess
import time
from datetime import datetime, timedelta, timezone

import httpx
import reflex as rx
from openai import AsyncOpenAI
from zoneinfo import ZoneInfo

logger = logging.getLogger("web")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _console = logging.StreamHandler()
    _console.setLevel(logging.INFO)
    logger.addHandler(_console)
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
    "now:Date.now(),"
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
    """Best-effort public IP -> country/countryCode/city/lat/lon/timezone. Never raises."""
    if not ip or ip in {"127.0.0.1", "::1"}:
        return {}
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(
                f"http://ip-api.com/json/{ip}",
                params={"fields": "status,country,countryCode,regionName,city,lat,lon,timezone"},
            )
            d = r.json()
        if d.get("status") == "success":
            return {
                "country": d.get("country", ""),
                "country_code": d.get("countryCode", ""),
                "region": d.get("regionName", ""),
                "city": d.get("city", ""),
                "lat": d.get("lat", ""),
                "lon": d.get("lon", ""),
                "timezone": d.get("timezone", ""),
            }
    except Exception:  # noqa: BLE001
        pass
    return {}


def _country_flag(country_code: str) -> str:
    """ISO 3166-1 alpha-2 -> flag emoji (regional indicator symbols)."""
    cc = (country_code or "").upper().strip()
    if len(cc) != 2 or not cc.isalpha():
        return ""
    return chr(0x1F1E6 + ord(cc[0]) - ord("A")) + chr(0x1F1E6 + ord(cc[1]) - ord("A"))


# Best-guess language -> flag emoji when the visitor's country is unknown.
_LANG_FLAGS = {
    "en": "🇬🇧", "de": "🇩🇪", "nl": "🇳🇱", "fr": "🇫🇷", "es": "🇪🇸", "pt": "🇵🇹",
    "it": "🇮🇹", "pl": "🇵🇱", "ru": "🇷🇺", "tr": "🇹🇷", "sv": "🇸🇪", "no": "🇳🇴",
    "da": "🇩🇰", "fi": "🇫🇮", "hu": "🇭🇺", "cs": "🇨🇿", "ro": "🇷🇴", "bg": "🇧🇬",
    "uk": "🇺🇦", "el": "🇬🇷", "he": "🇮🇱", "ar": "🇸🇦", "fa": "🇮🇷", "hi": "🇮🇳",
    "bn": "🇧🇩", "ja": "🇯🇵", "zh": "🇨🇳", "ko": "🇰🇷", "th": "🇹🇭", "vi": "🇻🇳",
    "id": "🇮🇩", "ms": "🇲🇾", "ca": "🇦🇩", "hr": "🇭🇷", "sk": "🇸🇰", "sl": "🇸🇮",
    "lt": "🇱🇹", "lv": "🇱🇻", "et": "🇪🇪", "is": "🇮🇸",
}


def _language_flag(lang: str) -> str:
    """Spoken language name (e.g. 'German') -> flag emoji, best-effort."""
    for code, name in _LANG_NAMES.items():
        if name == lang:
            return _LANG_FLAGS.get(code, "")
    return ""


# WMO weather codes -> (emoji, plain-word description).
_WMO = {
    0: ("☀️", "clear"),
    1: ("🌤️", "mostly sunny"),
    2: ("⛅", "partly cloudy"),
    3: ("☁️", "overcast"),
    45: ("🌫️", "foggy"),
    48: ("🌫️", "icy fog"),
    51: ("🌦️", "light drizzle"),
    53: ("🌦️", "drizzle"),
    55: ("🌧️", "heavy drizzle"),
    56: ("🌧️", "freezing drizzle"),
    57: ("🌧️", "freezing drizzle"),
    61: ("🌦️", "light rain"),
    63: ("🌧️", "rain"),
    65: ("🌧️", "heavy rain"),
    66: ("🌧️", "freezing rain"),
    67: ("🌧️", "freezing rain"),
    71: ("🌨️", "light snow"),
    73: ("🌨️", "snow"),
    75: ("❄️", "heavy snow"),
    77: ("🌨️", "snow grains"),
    80: ("🌦️", "light showers"),
    81: ("🌧️", "showers"),
    82: ("⛈️", "heavy showers"),
    85: ("🌨️", "snow showers"),
    86: ("🌨️", "heavy snow showers"),
    95: ("⛈️", "thunderstorm"),
     96: ("⛈️", "thunderstorm with hail"),
     99: ("⛈️", "thunderstorm with hail"),
}


# WMO codes that warrant a weather-warning mention to the visitor.
_WARNINGS = {
    56: "freezing drizzle",
    57: "freezing drizzle",
    66: "freezing rain",
    67: "freezing rain",
    65: "heavy rain",
    82: "heavy showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with hail",
    99: "thunderstorm with hail",
}


def _weather_warning(code: object) -> str:
    """WMO weather code -> warning string, '' when nothing alarming."""
    try:
        return _WARNINGS.get(int(code), "")
    except (TypeError, ValueError):
        return ""


# Moon phase index -> (emoji, name). open-meteo reports 0=new .. 0.5=full .. 1=new.
_MOON = [
    ("🌑", "new moon"),
    ("🌒", "waxing crescent"),
    ("🌓", "first quarter"),
    ("🌔", "waxing gibbous"),
    ("🌕", "full moon"),
    ("🌖", "waning gibbous"),
    ("🌗", "last quarter"),
    ("🌘", "waning crescent"),
]


def _moon_phase(phase: object) -> tuple[str, str]:
    """open-meteo moon_phase (0..1) -> (emoji, name)."""
    try:
        p = float(phase)
    except (TypeError, ValueError):
        return "", ""
    idx = round(p * 8) % 8
    return _MOON[idx]


async def _weather_lookup(lat: str, lon: str) -> dict[str, str]:
    """Best-effort current weather + sun/moon times from open-meteo (no key). Never raises."""
    if not lat or not lon:
        return {}
    out: dict[str, str] = {}
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": (
                        "temperature_2m,apparent_temperature,relative_humidity_2m,"
                        "precipitation,pressure_msl,wind_speed_10m,weather_code,is_day"
                    ),
                    "timezone": "auto",
                },
            )
            d = r.json()
        cw = (d.get("current") or {})
        emoji, word = _WMO.get(cw.get("weather_code", -1), ("🌡️", "unknown"))
        temp = cw.get("temperature_2m")
        feels = cw.get("apparent_temperature")
        hum = cw.get("relative_humidity_2m")
        precip = cw.get("precipitation")
        press = cw.get("pressure_msl")
        wind = cw.get("wind_speed_10m")

        def _fmt(v: object, unit: str, plus: bool = False) -> str:
            """Format a numeric value to a short string ('22°C'), '' if missing."""
            try:
                f = float(v)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return ""
            return f"{f:+.0f}{unit}" if plus else f"{f:.0f}{unit}"

        out.update({
            "emoji": emoji,
            "word": word,
            "temp": _fmt(temp, "°C", plus=True),
            "feels_like": _fmt(feels, "°C", plus=True),
            "humidity": _fmt(hum, "%"),
            "precip": _fmt(precip, "mm"),
            "pressure": _fmt(press, "hPa"),
            "wind": _fmt(wind, "km/h"),
            "is_day": bool(cw.get("is_day", 1)),
            "warning": _weather_warning(cw.get("weather_code")),
        })
    except Exception:  # noqa: BLE001
        pass
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "daily": "sunrise,sunset,moon_phase",
                    "timezone": "auto",
                    "forecast_days": "1",
                },
            )
            d = r.json()
        day = (d.get("daily") or {})
        moon_emoji, moon_name = _moon_phase((day.get("moon_phase") or [None])[0])


        def _clock(v: object) -> str:
            """'2026-08-04T05:47' -> '05:47', else ''."""
            s = str(v or "")
            return s.split("T")[-1][:5] if "T" in s else s[:5]

        out.update({
            "sunrise": _clock((day.get("sunrise") or [""])[0]),
            "sunset": _clock((day.get("sunset") or [""])[0]),
            "moon": moon_name,
            "moon_emoji": moon_emoji,
        })
    except Exception:  # noqa: BLE001
        pass
    return out


def _time_of_day(hour: int) -> str:
    """Map a local 0-23 hour to a greeting phrase (for the LLM's flavour)."""
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 22:
        return "evening"
    return "night"


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


def changelog_markdown() -> str:
    """Full git history rendered as markdown, newest first."""
    log = _git(["git", "log", "--pretty=format:%h|%ci|%s", "-50"])
    if not log:
        return "_No git history available._"
    lines = []
    for row in log.splitlines():
        sha, ci, subj = (row.split("|", 2) + ["", ""])[:3]
        date = ci[:10]
        lines.append(f"- `{sha}` **{date}** — {subj}")
    return "# Changelog\n\n" + "\n".join(lines)


def changelog_entries() -> list[tuple[str, str, str]]:
    """[(sha, iso-date, subject)] newest first, for the RSS feed."""
    log = _git(["git", "log", "--pretty=format:%h|%ci|%s", "-20"])
    out: list[tuple[str, str, str]] = []
    for row in (log or "").splitlines():
        sha, ci, subj = (row.split("|", 2) + ["", ""])[:3]
        out.append((sha, ci, subj))
    return out


def rss_xml() -> str:
    """Atom-ish RSS feed of the git changelog (site updates)."""
    items = "\n".join(
        f"<item><title>{sha} — {subj}</title>"
        f"<link>https://cv.story-tegu.ts.net/changelog/</link>"
        f"<guid>{sha}</guid><pubDate>{ci}</pubDate></item>"
        for sha, ci, subj in changelog_entries()
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>'
        "<title>Frank Escudero CV — changelog</title>"
        "<link>https://cv.story-tegu.ts.net/</link>"
        "<description>Site updates for the self-hosted AI CV.</description>"
        f"{items}</channel></rss>\n"
    )


def sitemap_xml() -> str:
    """Basic XML sitemap of all public pages, for crawlers."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = [
        "", "/about", "/cv", "/projects", "/about-fun", "/contact",
        "/contribute", "/architecture", "/resources", "/status",
        "/changelog", "/deploy", "/stack", "/timeline", "/worker-log",
    ]
    entries = "\n".join(
        f"<url><loc>https://cv.story-tegu.ts.net{u}/</loc>"
        f"<lastmod>{now}</lastmod><changefreq>weekly</changefreq></url>"
        for u in urls
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{entries}\n</urlset>\n"
    )


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


# Markdown pages that are searchable (site content Frank wants indexed).
SEARCH_DOCS = [
    "knowledge.md", "cv.md", "projects.md", "deploy.md", "stack.md",
    "timeline.md", "contact.md", "about.md",
]


def search_docs(query: str, limit: int = 8) -> list[dict[str, str]]:
    """Simple case-insensitive full-text search over the markdown docs."""
    q = (query or "").strip().lower()
    if not q:
        return []
    hits: list[dict[str, str]] = []
    for name in SEARCH_DOCS:
        text = read_doc(name)
        low = text.lower()
        start = 0
        while len(hits) < limit and start < len(low):
            pos = low.find(q, start)
            if pos < 0:
                break
            begin = max(0, pos - 60)
            end = min(len(text), pos + len(q) + 80)
            snippet = text[begin:end].replace("\n", " ").strip()
            hits.append({"page": name, "snippet": snippet})
            start = pos + len(q)
    return hits


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


def system_uptime() -> str:
    """Human uptime + boot time from /proc/uptime. '' if unavailable."""
    try:
        secs = float(pathlib.Path("/proc/uptime").read_text().split()[0])
        h, rem = divmod(int(secs), 3600)
        m = rem // 60
        boot = datetime.fromtimestamp(
            time.time() - secs, tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M UTC")
        return f"{h}h {m}m (boot {boot})"
    except Exception:  # noqa: BLE001
        return ""


def uptime_seconds() -> int:
    """Uptime in whole seconds (seed for the live client-side ticker)."""
    try:
        return int(float(pathlib.Path("/proc/uptime").read_text().split()[0]))
    except Exception:  # noqa: BLE001
        return 0


def uptime_ticker_js() -> str:
    """JS that ticks a live uptime clock (#cd-uptime) once per second."""
    return (
        "if (!window.uptimeStarted) {"
        "  window.uptimeStarted = true;"
        "  var start=" + str(int(time.time())) + "-" + str(uptime_seconds()) + ";"
        "  function fmt(s){var d=Math.floor(s/86400),h=Math.floor(s%86400/3600),"
        "  m=Math.floor(s%3600/60),sec=s%60;"
        "  var out='';"
        "  if(d)out+=d+'d ';"
        "  out+=('0'+h).slice(-2)+':'+('0'+m).slice(-2)+':'+('0'+sec).slice(-2);"
        "  return out;}"
        "  setInterval(function(){"
        "    var el=document.getElementById('cd-uptime');"
        "    if(el) el.textContent=fmt(Math.floor(Date.now()/1000)-start);"
        "  },1000);"
        "}"
    )


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


def status_page() -> rx.Component:
    """Live server/worker status: version, uptime, last worker runs."""
    runs = worker_run_summary()
    return rx.center(
        rx.vstack(
            rx.heading("status", size="4", color="#e8ecf4"),
            rx.link("Back to main", href="/", color=ACCENT, fontSize="0.85rem"),
            rx.box(
                rx.vstack(
                    rx.hstack(
                        rx.text("app version", color=MUTED, fontSize="0.8rem"),
                        rx.text(VERSION_LABEL, color="#c9d2e3"),
                        justify="between",
                        width="100%",
                    ),
                    rx.hstack(
                        rx.text("updated", color=MUTED, fontSize="0.8rem"),
                        rx.text(UPDATED_LABEL, color="#c9d2e3"),
                        justify="between",
                        width="100%",
                    ),
                    rx.hstack(
                        rx.text("server uptime", color=MUTED, fontSize="0.8rem"),
                        rx.text(
                            system_uptime() or "n/a",
                            color="#c9d2e3",
                            id="cd-uptime",
                        ),
                        justify="between",
                        width="100%",
                    ),
                    rx.hstack(
                        rx.text("worker runs", color=MUTED, fontSize="0.8rem"),
                        rx.text(str(len(runs)), color="#c9d2e3"),
                        justify="between",
                        width="100%",
                    ),
                    rx.text(
                        "All pages: 200 · log sentinel: 0 B · Funnel: on",
                        color=MUTED,
                        fontSize="0.8rem",
                    ),
                    spacing="2",
                    width="100%",
                ),
                background="#131826",
                border="1px solid #2a3247",
                borderRadius="0.5rem",
                padding="0.9rem 1rem",
                width="100%",
            ),
            rx.script(uptime_ticker_js()),
            rx.text("recent worker runs", color=MUTED, fontSize="0.8rem"),
            rx.box(
                rx.text(worker_log_tail(20), whiteSpace="pre-wrap", color="#c9d2e3", fontSize="0.75rem"),
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


def chat_scroll_js() -> str:
    """JS that pins #chat-log to the bottom (called after message updates)."""
    return (
        "var el=document.getElementById('chat-log');"
        "if(el)el.scrollTop=el.scrollHeight;"
    )


def _visitor_context_text(ctx: dict[str, str]) -> str:
    """Format the collected visitor context into an LLM-readable block."""
    if not ctx:
        return ""
    lines = [
        "\n\nVISITOR CONTEXT (everything known about the current visitor; use it to "
        "personalise answers):"
    ]
    if ctx.get("lang"):
        lines.append(f"- language: {ctx['lang']}")
    if ctx.get("locale"):
        lines.append(f"- locale: {ctx['locale']}")
    if ctx.get("platform"):
        lines.append(f"- platform: {ctx['platform']}")
    if ctx.get("is_windows"):
        lines.append("- Windows: flag emoji must NOT be used (fonts can't render them)")
    if ctx.get("local_time"):
        lines.append(f"- local time: {ctx['local_time']} ({ctx.get('time_of_day', '')})")
    if ctx.get("location"):
        lines.append(f"- location: {ctx['location']}")
    if ctx.get("weather"):
        parts = [f"- weather: {ctx['weather']}"]
        if ctx.get("temp"):
            parts.append(f"temp {ctx['temp']}")
        if ctx.get("feels_like"):
            parts.append(f"feels like {ctx['feels_like']}")
        if ctx.get("humidity"):
            parts.append(f"humidity {ctx['humidity']}")
        if ctx.get("pressure"):
            parts.append(f"pressure {ctx['pressure']}")
        if ctx.get("wind"):
            parts.append(f"wind {ctx['wind']}")
        if ctx.get("precip"):
            parts.append(f"precipitation {ctx['precip']}")
        lines.append(" ".join(parts))
    if ctx.get("sunrise") or ctx.get("sunset"):
        lines.append(f"- sun: rise {ctx.get('sunrise', '?')} / set {ctx.get('sunset', '?')} local")
    if ctx.get("moon"):
        lines.append(f"- moon: {ctx['moon']} {ctx.get('moon_emoji', '')}")
    if ctx.get("warning"):
        lines.append(f"- weather warning: {ctx['warning']}")
    if ctx.get("device"):
        lines.append(f"- device: {ctx['device']}")
    return "\n".join(lines)


def _system_message(ctx: dict[str, str] | None = None) -> dict[str, str]:
    return {
        "role": "system",
        "content": (
            read_doc("prompt.md")
            + "\n\nKNOWLEDGE:\n"
            + read_doc("knowledge.md")
            + _visitor_context_text(ctx or {})
        ),
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
    busy: bool = False
    greeted: bool = False
    visitor_context: dict[str, str] = {}
    search_results: list[dict[str, str]] = []
    searched: bool = False

    def do_search(self, form_data: dict):
        """Full-text search over the markdown docs (instant, server-side)."""
        q = str(form_data.get("search") or "").strip()
        self.searched = True
        self.search_results = search_docs(q)

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
        logger.info("greeting: on_browser_info raw=%r", info)

        browser: dict[str, str] = {}
        try:
            browser = json.loads(info or "{}")
            # Reflex may deliver the JS result double-JSON-encoded (a quoted
            # string). Unwrap one layer so `browser` is a dict, not a string.
            if isinstance(browser, str):
                logger.info("greeting: info was double-encoded, unwrapping")
                browser = json.loads(browser)
            if not isinstance(browser, dict):
                logger.info("greeting: info parsed to %r, resetting", type(browser).__name__)
                browser = {}
        except Exception:  # noqa: BLE001
            logger.warning("greeting: failed to parse info, treating as empty", exc_info=True)
        logger.info("greeting: browser=%r", browser)

        header = self.router.headers  # server-side, from the HTTP request
        ip = self.router.session.client_ip
        # Behind the Tailscale Funnel the real client IP usually comes through
        # x-forwarded-for (set by the funnel). Fall back to the socket IP.
        # raw_headers preserves the original (likely hyphenated) header keys.
        raw = getattr(header, "raw_headers", None) or {}
        forwarded = raw.get("x-forwarded-for") or raw.get("X-Forwarded-For") or ""
        real_ip = forwarded.partition(",")[0].strip() or ip
        logger.info("greeting: ip=%r forwarded=%r -> real_ip=%r", ip, forwarded, real_ip)
        geo = await _geo_lookup(real_ip)
        logger.info("greeting: geo=%r", geo)

        # Language: prefer the browser's reported language, then the header.
        prefs = (
            browser.get("lang")
            or browser.get("langs")
            or header.accept_language
            or ""
        )
        lang = detect_language(prefs) if prefs else "English"
        logger.info("greeting: lang=%r (prefs=%r, accept=%r)", lang, prefs, header.accept_language)

        # Visitor's local time: derive from the browser-reported epoch ms and
        # timezone so "good evening" matches where they actually are.
        local_epoch_s = 0
        try:
            local_epoch_s = float(browser.get("now") or 0) / 1000.0
        except (TypeError, ValueError):
            pass
        tz_name = browser.get("tz") or geo.get("timezone") or "UTC"
        local_hour: int | None = None
        try:
            local_hour = datetime.fromtimestamp(local_epoch_s, ZoneInfo(tz_name)).hour
        except Exception:  # noqa: BLE001
            local_hour = None
        logger.info("greeting: tz=%r local_hour=%r", tz_name, local_hour)
        time_of_day = _time_of_day(local_hour) if local_hour is not None else ""

        # --- Collect everything known about the visitor into one dict. ---
        # Stored on State and re-injected into EVERY chat request afterwards so
        # the assistant keeps personalising answers (not just the greeting).
        ctx: dict[str, str] = {
            "lang": lang,
            "locale": browser.get("lang") or "",
            "platform": browser.get("platform") or "",
            "is_windows": "1" if "Win" in (browser.get("platform") or "") else "",
            "tz": tz_name,
            "local_time": "",
            "time_of_day": time_of_day,
            "device": " ".join(
                part
                for part in (
                    browser.get("screen") or "",
                    f"{browser.get('cores')} cores" if browser.get("cores") else "",
                    f"{browser.get('mem')} GiB RAM" if browser.get("mem") else "",
                    "online" if browser.get("online") else "offline",
                )
                if part
            ),
        }
        if local_epoch_s:
            try:
                ctx["local_time"] = datetime.fromtimestamp(
                    local_epoch_s, ZoneInfo(tz_name)
                ).strftime("%H:%M")
            except Exception:  # noqa: BLE001
                ctx["local_time"] = ""
        if geo.get("city") and geo.get("country"):
            ctx["location"] = f"{geo['city']}, {geo['country']}"
        elif geo.get("country"):
            ctx["location"] = geo["country"]
        logger.info("greeting: ctx=%r", ctx)

        # Weather for their location (best-effort, open-meteo, no key).
        weather = await _weather_lookup(geo.get("lat", ""), geo.get("lon", ""))
        logger.info("greeting: weather=%r", weather)
        for key in (
            "word", "temp", "feels_like", "humidity", "precip",
            "pressure", "wind", "is_day", "warning",
        ):
            if weather.get(key):
                ctx[key] = str(weather[key])
        if weather.get("word"):
            ctx["weather"] = f"{weather['word']} {weather.get('emoji', '')}"
        ctx["sunrise"] = weather.get("sunrise", "")
        ctx["sunset"] = weather.get("sunset", "")
        ctx["moon"] = weather.get("moon", "")
        ctx["moon_emoji"] = weather.get("moon_emoji", "")
        self.visitor_context = ctx

        # Flags: prefer country flag (precise, from the IP geo), fall back to
        # the device-language flag.
        country_flag = _country_flag(geo.get("country_code", ""))
        lang_flag = _language_flag(lang)
        flag = country_flag or lang_flag
        is_windows = bool(ctx["is_windows"])
        location = ctx.get("location", "")
        logger.info("greeting: flag=%r country_flag=%r lang_flag=%r location=%r windows=%r", flag, country_flag, lang_flag, location, is_windows)

        self.messages.append({"role": "assistant", "content": ""})
        yield
        try:
            client = get_chat_client()
            parts = [
                read_doc("prompt.md"),
                "\n\nKNOWLEDGE:\n",
                read_doc("knowledge.md"),
                _visitor_context_text(ctx),
                "\n\nNow: you just detected a new visitor. Write a short ",
                f"personal greeting for them in {lang} (the visitor's language - ",
                f"EVERY word you write must be in {lang}, no exceptions). ",
                "Make it warm and relevant.",
            ]
            if time_of_day:
                parts.append(f" Their local time is {time_of_day}.")
            if weather.get("word"):
                parts.append(f" The weather there is {weather['word']} {weather['emoji']}.")
            if weather.get("temp"):
                parts.append(
                    f" Temperature: {weather['temp']}"
                    + (f" (feels like {weather['feels_like']})." if weather.get("feels_like") else ".")
                )
            if weather.get("pressure"):
                parts.append(f" Pressure: {weather['pressure']}.")
            if weather.get("humidity"):
                parts.append(f" Humidity: {weather['humidity']}.")
            if weather.get("wind"):
                parts.append(f" Wind: {weather['wind']}.")
            if weather.get("warning"):
                parts.append(
                    f" There is a weather warning in effect: {weather['warning']}. "
                    "Mention it in a natural, non-alarmist way."
                )
            if weather.get("sunrise") and weather.get("sunset"):
                parts.append(
                    f" The sun there rises at {weather['sunrise']} and sets at "
                    f"{weather['sunset']} local time."
                )
            if weather.get("moon"):
                parts.append(
                    f" The moon there is in its {weather['moon']} phase {weather['moon_emoji']}."
                )
            if location:
                parts.append(f" They are in {location}.")
            if flag and not is_windows:
                parts.append(f" Their country flag is {flag}. Put that flag at the START of the greeting.")
            elif is_windows:
                parts.append(
                    " They are on Windows. ONLY the country/flag emoji must be avoided "
                    "(Windows fonts cannot render regional-indicator flag emoji). Other "
                    "emoji - weather, sun, moon, temperature - are FINE and welcome. "
                    "Mention their country/region by name in plain text."
                )
            parts.append(
                " Craft the greeting around their local time, the sun cycle, the moon "
                "and the weather when available (e.g. a rainy evening gets a rain emoji "
                "and a 'cozy' note; at night, talk about the moon and when the sun will "
                "rise; during the day, mention sunset). Mention the pressure or other "
                "meteorological detail only if it makes the greeting feel natural. Never "
                "say the sun is out at night or vice versa. It must "
                "be 1-3 sentences, feel natural, and END by asking the visitor who they "
                "are. Only name their city/country if the visitor details actually provide "
                "a location. NEVER invent or guess a city from the timezone - if you are "
                "not told where they are, greet them warmly without naming a place. Do "
                "not mention IP addresses, tokens, or anything sensitive."
            )
            system_content = "".join(parts)
            stream = await client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": system_content,
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
                    yield rx.call_script(chat_scroll_js())
            logger.info("greeting: chunks=%d text=%r", len(chunks), self.messages[-1]["content"])
            if not chunks:
                self.messages[-1]["content"] = (
                    f"Hi! I'm Frank's assistant — welcome. I can tell you're in "
                    f"{ctx.get('location') or ctx.get('device') or 'a browser'} "
                    f"right now. Who are you?"
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("greeting generation failed")
            self.messages[-1]["content"] = (
                "Hi! I'm Frank's assistant. Ask me anything about Frank's CV. Who are you?"
            )

    async def handle_submit(self, form_data: dict):
        # Read straight from the DOM's FormData at submit time (the input is
        # uncontrolled) so Android GBoard autocomplete can't double characters
        # by racing a server round-trip on every keystroke.
        q = str(form_data.get("question") or "").strip()
        if not q or self.busy:
            return
        self.messages.append({"role": "user", "content": q})
        self.busy = True
        self.messages.append({"role": "assistant", "content": ""})
        yield
        try:
            history = [_system_message(self.visitor_context), *self.messages[:-1][-10:]]
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
                    yield rx.call_script(chat_scroll_js())
            draft = "".join(chunks).strip()
            ok, reason = await filter_draft(q, draft)
            if not ok:
                logger.warning("answer filtered out: %s", reason)
            self.messages[-1]["content"] = draft if ok else FALLBACK
            yield rx.call_script(chat_scroll_js())
        except Exception as exc:  # noqa: BLE001
            logger.exception("chat backend failure")
            self.messages[-1]["content"] = (
                f"(chat backend error: {exc.__class__.__name__})"
            )
        self.busy = False
        yield rx.call_script(chat_scroll_js())


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
            id="chat-log",
            spacing="3",
            width="100%",
            overflowY="auto",
            maxHeight="45vh",
        ),
        rx.el.form(
            rx.hstack(
                rx.el.input(
                    name="question",
                    placeholder="Ask something about this site...",
                    disabled=State.busy,
                    auto_complete="off",
                    auto_capitalize="off",
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
            auto_complete="off",
            reset_on_submit=True,
            width="100%",
            marginTop="1rem",
        ),
        **CARD,
        width="min(720px, 92vw)",
    )


def search_panel() -> rx.Component:
    return rx.box(
        rx.heading("Search the site", size="2", color="#e8ecf4", marginBottom="1rem"),
        rx.el.form(
            rx.hstack(
                rx.el.input(
                    name="search",
                    placeholder="Search CV, projects, stack, timeline...",
                    auto_complete="off",
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
                    "Search",
                    type="submit",
                    background="#3b82f6",
                    color="#0b0e14",
                    fontWeight="600",
                ),
                spacing="2",
                width="100%",
            ),
            on_submit=State.do_search,
            auto_complete="off",
            reset_on_submit=True,
            width="100%",
            marginTop="1rem",
        ),
        rx.cond(
            State.searched,
            rx.box(
                rx.cond(
                    State.search_results.length() == 0,
                    rx.text("No results.", color=MUTED),
                    rx.foreach(
                        State.search_results,
                        lambda r: rx.box(
                            rx.text(
                                f"in {r['page']}: ",
                                color=ACCENT,
                                fontSize="0.8rem",
                                fontWeight="600",
                            ),
                            rx.text(r["snippet"], color="#c9d2e3", fontSize="0.85rem"),
                            background="#131826",
                            border="1px solid #2a3247",
                            borderRadius="0.5rem",
                            padding="0.6rem 0.8rem",
                            width="100%",
                        ),
                    ),
                ),
                spacing="2",
                width="100%",
                marginTop="1rem",
            ),
            rx.text(
                "Search runs over the markdown behind every page.",
                color=MUTED,
                fontSize="0.8rem",
                marginTop="1rem",
            ),
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
            search_panel(),
            rx.hstack(
                rx.link("About me", href="/about", color=ACCENT),
                rx.link("CV", href="/cv", color=ACCENT),
                rx.link("Deployment", href="/deploy", color=ACCENT),
                rx.link("Stack", href="/stack", color=ACCENT),
                rx.link("Timeline", href="/timeline", color=ACCENT),
                rx.link("Projects", href="/projects", color=ACCENT),
                rx.link("About-fun", href="/about-fun", color=ACCENT),
                rx.link("Contact", href="/contact", color=ACCENT),
                rx.link("Contribute", href="/contribute", color=ACCENT),
                rx.link("Architecture", href="/architecture", color=ACCENT),
                rx.link("Resources", href="/resources", color=ACCENT),
                rx.link("Status", href="/status", color=ACCENT),
                rx.link("Changelog", href="/changelog", color=ACCENT),
                rx.text("cv", color=MUTED),
                spacing="4",
                fontSize="0.85rem",
                width="min(720px, 92vw)",
                justify="center",
            ),
            rx.hstack(
                rx.link("LinkedIn", href="https://www.linkedin.com/in/frankeee/", color=ACCENT, is_external=True),
                rx.link("GitHub", href="https://github.com/frankinkua", color=ACCENT, is_external=True),
                rx.text("story-tegu", color=MUTED),
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


def contact() -> rx.Component:
    body = read_doc("contact.md")
    return rx.center(
        rx.vstack(
            rx.heading("Contact", size="4", color="#e8ecf4"),
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


def projects() -> rx.Component:
    return markdown_page("Projects — Frank Escudero", "projects.md", read_doc("projects.md"))


def changelog() -> rx.Component:
    return markdown_page("Changelog — Frank Escudero CV", "changelog.md", changelog_markdown())


def about_fun() -> rx.Component:
    return markdown_page("About-fun — Frank Escudero", "about-fun.md", read_doc("about-fun.md"))


def contribute() -> rx.Component:
    return markdown_page("Contributing — Frank Escudero CV", "contribute.md", read_doc("contribute.md"))


def architecture() -> rx.Component:
    return markdown_page("Architecture — Frank Escudero CV", "architecture.md", read_doc("architecture.md"))


def resources() -> rx.Component:
    return markdown_page("Resources — Frank Escudero", "resources.md", read_doc("resources.md"))
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
app.add_page(contact, route="/contact", title="Contact — Frank Escudero CV")
app.add_page(status_page, route="/status", title="Status — Frank Escudero CV")
app.add_page(projects, route="/projects", title="Projects — Frank Escudero CV")
app.add_page(changelog, route="/changelog", title="Changelog — Frank Escudero CV")
app.add_page(about_fun, route="/about-fun", title="About-fun — Frank Escudero")
app.add_page(contribute, route="/contribute", title="Contributing — Frank Escudero CV")
app.add_page(architecture, route="/architecture", title="Architecture — Frank Escudero CV")
app.add_page(resources, route="/resources", title="Resources — Frank Escudero")
app.add_page(stack, route="/stack", title="Tech stack — Frank Escudero CV")
app.add_page(timeline, route="/timeline", title="Timeline — Frank Escudero CV")
app.add_page(worker_log_page, route="/worker-log", title="Worker log — Frank Escudero CV")


async def _rss(request):
    from starlette.responses import Response
    return Response(rss_xml(), media_type="application/rss+xml; charset=utf-8")


async def _sitemap(request):
    from starlette.responses import Response
    return Response(sitemap_xml(), media_type="application/xml; charset=utf-8")


try:
    app._api.add_route("/rss", _rss)
    app._api.add_route("/sitemap.xml", _sitemap)
except Exception:  # noqa: BLE001
    logger.warning("could not mount /rss or /sitemap.xml route", exc_info=True)
