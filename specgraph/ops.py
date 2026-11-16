"""Every change to the model is one of these operations (REQ-INT-01).

apply_ops() is pure: it returns a new model and never touches disk. The store
adds identity, lock rules, stamping and saving around it.
"""
import re
from datetime import datetime, timezone

from . import FORMAT_VERSION
from .model import clone, new_id, CONFIG_KINDS
from .defaults import ROUTINGS
from . import validate as V

OPS = {}


class OpError(Exception):
    """The operation is not allowed or its arguments are wrong."""


def op(name, doc):
    def deco(fn):
        fn.doc = doc
        OPS[name] = fn
        return fn
    return deco


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get(coll, id_, what):
    if not isinstance(id_, str) or id_ not in coll:
        raise OpError("%s %r does not exist" % (what, id_))
    return coll[id_]


def _text(a, key, default=None, max_len=200, required=False):
    v = a.get(key, default)
    if v is None and not required:
        return None
    if not isinstance(v, str) or len(v) > max_len or (required and not v.strip()):
        raise OpError("'%s' must be text%s (max %d characters)" % (
            key, ", not empty" if required else "", max_len))
    return v


def _int(a, key, default=None, lo=-100000, hi=100000):
    v = a.get(key, default)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
        raise OpError("'%s' must be a number" % key)
    return int(round(v))


def _folder_or_root(m, fid):
    if fid is not None:
        _get(m["folders"], fid, "folder")
    return fid


def _descends(m, fid, ancestor):
    while fid is not None:
        if fid == ancestor:
            return True
        fid = m["folders"][fid].get("parent")
    return False


def _check_label(m, label, self_id=None):
    if label and any(e.get("label") == label and eid != self_id for eid, e in m["elements"].items()):
        raise OpError("label '%s' is already used" % label)


def _auto_label(m, st_key, eid):
    """Type prefix plus the first 8 characters of the id, like a short git hash (ADR-023).
    Nothing is counted, so parallel branches do not clash. If those 8 characters are already
    in a label, more characters are taken."""
    prefix = m["config"]["stereotypes"][st_key].get("labelPrefix")
    if not prefix:
        return ""
    hexid, used = eid.replace("-", ""), {e.get("label") for e in m["elements"].values()}
    for n in range(8, len(hexid) + 1):
        label = "%s-%s" % (prefix, hexid[:n])
        if label not in used:
            return label
    return label


def _usable(m, kind, key, what):
    entry = m["config"][kind].get(key) if isinstance(key, str) else None
    if entry is None:
        raise OpError("%s %r does not exist" % (what, key))
    if entry.get("retired"):
        raise OpError("%s '%s' is retired and cannot be used for new items" % (what, entry["label"]))
    return entry


def _check_status(m, st_key, status):
    if status not in V.allowed_statuses(m["config"], st_key):
        raise OpError("status %r is not allowed for %s" % (status, st_key))


def _check_fields(m, st_key, fields):
    errs = V.check_fields(m["config"], st_key, fields)
    if errs:
        raise OpError("; ".join(errs))


# ---- folders ---------------------------------------------------------------

@op("folder.create", "{name, parent?} -> id. parent null = top level.")
def folder_create(m, a, ctx):
    fid = new_id()
    m["folders"][fid] = {"name": _text(a, "name", required=True),
                         "parent": _folder_or_root(m, a.get("parent")), "lock": None}
    return fid


@op("folder.update", "{id, name}")
def folder_update(m, a, ctx):
    _get(m["folders"], a.get("id"), "folder")["name"] = _text(a, "name", required=True)


@op("folder.move", "{id, parent} parent null = top level.")
def folder_move(m, a, ctx):
    f = _get(m["folders"], a.get("id"), "folder")
    parent = _folder_or_root(m, a.get("parent"))
    if _descends(m, parent, a["id"]):
        raise OpError("a folder cannot be moved into itself")
    if f.get("parent") != parent:
        f.pop("order", None)  # a place among the old siblings says nothing among the new ones
    f["parent"] = parent


@op("folder.delete", "{id} folder must be empty.")
def folder_delete(m, a, ctx):
    fid = a.get("id")
    _get(m["folders"], fid, "folder")
    if any(f.get("parent") == fid for f in m["folders"].values()) \
            or any(e.get("folder") == fid for e in m["elements"].values()) \
            or any(d.get("folder") == fid for d in m["diagrams"].values()):
        raise OpError("folder is not empty")
    del m["folders"][fid]


@op("folder.lock", "{id, reason?} lock folder and everything below it for yourself.")
def folder_lock(m, a, ctx):
    f = _get(m["folders"], a.get("id"), "folder")
    if f.get("lock"):
        raise OpError("folder is already locked by %s" % f["lock"]["owner"])
    f["lock"] = {"owner": ctx["actor"], "reason": _text(a, "reason", "", 500) or "", "at": now_iso()}


@op("folder.unlock", "{id} anyone may unlock; the CLI and editor ask for confirmation when it is another user's lock.")
def folder_unlock(m, a, ctx):
    f = _get(m["folders"], a.get("id"), "folder")
    if not f.get("lock"):
        raise OpError("folder is not locked")
    f["lock"] = None


ORDER_KINDS = {"folders": "parent", "diagrams": "folder", "elements": "folder"}


def tree_order(m, kind, parent):
    """Ids of the sub-folders, diagrams or elements directly in `parent`, as the explorer
    shows them (ADR-024): by `order` when set, the rest after them by name."""
    def name(x):
        return ((x.get("label") or "") + " " + x["topic"]).strip() if kind == "elements" else x["name"]

    kids = [(i, x) for i, x in m[kind].items() if x.get(ORDER_KINDS[kind]) == parent]
    kids.sort(key=lambda p: (0, p[1]["order"], "") if _is_order(p[1].get("order"))
              else (1, 0, name(p[1]).casefold()))
    return [i for i, _ in kids]


def _is_order(v):
    return isinstance(v, int) and not isinstance(v, bool)


@op("folder.order", "{id, kind, ids} order of the explorer. kind: folders|diagrams|elements directly in "
                    "folder id (null = top level, folders only). The listed ids come first, in that order; "
                    "siblings left out follow in their present order.")
def folder_order(m, a, ctx):
    parent, kind, ids = _folder_or_root(m, a.get("id")), a.get("kind"), a.get("ids")
    if kind not in ORDER_KINDS:
        raise OpError("kind must be one of %s" % ", ".join(ORDER_KINDS))
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids) or len(set(ids)) != len(ids):
        raise OpError("'ids' must be a list of different ids")
    now = tree_order(m, kind, parent)
    for i in ids:
        if i not in now:
            raise OpError("%r is not one of the %s directly in this folder" % (i, kind))
    for n, i in enumerate(ids + [i for i in now if i not in ids]):
        m[kind][i]["order"] = n


# ---- elements --------------------------------------------------------------

@op("element.create", "{stereotype, topic, folder, notes?, status?, label?, fields?} -> id")
def element_create(m, a, ctx):
    st = a.get("stereotype")
    _usable(m, "stereotypes", st, "stereotype")
    _get(m["folders"], a.get("folder"), "folder")
    allowed = V.allowed_statuses(m["config"], st)
    if not allowed:
        raise OpError("stereotype %s has no usable status" % st)
    status = a.get("status") or allowed[0]
    _check_status(m, st, status)
    fields = a.get("fields") or {}
    _check_fields(m, st, fields)
    label = _text(a, "label", None, 40)
    eid = new_id()
    if label is None:
        label = _auto_label(m, st, eid)
    _check_label(m, label)
    m["elements"][eid] = {"stereotype": st, "topic": _text(a, "topic", required=True, max_len=300),
                          "notes": _text(a, "notes", "", 20000), "status": status, "label": label,
                          "folder": a["folder"], "fields": fields}
    return eid


@op("element.update", "{id, topic?, notes?, status?, label?, stereotype?, fields?} "
                      "fields is merged; a null value removes that field.")
def element_update(m, a, ctx):
    eid = a.get("id")
    el = _get(m["elements"], eid, "element")
    if "stereotype" in a and a["stereotype"] != el["stereotype"]:
        _usable(m, "stereotypes", a["stereotype"], "stereotype")
        el["stereotype"] = a["stereotype"]
        defs = m["config"]["stereotypes"][el["stereotype"]].get("fields", {})
        el["fields"] = {k: v for k, v in el["fields"].items()
                        if k in defs and V.check_field_value(defs[k], v)}
        for l in m["links"].values():
            if eid in (l["source"], l["target"]) and not V.link_allowed(
                    m["config"], l["type"], m["elements"][l["source"]]["stereotype"],
                    m["elements"][l["target"]]["stereotype"]):
                raise OpError("an existing '%s' link does not allow this stereotype" %
                              m["config"]["linkTypes"][l["type"]]["label"])
        if "status" not in a and el["status"] not in V.allowed_statuses(m["config"], el["stereotype"], True):
            raise OpError("current status is not allowed for %s; pass a status too" % el["stereotype"])
    if "topic" in a:
        el["topic"] = _text(a, "topic", required=True, max_len=300)
    if "notes" in a:
        el["notes"] = _text(a, "notes", "", 20000) or ""
    if "status" in a and a["status"] != el["status"]:
        _check_status(m, el["stereotype"], a["status"])
        el["status"] = a["status"]
    if "label" in a:
        label = _text(a, "label", "", 40) or ""
        _check_label(m, label, eid)
        el["label"] = label
    if "fields" in a:
        if not isinstance(a["fields"], dict):
            raise OpError("'fields' must be an object")
        merged = dict(el["fields"])
        for k, v in a["fields"].items():
            if v is None or v == "":
                merged.pop(k, None)
            else:
                merged[k] = v
        _check_fields(m, el["stereotype"], merged)
        el["fields"] = merged


@op("element.move", "{id, folder}")
def element_move(m, a, ctx):
    el = _get(m["elements"], a.get("id"), "element")
    _get(m["folders"], a.get("folder"), "folder")
    if el["folder"] != a["folder"]:
        el.pop("order", None)
    el["folder"] = a["folder"]


@op("element.delete", "{id} deletes the element from the model, with its links and all its "
                      "diagram appearances. Use diagram.remove to only take it off a diagram.")
def element_delete(m, a, ctx):
    eid = a.get("id")
    _get(m["elements"], eid, "element")
    for lid in [lid for lid, l in m["links"].items() if eid in (l["source"], l["target"])]:
        _drop_link(m, lid)
    for d in m["diagrams"].values():
        d["nodes"].pop(eid, None)
    del m["elements"][eid]


# ---- links -----------------------------------------------------------------

def _drop_link(m, lid):
    del m["links"][lid]
    for d in m["diagrams"].values():
        d["links"].pop(lid, None)


def _check_link(m, type_key, src, dst, self_id=None):
    if src == dst:
        raise OpError("an element cannot be linked to itself")
    els = m["elements"]
    if not V.link_allowed(m["config"], type_key, els[src]["stereotype"], els[dst]["stereotype"]):
        raise OpError("link type '%s' may not connect %s to %s" % (
            m["config"]["linkTypes"][type_key]["label"], els[src]["stereotype"], els[dst]["stereotype"]))
    for lid, l in m["links"].items():
        if lid != self_id and (l["type"], l["source"], l["target"]) == (type_key, src, dst):
            raise OpError("this link already exists")


@op("link.create", "{type, source, target, label?} -> id. Links belong to the model, not to diagrams.")
def link_create(m, a, ctx):
    _usable(m, "linkTypes", a.get("type"), "link type")
    _get(m["elements"], a.get("source"), "element")
    _get(m["elements"], a.get("target"), "element")
    _check_link(m, a["type"], a["source"], a["target"])
    lid = new_id()
    m["links"][lid] = {"type": a["type"], "source": a["source"], "target": a["target"],
                       "label": _text(a, "label", "", 200) or ""}
    return lid


@op("link.update", "{id, type?, label?}")
def link_update(m, a, ctx):
    l = _get(m["links"], a.get("id"), "link")
    if "type" in a and a["type"] != l["type"]:
        _usable(m, "linkTypes", a["type"], "link type")
        _check_link(m, a["type"], l["source"], l["target"], a["id"])
        l["type"] = a["type"]
    if "label" in a:
        l["label"] = _text(a, "label", "", 200) or ""


@op("link.delete", "{id}")
def link_delete(m, a, ctx):
    _get(m["links"], a.get("id"), "link")
    _drop_link(m, a["id"])


# ---- diagrams --------------------------------------------------------------

@op("diagram.create", "{name, folder} -> id")
def diagram_create(m, a, ctx):
    _get(m["folders"], a.get("folder"), "folder")
    did = new_id()
    m["diagrams"][did] = {"name": _text(a, "name", required=True), "folder": a["folder"],
                          "nodes": {}, "links": {}}
    return did


@op("diagram.update", "{id, name}")
def diagram_update(m, a, ctx):
    _get(m["diagrams"], a.get("id"), "diagram")["name"] = _text(a, "name", required=True)


@op("diagram.move", "{id, folder}")
def diagram_move(m, a, ctx):
    d = _get(m["diagrams"], a.get("id"), "diagram")
    _get(m["folders"], a.get("folder"), "folder")
    if d["folder"] != a["folder"]:
        d.pop("order", None)
    d["folder"] = a["folder"]


@op("diagram.delete", "{id} elements stay in the model.")
def diagram_delete(m, a, ctx):
    _get(m["diagrams"], a.get("id"), "diagram")
    del m["diagrams"][a["id"]]


@op("diagram.place", "{diagram, element, x, y, w?, h?} put an existing element on a diagram.")
def diagram_place(m, a, ctx):
    d = _get(m["diagrams"], a.get("diagram"), "diagram")
    _get(m["elements"], a.get("element"), "element")
    if a["element"] in d["nodes"]:
        raise OpError("element is already on this diagram")
    d["nodes"][a["element"]] = {"x": _int(a, "x"), "y": _int(a, "y"),
                                "w": _int(a, "w", 190, 60, 2000), "h": _int(a, "h", 96, 40, 2000)}


@op("diagram.layout", "{diagram, element, x?, y?, w?, h?} move or resize on one diagram.")
def diagram_layout(m, a, ctx):
    d = _get(m["diagrams"], a.get("diagram"), "diagram")
    n = _get(d["nodes"], a.get("element"), "diagram node")
    for k, lo, hi in (("x", -100000, 100000), ("y", -100000, 100000), ("w", 60, 2000), ("h", 40, 2000)):
        if k in a:
            n[k] = _int(a, k, None, lo, hi)


@op("diagram.remove", "{diagram, element} take an element off one diagram; it stays in the model.")
def diagram_remove(m, a, ctx):
    d = _get(m["diagrams"], a.get("diagram"), "diagram")
    _get(d["nodes"], a.get("element"), "diagram node")
    del d["nodes"][a["element"]]
    for lid in [lid for lid in d["links"] if a["element"] in (
            m["links"][lid]["source"], m["links"][lid]["target"])]:
        del d["links"][lid]


@op("diagram.link", "{diagram, link, routing?, points?, hidden?, reset?} per-diagram look of a link. "
                    "routing: straight|auto|custom; points: [[x,y],...] for custom; reset removes the override.")
def diagram_link(m, a, ctx):
    d = _get(m["diagrams"], a.get("diagram"), "diagram")
    _get(m["links"], a.get("link"), "link")
    if a.get("reset"):
        d["links"].pop(a["link"], None)
        return
    o = dict(d["links"].get(a["link"], {}))
    if "routing" in a:
        if a["routing"] is None:
            o.pop("routing", None)
        elif a["routing"] in ROUTINGS:
            o["routing"] = a["routing"]
        else:
            raise OpError("routing must be one of %s" % ", ".join(ROUTINGS))
    if "points" in a:
        pts = a["points"]
        if not isinstance(pts, list) or len(pts) > 50:
            raise OpError("'points' must be a list of [x, y]")
        clean = []
        for p in pts:
            if not isinstance(p, list) or len(p) != 2:
                raise OpError("'points' must be a list of [x, y]")
            clean.append([_int({"v": p[0]}, "v"), _int({"v": p[1]}, "v")])
        if clean:
            o["points"] = clean
        else:
            o.pop("points", None)
    if "hidden" in a:
        if a["hidden"]:
            o["hidden"] = True
        else:
            o.pop("hidden", None)
    if o:
        d["links"][a["link"]] = o
    else:
        d["links"].pop(a["link"], None)


# ---- configuration ---------------------------------------------------------

def _slug(label):
    s = re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_")
    if not s or not s[0].isalpha():
        s = "k_" + s
    return s[:30]


@op("config.put", "{kind, key?, value} kind: stereotypes|statuses|linkTypes|coverageRules. Without key a "
                  "new entry is created (key derived from the label) -> key. With key, value is merged "
                  "into the entry. Set retired:true to retire an entry.")
def config_put(m, a, ctx):
    kind, key, value = a.get("kind"), a.get("key"), a.get("value")
    if kind not in CONFIG_KINDS:
        raise OpError("kind must be one of %s" % ", ".join(CONFIG_KINDS))
    if not isinstance(value, dict):
        raise OpError("'value' must be an object")
    coll = m["config"][kind]
    if key is None:
        base = _slug(str(value.get("label") or value.get("description") or kind))
        if kind == "stereotypes":
            base = base.upper()
        key, n = base, 2
        while key in coll:
            key, n = "%s_%d" % (base, n), n + 1
        entry = dict(value)
        if kind != "coverageRules":
            entry.setdefault("retired", False)
        if kind == "stereotypes":
            entry.setdefault("fields", {})
            entry.setdefault("statuses", None)
            entry.setdefault("shape", "rect")
            entry.setdefault("icon", "")
            entry.setdefault("labelPrefix", "")
        if kind == "linkTypes":
            entry.setdefault("sources", None)
            entry.setdefault("targets", None)
        if kind == "statuses":
            entry.setdefault("symbol", "")
            entry.setdefault("order", max([s.get("order", 0) for s in coll.values()], default=0) + 10)
    else:
        if not isinstance(key, str) or key not in coll:
            raise OpError("%s entry %r does not exist" % (kind, key))
        entry = dict(coll[key])
        entry.update(value)
    errs = V.check_config_value(kind, entry, m["config"])
    if errs:
        raise OpError("; ".join(errs))
    coll[key] = entry
    if kind == "stereotypes":
        for eid, el in m["elements"].items():
            if el["stereotype"] != key:
                continue
            name = el.get("label") or eid[:8]
            if el["status"] not in V.allowed_statuses(m["config"], key, True):
                raise OpError("element %s has status '%s', which would no longer be allowed" % (name, el["status"]))
            errs = V.check_fields(m["config"], key, el.get("fields", {}))
            if errs:
                raise OpError("element %s uses a field this change would break: %s" % (name, errs[0]))
    return key


def config_usage(m, kind, key):
    """Where a configuration entry is used (REQ-CFG-07)."""
    cfg, uses = m["config"], []
    if kind == "stereotypes":
        uses += ["element %s" % (e.get("label") or i[:8]) for i, e in m["elements"].items() if e["stereotype"] == key]
        uses += ["link type %s" % lt["label"] for lt in cfg["linkTypes"].values()
                 if key in (lt.get("sources") or []) or key in (lt.get("targets") or [])]
        uses += ["coverage rule %s" % k for k, r in cfg["coverageRules"].items()
                 if key in (r.get("stereotype"), r.get("other"))]
    elif kind == "statuses":
        uses += ["element %s" % (e.get("label") or i[:8]) for i, e in m["elements"].items() if e["status"] == key]
        uses += ["stereotype %s" % st["label"] for st in cfg["stereotypes"].values() if key in (st.get("statuses") or [])]
        uses += ["coverage rule %s" % k for k, r in cfg["coverageRules"].items() if key in (r.get("statuses") or [])]
    elif kind == "linkTypes":
        uses += ["link %s" % i[:8] for i, l in m["links"].items() if l["type"] == key]
        uses += ["coverage rule %s" % k for k, r in cfg["coverageRules"].items() if r.get("linkType") == key]
    return uses


@op("config.delete", "{kind, key} refused while the entry is in use; retire it instead.")
def config_delete(m, a, ctx):
    kind, key = a.get("kind"), a.get("key")
    if kind not in CONFIG_KINDS or not isinstance(key, str) or key not in m["config"][kind]:
        raise OpError("%s entry %r does not exist" % (kind, key))
    uses = config_usage(m, kind, key)
    if uses:
        raise OpError("still in use by %d item(s) (%s%s); retire it instead" % (
            len(uses), ", ".join(uses[:3]), ", ..." if len(uses) > 3 else ""))
    del m["config"][kind][key]


# ---- users (administrators only; enforced in rules.py) ---------------------

def _key(a, name="key"):
    parts = str(a.get(name, "")).split()
    if len(parts) < 2 or not (parts[0].startswith("ssh-") or parts[0].startswith("ecdsa-")
                              or parts[0].startswith("sk-")):
        raise OpError("'%s' must be an SSH public key, e.g. 'ssh-ed25519 AAAA...'" % name)
    return "%s %s" % (parts[0], parts[1])


def _key_free(m, key):
    for name, u in m["users"].items():
        if key in u["keys"]:
            raise OpError("this key already belongs to %s" % name)


@op("user.add", "{name, key, role?} key is an SSH public key; role: user|admin.")
def user_add(m, a, ctx):
    name = a.get("name")
    if not isinstance(name, str) or not V.USERNAME.match(name):
        raise OpError("user name may contain letters, digits and . _ @ - only")
    if name in m["users"]:
        raise OpError("user %s already exists" % name)
    role = a.get("role", "user")
    if role not in V.ROLES:
        raise OpError("role must be user or admin")
    key = _key(a)
    _key_free(m, key)
    m["users"][name] = {"role": role, "keys": [key]}


@op("user.update", "{name, role?, addKey?, removeKey?}")
def user_update(m, a, ctx):
    u = _get(m["users"], a.get("name"), "user")
    if "role" in a:
        if a["role"] not in V.ROLES:
            raise OpError("role must be user or admin")
        u["role"] = a["role"]
    if "addKey" in a:
        key = _key(a, "addKey")
        _key_free(m, key)
        u["keys"].append(key)
    if "removeKey" in a:
        key = _key(a, "removeKey")
        if key not in u["keys"]:
            raise OpError("user does not have this key")
        u["keys"].remove(key)
    if not any(x["role"] == "admin" and x["keys"] for x in m["users"].values()):
        raise OpError("there must remain an administrator with a key")


@op("user.remove", "{name}")
def user_remove(m, a, ctx):
    name = a.get("name")
    _get(m["users"], name, "user")
    if any((f.get("lock") or {}).get("owner") == name for f in m["folders"].values()):
        raise OpError("user still owns folder locks; unlock them first")
    del m["users"][name]
    if not any(x["role"] == "admin" and x["keys"] for x in m["users"].values()):
        raise OpError("there must remain an administrator with a key")


# ---- merge conflicts -------------------------------------------------------

@op("conflict.resolve", "{index, choice} choice: ours|theirs. Resolves one merge conflict.")
def conflict_resolve(m, a, ctx):
    conflicts = m.get("conflicts") or []
    i = a.get("index")
    if isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < len(conflicts):
        raise OpError("no such conflict")
    if a.get("choice") not in ("ours", "theirs"):
        raise OpError("choice must be ours or theirs")
    c = conflicts.pop(i)
    side, path, node = c[a["choice"]], c["path"], m
    for key in path[:-1]:
        node = node.setdefault(key, {})
    if side["present"]:
        node[path[-1]] = side["value"]
    else:
        node.pop(path[-1], None)
    if not conflicts:
        m.pop("conflicts", None)


def _core(el):
    """The element record itself: without its stamp of change and its place in the explorer."""
    return {k: v for k, v in el.items() if k not in ("modified", "order")} if isinstance(el, dict) else el


def upgrade(m, by, at):
    """Format 1 -> 2 (ADR-016): elements without an author get `by` and `at`."""
    for el in m.get("elements", {}).values():
        if isinstance(el, dict) and not el.get("modified"):
            el["modified"] = {"at": at, "by": by}
    m["formatVersion"] = FORMAT_VERSION


def touch(old, new, actor):
    """ADR-016: every element whose record differs gets the actor and the time."""
    at = now_iso()
    for eid, el in new["elements"].items():
        before = old.get("elements", {}).get(eid)
        if before is None or _core(before) != _core(el):
            el["modified"] = {"at": at, "by": actor}


def apply_ops(model, ops, actor):
    """Apply a batch atomically. '$N' in arguments refers to the id returned by op N."""
    m = clone(model)
    last = model.get("stamp") or {}
    upgrade(m, last.get("user") or actor, last.get("at") or now_iso())
    results, ctx = [], {"actor": actor}
    if not isinstance(ops, list) or not ops:
        raise OpError("expected a non-empty list of operations")

    def subst(v):
        if isinstance(v, str) and re.match(r"^\$\d+$", v):
            i = int(v[1:])
            if i >= len(results) or results[i] is None:
                raise OpError("%s does not refer to an earlier created item" % v)
            return results[i]
        if isinstance(v, dict):
            return {k: subst(x) for k, x in v.items()}
        if isinstance(v, list):
            return [subst(x) for x in v]
        return v

    for i, o in enumerate(ops):
        if not isinstance(o, dict) or o.get("op") not in OPS:
            raise OpError("operation %d: unknown op %r" % (i, o.get("op") if isinstance(o, dict) else o))
        args = o.get("args", {})
        if not isinstance(args, dict):
            raise OpError("operation %d: args must be an object" % i)
        try:
            results.append(OPS[o["op"]](m, subst(args), ctx))
        except OpError as exc:
            raise OpError("%s: %s" % (o["op"], exc))
        except (KeyError, TypeError, AttributeError) as exc:
            raise OpError("%s: the model is damaged here (%r); run validate" % (o["op"], exc))
    touch(model, m, actor)
    return m, results
