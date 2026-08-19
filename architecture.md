# The site's architecture, in depth

This page explains how `frank-escudero.com` actually works end to end.

## One site, one container

The whole site runs on a **single Debian 13 LXC container** named `cv` inside
Frank's home datacenter on the `story-tegu.ts.net` tailnet. There is no
systemd — PID 1 is `bash`, and the boot chain is:

```
/root/.bashrc
  └─ /usr/local/bin/start-rdp-server.sh
       ├─ sshd
       ├─ dbus
       ├─ xrdp + KDE/Plasma (X11, NVIDIA = AI-only)
       ├─ tailscaled --no-logs-no-support
       ├─ cloudflared (Cloudflare Tunnel → frank-escudero.com)
       └─ /etc/init.d/websiteserver start
            └─ reflex run --env prod (backend + frontend on :8000)
```

## Zero-trust ingress

The public URL is `https://frank-escudero.com`, served through a **Cloudflare
Tunnel** (token-based, `/etc/cloudflared/token`, runs as root). There is no
port forwarding and no public web server of our own:

```
visitor ──https──► Cloudflare Tunnel frank-escudero.com
                     └─► 127.0.0.1:8000  (Reflex, prod)
                           │  pages (SSR + hydration)
                           └─► olla LLM proxy 100.100.1.10:40114/olla/proxy/v1
```

The old Tailscale Funnel URL `cv.story-tegu.ts.net` still exists and
**301-redirects** to `frank-escudero.com` (middleware in `main.py`).

Tailnet-origin visitors resolve as CGNAT `100.x` or `127.0.0.1`, so geolocation
only works for public-IP visitors — the greeting degrades gracefully.

## The AI layer

One remote proxy powers chat, greeting and live restyle: the **olla LLM proxy**
on the tailnet box `gx10-23ef` (`100.100.1.10`), OpenAI-compatible at
`http://100.100.1.10:40114/olla/proxy/v1`, **no auth token**. The site uses
`prism-ml/bonsai-27b` for visitors (`CHAT_MODEL`).

```
            ┌─────────────────────────────┐
            │  olla proxy 100.100.1.10    │
            │  /olla/proxy/v1 (no auth)   │
            └───────▲─────────────────────┘
                    │ OpenAI-compatible /v1
   ┌────────────────┴───────────────┐
   │  chat (visitors)               │
   │  greeting (personalized)       │
   │  live restyle (theme/blocks)   │
   └────────────────────────────────┘
```

- **Probe / fingerprint:** on first load the browser runs a small probe script
  (`webapp/js.py`) and posts UA, screen, cores, memory, timezone, languages,
  WebRTC local IPs. The server builds a stable `device_id` and a normalized
  device name ("Samsung Galaxy S25 Ultra") fingerprint stored in SQLite.
- **Greeting:** `webapp/state.py` computes a first-visit greeting from the
  fingerprint (first time? returning? which device? which accent?) — no LLM
  round-trip needed for the greeting text.
- **Theme:** `webapp/theme.py` scores the profile (GPU vendor, timezone,
  language, screen shape) to pick an accent + gradient, injected per client.
- **Chat:** every visitor turn goes through `webapp/bot.py` → olla proxy with a
  system prompt built from `cv.md` + `timeline.md` + the client profile.
- **Blocks:** per-client CSS/HTML/JS overrides live in the SQLite `blocks`
  table (and a shared `block_pool`); the assistant can attach one via
  `extract_theme()` / `db.save_block()`.

## Storage

`/web/data/site.db` (SQLite, WAL, gitignored) holds `visitors`, `visits`,
`messages`, `blocks`, `block_pool`. Managed by `webapp/db.py`.

## Self-healing & resilience

- Every change is a git commit in `/web`, pushed to GitHub (`frankinkua/cv`);
  the timeline page shows the recent history.
- The boot script is idempotent; stray processes are `pgrep`-guarded so restarts
  are safe. A stale half-bound `:8000` is cleared by the restart flow.
- A runaway `tailscaled` log once filled the disk (49 GB); the start script now
  runs tailscaled with `--no-logs-no-support`, and the sentinel must stay at 0 B.
- The assistant bot's replies persist to `messages`, so a visitor's chat history
  survives reloads.

## Read more

- `/web/README.md` — the ops runbook (files, tests, reflections).
- `/web/AGENTS.md` — Reflex dev rules + test harness.
- `/web/webapp/` — the implementation package.