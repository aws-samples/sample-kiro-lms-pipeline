#!/usr/bin/env python3
"""
Lint lesson.md files across all modules in a course.

Validates structural correctness of lesson files before the SCORM build:
frontmatter, page boundaries, knowledge checks, image paths, heading depth,
and module end markers.

Usage:
    python scripts/lint-lessons.py [course-name]

The course name defaults to 'sample-course' when omitted. The script resolves
the course directory as courses/<course-name>/ relative to the repository root.
"""

from __future__ import annotations

import argparse
import dataclasses
import re
import sys
from pathlib import Path

import yaml


# --- data models -------------------------------------------------------------


@dataclasses.dataclass
class LintError:
    """A single validation error or warning."""

    module_id: str
    line: int | None  # Source line number (1-indexed), None for module-level errors
    message: str
    severity: str  # "error" or "warning"


# --- constants ---------------------------------------------------------------

REQUIRED_FRONTMATTER_FIELDS = {"module_id", "title"}


# --- linter ------------------------------------------------------------------


class LessonLinter:
    """Validates a single lesson.md file."""

    def __init__(self, lesson_path: Path, module_build_dir: Path) -> None:
        self.lesson_path = lesson_path
        self.module_build_dir = module_build_dir
        self.module_id = module_build_dir.name
        self.frontmatter: dict | None = None
        self.content: str | None = None

    def validate(self) -> list[LintError]:
        """Run all checks, return collected errors."""
        errors: list[LintError] = []
        errors.extend(self._check_frontmatter())
        errors.extend(self._check_page_boundaries())
        errors.extend(self._check_knowledge_checks())
        errors.extend(self._check_image_paths())
        errors.extend(self._check_heading_depth())
        errors.extend(self._check_module_end())
        return errors

    def _check_frontmatter(self) -> list[LintError]:
        """Validate YAML frontmatter between --- delimiters.

        Reads the lesson file, extracts the YAML block between the first pair
        of --- delimiters, parses it, and verifies required fields are present
        and non-empty. Stores parsed frontmatter as self.frontmatter and the
        body content (after frontmatter) as self.content for use by other checks.
        """
        errors: list[LintError] = []

        try:
            raw = self.lesson_path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(
                LintError(
                    module_id=self.module_id,
                    line=None,
                    message=f"Cannot read lesson file: {exc}",
                    severity="error",
                )
            )
            return errors

        lines = raw.split("\n")

        # Check for opening --- delimiter
        if not lines or lines[0].strip() != "---":
            errors.append(
                LintError(
                    module_id=self.module_id,
                    line=1,
                    message="Frontmatter is missing (no opening --- delimiter)",
                    severity="error",
                )
            )
            self.content = raw
            return errors

        # Find closing --- delimiter
        closing_index = None
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                closing_index = i
                break

        if closing_index is None:
            errors.append(
                LintError(
                    module_id=self.module_id,
                    line=1,
                    message="Frontmatter is missing (no closing --- delimiter)",
                    severity="error",
                )
            )
            self.content = raw
            return errors

        # Extract and parse YAML
        yaml_block = "\n".join(lines[1:closing_index])
        self.content = "\n".join(lines[closing_index + 1:])

        try:
            parsed = yaml.safe_load(yaml_block)
        except yaml.YAMLError as exc:
            # Determine line number within the frontmatter block
            error_line: int | None = None
            if hasattr(exc, "problem_mark") and exc.problem_mark is not None:
                # +2: +1 for 0-indexed to 1-indexed, +1 for the opening ---
                error_line = exc.problem_mark.line + 2
            errors.append(
                LintError(
                    module_id=self.module_id,
                    line=error_line,
                    message=f"Frontmatter YAML is invalid: {exc}",
                    severity="error",
                )
            )
            return errors

        # YAML parsed successfully but might not be a mapping
        if not isinstance(parsed, dict):
            errors.append(
                LintError(
                    module_id=self.module_id,
                    line=1,
                    message="Frontmatter must be a YAML mapping (key-value pairs)",
                    severity="error",
                )
            )
            return errors

        self.frontmatter = parsed

        # Verify required fields are present and non-empty
        for field in sorted(REQUIRED_FRONTMATTER_FIELDS):
            value = parsed.get(field)
            if value is None:
                errors.append(
                    LintError(
                        module_id=self.module_id,
                        line=None,
                        message=f"Required frontmatter field '{field}' is missing",
                        severity="error",
                    )
                )
            elif isinstance(value, str) and not value.strip():
                errors.append(
                    LintError(
                        module_id=self.module_id,
                        line=None,
                        message=f"Required frontmatter field '{field}' is empty",
                        severity="error",
                    )
                )

        return errors

    def _get_body(self) -> str:
        """Return the lesson body content after frontmatter.

        If self.content is already set (e.g. by _check_frontmatter), use it.
        Otherwise, read the file and strip the frontmatter block.
        """
        if hasattr(self, "content") and self.content is not None:
            return self.content

        try:
            raw = self.lesson_path.read_text(encoding="utf-8")
        except OSError:
            return ""

        # Strip frontmatter: content between first and second '---' lines
        lines = raw.split("\n")
        if lines and lines[0].strip() == "---":
            for i, line in enumerate(lines[1:], start=1):
                if line.strip() == "---":
                    return "\n".join(lines[i + 1 :])
        # No frontmatter found — entire content is the body
        return raw

    def _check_page_boundaries(self) -> list[LintError]:
        """Validate that every page between {% nextPage %} markers has content.

        Splits the body on {% nextPage %} markers. Page 1 is content before
        the first marker, page N is content between (N-1)th and Nth marker,
        and the final page is content after the last marker. Reports an error
        for any page that contains only whitespace.
        """
        errors: list[LintError] = []
        body = self._get_body()

        pages = body.split("{% nextPage %}")

        for page_num, page_content in enumerate(pages, start=1):
            if not page_content.strip():
                errors.append(
                    LintError(
                        module_id=self.module_id,
                        line=None,
                        message=f"Page {page_num} is empty (no non-whitespace content)",
                        severity="error",
                    )
                )

        return errors

    def _check_knowledge_checks(self) -> list[LintError]:
        """Validate knowledge check blocks have correct answers and are properly closed.

        Scans for {% knowledgeCheck %} / {% endknowledgeCheck %} blocks.
        Reports errors when:
        - A block has no option with `correct: true`
        - A {% knowledgeCheck %} has no matching {% endknowledgeCheck %}
        """
        errors: list[LintError] = []
        try:
            content = self.lesson_path.read_text(encoding="utf-8")
        except OSError:
            return errors

        lines = content.splitlines()
        open_pattern = re.compile(r"\{%\s*knowledgeCheck\s*%\}")
        close_pattern = re.compile(r"\{%\s*endknowledgeCheck\s*%\}")
        correct_pattern = re.compile(r"correct:\s*true")

        i = 0
        while i < len(lines):
            if open_pattern.search(lines[i]):
                open_line = i + 1  # 1-indexed
                # Search for matching close
                block_lines: list[str] = []
                j = i + 1
                found_close = False
                while j < len(lines):
                    if close_pattern.search(lines[j]):
                        found_close = True
                        break
                    block_lines.append(lines[j])
                    j += 1

                if not found_close:
                    errors.append(
                        LintError(
                            module_id=self.module_id,
                            line=open_line,
                            message="Unclosed knowledge check block (missing {% endknowledgeCheck %})",
                            severity="error",
                        )
                    )
                    # No matching close found; skip to end
                    break
                else:
                    # Check if block has at least one correct: true
                    block_content = "\n".join(block_lines)
                    if not correct_pattern.search(block_content):
                        errors.append(
                            LintError(
                                module_id=self.module_id,
                                line=open_line,
                                message="Knowledge check has no option with correct: true",
                                severity="error",
                            )
                        )
                    i = j + 1  # Move past the endknowledgeCheck line
                    continue
            i += 1

        errors.extend(self._check_knowledge_check_density(content))
        return errors

    def _check_knowledge_check_density(self, content: str) -> list[LintError]:
        """Warn when knowledge-check count looks off relative to page count.

        lesson-authoring.md recommends roughly 1-2 knowledge checks per 4
        pages, with a minimum of 1 per module regardless of length. This is
        a soft warning, not an error - page content varies enough that this
        is a nudge to reconsider, not a rule to enforce exactly.
        """
        errors: list[LintError] = []
        open_count = len(re.findall(r"\{%\s*knowledgeCheck\s*%\}", content))
        page_count = len(self._get_body().split("{% nextPage %}"))

        recommended_min = max(1, round(page_count / 4))
        recommended_max = max(recommended_min, round(page_count / 2))
        if open_count < recommended_min:
            errors.append(
                LintError(
                    module_id=self.module_id,
                    line=None,
                    message=(
                        f"Only {open_count} knowledge check(s) across {page_count} pages; "
                        "lesson-authoring.md recommends roughly 1-2 per 4 pages "
                        "(minimum 1 per module)"
                    ),
                    severity="warning",
                )
            )
        elif open_count > recommended_max:
            errors.append(
                LintError(
                    module_id=self.module_id,
                    line=None,
                    message=(
                        f"{open_count} knowledge checks across {page_count} pages exceeds "
                        "the recommended roughly 1-2 per 4 pages"
                    ),
                    severity="warning",
                )
            )

        return errors

    def _check_heading_depth(self) -> list[LintError]:
        """Detect ATX headings at depth 4+ outside of fenced code blocks.

        Iterates through the file content line by line, tracking whether we
        are inside a fenced code block (``` or ~~~). For lines outside code
        blocks, checks if the line starts with #### or more # characters
        followed by a space. Reports a warning for each such heading.
        """
        errors: list[LintError] = []

        try:
            raw = self.lesson_path.read_text(encoding="utf-8")
        except OSError:
            return errors

        lines = raw.split("\n")
        in_code_block = False

        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Toggle code block state on fence lines (``` or ~~~)
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_code_block = not in_code_block
                continue

            if in_code_block:
                continue

            # Check for ATX heading at depth 4+ (#### or more followed by a space)
            match = re.match(r"^(#{4,})\s+(.+)", line)
            if match:
                heading_text = match.group(2).strip()
                errors.append(
                    LintError(
                        module_id=self.module_id,
                        line=line_num,
                        message=f"Heading depth > 3: {heading_text}",
                        severity="warning",
                    )
                )

        return errors

    def _check_image_paths(self) -> list[LintError]:
        """Verify all markdown image references resolve to existing files.

        Extracts ![alt](path) patterns, resolves each path relative to the
        lesson file's parent directory (module_build_dir), and reports an error
        for any path that does not point to an existing file.
        """
        errors: list[LintError] = []
        try:
            content = self.lesson_path.read_text(encoding="utf-8")
        except OSError:
            return errors

        image_pattern = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

        for line_number, line in enumerate(content.splitlines(), start=1):
            for match in image_pattern.finditer(line):
                image_path = match.group(2).strip()
                resolved = (self.module_build_dir / image_path).resolve()
                if not resolved.is_file():
                    errors.append(
                        LintError(
                            module_id=self.module_id,
                            line=line_number,
                            message=f"Image not found: {image_path}",
                            severity="error",
                        )
                    )
        return errors

    def _check_module_end(self) -> list[LintError]:
        """Validate {% moduleEnd %} appears exactly once and on the final page.

        Searches the file content for all occurrences of {% moduleEnd %}.
        - If not found: reports a WARNING that the module end marker is missing.
        - If found more than once: reports an ERROR listing all occurrences
          with line numbers.
        - If found exactly once: determines which page it's on by splitting
          the body on {% nextPage %} markers. If it's on the final page, no
          error. If it's NOT on the final page, reports an ERROR.
        """
        errors: list[LintError] = []

        try:
            raw = self.lesson_path.read_text(encoding="utf-8")
        except OSError:
            return errors

        # Find all occurrences with line numbers
        lines = raw.split("\n")
        occurrences: list[int] = []
        for line_num, line in enumerate(lines, start=1):
            if "{% moduleEnd %}" in line:
                occurrences.append(line_num)

        if len(occurrences) == 0:
            # Missing moduleEnd — warning
            errors.append(
                LintError(
                    module_id=self.module_id,
                    line=None,
                    message="Module end marker {% moduleEnd %} is missing",
                    severity="warning",
                )
            )
        elif len(occurrences) > 1:
            # Duplicate moduleEnd — error
            line_list = ", ".join(str(ln) for ln in occurrences)
            errors.append(
                LintError(
                    module_id=self.module_id,
                    line=occurrences[0],
                    message=(
                        f"{{% moduleEnd %}} appears {len(occurrences)} times "
                        f"(lines {line_list}); must appear exactly once"
                    ),
                    severity="error",
                )
            )
        else:
            # Exactly one occurrence — check it's on the final page
            body = self._get_body()
            pages = body.split("{% nextPage %}")
            final_page = pages[-1] if pages else ""

            if "{% moduleEnd %}" not in final_page:
                errors.append(
                    LintError(
                        module_id=self.module_id,
                        line=occurrences[0],
                        message=(
                            "{% moduleEnd %} must be on the final page"
                        ),
                        severity="error",
                    )
                )

        return errors


# --- CLI and main ------------------------------------------------------------


def main() -> None:
    """CLI entry point: discover modules, lint each, report summary."""
    parser = argparse.ArgumentParser(
        description="Lint lesson.md files for a course before SCORM build."
    )
    parser.add_argument(
        "course_name",
        nargs="?",
        default="sample-course",
        metavar="course-name",
        help="Course name to lint (default: sample-course)",
    )
    args = parser.parse_args()

    # Resolve course directory relative to repo root
    repo_root = Path(__file__).resolve().parents[1]
    course_dir = repo_root / "courses" / args.course_name

    if not course_dir.exists():
        print(
            f"Error: course directory not found: {course_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Read course.yaml to discover modules
    course_yaml_path = course_dir / "course.yaml"
    if not course_yaml_path.exists():
        print(
            f"Error: course.yaml not found: {course_yaml_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        course_config = yaml.safe_load(course_yaml_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        print(
            f"Error: cannot parse course.yaml: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Extract module list from course config
    modules = course_config.get("modules", [])
    if not modules:
        print(
            "Error: no modules found in course.yaml",
            file=sys.stderr,
        )
        sys.exit(1)

    # Iterate over each module, lint its lesson.md, collect all errors
    all_errors: list[LintError] = []

    for module in modules:
        module_id = module.get("id")
        if not module_id:
            all_errors.append(
                LintError(
                    module_id="unknown",
                    line=None,
                    message="Module entry in course.yaml is missing 'id' field",
                    severity="error",
                )
            )
            continue

        module_build_dir = course_dir / "build" / module_id
        lesson_path = module_build_dir / "lesson.md"

        if not lesson_path.exists():
            all_errors.append(
                LintError(
                    module_id=module_id,
                    line=None,
                    message=f"lesson.md not found: {lesson_path}",
                    severity="error",
                )
            )
            continue

        linter = LessonLinter(lesson_path, module_build_dir)
        module_errors = linter.validate()
        all_errors.extend(module_errors)

    # Report errors grouped by module to stderr
    error_count = sum(1 for e in all_errors if e.severity == "error")
    warning_count = sum(1 for e in all_errors if e.severity == "warning")

    if all_errors:
        # Group errors by module
        errors_by_module: dict[str, list[LintError]] = {}
        for err in all_errors:
            errors_by_module.setdefault(err.module_id, []).append(err)

        for module_id, module_errors in errors_by_module.items():
            print(f"\n[{module_id}]", file=sys.stderr)
            for err in module_errors:
                location = f"line {err.line}" if err.line else "module-level"
                print(
                    f"  {err.severity.upper()}: {err.message} ({location})",
                    file=sys.stderr,
                )

    # Print summary to stdout
    module_count = len(modules)
    print(
        f"{error_count} errors, {warning_count} warnings across {module_count} modules"
    )

    # Exit with non-zero code if any errors found
    if error_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
