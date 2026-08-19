## Tech stack

Hosted on a single hardened **Debian 13 LXC** (`cv`, no systemd — PID 1 = bash).
All boot logic lives in `/usr/local/bin/start-rdp-server.sh` (reached from
`/root/.bashrc`).

### Access & network
- **Tailscale** tailnet `story-tegu.ts.net`; this node is `cv` @ `100.115.209.119`,
  authed as `franke2032@`, operator `frank`.
- **Public ingress** via **Cloudflare Tunnel** (`cloudflared`, token-based):
  `https://frank-escudero.com` (443) -> `127.0.0.1:8000`. No public web server,
  no port forwarding. Legacy Funnel `https://cv.story-tegu.ts.net` 301s there.
- **RDP**: xrdp 0.10.1 + KDE/Plasma (X11 only, no Wayland); NVIDIA GPUs are
  passthrough nodes (chmod 666) but run **AI-only** (GLX disabled in the xrdp
  Xorg config). No GPU passthrough into this LXC.

### App backend
- **Reflex 0.9.7** (Python 3.13), `--env prod`, ASGI (Starlette/uvicorn) backend
  on `:8000`, front served from the same origin. `rxconfig.py`: `app_name="web"`,
  `backend_port=frontend_port=8000`, `show_built_with_reflex=False` (no Reflex
  badge). Thin `main.py` (3 pages) + `webapp/` package (db, device, js, theme,
  blocks, bot, state, components, timeline).

### LLM (the single model endpoint)
- **olla proxy** on the tailnet box `gx10-23ef` (`100.100.1.10`),
  OpenAI-compatible `http://100.100.1.10:40114/olla/proxy/v1`, **no auth**.
- Site model: `prism-ml/bonsai-27b` (`CHAT_MODEL`) — chat, greeting, live restyle.
- Do NOT point anything at LM Studio `:1234` or the retired Ollama hub
  `100.100.1.7:8080`.

### Self-healing / ops
- Boot: `~/.bashrc` -> `start-rdp-server.sh` (idempotent, `pgrep`-guarded):
  sshd -> dbus -> xrdp -> tailscaled (`-no-logs-no-support`) -> cloudflared ->
  Reflex.
- **No systemd**; services are `/etc/init.d/*` scripts (`ssh`, `xrdp`, `dbus`,
  `cron`, `cloudflared`) + the `websiteserver` / `opencode-worker` scripts.
- **Log bomb protection**: tailscaled `-no-logs-no-support` + stderr ->
  `/dev/null`; `du -h /var/lib/tailscale/tailscaled.log1.txt` stays ~0-2 KB.
- **Rollback**: all `/web` changes are committed to git and pushed to GitHub.

### Notes
- cron is **disabled** (no recurrent jobs; only the @reboot bootstrap is inert).
- the opencode-worker is **off** by default and must stay off.
- `cron_improve.py` (legacy self-improvement cron) is broken on purpose — it
  imports removed APIs and is off unless `ENABLE_CRON_IMPROVE=1` is set.