"""REQ-AIL-01/02/03/05/06/08, ADR-034: AI labels in a second, signed file."""
import json
import os
import sqlite3
import subprocess
import sys

import pytest

from conftest import HERE, commit, do, git
from specgraph import ai as A, audit, index as I, model as M, stamp as S, validate as V
from specgraph.store import StoreError


def ai_do(store, *ops, model=None):
    return A.AIStore(store).apply(list(ops), model)[1]


def op(name, **args):
    return {"op": name, "args": args}


def rows(db, sql, *args):
    con = sqlite3.connect(db)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


@pytest.fixture
def world(ada):
    """A folder with three requirements; a vocabulary of three labels."""
    fid = do(ada, "folder.create", name="Web")
    r1 = do(ada, "element.create", stereotype="REQ", topic="Users sign in with the city account", folder=fid)
    r2 = do(ada, "element.create", stereotype="REQ", topic="The kiosk takes coins", folder=fid, notes="Cash only.")
    r3 = do(ada, "element.create", stereotype="REQ", topic="Export reports as CSV", folder=fid)
    keys = ai_do(ada, op("ai.vocab.add", label="Authentication", definition="Who a user is and how it is proved."),
                 op("ai.vocab.add", label="Payments", definition="Money paid by or to residents."),
                 op("ai.vocab.add", label="Reporting", definition="Reports and exports."))
    return dict(folder=fid, r1=r1, r2=r2, r3=r3, auth=keys[0], pay=keys[1], rep=keys[2])


def label(store, eid, *labels, **kw):
    h = A.element_hash(store.load()["elements"][eid])
    return ai_do(store, op("ai.label.set", element=eid, hash=h, labels=list(labels), **kw))


# -- AIL-01: a second, signed file; without it nothing changes ------------------------------------

def test_ail01_without_an_ai_file_everything_works_as_before(ada):
    do(ada, "folder.create", name="X")
    assert not os.path.exists(A.ai_path(ada.path))
    st = A.AIStore(ada).status()
    assert st["file"] is False and st["vocabulary"] == 0 and st["labelled"] == 0
    db = I.build(ada.path)["path"]
    assert rows(db, "SELECT count(*) FROM ai_vocabulary") == [(0,)]
    assert rows(db, "SELECT count(*) FROM ai_labels") == [(0,)]
    assert rows(db, "SELECT value FROM meta WHERE key='ai'") == [("none",)]


def test_ail01_the_ai_file_is_next_to_the_model_signed_and_canonical(ada, world):
    path = A.ai_path(ada.path)
    assert path == os.path.abspath(ada.path[:-len(".json")] + ".ai.json")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    ai = json.loads(text)
    assert text == M.canonical(ai)
    assert ai["format"] == "specgraph-ai" and ai["formatVersion"] == 1 and ai["vocabVersion"] == 1
    assert set(ai) == {"format", "formatVersion", "vocabVersion", "promptVersion", "vocabulary", "labels", "rules",
                       "findings", "dismissed", "stamp"}
    assert ai["stamp"]["user"] == "ada"
    assert S.check_integrity(ai, ada.load()["users"]) == []
    assert ai["vocabulary"][world["auth"]] == {"label": "Authentication", "changed": 1,
                                               "definition": "Who a user is and how it is proved."}


def test_ail01_ai_changes_never_touch_the_model(ada, world):
    before = open(ada.path, encoding="utf-8").read()
    label(ada, world["r1"], world["auth"])
    assert open(ada.path, encoding="utf-8").read() == before


# -- AIL-02: keyed by content; stale when content or vocabulary changed ---------------------------

def test_ail02_hash_covers_type_topic_notes_fields_only(ada, world):
    el = ada.load()["elements"][world["r1"]]
    h = A.element_hash(el)
    for k, v in (("status", "approved"), ("folder", "x"), ("label", "Y-1"), ("modified", {}), ("order", 3)):
        assert A.element_hash(dict(el, **{k: v})) == h
    for k, v in (("stereotype", "ADR"), ("topic", "t"), ("notes", "n"), ("fields", {"priority": "Must"})):
        assert A.element_hash(dict(el, **{k: v})) != h


def _labels(store):
    return A.AIStore(store).element_labels()


def test_ail02_status_change_keeps_labels_content_change_makes_them_stale(ada, world):
    label(ada, world["r1"], world["auth"])
    assert _labels(ada)[world["r1"]] == ([world["auth"]], False)
    do(ada, "element.update", id=world["r1"], status="approved")
    assert _labels(ada)[world["r1"]] == ([world["auth"]], False)
    do(ada, "element.update", id=world["r1"], topic="Users sign in with the city account or a badge")
    assert _labels(ada)[world["r1"]] == ([world["auth"]], True)          # old labels, shown as stale
    assert world["r2"] not in _labels(ada)                                # never labelled


def test_ail02_vocabulary_changes_stale_only_what_they_touch(ada, world):
    label(ada, world["r1"], world["auth"])
    label(ada, world["r2"], world["pay"])
    label(ada, world["r3"], world["rep"])
    ai_do(ada, op("ai.vocab.add", label="Privacy", definition="Personal data."))           # a new label: no effect
    assert all(not stale for _, stale in _labels(ada).values())
    ai_do(ada, op("ai.vocab.update", key=world["rep"], label="Reports"))                  # name only
    ai_do(ada, op("ai.vocab.update", key=world["pay"], definition="Money.", keepLabels=True))
    assert all(not stale for _, stale in _labels(ada).values())
    ai_do(ada, op("ai.vocab.update", key=world["auth"], definition="Proving identity."))  # redefined
    ai_do(ada, op("ai.vocab.retire", key=world["rep"]))
    got = _labels(ada)
    assert got[world["r1"]][1] is True and got[world["r3"]][1] is True and got[world["r2"]][1] is False
    label(ada, world["r1"], world["auth"])                                                # relabelled: current
    assert _labels(ada)[world["r1"]] == ([world["auth"]], False)


def test_ail02_merge_and_split_retire_with_a_pointer(ada, world):
    k = ai_do(ada, op("ai.vocab.add", label="Money", definition="All money matters."),
              op("ai.vocab.merge", keys=[world["pay"]], into="$0"))[0]
    vocab = A.AIStore(ada).load()["vocabulary"]
    assert vocab[world["pay"]]["retired"] is True and vocab[world["pay"]]["replacedBy"] == [k]
    a, b = ai_do(ada, op("ai.vocab.add", label="Sign-in", definition="Logging in."),
                 op("ai.vocab.add", label="Roles", definition="Who may do what."),
                 op("ai.vocab.split", key=world["auth"], into=["$0", "$1"]))[:2]
    assert A.AIStore(ada).load()["vocabulary"][world["auth"]]["replacedBy"] == [a, b]


# -- AIL-03: one checked write path -----------------------------------------------------------------

def test_ail03_label_set_is_checked(ada, world):
    h = A.element_hash(ada.load()["elements"][world["r1"]])
    for bad, msg in (({"hash": "0" * 64}, "current"), ({"labels": ["nope"]}, "vocabulary"),
                     ({"element": "missing"}, "does not exist")):
        args = dict(element=world["r1"], hash=h, labels=[world["auth"]])
        args.update(bad)
        with pytest.raises(StoreError, match=msg):
            ai_do(ada, op("ai.label.set", **args))
    ai_do(ada, op("ai.vocab.retire", key=world["rep"]))
    with pytest.raises(StoreError, match="retired"):
        label(ada, world["r3"], world["rep"])


def test_ail03_rules_forbid_and_add_labels(ada, world):
    ai_do(ada, op("ai.rule.set", element=world["r1"], label=world["pay"], kind="never", reason="not about money"),
          op("ai.rule.set", element=world["r1"], label=world["auth"], kind="always", reason="it is sign-in"))
    with pytest.raises(StoreError, match="rule"):
        label(ada, world["r1"], world["pay"])
    label(ada, world["r1"], world["rep"])
    assert _labels(ada)[world["r1"]] == (sorted([world["auth"], world["rep"]]), False)


def test_ail03_same_labels_again_change_nothing(ada, world):
    label(ada, world["r1"], world["auth"])
    before = open(A.ai_path(ada.path), encoding="utf-8").read()
    label(ada, world["r1"], world["auth"])
    assert open(A.ai_path(ada.path), encoding="utf-8").read() == before


def test_ail03_anyone_labels_only_administrators_change_vocabulary_and_rules(ada, bob, world):
    label(bob, world["r1"], world["auth"], model="sonnet")
    ai = A.AIStore(ada).load()
    entry = ai["labels"][A.element_hash(ada.load()["elements"][world["r1"]])]
    assert entry["by"] == "bob" and entry["model"] == "sonnet" and entry["elements"] == [world["r1"]]
    for o in (op("ai.vocab.add", label="X", definition="x"), op("ai.vocab.retire", key=world["pay"]),
              op("ai.rule.set", element=world["r1"], label=world["pay"], kind="never", reason="r"), op("ai.gc")):
        with pytest.raises(StoreError, match="administrator"):
            ai_do(bob, o)


def test_ail03_one_batch_raises_the_vocabulary_version_once(ada, world):
    v = A.AIStore(ada).load()["vocabVersion"]
    ai_do(ada, op("ai.vocab.add", label="A1", definition="a"), op("ai.vocab.add", label="A2", definition="b"))
    ai = A.AIStore(ada).load()
    assert ai["vocabVersion"] == v + 1
    label(ada, world["r1"], world["auth"])
    assert A.AIStore(ada).load()["vocabVersion"] == v + 1                   # labelling does not raise it


def test_ail03_gc_drops_entries_no_element_has(ada, world):
    label(ada, world["r1"], world["auth"])
    do(ada, "element.update", id=world["r1"], topic="changed")
    label(ada, world["r1"], world["auth"])
    assert len(A.AIStore(ada).load()["labels"]) == 2
    ai_do(ada, op("ai.gc"))
    assert len(A.AIStore(ada).load()["labels"]) == 1


def test_ail03_a_hand_edited_ai_file_is_refused(ada, world):
    path = A.ai_path(ada.path)
    ai = json.load(open(path, encoding="utf-8"))
    ai["vocabulary"][world["pay"]]["definition"] = "edited by hand"
    M.save(path, ai)
    with pytest.raises(StoreError, match="stamp"):
        label(ada, world["r1"], world["auth"])


def test_ail03_ai_command(ada, world, only_key, keys):
    h = A.element_hash(ada.load()["elements"][world["r2"]])
    ops = json.dumps([op("ai.label.set", element=world["r2"], hash=h, labels=[world["pay"]])])
    sg = [sys.executable, os.path.join(os.path.dirname(HERE), "sg.py"), "--file", ada.path]
    only_key(keys["ada"])                                   # the command signs with the one key in ssh-agent
    p = subprocess.run(sg + ["ai", "apply", ops, "--model", "haiku"], capture_output=True, text=True,
                       encoding="utf-8")
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["ok"] is True
    assert _labels(ada)[world["r2"]] == ([world["pay"]], False)
    assert A.AIStore(ada).load()["labels"][h]["model"] == "haiku"
    p = subprocess.run(sg + ["ai", "status"], capture_output=True, text=True, encoding="utf-8")
    st = json.loads(p.stdout)
    assert st["file"] is True and st["vocabulary"] == 3 and st["elements"] == 3


# -- AIL-05: the index carries vocabulary and labels; labels decide nothing ------------------------

def test_ail05_index_has_vocabulary_and_labels_with_staleness(ada, world):
    label(ada, world["r1"], world["auth"])
    label(ada, world["r2"], world["pay"], world["rep"])
    info = I.ensure(ada.path)
    db = info["path"]
    assert sorted(rows(db, "SELECT key, retired FROM ai_vocabulary")) == sorted(
        [(world["auth"], 0), (world["pay"], 0), (world["rep"], 0)])
    assert sorted(rows(db, "SELECT element, label, stale FROM ai_labels")) == sorted(
        [(world["r1"], world["auth"], 0), (world["r2"], world["pay"], 0), (world["r2"], world["rep"], 0)])
    do(ada, "element.update", id=world["r1"], topic="changed")              # the model changed: rebuilt
    assert rows(I.ensure(ada.path)["path"], "SELECT stale FROM ai_labels WHERE element=?", world["r1"]) == [(1,)]
    ai_do(ada, op("ai.vocab.retire", key=world["rep"]))                     # only the AI file changed: rebuilt
    info = I.ensure(ada.path)
    assert info["built"] is True
    assert rows(info["path"], "SELECT label, stale FROM ai_labels WHERE element=? ORDER BY label", world["r2"]) == \
        sorted([(world["pay"], 1), (world["rep"], 1)])
    assert I.ensure(ada.path)["built"] is False


def test_ail05_labels_are_not_used_by_validation(ada, world):
    before = V.validate(ada.load())
    label(ada, world["r1"], world["auth"])
    assert V.validate(ada.load()) == before


# -- AIL-06: commit check and audit -----------------------------------------------------------------

def _forge(store, keys, who, change):
    """Write the AI file the way a tool would, but signed by `who` without the admin check."""
    path = A.ai_path(store.path)
    ai = json.load(open(path, encoding="utf-8"))
    change(ai)
    S.make_stamp(ai, who, keys[who], "forged", [ai["stamp"]["id"]])
    M.save(path, ai)


def test_ail06_commit_check_refuses_vocabulary_change_by_a_non_admin(repo, ada, keys, world):
    commit(repo, "vocabulary")
    _forge(ada, keys, "bob", lambda ai: ai["vocabulary"][world["pay"]].update(definition="changed by bob"))
    git(repo, "add", "-A")
    findings, _ = audit.check_staged(ada)
    assert any("administrator" in f for f in findings)
    commit(repo, "forged")
    report = audit.audit_history(ada)
    assert any("administrator" in f for e in report for f in e["findings"])


def test_ail06_commit_check_refuses_a_hand_edited_ai_file(repo, ada, world):
    commit(repo, "vocabulary")
    path = A.ai_path(ada.path)
    ai = json.load(open(path, encoding="utf-8"))
    ai["vocabulary"][world["pay"]]["definition"] = "by hand"
    M.save(path, ai)
    git(repo, "add", "-A")
    findings, _ = audit.check_staged(ada)
    assert any("ai" in f and "stamp" in f for f in findings)


def test_ail06_labels_by_any_user_pass_the_checks(repo, ada, bob, world):
    commit(repo, "vocabulary")
    label(bob, world["r1"], world["auth"])
    git(repo, "add", "-A")
    assert audit.check_staged(ada)[0] == []
    commit(repo, "labels")
    assert all(not e["findings"] for e in audit.audit_history(ada))


def test_ail06_install_hooks_marks_the_ai_files(repo, ada, only_key):
    from specgraph import hooks
    only_key(ada.key())
    hooks.install(ada)
    attrs = (repo / ".gitattributes").read_text()
    assert "specmodel.ai.json text eol=lf merge=specgraph-ai linguist-generated" in attrs
    assert "specmodel.ai.log.jsonl text eol=lf merge=union linguist-generated" in attrs


# -- AIL-08: the log --------------------------------------------------------------------------------

def test_ail08_every_operation_is_logged_append_only(ada, world):
    log = A.log_path(ada.path)
    n0 = len(open(log, encoding="utf-8").read().splitlines())
    label(ada, world["r1"], world["auth"], reason="it is about signing in", confidence=0.9, model="sonnet")
    lines = [json.loads(x) for x in open(log, encoding="utf-8").read().splitlines()]
    assert len(lines) == n0 + 1
    last = lines[-1]
    assert last["op"] == "ai.label.set" and last["by"] == "ada" and last["element"] == world["r1"]
    assert last["reason"] == "it is about signing in" and last["confidence"] == 0.9 and last["model"] == "sonnet"
    assert last["stamp"] == A.AIStore(ada).load()["stamp"]["id"]


# -- AIL-04: work packets for agents; the tool never calls a language model ---------------------------

def _linked(ada, world):
    """r1 refined by a feature outside the packet's interest; r2 verified by a test."""
    feat = do(ada, "element.create", stereotype="FEAT", topic="Self-service portal", folder=world["folder"])
    test = do(ada, "element.create", stereotype="TEST-E2E", topic="Pay at the kiosk with coins",
              folder=world["folder"])
    do(ada, "link.create", type="refines", source=world["r1"], target=feat)
    do(ada, "link.create", type="relates_to", source=world["r3"], target=feat)    # not traceable
    return feat, test


def test_ail04_todo_lists_what_needs_labels_with_light_neighbours(ada, world):
    feat, test = _linked(ada, world)
    label(ada, world["r3"], world["rep"])
    p = A.AIStore(ada).todo(limit=10)
    m = ada.load()["elements"]
    lab = {e: m[e]["label"] for e in m}
    got = {e["label"]: e for e in p["elements"]}
    assert lab[world["r3"]] not in got                               # current labels: not asked again
    assert {lab[world["r1"]], lab[world["r2"]], lab[feat], lab[test]} == set(got)
    e1 = got[lab[world["r1"]]]
    assert e1["h"] == A.element_hash(m[world["r1"]])[:12] and e1["type"] == "REQ"
    assert e1["topic"] == m[world["r1"]]["topic"] and "notes" not in e1          # empty notes left out
    assert e1["links"] == ["refines>" + lab[feat]]
    assert got[lab[feat]]["links"] == ["<refines " + lab[world["r1"]]]           # relates_to is not traceable
    assert [v["key"] for v in p["vocabulary"]] == sorted([world["auth"], world["pay"], world["rep"]])
    assert p["promptVersion"] == A.PROMPT_VERSION and "ai.label.set" in p["prompt"]
    assert p["remaining"] == 0 and p["vocabVersion"] == 1


def test_ail04_todo_limit_stale_all_and_context(ada, world):
    feat, test = _linked(ada, world)
    p = A.AIStore(ada).todo(limit=1)
    assert len(p["elements"]) == 1 and p["remaining"] == 4
    label(ada, world["r1"], world["auth"])
    for e in (world["r2"], world["r3"], feat, test):
        label(ada, e)                                                # labelled with nothing: current
    ai_do(ada, op("ai.vocab.retire", key=world["auth"]))            # only r1 becomes stale
    m = ada.load()["elements"]
    p = A.AIStore(ada).todo(limit=1)
    assert p["elements"][0]["label"] == m[world["r1"]]["label"] and p["elements"][0]["was"] == [world["auth"]]
    assert m[feat]["label"] in p["context"]                         # a neighbour outside the packet, once
    assert p["context"][m[feat]["label"]] == {"type": "FEAT", "topic": "Self-service portal", "labels": []}
    assert len(A.AIStore(ada).todo(all_=True, limit=0)["elements"]) == 5


def test_ail04_todo_caps_neighbours_at_ten(ada, world):
    tests = ada.apply([{"op": "element.create", "args": {"stereotype": "TEST-E2E", "topic": "t%d" % i,
                                                         "folder": world["folder"]}} for i in range(12)])[1]
    ada.apply([{"op": "link.create", "args": {"type": "refines", "source": t, "target": world["r2"]}}
               for t in tests])
    m = ada.load()["elements"]
    e = [x for x in A.AIStore(ada).todo(limit=0)["elements"] if x["label"] == m[world["r2"]]["label"]][0]
    assert len(e["links"]) == 10 and e["moreLinks"] == 2


def test_ail04_todo_label_new_lists_candidates(ada, world):
    label(ada, world["r1"], world["auth"])
    label(ada, world["r2"], world["pay"])
    label(ada, world["r3"], world["rep"])
    k = ai_do(ada, op("ai.vocab.add", label="Cash handling", definition="Coins and notes paid at a kiosk."))[0]
    p = A.AIStore(ada).todo(label_new=k)
    m = ada.load()["elements"]
    assert [e["label"] for e in p["elements"]] == [m[world["r2"]]["label"]]   # words: coins, kiosk, cash
    assert p["elements"][0]["labels"] == [world["pay"]]


def test_ail04_label_set_takes_a_label_and_a_hash_prefix(ada, world):
    m = ada.load()["elements"]
    ai_do(ada, op("ai.label.set", element=m[world["r2"]]["label"], hash=A.element_hash(m[world["r2"]])[:12],
                  labels=[world["pay"]]))
    assert _labels(ada)[world["r2"]] == ([world["pay"]], False)
    with pytest.raises(StoreError, match="12"):
        ai_do(ada, op("ai.label.set", element=world["r2"], hash=A.element_hash(m[world["r2"]])[:8], labels=[]))
    ai_do(ada, op("ai.label.set", element=world["r3"], hash=A.element_hash(m[world["r3"]]), labels=[]))
    assert _labels(ada)[world["r3"]] == ([], False)                   # "nothing fits" counts as labelled


def test_ail04_vocabulary_packet(ada, world):
    _linked(ada, world)
    label(ada, world["r1"], world["auth"])
    p = A.AIStore(ada).vocab_packet(samples=3, terms=5)
    assert "ai.vocab.add" in p["prompt"]
    assert p["counts"]["elements"] == 5 and p["counts"]["byType"]["REQ"] == 3
    assert {v["key"]: v["used"] for v in p["vocabulary"]}[world["auth"]] == 1
    assert len(p["samples"]) == 3 and all(set(s) == {"type", "folder", "topic"} for s in p["samples"])
    assert len(p["terms"]) <= 5 and all(isinstance(t, list) and len(t) == 2 for t in p["terms"])
    assert any(t["key"] == "REQ" and t["description"] for t in p["types"])


def test_ail04_todo_and_apply_through_files(ada, world, only_key, keys, tmp_path):
    sg = [sys.executable, os.path.join(os.path.dirname(HERE), "sg.py"), "--file", ada.path]
    out = tmp_path / "packet.json"
    p = subprocess.run(sg + ["ai", "todo", "--limit", "2", "--out", str(out)], capture_output=True, text=True,
                       encoding="utf-8")
    assert p.returncode == 0, p.stderr
    packet = json.loads(out.read_text(encoding="utf-8"))
    assert len(packet["elements"]) == 2 and "2 element(s)" in p.stdout
    lines = out.read_text(encoding="utf-8").splitlines()
    assert sum(1 for x in lines if x.startswith('{"label"')) == 2              # one element per line
    ops = [op("ai.label.set", element=e["label"], hash=e["h"], labels=[]) for e in packet["elements"]]
    (tmp_path / "ops.json").write_text(json.dumps(ops), encoding="utf-8")
    only_key(keys["bob"])
    p = subprocess.run(sg + ["ai", "apply", "--ops-file", str(tmp_path / "ops.json"), "--model", "test"],
                       capture_output=True, text=True, encoding="utf-8")
    assert p.returncode == 0, p.stderr
    assert A.AIStore(ada).status()["labelled"] == 2


# -- AIL-07: merging the AI file (ADR-035) -------------------------------------------------------------

def _ai(vv=1, vocab=None, labels=None, rules=None, findings=None, dismissed=None):
    a = A.empty()
    a.update(vocabVersion=vv, vocabulary=vocab or {}, labels=labels or {}, rules=rules or {},
             findings=findings or {}, dismissed=dismissed or {})
    return a


def _v(label, changed, **kw):
    return dict({"label": label, "definition": label + " things.", "changed": changed}, **kw)


def _l(v, labels, elements, by="ada"):
    return {"v": v, "labels": labels, "by": by, "model": "", "elements": elements}


def test_ail07_labels_merge_as_a_cache():
    voc = {"a": _v("A", 1), "b": _v("B", 1)}
    base = _ai(1, voc, {"h0": _l(1, ["a"], ["e0"])})
    ours = _ai(1, voc, {"h0": _l(1, ["a"], ["e0"]), "h1": _l(1, ["a"], ["e1"]), "h3": _l(1, ["a"], ["e3"])})
    theirs = _ai(1, voc, {"h0": _l(1, ["a"], ["e0"]), "h2": _l(1, ["b"], ["e2"]), "h3": _l(1, ["b"], ["e3"], "bob")})
    merged, conflicts = A.merge3(base, ours, theirs)
    assert conflicts == []
    assert set(merged["labels"]) == {"h0", "h1", "h2"}             # union; h3 labelled differently, same v: dropped
    ours["labels"]["h3"]["v"] = 2
    ours["vocabVersion"] = theirs["vocabVersion"] = 2
    merged, _ = A.merge3(base, ours, theirs)
    assert merged["labels"]["h3"]["labels"] == ["a"]               # the newer vocabulary version wins
    same_a, same_b = _ai(1, voc, {"h4": _l(1, ["a"], ["e4"])}), _ai(1, voc, {"h4": _l(1, ["a"], ["e5"])})
    merged, _ = A.merge3(None, same_a, same_b)
    assert merged["labels"]["h4"]["elements"] == ["e4", "e5"]      # same labels: element lists joined


def test_ail07_vocabulary_and_rules_merge_per_key():
    base = _ai(1, {"a": _v("A", 1), "b": _v("B", 1)})
    ours = _ai(2, {"a": _v("A", 2, retired=True), "b": _v("B", 1)})
    theirs = _ai(2, {"a": _v("A", 1), "b": _v("B", 1), "c": _v("C", 2)},
                 rules={"r1": {"element": "e1", "label": "b", "kind": "never", "reason": "x", "by": "ada", "at": "t"}})
    merged, conflicts = A.merge3(base, ours, theirs)
    assert conflicts == []
    assert merged["vocabulary"]["a"]["retired"] is True and "c" in merged["vocabulary"] and "r1" in merged["rules"]
    assert merged["vocabVersion"] == 3                             # both sides changed the vocabulary
    only = _ai(2, {"a": _v("A", 1), "b": _v("B", 2, definition="Bee.")})
    assert A.merge3(base, only, base)[0]["vocabVersion"] == 2      # one side only: its version


def test_ail07_same_key_changed_on_both_sides():
    base = _ai(1, {"a": _v("A", 1)})
    newer = _ai(3, {"a": _v("A", 3, definition="New A.")})
    older = _ai(2, {"a": _v("A", 2, definition="Other A.")})
    merged, conflicts = A.merge3(base, older, newer)
    assert conflicts == [] and merged["vocabulary"]["a"]["definition"] == "New A."
    tie = _ai(3, {"a": _v("A", 3, definition="Tie A.")})
    merged, conflicts = A.merge3(base, tie, newer)
    assert [c["path"] for c in conflicts] == [["vocabulary", "a"]]
    assert merged["vocabulary"]["a"]["definition"] == "Tie A."     # ours kept until an administrator decides


def _clones(repo, tmp_path, keys):
    from specgraph.store import Store
    commit(repo, "base")
    other = tmp_path / "bobclone"
    git(tmp_path, "clone", "-q", str(repo), str(other))
    git(other, "config", "user.name", "Bob")
    git(other, "config", "user.email", "bob@example.org")
    return Store(cwd=str(other), key=keys["bob"]), other


def test_ail07_parallel_labelling_merges_without_a_person(repo, ada, world, keys, tmp_path, only_key):
    from specgraph import hooks
    hooks.install(ada)
    bob, other = _clones(repo, tmp_path, keys)
    hooks.install(bob)
    label(ada, world["r1"], world["auth"])
    ai_do(ada, op("ai.vocab.add", label="Privacy", definition="Personal data."))
    commit(repo, "ada labels")
    only_key(keys["bob"])                                   # the merge is signed by the person merging
    label(bob, world["r2"], world["pay"])
    label(bob, world["r3"], world["rep"])
    commit(other, "bob labels")
    p = subprocess.run(["git", "pull", "-q", "--no-rebase", "--no-edit", "origin", "docs/specifications"],
                       cwd=str(other), capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert p.returncode == 0, p.stdout + p.stderr
    got = _labels(bob)
    assert got[world["r1"]][0] == [world["auth"]] and got[world["r2"]][0] == [world["pay"]]
    assert got[world["r3"]][0] == [world["rep"]] and not any(s for _, s in got.values())
    ai = A.AIStore(bob).load()
    assert "privacy" in ai["vocabulary"] and ai["stamp"]["user"] == "bob" and ai["stamp"]["op"] == "merge"
    assert S.check_integrity(ai, bob.load()["users"]) == []
    assert all(not e["findings"] for e in audit.audit_history(bob)), audit.audit_history(bob)
    log = [json.loads(x) for x in open(A.log_path(bob.path), encoding="utf-8").read().splitlines()]   # union
    assert {r["by"] for r in log if r["op"] == "ai.label.set"} == {"ada", "bob"}


def test_ail07_merge_refuses_a_hand_edited_side_and_resolve_rebuilds(repo, ada, world, keys, tmp_path, only_key):
    bob, other = _clones(repo, tmp_path, keys)             # no merge driver installed: git leaves markers
    label(ada, world["r1"], world["auth"])
    commit(repo, "ada")
    label(bob, world["r2"], world["pay"])
    commit(other, "bob")
    subprocess.run(["git", "pull", "-q", "--no-rebase", "--no-edit", "origin", "docs/specifications"],
                   cwd=str(other), capture_output=True)
    with pytest.raises(M.ModelError):
        A.AIStore(bob).load()
    only_key(keys["bob"])
    from specgraph.cli import main
    assert main(["--file", bob.path, "ai", "resolve"]) == 0
    got = _labels(bob)
    assert got[world["r1"]][0] == [world["auth"]] and got[world["r2"]][0] == [world["pay"]]
    ours = A.AIStore(bob).load()
    edited = json.loads(json.dumps(ours))
    edited["vocabulary"][world["pay"]]["definition"] = "by hand"
    with pytest.raises(M.ModelError, match="outside the tool"):
        A.merge_texts(None, M.canonical(ours), M.canonical(edited), bob.load()["users"], keys["bob"])


# -- AIL-09: findings (ADR-036) -------------------------------------------------------------------------

def _finding(store, kind, elements, quotes, suggestion="Link or merge them.", **kw):
    ev = [{"element": e, "quote": q} for e, q in zip(elements, quotes)]
    return ai_do(store, op("ai.finding.add", kind=kind, elements=elements, evidence=ev, suggestion=suggestion, **kw))[0]


def test_ail09_a_finding_quotes_the_specs(ada, world):
    before = open(ada.path, encoding="utf-8").read()
    m = ada.load()["elements"]
    fid = _finding(ada, "duplicate", [m[world["r1"]]["label"], world["r2"]],
                   ["sign in with the CITY   account", "kiosk takes coins"], ops=[{"op": "element.delete"}])
    f = A.AIStore(ada).load()["findings"][fid]
    assert f["kind"] == "duplicate" and f["elements"] == sorted([world["r1"], world["r2"]]) and f["by"] == "ada"
    assert f["hashes"] == [A.element_hash(m[e]) for e in f["elements"]] and f["ops"] == [{"op": "element.delete"}]
    assert open(ada.path, encoding="utf-8").read() == before                      # the model is never changed
    db = I.ensure(ada.path)["path"]
    assert rows(db, "SELECT kind, stale FROM ai_findings WHERE id=?", fid) == [("duplicate", 0)]
    assert sorted(rows(db, "SELECT element FROM ai_finding_elements WHERE finding=?", fid)) == \
        sorted([(world["r1"],), (world["r2"],)])
    do(ada, "element.update", id=world["r2"], topic="The kiosk takes coins and cards")
    assert rows(I.ensure(ada.path)["path"], "SELECT stale FROM ai_findings WHERE id=?", fid) == [(1,)]


@pytest.mark.parametrize("kind,elements,quotes,msg", [
    ("duplicate", ["r1", "r2"], ["sign in with the city account", "not in this element"], "quote"),
    ("duplicate", ["r1", "r2"], ["sign in with the city account", "coins"], "12"),
    ("duplicate", ["r1"], ["sign in with the city account"], "two"),
    ("gap", ["r1", "r2"], ["sign in with the city account"], "quote"),
    ("wish", ["r1"], ["sign in with the city account"], "kind"),
])
def test_ail09_findings_without_evidence_are_refused(ada, world, kind, elements, quotes, msg):
    with pytest.raises(StoreError, match=msg):
        _finding(ada, kind, [world[e] for e in elements], quotes)


def test_ail09_dismissed_findings_never_come_back(ada, world):
    fid = _finding(ada, "duplicate", [world["r1"], world["r2"]], ["sign in with the city account", "kiosk takes coins"])
    with pytest.raises(StoreError, match="open"):
        _finding(ada, "duplicate", [world["r2"], world["r1"]], ["kiosk takes coins", "sign in with the city account"])
    ai_do(ada, op("ai.finding.dismiss", id=fid, reason="different services"))
    ai = A.AIStore(ada).load()
    assert fid not in ai["findings"] and list(ai["dismissed"].values())[0]["reason"] == "different services"
    with pytest.raises(StoreError, match="dismissed"):
        _finding(ada, "duplicate", [world["r2"], world["r1"]], ["kiosk takes coins", "sign in with the city account"])
    other = _finding(ada, "terminology", [world["r1"], world["r2"]], ["sign in with the city account", "kiosk takes coins"])
    ai_do(ada, op("ai.finding.close", id=other, note="renamed"))
    assert A.AIStore(ada).load()["findings"] == {}


def test_ail09_only_administrators_record_findings(bob, world):
    with pytest.raises(StoreError, match="administrator"):
        _finding(bob, "gap", [world["r3"]], ["Export reports as CSV"])


def test_ail09_review_packet_by_concept(ada, world):
    label(ada, world["r1"], world["auth"])
    label(ada, world["r2"], world["pay"], world["rep"])
    label(ada, world["r3"], world["rep"])
    sub_k = ai_do(ada, op("ai.vocab.add", label="CSV", definition="CSV exports.", parent=world["rep"]))[0]
    label(ada, world["r3"], world["rep"], sub_k)
    fid = _finding(ada, "gap", [world["r3"]], ["Export reports as CSV"])
    p = A.AIStore(ada).review()
    m = ada.load()["elements"]
    assert [c["key"] for c in p["concepts"]][0] == world["rep"]                 # largest first
    assert {e["label"] for e in p["elements"]} == {m[world[w]]["label"] for w in ("r1", "r2", "r3")}
    e3 = [e for e in p["elements"] if e["label"] == m[world["r3"]]["label"]][0]
    assert e3["folder"] == "Web" and e3["status"] == m[world["r3"]]["status"] and sub_k in e3["labels"]
    assert [f["id"] for f in p["findings"]] == [fid] and "ai.finding.add" in p["prompt"]
    p = A.AIStore(ada).review(label=world["rep"])                               # a concept and its children
    assert {c["key"] for c in p["concepts"]} == {world["rep"], sub_k}
    assert {e["label"] for e in p["elements"]} == {m[world["r2"]]["label"], m[world["r3"]]["label"]}
    p = A.AIStore(ada).review(limit=1)
    assert len(p["elements"]) == 1 and p["remaining"] == 2
    later, now = {c["key"] for c in p["otherConcepts"]}, {c["key"] for c in p["concepts"]}
    assert later | now == {world["auth"], world["pay"], world["rep"], sub_k} and not later & now
    assert world["rep"] in now and len(later) == 2                   # the largest first; two wait for --label


def test_ail09_findings_merge_and_dismissal_wins():
    f = {"kind": "gap", "elements": ["e1"], "hashes": ["h"], "evidence": [], "suggestion": "s", "by": "ada",
         "at": "t", "model": ""}
    base = _ai(1, findings={"f1": f})
    kept = _ai(1, findings={"f1": f, "f2": dict(f, elements=["e2"])})
    dismissed = _ai(1, findings={}, dismissed={"gap:e1": {"kind": "gap", "elements": ["e1"], "reason": "no",
                                                          "by": "ada", "at": "t"}})
    merged, conflicts = A.merge3(base, kept, dismissed)
    assert conflicts == [] and set(merged["findings"]) == {"f2"} and "gap:e1" in merged["dismissed"]
