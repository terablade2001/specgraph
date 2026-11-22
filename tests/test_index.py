"""REQ-AGT-01/02/05/06, ADR-032: the derived SQLite index of the model."""
import json
import os
import sqlite3
import subprocess
import sys

import pytest

from conftest import HERE, do
from specgraph import VERSION, index as I, model as M, validate as V


def rows(db, sql, *args):
    con = sqlite3.connect(db)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def dump(db):
    """Every row of every table, except the time of the build."""
    out = {}
    for (name,) in rows(db, "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE '%fts%' "
                            "AND name NOT LIKE '%trigram%' ORDER BY name"):
        out[name] = sorted(map(repr, rows(db, 'SELECT * FROM "%s"' % name)))
    out["meta"] = [r for r in out["meta"] if "built_at" not in r]
    return out


@pytest.fixture
def filled(ada):
    """Two folders (one locked), elements with a field, links, a diagram, a coverage rule."""
    top = do(ada, "folder.create", name="Top")
    sub = do(ada, "folder.create", name="Sub", parent=top)
    do(ada, "config.put", kind="stereotypes", key="REQ", value={"fields": {
        "priority": {"label": "Priority", "type": "enum", "options": ["Must", "Should"]},
        "cost": {"label": "Cost", "type": "number"}}})
    r1 = do(ada, "element.create", stereotype="REQ", topic="Users sign in with a password", folder=sub,
            notes="Two-factor later.", fields={"priority": "Must", "cost": 3})
    r2 = do(ada, "element.create", stereotype="REQ", topic="Café opening hours", folder=top)
    adr = do(ada, "element.create", stereotype="ADR", topic="Use passwords", folder=top)
    lnk = do(ada, "link.create", type="implements", source=adr, target=r1)
    dia = do(ada, "diagram.create", name="Overview", folder=top)
    do(ada, "diagram.place", diagram=dia, element=r1, x=0, y=0)
    do(ada, "config.put", kind="linkTypes", key="implements", value={"sources": ["ADR"]})
    rule = do(ada, "config.put", kind="coverageRules", value={
        "description": "every REQ is implemented", "stereotype": "REQ", "statuses": None,
        "linkType": "implements", "direction": "incoming", "other": "ADR"})
    do(ada, "folder.lock", id=top, reason="editing")
    return dict(top=top, sub=sub, r1=r1, r2=r2, adr=adr, link=lnk, dia=dia, rule=rule)


def test_agt01_index_lives_next_to_the_model_outside_git(ada, filled):
    info = I.build(ada.path)
    db = info["path"]
    assert db == os.path.abspath(os.path.join(os.path.dirname(ada.path), ".specgraph", "specmodel.json.db"))
    assert os.path.exists(db)
    with open(os.path.join(os.path.dirname(db), ".gitignore")) as fh:
        assert fh.read().strip() == "*"
    p = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=os.path.dirname(ada.path),
                       capture_output=True, text=True)
    assert ".specgraph" not in p.stdout
    os.remove(db)                                   # disposable: nothing is lost, the next build makes it again
    assert I.build(ada.path)["elements"] == 3


def test_agt01_index_holds_the_model(ada, filled):
    f = filled
    db = I.build(ada.path)["path"]
    m = ada.load()
    els = dict((r[0], r[1:]) for r in rows(db, "SELECT id, stereotype, status, topic, folder, folder_path, "
                                               "label, modified_by, notes_chars FROM elements"))
    assert set(els) == set(m["elements"])
    assert els[f["r1"]][:5] == ("REQ", m["elements"][f["r1"]]["status"], "Users sign in with a password",
                                f["sub"], "Top/Sub")
    assert els[f["r1"]][6:] == ("ada", len("Two-factor later."))
    assert rows(db, "SELECT notes FROM element_notes WHERE id=?", f["r1"]) == [("Two-factor later.",)]
    assert sorted(rows(db, "SELECT key, value, type FROM element_fields WHERE element=?", f["r1"])) == \
        [("cost", 3, "number"), ("priority", "Must", "enum")]
    assert rows(db, "SELECT type, source, target FROM links") == [("implements", f["adr"], f["r1"])]
    assert rows(db, "SELECT path, lock_owner, locked_by, locked_from FROM folders WHERE id=?", f["sub"]) == \
        [("Top/Sub", None, "ada", f["top"])]
    assert rows(db, "SELECT lock_owner, lock_reason FROM folders WHERE id=?", f["top"]) == [("ada", "editing")]
    assert rows(db, "SELECT name, folder_path FROM diagrams") == [("Overview", "Top")]
    assert rows(db, "SELECT diagram, element FROM diagram_elements") == [(f["dia"], f["r1"])]
    assert sorted(rows(db, "SELECT name, role FROM users")) == [("ada", "admin"), ("bob", "user")]
    assert sorted(rows(db, "SELECT element FROM coverage_violations WHERE rule=?", f["rule"])) == [(f["r2"],)]
    assert sorted(r[1] for r in rows(db, "SELECT * FROM coverage_violations")) == \
        sorted(e for _, e, _ in V.coverage_violations(m))
    v = rows(db, "SELECT source_label, source_stereotype, target_stereotype, traceable FROM v_links")
    assert v == [(m["elements"][f["adr"]]["label"], "ADR", "REQ", 1)]
    assert rows(db, "SELECT value FROM meta WHERE key='integrity'") == [("ok",)]


def test_agt01_deleted_elements_are_not_indexed(ada, filled):
    do(ada, "element.delete", id=filled["r2"])
    db = I.build(ada.path)["path"]
    assert rows(db, "SELECT count(*) FROM elements WHERE id=?", filled["r2"]) == [(0,)]
    assert rows(db, "SELECT count(*) FROM coverage_violations WHERE element=?", filled["r2"]) == [(0,)]


def test_agt01_same_model_gives_the_same_index(ada, filled, tmp_path):
    a = dump(I.build(ada.path)["path"])
    b = dump(I.build(ada.path)["path"])
    assert a == b


def test_agt01_hand_edited_model_is_indexed_and_says_so(ada, filled):
    m = ada.load()
    m["elements"][filled["r2"]]["topic"] = "changed by hand"
    M.save(ada.path, m)
    db = I.build(ada.path)["path"]
    assert rows(db, "SELECT topic FROM elements WHERE id=?", filled["r2"]) == [("changed by hand",)]
    (integrity,), = rows(db, "SELECT value FROM meta WHERE key='integrity'")
    assert "does not match its stamp" in integrity


def test_agt02_rebuilt_only_when_model_schema_or_tool_changed(ada, filled, monkeypatch):
    assert I.ensure(ada.path)["built"] is True
    assert I.ensure(ada.path)["built"] is False                     # nothing changed
    do(ada, "element.update", id=filled["r2"], status="approved")
    info = I.ensure(ada.path)
    assert info["built"] is True
    assert rows(info["path"], "SELECT status FROM elements WHERE id=?", filled["r2"]) == [("approved",)]
    monkeypatch.setattr(I, "SCHEMA_VERSION", I.SCHEMA_VERSION + 1)
    assert I.ensure(ada.path)["built"] is True
    assert I.ensure(ada.path)["built"] is False
    monkeypatch.setattr(I, "VERSION", VERSION + "-next")
    assert I.ensure(ada.path)["built"] is True


def test_agt02_broken_or_foreign_index_file_is_replaced(ada, filled):
    db = I.index_path(ada.path)
    os.makedirs(os.path.dirname(db), exist_ok=True)
    with open(db, "wb") as fh:
        fh.write(b"not a database")
    assert I.ensure(ada.path)["built"] is True
    assert rows(db, "SELECT count(*) FROM elements") == [(3,)]


def test_agt02_failed_build_keeps_the_old_index_and_leaves_no_temporary_file(ada, filled, monkeypatch):
    db = I.build(ada.path)["path"]
    do(ada, "element.update", id=filled["r2"], status="approved")

    def boom(*a):
        raise RuntimeError("disk full")
    monkeypatch.setattr(I, "_fill", boom)
    with pytest.raises(RuntimeError):
        I.ensure(ada.path)
    assert rows(db, "SELECT status FROM elements WHERE id=?", filled["r2"]) != [("approved",)]
    assert sorted(os.listdir(os.path.dirname(db))) == [".gitignore", "specmodel.json.db"]


def test_agt02_reader_holding_the_old_index_never_sees_a_half_built_one(ada, filled):
    db = I.build(ada.path)["path"]
    reader = sqlite3.connect("file:%s?mode=ro" % db.replace("\\", "/"), uri=True)
    try:
        before = reader.execute("SELECT count(*) FROM elements").fetchone()
        do(ada, "element.create", stereotype="REQ", topic="One more", folder=filled["sub"])
        info = I.ensure(ada.path)
        assert info["built"] is True
        assert rows(info["path"], "SELECT count(*) FROM elements") == [(4,)]   # fresh, swapped or private
        assert reader.execute("SELECT count(*) FROM elements").fetchone() == before
    finally:
        reader.close()
    if info["path"] != db:                      # Windows: the swap waited too long, a private copy was used
        assert info["private"] is True
        I.release(info)
        assert not os.path.exists(info["path"])
    assert I.ensure(ada.path)["built"] in (False, True)
    assert rows(db, "SELECT count(*) FROM elements") == [(4,)]


def test_agt05_index_carries_configuration_with_descriptions(ada, filled):
    db = I.build(ada.path)["path"]
    cfg = ada.load()["config"]
    st = dict((r[0], r[1:]) for r in rows(db, "SELECT key, label, description, label_prefix, retired "
                                              "FROM config_stereotypes"))
    assert set(st) == set(cfg["stereotypes"])
    assert st["REQ"] == (cfg["stereotypes"]["REQ"]["label"], cfg["stereotypes"]["REQ"]["description"],
                         cfg["stereotypes"]["REQ"].get("labelPrefix", ""), 0)
    assert dict(rows(db, "SELECT key, description FROM config_statuses")) == \
        {k: v["description"] for k, v in cfg["statuses"].items()}
    assert dict(rows(db, "SELECT key, description FROM config_link_types")) == \
        {k: v["description"] for k, v in cfg["linkTypes"].items()}
    ends = rows(db, "SELECT end, stereotype FROM config_link_type_ends WHERE link_type='implements'")
    lt = cfg["linkTypes"]["implements"]
    assert sorted(ends) == sorted([("source", s) for s in lt.get("sources") or []] +
                                  [("target", s) for s in lt.get("targets") or []])
    assert sorted(rows(db, "SELECT key, label, type, options FROM config_fields WHERE stereotype='REQ'")) == \
        [("cost", "Cost", "number", None), ("priority", "Priority", "enum", '["Must", "Should"]')]
    assert rows(db, "SELECT key, stereotype, link_type, direction, other FROM config_coverage_rules") == \
        [(filled["rule"], "REQ", "implements", "incoming", "ADR")]
    assert ("source", "ADR") in ends and not [e for e in ends if e[0] == "target"]


def test_agt05_index_describes_every_table_and_column(ada, filled):
    db = I.build(ada.path)["path"]
    doc = set(rows(db, 'SELECT "table", "column" FROM columns_doc'))
    meanings = rows(db, "SELECT meaning FROM columns_doc")
    assert all(m.strip() for (m,) in meanings)
    for (name,) in rows(db, "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') "
                            "AND name NOT LIKE 'elements_fts_%' AND name NOT LIKE 'elements_trigram_%'"):
        assert (name, "") in doc, name                      # the table itself
        for col in rows(db, 'SELECT name FROM pragma_table_info("%s")' % name):
            assert (name, col[0]) in doc, (name, col[0])


def test_agt06_full_text_search_when_available(ada, filled):
    if I.fts_mode() == "none":
        pytest.skip("this Python's SQLite has no FTS5")
    db = I.build(ada.path)["path"]
    assert rows(db, "SELECT value FROM meta WHERE key='fts'") == [(I.fts_mode(),)]
    hit = rows(db, "SELECT id FROM elements_fts WHERE elements_fts MATCH 'signing'")     # porter: sign/signing
    assert hit == [(filled["r1"],)]
    assert rows(db, "SELECT id FROM elements_fts WHERE elements_fts MATCH 'cafe'") == [(filled["r2"],)]
    assert rows(db, "SELECT id FROM elements_fts WHERE elements_fts MATCH 'must'") == [(filled["r1"],)]  # fields


def test_agt06_index_is_built_without_full_text_search(ada, filled, monkeypatch):
    monkeypatch.setattr(I, "fts_mode", lambda: "none")
    db = I.build(ada.path)["path"]
    assert rows(db, "SELECT value FROM meta WHERE key='fts'") == [("none",)]
    assert rows(db, "SELECT count(*) FROM sqlite_master WHERE name LIKE 'elements_fts%'") == [(0,)]
    assert rows(db, "SELECT id FROM elements WHERE topic LIKE '%sign in%'") == [(filled["r1"],)]


def test_agt01_index_command(ada, filled):
    p = subprocess.run([sys.executable, os.path.join(os.path.dirname(HERE), "sg.py"), "--file", ada.path, "index"],
                       capture_output=True, text=True, encoding="utf-8")
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert out["elements"] == 3 and out["links"] == 1 and out["path"] == I.index_path(ada.path)
    assert out["fts"] == I.fts_mode() and out["integrity"] == "ok" and out["seconds"] >= 0
