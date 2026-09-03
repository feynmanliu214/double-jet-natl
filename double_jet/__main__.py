"""`python -m double_jet` -- the canonical entry point (plan §3)."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
