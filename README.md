# Frank Escudero — virtual-employee CV site

A zero-trust, self-hosted, AI-updated personal site on a systemd-less Debian 13 LXC behind a Tailscale Funnel.

- URL: https://cv.story-tegu.ts.net/
- Local backend: http://127.0.0.1:8000
- Owner/ops notes (human): `/root/README.md`

---

## Architecture (how it boots & stays up)

```
Funnel  https://cv.story-tegu.ts.net  /  ->  http://127.0.0.1:8000  (TailScale Funnel)
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
            5) ollama serve  (user: frank)
            6) /etc/init.d/websiteserver start
                  -> uv run --project /web reflex run --env prod --backend-port 8000
                     pidfile /run/websiteserver.pid, log /var/log/websiteserver.log
```

- Worker (`/etc/init.d/opencode-worker`) and cron are OFF.
- Reboot recovers: Funnel `/` -> 200 + live countdown within ~12s. If `:8000` won't bind: `lsof -iTCP:8000 -sTCP:LISTEN` then `websiteserver restart`.

---

## Files we own (in `/web`)
- `main.py` — app: routes, countdown, chat, `page_footer()`, `app_version()`.
- `rxconfig.py` — `show_built_with_reflex=False`, `telemetry_enabled=False`, `disable_plugins=[SitemapPlugin]`, `backend_port=frontend_port=8000`.
- `AGENTS.md` — Reflex dev rules + the test checklist (agents should read this first).
- `app/` — page components (`index`, `about`, `cv`, `deploy`, `stack`, `timeline`, `chat`).
- `about.md`, `cv.md`, `deploy.md`, `stack.md`, `timeline.md` — markdown read via `read_doc()`.
- `filter.md` — chat safety gate rules (briefed below).
- `.venv/` — managed by `uv` (do not edit).
- `requirements*` — pinned by `uv` (no internet on host).

Ops (ref-only, outside `/web`): `/etc/init.d/websiteserver`, `/usr/local/bin/start-rdp-server.sh`, `/root/.bashrc`.

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
Commit to git at `/web` is optional; the app auto-loads new source on file change. There is no CI — "deploy" == `git commit` (if you want history) + confirm `/` is 200.

---

## Testing checklist (do before every commit)
```bash
# A. syntax + imports (instant, offline)
/web/.venv/bin/python -m py_compile main.py rxconfig.py               # all page comps live in main.py (no app/ package)
/web/.venv/bin/python - <<'PY'
import main
print("ok, routes known")
PY

# B. restart + HTTP contract (sleep 9 after restart)
/etc/init.d/websiteserver restart
sleep 9
curl -fsS -m6 http://127.0.0.1:8000/ -o /tmp/h
python3 - <<'PY'
import re
h = open("/tmp/h").read()
assert "Agentic Generated Self-Hosted AI Webserver" in h      # big title, once
assert h.lower().count("work in progress") == 1                # WIP banner only (case-insensitive)
assert re.search(r"v0\.1\.0 \([a-f0-9]{7}\)", h)              # footer version
assert "Built with Reflex" not in h                          # badge removed
print("contract OK:", re.findall(r"Deployment in \d\d:\d\d:\d\d", h)[0])
PY
for r in / /about/ /cv/ /deploy/ /stack/ /timeline/; do
  printf "%-9s " "$r"; curl -sS -m5 -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8000$r"
done

# C. public funnel
curl -fsS -m8 -o /dev/null -w "funnel %s\n" https://cv.story-tegu.ts.net/
tailscale serve status                                       # `/` -> 127.0.0.1:8000

# D. log-bomb sentinel
echo "log1 = $(stat -c%s /var/lib/tailscale/tailscaled.log1.txt)B"
ps -ef | grep -E 'tailscaled.*no-logs-no-support' | grep -v grep || echo "FIX flags"
```

Red lines (stop, fix, then commit): non-200 on `/`, "work in progress" count != 1, footer reads `vv…`, "Built with Reflex" present, log1 growing past a few KB.

---

## Learnings (the things that cost time the first time)

1. **The countdown is intentionally fixed at 2026-08-05 16:00 UTC.** It is client-side JS seeded from `COUNTDOWN_TARGET` in `main.py`. It is meant to be a hard ship-it date, not a "current server time" widget. Do not "correct" it to match the clock.
2. **"work in progress" must appear exactly once** on `/` — the banner. The big `h1` is the title, the banner is the status, the `<p>` below is the one-line description. Duplicating "work in progress" (e.g., back in the `h1`) regresses the cleanup done in commit `ea0ff58`. The test above enforces it.
3. **Double-`v` footer bug.** `app_version()` returns a string with no leading `v` (e.g. `0.1.0 (29c8ec7)`); `page_footer()` prints `v{VERSION_LABEL}`. If someone changes `app_version()` to include a `v`, the footer reads `vv0.1.0 …`. Keep that contract.
4. **Trailing slashes save a hop.** Reflex redirects `/cv` -> `/cv/`. Test links and curls with the trailing slash so your "200s" are real 200s, not redirect-chasing.
5. **Never `reflex run` from a shell.** Always use `/etc/init.d/websiteserver restart`. Ad-hoc `reflex run` leaks children and half-binds `:8000`, which is the exact condition that triggers the tailscaled log bomb (see 6).
6. **The 49 GB log bomb, root-caused.** `tailscaled` logtail retried `dial 127.0.0.1:8000: connect: connection refused` recursively during a rebuild, while tailscaled was running without `--no-logs-no-support`. Result: `tailscaled.log1.txt` hit 49 GB, disk to 0%, builds failed, Funnel 502. Fixed in `start-rdp-server.sh` via `--no-logs-no-support` + `2>/dev/null`; log1 now sits at 0 B. If `ps -ef | grep tailscaled` lacks that flag, re-apply it immediately.
7. **No internet for pip.** Host has no outbound for `pip install`. If a dependency is missing, it must be vendored or already vendored under the venv.
8. **Chat + worker share one LLM box.** LM Studio on frank's LAN at `http://192.168.178.120:1234/v1`, model `prism-ml/bonsai-27b` (reasoning, 256k ctx) powers both chat and the cron worker; keep it loaded in the box's VRAM. NVIDIA passthrough is a **host-side** task (you own the driver) — agents in this LXC must not touch `/dev/nvidia*`.
9. **Edit the app, not the framework.** Anything that seems to require editing `site-packages/reflex/**` is an API misuse — work around it in `app/` or `main.py`. The box can't `pip install`.

---

## Chat (Ask the site)
- Backend: **remote** LM Studio `http://192.168.178.120:1234/v1`, model `prism-ml/bonsai-27b` (reasoning, kept loaded in VRAM). Same endpoint the cron worker uses.
- SDK: `openai` (`AsyncOpenAI`). Streaming into the assistant message.
- Safety gate: `filter_draft(question, draft)` rejects ONLY on clear safety/security leaks; grounded on-topic answers pass. Rules in `/web/filter.md` (brief: no secrets leaked, no hostile rewrites of the CV).

---

## Footer contract (so the "updated" line is meaningful)
`page_footer()` prints:
```
v0.1.0 (<7-char git SHA>)        updated <UTC date>
```
- `v0.1.0 (29c8ec7)` — version + short SHA of `/web` HEAD.
- `updated 2026-08-04 11:39:51` — time `index()` rendered (UTC). It moves when the app restarts, which is why restarts must be intentional.

---

## Owner / next milestone
- Frank. `2026-08-05 16:00 UTC` — when the countdown hits 0, treat it as shipped.
