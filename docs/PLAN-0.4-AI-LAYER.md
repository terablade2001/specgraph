# Plan 0.4.x — a read layer for AI agents

Working plan for branch `3-Support_optimized_AI_synergy`. It replaces the owner's draft
(`SPECGRAPH_AI_LAYER_PLAN.md`, written without the code at hand). The current code is the truth: names
here are the names in the code. Each phase ends with tests, docs and the owner's review before the next.

Owner decisions so far (2026-11-22):

- 0.4.x carries both layers: 0.4.0 = the read index (Layer 1), 0.4.1+ = AI labels (Layer 2).
- The read index needs an ADR and a change to "Not in scope" in `CLAUDE.md`, approved before code.
- Baseline = this branch as it is (no digest script).
- `description` is always present on stereotypes, statuses and link types; empty when not given.
- ADRs go in `docs/ADRS.md`. The untracked root `specmodel.json` is a test model and is never committed.

---

## 1. Phase 0 report — what the code really is

### 1.1 Model (`docs/FORMAT.md`, `specgraph/model.py`)

| Draft said | Code has |
|---|---|
| element `type`, `title`, `body` | `stereotype`, `topic`, `notes` (+ `label`, `status`, `folder`, `fields`, `modified {at, by}`, `order?`) |
| link `from_id`, `to_id`, `note` | `source`, `target`, `label` (+ `type`) |
| `updated_by`, `updated_at` | `modified.by`, `modified.at` |
| per-element `content_hash` | none. One hash for the whole file: `stamp.contentHash` = sha256 of canonical JSON without the stamp |
| "maintainer" role | `users.<name>.role` = `admin` or `user` |
| model config somewhere | `config.{stereotypes, statuses, linkTypes, coverageRules}` inside `specmodel.json` (confirmed) |
| link type with from/to type | `sources`, `targets`: lists of stereotype keys or `null` = any; plus `traceable` (missing = true) |
| `description` on config | only `coverageRules` have one (max 500 chars). Stereotypes, statuses, link types do not |
| custom fields | `elements.<id>.fields` = `{key: value}`, defined per stereotype in `config.stereotypes.<K>.fields.<key> = {label, type, options?}` |
| — | `folders` (tree, `lock {owner, reason, at}` inherited by sub-folders) and `diagrams` (`nodes`: which elements, layout only) |

- Validation (`validate.check_config_value`) checks known keys and **ignores unknown ones**, so an
  added key passes old validation, but a `formatVersion` bump makes 0.3.x refuse the file
  (`READABLE_VERSIONS = (1, 2)`), as intended for a format change.
- Format upgrade has one place: `ops.upgrade(m, by, at)`, called by `apply_ops` and by the merge.
- Configuration is changed with `config.put` / `config.delete`. **Any registered user** may change
  configuration; only `users` is admin-only (`rules.check_change`).

### 1.2 Write path, signing, hooks, merge

- One write path: `Store.apply` → `ops.apply_ops` (pure) → `rules.check_change` → `stamp.make_stamp`
  → atomic `model.save`, under a `FileLock`. Deleted elements go to `specmodel.deleted.jsonl` (append only).
- `stamp.make_stamp(doc, user, key, op, prev)` and `stamp.check_integrity(doc, users)` work on any dict
  that holds a `stamp` and are checked against `users` of the model: reusable for a second file.
- `hooks.install`: pre-commit = `check --staged`, pre-push = `audit --push`, merge driver
  `merge=specgraph` for the model, `merge=union` for the deleted log, lines appended to `.gitattributes`.
  `.gitignore` has `.venv/`, `__pycache__/`, `*.pyc`.
- `merge.merge3`: generic three-way merge per key, conflicts recorded in the model. ADR-031 refuses a
  side whose stamp does not match.
- ADR-024: **no branch rule**. Anything "main only" needs an ADR that changes this (see §5.1).

### 1.3 Reading today

- `query.py`: `search` (substring on id prefix, label, topic, notes; filters stereotype/status/folder/unused),
  `usage`, `trace` (traceable link types only, optional depth), `impact`, `matrix`.
  `validate.coverage_violations` computes coverage rules.
- Agents get JSON from `sg.py search/show/trace/impact/matrix/history/validate`, or read the whole file.

### 1.4 Sizes

- `specmodel.example.json`: 26 elements, 26 links, 9 folders, 3 diagrams, 30 KB (~1.1 KB per element).
- At 10K elements the file would be ~11 MB, roughly 3M tokens: reading it whole is impossible, and
  `sg.py search ""` returns every element. No real large model exists, so a synthetic one is needed.
- SQLite here: 3.53 with FTS5 and the trigram tokenizer. Python 3.8 builds can ship SQLite < 3.34
  (no trigram) and a few builds lack FTS5: both must be optional at run time.

### 1.5 Repo rules that shape the plan

Stdlib only; never hand-edit the model; logic in Python, not `app.js`; canonical serialization;
no file per element; deleted log never read to decide anything; new behaviour → `VERSION` raise and
`CHANGELOG.md`; tests named after requirements and listed in `docs/REQUIREMENTS-COVERAGE.md`;
high/medium-stakes design → ADR approved by the owner.

---

## 2. Changes to the draft

1. **Names** follow the code (§1.1). The draft's `meta_*` tables become `config_*` tables.
2. **Lazy rebuild, no rebuild after `apply`.** `sg.py sql` checks whether the index matches the model
   and rebuilds when not. The editor server never builds it. `sg.py index` forces a build.
3. **Freshness key** = sha256 of the model file's bytes + of the AI file (Layer 2) + index schema
   version + tool version. Not the commit (the model is usually changed but not committed yet), and
   not `stamp.contentHash` (a hand-edited file keeps an old one).
4. **Location**: `<model folder>/.specgraph/<model file name>.db`. The tool writes
   `.specgraph/.gitignore` containing `*`, so nothing has to be added to the repo's `.gitignore`, and it
   works for `--file` models outside a repo. One per worktree by construction.
5. **Build into a temporary file and swap it in** (`os.replace`), instead of WAL refresh in place.
   Readers are short-lived CLI processes. On Windows a swap fails while another process has the file
   open: retry briefly, else keep the old file and query a private fresh copy. Tested on Windows.
6. **Deleted elements are not indexed** (the deleted log is never read to decide anything).
7. **Coverage is computed by the existing Python** (`validate.coverage_violations`) into a table, not
   re-implemented in SQL. Same for effective locks (`rules.effective_locks`) and folder paths.
8. **Existing commands stay** (`search`, `show`, `trace`, `impact`, `matrix`). No new query commands.
9. **`sg.py sql --schema`** prints tables, columns and their meaning from the database itself, so the
   agent guide cannot drift from the schema and stays short.
10. **No glossary feature** (owner, Q2). specgraph ships no glossary type and names none. A project
    that wants one creates its own stereotype and says in its `description` what it is ("Glossary: one
    element per domain term; field *synonyms* …"). Projects can also put synonyms straight into the
    descriptions of their types. The agent guide stays general: read the `config_*` tables and their
    descriptions first, and use any glossary the project describes to widen searches.
11. **LLM calls are made by the agent, never by specgraph.** The tool hands the agent a work packet and
    accepts the result through a checked write command (§5.2). Core stays stdlib only and provider-free.
12. **"Main only" is replaced by "admin only"** (ADR-024 has no branch rule), and the AI file is
    **signed like the model** so the hooks and the audit can enforce it (§5.1, question Q3/Q4).

---

## 3. Phases

Versions: 0.4.0 after Phase 6, 0.4.1 after Phase 9, 0.4.2 after Phase 11, 0.4.3 after Phase 12 (adjust as we go).

### Phase 1 — Evaluation baseline (no tool code)

- `sample/build_synthetic.py <dir> --elements N --seed S`: builds a model through `Store.apply` in
  batches, deterministic for a seed. Topics and notes from templates with **planted synonyms**
  ("login" / "sign in" / "authentication" / "credentials") and planted structure (chains
  B-REQ → U-REQ → FEAT → REQ → TEST, ADRs implementing REQs, approved REQs without tests, orphans,
  a locked folder, diagrams), so expected answers are known by construction. Sizes: 1K and 10K.
  Check build time; `coverage_violations` is O(rules × elements × links) and may need a cheaper loop
  (a fix there would help `validate` too).
- `evals/questions.md`: 15–20 questions, each with a type (exact trace, coverage, impact, concept
  search, field filter, lock, diagram membership) and expected element ids per model.
  Examples: "What is affected if ADR-x changes?", "Which approved REQs have no test?",
  "Everything about authentication", "Which elements in the locked folder link outside it?".
- `evals/score.py` (stdlib): compares an answer file of ids with the expected ids → precision, recall.
- Protocol `evals/README.md`: a Claude Code **Sonnet** subagent (owner, Q8) gets the question, the repo docs and
  only the tools of the variant under test; we record its answer, tool output size and token usage.
- Baseline run on the current tool (read the file, `search`, `show`, `trace`, …) on example, 1K, 10K.
- **Accept:** baseline table of accuracy and tokens per question type and model size.
- **Done 2026-11-22:** `evals/results/BASELINE.md` (mean F1 1.00 / 0.96 / 0.85 for 26 / 1K / 10K elements).

### Phase 2 — ADRs and requirements (docs only)

- ADR-032 "A derived SQLite index for agents" (stakes: high): derived, disposable, never committed,
  never a source of truth, lazy rebuild, read-only queries; changes "Not in scope: index generation"
  in `CLAUDE.md` and ADR-014/015.
- ADR-033 "Descriptions on configuration entries; format 3" (stakes: high, format change).
- New requirements in `docs/REQUIREMENTS.md` (group `AGT-…`) for index, `sql`, descriptions.
- **Accept:** owner approves the ADRs.
- **Done 2026-11-22:** ADR-032 and ADR-033 approved; output caps configurable (`--limit`/`--width`,
  `SPECGRAPH_SQL_LIMIT`/`SPECGRAPH_SQL_WIDTH`, defaults 50/200, 0 = no cap). `CLAUDE.md` scope updated.

### Phase 3 — Descriptions, format 3

- `FORMAT_VERSION = 3`, `READABLE_VERSIONS = (1, 2, 3)`. `ops.upgrade` adds `description: ""` to every
  stereotype, status and link type that lacks one (coverage rules already have it); the merge's
  upgrade call is generalised for any older side.
- `defaults.py`: a short generic `description` on every default stereotype, status and link type
  (owner, Q1). No new default stereotype (owner, Q2).
- `validate.check_config_value`: `description` is text, max 2000 characters, required in format 3.
- `config.put` sets `description: ""` on new entries.
- Editor: one "Description" text area in the configuration dialog for these three kinds
  (`web/app.js` field lists at ~1227), shown as the tooltip of the type in the explorer.
- `sample/build_example.py`: give the example's types descriptions; regenerate
  `specmodel.example.json` and check the README images still hold.
- Tests: v2 file loads, first change writes v3 with empty descriptions; merge of a v2 and a v3 side;
  0.3-style config without description validates after upgrade; editor round trip (ui).
- **Accept:** old models load and upgrade on first change; all tests pass.
- **Done 2026-11-22:** format 3, upgrade in `ops.upgrade`/`add_descriptions`, merge normalises the three sides,
  default descriptions, editor field and tooltips, example rebuilt, `VERSION` 0.4.0; 89 tests pass (incl. browser).

### Phase 4 — The index (`sg.py index`)

New module `specgraph/index.py` (only `sqlite3`, `hashlib`, `json`). One transaction, then swap.

| Table | Columns |
|---|---|
| `meta` | `key`, `value`: schema version, tool version, model sha256, format version, built at, integrity problems, fts mode (`fts5`, `fts5+trigram`, `none`) |
| `elements` | `id`, `label`, `stereotype`, `status`, `topic`, `folder`, `folder_path`, `modified_at`, `modified_by`, `notes_chars` — summary only |
| `element_notes` | `id`, `notes` |
| `element_fields` | `element`, `key`, `value` (text), `type` |
| `links` | `id`, `type`, `source`, `target`, `label` |
| `folders` | `id`, `name`, `parent`, `path`, `lock_owner`, `lock_reason`, `lock_at`, `locked_by` (effective owner incl. ancestors) |
| `diagrams`, `diagram_elements` | `id`, `name`, `folder`, `folder_path`; `diagram`, `element` |
| `users` | `name`, `role` |
| `config_stereotypes` | `key`, `label`, `description`, `label_prefix`, `retired` |
| `config_statuses` | `key`, `label`, `description`, `order`, `retired` |
| `config_link_types` | `key`, `label`, `description`, `traceable`, `retired` |
| `config_link_type_ends` | `link_type`, `end` (`source`/`target`), `stereotype` (no row = any) |
| `config_fields` | `stereotype`, `key`, `label`, `type`, `options` |
| `config_coverage_rules` | `key`, `description`, `stereotype`, `statuses`, `link_type`, `direction`, `other` |
| `coverage_violations` | `rule`, `element`, `message` (from `validate.coverage_violations`) |
| `columns_doc` | `table`, `column`, `meaning` (feeds `sql --schema`) |
| view `v_links` | link + source/target label, stereotype, status, and `traceable` |
| `elements_fts` | FTS5 over label, topic, notes, field values; `porter unicode61 remove_diacritics 2` (diacritics option needs SQLite ≥ 3.27; else plain `unicode61`) |
| `elements_trigram` | FTS5 trigram, only when available |

- Indexes on `links(source)`, `links(target)`, `links(type)`, `elements(stereotype, status)`.
- Integrity: the index is built even when the stamp does not match; `meta.integrity` says so and
  `sql` prints a warning line (reading is allowed today too).
- Tests: deterministic content for the same model; rebuild when the file changes; no rebuild when not;
  FTS absent → build still works; 10K synthetic build time (target ≈ 1 s, measured and reported).
- **Accept:** owner reviews schema and timings.
- **Done 2026-11-22:** `specgraph/index.py`, `sg.py index`, 14 tests (`tests/test_index.py`). Additions to the
  table above: `folders.locked_from` (folder carrying the lock in force), `config_stereotypes.statuses` (JSON list,
  NULL = all), an index on `element_fields(key, value)`. `element_fields.value` keeps the type (numbers stay
  numbers, booleans 1/0) so `value > 3` works. `ensure()` (used by `sql`) rebuilds only when stale; when the swap
  cannot happen in 2 s (Windows, a reader holds the old file) the caller gets a private fresh copy, removed after
  use. `validate.coverage_violations` now indexes links once (same output, checked on s1k and s10k).
  Timings (Windows, Python 3.13, SQLite 3.53, `fts5+trigram`):

  | Model | Build | Fresh check (no rebuild) | Index size |
  |---|---|---|---|
  | s1k (1 034 elements) | 0.07 s | — | — |
  | s10k (9 966 elements, 13 325 links) | 0.44 s (2.2 s before the coverage fix) | 0.006 s | 20 MB |

### Phase 5 — `sg.py sql`

- `sg.py sql "<query>" [--limit N] [--width N] [--json]`, `sg.py sql --schema`.
- Rebuilds the index first when stale (§2.2).
- Read only, three layers: URI `mode=ro`; `PRAGMA query_only=1`; an authorizer that allows only
  reading (`SELECT`, `READ`, functions, recursive CTEs) and refuses `ATTACH`, `PRAGMA` writes, DDL/DML;
  extension loading stays off. A progress handler stops a query after a time limit (default 10 s).
- Output: compact text table (default) or JSON; rows capped (default 50) and long cells cut (default 200
  characters), both configurable (`--limit`, `--width`, `SPECGRAPH_SQL_LIMIT`, `SPECGRAPH_SQL_WIDTH`, 0 = no cap) with `…`; footer `… N more rows — refine or use LIMIT/OFFSET` (counting stops at a
  ceiling, then "more than N").
- Exit codes like the rest: 2 = refused (write attempt, syntax error, timeout).
- Tests: every kind of write refused; ATTACH refused; caps and truncation; JSON shape; timeout.
- **Accept:** write attempts fail; caps hold; tests pass.
- **Done 2026-11-22:** `cmd_sql` in `cli.py`, `index.query`/`index.schema`, 37 tests (`tests/test_sql.py`). The
  authorizer allows SELECT, READ, functions (not `load_extension`), recursive CTEs and a fixed list of
  pragmas that never write (`table_info` … and `data_version`, which FTS5 uses); everything else is denied. Text
  output: `a | b` rows, `NULL`, line breaks as `\n`, footer `(N rows)` or `(50 of 60 rows shown; …)`, a second
  line when cells were cut. Counting ceiling 10 000 left-out rows. On s10k: elements without links 0.65 s
  including the rebuild, links into locked folders 0.28 s; `sql --schema` is about 6 KB.

### Phase 6 — Agent guide and measurement → release 0.4.0

- `docs/AGENTS.md`: a short "Reading a large model" section: start with `sql --schema` and the
  `config_*` tables; `COUNT(*)` before fetching; summaries first, `element_notes` for chosen ids;
  always `LIMIT`; recursive CTE traces with a depth limit (default 3) over traceable link types;
  expand searches with synonyms (`MATCH 'login OR "sign in" OR authenticat*'`) and then follow links;
  3–5 example queries (trace, impact, coverage, concept search, lock check).
- `docs/FORMAT.md`: index location and that it is derived; `README.md`, `CLAUDE.md`, `CHANGELOG.md`.
- Run the evals with the new path; compare with the baseline.
- Add a view or command only for a query the agents repeatedly got wrong or rewrote.
- **Decision gate** for Layer 2: residual concept-search misses large enough to justify labels.
- Raise `VERSION` to 0.4.0.
- **Gate decision (owner, 2026-11-22): go on to Layer 2 (labels).**
- **Done 2026-11-22:** guide in `docs/AGENTS.md` (examples checked on s1k and the
  example; they avoid the subjects of the eval questions), `docs/FORMAT.md` section on the index, evals rerun on
  the same models and questions (`evals/results/INDEX.md`). Mean F1 baseline → index: example 1.00 → 1.00,
  s1k 0.96 → 0.91 (0.96 → 0.97 without Q11), s10k 0.85 → 0.95 (0.90 → 0.99 without Q11); mean tokens down
  ~5–10K per question, largest 1K run 144K → 86K. No query was repeatedly got wrong: no new view or command.
  Residual concept misses: 11 planted elements over 6 concept questions, of which 3 are genuine meaning misses;
  Q11 (near-duplicates) is spoiled by the generator's " (2)" topics. `VERSION` was already 0.4.0 (Phase 3).

> **Layer 2 after the gate** (owner, 2026-11-22): go on to labels. Q3–Q7 and the new Q9–Q11 are answered (§5);
> the design is ADR-034 (the AI file, write path, packets, index) and ADR-035 (merging), **approved by the owner
> 2026-11-22**, with requirements AIL-01..08. Phases 8–12 below are kept short on purpose: the ADRs hold the detail.

### Phase 6b — Fair evaluation for labels (no tool code)

Labels can only show value on questions the index cannot answer. Before Phase 7:

- `sample/build_synthetic.py`: no " (2)" suffixes (vary repeated topics instead, so Q11 only has the planted
  pairs); the "fee table" note made clearly about payments or moved out of the concept facts; more planted
  elements whose concept is never named (like "downloads all data held about them"), per concept.
- New seeded builds stored as `evals/results/models/s1k-v2`, `s10k-v2` with their question files; the existing
  models and results stay as they are.
- Re-run the `index` variant on the concept and duplicate questions only (Q05a–c, Q11, and any new ones): the
  numbers labels must beat. Report in `evals/results/INDEX-V2.md`.
- **Accept:** the owner reviews the new baseline.
- **Done 2026-11-22:** generator fixed (tested: unique topics, hidden plants avoid the concept's words, duplicates
  only of plain requirements); models `s1k-v2`, `s10k-v2`; 8 runs (`evals/results/INDEX-V2.md`). Named concept
  elements 69/74 found, **hidden 23/38 (61%), from 0/6 to 6/6 between runs**; near-duplicates 3/3 and 8/10, found by
  comparing topics in SQL. Labels target the hidden-wording recall and its spread; Phase 12 runs each concept
  question at least twice per variant.

### Phase 7 — AI file, write path, index integration

- After the owner approves ADR-034/035: `specgraph/ai.py` (file, hash, staleness, operations, the change check on two
  AI file states), `sg.py ai apply`, `sg.py ai status`, stamp and log (ADR-034 §1–5, §8).
- Index: `ai_vocabulary`, `ai_labels(element, label, stale)`, freshness key with the AI file (ADR-034 §7).
- Tests (AIL-01, -02, -03, -05, -06, -08) first; everything also tested without an AI file.
- **Done 2026-11-22:** `specgraph/ai.py`, `sg.py ai apply|status|ops`, index schema 2 (`ai_vocabulary`, `ai_labels`,
  `meta.ai`, `meta.ai_integrity`), AI file in `check --staged` and `audit`, `.gitattributes` lines; 22 tests
  (`tests/test_ai.py`). Details settled in code: one `vocabVersion` raise per batch; a definition change stales
  unless `keepLabels`; merge/split = retire with `replacedBy`; label entries list their `elements` (so a changed
  element keeps showing its last labels, stale; noted in ADR-034 §2); removing label entries (`ai.gc`) is
  admin-only; rules are checked when labelling and an `always` label is added automatically.

### Phase 8 — Labelling by an agent

- `sg.py ai todo [--limit N]` (default 1000 elements, neighbours 1 hop, at most 10, light: label, type, topic,
  current labels) and `ai todo --vocab` (counts and capped samples for vocabulary work) — ADR-034 §6.
- Versioned prompt text shipped with the tool; `docs/AGENTS.md`: how to run a labelling pass, which model for which
  task: the user's choice; recommended cheaper for routine labelling, stronger for vocabulary and reviews. Assumed
  for the evaluations: Sonnet for labelling, Opus as the stronger model; changed if the cost is too high (owner).
- Cost, measured: first pass on s1k (1–2 agent runs, about 0.1–0.2M tokens). s10k only if s1k shows a gain
  (about 10 runs, 1–1.5M tokens).
- **Done 2026-11-22:** `ai todo` (one element per line; elements named by label with a 12-character hash prefix and
  links as `type>LABEL` / `<type LABEL`, outside neighbours once in `context`, `was` for stale labels, `--limit`,
  `--all`, `--label-new`, `--out`), `ai todo --vocab` (counts, type descriptions, frequent words, round-robin
  samples), prompts shipped in `ai.py` (`PROMPT_VERSION` 1; their examples avoid the eval concepts), `ai apply
  --ops-file`, empty label lists allowed, labelling guide in `docs/AGENTS.md`; 7 tests (AIL-04). Measured on s1k-v2
  (`evals/results/LABELS-S1K.md`): Opus vocabulary 90 concepts, 123K tokens; Sonnet labels in two packets of ~520,
  348K tokens (about 340 per element, above the estimate); all 56 planted concept elements labelled in the right
  branch, hidden ones included, 2 defensible extras. AI file 284 KB.

### Phase 9 — Vocabulary work (`update-ai-labels`) → release 0.4.1

- Operations `ai.vocab.add/update/merge/split/retire` and `ai.rule.set/delete`: **admin only**,
  enforced by `rules`-style checks on the difference of two AI file states (so tool, hook and audit
  share it). Each raises `vocabVersion`.
- Only labels that carry a retired, merged, split or redefined key become stale (`changed > v`); the next `todo`
  asks for them again. A new label stales nothing; `ai todo --label-new` lists elements to reconsider (ADR-034 §3).
- **Accept:** vocabulary within its size target; evals do not get worse.
- **Done 2026-11-22:** the operations, the admin-only check and the limited staleness were built in Phases 7–8; this
  phase exercised them on s1k-v2 (`evals/results/LABELS-S1K.md`): an Opus revision (95K tokens) retired a 6-concept
  branch; exactly the 179 elements carrying it went stale, the other 852 stayed current; Sonnet relabelled them in
  one packet (127K); planted concepts still all found. Vocabulary 84 active (the 100–200 target is for large models;
  the prompt allows fewer). "Evals do not get worse" is measured in Phase 12. No code change was needed.

### Phase 10 — Hooks, merge driver, clean-up

- Pre-commit and audit also check the AI file: stamp matches, signer registered, vocabulary/rules/
  findings changed only by an admin.
- Merge driver `merge=specgraph-ai`: `labels` = union per hash; same hash with different entries →
  keep the one with the higher `vocabVersion`, equal → drop it (stale, relabel later); `vocabulary`/
  `rules`: three-way per key, both sides changed the same key → the side with the higher `vocabVersion`
  wins (question Q3); log = union.
- `sg.py ai gc` (admin): drop label entries whose hash no element has any more.
- **Accept:** multi-branch tests merge with no manual conflict.

### Phase 11 — `specs-vs-ai-labels` → release 0.4.2

- `sg.py ai review [--label K]`: work packet for the agent (label clusters with their elements and
  links); the agent returns findings through `ai apply` (`ai.finding.add {kind, elements, evidence,
  suggestion}`; kinds: missing link, gap by topic, contradiction, duplicate, terminology, misplaced).
- Refused without evidence quoting the elements' own text (checked: the quote must occur in a topic,
  notes or field of a listed element).
- `ai.finding.dismiss`: remembered; a dismissed finding (same kind + same element set) is not
  accepted again. Committing findings/dismissals: admin only.
- Never edits the model; suggestions are text (optionally an `apply` batch for a person to run).

### Phase 12 — Re-measure and decide → release 0.4.3

- Evals with and without labels; results and the decision (labels on by default or not) in an ADR.

---

## 4. Risks

| Risk | Handling |
|---|---|
| File swap on Windows while a reader has the DB open | retry, then private copy; Windows test |
| Building 10K elements through `apply` is slow (validation, coverage loop) | measure in Phase 1; optimise `coverage_violations` if needed |
| FTS5 / trigram missing on some Python builds | detected at build, `meta` says which; `LIKE` still works |
| Agents write wrong SQL for the graph | `--schema` meanings, examples, evals decide whether a view is needed |
| Format 3 locks out 0.3.x users of a shared repo | CHANGELOG and README say "upgrade everyone"; same as the v1 → v2 step |
| Layer 2 adds a second signed file and its rules | own phases, own ADRs; Layer 1 works without it |

## 5. Open questions for the owner

- **Q1.** ~~Default types: short generic descriptions or empty?~~ **Answered: ship short generic
  descriptions.**
- **Q2.** ~~Glossary in the configuration?~~ **Answered: no glossary feature; a project may model one with its own type and describe it** (§2.10).
*Q3–Q7 were parked until the Phase 6 gate; answered by the owner 2026-11-22 with Q9–Q11.*

- **Q3.** **Answered: admin only, no branch rule;** vocabulary/rules merge three-way per key, higher `vocabVersion`
  wins, same version on both sides is a conflict for an administrator (ADR-035). (Original:) Replace
  "`update-ai-labels` on main only" and "merge takes main's vocabulary" with "admin only" and "higher
  `vocabVersion` wins", keeping ADR-024's "no branch rule"?
- **Q4.** **Answered: yes** (ADR-034 §2). (Original:) Sign `specmodel.ai.json` with the same stamp as the model, so the admin-only parts can be
  enforced by the hooks and the audit (otherwise anyone can edit it unnoticed)?
- **Q5.** **Answered: yes** (ADR-034 §3). (Original:) `elementHash` over stereotype, topic, notes and fields only (a status change or a move to
  another folder keeps the labels)?
- **Q6.** **Answered: yes, and light** — label, type, topic and current labels only, to keep packets small
  (ADR-034 §6). (Original:) Neighbour scope for labelling: 1 hop over traceable links, at most 10 neighbours, summaries only?
- **Q7.** **Answered: documented advice;** the audit still shows who signed. (Original:) "AI changes in separate
  commits": documented advice, or refused by the pre-commit hook?
- **Q9.** **Answered: yes** — fix the eval generator and set a new baseline before Phase 7 (Phase 6b).
- **Q10.** **Answered:** the first vocabulary comes from `ai todo --vocab` (counts and samples), proposed by an
  agent, applied by an administrator (ADR-034 §6).
- **Q11.** **Answered:** label s1k fully first; s10k only if s1k shows a gain; packets of about 1 000 elements with
  light neighbours (cost per run is mostly the fixed ~55K of an agent).
- **Q8.** **Answered:** evals are run by Claude Code **Sonnet** subagents, all by AI. Each run's
  commands are checked: a run that used anything outside its variant's tools is invalid and repeated.
  If Sonnet answers well, that is enough. (Original question:) Evals are run by Claude Code subagents in this environment, with their token usage as the
  measure. Acceptable, or do you want another agent/tool measured too?
