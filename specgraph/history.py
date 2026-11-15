"""Element history in human terms, derived from git history (REQ-HST-01)."""
from . import gitio, model as M
from .query import folder_path


def _label(cfg, kind, key):
    return ((cfg.get(kind) or {}).get(key) or {}).get("label", key)


def describe(old_model, new_model, eid):
    """Human sentences for what happened to one element between two versions."""
    a = (old_model or {}).get("elements", {}).get(eid)
    b = (new_model or {}).get("elements", {}).get(eid)
    out = []
    if a is None and b is None:
        return out
    if a is None:
        return ["created as %s '%s'" % (b["stereotype"], b["topic"])]
    if b is None:
        return ["deleted"]
    cfg = new_model["config"]
    if a["status"] != b["status"]:
        out.append("status %s → %s" % (_label(old_model["config"], "statuses", a["status"]),
                                             _label(cfg, "statuses", b["status"])))
    if a["stereotype"] != b["stereotype"]:
        out.append("stereotype %s → %s" % (a["stereotype"], b["stereotype"]))
    if a["topic"] != b["topic"]:
        out.append("topic '%s' → '%s'" % (a["topic"], b["topic"]))
    if a.get("label") != b.get("label"):
        out.append("label %s → %s" % (a.get("label") or "(none)", b.get("label") or "(none)"))
    if a.get("notes") != b.get("notes"):
        out.append("notes edited")
    if a["folder"] != b["folder"]:
        out.append("moved from %s to %s" % (folder_path(old_model, a["folder"]) or "?",
                                            folder_path(new_model, b["folder"]) or "?"))
    fa, fb = a.get("fields", {}), b.get("fields", {})
    for k in sorted(set(fa) | set(fb)):
        if fa.get(k) != fb.get(k):
            out.append("%s %s → %s" % (k, fa.get(k, "(empty)"), fb.get(k, "(empty)")))
    la = {i: l for i, l in old_model["links"].items() if eid in (l["source"], l["target"])}
    lb = {i: l for i, l in new_model["links"].items() if eid in (l["source"], l["target"])}

    def other(model, l):
        o = model["elements"].get(l["target"] if l["source"] == eid else l["source"]) or {}
        return o.get("label") or o.get("topic") or "?"

    for i in sorted(set(lb) - set(la)):
        out.append("link added: %s %s" % (_label(cfg, "linkTypes", lb[i]["type"]), other(new_model, lb[i])))
    for i in sorted(set(la) - set(lb)):
        out.append("link removed: %s %s" % (_label(old_model["config"], "linkTypes", la[i]["type"]), other(old_model, la[i])))
    return out


def element_history(store, eid, limit=500):
    if not store.root:
        return []
    rel = gitio.rel_path(store.root, store.path)
    code, out = gitio.git(store.root, "log", "--reverse", "--format=%H%x1f%an%x1f%aI%x1f%s",
                          "-n", str(limit), "--", rel, check=False)
    events, prev = [], None
    for line in out.splitlines() if code == 0 else []:
        commit, author, date, subject = (line.split("\x1f") + ["", "", ""])[:4]
        text = gitio.show(store.root, "%s:%s" % (commit, rel))
        try:
            cur = M.parse(text) if text else None
        except M.ModelError:
            continue
        if cur is None:
            continue
        changes = describe(prev, cur, eid) if prev or eid in cur["elements"] else []
        if changes:
            st = cur.get("stamp") or {}
            events.append({"commit": commit[:10], "by": st.get("user") or author, "author": author,
                           "date": date, "subject": subject, "changes": changes})
        prev = cur
    return list(reversed(events))
