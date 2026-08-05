# The site's architecture, in depth

This page explains how `cv.story-tegu.ts.net` actually works end to end.

## One page, one datacenter

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
       └─ /etc/init.d/websiteserver start
            └─ reflex run --env prod (backend + frontend on :8000)
```

## Zero-trust ingress

There is **no public web server and no port forwarding**. Traffic arrives via
**Tailscale Funnel**, which exposes the node's HTTPS on port 443 and proxies it
to the local Reflex app:

```
visitor ──https──► Funnel cv.story-tegu.ts.net:443
                     └─► 127.0.0.1:8000  (Reflex, prod)
                           │  pages (SSR + hydration)
                           └─► chat/search backends
                                └─► LM Studio 192.168.178.120:1234 (LAN)
```

Funnel visitors on the tailnet arrive as CGNAT `100.x` or `127.0.0.1`, so
geolocation only works for public-IP visitors — the greeting degrades
gracefully.

## The AI layer

One remote LLM server powers everything: **LM Studio** on Frank's LAN at
`http://192.168.178.120:1234/v1` (OpenAI-compatible), running
`prism-ml/bonsai-27b` — a 27B reasoning model with a 256k context, kept loaded
in the box's 11 GB VRAM.

```
            ┌─────────────────────────────┐
            │  LM Studio (LAN box)        │
            │  prism-ml/bonsai-27b        │
            └───────▲─────────────────────┘
                    │ OpenAI-compatible /v1
   ┌────────────────┴───────────────┐
   │  chat (visitors)               │
   │  greeting (personalized)       │
   │  filter_draft (safety gate)    │
   │  opencode-worker (cron agent)  │
   └────────────────────────────────┘
```

- **Greeting:** on first load the browser reports language/platform/timezone +
  epoch ms; the server adds IP geolocation + open-meteo weather (temp,
  pressure, humidity, wind, sun/moon times, warnings) and asks the model for a
  1–3 sentence personalized greeting.
- **Chat:** every visitor turn is sent with the collected `visitor_context`
  merged into the system prompt, so the assistant stays personal.
- **Safety gate:** each draft passes `filter_draft()` against `/web/filter.md`;
  a draft leaking internal details is replaced with a polite fallback.
- **Worker:** a single-shot opencode agent (currently **off by design**) runs
  in yolo mode, edits the site, verifies it, and commits — with git rollback
  if a run breaks the site.

## Self-healing & resilience

- Every change is a git commit in `/web`; the footer shows the live commit SHA
  and date, doubling as a "am I running the latest build?" check.
- The worker verifies `http://127.0.0.1:8000` after each run and rolls back to
  the last good commit if the site goes down.
- A runaway `tailscaled` log once filled the disk (49 GB); the start script now
  runs tailscaled with `--no-logs-no-support`, and the sentinel must stay at 0 B.
- `/status/` shows uptime and the last worker runs; `/rss` and `/changelog/`
  are generated live from git.

## Read more

- `/stack/` — the technology list.
- `/status/` — live uptime + worker log summary.
- `/changelog/` — every commit, newest first.
