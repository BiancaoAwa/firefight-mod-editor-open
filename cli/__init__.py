"""CLI package: scope resolution, document access, commands and entry point.

The CLI is the only writer of user-visible output and the only caller of the
package core; it never mutates entity files in this milestone (read and export
only).
"""
