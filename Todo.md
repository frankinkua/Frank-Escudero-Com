# TODO — cv.story-tegu.ts.net (Frank Escudero CV)

## Status
- Build: ✅ green
- Funnel: ✅ `https://cv.story-tegu.ts.net` → 200
- WIP banner count: ✅ exactly 1 on `/`
- Footer version present: ✅ `v{VERSION_LABEL}` with git SHA

---

### Next (toward the 48h launch mark)
- Re-enable the AI employee (`opencode-worker`) to keep regenerating content from GitHub issues / opencode sessions.
- Wire NVIDIA GPU passthrough so Ollama can run models on GPU for faster, richer chat completions.
- Add a `/contact/` page (email / tailnet handle) and `/projects/` page with detailed project descriptions and repos. (both shipped 2026-08-05; `/projects/` has descriptions, repos TBD)
- Expand `cv.md` with sections: Education, Projects, Languages, Certifications, GitHub links. (done 2026-08-05)
- Add a `/about-fun/` or `/blog/` page for informal posts, learnings, and "day in the life" entries.
- Implement search across all markdown pages (e.g., via a simple full-text index).

### Nice-to-have
- Add a dark/light theme toggle using CSS variables + `rx.cond`.
- Add RSS feed (`application/rss+xml`) from `/about/` + `/cv/` content for a blog-like presence.
- Add a `/status/` page mirroring the worker-log summary, with a live uptime counter since last boot. (done 2026-08-05)

### Nice-to-have (later)
- Add a "contribution guide" — how to suggest changes via email or tailnet DM.
- Add a `/resources/` page: tools I use daily, reading list, open-source contributions.
- Add social / profile links section on the footer nav (`github.com/franke2032`, `twitter/...`, etc.).

### Nice-to-have (even later)
- Add a "changelog" that auto-generates from `git log --oneline` and appends to `/web/changelog.md`. (done 2026-08-05 — served live from git at `/changelog/`)
- Add an "about the site's tech stack in depth" page with architecture diagrams (ASCII art).
- Add a /sponsors/ or /donations/ page if community support is desired.

---

### Bug fixes (prioritized)
- [x] Verify trailing-slash navigation on all 6 pages doesn't cause extra redirects in analytics / metrics. (307 → 200 for `/cv` → `/cv/`, as designed; all routes verified 200)
- [x] Check that the `/worker-log` page renders correctly after a fresh start and no worker has run yet. ("No worker runs logged yet." renders cleanly)
- [x] Ensure `main.py` compiles under Python 3.13 without deprecation warnings (check imports, type hints). (`-W error::DeprecationWarning` import passes clean)