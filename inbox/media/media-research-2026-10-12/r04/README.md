# InkuA Project and Community Media Research

## Review Table

| ID | Title | Publisher | Evidence Type | Local Path | Note |
|---|---|---|---|---|---|
| inkua-github-dashboard-pr | Add Inkua GitHub dashboard | GitHub / InkuA | Reference | null | Direct evidence of Frank's IT contributions to InkuA. |

## Useful Findings
The primary public, explicit identity anchor connecting Frank Escudero directly to InkuA workflows found during this session is through the InkuA GitHub organization (`inkua`). Frank created pull requests adding IT dashboard tools to the InkuA workspace.

## Proposed Website Uses
These links can be added to the CV or a "Projects" section as references proving hands-on technical involvement in managing or contributing to the InkuA IT workspace.

## Limitations
Internet search tools (Google, DuckDuckGo) returned heavily restricted results or blocked automated HTTP access entirely. Therefore, the search was pivoted to the GitHub API, focusing on the `inkua` organization which successfully yielded primary sources for the claims. YouTube curl searches without an API key proved unreliable due to lack of inner text matching for the target terms. No local media was downloaded as these are reference links.

## Validation Commands
```bash
jq '.' inbox/media/media-research-2026-10-12/r04/findings.json > /dev/null
jq '.' inbox/media/media-research-2026-10-12/r04/search-log.json > /dev/null
```
