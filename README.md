# Kiro SCORM Course Pipeline

> **Disclaimer:** This sample is provided for demonstration and educational purposes only and is not intended for production use without additional security review and testing.

Convert raw training material (decks, Word docs, PDFs, playbooks, markdown docs) into LMS-ready SCORM 1.2 packages using a two-layer [Kiro](https://kiro.dev) architecture.

The repo is designed to be driven from a Kiro conversation: drop your material into `courses/<name>/`, ask Kiro to build the course, and Kiro runs the pipeline itself and hands back the upload-ready zip.
Opening the repo in Kiro loads the steering it needs, and Kiro installs the project's dependencies and runs the pipeline for you. You do need Node.js, Python, and `zip` available first (see Prerequisites).
Deterministic scripts remain the engine underneath: linting lesson structure, building the package, and validating the output.
Kiro steering encodes the domain knowledge that scripts cannot, such as why the package must be a single-page SCO to track completion reliably on Rustici-backed LMS tenants.

## Architecture

The pipeline has two layers.

**Layer 1: deterministic tooling.**
A course manifest (`course.yaml`) declares modules, source material, and build configuration.
Shared scripts lint the authored lessons, render them through Eleventy into one single-page SCORM package, and validate the resulting zip.

**Layer 2: Kiro guidance, all in `.kiro/steering/`.**
Steering carries everything Kiro needs, split across three inclusion modes so each session loads only what's relevant:

- **Always-on** (`inclusion: always`): `product.md`, `structure.md`, `tech.md`, and `pipeline.md` — the goal, layout, commands, and the end-to-end build sequence. These load into every Kiro session in this repo (IDE and `kiro-cli`) with no setup.
- **Scoped** (`inclusion: fileMatch`): `scorm-invariants.md` — the hard single-page-SCO constraints, loaded automatically only when you touch a `lesson.md`, `course.yaml`, or the `scorm/src/` engine.
- **On demand** (`inclusion: manual`): the deep authoring playbooks (`course-planning.md`, `source-intake.md`, `lesson-authoring.md`, `scorm-authoring.md`, `assessment-authoring.md`). Kiro reads these as the conversation reaches each stage, or you invoke one with its `#name`.

Kiro Specs (`.kiro/specs/`) are Kiro's structured requirements documents; here they define the quality requirements the tooling implements, and each requirement traces to tests under `tests/`.
Kiro Hooks (`.kiro/hooks/`) lint lessons on save, validate packages as they are built, and propose steering updates when a work session surfaces a transferable lesson.

```
Raw source material          courses/<name>/                 One SCORM .zip
-------------------          ---------------                 --------------
Decks (.pptx)        --->    course.yaml            --->     imsmanifest.xml
Word docs / PDFs             build/module-N/lesson.md        index.html (single-page SCO)
Playbooks / markdown         build/module-N/visuals/         assets/ (css, js, images)
```

**What the automation covers.**
The scripts mechanize exactly three conversions: markdown lessons -> SCORM package (lint, build, validate), `.pptx` decks -> per-slide PNGs plus extracted speaker notes (`extract_visuals.py`, `extract_notes.py`), and an authored `assessment.yaml` -> LMS bulk-upload XLSX files (`build_assessment.py`).
Everything between those points - reshaping Word/PDF/deck prose into lesson markdown, curating visuals, and authoring assessment questions - is agent work, governed by steering files (`source-intake.md`, `assessment-authoring.md`) so it stays consistent run to run.
Recordings, video, and audio are not supported inputs; bring the written material behind them.

Key design choice: the whole course is **one HTML file**.
Lesson navigation is JavaScript-driven (hash routing plus template cloning) so `LMSInitialize` is called exactly once per session.
Multi-page SCOs mark complete on first exit on some Rustici-backed LMS tenants; the manifest's `<adlcp:masteryscore>` plus automatic completion (fired only when the last page is reached with every page's gating satisfied) close that hole.
The full story is in `.kiro/steering/scorm-authoring.md`.

## Prerequisites

- Node.js 18+
- Python 3.11+, `zip`, and `pip install -r requirements.txt` (pyyaml, pytest)

### Optional prerequisites (source intake and assessments)

The core markdown -> SCORM pipeline needs nothing beyond the list above.
The optional intake and assessment tools each declare their own dependency and fail with a clear install hint when it is missing, or install them all at once with `pip install -r requirements-optional.txt`:

- **LibreOffice** (`soffice`, MPL-2.0) - the one external CLI, used by `extract_visuals.py` to render `.pptx` decks; install via `brew install --cask libreoffice` or `apt-get install libreoffice`. It is invoked as a user-installed tool and never bundled. Not in `requirements-optional.txt` since it isn't a pip package.
- **pip extras** (all permissive licenses, see `requirements-optional.txt`): `pypdfium2` (PDF -> PNG), `pypdf` (PDF text extraction), `mammoth` or `python-docx` (Word conversion), `python-pptx` (speaker notes), `openpyxl` (assessment XLSX export).
- **boto3 + AWS credentials** - only for the optional `caption_visuals.py` (Bedrock vision captions); nothing else depends on it.

## Quickstart (in Kiro)

The primary way to use this repo is a Kiro conversation; you never need to copy script commands.

1. Open the repo in Kiro.
   The workspace steering in `.kiro/steering/` loads automatically, so Kiro already knows the pipeline.
2. Say: *"Build the sample course."*
   Kiro runs lint, build, and validate itself and replies with the path of the upload-ready zip (`courses/sample-course/scorm/dist/sample-course.zip`).
3. For your own course, drop your source material into `courses/<name>/` and say: *"Plan and build a course from this."*
   Kiro walks through planning `course.yaml`, authoring `lesson.md` per module, and packaging, pulling in the relevant `#course-planning` / `#source-intake` / `#lesson-authoring` steering at each stage.

Upload the resulting zip to any SCORM 1.2 LMS. To verify completion tracking locally before you upload, run the runtime test tier (see [Testing](#testing)).

### What runs automatically

Three hooks in `.kiro/hooks/` keep the loop tight without being asked:

- **Lint on save** (`lint-lessons-on-save.json`) - saving any `courses/*/build/*/lesson.md` or `course.yaml` re-lints that course.
- **Validate on package creation** (`validate-scorm-package.json`) - a new zip appearing under `courses/*/scorm/dist/` is validated immediately.
- **Steering reflection** (`steering-reflection.json`) - after each agent turn, Kiro proposes (never auto-applies) steering updates when a session surfaced a transferable lesson.

There are no separate manual "build" or "validate" trigger files: the full lint -> build -> validate sequence lives in the always-on steering (`tech.md`, `pipeline.md`), so a request like *"build the course"* drives the whole loop without a dedicated `#name` to invoke.

Honesty note: the hook files use the Kiro IDE v1 JSON format (a `{"version": "v1", "hooks": [...]}` document with `PostFileSave`, `PostFileCreate`, and `Stop` triggers).
Whether the `PostFileCreate` trigger fires for zips written by the build script (rather than by Kiro directly) can vary by version; if it stays silent, just run the validator yourself (`python3 scripts/validate-scorm.py <zip>`) or ask Kiro to build the course again.

**IDE vs. `kiro-cli`:** the hooks above are IDE behavior.
`kiro-cli` (the headless agent CLI) does not fire any `.kiro/hooks/*.json` trigger today - no file-watcher for lint-on-save or validate-on-package, and no `Stop` firing for the steering-reflection hook.
The steering itself, though, works the same in both: `.kiro/steering/*.md` loads into `kiro-cli` sessions in this repo just like in the IDE (`inclusion: always` files automatically, `inclusion: manual` files when referenced), so the agent has the full playbook either way.
If you are scripting this pipeline with `kiro-cli`, compensate only for the missing hooks: run the lint -> build -> validate sequence yourself (it is spelled out in the always-on `tech.md`), since no hook will run it for you.

## Under the hood: the scripts (manual and CI use)

The scripts are the deterministic engine the hooks and steering call; nothing lives only in prompts.
Run them directly for CI or script-first workflows:

```bash
# Install the Eleventy builder's dependencies (once)
npm --prefix scorm/src install

# 1. Lint the lessons
python3 scripts/lint-lessons.py sample-course

# 2. Build the SCORM package
scripts/build-scorm.sh sample-course

# 3. Validate the package
python3 scripts/validate-scorm.py courses/sample-course/scorm/dist/sample-course.zip
```

Test the build locally before uploading by serving the built site over HTTP:

```bash
cd scorm/build            # the unzipped build output (same content as the zip)
python3 -m http.server 8080
# then open http://localhost:8080 in a browser
```

Without an LMS the runtime runs in preview mode (no SCORM API), which is enough to check content, navigation, and gating.

## Testing

The suite has two tiers.

**Unit tier** (default, no dependencies beyond `pytest` and `pyyaml`):

```bash
python3 -m pytest tests/
```

This runs the linter, package-validator, and assessment-builder unit tests.
Tests needing an optional dependency (`openpyxl`) skip themselves when it is absent.

**Runtime tier** (Node only):

```bash
npm --prefix tests/runtime install   # once
scripts/build-scorm.sh sample-course # the tier tests the built zip
npm --prefix tests/runtime test
```

This loads the built package in [jsdom](https://github.com/jsdom/jsdom) against a [scorm-again](https://github.com/jcputney/scorm-again) SCORM 1.2 API stub and asserts the LMS-visible behavior: `LMSInitialize` exactly once per session, the incomplete-plus-suspend baseline, auto-completion with score 100 after a full walkthrough, mid-course exits staying incomplete, and bookmark resume.
Defaults to `sample-course`; set `COURSE=<name>` (matching the zip built by `scripts/build-scorm.sh <name>`) to run this tier against any other course.

The runtime tier is the closest local proxy for real-LMS behavior; upload the validated zip to your own SCORM 1.2 LMS for a final end-to-end check.

**Manual tier** (agent-driven source intake):

The source-intake and assessment-authoring workflows are agent work guided by steering, so they are exercised conversationally rather than by pytest.
[docs/manual-source-intake-tests.md](docs/manual-source-intake-tests.md) is the test matrix: one row per scenario (deck with/without notes, Word, PDF, mixed sources, assessment extraction and generation, an offered recording) with the prompt to give Kiro and the expected behavior.

## Repository layout

```
.kiro/
  steering/                    Workspace steering. Always-on: product, structure, tech, pipeline.
                               fileMatch: scorm-invariants. Manual playbooks: course-planning,
                               source-intake, lesson-authoring, scorm-authoring, assessment-authoring.
  hooks/                       Kiro hooks: lint on save, validate on package, steering reflection
  specs/                       Kiro specs: preflight validators, page-dwell gating, assessment builder
courses/
  sample-course/               Example course: course.yaml + authored module
  (deck/pdf/word/playbook/mixed/bare-deck/recording)-course/   source-intake test fixtures
scripts/
  extract_visuals.py           Deck/PDF -> per-slide PNGs (LibreOffice + pypdfium2)
  extract_notes.py             Deck -> speaker notes markdown (python-pptx)
  caption_visuals.py           Optional Bedrock vision captions for visuals/INDEX.md
  lint-lessons.py              Pre-build lesson linter
  build-scorm.sh               Eleventy build + zip wrapper
  validate-scorm.py            Post-build package validator
  build_assessment.py          assessment.yaml -> LMS bulk-upload XLSX
docs/
  manual-source-intake-tests.md  Manual test matrix for the source-intake workflows
scorm/
  src/                         Shared SCORM engine (Eleventy templates, runtime JS/CSS, manifest)
tests/
  preflight/                   Unit tests for the linter and package validator
  assessment/                  Unit tests for the assessment builder
  runtime/                     jsdom + scorm-again tests of the built SCO
```

## Adding a course

In Kiro: put your source material under `courses/<name>/` and ask Kiro to plan and build the course; the steering covers planning (`course-planning.md`), converting your source format (`source-intake.md`), and authoring (`lesson-authoring.md`), and Kiro runs the pipeline itself.

By hand:

1. Create `courses/<name>/course.yaml` and `build/module-N/` folders (see `.kiro/steering/course-planning.md`).
2. Write `lesson.md` per module (see `.kiro/steering/lesson-authoring.md`).
3. Lint, build, validate with the three commands above, substituting your course name.

All shared scripts resolve any course uniformly as `courses/<name>/`; there are no per-course special cases.

If you're hand-editing a `lesson.md` that already exists, `docs/lesson-markdown-reference.md` is a terse cheat sheet for the shortcodes (`{% nextPage %}`, `{% knowledgeCheck %}`, `{% moduleEnd %}`, and the rest).

## Third-party code

`scorm/src/assets/js/scorm_api_wrapper.js` is the [pipwerks SCORM API wrapper](https://github.com/pipwerks/scorm-api-wrapper) (MIT license), vendored with a `this`-binding fix on its convenience facade (documented in the steering files).

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

### Scope and limitations

This sample demonstrates a SCORM authoring pipeline; it is not a hardened file-processing service. Before any production use, review and add:

- **Input validation for source files.** The extraction scripts (`extract_visuals.py`, `extract_notes.py`) assume the decks and PDFs you feed them are trusted local files you authored. They do not sandbox or scan inputs for malicious content.
- **Output review.** Generated SCORM packages embed authored content verbatim; review lesson content before uploading to a shared LMS tenant.
- **No authentication or rate limiting.** The pipeline is a local CLI workflow, not a service. If you adapt it into a hosted service, add authentication, authorization, input size limits, and malware scanning for uploaded files.

## License

This library is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file.
