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

## Phase 9 — a vocabulary revision and the relabelling it causes

An Opus agent reviewed the labelled model as an administrator would (`ai todo --vocab` with `used` counts, then SQL on
`ai_labels`) with the instruction to change only what is clearly better, since every change costs relabelling.

| Step | Agent | Tokens | Time |
|---|---|---|---|
| Revision: retire the "Kinds of case" branch (6 concepts) | Opus | 95K | 1.7 min |
| Relabel the stale elements (`ai todo`: 179 elements, one packet) | Sonnet | 127K | 1.4 min |

- Its reason: the five case-kind concepts restated each service folder's own noun and sat on only ~20% of the
  elements they described (mostly tests and ADRs), so a search by them would miss most; `--folder` and full-text
  search already find those elements.
- `ai status` after applying: exactly the **179** elements carrying a retired concept stale (as the agent predicted),
  the other 852 current. After relabelling: 1 031 current, 0 stale; vocabulary 84 active, 6 retired, version 2.
- Planted concepts unchanged: authentication 24/24, payments 18/18, personal data 14/14, hidden 19/19; 2 extras.
- Incremental cost: ~127K for 179 elements, of which ~55K is the fixed cost of one agent run.

## Phase 11 — a first review through the labels (ADR-036)

One Opus agent reviewed the first `ai review` packet of s1k-v2 (the 7 largest concepts, 300 elements, 109 KB) and
wrote `ai.finding.add` operations; they were applied as the administrator.

| Step | Agent | Tokens | Time |
|---|---|---|---|
| Review of packet 1 (7 concepts, 300 elements) | Opus | 147K | 3.2 min |

- **23 findings, all accepted** (every quote found in its element): 21 `missing-link`, 1 `gap`, 1 `duplicate`.
- **Planted problems** (`facts.json`): 1 of the 3 near-duplicate pairs recorded (`REQ-0696580b` / `REQ-1ea3cf09`, also
  noted as misplaced); the other two pairs were spotted by a SQL check but not reported because their elements were
  not in this packet. 1 of the 4 elements without links found (the only one in the packet), with an `ops` batch
  linking it.
- **Unplanted but real by the texts:** the generator links tests to requirements of the same module at random, so a
  requirement "a … that waits more than N days is marked late" is often verified by an unrelated test while the "a
  late … is marked late" test verifies something else. The agent reported 20 such pairs; read as specs they are true
  findings. One `gap`: two business goals with no user requirement refining them.
- No contradiction, terminology or misplaced finding of its own (the model has few to find).

A full review of s1k-v2 would take about 4 such packets (~600K Opus tokens); reviews are meant to be run on request,
per concept.
