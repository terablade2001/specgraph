# Requirements

The requirement IDs used in tests, ADRs and code comments (for example `REQ-STO-03`).
`docs/REQUIREMENTS-COVERAGE.md` maps each one to its tests.

These statements were written afterwards from the tests, the code and the ADRs, because the
original wording was not kept. They describe what the tool is tested to do. IDs whose meaning
could not be established from the repository are left out (see the end of this file) rather
than guessed. If a statement here disagrees with the tool, ask the owner which one is right.

## STO — storage and Git

| ID | Requirement |
|---|---|
| STO-01 | The model is kept in one JSON file in the Git repository. |
| STO-02 | Organizing the model (folders, diagrams) changes content only; no file per element, folder or diagram. |
| STO-03 | An unchanged model serializes to identical bytes; changing one field gives a small diff. |
| STO-04 | What changed, when and by whom can be read from Git history. |
| STO-05 | The tool works on whatever branch is checked out; there is no branch rule (ADR-024, replaces the configured branch of ADR-009). |
| STO-06 | People working in parallel can merge: different items or fields merge cleanly, the same field changed twice is surfaced with both values kept. |
| STO-07 | A session holding an old view is told to reload instead of overwriting newer changes. |
| STO-08 | Agents read the file as plain JSON and change it through a command. |

## ELM — elements

| ID | Requirement |
|---|---|
| ELM-01 | An element has a stereotype, a topic, notes and a status. |
| ELM-02 | An element gets a generated label that is unique: the type prefix plus the first 8 characters of its id (ADR-023). |
| ELM-03 | Internal ids are random and need no coordination between people. |
| ELM-04 | The status of an element is one of the configured statuses. |
| ELM-05 | An element exists once in the model and may appear on several diagrams. |
| ELM-06 | Removing an element from a diagram keeps it; deleting shows where it is used and removes its links. |
| ELM-07 | Changing the stereotype of an element gives it a new generated label of the new type, unless a label is given in the same change (ADR-026). |

## FLD — folders

| ID | Requirement |
|---|---|
| FLD-01 | Folders can be created, renamed and moved. |
| FLD-02 | Elements and diagrams can be moved between folders. |
| FLD-03 | The sub-folders, diagrams and elements of a folder can be put in an order, in the editor by drag and drop (ADR-024). |

## DGM — diagrams

| ID | Requirement |
|---|---|
| DGM-01 | A diagram shows elements and links of the model; it stores layout only. |
| DGM-02 | Elements can be placed, moved, resized and linked by dragging. |
| DGM-03 | Each diagram has its own layout; an element appears at most once per diagram. |
| DGM-04 | Link routing is straight, automatic or user-defined, and can be overridden per diagram. |
| DGM-05 | Elements show their stereotype and status visually. |
| DGM-06 | A link's look follows its link type. |
| DGM-07 | Links between elements on a diagram appear from the model. |
| DGM-08 | A diagram can be exported as an image (SVG and PNG file) or copied to the clipboard as an image, from the *Export* menu of the diagram tools. |
| DGM-09 | Several elements of a diagram can be selected: Ctrl+A selects all, Ctrl+click or Shift+click adds or removes one, Shift+drag selects every element touching the rectangle (ADR-027). |
| DGM-10 | Dragging one element of a selection moves them all as one change; links follow while dragging, and the bend points of links between selected elements move along. |
| DGM-11 | The selected elements can be aligned with the last selected one, from the Align submenu or the keyboard: horizontally by left edge, centre or right edge (Ctrl+Shift+1/2/3), vertically by top edge, centre or bottom edge (Alt+Shift+1/2/3) (ADR-028). |
| DGM-12 | Elements can snap to a grid when they are created, moved or resized; the grid size and the switch are in the diagram tools, start at the same default for everyone (20, on) and are kept by the browser. |
| DGM-13 | An overview of the whole diagram shows which part is in view; a click there moves the view to that point and dragging its box moves the view. It can be hidden (ADR-028). |
| DGM-14 | *Fit* and the mouse wheel zoom out down to 2%, so a large diagram fits in the window. |
| DGM-15 | With *Auto size* on (the default), an element on a diagram is sized to show its whole text without changing a font, and is always wider than tall (width / height above 1.2): when it is created, when its topic, label or type changes, and when its width is dragged. *Fit to text* does the same on demand (ADR-030). |

## LNK — links

| ID | Requirement |
|---|---|
| LNK-01 | Links are typed. |
| LNK-02 | Links belong to the model, not to a diagram. |
| LNK-03 | A link type can restrict the stereotypes of its source and target. |

## TRC — traceability

| ID | Requirement |
|---|---|
| TRC-01 | Traceability follows links over several levels. |
| TRC-02 | Traceability uses the model, not diagrams. |
| TRC-03 | A link type can opt out of traceability. |
| TRC-04 | A matrix of stereotype × stereotype for chosen link types, and impact analysis (downstream). |
| TRC-05 | Coverage rules are configurable and violations are reported. |

## CFG — configuration

| ID | Requirement |
|---|---|
| CFG-01 | Stereotypes can be added and changed through the tool. |
| CFG-02 | Statuses can be added and changed through the tool. |
| CFG-03 | Which statuses a stereotype allows is configurable (status transition rules: optional, not built). |
| CFG-04 | Stereotypes can have typed custom fields. |
| CFG-05 | Link types can be added and changed through the tool. |
| CFG-06 | Data refers to configuration by stable key, never by display label. |
| CFG-07 | A configuration entry that is in use cannot be deleted, but can be retired: existing data stays valid and editable, new use is refused. |
| CFG-08 | A default configuration ships with the tool (stereotypes, statuses, link types; see ADR-020); everything in it can be edited. |

## SRC — search

| ID | Requirement |
|---|---|
| SRC-01 | Search by id (or its start), label and text. |
| SRC-02 | Search results list the diagrams that show each element. |
| SRC-03 | A search result can open a diagram with the element centred and selected. |
| SRC-04 | An element's context menu finds it in all diagrams. |
| SRC-05 | A list of elements that are not used (not linked or not on a diagram). |

## INT — integrity

| ID | Requirement |
|---|---|
| INT-01 | Every change carries a unique, signed stamp with who, when and tool version. |
| INT-02 | A change that bypassed the tool is detected. |
| INT-03 | Changes by agents also go through the tool. |
| INT-04 | The model is validated: structure, references and configuration rules. |
| INT-05 | What the integrity mechanism does and does not prove is documented (ADR-003). |

## USR — users

| ID | Requirement |
|---|---|
| USR-01 | Users are names with existing SSH public keys; no passwords. |
| USR-02 | There is an administrator role. |

## LCK — locks

| ID | Requirement |
|---|---|
| LCK-01 | A folder can be locked, covering its sub-folders and contents; only the owner's key may change locked content. |
| LCK-02 | Anyone can unlock; unlocking another user's lock needs a confirmation (ADR-022). |
| LCK-03 | Lock information is available for the tree and diagrams. |
| LCK-04 | Locked content can still be viewed and placed on other diagrams; only the lock owner may link to it (ADR-022). |
| LCK-05 | A hand edit of locked content is rejected, even if re-stamped with a valid key. |
| LCK-06 | Two people locking the same folder is surfaced as a conflict. |

## CHK — checks

| ID | Requirement |
|---|---|
| CHK-01 | A pre-commit hook blocks hand edits and invalid models. |
| CHK-02 | One command installs the hooks and the merge driver. |
| CHK-03 | A history audit reports integrity, lock and identity violations. |
| CHK-04 | The audit run by hand checks the whole history, or only the commits from one given commit to another, both included (ADR-025). |
| CHK-05 | The pre-push hook checks only the commits that the remote does not have yet. |

## HST, USE, DOC

| ID | Requirement |
|---|---|
| HST-01 | An element's history is shown in words from Git history. |
| USE-01 | The editor has a folder tree, diagrams and a properties panel. |
| USE-02 | The editor server is local only (see ADR-002). |
| USE-05 | The editor opens only for someone who can sign with the registered private key (ADR-021). |
| USE-06 | The tool runs only when exactly one key is loaded in ssh-agent. |
| USE-07 | A folder can be collapsed or expanded together with all its sub-folders. |
| USE-08 | The widths of the explorer and the properties pane, and the height of the bottom panel, are changed by dragging the line next to them. |
| USE-09 | In the explorer, a double-click opens a diagram and opens or closes a folder; Ctrl+double-click opens a folder with all its sub-folders, Alt+double-click closes them all. |
| USE-10 | "Find in explorer" opens the folders above the selected item, selects it there and scrolls it into view. |
| USE-11 | An element with notes is marked on the diagram and in the tree; pointing at the mark shows the start of the notes. |
| USE-12 | The editor has its own icon in the browser tab. |
| DOC-05 | A demo model, built through the tool's own operations. |

## IDs with no recorded meaning

`USE-03`, `USE-04` and `DOC-01`..`DOC-04` are mentioned in `docs/REQUIREMENTS-COVERAGE.md` and
ADR-002 as documents or constraints that tests cannot check. Nothing in the repository says what
they required, so they are not restated here. ADR-002 lists the constraints that shaped the
design (start from a Python script, nothing non-Python to install, no licence risk).
