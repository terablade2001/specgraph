"""REQ-CFG-09 / ADR-033: every stereotype, status and link type has a description; format version 3."""
import pytest

from specgraph import FORMAT_VERSION, READABLE_VERSIONS, merge as MG, model as M, stamp as S, validate as V
from specgraph.store import StoreError
from conftest import do

KINDS = ("stereotypes", "statuses", "linkTypes")


def test_cfg09_format_version_3_reads_older_files():
    assert FORMAT_VERSION == 3 and READABLE_VERSIONS == (1, 2, 3)


def test_cfg09_defaults_ship_a_description_for_every_type(ada):
    m = ada.load()
    assert m["formatVersion"] == 3
    for kind in KINDS:
        for key, entry in m["config"][kind].items():
            assert isinstance(entry["description"], str) and entry["description"].strip(), (kind, key)
    assert not V.errors(m)


def test_cfg09_new_entry_gets_an_empty_description_and_keeps_a_given_one(ada):
    k1 = do(ada, "config.put", kind="statuses", value={"label": "Parked", "color": "#000000"})
    k2 = do(ada, "config.put", kind="linkTypes", value={
        "label": "verifies", "lineStyle": "dashed", "color": "#6d28d9", "sourceArrow": "none",
        "targetArrow": "open", "showLabel": True, "routing": "auto", "description": "The test proves the target."})
    k3 = do(ada, "config.put", kind="stereotypes", value={"label": "Term", "fill": "#ffffff", "border": "#000000"})
    cfg = ada.load()["config"]
    assert cfg["statuses"][k1]["description"] == ""
    assert cfg["linkTypes"][k2]["description"] == "The test proves the target."
    assert cfg["stereotypes"][k3]["description"] == ""
    do(ada, "config.put", kind="statuses", key=k1, value={"description": "Waiting for a decision elsewhere."})
    assert ada.load()["config"]["statuses"][k1]["description"] == "Waiting for a decision elsewhere."


def test_cfg09_description_must_be_text_of_at_most_2000_characters(ada):
    do(ada, "config.put", kind="statuses", key="approved", value={"description": "x" * 2000})
    for bad in ("x" * 2001, 5, None, ["a"]):
        with pytest.raises(StoreError, match="description"):
            do(ada, "config.put", kind="statuses", key="approved", value={"description": bad})
    m = ada.load()
    del m["config"]["linkTypes"]["refines"]["description"]
    assert any("description" in e["message"] for e in V.errors(m))   # required in format 3


def test_cfg09_version2_file_is_read_and_upgraded_on_first_change(ada, keys):
    m = ada.load()
    for kind in KINDS:
        for entry in m["config"][kind].values():
            del entry["description"]
    m["config"]["statuses"]["approved"]["description"] = "kept as it is"   # a v2 file may carry the key already
    m["formatVersion"] = 2
    S.make_stamp(m, "ada", keys["ada"], "old tool", [])
    M.save(ada.path, m)
    old = ada.load()
    assert old["formatVersion"] == 2 and not V.errors(old)                # still readable and valid
    fid = do(ada, "folder.create", name="After the upgrade")
    m = ada.load()
    assert m["formatVersion"] == 3 and fid in m["folders"] and not V.errors(m)
    assert m["config"]["statuses"]["approved"]["description"] == "kept as it is"
    assert m["config"]["statuses"]["proposed"]["description"] == ""       # nobody wrote one
    assert all("description" in e for kind in KINDS for e in m["config"][kind].values())


def _cfg(**entries):
    return {"formatVersion": 2, "config": {"stereotypes": {}, "statuses": dict(entries), "linkTypes": {}, "coverageRules": {}}}


def test_cfg09_merge_of_an_upgraded_and_an_old_side_has_no_conflict():
    base = _cfg(open={"label": "Open"}, done={"label": "Done"})
    ours = _cfg(open={"label": "Open", "description": "Being worked on"}, done={"label": "Done", "description": ""})
    ours["formatVersion"] = 3
    theirs = _cfg(open={"label": "Open (new)"})                            # an old tool renamed one, deleted the other
    merged, conflicts = MG.merge3(base, ours, theirs)
    assert conflicts == []
    assert merged["config"]["statuses"] == {"open": {"label": "Open (new)", "description": "Being worked on"}}
    assert merged["formatVersion"] == 3
