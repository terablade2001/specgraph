"""REQ-DOC-05: the example model of the README (sample/build_example.py and the stored
specmodel.example.json)."""
import os
import sys

from conftest import HERE
from specgraph import model as M, stamp as S, validate as V

ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "sample"))


def shape(m):
    """What the model says, without the random ids."""
    name = {i: e["label"] for i, e in m["elements"].items()}
    return {
        "elements": sorted((e["label"], e["stereotype"], e["topic"], e["status"], e["notes"], sorted(e["fields"].items()))
                           for e in m["elements"].values()),
        "links": sorted((l["type"], name[l["source"]], name[l["target"]]) for l in m["links"].values()),
        "diagrams": sorted((d["name"], sorted((name[e], n["x"], n["y"]) for e, n in d["nodes"].items()))
                           for d in m["diagrams"].values()),
        "folders": sorted((f["name"], bool(f["lock"])) for f in m["folders"].values()),
        "config": m["config"],
    }


def test_doc05_example_builder_makes_a_valid_model(tmp_path, keys):
    import build_example
    m = build_example.build(str(tmp_path / "example"), key=keys["ada"], user="ada").load()
    problems = V.validate(m)
    assert [p["code"] for p in problems] == ["coverage"]          # one requirement without a test, on purpose
    kinds = {e["stereotype"] for e in m["elements"].values()}
    assert {"B-REQ", "U-REQ", "FEAT", "REQ", "ADR", "TEMPORAL-ADR", "CONSTRAINT", "RISK", "ISSUE", "TEST-E2E", "TEST-INT"} <= kinds
    assert len(m["diagrams"]) == 3 and "verifies" in m["config"]["linkTypes"]
    shared = [e for e in m["elements"] if sum(e in d["nodes"] for d in m["diagrams"].values()) > 1]
    assert shared and any(f["lock"] for f in m["folders"].values())


def test_doc05_stored_example_is_the_builder_output(tmp_path, keys):
    import build_example
    with open(os.path.join(ROOT, "specmodel.example.json"), encoding="utf-8") as fh:
        stored = M.parse(fh.read())
    assert S.check_integrity(stored) == []                         # written by the tool, never by hand
    built = build_example.build(str(tmp_path / "example"), key=keys["ada"], user="ada").load()
    assert shape(stored) == shape(built)
