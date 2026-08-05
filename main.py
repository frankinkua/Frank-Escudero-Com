from __future__ import annotations

import json
import logging
import os
import pathlib
import secrets
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone

import asyncio
import httpx
import reflex as rx
from openai import AsyncOpenAI
from zoneinfo import ZoneInfo

import site_store

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


# In-memory geo cache so repeat visits (and analytics) don't re-hit ip-api.com.
_GEO_CACHE: dict[str, dict[str, str] | None] = {}
_GEO_LOCK = threading.Lock()


async def _geo_for(ip: str) -> dict[str, str]:
    """Cached async geo lookup. Empty IPs and failures are cached too."""
    if not ip:
        return {}
    with _GEO_LOCK:
        if ip in _GEO_CACHE:
            return _GEO_CACHE[ip] or {}
    geo = await _geo_lookup(ip)
    with _GEO_LOCK:
        _GEO_CACHE[ip] = geo or None
    return geo


async def _enrich_visit(ip: str) -> None:
    """Background geo lookup for a just-recorded visit, then backfill older rows."""
    try:
        geo = await _geo_for(ip)
        site_store.backfill_geo(ip, geo)
    except Exception:  # noqa: BLE001
        logger.exception("visit geo enrichment failed")


def _real_client_ip(router) -> str:
    """Real visitor IP, honouring the Tailscale Funnel x-forwarded-for."""
    headers = router.headers
    raw = getattr(headers, "raw_headers", None) or {}
    forwarded = raw.get("x-forwarded-for") or raw.get("X-Forwarded-For") or ""
    return forwarded.partition(",")[0].strip() or router.session.client_ip or ""


def server_log_tail(lines: int = 40) -> str:
    try:
        return "\n".join(
            pathlib.Path("/var/log/websiteserver.log").read_text(errors="replace").splitlines()[-lines:]
        )
    except OSError:
        return "(no server log yet)"


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


def changelog_entries() -> list[tuple[str, str, str]]:
    """[(sha, iso-date, subject)] newest first, for the RSS feed."""
    log = _git(["git", "log", "--pretty=format:%h|%ci|%s", "-20"])
    out: list[tuple[str, str, str]] = []
    for row in (log or "").splitlines():
        sha, ci, subj = (row.split("|", 2) + ["", ""])[:3]
        out.append((sha, ci, subj))
    return out


def rss_xml() -> str:
    """Atom-ish RSS feed: site about/cv content (static) + git changelog (live)."""
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    def _slug(text: str, n: int = 200) -> str:
        flat = " ".join(text.split())
        return flat[:n] + ("…" if len(flat) > n else "")

    changelog_items = "\n".join(
        f"<item><title>update {sha} — {subj}</title>"
        f"<link>https://cv.story-tegu.ts.net/</link>"
        f"<guid>{sha}</guid><pubDate>{ci}</pubDate>"
        f"<description>Site update {sha}</description></item>"
        for sha, ci, subj in changelog_entries()
    )
    static_items = "\n".join(
        f"<item><title>{title}</title>"
        f"<link>https://cv.story-tegu.ts.net/{link}</link>"
        f"<guid>{guid}</guid><pubDate>{now}</pubDate>"
        f"<description>{_slug(body)}</description></item>"
        for title, link, guid, body in (
            ("About Frank Escudero", "about", "about", read_doc("knowledge.md")),
            ("CV — Frank Escudero", "cv", "cv", read_doc("cv.md")),
            ("Projects — Frank Escudero", "projects", "projects", read_doc("projects.md")),
        )
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>'
        "<title>Frank Escudero CV</title>"
        "<link>https://cv.story-tegu.ts.net/</link>"
        "<description>Frank Escudero's self-hosted AI CV — content and site updates.</description>"
        f"{changelog_items}{static_items}</channel></rss>\n"
    )


def sitemap_xml() -> str:
    """Basic XML sitemap of all public pages, for crawlers."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = [
        "", "/about", "/cv", "/projects", "/contact",
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
        rx.cond(
            State.is_admin,
            rx.link(
                "admin",
                href="/admin",
                fontSize="0.75rem",
                color="#64748b",
                fontFamily="ui-monospace, Menlo, monospace",
            ),
            rx.text("", fontSize="0.75rem"),
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
            auth_menu(),
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

    # Auth session: the cookie holds an opaque token; identity is re-verified
    # against site_store.sessions.json on every page load, never trusted from
    # the client alone.
    session_token: str = rx.Cookie("", name="cv_sess", max_age=30 * 86400, same_site="lax", secure=False)
    user_email: str = ""
    user_name: str = ""
    user_role: str = ""
    is_admin: bool = False
    auth_error: str = ""

    # Per-session analytics/transcript identifiers.
    conv_id: str = ""
    visitor_ip: str = ""
    visitor_geo: dict[str, str] = {}

    # Admin dashboard payload (populated only by load_admin after token check).
    admin_stats: dict[str, int] = {}
    admin_locations: list[dict[str, object]] = []
    admin_pages: list[dict[str, object]] = []
    admin_visits: list[dict[str, object]] = []
    admin_convs: list[dict[str, str]] = []
    admin_log: str = ""

    @rx.var
    def is_logged_in(self) -> bool:
        return bool(self.user_email)

    def _restore_session(self) -> None:
        """Re-derive identity from the cookie token (runs on every page load)."""
        token = self.session_token or ""
        sess = site_store.validate_session(token)
        if sess is None:
            if token:
                self.session_token = ""
            self.user_email = ""
            self.user_name = ""
            self.user_role = ""
            self.is_admin = False
            return
        self.user_email = sess["email"]
        self.user_name = sess.get("name", "") or sess["email"].split("@")[0]
        self.user_role = sess["role"]
        self.is_admin = sess["role"] == "admin"

    async def _record_visit(self) -> None:
        """Log a page view into the analytics store (skips the admin's own views).

        Never blocks page load on a geo lookup: writes immediately with any
        cached geo and lets a background task enrich + backfill the row.
        """
        try:
            if self.user_role == "admin":
                return
            router = self.router
            headers = router.headers
            raw = getattr(headers, "raw_headers", None) or {}
            ip = _real_client_ip(router)
            path = getattr(router.url, "path", None) or "/"
            if path in ("", "/index"):
                path = "/"
            ua = raw.get("user-agent") or raw.get("User-Agent") or ""
            ref = raw.get("referer") or raw.get("Referer") or ""
            lang = headers.accept_language or ""
            geo: dict[str, str] = {}
            with _GEO_LOCK:
                cached = _GEO_CACHE.get(ip)
                if cached:
                    geo = dict(cached)
            site_store.log_visit(path=path, ip=ip, geo=geo, lang=lang, ua=ua, ref=ref)
            if cached is None and ip:
                asyncio.get_running_loop().create_task(_enrich_visit(ip))
        except Exception:  # noqa: BLE001
            logger.exception("visit recording failed")

    async def load_home(self):
        """on_load for `/`: restore session, log the visit, probe the browser."""
        self._restore_session()
        await self._record_visit()
        return rx.call_script(BROWSER_INFO_JS, callback=State.on_browser_info)

    async def load_public(self) -> None:
        """on_load for public content pages: restore session + log the visit."""
        self._restore_session()
        await self._record_visit()

    def load_profile(self) -> None:
        self._restore_session()

    async def load_admin(self):
        """on_load for `/admin`: guard, then pull the analytics payload."""
        self._restore_session()
        if not self.is_admin:
            return rx.redirect("/")
        data = site_store.admin_data()
        self.admin_stats = {
            "total": data["total"],
            "unique": data["unique"],
            "convs": data["convs"],
            "messages": data["messages"],
        }
        self.admin_locations = data["locations"]
        self.admin_pages = data["pages"]
        self.admin_visits = data["recent"]
        self.admin_convs = data["convs_list"]
        self.admin_log = server_log_tail(40)

    async def do_login(self, form_data: dict):
        email = str(form_data.get("email") or "").strip().lower()
        password = str(form_data.get("password") or "")
        ok, msg, user = site_store.authenticate(email, password)
        if not ok:
            self.auth_error = msg
            return
        self.auth_error = ""
        self.user_email = email
        self.user_name = user.get("name", "") or email.split("@")[0]
        self.user_role = user["role"]
        self.is_admin = user["role"] == "admin"
        self.session_token = site_store.create_session(email, user["role"], self.user_name)
        return rx.redirect("/")

    async def do_signup(self, form_data: dict):
        name = str(form_data.get("name") or "").strip()
        email = str(form_data.get("email") or "").strip().lower()
        password = str(form_data.get("password") or "")
        confirm = str(form_data.get("confirm") or "")
        if password != confirm:
            self.auth_error = "Passwords do not match."
            return
        ok, msg = site_store.create_user(name, email, password)
        if not ok:
            self.auth_error = msg
            return
        self.auth_error = ""
        self.user_email = email
        self.user_name = name or email.split("@")[0]
        self.user_role = "user"
        self.is_admin = False
        self.session_token = site_store.create_session(email, "user", self.user_name)
        return rx.redirect("/")

    async def do_signout(self):
        if self.session_token:
            site_store.destroy_session(self.session_token)
        self.session_token = ""
        self.user_email = ""
        self.user_name = ""
        self.user_role = ""
        self.is_admin = False
        return rx.redirect("/")

    def do_search(self, form_data: dict):
        """Full-text search over the markdown docs (instant, server-side)."""
        q = str(form_data.get("search") or "").strip()
        self.searched = True
        self.search_results = search_docs(q)

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
        geo = await _geo_for(real_ip)
        logger.info("greeting: geo=%r", geo)
        self.visitor_ip = real_ip
        self.visitor_geo = geo
        if not self.conv_id:
            self.conv_id = "c_" + secrets.token_hex(6)

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
        site_store.log_conv_message(
            self.conv_id, "assistant", self.messages[-1]["content"],
            self.visitor_ip, self.visitor_geo,
        )
        site_store.backfill_geo(self.visitor_ip, self.visitor_geo)

    async def handle_submit(self, form_data: dict):
        # Read straight from the DOM's FormData at submit time (the input is
        # uncontrolled) so Android GBoard autocomplete can't double characters
        # by racing a server round-trip on every keystroke.
        q = str(form_data.get("question") or "").strip()
        if not q or self.busy:
            return
        if not self.conv_id:
            self.conv_id = "c_" + secrets.token_hex(6)
        self.messages.append({"role": "user", "content": q})
        site_store.log_conv_message(self.conv_id, "user", q, self.visitor_ip, self.visitor_geo)
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
        site_store.log_conv_message(
            self.conv_id, "assistant", self.messages[-1]["content"],
            self.visitor_ip, self.visitor_geo,
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
                auth_menu(),
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
                rx.link("About", href="/about", color=ACCENT),
                rx.link("CV", href="/cv", color=ACCENT),
                rx.link("Projects", href="/projects", color=ACCENT),
                rx.link("Contact", href="/contact", color=ACCENT),
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
            auth_menu(),
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


def contact() -> rx.Component:
    body = read_doc("contact.md")
    return rx.center(
        rx.vstack(
            auth_menu(),
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


# --------------------------------------------------------------------------- #
# Auth + analytics pages
# --------------------------------------------------------------------------- #
def auth_menu() -> rx.Component:
    """Small profile menu: sign-in links when anonymous, dropdown when signed in."""
    return rx.hstack(
        rx.cond(
            State.is_logged_in,
            rx.menu.root(
                rx.menu.trigger(
                    rx.button(
                        f"Hi {State.user_name} ▾",
                        size="1",
                        variant="outline",
                        background="transparent",
                        color=ACCENT,
                        borderColor="#2a3247",
                    ),
                ),
                rx.menu.content(
                    rx.menu.item("Profile", on_click=rx.redirect("/profile")),
                    rx.cond(
                        State.is_admin,
                        rx.menu.item("Admin dashboard", on_click=rx.redirect("/admin")),
                    ),
                    rx.menu.item("Sign out", on_click=State.do_signout),
                    background="#131826",
                    color="#e8ecf4",
                ),
            ),
            rx.hstack(
                rx.link("Sign in", href="/login", color=MUTED, fontSize="0.85rem"),
                rx.link("Sign up", href="/signup", color=ACCENT, fontSize="0.85rem"),
                spacing="3",
            ),
        ),
        align="center",
    )


def auth_error_box() -> rx.Component:
    return rx.cond(
        State.auth_error != "",
        rx.box(
            State.auth_error,
            color="#fca5a5",
            background="#3f1214",
            border="1px solid #7f1d1d",
            borderRadius="0.5rem",
            padding="0.5rem 0.8rem",
            width="100%",
            fontSize="0.85rem",
        ),
    )


def _auth_input(name: str, placeholder: str, type_: str = "text") -> rx.Component:
    return rx.el.input(
        name=name,
        placeholder=placeholder,
        type=type_,
        required=True,
        auto_complete="on",
        style={
            "width": "100%",
            "background": "#0d1117",
            "color": "#e8ecf4",
            "border": "1px solid #2a3247",
            "borderRadius": "0.5rem",
            "padding": "0.6rem 0.8rem",
            "fontFamily": "inherit",
        },
    )


def login_page() -> rx.Component:
    return rx.center(
        rx.vstack(
            auth_menu(),
            rx.heading("Sign in", size="4", color="#e8ecf4"),
            rx.text("Sign in to get updates from this site.", color=MUTED, fontSize="0.85rem"),
            rx.el.form(
                rx.vstack(
                    _auth_input("email", "email", "email"),
                    _auth_input("password", "password", "password"),
                    rx.button("Sign in", type="submit", background=ACCENT, color="#0b0e14", fontWeight="600"),
                    spacing="3",
                    width="100%",
                ),
                on_submit=State.do_login,
                width="100%",
            ),
            auth_error_box(),
            rx.hstack(
                rx.link("Create an account", href="/signup", color=ACCENT, fontSize="0.85rem"),
                rx.link("Back to main", href="/", color=MUTED, fontSize="0.85rem"),
                spacing="4",
            ),
            page_footer(),
            spacing="4",
            width="min(420px, 92vw)",
            padding="2.5rem 1rem",
            align="center",
        ),
        width="100%",
        minHeight="100vh",
        background=BG,
        fontFamily="ui-monospace, Menlo, monospace",
    )


def signup_page() -> rx.Component:
    return rx.center(
        rx.vstack(
            auth_menu(),
            rx.heading("Create account", size="4", color="#e8ecf4"),
            rx.text("Signing up subscribes you to updates from this site.", color=MUTED, fontSize="0.85rem"),
            rx.el.form(
                rx.vstack(
                    _auth_input("name", "name (optional)"),
                    _auth_input("email", "email", "email"),
                    _auth_input("password", "password (min 8 chars)", "password"),
                    _auth_input("confirm", "confirm password", "password"),
                    rx.button("Sign up", type="submit", background=ACCENT, color="#0b0e14", fontWeight="600"),
                    spacing="3",
                    width="100%",
                ),
                on_submit=State.do_signup,
                width="100%",
            ),
            auth_error_box(),
            rx.hstack(
                rx.link("Already have an account? Sign in", href="/login", color=ACCENT, fontSize="0.85rem"),
                rx.link("Back to main", href="/", color=MUTED, fontSize="0.85rem"),
                spacing="4",
            ),
            page_footer(),
            spacing="4",
            width="min(420px, 92vw)",
            padding="2.5rem 1rem",
            align="center",
        ),
        width="100%",
        minHeight="100vh",
        background=BG,
        fontFamily="ui-monospace, Menlo, monospace",
    )


def profile_page() -> rx.Component:
    return rx.center(
        rx.vstack(
            auth_menu(),
            rx.heading("Profile", size="4", color="#e8ecf4"),
            rx.cond(
                State.is_logged_in,
                rx.vstack(
                    rx.box(
                        rx.vstack(
                            rx.hstack(
                                rx.text("name", color=MUTED, fontSize="0.8rem"),
                                rx.text(State.user_name, color="#c9d2e3"),
                                justify="between",
                                width="100%",
                            ),
                            rx.hstack(
                                rx.text("email", color=MUTED, fontSize="0.8rem"),
                                rx.text(State.user_email, color="#c9d2e3"),
                                justify="between",
                                width="100%",
                            ),
                            rx.hstack(
                                rx.text("role", color=MUTED, fontSize="0.8rem"),
                                rx.text(State.user_role, color="#c9d2e3"),
                                justify="between",
                                width="100%",
                            ),
                            rx.hstack(
                                rx.text("updates", color=MUTED, fontSize="0.8rem"),
                                rx.text("on", color=ACCENT),
                                justify="between",
                                width="100%",
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
                    rx.cond(
                        State.is_admin,
                        rx.link("Open admin dashboard", href="/admin", color=ACCENT, fontSize="0.85rem"),
                    ),
                    rx.button("Sign out", on_click=State.do_signout, background="#3b82f6", color="#0b0e14", fontWeight="600"),
                    spacing="4",
                    width="100%",
                ),
                rx.vstack(
                    rx.text("You are not signed in.", color="#c9d2e3"),
                    rx.link("Sign in", href="/login", color=ACCENT, fontSize="0.85rem"),
                    rx.link("Back to main", href="/", color=MUTED, fontSize="0.85rem"),
                    spacing="3",
                ),
            ),
            page_footer(),
            spacing="4",
            width="min(520px, 92vw)",
            padding="2.5rem 1rem",
            align="center",
        ),
        width="100%",
        minHeight="100vh",
        background=BG,
        fontFamily="ui-monospace, Menlo, monospace",
    )


def admin_table(rows, key_col: str, val_col: str, empty_text: str) -> rx.Component:
    return rx.cond(
        rows.length() == 0,
        rx.text(empty_text, color=MUTED, fontSize="0.8rem"),
        rx.vstack(
            rx.foreach(
                rows,
                lambda row: rx.hstack(
                    rx.text(row[key_col], color="#c9d2e3", fontSize="0.85rem", flex="1"),
                    rx.text(row[val_col], color=ACCENT, fontSize="0.85rem", fontWeight="600"),
                    justify="between",
                    width="100%",
                    background="#131826",
                    border="1px solid #2a3247",
                    borderRadius="0.5rem",
                    padding="0.5rem 0.9rem",
                ),
            ),
            spacing="2",
            width="100%",
        ),
    )


def admin_visit_list() -> rx.Component:
    return rx.cond(
        State.admin_visits.length() == 0,
        rx.text("No visits recorded yet.", color=MUTED, fontSize="0.8rem"),
        rx.vstack(
            rx.foreach(
                State.admin_visits,
                lambda v: rx.hstack(
                    rx.text(v["ts"], color=MUTED, fontSize="0.75rem", flex="1"),
                    rx.text(v["path"], color="#c9d2e3", fontSize="0.8rem"),
                    rx.text(v["where"], color=ACCENT, fontSize="0.8rem"),
                    rx.text(v["ip"], color=MUTED, fontSize="0.75rem"),
                    justify="between",
                    width="100%",
                    background="#131826",
                    border="1px solid #2a3247",
                    borderRadius="0.5rem",
                    padding="0.45rem 0.9rem",
                    flexWrap="wrap",
                ),
            ),
            spacing="2",
            width="100%",
        ),
    )


def admin_conversations() -> rx.Component:
    return rx.cond(
        State.admin_convs.length() == 0,
        rx.text("No conversations recorded yet.", color=MUTED, fontSize="0.8rem"),
        rx.vstack(
            rx.foreach(
                State.admin_convs,
                lambda r: rx.cond(
                    r["kind"] == "header",
                    rx.box(
                        rx.hstack(
                            rx.text(f"#{r['id']}", color=ACCENT, fontSize="0.8rem", fontWeight="600"),
                            rx.text(r["created"], color=MUTED, fontSize="0.75rem"),
                            rx.text(r["location"], color=MUTED, fontSize="0.75rem"),
                            justify="between",
                            width="100%",
                        ),
                        background="#131826",
                        border="1px solid #2a3247",
                        borderRadius="0.5rem",
                        padding="0.5rem 0.9rem",
                        width="100%",
                    ),
                    rx.box(
                        rx.text(r["content"], whiteSpace="pre-wrap", color="#c9d2e3", fontSize="0.85rem"),
                        background=rx.cond(r["role"] == "user", "#1f2937", "#182032"),
                        border="1px solid #2f3b52",
                        borderRadius="0.6rem",
                        padding="0.5rem 0.8rem",
                        width="100%",
                    ),
                ),
            ),
            spacing="2",
            width="100%",
        ),
    )


def admin_page() -> rx.Component:
    return rx.center(
        rx.vstack(
            auth_menu(),
            rx.heading("Admin dashboard", size="4", color="#e8ecf4"),
            rx.cond(
                State.is_admin,
                rx.vstack(
                    rx.hstack(
                        *[
                            rx.box(
                                rx.vstack(
                                    rx.text(label, color=MUTED, fontSize="0.75rem"),
                                    rx.text(State.admin_stats[key], color="#e8ecf4", fontSize="1.4rem", fontWeight="700"),
                                    spacing="1",
                                ),
                                background="#131826",
                                border="1px solid #2a3247",
                                borderRadius="0.5rem",
                                padding="1rem",
                                flex="1",
                                width="100%",
                            )
                            for label, key in [
                                ("visits", "total"),
                                ("visitors", "unique"),
                                ("conversations", "convs"),
                                ("messages", "messages"),
                            ]
                        ],
                        spacing="3",
                        width="100%",
                        flexWrap="wrap",
                    ),
                    rx.heading("Visitor locations", size="2", color="#e8ecf4", marginTop="1rem"),
                    admin_table(State.admin_locations, "location", "count", "No visits yet."),
                    rx.heading("Pages", size="2", color="#e8ecf4", marginTop="1rem"),
                    admin_table(State.admin_pages, "path", "count", "No visits yet."),
                    rx.heading("Recent visits", size="2", color="#e8ecf4", marginTop="1rem"),
                    admin_visit_list(),
                    rx.heading("Conversations", size="2", color="#e8ecf4", marginTop="1rem"),
                    admin_conversations(),
                    rx.heading("Server log", size="2", color="#e8ecf4", marginTop="1rem"),
                    rx.box(
                        rx.text(State.admin_log, whiteSpace="pre-wrap", color="#c9d2e3", fontSize="0.75rem"),
                        background="#0d1117",
                        border="1px solid #2a3247",
                        borderRadius="0.5rem",
                        padding="0.7rem 0.9rem",
                        width="100%",
                        overflowX="auto",
                    ),
                    rx.text(f"server uptime: {system_uptime()} · worker runs: {len(worker_run_summary())}",
                            color=MUTED, fontSize="0.8rem"),
                    rx.button("Sign out", on_click=State.do_signout, background="#3b82f6", color="#0b0e14", fontWeight="600"),
                    spacing="3",
                    width="100%",
                ),
                rx.vstack(
                    rx.text("This area is restricted to the admin.", color="#c9d2e3"),
                    rx.link("Sign in", href="/login", color=ACCENT, fontSize="0.85rem"),
                    rx.link("Back to main", href="/", color=MUTED, fontSize="0.85rem"),
                    spacing="3",
                ),
            ),
            page_footer(),
            spacing="4",
            width="min(920px, 94vw)",
            padding="2.5rem 1rem",
            align="center",
        ),
        width="100%",
        minHeight="100vh",
        background=BG,
        fontFamily="ui-monospace, Menlo, monospace",
    )


try:
    _boot = site_store.ensure_admin()
    if _boot:
        logger.warning("ADMIN BOOTSTRAP: email=%s password=%s (also in /web/data/.admin-bootstrap)",
                       site_store.ADMIN_EMAIL, _boot)
except Exception:  # noqa: BLE001
    logger.exception("admin bootstrap failed")

app = rx.App(
    head_components=[
        rx.el.link(rel="icon", type="image/svg+xml", href=FAVICON_SVG),
        rx.el.link(rel="apple-touch-icon", href=FAVICON_SVG),
        rx.el.meta(name="description", content="Frank Escudero CV - zero-trust, self-hosted, AI-updated virtual employee."),
        rx.el.meta(property="og:site_name", content="Frank Escudero CV"),
        rx.el.meta(property="og:title", content="Frank Escudero — virtual-employee CV"),
        rx.el.meta(property="og:description", content="Frank Escudero CV - zero-trust, self-hosted, AI-updated virtual employee."),
        rx.el.meta(property="og:type", content="website"),
        rx.el.meta(property="og:url", content="https://cv.story-tegu.ts.net/"),
        rx.el.meta(name="twitter:card", content="summary"),
        rx.el.meta(name="twitter:title", content="Frank Escudero — virtual-employee CV"),
        rx.el.meta(name="twitter:description", content="Frank Escudero CV - zero-trust, self-hosted, AI-updated virtual employee."),
    ],
)
app.add_page(index, route="/", title="Frank Escudero — virtual-employee CV", on_load=State.load_home)
app.add_page(about, route="/about", title="About — Frank Escudero", on_load=State.load_public)
app.add_page(cv, route="/cv", title="CV — Frank Escudero", on_load=State.load_public)
app.add_page(contact, route="/contact", title="Contact — Frank Escudero CV", on_load=State.load_public)
app.add_page(projects, route="/projects", title="Projects — Frank Escudero CV", on_load=State.load_public)
app.add_page(login_page, route="/login", title="Sign in — Frank Escudero CV", on_load=State.load_public)
app.add_page(signup_page, route="/signup", title="Sign up — Frank Escudero CV", on_load=State.load_public)
app.add_page(profile_page, route="/profile", title="Profile — Frank Escudero CV", on_load=State.load_profile)
app.add_page(admin_page, route="/admin", title="Admin — Frank Escudero CV", on_load=State.load_admin)


async def _rss(request):
    from starlette.responses import Response
    return Response(rss_xml(), media_type="application/rss+xml; charset=utf-8")


async def _sitemap(request):
    from starlette.responses import Response
    return Response(sitemap_xml(), media_type="application/xml; charset=utf-8")


async def _robots(request):
    from starlette.responses import Response
    return Response(
        "User-agent: *\nAllow: /\nSitemap: https://cv.story-tegu.ts.net/sitemap.xml\n",
        media_type="text/plain; charset=utf-8",
    )


try:
    app._api.add_route("/rss", _rss)
    app._api.add_route("/sitemap.xml", _sitemap)
    app._api.add_route("/robots.txt", _robots)
except Exception:  # noqa: BLE001
    logger.warning("could not mount /rss, /sitemap.xml or /robots.txt route", exc_info=True)
