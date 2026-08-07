"""Unit tests for _check_knowledge_checks in LessonLinter."""

import pytest

# Loaded once by tests/preflight/conftest.py (hyphenated script filename)
import lint_lessons

LessonLinter = lint_lessons.LessonLinter
LintError = lint_lessons.LintError


class TestKnowledgeChecks:
    """Tests for _check_knowledge_checks method."""

    def test_valid_knowledge_check_no_errors(self, tmp_path):
        """A knowledge check with correct: true produces no errors."""
        lesson = tmp_path / "lesson.md"
        lesson.write_text(
            "{% knowledgeCheck %}\n"
            "question: \"What is 2+2?\"\n"
            "options:\n"
            "  - text: \"4\"\n"
            "    correct: true\n"
            "    feedback: \"Correct!\"\n"
            "  - text: \"5\"\n"
            "    correct: false\n"
            "    feedback: \"Wrong\"\n"
            "{% endknowledgeCheck %}\n"
        )
        linter = LessonLinter(lesson, tmp_path)
        errors = linter._check_knowledge_checks()
        assert len(errors) == 0

    def test_no_correct_answer_reports_error(self, tmp_path):
        """A knowledge check without correct: true reports an error."""
        lesson = tmp_path / "lesson.md"
        lesson.write_text(
            "{% knowledgeCheck %}\n"
            "question: \"What is 2+2?\"\n"
            "options:\n"
            "  - text: \"4\"\n"
            "    correct: false\n"
            "  - text: \"5\"\n"
            "    correct: false\n"
            "{% endknowledgeCheck %}\n"
        )
        linter = LessonLinter(lesson, tmp_path)
        errors = linter._check_knowledge_checks()
        assert len(errors) == 1
        assert errors[0].severity == "error"
        assert "no option with correct: true" in errors[0].message
        assert errors[0].line == 1  # Line of the opening marker

    def test_unclosed_block_reports_error(self, tmp_path):
        """A knowledgeCheck without endknowledgeCheck reports an error."""
        lesson = tmp_path / "lesson.md"
        lesson.write_text(
            "{% knowledgeCheck %}\n"
            "question: \"What is 2+2?\"\n"
            "options:\n"
            "  - text: \"4\"\n"
            "    correct: true\n"
        )
        linter = LessonLinter(lesson, tmp_path)
        errors = linter._check_knowledge_checks()
        assert len(errors) == 1
        assert errors[0].severity == "error"
        assert "Unclosed" in errors[0].message
        assert errors[0].line == 1

    def test_multiple_blocks_mixed_validity(self, tmp_path):
        """Multiple blocks: one valid, one without correct answer."""
        lesson = tmp_path / "lesson.md"
        lesson.write_text(
            "{% knowledgeCheck %}\n"
            "options:\n"
            "  - text: \"A\"\n"
            "    correct: true\n"
            "{% endknowledgeCheck %}\n"
            "\n"
            "{% knowledgeCheck %}\n"
            "options:\n"
            "  - text: \"B\"\n"
            "    correct: false\n"
            "{% endknowledgeCheck %}\n"
        )
        linter = LessonLinter(lesson, tmp_path)
        errors = [e for e in linter._check_knowledge_checks() if e.severity == "error"]
        assert len(errors) == 1
        assert "no option with correct: true" in errors[0].message
        assert errors[0].line == 7  # Second block starts at line 7

    def test_no_knowledge_checks_no_structural_errors(self, tmp_path):
        """A file with no knowledge checks produces no severity=error entries.

        It does produce a density warning (soft nudge), which is expected
        and covered separately in test_knowledge_check_density.py.
        """
        lesson = tmp_path / "lesson.md"
        lesson.write_text("Just some content without knowledge checks.\n")
        linter = LessonLinter(lesson, tmp_path)
        errors = linter._check_knowledge_checks()
        assert not any(e.severity == "error" for e in errors)

    def test_line_number_reflects_position_in_file(self, tmp_path):
        """The error line number matches the opening marker's position."""
        lesson = tmp_path / "lesson.md"
        lesson.write_text(
            "---\n"
            "module_id: test\n"
            "title: Test\n"
            "---\n"
            "Some content\n"
            "{% knowledgeCheck %}\n"
            "options:\n"
            "  - text: \"A\"\n"
            "    correct: false\n"
            "{% endknowledgeCheck %}\n"
        )
        linter = LessonLinter(lesson, tmp_path)
        errors = linter._check_knowledge_checks()
        assert len(errors) == 1
        assert errors[0].line == 6  # knowledgeCheck is on line 6

    def test_wired_into_validate(self, tmp_path):
        """_check_knowledge_checks is called as part of validate()."""
        lesson = tmp_path / "lesson.md"
        lesson.write_text(
            "{% knowledgeCheck %}\n"
            "options:\n"
            "  - text: \"A\"\n"
            "    correct: false\n"
            "{% endknowledgeCheck %}\n"
        )
        linter = LessonLinter(lesson, tmp_path)
        errors = linter.validate()
        # Should contain at least the knowledge check error
        kc_errors = [e for e in errors if "correct: true" in e.message]
        assert len(kc_errors) == 1
