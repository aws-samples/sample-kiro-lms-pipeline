"""Unit tests for LessonLinter._check_image_paths.

Validates Requirements 4.1, 4.2, 4.3:
- Resolve markdown image references relative to module build directory
- Report error for paths that don't resolve to existing files
- Handle both relative paths and paths with ../ prefixes
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Loaded once by tests/preflight/conftest.py (hyphenated script filename)
import lint_lessons

LessonLinter = lint_lessons.LessonLinter
LintError = lint_lessons.LintError


def _make_lesson(tmp_path: Path, content: str) -> tuple[Path, Path]:
    """Create a lesson.md in a temporary module build directory.

    Returns (lesson_path, module_build_dir).
    """
    module_dir = tmp_path / "build" / "module-1"
    module_dir.mkdir(parents=True, exist_ok=True)
    lesson_path = module_dir / "lesson.md"
    lesson_path.write_text(content, encoding="utf-8")
    return lesson_path, module_dir


class TestImagePathResolution:
    """Tests for _check_image_paths method."""

    def test_no_images_returns_no_errors(self, tmp_path: Path) -> None:
        """A lesson with no image references produces no errors."""
        content = "---\nmodule_id: m1\ntitle: Test\n---\nSome content.\n"
        lesson_path, module_dir = _make_lesson(tmp_path, content)
        linter = LessonLinter(lesson_path, module_dir)
        errors = linter._check_image_paths()
        assert errors == []

    def test_existing_image_no_error(self, tmp_path: Path) -> None:
        """An image reference pointing to an existing file produces no error."""
        content = "---\nmodule_id: m1\ntitle: Test\n---\n![alt](visuals/slide_01.png)\n"
        lesson_path, module_dir = _make_lesson(tmp_path, content)

        # Create the image file
        visuals_dir = module_dir / "visuals"
        visuals_dir.mkdir(parents=True, exist_ok=True)
        (visuals_dir / "slide_01.png").write_bytes(b"\x89PNG")

        linter = LessonLinter(lesson_path, module_dir)
        errors = linter._check_image_paths()
        assert errors == []

    def test_missing_image_reports_error(self, tmp_path: Path) -> None:
        """An image reference to a non-existent file reports an error."""
        content = "---\nmodule_id: m1\ntitle: Test\n---\n![alt](visuals/missing.png)\n"
        lesson_path, module_dir = _make_lesson(tmp_path, content)

        linter = LessonLinter(lesson_path, module_dir)
        errors = linter._check_image_paths()

        assert len(errors) == 1
        assert errors[0].severity == "error"
        assert "visuals/missing.png" in errors[0].message
        assert errors[0].line == 5  # line 5 in the file (after frontmatter)
        assert errors[0].module_id == "module-1"

    def test_relative_path_with_parent_prefix(self, tmp_path: Path) -> None:
        """Paths with ../ prefixes are resolved correctly."""
        content = "---\nmodule_id: m1\ntitle: Test\n---\n![alt](../shared/image.png)\n"
        lesson_path, module_dir = _make_lesson(tmp_path, content)

        # Create the image file one level up from module_dir
        shared_dir = module_dir.parent / "shared"
        shared_dir.mkdir(parents=True, exist_ok=True)
        (shared_dir / "image.png").write_bytes(b"\x89PNG")

        linter = LessonLinter(lesson_path, module_dir)
        errors = linter._check_image_paths()
        assert errors == []

    def test_relative_path_with_parent_prefix_missing(self, tmp_path: Path) -> None:
        """Paths with ../ that don't resolve to existing files report errors."""
        content = "---\nmodule_id: m1\ntitle: Test\n---\n![alt](../shared/missing.png)\n"
        lesson_path, module_dir = _make_lesson(tmp_path, content)

        linter = LessonLinter(lesson_path, module_dir)
        errors = linter._check_image_paths()

        assert len(errors) == 1
        assert errors[0].severity == "error"
        assert "../shared/missing.png" in errors[0].message

    def test_multiple_images_on_same_line(self, tmp_path: Path) -> None:
        """Multiple image references on the same line are all checked."""
        content = (
            "---\nmodule_id: m1\ntitle: Test\n---\n"
            "![a](img1.png) text ![b](img2.png)\n"
        )
        lesson_path, module_dir = _make_lesson(tmp_path, content)

        # Only create img1.png
        (module_dir / "img1.png").write_bytes(b"\x89PNG")

        linter = LessonLinter(lesson_path, module_dir)
        errors = linter._check_image_paths()

        assert len(errors) == 1
        assert "img2.png" in errors[0].message

    def test_multiple_images_across_lines(self, tmp_path: Path) -> None:
        """Image references on different lines report correct line numbers."""
        content = (
            "---\nmodule_id: m1\ntitle: Test\n---\n"
            "![a](exists.png)\n"
            "Some text\n"
            "![b](missing1.png)\n"
            "More text\n"
            "![c](missing2.png)\n"
        )
        lesson_path, module_dir = _make_lesson(tmp_path, content)
        (module_dir / "exists.png").write_bytes(b"\x89PNG")

        linter = LessonLinter(lesson_path, module_dir)
        errors = linter._check_image_paths()

        assert len(errors) == 2
        assert errors[0].line == 7  # "![b](missing1.png)" is line 7
        assert errors[1].line == 9  # "![c](missing2.png)" is line 9
        assert "missing1.png" in errors[0].message
        assert "missing2.png" in errors[1].message

    def test_image_with_empty_alt_text(self, tmp_path: Path) -> None:
        """Image references with empty alt text are still checked."""
        content = "---\nmodule_id: m1\ntitle: Test\n---\n![](visuals/img.png)\n"
        lesson_path, module_dir = _make_lesson(tmp_path, content)

        linter = LessonLinter(lesson_path, module_dir)
        errors = linter._check_image_paths()

        assert len(errors) == 1
        assert "visuals/img.png" in errors[0].message

    def test_unreadable_file_returns_empty(self, tmp_path: Path) -> None:
        """If the lesson file cannot be read, return no errors gracefully."""
        lesson_path = tmp_path / "nonexistent" / "lesson.md"
        module_dir = tmp_path / "nonexistent"

        linter = LessonLinter(lesson_path, module_dir)
        errors = linter._check_image_paths()
        assert errors == []
