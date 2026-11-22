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
                       "stamp"}
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
    assert "specmodel.ai.json text eol=lf linguist-generated" in attrs
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
