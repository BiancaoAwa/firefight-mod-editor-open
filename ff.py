"""Editor entry point: ``python ff.py <scope> <command> [selector] [key=value ...]``.

The implementation lives in ``core/``; kept at the editor root so a checkout runs with no install step.
"""

from core.cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
