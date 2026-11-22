# How AI agents read and change the model

## Read

Read `specmodel.json` directly; `docs/FORMAT.md` describes it. Or ask the tool (JSON on stdout):

```
python sg.py search "gaps" --stereotype REQ      # also: --status, --folder <id>, --unused
python sg.py show REQ-3d6e7863                     # id, unique id prefix or label
python sg.py trace REQ-3d6e7863                        # what it traces to / what traces to it
python sg.py impact CON-9a41c0de                        # everything depending on it
python sg.py matrix ADR REQ --types implements
python sg.py history REQ-3d6e7863
python sg.py validate
```

For questions no command answers (counts, joins, "elements without links", whole-model lists), query a
read-only SQLite copy of the model (ADR-032):

```
python sg.py sql --schema                                   # tables and what every column holds
python sg.py sql "SELECT stereotype, count(*) FROM elements GROUP BY stereotype"
python sg.py sql "SELECT ..." --json                         # {columns, rows, total, truncatedRows, truncatedCells}
```

- The copy is `.specgraph/<model file>.db` next to the model, rebuilt first when the model changed; it is never
  committed and safe to delete (`sg.py index` rebuilds it now).
- One `SELECT`/`WITH` statement per call. Anything that would write, attach a file or change the schema is
  refused (exit code 2), as are SQL errors and queries over 10 s.
- Output is capped: 50 rows and 200 characters a cell, and the last line says what was left out. Prefer
  `count(*)`, `GROUP BY` and `LIMIT/OFFSET` to raising the caps; `--limit N` / `--width N` (or
  `SPECGRAPH_SQL_LIMIT` / `SPECGRAPH_SQL_WIDTH`) change them, 0 = no cap.
- Full-text search, when `meta` says `fts` is not `none`: `elements_fts MATCH 'sign* OR login'` (stemmed,
  accents ignored), `ORDER BY rank`.
- A warning on stderr means the model file was changed outside the tool; the copy shows it as it is.

What the types mean in this project: every stereotype, status and link type has a `description` in
`config` (empty when nobody wrote one). Read them before interpreting the model.

## Change — always through `apply`, never by editing the file

```
python sg.py apply '[{"op": "element.update", "args": {"id": "<id>", "status": "approved"}}]'
```

- The argument (or stdin) is a JSON list of operations, applied **atomically**: all or nothing.
- `"$N"` in an argument is replaced by the id created by operation N of the same batch:

  ```
  [{"op": "element.create", "args": {"stereotype": "REQ", "topic": "Export as CSV", "folder": "<folder id>"}},
   {"op": "link.create",    "args": {"type": "refines", "source": "$0", "target": "<element id>"}},
   {"op": "diagram.place",  "args": {"diagram": "<diagram id>", "element": "$0", "x": 100, "y": 100}}]
  ```

- Output: `{"ok": true, "results": [ids or null, ...], "stamp": "<stamp id>"}`. Exit code 2 with a
  message on stderr when refused (validation, lock, identity).
- `element.delete` needs `--yes`; without it the command prints where the element is used and exits 3.
- `python sg.py ops` lists every operation with its arguments.
- `element.update` with a new `stereotype` also replaces the label by a generated one of the new type
  (ADR-026); pass `label` in the same call to keep or set another.
- The tool works on whatever branch is checked out; choosing the branch is up to the user.
- The order of the explorer: `{"op": "folder.order", "args": {"id": "<folder id or null>", "kind": "elements", "ids": [...]}}`
  (`kind`: `folders`, `diagrams` or `elements`). Leave it alone unless the user asks for an order.
- A folder lock means someone works there: do not work around it, and do not link to its elements. Anyone may unlock
  (`folder.unlock`; another user's lock needs `--yes`), but never on your own: ask the user.
- Every element you create or change gets `modified: {at, by}` with your user name; do not pass it.
- A deleted element is appended to `specmodel.deleted.jsonl`. Stage that file with the model
  (`git add specmodel.json specmodel.deleted.jsonl`); never edit or shorten it.
- There is no undo on the command line; use git (`git checkout -- specmodel.json` before a commit).
- `python sg.py --version` prints the tool version.

The agent's changes get the same validation, lock rules and signed stamp as a person's. The agent
signs through the ssh-agent of the account it runs under, which must hold exactly one key. Give the agent
its own account (or its own agent with its own key), registered as its own user, so its changes are attributable.

Do not write `specmodel.json` yourself: the tool then turns read-only for everyone and the
pre-commit check and the history audit report the change.
