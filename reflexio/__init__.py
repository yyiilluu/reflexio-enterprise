"""Reflexio enterprise package — bootstraps open_source submodule onto sys.path."""

import sys
from pathlib import Path

_submodule_src = Path(__file__).resolve().parent.parent / "open_source" / "reflexio"
if str(_submodule_src) not in sys.path:
    sys.path.insert(0, str(_submodule_src))
