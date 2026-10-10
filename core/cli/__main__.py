"""``python -m core.cli`` entry point.

Run it from the editor root (the directory holding ``core/``); the launchers set that directory themselves.
"""

from core.cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
