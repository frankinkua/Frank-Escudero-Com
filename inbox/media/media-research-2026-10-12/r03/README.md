# R03 Research Packet: Campaign and award media

## Overview
This packet investigates campaign and award media connected to Frank / Ezequiel Escudero and Asombro Extremo (now Amaze / Asombro Extremo LLC). Initial open-web searches were blocked by tool limitations, so direct reviewer-supplied fallbacks were utilized.

## Findings
* **Amaze (Asombro Extremo LLC):** Discovered the corporate continuity to weareamaze.com. Their Terms & Conditions (Section 6.3) strictly prohibit copying/reproduction without express written consent. Consequently, zero local downloads were made; all assets are tracked as `reference_only`.
* **Clarín Creativity Awards 2015:** Asombro Extremo won Gold in Digital Campaigns and Silver in Mobile for the Coca-Cola "El llamado de Papá Noel" campaign. The article clarifies that Blue Hive (for Ford) won the Cannes Lions trip, explicitly removing a Cannes Lions link from Asombro Extremo in this context.
* **Cannes Lions:** Contextual imagery is present on the official site, but no specific attribution to Frank or rights grants for republication were found.

Because of strict rights limitations, the catalogue entries contain exact canonical references and zero local assets.

## Limitations
* Open web searches for specific campaigns and "Cannes Lions" failed completely.
* The Iberia case study page and embedded YouTube video were throttled/blocked from direct retrieval.
* All assets found are under strict copyright (reference-only), preventing direct incorporation into the website's local assets.

## Exact Validation Commands
```bash
python3 -m json.tool inbox/media/media-research-2026-10-12/r03/findings.json
python3 -m json.tool inbox/media/media-research-2026-10-12/r03/search-log.json
node --test tests/*.test.cjs
PYTHONPATH=. uv run pytest
```
