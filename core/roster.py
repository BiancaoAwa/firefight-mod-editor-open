"""The plain-text rosters a project declares in its settings.

A roster is one entry per line, and an entry is the name of a document under ``Data/``.  ``//``
starts a comment -- the whole line, or a note trailing the entry -- and a line that is only a
comment names the group the entries after it belong to.  Which files are rosters is decided by
the project's own settings and not here (core/cli/commands.py, ``declared_lists``).  This module
only reads a roster and compares it with the documents that are there; the two row writes reuse
``core.web.tables`` and go through ``core.edit``, so they are planned, journalled and undoable
like every other change (docs/cli.md section 4.14).
"""

COMMENT = "//"


def parse(text: str) -> list[dict]:
    """One dict per physical line: number, entry, trailing note, group, whether it carries an entry.

    The number counts every physical line, comments and blanks included, so it is the number a
    reader sees in an editor.
    """
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    rows: list[dict] = []
    group = ""
    for number, raw in enumerate(lines, start=1):
        body, marker, note = raw.partition(COMMENT)
        entry = body.strip()
        note = note.strip()
        if not entry and note:
            group = note
        rows.append(
            {
                "line": number,
                "value": entry,
                "note": note,
                "group": group,
                "blank": not entry,
            }
        )
    return rows


def names(rows: list[dict]) -> list[str]:
    """Every entry in file order."""
    return [row["value"] for row in rows if row["value"]]


def line_of(rows: list[dict], value: str) -> int:
    """The line one entry sits on, counting every physical line; 0 when it is not there."""
    for row in rows:
        if row["value"] == value:
            return row["line"]
    return 0


def gaps(listed: dict[str, list[str]], documents: dict[str, str]) -> dict:
    """The two ways a roster and the documents on disk disagree.

    ``missing`` pairs a roster with an entry no document answers; ``orphans`` names a document
    that no roster lists, which is a document the game cannot reach.  ``documents`` maps the name
    an entry would carry to the project-relative path of the document behind it.
    """
    missing = [
        {"roster": roster, "name": name}
        for roster, entries in sorted(listed.items())
        for name in entries
        if name not in documents
    ]
    named = {name for entries in listed.values() for name in entries}
    orphans = [
        {"name": name, "path": documents[name]} for name in sorted(documents) if name not in named
    ]
    return {"missing": missing, "orphans": orphans}
