# Phase 6b — the baseline labels must beat

Run 2026-11-22 (tool 0.4.0, branch `3-Support_optimized_AI_synergy`). Same protocol and prompt as `INDEX.md`
(variant `index`: docs, Read/Grep on the model, `sg.py` including `sql`; Sonnet, one fresh agent per question), on
new models from the fixed generator. Only the questions labels are meant to help with: concept search (Q05a–c) and
near-duplicates (Q11). Answers: `index-v2-s1k.json`, `index-v2-s10k.json`; questions: `questions-s1k-v2.json`,
`questions-s10k-v2.json`; models: `models/s1k-v2`, `models/s10k-v2` (`--seed 1`, 1 031 and 9 978 elements).

## What changed in the generator (`sample/build_synthetic.py`)

- **No " (2)" topics.** U-REQs carry the module name; requirement, ADR, risk and test templates are drawn without
  repetition per module; a clash gets other numbers or another wording of the same concept; a concept is planted at
  most once per module and kind. Every topic is unique (`suffixed: 0` in `facts.json`, tested).
- **Unambiguous notes.** "Residents pay a fee for this; …" and "This stores residents' personal data; …" replace
  the notes the agents judged incidental. "a retention period … for photos" became "photos of residents follow the
  personal data retention rules".
- **Hidden plants.** Per concept, requirements that are about it without its usual words ("the kiosk takes coins
  and contactless", "a resident can have their records removed", "after 2 failed attempts the kiosk waits one
  minute"): 8 of 24 for authentication, 5 of 18 for payments, 6 of 14 for personal data. Listed in
  `facts.json` → `hidden`; the test checks they never match the concept's words.
- **Near-duplicates.** 3 pairs at 1K, 10 at 10K (was 2 and 5), copied only from requirements outside every concept,
  reworded with synonyms ("a clerk merges two …" → "a staff member combines two …").

## Results

| Q | s1k F1 · tokens | s10k F1 · tokens | named found | hidden found |
|---|---|---|---|---|
| Q05a authentication | 1.00 · 73K | 0.86 · 69K | 16/16 · 12/16 | 8/8 · 6/8 |
| Q05b payments | 0.84 · 68K | 0.94 · 80K | 13/13 · 13/13 | **0/5** · 3/5 |
| Q05c personal data | 0.67 · 64K | 1.00 · 87K | 7/8 · 8/8 | **0/6** · 6/6 |
| Q11 near-duplicates | 1.00 · 81K | 0.89 · 83K | — | — |

Precision was 1.00 in all eight answers.

- **Named concept elements: 69 of 74 found (93%).** The misses are judgement: the 10K authentication agent left out
  four "session token expires" requirements as "timeout, not authentication"; one personal-data element at 1K.
- **Hidden concept elements: 23 of 38 found (61%), and very unevenly.** A run either thinks of the right words and
  finds them all (s1k authentication 8/8, s10k personal data 6/6) or finds none (s1k payments 0/5, s1k personal data
  0/6 — that run used only `sg.py search`, never full-text search). Wordings never found: "the kiosk takes coins and
  contactless", "the price … is shown before it is booked" (1K), "the finance office sees what each … brought in",
  "after 2 failed attempts the kiosk waits one minute" (10K), "a resident can have their records removed", "the home
  address … is hidden", "residents' names never appear in the open data" (1K).
- **Near-duplicates are found by structure.** With the " (2)" noise gone, agents compared topics within an area
  in SQL and found 3/3 pairs at 1K and 8/10 at 10K (missed: "works for" → "keeps working for", "moved to" →
  "transferred to"). Rewordings this shallow are a SQL task; labels would add little.
- Tokens: 64–87K per question (9–32K of work), more than the structural questions (60–66K), because agents iterate
  on search terms.

## What labels have to beat

The room left for labels is **concept search on wordings an agent does not think of**: 39% of hidden plants
missed, with a large spread between runs. Labels assigned once, by an agent reading each element, should make this
recall stable. Phase 12 compares on these models and question files, by the same protocol, with labels available.
One run per question is noisy (the same kind of question went 0/6 and 6/6); Phase 12 should run each concept
question at least twice per variant.
