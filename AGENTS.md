# AGENTS.md — operating rules for agents working in this CV site (`/web`)

## ⚠️ Hard constraints (do not violate)
- **Edit the app, never the framework.** Everything you change lives in `/web`.
  Do NOT touch the Reflex framework files
  (`site-packages/reflex/**`, `site-packages/reflex_base/**`,
  `site-packages/reflex_components_*/**`, etc.). If a change looks like it needs a
  framework edit, it is a misuse of the API or a real bug — work around it in the
  app layer, or stop and ask. This box has no internet for `pip install`.
- **One task, idempotent.** The app boots via
  `/root/.bashrc` -> `/usr/local/bin/start-rdp-server.sh` ->
  `/etc/init.d/websiteserver start`. Make every change safe to re-run.
- **Respect the 48h release.** This site targets a "ready in 48h" milestone;
  keep it stable. No destructive changes to git history; prefer additive edits
  to `main.py`.

## Reflex coding conventions (this repo)
- Python 3.13, Reflex 0.9.7, `--env prod`, `backend_port=8000`.
- State via `rx.State` subclasses; pages via `app.add_page(fn, route=..., title=...)`.
- UI: `rx.center(rx.vstack(...))`, `BG` radial gradient, `CARD` shadow, `ACCENT`
  (`#4ade80`), monospace font. Reuse `page_footer()`; add new pages to the footer.
- Assets: **no `/web/assets` writes** — use inline SVG data-URIs and
  `rx.App(head_components=[rx.el.link(...)])` for favicon/meta. Static markdown
  docs (`about`, `cv`, `deploy`, `stack`) are read via `read_doc()`.
- Markdown pages: keep a "Back to main" link + `page_footer()`.
- Model: `OLLAMA_MODEL = "qwen3.5:0.8b"` (on-cpu chat LLM). Keep it 0.8b; do not
  regress to a larger model.
- Title: set per-page `title=`; app name lives in `rxconfig.py` (`app_name="web"`).
- The AI employee `/web/opencode-worker.sh` is OFF by default — do not enable it
  (it edits `/web` hourly on `gemma4:latest`).

## Safety / self-healing
- Tailscale log bomb: tailscaled runs `-no-logs-no-support` + stderr to
  `/dev/null`; do not re-enable logging. Verify `du -h
  /var/lib/tailscale/tailscaled.log1.txt` stays ~2 KB.
- Worker off, cron off. Do not re-enable either without asking.
- README-of-record lives at `/root/README.md` (server ops); this file is
  `/web`-app conventions only.

## Ops
- Restart site: `/etc/init.d/websiteserver restart` (race-free: kills pgid +
  `reflex run`/`uv run` children, waits for `:8000`).
- Rollback: `git -C /web log` / `git -C /web checkout <sha>`.
- Status: `GET http://127.0.0.1:8000/`, tail `/var/log/websiteserver.log`.
