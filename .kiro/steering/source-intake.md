---
inclusion: manual
description: "Convert raw source material (markdown, Word, PDF, .pptx decks with or without notes, mixed sources) into lesson markdown: which conversions the scripts automate, which reshaping is agent work, and the visuals/INDEX.md contract. Read at pipeline step 3 when the source is anything other than finished lesson markdown."
---

# Source Intake

How raw source material — written docs, decks, or a mix — becomes lesson markdown the build can consume. Read after `course-planning.md` Step 1 (the source inventory) and before authoring lessons.

## The dividing line: scripts vs. agent work

The scripts automate exactly one conversion: **deck → slide PNGs + speaker notes** (`extract_visuals.py`, `extract_notes.py`). **Everything else — reshaping prose, structuring modules, writing lesson text from notes or bullets — is your work**, written directly as build-format `lesson.md` (`{% nextPage %}` / `{% knowledgeCheck %}`; see `lesson-authoring.md`).

Three absolute rules:

- **Never silently invent facts.** Lesson text must trace back to the source. When you must bridge a gap (a transition, a summary, an implied example), keep it minimal and consistent with the source.
- **Mark low-confidence sections for review.** Where the source was too thin to author confidently, insert a searchable marker, then tell the user which modules carry them at handover:
  ```markdown
  <!-- REVIEW: drafted from slide bullets only; SME should verify the config values here -->
  ```
- **Confirm the material is trainable before extracting.** Does it teach a skill, convey transferable knowledge, or describe a repeatable process? If not, stop and tell the user rather than drafting a "lesson" out of a status/report/meeting artifact.

## Where intake lands

Every path converges on build-format `lesson.md` at `courses/<course>/build/module-N/lesson.md`, checked by `lint-lessons.py` and packaged by the SCORM build. The `source_deck` / `source_playbook` fields in `course.yaml` are **provenance annotations only** — they record where material came from for re-extraction and audits; no script reads them to drive a conversion.

## Path: markdown docs and playbooks

The simplest case — reshape into `lesson.md`, one per module:

1. Split into modules per `course-planning.md` (one per major topic).
2. Per module, write frontmatter + body, paginating with `{% nextPage %}` (5–15 pages).
3. Reflow for the screen: shorter paragraphs, tables/lists where the source rambles, second person ("you configure…", not "the user configures…").
4. Leave the source unchanged; derivatives go under the course's `build/`.

## Path: Word documents (.docx)

Convert to markdown first, then follow the markdown path. Two permissive-licensed options:

- **mammoth** (`pip install mammoth`) — best for normally styled docs; maps Word styles to clean markdown. Prefer the Python API over the `python3 -m mammoth` CLI, which can emit empty output depending on shell arg handling:
  ```python
  import mammoth
  with open("source.docx", "rb") as f:
      markdown = mammoth.convert_to_markdown(f).value
  ```
  Mammoth places an inline `<a id="...">` anchor right before each heading rather than a `#` marker — when scanning output programmatically, match the anchor or heading text, not a `^#` regex.
- **python-docx** (`pip install python-docx`) — read the doc structurally (paragraphs, styles, tables) when mammoth needs help, e.g. complex tables.

Preserve embedded images: mammoth extracts them; save into the module's `visuals/` and reference as `visuals/<name>.png`.

## Path: PDF documents

Extract text with **pypdf** (`pip install pypdf`), then follow the markdown path:

```python
from pypdf import PdfReader
text = "\n\n".join(page.extract_text() for page in PdfReader("source.pdf").pages)
```

PDF extraction is lossy — reading order, headings, tables, and multi-column layouts frequently scramble. Treat it as raw material, not structure: **warn the user that layout-heavy PDFs need author review** and mark reconstructed sections with `<!-- REVIEW: ... -->`. If a PDF is essentially a rendered deck (one image per page), treat it as a deck — `extract_visuals.py` accepts `.pdf` directly.

## Path: deck (.pptx) with speaker notes

The best deck case — the notes are authored prose and become the lesson backbone. Only `.pptx` is supported (export Keynote/Google Slides to `.pptx` first); `.pptx` extraction needs LibreOffice (`soffice --headless`) for the PPTX→PDF render, while `.pdf` input skips that step.

1. **Extract visuals** (every slide → PNG):
   ```bash
   python3 scripts/extract_visuals.py path/to/deck.pptx --course <course-name> --module module-N
   ```
2. **Extract notes** — authored prose keyed by slide number:
   ```bash
   python3 scripts/extract_notes.py path/to/deck.pptx -o courses/<course>/build/module-N/notes.md
   ```
   Notes stay aligned with the slide PNGs because both sides drop hidden slides by default: `extract_notes.py` skips them and renumbers densely, and LibreOffice's PDF export (in `extract_visuals.py`) omits them. The script prints a `skipped N hidden slide(s)` note so a count mismatch is never silent. Only `--include-hidden` breaks the alignment — use it just when you deliberately want hidden-slide content.
3. **Curate visuals**: delete slides that won't appear (dividers, back-matter, text-heavy slides the prose already carries). Re-extraction is cheap, so be aggressive — typical keep rate 30–50%.
4. **Catalog the keepers** in `visuals/INDEX.md` (contract below).
5. **Author the lesson**: notes as the prose backbone, reshaped per `lesson-authoring.md`, visuals placed where `INDEX.md` says.

## Path: deck (.pptx) without notes

Same extraction, thinner material — slide titles and bullets are all the text you have:

- Draft prose from titles/bullets, expanding only as far as the slides support.
- Mark every expansion beyond what the slides state with `<!-- REVIEW: ... -->`.
- **Warn the user explicitly** that these lessons are drafts from slide fragments and need an author pass before shipping.

## One deck feeding multiple modules

`extract_visuals.py` renders the whole deck into a single module's `visuals/<deck-slug>/` — it has no concept of module boundaries. When a deck's slides split across modules (normal for any multi-module deck), extract once and redistribute rather than re-running per module:

1. Run `extract_visuals.py` once, targeting any one of the deck's modules.
2. Move each *other* module's slides into that module's `visuals/`; delete the ones that don't belong.
3. Flatten the `deck-slug/` subfolder in every module so images live directly at `visuals/slide-NNN.png` — keeps `lesson.md` image paths simple and avoids partial duplicate subfolders.
4. Catalog each module's final set in its own `visuals/INDEX.md`.

Applies to both deck paths, notes or no notes.

## Path: mixed sources (deck + doc + …)

1. **Inventory first** — `course-planning.md` Step 1's `build/inventory.md`; list every source and what it uniquely carries.
2. **Pick one backbone for structure** — usually the most complete written doc, or the deck notes when they're the fullest prose. The backbone decides module boundaries and page flow.
3. **Merge the rest as support** — deck visuals, detail paragraphs/tables from secondary docs, quiz questions from wherever they exist (see `assessment-authoring.md`).
4. **Flag conflicts** — when sources disagree (step orders, numbers), don't pick silently: note it in `<!-- REVIEW: sources disagree ... -->` and tell the user.

## Not supported: recordings, video, audio

The pipeline ingests none of these — no transcript workflow, frame extraction, or speech-to-text. If the source is a recording, the user must bring written material instead (the deck it presented, the playbook it walked through, or prose they author). Say this plainly; don't improvise a conversion.

## The `visuals/INDEX.md` contract

Every module with visuals keeps `build/module-N/visuals/INDEX.md` cataloging the curated set; you read it during authoring to place images.

```markdown
# Module N Visuals - Index

One line on where these came from and how they were curated.

## <Source deck or group name> (<count> images)

| File | Visual type | Caption | Lesson placement |
|---|---|---|---|
| `deck-slug/slide-003.png` | diagram | One factual sentence describing what is visible. | Page 4: the three-phase flow |
| `deck-slug/slide-007.png` | ui_screenshot | ... | Page 6: tool walkthrough |

## Publishing review needed

- `deck-slug/slide-012.png` - looks like real customer data in the header; review at
  full resolution before publishing, crop or replace if unsafe.

## Dropped during curation

- `slide-001.png`, `slide-002.png` - title and agenda, no teaching content
```

Rules:

- **Every surviving image appears in the table; every row names a real file.** Rewrite the INDEX after each curation pass so it matches the folder exactly.
- **File paths** are `deck-slug/slide-NNN.png` for a deck extracted into one module; use the flat `slide-NNN.png` after flattening for a multi-module deck — match whatever the folder actually looks like.
- **Captions are factual**, one sentence, describing what's visible — not marketing. Hand-written, agent-written, or via the optional `scripts/caption_visuals.py` (needs AWS credentials, Bedrock access, boto3; nothing else depends on it).
- **`Lesson placement`** says where the visual goes ("Page 3: …" or "unplaced" while authoring) — this is what makes the INDEX useful.
- **`Publishing review needed`** lists anything sensitive (names, customer data, internal URLs, real dashboard numbers). Everything listed must be resolved — cropped, replaced, or cleared — before the course ships.

## Checklist: before lesson authoring

- [ ] Every source converted along one path above, or explicitly declined (recordings).
- [ ] Source confirmed genuinely instructional, not a status/report/meeting artifact.
- [ ] Backbone source chosen when sources are mixed.
- [ ] Deck visuals extracted, curated, and cataloged in `visuals/INDEX.md`; notes extracted where present.
- [ ] All low-confidence sections carry `<!-- REVIEW: ... -->` markers; user warned about modules needing SME/author review.
- [ ] Original source files untouched.
