"""Per-client CSS / HTML / JS blocks.

The assistant may attach custom blocks to a specific client (by device_id).
On the next page render, those blocks are injected into the visitor's DOM:
  - css  -> a <style> element
  - html -> a raw <div> rendered near the top of the page
  - js   -> a <script> element evaluated on the client each load

All blocks live in SQLite (webapp.db_*). `pool_all()` are hand-authored
templates the assistant can pick from; `get_blocks(device_id)` are the ones
actually attached to this client. The keep/restore form is scoped to the
device's own keys.
"""

from __future__ import annotations

from . import db


def attach(device_id: str, key: str, kind: str, content: str) -> None:
    db.save_block(device_id, key, kind, content)


def detach(device_id: str, key: str) -> None:
    db.delete_block(device_id, key)


def for_client(device_id: str) -> dict[str, list[dict]]:
    """Split a client's blocks into css / html / js lists for rendering."""
    out = {"css": [], "html": [], "js": []}
    for b in db.get_blocks(device_id):
        kind = (b.get("kind") or "").lower()
        if kind in out:
            out[kind].append(b)
    return out


def from_pool(kind: str) -> list[dict]:
    return [b for b in db.pool_all() if (b.get("kind") or "").lower() == kind]