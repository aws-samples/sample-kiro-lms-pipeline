"""Unit tests for _check_knowledge_check_density in LessonLinter.

lesson-authoring.md's rule (kept in sync with this check): roughly 1-2
knowledge checks per 4 pages, minimum 1 per module regardless of length.
"""

import pytest

# Loaded once by tests/preflight/conftest.py (hyphenated script filename)
import lint_lessons

LessonLinter = lint_lessons.LessonLinter


def _body(page_count: int, kc_count: int) -> str:
    """Build a lesson body with the given page and knowledge-check counts."""
    pages = ["Some page content."] * page_count
    body = "\n\n{% nextPage %}\n\n".join(pages)
    kc_block = (
        "\n\n{% knowledgeCheck %}\n"
        "question: \"Q?\"\n"
        "options:\n"
        "  - text: \"A\"\n"
        "    correct: true\n"
        "{% endknowledgeCheck %}\n"
    )
    return body + kc_block * kc_count


def _density_warnings(errors):
    return [e for e in errors if "knowledge check(s) across" in e.message or "exceeds the recommended" in e.message]


class TestKnowledgeCheckDensity:
    """Tests for _check_knowledge_check_density method."""

    def test_short_module_zero_checks_warns(self, tmp_path):
        """A <=6 page module with zero knowledge checks gets a density warning."""
        lesson = tmp_path / "lesson.md"
        lesson.write_text(_body(page_count=3, kc_count=0))
        linter = LessonLinter(lesson, tmp_path)
        warnings = _density_warnings(linter._check_knowledge_checks())
        assert len(warnings) == 1
        assert warnings[0].severity == "warning"

    def test_short_module_one_check_no_warning(self, tmp_path):
        """A <=6 page module with one knowledge check meets the minimum."""
        lesson = tmp_path / "lesson.md"
        lesson.write_text(_body(page_count=3, kc_count=1))
        linter = LessonLinter(lesson, tmp_path)
        assert _density_warnings(linter._check_knowledge_checks()) == []

    def test_long_module_one_check_warns(self, tmp_path):
        """A module over 6 pages needs at least 2 knowledge checks, not 1."""
        lesson = tmp_path / "lesson.md"
        lesson.write_text(_body(page_count=8, kc_count=1))
        linter = LessonLinter(lesson, tmp_path)
        warnings = _density_warnings(linter._check_knowledge_checks())
        assert len(warnings) == 1
        assert "Only 1 knowledge check(s) across 8 pages" in warnings[0].message

    def test_long_module_two_checks_no_warning(self, tmp_path):
        """A module over 6 pages with 2 knowledge checks meets the minimum."""
        lesson = tmp_path / "lesson.md"
        lesson.write_text(_body(page_count=8, kc_count=2))
        linter = LessonLinter(lesson, tmp_path)
        assert _density_warnings(linter._check_knowledge_checks()) == []

    def test_too_many_checks_warns(self, tmp_path):
        """Far more checks than the page count supports exceeds the range."""
        lesson = tmp_path / "lesson.md"
        lesson.write_text(_body(page_count=2, kc_count=5))
        linter = LessonLinter(lesson, tmp_path)
        warnings = _density_warnings(linter._check_knowledge_checks())
        assert len(warnings) == 1
        assert "exceeds the recommended roughly 1-2 per 4 pages" in warnings[0].message

    def test_density_warning_is_not_an_error(self, tmp_path):
        """Density issues are warnings, never severity=error."""
        lesson = tmp_path / "lesson.md"
        lesson.write_text(_body(page_count=3, kc_count=0))
        linter = LessonLinter(lesson, tmp_path)
        errors = linter._check_knowledge_checks()
        assert not any(e.severity == "error" for e in errors)
