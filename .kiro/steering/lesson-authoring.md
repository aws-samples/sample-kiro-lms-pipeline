---
inclusion: manual
description: "Write the per-module lesson.md: the page model, frontmatter, shortcodes (nextPage, knowledgeCheck, objectives, moduleEnd, dwell), and learner-facing writing guidance. Read at pipeline step 3 while authoring lessons."
---

# Lesson Authoring

Covers writing the per-module `lesson.md` — the learner-facing markdown Eleventy renders into SCORM pages. This is the heart of the workflow; everything else serves the lesson. For terse shortcode syntax while hand-editing an existing file, see `docs/lesson-markdown-reference.md`; this file is the judgment (tone, sizing, placement, what to omit).

## Mental model

The `lesson.md` you write **is** the lesson — not a prompt for an AI, not raw source material, not a facilitator's guide. It's finished learner-facing content that renders directly to HTML inside the SCORM package. Write for the learner, in second person, structured and conversational-but-precise. Aim for "well-written technical article," not "lecture transcript" or "whitepaper."

## File layout (per module)

```
build/module-N/
  lesson.md               ← the main authored content (this file)
  learning-objectives.md  ← standalone objectives list
  visuals/                ← images the lesson embeds
```

## Page model

Eleventy splits each `lesson.md` into **lesson pages** at explicit `{% nextPage %}` markers. Each page is inlined into the single-page SCORM `index.html` as an inert `<template>`; `course.js` clones the right one into the reading column when the learner navigates. To the learner each page is a distinct screen with its own prev/next — but there are no per-page HTML files on disk (that single-page design is what keeps completion tracking working; see `scorm-authoring.md`).

```markdown
## From Markdown to SCORM
...page 1 content...

{% nextPage %}

## Authoring Building Blocks
...page 2 content...
```

Within a page, use standard markdown headings for structure. **Page sizing:**
- 150–400 words per page (longer → skimming; shorter → too many Next clicks).
- One main concept per page; break complex topics across pages.
- 5–15 pages per module is the usable range.

## Frontmatter

```yaml
---
module_id: module-1
module_number: 1
title: "The Authoring Pipeline"
duration_minutes: 10
learning_objectives:
  - "Describe how a `lesson.md` file becomes a single-page SCORM package"
  - "Use pagination markers, callouts, and knowledge checks in lesson content"
  - "Run the lint, build, and validate steps for a course"
---
```

The linter only **requires** `module_id` and `title`; the rest are convention. `learning_objectives` feeds the `{% objectives %}` block and the module-end checklist, so keep it in sync with `learning-objectives.md`.

## Content components

Author as standard markdown plus a small set of shortcodes.

**Standard markdown:** headings (`#`/`##`/`###`), paragraphs, `**bold**`, `*italic*`, `inline code`, lists, tables, fenced code, blockquotes, rules.

**Images** — paths relative to `build/module-N/`; Eleventy copies them into SCORM `assets/` and rewrites paths at build:
```markdown
![Caption text](visuals/slide-14.png)
```

**Callouts** — `{% tip "Label" %}…{% endtip %}`, `{% warning %}…{% endwarning %}`, `{% info %}…{% endinfo %}`.

**Knowledge check** — in-page quiz with per-option feedback:
```markdown
{% knowledgeCheck %}
question: "Why render the whole course into a single HTML file?"
options:
  - text: "So the SCORM session initializes exactly once per launch"
    correct: true
    feedback: "Correct. Multi-page SCOs re-initialize on every navigation, breaking tracking on some LMSs."
  - text: "Because SCORM 1.2 only allows one HTML file"
    correct: false
    feedback: "SCORM 1.2 allows many files; single-page is a deliberate compatibility choice."
{% endknowledgeCheck %}
```
- **Ungraded by default** (practice, no SCORM score contribution). Add `graded: true` to count toward completion score.
- Must have at least one `correct: true` option and a matching `{% endknowledgeCheck %}` (lint errors otherwise).

**Module end** — `{% moduleEnd %}` marks end of the *module* (not a page break). Renders a summary card with the objectives checklist and a "Next module" button. Put it on the final page, exactly once.

**Per-page dwell** — `{% dwell 45 %}` overrides the course-wide `min_page_dwell_seconds` (from `course.yaml`) for that page; `{% dwell 0 %}` removes the dwell gate entirely (e.g., a short divider page). Renders as a hidden meta tag the runtime reads.

## Structure guidance

**Opening a module** — start with the payoff, not the agenda. The learner should grasp in 10 seconds what they'll be able to do differently.
> Avoid: "This module covers the authoring pipeline. We'll discuss `lesson.md`, the build step, and validation."
> Prefer: "By the end of this module you'll take a course from markdown to an upload-ready SCORM package: authoring lessons, building the zip, and validating it."

**Objectives block** — near the top of the first page, render `{% objectives %}` (pulls from frontmatter `learning_objectives`).

**Knowledge-check placement** — roughly 1–2 per 4 pages, minimum 1 per module (the linter warns outside this band). Use them to reinforce the previous page's concept.
- Good: after a key concept, before a decision-tree page, between two ideas learners confuse.
- Bad: clustered at the end (feels like a test), one per page (exhausting), trivia that doesn't matter for the job.

**Closing a module** — final page carries a 3–5 bullet summary, the objectives checklist, and a next-step pointer. `{% moduleEnd %}` renders this consistently.

## Writing guidance

- **Audience/tone:** state the audience up top and match register. For technical audiences: professional, direct, second-person, assumes platform fundamentals. Avoid marketing voice ("transformative"), hedging ("it might be worth considering…"), and talking *about* the lesson ("in this section we will discuss…") — just teach.
- **Technical accuracy:** define acronyms on first use; use exact numbers ("5–15 pages," not "a handful"); name the specific services from the source, not adjacent ones you assume. These are judgment calls — err toward restraint when unsure.
- **Headings:** `##` for page sections (2–4 per page), `###` for sub-points. `####`+ signals an overpacked page (the linter warns on depth > 3).
- **Tables:** use for structured comparisons/reference/rubrics, not narrative lists. 2–4 columns; 5+ scrolls horizontally and breaks on mobile.
- **Code blocks:** fenced with a language hint for syntax highlighting; `inline code` for short paths/commands.

## Content to omit

Common in older prompt-based workflows; they don't belong in `lesson.md` (it renders straight to HTML — nothing interprets it):
- "Context for the AI Assistant" / tone instructions.
- Design-note quiz questions not meant to render (if a question is in the lesson, it renders).
- Multiple parallel versions of the same content — write one and iterate; parallel copies drift.
- "Recommended sections" scaffolding — write the actual sections.
- Facilitator instructions — a facilitator's guide is a separate artifact.

## Linting

Run before building: `python3 scripts/lint-lessons.py <course-name>` (also fires on save via the lint hook). Exit is non-zero only when there are **errors**.

- **Errors** (block the build): missing/invalid frontmatter or missing `module_id`/`title`; an empty page between `{% nextPage %}` markers; a knowledge check with no `correct: true` or no `{% endknowledgeCheck %}`; an image path that doesn't resolve; `{% moduleEnd %}` appearing more than once or not on the final page.
- **Warnings** (worth fixing, non-blocking): headings deeper than `###`; a missing `{% moduleEnd %}`; knowledge-check count outside ~1–2 per 4 pages.

## Checklist per module

- [ ] `lesson.md` written, paginated (150–400 words/page), and reviewed.
- [ ] `learning-objectives.md` exists and matches the frontmatter list.
- [ ] All referenced visuals exist under `visuals/`.
- [ ] Knowledge checks have feedback text (not just right/wrong).
- [ ] `{% moduleEnd %}` on the final page; linter passes with no errors.

Once all modules are lint-clean, move to `scorm-authoring.md` to build the package.
