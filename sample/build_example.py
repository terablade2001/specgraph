#!/usr/bin/env python3
"""Builds the example model shown in the README, through the tool's own operations.

    python sample/build_example.py <empty-directory>

The example is a small library app ("borrow a book with your phone"): business and user
requirements, features, requirements, decisions, constraints, risks, an issue and tests,
linked from the business goal down to the tests. It adds one link type ("verifies") and
one coverage rule, has three diagrams that share elements, and one locked folder.

`specmodel.example.json` in the repository root is the output of this script. That file
is signed by a throwaway key, so the editor will not open it for you. This script builds
the same model in a new folder with the key loaded in your ssh-agent as administrator
"demo", so you can change it. Ids are random and differ on every run.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from specgraph.store import Store  # noqa: E402

FOLDERS = [  # ref, name, parent ref
    ("biz", "Business", None), ("usr", "Users", None), ("prod", "Product", None),
    ("chk", "Checkout", "prod"), ("rem", "Reminders", "prod"), ("ovd", "Overdue", "prod"),
    ("arch", "Architecture", None), ("ver", "Verification", None),
    ("comp", "Compliance (locked)", None),
]

ELEMENTS = [  # ref, stereotype, topic, folder ref, status, fields, notes
    ("b1", "B-REQ", "Halve the desk time spent on loans", "biz", "approved", {"priority": "Must", "owner": "Library board"},
     "Today a librarian spends about 40% of a shift scanning books in and out."),
    ("b2", "B-REQ", "Fewer than 5% of loans are returned late", "biz", "approved", {"priority": "Should"}, ""),
    ("u1", "U-REQ", "As a member I borrow a book with my phone", "usr", "approved", {"priority": "Must"},
     "No queue at the desk, also when the desk is closed."),
    ("u2", "U-REQ", "As a member I am reminded before a loan is due", "usr", "validated", {"priority": "Should"}, ""),
    ("u3", "U-REQ", "As a librarian I see overdue loans at a glance", "usr", "proposed", {"priority": "Could"}, ""),
    ("f1", "FEAT", "Self-service checkout", "chk", "implemented", {"owner": "Mobile team"}, ""),
    ("f2", "FEAT", "Due-date reminders", "rem", "approved", {"owner": "Backend team"}, ""),
    ("f3", "FEAT", "Overdue dashboard", "ovd", "proposed", {}, ""),
    ("r1", "REQ", "Scan the book barcode with the phone camera", "chk", "implemented", {"priority": "Must"}, ""),
    ("r2", "REQ", "A loan is recorded within 2 seconds", "chk", "validated", {"priority": "Must"},
     "Measured from the scan to the confirmation on the screen."),
    ("r3", "REQ", "Checkout works without network and syncs later", "chk", "approved", {"priority": "Should"},
     "The basement shelves have no reception."),
    ("r4", "REQ", "Send a reminder 3 days before the due date", "rem", "approved", {"priority": "Must"}, ""),
    ("r5", "REQ", "The member chooses the reminder channel", "rem", "proposed", {"priority": "Could"}, "E-mail, SMS or push."),
    ("r6", "REQ", "List overdue loans sorted by days late", "ovd", "proposed", {"priority": "Should"}, ""),
    ("c1", "CONSTRAINT", "Loan history is deleted 30 days after return", "comp", "approved", {"owner": "Data protection officer"},
     "Privacy rule. Do not change without the data protection officer."),
    ("c2", "CONSTRAINT", "Personal data stays in the EU", "comp", "approved", {"owner": "Data protection officer"}, ""),
    ("a1", "ADR", "Keep an offline queue of loans on the phone", "arch", "approved", {"decisionDate": "2026-09-14", "owner": "Mobile team"},
     "Loans made offline are queued and sent when the phone is online again. The server decides which loan wins."),
    ("a2", "ADR", "Send all reminders through one notification service", "arch", "approved", {"decisionDate": "2026-10-02"}, ""),
    ("a3", "ADR", "Store loans in PostgreSQL hosted in Frankfurt", "arch", "implemented", {"decisionDate": "2026-08-20"}, ""),
    ("t1", "TEMPORAL-ADR", "E-mail only until the SMS contract is signed", "arch", "approved", {"decisionDate": "2026-10-09"},
     "Temporary. Review when procurement closes the SMS contract."),
    ("k1", "RISK", "Two phones borrow the same copy while offline", "arch", "approved", {"severity": "High", "likelihood": "Medium"}, ""),
    ("k2", "RISK", "Reminders land in the spam folder", "arch", "proposed", {"severity": "Medium", "likelihood": "Medium"}, ""),
    ("i1", "ISSUE", "Camera fails on barcodes under glossy covers", "chk", "proposed", {"owner": "Mobile team"}, ""),
    ("e1", "TEST-E2E", "Borrow offline, reconnect, the loan appears", "ver", "implemented", {}, ""),
    ("e2", "TEST-E2E", "Reminder arrives 3 days before the due date", "ver", "approved", {}, ""),
    ("n1", "TEST-INT", "Loan API answers within 2 seconds under load", "ver", "implemented", {}, ""),
]

LINKS = [  # type, source ref, target ref
    ("refines", "u1", "b1"), ("refines", "u2", "b2"), ("refines", "u3", "b2"),
    ("refines", "f1", "u1"), ("refines", "f2", "u2"), ("refines", "f3", "u3"),
    ("refines", "r1", "f1"), ("refines", "r2", "f1"), ("refines", "r3", "f1"),
    ("refines", "r4", "f2"), ("refines", "r5", "f2"), ("refines", "r6", "f3"),
    ("depends_on", "r3", "r2"), ("depends_on", "r6", "c1"),
    ("implements", "a1", "r3"), ("implements", "a2", "r4"), ("implements", "a2", "r5"),
    ("implements", "a3", "r2"), ("implements", "a3", "c2"), ("implements", "t1", "r5"),
    ("mitigates", "a1", "k1"), ("mitigates", "a2", "k2"),
    ("relates_to", "i1", "r1"),
    ("verifies", "e1", "r3"), ("verifies", "e2", "r4"), ("verifies", "n1", "r2"),
]

DIAGRAMS = [  # ref, name, folder ref, [(element ref, x, y)]
    ("d1", "Checkout: from business goal to tests", "chk", [
        ("b1", 290, 20), ("u1", 290, 170), ("f1", 290, 320), ("n1", 40, 320), ("e1", 790, 320),
        ("r1", 40, 480), ("r2", 290, 480), ("r3", 540, 480),
        ("i1", 40, 650), ("a3", 290, 650), ("a1", 540, 650), ("k1", 790, 650)]),
    ("d2", "Reminders and overdue loans", "rem", [
        ("b2", 600, 20), ("u2", 415, 170), ("u3", 790, 170), ("f2", 415, 320), ("f3", 790, 320),
        ("e2", 40, 480), ("r4", 290, 480), ("r5", 540, 480), ("r6", 790, 480), ("c1", 1040, 480),
        ("k2", 40, 650), ("a2", 290, 650), ("t1", 540, 650)]),
    ("d3", "Decisions, what they implement and the risks", "arch", [
        ("k2", 40, 20), ("a2", 380, 20), ("r4", 720, 20), ("r5", 720, 150), ("t1", 380, 190),
        ("k1", 40, 360), ("a1", 380, 360), ("r3", 720, 330),
        ("a3", 380, 530), ("r2", 720, 460), ("c2", 720, 600)]),
]

VERIFIES = {"label": "verifies", "lineStyle": "dashed", "color": "#6d28d9", "sourceArrow": "none",
            "targetArrow": "open", "showLabel": True, "routing": "auto", "traceable": True,
            "sources": ["TEST-E2E", "TEST-INT"], "targets": None, "retired": False}
RULE = {"description": "An approved requirement is verified by a test", "stereotype": "REQ",
        "statuses": ["approved", "validated", "implemented"], "linkType": "verifies",
        "direction": "incoming", "other": None}


def build(target, key=None, user="demo"):
    os.makedirs(target, exist_ok=True)
    if not os.path.isdir(os.path.join(target, ".git")):
        subprocess.run(["git", "init", "-q", "-b", "docs/specifications"], cwd=target, check=True)
    s = Store(cwd=target, key=key)
    s.init(user)
    s.apply([{"op": "config.put", "args": {"kind": "linkTypes", "value": VERIFIES}}])   # key from the label: "verifies"
    s.apply([{"op": "config.put", "args": {"kind": "coverageRules", "value": RULE}}])
    prefixes = s.load()["config"]["stereotypes"]
    ops, idx, counts = [], {}, {}

    def add(ref, op, **args):
        if ref:
            idx[ref] = "$%d" % len(ops)
        ops.append({"op": op, "args": args})

    for ref, name, parent in FOLDERS:
        add(ref, "folder.create", name=name, parent=idx[parent] if parent else None)
    for ref, st, topic, folder, status, fields, notes in ELEMENTS:
        counts[st] = counts.get(st, 0) + 1   # readable numbered labels; new elements get short-id labels
        add(ref, "element.create", stereotype=st, topic=topic, folder=idx[folder], status=status, fields=fields,
            notes=notes, label="%s-%03d" % (prefixes[st]["labelPrefix"], counts[st]))
    for type_, a, b in LINKS:
        add(None, "link.create", type=type_, source=idx[a], target=idx[b])
    for ref, name, folder, nodes in DIAGRAMS:
        add(ref, "diagram.create", name=name, folder=idx[folder])
        for el, x, y in nodes:
            add(None, "diagram.place", diagram=idx[ref], element=idx[el], x=x, y=y)
    add(None, "folder.lock", id=idx["comp"], reason="Agreed with the data protection officer; ask before changing")
    s.apply(ops)
    return s


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    store = build(sys.argv[1])
    print("example model written to %s\nrun:  python %s --file %s serve" % (
        store.path, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sg.py"), store.path))
