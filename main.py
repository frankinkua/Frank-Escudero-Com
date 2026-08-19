"""Frank Escudero CV site — Reflex entry point.

A clean, modular landing page that renders the CV from `cv.md`, plus an
aggressive in-page assistant that opens by itself and restyles the site live
per visitor (device-aware by default, per-client CSS/HTML/JS blocks from SQLite).

Pages:
  /          home —— CV summary + auto-opening chat
  /cv        full CV markdown
  /timeline  work history (curated + git log)
"""

from __future__ import annotations

import logging

import reflex as rx

from webapp import db
from webapp.components import chat_widget, cv_body, nav, timeline_body, footer
from webapp.state import State
from webapp import timeline as timeline_mod

logger = logging.getLogger("cv")

db.init()


def index() -> rx.Component:
    return rx.vstack(
        nav(),
        rx.container(
            rx.vstack(
                rx.badge(State.server_ts, variant="soft", colorScheme="teal"),
                rx.heading("Frank Escudero", size="5", color="#e8ecf4"),
                rx.text(
                    "Full-stack engineer · infrastructure developer · 5-time startup founder",
                    color="#9aa4bb", fontSize="0.9rem",
                ),
                rx.text(State.greeting, color="#5eead4", fontSize="0.9rem", fontStyle="italic"),
                rx.markdown(State.home_md, color="#c9d2e3"),
                rx.link("Read the full CV →", href="/cv", color="#5eead4", marginTop="0.5rem"),
            ),
            maxWidth="760px",
            padding="3rem 1rem 1rem",
        ),
        footer(),
        chat_widget(),
        width="100%",
        minHeight="100vh",
    )


def cv_page() -> rx.Component:
    return rx.vstack(
        nav(),
        cv_body(State.cv_md),
        footer(),
        chat_widget(),
        width="100%",
        minHeight="100vh",
    )


def timeline_page() -> rx.Component:
    return rx.vstack(
        nav(),
        timeline_body(),
        footer(),
        chat_widget(),
        width="100%",
        minHeight="100vh",
    )


app = rx.App()

app.add_page(index, route="/", title="Frank Escudero — CV", on_load=State.load_home)
app.add_page(cv_page, route="/cv", title="CV — Frank Escudero", on_load=State.load_cv)
app.add_page(timeline_page, route="/timeline", title="Timeline — Frank Escudero", on_load=State.load_timeline)


from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402
from starlette.responses import RedirectResponse  # noqa: E402


class RedirectOldDomainMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        host = request.headers.get("host", "")
        if host.endswith("cv.story-tegu.ts.net"):
            new_url = f"https://frank-escudero.com{request.url.path}"
            if request.url.query:
                new_url += f"?{request.url.query}"
            return RedirectResponse(url=new_url, status_code=301)
        return await call_next(request)


app._api.add_middleware(RedirectOldDomainMiddleware)


async def _robots(request):
    from starlette.responses import Response
    return Response(
        "User-agent: *\nAllow: /\nSitemap: https://frank-escudero.com/sitemap.xml\n",
        media_type="text/plain; charset=utf-8",
    )


async def _sitemap(request):
    from starlette.responses import Response
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>https://frank-escudero.com/</loc></url>"
        "<url><loc>https://frank-escudero.com/cv</loc></url>"
        "<url><loc>https://frank-escudero.com/timeline</loc></url>"
        "</urlset>"
    )
    return Response(xml, media_type="application/xml; charset=utf-8")


app._api.add_route("/robots.txt", _robots)
app._api.add_route("/sitemap.xml", _sitemap)