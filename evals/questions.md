# Evaluation questions

Questions an agent is asked about a model, as templates. `evals/instances.py` picks the subject of each
question from a model (fixed rules, fixed seed) and computes the expected answer. Expected answers come
from the tool's own definitions (`query.trace`, `query.impact`, `validate.coverage_violations`,
`rules.effective_locks`) or from facts planted by `sample/build_synthetic.py` (`facts.json`), or written
by hand for the example (`evals/example.facts.json`). No person judges an answer.

| Id | Kind | Question (template) | What it tests | Expected answer from |
|---|---|---|---|---|
| Q01 | ids | Which business requirements (B-REQ) does *REQ x* ultimately serve, following traceable links? | trace up, several hops | `trace(x).to`, B-REQ only |
| Q02 | ids | If *FEAT x* changes, which elements are affected (everything that traces to it)? | impact, many hops, many results | `impact(x)` |
| Q03 | ids | Which elements in folder *f* break a coverage rule? | coverage, folder scope | `coverage_violations` in *f* |
| Q04 | count | How many elements break a coverage rule in the whole model? | whole-model aggregate | `coverage_violations` |
| Q05a–c | ids | List every element whose own topic or notes are about *concept*, however it is worded. | search by meaning, different words | planted concepts |
| Q06 | ids | Which RISK elements in folder *f* (and below) have severity High and likelihood High? | custom fields, folder tree | model data |
| Q07 | paths | Which folders are locked? | locks | `folders.*.lock` |
| Q08 | ids | Which elements outside every locked folder link to an element inside one? | locks × links | `effective_locks` + links |
| Q09 | ids | Which elements on diagram *d* are not approved, validated or implemented? | diagram membership × status | `diagrams.*.nodes` |
| Q10 | ids | Which elements have no links at all? | whole-model scan | links |
| Q11 | ids | Which requirements say the same as another one in other words? List all of each pair. | near-duplicates (meaning) | planted pairs (synthetic only) |
| Q12 | count | How many REQ elements are in status approved? | aggregate | model data |
| Q13 | ids | Which tests verify the REQs that refine *FEAT x* directly? | two typed hops | links |
| Q14 | ids | Which elements in folder *f* have a depends_on link to an element in another folder? | link type × folder | links |
| Q15 | ids | Which elements does *ADR x* implement or mitigate? | one typed hop | links |

Subjects are chosen so that answers stay small (usually 1–40 items); the counts (Q04, Q12) and the
whole-model scans (Q10) grow with the model on purpose.

Definitions the agent is expected to use come from `docs/FORMAT.md` ("Traceability": links whose type has
`traceable` not false; "impact of Y" = everything with a path to Y).
