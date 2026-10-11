"""Entry point of the MCP server: ``python -m core.mcp [--write]`` (docs/mcp.md section 7)."""

import sys

from core.mcp.server import main

if __name__ == "__main__":
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    sys.exit(main())
