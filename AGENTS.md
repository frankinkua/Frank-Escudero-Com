# Public content boundaries

This is Frank's public portfolio, not an exhaustive career archive.

- Preserve the owner's publication choices. Do not reintroduce withdrawn employer,
  agency, campaign or press associations from older commits, PRs or research.
- The current approved media are the selected personal photograph and the
  institutional workshop reference in `inbox/media/catalog.json`.
- Keep owner-reported career figures and their bounds; do not assign them to a
  company or infer dates or independently audited status.
- Obtain explicit owner approval before adding a new affiliation, campaign,
  award, biographical source or media item to public repository content.
- Draft research is not an exemption: this repository and its PRs are public.
- Frank authorizes downloading media, including copyright or rights-unknown
  images, for private internal review. Keep those binaries only under
  `inbox/media/private/`, which is gitignored. Never include them in a commit,
  PR, public catalogue or website deployment. Keep `local_path` null in public
  records and retain source and rights details. This private-copy authorization
  does not change the public-content approval rules above.
- Run `node --test tests/*.test.cjs` and the approved-file build before publishing.
