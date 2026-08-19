"""Build a markdown timeline of the work done on this site.

The timeline mixes:
  - tracked milestones stored in timeline.md (curated, readable)
  - the git log since the repository's first commit (for completeness)
Kept as plain markdown so the CV page can render it and the reader can verify
it against git at any time.
"""

from __future__ import annotations

import subprocess

CURATED = "/web/timeline.md"


def _git_log(lines: int = 60) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", "/web", "log", "--pretty=format:%ad %s", "--date=short", f"-{lines}"],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() or ""
    except Exception:  # noqa: BLE001
        return ""


def build() -> str:
    curated = ""
    try:
        curated = open(CURATED, encoding="utf-8").read().strip()
    except Exception:  # noqa: BLE001
        pass

    git = _git_log()
    if not git:
        git = "no git history available"
    section = (
        "\n\n---\n\n"
        "## Full git history (machine-readable)\n\n"
        "```\n" + git + "\n```"
    )
    return curated + section