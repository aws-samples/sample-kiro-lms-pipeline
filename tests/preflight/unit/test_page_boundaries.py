"""Unit tests for _check_page_boundaries in LessonLinter."""

from __future__ import annotations

from pathlib import Path

import pytest

# Loaded once by tests/preflight/conftest.py (hyphenated script filename)
import lint_lessons

LessonLinter = lint_lessons.LessonLinter
LintError = lint_lessons.LintError


@pytest.fixture
def tmp_lesson(tmp_path: Path):
    """Helper to create a temporary lesson file with given content."""

    def _create(content: str) -> Path:
        lesson = tmp_path / "lesson.md"
        lesson.write_text(content, encoding="utf-8")
        return lesson

    return _create


class TestPageBoundaries:
    """Tests for _check_page_boundaries."""

    def test_single_page_with_content(self, tmp_lesson):
        """A single page with content should produce no errors."""
        lesson_path = tmp_lesson("---\nmodule_id: m1\ntitle: Test\n---\nSome content here.")
        linter = LessonLinter(lesson_path, lesson_path.parent)
        linter._check_frontmatter()  # Parse frontmatter first to set self.content
        errors = linter._check_page_boundaries()
        assert errors == []

    def test_multiple_pages_all_with_content(self, tmp_lesson):
        """Multiple pages all with content should produce no errors."""
        content = (
            "---\nmodule_id: m1\ntitle: Test\n---\n"
            "Page 1 content\n"
            "{% nextPage %}\n"
            "Page 2 content\n"
            "{% nextPage %}\n"
            "Page 3 content"
        )
        lesson_path = tmp_lesson(content)
        linter = LessonLinter(lesson_path, lesson_path.parent)
        linter._check_frontmatter()
        errors = linter._check_page_boundaries()
        assert errors == []

    def test_empty_page_reports_error(self, tmp_lesson):
        """An empty page (whitespace only) should report an error with page number."""
        content = (
            "---\nmodule_id: m1\ntitle: Test\n---\n"
            "Page 1 content\n"
            "{% nextPage %}\n"
            "   \n"
            "{% nextPage %}\n"
            "Page 3 content"
        )
        lesson_path = tmp_lesson(content)
        linter = LessonLinter(lesson_path, lesson_path.parent)
        linter._check_frontmatter()
        errors = linter._check_page_boundaries()
        assert len(errors) == 1
        assert errors[0].severity == "error"
        assert "Page 2" in errors[0].message
        assert "empty" in errors[0].message.lower()

    def test_empty_first_page(self, tmp_lesson):
        """An empty first page should report an error for page 1."""
        content = (
            "---\nmodule_id: m1\ntitle: Test\n---\n"
            "\n"
            "{% nextPage %}\n"
            "Page 2 content"
        )
        lesson_path = tmp_lesson(content)
        linter = LessonLinter(lesson_path, lesson_path.parent)
        linter._check_frontmatter()
        errors = linter._check_page_boundaries()
        assert len(errors) == 1
        assert "Page 1" in errors[0].message

    def test_empty_last_page(self, tmp_lesson):
        """An empty last page should report an error for the final page."""
        content = (
            "---\nmodule_id: m1\ntitle: Test\n---\n"
            "Page 1 content\n"
            "{% nextPage %}\n"
            "  \n"
        )
        lesson_path = tmp_lesson(content)
        linter = LessonLinter(lesson_path, lesson_path.parent)
        linter._check_frontmatter()
        errors = linter._check_page_boundaries()
        assert len(errors) == 1
        assert "Page 2" in errors[0].message

    def test_multiple_empty_pages(self, tmp_lesson):
        """Multiple empty pages should each report an error."""
        content = (
            "---\nmodule_id: m1\ntitle: Test\n---\n"
            "\n"
            "{% nextPage %}\n"
            "\n"
            "{% nextPage %}\n"
            "Page 3 content"
        )
        lesson_path = tmp_lesson(content)
        linter = LessonLinter(lesson_path, lesson_path.parent)
        linter._check_frontmatter()
        errors = linter._check_page_boundaries()
        assert len(errors) == 2
        assert "Page 1" in errors[0].message
        assert "Page 2" in errors[1].message

    def test_no_nextpage_markers(self, tmp_lesson):
        """A file with no nextPage markers is a single page — no error if it has content."""
        content = "---\nmodule_id: m1\ntitle: Test\n---\nJust one page of content."
        lesson_path = tmp_lesson(content)
        linter = LessonLinter(lesson_path, lesson_path.parent)
        linter._check_frontmatter()
        errors = linter._check_page_boundaries()
        assert errors == []

    def test_page_count_equals_markers_plus_one(self, tmp_lesson):
        """N markers should produce N+1 pages."""
        # 3 markers → 4 pages
        content = (
            "---\nmodule_id: m1\ntitle: Test\n---\n"
            "P1\n{% nextPage %}\nP2\n{% nextPage %}\nP3\n{% nextPage %}\nP4"
        )
        lesson_path = tmp_lesson(content)
        linter = LessonLinter(lesson_path, lesson_path.parent)
        linter._check_frontmatter()
        errors = linter._check_page_boundaries()
        assert errors == []

    def test_error_severity_is_error(self, tmp_lesson):
        """Empty page errors should have severity 'error'."""
        content = (
            "---\nmodule_id: m1\ntitle: Test\n---\n"
            "{% nextPage %}\n"
            "Page 2"
        )
        lesson_path = tmp_lesson(content)
        linter = LessonLinter(lesson_path, lesson_path.parent)
        linter._check_frontmatter()
        errors = linter._check_page_boundaries()
        # Page 1 is empty (content before first marker is just empty)
        assert len(errors) == 1
        assert errors[0].severity == "error"

    def test_module_id_in_error(self, tmp_lesson):
        """Errors should include the correct module_id."""
        content = (
            "---\nmodule_id: m1\ntitle: Test\n---\n"
            "\n{% nextPage %}\nPage 2"
        )
        lesson_path = tmp_lesson(content)
        linter = LessonLinter(lesson_path, lesson_path.parent)
        linter._check_frontmatter()
        errors = linter._check_page_boundaries()
        assert len(errors) == 1
        assert errors[0].module_id == lesson_path.parent.name
