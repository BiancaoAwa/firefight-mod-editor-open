# Changelog

Notable changes are recorded here, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the version is
semantic and is written down in one place, `core/__init__.py`.

## [0.1.0] — unreleased

### Added

* The editor command line: 22 commands over two scopes, `Firefight` for the
  game's own data and any named directory for a mod project. `init`, `list`,
  `show`, `get`, `find`, `stats`, `refs`, `deps`, `check`, `set`, `add`,
  `remove`, `index`, `convert`, `settings`, `export`, `pack`, `log`, `undo`,
  `redo`, `version`, `web`. Each accepts `--json`.
* A Web UI bound to the loopback address, in Chinese and English with a
  language switch, offering the same commands behind the same gates
  (docs/web.md).
* An MCP server for two protocol families, exposing 19 tools of which 8 are
  read-only; the writing tools are registered only under `--write`
  (docs/mcp.md).
* `pack` builds an installable mod archive: `<name>-<version>.zip` holding a
  `Mod/` prefix, project documents rendered back to the stock XML, the
  project's `mod_setting.toml` rendered into `Mod/mod.txt`, and neither
  `.editor/` nor `EditorCache/` in the archive. Member timestamps are fixed,
  so two runs over the same project produce identical bytes. A document that
  cannot be rendered is reported and left out; `strict=1` refuses instead.
* `init` creates a project from nothing: `mod.toml` and an empty `Mod/Data`.
* `convert` turns the stock `.txt` documents of a scope into working `.toml`
  files under a destination project; `assets=1` also copies the scope's
  `Images/` and `Sounds/` trees byte for byte.
* `settings` translates between `Mod/mod.txt` and `mod_setting.toml` in both
  directions (`op=render`, `op=emit`).
* `index` caches the document list and the reference table under `.editor/`;
  `refs` and `deps` read the cache while its fingerprint is current and walk
  the documents again when it is not.
* An undo journal: every write appends a record holding the bytes before and
  after it. `log` lists the records and filters them by document, field,
  actor, result or time; `undo` and `redo` restore from them. `log`, `undo`
  and `redo` accept `--dry-run`.
* Editing of array and table entries in `set` (`op=append`, `op=delete`) and
  whole-document `add` and `remove`.

### Changed

* User-visible text is English throughout. The Web UI carries a Chinese
  translation of all 187 templates and a `lang=zh|en` switch.
* `export` replaces a file that is already there unless `overwrite=0` is
  given; `convert` and `settings` skip an existing destination unless
  `overwrite=1` is given.

### Known limitations

* `pack` carries everything under the project's `Mod/` directory as it stands, plus the
  project's `README.md` and `LICENSE`; `Images/` and `Sounds/` reach the archive only when
  they are already in the project directory (docs/cli.md section 4.8).
* Dangling references are reported by `check` and counted by `pack`, but
  nothing resolves them.

[0.1.0]: https://github.com/BiancaoAwa/firefight-mod-editor-open
