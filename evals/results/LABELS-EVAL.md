# Phase 12 — the same questions with and without AI labels

Run 2026-11-22, tool 0.4.0 (after Phase 11). Model s1k-v2 (1 031 elements), questions `questions-s1k-v2.json`:
the concept questions Q05a–c and the near-duplicate question Q11. Same protocol and prompt as `INDEX.md` /
`INDEX-V2.md` (Sonnet, one fresh agent per question, docs + Read/Grep on the model + `sg.py` incl. `sql`); the
`docs/AGENTS.md` the agents read now has the AI-labels section.

- **labels**: a copy of the model with the AI file of the first labelling pass after the vocabulary revision
  (commit 5390fe8: 84 concepts, all 1 031 elements labelled, **no findings**, so the review's duplicate finding
  could not give Q11 away). Two runs, A and B.
- **no labels**: a copy without an AI file. One run here, plus the run of `INDEX-V2.md` on the same model and
  questions.

Answers: `p12-labels-a-s1k-v2.json`, `p12-labels-b-s1k-v2.json`, `p12-nolabels-s1k-v2.json`, `index-v2-s1k.json`.

## Results

| Q | no labels (6b) | no labels (12) | labels A | labels B |
|---|---|---|---|---|
| Q05a authentication | 1.00 (hidden 8/8) | 0.91 (4/8) | 0.98 (7/8) | 0.91 (8/8) |
| Q05b payments | 0.84 (0/5) | 0.84 (0/5) | 0.94 (3/5) | 0.94 (3/5) |
| Q05c personal data | 0.67 (0/6) | 0.83 (2/6) | 1.00 (6/6) | 1.00 (6/6) |
| Q11 near-duplicates | 1.00 | 1.00 | 1.00 | 1.00 |
| **Mean F1, concepts** | 0.84 | 0.86 | **0.97** | **0.95** |
| **Hidden plants found** | 8/19 | 6/19 | **16/19** | **17/19** |
| Mean tokens, concepts | 68K | 67K | 72K | 74K |

Precision was 1.00 in all 16 answers.

- **Hidden concept elements: 14/38 (37%) without labels, 33/38 (87%) with labels**, and steady between runs (16
  and 17 of 19, against 6 to 8 without). This is what Layer 2 was built for.
- Every labelled run queried `ai_labels` (by key, by key pattern or by the concept's branch), next to full-text
  search. None relied on labels alone.
- **What labels did not fix is judgement.** The agents found the labelled elements and then left some out:
  both runs dropped "the price of a … is shown before it is booked" as "showing a price, not paying"; run B dropped
  four elements whose authentication is only in the notes ("Clerks reach this only after they log in with their
  badge") although they carry authentication labels. The question's wording, not the retrieval, decided these.
- **Near-duplicates (Q11): no difference.** Every run read all 417 requirement topics in four pages of SQL and found
  the three pairs; the labels were not used for it.
- **Cost of answering:** about +5K tokens per concept question with labels (agents read the vocabulary first).
  The labels themselves cost 471K tokens once (`LABELS-S1K.md`) and ~130K per revision with relabelling.

## Limits

- One model of 1 000 elements, three concepts, 19 hidden plants; at 10 000 elements the labelling pass would cost
  ~3.4M tokens and was not run.
- The vocabulary agent saw the hidden wordings in its samples (`LABELS-S1K.md`); on a real model, or at 10K, the
  vocabulary may cover such wordings less well.
- Two runs per variant; the spread between runs without labels (0 to 8 of 8 per concept) is larger than with them.
