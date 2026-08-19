<!-- reflex managed begin (do not edit inside this block; add custom content outside the markers) -->
# Agents

This project uses the **Reflex agent skills** — up-to-date knowledge for building full-stack Python web apps with [Reflex](https://reflex.dev). Install them first, then use them as described below.

## Installing the Skills

Before working on this project, make sure the Reflex skills are available to you.

### Claude Code

If the skills are not already available, install them yourself by running these shell commands:

```bash
claude plugin marketplace add reflex-dev/agent-skills
claude plugin install reflex@reflex-agent-skills
```

Newly installed plugins load on the next session. After installing, tell the user to restart the session so the skills auto-load; until then, read the skill files directly from `~/.claude/plugins/` when you need them.

### Other agents (Cursor, OpenCode, Codex, Pi)

```
npx skills add reflex-dev/agent-skills
```

Or clone https://github.com/reflex-dev/agent-skills and copy the `skills/` folders into your agent's skill directory (see the repo README for paths).

### Verifying

Before writing or editing any Reflex code, confirm these three skills are available: `reflex-docs`, `setup-python-env`, and `reflex-process-management`. If they are not, STOP and run the install step above — do not proceed without them.

## Using the Skills

### Reflex documentation

For anything about Reflex APIs — components, state management, events, styling, database, routing, authentication — use the **reflex-docs** skill rather than relying on memory. It carries current, version-accurate docs.

### Initializing a new Reflex project

When starting a new Reflex project or setting up a development environment, you **must** follow the **setup-python-env** skill before doing anything else.

Do not skip any steps. Do not assume a virtual environment or Reflex is already available — always verify first by following the skill's instructions in order.

After the environment is ready and Reflex is installed, run:

```bash
reflex init
```

Then proceed with the user's request.

### Managing a Reflex process

When you need to compile, run, reload, or debug a Reflex application, follow the **reflex-process-management** skill for the correct sequence and error investigation steps.
<!-- reflex managed end -->

# AGENTS.md — operating rules for agents working in this CV site (`/web`)

> Canonical ops runbook: **`/web/README.md`**. This file = Reflex *dev rules + test harness* only.

## ⚠️ Hard constraints (do not violate)
- **Edit the app, NEVER the framework.** Everything you change lives under `/web`.
  Do NOT touch the Reflex framework files in the venv
  (`site-packages/reflex/**`, `site-packages/reflex_base/**`,
  `site-packages/reflex_components_*/**`, etc.). This box has **no internet for `pip install`**,
  so a "framework edit" is really an API misuse — work around it in the app layer, or stop.
- **One task, idempotent.** The app boots via
  `/root/.bashrc` -> `/usr/local/bin/start-rdp-server.sh` ->
  `/etc/init.d/websiteserver start`. Make every change safe to re-run.
- **Do not touch git history destructively.** Prefer additive edits; never rewrite
  commits already pushed to this LXC (it is the only "remote").
- **Never create branches. Trunk-based only.** Commit **directly on `main`**. Do NOT
  run `git checkout -b` / `git switch -c` / `git branch <name>`, and do NOT open pull
  requests. Stray agent-created branches (`*-<taskid>`) polluted the remote and had to
  be force-deleted; a `.githooks/pre-commit` hook now refuses commits off `main`
  (`core.hooksPath` is set to `.githooks` in this clone; keep it that way).

## Reality check (what this actually is right now)
- Public site: **`https://frank-escudero.com`** via **Cloudflare Tunnel**
  (`cloudflared`), terminating on `127.0.0.1:8000`. The old Tailscale Funnel URL
  `cv.story-tegu.ts.net` still exists but **301-redirects** to `frank-escudero.com`
  (`RedirectOldDomainMiddleware` in `main.py`).
- Stack: Reflex 0.9.7, Python 3.13, `uv`, `--env prod`, `backend_port=8000`, `frontend_port=8000`.
- Host: systemd-less Debian 13 LXC (`cv`), PID 1 = `bash`; **boot = `/root/.bashrc`**.
- Code layout: `main.py` is a thin entry point; all real logic lives in the
  **`/web/webapp/` package** (see README). Pages: `/`, `/cv`, `/timeline`
  (+ `robots.txt`, `sitemap.xml`). Markdown content: `home.md`, `cv.md`, `timeline.md`.
- **LLM (chat, greeting, style): the olla proxy** on the tailnet box `gx10-23ef`
  (`100.100.1.10`), OpenAI-compatible endpoint
  `CHAT_URL="http://100.100.1.10:40114/olla/proxy/v1"`, **no auth required**
  (`CHAT_API_KEY="olla"` is accepted), model `CHAT_MODEL="prism-ml/bonsai-27b"`.
  These are the defaults in `/web/webapp/bot.py` and `/etc/init.d/websiteserver`.
  Do NOT point anything at LM Studio `:1234` or the retired Ollama
  `100.100.1.7:8080` endpoints. Never touch `/dev/nvidia*` (no GPU passthrough in this LXC).

## Reflex dev rules (the ones that save time)
- Edit only: `/web/main.py`, `/web/rxconfig.py`, `/web/webapp/` (package modules),
  and the markdown content under `/web/` that the pages render (`home.md`, `cv.md`,
  `timeline.md`). Other `.md` files (knowledge/README/architecture/...) are docs —
  update them only when behavior changes.
- Never edit the venv. Use `/web/.venv/bin/python`, `/web/.venv/bin/reflex` if needed (rare).
- `rxconfig.py`: `show_built_with_reflex=False`, `telemetry_enabled=False`, `disable_plugins=[SitemapPlugin]`,
  `backend_port=8000`. If the "Built with Reflex" badge reappears, this line was reverted — fix here, not in the DOM.
- Pages via `app.add_page(fn, route=..., title=...)`. Use `rx.link` for nav. **Trailing slashes matter:** Reflex redirects `/x` -> `/x/`, so a nav link to `/cv` (no slash) costs you an extra 200 hop in tests. Use `/cv/`.
- Styling via `rx.*` primitives + `class_name:`; do not inject arbitrary Tailwind classes (Reflex 0.9.7 props, not Tailwind).
- Components: every page fn returns `rx.Component`. Reuse `nav()` and `footer()`; if you add a route, add it to the nav so link counts stay consistent.
- Static assets: **no writes to `/web/assets`**. Favicon is an inline SVG data-URI in
  `rx.App(head_components=[rx.el.link(rel="icon", href=<data-uri>)])`.
- `<title>` + `<meta description>` live in `head_components`/`rx.App`. Do not duplicate per page unless the title genuinely differs.
- `rx.Html(...)` content is SSR-rendered *and* client-rendered. If a snippet needs the browser, wrap it in `if (typeof document !== 'undefined')` (see the probe/theme script patterns in `webapp/js.py` and `webapp/state.py`).

## Data model (SQLite, the "store")
`/web/webapp/db.py` manages `/web/data/site.db` (WAL). Tables:
- `visitors` — per-device fingerprint (`device_id` PK, device name, profile JSON, IPs, visits).
- `visits` — per-load rows (path, ip, ua, lang, ref).
- `messages` — chat log (device_id, role, content).
- `blocks` — **per-client** CSS/HTML/JS overrides keyed by device_id.
- `block_pool` — shared pool any visitor can receive.

## How to test (do this before every commit)
### A. Syntax + import (instant, offline)
```bash
cd /web
/root/.local/bin/uv run --no-sync python -m py_compile main.py webapp/*.py   # all modules
/root/.local/bin/uv run --no-sync python - <<'PY'                            # imports OK?
from webapp import db, bot, theme, device
import main; print("ok")
PY
```
### B. Restart + HTTP contract (after `/etc/init.d/websiteserver restart`, sleep ~9)
```bash
for p in / /cv/ /timeline/ /robots.txt /sitemap.xml; do
  printf "%-12s " "$p"; curl -sS -m6 -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8000$p"
done
# prose in SSR
curl -fsS -m6 http://127.0.0.1:8000/ | grep -q "Frank Escudero" && echo "home ok"
curl -fsS -m6 http://127.0.0.1:8000/cv/ | grep -qi "curl\|pip\|experience" && echo "cv ok"
curl -fsS -m6 http://127.0.0.1:8000/timeline/ | grep -qi "timeline" && echo "timeline ok"
# old funnel domain must 301 to frank-escudero.com
curl -sS -m6 -o /dev/null -w "old domain -> %{http_code}\n" -H "Host: cv.story-tegu.ts.net" http://127.0.0.1:8000/
```
### C. Chat + LLM (against the olla proxy)
```bash
curl -s http://100.100.1.10:40114/olla/proxy/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"prism-ml/bonsai-27b","messages":[{"role":"user","content":"say ok"}],"max_tokens":8}'
```
### D. Log-bomb sentinel (must stay near 0)
```bash
echo "log1 = $(stat -c%s /var/lib/tailscale/tailscaled.log1.txt)B"
ps -ef | grep -E 'tailscaled.*no-logs-no-support' | grep -v grep || echo "FIX: tailscaled lost its no-log flag"
```

**Red lines:** a non-200 on `/`, "Built with Reflex" present, `/:8000` half-bound, or log1 growing past a few KB — stop and fix before committing.

## Restart flow (no systemd)
```bash
/etc/init.d/websiteserver restart   # race-free: kills pgid + reflex/uv children, waits for :8000 free
```
Never `reflex run` from a shell — that leaks children and leaves `:8000` half-bound, which is exactly what triggers the tailscaled log bomb (see below).

## Chat/personalization debugging (time-saver #2)
- Everything relevant to the assistant lives in `/web/webapp/bot.py` (system prompt,
  chat call), `state.py` (greeting, probe handling), `theme.py` (per-client accent),
  `blocks.py` (per-client CSS/HTML/JS). Grep `/var/log/websiteserver.log` for
  `greeting:` / `probe` / `blocks` to trace the pipeline (raw probe JSON -> ip ->
  device_name -> theme -> blocks -> chat).
- The greeting degrades gracefully: if geolocation is empty (tailnet/CGNAT/`127.0.0.1`)
  the starter text just omits location. Do not "fix" it.
- Never put a raw timezone string in a prompt handed to the LLM — the model repeats
  it as a location ("Europe/Berlin" -> "you are in Berlin"). Pass only resolved
  local time-of-day, or the profile fields (`tz`) are fine as raw data for scoring;
  keep raw TZ out of the LLM prose.
- Windows browsers can't render flag emoji; the greeting omits the flag on `Win`.
  ONLY the flag emoji is blocked — weather/sun/moon emoji must still be used.
- The per-client persona is built in `bot.system_prompt(profile, device_name, history_count)`.
  The assistant may attach CSS/HTML/JS blocks to a visitor via `extract_theme()` /
  `db.save_block()`; blocks render from `blocks.for_client(device_id)`.

## The log-bomb lesson (time-saver #1)
- Symptom: `/var/lib/tailscale/tailscaled.log1.txt` swelled to 49 GB; disk fell to 0% free; Reflex restarts failed to bind `:8000`; the old Funnel returned 502.
- Root cause: `tailscaled` logtail retried `dial 127.0.0.1:8000: connect: connection refused` recursively during a rebuild, while `tailscaled` was started **without** `--no-logs-no-support`.
- Fix (applied in `/usr/local/bin/start-rdp-server.sh`): `tailscaled --no-logs-no-support ... 2>/dev/null`.
- Agent rule: if `ps -ef | grep tailscaled` does NOT show `--no-logs-no-support`, the start script was reverted or tailscaled was restarted by hand without the flag — re-apply the flag before doing anything else. log1 must stay ≈0 B.

## Boot survival (so you don't break it)
- `/root/.bashrc` -> `start-rdp-server.sh` brings up sshd -> dbus -> xrdp+Plasma ->
  tailscaled -> ollama-as-frank -> cloudflared -> websiteserver.
- Worker (`/etc/init.d/opencode-worker`) and cron are OFF by design. Do not enable either.
- `cron_improve.py` exists but is **disabled by default** (`ENABLE_CRON_IMPROVE=1`
  must be set) and imports the old `site_store`/`main.get_chat_client` APIs — it is
  currently broken on purpose; do not blame regression reports on it.
- On reboot, `https://frank-escudero.com/` must be 200 within ~15s (cloudflared) and
  `https://cv.story-tegu.ts.net/` must 301. If `:8000` won't bind after boot, run
  `lsof -iTCP:8000 -sTCP:LISTEN` and restart websiteserver.