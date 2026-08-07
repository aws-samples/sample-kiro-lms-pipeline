"""Unit tests for _check_module_end in LessonLinter."""

from __future__ import annotations

import pytest

# Loaded once by tests/preflight/conftest.py (hyphenated script filename)
import lint_lessons

LessonLinter = lint_lessons.LessonLinter
LintError = lint_lessons.LintError

FRONTMATTER = "---\nmodule_id: m1\ntitle: Test\n---\n"


@pytest.fixture
def make_linter(tmp_path):
    """Create a LessonLinter with a temp file containing the given content."""

    def _make(content: str) -> LessonLinter:
        lesson_path = tmp_path / "lesson.md"
        lesson_path.write_text(content, encoding="utf-8")
        return LessonLinter(lesson_path, tmp_path)

    return _make


class TestModuleEnd:
    """Tests for _check_module_end method."""

    def test_module_end_on_final_page_no_errors(self, make_linter):
        """A single {% moduleEnd %} on the final page produces no errors."""
        content = (
            FRONTMATTER
            + "Page 1 content\n"
            + "{% nextPage %}\n"
            + "Page 2 content\n"
            + "{% moduleEnd %}\n"
        )
        linter = make_linter(content)
        errors = linter._check_module_end()
        assert errors == []

    def test_module_end_single_page_no_errors(self, make_linter):
        """A single-page lesson with {% moduleEnd %} produces no errors."""
        content = FRONTMATTER + "Only page\n{% moduleEnd %}\n"
        linter = make_linter(content)
        errors = linter._check_module_end()
        assert errors == []

    def test_missing_module_end_is_warning(self, make_linter):
        """A lesson without {% moduleEnd %} reports a warning, not an error."""
        content = FRONTMATTER + "Page content, no end marker.\n"
        linter = make_linter(content)
        errors = linter._check_module_end()
        assert len(errors) == 1
        assert errors[0].severity == "warning"
        assert "missing" in errors[0].message.lower()
        assert errors[0].line is None

    def test_duplicate_module_end_is_error(self, make_linter):
        """More than one {% moduleEnd %} reports an error listing every line."""
        content = (
            FRONTMATTER
            + "Page 1\n"
            + "{% moduleEnd %}\n"
            + "{% nextPage %}\n"
            + "Page 2\n"
            + "{% moduleEnd %}\n"
        )
        linter = make_linter(content)
        errors = linter._check_module_end()
        assert len(errors) == 1
        assert errors[0].severity == "error"
        assert "2 times" in errors[0].message
        assert "lines 6, 9" in errors[0].message
        assert errors[0].line == 6  # First occurrence

    def test_module_end_on_non_final_page_is_error(self, make_linter):
        """{% moduleEnd %} on a page before the last reports an error."""
        content = (
            FRONTMATTER
            + "Page 1\n"
            + "{% moduleEnd %}\n"
            + "{% nextPage %}\n"
            + "Page 2 content\n"
        )
        linter = make_linter(content)
        errors = linter._check_module_end()
        assert len(errors) == 1
        assert errors[0].severity == "error"
        assert "final page" in errors[0].message
        assert errors[0].line == 6  # Line of the marker

    def test_wired_into_validate(self, make_linter):
        """_check_module_end is called as part of validate()."""
        content = FRONTMATTER + "Page content, no end marker.\n"
        linter = make_linter(content)
        errors = linter.validate()
        module_end_errors = [
            e for e in errors if "moduleEnd" in e.message
        ]
        assert len(module_end_errors) == 1
        assert module_end_errors[0].severity == "warning"
