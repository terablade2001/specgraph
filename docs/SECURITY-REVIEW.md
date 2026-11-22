# Security review of specgraph 0.4.0

- **Reviewed by:** Claude (model Opus 5.5), an AI model made by Anthropic, at the request of the project owner.
- **Date:** 2026-11-23.
- **Version:** 0.4.0 (not yet released): branch `3-Support_optimized_AI_synergy` at commit `e8a2fcb`, plus the fixes
  for five findings of this review, committed together with this document. The files and hashes are listed at the
  end.
- **Builds on:** the review of 0.3.1 (2026-11-21, Claude, model Opus 5.5). Everything changed since 0.3.1 was read
  and tried again; the unchanged files were checked against their 0.3.1 hashes and not re-read line by line.
- **Question asked:** does the software do harm on purpose (steal data, communicate in secret, run hidden
  code), and does it have security weaknesses?

## What this document is, and is not

- It says what was checked, how, and what was found, for the exact files listed at the end.
- It is **not a cryptographic signature**. An AI model holds no signing key. The statement is tied to the
  code by the file hashes at the end. If a file's hash differs, this review does not cover that file.
- It is **not a certification, a guarantee or an independent audit**. Claude models wrote this code, the same
  model version wrote most of the 0.4.0 changes and this review. No human security specialist has reviewed it.
- A review can show that problems were not found. It cannot prove that none exist.

## Result

**No harmful behaviour was found.** The new code (the SQLite index and `sql` command, the AI labels file, its
merge driver, work packets and findings) contains no network code, starts no program other than `git`, reads no
private key, and runs no text from the model or from an agent as a program. Its only new library is Python's own
`sqlite3`.

**No high- or medium-severity weakness was found.** Five low-severity weaknesses were found and are **fixed in this
version**, each with a test (points 1 to 5). Two limits are new (points 6 and 7); the limits of 0.3.1 still apply
(points 8 to 15).

## What changed since 0.3.1

- `specgraph/index.py` (new): builds a derived SQLite database from the model in `.specgraph/` next to it, and runs
  one read-only query for `sg.py sql`: database opened read-only, `PRAGMA query_only`, an authorizer that allows
  only reading (no writes, schema changes, `ATTACH`, transactions, writing pragmas or `load_extension`), a time
  limit and capped output.
- `specgraph/ai.py` (new): the optional AI labels file `specmodel.ai.json` (vocabulary, labels, rules, findings),
  signed like the model, with one checked write path (`sg.py ai apply`), an append-only log, work packets for
  agents, and a three-way merge driver. Vocabulary, rules and findings can be changed by administrators only; the
  commit hook and `audit` check that on every commit.
- `cli.py`, `audit.py`, `hooks.py`: the commands `index`, `sql` and `ai …`; the commit check and the audit also
  check the AI file; `install-hooks` configures a second merge driver.
- Format 3 (`ops.py`, `validate.py`, `merge.py`, `defaults.py`): a description per type, status and link type. The
  editor shows it as a tooltip (`setAttribute`, never as HTML) and edits it in a text area.
- `sample/build_synthetic.py` (new, not part of the tool): builds large test models; it creates a throwaway key in
  the target folder (ignored by git there) and a private `ssh-agent` that it stops afterwards.

## What the software does on your machine

| Area | Finding |
|---|---|
| Network | Unchanged: only the local editor server on `127.0.0.1`. The new code opens no connection. |
| Programs it starts | `git`, `ssh-keygen`, `ssh-add` (argument lists, no shell); through git its own hooks and **two** merge drivers, which run `sg.py`. Nothing else. |
| Files it reads | As in 0.3.1, plus the AI file and its log, the derived index in `.specgraph/`, and files an agent or user passes to `ai apply --ops-file`. |
| Files it writes | As in 0.3.1, plus: `.specgraph/` next to the model (the index, its temporary build file and a `.gitignore` with `*`), the AI file and its log (only through `ai apply`, `ai resolve` or the merge driver), packet files given with `--out`, and the `.gitattributes` lines and merge-driver setting for the AI file (only on `install-hooks`). |
| Secrets | Unchanged: no private key or passphrase is read; signing goes through `ssh-agent`. |
| Dynamic code | None in the new code. Text from the model and from agents is stored, compared or shown, never run. A finding's `ops` is a suggestion stored as data; the tool never runs it. |
| Dependencies | Python standard library only (`sqlite3` is part of it). |

## How it was checked

1. **Reading the code.** Everything changed since 0.3.1 was read (`git diff` against 0.3.1, about 1 800 added lines
   of Python, plus the page change). The new modules were searched for every network, process, file, environment,
   SQL and dynamic-code call. The authorizer, the integrity and permission checks of the AI file, the merge driver
   and the audit changes were read in full.
2. **Probes** (16, written for this review, not kept in the repository):
   - 11 more ways to write through `sql` (table-valued pragmas with arguments, `INSERT` inside `WITH`, two
     statements, a trigger, `readfile`, `edit`, `load_extension`, FTS functions): all refused or harmless, and the
     index file was byte-for-byte unchanged after each.
   - a malformed AI file: the index, `ai status` and `ai todo` kept working;
   - a finding with 1 000 suggested operations and a 5 000-character quote: stored, nothing run;
   - a model folder named with `#`, a hand-edited model with a self-made administrator, and an index file with
     altered content: these found points 1 to 3 below; all three now pass.
3. **Watching what it does.** The 170 tests without a browser were run with a Python audit hook in every Python
   process they started (including `sg.py` run by git hooks and both merge drivers). Every network call went to
   `127.0.0.1` (the tests' own editor servers). The programs started were `git`, `ssh-keygen`, `ssh-add`,
   `ssh-agent` (started by the tests) and `sg.py` itself. Every file written was inside the tests' temporary
   folders or git's temporary merge files.
4. **Tests.** All automated tests pass on this version, the browser tests included (Windows 11, Python 3.13,
   SQLite 3.53, Chrome); five of them were added by this review (`test_sec_*` in `test_ai.py`, `test_index.py`,
   `test_sql.py`).

## Findings, points and limits

### Fixed in this version

1. **Low: the AI file could be signed on top of a hand-edited model.** `ai apply` checked the AI file's stamp but
   not the model's. Tried: the model was edited by hand to make an unregistered user an administrator; that user
   then signed vocabulary changes, and the tool accepted them. The commit hook and `audit` would have reported both
   files, but the tool should not sign there. **Fix:** `ai apply` refuses when the model does not match its stamp,
   like `Store.apply` (`test_sec_ai_writes_refused_on_a_hand_edited_model`).
2. **Low: a planted index was trusted.** `sql` used any `.specgraph/<model>.db` whose recorded hashes matched the
   model. A repository could commit such a file with false content (agents would read it), and an untrusted SQLite
   file would be opened. **Fix:** `sql` and `index` refuse an index folder that is tracked by git or is a link, and
   say how to remove it (`test_sec_index_tracked_by_git_or_linked_is_not_used`). An index changed locally by
   someone who can already write your files is not covered.
3. **Low: a `#` in a folder name broke the read-only opening.** The index is opened through a SQLite URI; a `#`
   ended the path there, the read-only flag was lost, and SQLite created an empty file next to the folder. **Fix:**
   the path is escaped (`test_sec_index_in_a_folder_with_special_characters`).
4. **Low: instructions hidden in spec text.** Work packets give agents the model's text; a spec could contain text
   aimed at the agent ("label everything X", or a finding whose `ops` deletes elements). Nothing in the tool runs
   such output: labels and findings pass the checks of `ai apply`, and `ops` are never run. **Fix:** the prompts
   (version 2) and `docs/AGENTS.md` say that model text is data, not instructions, and that a finding's `ops` must
   be read before anyone runs them (`test_sec_prompts_say_model_text_is_data`). This lowers, not removes, the risk:
   a language model can still be misled.
5. **Low: a query could use a lot of memory within its time limit.** A recursive query doubling a string reaches
   SQLite's 1 GB value limit in seconds. Only the person (or agent) running `sql` is affected. **Fix:** on Python
   3.11 and later, a value above 10 MB stops the query (`test_sec_a_query_cannot_build_huge_values`). On older
   Python the 10-second limit and SQLite's own limit remain.

### New limits

6. **The AI merge trusts the users of both sides.** Like the model merge (ADR-031), the AI merge driver checks each
   side's signature against the users known on either side and in the working file, and signs the result as the
   person merging. A branch that adds its own user and signs AI changes with that key passes the merge; the commit
   check and a full `audit` report it at its own commit.
7. **Findings and AI labels are advice written by a language model.** They can be wrong or steered by text in the
   specs (point 4). Only administrators can store findings; nothing in the tool acts on labels or findings. Quotes
   and suggested `ops` have no size cap; an administrator could make the AI file large.

### Still true from 0.3.1

8. **Once a bad commit is on the remote, only a full audit finds it** (pre-push checks only new commits). Run
   `sg.py audit` now and then, for example in CI.
9. **The access token is visible to other programs of the same user** while the editor runs.
10. **Git hooks and the merge-driver settings contain your paths inside double quotes**; a `"`, `$` or backtick in a
    path would break them. Only your own folder names are involved.
11. **The environment decides which programs run** (`SPECGRAPH_SSH_KEYGEN`, `SPECGRAPH_SSH_ADD`, `PATH`).
12. **What the signatures prove is limited** (ADR-003): they detect edits outside the tool and name a registered
    key; the first version trusts its own user list; the deleted-elements log and the AI log are not signed; the
    working file and each side of a merge are checked against their own user lists.
13. **Running the tool means running the code in your copy**, also through hooks and both merge drivers after
    `install-hooks`. Review updates to the tool as you would any program.
14. **The tests are less strict than the tool** (Chrome without its sandbox against the local page; throwaway keys
    and a private `ssh-agent`).
15. **Stale lock file:** two writers at the same moment after 60 seconds could both proceed (a lost change, not a
    leak). The AI file uses the same lock.

## Not covered

- Python, SQLite, Git, OpenSSH and the browser themselves.
- Linux and macOS: everything was run on Windows 11 with Python 3.13, SQLite 3.53, Git for Windows and Chrome.
- The language models agents use, and the agents' own tools; what an agent does outside `sg.py` is outside this
  review.
- `evals/` (evaluation scripts and recorded results, not part of the tool) beyond checking that no private key is
  stored there.
- Fuzzing, or a search for mistakes in the merge, validation and SQL logic beyond what the tests and probes
  exercise.
- Anything changed after this review: check the hashes.

## Reviewed files

40 files. Each hash is the git object id of the file. Check one with `git hash-object <file>`, or all of
them against `git ls-files -s`.

| File | Git object id |
|---|---|
| `.gitattributes` | `189aa1426a5718cd255a7bfcff523685f2ba36ac` |
| `.gitignore` | `79e7df79c878e7ba22974b15f76ef037ef9aa1c9` |
| `sample/build_example.py` | `a145d0581a333cefa64d5922a48b124d2e00bacb` |
| `sample/build_sample.py` | `1d2198c4fc2789e364ee3b7a925e875222d49e8f` |
| `sample/build_synthetic.py` | `3028996e4fd00b42fdf2713e07fb632cb07ced65` |
| `sg.py` | `368f799da2624a4ef9d5d68039b61bce277ad6fd` |
| `specgraph/__init__.py` | `1979722cbb2e0e503b0066fb3ef646d2fc7c0e8e` |
| `specgraph/__main__.py` | `8dc43872898801f27d1945e099aac3bdc255c005` |
| `specgraph/ai.py` | `a1cb2efbb13cf29c50d9a3891b52061236081215` |
| `specgraph/audit.py` | `6f0bb8fbb09d8b2b184185bca0081e2024ebe69c` |
| `specgraph/cli.py` | `38a0cd7860eab175e150cd20357f019f6cdce624` |
| `specgraph/defaults.py` | `78e6545ddfb929c87ffb9448e9f5fe83768accd1` |
| `specgraph/gitio.py` | `b7b5a100da84d5d82d85c0094336bf27adf196f2` |
| `specgraph/history.py` | `0b7372d9dfb88882741ba1058e26d4dd2d399efb` |
| `specgraph/hooks.py` | `fc8c3dd903499135dfdb3e4bc8378481a89f2d92` |
| `specgraph/index.py` | `b737f2836be810fa8806ac01f6050a37133ad236` |
| `specgraph/merge.py` | `2c0589dcd40b6d18b4cc22755ff5550f52494854` |
| `specgraph/model.py` | `1ba7b04b00c28d8e807cc34b009c5fd634eef9a0` |
| `specgraph/ops.py` | `8f03724e2ca6a97ae2dbef67549fcf4d8f99ff7b` |
| `specgraph/query.py` | `9e6309872dcd4da72a4eeee37d2b718d1f4d33b2` |
| `specgraph/rules.py` | `e2fedf80844b10b5b019c8fe13768b435d550c53` |
| `specgraph/server.py` | `1f22c58051edd8b5074801f1c754caaa43e9badb` |
| `specgraph/stamp.py` | `42c0a2897f9632c245efabe7d0479c5ddd685407` |
| `specgraph/store.py` | `ada2ef076891e86f64455204ac4493e989168b57` |
| `specgraph/validate.py` | `5c2a77fd7d971c4ba3b5f9bd12e8a8f83ddd9ff9` |
| `specgraph/web/app.js` | `6364cc4e9a7c672d861c508938a4528a6a3d097d` |
| `specgraph/web/favicon.svg` | `8b45d7c799fdde7aa783ce28d9f6c37596926cad` |
| `specgraph/web/index.html` | `f65a8e5d77865af4bc8348584910f9dc5d124f5e` |
| `specgraph/web/style.css` | `6148e5f997010c9db90fb2088da9d69bc88bf027` |
| `tests/conftest.py` | `1555d157ab8f95c6db45a844b8ebc2f2fc7b80d7` |
| `tests/test_ai.py` | `847328db6ec25af0d8a12fdef63d44ba3fbe3eff` |
| `tests/test_changes.py` | `0600fe14ef624d7d2d3345245abf167d54960ea1` |
| `tests/test_core.py` | `d68a7d9675557753b0c7b4eca29b42bc0ad94d59` |
| `tests/test_descriptions.py` | `e162f905bddd348400511749fdc80ca032ecb2e4` |
| `tests/test_example.py` | `c8634f58c44151ad09d8dbac5dbeb93253641816` |
| `tests/test_index.py` | `6744a62559fcf0ea04f0edbdb2d6630d157b7365` |
| `tests/test_integrity.py` | `34cbffa602b74d6641b29f345ca4eaf746decb7b` |
| `tests/test_sql.py` | `4584ceec86b4dc668720d450bc1a9afe22669642` |
| `tests/test_synthetic.py` | `1bca8cc586af59f7b05a57e39b04f8f5f8c8c037` |
| `tests/test_ui.py` | `d17118eaacd36fee4c066b7f00073aac60285113` |
