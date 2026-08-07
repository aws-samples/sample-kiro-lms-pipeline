# lesson.md Quick Reference

A cheat sheet for the shortcodes and structure used in `courses/<name>/build/module-N/lesson.md`.
This is the terse version for hand-editing a file that already exists.
For the full authoring guidance - tone, page sizing, where to place knowledge checks, what to omit - see `.kiro/steering/lesson-authoring.md`.

## Frontmatter

Every `lesson.md` starts with:

```yaml
---
module_id: module-1
module_number: 1
title: "Module Title"
duration_minutes: 15
learning_objectives:
  - "Objective one"
  - "Objective two"
---
```

## Page breaks

`{% nextPage %}` ends the current page and starts a new one. Everything between two `{% nextPage %}` markers (or between the top of the file and the first one, or the last one and end of file) is one page.

```markdown
## Page 1 heading

Page 1 content...

{% nextPage %}

## Page 2 heading

Page 2 content...
```

## Objectives block

`{% objectives %}` renders the frontmatter's `learning_objectives` list as a visual element. Place it near the top of the first page.

## Knowledge check (in-page quiz)

```markdown
{% knowledgeCheck %}
question: The question text?
options:
  - text: "Option A"
    correct: false
    feedback: "Why this is wrong."
  - text: "Option B"
    correct: true
    feedback: "Why this is right."
{% endknowledgeCheck %}
```

Ungraded by default (practice only, no SCORM score contribution). Add `graded: true` at the top of the block to count it toward module completion score. Needs at least one `correct: true` option.

## Callouts

```markdown
{% tip "Optional label" %}
Tip content.
{% endtip %}

{% warning %}
Warning content.
{% endwarning %}

{% info %}
Info content.
{% endinfo %}
```

## Images

```markdown
![Caption text](visuals/slide-14.png)
```

Paths are relative to the module folder.

## Per-page dwell override

`{% dwell 45 %}` overrides the course-wide `min_page_dwell_seconds` for the page it appears on. `{% dwell 0 %}` removes the dwell gate on that page.

## End of module

`{% moduleEnd %}` marks the end of the module (not a page break). Renders a summary card with the objectives checklist and a "next module" button. Put it after the module's final page content.

## Lint

Run `python3 scripts/lint-lessons.py <course-name>` after hand-editing to catch structural mistakes: unbalanced `{% nextPage %}`/shortcode pairs, malformed knowledge checks, missing `correct: true` options.
