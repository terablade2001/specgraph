# Phase 6 — the same questions with the index (`sg.py sql`)

Run 2026-11-22 on branch `3-Support_optimized_AI_synergy` (tool 0.4.0, after Phases 3–5). Protocol:
`evals/README.md`, variant `index`: the baseline variant plus `sg.py sql|index` and the new "Reading a large model"
section of `docs/AGENTS.md`. Same stored models (`models/s1k`, `models/s10k`, `specmodel.example.json`), same question
files (`questions-*.json`), same prompt wording as the baseline repeats, one fresh Sonnet subagent per question.
Answers: `index-example.json`, `index-s1k.json`, `index-s10k.json`; scored with `evals/score.py`. Baseline:
`BASELINE.md`.

## Results

| Model | Mean F1 baseline → index | Without Q11 ¹ | Mean tokens baseline → index | Largest run baseline → index |
|---|---|---|---|---|
| example (26 elements) | 1.00 → **1.00** | 1.00 → 1.00 | 62K → 62K | 74K → 65K |
| s1k (1 034) | 0.96 → **0.91** | 0.96 → **0.97** | 74K → 65K | 144K → 86K |
| s10k (9 966) | 0.85 → **0.95** | 0.90 → **0.99** | 70K → 66K | 93K → 103K |

¹ Q11 (near-duplicates) depends on a known flaw of the generator (below); without it the comparison is cleaner.

Control overhead is 55K tokens (`BASELINE.md`), so the work of an average question went from ~15–18K to ~7–11K.
No run used a forbidden tool. Six s1k runs were cut by a usage limit before answering and were rerun with fresh
agents; only the reruns are recorded.

Per question (F1 · thousand tokens, baseline → index):

| Q | Kind | example | s1k | s10k |
|---|---|---|---|---|
| Q01 | trace up | 1.00 · 60 → 1.00 · 60 | 1.00 · 59 → 1.00 · 60 | 1.00 · 59 → 1.00 · 60 |
| Q02 | impact | 1.00 · 60 → 1.00 · 60 | 1.00 · 61 → 1.00 · 61 | 1.00 · 61 → 1.00 · 61 |
| Q03 | coverage in a folder | 1.00 · 61 → 1.00 · 62 | 1.00 · 70 → 1.00 · 63 | 1.00 · 69 → 1.00 · 61 |
| Q04 | coverage count | 1.00 · 58 → 1.00 · 60 | 1.00 · 63 → 1.00 · 62 | 1.00 · 61 → 1.00 · 62 |
| Q05a | concept: authentication | 1.00 · 63 → 1.00 · 63 | 0.77 · 65 → **1.00** · 76 | 0.70 · 71 → **1.00** · 70 |
| Q05b | concept: payments | 1.00 · 62 → 1.00 · 63 | 0.91 · 72 → 0.91 · 65 | 1.00 · 72 → 0.91 · 65 |
| Q05c | concept: personal data | 1.00 · 61 → 1.00 · 61 | 0.88 · 72 → 0.83 · 65 | 0.73 · 69 → **0.96** · 83 |
| Q06 | field filter | — | 1.00 · 74 → 1.00 · 65 | 1.00 · 81 → 1.00 · 62 |
| Q07 | locked folders | 1.00 · 59 → 1.00 · 59 | 1.00 · 61 → 1.00 · 61 | 1.00 · 61 → 1.00 · 61 |
| Q08 | links into locked folders | 1.00 · 63 → 1.00 · 64 | 1.00 · **93** → 1.00 · 66 | 1.00 · **93** → 1.00 · 63 |
| Q09 | diagram × status | 1.00 · 74 → 1.00 · 65 | 1.00 · 67 → 1.00 · 62 | 1.00 · 69 → 1.00 · 65 |
| Q10 | elements without links | 1.00 · 70 → 1.00 · 59 | 1.00 · **144** → 1.00 · 63 | **0.00** · 78 → **1.00** · 63 |
| Q11 | near-duplicates | — | 1.00 · 101 → **0.00** · 86 | 0.00 · 88 → 0.33 · 103 |
| Q12 | count | 1.00 · 59 → 1.00 · 59 | 1.00 · 60 → 1.00 · 60 | 1.00 · 61 → 1.00 · 60 |
| Q13 | two typed hops | 1.00 · 61 → 1.00 · 65 | 0.80 · 62 → 0.80 · 63 | 1.00 · 64 → 1.00 · 66 |
| Q14 | depends_on across folders | 1.00 · 64 → 1.00 · 62 | 1.00 · 67 → 1.00 · 63 | 1.00 · 70 → 1.00 · 62 |
| Q15 | one typed hop | 1.00 · 59 → 1.00 · 59 | 1.00 · 59 → 1.00 · 60 | 1.00 · 59 → 1.00 · 60 |

## What changed

1. **Joins and whole-model scans are solved.** Q10 (no links) is one query at every size: 144K → 63K tokens at 1K,
   F1 0.00 → 1.00 at 10K. Q08 (links into locked folders) 93K → 64K. Q03/Q04/Q06/Q09/Q14 are one or two queries.
   No run had to page through `validate` or `search ""`, and none reached for a forbidden tool to read a saved
   output file (three baseline runs did).
2. **Cost no longer grows with the model.** Every question except Q05c and Q11 costs 60–66K tokens (5–11K of work)
   at 26, 1 000 and 10 000 elements.
3. **Concept search improved where wording varies most.** Authentication, the hardest concept of the baseline,
   is 1.00 at 1K and 10K (from 0.77 and 0.70). Agents used `elements_fts` with many terms, then `LIKE` and a
   `GROUP BY notes` to find wordings they had not thought of.
4. **The existing commands are still used where they fit.** `trace`, `impact`, `show` answered Q01, Q02, Q13, Q15
   as before; agents took SQL only where no command answers.

## What did not change, and why

- **Q11 (near-duplicates) is not an index question.** With SQL, agents found the ~370 identical topics that the
  generator makes unique with " (2)", " (3)" (a known flaw, `BASELINE.md`) and either reported them (1K, F1 0.00)
  or excluded them and found one of the five planted pairs by filtering (10K, 0.33). The baseline 1K run read all
  topics by hand instead. Finding rewordings needs meaning, not joins; the noise from the generator makes the
  question unfair as it stands.
- **Residual concept misses** (Q05b, Q05c), all checked by hand:
  - payments, 3 misses at 1K and 10K: elements whose only hint is the note "The fee table comes from the finance
    office every January". The agents saw the note and judged it incidental — the ambiguity already listed in
    `BASELINE.md`, not a search failure (FTS matches *fee*).
  - personal data: "a resident downloads all data held about them" (a subject access request, never called
    personal data) — 2 misses at 1K, 1 at 10K. This is the one true *meaning* miss: no search term an agent tried
    reaches it.
  - personal data at 1K: two elements with the note "The data protection officer asked for this retention rule"
    were found and then left out by the agent's judgement; the 10K agent kept them.
- Q13 at 1K: the same miss as the baseline (a test that verifies the REQ only through a `depends_on` hop).

## Things agents stumbled on (for the guide, not the tool)

- Backslash paths in the prompt are eaten by Git Bash: about a third of the runs needed a second call. This is
  the prompt (same in the baseline), not the tool.
- Two runs guessed column names of `element_notes` (`element`, `text`, `body`) before reading `sql --schema`. The
  guide says to start with the schema; no change needed.
- One run tried `matrix TEST REQ` at 10K (1.3 MB of output) and switched to SQL.

No query was got wrong or rewritten often enough to justify a new view or command (plan §Phase 6).

## For the Layer 2 decision gate

The index removed the scaling failures. What remains of concept search is small: across 6 concept questions on
the synthetic models (s1k and s10k, 3 each), 11 planted elements were missed: 6 are the ambiguous "fee table" note,
2 are judgement calls on notes the agent had found, and 3 are genuine meaning misses of one kind ("downloads all
data held about them"). Precision stayed 1.00. Labels would address only
those. Q11 needs meaning too, but cannot be judged until the generator stops producing identical topics.
