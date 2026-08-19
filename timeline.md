# Timeline

A human-readable history of the work on this site and the home datacenter that
ships it. The machine-readable git log is appended below automatically.

## The pipeline that moves this site

- **2026-08-03** — `bootstrap.sh` boot entrypoint, one source of truth for
  service ordering on a systemd-less LXC (PID 1 = bash).
- **2026-08-03** — `start-rdp-server.sh` idempotent boot: openssh, dbus, xrdp,
  tailscaled, ollama, the Reflex website on `:8000`, opencode-serve on `:4096`.
- **2026-08-10** — **Cloudflare Tunnel** for `frank-escudero.com` (token-based,
  `cloudflared tunnel run`), wired into boot so the public URL survives reboots.
- **2026-08-18** — chat + cron worker repointed to the **olla LLM proxy**
  (`100.100.1.10:40114/olla/proxy/v1`), replacing the retired LiteLLM `:4000`.

## The chat / engagement work

- **2026-08-05** — ntfy.sh notifications, visitor fingerprint (incl. IP),
  appointments redirect, `/robots.txt`, sitemap + RSS, uptime ticker.
- **2026-08-07** — admin dashboard, live chat handling, 80k-token compactor.
- **2026-08-10** — floating chat FAB + popup window; trunk-based workflow
  guardrails (no feature branches).
- **2026-08-18** — repointed chat + worker to the olla proxy.

## The 2026-08-19 rebuild (this site)

Absolute-scratch rebuild of the CV site with:

- a clean modular Python package (`webapp/`) instead of a 3,974-line monolith;
- SQLite visitor/visit/block store (`data/site.db`);
- per-device fingerprint (UA -> readable device name, screen, cores/memory,
  timezone, language, WebRTC local IP observations) stored under a stable
  `device_id`;
- an **aggressive** site assistant: opens the chat by itself, greets the visitor
  by the learned device/profile, nudges idle visitors, and restyles the site
  live for them (theme + optional per-client CSS/HTML/JS blocks loaded from the
  database).