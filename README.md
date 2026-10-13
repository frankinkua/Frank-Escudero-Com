# Frank Escudero — personal website

A static, locally hosted-asset portfolio for Frank / Ezequiel Escudero. Ivory, cobalt and a real user-supplied portrait; engineering interests, two accessible comparison charts, and a multilingual searchable media catalogue.

## Evidence and media

- `inbox/media/catalog.json` records sources, rights, identity evidence, dates, exact local asset hashes, and numeric comparators.
- Frank confirmed the 40M+ videos, 180M+ images and €9M to <€0.5M annual VoIP cost figures on 11 October 2026. They are owner-reported and not independently audited (recorded as `owner_report` in the catalogue); on 13 October 2026 Frank asked for the public pages to drop the owner-reported label, so the site shows them with their bounds only. Project dates remain unspecified.
- Only the user-selected dog photograph, the owner-approved studio portrait and system metrics telemetry card, and the approved institutional workshop reference are in the public media catalogue.
- Shared canonical tags and bilingual aliases are in `inbox/media/tag-aliases.json`.
- Jules draft research folders are not a source of automatic publication or verified claims.
- Public content follows the owner's current publication choices. Do not restore withdrawn employer, agency, campaign or press associations from older commits or research drafts. New affiliations and related sources require explicit owner approval.

## Local checks

```bash
node --test tests/*.test.cjs
python3 -m http.server 8080 --bind 127.0.0.1
```

The page does not require a build, CDN, account, analytics service or contact-form backend. Test at desktop and 390px mobile widths; test menu/Escape, filters, no results and keyboard focus.

## Deployment

GitHub Pages uses `.github/workflows/pages.yml`. `node scripts/build.cjs` creates a new `_site/` using an explicit allowlist and only approved catalogue images. It refuses to overwrite an existing build. Research drafts and repository metadata are excluded.

The existing `CNAME` is preserved. As checked on 11 October 2026, HTTP works at http://frank-escudero.com/ but the HTTPS certificate does not match the hostname. This pre-existing hosting issue is separate from the site build; do not bypass certificate warnings.

DM Sans and Instrument Serif are bundled under their SIL Open Font Licenses. User-supplied photography is not relicensed by this code repository.
