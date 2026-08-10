# TODO — cv.story-tegu.ts.net (Frank Escudero CV)

## Status (2026-08-05, ~13:10 UTC)
- Build: ✅ green (compiles clean, no deprecation warnings)
- Funnel: ✅ `https://cv.story-tegu.ts.net` → 200 (tailnet `cv` @ 100.115.209.119)
- WIP banner count: ✅ exactly 1 on `/`
- Footer version present: ✅ `v{VERSION_LABEL}` with git SHA
- Routes: ✅ 5 public pages + `/appointments` (302 → Google Calendar booking) + auth (`/login` `/signup` `/profile`) + `/admin` + `/rss` + `/sitemap.xml` + `/robots.txt` all 200
- Bloat: ✅ 10 routes removed (`/deploy /stack /timeline /about-fun /contribute /architecture /resources /changelog /status /worker-log` → 404)
- Admin: ✅ bootstrap user `frank@inkua.eu` (one-time password in `/web/data/.admin-bootstrap`, mode 600)
- Analytics store: ✅ `/web/data/` (users/sessions/visits/conversations JSON, gitignored, single-process + lock-safe)
- Log sentinel: ✅ `tailscaled.log1.txt` = 0 B, `--no-logs-no-support` flag present
- Worker: ⛔ intentionally OFF (do not enable)

## Shipped this session (2026-08-05)
- [x] **Page de-bloat**: kept only `/` `/about` `/cv` `/projects` `/contact` public; removed 10 routes + nav links; `/status` + `/worker-log` content folded into the admin dashboard. Updated sitemap, RSS (removed dead-page links), footer (gated `admin` link).
- [x] **`/appointments`**: short URL that 302-redirects to Frank's Google Calendar booking page (`APPOINTMENTS_URL`); linked from the home nav ("Appointments") and `contact.md`; added to sitemap.
- [x] **Auth**: JSON-file account store (`/web/site_store.py`) with pbkdf2-sha256 password hashing; opaque 30-day session tokens in a `cv_sess` cookie; `_restore_session()` re-verifies the token on every page load (never trusts the client).
- [x] **Sign-in for updates**: `/login`, `/signup` (auto-login), `/profile` (shows account + updates:on + sign out); small profile dropdown menu (`auth_menu`) on every page — "Sign in / Sign up" links when anonymous, "Hi <name>" menu with Profile / Admin dashboard / Sign out when logged in.
- [x] **Analytics**: every page load logs a visit (path, IP, geo, language, referrer) to `visits.json`; geo is cached in-memory and enriched in the background (never blocks page load); admin's own views are excluded.
- [x] **Conversation transcripts**: greeting + every user/assistant exchange logged per session to `conversations.json` (full chats to review).
- [x] **Admin dashboard** (`/admin`): visit/visitor/conversation/message stat cards, visitor-location counts, per-page counts, recent visits list, full conversation review, server-log tail, uptime + worker-run summary. Content is only fetched server-side after an admin token check — anonymous SSR shows "restricted" and no sensitive data.

- [x] **ntfy.sh notifications**: key events push to topic `franke2032` (owner's phone) via `/web/notify.py` (async fire-and-forget, never raises) — site startup (lifespan task), new visitor conversation, first chat message per conversation (deduped via `_NOTIFIED_CONVS`), new signup, admin login, AI/greeting failures. `/etc/init.d/websiteserver` curls a "site DOWN" alert on start failure. Disable with `NTFY_ENABLED=0`, retarget with `NTFY_URL`.
- [x] **Removed the "Search the site" box** on `/` (UI element + `search_panel`, `do_search`, `search_results`/`searched` state, `search_docs`/`SEARCH_DOCS`); chat is the discovery path now. Admin credentials pushed to ntfy `franke2032` on request (also in `/web/data/.admin-bootstrap`).
- [x] **Full visitor data in notifications**: the **new-visitor** ping includes the complete fingerprint (IP, geo country/region/city/lat-lon/timezone, language/locale, platform/device, local time, weather incl. pressure/humidity/wind/precip/warnings, sun/moon) via `_visitor_notify_text`; the **visitor-message** ping was trimmed to just location + IP + question (per Frank) to identify the conversation.
- [x] **Assistant is an eager booking agent**: bot proactively offers to set up an appointment and sends `[book a slot](/appointments)` in chat (greeting + system prompt). Never mentions the domain/URL anymore — all visible `cv.story-tegu.ts.net` references removed from the visitor pages (bot prompt, knowledge.md, cv.md, projects.md, contact.md); only non-visible `og:url` meta remains.
  - Tuned (Frank): booking is now **not** aggressive — the bot only suggests a call *after* it knows who the visitor is and only when relevant (recruiter/hiring manager/client); no booking offer in the greeting, none for casual visitors, never repeated after a decline.

## Remaining open
### Next (feasible in this LXC)
- ~~Add GitHub repo links to `/projects/`~~ — **cancelled (2026-08-05):** `github.com/frankinkua` has 0 public repos, so there is nothing to link. `/projects/` stays description-only until Frank publishes repos.
- Reset admin password via `/web/data/users.json` or a re-bootstrap if the one-time password is lost.
- Optional: paginate conversations / add a "location" map view on `/admin`.

### Deferred — do NOT attempt without host access / Frank's go-ahead
- Re-enable the AI employee (`opencode-worker`) — **OFF by design** (AGENTS.md). Do not enable.
- Wire NVIDIA GPU passthrough — **host-side task** (this LXC has no `/dev/nvidia*`). Do not touch.
- Dark/light theme toggle — hardcoded hex palette across ~40 component props; a full refactor to CSS vars is risky on a live site. Needs careful design first.
- `/sponsors/` or `/donations/` page — only if community support is actually desired.

## Bug fixes (all verified)
- [x] Trailing-slash navigation: `/cv` → 307 → `/cv/` → 200, as designed.
- [x] `main.py` compiles under Python 3.13 with no deprecation warnings.
- [x] Reflex gotchas hit + worked around: no `rx.EventSpec` (drop return annotations on handlers), computed vars need `@rx.var` not `@property`, no `or`/`.get()` on Var proxies (precompute in store), no nested `foreach` over `dict[str, object]` (flatten rows in store).

### Done this session (2026-08-10)
- [x] **Cloudflare Tunnel**: `frank-escudero.com` + `www.frank-escudero.com` → `https://frank-escudero.com/` (Cloudflare Zero Trust tunnel, token-based)
- [x] **Redirect old domain**: `cv.story-tegu.ts.net/*` → `frank-escudero.com/*` (301 permanent, preserves path + query) via Starlette middleware + JS fallback
- [x] **Social metadata**: Updated OpenGraph + Twitter Card tags with new domain, `summary_large_image`, `og:image` + `twitter:image` pointing to `/media/frank.png`
- [x] **Image copy**: `cv-image-frank-with-his-horse.png` → `/web/media/frank.png` (served via existing `/media/frank.png` route)

### Future — Rabbit Holes (DO NOT START without explicit go-ahead)
- **Dynamic OG image via ComfyUI img2img**: Generate time/culture/weather/relationship-adapted variants of `frank.png` on request. Requires ComfyUI API, prompt templates, caching layer.
- **Audio greetings**: Generate WhatsApp-style voice notes (TTS or local model) per visitor context. Play button on home page.
- **Audio input**: Visitor voice messages → STT → chat pipeline.
- **Visitor-aware personalization**: Use geo/IP/timezone/weather from analytics to customize image/audio/content.
