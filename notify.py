"""ntfy.sh push notifications for key website events.

Topic: franke2032 (the site owner's phone). All sends are best-effort,
non-blocking for the caller when wrapped in a fire-and-forget task, and
never raise — a notification must never break the site.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger("web.notify")

NTFY_URL = os.environ.get("NTFY_URL", "https://ntfy.sh/franke2032")
ENABLED = os.environ.get("NTFY_ENABLED", "1") == "1"


async def send(title: str, message: str, tags: list[str] | None = None) -> None:
    """Push a single notification to the ntfy topic. Never raises."""
    if not ENABLED:
        return
    try:
        headers = {"Title": title[:200]}
        if tags:
            headers["Tags"] = ",".join(tags)
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(NTFY_URL, content=message.encode("utf-8"), headers=headers)
        logger.info("ntfy: %r -> HTTP %s", title, r.status_code)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ntfy: send failed for %r: %s", title, exc)
