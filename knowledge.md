## The site
- URL: https://cv.story-tegu.ts.net (Tailscale Funnel, public internet).
- Purpose: the authoritative personal homepage of Frank Escudero; continuously improved by an autonomous AI worker loop.
- Stack: Reflex (Python) app, module `main.py` in /web, running in prod mode on 127.0.0.1:8000. Reflex is configured via rxconfig.py with app_module_import="main" so the standard main.py entry point is used. Ollama serves local models at http://127.0.0.1:11434 (OpenAI-compatible /v1 endpoint): qwen3.5:0.8b powers the site's chatbot; gemma4:latest powers the opencode worker.

## The three document files in /web (single source of truth)
- `prompt.md` — the chatbot's system prompt (persona + rules). Kept minimal: Frank as a concise, grounded infra/CV assistant — no self-aggrandizing lore.
- `knowledge.md` — this file: all knowledge the chatbot may use AND the
  operations manual for agents working on the site.
- `filter.md` — quality requirements. Every chatbot answer is run through a
  second AI pass ("the filter") that checks the draft against filter.md and
  only then releases it to the visitor; failing drafts are replaced with a
  polite refusal.

## The AI worker loop (how this site gets improved)
- `/web/opencode-worker.sh` reads `/web/opencode-worker.conf` and loops
  forever: every INTERVAL_MINUTES it spawns a BRAND-NEW `opencode run`
  session (fresh context, so no session can poison the next) with the task
  "Polish and improve the website by any means." and --auto permissions.
- Each run may edit anything in /web. After the run the worker health-checks
  the site; if it is broken the run is SCRAPPED (git rollback to last good
  commit, website service restarted) and a marker file
  `/web/.last_build_failed` (gitignored) is written; the site then shows
  "ai build failed last <timestamp>". Successful runs are committed to git
  with message `opencode-worker run N`.
- Worker lifecycle: `/etc/init.d/opencode-worker {start|stop|status|restart}`.
  The cron watchdog is DISABLED on purpose: it used to resurrect stopped
  workers whose rollback deleted untracked files. Start/stop the worker
  manually; it survives session closes (setsid).
- The opencode binary is /home/frank/.opencode/bin/opencode, run as root.

## Services on this machine (hostname: cv)
- `websiteserver` — `/etc/init.d/websiteserver {start|stop|status|restart}`;
  runs the Reflex app in prod on port 8000. Logs: /var/log/websiteserver.log.
  Supervision is via `pgrep` + the init script; no systemd.
- `opencode-worker` — the improvement loop (see above).
- `tailscaled` — Tailscale daemon; the funnel is REQUIRED for the site.
  NEVER stop tailscaled, never disable the funnel, never close ports in or
  out of this server.
- `cron`, `ollama` — system / model services. Ollama currently runs
  interactively as user `frank`; keep it alive.
- Boot: this LXC container boots a bare `bash` as PID 1 (no systemd). The
  bootstrap runs from `~/.bashrc -> start-rdp-server.sh`, which is what
  restores services after a container restart.

## How the chatbot pipeline works (implementation notes)
1. Visitor message -> system prompt = prompt.md + "\n\n" + knowledge.md
   (+ chat history, last ~10 turns).
2. Draft answer from qwen3.5:0.8b (non-streaming chat completion) — a plain
   prompt with the documents above, NO opencode session, NO tools.
   Reasoning is disabled (`reasoning_effort: "none"`): qwen3.5 thinks by
   default, which burns minutes of CPU for long think-token dumps; the
   "none" effort keeps answers fast on this 23GiB CPU-only box.
3. Filter pass: a second completion asks "does this draft meet the
   requirements in filter.md? Reply JSON {\"pass\": bool, \"reason\": str}".
4. If pass -> draft is sent. If not -> the draft is dropped and the visitor
   gets a short polite fallback. Every filter failure is logged server-side.

## Conventions
- `main.py` is the standard entry point for ALL future applications on this
  machine. New apps keep this name.
- All configuration lives in files next to the code, documented with
  comments, e.g. `/web/opencode-worker.conf`.
- /web is a git repo; generated dirs (.venv, .web, __pycache__) and the
  marker `.last_build_failed` are gitignored. One commit per worker run so
  any change can be rolled back (`git log`, `git checkout`).
- NEVER use `git clean -fd` or `git clean -x` here: it deletes untracked
  config files (rxconfig.py, prompt.md, knowledge.md, filter.md,
  pyproject.toml). Roll back with `git checkout -- .` only.
- When you (an agent) make changes, update the docs above and the site's
  "About me" page so the next fresh session inherits the knowledge.
