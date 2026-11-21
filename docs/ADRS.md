# Architecture Decision Records

Status of all ADRs: **decided by the implementer, awaiting human review.** The owner chose
"build now, review after", so high- and medium-stakes ADRs below were implemented before approval.
Each says what changing it later would cost.

## Ambiguities found in the requirements, and the reading taken

| # | Point | Reading taken |
|---|---|---|
| 1 | REQ-INT-01 "every change SHALL go through the tool" — a file in git can always be edited | Outside changes cannot be prevented, only **detected and blocked from commit**; see ADR-003 |
| 2 | REQ-LCK-01 "without the lock owner's key" | Every change is signed with the author's SSH key; a change to locked content is accepted only when signed by the owner |
| 3 | May an administrator edit locked content? | No. Anyone may **unlock** (REQ-LCK-02, ADR-022); the unlock is itself a stamped change |
| 4 | Which lock protects a link (links have no folder)? | The lock on its **source** element's folder. Since ADR-022 a new link *to* locked content is also refused, except for the lock owner |
| 5 | Can an element appear twice on one diagram? | No, once per diagram |
| 6 | Can elements live at the top level? | No, every element and diagram is in a folder; only folders can be top-level |
| 7 | Direction of traceability / "downstream" (REQ-TRC-04) | A link reads "source *type* target"; source depends on target. Impact of X = everything that reaches X |
| 8 | REQ-CFG-01 "ordinary user" vs. integrity | Any registered user may change configuration; only administrators change users |
| 9 | REQ-ELM-04 unique labels vs. parallel work | Generated labels come from the id (ADR-023), so parallel branches do not clash. Uniqueness is enforced on entry; a hand-typed duplicate from two branches is reported after the merge for a person to fix |
| 10 | REQ-STO-04 "what changed, when, by whom" when several changes are made before one commit | Git commit granularity. The stamp names the last change; the commit diff shows all of them |

---

## ADR-001 — One canonical JSON file, items keyed by id  · stakes: high
**Context.** REQ-STO-01..04, REQ-ELM-02/05, REQ-LNK-02.
**Options.** (a) arrays of items; (b) objects keyed by id; (c) JSON Lines.
**Decision.** (b). Collections `folders`, `elements`, `links`, `diagrams` are objects keyed by UUID.
Diagrams hold layout only and refer to elements by id. Serialization is canonical (sorted keys,
one value per line, LF).
**Consequences.** Identical bytes for an unchanged model; one changed field is one changed line;
adding an item never shifts other lines, which is what makes merges clean. Order in the file is
by id, not by meaning — people read it through the tool, agents by key. Changing this later means
a format migration (`formatVersion` exists for that).

## ADR-002 — Local Python web server + plain-JavaScript browser UI  · stakes: high
**Context.** REQ-USE-01..04; owner constraints: start from a Python script, nothing non-Python to
install, no licence risk.
**Options.** (a) tkinter desktop app; (b) Python + pip GUI/web framework; (c) Python standard-library
HTTP server serving hand-written HTML/CSS/JS with SVG diagrams.
**Decision.** (c). `http.server` on 127.0.0.1; three static files; no library, no bundler.
**Consequences.** Zero installs and zero third-party licences. The diagram editor is about 900 lines of
JavaScript we own. Logic that matters (operations, validation, locks, search, trace) lives in Python
and is shared by UI, CLI and hooks. The UI redraws whole panels on each change — simple, fine for
hundreds of elements per diagram, not tuned for thousands.

## ADR-003 — Identity = existing SSH keys; every change carries a signed stamp  · stakes: high
**Context.** REQ-INT-01/02/05, REQ-USR-01/02. Python's standard library has no public-key signatures.
**Options.** (a) hash only, no signature; (b) per-user shared secret (HMAC); (c) `cryptography` pip
package; (d) `ssh-keygen -Y sign/verify`, which ships with Git.
**Decision.** (d). A user is a name, a role and SSH public keys, stored in the model. The tool finds
your key in ssh-agent (ADR-021), maps it to a user, and after each change writes a stamp `{id, user, at, tool, toolVersion,
op, prev, contentHash}` signed with your key. Private keys never enter the tool.
**What this proves.**
- The committed content is byte-for-byte what a tool run stamped (hash), so *any* edit made afterwards
  outside the tool — accidental or deliberate — is detected.
- The stamp was produced by someone holding a private key registered for the named user. For
  committed history the key list is taken from the **previous** commit, so nobody can add themselves
  and sign in one step.
**What this does not prove.**
- Only the last stamp before each commit is kept; intermediate changes between two commits are not
  individually provable (git shows their combined diff).
- It does not prove the official tool was used. A registered user can sign anything with their own
  key; what they cannot do is break lock or user rules unnoticed, because those are re-checked from
  the diff by everyone's hooks and by `audit`.
- `at` and `toolVersion` are self-reported. The first commit of a model is trusted as-is (bootstrap).
- It does not stop history rewriting or force-pushes; protect the branch on the git server for that.
- A merge that silently drops one side's change while every item still equals one parent is not flagged.
- A stolen administrator key defeats it.
**Consequences.** No passwords, no new accounts. Needs `ssh-keygen` on the machine (present with Git
on Linux, macOS and Git for Windows). Passphrase-protected keys must be in `ssh-agent`.

## ADR-004 — Model-aware three-way merge; conflicts stay in the file for a person  · stakes: high
**Context.** REQ-STO-06, REQ-ELM-03, REQ-LCK-06. A text merge of one JSON file conflicts constantly
(at least on the stamp).
**Options.** (a) rely on git's text merge; (b) file per item (forbidden by REQ-STO-02); (c) custom
merge driver.
**Decision.** (c). `install-hooks` registers a git merge driver. It merges per item and per field.
Same value changed differently on both sides (including delete-vs-edit and two people locking the
same folder) is a conflict: our value stays, both values are recorded under `conflicts`, git reports
the conflict, and the editor offers *Keep mine / Take theirs*. The merged file gets a `merge` stamp
with both parents. `resolve` does the same from git's index if the driver was not installed.
**Consequences.** Parallel work merges without loss; nothing is resolved silently. Problems that only
exist after merging (two elements with the same label, a link to a deleted element) are reported by
validation and block the commit until fixed. The driver must be installed per clone (one command).

## ADR-005 — Locks live in the model and are enforced on the diff  · stakes: high
**Context.** REQ-LCK-01..06.
**Options.** (a) UI-only locks; (b) lock files; (c) lock stored on the folder, rule checked on the
difference between two model states.
**Decision.** (c). One function compares "before" and "after" and rejects any changed item whose
folder (or an ancestor) is locked by someone else. It runs when an operation is applied, in the
pre-commit hook (staged vs. HEAD), and in `audit` (each commit vs. its parents). So the rule holds
even if the UI or the tool is bypassed. Unlock: anyone (ADR-022). A lock cannot be taken over
or inside someone else's lock.
**Concurrency.** A lock exists for others once they pull it. Two people locking the same folder on
two clones is a merge conflict (ADR-004). Edits made elsewhere before the lock arrived merge in
normally: they were legitimate when made.
**Consequences.** Locks are advisory in real time (no server) but enforced at commit and provable in
history. Deleting an element is refused if that would alter a locked diagram or a link owned by a
locked element.

## ADR-006 — Local checks: git hooks plus an after-the-fact audit  · stakes: medium · amended by ADR-025
**Context.** REQ-CHK-01..03.
**Decision.** `install-hooks` writes `pre-commit` (`check --staged`) and `pre-push` (`audit`), and
never overwrites a foreign hook without `--force`. `audit` replays the same checks for every commit
touching the model and exits non-zero on findings; anyone can run it.
**Consequences.** Hooks can be skipped (`--no-verify`); the audit finds it afterwards. Audit time
grows with history length (one signature check per commit).

## ADR-007 — Configuration entries have stable keys; retire instead of delete  · stakes: medium
**Context.** REQ-CFG-01/06/07.
**Decision.** Data stores the entry key (`REQ`, `approved`); the label is display only. Keys are
generated from the first label and never change. In-use entries cannot be deleted, only retired.
A stereotype change that would invalidate existing elements (dropping a used field or status) is refused.
**Consequences.** After renaming a label the key may look unrelated to it; that is cosmetic.

## ADR-008 — Traceability semantics  · stakes: medium
**Decision.** Links are directed; traceability follows links whose type is traceable (default yes),
over the model only. "Traces to" follows source→target; "traced from" the reverse, and is used as the
impact view. Coverage rules are optional, none by default, reported as warnings.
**Consequences.** Teams must draw links in the "depends on / derives from" direction for impact to
read correctly. The default link types are named accordingly.

## ADR-009 — Branch rule  · stakes: medium · **replaced by ADR-024**
**Decision.** `settings.branch` (default `docs/specifications`) is stored in the model. On another
branch the tool refuses changes and the pre-commit check refuses model commits. Empty value disables it.
**Consequences.** Merging the specification branch into `main` is unaffected (no model change is made there).

## ADR-010 — Ids and labels  · stakes: low
UUID v4 for every item: unique across branches without coordination. Optional label, generated from the
stereotype's prefix and the id (ADR-023), editable, unique on entry.

## ADR-011 — Not overwriting outside changes  · stakes: low
The tool keeps no model in memory between requests. Each change re-reads the file under a short file
lock and compares the stamp id the caller last saw; on mismatch the change is refused and the UI
reloads. The UI also polls every 3 s and reloads after a `git pull`.

## ADR-012 — Link routing  · stakes: low
Straight, automatic (orthogonal, chosen from the relative position of the two boxes; no obstacle
avoidance) and user-defined (bend points). Type default plus per-diagram override. Automatic
diagram layout is out of scope; positions are plain numbers so a layouter can be added.

## ADR-013 — Licence  · stakes: low
MIT (owner's choice). No third-party source is included; runtime needs only Python, git and OpenSSH.

## ADR-014 — Deliberately not built  · stakes: low
Status transition rules (MAY in REQ-CFG-03), and everything listed under "Not in scope" in `CLAUDE.md`.

## ADR-015 — Keeping the future open  · stakes: low
- Generators and indexes: stereotypes, typed links and stable ids let a generator read the file as is.
- MCP server: can wrap `query.py` (read) and `Store.apply` (write) without touching them.
- Importers: an importer only has to emit operations.
- Baselines: a git tag is a snapshot; `audit.check_version`/`history.describe` already compare two versions.

---

# Added 2026-11-15 — accepted, implemented

## ADR-016 — Every element carries who last changed it and when  · stakes: high (format change)
**Context.** Owner request: each element has a date and a non-blank author, traceable in git.
**Options.** (a) derive both from git history only (nothing stored; blank until committed);
(b) store `created` and `modified`; (c) store `modified: {at, by}` only.
**Decision.** (c). `elements.<id>.modified = { "at": ISO time, "by": user name }`. It is set in one
place, `ops.apply_ops`, for every element whose record differs after a batch, so no operation can
forget it and an unchanged element keeps its bytes. `by` is the signing user (ADR-003), so it is
never blank. Diagram layout does not touch it (layout is not part of the element).
`formatVersion` becomes 2. A version-1 file is still read; the first change through the tool
upgrades it and gives elements without `modified` the user and time of the stamp in force (the last
person who signed the model containing them). Validation requires `modified` in version 2.
**Merge.** Two people editing different fields of one element would now always collide on
`modified`; the merge driver takes the later `at` instead of reporting a conflict.
**Lock rule.** Adding `modified` to an element that had none is not counted as a change to it
(otherwise the upgrade would be blocked by other people's locks).
**Consequences.** Every element change adds two changed lines to the diff. `modified` is
self-reported like the stamp's `at`; it is not checked against the stamp user (an undo and a merge
legitimately keep someone else's name). Older tool versions refuse a version-2 file.

## ADR-017 — Undo in the editor: N snapshots in the server's memory  · stakes: medium
**Context.** Owner request: configurable N steps of undo (example: element removed from a diagram).
**Options.** (a) inverse operation per operation (about 35 inverses to write and keep correct);
(b) undo log stored in the model or a side file; (c) the editor server keeps the last N model
states in memory and writes the previous one back as a new stamped change.
**Decision.** (c). `Store.undo()` restores the state before the last change made in this editor
session, through the normal path: integrity check, lock/user rules on the difference, new stamp
(`op: "undo"`), save. It is refused, and the undo list emptied, when the file was changed by
anything else in between (CLI, agent, `git pull`). N comes from `serve --undo N` or
`SPECGRAPH_UNDO` (default 20; 0 turns it off). Editor: Undo button and Ctrl+Z.
**Consequences.** Works for every operation with no per-operation code. The list is lost when the
server stops; after a commit, git is the undo. No redo. CLI and agents have no undo (they have git).
Memory: N copies of the model.

## ADR-018 — Deleted elements are recorded in a second file  · stakes: medium
**Context.** Owner request: a separate file that keeps deleted elements and their latest commit.
REQ-STO-02 forbids a file per element; this is one file per model.
**Options.** (a) one JSON object keyed by element id; (b) JSON Lines, one line per event,
append-only, merged by git with `merge=union`.
**Decision.** (b), file `specmodel.deleted.jsonl` next to the model. Each line is one JSON object:
`{"event": "deleted", "id", "at", "by", "lastCommit", "element": {...}, "links": {...},
"folderPath"}`. `lastCommit` is the last commit that changed the model file while it still held the
element (null if the element was never committed); `git show <lastCommit>:specmodel.json` shows it.
When a deleted element comes back (undo, or a merge conflict settled the other way) a line
`{"event": "restored", "id", "at", "by"}` is appended. The tool only ever appends; it never reads
the file to decide anything. `Store.apply`, `undo` and `adopt` write it; the pre-commit check
refuses a commit that removes an element without a matching line in the staged file.
`install-hooks` adds the `merge=union` rule to `.gitattributes`.
**Consequences.** Two branches deleting different elements never conflict in this file. The file is
not signed: it is a convenience index, the proof stays in git history. Deleted links alone (without
their element) are not recorded.

## ADR-019 — Deleting from the model always needs a confirmation  · stakes: low
The editor asks before every delete from the model (element, link, diagram, folder, configuration
entry, user). The server refuses an `element.delete` that does not carry `confirmed: true`, the same
way the CLI needs `--yes`, so the rule does not live in `app.js` alone. Removing an element from one
diagram is not a delete from the model: no pop-up, and Undo brings it back.
The id line in the properties panel gets a copy button (clipboard API; works on 127.0.0.1).

## ADR-020 — Initial element types and the association link  · stakes: low
**Context.** Owner request (2026-11-15): the starting configuration of a new model should offer these
element types: ADR, REQ, NAMESPACE, RISK, ISSUE, B-REQ, U-REQ, CONSTRAINT, TEMPORAL-ADR, FEAT, TEST-E2E,
TEST-INT, ASSET, DOC, and an "association" link type. BRULE is no longer a default type.
**Decision.** `defaults.py` defines them, each with its own colour, icon and label prefix. Keys may now
contain `-` (`validate.KEY`), which the names need. `association` is a solid, arrowless, labelled link
that is not traceable. No link type limits which stereotypes it may connect, and no stereotype limits its statuses
(owner decision: no built-in restrictions; a user adds limits in the configuration, `sources` and `targets` on a
link type, `statuses` on a stereotype). Fields: priority and owner on REQ, B-REQ, U-REQ; owner on ISSUE, CONSTRAINT, FEAT and the
tests; owner on both ADR kinds (a decision date was removed by ADR-029); severity and likelihood on RISK.
**Consequences.** Only models created after this change get the new defaults; an existing
`specmodel.json` keeps its own configuration and is changed through `config.put`. A tool older than
this change rejects a model that uses a hyphenated key. Everything here is editable in the tool.

## ADR-021 — Identity comes from ssh-agent; the editor proves it before it opens  · stakes: high
**Context.** Owner report (2026-11-15): after `ssh-add -D` the editor still opened and worked as
administrator, because identity was read from the public key (a plain file) and the tool signed with the
private key file itself, asking for the passphrase in the terminal. Owner decision: use `ssh-agent` only,
no pointing at key files.
**Decision.** The tool never reads a private key and never asks for a passphrase. It lists the agent's keys
(`ssh-add -L`) and acts with its one key (see below); signing is `ssh-keygen -Y sign` with the
public key, which makes ssh-keygen sign through the agent. `serve` first signs a random challenge and verifies it
(`Store.prove_identity()`); failure stops start-up. Exactly one key must be loaded: with none or with several the
tool refuses and never picks one (owner decision), so there is no way to act under a key by accident. `init`
registers that one key. There is no key path, no `SPECGRAPH_KEY`, no git-config or `~/.ssh` lookup, and no test
stand-in for `ssh-keygen`; tests choose a key through the `Store(key=...)` argument or by loading just one key.
**Consequences.** An empty or unreachable agent locks the tool, as intended. Windows users run it from Git Bash or
start the OpenSSH agent service. While a key is loaded, any program of the same user can ask the agent to sign
(as with Git). A key without a passphrase is still only as safe as its file. The tests run a private agent;
the Windows named-pipe agent is not tested.

## ADR-022 — A lock marks work in progress; anyone may unlock after a confirmation  · stakes: high
**Context.** Owner decisions (2026-11-15): a lock is temporary and means "someone is working here in
isolation, before releasing to the others"; it is an indicator, not ownership. If the person who set it
is gone (left the company, forgot), the others must be able to clear it.
**Decision.**
1. While a folder is locked, only the lock owner changes it, as before, and now only the owner may
   create a link *to* an element in it (or point an existing link at one). Everyone else is refused by the
   same difference check (`rules.check_change`: tool, commit hook, audit). Viewing and placing the element on
   other diagrams stay possible.
2. Anyone may remove a lock, not only the owner or an administrator. The CLI (`--yes`) and the editor (a
   dialog naming the owner, reason and date) ask for a confirmation when the lock is someone else's; unlocking
   one's own lock needs none. `Store.foreign_unlocks` finds such operations. The unlock is a stamped change, so
   history shows who cleared whose lock and when.
3. Taking over a lock is still not possible: unlock first, then lock.
**Consequences.** Links into locked content cannot be added by others, so traceability to a folder under
work resumes after the unlock. Links made before the lock stay, and the owner can still change the meaning
of the content: the tool does not flag such links as stale (a possible later feature). The lock only protects
others once they have pulled it, so lock, then commit and push. There is no expiry; clearing a forgotten lock
is a deliberate act. Replaces REQ-LCK-04 as written (linking to locked content) and the "owner or
administrator" part of REQ-LCK-02.

## ADR-023 — Generated labels are the type prefix plus the first 8 id characters  · stakes: medium · amended by ADR-026
**Context.** Owner decision (2026-11-15): sequential labels (`REQ-014`, highest number plus one) clash when two
branches create elements in parallel, and a number is reused after a delete, so an old reference in a document can
point at something else. A short form of the id works like a short git hash. Four characters were rejected as too
easy to confuse. Eight make a reference to one item almost certain, which also helps reports written by agents.
**Decision.** `ops._auto_label` returns `<labelPrefix>-<first 8 hex characters of the id>`, for example
`REQ-3d6e7863`. If that label is already in use, characters are added one by one until it is unique. An empty
prefix gives no label. Nothing is counted or stored. Labels stay editable and unique on entry. Existing labels are
not changed; the demo model keeps its hand-typed `REQ-001` style labels.
**Consequences.** No clashes between branches and no reuse after deletes, since an id is never issued twice. The
label is not memorable and shows no order. Two 8-character prefixes in the same model are about a 1% chance in
10,000 elements; the longer label then keeps them apart. `sg.py show`, search and the editor already accept an id
prefix, so a label or the plain 8 characters both find the item.

## ADR-024 — No branch rule; the explorer has a stored order  · stakes: medium · **approved by the owner 2026-11-16**
**Context.** Owner decision (2026-11-16), version 0.2.0. (a) The tool must run on any branch, not only on
`docs/specifications`. (b) People want to put the items of the explorer in their own order by dragging; until now the
tree was sorted by name. (c) Folders are opened and closed together with their sub-folders, and the panes of the
editor are resized by dragging the lines between them.
**Decision.**
1. The branch rule of ADR-009 is removed, not made optional: the tool, the commit check and the editor no longer
   look at the branch. The operation `settings.put` is gone and a new model has an empty `settings`. A
   `settings.branch` written by version 0.1 is left in the file and ignored, so no migration is needed. Teams that
   want changes on one branch only protect it on the git server.
2. Folders, diagrams and elements may carry an optional whole number `order`. The explorer shows the sub-folders,
   then the diagrams, then the elements of a folder, each group by `order`, and the items without one after them by
   name. The new operation `folder.order {id, kind, ids}` numbers the items of one kind in one folder (`ops.py`,
   listed ids first). Moving an item to another folder removes its `order`; the editor sends the move and the new
   order as one batch when an item is dropped between two items of another folder.
3. `order` is a place in the tree, not content: it does not set an element's `modified` (ADR-016), and when two
   branches order the same items the merge keeps ours without recording a conflict (one question per item would
   be noise). Lock rules apply: the content of a folder locked by someone else cannot be reordered. A folder's own
   `order` belongs to its parent, so a locked folder can be placed among its siblings by anyone who may change the
   parent (`rules.check_change`).
4. Which folders are open and how wide the panes are is not model data. The open folders live in the page; the
   pane sizes are kept in the browser's `localStorage` and are lost with it. Nothing is written to the file.
**Consequences.** Nothing stops a change on the wrong branch any more. `order` is an optional key, so the format
version stays 2 and version 0.1 still reads the file (it ignores the order and still enforces an old
`settings.branch`). The first reorder in a folder numbers all items of that kind there, which touches several
lines of the file. An order chosen on the other branch can be lost in a merge; drag again. Items of different
kinds cannot be mixed in the tree.

## ADR-025 — The pre-push hook checks only the commits being pushed  · stakes: medium · **approved by the owner 2026-11-21**
**Context.** Owner request (2026-11-21), version 0.3.0. The pre-push hook of ADR-006 audits the whole history on
every push. One old finding then blocks every later push, and the user is pushed towards `--no-verify`, which
skips the check for the new commits too.
**Decision.**
1. The pre-push hook reads the refs git hands it on stdin and audits only the commits that the remote does not have
   yet: for each pushed ref, `<local sha> --not <remote sha> --remotes=<remote>`. A deleted ref is skipped. A new
   branch is checked from where it leaves what the remote already has. Findings in these commits block the push,
   as before.
2. `sg.py audit` run by hand still checks the whole history of `HEAD` and reports every finding. A new form
   `sg.py audit <from> <to>` checks only the commits from `<from>` to `<to>`, both included. `--rev` and `--since`
   stay for scripts.
3. Hooks installed by an older version keep auditing the whole history until `sg.py install-hooks` is run again;
   it replaces its own hooks without `--force`.
**Consequences.** A push no longer re-checks old commits, so an old finding is no longer reported on every push:
it is seen only when someone runs `sg.py audit`. Pushing a branch that is not on the remote yet checks all its
commits that are not on any branch of that remote.

## ADR-026 — Changing an element's type gives it a new generated label  · stakes: medium · **approved by the owner 2026-11-21**
**Context.** Owner request (2026-11-21). After a type change (ADR to REQ) the label still shows the old prefix
(`ADR-3d6e7863`), which reads as the wrong type. ADR-023 said existing labels are never changed.
**Decision.** When `element.update` changes the stereotype and the call does not pass a `label`, the label is
replaced by a new generated one for the new type (`ops._auto_label`, ADR-023), for example `REQ-3d6e7863`. This
applies to every old label, also a hand-typed one such as `ADR-001`. A new type with an empty prefix gives no
label. A `label` passed in the same call wins. ADR-023 is amended: labels are not changed, except on a type change.
**Consequences.** The label always matches the type after a type change. A reference to the old label in a
document, commit message or report no longer finds the element; the id prefix still does. Hand-typed labels are
lost on a type change; type the label again if it is still wanted.

## ADR-027 — Editor: multi-selection, alignment and a snap grid  · stakes: low · **approved by the owner 2026-11-21**
Ctrl+click adds or removes a node of a diagram from the selection; Shift+drag on the empty canvas selects every node
touching the rectangle. A selection moves as one: its nodes and the bend points of links between them move
together, links to other nodes follow while dragging, and the result is one `diagram.layout` batch (one undo
step). Alignment lines the selected nodes up with the last selected node (the set of alignments is in ADR-028). The grid size and the snap switch are view state kept in the browser (like the pane
sizes, ADR-024); nothing is stored in the model. Everyone starts with the same default: a 20-pixel grid, snap on. Snapping puts the top-left corner of a node on the grid when it is created or moved (in a group move: the dragged
node; the others keep their distance to it) and the lower-right corner when it is resized. Alignment is not snapped:
the edges or centres must line up exactly. While snapping is on, the grid is shown as dots in place of the plain background dots; it is not exported.

## ADR-028 — Editor: an overview of the diagram and six alignments in a submenu  · stakes: low
Owner request (2026-11-21). **Overview:** a small map of the whole open diagram at the bottom right of the canvas,
with a box for the part in view. A click there centres the view on that point; dragging the box moves the view. It
scales to fit the diagram and the view together, keeps that scale while dragging, draws nodes in their type colours
and links as straight lines, and is not exported. An *Overview* switch in the diagram tools hides it; the browser
keeps that choice (view state, like the grid). It covers a corner of the canvas: pan or hide it to reach what is
under it. **Alignment** replaces the two centre alignments of ADR-027 with six, in a submenu Align ▸ Horizontal
(left, center, right: Ctrl+Shift+1/2/3, same x of an edge or the centre) and Align ▸ Vertical (top, center, bottom:
Alt+Shift+1/2/3, same y). This swaps the meaning of the earlier names: *vertical center* (Alt+Shift+2) now lines
centres up in one row, *horizontal center* (Ctrl+Shift+2) in one column. The menu helper gains submenus
(`[label, [items]]`), opened on hover and to the left near the right edge of the window.
**Export and zoom** (owner request, same day): *Export SVG* and *Export PNG* move into an *Export* menu, which also
copies the diagram to the clipboard as a PNG image (Clipboard API; the editor's 127.0.0.1 address counts as a secure
origin). A PNG is drawn at twice the size, less when that would pass the browsers' canvas limits (16000 pixels a side,
64 million pixels in all), so a very large diagram is scaled down instead of failing. *Fit* and the wheel zoom out to
2% instead of 20%: text is unreadable there, but the whole diagram fits; nothing else depends on the zoom. The snap
dots are not drawn when they would be closer than 4 screen pixels.

## ADR-029 — No decision date field; notes mark, Shift+click and a tab icon  · stakes: low
Owner decisions (2026-11-21). **Decision date:** the default ADR and TEMPORAL-ADR types no longer have a typed
`decisionDate` field. Every element already records its last change (`modified`, ADR-016), and a date that matters
for a decision goes into its notes. Only new models are affected; an existing model keeps the field and its values
until someone deletes the field under Configure → Stereotypes. The example model is rebuilt without it.
**Notes mark:** an element whose notes are not blank shows a scroll badge (📜 in a blue circle) at the top right of its box (left of
the lock badge when both are shown) and a 📜 in the tree; the tooltip shows the first 300 characters of the notes. The badge
is part of the drawing, so it is also exported. **Shift+click** on a node adds or removes it like Ctrl+click; a Shift
press that moves more than 3 pixels is a rectangle selection, as before. **Tab icon:** `web/favicon.svg`, a page with a
small graph on it (the owner's pick of four designs), served as one more file of the fixed static list (`server.STATIC`); `/favicon.ico` still answers
204 for browsers that ask for it.

## ADR-030 — Auto size: whole text visible, always landscape  · stakes: low
Owner request (2026-11-21). **Rule** (`app.js`, `fitSize`): fonts never change. The width of a node is a minimum
(190 for a new one); it grows when the top line («type» and label), the status pill or the longest word of the
topic would not fit. The topic is wrapped at that width and the height is just enough for all its lines, the top line
and the pill (an ellipse needs more, its text area is smaller). The box is always landscape: width / height above
1.2, never equal; when the text would need a portrait box the width grows instead, in grid steps when snapping
(10 pixels otherwise), and both sides end on the grid. **When:** with *Auto size* on (diagram tools, kept by the
browser like *Snap*, on by default) a node is fitted when it is placed, when the element's topic, label or type
changes (on every diagram it is on, in the same change as the edit, so one undo step; diagrams in a folder locked by
someone else are left alone, since their change would refuse the whole edit), and while its width is dragged (the
height follows; dragging the height alone does nothing). *Fit to text* in the context menu fits one node or a
selection whatever the switch says. With the switch off, sizes are manual and any shape is allowed. **Limit:**
text is measured in the browser, so a change made with `sg.py apply` or by an agent is not fitted; *Fit to text*
fixes that later. For a type change the editor measures the label the server will generate (ADR-026).
**Additions (same day):** the label ends left of the lock and notes badges, and the fitted width leaves them that room.
Switching *Auto size* on fits the selected nodes at once. Ctrl+A selects every node of the open diagram; the tree
shows the selected elements grey and the last selected (the alignment reference) blue. *Fit* keeps
the corner of the overview free: it fits the diagram beside or above the overview, whichever gives the larger picture.
