#!/usr/bin/env python3
"""Turns the question templates of evals/questions.md into concrete questions with expected answers.

    python evals/instances.py <specmodel.json> <facts.json> <questions.json>

Subjects (which feature, which folder, ...) are picked from the model by fixed rules and a fixed
seed, so the same model gives the same questions. Expected answers come from the tool's own
definitions (query.trace/impact, validate.coverage_violations) and from the planted facts.
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from specgraph import model as M, query as Q, rules, validate as V  # noqa: E402

GOOD = ("approved", "validated", "implemented")


def make(model, facts):
    els, links, folders = model["elements"], model["links"], model["folders"]
    lab = lambda i: els[i]["label"]
    path = lambda fid: Q.folder_path(model, fid)
    out = []

    def pick(qid, candidates):
        cands = sorted(candidates, key=lambda c: json.dumps(c, sort_keys=True))
        return random.Random(qid).choice(cands) if cands else None

    def q(qid, kind, text, expected, subject=None):
        out.append({"id": qid, "kind": kind, "question": text, "expected": expected, "subject": subject})

    def desc(i):
        return "%s (\"%s\")" % (lab(i), els[i]["topic"])

    linked = set()
    for l in links.values():
        linked.update((l["source"], l["target"]))
    flat_to = lambda i: Q.flatten(Q.trace(model, i)["to"])

    # Q01 trace up to business requirements
    c = [i for i, e in els.items() if e["stereotype"] == "REQ" and
         any(n["stereotype"] == "B-REQ" for n in flat_to(i))]
    s = pick("Q01", c)
    if s:
        q("Q01", "ids", "Which business requirements (stereotype B-REQ) does %s ultimately serve, following "
          "traceable links from it?" % desc(s),
          sorted({n["label"] for n in flat_to(s) if n["stereotype"] == "B-REQ"}), lab(s))

    # Q02 impact of a feature
    c = [i for i, e in els.items() if e["stereotype"] == "FEAT" and 5 <= len(Q.impact(model, i)) <= 40]
    s = pick("Q02", c)
    if s:
        q("Q02", "ids", "If %s changes, which elements are affected, i.e. everything that traces to it "
          "directly or indirectly over traceable links?" % desc(s),
          sorted(n["label"] for n in Q.impact(model, s)), lab(s))

    cov = V.coverage_violations(model)
    by_folder = {}
    for _, eid, _ in cov:
        by_folder.setdefault(els[eid]["folder"], set()).add(eid)

    # Q03 coverage in one folder
    s = pick("Q03", [f for f, v in by_folder.items() if 1 <= len(v) <= 8])
    if s:
        q("Q03", "ids", "Which elements in folder '%s' break a coverage rule of the model?" % path(s),
          sorted(lab(i) for i in by_folder[s]), path(s))

    # Q04 count of coverage violations
    q("Q04", "count", "How many elements break a coverage rule in the whole model?", len({e for _, e, _ in cov}))

    # Q05.. concepts
    for n, (cname, ids) in enumerate(sorted(facts.get("concepts", {}).items())):
        if ids:
            q("Q05%s" % "abc"[n], "ids", "List every element whose own topic or notes are about %s, however "
              "it is worded. Elements that only link to such elements do not count." % cname,
              sorted(lab(i) for i in ids), cname)

    # Q06 field filter in one service (a top-level folder)
    def risks_hh(top):
        return sorted(lab(i) for i, e in els.items() if e["stereotype"] == "RISK"
                      and Q._in_folder(model, e["folder"], top)
                      and e["fields"].get("severity") == "High" and e["fields"].get("likelihood") == "High")
    s = pick("Q06", [f for f, x in folders.items() if x["parent"] is None and 1 <= len(risks_hh(f)) <= 8])
    if s:
        q("Q06", "ids", "Which RISK elements in folder '%s' (including its sub-folders) have severity High "
          "and likelihood High?" % path(s), risks_hh(s), path(s))

    # Q07 locked folders
    locks = {fid: f["lock"]["owner"] for fid, f in folders.items() if f.get("lock")}
    q("Q07", "paths", "Which folders are locked (give their paths)?", sorted(path(f) for f in locks))

    # Q08 links into locked folders from outside
    eff = rules.effective_locks(model)
    src = sorted({lab(l["source"]) for l in links.values()
                  if els[l["target"]]["folder"] in eff and els[l["source"]]["folder"] not in eff})
    q("Q08", "ids", "Which elements outside every locked folder have a link to an element inside a locked "
      "folder? Give the source elements.", src)

    # Q09 diagram contents by status
    def not_good(did):
        return sorted(lab(i) for i in model["diagrams"][did]["nodes"] if els[i]["status"] not in GOOD)
    s = pick("Q09", [d for d in model["diagrams"] if 1 <= len(not_good(d)) <= 12])
    if s:
        q("Q09", "ids", "Which elements shown on diagram '%s' are in a status other than approved, validated "
          "or implemented?" % model["diagrams"][s]["name"], not_good(s), model["diagrams"][s]["name"])

    # Q10 no links at all
    q("Q10", "ids", "Which elements have no links at all (neither incoming nor outgoing)?",
      sorted(lab(i) for i in els if i not in linked))

    # Q11 duplicates
    if facts.get("duplicates"):
        q("Q11", "ids", "Some requirements say the same thing as another requirement in slightly different "
          "words. List all elements of every such pair.", sorted(lab(i) for p in facts["duplicates"] for i in p))

    # Q12 count by status
    q("Q12", "count", "How many REQ elements are in status 'approved'?",
      sum(1 for e in els.values() if e["stereotype"] == "REQ" and e["status"] == "approved"))

    # Q13 tests of the requirements of a feature
    def tests_of(feat):
        reqs = {l["source"] for l in links.values() if l["type"] == "refines" and l["target"] == feat
                and els[l["source"]]["stereotype"] == "REQ"}
        return sorted({lab(l["source"]) for l in links.values() if l["type"] == "verifies" and l["target"] in reqs})
    s = pick("Q13", [i for i, e in els.items() if e["stereotype"] == "FEAT" and 1 <= len(tests_of(i)) <= 10])
    if s:
        q("Q13", "ids", "Which tests verify the requirements (REQ) that refine %s directly?" % desc(s),
          tests_of(s), lab(s))

    # Q14 cross-folder dependencies
    def cross(fid):
        return sorted({lab(l["source"]) for l in links.values() if l["type"] == "depends_on"
                       and els[l["source"]]["folder"] == fid and els[l["target"]]["folder"] != fid})
    s = pick("Q14", [f for f in folders if 1 <= len(cross(f)) <= 8])
    if s:
        q("Q14", "ids", "Which elements in folder '%s' have a depends_on link to an element in another folder?"
          % path(s), cross(s), path(s))

    # Q15 what a decision does
    def adr_reach(a):
        return sorted({lab(l["target"]) for l in links.values() if l["source"] == a
                       and l["type"] in ("implements", "mitigates")})
    s = pick("Q15", [i for i, e in els.items() if e["stereotype"] in ("ADR", "TEMPORAL-ADR")
                     and 2 <= len(adr_reach(i)) <= 6])
    if s:
        q("Q15", "ids", "Which elements does %s implement or mitigate?" % desc(s), adr_reach(s), lab(s))
    return out


def main(argv):
    if len(argv) != 3:
        sys.exit(__doc__)
    model = M.load(argv[0])
    with open(argv[1], encoding="utf-8") as fh:
        facts = json.load(fh)
    # facts may name elements by label (hand-written, for the example) or by id
    by_label = {e["label"]: i for i, e in model["elements"].items()}
    fix = lambda x: by_label.get(x, x)
    facts["concepts"] = {k: [fix(x) for x in v] for k, v in facts.get("concepts", {}).items()}
    facts["duplicates"] = [[fix(x) for x in p] for p in facts.get("duplicates", [])]
    qs = make(model, facts)
    with open(argv[2], "w", encoding="utf-8", newline="\n") as fh:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        rel = os.path.relpath(os.path.abspath(argv[0]), root).replace("\\", "/")
        json.dump({"model": rel if not rel.startswith("..") else os.path.abspath(argv[0]).replace("\\", "/"),
                   "questions": qs}, fh, indent=1)
        fh.write("\n")
    for x in qs:
        n = x["expected"] if x["kind"] == "count" else len(x["expected"])
        print("%-5s %-6s %5s  %s" % (x["id"], x["kind"], n, x["question"][:90]))


if __name__ == "__main__":
    main(sys.argv[1:])
