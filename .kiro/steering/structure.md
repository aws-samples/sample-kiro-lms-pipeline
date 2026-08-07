---
inclusion: always
---

# Structure: where things live

```
.kiro/
  steering/       always-on wiring (product, structure, tech, pipeline) +
                  fileMatch invariants + manual playbooks (course-planning,
                  source-intake, lesson-authoring, scorm-authoring,
                  assessment-authoring)
  hooks/          lint on save, validate on package, steering reflection
  specs/          quality requirements traced to tests
courses/<name>/   one course per directory, uniform shape:
  course.yaml               course manifest (modules, scorm config)
  build/module-N/lesson.md  authored markdown per module
  build/module-N/visuals/   images referenced by the lesson
  scorm/dist/<name>.zip     build output (gitignored)
scripts/          lint-lessons.py, build-scorm.sh, validate-scorm.py,
                  extract_visuals.py, extract_notes.py, caption_visuals.py, build_assessment.py
scorm/src/        shared SCORM engine (Eleventy templates, runtime JS/CSS, manifest)
tests/            preflight + assessment (unit), runtime (jsdom)
```

- All scripts resolve any course uniformly as `courses/<name>/`; there are no per-course special cases.
- New course: create `courses/<name>/course.yaml` and `build/module-N/` folders, then author `lesson.md` per module.
  Follow the `#course-planning`, `#source-intake`, and `#lesson-authoring` steering (see `pipeline.md` for the full sequence).
- Never modify original source material; derivatives go under `build/` and `scorm/`.
- Build outputs (`**/scorm/build/`, `**/scorm/dist/`) are gitignored; never commit them.
