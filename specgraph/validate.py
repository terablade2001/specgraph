"""Model validation (REQ-INT-04): structure, references, configuration rules."""
import re
from datetime import date

from .defaults import SHAPES, LINE_STYLES, ARROWS, ROUTINGS, FIELD_TYPES
from .model import COLLECTIONS, CONFIG_KINDS

COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
USERNAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]{0,63}$")
ROLES = ("admin", "user")


def traceable(link_type):
    """REQ-TRC-02: optional flag, a missing value means yes."""
    return link_type.get("traceable", True) is not False


def allowed_statuses(config, st_key, include_retired=False):
    statuses = config["statuses"]
    allowed = (config["stereotypes"].get(st_key) or {}).get("statuses")
    keys = [k for k in statuses if allowed is None or k in allowed]
    if not include_retired:
        keys = [k for k in keys if not statuses[k].get("retired")]
    return sorted(keys, key=lambda k: (statuses[k].get("order", 0), k))


def _is_str(v, max_len=200):
    return isinstance(v, str) and len(v) <= max_len


def _key_list(v, pool):
    return v is None or (isinstance(v, list) and all(k in pool for k in v))


def check_config_value(kind, value, config):
    """Return a list of problems with one configuration entry."""
    errs = []
    if not isinstance(value, dict):
        return ["entry must be an object"]

    def need(cond, msg):
        if not cond:
            errs.append(msg)

    if kind != "coverageRules":
        need(_is_str(value.get("label")) and value.get("label", "").strip(), "label is required")
        need(isinstance(value.get("retired", False), bool), "retired must be true/false")
    if kind == "stereotypes":
        need(COLOR.match(str(value.get("fill", ""))), "fill must be a colour like #aabbcc")
        need(COLOR.match(str(value.get("border", ""))), "border must be a colour like #aabbcc")
        need(_is_str(value.get("icon", ""), 4), "icon must be at most 4 characters")
        need(value.get("shape", "rect") in SHAPES, "shape must be one of %s" % ", ".join(SHAPES))
        need(_is_str(value.get("labelPrefix", ""), 12), "labelPrefix too long")
        need(_key_list(value.get("statuses"), config["statuses"]), "statuses must be existing status keys")
        fields = value.get("fields", {})
        if not isinstance(fields, dict):
            errs.append("fields must be an object")
        else:
            for fkey, f in fields.items():
                if not KEY.match(fkey) or not isinstance(f, dict):
                    errs.append("field key %r is invalid" % fkey)
                    continue
                need(_is_str(f.get("label")), "field %s: label is required" % fkey)
                need(f.get("type") in FIELD_TYPES, "field %s: type must be one of %s" % (fkey, ", ".join(FIELD_TYPES)))
                if f.get("type") == "enum":
                    opts = f.get("options")
                    need(isinstance(opts, list) and opts and all(_is_str(o) for o in opts),
                         "field %s: enum needs a list of options" % fkey)
    elif kind == "statuses":
        need(COLOR.match(str(value.get("color", ""))), "color must be a colour like #aabbcc")
        need(_is_str(value.get("symbol", ""), 4), "symbol must be at most 4 characters")
        need(isinstance(value.get("order", 0), int), "order must be a whole number")
    elif kind == "linkTypes":
        need(value.get("lineStyle") in LINE_STYLES, "lineStyle must be one of %s" % ", ".join(LINE_STYLES))
        need(COLOR.match(str(value.get("color", ""))), "color must be a colour like #aabbcc")
        need(value.get("sourceArrow") in ARROWS, "sourceArrow must be one of %s" % ", ".join(ARROWS))
        need(value.get("targetArrow") in ARROWS, "targetArrow must be one of %s" % ", ".join(ARROWS))
        need(isinstance(value.get("showLabel"), bool), "showLabel must be true/false")
        need(value.get("routing") in ROUTINGS, "routing must be one of %s" % ", ".join(ROUTINGS))
        need(isinstance(value.get("traceable", True), bool), "traceable must be true/false")
        need(_key_list(value.get("sources"), config["stereotypes"]), "sources must be existing stereotype keys")
        need(_key_list(value.get("targets"), config["stereotypes"]), "targets must be existing stereotype keys")
    elif kind == "coverageRules":
        need(_is_str(value.get("description", ""), 500), "description must be text")
        need(value.get("stereotype") in config["stereotypes"], "stereotype must exist")
        need(_key_list(value.get("statuses"), config["statuses"]), "statuses must be existing status keys")
        need(value.get("linkType") in config["linkTypes"], "linkType must exist")
        need(value.get("direction") in ("incoming", "outgoing"), "direction must be incoming or outgoing")
        need(value.get("other") is None or value.get("other") in config["stereotypes"],
             "other must be a stereotype key or null")
    return errs


def check_field_value(fdef, value):
    t = fdef.get("type")
    if t in ("string", "text"):
        return isinstance(value, str)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "boolean":
        return isinstance(value, bool)
    if t == "enum":
        return value in (fdef.get("options") or [])
    if t == "date":
        try:
            date.fromisoformat(value)
            return isinstance(value, str) and len(value) == 10
        except (TypeError, ValueError):
            return False
    return False


def check_fields(config, st_key, fields):
    """Validate an element's custom fields against its stereotype (REQ-CFG-04)."""
    errs = []
    defs = (config["stereotypes"].get(st_key) or {}).get("fields", {})
    if not isinstance(fields, dict):
        return ["fields must be an object"]
    for key, value in fields.items():
        if key not in defs:
            errs.append("unknown field %r for stereotype %s" % (key, st_key))
        elif not check_field_value(defs[key], value):
            errs.append("field %r: %r is not a valid %s" % (key, value, defs[key].get("type")))
    return errs


def link_allowed(config, type_key, src_st, dst_st):
    """REQ-LNK-03."""
    lt = config["linkTypes"].get(type_key) or {}
    if lt.get("sources") is not None and src_st not in lt["sources"]:
        return False
    if lt.get("targets") is not None and dst_st not in lt["targets"]:
        return False
    return True


def coverage_violations(model):
    """REQ-TRC-05. Returns [(rule_key, element_id, message)]."""
    out = []
    cfg = model["config"]
    for rkey, rule in sorted(cfg.get("coverageRules", {}).items()):
        for eid, el in sorted(model["elements"].items()):
            if el.get("stereotype") != rule.get("stereotype"):
                continue
            if rule.get("statuses") is not None and el.get("status") not in rule["statuses"]:
                continue
            ok = False
            for link in model["links"].values():
                if link.get("type") != rule.get("linkType"):
                    continue
                mine, other = ("target", "source") if rule.get("direction") == "incoming" else ("source", "target")
                if link.get(mine) != eid:
                    continue
                oel = model["elements"].get(link.get(other))
                if oel and (rule.get("other") is None or oel.get("stereotype") == rule["other"]):
                    ok = True
                    break
            if not ok:
                out.append((rkey, eid, "%s violates coverage rule: %s" % (
                    el.get("label") or eid[:8], rule.get("description") or rkey)))
    return out


def validate(model):
    """Return a list of {level, code, message, ref}. level is error or warning."""
    out = []

    def err(code, message, ref=None):
        out.append({"level": "error", "code": code, "message": message, "ref": ref})

    for name in COLLECTIONS + ("users", "config", "settings"):
        if not isinstance(model.get(name), dict):
            err("structure", "'%s' must be an object" % name)
    cfg = model.get("config")
    if out or any(not isinstance(cfg.get(k), dict) for k in CONFIG_KINDS):
        if not out:
            err("structure", "config must contain %s" % ", ".join(CONFIG_KINDS))
        return out
    users, folders, elements = model["users"], model["folders"], model["elements"]
    links, diagrams = model["links"], model["diagrams"]

    for kind in CONFIG_KINDS:
        for key, value in cfg[kind].items():
            if not KEY.match(key):
                err("config", "%s key %r is invalid" % (kind, key), key)
            for msg in check_config_value(kind, value, cfg):
                err("config", "%s %s: %s" % (kind, key, msg), key)
    if any(p["code"] == "config" for p in out):
        return out

    for name, u in users.items():
        if not USERNAME.match(name) or not isinstance(u, dict) or u.get("role") not in ROLES \
                or not isinstance(u.get("keys"), list) or not all(isinstance(k, str) for k in u["keys"]):
            err("user", "user %r is malformed" % name, name)
    if users and not any(isinstance(u, dict) and u.get("role") == "admin" for u in users.values()):
        err("user", "there is no administrator")

    for fid, f in folders.items():
        if not isinstance(f, dict) or not _is_str(f.get("name")) or not f.get("name"):
            err("folder", "folder %s is malformed" % fid, fid)
            continue
        if f.get("parent") is not None and f["parent"] not in folders:
            err("reference", "folder '%s' has a missing parent" % f["name"], fid)
        seen, cur = set(), fid
        while cur is not None and cur in folders:
            if cur in seen:
                err("folder", "folder '%s' is part of a cycle" % f["name"], fid)
                break
            seen.add(cur)
            cur = folders[cur].get("parent") if isinstance(folders[cur], dict) else None
        lock = f.get("lock")
        if lock is not None and (not isinstance(lock, dict) or lock.get("owner") not in users):
            err("lock", "folder '%s' has a lock without a known owner" % f["name"], fid)

    labels = {}
    for eid, el in elements.items():
        if not isinstance(el, dict) or not isinstance(el.get("topic"), str) \
                or not isinstance(el.get("notes", ""), str):
            err("element", "element %s is malformed" % eid, eid)
            continue
        name = el.get("label") or el["topic"] or eid[:8]
        st = el.get("stereotype")
        if st not in cfg["stereotypes"]:
            err("reference", "element '%s' has unknown stereotype %r" % (name, st), eid)
        elif el.get("status") not in allowed_statuses(cfg, st, include_retired=True):
            err("status", "element '%s' has status %r, which %s does not allow" % (name, el.get("status"), st), eid)
        else:
            for msg in check_fields(cfg, st, el.get("fields", {})):
                err("field", "element '%s': %s" % (name, msg), eid)
        if el.get("folder") not in folders:
            err("reference", "element '%s' is in a missing folder" % name, eid)
        if el.get("label"):
            labels.setdefault(el["label"], []).append(eid)
        mod = el.get("modified")
        if model.get("formatVersion", 1) >= 2 and not (
                isinstance(mod, dict) and isinstance(mod.get("at"), str) and mod["at"]
                and isinstance(mod.get("by"), str) and mod["by"].strip()):
            err("element", "element '%s' has no author and date ('modified')" % name, eid)
    for label, ids in labels.items():
        if len(ids) > 1:
            for eid in ids:
                err("label", "label '%s' is used by %d elements" % (label, len(ids)), eid)

    seen_links = {}
    for lid, l in links.items():
        if not isinstance(l, dict):
            err("link", "link %s is malformed" % lid, lid)
            continue
        s, t = elements.get(l.get("source")), elements.get(l.get("target"))
        if l.get("type") not in cfg["linkTypes"]:
            err("reference", "link %s has unknown type %r" % (lid[:8], l.get("type")), lid)
        if not isinstance(s, dict) or not isinstance(t, dict):
            err("reference", "link %s points to a missing element" % lid[:8], lid)
        elif l.get("type") in cfg["linkTypes"] and not link_allowed(
                cfg, l["type"], s.get("stereotype"), t.get("stereotype")):
            err("link", "link type '%s' may not connect %s to %s" % (
                cfg["linkTypes"][l["type"]]["label"], s.get("stereotype"), t.get("stereotype")), lid)
        sig = (l.get("type"), l.get("source"), l.get("target"))
        if sig in seen_links:
            err("link", "duplicate link %s (same type and ends as %s)" % (lid[:8], seen_links[sig][:8]), lid)
        seen_links[sig] = lid

    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    for did, d in diagrams.items():
        if not isinstance(d, dict) or not _is_str(d.get("name")) or not isinstance(d.get("nodes"), dict) \
                or not isinstance(d.get("links"), dict):
            err("diagram", "diagram %s is malformed" % did, did)
            continue
        if d.get("folder") not in folders:
            err("reference", "diagram '%s' is in a missing folder" % d["name"], did)
        for eid, n in d["nodes"].items():
            if eid not in elements:
                err("reference", "diagram '%s' shows a missing element %s" % (d["name"], eid[:8]), did)
            if not isinstance(n, dict) or not all(num(n.get(k)) for k in ("x", "y", "w", "h")):
                err("diagram", "diagram '%s' has a bad layout for %s" % (d["name"], eid[:8]), did)
        for lid, o in d["links"].items():
            if lid not in links:
                err("reference", "diagram '%s' styles a missing link %s" % (d["name"], lid[:8]), did)
            pts = o.get("points", []) if isinstance(o, dict) else None
            if pts is None or o.get("routing", "auto") not in ROUTINGS or not isinstance(pts, list) \
                    or not all(isinstance(p, list) and len(p) == 2 and num(p[0]) and num(p[1]) for p in pts):
                err("diagram", "diagram '%s' has a bad link override %s" % (d["name"], lid[:8]), did)

    branch = model["settings"].get("branch", "")
    if not isinstance(branch, str):
        err("settings", "settings.branch must be text")

    for i, c in enumerate(model.get("conflicts", []) or []):
        err("conflict", "unresolved merge conflict at %s" % "/".join(map(str, c.get("path", []))), i)

    if not any(p["level"] == "error" for p in out):
        for rkey, eid, msg in coverage_violations(model):
            out.append({"level": "warning", "code": "coverage", "message": msg, "ref": eid})
    return out


def errors(model):
    return [p for p in validate(model) if p["level"] == "error"]
