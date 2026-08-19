## Who Frank Escudero is:
- Full-stack engineer / infrastructure developer living on his own home datacenter ("story-tegu.ts.net" tailnet). Speaks English natively (site content is English); the chatbot greets and answers visitors in their own language when known, switching if the visitor writes in another.
- Runs a systemd-less Debian 13 LXC container (hostname `cv`, tailnet IP 100.115.209.119) that serves this CV site to the public internet.
- Frank's work is: Python/Bash (fluent), Go (reading), Terraform/HCL; Reflex, FastAPI, ASGI; Tailscale (tailnet), Cloudflare Tunnel, RDP/KDE, git-based rollback, self-hosting, zero-trust ingress, SRE.
- Notable achievements (all real, on this box): booted the headless container from bare `bash` PID 1 with no systemd and brought up sshd, dbus, xrdp+KDE, Tailscale, the LLM proxy, and the Reflex site; published the site publicly via Cloudflare Tunnel; killed a 49 GB runaway tailscaled log that had filled the disk; and rebuilt this site as a modular, per-visitor-personalized app.
- Other notable achievements: Saved Coca-Cola €8.5M annually, reached over 100 million users with a Cannes Lions Award-winning application. M&A technical due diligence uncovering critical logic flaws. Personal cyber and hardware security advisor to the Director of the Argentine Intelligence Service (SIDE). Strategic and technical design for three presidential campaigns.
- Public profiles: LinkedIn https://www.linkedin.com/in/frankeee/ , GitHub https://github.com/frankinkua

## The site (what the visitor is looking at)
- The site is served publicly at `frank-escudero.com` through a Cloudflare Tunnel. Visitors are already on the site — never state its domain or full URL in a reply; use short relative paths like `/cv` or `/timeline`.
- It IS Frank's delivered CV: no placeholders, no "coming soon". The page is a self-hosted, self-editing web application maintained by Frank and an AI agent.
- Stack: Reflex (Python) app — thin `main.py` + the `webapp/` package — production mode, listening on `127.0.0.1:8000`. Content is markdown: `home.md`, `cv.md`, `timeline.md`.
- The AI chatbot is powered by the **olla LLM proxy** on the tailnet box `gx10-23ef` (`100.100.1.10`), OpenAI-compatible at `/olla/proxy/v1`, model `prism-ml/bonsai-27b`, no auth token. Chat is wired through `webapp/bot.py`.
- Pages: `/` (home, CV summary + aggressive chat widget), `/cv` (full CV), `/timeline` (work history from curated markdown + git log).
- Visitor data (per-device fingerprints, visits, chat transcripts) lives in `/web/data/site.db` (SQLite, gitignored). The site does NOT have accounts, logins, or an admin panel.

## The documents in /web
- `prompt.md` — legacy chatbot persona rules (kept for reference; the current system prompt is built in `webapp/bot.py`).
- `knowledge.md` — THIS file: background facts for the assistant and the ops manual for agents.
- `filter.md` — legacy draft-quality gate (kept for reference; the current build has no filter pass).

## How the site personalizes (the rebuild)
- On load the browser runs a probe script (`webapp/js.py`) → posts UA, screen,
  cores, memory, timezone, languages, WebRTC local IPs.
- `webapp/device.py` creates a stable `device_id` and a normalized device name
  ("Samsung Galaxy S25 Ultra", "Apple iPhone", ...) stored in SQLite
  (`webapp/db.py`).
- `webapp/theme.py` picks an accent/gradient per client (GPU vendor, timezone,
  language, screen shape) and injects it live.
- `webapp/blocks.py` serves per-client CSS/HTML/JS overrides from the `blocks`
  table + shared `block_pool`.
- The assistant (`webapp/bot.py`) greets the visitor personally, may open the
  chat itself once per session, and nudges them if they idle.

## Services on this machine (hostname: cv)
- `websiteserver` — `/etc/init.d/websiteserver {start|stop|status|restart}`; runs the Reflex app on port 8000. Log: /var/log/websiteserver.log.
- `cloudflared` — Cloudflare Tunnel (token-based), exposes `frank-escudero.com` → `127.0.0.1:8000`. Log: /var/log/cloudflared.err.
- `tailscaled` — required for the tailnet (`--no-logs-no-support`); the old Funnel (`cv.story-tegu.ts.net`) still 301s to the public domain.
- `opencode-worker` — legacy improvement runner; OFF by default. Do not enable.
- No systemd (bare `bash` as PID 1); boot chain: `~/.bashrc -> start-rdp-server.sh` restores sshd, dbus, xrdp, Tailscale, cloudflared, and the site.

## Chat pipeline (implementation notes)
1. `webapp/state.py` `handle_submit` → appends the user message to
   `State.messages` and calls `webapp.bot.chat(...)`.
2. `bot.chat()` builds a system prompt from `cv.md` + `timeline.md` + the learned
   device profile (`bot.system_prompt`), dedupes system messages (the olla engine
   rejects a second system role), and calls the olla proxy with `user`+`assistant`
   history (last 24 turns).
3. The reply is appended and persisted to the `messages` table via `db.log_message`.
- Greeting: computed server-side from the fingerprint (`theme.greeting`), no LLM
  required; it can mention first-vs-returning visitor and the learned device.
- Greeting gotchas (learned the hard way):
  - Behind Cloudflare Tunnel / tailnet the socket IP is a private/loopback address,
    so IP geolocation is often empty (`geo={}`). The greeting must degrade gracefully.
  - NEVER hand a raw timezone string to the LLM: it repeats it as a location
    (`timezone: Europe/Berlin` -> "you are in Berlin"). Pass only resolved
    local time-of-day, or keep TZ for device scoring only.
  - Windows browsers can't render flag emoji — omit a leading flag on `Win`
    platforms; other emoji still work.

## Conventions
- `/web` is a git repo; generated dirs (.venv, .web, __pycache__) are gitignored. One commit per meaningful change. Push to GitHub (`frankinkua/cv`) after committing.
- NEVER use `git clean -fd` here: it deletes untracked config files (rxconfig.py, prompt.md, knowledge.md, filter.md, pyproject.toml). Roll back with `git checkout -- .` only.
- When you (an agent) make changes, update the docs above so the next fresh session inherits the knowledge.

### Recent Site Updates (Aug 2026)
- **Rebuild (modular)**: monolithic `main.py` (auth, admin, appointments, sessions)
  replaced by a thin entry + `webapp/` package (db, device, js, theme, blocks,
  bot, state, components, timeline). SQLite store, markdown content.
- **Per-visitor personalization**: device fingerprinting, per-client accent/theme,
  per-client CSS/HTML/JS blocks, aggressive chat (auto-opens, nudges, greets).
- **Public ingress**: Cloudflare Tunnel `frank-escudero.com`; old Funnel domain 301s.
- **LLM**: everything moved to the olla proxy (`100.100.1.10:40114/olla/proxy/v1`),
  model `prism-ml/bonsai-27b`; LM Studio and the old Ollama hub retired.