# AGENTS.md — operating rules for agents working in this CV site (`/web`)

> Canonical ops runbook: **`/web/README.md`**. This file = Reflex *dev rules + test harness* only.

## ⚠️ Hard constraints (do not violate)
- **Edit the app, NEVER the framework.** Everything you change lives in `/web`.
  Do NOT touch the Reflex framework files in the venv
  (`site-packages/reflex/**`, `site-packages/reflex_base/**`,
  `site-packages/reflex_components_*/**`, etc.). This box has **no internet for `pip install`**,
  so a "framework edit" is really an API misuse — work around it in the app layer, or stop.
- **One task, idempotent.** The app boots via
  `/root/.bashrc` -> `/usr/local/bin/start-rdp-server.sh` ->
  `/etc/init.d/websiteserver start`. Make every change safe to re-run.
- **Do not touch git history destructively.** Prefer additive edits; never rewrite
  commits already pushed to this LXC (it is the only "remote").

## Reality check (what this actually is right now)
- Site: **`https://cv.story-tegu.ts.net`** (Tailscale Funnel `/` -> `127.0.0.1:8000`).
- Stack: Reflex 0.9.7, Python 3.13, `uv`, `--env prod`, `backend_port=8000`, `frontend_port=8000`.
- Host: systemd-less Debian 13 LXC (`cv`), PID 1 = `bash`; **boot = `/root/.bashrc`**.
- Chat + cron worker both use **LM Studio** on frank's LAN: `CHAT_URL="http://192.168.178.120:1234/v1"`, `CHAT_MODEL="prism-ml/bonsai-27b"` (a reasoning model, 256k ctx, loaded in the box's VRAM). This is a remote endpoint — do not rewrite it to local ollama, and never touch `/dev/nvidia*` here (no GPU passthrough in this LXC).
- Release target is **2026-08-05 16:00 UTC** (a fixed deployment date). The client-side countdown that displayed it was **removed** (the banner is now text-only) — do not resurrect it as a "server time" widget.
- "work in progress" text appears **exactly once** on `/` (the banner). That is an invariant.

## Reflex dev rules (the ones that save time)
- Edit only: `/web/main.py`, `/web/rxconfig.py`, `/web/app/` (page components), and
  markdown under `/web/` that `read_doc()` opens (`about.md`, `cv.md`, `deploy.md`, `stack.md`, `timeline.md`).
- Never edit the venv. Use `/web/.venv/bin/python`, `/web/.venv/bin/reflex` if needed (rare).
- `rxconfig.py`: `show_built_with_reflex=False`, `telemetry_enabled=False`, `disable_plugins=[SitemapPlugin]`,
  `backend_port=8000`. If the "Built with Reflex" badge reappears, this line was reverted — fix here, not in the DOM.
- Pages via `app.add_page(fn, route=..., title=...)`. Use `rx.link` for nav. **Trailing slashes matter:** Reflex redirects `/x` -> `/x/`, so a nav link to `/cv` (no slash) costs you an extra 200 hop in tests. Use `/cv/`.
- Styling via `rx.*` primitives + `class_name:`; do not inject arbitrary Tailwind classes (Reflex 0.9.7 props, not Tailwind).
- Components: every page fn returns `rx.Component`. Reuse `page_footer()`; if you add a route, add it to the footer nav so the link count stays consistent.
- Static assets: **no writes to `/web/assets`**. Favicon is an inline SVG data-URI in
  `rx.App(head_components=[rx.el.link(rel="icon", href=<data-uri>)])`.
- `<title>` + `<meta description>` live in `head_components`/`rx.App`. Do not duplicate per page unless the title genuinely differs.
- `rx.Html(...)` content is SSR-rendered *and* client-rendered. If a snippet needs the browser, wrap it in `if (typeof document !== 'undefined')` (see the theme script pattern already in `index()`).
- Chat: `filter_draft(question, draft)` rejects a draft ONLY on clear safety/security leaks (see `/web/filter.md`). Grounded on-topic answers pass by default.

## How to test (do this before every commit)
### A. Syntax + import (instant, offline)
```bash
cd /web
/web/.venv/bin/python -m py_compile main.py site_store.py rxconfig.py    # all page comps live in main.py; there is NO app/ package
/web/.venv/bin/python - <<'PY'                                           # imports OK? (bootstraps admin on first run)
import main; print("routes:", sorted(r.path for r in main.app._api.routes if hasattr(r,"path")))
PY
```
### B. Restart + HTTP contract (after `/etc/init.d/websiteserver restart`, sleep 9)
```bash
curl -fsS -m6 http://127.0.0.1:8000/ -o /tmp/h
python3 - <<'PY'
import re; h=open("/tmp/h").read()
assert "Agentic Generated Self-Hosted AI Webserver" in h, "big title missing"
assert h.lower().count("work in progress") == 1, "WIP text duplicated (case-insensitive)"
assert re.search(r"v0\.1\.0 \([a-f0-9]{7}\)", h), "footer version missing/odd"
assert "Built with Reflex" not in h, "reflex badge leaked"
assert "Sign in" in h and "Sign up" in h, "auth menu missing on home"
print("contract OK: countdown absent =", "Deployment in" not in h)
PY
echo "/ -> $(curl -sS -m6 -o /dev/null -w %{http_code} http://127.0.0.1:8000/)"
for r in /about/ /cv/ /projects/ /contact/ /login/ /signup/ /profile/ /admin/; do
  printf "%-9s " "$r"; curl -sS -m5 -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8000$r"
done
# admin SSR must NOT leak data to anonymous curl
curl -fsS -m6 http://127.0.0.1:8000/admin/ | grep -q "This area is restricted to the admin." \
  && echo "admin SSR safe" || echo "ADMIN SSR LEAK - fix before commit"
```
### C. Tailscale funnel (external) — check after B passes
```bash
tailscale serve status              # Funnel `/` -> http://127.0.0.1:8000  must be listed
curl -fsS -m8 -o /dev/null -w "%{http_code}\n" https://cv.story-tegu.ts.net/
```
### D. Log-bomb sentinel (must stay near 0)
```bash
echo "log1 = $(stat -c%s /var/lib/tailscale/tailscaled.log1.txt)B"
ps -ef | grep -E 'tailscaled.*no-logs-no-support' | grep -v grep || echo "FIX: tailscaled lost its no-log flag"
```
**Red lines:** a non-200 on `/`, `work in progress` count != 1, footer reading `vv…`, `Built with Reflex` present, or log1 growing past a few KB — stop and fix before committing.

## Restart flow (no systemd)
```bash
/etc/init.d/websiteserver restart   # race-free: kills pgid + reflex/uv children, waits for :8000 free
```
Never `reflex run` from a shell — that leaks children and leaves `:8000` half-bound, which is exactly what triggers the tailscaled log bomb (see below).

## Greeting/chat debugging (time-saver #2)
- The `web` logger has its own INFO StreamHandler (top of `main.py`); without it Reflex
  suppresses INFO and you'll see nothing in `/var/log/websiteserver.log`. Grep for `greeting:`
  / `chat backend` to trace the pipeline (raw browser JSON -> ip -> geo -> lang -> weather ->
  chunks).
- Funnel visitors on the tailnet resolve to a CGNAT `100.x` IP that ip-api.com can't geolocate
  (`geo={}`) — that is expected, the greeting degrades gracefully. Do not "fix" it.
- Never put the raw timezone string in a prompt handed to the LLM — the model repeats it as a
  location ("Europe/Berlin" -> "you are in Berlin"). Pass only the resolved local time-of-day.
- Windows browsers can't render flag emoji; when `platform` contains `Win`, the greeting omits
  the flag and names the country/language in plain text instead. ONLY the flag emoji is blocked
  on Windows — weather/sun/moon emoji must still be used there.
- The visitor's collected data (geo, language, locale, time, weather incl. pressure/warnings,
  sun/moon times) lives in `State.visitor_context` and is re-injected into EVERY chat request
  via `_system_message(ctx)`. Keep the raw timezone string OUT of any LLM prompt — pass only
  the resolved local time/time-of-day.

## The log-bomb lesson (time-saver #1)
- Symptom: `/var/lib/tailscale/tailscaled.log1.txt` swelled to 49 GB; disk fell to 0% free; Reflex restarts failed to bind `:8000`; Funnel returned 502.
- Root cause: `tailscaled` logtail retried `dial 127.0.0.1:8000: connect: connection refused` recursively during a rebuild, while `tailscaled` was started **without** `--no-logs-no-support`.
- Fix (applied in `/usr/local/bin/start-rdp-server.sh`): `tailscaled --no-logs-no-support ... 2>/dev/null`.
- Agent rule: if `ps -ef | grep tailscaled` does NOT show `--no-logs-no-support`, the start script was reverted or tailscaled was restarted by hand without the flag — re-apply the flag before doing anything else. log1 must stay ≈0 B.

## Boot survival (so you don't break it)
- `/root/.bashrc` -> `start-rdp-server.sh` brings up sshd -> dbus -> xrdp+Plasma -> tailscaled -> ollama-as-frank -> websiteserver.
- Worker (`/etc/init.d/opencode-worker`) and cron are OFF by design. Do not enable either.
- On reboot, Funnel + `/` → 200 all recover automatically. After any reboot: `curl https://cv.story-tegu.ts.net/` must be 200 within ~12s; if `:8000` won't bind, run `lsof -iTCP:8000 -sTCP:LISTEN` and restart websiteserver.
