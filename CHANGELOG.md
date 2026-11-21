# Changelog

Changes of the tool that a user or an agent can notice, newest first. The version is `VERSION` in
`specgraph/__init__.py` (`python sg.py --version`). Design reasons are in `docs/ADRS.md`.

## 0.3.0 — 2026-11-21

Design: ADR-025, ADR-026, ADR-027 (approved by the owner 2026-11-21); ADR-028, ADR-029, ADR-030.

### Changed

- **No "Decision date" field in new models.** ADR and TEMPORAL-ADR start with *Owner* only; the last change of
  every element is recorded anyway. An existing model keeps the field until you delete it under
  *Configure* → *Stereotypes*. The stored example model is rebuilt without it.
- **A type change gives a new label.** Changing an element's stereotype (ADR to REQ) replaces its label by
  the generated label of the new type (`ADR-3d6e7863` becomes `REQ-3d6e7863`), also when the label was
  typed by hand (`ADR-001`). A label passed in the same `element.update` wins. References to the old
  label no longer find the element; its id prefix still does.
- **The pre-push hook checks only the commits being pushed** (those the remote does not have yet), so an
  old finding no longer blocks every push and `--no-verify` is not needed for it. Run
  `python sg.py install-hooks` once to update hooks installed by an older version.

### Added

- **`sg.py audit <from> [<to>]`** checks only the commits from `<from>` to `<to>`, both included (`<to>`
  defaults to `HEAD`). `sg.py audit` without commits still checks the whole history.
- **Find in explorer.** Right-click an element on a diagram, or use the button in the properties of an
  element, diagram or folder: the folders above it open, it is selected and the explorer scrolls to it.
- **Double-click in the explorer on a folder** opens or closes it. Ctrl+double-click opens it with all
  sub-folders; Alt+double-click closes it with all sub-folders.

- **Several elements on a diagram.** Ctrl+click or Shift+click adds or removes an element; Shift+drag selects every
  element touching the rectangle. Dragging one moves them all as one change (one undo step); links follow
  while dragging. *Delete* removes all of them from the diagram.
- **Alignment.** With two or more selected, right-click one for *Align* ▸ *Horizontal* ▸ *Left / Center /
  Right* (Ctrl+Shift+1/2/3) or *Align* ▸ *Vertical* ▸ *Top / Center / Bottom* (Alt+Shift+1/2/3). They line
  up with the last selected element. The same six buttons are in the properties pane.
- **Auto size**, on by default. Elements are sized to show their whole text without changing fonts and are
  always wider than tall (width / height above 1.2): when placed, when their topic, label or type changes, and
  while their width is dragged. Right-click → *Fit to text* fits one element or a selection at any time;
  switching *Auto size* on fits the selected elements.
- **Selection in the explorer.** Ctrl+click and Shift+click work in the tree too; the tree and the open diagram
  share one selection. Dragging a selected row moves or places all selected elements, as one change.
- **Ctrl+A** selects every element of the open diagram. In the tree the selected elements are grey-green, the last
  selected (the reference for alignment) blue, so the ones not selected stand out.
- **Notes mark.** An element with notes shows a 📜 badge on the diagram (next to the lock, if any) and in the
  tree; point at it for the start of the notes.
- **Tab icon.** The editor has its own icon in the browser tab.
- **Export menu.** *Export SVG* and *Export PNG* are now in an *Export ▾* menu of the diagram tools, which
  also has *Copy image to clipboard* (a PNG).
- **Overview of the diagram** at the bottom right of the canvas, with a box for the part in view: click to
  look there, drag the box to move the view. *Overview* in the diagram tools hides it.
- **Snap to grid**, on by default. *Grid* (size in diagram pixels, default 20) and *Snap* in the diagram
  tools. With snap on, elements land on the grid when they are created, moved or resized; the grid is
  shown as dots in place of the plain background dots.
  The browser remembers the settings; they are not part of the model.

### Fixed

- The lock and notes badges no longer cover the end of an element's label.
- *Fit* no longer puts elements under the overview.
- *Fit* and the mouse wheel stopped at 20%, so a large diagram did not fit. They now go down to 2%.
- PNG export of a very large diagram failed (the image was beyond the browser's limits). It is now scaled down.
- Double-clicking a diagram in the explorer opens it again. The first click re-drew the tree, so the
  browser never reported the double-click.

### Compatibility

- The format version stays 2; nothing in the file changed shape. Version 0.2 reads a file written by 0.3.
- Hooks installed by 0.2 keep checking the whole history on every push until `python sg.py install-hooks`
  is run again.
- Grid, snap, auto size and overview settings are kept by the browser, not in the model.

### Documentation

- The README screenshots show version 0.3.0. The stored example model (`specmodel.example.json`) is rebuilt.

### Known gaps

- `docs/SECURITY-REVIEW.md` reviews version 0.1.0; its file hashes no longer match. 0.3.0 adds one static file
  (`favicon.svg`) to the server's fixed list and lets the pre-push hook read the refs git passes on stdin.
- Elements laid out before 0.3.0 keep their sizes; select them and use *Fit to text* to apply auto size.

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
