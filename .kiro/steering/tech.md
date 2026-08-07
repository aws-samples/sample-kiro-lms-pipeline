---
inclusion: always
---

# Tech: the deterministic pipeline

The scripts are the source of truth for all mechanical work.
Run them yourself from the repository root; do not re-implement their logic in conversation.

## Pipeline commands (in order, for any course)

```bash
python3 scripts/lint-lessons.py <name>                                  # 1. lint authored lessons
scripts/build-scorm.sh <name>                                           # 2. render + zip the package
python3 scripts/validate-scorm.py courses/<name>/scorm/dist/<name>.zip  # 3. validate before upload
```

- One-time setup if `scorm/src/node_modules/` is missing: `npm --prefix scorm/src install`.
- `scripts/build-scorm.sh` sets `COURSE_ROOT` for Eleventy; never run Eleventy directly.
- Fix lint errors before building; fix validation errors before ever mentioning upload. Fix mechanical issues (broken image paths, missing frontmatter fields, heading depth) directly, but ask before changing lesson content for judgment calls (empty pages, a knowledge check with no correct answer).
- To run the whole packaging tail on an already-authored course, just run the three commands above in order; there is no separate trigger to invoke.
- Source intake (optional tier): `scripts/extract_visuals.py` renders `.pptx`/PDF decks to per-slide PNGs, `scripts/extract_notes.py` pulls speaker notes; both fail with install hints when their optional dependency is missing (see `#source-intake`).
- Assessments (optional tier): `scripts/build_assessment.py <name>` validates an authored `courses/<name>/assessment.yaml` and exports LMS bulk-upload XLSX files (see `#assessment-authoring`).

## Tests

- Unit tier (default): `python3 -m pytest tests/` (needs `pyyaml`, `pytest`).
- Runtime tier: `npm --prefix tests/runtime test` after a fresh build (jsdom + scorm-again against the zip).
- Run the relevant tier after changing anything under `scripts/` or `scorm/src/`.

## Prerequisites

Node.js 18+, Python 3.11+ with `pyyaml` and `pytest`, and `zip`.
If one is missing, say which command failed and what to install; do not silently skip a pipeline stage.
