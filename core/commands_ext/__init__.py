"""Extension point for commands declared outside core.

A module here exports ``COMMANDS`` as a tuple of ``core.registry.Command``; it is
imported on first use, so adding a command means adding a file, not editing the
core command table.
"""
