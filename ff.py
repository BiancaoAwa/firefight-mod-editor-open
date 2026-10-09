"""Editor entry point: ``python ff.py <scope> <command> [selector] [key=value ...]``.

Kept at the repository root so the demo runs from a checkout with no install
step; the implementation lives in ``cli/`` (docs/cli.md).
"""

from cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
