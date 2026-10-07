import pytest
from starlette.requests import Request
import os
from unittest.mock import patch

# Mock webapp.db.init before importing main so it doesn't try to create /web/data
with patch('webapp.db.init'):
    from main import _robots, _sitemap, RedirectOldDomainMiddleware

@pytest.mark.asyncio
async def test_robots():
    req = Request({"type": "http", "method": "GET", "path": "/robots.txt"})
    response = await _robots(req)
    assert response.status_code == 200
    assert response.media_type == "text/plain; charset=utf-8"
    assert b"User-agent: *" in response.body
    assert b"Sitemap: https://frank-escudero.com/sitemap.xml" in response.body

@pytest.mark.asyncio
async def test_sitemap():
    req = Request({"type": "http", "method": "GET", "path": "/sitemap.xml"})
    response = await _sitemap(req)
    assert response.status_code == 200
    assert response.media_type == "application/xml; charset=utf-8"
    assert b"https://frank-escudero.com/</loc>" in response.body
    assert b"https://frank-escudero.com/cv</loc>" in response.body

@pytest.mark.asyncio
async def test_redirect_old_domain_middleware():
    async def call_next(request):
        from starlette.responses import Response
        return Response(b"ok")

    app = RedirectOldDomainMiddleware(app=None)

    # Test old domain
    req = Request({
        "type": "http",
        "method": "GET",
        "path": "/some/path",
        "headers": [(b"host", b"cv.story-tegu.ts.net")]
    })
    response = await app.dispatch(req, call_next)
    assert response.status_code == 301
    assert response.headers["location"] == "https://frank-escudero.com/some/path"

    # Test old domain with query
    req = Request({
        "type": "http",
        "method": "GET",
        "path": "/some/path",
        "query_string": b"foo=bar",
        "headers": [(b"host", b"cv.story-tegu.ts.net")]
    })
    response = await app.dispatch(req, call_next)
    assert response.status_code == 301
    assert response.headers["location"] == "https://frank-escudero.com/some/path?foo=bar"

    # Test new domain (no redirect)
    req = Request({
        "type": "http",
        "method": "GET",
        "path": "/some/path",
        "headers": [(b"host", b"frank-escudero.com")]
    })
    response = await app.dispatch(req, call_next)
    assert response.status_code == 200
    assert response.body == b"ok"
