# Security review of specgraph 0.1.0

- **Reviewed by:** Claude (model Fable 5.2), an AI model made by Anthropic, at the request of the project owner.
- **Date:** 2026-11-15.
- **Question asked:** does the software do harm on purpose (steal data, communicate in secret, run hidden code), and does it have security weaknesses?

## What this document is, and is not

- It is a statement of what was checked, how, and what was found, for the exact files listed at the end.
- It is **not a cryptographic signature**. An AI model holds no signing key. The statement is tied to the
  code by the file hashes at the end: if a file's hash differs, this review does not cover it.
- It is **not a certification or a guarantee**, and not an independent audit. The same AI model wrote
  much of this code, so the review is not by a separate party. No human security specialist has
  reviewed the code.
- A review can show that problems were not found. It cannot prove that none exist.

## Result

**No harmful behaviour was found.** In the reviewed files there is no code that sends data anywhere,
no connection to any machine other than your own, no hidden or encoded code, no reading of private
keys, passwords, browser data or files outside the repository it works in, and nothing that runs
text from the model as a program.

**No high- or medium-severity weakness was found.** Eight low-severity points and limits are listed
below so that users can judge them.

## What the software does on your machine

| Area | Finding |
|---|---|
| Network | The only network code is the local editor server (`specgraph/server.py`). It listens on `127.0.0.1` only. Nothing in the tool opens a connection to another machine. No telemetry, no update check. |
| Browser page | Three local files. No external script, font, image or link. The page talks only to the local server. A content security policy forbids everything else, so even a model file with hostile content cannot make the page load from or send to another site. |
| Programs it starts | `git`, `ssh-keygen` and `ssh-add`, always with an argument list (no shell). Your default browser, once, to open the local link. Nothing else. |
| Files it reads | The model file, its deleted-elements log, the three page files, `.gitattributes`, an existing git hook (to see whether it is its own), and git objects through `git`. Public keys only: from `ssh-agent`, never a private key file. |
| Files it writes | The model file (through a temporary file next to it), a `.lock` file next to it, the deleted-elements log, `.gitattributes`, two git hooks and the merge-driver setting (only on `install-hooks`), and short-lived files in a private temporary folder for signing. |
| Secrets | It never reads a private key or a passphrase. Signing is done by `ssh-keygen` through `ssh-agent`. |
| Dynamic code | No `eval`, `exec`, `pickle`, dynamic import or encoded data in the Python code. No `eval`, `innerHTML` or script injection in the page code. |
| Dependencies | Python standard library only. No third-party package is installed or bundled to run the tool. |

## How it was checked

1. **Reading the code.** All Python files of the tool (about 2,750 lines), the page code and the sample
   scripts were searched for every network, process, file, environment and dynamic-code call, and the
   places found were read. The server, signing, git and hook code were read in full.
2. **Probing the running server** from outside the page. All of these were refused as intended:
   a request without a token or with a wrong token; a token placed in the address instead of the
   header; a foreign `Host` header (the "DNS rebinding" attack); attempts to fetch files outside the
   three page files (`/../sg.py`, encoded variants, `/specmodel.json`, `/.git/config`); a write sent
   as a plain web form; a write from a foreign host; an oversized request; a cross-site preflight
   request. A connection through the machine's network address was refused: the server is reachable
   from the same machine only. The model file was unchanged after the probes.
3. **Watching what it does.** The test suite (59 tests, without the browser tests) was run with a
   Python audit hook that records every network call, every program started and every file opened for
   writing, in the tool and in every Python process it starts. Result: every network call went to
   `127.0.0.1`; the programs started were `git` and the OpenSSH programs from the Git installation;
   every file written was inside the test's own temporary folders.
4. **Tests.** All 62 automated tests pass, including the browser tests and the tests that try to
   bypass locks, forge stamps and edit the file by hand.

## Low-severity points and limits

1. **The access token is visible to other programs of the same user.** `serve` prints the link with
   the token and hands it to the browser. Another program running under your account could read it.
   Such a program could already edit the model file directly, so this adds little.
2. **Git hooks are written with your paths inside double quotes.** If the path to Python or to the
   model contained a `"`, `$` or backtick character, the hook would break or the shell would interpret
   that text. Only your own folder names are involved.
3. **The environment decides which programs run.** `SPECGRAPH_SSH_KEYGEN`, `SPECGRAPH_SSH_ADD` and
   `PATH` choose the `ssh-keygen`, `ssh-add` and `git` that are started. Whoever controls your
   environment controls the tool. This is normal for command-line tools.
4. **Running the tool means running the code in your copy.** After `install-hooks`, git also runs it
   on commit, push and merge. If you pull a changed `sg.py` or `specgraph/` from someone else, that
   code runs as you. Review updates to the tool as you would any program.
5. **What the signatures prove is limited** (ADR-003 in `docs/ADRS.md`). They detect edits made
   outside the tool and name a registered key. They do not stop a registered user from making any
   change the rules allow, the first version of a model trusts its own user list, and the
   deleted-elements log is not signed.
6. **A hostile model file was not tried in the browser.** The page writes model text as text and the
   content security policy blocks outside connections, but no test opened a deliberately malicious
   model.
7. **The tests are less strict than the tool.** The browser tests start Chrome with its sandbox
   switched off (against the local page only), and the tests create throwaway keys and a private
   `ssh-agent`. This affects people who run the tests, not users of the tool.
8. **Stale lock file.** A `.lock` file older than 60 seconds is removed by the next writer. Two
   writers at that exact moment could both proceed. The effect would be a lost change, not a leak.

## Not covered

- Python, Git, OpenSSH and the browser themselves.
- Linux and macOS: everything was run on Windows 11 with Python 3.13 and Git Bash.
- Fuzzing, or a search for mistakes in the merge and validation logic beyond what the tests exercise.
- Anything changed after this review: check the hashes.

## Reviewed files

31 files. Each hash is the git object id of the file; check one with `git hash-object <file>`, or
all of them against `git ls-files -s`.

| File | Git object id |
|---|---|
| `.gitattributes` | `3763ad9334a2b7a13e948d0a566557ddc4eafb65` |
| `.gitignore` | `77ac75498fba8af48ba35bda27fca8ff915cdff3` |
| `sample/build_example.py` | `0b6616c59fd9bc13b40ed476ec12a47ec2955ef5` |
| `sample/build_sample.py` | `1d2198c4fc2789e364ee3b7a925e875222d49e8f` |
| `sg.py` | `368f799da2624a4ef9d5d68039b61bce277ad6fd` |
| `specgraph/__init__.py` | `5c7a00dfbf20e84299123eb89c2d981037d06b49` |
| `specgraph/__main__.py` | `8dc43872898801f27d1945e099aac3bdc255c005` |
| `specgraph/audit.py` | `e533f1f0aeb82c03234c87d622833d50cb4abb01` |
| `specgraph/cli.py` | `2314c71e94c9adf48ed6818873b8a8ad5ace9316` |
| `specgraph/defaults.py` | `acbb1791950d8236a031f46d4eba11388aa40b2b` |
| `specgraph/gitio.py` | `4c2aa642307f6a128a04c8ca0470ca32b69566cd` |
| `specgraph/history.py` | `0b7372d9dfb88882741ba1058e26d4dd2d399efb` |
| `specgraph/hooks.py` | `fddb88cbc4eda6cd6dfe28c55b9e1b95e1bfdc3e` |
| `specgraph/merge.py` | `e034ba32d33072d68b3531639cf6959b8d82418b` |
| `specgraph/model.py` | `6f4da6a02b891af6771a2661d55d8d5c6f4b359b` |
| `specgraph/ops.py` | `c4ec107bd24a6d61f28a8138f406abe0a75ba4d4` |
| `specgraph/query.py` | `9e6309872dcd4da72a4eeee37d2b718d1f4d33b2` |
| `specgraph/rules.py` | `e9be833aebad62250f939f8e0a74de0d6a647ea1` |
| `specgraph/server.py` | `cdddff801cdd7eb0cf3cd9d971792f66fbb02030` |
| `specgraph/stamp.py` | `42c0a2897f9632c245efabe7d0479c5ddd685407` |
| `specgraph/store.py` | `caac1b0f543cfed4d86d606532fdd684a390c1f3` |
| `specgraph/validate.py` | `27bda3de71b8e3668b458ec14f948cc3781bc489` |
| `specgraph/web/app.js` | `85a70c3c135c13f15f1c326567c65fc7e6edfc0f` |
| `specgraph/web/index.html` | `0b7d626233be268c043121d8aed02b79e3ed4bf4` |
| `specgraph/web/style.css` | `2f42a450bfe2d89e457a89d069745e3fef1dea30` |
| `tests/conftest.py` | `1555d157ab8f95c6db45a844b8ebc2f2fc7b80d7` |
| `tests/test_changes.py` | `996911ba8527aa6ce952d580a2e8de28f05d7789` |
| `tests/test_core.py` | `e713e73a81e4f4f1e886aacb97d7dd56fb402248` |
| `tests/test_example.py` | `c8634f58c44151ad09d8dbac5dbeb93253641816` |
| `tests/test_integrity.py` | `5fe5be56447eb450d5de4dcaed23c28c2a25b4cc` |
| `tests/test_ui.py` | `e93ef7278546babb79919ac2e2819df3756eb1cc` |
