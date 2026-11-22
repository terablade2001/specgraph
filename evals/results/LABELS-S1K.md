# Phase 8 — first labelling pass on s1k-v2: cost and quality

Run 2026-11-22, tool 0.4.0 with `sg.py ai todo` / `ai apply` (ADR-034). Model `models/s1k-v2` (1 031 elements). The
agents followed `docs/AGENTS.md` ("Running a labelling pass") and the prompts inside the packets; they wrote operation
files and the operations were applied with the model's throwaway administrator key ("synth"). The resulting
`specmodel.ai.json` and `specmodel.ai.log.jsonl` are stored next to the model for Phase 12.

## Cost

| Step | Agent | Packet | Tokens | Time |
|---|---|---|---|---|
| Vocabulary (`ai todo --vocab`, 400 samples, 200 terms) | Opus | 51 KB | 123K | 3.1 min |
| Labels, packet 1 (`--limit 520`) | Sonnet | 135 KB | 178K | 3.9 min |
| Labels, packet 2 (remaining 511) | Sonnet | 130 KB | 170K | 3.5 min |
| **Total** | | | **471K** | 10.5 min |

About 340 tokens per element for labelling, against the 0.1–0.2M estimated for s1k (ADR-034, plan Q11): the agents
read each packet in pages, wrote ~520 operations each (split into three files), and the fixed ~55K per run counts
twice. Packets of ~520 elements worked; 1 000 would have been one run but more output in one go. Extrapolated to
s10k: ~3.4M tokens for a first pass with Sonnet, plus a vocabulary run. Afterwards only changed elements are
relabelled.

## Result

- Vocabulary: 90 concepts (19 top-level, 71 second-level) proposed by Opus, applied unchanged. 76 used; 14 unused.
- Labels: all 1 031 elements, 1 679 element–label pairs (1.6 per element), none empty. No operation was refused
  (every key in the vocabulary, every hash current).
- Files: `specmodel.ai.json` 284 KB (about 275 bytes per element: hash key, labels, user, model, element list —
  more than the ~100 bytes estimated), log 246 KB (1 121 lines).

Planted concepts against the vocabulary branch that covers them (`facts.json`):

| Concept | Branch | Planted found | Hidden found | Labelled in branch but not planted |
|---|---|---|---|---|
| authentication | Security and access | 24/24 | 8/8 | 0 |
| payments | Payments and fees | 18/18 | 5/5 | 0 |
| personal data | Privacy and personal data | 14/14 | 6/6 | 2 ("a stolen password opens resident records": also confidentiality) |

With the index alone, agents found 61% of the hidden plants (`INDEX-V2.md`); the labels carry all of them. One
caveat: the vocabulary agent saw the hidden wordings among its 400 samples (at 1K they cover most of the ~60
templates) and wrote some into the definitions ("coins and contactless at a kiosk", "the national e-ID app"). That
is how labels are meant to help — one agent reads the whole model once — but at 10K, or on real models, the samples
cover less, so the vocabulary depends more on the labelling agent's own judgement. Phase 12 measures whether agents
answering questions actually use the labels.
