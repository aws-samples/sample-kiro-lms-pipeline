---
inclusion: fileMatch
fileMatchPattern: ["scorm/src/**", "courses/*/build/**", "courses/*/course.yaml"]
---

# SCORM engine invariants

These are hard constraints; violating any of them breaks completion tracking on real LMS tenants.
The full rationale is in `scorm-authoring.md` (`#scorm-authoring`).

- The whole course stays a **single-page SCO**: one `index.html`, every lesson body inlined as a `<template>`, `LMSInitialize` called exactly once per session.
  Never split the output into multiple HTML pages or add a `pages/` directory.
- The manifest must keep `<schemaversion>1.2</schemaversion>` and `<adlcp:masteryscore>` on the SCO item.
  Without the mastery score, many LMSs treat any exit as completion.
- `imsmanifest.xml` and `index.html` must sit at the **zip root** (build-scorm.sh zips from inside the build dir; keep it that way).
- Lesson markdown contract: pages split by `{% nextPage %}`, module ends with `{% moduleEnd %}`, knowledge checks need at least one `correct: true` option, image paths resolve relative to the module dir.
  `scripts/lint-lessons.py` enforces this; run it after editing lessons.
- Completion is automatic (dwell time + all pages visited + knowledge checks answered); there is no manual Finish flow to reintroduce.
