# Baseline (Phase 1) — specgraph 0.3.1 as it is

Run 2026-11-22 on branch `3-Support_optimized_AI_synergy`, before any 0.4 change. Protocol: `evals/README.md`.
Agent: Claude Code subagent on **Sonnet**, one fresh agent per question. Variant `baseline`: the docs
(`README.md`, `docs/FORMAT.md`, `docs/AGENTS.md`), Read/Grep on the model file, and
`sg.py search|show|trace|impact|matrix|validate`. Answers: `baseline-example.json`, `baseline-s1k.json`,
`baseline-s10k.json`; scored with `evals/score.py`.

## Models

| Model | Elements | Links | File | Build |
|---|---|---|---|---|
| example (`specmodel.example.json`) | 26 | 26 | 30 KB | stored |
| s1k (`build_synthetic.py --elements 1000 --seed 1`, stored in `models/s1k/`) | 1 034 | 1 320 | 0.7 MB | 0.7 s |
| s10k (`--elements 10000 --seed 1`, stored in `models/s10k/`) | 9 966 | 13 325 | 7 MB | 21 s |

## Results

Tokens = everything the subagent used. A control run that only answers "ok" costs **55 205** tokens
(system prompt + tool definitions), so the work of a question is roughly *tokens − 55K*.

| Model | Mean F1 | Questions | Mean tokens | Mean work tokens (− 55K) | Invalid runs (repeated) |
|---|---|---|---|---|---|
| example | **1.00** | 15 | 62 293 | ~7K | 0 |
| s1k | **0.96** | 17 | 73 537 | ~18K | 1 (pipe into `head`) |
| s10k | **0.85** | 17 | 69 783 | ~15K | 2 (read the generator; grepped a saved output file) |

Per question (F1; tokens in thousands):

| Q | Kind of question | example | s1k | s10k |
|---|---|---|---|---|
| Q01 | trace up to B-REQ | 1.00 · 60 | 1.00 · 59 | 1.00 · 59 |
| Q02 | impact of a feature | 1.00 · 60 | 1.00 · 61 | 1.00 · 61 |
| Q03 | coverage in a folder | 1.00 · 61 | 1.00 · 70 | 1.00 · 69 ¹ |
| Q04 | coverage count, whole model | 1.00 · 58 | 1.00 · 63 | 1.00 · 61 ¹ |
| Q05a | concept: authentication | 1.00 · 63 | **0.77** · 65 | **0.70** · 71 |
| Q05b | concept: payments | 1.00 · 62 | **0.91** · 72 | 1.00 · 72 |
| Q05c | concept: personal data | 1.00 · 61 | **0.88** · 72 | **0.73** · 69 |
| Q06 | field filter in a folder tree | — | 1.00 · 74 | 1.00 · 81 |
| Q07 | locked folders | 1.00 · 59 | 1.00 · 61 | 1.00 · 61 |
| Q08 | links into locked folders | 1.00 · 63 | 1.00 · 93 | 1.00 · 93 |
| Q09 | diagram × status | 1.00 · 74 | 1.00 · 67 | 1.00 · 69 |
| Q10 | elements without links | 1.00 · 70 | 1.00 · **144** ² | **0.00** · 78 ³ |
| Q11 | near-duplicate requirements | — | 1.00 · **101** | **0.00** · 88 ³ |
| Q12 | count REQ approved | 1.00 · 59 | 1.00 · 60 | 1.00 · 61 |
| Q13 | tests of a feature's REQs | 1.00 · 61 | **0.80** · 62 | 1.00 · 64 |
| Q14 | depends_on across folders | 1.00 · 64 | 1.00 · 67 | 1.00 · 70 |
| Q15 | what an ADR implements | 1.00 · 59 | 1.00 · 59 | 1.00 · 59 |

¹ The `validate` output (1 104 warnings) is too large to read; the agent reports how it counted, which
could not be checked from its transcript. ² 59 tool calls, 171 s: Grep on the model, one id prefix at a
time. ³ The agent gave up and said so.

Precision was 1.00 on every answer that was not empty: when Sonnet answers, it is right; it misses.

## What the baseline shows

1. **Questions the existing commands answer are cheap and correct at every size.** `trace`, `impact`,
   `show`, `search --folder/--stereotype/--status` (Q01, Q02, Q06, Q09, Q13–Q15): 1 call, ~60K tokens,
   F1 1.00 even at 10K. Nothing to fix there.
2. **Questions without a command fall back to reading the file, and that stops scaling.**
   - Q10 (no links): fine at 26, 144K tokens and 59 calls at 1K, impossible at 10K.
   - Q11 (duplicates): 101K at 1K by reading every topic, impossible at 10K.
   - Q08 (links into locked folders): 93K at 1K and 10K, because links must be matched by hand.
   These are joins and anti-joins (`elements` without `links`, `links` × `folders`): what SQL does in one line.
3. **Large outputs break the tools at 10K.** `validate` and `search ""` print thousands of entries;
   Claude Code saves them to a file instead of showing them. Agents then reach for forbidden tools
   (grep on the saved file, pipes into `head`, a shell loop) or read the generator script. Row caps,
   `COUNT(*)` and `LIMIT` answer this directly.
4. **Search by meaning misses at every size above the toy example.** Substring `search` finds only the
   words the agent thinks of. Authentication is the clear case: "signs in", "two-factor", "session
   token", "log in" were missed (recall 0.54–0.62; 0.65–0.75 when only topic matches count). This is
   what FTS with stemming, synonym expansion and, later, labels are meant to fix — and the case the
   Phase 6 gate will look at.
5. **Tokens stay flat (~60–90K) because output is cut, not because the work is small.** The cost of a
   large model shows up as wrong or empty answers and tool misuse, not as a higher token count.

## Issues found in the evaluation itself (to fix before Phase 6, without changing these builds)

- **The generator gives answers away.** One run read `sample/build_synthetic.py` and grepped the pattern
  of the planted orphans. Every prompt now forbids reading `sample/`, `evals/`, `specgraph/`, `tests/`
  and saved tool output files (the repeats already used this wording).
- **Ambiguous planted concepts.** (a) Elements whose concept is only in the notes (e.g. "The fee table
  comes from the finance office") were judged incidental by the agents. (b) The template "a retention
  period of N months for *X* photos" is not clearly about personal data. Both are reported separately
  above; the strict reading only changes the payments and personal-data numbers.
- **Repeated topics.** When a template repeats, the generator appends " (2)", " (3)": ~370 identical
  requirements at 10K. They do not change any expected answer but add noise to Q11.
- The Phase 6 run uses the **same models**, stored in `evals/results/models/`, and the same question files
  (`evals/results/questions-*.json`), so the numbers compare one to one; the generator fixes go in after that comparison.
