---
inclusion: always
---

# Product: SCORM course pipeline

This repository turns raw training material (decks, Word docs, PDFs, playbooks, markdown docs) into LMS-ready SCORM 1.2 packages.
Recordings, video, and audio are not supported inputs; ask the user for the written material behind them.
The deliverable per course is exactly one zip: `courses/<name>/scorm/dist/<name>.zip`.

## The user journey is a conversation

Users drop source material into `courses/<name>/` and ask you to build the course.
You drive the whole pipeline yourself with the repo's deterministic scripts (see `tech.md`).
Never tell the user to run a script by hand; run it, then report the result and the resulting zip path.

The deep authoring playbooks (course planning, source intake, lesson authoring, SCORM packaging, assessment authoring) live as `inclusion: manual` steering files in `.kiro/steering/`; `pipeline.md` maps which one to load at each stage.
Consult them for authoring judgment; the always-on steering covers how this repo is wired.

## Quality bar

- A course is done only when lint, build, and validate all pass and the zip path has been reported to the user.
- Never suggest uploading a package that fails validation.
