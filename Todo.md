# TODO — cv.story-tegu.ts.net (Frank Escudero CV)

## Status (2026-08-05, ~13:10 UTC)
- Build: ✅ green (compiles clean, no deprecation warnings)
- Funnel: ✅ `https://cv.story-tegu.ts.net` → 200 (tailnet `cv` @ 100.115.209.119)
- WIP banner count: ✅ exactly 1 on `/`
- Footer version present: ✅ `v{VERSION_LABEL}` with git SHA
- Routes: ✅ 5 public pages + auth (`/login` `/signup` `/profile`) + `/admin` + `/rss` + `/sitemap.xml` + `/robots.txt` all 200
- Bloat: ✅ 10 routes removed (`/deploy /stack /timeline /about-fun /contribute /architecture /resources /changelog /status /worker-log` → 404)
- Admin: ✅ bootstrap user `frank@inkua.eu` (one-time password in `/web/data/.admin-bootstrap`, mode 600)
- Analytics store: ✅ `/web/data/` (users/sessions/visits/conversations JSON, gitignored, single-process + lock-safe)
- Log sentinel: ✅ `tailscaled.log1.txt` = 0 B, `--no-logs-no-support` flag present
- Worker: ⛔ intentionally OFF (do not enable)

## Shipped this session (2026-08-05)
- [x] **Page de-bloat**: kept only `/` `/about` `/cv` `/projects` `/contact` public; removed 10 routes + nav links; `/status` + `/worker-log` content folded into the admin dashboard. Updated sitemap (5 URLs), RSS (removed dead-page links), footer (gated `admin` link).
- [x] **Auth**: JSON-file account store (`/web/site_store.py`) with pbkdf2-sha256 password hashing; opaque 30-day session tokens in a `cv_sess` cookie; `_restore_session()` re-verifies the token on every page load (never trusts the client).
- [x] **Sign-in for updates**: `/login`, `/signup` (auto-login), `/profile` (shows account + updates:on + sign out); small profile dropdown menu (`auth_menu`) on every page — "Sign in / Sign up" links when anonymous, "Hi <name>" menu with Profile / Admin dashboard / Sign out when logged in.
- [x] **Analytics**: every page load logs a visit (path, IP, geo, language, referrer) to `visits.json`; geo is cached in-memory and enriched in the background (never blocks page load); admin's own views are excluded.
- [x] **Conversation transcripts**: greeting + every user/assistant exchange logged per session to `conversations.json` (full chats to review).
- [x] **Admin dashboard** (`/admin`): visit/visitor/conversation/message stat cards, visitor-location counts, per-page counts, recent visits list, full conversation review, server-log tail, uptime + worker-run summary. Content is only fetched server-side after an admin token check — anonymous SSR shows "restricted" and no sensitive data.

- [x] **ntfy.sh notifications**: key events push to topic `franke2032` (owner's phone) via `/web/notify.py` (async fire-and-forget, never raises) — site startup (lifespan task), new visitor conversation, first chat message per conversation (deduped via `_NOTIFIED_CONVS`), new signup, admin login, AI/greeting failures. `/etc/init.d/websiteserver` curls a "site DOWN" alert on start failure. Disable with `NTFY_ENABLED=0`, retarget with `NTFY_URL`.
- [x] **Removed the "Search the site" box** on `/` (UI element + `search_panel`, `do_search`, `search_results`/`searched` state, `search_docs`/`SEARCH_DOCS`); chat is the discovery path now. Admin credentials pushed to ntfy `franke2032` on request (also in `/web/data/.admin-bootstrap`).

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
