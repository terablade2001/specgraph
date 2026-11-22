# Changelog

Changes of the tool that a user or an agent can notice, newest first. The version is `VERSION` in
`specgraph/__init__.py` (`python sg.py --version`). Design reasons are in `docs/ADRS.md`.

## 0.4.0 — in progress

Design: ADR-032, ADR-033 (approved by the owner 2026-11-22). Plan: `docs/PLAN-0.4-AI-LAYER.md`.

### Changed

- **Format version 3: every stereotype, status and link type has a description.** Write in it what the type means
  in your project (Configure → the type → *Description*); people see it as a tooltip and agents read it from the
  file. New models start with short generic descriptions of the initial types. An older model is read as before
  and is written as version 3 on its first change, with empty descriptions. **Upgrade everyone together:** a tool
  before 0.4.0 refuses a version-3 file.
- `config.put` gives a new stereotype, status or link type `description: ""` when none is passed.
- A merge no longer reports a conflict just because one side was upgraded to version 3 and the other was not.
- The stored example model is rebuilt (format 3; its *verifies* link type has a description).

### Added

- **AI labels (ADR-034), first part.** An optional second file `specmodel.ai.json` holds a controlled vocabulary of
  concepts, labels per element (keyed by a hash of type, topic, notes and fields) and people's rules, signed like
  the model; `specmodel.ai.log.jsonl` logs every operation. `sg.py ai apply` is its only write path (labels: any
  user; vocabulary and rules: administrators), `sg.py ai status` and `sg.py ai ops` report. The index gets
  `ai_vocabulary` and `ai_labels` (with a stale flag) and is rebuilt when the AI file changes. The commit check and
  `audit` check the AI file's stamp and that only administrators changed vocabulary and rules. `install-hooks` marks
  both files in `.gitattributes`. The tool never calls a language model; work packets for agents come next.

- **`sg.py index`**: builds a read-only SQLite index of the model in `.specgraph/<model file name>.db` next to the
  model (ADR-032). It is derived and disposable: the tool writes `.specgraph/.gitignore`, so it is never committed,
  and deleting it loses nothing. It holds elements, notes, fields, links, folders with paths and locks in force,
  diagrams, users, the configuration with its descriptions, coverage violations, a full-text index when the Python
  build has FTS5, and `columns_doc`, the meaning of every column. Prints what it built as JSON. A 10 000-element
  model builds in about half a second.
- `docs/AGENTS.md`: "Reading a large model", a short guide with example queries for agents.
- `docs/FORMAT.md`: where the derived index lives and what it is not.
- **`sg.py sql "<query>"`**: runs one read-only `SELECT`/`WITH` statement on the index, rebuilding it first when
  the model changed. Writing, `ATTACH`, schema changes, transactions, writing pragmas and extensions are refused
  (exit code 2), and a query stops after 10 s. Output is a compact table (`a | b`, `NULL`, line breaks as `\n`)
  or `--json`; it shows at most 50 rows and 200 characters a cell, and says how much was left out. Change the caps
  with `--limit N` / `--width N` or `SPECGRAPH_SQL_LIMIT` / `SPECGRAPH_SQL_WIDTH` (0 = no cap).
  `sg.py sql --schema` prints every table and what its columns hold. A warning is printed when the model file was
  changed outside the tool.

### Faster

- `sg.py validate` and the editor's *Check* compute coverage rules in one pass over the links (same results; a
  10 000-element model went from about 2 s to well under 0.1 s).

### Added (for evaluations, not part of the tool)

- `sample/build_synthetic.py`: a large synthetic model with planted facts, the same for the same seed.
- `evals/`: questions, expected answers, scoring and the baseline of agents on 0.3.1 (`evals/results/BASELINE.md`).
- The same evaluations with the index (`evals/results/INDEX.md`): at 10 000 elements mean F1 0.85 → 0.95, and
  questions that needed 90–145K tokens now need about 65K.
- The evaluation generator writes unique topics, clear concept notes and *hidden* concept wordings; new stored
  models (`s1k-v2`, `s10k-v2`) and the baseline for labels (`evals/results/INDEX-V2.md`).

## 0.3.1 — 2026-11-21

Design: ADR-031 (approved by the owner 2026-11-21). Fixes two findings of the security review of 0.3.0.

### Changed

- **A merge refuses a side that was edited outside the tool.** The merge driver and `sg.py resolve` check the stamp
  of our and their version first. If one of them was changed by hand, nothing is merged, git reports the model as
  conflicted with our version in place, and the message says which side. Run `git merge --abort` and have that
  branch repaired (its author runs `sg.py adopt` there, or restores the file from git). Before, such an edit was
  merged in silently and signed by the person merging.

### Fixed

- The editor uses a type, status or link colour only when it is `#rrggbb`. A colour edited by hand into the file
  could put arbitrary CSS into the page's styles (the content security policy still blocked outside loads).

### Documentation

- `docs/SECURITY-REVIEW.md` and `AI-Disclaimer.md` cover 0.3.1.

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

- A merge does not check the stamps of the two sides: a model edited by hand on another branch is merged
  without a warning and signed by the person merging. Fixed in 0.3.1.
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
