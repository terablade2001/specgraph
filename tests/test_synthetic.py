"""The synthetic model of the evaluations (sample/build_synthetic.py, evals/README.md) is reproducible:
the same seed gives the same ids, labels, content and planted facts, so questions and answers recorded
for one build hold for a rebuild."""
import os
import sys

from conftest import HERE
from specgraph import model as M, validate as V

sys.path.insert(0, os.path.join(os.path.dirname(HERE), "sample"))


def content(m):
    """Everything that questions can depend on: not the stamp, the keys or the times (changes, locks)."""
    els = {i: {k: v for k, v in e.items() if k != "modified"} for i, e in m["elements"].items()}
    fold = {i: dict(f, lock=f["lock"] and {k: v for k, v in f["lock"].items() if k != "at"})
            for i, f in m["folders"].items()}
    return {"elements": els, "links": m["links"], "folders": fold, "diagrams": m["diagrams"],
            "config": m["config"], "users": sorted(m["users"])}


def test_eval_synthetic_model_is_reproducible(tmp_path, keys):
    import build_synthetic as B
    a, fa = B.build(str(tmp_path / "a"), 300, seed=7, key=keys["ada"])
    b, fb = B.build(str(tmp_path / "b"), 300, seed=7, key=keys["ada"])
    c, _ = B.build(str(tmp_path / "c"), 300, seed=8, key=keys["ada"])
    ma, mb, mc = a.load(), b.load(), c.load()
    assert content(ma) == content(mb)
    fa.pop("buildSeconds"), fb.pop("buildSeconds")
    assert fa == fb
    assert set(ma["elements"]) != set(mc["elements"])            # another seed, other ids
    assert [p["code"] for p in V.validate(ma) if p["level"] == "error"] == []


def test_eval_synthetic_topics_are_unique_and_hidden_concepts_avoid_their_words(tmp_path, keys):
    """Phase 6b: no " (2)" topics (Q11 has only the planted pairs); hidden plants never use the concept's words;
    duplicates copy only plain requirements."""
    import re
    import build_synthetic as B
    s, f = B.build(str(tmp_path / "a"), 1000, seed=3, key=keys["ada"])
    m = s.load()
    topics = [e["topic"] for e in m["elements"].values()]
    assert f["suffixed"] == 0 and len(set(topics)) == len(topics)
    assert not [t for t in topics if re.search(r" \(\d+\)$", t)]
    tagged = {x for v in f["concepts"].values() for x in v}
    for cname, ids in f["hidden"].items():
        assert ids and set(ids) <= set(f["concepts"][cname])
        words = re.compile(B.CONCEPTS[cname]["words"], re.I)
        for i in ids:
            assert not words.search(m["elements"][i]["topic"] + " " + m["elements"][i]["notes"]), i
    for a, b in f["duplicates"]:
        assert a not in tagged and b not in tagged and m["elements"][a]["topic"] != m["elements"][b]["topic"]


def test_eval_synthetic_ids_do_not_leak(tmp_path, keys):
    """After a build the tool makes random ids again (the seeded ids are only for the build)."""
    import build_synthetic as B
    import specgraph.ops as O
    import specgraph.stamp as S
    before = (M.new_id, O.new_id, S.new_id)
    B.build(str(tmp_path / "a"), 100, seed=1, key=keys["ada"])
    assert (M.new_id, O.new_id, S.new_id) == before
