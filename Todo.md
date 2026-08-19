# TODO — frank-escudero.com (Frank Escudero CV)

> **Status (2026-08-19): REBUILT.** The site was rebuilt from a ~4k-line
> monolithic `main.py` into a thin entry point + the `webapp/` package,
> drop/auth-admin/appointments/sessions. Everything below marked "archive" is
> the pre-rebuild state, kept for history.

## Current status (2026-08-19, rebuild shipped)
- Public: ✅ `https://frank-escudero.com` → 200 (Cloudflare Tunnel → `127.0.0.1:8000`)
- Old tailnet URL: ✅ legacy URL → 301 → `frank-escudero.com` (not advertised)
- Routes: ✅ `/`, `/cv/`, `/timeline/` + `robots.txt` + `sitemap.xml` all 200
- Stack: ✅ Reflex 0.9.7, thin `main.py` + `webapp/` package; SQLite store `/web/data/site.db`
- Per-client: ✅ device fingerprinting, theme accent, CSS/HTML/JS blocks, aggressive chat
- LLM: ✅ olla proxy `100.100.1.10:40114/olla/proxy/v1`, model `prism-ml/bonsai-27b`
- Log sentinel: ✅ `tailscaled.log1.txt` = 0 B, `--no-logs-no-support` flag present
- Worker: ⛔ intentionally OFF (do not enable); `cron_improve.py` broken-on-purpose (legacy imports)

## Shipped in the rebuild (2026-08-19)
- [x] **Modular package**: `webapp/` = db, device, js, theme, blocks, bot, state, components, timeline.
- [x] **Markdown content**: home rendered from `home.md`, CV from `cv.md`, timeline from `timeline.md` + git log.
- [x] **Per-device fingerprinting**: stable `device_id`, normalized device name, IPs, visits, capabilities → SQLite.
- [x] **Live personalization**: `theme.py` picks accent/gradient per client (GPU/timezone/language/screen).
- [x] **Per-client blocks**: CSS/HTML/JS in the `blocks` table + shared `block_pool`.
- [x] **Aggressive chat**: auto-opens once per session, nudges on idle, greets by learned device; olla proxy backend with deduped system message.
- [x] **Old-domain redirect**: Starlette middleware 301s the legacy tailnet URL → `frank-escudero.com`.

## Archive (pre-rebuild, Aug 2026) — what was removed
- ~~Auth (/login /signup /profile, sessions, pbkdf2)~~ — **dropped in rebuild.**
- ~~Admin dashboard (/admin, analytics, transcripts, live handoff)~~ — **dropped.**
- ~~Appointments (/appointments → Google Calendar)~~ — **dropped.**
- ~~JSON stores (site_store.py: users/sessions/visits/conversations)~~ — **replaced by SQLite.**
- ~~Search box, countdown, RSS, changelog, /status, /worker-log~~ — **removed.**

## Remaining open
- Repoint `cron_improve.py` to the new `webapp`/`db` APIs (it still imports the removed
  `site_store`/`main.get_chat_client`); keep it disabled unless Frank asks.
- Optional: paginate chat history / add an admin view of visitors + messages.
- Re-enable the AI employee (`opencode-worker`) — **OFF by design** (AGENTS.md). Do not enable.
- Wire NVIDIA GPU passthrough — **host-side task** (no `/dev/nvidia*` in this LXC). Do not touch.

### Rabbit Holes (DO NOT START without explicit go-ahead)
- **Audio greetings**: WhatsApp-style voice notes per visitor context.
- **Audio input**: visitor voice → STT → chat pipeline.
- **Dynamic OG image** (ComfyUI img2img variants of `frank.png`).
- **Visitor-aware richer personalization** (geo/weather/photo-driven content variants).