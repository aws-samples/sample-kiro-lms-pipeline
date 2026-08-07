#!/usr/bin/env python3
"""Validate an authored assessment.yaml and export LMS bulk-upload XLSX files.

Pipeline: Load courses/<course>/assessment.yaml -> Validate constraints
         -> Write build/assessment.xlsx + build/metadata.xlsx

The questions themselves are authored by hand or by an agent (extracted from
source material or derived from the finished lessons) - see the power's
``assessment-authoring.md`` steering file. This script never generates
content; it only checks the authored file against bulk-upload constraints
and renders it into an example bulk-import XLSX format. The concrete column
layout and constraint numbers below (750-question cap, 20 options, 2000-char
texts) come from one real LMS bulk-upload template; adapt them to your LMS
if yours differs.

Requirements (optional-tier, not needed for the SCORM pipeline itself):

- pyyaml:   ``pip install pyyaml`` (also required by the SCORM pipeline)
- openpyxl: ``pip install openpyxl``

Usage:
    python3 scripts/build_assessment.py [course-name] [--name ...]
        [--description ...] [--passing-score N] [--time-limit N]
        [--tags ...] [--language ...]
"""

from __future__ import annotations

import dataclasses
import json
import sys
from argparse import Namespace
from collections import namedtuple
from pathlib import Path
from typing import Any


def _import_yaml():
    """Import pyyaml on first use so ``--help`` works without it."""
    try:
        import yaml
    except ImportError:
        print(
            "ERROR: pyyaml not installed (needed to read course.yaml and assessment.yaml).\n"
            "Install with: pip install pyyaml",
            file=sys.stderr,
        )
        sys.exit(1)
    return yaml


# ---------------------------------------------------------------------------
# Named tuples
# ---------------------------------------------------------------------------

ModuleInfo = namedtuple("ModuleInfo", ["id", "title", "lesson_path"])
"""A discovered module: id, title, and resolved lesson.md path."""


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class Option:
    text: str
    correct: bool
    explanation: str = ""


@dataclasses.dataclass
class Question:
    question_text: str
    response_type: str  # "Single select", "Multi select", "True/False", etc.
    options: list[Option]
    correct_answer: str  # Formatted per the bulk-upload template rules
    correct_answer_explanation: str = ""
    score: int = 1


@dataclasses.dataclass
class Section:
    title: str
    description: str = ""
    questions: list[Question] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class Assessment:
    name: str
    description: str = ""
    passing_score: int = 80
    time_limit_minutes: int | None = None
    language: str = "English (US)"
    tags: list[str] = dataclasses.field(default_factory=list)
    sections: list[Section] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class ValidationError:
    field: str
    message: str
    severity: str = "error"  # "error" or "warning"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_RESPONSE_TYPES: list[str] = [
    "Single select",
    "Multi select",
    "Text",
    "Free text",
    "Yes/No",
    "True/False",
    "Number",
    "Percentage",
    "Pass/Fail",
]


# ---------------------------------------------------------------------------
# Module discovery and lesson parsing
# ---------------------------------------------------------------------------


def discover_modules(course_dir: Path, course_config: dict) -> list[ModuleInfo]:
    """Read course.yaml and resolve lesson.md paths for each module.

    Skips modules with resources_only=True and modules whose lesson.md is
    missing (both with a stderr warning). Returns ModuleInfo(id, title,
    lesson_path) for each valid module.
    """
    modules = course_config.get("modules", [])
    result: list[ModuleInfo] = []

    for module in modules:
        module_id = module.get("id")
        module_title = module.get("title")

        if not module_id or not module_title:
            continue

        # Skip resource-only modules
        if module.get("resources_only", False):
            print(
                f"WARNING: Skipping resources_only module '{module_id}'",
                file=sys.stderr,
            )
            continue

        # Resolve lesson path
        lesson_path = course_dir / "build" / module_id / "lesson.md"

        # Skip modules with missing lesson files
        if not lesson_path.exists():
            print(
                f"WARNING: Lesson file not found for module '{module_id}': {lesson_path}",
                file=sys.stderr,
            )
            continue

        result.append(ModuleInfo(id=module_id, title=module_title, lesson_path=lesson_path))

    return result


def strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter (--- delimited) from lesson markdown.

    Returns the body content after the closing --- delimiter.
    If no frontmatter is detected, returns content as-is.
    """
    if not content.startswith("---"):
        return content

    # Find the closing --- delimiter (must be after the opening one)
    # The opening "---" is at position 0, so search for the next "---" line
    # after the first line.
    newline_pos = content.find("\n")
    if newline_pos == -1:
        # Content is just "---" with no newline - no valid frontmatter
        return content

    # Search for closing "---" on its own line after the opening delimiter
    closing_pos = content.find("\n---", newline_pos)
    if closing_pos == -1:
        # No closing delimiter found - not valid frontmatter
        return content

    # Move past the closing "---" line
    after_closing = closing_pos + len("\n---")

    # Skip the newline immediately after the closing "---" if present
    if after_closing < len(content) and content[after_closing] == "\n":
        after_closing += 1

    return content[after_closing:]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_assessment(assessment: Assessment) -> list[ValidationError]:
    """Check the bulk-upload template constraints.

    Returns empty list if valid. Runs all checks without short-circuiting
    to report all violations at once.

    Constraints checked (example bulk-import rules; adapt to your LMS):
    - name <= 250 characters
    - description <= 5000 characters
    - tags <= 15
    - total questions > 0
    - passing_score in [0, 100]
    - each section <= 100 questions
    - total questions <= 750
    - question text <= 2000 characters
    - option text <= 2000 characters
    - options per question <= 20
    - Single select / Multi select types must have >= 2 options
    """
    errors: list[ValidationError] = []

    # Assessment name <= 250 characters
    if len(assessment.name) > 250:
        errors.append(ValidationError(
            field="name",
            message=f"Assessment name exceeds 250 characters ({len(assessment.name)} chars)",
        ))

    # Assessment description <= 5000 characters
    if len(assessment.description) > 5000:
        errors.append(ValidationError(
            field="description",
            message=f"Assessment description exceeds 5000 characters ({len(assessment.description)} chars)",
        ))

    # Tags <= 15
    if len(assessment.tags) > 15:
        errors.append(ValidationError(
            field="tags",
            message=f"Assessment has more than 15 tags ({len(assessment.tags)} tags)",
        ))

    # Passing score in [0, 100]
    if assessment.passing_score < 0 or assessment.passing_score > 100:
        errors.append(ValidationError(
            field="passing_score",
            message=f"Passing score must be between 0 and 100 inclusive (got {assessment.passing_score})",
        ))

    # Count total questions across all sections
    total_questions = 0
    for section_idx, section in enumerate(assessment.sections):
        section_question_count = len(section.questions)
        total_questions += section_question_count

        # Each section <= 100 questions
        if section_question_count > 100:
            errors.append(ValidationError(
                field=f"sections[{section_idx}].questions",
                message=f"Section '{section.title}' exceeds 100 questions ({section_question_count} questions)",
            ))

        # Per-question checks within this section
        for q_idx, question in enumerate(section.questions):
            # Question text <= 2000 characters
            if len(question.question_text) > 2000:
                errors.append(ValidationError(
                    field=f"sections[{section_idx}].questions[{q_idx}].question_text",
                    message=f"Question text exceeds 2000 characters ({len(question.question_text)} chars)",
                ))

            # Options per question <= 20
            if len(question.options) > 20:
                errors.append(ValidationError(
                    field=f"sections[{section_idx}].questions[{q_idx}].options",
                    message=f"Question has more than 20 options ({len(question.options)} options)",
                ))

            # Single select / Multi select must have >= 2 options
            if question.response_type in ("Single select", "Multi select"):
                if len(question.options) < 2:
                    errors.append(ValidationError(
                        field=f"sections[{section_idx}].questions[{q_idx}].options",
                        message=f"'{question.response_type}' question must have at least 2 options (got {len(question.options)})",
                    ))

            # Option text <= 2000 characters (each option)
            for opt_idx, option in enumerate(question.options):
                if len(option.text) > 2000:
                    errors.append(ValidationError(
                        field=f"sections[{section_idx}].questions[{q_idx}].options[{opt_idx}].text",
                        message=f"Option text exceeds 2000 characters ({len(option.text)} chars)",
                    ))

    # Total questions > 0
    if total_questions == 0:
        errors.append(ValidationError(
            field="questions",
            message="Assessment contains zero questions",
        ))

    # Total questions <= 750
    if total_questions > 750:
        errors.append(ValidationError(
            field="questions",
            message=f"Assessment exceeds 750 total questions ({total_questions} questions)",
        ))

    return errors


# ---------------------------------------------------------------------------
# XLSX export
# ---------------------------------------------------------------------------


def format_correct_answer(question: Question) -> int | str:
    """Format the correct_answer field according to the bulk-upload rules.

    Formatting rules by response_type:
      - Single select: integer (1-based index of correct option) - must be numeric type in XLSX
      - Multi select: JSON list of integers as string (e.g., "[1, 2, 4]")
      - Text: JSON list of strings (e.g., '["answer1", "answer2"]')
      - Yes/No: "YES" or "NO"
      - True/False: "TRUE" or "FALSE"
      - Pass/Fail: "PASS" or "FAIL"
      - Number: the numeric value as int
      - Percentage: the numeric value as int
      - Free text: empty string (no correct answer)

    Falls back to question.correct_answer if already set and response_type
    doesn't match a known formatting rule.
    """
    rt = question.response_type

    if rt == "Single select":
        # Find the 1-based index of the correct option - must be int for the template
        for idx, opt in enumerate(question.options, start=1):
            if opt.correct:
                return idx
        # Fallback: use existing correct_answer as int if possible
        try:
            return int(question.correct_answer)
        except (ValueError, TypeError):
            return question.correct_answer

    if rt == "Multi select":
        # Collect 1-based indices of all correct options
        indices = [idx for idx, opt in enumerate(question.options, start=1) if opt.correct]
        if indices:
            # Format as "[1, 2, 4]" - the template validates this pattern
            return "[" + ", ".join(str(i) for i in indices) + "]"
        # Fallback: use existing correct_answer
        return question.correct_answer

    if rt == "Text":
        # Collect text of all correct options as a JSON list of strings
        correct_texts = [opt.text for opt in question.options if opt.correct]
        if correct_texts:
            return json.dumps(correct_texts)
        # Fallback: if correct_answer is already a JSON list, use it
        return question.correct_answer

    if rt == "Yes/No":
        # Determine from options or existing correct_answer
        for opt in question.options:
            if opt.correct:
                return opt.text.upper() if opt.text.upper() in ("YES", "NO") else "YES"
        ca = question.correct_answer.strip().upper()
        return ca if ca in ("YES", "NO") else question.correct_answer

    if rt == "True/False":
        # Determine from options or existing correct_answer
        for opt in question.options:
            if opt.correct:
                return opt.text.upper() if opt.text.upper() in ("TRUE", "FALSE") else "TRUE"
        ca = question.correct_answer.strip().upper()
        return ca if ca in ("TRUE", "FALSE") else question.correct_answer

    if rt == "Pass/Fail":
        for opt in question.options:
            if opt.correct:
                return opt.text.upper() if opt.text.upper() in ("PASS", "FAIL") else "PASS"
        ca = question.correct_answer.strip().upper()
        return ca if ca in ("PASS", "FAIL") else question.correct_answer

    if rt in ("Number", "Percentage"):
        return question.correct_answer

    if rt == "Free text":
        return question.correct_answer

    # Unknown type - return as-is
    return question.correct_answer


# Static content for the Instructions sheet (mirrors an example LMS
# bulk-upload template; adapt to your LMS if its template differs)
_INSTRUCTIONS_CONTENT: list[str | None] = [
    "The Excel file should contain the following sheets:",
    "Sections sheet: Consisting of section titles and descriptions",
    "Language sheets: Separate sheets for each supported language of the evaluation, containing questions and their respective localizations",
    None,
    "In the Sections sheet:",
    "Provide localizations for section titles and descriptions for all languages horizontally",
    "Place the section titles and descriptions side by side",
    None,
    "General Constraints:",
    "Maximum number of questions allowed in bulk upload is 750",
    "Maximum number of questions per section can be less than or equal to 100",
    None,
    "Question Types:",
    "The question types vary for different evaluation types (Checklist, Survey, and Assessments)",
    "Refer to the sample sheets for reference on question types for each evaluation type",
    None,
    "Default Language:",
    "Do not edit default language texts, they are only added for reference in the download",
    "Add the default key for the default questions sheet",
    None,
    "Question IDs:",
    "Question IDs are added to update existing questions",
    "If no question ID is provided, the system assumes it as a new question",
    "You can delete and add questions as needed",
    "To add or delete questions, download the file, make changes, and re-upload",
    "The entire evaluation will be replaced with the questions uploaded in the file",
    "Do not add question IDs manually, as it will cause the upload to fail",
    "New questions do not need a question ID",
    None,
    "Column Structure:",
    "The columns in the questions sheet vary according to the evaluation type",
    "For example, Assessments will have a question score column, but not Checklists and Surveys",
    "Check the template and validate before uploading",
    None,
    "Error Handling:",
    "When a file is invalid, errors will be displayed",
    "You can download the file to see the list of errors",
    None,
    "Options per Question:",
    "Maximum number of options per question is 20",
    "All options need to follow a serial order, and no option can be missed in between",
    None,
    "Mandatory/Optional Questions:",
    "Ensure to provide whether a question is mandatory or optional for Checklists and Surveys",
    "For Assessments, all questions will be mandatory by default",
    None,
    "Uploading and Saving:",
    "Uploading a file will save the questions to the draft",
    None,
    "Correct Answer Patterns in Assessments:",
    "Single select: number (e.g., 1)",
    "Multi-select: list of numbers (e.g., [1, 2])",
    'Text: list of strings with each string limit of 150 characters and an overall length of 2000 (e.g., ["abcd", "efgh"])',
    "Number: a valid number (e.g., 30)",
    "YES/NO: YES or NO (e.g., YES)",
    "TRUE/FALSE: TRUE or FALSE (e.g., FALSE)",
    "PASS/FAIL: PASS or FAIL (e.g., PASS)",
    "Percentage: number from 0-100 (e.g., 50)",
    None,
    "Text Limitations:",
    "All text should limit its character count to 2000",
]


def _import_openpyxl():
    """Import openpyxl on first use so validation-only runs work without it."""
    try:
        import openpyxl
    except ImportError:
        print(
            "ERROR: openpyxl not installed (needed to write the XLSX files).\n"
            "Install with: pip install openpyxl",
            file=sys.stderr,
        )
        sys.exit(1)
    return openpyxl


def write_xlsx(assessment: Assessment, output_path: Path) -> None:
    """Generate the bulk-upload XLSX from validated assessment data.

    Creates workbook with:
      - "Instructions" sheet: static content describing the template format
      - "Sections" sheet: Language row + section titles/descriptions
      - Default language question sheet (e.g., "English (US) (d)"): all questions

    The question sheet columns:
      Section no, Question id, Question text, Response type,
      Option 1, Option 1 explanation, Option 2, Option 2 explanation, ...,
      Option 20, Option 20 explanation,
      Correct answer, Correct answer explanation, Question score

    Args:
        assessment: Validated Assessment object with sections and questions.
        output_path: Path where the XLSX file will be written.
    """
    openpyxl = _import_openpyxl()

    wb = openpyxl.Workbook()

    # --- Instructions sheet ---
    ws_instructions = wb.active
    ws_instructions.title = "Instructions"
    for line in _INSTRUCTIONS_CONTENT:
        ws_instructions.append([line])

    # --- Sections sheet ---
    ws_sections = wb.create_sheet("Sections")

    # Header row: Language, Section 1 title, Section 1 description, Section 2 title, ...
    sections_header = ["Language"]
    for idx in range(1, len(assessment.sections) + 1):
        sections_header.append(f"Section {idx} title")
        sections_header.append(f"Section {idx} description")
    ws_sections.append(sections_header)

    # Data row for the default language
    sections_row: list[str | None] = [assessment.language]
    for section in assessment.sections:
        sections_row.append(section.title)
        sections_row.append(section.description or "")
    ws_sections.append(sections_row)

    # --- Default language question sheet ---
    # The template requires the (d) suffix to mark the default language sheet
    sheet_name = f"{assessment.language} (d)"
    ws_questions = wb.create_sheet(sheet_name)

    # Build header row
    # Fixed columns: Section no, Question id, Question text, Response type
    # Then Option 1, Option 1 explanation, ..., Option 20, Option 20 explanation
    # Then Correct answer, Correct answer explanation, Question score
    max_options = 20
    header: list[str] = ["Section no", "Question id", "Question text", "Response type"]
    for i in range(1, max_options + 1):
        header.append(f"Option {i}")
        header.append(f"Option {i} explanation")
    header.append("Correct answer")
    header.append("Correct answer explanation")
    header.append("Question score")
    ws_questions.append(header)

    # Write question rows
    for section_idx, section in enumerate(assessment.sections, start=1):
        for question in section.questions:
            row: list[Any] = [
                section_idx,       # Section no
                None,              # Question id (left blank for new questions)
                question.question_text,
                question.response_type,
            ]

            # Options (up to 20 pairs of text + explanation)
            for i in range(max_options):
                if i < len(question.options):
                    row.append(question.options[i].text)
                    row.append(question.options[i].explanation or None)
                else:
                    row.append(None)
                    row.append(None)

            # Correct answer (formatted per the bulk-upload rules)
            row.append(format_correct_answer(question))
            row.append(question.correct_answer_explanation or None)
            row.append(question.score)

            ws_questions.append(row)

    # Ensure output directory exists and save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(output_path))


def write_metadata_xlsx(assessment: Assessment, output_path: Path) -> None:
    """Generate the metadata XLSX carrying the evaluation title/description.

    Creates workbook with:
      - "Instructions" sheet: guidance on the metadata format
      - "Metadata" sheet: Language, Title, Description columns

    The example template requires exactly these two sheet names. This file
    is uploaded separately from the assessment questions XLSX.

    Args:
        assessment: Assessment object with name and description.
        output_path: Path where the Metadata XLSX file will be written.
    """
    openpyxl = _import_openpyxl()

    wb = openpyxl.Workbook()

    # --- Instructions sheet ---
    ws_instructions = wb.active
    ws_instructions.title = "Instructions"
    instructions = [
        "Add all languages selected on the UI in the Metadata sheet",
        "Title, Description should be valid strings",
        "Title should not exceed 250 characters",
        "Description should not exceed 5000 characters",
        "Get the language names from the UI when selected.",
        "Ignore html tags when the file is downloaded, you can remove or keep the tags as is while uploading.",
        "Please download the sample template from the upload file pop up.",
    ]
    for line in instructions:
        ws_instructions.append([line])

    # --- Metadata sheet ---
    ws_metadata = wb.create_sheet("Metadata")
    ws_metadata.append(["Language", "Title", "Description"])
    ws_metadata.append([assessment.language, assessment.name, assessment.description])

    # Ensure output directory exists and save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(output_path))


# ---------------------------------------------------------------------------
# assessment.yaml loading
# ---------------------------------------------------------------------------


def parse_assessment_yaml(yaml_path: Path) -> tuple[list[Section], dict]:
    """Parse assessment.yaml into Section/Question objects.

    Reads the YAML file, maps the structure to Section and Question dataclass
    objects, and returns a tuple of (sections, metadata).

    The metadata dict contains top-level keys like name, description,
    passing_score, time_limit_minutes, and language.

    On YAML parse errors or missing required fields, prints an error to stderr
    and exits with code 1.

    Returns (sections, metadata) tuple.
    """
    yaml = _import_yaml()

    # Read and parse YAML
    try:
        content = yaml_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: Cannot read assessment YAML file '{yaml_path}': {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        print(f"ERROR: Failed to parse assessment YAML '{yaml_path}': {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, dict):
        print(f"ERROR: Assessment YAML '{yaml_path}' must be a mapping, got {type(data).__name__}", file=sys.stderr)
        sys.exit(1)

    # Extract metadata (top-level keys excluding sections and questions)
    metadata: dict = {}
    for key in ("name", "description", "passing_score", "time_limit_minutes", "language"):
        if key in data:
            metadata[key] = data[key]

    # Parse sections
    sections_data = data.get("sections", [])
    if not isinstance(sections_data, list):
        print(f"ERROR: 'sections' in '{yaml_path}' must be a list", file=sys.stderr)
        sys.exit(1)

    sections_by_title: dict[str, Section] = {}
    sections: list[Section] = []
    for idx, sec in enumerate(sections_data):
        if not isinstance(sec, dict):
            print(
                f"ERROR: Section {idx + 1} in '{yaml_path}' must be a mapping",
                file=sys.stderr,
            )
            sys.exit(1)
        title = sec.get("title")
        if not title:
            print(
                f"ERROR: Section {idx + 1} in '{yaml_path}' is missing required 'title' field",
                file=sys.stderr,
            )
            sys.exit(1)
        section = Section(title=title, description=sec.get("description", ""))
        sections.append(section)
        sections_by_title[title] = section

    # Parse questions
    questions_data = data.get("questions", [])
    if not isinstance(questions_data, list):
        print(f"ERROR: 'questions' in '{yaml_path}' must be a list", file=sys.stderr)
        sys.exit(1)

    for idx, q_dict in enumerate(questions_data):
        if not isinstance(q_dict, dict):
            print(
                f"ERROR: Question {idx + 1} in '{yaml_path}' must be a mapping",
                file=sys.stderr,
            )
            sys.exit(1)

        # Validate required fields
        question_text = q_dict.get("question_text")
        if not question_text:
            print(
                f"ERROR: Question {idx + 1} in '{yaml_path}' is missing required 'question_text' field",
                file=sys.stderr,
            )
            sys.exit(1)

        response_type = q_dict.get("response_type")
        if not response_type:
            print(
                f"ERROR: Question {idx + 1} in '{yaml_path}' is missing required 'response_type' field",
                file=sys.stderr,
            )
            sys.exit(1)

        if response_type not in VALID_RESPONSE_TYPES:
            print(
                f"ERROR: Question {idx + 1} in '{yaml_path}' has invalid response_type "
                f"'{response_type}'. Must be one of: {', '.join(VALID_RESPONSE_TYPES)}",
                file=sys.stderr,
            )
            sys.exit(1)

        # Parse options
        options_data = q_dict.get("options", [])
        if not isinstance(options_data, list):
            print(
                f"ERROR: Question {idx + 1} in '{yaml_path}': 'options' must be a list",
                file=sys.stderr,
            )
            sys.exit(1)

        options: list[Option] = []
        for opt_idx, opt in enumerate(options_data):
            if not isinstance(opt, dict):
                print(
                    f"ERROR: Question {idx + 1}, option {opt_idx + 1} in '{yaml_path}' must be a mapping",
                    file=sys.stderr,
                )
                sys.exit(1)
            opt_text = opt.get("text")
            if not opt_text:
                print(
                    f"ERROR: Question {idx + 1}, option {opt_idx + 1} in '{yaml_path}' "
                    f"is missing required 'text' field",
                    file=sys.stderr,
                )
                sys.exit(1)
            options.append(
                Option(
                    text=opt_text,
                    correct=bool(opt.get("correct", False)),
                    explanation=opt.get("explanation", ""),
                )
            )

        # Build Question object
        question = Question(
            question_text=question_text,
            response_type=response_type,
            options=options,
            correct_answer=str(q_dict.get("correct_answer", "")),
            correct_answer_explanation=q_dict.get("correct_answer_explanation", ""),
            score=int(q_dict.get("score", 1)),
        )

        # Assign question to section
        section_title = q_dict.get("section")
        if section_title:
            if section_title in sections_by_title:
                sections_by_title[section_title].questions.append(question)
            else:
                # Create a new section for unmatched section references
                new_section = Section(title=section_title)
                new_section.questions.append(question)
                sections.append(new_section)
                sections_by_title[section_title] = new_section
        else:
            # If no section specified, add to a default section
            default_title = "General"
            if default_title not in sections_by_title:
                default_section = Section(title=default_title)
                sections.append(default_section)
                sections_by_title[default_title] = default_section
            sections_by_title[default_title].questions.append(question)

    return sections, metadata


def extract_knowledge_checks(lesson_content: str, module_id: str = "") -> list[Question]:
    """Parse {% knowledgeCheck %} blocks from lesson markdown.

    A helper for assessment authoring (see the power's
    ``assessment-authoring.md`` steering file): the knowledge checks already
    embedded in lessons are a ready-made question source the agent can lift
    into assessment.yaml instead of re-deriving them from prose.

    Scans lesson content for {% knowledgeCheck %} / {% endknowledgeCheck %}
    block pairs, parses the YAML content within each block, and maps to
    Question objects.

    Type mapping:
      - Exactly 1 option with correct=true -> "Single select"
      - Multiple options with correct=true -> "Multi select"

    On malformed blocks (YAML parse errors, missing required fields), prints a
    warning to stderr with the module_id and approximate line number, then
    continues processing remaining blocks.

    Args:
        lesson_content: The full lesson markdown content (may include frontmatter).
        module_id: Module identifier for error reporting in warnings.

    Returns:
        List of Question objects extracted from knowledgeCheck blocks.
    """
    yaml = _import_yaml()

    questions: list[Question] = []

    # Split content into lines for line-number tracking
    lines = lesson_content.split("\n")
    total_lines = len(lines)

    # Find all knowledgeCheck block pairs by scanning lines
    i = 0
    while i < total_lines:
        line = lines[i]
        stripped = line.strip()

        # Detect opening tag
        if stripped == "{% knowledgeCheck %}":
            block_start_line = i + 1  # 1-based line number for reporting
            block_lines: list[str] = []
            i += 1
            found_end = False

            # Collect lines until closing tag
            while i < total_lines:
                inner_line = lines[i]
                inner_stripped = inner_line.strip()
                if inner_stripped == "{% endknowledgeCheck %}":
                    found_end = True
                    i += 1
                    break
                block_lines.append(inner_line)
                i += 1

            if not found_end:
                print(
                    f"WARNING: [{module_id}] line {block_start_line}: "
                    f"knowledgeCheck block has no closing tag, skipping",
                    file=sys.stderr,
                )
                continue

            # Parse the YAML content of this block
            yaml_content = "\n".join(block_lines)
            try:
                parsed = yaml.safe_load(yaml_content)
            except yaml.YAMLError as exc:
                print(
                    f"WARNING: [{module_id}] line {block_start_line}: "
                    f"Failed to parse YAML in knowledgeCheck block: {exc}",
                    file=sys.stderr,
                )
                continue

            if not isinstance(parsed, dict):
                print(
                    f"WARNING: [{module_id}] line {block_start_line}: "
                    f"knowledgeCheck block did not parse as a YAML mapping, skipping",
                    file=sys.stderr,
                )
                continue

            # Extract question text
            question_text = parsed.get("question")
            if not question_text:
                print(
                    f"WARNING: [{module_id}] line {block_start_line}: "
                    f"knowledgeCheck block missing 'question' field, skipping",
                    file=sys.stderr,
                )
                continue

            # Extract options
            raw_options = parsed.get("options")
            if not raw_options or not isinstance(raw_options, list):
                print(
                    f"WARNING: [{module_id}] line {block_start_line}: "
                    f"knowledgeCheck block missing or invalid 'options' field, skipping",
                    file=sys.stderr,
                )
                continue

            options: list[Option] = []
            valid_block = True
            for opt_idx, raw_opt in enumerate(raw_options):
                if not isinstance(raw_opt, dict):
                    print(
                        f"WARNING: [{module_id}] line {block_start_line}: "
                        f"Option {opt_idx + 1} is not a mapping, skipping block",
                        file=sys.stderr,
                    )
                    valid_block = False
                    break

                opt_text = raw_opt.get("text")
                if not opt_text:
                    print(
                        f"WARNING: [{module_id}] line {block_start_line}: "
                        f"Option {opt_idx + 1} missing 'text' field, skipping block",
                        file=sys.stderr,
                    )
                    valid_block = False
                    break

                opt_correct = bool(raw_opt.get("correct", False))
                opt_feedback = raw_opt.get("feedback", "")

                options.append(Option(
                    text=str(opt_text),
                    correct=opt_correct,
                    explanation=str(opt_feedback) if opt_feedback else "",
                ))

            if not valid_block:
                continue

            if len(options) < 2:
                print(
                    f"WARNING: [{module_id}] line {block_start_line}: "
                    f"knowledgeCheck block has fewer than 2 options, skipping",
                    file=sys.stderr,
                )
                continue

            # Determine response type based on number of correct options
            correct_count = sum(1 for opt in options if opt.correct)
            if correct_count > 1:
                response_type = "Multi select"
            else:
                response_type = "Single select"

            # Format correct_answer
            if response_type == "Single select":
                correct_answer = ""
                for idx, opt in enumerate(options, start=1):
                    if opt.correct:
                        correct_answer = str(idx)
                        break
            else:
                # Multi select: JSON list of 1-based indices
                indices = [idx for idx, opt in enumerate(options, start=1) if opt.correct]
                correct_answer = json.dumps(indices)

            # Build correct_answer_explanation from the correct option(s) feedback
            correct_explanations = [opt.explanation for opt in options if opt.correct and opt.explanation]
            correct_answer_explanation = " ".join(correct_explanations) if correct_explanations else ""

            questions.append(Question(
                question_text=str(question_text),
                response_type=response_type,
                options=options,
                correct_answer=correct_answer,
                correct_answer_explanation=correct_answer_explanation,
            ))
        else:
            i += 1

    return questions


# ---------------------------------------------------------------------------
# Configuration and CLI
# ---------------------------------------------------------------------------


def resolve_config(cli_args: Namespace, course_config: dict, yaml_metadata: dict | None = None) -> Assessment:
    """Merge CLI args > assessment.yaml metadata > course.yaml > defaults.

    Precedence: CLI arguments override the assessment.yaml top-level metadata,
    which overrides the course.yaml ``assessment:`` block, which overrides
    course-level fallbacks (course.title for name, scorm.passing_score for
    passing_score, course.tags for tags), which override hardcoded defaults.

    Returns an Assessment with all metadata fields resolved (no sections yet).
    """
    yaml_metadata = yaml_metadata or {}
    assessment_cfg = dict(course_config.get("assessment", {}) or {})
    assessment_cfg.update(yaml_metadata)
    course_info = course_config.get("course", {}) or {}
    scorm_cfg = course_config.get("scorm", {}) or {}

    # name: cli > assessment.name > course.title
    cli_name = getattr(cli_args, "name", None)
    name = (
        cli_name if cli_name is not None
        else assessment_cfg.get("name") if assessment_cfg.get("name") is not None
        else course_info.get("title") or ""
    )

    # description: cli > assessment.description > ""
    cli_desc = getattr(cli_args, "description", None)
    description = (
        cli_desc if cli_desc is not None
        else assessment_cfg.get("description") if assessment_cfg.get("description") is not None
        else ""
    )

    # passing_score: cli > assessment.passing_score > scorm.passing_score > 80
    cli_ps = getattr(cli_args, "passing_score", None)
    passing_score = (
        cli_ps if cli_ps is not None
        else assessment_cfg.get("passing_score") if assessment_cfg.get("passing_score") is not None
        else scorm_cfg.get("passing_score") if scorm_cfg.get("passing_score") is not None
        else 80
    )

    # time_limit_minutes: cli > assessment.time_limit_minutes > None
    cli_tl = getattr(cli_args, "time_limit", None)
    time_limit_minutes = (
        cli_tl if cli_tl is not None
        else assessment_cfg.get("time_limit_minutes") if assessment_cfg.get("time_limit_minutes") is not None
        else None
    )

    # language: cli > assessment.language > "English (US)"
    cli_lang = getattr(cli_args, "language", None)
    language = (
        cli_lang if cli_lang is not None
        else assessment_cfg.get("language") if assessment_cfg.get("language") is not None
        else "English (US)"
    )

    # tags: cli > assessment.tags > course.tags > []
    cli_tags = getattr(cli_args, "tags", None)
    tags = (
        cli_tags if cli_tags is not None
        else assessment_cfg.get("tags") if assessment_cfg.get("tags") is not None
        else course_info.get("tags") if course_info.get("tags") is not None
        else []
    )

    return Assessment(
        name=name,
        description=description,
        passing_score=passing_score,
        time_limit_minutes=time_limit_minutes,
        language=language,
        tags=tags,
    )


def parse_args(argv: list[str] | None = None) -> Namespace:
    """Parse CLI arguments for the assessment builder.

    Returns an argparse.Namespace with all configured options.
    Pass argv for testing; defaults to sys.argv when None.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate an authored assessment.yaml and export LMS bulk-upload XLSX files.",
        prog="build_assessment",
    )

    # Positional argument
    parser.add_argument(
        "course_name",
        nargs="?",
        default="sample-course",
        help="Course name to build the assessment for (default: sample-course)",
    )

    # Metadata arguments
    parser.add_argument(
        "--name",
        default=None,
        help="Assessment name (overrides assessment.yaml and course.yaml)",
    )
    parser.add_argument(
        "--description",
        default=None,
        help="Assessment description (overrides assessment.yaml and course.yaml)",
    )
    parser.add_argument(
        "--passing-score",
        type=int,
        default=None,
        help="Passing score percentage 0-100 (overrides assessment.yaml and course.yaml)",
    )
    parser.add_argument(
        "--time-limit",
        type=int,
        default=None,
        help="Time limit in minutes (overrides assessment.yaml and course.yaml)",
    )
    parser.add_argument(
        "--tags",
        nargs="+",
        default=None,
        help="Assessment tags (overrides assessment.yaml and course.yaml)",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Default language for the assessment sheet (default: English (US))",
    )

    return parser.parse_args(argv)


def main() -> None:
    """CLI entry point for the assessment builder.

    Orchestrates the pipeline: parse CLI -> load assessment.yaml ->
    resolve config -> validate -> write XLSX.
    """
    args = parse_args()
    yaml = _import_yaml()

    # Resolve course directory
    repo_root = Path(__file__).resolve().parent.parent
    course_dir = repo_root / "courses" / args.course_name

    # Read course.yaml
    course_yaml_path = course_dir / "course.yaml"
    if not course_yaml_path.exists():
        print(f"ERROR: course.yaml not found at '{course_yaml_path}'", file=sys.stderr)
        sys.exit(1)

    try:
        course_config = yaml.safe_load(course_yaml_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        print(f"ERROR: Failed to parse course.yaml: {exc}", file=sys.stderr)
        sys.exit(1)

    # Load the authored assessment.yaml (required - this script never
    # generates questions; see the power's assessment-authoring.md steering)
    assessment_yaml_path = course_dir / "assessment.yaml"
    if not assessment_yaml_path.exists():
        print(
            f"ERROR: assessment.yaml not found at '{assessment_yaml_path}'.\n"
            "Author it by hand or with your agent (see the power's "
            "assessment-authoring.md steering file), then re-run.",
            file=sys.stderr,
        )
        sys.exit(1)

    sections, yaml_metadata = parse_assessment_yaml(assessment_yaml_path)

    # Resolve configuration (CLI > assessment.yaml > course.yaml > defaults)
    assessment = resolve_config(args, course_config, yaml_metadata)
    assessment.sections = sections

    # Validate assessment constraints
    errors = validate_assessment(assessment)
    if errors:
        print("Validation errors:", file=sys.stderr)
        for err in errors:
            print(f"  [{err.severity}] {err.field}: {err.message}", file=sys.stderr)
        sys.exit(1)

    # Write XLSX output
    output_path = course_dir / "build" / "assessment.xlsx"
    write_xlsx(assessment, output_path)

    # Write Metadata XLSX (evaluation title/description for the upload)
    metadata_path = course_dir / "build" / "metadata.xlsx"
    write_metadata_xlsx(assessment, metadata_path)

    # Print success summary to stdout
    total_questions = sum(len(s.questions) for s in assessment.sections)
    print(f"\nOutput: {output_path}")
    print(f"Metadata: {metadata_path}")
    print(f"Sections: {len(assessment.sections)}", end="")
    # Include per-section question counts
    section_details = ", ".join(
        f"{s.title} ({len(s.questions)})" for s in assessment.sections
    )
    if section_details:
        print(f" [{section_details}]")
    else:
        print()
    print(f"Total questions: {total_questions}")


if __name__ == "__main__":
    main()
