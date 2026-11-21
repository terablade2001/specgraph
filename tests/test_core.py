"""Elements, folders, diagrams, links, configuration, search, traceability."""
import json
import os

import pytest

from specgraph import model as M, query as Q, validate as V
from specgraph.store import StoreError
from conftest import do


@pytest.fixture
def base(ada):
    """A small model: folder F with REQ r1, r2, ADR a1, RISK k1 and two diagrams."""
    ids = {}
    ids["F"] = do(ada, "folder.create", name="Billing")
    ids["r1"] = do(ada, "element.create", stereotype="REQ", topic="Invoices are numbered", folder=ids["F"])
    ids["r2"] = do(ada, "element.create", stereotype="REQ", topic="Numbers have no gaps", folder=ids["F"],
                   notes="Legal requirement in Greece")
    ids["a1"] = do(ada, "element.create", stereotype="ADR", topic="Use a DB sequence", folder=ids["F"])
    ids["k1"] = do(ada, "element.create", stereotype="RISK", topic="Sequence gaps on rollback", folder=ids["F"])
    ids["d1"] = do(ada, "diagram.create", name="Overview", folder=ids["F"])
    ids["d2"] = do(ada, "diagram.create", name="Detail", folder=ids["F"])
    return ids


# --- storage ---------------------------------------------------------------

def test_sto01_02_single_file_and_no_per_item_files(ada, base, repo):
    """REQ-STO-01/02: one JSON file; organizing changes content only."""
    before = sorted(p for p in os.listdir(repo) if p != ".git")
    g = do(ada, "folder.create", name="Archive")
    do(ada, "element.move", id=base["r1"], folder=g)
    do(ada, "folder.move", id=g, parent=base["F"])
    assert sorted(p for p in os.listdir(repo) if p != ".git") == before == ["specmodel.json"]
    assert ada.load()["elements"][base["r1"]]["folder"] == g


def test_sto03_stable_serialization_and_small_diff(ada, base):
    """REQ-STO-03: unchanged model serializes identically; one field = small diff."""
    text1 = open(ada.path, encoding="utf-8").read()
    assert M.canonical(json.loads(text1)) == text1
    M.save(ada.path, M.load(ada.path))
    assert open(ada.path, encoding="utf-8").read() == text1
    do(ada, "element.update", id=base["r1"], status="approved")
    text2 = open(ada.path, encoding="utf-8").read()
    changed = [l for l in text2.splitlines() if l not in text1.splitlines()]
    body = [l for l in changed if '"status"' in l]
    stamp = [l for l in changed if l not in body]
    assert len(body) == 1 and len(stamp) <= 8  # the field + the stamp's own lines + the element's modified.at (ADR-016)


def test_sto07_no_silent_overwrite_of_outside_change(ada, bob, base):
    """REQ-STO-07: a session holding an old view is told to reload, not overwritten."""
    seen = ada.load()["stamp"]["id"]
    do(bob, "element.update", id=base["r2"], topic="Changed by Bob meanwhile")
    with pytest.raises(StoreError) as e:
        ada.apply([{"op": "element.update", "args": {"id": base["r2"], "topic": "Ada"}}], base=seen)
    assert e.value.code == "stale"
    assert ada.load()["elements"][base["r2"]]["topic"] == "Changed by Bob meanwhile"


def test_sto05_the_tool_works_on_any_branch(ada, base, repo):
    """REQ-STO-05 (ADR-024): no branch rule; a `settings.branch` written by version 0.1 is ignored."""
    from conftest import git, commit
    from specgraph import audit as A, ops as O, stamp as S
    assert ada.load()["settings"] == {}
    commit(repo)
    git(repo, "switch", "-q", "-c", "feature/x")
    do(ada, "folder.create", name="X")
    m = ada.load()
    m["settings"]["branch"] = "docs/specifications"          # a model made by version 0.1
    S.make_stamp(m, "ada", ada.key(), "old tool", [m["stamp"]["id"]])
    M.save(ada.path, m)
    do(ada, "folder.create", name="Y")
    assert not V.errors(ada.load()) and "branch" not in ada.state() and "settings.put" not in O.OPS
    git(repo, "add", "-A")
    assert A.check_staged(ada)[0] == []                       # the commit check has no branch finding either


# --- elements --------------------------------------------------------------

def test_elm01_02_04_element_fields_id_and_label(ada, base):
    """REQ-ELM-01/02/04: stereotype, topic, notes, status, auto id, unique label."""
    m = ada.load()
    el = m["elements"][base["r1"]]
    assert {"stereotype", "topic", "notes", "status", "fields", "label", "folder"} <= set(el)
    assert len(base["r1"]) == 36 and len({base[k] for k in ("r1", "r2", "a1", "k1")}) == 4
    short = lambda eid: eid.replace("-", "")[:8]  # ADR-023: the label is the type prefix plus the first 8 id characters
    assert el["label"] == "REQ-" + short(base["r1"]) and m["elements"][base["r2"]]["label"] == "REQ-" + short(base["r2"])
    with pytest.raises(StoreError):
        do(ada, "element.update", id=base["r2"], label=el["label"])
    do(ada, "element.update", id=base["r2"], label="REQ-013")
    assert base["r2"] in ada.load()["elements"]  # id never changes


def test_elm02_label_grows_when_the_short_id_is_taken():
    """ADR-023: a clash of the first 8 id characters is resolved by taking more characters."""
    from specgraph import ops as O
    eid = "3d6e7863-98c3-4dce-8141-c844f7bb20eb"
    m = {"config": {"stereotypes": {"REQ": {"labelPrefix": "REQ"}, "X": {"labelPrefix": ""}}},
         "elements": {"a": {"label": "REQ-3d6e7863"}}}
    assert O._auto_label(m, "REQ", eid) == "REQ-3d6e78639"
    assert O._auto_label({"config": m["config"], "elements": {}}, "REQ", eid) == "REQ-3d6e7863"
    assert O._auto_label(m, "X", eid) == ""



def test_elm07_type_change_gives_a_new_label(ada, base):
    """REQ-ELM-07 (ADR-026): changing the type replaces the label by a generated one for the new type,
    also a hand-typed one; a label passed in the same change wins."""
    short = base["a1"].replace("-", "")[:8]
    label = lambda: ada.load()["elements"][base["a1"]]["label"]
    assert label() == "ADR-" + short
    do(ada, "element.update", id=base["a1"], stereotype="REQ")
    assert label() == "REQ-" + short
    do(ada, "element.update", id=base["a1"], stereotype="ADR")          # back again: its own old label is free
    assert label() == "ADR-" + short
    do(ada, "element.update", id=base["a1"], label="ADR-001")
    do(ada, "element.update", id=base["a1"], stereotype="RISK")
    assert label() == "RISK-" + short
    do(ada, "element.update", id=base["a1"], stereotype="REQ", label="REQ-777")
    assert label() == "REQ-777"
    do(ada, "element.update", id=base["a1"], topic="Same type, other topic")
    assert label() == "REQ-777"                                           # no type change: the label stays

def test_elm03_ids_unique_across_parallel_creation():
    """REQ-ELM-03: random 122-bit ids need no coordination."""
    assert len({M.new_id() for _ in range(20000)}) == 20000


def test_elm05_dgm03_one_element_many_diagrams(ada, base):
    """REQ-ELM-05, REQ-DGM-01/03: element exists once; each diagram has its own layout."""
    do(ada, "diagram.place", diagram=base["d1"], element=base["r1"], x=10, y=10)
    do(ada, "diagram.place", diagram=base["d2"], element=base["r1"], x=300, y=200, w=220, h=120)
    do(ada, "element.update", id=base["r1"], topic="Invoices carry a number")
    m = ada.load()
    assert m["diagrams"][base["d1"]]["nodes"][base["r1"]]["x"] == 10
    assert m["diagrams"][base["d2"]]["nodes"][base["r1"]] == {"x": 300, "y": 200, "w": 220, "h": 120}
    assert "topic" not in m["diagrams"][base["d1"]]["nodes"][base["r1"]]
    assert m["elements"][base["r1"]]["topic"] == "Invoices carry a number"


def test_elm06_remove_from_diagram_vs_delete(ada, base):
    """REQ-ELM-06: removing from a diagram keeps the element; delete shows usage and cascades."""
    do(ada, "diagram.place", diagram=base["d1"], element=base["r1"], x=0, y=0)
    do(ada, "diagram.place", diagram=base["d2"], element=base["r1"], x=0, y=0)
    lid = do(ada, "link.create", type="implements", source=base["a1"], target=base["r1"])
    do(ada, "diagram.remove", diagram=base["d1"], element=base["r1"])
    m = ada.load()
    assert base["r1"] in m["elements"] and base["r1"] not in m["diagrams"][base["d1"]]["nodes"]
    use = Q.usage(m, base["r1"])
    assert [d["name"] for d in use["diagrams"]] == ["Detail"] and use["links"][0]["id"] == lid
    do(ada, "element.delete", id=base["r1"])
    m = ada.load()
    assert base["r1"] not in m["elements"] and lid not in m["links"]
    assert base["r1"] not in m["diagrams"][base["d2"]]["nodes"] and not V.errors(m)


def test_cli_delete_requires_confirmation(ada, base, capsys, monkeypatch, only_key):
    """REQ-ELM-06 for agents: element.delete without --yes shows usage and changes nothing."""
    from specgraph.cli import main
    only_key(ada.key())
    ops = json.dumps([{"op": "element.delete", "args": {"id": base["r1"]}}])
    assert main(["--file", ada.path, "apply", ops]) == 3
    assert "usage" in capsys.readouterr().out and base["r1"] in ada.load()["elements"]
    assert main(["--file", ada.path, "apply", ops, "--yes"]) == 0
    assert base["r1"] not in ada.load()["elements"]


# --- folders ---------------------------------------------------------------

def test_fld01_02_folder_tree(ada, base):
    """REQ-FLD-01/02: create, rename, move folders; move elements and diagrams."""
    sub = do(ada, "folder.create", name="Sub", parent=base["F"])
    do(ada, "folder.update", id=sub, name="Numbering")
    do(ada, "element.move", id=base["r1"], folder=sub)
    do(ada, "diagram.move", id=base["d1"], folder=sub)
    m = ada.load()
    assert Q.folder_path(m, m["elements"][base["r1"]]["folder"]) == "Billing/Numbering"
    with pytest.raises(StoreError):
        do(ada, "folder.move", id=base["F"], parent=sub)  # no cycles
    with pytest.raises(StoreError):
        do(ada, "folder.delete", id=sub)  # not empty
    do(ada, "folder.move", id=sub, parent=None)
    assert ada.load()["folders"][sub]["parent"] is None


# --- links and diagrams ----------------------------------------------------

def test_lnk01_02_03_typed_links_in_model(ada, base):
    """REQ-LNK-01/02/03: typed, owned by the model; stereotype limits only where the user sets them."""
    lid = do(ada, "link.create", type="implements", source=base["a1"], target=base["r1"])
    m = ada.load()
    assert m["links"][lid]["type"] == "implements"
    assert all(lid not in d["links"] for d in m["diagrams"].values())
    with pytest.raises(StoreError):
        do(ada, "link.create", type="implements", source=base["a1"], target=base["r1"])  # duplicate
    assert all(t["sources"] is None and t["targets"] is None for t in m["config"]["linkTypes"].values())  # no default limits
    rid = do(ada, "link.create", type="implements", source=base["r1"], target=base["a1"])  # any pair is fine by default
    do(ada, "link.delete", id=rid)
    do(ada, "config.put", kind="linkTypes", key="implements", value={"sources": ["ADR"], "targets": ["REQ"]})  # the user's own limit
    with pytest.raises(StoreError):
        do(ada, "link.create", type="implements", source=base["r1"], target=base["a1"])  # REQ can't implement
    with pytest.raises(StoreError):
        do(ada, "link.create", type="nonsense", source=base["a1"], target=base["r1"])


def test_dgm04_routing_per_diagram(ada, base):
    """REQ-DGM-04: straight / auto / user-defined, overridable per diagram."""
    lid = do(ada, "link.create", type="depends_on", source=base["r2"], target=base["r1"])
    for d in ("d1", "d2"):
        do(ada, "diagram.place", diagram=base[d], element=base["r1"], x=0, y=0)
        do(ada, "diagram.place", diagram=base[d], element=base["r2"], x=300, y=0)
    do(ada, "diagram.link", diagram=base["d1"], link=lid, routing="custom", points=[[150, 80], [200, 80]])
    do(ada, "diagram.link", diagram=base["d2"], link=lid, routing="straight")
    m = ada.load()
    assert m["diagrams"][base["d1"]]["links"][lid] == {"routing": "custom", "points": [[150, 80], [200, 80]]}
    assert m["diagrams"][base["d2"]]["links"][lid] == {"routing": "straight"}
    assert m["config"]["linkTypes"]["depends_on"]["routing"] == "auto"  # the default
    do(ada, "diagram.link", diagram=base["d1"], link=lid, reset=True)
    assert lid not in ada.load()["diagrams"][base["d1"]]["links"]
    with pytest.raises(StoreError):
        do(ada, "diagram.link", diagram=base["d1"], link=lid, routing="wavy")


# --- configuration ---------------------------------------------------------

def test_cfg01_new_entries_without_code(ada, base):
    """REQ-CFG-01/02/03/05: add stereotype, status and link type through the tool."""
    st = do(ada, "config.put", kind="stereotypes", value={"label": "Test case", "fill": "#eeeeff",
            "border": "#333399", "icon": "T", "shape": "rect"})
    s = do(ada, "config.put", kind="statuses", value={"label": "On hold", "color": "#aa8800", "symbol": "~"})
    lt = do(ada, "config.put", kind="linkTypes", value={"label": "verifies", "lineStyle": "dotted",
            "color": "#333399", "sourceArrow": "none", "targetArrow": "triangle", "showLabel": True,
            "routing": "straight", "sources": [st], "targets": ["REQ"]})
    t = do(ada, "element.create", stereotype=st, topic="Numbering test", folder=base["F"], status=s)
    do(ada, "link.create", type=lt, source=t, target=base["r1"])
    cfg = ada.load()["config"]
    assert V.traceable(cfg["linkTypes"][lt])  # REQ-TRC-02: omitted = yes
    assert not V.errors(ada.load())
    with pytest.raises(StoreError):
        do(ada, "config.put", kind="statuses", value={"label": "Bad", "color": "red"})


def test_cfg04_custom_fields_validated(ada, base):
    """REQ-CFG-04: typed custom fields per stereotype."""
    do(ada, "element.update", id=base["r1"], fields={"priority": "Must", "owner": "Ann"})
    assert ada.load()["elements"][base["r1"]]["fields"] == {"priority": "Must", "owner": "Ann"}
    for bad in ({"priority": "Maybe"}, {"nope": 1}, {"owner": 5}):
        with pytest.raises(StoreError):
            do(ada, "element.update", id=base["r1"], fields=bad)
    with pytest.raises(StoreError):  # dropping a field definition that elements still use is refused
        do(ada, "config.put", kind="stereotypes", key="REQ", value={"fields": {}})
    fields = dict(ada.load()["config"]["stereotypes"]["REQ"]["fields"])
    fields.update({"effort": {"label": "Effort (days)", "type": "number"}, "due": {"label": "Due", "type": "date"}})
    do(ada, "config.put", kind="stereotypes", key="REQ", value={"fields": fields})
    do(ada, "element.update", id=base["r2"], fields={"effort": 3.5, "due": "2026-12-01"})
    with pytest.raises(StoreError):
        do(ada, "element.update", id=base["r2"], fields={"due": "tomorrow"})


def test_cfg03_statuses_per_stereotype(ada, base):
    """REQ-CFG-03: which statuses a stereotype allows is configurable."""
    do(ada, "config.put", kind="stereotypes", key="RISK", value={"statuses": ["proposed", "approved"]})
    do(ada, "element.update", id=base["k1"], status="approved")
    with pytest.raises(StoreError):
        do(ada, "element.update", id=base["k1"], status="implemented")


def test_cfg06_rename_label_keeps_data(ada, base):
    """REQ-CFG-06: data refers to stable keys, not display labels."""
    do(ada, "config.put", kind="stereotypes", key="REQ", value={"label": "Requirement"})
    do(ada, "config.put", kind="statuses", key="proposed", value={"label": "Draft"})
    m = ada.load()
    assert m["elements"][base["r1"]]["stereotype"] == "REQ" and not V.errors(m)


def test_cfg07_in_use_not_deletable_but_retirable(ada, base):
    """REQ-CFG-07."""
    with pytest.raises(StoreError):
        do(ada, "config.delete", kind="stereotypes", key="REQ")
    do(ada, "config.put", kind="stereotypes", key="REQ", value={"retired": True})
    assert not V.errors(ada.load())  # existing usages still valid
    do(ada, "element.update", id=base["r1"], topic="still editable")
    with pytest.raises(StoreError):
        do(ada, "element.create", stereotype="REQ", topic="new", folder=base["F"])
    key = do(ada, "config.put", kind="statuses", value={"label": "Unused", "color": "#000000"})
    do(ada, "config.delete", kind="statuses", key=key)


def test_cfg08_initial_configuration(ada):
    """REQ-CFG-08: the initial stereotypes and the association link type, each stereotype with its own visuals."""
    cfg = ada.load()["config"]
    expected = {"ADR", "REQ", "NAMESPACE", "RISK", "ISSUE", "B-REQ", "U-REQ", "CONSTRAINT",
                "TEMPORAL-ADR", "FEAT", "TEST-E2E", "TEST-INT", "ASSET", "DOC"}
    assert set(cfg["stereotypes"]) == expected
    assert len({s["fill"] for s in cfg["stereotypes"].values()}) == len(expected)
    assert len({s["icon"] for s in cfg["stereotypes"].values()}) == len(expected)
    assert len({s["labelPrefix"] for s in cfg["stereotypes"].values()}) == len(expected)
    assert "association" in cfg["linkTypes"]
    assert len(cfg["statuses"]) >= 5 and len(cfg["linkTypes"]) >= 3
    assert cfg["coverageRules"] == {}  # REQ-TRC-05: none active by default
    # no typed decision date: the last change of an element is recorded anyway (ADR-016, ADR-029)
    assert cfg["stereotypes"]["ADR"]["fields"] == {"owner": {"label": "Owner", "type": "string"}}
    assert not any(f["type"] == "date" for s in cfg["stereotypes"].values() for f in s["fields"].values())


# --- search ----------------------------------------------------------------

def test_src01_02_05_search(ada, base):
    """REQ-SRC-01/02/05: by id (prefix), label, text; diagrams listed; unused list."""
    do(ada, "diagram.place", diagram=base["d1"], element=base["r2"], x=0, y=0)
    do(ada, "diagram.place", diagram=base["d2"], element=base["r2"], x=0, y=0)
    m = ada.load()
    assert [r["id"] for r in Q.search(m, base["r2"])] == [base["r2"]]
    hit = Q.search(m, base["r2"][:8])[0]
    assert hit["match"] == "id" and [d["name"] for d in hit["diagrams"]] == ["Detail", "Overview"]
    assert Q.search(m, m["elements"][base["r2"]]["label"].lower())[0]["id"] == base["r2"]  # label, any case
    assert Q.search(m, "no gaps")[0]["match"] == "topic"
    assert Q.search(m, "greece")[0]["match"] == "notes"
    assert {r["id"] for r in Q.search(m, "", stereotype="REQ")} == {base["r1"], base["r2"]}
    assert Q.search(m, "", status="approved") == []
    assert len(Q.search(m, "", folder=base["F"])) == 4
    assert {r["id"] for r in Q.search(m, "", unused=True)} == {base["r1"], base["a1"], base["k1"]}


# --- traceability ----------------------------------------------------------

def test_trc01_02_03_trace_follows_model(ada, base):
    """REQ-TRC-01/02/03: multi-level, model-based, per-type opt-out."""
    do(ada, "link.create", type="implements", source=base["a1"], target=base["r2"])
    do(ada, "link.create", type="refines", source=base["r2"], target=base["r1"])
    do(ada, "link.create", type="relates_to", source=base["k1"], target=base["r1"])  # not traceable
    m = ada.load()
    assert all(not d["nodes"] for d in m["diagrams"].values())  # nothing on any diagram
    t = Q.trace(m, base["a1"])
    assert t["to"][0]["id"] == base["r2"] and t["to"][0]["children"][0]["id"] == base["r1"]
    back = Q.trace(m, base["r1"])["from"]
    assert back[0]["id"] == base["r2"] and back[0]["children"][0]["id"] == base["a1"]
    assert base["k1"] not in [n["id"] for n in Q.flatten(back)]
    assert [n["id"] for n in Q.impact(m, base["r1"])] == [base["r2"], base["a1"]]
    assert Q.trace(m, base["a1"], depth=1)["to"][0]["children"] == []


def test_trc04_matrix(ada, base):
    """REQ-TRC-04: stereotype x stereotype matrix for chosen link types."""
    do(ada, "link.create", type="implements", source=base["a1"], target=base["r2"])
    m = ada.load()
    mx = Q.matrix(m, "ADR", "REQ", ["implements"])
    assert mx["cells"][base["a1"]][base["r2"]] == [{"type": "implements", "dir": "out"}]
    assert Q.matrix(m, "REQ", "ADR")["cells"][base["r2"]][base["a1"]][0]["dir"] == "in"
    assert Q.matrix(m, "ADR", "REQ", ["trace"])["cells"] == {}


def test_trc05_coverage_rules(ada, base):
    """REQ-TRC-05: configurable coverage rule, violations reported."""
    do(ada, "config.put", kind="coverageRules", value={
        "description": "every approved REQ must be implemented by an ADR", "stereotype": "REQ",
        "statuses": ["approved"], "linkType": "implements", "direction": "incoming", "other": "ADR"})
    do(ada, "element.update", id=base["r1"], status="approved")
    do(ada, "element.update", id=base["r2"], status="approved")
    do(ada, "link.create", type="implements", source=base["a1"], target=base["r2"])
    warn = [p for p in V.validate(ada.load()) if p["code"] == "coverage"]
    assert [p["ref"] for p in warn] == [base["r1"]]


# --- validation ------------------------------------------------------------

def test_int04_validation_reports_problems(ada, base):
    """REQ-INT-04: structure, references and configuration rules."""
    m = ada.load()
    assert V.validate(m) == []
    m["elements"][base["r1"]]["folder"] = "gone"
    m["elements"][base["r2"]]["status"] = "nope"
    m["elements"][base["a1"]]["label"] = m["elements"][base["r1"]]["label"]
    m["links"]["x"] = {"type": "implements", "source": base["r1"], "target": "missing", "label": ""}
    m["diagrams"][base["d1"]]["nodes"]["ghost"] = {"x": 0, "y": 0, "w": 1, "h": 1}
    codes = {p["code"] for p in V.validate(m)}
    assert {"reference", "status", "label"} <= codes
    assert V.validate({"format": "x"})[0]["code"] == "structure"


def test_batch_ops_are_atomic(ada, base):
    """A failing batch changes nothing; $N refers to earlier results."""
    before = open(ada.path, encoding="utf-8").read()
    with pytest.raises(StoreError):
        ada.apply([{"op": "element.create", "args": {"stereotype": "REQ", "topic": "A", "folder": base["F"]}},
                   {"op": "diagram.place", "args": {"diagram": "nope", "element": "$0", "x": 0, "y": 0}}])
    assert open(ada.path, encoding="utf-8").read() == before
    _, res = ada.apply([{"op": "element.create", "args": {"stereotype": "REQ", "topic": "A", "folder": base["F"]}},
                        {"op": "diagram.place", "args": {"diagram": base["d1"], "element": "$0", "x": 5, "y": 5}}])
    assert res[0] in ada.load()["diagrams"][base["d1"]]["nodes"]
