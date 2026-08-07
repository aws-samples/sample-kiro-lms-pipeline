"""Shared test setup: import the hyphenated pipeline scripts exactly once.

``scripts/lint-lessons.py`` and ``scripts/validate-scorm.py`` have hyphenated
filenames, so a plain ``import`` cannot load them. This conftest loads each
script once via importlib and registers it in ``sys.modules`` under an
underscored name. pytest imports this conftest before collecting any test
module below it, so test files can simply do::

    import lint_lessons
    import validate_scorm
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


def _load_script(module_name: str, file_name: str):
    """Load ``scripts/<file_name>`` as ``module_name``, once per session."""
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(
        module_name, _SCRIPTS_DIR / file_name
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_load_script("lint_lessons", "lint-lessons.py")
_load_script("validate_scorm", "validate-scorm.py")
