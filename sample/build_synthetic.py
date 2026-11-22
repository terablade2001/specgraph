#!/usr/bin/env python3
"""Builds a large synthetic model for the agent evaluations (evals/), through the tool's own operations.

    python sample/build_synthetic.py <empty-directory> [--elements N] [--seed S]

The model is a made-up platform of city services. Each service has modules; each module has user
requirements, features, requirements, decisions, risks, tests and sometimes a constraint or an issue,
linked like a real project (refines, implements, mitigates, verifies, depends_on, relates_to).

Some facts are planted on purpose so that the right answer to an evaluation question is known
without anyone judging it:

- concepts written with many different words (authentication, payments, personal data), with a
  fixed number of elements each, whatever the size; no other element uses their words;
- near-duplicate requirement pairs, requirements without any link, cross-module dependencies,
  locked folders and diagrams.

Next to the model it writes `facts.json` (planted facts by element id). Same seed = same model: the
ids (and so the generated labels) come from the seed during the build, so a rebuild gives the same
questions and answers. Only the stamp signature and the change times differ.

Signing: the script makes a throwaway key in <directory>/.key and starts a private ssh-agent
for the build, so your own agent and keys are not touched. The model is owned by user "synth".
"""
import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from specgraph import model as M, ops as O, stamp as S  # noqa: E402
from specgraph.store import Store  # noqa: E402

SERVICES = [  # name, things it handles (plural), one thing
    ("Parking", "permits", "permit"), ("Waste collection", "pickups", "pickup"),
    ("Libraries", "loans", "loan"), ("Swimming pools", "lane bookings", "lane booking"),
    ("Street lighting", "lamp faults", "lamp fault"), ("Building control", "building applications", "building application"),
    ("Public transport", "route changes", "route change"), ("School enrolment", "enrolments", "enrolment"),
    ("Parks", "park events", "park event"), ("Water supply", "meter readings", "meter reading"),
    ("Road works", "road closures", "road closure"), ("Housing", "repair requests", "repair request"),
    ("Cemeteries", "plot reservations", "plot reservation"), ("Markets", "stall allocations", "stall allocation"),
    ("Animal control", "dog registrations", "dog registration"), ("Snow clearing", "gritting runs", "gritting run"),
    ("Sports halls", "hall bookings", "hall booking"), ("Tree care", "tree inspections", "tree inspection"),
    ("Noise control", "noise complaints", "noise complaint"), ("Bike sharing", "bike rentals", "bike rental"),
    ("Elder care", "home visits", "home visit"), ("Youth centres", "workshop sign-ups", "workshop sign-up"),
    ("Museums", "guided tours", "guided tour"), ("Recycling centres", "drop-off slots", "drop-off slot"),
    ("Flood defence", "pump checks", "pump check"),
]
ASPECTS = ["Requests", "Scheduling", "Reporting", "Field app", "Map view", "Inspections", "Inventory",
           "Complaints", "Staff planning", "Maintenance", "Statistics", "Kiosk", "Open data", "Audits",
           "Notices", "Work orders"]
ATTRS = ["date", "district", "status", "street", "team", "priority", "age", "type"]
TEAMS = ["Field team", "Back office", "Platform team", "Mobile team", "Data team", "Service desk"]
LEVELS = ["Low", "Medium", "High"]

GENERIC_REQ = [
    "{M}: show the list of {objs} sorted by {attr}",
    "{M}: export the {objs} as CSV",
    "{M}: a clerk assigns a {obj} to a team",
    "{M}: the map shows every {obj} within {n}00 metres",
    "{M}: {objs} are refreshed every {n} minutes",
    "{M}: the overview page opens within {n} seconds",
    "{M}: a supervisor approves a {obj} before it is published",
    "{M}: search {objs} by {attr}",
    "{M}: send a reminder {n} days before a {obj} is due",
    "{M}: a {obj} can be moved to another {attr}",
    "{M}: show how many {objs} are open per {attr}",
    "{M}: print a {obj} on one A4 page",
    "{M}: the field app works for {n} hours without network",
    "{M}: a {obj} keeps a history of every change",
    "{M}: staff add a photo to a {obj}",
    "{M}: a {obj} that waits more than {n} days is marked late",
    "{M}: group {objs} by {attr} in the weekly report",
    "{M}: the kiosk screen shows today's {objs}",
    "{M}: a clerk merges two {objs} into one",
    "{M}: {objs} can be filtered by {attr} and {attr2}",
]
GENERIC_NOTES = [
    "Agreed with the {T} in the last review.", "Needed before the spring season.",
    "The current spreadsheet is replaced by this.", "Keep the wording the clerks already use.",
    "Measured on the slowest supported tablet.", "Applies to all districts from the next release.",
]
GENERIC_UREQ = ["{M}: as a resident I see where my {obj} stands", "{M}: as a clerk I handle a {obj} in one screen",
                "{M}: as a supervisor I see which {objs} are late", "{M}: as field staff I record a {obj} on site"]
GENERIC_FEAT = ["{M} overview", "{M} editing", "{M} weekly report", "{M} field work", "{M} reminders"]
GENERIC_ADR = ["{M}: keep {objs} in the central database", "{M}: render the map tiles on the server",
               "{M}: sync the field app every {n} minutes", "{M}: one queue for all {objs}",
               "{M}: reuse the city design system", "{M}: build the report from nightly copies"]
GENERIC_RISK = ["{M}: the field app loses {objs} made offline", "{M}: reports are late at month end",
                "{M}: the map is unreadable on small phones", "{M}: two clerks change the same {obj}"]
GENERIC_TEST_E2E = ["{M}: create a {obj} and find it in the list", "{M}: a late {obj} is marked late",
                    "{M}: the weekly report counts every {obj}"]
GENERIC_TEST_INT = ["{M}: the {obj} interface answers within {n} seconds", "{M}: the nightly copy holds all {objs}"]
GENERIC_CON = ["{M}: works with the tablets bought in 2021", "{M}: no change to the district boundaries file"]
GENERIC_ISSUE = ["{M}: the list jumps to the top after saving", "{M}: dates show in the wrong format"]
GENERIC_BREQ = ["{S}: answer residents faster", "{S}: cut the paper work of the clerks in half"]

# Planted concepts: each is written in many ways; untagged text never uses these words.
CONCEPTS = {
    "authentication": {
        "count": 24,
        "words": r"\b(log ?in|logs in|sign(s|ed)? in|sign-on|password|credential|two-factor|identity provider|"
                 r"session token|authenticat\w*|account)",
        "REQ": ["{M}: staff log in with the city identity provider",
                "{M}: a resident signs in before sending a {obj}",
                "{M}: lock the account after {n} wrong passwords",
                "{M}: supervisors pass a two-factor check",
                "{M}: the session token expires after {n}0 minutes of inactivity",
                "{M}: single sign-on with the intranet",
                "{M}: credentials are never kept in the browser"],
        "ADR": ["{M}: use OpenID Connect against the identity provider"],
        "RISK": ["{M}: a stolen password opens resident records"],
        "TEST-E2E": ["{M}: signing in fails after the session token expires"],
        "notes": ["Clerks reach this only after they log in with their badge.",
                  "Residents must be signed in; anonymous use is refused."],
        # the concept without its usual words: only meaning finds these
        "hidden": ["{M}: only staff with a city badge reach the back office",
                   "{M}: the kiosk asks residents who they are before showing their {objs}",
                   "{M}: after {n} failed attempts the kiosk waits one minute",
                   "{M}: a resident proves who they are with the national e-ID app"],
        "hiddenWords": r"\b(badge|who they are|failed attempts|e-ID)\b",
    },
    "payments": {
        "count": 18,
        "words": r"\b(fee|fees|invoice\w*|refund\w*|billing|pay|pays|paid|payment\w*|charge[sd]?|card)\b",
        "REQ": ["{M}: the resident pays the {obj} fee online",
                "{M}: an invoice is created when a {obj} is approved",
                "{M}: refunds are made within {n} days",
                "{M}: a monthly billing report for the finance office",
                "{M}: the card is charged only after confirmation"],
        "ADR": ["{M}: use the national payment gateway"],
        "RISK": ["{M}: a refund is paid twice"],
        "TEST-INT": ["{M}: an approved {obj} creates exactly one invoice"],
        "notes": ["Residents pay a fee for this; the finance office sets the fee table every January."],
        "hidden": ["{M}: the resident gets the money back when a {obj} is cancelled",
                   "{M}: the kiosk takes coins and contactless",
                   "{M}: the price of a {obj} is shown before it is booked",
                   "{M}: the finance office sees what each {obj} brought in"],
        "hiddenWords": r"\b(money|coins|contactless|price|brought in)\b",
    },
    "personal data": {
        "count": 14,
        "words": r"\b(personal data|GDPR|anonymi[sz]\w*|retention|erase[sd]?|data held about|consent)\b",
        "REQ": ["{M}: personal data is erased {n}0 days after a {obj} is closed",
                "{M}: names are anonymised in the statistics",
                "{M}: a resident downloads all data held about them",
                "{M}: photos of residents follow the personal data retention rules",
                "{M}: follow the GDPR consent rules"],
        "CONSTRAINT": ["{M}: personal data never leaves the city data centre"],
        "notes": ["This stores residents' personal data; the data protection officer reviewed it."],
        "hidden": ["{M}: a resident downloads all the information the city keeps about them",
                   "{M}: the home address of a resident is hidden from other residents",
                   "{M}: a resident can have their records removed",
                   "{M}: residents' names never appear in the open data"],
        "hiddenWords": r"\b(information the city keeps|home address|records removed|names never appear)\b",
    },
}
ALL_CONCEPT_WORDS = re.compile("|".join("(%s)" % w for c in CONCEPTS.values()
                                          for w in (c["words"], c["hiddenWords"])), re.I)

VERIFIES = {"label": "verifies", "lineStyle": "dashed", "color": "#6d28d9", "sourceArrow": "none",
            "targetArrow": "open", "showLabel": True, "routing": "auto", "traceable": True,
            "sources": ["TEST-E2E", "TEST-INT"], "targets": None, "retired": False}
RULE = {"description": "An approved requirement is verified by a test", "stereotype": "REQ",
        "statuses": ["approved", "validated", "implemented"], "linkType": "verifies",
        "direction": "incoming", "other": None}
SYNONYMS = [  # rewording of a near-duplicate requirement: same meaning, other words
    ("show the list of", "list all"), ("export", "download"), ("a clerk", "a staff member"),
    ("a supervisor", "a team lead"), ("search", "look up"), ("are refreshed", "are updated"),
    ("opens within", "loads in under"), ("send a reminder", "remind the resident"), ("print", "fit"),
    ("keeps a history of every change", "records each change made to it"), ("staff add", "staff attach"),
    ("is marked late", "is flagged as overdue"), ("in the weekly report", "in the report of each week"),
    ("the kiosk screen shows", "the kiosk displays"), ("merges two", "combines two"),
    ("can be filtered by", "can be narrowed down by"), ("can be moved to", "can be transferred to"),
    ("show how many", "count the"), ("works for", "keeps working for"), ("the map shows", "the map displays"),
]
REQ_STATUS = (["proposed"] * 3 + ["approved"] * 4 + ["validated"] * 2 + ["implemented"] * 3
              + ["rejected", "deprecated"])
PER_MODULE = 24  # about this many elements per module


class Gen:
    def __init__(self, n_elements, seed):
        self.r = random.Random(seed)
        self.n = n_elements
        self.ops, self.refs = [], {}
        self.elements = []          # (ref, stereotype, module ref or None)
        self.topics, self.links = set(), set()
        self.facts = {"seed": seed, "elements": n_elements, "concepts": {k: [] for k in CONCEPTS},
                      "hidden": {k: [] for k in CONCEPTS}, "suffixed": 0,
                      "orphans": [], "duplicates": [], "crossModule": [], "modules": {}, "services": {},
                      "locked": [], "diagrams": []}

    # ---- operations with references --------------------------------------------------
    def add(self, op, ref=None, **args):
        if ref:
            self.refs[ref] = "$%d" % len(self.ops)
        self.ops.append({"op": op, "args": args})

    def fill(self, tpl, mod):
        n = self.r.randint(2, 9)
        a1, a2 = self.r.sample(ATTRS, 2)
        return tpl.format(M=mod["name"], S=mod.get("service", ""), obj=mod["obj"], objs=mod["objs"], n=n,
                          attr=a1, attr2=a2, T=self.r.choice(TEAMS).lower())

    def unique(self, text, remake=None):
        """A topic no other element has: other numbers/attributes of the template first, a suffix last."""
        for _ in range(30):
            if text not in self.topics or remake is None:
                break
            text = remake()
        base, k = text, 2
        while text in self.topics:
            text, k = "%s (%d)" % (base, k), k + 1
            self.facts["suffixed"] += 1
        self.topics.add(text)
        return text

    def element(self, ref, st, mod, folder_ref, topic, status, fields=None, notes="", concept=None,
                remake=None, hidden=False):
        topic = self.unique(topic, remake)
        if concept is None:
            assert not ALL_CONCEPT_WORDS.search(topic + " " + notes), topic + " / " + notes
        self.add("element.create", ref, stereotype=st, topic=topic, folder=self.refs[folder_ref],
                 status=status, fields=fields or {}, notes=notes)
        self.elements.append((ref, st, mod["ref"] if mod else None))
        if concept:
            self.facts["concepts"][concept].append(ref)
            if hidden:
                self.facts["hidden"][concept].append(ref)
        return ref

    def link(self, type_, a, b):
        """Create a link once; returns False when the same link exists already."""
        sig = (type_, a, b)
        if sig in self.links or a == b:
            return False
        self.links.add(sig)
        self.add("link.create", None, type=type_, source=self.refs[a], target=self.refs[b])
        return True

    # ---- the model ---------------------------------------------------------------------
    def build_ops(self):
        r = self.r
        n_modules = max(2, self.n // PER_MODULE)
        modules = []
        services = []
        for si, (sname, objs, obj) in enumerate(SERVICES):
            services.append({"ref": "s%d" % si, "name": sname, "objs": objs, "obj": obj})
        for k in range(n_modules):
            s = services[k % len(services)]
            aspect = ASPECTS[(k // len(services)) % len(ASPECTS)]
            rnd = k // (len(services) * len(ASPECTS))
            name = "%s %s" % (s["name"], aspect) + (" %d" % (rnd + 1) if rnd else "")
            modules.append({"ref": "m%d" % k, "name": name, "service": s["name"], "sref": s["ref"],
                            "objs": s["objs"], "obj": s["obj"]})
        used_services = sorted({m["sref"] for m in modules}, key=lambda x: int(x[1:]))
        services = [s for s in services if s["ref"] in used_services]

        # concept placement: (module index, stereotype or "notes") slots chosen up front
        slots = {}
        for cname, c in CONCEPTS.items():
            kinds = [k for k in ("REQ", "ADR", "RISK", "TEST-E2E", "TEST-INT", "CONSTRAINT") if k in c]
            for i in range(c["count"]):
                kind = "notes" if i % 6 == 5 else kinds[i % len(kinds)] if i % 3 == 2 else "REQ"
                if kind == "REQ" and i % 4 in (1, 2):
                    kind = "hidden"
                mi = r.randrange(n_modules)
                for _ in range(50):          # one plant of a concept and kind per module, so wordings do not repeat
                    if (cname, kind) not in slots.get(mi, []):
                        break
                    mi = r.randrange(n_modules)
                slots.setdefault(mi, []).append((cname, kind))

        for s in services:
            self.add("folder.create", s["ref"], name=s["name"], parent=None)
            self.facts["services"][s["ref"]] = s["name"]
            for j, tpl in enumerate(GENERIC_BREQ):
                self.element("%s_b%d" % (s["ref"], j), "B-REQ", None, s["ref"],
                             tpl.format(S=s["name"]), r.choice(["approved", "approved", "proposed"]),
                             {"priority": r.choice(["Must", "Should"])})

        reqs_by_module = {}
        for mi, mod in enumerate(modules):
            m = mod["ref"]
            self.add("folder.create", m, name=mod["name"], parent=self.refs[mod["sref"]])
            self.facts["modules"][m] = mod["name"]
            todo = list(slots.get(mi, []))

            def concept_for(kind):
                for i, (cname, ck) in enumerate(todo):
                    if ck == kind:
                        todo.pop(i)
                        return cname
                return None

            def text(kind, generic, concept, tpl=None):
                """(topic, remake). A remake varies numbers and attributes; for a concept it may also take
                another wording of the same concept."""
                if concept:
                    pool = CONCEPTS[concept][kind]
                    return self.fill(r.choice(pool), mod), lambda: self.fill(r.choice(pool), mod)
                tpl = tpl or r.choice(generic)
                return self.fill(tpl, mod), lambda: self.fill(tpl, mod)

            ureqs, feats, reqs = [], [], []
            for j in range(2):
                ureqs.append(self.element("%s_u%d" % (m, j), "U-REQ", mod, m, self.fill(GENERIC_UREQ[j * 2 + r.randrange(2)], mod),
                                          r.choice(["approved", "validated", "proposed"]), {"priority": r.choice(["Must", "Should", "Could"])}))
                self.link("refines", ureqs[-1], "%s_b%d" % (mod["sref"], r.randrange(2)))
            for j in range(2):
                feats.append(self.element("%s_f%d" % (m, j), "FEAT", mod, m, self.fill(GENERIC_FEAT[(j + mi) % len(GENERIC_FEAT)], mod),
                                          r.choice(["approved", "implemented", "proposed"]), {"owner": r.choice(TEAMS)}))
                self.link("refines", feats[-1], ureqs[j])
            req_tpls = r.sample(GENERIC_REQ, 10)
            for j in range(10):
                c = concept_for("REQ")
                hid = None if c else concept_for("hidden")
                notes_c = None if c or hid else concept_for("notes")
                notes = r.choice(CONCEPTS[notes_c]["notes"]) if notes_c else (
                    self.fill(r.choice(GENERIC_NOTES), mod) if r.random() < 0.4 else "")
                if hid:
                    topic, remake = text("hidden", None, hid)
                else:
                    topic, remake = text("REQ", None, c, req_tpls[j])
                ref = self.element("%s_r%d" % (m, j), "REQ", mod, m, topic,
                                   r.choice(REQ_STATUS), {"priority": r.choice(["Must", "Should", "Could"]),
                                                          "owner": r.choice(TEAMS)}, notes, c or hid or notes_c,
                                   remake, hidden=bool(hid))
                reqs.append(ref)
                self.link("refines", ref, feats[j % 2])
            reqs_by_module[m] = reqs
            adr_tpls, risk_tpls = r.sample(GENERIC_ADR, 3), r.sample(GENERIC_RISK, 2)
            for j in range(3):
                c = concept_for("ADR")
                topic, remake = text("ADR", None, c, adr_tpls[j])
                ref = self.element("%s_a%d" % (m, j), "ADR", mod, m, topic,
                                   r.choice(["approved", "implemented", "proposed"]), {"owner": r.choice(TEAMS)},
                                   concept=c, remake=remake)
                for t in r.sample(reqs, r.randint(1, 3)):
                    self.link("implements", ref, t)
                if j < 2:
                    cr = concept_for("RISK")
                    topic, remake = text("RISK", None, cr, risk_tpls[j])
                    risk = self.element("%s_k%d" % (m, j), "RISK", mod, m, topic,
                                        r.choice(["approved", "proposed"]),
                                        {"severity": r.choice(LEVELS), "likelihood": r.choice(LEVELS)}, concept=cr,
                                        remake=remake)
                    self.link("mitigates", ref, risk)
            tested = r.sample(reqs, 6)
            e2e_tpls = r.sample(GENERIC_TEST_E2E, 3)
            for j in range(4):
                st = "TEST-E2E" if j < 3 else "TEST-INT"
                c = concept_for(st)
                topic, remake = text(st, GENERIC_TEST_INT, c, e2e_tpls[j] if j < 3 else None)
                ref = self.element("%s_t%d" % (m, j), st, mod, m, topic,
                                   r.choice(["implemented", "approved"]), {"owner": r.choice(TEAMS)}, concept=c,
                                   remake=remake)
                for t in tested[j::4] or tested[:1]:
                    self.link("verifies", ref, t)
            for j in range(3):
                a, b = r.sample(reqs, 2)
                self.link("depends_on", a, b)
            c = concept_for("CONSTRAINT")
            if c or r.random() < 0.4:
                topic, remake = text("CONSTRAINT", GENERIC_CON, c)
                ref = self.element("%s_c0" % m, "CONSTRAINT", mod, m, topic,
                                   "approved", {"owner": r.choice(TEAMS)}, concept=c, remake=remake)
                self.link("depends_on", r.choice(reqs), ref)
            if r.random() < 0.4:
                ref = self.element("%s_i0" % m, "ISSUE", mod, m, self.fill(r.choice(GENERIC_ISSUE), mod),
                                   "proposed", {"owner": r.choice(TEAMS)})
                self.link("relates_to", ref, r.choice(reqs))
            for cname, kind in todo:  # a concept slot whose kind did not occur: plant it as a REQ
                hid = kind == "hidden"
                topic, remake = text("hidden" if hid else "REQ", None, cname)
                ref = self.element("%s_x%d" % (m, len(self.elements)), "REQ", mod, m, topic, r.choice(REQ_STATUS),
                                   {"priority": "Should"}, concept=cname, remake=remake, hidden=hid)
                self.link("refines", ref, feats[0])

        # cross-module dependencies (REQ depends_on a REQ of another module)
        mrefs = list(reqs_by_module)
        for _ in range(max(3, n_modules // 4)):
            a_m, b_m = r.sample(mrefs, 2)
            a, b = r.choice(reqs_by_module[a_m]), r.choice(reqs_by_module[b_m])
            if self.link("depends_on", a, b):
                self.facts["crossModule"].append([a, b])
        # requirements with no link at all
        for k in range(min(8, max(2, n_modules // 10))):
            mod = modules[r.randrange(n_modules)]
            tpl = r.choice(GENERIC_REQ)
            ref = self.element("orphan%d" % k, "REQ", mod, mod["ref"], self.fill(tpl, mod),
                               r.choice(REQ_STATUS), {"priority": "Could"}, remake=lambda: self.fill(r.choice(GENERIC_REQ), mod))
            self.facts["orphans"].append(ref)
        # near-duplicate pairs: same module text, written a second time a little differently
        tagged = {x for refs in self.facts["concepts"].values() for x in refs}
        plain = [mi for mi, mod in enumerate(modules) if any(x not in tagged for x in reqs_by_module[mod["ref"]])]
        for k in range(min(10, max(3, n_modules // 20)) if plain else 0):  # a tiny model may have no plain REQ
            mi = r.choice(plain)
            mod = modules[mi]
            src = r.choice([x for x in reqs_by_module[mod["ref"]] if x not in tagged])
            other = modules[(mi + 1 + r.randrange(n_modules - 1)) % n_modules]
            self.facts["duplicates"].append([src, "dup%d" % k, other["ref"], mod["ref"]])
        return modules

    def duplicates_ops(self, model, ids):
        """Second pass: duplicates copy the topic of an existing element (now known)."""
        ops = []
        for src, dref, other_m, mod_m in self.facts["duplicates"]:
            topic = model["elements"][ids[src]]["topic"]
            head, tail = topic.split(":", 1)
            tail = " " + tail.strip()
            for old, new in SYNONYMS:
                tail = tail.replace(" " + old, " " + new, 1)
            dup = "%s:%s" % (head, tail)
            if dup == topic:
                dup = topic + ", for every district"
            ops.append({"op": "element.create", "args": {
                "stereotype": "REQ", "topic": dup, "folder": ids[other_m], "status": "proposed",
                "fields": {"priority": "Should"}, "notes": ""}})
        return ops


@contextmanager
def seeded_ids(seed):
    """During the build, new ids come from the seed instead of uuid4 (and are restored after)."""
    rng = random.Random("ids-%d" % seed)
    saved = (M.new_id, O.new_id, S.new_id)
    fake = lambda: str(uuid.UUID(int=rng.getrandbits(128), version=4))
    M.new_id = O.new_id = S.new_id = fake
    try:
        yield
    finally:
        M.new_id, O.new_id, S.new_id = saved


def private_agent(target):
    """A throwaway key in <target>/.key, loaded in a private ssh-agent. Returns (pubkey path, stop)."""
    keygen = os.environ.get("SPECGRAPH_SSH_KEYGEN") or shutil.which("ssh-keygen")
    agent = shutil.which("ssh-agent") or os.path.join(os.path.dirname(keygen), "ssh-agent")
    add = shutil.which("ssh-add") or os.path.join(os.path.dirname(keygen), "ssh-add")
    kdir = os.path.join(target, ".key")
    os.makedirs(kdir, exist_ok=True)
    with open(os.path.join(kdir, ".gitignore"), "w") as fh:
        fh.write("*\n")
    key = os.path.join(kdir, "synth")
    if not os.path.exists(key):
        subprocess.run([keygen, "-t", "ed25519", "-N", "", "-f", key, "-C", "synth", "-q"], check=True)
    p = subprocess.run([agent, "-s"], capture_output=True, text=True)
    sock = re.search(r"SSH_AUTH_SOCK=([^;]+);", p.stdout).group(1)
    pid = re.search(r"SSH_AGENT_PID=(\d+);", p.stdout)
    old = {k: os.environ.get(k) for k in ("SSH_AUTH_SOCK", "SSH_AGENT_PID", "SPECGRAPH_SSH_ADD")}
    os.environ["SSH_AUTH_SOCK"] = sock
    if pid:
        os.environ["SSH_AGENT_PID"] = pid.group(1)
    os.environ["SPECGRAPH_SSH_ADD"] = add
    subprocess.run([add, key], check=True, capture_output=True)

    def stop():
        subprocess.run([agent, "-k"], capture_output=True, env=dict(os.environ))
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return key + ".pub", stop


def build(target, n_elements=1000, seed=1, key=None, batch=4000):
    os.makedirs(target, exist_ok=True)
    if not os.path.isdir(os.path.join(target, ".git")):
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=target, check=True)
    stop = None
    if key is None:
        key, stop = private_agent(target)
    try:
        with seeded_ids(seed):
            return _build(target, n_elements, seed, key, batch)
    finally:
        if stop:
            stop()


def _build(target, n_elements, seed, key, batch):
    t0 = time.time()
    s = Store(cwd=target, key=key)
    s.init("synth")
    s.apply([{"op": "config.put", "args": {"kind": "linkTypes", "value": VERIFIES}}])
    s.apply([{"op": "config.put", "args": {"kind": "coverageRules", "value": RULE}}])
    g = Gen(n_elements, seed)
    modules = g.build_ops()
    # apply in batches; "$N" refers within a batch, so resolve earlier refs to real ids
    ids, ops = {}, g.ops
    by_index = {int(v[1:]): k for k, v in g.refs.items()}
    start = 0
    while start < len(ops):
        end = min(len(ops), start + batch)
        chunk = []
        for i in range(start, end):
            o = json.loads(json.dumps(ops[i]))

            def res(v):
                if isinstance(v, str) and re.match(r"^\$\d+$", v):
                    j = int(v[1:])
                    return ids[by_index[j]] if j < start else "$%d" % (j - start)
                return v
            o["args"] = {k: res(v) for k, v in o["args"].items()}
            chunk.append(o)
        _, results = s.apply(chunk)
        for i in range(start, end):
            if i in by_index:
                ids[by_index[i]] = results[i - start]
        start = end
    model = s.load()
    dup_ops = g.duplicates_ops(model, ids)
    if dup_ops:
        _, results = s.apply(dup_ops)
        for (src, dref, _, _), new in zip(g.facts["duplicates"], results):
            ids[dref] = new
    # diagrams: every fourth module, its elements in a grid
    dops, placed = [], []
    mod_elements = {}
    for ref, st, m in g.elements:
        if m:
            mod_elements.setdefault(m, []).append(ref)
    for k, mod in enumerate(modules):
        if k % 4:
            continue
        dops.append({"op": "diagram.create", "args": {"name": mod["name"] + " overview", "folder": ids[mod["ref"]]}})
        di = len(dops) - 1
        for j, ref in enumerate(mod_elements.get(mod["ref"], [])[:16]):
            dops.append({"op": "diagram.place", "args": {"diagram": "$%d" % di, "element": ids[ref],
                                                         "x": 40 + (j % 4) * 260, "y": 40 + (j // 4) * 160}})
        placed.append((di, mod["name"] + " overview"))
    lock_mods = [modules[i] for i in sorted(g.r.sample(range(len(modules)), min(3, len(modules))))]
    for mod in lock_mods:
        dops.append({"op": "folder.lock", "args": {"id": ids[mod["ref"]], "reason": "Being reworked"}})
    _, results = s.apply(dops)
    g.facts["diagrams"] = [{"id": results[di], "name": name} for di, name in placed]
    g.facts["locked"] = [ids[mod["ref"]] for mod in lock_mods]

    # facts by real id
    f = g.facts
    out = {"seed": f["seed"], "elements": f["elements"],
           "concepts": {k: [ids[x] for x in v] for k, v in f["concepts"].items()},
           "hidden": {k: [ids[x] for x in v] for k, v in f["hidden"].items()},
           "suffixed": f["suffixed"],
           "orphans": [ids[x] for x in f["orphans"]],
           "duplicates": [[ids[a], ids[b]] for a, b, _, _ in f["duplicates"]],
           "crossModule": [[ids[a], ids[b]] for a, b in f["crossModule"]],
           "modules": {ids[k]: v for k, v in f["modules"].items()},
           "services": {ids[k]: v for k, v in f["services"].items()},
           "locked": f["locked"], "diagrams": f["diagrams"],
           "buildSeconds": round(time.time() - t0, 1)}
    with open(os.path.join(target, "facts.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
        fh.write("\n")
    return s, out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target")
    ap.add_argument("--elements", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    store, facts = build(a.target, a.elements, a.seed)
    m = store.load()
    print("%s: %d elements, %d links, %d folders, %d diagrams, %.1f s" % (
        store.path, len(m["elements"]), len(m["links"]), len(m["folders"]), len(m["diagrams"]), facts["buildSeconds"]))
