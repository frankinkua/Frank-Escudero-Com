## Timeline — accomplished vs. next

### Done
- Headless box booted (Debian 13 LXC, no systemd). `sshd`, `dbus`, `xrdp`+KDE/Plasma RDP, Tailscale, Ollama, Reflex site — all up via `/root/.bashrc -> start-rdp-server.sh`.
- Public site over a Tailscale Funnel: `https://cv.story-tegu.ts.net` -> `127.0.0.1:8000`.
- Killed the **49 GB runaway tailscale log** (cured permanently: tailscaled `-no-logs-no-support` + stderr -> /dev/null).
- App LLM switched to on-cpu `qwen3.5:0.8b` (fast).
- Removed the "Powered by Reflex" badge; added version + last-updated footer on every page.
- Added `/cv`, `/deploy`, `/stack`, `/timeline` pages + favicon + page `<title>`.
- Disabled the auto-restarting agent (cron off, opencode-worker off by default) so the site stays stable.
- Documented everything in `/root/README.md` and `/web/AGENTS.md`.

### Next (toward the 48h launch mark)
- Drop Frank's real CV data into `/web/cv.md` (placeholder now).
- Make the countdown live (JS) if desired; otherwise it refreshes on each site restart.
- Optional: re-enable the AI employee (`opencode-worker`) to keep regenerating.
- Optional: wire NVIDIA GPU passthrough so Ollama can run models on GPU.
