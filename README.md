# Frank Escudero — CV site

A zero-trust, self-hosted, AI-personalized CV site on a systemd-less Debian 13 LXC,
published behind a **Cloudflare Tunnel**.

- URL: https://frank-escudero.com/  (Cloudflare Tunnel → 127.0.0.1:8000)
- Local backend: http://127.0.0.1:8000

---

## Architecture (how it boots & stays up)

```
Internet  https://frank-escudero.com   →  Cloudflare Tunnel (cloudflared)
                                                      |
                                                Reflex 0.9.7 app
                                                      |
PID 1 = bash
  /root/.bashrc
    -> /usr/local/bin/start-rdp-server.sh        (single boot entrypoint; no systemd)
          1) sshd
          2) dbus
          3) xrdp + Plasma
          4) tailscaled   (-no-logs-no-support, stderr -> /dev/null)
          5) ollama serve  (user: frank — local models, unused by the site)
          6) /etc/init.d/cloudflared start      (token-based tunnel, frank-escudero.com)
          7) /etc/init.d/websiteserver start
                -> uv run --project /web reflex run --env prod --backend-port 8000
                   pidfile /run/websiteserver.pid, log /var/log/websiteserver.log
```

The site itself talks to the **olla LLM proxy** on the tailnet box `gx10-23ef`
(`100.100.1.10`): OpenAI-compatible `http://100.100.1.10:40114/olla/proxy/v1`,
**no auth**, model `prism-ml/bonsai-27b`. See "LLM" below.

- Worker (`/etc/init.d/opencode-worker`) and cron are OFF.
- Reboot recovers: `https://frank-escudero.com/` → 200 within ~15s. If `:8000` won't bind:
  `lsof -iTCP:8000 -sTCP:LISTEN` then `websiteserver restart`.

---

## Files we own (in `/web`)
- `main.py` — thin entry point: pages (`/`, `/cv`, `/timeline`), robots.txt, sitemap,
  old-domain redirect middleware.
- `rxconfig.py` — `show_built_with_reflex=False`, `telemetry_enabled=False`,
  `disable_plugins=[SitemapPlugin]`, `backend_port=frontend_port=8000`.
- `webapp/` — the package with all real logic:
  - `db.py` — SQLite store (`/web/data/site.db`): visitors, visits, messages, blocks, block_pool.
  - `device.py` — fingerprinting: `device_id` (stable), normalized device name, client profile.
  - `js.py` — client probe / auto-open-chat / nudge scripts.
  - `theme.py` — per-client accent + gradient (GPU/timezone/language-aware scoring).
  - `blocks.py` — per-client CSS/HTML/JS blocks (attach/detach/for_client/from_pool).
  - `bot.py` — assistant: system prompt, chat call (olla proxy), live restyle.
  - `state.py` — Reflex `State`: greeting, probe, chat, auto-open nudges.
  - `components.py` — nav, footer, chat widget, page bodies.
  - `timeline.py` — timeline builder (curated `timeline.md` + recent git log).
- `home.md`, `cv.md`, `timeline.md` — markdown content rendered by the pages.
- `AGENTS.md` — Reflex dev rules + the test checklist (agents should read this first).
- Docs (not rendered): `README.md`, `architecture.md`, `knowledge.md`, `deploy.md`,
  `stack.md`, `resources.md`, `filter.md`, `prompt.md`, `Todo.md`, `LEARNINGS.md`, `incident.md`.
- `.venv/` — managed by `uv` (do not edit).
- `requirements*` — pinned by `uv` (no internet on host).

Ops (ref-only, outside `/web`): `/etc/init.d/websiteserver`, `/etc/init.d/cloudflared`,
`/usr/local/bin/start-rdp-server.sh`, `/root/.bashrc`.

---

## LLM (chat, greeting, style)
- Endpoint: **olla proxy**, `CHAT_URL="http://100.100.1.10:40114/olla/proxy/v1"`
  (tailnet box `gx10-23ef` / "spark", Go proxy → backend hub, no auth token).
- Model: `CHAT_MODEL="prism-ml/bonsai-27b"` (visitor-facing bonsai).
- API key: `CHAT_API_KEY="olla"` is accepted (proxy needs none).
- Env defaults live in `/etc/init.d/websiteserver` and `/web/webapp/bot.py`. Do not
  point anything at LM Studio `:1234` or the retired Ollama `100.100.1.7:8080`.
- The assistant can **restyle the site live per client** (accent/background via
  `theme.py`) and attach per-client CSS/HTML/JS blocks (via `blocks.py` + `db.blocks`).

## Data privacy
- `/web/data/` is gitignored (device fingerprints, IPs, chat transcripts).
- Per-device fingerprint: stable `device_id` hash, normalized device name
  (e.g. "Samsung Galaxy S25 Ultra"), IPs, visit timestamps, UA, screen, CPU cores,
  memory, timezone, language, WebRTC local IPs.

---

## Run / restart / deploy
```bash
# restart the site (race-free; frees :8000 first)
/etc/init.d/websiteserver restart
# tail
tail -n 40 /var/log/websiteserver.log
# local check
curl -fsS -m6 http://127.0.0.1:8000/
```
There is no CI — "deploy" == `git commit` + push to GitHub (`frankinkua/cv`) + confirm `/` is 200.

---

## Testing checklist (do before every commit)
```bash
# A. syntax + imports (instant, offline)
/root/.local/bin/uv run --no-sync python -m py_compile main.py webapp/*.py
/root/.local/bin/uv run --no-sync python - <<'PY'
from webapp import db, bot, theme, device
import main
print("ok")
PY

# B. restart + HTTP contract (sleep ~9 after restart)
/etc/init.d/websiteserver restart
sleep 9
for p in / /cv/ /timeline/ /robots.txt; do
  printf "%-12s " "$p"; curl -sS -m6 -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8000$p"
done

# C. public tunnel
curl -fsS -m8 -o /dev/null -w "public %s\n" https://frank-escudero.com/

# D. log-bomb sentinel
echo "log1 = $(stat -c%s /var/lib/tailscale/tailscaled.log1.txt)B"
ps -ef | grep -E 'tailscaled.*no-logs-no-support' | grep -v grep || echo "FIX flags"
```

Red lines (stop, fix, then commit): non-200 on `/`, "Built with Reflex" present,
`:8000` half-bound, log1 growing past a few KB.

---

## Reflections (the things that cost time the first time)

1. **Radix layout props take literals, not CSS values.** `rx.hstack` / `rx.vstack`
   `justify` accepts only `'start' | 'center' | 'end' | 'between'`; `justify="space-between"`
   (and non-existent props) raise `TypeError` at page compile, which crashes the site on
   restart. Use `justify="between"`, or put CSS in `style={...}`.
2. **Reflex can't evaluate Vars in plain Python.** No `x if cond else y` on a Var —
   use `rx.cond(cond, a, b)` inside component props, and never `bool()` a Var.
3. **Never `reflex run` from a shell.** Always use `/etc/init.d/websiteserver restart`.
   Ad-hoc `reflex run` leaks children and half-binds `:8000` (init script's pidfile
   won't match, stale PIDs hold the port). Old stale processes must be `kill`ed by PID.
4. **The 49 GB log bomb, root-caused.** `tailscaled` logtail retried
   `dial 127.0.0.1:8000: connect: connection refused` recursively during a rebuild while
   tailscaled ran without `--no-logs-no-support`. Result: `tailscaled.log1.txt` hit 49 GB,
   disk to 0%, builds failed, tailnet ingress 502. Fixed in `start-rdp-server.sh` via
   `--no-logs-no-support` + `2>/dev/null`; log1 now sits at 0 B.
5. **No internet for pip.** Host has no outbound for `pip install`. If a dependency is
   missing, it must be vendored or already vendored under the venv.
6. **olla proxy = the single model endpoint.** Everything (chat, greeting, opencode)
   goes through `http://100.100.1.10:40114/olla/proxy/v1`. Backends (LM Studio `:1234`,
   Ollama hub on `.7:8080`) are retired — do not build on them.
7. **Multiple system messages break the olla engine.** `bot.chat()` dedupes system
   messages (injects its own system prompt only if none is present); the engine rejects
   `System message must be at the beginning`.
8. **Trailing slashes save a hop.** Reflex redirects `/cv` -> `/cv/`. Test with the
   trailing slash so your "200s" are real 200s, not redirect-chasing.
9. **SSR is not the whole story.** `on_load`-populated state (greeting, probe-triggered
   content, blocks) is absent from `curl`'d HTML; verify such features against the running
   app (chat call, DB rows) or the compiled client bundle.
10. **Cloudflare Tunnel is the public ingress.** The tailnet only serves as the
    private network layer; `frank-escudero.com` is the one public domain.