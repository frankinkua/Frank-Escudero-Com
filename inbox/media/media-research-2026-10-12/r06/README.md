# Research Packet R06

## Review table
| Title | Type | Status | Rights |
|---|---|---|---|
| Asombro Extremo founders - 2018 | image | verified | reference_only |
| Julián Avila, Marcos Amadeo y Ezequiel Escudero - 2019 | image | verified | reference_only |

## Useful findings
- Identified two authentic portraits from previously cataloged `LA NACION` press articles.
- The 2018 article features a portrait of the Asombro Extremo founders (`asombro-2018-portrait`).
- The 2019 article features a portrait with an explicit caption identifying Ezequiel Escudero (`asombro-2019-portrait`).

## Proposed website uses
- Use the identified canonical URLs to display or reference these portraits in the "press" or "entrepreneurship" sections of the website. Because they belong to `LA NACION`, they must remain `reference_only` and cannot be downloaded/hosted locally.

## Limitations
- General Google searches for images of "Ezequiel Escudero" and "Frank Escudero" yielded no high-quality, verified results. Many queries returned zero usable hits.
- Attempted to read the SETOFF project PDF but the current environment lacks `pdftotext` or Python PDF parsing libraries (`pypdf`, `fitz`/`PyMuPDF`) required to extract contents or embedded images from the document.

## Validation Commands
```bash
python3 -m json.tool inbox/media/media-research-2026-10-12/r06/findings.json
python3 -m json.tool inbox/media/media-research-2026-10-12/r06/search-log.json
uvx ruff check .
PYTHONPATH=. uv run pytest
```
