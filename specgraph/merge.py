"""Three-way merge that understands the model (REQ-STO-06).

Two people changing different items, or different fields of the same item,
merge automatically. Both changing the same field differently is a conflict:
our value is kept in place, and both values are recorded under "conflicts" for
a human to choose in the tool. Nothing is ever dropped silently.
"""
from . import gitio, model as M, ops as O, stamp as S, validate as V

_MISSING = object()
_SKIP = ("stamp", "conflicts")


def _side(v):
    return {"present": False, "value": None} if v is _MISSING else {"present": True, "value": v}


def _merge(base, ours, theirs, path, conflicts):
    def same(a, b):
        return a is b or (a is not _MISSING and b is not _MISSING and a == b)

    if same(ours, theirs):
        return ours
    if same(ours, base):
        return theirs
    if same(theirs, base):
        return ours
    if len(path) == 3 and path[0] == "elements" and path[2] == "modified" \
            and isinstance(ours, dict) and isinstance(theirs, dict):
        return theirs if str(theirs.get("at")) > str(ours.get("at")) else ours  # ADR-016: later one wins
    if len(path) == 3 and path[0] in O.ORDER_KINDS and path[2] == "order":
        return ours  # ADR-024: explorer order only; not worth one question per item
    if isinstance(ours, dict) and isinstance(theirs, dict) and (base is _MISSING or isinstance(base, dict)):
        b = {} if base is _MISSING else base
        out = {}
        for key in sorted(set(b) | set(ours) | set(theirs)):
            v = _merge(b.get(key, _MISSING), ours.get(key, _MISSING), theirs.get(key, _MISSING),
                       path + [key], conflicts)
            if v is not _MISSING:
                out[key] = v
        return out
    conflicts.append({"path": path, "base": _side(base), "ours": _side(ours), "theirs": _side(theirs)})
    return ours


def merge3(base, ours, theirs):
    """Return (merged_model_without_stamp, conflicts)."""
    def strip(m):
        out = M.clone({k: v for k, v in (m or {}).items() if k not in _SKIP})
        O.add_descriptions(out)  # ADR-033: an upgraded side and an old side must not differ by the empty default
        return out
    conflicts = list((ours or {}).get("conflicts", [])) + list((theirs or {}).get("conflicts", []))
    merged = _merge(strip(base) if base else _MISSING, strip(ours), strip(theirs), [], conflicts)
    if conflicts:
        merged["conflicts"] = conflicts
    return merged, conflicts


def merge_texts(base_text, ours_text, theirs_text, key_path):
    """Merge three file versions; returns (model, conflicts, validation_errors)."""
    try:
        base = M.parse(base_text) if base_text and base_text.strip() else None
    except M.ModelError:
        base = None
    ours, theirs = M.parse(ours_text), M.parse(theirs_text)
    for side, model in (("our", ours), ("their", theirs)):  # ADR-031: never carry in and re-sign a hand edit
        problems = S.check_integrity(model)
        if problems:
            raise M.ModelError("%s version was changed outside the tool, so it is not merged: %s. Run "
                               "'git merge --abort' and have that branch repaired first (its author runs "
                               "'adopt' there, or restores the file from git)." % (side, problems[0]))
    merged, conflicts = merge3(base, ours, theirs)
    actor = S.whoami(merged, key_path)
    if merged.get("formatVersion", 1) >= 2:  # one side may still be format 1
        O.upgrade(merged, actor, O.now_iso())
    S.make_stamp(merged, actor, key_path, "merge",
                 [(ours.get("stamp") or {}).get("id"), (theirs.get("stamp") or {}).get("id")])
    return merged, conflicts, [e for e in V.errors(merged) if e["code"] != "conflict"]


def resolve_from_index(store):
    """For a merge done without the merge driver: rebuild from git's stages."""
    rel = gitio.rel_path(store.root, store.path)
    stages = [gitio.show(store.root, ":%d:%s" % (n, rel)) for n in (1, 2, 3)]
    if stages[1] is None or stages[2] is None:
        raise M.ModelError("git has no unmerged versions of %s" % rel)
    merged, conflicts, errs = merge_texts(stages[0], stages[1], stages[2], store.key())
    M.save(store.path, merged)
    return conflicts, errs
