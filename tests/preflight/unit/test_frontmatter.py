"""Unit tests for _check_frontmatter in LessonLinter."""

from __future__ import annotations

from pathlib import Path

import pytest

# Loaded once by tests/preflight/conftest.py (hyphenated script filename)
import lint_lessons

LessonLinter = lint_lessons.LessonLinter
LintError = lint_lessons.LintError

_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture
def tmp_lesson(tmp_path: Path):
    """Helper to create a temporary lesson file with given content."""

    def _create(content: str) -> Path:
        lesson = tmp_path / "lesson.md"
        lesson.write_text(content, encoding="utf-8")
        return lesson

    return _create


class TestCheckFrontmatter:
    """Tests for _check_frontmatter method."""

    def test_valid_frontmatter_no_errors(self, tmp_lesson):
        """Valid YAML with required fields produces no errors."""
        content = '---\nmodule_id: mod-1\ntitle: "My Title"\n---\n\n# Body\n'
        lesson_path = tmp_lesson(content)
        linter = LessonLinter(lesson_path, lesson_path.parent)
        errors = linter._check_frontmatter()

        assert len(errors) == 0
        assert linter.frontmatter == {"module_id": "mod-1", "title": "My Title"}
        assert linter.content is not None

    def test_missing_opening_delimiter(self, tmp_lesson):
        """File without opening --- reports missing frontmatter error."""
        content = "# Just a heading\n\nSome content.\n"
        lesson_path = tmp_lesson(content)
        linter = LessonLinter(lesson_path, lesson_path.parent)
        errors = linter._check_frontmatter()

        assert len(errors) == 1
        assert errors[0].severity == "error"
        assert "missing" in errors[0].message.lower()
        assert errors[0].line == 1

    def test_missing_closing_delimiter(self, tmp_lesson):
        """File with opening --- but no closing --- reports error."""
        content = "---\nmodule_id: mod-1\ntitle: Test\n"
        lesson_path = tmp_lesson(content)
        linter = LessonLinter(lesson_path, lesson_path.parent)
        errors = linter._check_frontmatter()

        assert len(errors) == 1
        assert errors[0].severity == "error"
        assert "closing" in errors[0].message.lower()

    def test_invalid_yaml_syntax(self, tmp_lesson):
        """Syntactically invalid YAML reports an error."""
        content = '---\nmodule_id: mod-1\ntitle: "unclosed string\n---\n\n# Body\n'
        lesson_path = tmp_lesson(content)
        linter = LessonLinter(lesson_path, lesson_path.parent)
        errors = linter._check_frontmatter()

        assert len(errors) == 1
        assert errors[0].severity == "error"
        assert "invalid" in errors[0].message.lower()

    def test_missing_module_id(self, tmp_lesson):
        """Missing module_id field reports an error."""
        content = '---\ntitle: "My Title"\n---\n\n# Body\n'
        lesson_path = tmp_lesson(content)
        linter = LessonLinter(lesson_path, lesson_path.parent)
        errors = linter._check_frontmatter()

        assert len(errors) == 1
        assert errors[0].severity == "error"
        assert "module_id" in errors[0].message

    def test_missing_title(self, tmp_lesson):
        """Missing title field reports an error."""
        content = "---\nmodule_id: mod-1\n---\n\n# Body\n"
        lesson_path = tmp_lesson(content)
        linter = LessonLinter(lesson_path, lesson_path.parent)
        errors = linter._check_frontmatter()

        assert len(errors) == 1
        assert errors[0].severity == "error"
        assert "title" in errors[0].message

    def test_empty_module_id(self, tmp_lesson):
        """Empty string module_id reports an error."""
        content = '---\nmodule_id: ""\ntitle: "My Title"\n---\n\n# Body\n'
        lesson_path = tmp_lesson(content)
        linter = LessonLinter(lesson_path, lesson_path.parent)
        errors = linter._check_frontmatter()

        assert len(errors) == 1
        assert errors[0].severity == "error"
        assert "module_id" in errors[0].message
        assert "empty" in errors[0].message.lower()

    def test_empty_title(self, tmp_lesson):
        """Whitespace-only title reports an error."""
        content = '---\nmodule_id: mod-1\ntitle: "   "\n---\n\n# Body\n'
        lesson_path = tmp_lesson(content)
        linter = LessonLinter(lesson_path, lesson_path.parent)
        errors = linter._check_frontmatter()

        assert len(errors) == 1
        assert errors[0].severity == "error"
        assert "title" in errors[0].message
        assert "empty" in errors[0].message.lower()

    def test_both_fields_missing(self, tmp_lesson):
        """Both required fields missing reports two errors."""
        content = "---\ndescription: something\n---\n\n# Body\n"
        lesson_path = tmp_lesson(content)
        linter = LessonLinter(lesson_path, lesson_path.parent)
        errors = linter._check_frontmatter()

        assert len(errors) == 2
        messages = [e.message for e in errors]
        assert any("module_id" in m for m in messages)
        assert any("title" in m for m in messages)

    def test_frontmatter_not_a_mapping(self, tmp_lesson):
        """YAML that parses to a non-dict (e.g., a list) reports an error."""
        content = "---\n- item1\n- item2\n---\n\n# Body\n"
        lesson_path = tmp_lesson(content)
        linter = LessonLinter(lesson_path, lesson_path.parent)
        errors = linter._check_frontmatter()

        assert len(errors) == 1
        assert "mapping" in errors[0].message.lower()

    def test_content_stored_after_frontmatter(self, tmp_lesson):
        """Body content after frontmatter is stored in self.content."""
        content = "---\nmodule_id: mod-1\ntitle: Test\n---\n\n# Body content\n"
        lesson_path = tmp_lesson(content)
        linter = LessonLinter(lesson_path, lesson_path.parent)
        linter._check_frontmatter()

        assert linter.content is not None
        assert "# Body content" in linter.content

    def test_frontmatter_stored_for_other_checks(self, tmp_lesson):
        """Parsed frontmatter is stored as self.frontmatter."""
        content = "---\nmodule_id: mod-1\ntitle: Test\nextra: value\n---\n\n# Body\n"
        lesson_path = tmp_lesson(content)
        linter = LessonLinter(lesson_path, lesson_path.parent)
        linter._check_frontmatter()

        assert linter.frontmatter is not None
        assert linter.frontmatter["extra"] == "value"

    def test_wired_into_validate(self, tmp_lesson):
        """_check_frontmatter is called as part of validate()."""
        content = "# No frontmatter\n\nJust content.\n"
        lesson_path = tmp_lesson(content)
        linter = LessonLinter(lesson_path, lesson_path.parent)
        errors = linter.validate()

        # Should have at least the frontmatter error
        frontmatter_errors = [
            e for e in errors if "frontmatter" in e.message.lower()
        ]
        assert len(frontmatter_errors) >= 1

    def test_file_not_found(self, tmp_path):
        """Non-existent file reports a read error."""
        lesson_path = tmp_path / "nonexistent.md"
        linter = LessonLinter(lesson_path, tmp_path)
        errors = linter._check_frontmatter()

        assert len(errors) == 1
        assert errors[0].severity == "error"
        assert "Cannot read" in errors[0].message

    def test_valid_fixture_file(self):
        """The valid_lesson.md fixture passes frontmatter validation."""
        fixture = _FIXTURES_DIR / "valid_lesson.md"
        linter = LessonLinter(fixture, fixture.parent)
        errors = linter._check_frontmatter()

        assert len(errors) == 0
        assert linter.frontmatter is not None
        assert linter.frontmatter["module_id"] == "module-test"
        assert linter.frontmatter["title"] == "Introduction to Cloud Resilience"

    def test_valid_fixture_full_validate(self):
        """The valid_lesson.md fixture passes the full validate() end to end."""
        fixture = _FIXTURES_DIR / "valid_lesson.md"
        linter = LessonLinter(fixture, fixture.parent)
        errors = linter.validate()

        assert errors == []

    def test_invalid_fixture_file(self):
        """The invalid_frontmatter.md fixture reports YAML error."""
        fixture = _FIXTURES_DIR / "invalid_frontmatter.md"
        linter = LessonLinter(fixture, fixture.parent)
        errors = linter._check_frontmatter()

        assert len(errors) >= 1
        assert errors[0].severity == "error"
        assert "invalid" in errors[0].message.lower()
