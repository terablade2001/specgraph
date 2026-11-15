"""Read-only questions about the model: search, usage, traceability."""
from .validate import traceable


def folder_path(model, fid):
    parts, seen = [], set()
    while fid is not None and fid in model["folders"] and fid not in seen:
        seen.add(fid)
        parts.append(model["folders"][fid]["name"])
        fid = model["folders"][fid].get("parent")
    return "/".join(reversed(parts))


def diagrams_of(model, eid):
    """All diagrams an element is used in (REQ-SRC-02)."""
    return sorted(({"id": did, "name": d["name"], "folderPath": folder_path(model, d["folder"])}
                   for did, d in model["diagrams"].items() if eid in d["nodes"]),
                  key=lambda d: (d["name"], d["id"]))


def summary(model, eid):
    el = model["elements"][eid]
    return {"id": eid, "label": el.get("label", ""), "topic": el["topic"], "stereotype": el["stereotype"],
            "status": el["status"], "folder": el["folder"], "folderPath": folder_path(model, el["folder"])}


def _in_folder(model, fid, root):
    seen = set()
    while fid is not None and fid not in seen:
        if fid == root:
            return True
        seen.add(fid)
        fid = (model["folders"].get(fid) or {}).get("parent")
    return False


def search(model, q="", stereotype=None, status=None, folder=None, unused=False):
    """REQ-SRC-01/02/05. q matches id (full or prefix), label, topic and notes."""
    q = (q or "").strip().lower()
    out = []
    for eid, el in model["elements"].items():
        if stereotype and el["stereotype"] != stereotype:
            continue
        if status and el["status"] != status:
            continue
        if folder and not _in_folder(model, el["folder"], folder):
            continue
        match = None
        if not q:
            match = "all"
        elif eid.lower().startswith(q):
            match = "id"
        elif q in (el.get("label") or "").lower():
            match = "label"
        elif q in el["topic"].lower():
            match = "topic"
        elif q in (el.get("notes") or "").lower():
            match = "notes"
        if not match:
            continue
        used = diagrams_of(model, eid)
        if unused and used:
            continue
        out.append(dict(summary(model, eid), match=match, diagrams=used))
    order = {"id": 0, "label": 1, "topic": 2, "notes": 3, "all": 4}
    return sorted(out, key=lambda r: (order[r["match"]], r["label"], r["topic"], r["id"]))


def usage(model, eid):
    """Where an element is used; shown before deleting it (REQ-ELM-06)."""
    links = []
    for lid, l in sorted(model["links"].items()):
        if eid in (l["source"], l["target"]):
            other = l["target"] if l["source"] == eid else l["source"]
            links.append({"id": lid, "type": l["type"],
                          "direction": "out" if l["source"] == eid else "in",
                          "other": summary(model, other)})
    return {"element": summary(model, eid), "diagrams": diagrams_of(model, eid), "links": links}


def _walk(model, start, direction, depth):
    """Tree of elements reached over traceable links. Each element appears once."""
    mine, other = ("source", "target") if direction == "to" else ("target", "source")
    types = model["config"]["linkTypes"]
    seen = {start}

    def children(eid, level):
        out = []
        if depth is not None and level > depth:
            return out
        hits = sorted((l[other], lid, l["type"]) for lid, l in model["links"].items()
                      if l[mine] == eid and traceable(types.get(l["type"], {})))
        fresh = []
        for oid, lid, ltype in hits:
            if oid in seen or oid not in model["elements"]:
                continue
            seen.add(oid)
            fresh.append((oid, lid, ltype))
        for oid, lid, ltype in fresh:
            out.append(dict(summary(model, oid), link=lid, linkType=ltype, level=level,
                            children=children(oid, level + 1)))
        return out

    return children(start, 1)


def trace(model, eid, depth=None):
    """REQ-TRC-01/03: follows model links, never diagrams.

    'to'   = what this element traces to (following links source -> target).
    'from' = what traces to it (target -> source); this is also the impact set:
             everything that depends, directly or indirectly, on this element.
    """
    return {"element": summary(model, eid), "to": _walk(model, eid, "to", depth),
            "from": _walk(model, eid, "from", depth)}


def flatten(tree):
    out = []
    for node in tree:
        out.append({k: v for k, v in node.items() if k != "children"})
        out.extend(flatten(node["children"]))
    return out


def impact(model, eid):
    """REQ-TRC-04: everything affected downstream of an element."""
    return flatten(_walk(model, eid, "from", None))


def matrix(model, rows, cols, types=None):
    """REQ-TRC-04: stereotype x stereotype matrix for the chosen link types."""
    r = sorted((summary(model, i) for i, e in model["elements"].items() if e["stereotype"] == rows),
               key=lambda s: (s["label"], s["topic"]))
    c = sorted((summary(model, i) for i, e in model["elements"].items() if e["stereotype"] == cols),
               key=lambda s: (s["label"], s["topic"]))
    rset, cset, cells = {s["id"] for s in r}, {s["id"] for s in c}, {}
    for l in model["links"].values():
        if types and l["type"] not in types:
            continue
        if l["source"] in rset and l["target"] in cset:
            cells.setdefault(l["source"], {}).setdefault(l["target"], []).append({"type": l["type"], "dir": "out"})
        elif l["target"] in rset and l["source"] in cset:
            cells.setdefault(l["target"], {}).setdefault(l["source"], []).append({"type": l["type"], "dir": "in"})
    return {"rows": r, "cols": c, "cells": cells}
