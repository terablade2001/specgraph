"""Stamps, users, locks, merge, hooks, audit, history, server."""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

import pytest

from specgraph import audit as A, hooks, merge as MG, model as M, rules, stamp as S, validate as V
from specgraph import history as H
from specgraph.cli import main
from specgraph.server import start
from specgraph.store import Store, StoreError
from conftest import do, git, commit, pub


@pytest.fixture
def base(ada):
    ids = {}
    ids["F"] = do(ada, "folder.create", name="Billing")
    ids["S"] = do(ada, "folder.create", name="Sub", parent=ids["F"])
    ids["G"] = do(ada, "folder.create", name="Open")
    ids["r1"] = do(ada, "element.create", stereotype="REQ", topic="Locked req", folder=ids["S"])
    ids["r2"] = do(ada, "element.create", stereotype="REQ", topic="Free req", folder=ids["G"])
    ids["d1"] = do(ada, "diagram.create", name="Locked diagram", folder=ids["F"])
    ids["d2"] = do(ada, "diagram.create", name="Free diagram", folder=ids["G"])
    return ids


# --- stamps and identity ----------------------------------------------------

def test_int01_every_change_is_stamped(ada, bob, base):
    """REQ-INT-01: unique stamp with who, when and tool version, signed."""
    s1 = ada.load()["stamp"]
    do(bob, "element.update", id=base["r2"], topic="x")
    s2 = bob.load()["stamp"]
    assert s1["id"] != s2["id"] and s2["prev"] == [s1["id"]]
    assert s2["user"] == "bob" and s2["toolVersion"] and s2["at"].endswith("Z") and s2["op"] == "element.update"
    assert S.check_integrity(bob.load()) == []


def test_int02_hand_edit_is_detected_and_blocks(ada, base):
    """REQ-INT-02: a change that bypassed the tool is detected."""
    m = M.load(ada.path)
    m["elements"][base["r2"]]["status"] = "approved"
    M.save(ada.path, m)
    assert "outside the tool" in S.check_integrity(M.load(ada.path))[0]
    with pytest.raises(StoreError) as e:
        do(ada, "folder.create", name="X")
    assert e.value.code == "integrity"
    ada.adopt()
    st = ada.load()["stamp"]
    assert st["op"] == "adopt" and S.check_integrity(ada.load()) == []


def test_int02_forged_stamp_is_detected(ada, base, keys):
    """A stamp re-computed by hand but signed with an unregistered key fails."""
    m = M.load(ada.path)
    m["elements"][base["r2"]]["topic"] = "forged"
    S.make_stamp(m, "ada", keys["eve"], "element.update", [])
    assert "signature" in S.check_integrity(m)[0]


def test_usr01_users_keys_and_admin(ada, bob, eve, base, keys):
    """REQ-USR-01/02: users are names + existing SSH keys; admin role; no passwords."""
    assert ada.me(ada.load())["role"] == "admin" and bob.me(bob.load())["role"] == "user"
    with pytest.raises(StoreError) as e:
        do(eve, "folder.create", name="X")
    assert e.value.code == "identity"
    with pytest.raises(StoreError):  # only admins manage users
        do(bob, "user.add", name="eve", key=pub(keys["eve"]))
    do(ada, "user.add", name="eve", key=pub(keys["eve"]))
    do(eve, "folder.create", name="X")
    with pytest.raises(StoreError):
        do(ada, "user.update", name="ada", role="user")  # keep an administrator


# --- locks -----------------------------------------------------------------

def test_lck01_02_lock_covers_subtree(ada, bob, base):
    """REQ-LCK-01/02: lock covers folder, sub-folders and contents; anyone may unlock (ADR-022)."""
    do(bob, "folder.lock", id=base["F"], reason="release prep")
    for op, args in [("element.update", {"id": base["r1"], "topic": "x"}),
                     ("element.delete", {"id": base["r1"]}),
                     ("element.move", {"id": base["r1"], "folder": base["G"]}),
                     ("element.move", {"id": base["r2"], "folder": base["S"]}),
                     ("element.create", {"stereotype": "REQ", "topic": "n", "folder": base["S"]}),
                     ("folder.update", {"id": base["S"], "name": "x"}),
                     ("folder.create", {"name": "n", "parent": base["F"]}),
                     ("diagram.place", {"diagram": base["d1"], "element": base["r2"], "x": 0, "y": 0}),
                     ("diagram.update", {"id": base["d1"], "name": "x"}),
                     ("link.create", {"type": "refines", "source": base["r1"], "target": base["r2"]})]:
        with pytest.raises(StoreError) as e:
            do(ada, op, **args)
        assert e.value.code == "locked", op
    do(bob, "element.update", id=base["r1"], topic="owner may edit")
    ada2 = Store(path=ada.path, key=ada.key())
    with pytest.raises(StoreError):  # a lock inside someone else's lock
        do(ada2, "folder.lock", id=base["S"])
    do(ada, "folder.unlock", id=base["F"])  # a lock is an indicator, not ownership: anyone may clear it
    do(ada, "folder.lock", id=base["F"])
    with pytest.raises(StoreError):
        do(bob, "folder.lock", id=base["F"], reason="takeover")  # already locked: unlock first
    do(bob, "folder.unlock", id=base["F"])  # a non-admin may clear it too
    assert ada.load()["folders"][base["F"]]["lock"] is None


def test_lck03_04_locks_visible_and_content_usable(ada, bob, base):
    """REQ-LCK-03/04 (ADR-022): lock info exposed; view and place elsewhere; only the owner links to it."""
    do(bob, "folder.lock", id=base["F"], reason="audit week")
    st = ada.state()
    assert st["locks"][base["S"]]["owner"] == "bob" and st["locks"][base["S"]]["reason"] == "audit week"
    assert st["locks"][base["S"]]["from"] == base["F"] and base["G"] not in st["locks"]
    do(ada, "diagram.place", diagram=base["d2"], element=base["r1"], x=0, y=0)  # on another diagram
    with pytest.raises(StoreError) as e:  # others build nothing on content that is being worked on
        do(ada, "link.create", type="refines", source=base["r2"], target=base["r1"])
    assert e.value.code == "locked"
    do(bob, "link.create", type="refines", source=base["r2"], target=base["r1"])  # the owner may
    from specgraph import query as Q
    assert Q.search(ada.load(), "Locked req")[0]["id"] == base["r1"]
    assert Q.trace(ada.load(), base["r1"])["from"][0]["id"] == base["r2"]


def test_lck05_enforced_beyond_ui(ada, bob, base, repo):
    """REQ-LCK-05: a hand edit of locked content, even re-stamped with a valid key, is rejected."""
    do(bob, "folder.lock", id=base["F"])
    commit(repo, "bob locks")
    m = M.load(ada.path)
    m["elements"][base["r1"]]["topic"] = "sneaky"
    S.make_stamp(m, "ada", ada.key(), "element.update", [])  # ada bypasses the tool but signs
    M.save(ada.path, m)
    assert main(["--file", ada.path, "check"]) == 1
    git(repo, "add", "-A")
    findings, _ = A.check_staged(ada)
    assert any("locked by bob" in f for f in findings)
    with pytest.raises(StoreError):  # adopt cannot launder it either
        ada.adopt()


# --- concurrent work -------------------------------------------------------

def _two_clones(repo, tmp_path, keys):
    commit(repo, "base")
    other = tmp_path / "bobclone"
    git(tmp_path, "clone", "-q", str(repo), str(other))
    git(other, "config", "user.name", "Bob")
    git(other, "config", "user.email", "bob@example.org")
    return Store(cwd=str(other), key=keys["bob"]), other


def test_sto06_parallel_edits_merge_without_loss(ada, base, repo, tmp_path, keys, monkeypatch, only_key):
    """REQ-STO-06 / REQ-ELM-03: different items and different fields merge cleanly via the merge driver."""
    bob, other = _two_clones(repo, tmp_path, keys)
    for store in (ada, bob):
        hooks.install(store)
    do(ada, "element.update", id=base["r2"], status="approved")
    a_new = do(ada, "element.create", stereotype="ADR", topic="Ada's ADR", folder=base["G"], label="ADR-A")
    commit(repo, "ada")
    do(bob, "element.update", id=base["r2"], topic="Bob's wording")
    b_new = do(bob, "element.create", stereotype="RISK", topic="Bob's risk", folder=base["G"])
    commit(other, "bob")
    only_key(keys["bob"])
    git(other, "pull", "-q", "--no-rebase", "--no-edit", "origin", "docs/specifications")
    m = bob.load()
    assert m["elements"][base["r2"]]["status"] == "approved"
    assert m["elements"][base["r2"]]["topic"] == "Bob's wording"
    assert a_new in m["elements"] and b_new in m["elements"]
    assert m["stamp"]["op"] == "merge" and len(m["stamp"]["prev"]) == 2
    assert S.check_integrity(m) == [] and not V.errors(m)
    assert all(not e["findings"] for e in A.audit_history(bob)), A.audit_history(bob)


def test_sto06_same_field_conflict_goes_to_a_human(ada, base, repo, tmp_path, keys, monkeypatch, only_key):
    """REQ-STO-06 / REQ-LCK-06: same field changed twice -> surfaced, both values kept."""
    bob, other = _two_clones(repo, tmp_path, keys)
    hooks.install(bob)
    do(ada, "element.update", id=base["r2"], topic="Ada's wording")
    do(ada, "folder.lock", id=base["G"], reason="ada")
    commit(repo, "ada")
    do(bob, "element.update", id=base["r2"], topic="Bob's wording")
    do(bob, "folder.lock", id=base["G"], reason="bob")
    commit(other, "bob")
    only_key(keys["bob"])
    p = subprocess.run(["git", "pull", "-q", "--no-rebase", "--no-edit", "origin", "docs/specifications"],
                       cwd=str(other), capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert p.returncode != 0
    m = bob.load()  # still valid JSON, opened by the tool
    paths = ["/".join(c["path"]) for c in m["conflicts"]]
    assert "elements/%s/topic" % base["r2"] in paths and any(p_.endswith("/lock") for p_ in paths)
    assert m["elements"][base["r2"]]["topic"] == "Bob's wording"  # ours stays until decided
    assert any(e["code"] == "conflict" for e in V.errors(m))
    assert main(["--file", bob.path, "check"]) == 1  # cannot be committed unresolved
    while bob.load().get("conflicts"):
        c = bob.load()["conflicts"][0]
        choice = "theirs" if c["path"][-1] == "topic" else "ours"
        bob.apply([{"op": "conflict.resolve", "args": {"index": 0, "choice": choice}}])
    m = bob.load()
    assert m["elements"][base["r2"]]["topic"] == "Ada's wording" and m["folders"][base["G"]]["lock"]["owner"] == "bob"
    assert not V.errors(m)


def test_merge_without_driver_can_be_rebuilt(ada, base, repo, tmp_path, keys, monkeypatch, only_key):
    """Without the merge driver git leaves conflict markers; `resolve` rebuilds from both sides."""
    bob, other = _two_clones(repo, tmp_path, keys)
    do(ada, "element.update", id=base["r2"], status="approved")
    commit(repo, "ada")
    do(bob, "element.update", id=base["r1"], status="approved")
    commit(other, "bob")
    subprocess.run(["git", "pull", "-q", "--no-rebase", "--no-edit", "origin", "docs/specifications"],
                   cwd=str(other), capture_output=True)
    with pytest.raises(StoreError):
        bob.load()
    only_key(keys["bob"])
    assert main(["--file", bob.path, "resolve"]) == 0
    m = bob.load()
    assert m["elements"][base["r1"]]["status"] == m["elements"][base["r2"]]["status"] == "approved"


def test_merge3_delete_vs_edit_is_a_conflict():
    b = {"elements": {"e": {"topic": "t", "status": "s"}}}
    ours = {"elements": {}}
    theirs = {"elements": {"e": {"topic": "t2", "status": "s"}}}
    merged, conflicts = MG.merge3(b, ours, theirs)
    assert conflicts[0]["path"] == ["elements", "e"] and conflicts[0]["theirs"]["value"]["topic"] == "t2"


# --- hooks and audit -------------------------------------------------------

def test_chk01_02_hooks_run_locally(ada, base, repo, monkeypatch, only_key):
    """REQ-CHK-01/02: pre-commit hook blocks a hand edit; one command to set up."""
    only_key(ada.key())
    done = hooks.install(ada)
    assert any("pre-commit" in d for d in done) and os.path.exists(repo / ".git" / "hooks" / "pre-push")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "good")  # hook passes
    text = open(ada.path, encoding="utf-8").read().replace("Free req", "Edited in a text editor")
    open(ada.path, "w", encoding="utf-8", newline="\n").write(text)
    git(repo, "add", "-A")
    p = subprocess.run(["git", "commit", "-q", "-m", "bad"], cwd=str(repo), capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert p.returncode != 0 and "outside the tool" in p.stderr


def test_chk03_audit_finds_bypassed_rules(ada, bob, eve, base, repo, keys):
    """REQ-CHK-03: history audit reports integrity, lock and identity violations."""
    commit(repo, "c1 ok")
    do(bob, "folder.lock", id=base["F"])
    commit(repo, "c2 bob locks")
    m = M.load(ada.path)  # hand edit, hooks bypassed
    m["elements"][base["r2"]]["topic"] = "hand edit"
    M.save(ada.path, m)
    commit(repo, "c3 hand edit")
    ada.adopt()
    commit(repo, "c4 adopt")
    m = M.load(ada.path)  # locked content changed and properly signed by ada
    m["elements"][base["r1"]]["topic"] = "lock ignored"
    S.make_stamp(m, "ada", ada.key(), "element.update", [])
    M.save(ada.path, m)
    commit(repo, "c5 lock break")
    m = M.load(ada.path)  # unknown person adds herself and signs
    m["users"]["eve"] = {"role": "admin", "keys": [pub(keys["eve"])]}
    S.make_stamp(m, "eve", keys["eve"], "user.add", [])
    M.save(ada.path, m)
    commit(repo, "c6 unknown identity")
    rep = {e["subject"]: e for e in A.audit_history(ada)}
    assert rep["c1 ok"]["findings"] == [] and rep["c2 bob locks"]["findings"] == []
    assert any("outside the tool" in f for f in rep["c3 hand edit"]["findings"])
    assert rep["c4 adopt"]["findings"] == [] and "adopted" in rep["c4 adopt"]["notes"][0]
    assert any("locked by bob" in f for f in rep["c5 lock break"]["findings"])
    assert any("signature" in f for f in rep["c6 unknown identity"]["findings"])
    assert main(["--file", ada.path, "audit", "--quiet"]) == 1



def _hand_edit(store, eid, text):
    m = M.load(store.path)
    m["elements"][eid]["topic"] = text
    M.save(store.path, m)


def test_chk04_audit_of_a_range_of_commits(ada, base, repo, capsys):
    """REQ-CHK-04 (ADR-025): `audit` checks the whole history; `audit <from> <to>` only those commits,
    both included; `audit <from>` up to HEAD."""
    head = lambda: git(repo, "rev-parse", "HEAD").strip()
    commit(repo, "c1 ok")
    c1 = head()
    _hand_edit(ada, base["r2"], "hand edit")
    commit(repo, "c2 hand edit")
    c2 = head()
    ada.adopt()
    commit(repo, "c3 adopt")
    c3 = head()
    do(ada, "element.update", id=base["r2"], topic="Tool edit")
    commit(repo, "c4 ok")
    c4 = head()
    run = lambda *a: (main(["--file", ada.path, "audit"] + list(a)), capsys.readouterr().out)
    code, out = run()
    assert code == 1 and all(c[:10] in out for c in (c1, c2, c3, c4))
    code, out = run(c3, c4)
    assert code == 0 and c3[:10] in out and c4[:10] in out and c2[:10] not in out and "2 commit(s) checked" in out
    code, out = run(c1, c2)
    assert code == 1 and "FAIL %s" % c2[:10] in out and c3[:10] not in out
    code, out = run(c1, c1)                                               # the first commit of the repository
    assert code == 0 and "1 commit(s) checked" in out
    code, out = run(c3)                                                   # from c3 up to HEAD
    assert code == 0 and "2 commit(s) checked" in out


def test_chk05_pre_push_checks_only_the_pushed_commits(ada, base, repo, tmp_path):
    """REQ-CHK-05 (ADR-025): the pre-push hook audits only commits the remote does not have yet, so an
    old finding does not block a push, and a new one does."""
    def push(*a):
        p = subprocess.run(["git", "push"] + list(a), cwd=str(repo), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        return p.returncode, p.stdout + p.stderr
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    _hand_edit(ada, base["r2"], "old hand edit")
    commit(repo, "old hand edit")
    ada.adopt()
    commit(repo, "adopt")
    assert push("--no-verify", "-u", "origin", "HEAD")[0] == 0             # the history already holds a finding
    assert main(["--file", ada.path, "audit", "--quiet"]) == 1
    hooks.install(ada)
    do(ada, "element.update", id=base["r2"], topic="Good change")
    commit(repo, "good")
    code, err = push()
    assert code == 0, err                                                  # the old finding does not block
    git(repo, "switch", "-q", "-c", "feature")
    do(ada, "element.update", id=base["r2"], topic="On a new branch")
    commit(repo, "feature work")
    code, err = push("-u", "origin", "feature")
    assert code == 0, err                                                  # a new branch: only its own commits
    _hand_edit(ada, base["r2"], "new hand edit")
    commit(repo, "new hand edit")
    code, err = push()
    assert code != 0 and "push blocked" in err and "outside the tool" in err
    code, err = push("origin", ":feature")                                 # deleting a branch checks nothing
    assert code == 0, err

def test_sto04_hst01_history_in_human_terms(ada, bob, base, repo):
    """REQ-STO-04 / REQ-HST-01: what changed, when and by whom, from git history."""
    commit(repo, "create")
    do(bob, "element.update", id=base["r2"], status="validated")
    commit(repo, "validate")
    do(ada, "element.move", id=base["r2"], folder=base["F"])
    commit(repo, "move")
    ev = H.element_history(ada, base["r2"])
    assert ev[0]["changes"] == ["moved from Open to Billing"] and ev[0]["by"] == "ada"
    assert ev[1]["changes"] == ["status Proposed → Validated"] and ev[1]["by"] == "bob" and ev[1]["date"]
    assert ev[2]["changes"][0].startswith("created as REQ")


# --- agents and server -----------------------------------------------------

def test_int03_sto08_agents_use_the_cli(ada, base, monkeypatch, capsys, only_key):
    """REQ-INT-03 / REQ-STO-08: agents change the model through the tool and read plain JSON."""
    only_key(ada.key())
    ops = [{"op": "element.create", "args": {"stereotype": "CONSTRAINT", "topic": "VAT is 24%", "folder": base["G"]}},
           {"op": "link.create", "args": {"type": "depends_on", "source": base["r2"], "target": "$0"}}]
    assert main(["--file", ada.path, "apply", json.dumps(ops)]) == 0
    out = json.loads(capsys.readouterr().out)
    raw = json.load(open(ada.path, encoding="utf-8"))  # direct read, no tool needed
    assert raw["elements"][out["results"][0]]["topic"] == "VAT is 24%"
    assert raw["stamp"]["id"] == out["stamp"] and S.check_integrity(raw) == []
    assert main(["--file", ada.path, "apply", '[{"op":"element.update","args":{"id":"nope"}}]']) == 2
    assert main(["--file", ada.path, "show", raw["elements"][out["results"][0]]["label"]]) == 0
    assert main(["--file", ada.path, "validate"]) == 0


def test_use02_server_is_local_and_token_protected(ada, base):
    """REQ-USE-02 + safety: localhost only, token required, foreign Host refused."""
    httpd, url = start(ada, 18765, token="secret-token")
    import threading
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    root = url.split("#")[0]
    assert httpd.server_address[0] == "127.0.0.1"

    def call(path, token=None, data=None, host=None):
        req = urllib.request.Request(root + path.lstrip("/"), data=json.dumps(data).encode() if data else None)
        if token:
            req.add_header("X-specgraph-Token", token)
        if data:
            req.add_header("Content-Type", "application/json")
        if host:
            req.add_header("Host", host)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    try:
        assert call("/")[0] == 200 and b"<html" in call("/")[1]
        assert call("/api/state")[0] == 401 and call("/api/state", "wrong")[0] == 401
        assert call("/api/state", "secret-token", host="evil.example:18765")[0] == 403
        assert call("/../sg.py")[0] == 404
        code, body = call("/api/state", "secret-token")
        st = json.loads(body)
        assert code == 200 and st["me"]["user"] == "ada" and st["integrity"] == []
        ops = {"base": st["head"], "ops": [{"op": "element.update", "args": {"id": base["r2"], "topic": "via UI"}}]}
        code, body = call("/api/ops", "secret-token", ops)
        assert code == 200 and json.loads(body)["model"]["elements"][base["r2"]]["topic"] == "via UI"
        code, body = call("/api/ops", "secret-token", ops)  # stale base
        assert code == 409 and json.loads(body)["code"] == "stale"
        code, body = call("/api/search?q=via", "secret-token")
        assert json.loads(body)[0]["id"] == base["r2"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def _agent(*args):
    subprocess.run([S.ssh_add()] + list(args), capture_output=True, check=True)


def test_use05_editor_refuses_to_open_without_the_key_in_ssh_agent(ada, eve, keys, repo, only_key):
    """ADR-021: no key in ssh-agent, no editor; the key is found in the agent without any setting."""
    from specgraph.server import serve
    only_key(keys["ada"])
    auto = Store(path=ada.path)  # nothing pointed to: the one key in the agent is used
    assert auto.prove_identity() == "ada"
    with pytest.raises(StoreError):
        eve.prove_identity()  # key not registered
    _agent("-D")  # as after `ssh-add -D`
    with pytest.raises(StoreError, match="no key is loaded in ssh-agent"):
        Store(path=ada.path).prove_identity()
    with pytest.raises(StoreError, match="signing failed|no key is loaded"):
        ada.prove_identity()  # even when its key file is named explicitly
    with pytest.raises(StoreError):
        serve(Store(path=ada.path), 18766, open_browser=False)
    with pytest.raises(StoreError):
        auto.apply([{"op": "folder.create", "args": {"name": "x"}}])
    only_key(keys["ada"])
    assert Store(path=ada.path).prove_identity() == "ada"


def test_use06_exactly_one_key_must_be_loaded(ada, keys, only_key):
    """Owner decision: with several keys in the agent the tool does not run; it never guesses."""
    from specgraph.server import serve
    import specgraph.stamp as S
    only_key(keys["ada"])
    assert Store(path=ada.path).prove_identity() == "ada"  # exactly one: fine
    subprocess.run([S.ssh_add(), keys["bob"]], capture_output=True, check=True)  # now two are loaded
    for call in (lambda: Store(path=ada.path).prove_identity(),
                 lambda: Store(path=ada.path).apply([{"op": "folder.create", "args": {"name": "x"}}]),
                 lambda: serve(Store(path=ada.path), 18767, open_browser=False)):
        with pytest.raises(StoreError, match="exactly one"):
            call()
