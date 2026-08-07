"""Shared test setup: make scripts/build_assessment.py importable.

Unlike the hyphenated pipeline scripts, ``build_assessment.py`` has a normal
module name, so putting ``scripts/`` on ``sys.path`` is enough for test files
to simply do::

    import build_assessment
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
