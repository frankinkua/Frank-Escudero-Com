# Research Packet: R01 - Asombro Extremo interviews

## Objective
Find new first-party or original publisher interviews explicitly naming Ezequiel/Frank Escudero and explaining his technical/creative role.

## Review Table
| Title | Type | Source | Supported Claim | Confidence | Status |
|-------|------|--------|-----------------|------------|--------|
| Juntaba propinas siendo mago en Plaza Serrano y hoy es reconocido en el mundo | article | LA NACION | Ezequiel Escudero provided a notable technological impulse to their shows | high | Verified |

## Useful Findings
An article from LA NACION (2019) profiling Marcos Amadeo explicitly names Ezequiel Escudero. It describes him as a "technological genius" who gave a "notable technological impulse" to the show, allowing the magicians to perform "true miracles on stage."

**Important Conflict:** This article claims Ezequiel Escudero was met during a 2014 tour in Europe and incorporated as a partner later. This directly conflicts with the timeline in the baseline catalog articles (which assert Asombro Extremo was created in 2012 by all three founders).

## Proposed Website Uses
- Add the article to the media catalog to further substantiate Ezequiel/Frank Escudero's core role in bringing technological innovation to Asombro Extremo.
- The conflict note should be included in the front matter or catalog metadata to present an honest historical record.

## Limitations
* Google Search via automated queries yielded "No results" for exact names and campaigns, highlighting the limitations of the search tool API. This led to initially inconclusive findings.
* The orchestrator provided a URL which successfully yielded the new finding.
* "Ezequiel Escudero" and "Asombro Extremo" returned no fresh qualitative interview content via the search API that met the criteria.

## Validation Commands
```bash
jq '.' inbox/media/media-research-2026-10-12/r01/findings.json
jq '.' inbox/media/media-research-2026-10-12/r01/search-log.json
```