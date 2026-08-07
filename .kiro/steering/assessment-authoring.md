---
inclusion: manual
description: "Author a standalone course assessment as assessment.yaml (extract existing quiz questions or derive them from the lessons) and export it to LMS bulk-upload XLSX files with build_assessment.py. Read at the optional assessment step (pipeline step 7)."
---

# Assessment Authoring

Covers authoring a standalone course assessment as `courses/<course>/assessment.yaml` and exporting it to LMS bulk-upload XLSX files with `scripts/build_assessment.py`. The assessment is separate from in-lesson knowledge checks: it's the graded question bank an LMS runs against the course.

## The dividing line: you author, the script exports

`build_assessment.py` never generates questions. **You author `assessment.yaml`** — by extracting questions already in the source material, or deriving them from the finished lessons — and the script validates it against the bulk-upload constraints and renders the XLSX. This keeps questions reviewable as plain text before anything touches an LMS.

Two sourcing modes, in order of preference:

## Mode 1: extract existing questions (preferred)

When a source doc (Word, PDF, playbook, or the lessons) carries a quiz, lift it into the schema below. Preserve original wording of questions, options, and explanations; only reshape what the schema requires (e.g. splitting a combined answer key back onto its options).

If the lessons contain `{% knowledgeCheck %}` blocks, lift those rather than re-deriving from prose. The script exposes a helper:

```python
from build_assessment import extract_knowledge_checks
questions = extract_knowledge_checks(lesson_markdown, module_id="module-1")
```

It parses every `{% knowledgeCheck %}` block into question/option/correctness/feedback structures (one correct option → "Single select", several → "Multi select") and warns without stopping on malformed blocks. Draft from its output, then curate — an end-of-course assessment usually wants a subset of the in-lesson checks, not all of them verbatim.

## Mode 2: generate from the lessons

When writing questions yourself, work from the finished `lesson.md`, not the raw source:

- **Cover every content module**, weighted by its share of the material; skip resources-only modules.
- **Test the objectives**, not trivia from the prose — write against each module's learning objectives.
- **Plausible distractors** — wrong options a partially-informed learner would actually pick (misconceptions, adjacent concepts), not obvious throwaways.
- **No trick questions** — no double negatives, no "all of the above", no options differing by one subtle word. Test understanding, not reading care.
- **Ground every question in lesson text** — a learner who studied the lessons must be able to answer. Never quiz on facts the course doesn't teach.
- **Explanations teach** — use `explanation` / `correct_answer_explanation` to say *why* the answer is right, pointing back at the concept.

## The `assessment.yaml` schema

```yaml
# courses/<course>/assessment.yaml
name: "Course Fundamentals Check"     # optional; see Metadata resolution
description: "What this assessment validates."
passing_score: 80
time_limit_minutes: 30
language: "English (US)"
tags: [tag-1, tag-2]

sections:
  - title: "First Topic"
    description: "Optional section description."
  - title: "Second Topic"

questions:
  - question_text: "Which file is the source of truth for a module's lesson content?"
    response_type: "Single select"
    section: "First Topic"
    options:
      - text: "lesson.md"
        correct: true
        explanation: "Each module's lesson.md is the authored source."
      - text: "index.html"
        correct: false
    correct_answer_explanation: "lesson.md is the authored source; everything else is generated."
    score: 1

  - question_text: "Which of the following are produced by the build?"
    response_type: "Multi select"
    section: "First Topic"
    options:
      - text: "index.html"
        correct: true
      - text: "imsmanifest.xml"
        correct: true
      - text: "The source lesson.md"
        correct: false
    score: 2

  - question_text: "How many seconds of dwell time unlock Next by default?"
    response_type: "Number"
    correct_answer: "20"      # answer-value types carry it here, not in options
    options: []
    score: 1
```

- **`response_type`** ∈ `Single select`, `Multi select`, `Text`, `Free text`, `Yes/No`, `True/False`, `Number`, `Percentage`, `Pass/Fail`.
- **Select types** mark correctness on options. **Value types** (`Text`, `Number`, `Percentage`, `Free text`) carry the answer in `correct_answer`. `Yes/No`, `True/False`, `Pass/Fail` use two options with the correct one flagged.
- **Sections:** a question's `section` names its group; naming an undeclared section creates it; omitting it files the question under "General".

### Metadata resolution

Each top-level metadata field resolves with this precedence, so don't repeat what `course.yaml` already says:

1. CLI flags (`--name`, `--description`, `--passing-score`, `--time-limit`, `--tags`, `--language`)
2. `assessment.yaml` top-level fields
3. The `assessment:` block in `course.yaml`
4. Course-level fallbacks: `course.title` (name), `scorm.passing_score`, `course.tags`
5. Defaults: passing score 80, language "English (US)"

## Validation constraints

The script checks all of these and reports every violation at once. They come from one real LMS bulk-upload template — treat them as a worked example and adapt for a different LMS:

| Constraint | Limit |
|---|---|
| Assessment name | ≤ 250 characters |
| Description | ≤ 5000 characters |
| Tags | ≤ 15 |
| Total questions | 1 to 750 |
| Passing score | 0 to 100 |
| Questions per section | ≤ 100 |
| Question / option text | ≤ 2000 characters |
| Options per question | ≤ 20 |
| Single/Multi select options | ≥ 2 |

## Validate and export

```bash
python3 scripts/build_assessment.py <course-name>
```

- Success writes `build/assessment.xlsx` (Instructions, Sections, and the per-language question sheet) plus `build/metadata.xlsx` (title and description, uploaded separately in the example template), under `courses/<course>/`, and prints a section/question summary.
- Validation errors print to stderr with a non-zero exit and **nothing is written** — fix the YAML and rerun.
- Needs `pyyaml` and `openpyxl` (`pip install pyyaml openpyxl`); `--help` works without them.

## Checklist: before handing the assessment over

- [ ] Every content module covered by at least one question.
- [ ] Existing source questions extracted rather than re-invented.
- [ ] Every question answerable from the lessons alone.
- [ ] Distractors plausible; no trick questions.
- [ ] Explanations written where needed.
- [ ] `python3 scripts/build_assessment.py <course>` exits 0; both XLSX files present under `courses/<course>/build/`.
