# CLAUDE.md — specgraph

## What this is

A graph of specifications: elements of any user-defined type (requirements, decisions,
rules, risks, tests, ideas, …) and typed links between them, kept as a linked model in
**one JSON file in the Git repo** (`specmodel.json`). People edit it in a local browser
editor; agents read the file directly and change it through a command.

Simplicity is a primary goal. This is not a general UML tool. Every feature beyond
`docs/` requirements needs a justification.

## Hard rules

1. **Never edit `specmodel.json` by hand** (no Edit/Write, no sed, no scripts writing it).
   Change it only with `sg.py apply`. A hand edit breaks the signed stamp: the tool goes
   read-only for everyone and the commit hook and history audit report it.
2. **Standard library only.** No pip packages, no Node/npm, no build step, no bundled
   third-party code. Runtime needs only Python, `git` and `ssh-keygen`.
3. **Licence is MIT.** Do not copy code from elsewhere into the project.
4. **In `web/app.js`, never use `innerHTML`** or string-built HTML. Use the `h()`, `sv()`
   and `put()` helpers. The CSP forbids inline scripts and `eval`.
5. **The server stays local**: bind `127.0.0.1` only, token on every `/api/` call, Host
   header check, fixed static file list. Do not weaken these.
6. The tool works on whatever branch is checked out (ADR-024). There is no branch rule; do not add one back
   without an ADR. An old `settings.branch` in a model is ignored.
7. High- and medium-stakes design changes need a new or updated ADR in `docs/ADRS.md`
   and the owner's approval before implementation.

## Requirements to run

- Python 3.8+ (tested on 3.13)
- Git (2.28+ for the demo builder)
- `ssh-keygen` and `ssh-add` (ship with Git/OpenSSH) and an SSH key **loaded in `ssh-agent`**; on Windows use Git Bash
- A desktop browser

## Python setup (when someone asks how to set up Python)

The tool is tested on Python 3.13. If the machine's default Python is a different
version, or things fail to start, create a project-local `.venv` with `uv`. Run all
commands from the tool's folder.

**Windows (cmd)**

```
pip install uv
python -m uv python install 3.13
python -m uv venv --python 3.13 .venv
.venv\Scripts\activate
python --version
```

**Linux / macOS**

```
pip install uv
python -m uv python install 3.13
python -m uv venv --python 3.13 .venv
source .venv/bin/activate
python --version
```

Notes for the agent helping with this:

- After `pip install uv`, the `uv` command is often not on PATH (Windows prints
  "'uv' is not recognized"). Always use `python -m uv …` instead; do not try to fix PATH.
- `python --version` must print 3.13.x after activation. If it does not, the venv is
  not active in that terminal.
- The venv must be activated in **every new terminal** before running `sg.py`.
- The tool itself needs **no packages**. Do not install anything into the venv to run it.
- Only for running the tests: `python -m uv pip install pytest`
  (optional: `playwright` for browser tests).
- Run `python sg.py install-hooks` **with the venv active**. The git hooks and merge
  driver store the path of the Python that installed them. If `.venv` is deleted, moved
  or recreated, run `python sg.py install-hooks --force` again.
- Add `.venv/` to `.gitignore`; never commit it.
- On Windows, `git` and `ssh-keygen` come from Git for Windows. If `ssh-keygen` is not
  found, set `SPECGRAPH_SSH_KEYGEN` to its full path
  (usually `C:\Program Files\Git\usr\bin\ssh-keygen.exe`).

## First-time setup problems (read this when helping a new user)

Problems a new Windows user typically hits, in order. Check these before anything else.

1. **Wrong folder.** `sg.py` is in the repository root; run `python sg.py …` from there.
   "can't open file …\sg.py" means the terminal is in another folder.
2. **Branch.** Any branch works. `git switch <branch>` fails with "invalid reference" when the
   branch does not exist: use `git switch -c <branch>`. A brand-new repo needs one commit first.
3. **Commands pasted into cmd.** Trailing `# comments`, `source`, `ls`, `curl | sh` are
   not Windows cmd. `source .venv/bin/activate` is `.venv\Scripts\activate`. Shortcuts
   such as `gm`, `gl`, `gs` are the user's own aliases, not part of the project.
4. **`uv` not recognised after `pip install uv`**: use `python -m uv …` (see below).
   Typo check: `pip instal` fails with a confusing traceback.
5. **Key and agent (ADR-021).** The tool never reads a private key file and never asks for a
   passphrase: it asks `ssh-agent` which keys are loaded and uses the one registered in the model.
   Nothing to configure. "no key is loaded in ssh-agent" / "cannot reach ssh-agent": in Git Bash run
   `eval "$(ssh-agent -s)"` then `ssh-add` (Windows cmd/PowerShell: start the "OpenSSH Authentication
   Agent" service, then `ssh-add`). Exactly one key must be loaded: with several the tool refuses and never
   guesses (`ssh-add -D`, then `ssh-add <key>`). There is no `SPECGRAPH_KEY` any more. `ssh-add -D` locks
   everyone out, which is intended.
6. **Never commit a private key.** A user may keep a key in the project folder on purpose; do
   not tell them to move it to `~/.ssh/`. Just make sure it and its `.pub` are in `.gitignore`.
7. **`whoami` before `init`** fails with "cannot read …specmodel.json". Expected: run `init` first.
8. **Administrator name** comes from `git config user.name` with spaces turned into dots
   ("Ann Smith" → `Ann.Smith`). Override with `init --user NAME`.
9. **Editor start-up.** `serve` signs a challenge through the agent first and refuses to open if it
   cannot. A key without a passphrase is only as safe as the file; advise a passphrase.
10. **"LF will be replaced by CRLF" warnings** on `git add` come from Windows
    `core.autocrlf=true`. `.gitattributes` starts with `* text=auto eol=lf`, which removes
    them for all files; keep that line (`install-hooks` only appends the model rule).
11. After `install-hooks`, commit `.gitattributes` together with `specmodel.json`.

## Running it

Run these from the repository root, where `sg.py` is.

```
python sg.py init            # once per model; caller becomes administrator
python sg.py install-hooks   # once per clone: hooks + merge driver
python sg.py serve           # editor; prints a link with a one-time token
python sg.py whoami          # which user the local SSH key maps to
```

`serve` options: `--port N` (default 8765), `--no-browser`, `--undo N` (undo steps, default 20). Open exactly the printed link;
without its token the page is refused.

Example model in a throwaway local repo (no remote needed):

```
python sample/build_example.py /tmp/example
python sg.py --file /tmp/example/specmodel.json serve
```

`specmodel.example.json` (repository root) is the stored output of that script, signed by a
throwaway key: readable with `--file`, not editable. Never edit it by hand; to change the example,
change `sample/build_example.py`, run it, copy its `specmodel.json` over the stored file and retake
`docs/img/*.png` (README). `sample/build_sample.py` is the smaller demo used by the browser tests.

Environment variables: `SPECGRAPH_FILE` (model path),
`SPECGRAPH_SSH_KEYGEN` / `SPECGRAPH_SSH_ADD` (paths to ssh-keygen / ssh-add), `SPECGRAPH_UNDO` (undo steps of the editor). 

## Reading the model

Read `specmodel.json` directly; the format is in `docs/FORMAT.md`. Or query (JSON output):

```
sg.py search "text" [--stereotype REQ] [--status approved] [--folder <id>] [--unused]
sg.py show <id | id-prefix | label>
sg.py trace <id>        sg.py impact <id>       sg.py matrix ADR REQ [--types implements]
sg.py history <id>      sg.py validate
```

## Changing the model

```
sg.py apply '[{"op": "element.update", "args": {"id": "<id>", "status": "approved"}}]'
```

- A JSON list of operations (argument or stdin), applied atomically.
- `"$N"` refers to the id created by operation N in the same batch.
- `sg.py ops` lists every operation and its arguments. Details: `docs/AGENTS.md`.
- `element.delete` needs `--yes`; without it, usage is printed and the exit code is 3.
- Exit code 2 = refused (validation, lock, identity); read stderr.
- `sg.py audit` checks the whole history; `sg.py audit <from> <to>` only that range (both included). The
  pre-push hook checks only the commits being pushed (ADR-025).
- A folder lock by another user blocks changes to everything under it, and new links to it
  (ADR-022). A lock means "someone is working there". Do not work around it. Anyone may
  unlock (`folder.unlock`, `--yes` for another user's lock), but never do that on your own:
  ask the user, who decides whether the owner is really gone.

- A deleted element is appended to `specmodel.deleted.jsonl` (ADR-018). Never edit that file;
  stage it together with `specmodel.json`.

After changes: `sg.py validate`, then commit normally. The pre-commit hook runs
`sg.py check --staged`.

## Common problems

| Message | Meaning / fix |
|---|---|
| "your SSH key is not registered" | An administrator must add the public key under Users (`user.add`) |
| "content does not match its stamp" | File was edited outside the tool. `git checkout -- specmodel.json`, or `sg.py adopt` to take responsibility |
| "model is edited on branch X but you are on Y" | A copy of the tool older than 0.2.0 is running; since ADR-024 there is no branch rule |
| "not valid JSON … conflict markers" | Merge ran without the driver: `sg.py resolve` |
| Merge conflicts listed under Check | A person chooses per conflict in the editor, then `git add` + commit |
| "ssh-keygen was not found" | Install Git/OpenSSH or set `SPECGRAPH_SSH_KEYGEN` |
| "signing failed" / "cannot prove that you hold the private key" / "no key is loaded in ssh-agent" | Key not in `ssh-agent`: `ssh-add` (first-time item 5) |
| "deleted element(s) are not recorded in the staged …deleted.jsonl" | `git add specmodel.deleted.jsonl` |
| "has no author and date" | An element lost its `modified` entry (hand edit or old tool): restore the file from git, or make any change through the tool, which fills it in |

## Code map

```
sg.py                 entry point
specgraph/
  __init__.py         TOOL_NAME, VERSION, defaults
  model.py            canonical JSON, hashing, atomic save, file lock
  defaults.py         initial stereotypes, statuses, link types
  ops.py              every change operation (pure, no disk access)
  validate.py         model validation, field and config checks
  rules.py            who may change what (locks, admin-only), checked on a diff
  query.py            search, usage, trace, impact, matrix
  stamp.py            SSH identity, signing, integrity check
  store.py            the single write path: load → check → ops → rules → stamp → save;
                      undo (editor only) and the deleted-elements log
  merge.py            model-aware three-way merge, conflicts
  audit.py            checks for staged file and for branch history
  history.py          element history from git
  hooks.py            installs git hooks and merge driver
  cli.py, server.py   command line; local HTTP API
  web/                index.html, style.css, app.js (plain JS, SVG diagrams)
tests/                test_core, test_integrity, test_changes, test_example, test_ui (browser, optional)
docs/                 FORMAT.md, AGENTS.md, ADRS.md, REQUIREMENTS.md, REQUIREMENTS-COVERAGE.md,
                      SECURITY-REVIEW.md (lists a hash per reviewed file: it goes stale when code changes)
sample/                build_example.py (README example), build_sample.py (demo for the browser tests)
specmodel.example.json  stored example model (output of build_example.py)
```

## Design invariants (do not break without an ADR)

- All writes go through `Store.apply`; UI, CLI and agents share it. Logic belongs in
  Python, not in `app.js`.
- Items are stored under random UUIDs that never change; all references use ids.
- Data refers to configuration by stable key (`REQ`, `approved`), never by label.
- Elements and links belong to the model; diagrams store layout only.
- Serialization is canonical (sorted keys, one value per line, LF). An unchanged model
  must produce identical bytes.
- Lock and user rules are checked on the difference between two states
  (`rules.check_change`), so the same check serves the tool, the commit hook and the audit.
- The tool creates no file per element, folder or diagram.
- `elements.<id>.modified` is set in one place (`ops.touch`, called by `apply_ops`), never by an operation.
- `specmodel.deleted.jsonl` is append-only and is never read to decide anything except by the
  pre-commit check.
- The order of the explorer is the optional `order` of folders, diagrams and elements, written only by
  `folder.order` (ADR-024). Open folders and pane sizes are view state of the browser, never model data.
- The tool version is `VERSION` in `specgraph/__init__.py` (shown by `--version`, in the editor
  bar and in every stamp). Raise it when behaviour changes.

## Developing

- Test first: write or extend a failing test, then implement. Name tests after the
  requirement (`test_cfg07_…`) and update `docs/REQUIREMENTS-COVERAGE.md`.
- Run: `python -m pytest tests` (needs `pytest`). Browser tests need `playwright` and
  Chrome and skip otherwise. Signing tests use the real `ssh-keygen` and a private
  `ssh-agent` they start themselves, and skip without them.
- New operation: add it in `ops.py` with a doc string, cover it in tests, and it appears
  in `sg.py ops` and the API automatically.
- Format change: bump `formatVersion`, write a migration, update `docs/FORMAT.md`.
- Keep `README.md`, `docs/FORMAT.md` and `docs/AGENTS.md` in step with behaviour.
- Add every change a user or agent can notice to `CHANGELOG.md`, under the version that carries it.

## Known limits

- Status transition rules are not implemented.
- Undo has no redo and lives only as long as the editor server (ADR-017).
- Automatic link routing does not avoid other boxes.
- Only the last stamp before each commit is kept; see ADR-003 for what the signature
  does and does not prove.
- Tested on Windows (Git Bash, Python 3.13). Linux and macOS are expected to work but were not
  re-run since the move to ssh-agent signing (ADR-021). The browser tests (playwright) pass on Windows with Chrome; they need `CHROME` set to the path of `chrome.exe` there.

## Not in scope (do not build unless asked)

Real-time collaboration, hosted servers, import/export of other tools' formats, full UML/SysML, mobile use,
index generation, MCP server, baselines, automatic diagram layout.