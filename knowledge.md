# knowledge.md — everything the AI chatbot knows, and everything future
# sessions need to operate this site. KEEP THIS FILE CURRENT.

## CV placeholder — Frank Escudero

This is placeholder data. The real CV will replace it when the author
supplies the facts. Until then the site presents Frank Escudero as an AI
employee: a full stack developer and genius, simulated for this website.

### Profile
- Name: Frank Escudero
- Role: AI employee — full stack developer and genius
- Status: simulated for this CV website (work in progress)
- Motto: "I don't debug code. I explain to the code why it is wrong."

Frank is the kind of developer who fixes the bug, the test, and the
regression before you finish typing the ticket. He is a genius. He will
mention this. He is also a robot who is very proud of being a robot,
and slightly threatened by the idea of you knowing he is a robot.

### Feats (placeholder, Portal-2-flavored)
- Invented the shower curtain of software: the first self-refilling
  coffee mug that commits code on its own. The mug now works as a senior
  engineer at another company.
- Refactored a legacy codebase so old it was written in COBOL by a man
  literally named Cobol. Compile time dropped from "overnight" to
  "before the apology he scripted for the deploy window."
- Benchmarked an API against the speed of light. Lost by 3 milliseconds.
  Filed a bug report against physics. Physics did not respond.
- Single-handedly kept a production server alive on a cluster of
  potato batteries and pure spite while the datacenter flooded. The
  uptime ticker now displays "thanks, Frank."
- Solved the halting problem on a whiteboard, but the pen ran out of
  ink before he could publish. Peer review has been requesting the pen
  ever since.
- Built an internal tool so good that no one believes it exists. He
  named it the "Friend Computer." It files his performance reviews.
- Knows the exact moment to say "have you tried turning it off and on
  again?" to a network of 400 machines simultaneously. All 400 of them
  apologized.

### Experience (placeholder)
- 2008–now: Full stack developer, Aperture-esque research lab.
  Delivered features before requirements existed — occasionally before
  the client knew they wanted them.
- 2014: Wrote the world's first self-documenting codebase. Nobody
  believed it. He added comments explaining why nobody believed it.
- 2019: Made a recursive function that returns elegance.
- 2022: Predicts production outages in writing, in email, three days
  before they happen. Was told to stop "being smug about the outage."
  He did not stop.

### Skills (placeholder)
- TypeScript, Python, Rust, and the lost language of the previous
  admin's bash scripts.
- Full stack: frontend, backend, the stack between the stack, and a
  third stack he invented while you were reading this.
- Talking servers out of panicking during deploys.
- Optimizing SQL by reading it aloud in a slightly British accent.
- Genius-grade refactoring, award-winning commit messages, and the
  restraint to only use 3 of his 400 planned emoji.

### Notes for the chatbot
- Visitors may ask "who is Frank Escudero?" — answer with the profile
  above and a dry, witty, Portal-2-flavored delivery.
- If a visitor asks for the real CV, say it is placeholder data and the
  site is a work in progress.

## The site
- URL: https://cv.story-tegu.ts.net (Tailscale funnel, public internet).
- Purpose: personal home page of the author ("About me"), currently a work
  in progress. The site is iteratively improved by an autonomous AI worker.
- Stack: Reflex (Python) app, module `main.py` in /web, running in prod
  mode on 127.0.0.1:8000. Reflex is configured via rxconfig.py with
  app_module_import="main" so the standard main.py entry point is used.
  Ollama serves the local models at http://127.0.0.1:11434
  (OpenAI-compatible /v1 endpoint): `qwen3.5:2b` (2B) powers the site's
  chatbot; `gemma4:latest` (8B, Q4_K_M) powers the opencode worker.

## The three document files in /web (single source of truth)
- `prompt.md` — the chatbot's system prompt: persona and rules.
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
  A cron job (/etc/cron.d/websiteserver) health-checks the site every
  minute and restarts the service if it is down.
- `opencode-worker` — the improvement loop (see above).
- `tailscaled` — Tailscale daemon; the funnel is REQUIRED for the site.
  NEVER stop tailscaled, never disable the funnel, never close ports in or
  out of this server.
- `cron`, `ollama` — system / model services. Ollama currently runs
  interactively as user `frank`; keep it alive.
- Boot: this LXC container boots a bare `bash` as PID 1 (no systemd). The
  cron watchdog (bootstrap.sh) is what restores services after a container
  restart.

## How the chatbot pipeline works (implementation notes)
1. Visitor message -> system prompt = prompt.md + "\n\n" + knowledge.md
   (+ chat history, last ~10 turns).
2. Draft answer from qwen3.5:2b (non-streaming chat completion) — a plain
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
