# Model file format (version 2)

One UTF-8 JSON file, `specmodel.json`. Readable without the tool; **written only by the tool**.

Serialization is canonical: keys sorted, one value per line, 1-space indent, LF, final newline.
An unchanged model always serializes to identical bytes, and one changed field is one changed
line (plus the stamp block).

```
{
 "format": "specgraph-model", "formatVersion": 2,
 "settings":  { "branch": "docs/specifications" },
 "config":    { "stereotypes": {...}, "statuses": {...}, "linkTypes": {...}, "coverageRules": {...} },
 "users":     { "<name>": { "role": "admin" | "user", "keys": ["ssh-ed25519 AAAA..."] } },
 "folders":   { "<id>": { "name", "parent": "<folder id>" | null, "lock": null | { "owner", "reason", "at" } } },
 "elements":  { "<id>": { "stereotype", "topic", "notes", "status", "label", "folder", "fields": {...},
                        "modified": { "at", "by" } } },
 "links":     { "<id>": { "type", "source": "<element id>", "target": "<element id>", "label" } },
 "diagrams":  { "<id>": { "name", "folder", "nodes": {...}, "links": {...} } },
 "conflicts": [ ... ],            // only present after a merge with conflicts
 "stamp":     { ... }             // identifies the last change
}
```

## Identity of things

- Every folder, element, link and diagram is stored under its **id**, a random UUID
  (e.g. `0ee71cd1-...`) generated on creation. Ids never change and all references use them.
- `label` on an element is the optional short human name; unique when not empty. Generated as the type's `labelPrefix` plus the first 8 characters of the id (`REQ-3d6e7863`, ADR-023); editable.
- `stereotype`, `status` and link `type` hold the **key** of a configuration entry
  (`"REQ"`, `"approved"`, `"implements"`), never its display label, so labels can be renamed.

## Elements, links, diagrams

- An element exists once. `folder` says where it lives in the tree. `fields` holds the custom
  fields its stereotype defines (`config.stereotypes.<key>.fields`), e.g. `{"priority": "Must"}`.
- `modified` says who last changed the element record and when (`at`: UTC time, `by`: user name).
  The tool sets it on every change to the element; moving it on a diagram is not such a change.
  It is never blank in a version-2 file (validation error otherwise).
- A link is directed `source → target` and belongs to the model, not to a diagram.
  Read it as "source *type* target": `ADR-3d6e7863 implements REQ-a41c09f2`.
- A diagram only stores layout:
  - `nodes`: `{ "<element id>": { "x", "y", "w", "h" } }` — which elements are shown and where.
  - `links`: `{ "<link id>": { "routing"?: "straight"|"auto"|"custom", "points"?: [[x,y],...], "hidden"?: true } }`
    — per-diagram overrides only. A link is drawn on a diagram whenever both its ends are on it,
    unless hidden there.

## Configuration

Keys of stereotypes, statuses, link types and fields start with a letter and contain letters, digits, `_` and `-`
(at most 40 characters), for example `B-REQ`.

- `stereotypes.<KEY>`: `label, fill, border, icon, shape (rect|rounded|hexagon|ellipse), labelPrefix,
  statuses (list of status keys or null = all), fields, retired`.
  `fields.<key>`: `{ label, type: string|text|number|boolean|enum|date, options? }`.
- `statuses.<key>`: `label, color, symbol, order, retired`.
- `linkTypes.<key>`: `label, lineStyle (solid|dashed|dotted), color, sourceArrow, targetArrow
  (none|open|triangle|hollow-triangle|diamond|hollow-diamond), showLabel, routing, traceable
  (optional, missing = true), sources, targets (lists of stereotype keys or null = any), retired`.
- `coverageRules.<key>`: `description, stereotype, statuses, linkType, direction (incoming|outgoing), other`.
- `retired: true` entries still display on existing items but cannot be used for new ones.

## Traceability

Follow links whose type has `traceable` not `false`, over the whole model (diagrams are irrelevant).
"X traces to Y" = a path of links from X to Y. "Impact of Y" = everything with a path to Y.

## Locks

`folders.<id>.lock = { owner, reason, at }` locks that folder, all sub-folders and all elements and
diagrams in them. A link is protected together with its **source** element. A lock means "someone works
here": only its owner changes the content or creates a link to an element in it (ADR-022), and anyone may
remove the lock. Locked items may still be read, searched, traced and placed on other diagrams.

## Stamp

```
"stamp": { "id", "user", "at", "tool", "toolVersion", "op", "prev": [stamp ids],
           "contentHash": "sha256:<hash of the file without the stamp>", "sig": "<SSH signature>" }
```

`sig` is an OpenSSH signature (namespace `specgraph`) by one of `users.<user>.keys` over the stamp
without `sig`. If the content does not hash to `contentHash`, the file was edited outside the tool.

## Conflicts

After a merge where both sides changed the same value: `conflicts` is a list of
`{ path: [...], base, ours, theirs }` with each side as `{ present, value }`. Our value stays in
place until a person chooses. A model with conflicts fails validation and cannot be committed.

## Version 1 files

Version 1 had no `modified`. The tool still reads such a file. The first change made through the
tool writes it back as version 2 and gives every element without `modified` the user and time of
the stamp that was in force. A copy of the tool from before this change refuses a version-2 file ("unsupported formatVersion").

## Deleted elements log

`specmodel.deleted.jsonl`, next to the model. One JSON object per line; the tool only appends.

```
{"event": "deleted", "id": "<element id>", "at", "by", "lastCommit": "<commit hash>" | null,
 "folderPath", "element": { the element as it was }, "links": { "<link id>": { its links } }}
{"event": "restored", "id": "<element id>", "at", "by"}
```

- `lastCommit` is the last commit that changed the model while it still contained the element;
  `git show <lastCommit>:specmodel.json` shows it. `null` = the element was never committed.
- `restored` is written when a deleted element comes back (undo, or a merge conflict settled so).
- Commit this file together with `specmodel.json`: the pre-commit check refuses a commit that
  removes an element without its line. `.gitattributes` merges it with `merge=union`, so two
  branches never conflict in it.
- It is not signed. It is an index for people; the proof is git history.
