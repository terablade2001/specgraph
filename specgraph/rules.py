"""Rules about WHO may change WHAT, checked on the difference between two
model states. The same check runs when an operation is applied, before a
commit, and when auditing history (REQ-LCK-05, REQ-CHK-03) - so bypassing the
UI does not bypass the rules.
"""
from .model import COLLECTIONS


def lock_owner(model, folder_id):
    """Owner of the nearest lock on the folder or its ancestors, else None."""
    seen = set()
    folders = model.get("folders", {})
    while folder_id is not None and folder_id in folders and folder_id not in seen:
        seen.add(folder_id)
        lock = folders[folder_id].get("lock")
        if lock:
            return lock.get("owner")
        folder_id = folders[folder_id].get("parent")
    return None


def effective_locks(model):
    """{folder_id: {owner, reason, at, from}} for every folder under a lock."""
    out = {}
    for fid in model.get("folders", {}):
        cur, seen = fid, set()
        while cur is not None and cur in model["folders"] and cur not in seen:
            seen.add(cur)
            lock = model["folders"][cur].get("lock")
            if lock:
                out[fid] = dict(lock, **{"from": cur})
                break
            cur = model["folders"][cur].get("parent")
    return out


def home_folder(model, coll, id_):
    """The folder whose lock protects an item. A link is protected with its source."""
    item = model.get(coll, {}).get(id_)
    if item is None:
        return None
    if coll == "folders":
        return id_
    if coll == "links":
        src = model["elements"].get(item.get("source"))
        return src.get("folder") if src else None
    return item.get("folder")


def _name(model, coll, id_):
    item = model.get(coll, {}).get(id_) or {}
    return "%s '%s'" % (coll[:-1], item.get("label") or item.get("name") or item.get("topic") or id_[:8])


def changed_items(old, new):
    out = set()
    for coll in COLLECTIONS:
        a, b = old.get(coll, {}), new.get(coll, {})
        for id_ in set(a) | set(b):
            x, y = a.get(id_), b.get(id_)
            if coll == "elements" and isinstance(x, dict) and isinstance(y, dict) and "modified" not in x:
                y = {k: v for k, v in y.items() if k != "modified"}  # format upgrade, not a change
            if x != y:
                out.add((coll, id_))
    return out


def _but(item, key):
    return {k: v for k, v in item.items() if k != key}


def _descendants(model, fid):
    out, todo = [], [fid]
    while todo:
        cur = todo.pop()
        for k, f in model["folders"].items():
            if f.get("parent") == cur and k not in out:
                out.append(k)
                todo.append(k)
    return out


def check_change(olds, new, actor):
    """Violations for moving from state(s) `olds` to `new`, done by `actor`.

    `olds` has one entry normally and several for a merge commit. An item that
    equals its value in any parent is not attributed to the actor.
    """
    olds = [o for o in olds if o is not None]
    if not olds:
        return []
    changed = set.intersection(*[changed_items(o, new) for o in olds])
    users_changed = all(o.get("users") != new.get("users") for o in olds)
    out = []
    for old in olds:
        admin = (old.get("users", {}).get(actor) or {}).get("role") == "admin"
        if users_changed and not admin:
            out.append("only an administrator may change users (changed by %s)" % actor)
        for coll, id_ in sorted(changed):
            before, after = old.get(coll, {}).get(id_), new.get(coll, {}).get(id_)
            lock_only = False
            order_only = bool(coll == "folders" and before and after and _but(before, "order") == _but(after, "order"))
            if coll == "folders" and before and after:
                l0, l1 = before.get("lock"), after.get("lock")
                if l0 != l1:
                    lock_only = _but(before, "lock") == _but(after, "lock")
                    if l1 and l1.get("owner") != actor:
                        out.append("%s: a lock can only be taken for yourself (%s set owner %s)" % (
                            _name(new, coll, id_), actor, l1.get("owner")))
                    if l0 and l1 and l0.get("owner") != actor:
                        out.append("%s: locked by %s; unlock it first (attempt by %s)" % (
                            _name(old, coll, id_), l0.get("owner"), actor))
                    if l1 and not l0:
                        for sub in _descendants(old, id_):
                            sl = old["folders"][sub].get("lock")
                            if sl and sl.get("owner") != actor:
                                out.append("%s: contains a folder locked by %s" % (
                                    _name(old, coll, id_), sl.get("owner")))
                    if lock_only and l0 and (not l1 or l0.get("owner") == actor):
                        continue  # anyone may clear a lock (ADR-022); it is a "someone works here" mark
            if coll == "links" and after and (before is None or before.get("target") != after.get("target")):
                tgt = new.get("elements", {}).get(after.get("target"))
                owner = lock_owner(_with_old_locks(old, new), tgt.get("folder")) if tgt else None
                if owner and owner != actor:
                    out.append("%s points to an element in a folder locked by %s (change by %s)" % (
                        _name(new, coll, id_), owner, actor))
            for state, item in ((old, before), (new, after)):
                if item is None:
                    continue
                home = home_folder(state, coll, id_)
                if state is old and lock_only:
                    home = before.get("parent")  # own lock handled above
                if order_only:
                    home = item.get("parent")  # its place among its siblings belongs to the parent (ADR-024)
                owner = lock_owner(old if state is old else _with_old_locks(old, new), home)
                if owner and owner != actor:
                    out.append("%s is in a folder locked by %s (change by %s)" % (
                        _name(state, coll, id_), owner, actor))
                    break
    return sorted(set(out))


def _with_old_locks(old, new):
    """New tree structure, but locks as they were before the change, plus new
    folders. Stops someone escaping a lock by unlocking in the same change."""
    folders = {}
    for fid, f in new.get("folders", {}).items():
        prev = old.get("folders", {}).get(fid)
        folders[fid] = dict(f, lock=prev.get("lock") if prev else f.get("lock"))
    return {"folders": folders}
