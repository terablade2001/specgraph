# Security review of specgraph 0.3.1

- **Reviewed by:** Claude (model Opus 5.5), an AI model made by Anthropic, at the request of the project owner.
- **Date:** 2026-11-21.
- **Version:** 0.3.1: release 0.3.0 (commit `68dc2ab`) plus the fixes for two findings of this review
  (ADR-031). The files and hashes are listed at the end.
- **Replaces:** the review of version 0.1.0 (2026-11-15, Claude, model Fable 5.2). This review was done again
  from the start. It did not reuse the earlier result.
- **Question asked:** does the software do harm on purpose (steal data, communicate in secret, run hidden
  code), and does it have security weaknesses?

## What this document is, and is not

- It says what was checked, how, and what was found, for the exact files listed at the end.
- It is **not a cryptographic signature**. An AI model holds no signing key. The statement is tied to the
  code by the file hashes at the end. If a file's hash differs, this review does not cover that file.
- It is **not a certification, a guarantee or an independent audit**. Claude models wrote most of this
  code. This review was done by a different model version, but it is still not an outside party. No human
  security specialist has reviewed the code.
- A review can show that problems were not found. It cannot prove that none exist.

## Result

**No harmful behaviour was found.** The reviewed files contain no code that sends data anywhere and no
connection to any machine other than your own. They contain no hidden or encoded code. They do not read
private keys, passwords, browser data or files outside the repository the tool works in. Nothing runs text
from the model as a program.

**One medium-severity weakness was found in 0.3.0 and is fixed in 0.3.1.** A merge accepted a model
edited by hand on another branch without a warning, and stamped it under the name of the person merging
(point 1 below). A low-severity weakness in the page was fixed with it (point 3). Both fixes have tests,
and the trials that found the weaknesses were run again against 0.3.1. **No high- or medium-severity
weakness remains known.** Eight low-severity points and limits remain, listed below so that users can
judge them.

## What changed since the 0.1.0 review

Every file was read again. The changes that matter for security:

- The server serves a fourth static file, `favicon.svg` (a fixed drawing, no script).
- The pre-push hook passes the remote name (`"$1"`) to `sg.py` and reads the refs git hands it on stdin.
  It now checks only the commits being pushed (ADR-025). This is safe in itself, but see point 2.
- `audit <from> <to>` takes two revisions from the command line and passes them to `git rev-list`.
- The branch rule was removed (ADR-024). A new `order` field and the `folder.order` operation follow the
  lock rules (checked).
- The editor page gained multi-selection, alignment, a grid, an overview, PNG export and copy to clipboard.
  It still builds every element with `textContent` / `setAttribute`. It has no `innerHTML`, no `eval`,
  and makes no request except to its own server.

## What the software does on your machine

| Area | Finding |
|---|---|
| Network | The only network code is the local editor server (`specgraph/server.py`). It listens on `127.0.0.1` only. Nothing in the tool opens a connection to another machine. No telemetry, no update check. |
| Browser page | Four local files. No external script, font, image or link. The page talks only to the local server. A content security policy forbids everything else, so even a hostile model file cannot make the page load from or send to another site (tried, see below). |
| Programs it starts | `git`, `ssh-keygen` and `ssh-add`, always with an argument list (no shell). Your default browser, once, to open the local link. Through git: its own hooks and merge driver, which run `sg.py` again. Nothing else. |
| Files it reads | The model file, its deleted-elements log, the four page files, `.gitattributes`, an existing git hook (to see whether it is its own), the merge driver's three temporary files from git, and git objects through `git`. Public keys only, from `ssh-agent`. It never reads a private key file. |
| Files it writes | The model file (through a temporary file next to it), a `.lock` file next to it, the deleted-elements log, `.gitattributes`, two git hooks and the merge-driver setting (only on `install-hooks`), and short-lived files in a private temporary folder for signing. |
| Secrets | It never reads a private key or a passphrase. Signing is done by `ssh-keygen` through `ssh-agent`. The editor's access token is random (192 bits), compared in constant time, kept for the browser tab only (`sessionStorage`), and removed from the address bar on load. |
| Dynamic code | No `eval`, `exec`, `pickle`, dynamic import or encoded data in the Python code. No `eval`, `innerHTML`, `new Function` or script injection in the page code. |
| Dependencies | Python standard library only. No third-party package is installed or bundled to run the tool. |

## How it was checked

1. **Reading the code.** All Python files of the tool (about 2,840 lines) were read. They were also
   searched for every network, process, file, environment and dynamic-code call. The page code (about 1,370
   lines of JavaScript) was searched for every place where model text reaches the page, the network,
   storage or the clipboard, and those places were read. The server, signing, git, hook, audit, merge,
   store and rule code were read in full. So was the whole change since version 0.1.0, and the two fixes
   of 0.3.1.
2. **Probing the running server** from outside the page, with 31 hostile requests. All were refused as
   intended:
   - a request without a token, with a wrong token, or with the token in the address instead of the header;
   - a foreign, look-alike or empty `Host` header (the "DNS rebinding" attack);
   - ten attempts to fetch files outside the four page files (`/../sg.py`, encoded variants,
     `/specmodel.json`, `/.git/config`, `/C:/Windows/win.ini` and others);
   - a write sent as a web form or as plain text, a write without a token or from a foreign host;
   - an oversized or negative request length, a body that is not a JSON object, an unknown operation;
   - a delete without confirmation;
   - a cross-site preflight request (answered without any permission header);
   - malformed queries.

   A connection through the machine's network address was refused: the server can be reached from the
   same machine only. The model file was byte-for-byte unchanged after the probes. The probes were run on
   0.3.0 and again on 0.3.1, with the same result.
3. **A hostile model in the browser.** This was listed as untried in the 0.1.0 review. A model was edited
   by hand so that element topics, notes, labels, folder, diagram, type and link names contained
   `<script>`, `<img onerror>`, `<svg onload>` and `javascript:` text. Type, status and link colours
   contained CSS that loads an image from another site. The editor was opened on it in Chrome.
   - In both versions all text was shown as text. No script ran, no element got an event attribute, and
     no image element was created.
   - In 0.3.0 the CSS in a type colour reached an inline style (point 3). The content security policy
     blocked the outside image every time (9 attempts in the console).
   - In 0.3.1 no hostile colour appears in any style or drawing, and the page made no attempt to reach
     another site. A browser test now does the same check (`test_sec_colours_*`).
4. **Watching what it does.** The test suite without the browser tests (66 tests on 0.3.1) was run with a
   Python audit hook. The hook recorded every network call, every program started and every file opened
   for writing, in the tool and in every Python process it started, the git hooks included. Results, the
   same on 0.3.0 and 0.3.1:
   - Every network call went to `127.0.0.1`, to the tests' own editor servers.
   - The programs started were `git` and the OpenSSH programs `ssh-keygen`, `ssh-add` and `ssh-agent`.
     `ssh-agent` is started by the tests only.
   - Every file written was inside the tests' temporary folders, Python's private temporary folders for
     signing, or git's temporary merge files.
5. **Tests.** All 81 automated tests pass on 0.3.1, the browser tests included (Windows 11, Python 3.13,
   Chrome). Some of them try to bypass locks, forge stamps, edit the file by hand, push bad commits and
   merge a hand-edited branch.
6. **A merge of a hand-edited branch** was tried in a scratch repository, on 0.3.0 and on 0.3.1 (point 1).

## Findings, points and limits

1. **Medium, fixed in 0.3.1: a merge laundered a hand edit.** In 0.3.0 the merge driver and `sg.py resolve`
   did not check the stamps of the two versions they merged. Tried: user *bob* edits the file by hand to
   make himself an administrator, and commits with `--no-verify`. User *ada* merges that branch. The merge
   succeeded without a warning, and the result was stamped and signed by *ada*. The editor and
   `sg.py check` then reported the file as intact. The merge commit also passed the commit hook and the
   audit, because every item in it equals one of its parents. Only a full `sg.py audit` still showed the
   hand edit, at its own commit.
   **Fix (ADR-031):** before merging, the driver and `resolve` check our and their version the way the
   editor checks the working file. If either was changed outside the tool, nothing is written and git
   reports the model as conflicted with our version in place. The same trial on 0.3.1: the merge stops,
   *bob* stays a plain user, and *ada*'s file is unchanged and intact. **Remaining limit:** someone who
   edits their side, adds their own key to it and signs with that key passes this check, as with the
   working file (point 7). The commit hook and `audit` still catch that case.
2. **Low: once a bad commit is on the remote, only a full audit finds it.** Since ADR-025 the pre-push hook
   checks only commits the remote does not have yet. Hooks run on each person's machine and can be skipped
   with `--no-verify`. Nothing on the git server checks the model. A bad commit pushed that way is reported
   only when someone runs `sg.py audit` without arguments, or when someone tries to merge it (point 1).
   Run the full audit now and then, for example in CI.
3. **Low, fixed in 0.3.1: a colour from a hand-edited model reached an inline style.** In 0.3.0 the small
   type chip in the editor (tree and properties) put the stereotype's colours into a `style` text without
   checking them. The tool's own operations accept only `#rrggbb` colours, so this needed a model edited
   outside the tool. The content security policy blocked every outside load. **Fix:** the page uses a
   type, status or link colour only when it is `#rrggbb`, and falls back to grey otherwise
   (`specgraph/web/app.js`, `hex`).
4. **The access token is visible to other programs of the same user.** `serve` prints the link with the
   token and hands it to the browser, and the browser may keep the link in its history. Another program
   running under your account could read it while the editor runs. Such a program could already edit the
   model file directly, so this adds little.
5. **Git hooks are written with your paths inside double quotes.** If the path to Python or to the model
   contained a `"`, `$` or backtick character, the hook would break or the shell would interpret that text.
   Only your own folder names are involved.
6. **The environment decides which programs run.** `SPECGRAPH_SSH_KEYGEN`, `SPECGRAPH_SSH_ADD` and `PATH`
   choose the `ssh-keygen`, `ssh-add` and `git` that are started. Whoever controls your environment
   controls the tool. This is normal for command-line tools.
7. **What the signatures prove is limited** (ADR-003 in `docs/ADRS.md`). They detect edits made outside
   the tool and name a registered key. Several things are outside that:
   - They do not stop a registered user from making any change the rules allow.
   - The first version of a model trusts its own user list.
   - The deleted-elements log is not signed.
   - The working file, and each side of a merge, is checked against its own user list. Someone who edits
     the file, adds their own key and signs with it gets a file the editor shows as intact. The commit hook
     and `audit` catch this, because they check against the previous commit's user list.
8. **Running the tool means running the code in your copy.** After `install-hooks`, git also runs it on
   commit, push and merge. When `sg.py` lives inside the repository, the hooks run the `sg.py` of the
   branch that is checked out. If you check out or pull a changed `sg.py` or `specgraph/` from someone
   else, that code runs as you on your next commit. Review updates to the tool as you would any program.
9. **The tests are less strict than the tool.** The browser tests start Chrome with its sandbox switched
   off (against the local page only). The tests also create throwaway keys and a private `ssh-agent`. This
   affects people who run the tests, not users of the tool.
10. **Stale lock file.** The next writer removes a `.lock` file older than 60 seconds. Two writers at that
    exact moment could both proceed. The effect would be a lost change, not a leak.

## Not covered

- Python, Git, OpenSSH and the browser themselves.
- Linux and macOS: everything was run on Windows 11 with Python 3.13, Git for Windows and Chrome 157.
- Fuzzing, or a search for mistakes in the merge and validation logic beyond what the tests and the merge
  trials exercise.
- Anything changed after this review: check the hashes.

## Reviewed files

32 files. Each hash is the git object id of the file. Check one with `git hash-object <file>`, or all of
them against `git ls-files -s`.

| File | Git object id |
|---|---|
| `.gitattributes` | `3763ad9334a2b7a13e948d0a566557ddc4eafb65` |
| `.gitignore` | `77ac75498fba8af48ba35bda27fca8ff915cdff3` |
| `sample/build_example.py` | `17b40729c13c8da20ffa4e4a293892110d028a33` |
| `sample/build_sample.py` | `1d2198c4fc2789e364ee3b7a925e875222d49e8f` |
| `sg.py` | `368f799da2624a4ef9d5d68039b61bce277ad6fd` |
| `specgraph/__init__.py` | `e4ea5f2e2853a029e7c057454a63fe40c0786f66` |
| `specgraph/__main__.py` | `8dc43872898801f27d1945e099aac3bdc255c005` |
| `specgraph/audit.py` | `db851be880315b76648bcaa93efa8e3e1ac1bf58` |
| `specgraph/cli.py` | `e79b35a492c93c3bbce358e3ab84e6ebee603339` |
| `specgraph/defaults.py` | `290a3cf707c7f03897b0172f0e1c96ba2c39aa76` |
| `specgraph/gitio.py` | `b7b5a100da84d5d82d85c0094336bf27adf196f2` |
| `specgraph/history.py` | `0b7372d9dfb88882741ba1058e26d4dd2d399efb` |
| `specgraph/hooks.py` | `9004d7f4fd69317f41f2c21c3dfe4638da5198a5` |
| `specgraph/merge.py` | `9a105901d9f39a2e573a89b90ec11243afaf4429` |
| `specgraph/model.py` | `1ba7b04b00c28d8e807cc34b009c5fd634eef9a0` |
| `specgraph/ops.py` | `32501cdd3d34d6ca4b40c23b57592f082cf1ef5e` |
| `specgraph/query.py` | `9e6309872dcd4da72a4eeee37d2b718d1f4d33b2` |
| `specgraph/rules.py` | `e2fedf80844b10b5b019c8fe13768b435d550c53` |
| `specgraph/server.py` | `1f22c58051edd8b5074801f1c754caaa43e9badb` |
| `specgraph/stamp.py` | `42c0a2897f9632c245efabe7d0479c5ddd685407` |
| `specgraph/store.py` | `ada2ef076891e86f64455204ac4493e989168b57` |
| `specgraph/validate.py` | `825122614aaf68de56236ddd807bcb2d0e8de443` |
| `specgraph/web/app.js` | `8b614ecc12d07c923f7f6defa7fc826c6d6fa349` |
| `specgraph/web/favicon.svg` | `8b45d7c799fdde7aa783ce28d9f6c37596926cad` |
| `specgraph/web/index.html` | `f65a8e5d77865af4bc8348584910f9dc5d124f5e` |
| `specgraph/web/style.css` | `6148e5f997010c9db90fb2088da9d69bc88bf027` |
| `tests/conftest.py` | `1555d157ab8f95c6db45a844b8ebc2f2fc7b80d7` |
| `tests/test_changes.py` | `801590ce958f3d6afab909ad97dc764f0430f4db` |
| `tests/test_core.py` | `d68a7d9675557753b0c7b4eca29b42bc0ad94d59` |
| `tests/test_example.py` | `c8634f58c44151ad09d8dbac5dbeb93253641816` |
| `tests/test_integrity.py` | `34cbffa602b74d6641b29f345ca4eaf746decb7b` |
| `tests/test_ui.py` | `190ef13c5cc64ba1c1617a033a0fe1a97fdb50a7` |
