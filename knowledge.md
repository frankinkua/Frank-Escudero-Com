## Who Frank Escudero is
- Full-stack engineer / infrastructure developer living on his own home datacenter ("story-tegu.ts.net" tailnet). Speaks English natively (site content is English); the chatbot may greet visitors in their own language but must be able to answer in English too.
- Runs a systemd-less Debian 13 LXC container (hostname `cv`, tailnet IP 100.115.209.119) that serves this CV site to the public internet.
- Frank's work is: Python/Bash (fluent), Go (reading), Terraform/HCL; Reflex, FastAPI, ASGI; Tailscale (Funnel + tailnet), RDP/KDE, git-based rollback, self-hosting, zero-trust ingress, SRE.
- Notable achievements (all real, on this box): booted the headless container from bare `bash` PID 1 with no systemd and brought up sshd, dbus, xrdp+KDE, Tailscale, the LLM, and the Reflex site; published the site publicly over a Tailscale Funnel; killed a 49 GB runaway tailscaled log that had filled the disk; and built this site so it is auto-updated by an autonomous AI agent.
- Public profiles: LinkedIn https://www.linkedin.com/in/frankeee/ , GitHub https://github.com/frankinkua

## The site (what the visitor is looking at)
- URL: https://cv.story-tegu.ts.net — served over a Tailscale Funnel, public internet, zero-trust.
- It IS Frank's delivered CV: no placeholders, no "coming soon". The page is a self-hosted, self-editing web application maintained by Frank and an AI agent.
- Stack: Reflex (Python) app in `/web/main.py`, production mode, listening on 127.0.0.1:8000.
- The AI chatbot on this page is powered by a remote LLM server on Frank's LAN (LM Studio at http://192.168.178.120:1234, OpenAI-compatible /v1 API). The model is `prism-ml/bonsai-27b` (a reasoning model with 256k context, loaded on an 11GB VRAM GPU). The same model powers the opencode agent that improves the site.
- Pages: `/` (home + chat + countdown), `/about` (about Frank), `/cv` (the CV), `/projects`, `/contact`, `/login` (sign in to get updates), `/signup`, `/profile`. The admin gets `/admin` — a private analytics dashboard (visits, visitor locations + counts, full conversation transcripts, server log). All visitor data (analytics + chat transcripts) lives in `/web/data/` (JSON, gitignored); the bootstrap admin is `frank@inkua.eu` with a one-time password in `/web/data/.admin-bootstrap`.
- Notifications: key events push to ntfy.sh topic `franke2032` (owner's phone) — site startup, new visitor conversation, first chat message, new signup, admin login, AI/greeting failures (from `notify.py`, fire-and-forget), plus a "site DOWN" alert from `/etc/init.d/websiteserver` if the server fails to start. Disable via env `NTFY_ENABLED=0`, retarget via `NTFY_URL`.

## The documents in /web (single source of truth)
- `prompt.md` — the chatbot's system prompt (persona + rules).
- `knowledge.md` — THIS file: everything the chatbot may answer from, plus the ops manual for agents.
- `filter.md` — quality rules. Every chatbot answer is checked by a second AI pass; a draft that leaks internal details (model names, file paths, ports, tokens) is replaced with a polite refusal.

## The AI worker loop (how the site gets improved)
- `/web/opencode-worker.sh` is a SINGLE-SHOT runner (start -> run -> close). Each invocation spawns one fresh `opencode run` session against LM Studio `prism-ml/bonsai-27b`, works in `/web`, health-checks the site, commits, prints a `RESULT=` line, and exits. It has a hard TIMEOUT_MINUTES cap (30) and never lingers.
- Scheduling repeats is the caller's job (cron / a wrapper / a terminal); the script itself has no loop and no sleep.
- Rollback safety: one git commit per run; if the site is broken after a run the worker rolls back (`git checkout -- .`) and restarts the website service.
- Config lives in `/web/opencode-worker.conf` (model, URL, prompt, timeouts). The cron watchdog is DISABLED on purpose.

## Services on this machine (hostname: cv)
- `websiteserver` — `/etc/init.d/websiteserver {start|stop|status|restart}`; runs the Reflex app on port 8000. Log: /var/log/websiteserver.log.
- `opencode-worker` — the improvement runner (see above); off by default, started manually.
- `tailscaled` — REQUIRED for the funnel; never stop it or close the funnel.
- No systemd (bare `bash` as PID 1); boot chain: `~/.bashrc -> start-rdp-server.sh` restores sshd, dbus, xrdp, Tailscale, and the site after a container restart.

## How the chatbot pipeline works (implementation notes)
1. Visitor message -> system prompt = prompt.md + "\n\n" + knowledge.md (+ last ~10 chat turns).
2. Draft answer from LM Studio `prism-ml/bonsai-27b` (streaming chat completion), reasoning disabled (`reasoning_effort: "none"`).
3. Filter pass: a second completion checks the draft against filter.md and replies JSON {"pass": bool, "reason": str}.
4. Pass -> draft sent to visitor. Fail -> polite fallback. Failures are logged.
- On first visit the site also sends a personalized greeting: the browser's
  language/platform/timezone + epoch ms (`Date.now()`) plus a public IP
  geolookup are used to greet the visitor in their own language and ask who
  they are. The greeting can include: the visitor's local time of day
  (morning/afternoon/evening/night, from their timezone), current weather
  (open-meteo, no key, via lat/lon from the IP lookup), their city/country,
  local sunrise/sunset times and the current moon phase (open-meteo
  `/v1/forecast` with `daily=sunrise,sunset,moon_phase`), current conditions
  (temperature, feels-like, humidity, precipitation, pressure, wind speed)
  plus a derived weather warning for severe codes (freezing rain, heavy rain,
  thunderstorms/hail), and a country or language flag emoji. Location precision
  is city-level via ip-api.com; a MaxMind GeoLite2 `.mmdb` is NOT installed
  (would need the `geoip2` package + DB file for offline lookups). Windows
  system fonts do NOT render flag emoji (regional-indicator chars show as
  letters), so the greeting must NOT start with a flag emoji when the platform
  is Windows - use the country/device language in plain text instead. ALL other
  emoji (weather, sun, moon, temperature) still work on Windows.
- The collected visitor data is stored on the chat State as `visitor_context`
  and re-injected into EVERY chat request afterwards (via `_system_message`),
  so the assistant keeps personalizing follow-up answers (geo, language, locale,
  time, weather incl. pressure/warnings, sun times), not just the greeting.
- Greeting gotchas (learned the hard way):
  - Behind the Tailscale Funnel the socket IP is `127.0.0.1`, and a visitor on
    the tailnet shows up as a CGNAT `100.x` address that ip-api.com cannot
    geolocate (`geo={}`). Only public-IP visitors (e.g. phone on LTE) resolve to
    a city. The greeting must therefore degrade gracefully when geo is empty.
  - NEVER hand the raw timezone string to the LLM: it repeats it as a location
    (`timezone: Europe/Berlin` -> "you are in Berlin"). Only pass the resolved
    local time-of-day ("their local time is evening"). City/country must come
    exclusively from the IP geolocation.
  - The `web` logger needs its own `StreamHandler(level=INFO)`: Reflex's default
    config suppresses INFO, so `greeting:` diagnostics never reached
    `/var/log/websiteserver.log`. Grep that file for `greeting:` to debug.
  - Language detection: `str(x) for x in (a or b or c)` iterates the STRING
    character-by-character (parens do not make a tuple) - pass the raw string.
  - open-meteo has NO `/v1/astronomy` endpoint (returns 404); sunrise, sunset and
    moon_phase all come from `/v1/forecast` with `daily=sunrise,sunset,moon_phase`.

## Conventions
- `/web` is a git repo; generated dirs (.venv, .web, __pycache__) are gitignored. One commit per meaningful change.
- NEVER use `git clean -fd` here: it deletes untracked config files (rxconfig.py, prompt.md, knowledge.md, filter.md, pyproject.toml). Roll back with `git checkout -- .` only.
- When you (an agent) make changes, update the docs above so the next fresh session inherits the knowledge.
