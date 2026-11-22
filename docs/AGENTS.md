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

## Reading a large model

A model of a few thousand elements is several megabytes: do not read the file, and do not page through
`search ""` or `validate`. Work like this:

1. **Learn the vocabulary first.** `sql --schema`, then the configuration with its descriptions:
   `SELECT key, label, description FROM config_stereotypes` (also `config_statuses`, `config_link_types`,
   `config_fields`, `config_coverage_rules`). A project may describe its own glossary type there; use it to
   widen searches.
2. **Count before you fetch.** `SELECT count(*) …` or `GROUP BY`; fetch rows only when the number is small,
   and always with `LIMIT`. When the footer says rows were left out, the answer is incomplete: narrow the
   query or page with `LIMIT/OFFSET`.
3. **Summaries first.** `elements` has label, type, status, topic and folder path; read `element_notes` only for
   the ids you chose.
4. **One element's trace or impact:** `sg.py trace` / `sg.py impact` answer exactly. Use SQL when you need it
   for many elements at once or combined with other conditions.
5. **Search by meaning, not by one word.** A concept is worded many ways. Search topics and notes with several
   words and stems at once, read the hits, then add the words you find in them and search again. Follow links
   from the hits when the question is about what they lead to.
6. **Answer with labels** (`elements.label`) unless the question asks for something else.

Example queries (labels and names are placeholders):

```sql
-- how many elements of each type and status
SELECT stereotype, status, count(*) FROM elements GROUP BY stereotype, status;

-- something missing: approved requirements that no ADR implements
SELECT e.label, e.topic FROM elements e
WHERE e.stereotype = 'REQ' AND e.status = 'approved' AND NOT EXISTS (
  SELECT 1 FROM links l JOIN elements a ON a.id = l.source
  WHERE l.target = e.id AND l.type = 'implements' AND a.stereotype = 'ADR');

-- impact: everything that traces to an element (follows traceable links only; UNION stops on cycles)
WITH RECURSIVE up(id) AS (
  SELECT id FROM elements WHERE label = 'FEAT-1234abcd'
  UNION
  SELECT l.source FROM links l JOIN up ON l.target = up.id
  JOIN config_link_types t ON t.key = l.type AND t.traceable = 1)
SELECT e.label, e.stereotype, e.topic FROM up JOIN elements e ON e.id = up.id
WHERE e.label <> 'FEAT-1234abcd';
-- what it traces to: swap source and target. Add a depth column (depth + 1 … WHERE depth < 3) to stop early.

-- coverage problems per rule, and in one folder tree
SELECT rule, count(*) FROM coverage_violations GROUP BY rule;
SELECT e.label, e.topic FROM coverage_violations v JOIN elements e ON e.id = v.element
WHERE e.folder_path = 'Billing' OR e.folder_path LIKE 'Billing/%';

-- concept search: stemmed full text over label, topic, notes and text fields, best first
SELECT f.label, e.stereotype, e.topic FROM elements_fts f JOIN elements e ON e.id = f.id
WHERE elements_fts MATCH 'deliver* OR shipping OR dispatch* OR courier OR "sent out"' ORDER BY rank LIMIT 40;
-- without full text (meta fts = 'none'): WHERE lower(topic) LIKE '%deliver%' OR ...

-- locks: what is locked, by whom, and is a given element's folder under a lock
SELECT path, lock_owner, lock_reason FROM folders WHERE lock_owner IS NOT NULL;
SELECT e.label, f.locked_by, f.locked_from FROM elements e JOIN folders f ON f.id = e.folder
WHERE e.label = 'REQ-1234abcd';

-- custom fields: one row per element and field
SELECT e.label, p.value FROM elements e
JOIN element_fields p ON p.element = e.id AND p.key = 'priority'
WHERE e.stereotype = 'REQ' AND p.value = 'Must';
```

## AI labels (optional, ADR-034)

A project may keep a vocabulary of concepts and per-element labels in `specmodel.ai.json`. In the index:
`ai_vocabulary` (read it like the configuration) and `ai_labels(element, label, stale)`.
`SELECT e.label, e.topic FROM ai_labels a JOIN elements e ON e.id = a.element WHERE a.label = 'payments'` finds
elements by concept even when their words differ. Labels find, specs answer: `stale = 1` means possibly outdated,
an element may be unlabelled, and labels can be wrong, so combine them with full-text search and links.
`python sg.py ai status` shows how much is labelled; `python sg.py ai ops` lists the operations of
`python sg.py ai apply` (vocabulary and rules: administrators only).

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
