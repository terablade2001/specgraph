"""Checks on committed versions (REQ-CHK-01/03). Used by the git hooks for
the commit being made, and by `audit` for the whole branch history, so a
bypassed hook is still found afterwards."""
import json

from . import gitio, model as M, rules, stamp as S, validate as V


def check_version(new_text, parent_texts):
    """Findings for one version of the file given its parent version(s).
    Returns (findings, notes): findings are rule breaks, notes are information."""
    findings, notes = [], []
    try:
        new = M.parse(new_text)
    except M.ModelError as exc:
        return ["unreadable model: %s" % exc], notes
    parents = []
    for t in parent_texts:
        if t is None:
            continue
        try:
            parents.append(M.parse(t))
        except M.ModelError:
            notes.append("a parent version is unreadable; comparison skipped for it")
    if any(M.canonical(p) == M.canonical(new) for p in parents):
        return findings, notes
    st = new.get("stamp") or {}
    actor = st.get("user")
    if parents:
        trusted = {}
        for p in parents:
            trusted.update(p.get("users", {}))
    else:
        trusted = new.get("users", {})
        notes.append("first version of the model: user list is trusted as-is (bootstrap)")
    problems = S.check_integrity(new, trusted)
    findings += ["integrity: " + p for p in problems]
    if st.get("op") == "adopt":
        notes.append("outside change adopted by %s at %s" % (actor, st.get("at")))
    if not problems:
        findings += ["rule: " + v for v in rules.check_change(parents, new, actor)]
    findings += ["invalid: " + e["message"] for e in V.errors(new)]
    return findings, notes


def _unlogged_deletes(store, head_text, staged_text):
    """ADR-018: an element may only leave the model together with its line in the log."""
    try:
        gone = set(M.parse(head_text)["elements"]) - set(M.parse(staged_text)["elements"])
    except (M.ModelError, KeyError, TypeError):
        return []
    if not gone:
        return []
    rel = M.deleted_path(gitio.rel_path(store.root, store.path))
    logged = set()
    for line in (gitio.show(store.root, ":" + rel) or "").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict) and rec.get("event") == "deleted":
            logged.add(rec.get("id"))
    if gone - logged:
        return ["deleted: %d deleted element(s) are not recorded in the staged %s; run: git add %s"
                % (len(gone - logged), rel, rel)]
    return []


def check_staged(store):
    """Pre-commit: the staged model against HEAD. Returns (findings, notes)."""
    rel = gitio.rel_path(store.root, store.path)
    staged = gitio.show(store.root, ":" + rel)
    if staged is None:
        code, out = gitio.git(store.root, "ls-files", "--stage", "--", rel, check=False)
        if out.strip():
            return ["%s has unresolved git conflicts; run the 'resolve' command" % rel], []
        return [], ["model file is not staged"]
    head = gitio.show(store.root, "HEAD:" + rel)
    if head == staged:
        return [], []
    findings, notes = check_version(staged, [head])
    findings += _unlogged_deletes(store, head, staged)
    return findings, notes


def audit_history(store, rev="HEAD", since=None):
    """Walk every commit that touched the model. Returns a list of
    {commit, author, date, subject, findings, notes}."""
    rel = gitio.rel_path(store.root, store.path)
    rng = "%s..%s" % (since, rev) if since else rev
    _, out = gitio.git(store.root, "rev-list", "--topo-order", "--reverse", "--full-history",
                       "--parents", rng, "--", rel)
    report = []
    for line in out.splitlines():
        commit, *parents = line.split()
        text = gitio.show(store.root, "%s:%s" % (commit, rel))
        _, meta = gitio.git(store.root, "show", "-s", "--format=%an <%ae>%x1f%aI%x1f%s", commit)
        author, date, subject = (meta.strip().split("\x1f") + ["", "", ""])[:3]
        entry = {"commit": commit, "author": author, "date": date, "subject": subject,
                 "findings": [], "notes": []}
        if text is None:
            entry["notes"].append("model file deleted in this commit")
        else:
            ptexts = [gitio.show(store.root, "%s:%s" % (p, rel)) for p in parents]
            entry["findings"], entry["notes"] = check_version(text, ptexts if parents else [])
        report.append(entry)
    return report
