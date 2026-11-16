"""ADR-016..019: author and date on elements, undo, the deleted-elements log,
confirmation of deletes, tool version."""
import json
import os
import threading
import urllib.error
import urllib.request

import pytest

from specgraph import VERSION, audit as A, hooks, merge as MG, model as M, stamp as S, validate as V
from specgraph.cli import main
from specgraph.server import start
from specgraph.store import StoreError
from conftest import do, git, commit


@pytest.fixture
def base(ada):
    ids = {}
    ids["F"] = do(ada, "folder.create", name="Billing")
    ids["G"] = do(ada, "folder.create", name="Open")
    ids["r1"] = do(ada, "element.create", stereotype="REQ", topic="Invoices are numbered", folder=ids["F"])
    ids["r2"] = do(ada, "element.create", stereotype="REQ", topic="Numbers have no gaps", folder=ids["G"])
    ids["a1"] = do(ada, "element.create", stereotype="ADR", topic="Use a DB sequence", folder=ids["G"])
    ids["d1"] = do(ada, "diagram.create", name="Overview", folder=ids["G"])
    return ids


def log_lines(store):
    path = M.deleted_path(store.path)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh.read().splitlines()]


# --- ADR-016: who and when ---------------------------------------------------

def test_adr016_every_element_change_records_author_and_date(ada, bob, base):
    m = ada.load()
    assert m["formatVersion"] == 2
    first = m["elements"][base["r1"]]["modified"]
    assert first["by"] == "ada" and len(first["at"]) == 20 and first["at"].endswith("Z")
    other = m["elements"][base["r2"]]["modified"]
    do(bob, "element.update", id=base["r1"], status="approved")
    m = bob.load()
    assert m["elements"][base["r1"]]["modified"]["by"] == "bob"
    assert m["elements"][base["r2"]]["modified"] == other        # untouched element keeps its own
    do(bob, "element.move", id=base["r2"], folder=base["F"])
    assert bob.load()["elements"][base["r2"]]["modified"]["by"] == "bob"
    assert not V.errors(bob.load())


def test_adr016_layout_and_no_change_do_not_touch_the_element(ada, bob, base):
    before = ada.load()["elements"][base["r2"]]
    do(bob, "diagram.place", diagram=base["d1"], element=base["r2"], x=0, y=0)
    do(bob, "element.update", id=base["r2"], topic=before["topic"])   # same value
    assert bob.load()["elements"][base["r2"]] == before


def test_adr016_missing_author_is_a_validation_error(ada, base):
    m = ada.load()
    del m["elements"][base["r1"]]["modified"]
    assert any("author" in e["message"] for e in V.errors(m))
    m["elements"][base["r1"]]["modified"] = {"at": "2026-01-01T00:00:00Z", "by": ""}
    assert any("author" in e["message"] for e in V.errors(m))


def test_adr016_version1_file_is_upgraded_on_first_change(ada, bob, base, keys):
    do(bob, "folder.lock", id=base["F"], reason="mine")          # r1 sits in bob's lock
    m = ada.load()
    for el in m["elements"].values():
        del el["modified"]
    m["formatVersion"] = 1
    st = S.make_stamp(m, "bob", keys["bob"], "old tool", [])
    M.save(ada.path, m)
    assert ada.load()["formatVersion"] == 1 and not V.errors(ada.load())   # still readable
    do(ada, "element.update", id=base["r2"], notes="after the upgrade")
    m = ada.load()
    assert m["formatVersion"] == 2 and not V.errors(m)
    assert m["elements"][base["r1"]]["modified"] == {"at": st["at"], "by": "bob"}   # from the old stamp
    assert m["elements"][base["r2"]]["modified"]["by"] == "ada"


def test_adr016_merge_takes_the_later_author_instead_of_a_conflict():
    el = {"topic": "t", "status": "s", "modified": {"at": "2026-01-01T00:00:00Z", "by": "ada"}}
    ours = dict(el, topic="t2", modified={"at": "2026-02-01T00:00:00Z", "by": "ada"})
    theirs = dict(el, status="s2", modified={"at": "2026-03-01T00:00:00Z", "by": "bob"})
    merged, conflicts = MG.merge3({"elements": {"e": el}}, {"elements": {"e": ours}}, {"elements": {"e": theirs}})
    assert not conflicts
    assert merged["elements"]["e"] == {"topic": "t2", "status": "s2",
                                       "modified": {"at": "2026-03-01T00:00:00Z", "by": "bob"}}


# --- ADR-017: undo -------------------------------------------------------------

def test_adr017_undo_restores_the_last_n_changes(ada, base):
    ada.undo_steps = 2
    start_state = ada.load()
    do(ada, "diagram.place", diagram=base["d1"], element=base["r2"], x=5, y=5)
    placed = ada.load()
    do(ada, "diagram.remove", diagram=base["d1"], element=base["r2"])
    do(ada, "element.update", id=base["r2"], topic="Renamed")
    assert ada.state()["undo"]["steps"] == 2
    ada.undo()
    m = ada.load()
    assert m["elements"][base["r2"]] == placed["elements"][base["r2"]]
    assert m["stamp"]["op"].startswith("undo") and S.check_integrity(m) == []
    ada.undo()
    assert ada.load()["diagrams"][base["d1"]]["nodes"][base["r2"]] == {"x": 5, "y": 5, "w": 190, "h": 96}
    with pytest.raises(StoreError, match="nothing to undo"):   # only 2 steps are kept
        ada.undo()
    assert M.content_hash(ada.load()) != M.content_hash(start_state)


def test_adr017_undo_is_off_by_default_and_refused_after_an_outside_change(ada, bob, base):
    do(ada, "element.update", id=base["r2"], topic="x")
    with pytest.raises(StoreError, match="nothing to undo"):
        ada.undo()
    ada.undo_steps = 5
    do(ada, "element.update", id=base["r2"], topic="mine")
    do(bob, "element.update", id=base["r2"], topic="bob was here")    # another program
    with pytest.raises(StoreError, match="outside this editor"):
        ada.undo()
    assert ada.load()["elements"][base["r2"]]["topic"] == "bob was here"
    assert ada.state()["undo"]["steps"] == 0


def test_adr017_undo_obeys_locks(ada, bob, base):
    ada.undo_steps = 5
    do(ada, "element.update", id=base["r2"], topic="before the lock")
    head = ada.load()["stamp"]["id"]
    bob.apply([{"op": "folder.lock", "args": {"id": base["G"]}}])
    ada._undo_head = bob.load()["stamp"]["id"]     # pretend the editor saw it
    with pytest.raises(StoreError, match="locked by bob"):
        ada.undo()
    assert head != ada.load()["stamp"]["id"] and ada.load()["elements"][base["r2"]]["topic"] == "before the lock"


# --- ADR-018: deleted elements log ---------------------------------------------

def test_adr018_deleted_elements_are_logged_with_their_last_commit(ada, base, repo):
    lid = do(ada, "link.create", type="implements", source=base["a1"], target=base["r1"])
    do(ada, "element.delete", id=base["a1"])                        # never committed
    rec = log_lines(ada)[0]
    assert rec["event"] == "deleted" and rec["id"] == base["a1"] and rec["by"] == "ada"
    assert rec["lastCommit"] is None and rec["element"]["topic"] == "Use a DB sequence"
    assert rec["folderPath"] == "Open" and rec["links"][lid]["target"] == base["r1"]
    commit(repo, "first")
    sha = git(repo, "rev-parse", "HEAD").strip()
    commit_free = repo / "other.txt"
    commit_free.write_text("x")
    commit(repo, "does not touch the model")
    do(ada, "element.delete", id=base["r1"])
    rec = log_lines(ada)[1]
    assert rec["id"] == base["r1"] and rec["lastCommit"] == sha and rec["at"].endswith("Z")
    shown = json.loads(git(repo, "show", "%s:specmodel.json" % sha))
    assert shown["elements"][base["r1"]]["topic"] == "Invoices are numbered"


def test_adr018_undo_of_a_delete_appends_a_restored_line(ada, base):
    ada.undo_steps = 3
    do(ada, "element.delete", id=base["r1"])
    ada.undo()
    assert base["r1"] in ada.load()["elements"]
    assert [(r["event"], r["id"]) for r in log_lines(ada)] == [("deleted", base["r1"]), ("restored", base["r1"])]
    r = do(ada, "element.create", stereotype="REQ", topic="Short-lived", folder=base["G"])
    ada.undo()                                                       # undo of a create is a delete
    assert log_lines(ada)[-1]["event"] == "deleted" and log_lines(ada)[-1]["id"] == r


def test_adr018_commit_needs_the_log_staged(ada, base, repo, monkeypatch, only_key):
    only_key(ada.key())
    done = hooks.install(ada)
    assert any("merge=union" in d or "deleted" in d for d in done)
    assert "specmodel.deleted.jsonl text eol=lf merge=union" in (repo / ".gitattributes").read_text()
    commit(repo, "first")
    do(ada, "element.delete", id=base["r1"])
    git(repo, "add", "specmodel.json")
    findings, _ = A.check_staged(ada)
    assert any("specmodel.deleted.jsonl" in f for f in findings)
    git(repo, "add", "-A")
    assert A.check_staged(ada) == ([], [])


# --- ADR-019: confirmation; version --------------------------------------------

def test_adr019_server_wants_confirmation_and_offers_undo(ada, base):
    ada.undo_steps = 4
    httpd, url = start(ada, 18790, token="tok")
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    root = url.split("#")[0]

    def call(path, data=None):
        req = urllib.request.Request(root + path.lstrip("/"), data=json.dumps(data).encode() if data is not None else None)
        req.add_header("X-specgraph-Token", "tok")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    try:
        code, st = call("/api/state")
        assert st["version"] == VERSION and st["undo"]["steps"] == 0
        ops = [{"op": "element.delete", "args": {"id": base["r1"]}}]
        code, body = call("/api/ops", {"base": st["head"], "ops": ops})
        assert code == 409 and body["code"] == "confirm" and base["r1"] in ada.load()["elements"]
        code, st = call("/api/ops", {"base": st["head"], "ops": ops, "confirmed": True})
        assert code == 200 and base["r1"] not in st["model"]["elements"]
        assert st["undo"] == {"steps": 1, "next": "element.delete"}
        code, st = call("/api/undo", {"base": st["head"]})
        assert code == 200 and base["r1"] in st["model"]["elements"] and st["undo"]["steps"] == 0
        code, body = call("/api/undo", {"base": st["head"]})
        assert code == 409 and "nothing to undo" in body["error"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_tool_has_a_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0 and VERSION in capsys.readouterr().out and VERSION.count(".") == 2


def test_adr017_undo_of_a_delete_brings_back_the_element_its_links_and_diagram_places(ada, base):
    """Deleting an element removes its links and diagram places; undo restores all of it."""
    ada.undo_steps = 3
    lid = do(ada, "link.create", type="implements", source=base["a1"], target=base["r1"])
    do(ada, "diagram.place", diagram=base["d1"], element=base["r1"], x=1, y=2)
    before = ada.load()
    do(ada, "element.delete", id=base["r1"])
    gone = ada.load()
    assert base["r1"] not in gone["elements"] and lid not in gone["links"]       # no dangling link
    assert base["r1"] not in gone["diagrams"][base["d1"]]["nodes"]
    assert not [l for l in gone["links"].values() if base["r1"] in (l["source"], l["target"])]
    ada.undo()
    back = ada.load()
    for part in ("elements", "links", "diagrams"):
        assert back[part] == before[part], part


# --- ADR-024: order of the explorer ---------------------------------------------

def test_fld03_explorer_order_is_set_per_folder_and_kind(ada, bob, base):
    """REQ-FLD-03: sub-folders, diagrams and elements of a folder can be put in an order."""
    from specgraph import ops as O
    G, r2, a1 = base["G"], base["r2"], base["a1"]
    r3 = do(ada, "element.create", stereotype="REQ", topic="Third", folder=G)
    m = ada.load()
    assert O.tree_order(m, "elements", G)[0] == a1                     # no order yet: by name (ADR-... before REQ-...)
    before = m["elements"][r2]["modified"]
    do(bob, "folder.order", id=G, kind="elements", ids=[r3, r2, a1])
    m = ada.load()
    assert O.tree_order(m, "elements", G) == [r3, r2, a1]
    assert m["elements"][r2]["modified"] == before                     # a place in the tree is not a change of the element
    do(ada, "folder.order", id=G, kind="elements", ids=[a1])           # listed ones first, the rest keep their order
    assert O.tree_order(ada.load(), "elements", G) == [a1, r3, r2]
    new = do(ada, "element.create", stereotype="REQ", topic="Fourth", folder=G)
    assert O.tree_order(ada.load(), "elements", G) == [a1, r3, r2, new]  # not ordered yet: after the ordered ones
    do(ada, "folder.order", id=None, kind="folders", ids=[G, base["F"]])
    assert O.tree_order(ada.load(), "folders", None) == [G, base["F"]]
    do(ada, "element.move", id=a1, folder=base["F"])                   # the old place says nothing in the new folder
    assert "order" not in ada.load()["elements"][a1]
    for bad in ({"id": G, "kind": "links", "ids": []}, {"id": G, "kind": "elements", "ids": [base["r1"]]},
                {"id": G, "kind": "elements", "ids": [r3, r3]}, {"id": "nope", "kind": "elements", "ids": []}):
        with pytest.raises(StoreError):
            do(ada, "folder.order", **bad)
    m = ada.load()
    assert not V.errors(m)
    m["diagrams"][base["d1"]]["order"] = "first"
    assert any(e["code"] == "order" for e in V.errors(m))


def test_fld03_order_obeys_locks(ada, bob, base):
    """The content of a locked folder cannot be reordered by others; the folder's own place among
    its siblings is not inside its lock."""
    s1 = do(ada, "folder.create", name="One", parent=base["G"])
    s2 = do(ada, "folder.create", name="Two", parent=base["G"])
    do(bob, "folder.lock", id=base["G"], reason="mine")
    for kind, ids in (("elements", [base["r2"], base["a1"]]), ("folders", [s2, s1])):
        with pytest.raises(StoreError) as e:
            do(ada, "folder.order", id=base["G"], kind=kind, ids=ids)
        assert e.value.code == "locked"
    do(ada, "folder.order", id=None, kind="folders", ids=[base["G"], base["F"]])
    assert ada.load()["folders"][base["G"]]["order"] == 0
    do(bob, "folder.order", id=base["G"], kind="folders", ids=[s2, s1])


def test_fld03_merge_keeps_our_order_without_a_conflict():
    b = {"elements": {"e": {"topic": "t", "order": 0}}}
    ours = {"elements": {"e": {"topic": "t", "order": 2}}}
    theirs = {"elements": {"e": {"topic": "t2", "order": 5}}}
    merged, conflicts = MG.merge3(b, ours, theirs)
    assert not conflicts and merged["elements"]["e"] == {"topic": "t2", "order": 2}
