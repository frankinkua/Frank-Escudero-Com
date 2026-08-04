## Timeline — accomplished vs. next

### Done
- Headless box booted (Debian 13 LXC, no systemd). `sshd`, `dbus`, `xrdp`+KDE/Plasma RDP, Tailscale, Ollama, Reflex site — all up via `/root/.bashrc -> start-rdp-server.sh`.
- Public site over a Tailscale Funnel: `https://cv.story-tegu.ts.net` -> `127.0.0.1:8000`.
- Extinguished the **49 GB runaway tailscale log** (cured permanently: tailscaled `-no-logs-no-support` + stderr -> /dev/null).
- Right-sized the in-browser LLM to on-cpu `qwen3.5:0.8b` for low-latency chat on a constrained single box.
- Presented this site under its own brand by stripping the "Powered by Reflex" attribution; added version + last-updated footer on every page.
- Added `/cv`, `/deploy`, `/stack`, `/timeline` pages + favicon + page `<title>`.
- Kept the site stable by leaving the auto-restarting agent off (cron off, opencode-worker off by default).
- Documented everything in `/root/README.md` and `/web/AGENTS.md`.

### Next (toward the 48h launch mark)
- The CV content is delivered and live; no placeholder remains.
- The countdown is live (JS) and auto-refreshes on each site restart.
- Optional: re-enable the AI employee (`opencode-worker`) to keep regenerating.
- Optional: wire NVIDIA GPU passthrough so Ollama can run models on GPU.
