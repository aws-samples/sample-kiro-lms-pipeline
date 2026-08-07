---
inclusion: always
---

# Pipeline: how a course gets built

This is the orchestration layer. It names the end-to-end sequence for turning raw source material into an upload-ready SCORM package, and points at the deep steering file to load at each stage. `product.md` covers the goal, `tech.md` the exact commands, `structure.md` the layout; this file is the order they run in.

You drive the whole sequence from the conversation. Run the scripts yourself, fix what fails, and report the resulting zip path. Never hand the user a script to run.

## Onboarding (once per workspace, before the first build)

1. Confirm `node` (18+), `python3` (3.11+ with `pyyaml` and `pytest`), and `zip` are on PATH. If one is missing, tell the user exactly what to install; do not skip a pipeline stage.
2. If `scorm/src/node_modules/` is missing, run `npm --prefix scorm/src install`.

## The end-to-end sequence

For any new course, in order. Steps 2-3 are agent authoring work; steps 4-6 are the deterministic packaging tail.

1. **Drop source material** into `courses/<name>/`. Supported: decks (`.pptx`), Word, PDF, playbooks, markdown docs. Recordings/video/audio are not supported inputs (see `product.md`).
2. **Plan the course** - read `#course-planning`. Produce `course.yaml` and one `build/module-N/` folder per module.
3. **Convert the source and author lessons** - read `#source-intake` when the source is anything other than finished lesson markdown (decks, Word, PDF, mixed), then `#lesson-authoring` to write `lesson.md` per module. This is the bulk of the work.
4. **Lint** - `python3 scripts/lint-lessons.py <name>` and fix every error. (Also fires automatically on save via the lint hook.)
5. **Build** - `scripts/build-scorm.sh <name>` renders every `lesson.md` into one `index.html` and zips the SCORM package. Read `#scorm-authoring` to diagnose any build failure.
6. **Validate** - `python3 scripts/validate-scorm.py courses/<name>/scorm/dist/<name>.zip`. Never suggest uploading a package that fails validation.
7. **Author the assessment (optional)** - read `#assessment-authoring`, write `assessment.yaml`, export with `python3 scripts/build_assessment.py <name>`.
8. **Upload to the LMS** - the SCORM zip plus training metadata, and the assessment XLSX files if produced.

Steps 4-6 only have anything to do once lessons exist (step 3). When a course's lessons are already authored, just run that packaging tail (lint -> build -> validate, see `tech.md`) directly - a request like "build the course" is enough; there is no separate trigger to invoke.

## Steering map

Each deep playbook is `inclusion: manual` - load it at the matching stage by reading it (or with its `#name` in the chat context):

| Stage | Steering file |
|---|---|
| Plan structure, objectives, `course.yaml` | `#course-planning` |
| Convert raw source into lesson markdown | `#source-intake` |
| Write `lesson.md` per module | `#lesson-authoring` |
| Build / package / debug the SCORM zip | `#scorm-authoring` |
| Author and export the assessment | `#assessment-authoring` |

The hard SCORM invariants that must never be violated load automatically via `scorm-invariants.md` (`inclusion: fileMatch`) whenever you touch a `lesson.md`, `course.yaml`, or the `scorm/src/` engine.
