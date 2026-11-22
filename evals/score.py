#!/usr/bin/env python3
"""Scores agent answers against the expected answers of evals/instances.py.

    python evals/score.py <questions.json> <answers.json> [--md]

answers.json: {"<question id>": {"answer": [labels or ids] | number | [folder paths],
                                 "tokens": n?, "valid": true?, "note": "..."?}, ...}

For lists: precision, recall and F1 (labels compare case-insensitively; a full id is mapped to its
label). For counts: exact match (1 or 0). A run marked "valid": false (it used a command outside its
variant) is reported but not counted.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from specgraph import model as M  # noqa: E402


def norm_set(values, kind, id2label):
    out = set()
    for v in values or []:
        v = str(v).strip()
        if kind == "paths":
            out.add(v.strip("/").lower())
        else:
            out.add(id2label.get(v, v).upper())
    return out


def score_one(q, ans, id2label):
    if q["kind"] == "count":
        try:
            ok = float(ans) == float(q["expected"])
        except (TypeError, ValueError):
            ok = False
        return {"precision": None, "recall": None, "f1": 1.0 if ok else 0.0}
    exp = norm_set(q["expected"], q["kind"], id2label)
    got = norm_set(ans if isinstance(ans, list) else [], q["kind"], id2label)
    if not exp and not got:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    tp = len(exp & got)
    p = tp / len(got) if got else 0.0
    r = tp / len(exp) if exp else 0.0
    return {"precision": p, "recall": r, "f1": 2 * p * r / (p + r) if p + r else 0.0}


def main(argv):
    md = "--md" in argv
    argv = [a for a in argv if a != "--md"]
    if len(argv) != 2:
        sys.exit(__doc__)
    with open(argv[0], encoding="utf-8") as fh:
        qs = json.load(fh)
    with open(argv[1], encoding="utf-8") as fh:
        answers = json.load(fh)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    model = M.load(os.path.join(root, qs["model"]))  # relative to the repository root (absolute also works)
    id2label = {i: e["label"] for i, e in model["elements"].items()}
    rows, f1s, toks = [], [], []
    for q in qs["questions"]:
        a = answers.get(q["id"])
        if a is None:
            rows.append((q["id"], q["kind"], "-", "-", "-", "-", "not run"))
            continue
        s = score_one(q, a.get("answer"), id2label)
        valid = a.get("valid", True)
        if valid:
            f1s.append(s["f1"])
            if a.get("tokens") is not None:
                toks.append(a["tokens"])
        fmt = lambda x: "-" if x is None else "%.2f" % x
        rows.append((q["id"], q["kind"], fmt(s["precision"]), fmt(s["recall"]), fmt(s["f1"]),
                     a.get("tokens", "-"), ("" if valid else "INVALID ") + (a.get("note") or "")))
    head = ("question", "kind", "precision", "recall", "F1", "tokens", "note")
    if md:
        print("| " + " | ".join(head) + " |")
        print("|" + "---|" * len(head))
        for r in rows:
            print("| " + " | ".join(str(x) for x in r) + " |")
    else:
        for r in [head] + rows:
            print("%-9s %-6s %-9s %-7s %-5s %-8s %s" % r)
    mean = sum(f1s) / len(f1s) if f1s else 0.0
    print("\nmean F1 %.2f over %d valid answers; tokens total %s, mean %s" % (
        mean, len(f1s), sum(toks) if toks else "-", int(sum(toks) / len(toks)) if toks else "-"))


if __name__ == "__main__":
    main(sys.argv[1:])
