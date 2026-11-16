# Requirement → test

`core` = tests/test_core.py, `integ` = tests/test_integrity.py, `changes` = tests/test_changes.py,
`example` = tests/test_example.py, `ui` = tests/test_ui.py (browser). What each requirement says: `docs/REQUIREMENTS.md`.

| Requirement | Covered by |
|---|---|
| STO-01, STO-02 | core `test_sto01_02_*` |
| STO-03 | core `test_sto03_*` |
| STO-04 | integ `test_sto04_hst01_*` |
| STO-05 | core `test_sto05_*` (any branch, old `settings.branch` ignored, no finding in the commit check) |
| STO-06 | integ `test_sto06_parallel_*`, `test_sto06_same_field_*`, `test_merge3_*`, `test_merge_without_driver_*` |
| STO-07 | core `test_sto07_*`; integ server test (stale base → 409) |
| STO-08 | integ `test_int03_sto08_*`; docs/FORMAT.md |
| ELM-01, ELM-02, ELM-04 | core `test_elm01_02_04_*` |
| ELM-03 | core `test_elm03_*`; integ `test_sto06_parallel_*` |
| ELM-05 | core `test_elm05_dgm03_*`; ui |
| ELM-06 | core `test_elm06_*`, `test_cli_delete_requires_confirmation`; ui (dialog shows usage) |
| FLD-01, FLD-02 | core `test_fld01_02_*`; ui (tree) |
| FLD-03 | changes `test_fld03_*` (3 tests: order per folder and kind, locks, merge); ui `test_tree_order_*` (drag before/after, into another folder, top-level folders) |
| DGM-01, DGM-03 | core `test_elm05_dgm03_*` |
| DGM-02 | ui (place, move, link by dragging). Resize is implemented but has no automated test |
| DGM-04 | core `test_dgm04_*`; ui (override + bend by double-click) |
| DGM-05, DGM-06 | ui (stereotype marker, status pill, link stroke/dash asserted) |
| DGM-07 | ui (links appear from the model) |
| DGM-08 | ui (SVG and PNG download) |
| LNK-01..03 | core `test_lnk01_02_03_*` |
| TRC-01..03 | core `test_trc01_02_03_*`; ui |
| TRC-04 | core `test_trc04_matrix`, impact in `test_trc01_*`; ui |
| TRC-05 | core `test_trc05_*` |
| CFG-01, CFG-02, CFG-05 | core `test_cfg01_*`; ui (new link type in the dialog) |
| CFG-03 | core `test_cfg03_*`; ui. Status transitions (MAY) not built |
| CFG-04 | core `test_cfg04_*` |
| CFG-06 | core `test_cfg06_*` |
| CFG-07 | core `test_cfg07_*` |
| CFG-08 | core `test_cfg08_*` |
| SRC-01, SRC-02, SRC-05 | core `test_src01_02_05_*`; ui |
| SRC-03, SRC-04 | ui |
| INT-01 | integ `test_int01_*` |
| INT-02 | integ `test_int02_*` (two tests) |
| INT-03 | integ `test_int03_sto08_*` |
| INT-04 | core `test_int04_*` |
| INT-05 | docs/ADRS.md ADR-003 (a document, not testable) |
| USR-01, USR-02 | integ `test_usr01_*` |
| LCK-01, LCK-02 | integ `test_lck01_02_*`, `test_lck07_*` (anyone unlocks, confirmation in CLI and server); ui (bob refused). The unlock dialog in the editor has no automated test |
| LCK-03 | integ `test_lck03_04_*` (data); ui (badge on diagram, tree, properties) |
| LCK-04 | integ `test_lck03_04_*` (owner may link, others refused) |
| LCK-05 | integ `test_lck05_*`, `test_chk03_*` |
| LCK-06 | integ `test_sto06_same_field_*` (two people lock the same folder); ADR-005 |
| CHK-01, CHK-02 | integ `test_chk01_02_*` |
| CHK-03 | integ `test_chk03_*` |
| HST-01 | integ `test_sto04_hst01_*` |
| USE-01 | ui |
| USE-02 | integ `test_use02_*` |
| USE-05 | integ `test_use05_*` (no key in ssh-agent, no editor) |
| USE-06 | integ `test_use06_*` (two keys loaded: prove, apply and serve refuse) |
| USE-07 | ui `test_tree_order_*` (context menu). Shift+click on the arrow and the two entries of the tree background menu have no automated test |
| USE-08 | ui `test_tree_order_*` (three lines dragged, size kept after a reload, double-click resets) |
| USE-03, USE-04, DOC-01..04 | documents; not testable |
| DOC-05 | ui `test_sample_model_is_valid`; example `test_doc05_*` (2 tests: the README example builds and is valid, the stored `specmodel.example.json` matches the builder) |
| ADR-016 author and date on every element | changes `test_adr016_*` (5 tests: set on change, untouched otherwise, validation, version-1 upgrade, merge) |
| ADR-017 undo, N steps | changes `test_adr017_*` (3 tests), server part in `test_adr019_*`. Button and Ctrl+Z checked by hand in a browser, no automated ui test |
| ADR-018 deleted elements log | changes `test_adr018_*` (3 tests) |
| ADR-019 confirmation before delete | changes `test_adr019_*` (server); core `test_cli_delete_requires_confirmation`. Pop-ups for folder, configuration entry and user, and the copy-id button, have no automated test |
| Tool version | changes `test_tool_has_a_version` |

Honest notes: the tests were written alongside the code rather than strictly before it. Signing
tests need the real `ssh-keygen` and `ssh-agent`; they start a private agent and skip without them.
The Windows agent service (named pipe) is not exercised by the tests.
