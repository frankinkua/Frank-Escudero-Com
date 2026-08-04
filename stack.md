## Tech stack

Hosted on a single hardened **Debian 13 LXC** (`cv`, no systemd — PID 1 = bash).
All boot logic lives in `/usr/local/bin/start-rdp-server.sh` (reached from
`/root/.bashrc`).

### Access & network
- **Tailscale** tailnet `story-tegu.ts.net`; this node is `cv` @ `100.115.209.119`,
  authed as `franke2032@`, operator `frank`.
- **Zero-trust ingress** via **Tailscale Funnel**: `https://cv.story-tegu.ts.net`
  (443) -> `127.0.0.1:8000`. No public web server, no port forwarding.
- **RDP**: xrdp 0.10.1 + KDE/Plasma (X11 only, no Wayland); NVIDIA GPUs are
  passthrough nodes (chmod 666) but run **AI-only** (GLX disabled in the xrdp
  Xorg config).

### App backend
- **Reflex 0.9.7** (Python 3.13), `--env prod`, ASGI (Starlette/uvicorn) backend
  on `:8000`, front served from the same origin. `rxconfig.py`: `app_name="web"`,
  `backend_port=frontend_port=8000`, `show_built_with_reflex=False` (no Reflex
  badge). Chat LLM on-cpu: `qwen3.5:0.8b` (~1 GB), via Ollama.

### AI / LLM
- **Ollama** (as `frank`), serving `127.0.0.1:11434`. Models present:
  `qwen3.5:0.8b` (site chat), `gemma4:latest` (the on-cpu AI-employee agent).
  CPU inference only (no GPU wired yet).

### Self-healing / ops
- Boot: `~/.bashrc` -> `start-rdp-server.sh` (idempotent, `pgrep`-guarded):
  sshd -> dbus -> xrdp -> tailscaled (`-no-logs-no-support`) -> ollama -> Reflex.
- **No systemd**; services are `/etc/init.d/*` scripts (`ssh`, `xrdp`, `dbus`,
  `cron`) + the `websiteserver`/`opencode-worker` scripts.
- **Log bomb protection**: tailscaled `-no-logs-no-support` + stderr ->
  `/dev/null`; `du -h /var/lib/tailscale/tailscaled.log1.txt` stays ~2 KB.
- **Rollback**: the AI employee commits each cycle to git in `/web` (`git log` /
  `git checkout`).

### Notes
- cron is **disabled** (no recurrent jobs; only the @reboot bootstrap is inert).
- the opencode-worker is **off** by default; start it with
  `/etc/init.d/opencode-worker start` (60-min loop, `gemma4:latest`, commits to
  `/web`).
