"""Root conftest.

Puts the repository root on ``sys.path`` so tests can use absolute imports
without requiring a per-file ``sys.path`` shim. Pytest auto-discovers this
file at the rootdir on every collection.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
