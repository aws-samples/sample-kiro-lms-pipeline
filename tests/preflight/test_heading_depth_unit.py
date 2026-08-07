"""Unit tests for _check_heading_depth in LessonLinter."""

import pytest

# Loaded once by tests/preflight/conftest.py (hyphenated script filename)
import lint_lessons

LessonLinter = lint_lessons.LessonLinter
LintError = lint_lessons.LintError


@pytest.fixture
def make_linter(tmp_path):
    """Create a LessonLinter with a temp file containing the given content."""

    def _make(content: str) -> LessonLinter:
        lesson_path = tmp_path / "lesson.md"
        lesson_path.write_text(content, encoding="utf-8")
        return LessonLinter(lesson_path, tmp_path)

    return _make


class TestHeadingDepthBasic:
    """Test basic heading depth detection."""

    def test_no_deep_headings(self, make_linter):
        content = "# H1\n## H2\n### H3\nSome text\n"
        linter = make_linter(content)
        errors = linter._check_heading_depth()
        assert errors == []

    def test_depth_4_heading(self, make_linter):
        content = "#### Deep Heading\n"
        linter = make_linter(content)
        errors = linter._check_heading_depth()
        assert len(errors) == 1
        assert errors[0].severity == "warning"
        assert errors[0].line == 1
        assert "Deep Heading" in errors[0].message

    def test_depth_5_heading(self, make_linter):
        content = "##### Very Deep\n"
        linter = make_linter(content)
        errors = linter._check_heading_depth()
        assert len(errors) == 1
        assert errors[0].severity == "warning"
        assert "Very Deep" in errors[0].message

    def test_depth_6_heading(self, make_linter):
        content = "###### Deepest\n"
        linter = make_linter(content)
        errors = linter._check_heading_depth()
        assert len(errors) == 1
        assert errors[0].severity == "warning"
        assert "Deepest" in errors[0].message

    def test_multiple_deep_headings(self, make_linter):
        content = "# H1\n#### H4\ntext\n##### H5\n"
        linter = make_linter(content)
        errors = linter._check_heading_depth()
        assert len(errors) == 2
        assert errors[0].line == 2
        assert errors[1].line == 4


class TestHeadingDepthCodeBlocks:
    """Test that headings inside code blocks are ignored."""

    def test_heading_inside_backtick_fence(self, make_linter):
        content = "```\n#### Should be ignored\n```\n"
        linter = make_linter(content)
        errors = linter._check_heading_depth()
        assert errors == []

    def test_heading_inside_tilde_fence(self, make_linter):
        content = "~~~\n#### Should be ignored\n~~~\n"
        linter = make_linter(content)
        errors = linter._check_heading_depth()
        assert errors == []

    def test_heading_outside_fence_detected(self, make_linter):
        content = "```\n#### Ignored\n```\n#### Not Ignored\n"
        linter = make_linter(content)
        errors = linter._check_heading_depth()
        assert len(errors) == 1
        assert "Not Ignored" in errors[0].message

    def test_heading_before_and_after_fence(self, make_linter):
        content = "#### Before\n```\n#### Inside\n```\n#### After\n"
        linter = make_linter(content)
        errors = linter._check_heading_depth()
        assert len(errors) == 2
        assert "Before" in errors[0].message
        assert "After" in errors[1].message

    def test_backtick_fence_with_language(self, make_linter):
        content = "```python\n#### Ignored\n```\n"
        linter = make_linter(content)
        errors = linter._check_heading_depth()
        assert errors == []


class TestHeadingDepthEdgeCases:
    """Test edge cases for heading depth detection."""

    def test_hashes_without_space_not_heading(self, make_linter):
        # ####NoSpace is not a valid ATX heading
        content = "####NoSpace\n"
        linter = make_linter(content)
        errors = linter._check_heading_depth()
        assert errors == []

    def test_heading_with_frontmatter(self, make_linter):
        content = "---\nmodule_id: test\ntitle: Test\n---\n#### Deep\n"
        linter = make_linter(content)
        errors = linter._check_heading_depth()
        assert len(errors) == 1
        assert "Deep" in errors[0].message
        assert errors[0].line == 5

    def test_empty_file(self, make_linter):
        content = ""
        linter = make_linter(content)
        errors = linter._check_heading_depth()
        assert errors == []

    def test_all_severity_is_warning(self, make_linter):
        content = "#### H4\n##### H5\n###### H6\n"
        linter = make_linter(content)
        errors = linter._check_heading_depth()
        assert all(e.severity == "warning" for e in errors)
