# TODO — cv.story-tegu.ts.net (Frank Escudero CV)

## Status (2026-08-05, ~07:40 UTC)
- Build: ✅ green (compiles clean, no deprecation warnings)
- Funnel: ✅ `https://cv.story-tegu.ts.net` → 200 (tailnet `cv` @ 100.115.209.119)
- WIP banner count: ✅ exactly 1 on `/`
- Footer version present: ✅ `v{VERSION_LABEL}` with git SHA
- Routes: ✅ 15 pages + `/rss` all 200
- Log sentinel: ✅ `tailscaled.log1.txt` = 0 B, `--no-logs-no-support` flag present
- Worker: ⛔ intentionally OFF (do not enable)

## Shipped this session (2026-08-05)
- [x] Enriched visitor context (pressure/humidity/wind/precip/warnings) injected into EVERY chat request via `_system_message`; Windows keeps all emoji except flags (`6282c49`, `a52ded4`)
- [x] `/contact/` + `/projects/` pages (`3332e6e`, `2bb5827`)
- [x] `/status/` page (version, uptime, worker runs) (`9e5c6ed`)
- [x] `/changelog/` page auto-generated from git (`271898c`)
- [x] Full-text search box over all markdown on `/` (`2024dc6`)
- [x] `/rss` feed (live git changelog, application/rss+xml) (`e47f106`)
- [x] Social links: LinkedIn `frankeee`, GitHub `frankinkua` (nav, contact, cv, knowledge) (`a2be539`)
- [x] `/about-fun/` (verified fun-facts data) (`ff9f018`)
- [x] `/contribute/` (`34fd814`)
- [x] `/architecture/` (boot chain + ASCII diagrams) (`dcfbfd5`)
- [x] `/resources/` (`a2be26a`)
- [x] Expanded `cv.md` (education, projects, languages, awards) (`6b4e005`)
- [x] README learnings 14–15 (`a52ded4`)
- [x] Todo bug-fix items verified (trailing slash, `/worker-log` empty state, no deprecation warnings)

## Remaining open
### Next (feasible in this LXC, do not require host work)
- [x] Live-ticking uptime counter on `/status/` (client-side JS, `uptime_ticker_js`, ticks `#cd-uptime` every second).
- [x] `/sitemap.xml` (Starlette route, lists all 15 public pages).
- Enrich `/rss` with `/about/` + `/cv/` content as originally specified (currently only the git changelog).
- Add GitHub repo links to `/projects/` (currently descriptions only; needs Frank's repo URLs).

### Deferred — do NOT attempt without host access / Frank's go-ahead
- Re-enable the AI employee (`opencode-worker`) — **OFF by design** (AGENTS.md). Do not enable.
- Wire NVIDIA GPU passthrough — **host-side task** (this LXC has no `/dev/nvidia*`). Do not touch.
- Dark/light theme toggle — hardcoded hex palette across ~40 component props; a full refactor to CSS vars is risky on a live site. Needs careful design first.
- `/sponsors/` or `/donations/` page — only if community support is actually desired.

## Bug fixes (all verified)
- [x] Trailing-slash navigation: `/cv` → 307 → `/cv/` → 200, as designed.
- [x] `/worker-log` renders "No worker runs logged yet." cleanly after fresh start.
- [x] `main.py` compiles under Python 3.13 with no deprecation warnings.
