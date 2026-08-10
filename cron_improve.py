#!/usr/bin/env python3
"""Self-improving cron: analyzes visitor chats -> proposes/applies content & style tweaks.

Run manually: `uv run --project /web python cron_improve.py`
Enable via systemd: `systemctl enable --now cv-improve.timer`

Safety: exits immediately unless ENABLE_CRON_IMPROVE=1 in environment.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure we can import from /web
sys.path.insert(0, "/web")

import site_store
from main import get_chat_client, CHAT_MODEL

logger = logging.getLogger("cron_improve")

WEB = Path("/web")
DATA = WEB / "data"

# Exit early if not enabled
if os.environ.get("ENABLE_CRON_IMPROVE", "0") != "1":
    print("Cron improvement disabled. Set ENABLE_CRON_IMPROVE=1 to enable.")
    sys.exit(0)

# Load settings
site_store.ensure_default_settings()
settings = site_store.get_all_settings()
LOOKBACK_HOURS = int(settings.get("cron_lookback_hours", 24))
MIN_CONFIDENCE = float(settings.get("cron_min_confidence", 0.8))
MAX_CHANGES = int(settings.get("cron_max_changes_per_run", 5))
NOTIFY_ON_APPLY = settings.get("cron_notify_on_apply", True)

ANALYSIS_PROMPT = """You are a content strategist analyzing visitor conversations on Frank Escudero's CV site.
Extract ONLY actionable improvements to existing content/style.

ALLOWED (return as type "content" or "style"):
- Rewrite homepage intro, about text, project descriptions, contact info
- Adjust CSS custom properties (colors, spacing, fonts, radii) via :root variables
- Fix typos, clarify confusing copy, add missing info visitors asked about
- Improve engagement copy (CTAs, value props, FAQ entries)

FORBIDDEN (return as "too_big" with contact info):
- New features/pages/components/routes
- Code changes (Python, JS, Reflex logic, HTML structure)
- Admin/auth/permission changes
- Database/schema changes
- Any logic modification
- Adding/removing files

CSS CUSTOM PROPERTIES AVAILABLE (in :root):
--bg: main background
--card-bg: card background  
--accent: primary accent color (green #4ade80)
--muted: muted text color
--border: border color
--card-radius: border radius for cards
--font-mono: monospace font stack
--font-sans: sans-serif font stack
--transition-fast: fast transition duration
--transition-normal: normal transition duration

OUTPUT JSON ONLY:
{
  "proposals": [
    {
      "type": "content|style|too_big|reject",
      "target": "home.md|knowledge.md|cv.md|projects.md|contact.md|:root",
      "current": "exact current text or CSS value",
      "proposed": "exact proposed replacement",
      "reason": "Visitors asked X 3 times / analytics show Y",
      "visitor_contact": "hashed_email_or_ip",
      "confidence": 0.85
    }
  ]
}"""


def get_css_custom_properties() -> dict[str, str]:
    """Read current CSS custom properties from main.py head_components."""
    main_py = WEB / "main.py"
    content = main_py.read_text()
    # Extract :root { ... } from GIRLY_CSS or head_components
    # For now, return defaults - the LLM will propose changes
    return {
        "--bg": "#0b0e14",
        "--card-bg": "#131826",
        "--accent": "#4ade80",
        "--muted": "#66708a",
        "--border": "#2a3247",
        "--card-radius": "0.9rem",
        "--font-mono": "ui-monospace, Menlo, monospace",
        "--font-sans": "system-ui, -apple-system, sans-serif",
        "--transition-fast": "150ms",
        "--transition-normal": "300ms",
    }


def read_content_file(filename: str) -> str:
    """Read a markdown content file."""
    path = WEB / filename
    try:
        return path.read_text()
    except OSError:
        return ""


def write_content_file(filename: str, content: str) -> bool:
    """Write a markdown content file atomically."""
    path = WEB / filename
    try:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(content)
        import os
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def apply_css_change(prop: str, value: str) -> bool:
    """Apply a CSS custom property change to main.py head_components."""
    main_py = WEB / "main.py"
    content = main_py.read_text()
    
    # Find the CSS custom properties in head_components
    # We'll inject them into a new <style> in head_components
    # For simplicity, we'll update a dedicated CSS variable block
    marker = "/* CRON_CSS_VARS_START */"
    end_marker = "/* CRON_CSS_VARS_END */"
    
    new_vars = f"""{marker}
:root {{
  {prop}: {value};
}}
{end_marker}"""
    
    if marker in content:
        # Replace existing
        import re
        pattern = f"{marker}.*?{end_marker}"
        content = re.sub(pattern, new_vars, content, flags=re.DOTALL)
    else:
        # Insert before </head> equivalent - find head_components list
        # Add to GIRLY_CSS area or create new style
        # For now, append to GIRLY_CSS (it's in head_components)
        insert_point = content.find("GIRLY_CSS = \"\"\"")
        if insert_point != -1:
            content = content[:insert_point] + new_vars + "\n\n" + content[insert_point:]
        else:
            return False
    
    try:
        tmp = main_py.with_suffix(main_py.suffix + ".tmp")
        tmp.write_text(content)
        import os
        os.replace(tmp, main_py)
        return True
    except OSError:
        return False


def git_commit_and_push(message: str) -> tuple[bool, str]:
    """Commit all changes and push. Returns (success, commit_sha)."""
    try:
        # Add all changes
        subprocess.run(["git", "add", "-A"], cwd=WEB, check=True, capture_output=True)
        # Commit
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=WEB, check=True, capture_output=True, text=True
        )
        # Get commit SHA
        sha_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=WEB, check=True, capture_output=True, text=True
        )
        sha = sha_result.stdout.strip()
        # Push
        subprocess.run(["git", "push", "origin", "main"], cwd=WEB, check=True, capture_output=True)
        return True, sha
    except subprocess.CalledProcessError as e:
        return False, e.stderr


def send_ntfy(title: str, message: str, tags: list[str] | None = None) -> None:
    """Send ntfy notification."""
    try:
        import httpx
        ntfy_url = os.environ.get("NTFY_URL", "https://ntfy.sh/franke2032")
        headers = {"Title": title[:200]}
        if tags:
            headers["Tags"] = ",".join(tags)
        with httpx.Client(timeout=10.0) as client:
            client.post(ntfy_url, content=message.encode("utf-8"), headers=headers)
    except Exception:
        pass


async def analyze_conversations() -> list[dict]:
    """Analyze recent conversations and return proposals."""
    convs = site_store.get_recent_conversations(LOOKBACK_HOURS)
    if not convs:
        return []
    
    pairs = site_store.get_visitor_messages(convs)
    if not pairs:
        return []
    
    # Build conversation summary for LLM
    conv_summary = []
    for p in pairs[-50:]:  # Limit to last 50 pairs
        conv_summary.append(f"Q: {p['question'][:200]}\nA: {p['answer'][:200]}")
    
    transcript = "\n---\n".join(conv_summary)
    
    # Get current content for context
    current_content = {
        "home.md": read_content_file("home.md"),
        "knowledge.md": read_content_file("knowledge.md"),
        "cv.md": read_content_file("cv.md"),
        "projects.md": read_content_file("projects.md"),
        "contact.md": read_content_file("contact.md"),
    }
    css_props = get_css_custom_properties()
    
    context = f"""CURRENT CONTENT:
{json.dumps(current_content, indent=2)}

CURRENT CSS VARIABLES:
{json.dumps(css_props, indent=2)}

VISITOR CONVERSATIONS (last {LOOKBACK_HOURS}h):
{transcript}"""
    
    client = get_chat_client()
    if client is None:
        logger.warning("AI chat disabled, skipping analysis")
        return []
    resp = await client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": ANALYSIS_PROMPT},
            {"role": "user", "content": context},
        ],
        temperature=0.3,
        max_tokens=4096,
    )
    
    raw = resp.choices[0].message.content.strip()
    try:
        # Extract JSON from response
        start = raw.find("{")
        end = raw.rfind("}") + 1
        data = json.loads(raw[start:end])
        return data.get("proposals", [])
    except Exception:
        return []


def hash_contact(email: str, ip: str) -> str:
    """Create a privacy-preserving contact identifier."""
    import hashlib
    source = f"{email}:{ip}" if email else ip
    return hashlib.sha256(source.encode()).hexdigest()[:12]


async def main():
    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting cron improvement run")
    
    proposals = await analyze_conversations()
    if not proposals:
        print("No proposals generated")
        return
    
    print(f"Generated {len(proposals)} proposals")
    
    applied = []
    pending = []
    rejected = []
    
    for prop in proposals[:MAX_CHANGES]:
        prop_type = prop.get("type", "reject")
        confidence = prop.get("confidence", 0)
        
        if prop_type in ("content", "style") and confidence >= MIN_CONFIDENCE:
            # Auto-apply
            target = prop.get("target", "")
            proposed = prop.get("proposed", "")
            current = prop.get("current", "")
            
            success = False
            if target.endswith(".md"):
                # Content change
                current_content = read_content_file(target)
                if current in current_content:
                    new_content = current_content.replace(current, proposed, 1)
                    if write_content_file(target, new_content):
                        success = True
            elif target == ":root":
                # CSS change - prop should contain the property name
                # For CSS, we need to know which property
                # The proposed field should be "property: value"
                if ":" in proposed:
                    css_prop, css_val = proposed.split(":", 1)
                    css_prop = css_prop.strip()
                    css_val = css_val.strip()
                    if apply_css_change(css_prop, css_val):
                        success = True
            
            if success:
                applied.append(prop)
                print(f"Applied: {target}")
            else:
                prop["type"] = "rejected"
                prop["reject_reason"] = "Failed to apply"
                rejected.append(prop)
        elif prop_type == "too_big":
            # Log for review with contact info
            prop["visitor_contact"] = prop.get("visitor_contact", "unknown")
            pending.append(prop)
            print(f"Too big (logged for review): {prop.get('reason', '')[:80]}")
        else:
            rejected.append(prop)
    
    # Commit if any applied
    commit_sha = None
    if applied:
        commit_msg = f"cron: auto-improve ({len(applied)} changes)"
        success, sha = git_commit_and_push(commit_msg)
        if success:
            commit_sha = sha
            print(f"Committed: {sha[:7]}")
            # Log applied proposals
            for prop in applied:
                prop["type"] = "applied"
                prop["commit_sha"] = sha
                site_store.log_proposal(prop)
            # Notify
            if NOTIFY_ON_APPLY:
                send_ntfy(
                    f"Cron: {len(applied)} improvements applied",
                    "\n".join(f"- {p.get('target')}: {p.get('reason', '')[:60]}" for p in applied),
                    ["robot", "chart_increasing"]
                )
        else:
            print(f"Commit failed: {sha}")
            for prop in applied:
                prop["type"] = "rejected"
                prop["reject_reason"] = f"Commit failed: {sha}"
                rejected.append(prop)
    
    # Log pending/rejected
    for prop in pending:
        site_store.log_proposal(prop)
    for prop in rejected:
        site_store.log_proposal(prop)
    
    print(f"Done. Applied: {len(applied)}, Pending: {len(pending)}, Rejected: {len(rejected)}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())