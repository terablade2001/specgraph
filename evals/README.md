# Agent evaluations

Measures how well an AI agent answers questions about a specgraph model, and how many tokens it needs.
Used for the 0.4.x read layer (`docs/PLAN-0.4-AI-LAYER.md`): a baseline on the tool as it is, then the
same questions with the new tools. Nothing here is part of the tool; it only uses it.

## Files

| File | What |
|---|---|
| `sample/build_synthetic.py` | builds a large synthetic model + `facts.json` (planted facts) |
| `evals/questions.md` | the question templates and where their answers come from |
| `evals/instances.py` | model + facts → concrete questions with expected answers (`questions.json`) |
| `evals/example.facts.json` | hand-written facts for `specmodel.example.json` |
| `evals/score.py` | answers → precision / recall / F1 per question, tokens |
| `evals/results/` | recorded runs: questions of the builds used, answers, reports (`BASELINE.md`) |
| `evals/results/models/` | the synthetic models the recorded runs used (`specmodel.json` + `facts.json`), kept so every later run uses the same ones |
| `evals/build/` | scratch: new builds and questions; not committed (holds a throwaway private key) |

## Building the models

```
python sample/build_synthetic.py evals/build/s1k  --elements 1000  --seed 1
python sample/build_synthetic.py evals/build/s10k --elements 10000 --seed 1
python evals/instances.py specmodel.example.json evals/example.facts.json evals/build/q-example.json
python evals/instances.py evals/build/s1k/specmodel.json  evals/build/s1k/facts.json  evals/build/q-s1k.json
python evals/instances.py evals/build/s10k/specmodel.json evals/build/s10k/facts.json evals/build/q-s10k.json
```

The same seed gives the same model: ids and generated labels come from the seed, so a rebuild gives the
same questions and answers (only the signature, the key and the times differ; `tests/test_synthetic.py`).
The two stored models below were built **before** ids were seeded, so a rebuild does not reproduce them. **To compare with the recorded baseline, use the stored models, not a new
build:** `evals/results/models/s1k/specmodel.json` and `…/s10k/specmodel.json` (signed by a throwaway key:
readable with `--file`, not editable). The question files in `evals/results/` point at them, with paths relative
to the repository root.

**Version 2 (Phase 6b).** The generator was fixed after the Phase 6 comparison: unique topics (no " (2)"),
unambiguous concept notes, *hidden* concept plants that never use the concept's words (`facts.json` → `hidden`),
more near-duplicate pairs reworded with synonyms. Stored as `evals/results/models/s1k-v2` and `…/s10k-v2`
(`--seed 1`) with `questions-s1k-v2.json` / `questions-s10k-v2.json`; results in `results/INDEX-V2.md`. The label
measurements (Phase 12) use these. The version-1 models stay for the recorded baseline and `INDEX.md`.

## Running (protocol)

- **Agent:** a Claude Code subagent on **Sonnet**, one fresh agent per question and model, so no run
  sees another's work. All runs are done by AI.
- **Prompt:** the repository path, the model path, the allowed tools of the variant, the question, and
  the answer format (last lines `COMMANDS: …` and `ANSWER: <JSON>`). Nothing else: no hint about the
  answer or how to find it.
- **Variants:**
  - `baseline` — docs (`README.md`, `docs/FORMAT.md`, `docs/AGENTS.md`), the Read and Grep tools on the
    model file, and `python sg.py --file <model> search|show|trace|impact|matrix|validate`.
  - `index` (Phase 6) — the same plus `sg.py sql|index` and the "Reading a large model" section of
    `docs/AGENTS.md`. Recorded in `results/INDEX.md` (`index-*.json`).
- **Forbidden in every variant:** reading any other repository file (`sample/`, `evals/`, `specgraph/`,
  `tests/` — the generator would give answers away), Grep/Read on saved tool output files, pipes,
  redirection, shell `grep`/`cat`/`head`, `python -c`, any other script.
- **Checking:** every run reports the commands it ran; a run that used anything outside its variant
  (another script, `python -c`, shell `grep`/`cat`, …) is marked invalid and repeated.
- **Measured:** the answer (scored by `score.py`) and the total tokens of the subagent run as reported
  by Claude Code.
- **Cut-off:** a run that cannot fit the model into its context reports that and gives its best answer;
  that is a result, not an error.
