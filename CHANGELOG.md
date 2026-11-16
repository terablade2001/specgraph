# Changelog

Changes of the tool that a user or an agent can notice, newest first. The version is `VERSION` in
`specgraph/__init__.py` (`python sg.py --version`). Design reasons are in `docs/ADRS.md`.

## 0.2.0 — 2026-11-16

Design: ADR-024 (approved by the owner).

### Changed

- **The tool works on any branch.** The branch rule is removed: the tool, the commit check and the
  editor no longer look at which branch is checked out. A `settings.branch` written by version 0.1
  stays in the file and is ignored; no migration is needed. To keep changes on one branch, protect
  it on the git server.
- A new model has an empty `settings`.

### Added

- **Order of the explorer.** Drag an item onto the upper or lower edge of another item of the same
  kind (folder, diagram, element) to put it before or after it; the middle of a folder still moves
  it into that folder. The order is saved in the model as an optional `order` number and is set by
  the new operation `folder.order {id, kind, ids}`.
  - A folder shows its sub-folders, then its diagrams, then its elements; the order applies inside
    each group. New and moved items go to the end of their group.
  - Reordering does not change an element's "Last changed" (`modified`).
  - When two branches order the same items, a merge keeps ours without a conflict.
  - Others cannot reorder the content of a locked folder; a locked folder itself can be placed
    among its siblings.
- **Collapse and expand with sub-folders.** Right-click a folder for *Expand with sub-folders* and
  *Collapse with sub-folders*, or Shift+click its arrow. Right-click the empty part of the tree for
  all folders at once.
- **Resizable panes.** Drag the line next to the explorer, next to the properties pane, or above the
  bottom panel. Double-click a line for the default size. The browser remembers the sizes; they are
  not part of the model.
- Validation reports an `order` that is not a whole number.

### Removed

- The operation `settings.put` and the "wrong branch" refusal (exit code 2, code `branch`).
- The `branch` entry of the editor state (`/api/state`).

### Compatibility

- The format version stays 2. Version 0.1 still reads a file written by 0.2: it ignores `order`, and
  it still enforces an old `settings.branch` if the file has one.
- Git hooks installed by 0.1 keep working; they call the current `sg.py`.

### Known gaps

- `docs/SECURITY-REVIEW.md` reviews version 0.1.0; its file hashes no longer match.
- The screenshots in `docs/img/` show version 0.1.0.

## 0.1.0

Initial release.
