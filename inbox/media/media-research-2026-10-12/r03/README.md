# R03 Research Packet: Campaign and award media

## Overview
This packet investigates campaign and award media connected to Frank / Ezequiel Escudero and Asombro Extremo (now Amaze / Asombro Extremo LLC). Initial open-web searches were inconclusive, so direct reviewer-supplied fallbacks and explicitly provided leads were utilized.

## Findings
* **Amaze (Asombro Extremo LLC):** Discovered the corporate continuity to weareamaze.com. Their Terms & Conditions (Section 6.3) strictly prohibit copying/reproduction without express written consent. Consequently, zero local downloads were made; all assets are tracked as `reference_only`.
* **Clarín Creativity Awards 2015:** Asombro Extremo won Gold in Digital Campaigns and Silver in Mobile for the Coca-Cola "El llamado de Papá Noel" campaign. The article clarifies that Blue Hive (for Ford) won the Cannes Lions trip, explicitly removing a Cannes Lions link from Asombro Extremo in this context.
* **Personal Attribution:** While many awards target the agency, an article on AleTecno explicitly credits Ezequiel Escudero with "Desarrollo Digital" for the Samsung "El Plan Perfecto" campaign, distinguishing his personal work.

Because of strict rights limitations, the catalogue entries contain exact canonical references and zero local assets. Generic Cannes Lions context imagery was rejected as a finding as it provided no proof of agency/personal involvement.

## Limitations
* Open web searches for specific campaigns and "Cannes Lions" yielded no results / inconclusive results.
* The Iberia case study page and embedded YouTube video were throttled/blocked from direct programmatic retrieval and required manual/reviewer fallback.
* All assets found are under strict copyright (reference-only), preventing direct incorporation into the website's local assets.

## Exact Validation Commands
```bash
python3 -m json.tool inbox/media/media-research-2026-10-12/r03/keyword-map.json
python3 -m json.tool inbox/media/media-research-2026-10-12/r03/findings.json
python3 -m json.tool inbox/media/media-research-2026-10-12/r03/search-log.json
node --test tests/*.test.cjs
PYTHONPATH=. uv run pytest
```
