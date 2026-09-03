#!/usr/bin/env python
"""Thin shim for the invocation spelling in the wave prompt.

    python scripts/double_jet.py --config configs/double_jet.yaml

Running this file directly puts `scripts/` -- not the repository root -- on `sys.path`, so
`import double_jet` would fail. The two lines below fix that and hand off to the real entry point.
The canonical spelling, and the one the job scripts use, is `python -m double_jet` (plan §3).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from double_jet.cli import main  # noqa: E402  (import must follow the sys.path fix)

if __name__ == "__main__":
    sys.exit(main())
