---
inclusion: manual
description: "Plan a course under the single-SCORM architecture: module structure, learning objectives, course-level metadata, and the course.yaml manifest. Start here for any new course (pipeline step 2)."
---

# Course Planning

Covers planning a course under the single-SCORM architecture: module structure, learning objectives, training metadata, and the `course.yaml` manifest. Start here for any new course (pipeline step 2).

## Architecture reminder

One course produces **one SCORM `.zip`** that uploads as **one training** on the LMS. "Modules" are sections inside that SCORM, not independent trainings. Consequences:

- Metadata is course-level; module metadata is internal nav, not separate platform records.
- Completion is tracked for the course, not per module.
- One thumbnail, one duration, one description for the whole package.

## Step 1: Inventory the source material

List what you have into `build/inventory.md` (it matters later when deciding per-module content):

- **Decks** — `.pptx` (export Keynote/Google Slides to `.pptx` first).
- **Written docs** — playbooks, READMEs, markdown, Word, PDF. A script from a live session counts as a written doc.
- **Recordings/video/audio are NOT supported** — there's no transcript workflow. If the material is a recording, ask for the written sources behind it (the deck, the playbook). See `source-intake.md` for how each supported type becomes lesson markdown.

**Cross-module visual sourcing:** when an earlier module promises a preview of an artifact whose authentic visual lives in a *later* module's source, pull that visual into the earlier module's `visuals/`, label its origin in `INDEX.md` (e.g. `source: module-3 deck`), and keep a single copy — reference, don't duplicate. Test: does an earlier module say "here's a real example" of something not produced until later? Usually a handful of visuals per course.

## Step 2: Decide module structure

- **Default: one module per major phase** of the workflow being taught. Resist splitting into many small modules.
- **Target 15–25 min of learner time per module** (not raw source volume). A 40-slide deck or 20-page chapter usually becomes a 15–20 min module after curation.
- **Page count:** each module is a sequence of HTML pages; target **5–15 pages** (see `lesson-authoring.md`).
- **"Resources"/"Field Guide" module (optional):** for courses with heavy reference material, add a final module with outbound links, quick-reference cards, and copy-pastable templates/checklists. Still a section of the one SCORM, just different pedagogy; mark it `resources_only: true` in `course.yaml`.

## Step 3: Draft learning objectives

3–5 per module, using **measurable verbs**, phrased "By the end of this module, the learner will be able to…":

| Avoid | Prefer |
|---|---|
| Understand… | Identify…, Describe…, Explain… |
| Learn about… | Apply…, Demonstrate…, Calibrate… |
| Be familiar with… | Use…, Produce…, Evaluate… |

Save to `build/module-N/learning-objectives.md`. These feed two places: the module's opening `{% objectives %}` block, and the course-level objectives on the LMS page (concatenate all modules, trim to the top 5–8).

## Step 4: Write course metadata (course-level, not per-module)

The course **is** the training, so write one metadata set into `build/course-metadata.md`. Character/size limits below are typical LMS constraints — verify your platform's actual limits.

- **Title** (typically ≤150 chars): lead with the outcome, active voice, name the role or job-to-be-done.

  | Avoid | Prefer |
  |---|---|
  | Introduction to Incident Response | Run an Incident Response Process End-to-End |
  | Security Best Practices Training | Apply Security Best Practices in Your Workload |

- **Description** (typically ≤150 words): one sentence on who it's for and what they'll do → 4–8 bullets of cross-module outcomes → one sentence on prerequisites/context.
- **Tags:** what learners would realistically search; mix specific, general, and role-based. Avoid single-letter or generic tags like `training`.
- **Duration:** sum of module durations plus a few minutes for navigation (e.g. 5 × 15–20 min ≈ 75–100 min).
- **Thumbnail:** landscape, common spec 320×180 px ≤100 KB, PNG/JPG, minimal high-contrast text, represents the whole course. Store at `build/thumbnail.png`.
- **Language:** default `en-US`. For multi-language, produce parallel SCORM packages (one per language), each uploaded as its own training.

## Step 5: Module-internal metadata

Each module carries light metadata for the SCORM build only (none of it goes to the platform), in `course.yaml`: `title` (nav sidebar, page headers), `short_description` (home-page module list), `target_duration_minutes` (per-module budget). Module learning objectives live in the lesson frontmatter and `learning-objectives.md` — see `lesson-authoring.md`.

## Step 6: Produce `course.yaml`

Single source of truth for the course:

```yaml
course:
  title: "Your Course Title"
  short_name: "short-name"           # lowercase kebab-case, used in file names
  short_description: "One-line course description."
  description_file: build/course-metadata.md
  thumbnail: build/thumbnail.png
  default_language: en-US
  tags: [tag-1, tag-2, tag-3]
  total_duration_minutes: 90         # sum of modules + nav overhead

modules:
  - id: module-1
    title: "Module 1 Title"
    short_description: "One-sentence summary"
    source_deck: "sources/module-1-slides.pptx"   # optional
    source_playbook: ["sources/module-1-guide.md"] # optional
    target_duration_minutes: 15
  # ... more modules
  - id: module-5
    title: "Field Guide & Resources"
    resources_only: true
    short_description: "References used during real engagements"

scorm:
  version: "1.2"
  output: scorm/dist/course.zip
  completion_strategy: explicit_finish   # documentary only; NOT read by the pipeline.
                                         # Completion is automatic (last page reached,
                                         # all page gating satisfied). See scorm-authoring.md.
  passing_score: 100                     # drives <adlcp:masteryscore> and the score written on completion
  min_page_dwell_seconds: 5              # per-page Next-button dwell gate (see scorm-authoring.md)
```

## Step 7: Scaffold the build directory

```bash
for m in module-1 module-2 module-3 module-4; do mkdir -p "build/$m/visuals"; done
mkdir -p "build/module-5"   # resources module (no visuals)
```

Each module folder's contract:

```
build/module-N/
  lesson.md               ← authored lesson content (lesson-authoring.md)
  learning-objectives.md  ← measurable objectives
  visuals/                ← images used in lesson pages
    INDEX.md              ← catalog with captions (see source-intake.md)
```

## Checklist: before lesson authoring

- [ ] `build/inventory.md` lists all source material.
- [ ] Module count and boundaries decided.
- [ ] 3–5 measurable-verb objectives per module.
- [ ] Course title (outcome-focused), description, and tags written.
- [ ] Per-module and total durations estimated; thumbnail spec noted.
- [ ] `course.yaml` complete; `build/module-N/` folders scaffolded.

Once this is done, move to `lesson-authoring.md`.
