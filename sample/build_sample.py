#!/usr/bin/env python3
"""Builds the demo model (REQ-DOC-05) through the tool's own operations.

    python sample/build_sample.py <empty-directory>

Creates a git repository on docs/specifications with a model containing a few
elements per stereotype, three diagrams sharing elements and one locked folder.
Uses the key loaded in ssh-agent as the administrator "demo".
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from specgraph.store import Store  # noqa: E402


def build(target, key=None, user="demo"):
    os.makedirs(target, exist_ok=True)
    if not os.path.isdir(os.path.join(target, ".git")):
        subprocess.run(["git", "init", "-q", "-b", "docs/specifications"], cwd=target, check=True)
    s = Store(cwd=target, key=key)
    s.init(user)
    ops, idx = [], {}

    def add(ref, op, **args):
        idx[ref] = "$%d" % len(ops)
        ops.append({"op": op, "args": args})

    add("inv", "folder.create", name="Invoicing")
    add("num", "folder.create", name="Numbering", parent="$0")
    add("arch", "folder.create", name="Architecture")
    add("leg", "folder.create", name="Legal baseline (locked)")
    prefixes, counts = s.load()["config"]["stereotypes"], {}

    def label(st):  # the demo uses readable numbered labels, typed by hand; new elements get short-id labels
        counts[st] = counts.get(st, 0) + 1
        return "%s-%03d" % (prefixes[st]["labelPrefix"], counts[st])

    el = lambda n, st, topic, folder, **kw: add(n, "element.create", stereotype=st, topic=topic, label=label(st),
                                                 folder=idx[folder], **kw)
    el("br1", "CONSTRAINT", "Invoice numbers are consecutive per fiscal year", "leg", status="approved",
       notes="Tax authority rule. Do not change without the legal team.")
    el("br2", "CONSTRAINT", "Issued invoices are immutable", "leg", status="approved")
    el("r1", "REQ", "Every invoice gets a unique number", "num", status="approved", fields={"priority": "Must"})
    el("r2", "REQ", "Numbering has no gaps", "num", status="validated", fields={"priority": "Must"})
    el("r3", "REQ", "Corrections are made by credit note", "inv", status="proposed", fields={"priority": "Should"})
    el("r4", "REQ", "Invoices can be exported as PDF", "inv", status="implemented", fields={"priority": "Could"})
    el("a1", "ADR", "Allocate numbers from a database sequence table", "arch", status="approved")
    el("a2", "ADR", "Store invoices append-only", "arch", status="proposed")
    el("a3", "ADR", "Render PDFs server-side", "arch", status="implemented")
    el("k1", "RISK", "Rollback leaves a gap in the sequence", "num", status="approved",
       fields={"severity": "High", "likelihood": "Medium"})
    el("k2", "RISK", "Concurrent issuing produces duplicates", "num", status="proposed", fields={"severity": "High"})
    el("k3", "RISK", "PDF layout differs between printers", "inv", status="rejected", fields={"severity": "Low"})
    ln = lambda t, a, b: ops.append({"op": "link.create", "args": {"type": t, "source": idx[a], "target": idx[b]}})
    ln("refines", "r1", "br1"); ln("refines", "r2", "br1"); ln("refines", "r3", "br2")
    ln("implements", "a1", "r1"); ln("implements", "a1", "r2"); ln("implements", "a2", "r3")
    ln("implements", "a2", "br2"); ln("implements", "a3", "r4")
    ln("mitigates", "a1", "k1"); ln("mitigates", "a1", "k2"); ln("depends_on", "r2", "r1"); ln("relates_to", "k3", "r4")
    add("d1", "diagram.create", name="Numbering overview", folder=idx["num"])
    add("d2", "diagram.create", name="Decisions and what they implement", folder=idx["arch"])
    add("d3", "diagram.create", name="Risks", folder=idx["num"])
    pl = lambda d, e, x, y: ops.append({"op": "diagram.place", "args": {"diagram": idx[d], "element": idx[e], "x": x, "y": y}})
    pl("d1", "br1", 300, 20); pl("d1", "r1", 120, 190); pl("d1", "r2", 480, 190); pl("d1", "a1", 300, 370); pl("d1", "k1", 660, 370)
    pl("d2", "a1", 40, 40); pl("d2", "a2", 40, 200); pl("d2", "a3", 40, 360)
    pl("d2", "r1", 380, 0); pl("d2", "r2", 380, 110); pl("d2", "r3", 380, 220); pl("d2", "br2", 660, 220); pl("d2", "r4", 380, 360)
    pl("d3", "k1", 40, 40); pl("d3", "k2", 40, 200); pl("d3", "a1", 360, 120); pl("d3", "k3", 40, 360); pl("d3", "r4", 360, 360)
    ops.append({"op": "folder.lock", "args": {"id": idx["leg"], "reason": "Signed off by legal; ask before changing"}})
    s.apply(ops)
    return s


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    store = build(sys.argv[1])
    print("sample model written to %s\nrun:  python %s --file %s serve" % (
        store.path, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sg.py"), store.path))
