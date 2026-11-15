"""Command line: the interface for people's terminals, git hooks and AI agents."""
import argparse
import json
import os
import sys

from . import TOOL_NAME, VERSION, DEFAULT_UNDO
from . import audit as A, gitio, history as H, hooks, merge as MG, model as M
from . import ops as O, query as Q, stamp as S, validate as V
from .store import Store, StoreError


def _out(obj):
    sys.stdout.write(json.dumps(obj, indent=1, ensure_ascii=False, sort_keys=True) + "\n")


def _resolve_id(model, ref):
    """Accept a full id, a unique id prefix, or a label."""
    els = model["elements"]
    if ref in els:
        return ref
    hits = [i for i, e in els.items() if e.get("label") == ref] or \
           [i for i in els if i.startswith(ref.lower())]
    if len(hits) != 1:
        raise StoreError("%r matches %d elements" % (ref, len(hits)))
    return hits[0]


def cmd_init(store, a):
    name = a.user or (gitio.config_get(store.root, "user.name") or "").strip().replace(" ", ".")
    store.init(name)
    print("created %s with administrator '%s'" % (store.path, name))


def cmd_serve(store, a):
    from .server import serve
    try:
        undo = a.undo if a.undo is not None else int(os.environ.get("SPECGRAPH_UNDO") or DEFAULT_UNDO)
    except ValueError:
        raise StoreError("SPECGRAPH_UNDO must be a whole number")
    serve(store, a.port, not a.no_browser, undo)


def cmd_whoami(store, a):
    model = store.load()
    info = store.me(model)
    try:
        info["key"] = S.resolve_key(store.key(), model)
    except S.IdentityError:
        info["key"] = None
    _out(info)


def cmd_apply(store, a):
    text = a.ops if a.ops else sys.stdin.read()
    try:
        ops = json.loads(text)
    except ValueError as exc:
        raise StoreError("operations are not valid JSON: %s" % exc)
    if isinstance(ops, dict):
        ops = [ops]
    if any(isinstance(o, dict) and o.get("op") == "element.delete" for o in ops) and not a.yes:
        model = store.load()
        for o in ops:
            if o.get("op") == "element.delete" and (o.get("args") or {}).get("id") in model["elements"]:
                _out({"confirm": "element.delete needs --yes", "usage": Q.usage(model, o["args"]["id"])})
        return 3
    if not a.yes:
        found = store.foreign_unlocks(store.load(), ops)
        if found:
            _out({"confirm": "unlocking another user's lock needs --yes", "locks": found})
            return 3
    model, results = store.apply(ops)
    _out({"ok": True, "results": results, "stamp": model["stamp"]["id"]})


def cmd_ops(store, a):
    for name in sorted(O.OPS):
        print("%-18s %s" % (name, O.OPS[name].doc))


def cmd_show(store, a):
    model = store.load()
    eid = _resolve_id(model, a.id)
    _out(dict(model["elements"][eid], id=eid, usage=Q.usage(model, eid)))


def cmd_search(store, a):
    _out(Q.search(store.load(), a.query, a.stereotype, a.status, a.folder, a.unused))


def cmd_trace(store, a):
    model = store.load()
    _out(Q.trace(model, _resolve_id(model, a.id), a.depth))


def cmd_impact(store, a):
    model = store.load()
    _out(Q.impact(model, _resolve_id(model, a.id)))


def cmd_matrix(store, a):
    _out(Q.matrix(store.load(), a.rows, a.cols, a.types.split(",") if a.types else None))


def cmd_history(store, a):
    model = store.load()
    _out(H.element_history(store, _resolve_id(model, a.id)))


def cmd_validate(store, a):
    model = store.load()
    problems = V.validate(model)
    for p in problems:
        print("%s [%s] %s" % (p["level"].upper(), p["code"], p["message"]))
    print("%d error(s), %d warning(s)" % (sum(p["level"] == "error" for p in problems),
                                          sum(p["level"] == "warning" for p in problems)))
    return 1 if any(p["level"] == "error" for p in problems) else 0


def cmd_check(store, a):
    """validation + integrity + locks + identity, for the hooks."""
    if a.staged:
        if not store.root:
            raise StoreError("not inside a git repository")
        findings, notes = A.check_staged(store)
    else:
        with open(store.path, "r", encoding="utf-8") as fh:
            text = fh.read()
        head = gitio.show(store.root, "HEAD:" + gitio.rel_path(store.root, store.path)) if store.root else None
        findings, notes = A.check_version(text, [head])
    for n in notes:
        print("note: " + n)
    for f in findings:
        print("%s: %s" % (TOOL_NAME, f), file=sys.stderr)
    if findings:
        print("%s: %d problem(s); nothing was committed" % (TOOL_NAME, len(findings)), file=sys.stderr)
        return 1
    if not a.staged:
        print("ok")
    return 0


def cmd_audit(store, a):
    if not store.root:
        raise StoreError("not inside a git repository")
    report = A.audit_history(store, a.rev, a.since)
    bad = 0
    for e in report:
        if e["findings"]:
            bad += 1
        if a.quiet and not e["findings"]:
            continue
        print("%s %s %s  %s" % ("FAIL" if e["findings"] else "ok  ", e["commit"][:10], e["date"][:10], e["author"]))
        for f in e["findings"]:
            print("      " + f)
        for n in e["notes"]:
            print("      note: " + n)
    if not a.quiet or bad:
        print("%d commit(s) checked, %d with findings" % (len(report), bad))
    return 1 if bad else 0


def cmd_install_hooks(store, a):
    for line in hooks.install(store, a.force):
        print(line)


def cmd_merge_driver(store, a):
    try:
        texts = []
        for p in (a.base, a.ours, a.theirs):
            with open(p, "r", encoding="utf-8") as fh:
                texts.append(fh.read())
        merged, conflicts, errs = MG.merge_texts(texts[0], texts[1], texts[2], store.key())
    except (M.ModelError, S.IdentityError, OSError) as exc:
        print("%s: cannot merge model: %s" % (TOOL_NAME, exc), file=sys.stderr)
        return 2
    M.save(a.ours, merged)
    return _merge_report(conflicts, errs)


def _merge_report(conflicts, errs):
    for c in conflicts:
        print("%s: CONFLICT at %s" % (TOOL_NAME, "/".join(map(str, c["path"]))), file=sys.stderr)
    for e in errs:
        print("%s: after merge: %s" % (TOOL_NAME, e["message"]), file=sys.stderr)
    if conflicts or errs:
        print("%s: open the tool, settle these under 'Check', then git add and commit" % TOOL_NAME, file=sys.stderr)
        return 1
    return 0


def cmd_resolve(store, a):
    conflicts, errs = MG.resolve_from_index(store)
    print("model rebuilt from both sides")
    return _merge_report(conflicts, errs)


def cmd_adopt(store, a):
    store.adopt()
    print("content adopted and stamped")


def build_parser():
    p = argparse.ArgumentParser(prog=TOOL_NAME, description="%s %s - requirements model in one JSON file" % (TOOL_NAME, VERSION))
    p.add_argument("--file", help="model file (default: <repo root>/specmodel.json)")
    p.add_argument("--version", action="version", version="%s %s" % (TOOL_NAME, VERSION))
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(fn=fn)
        return sp

    sp = add("init", cmd_init, "create a new model; you become administrator")
    sp.add_argument("--user", help="your user name (default: git user.name)")
    sp = add("serve", cmd_serve, "start the editor in your browser")
    sp.add_argument("--port", type=int, default=8765)
    sp.add_argument("--no-browser", action="store_true")
    sp.add_argument("--undo", type=int, metavar="N", help="undo steps kept by the editor "
                    "(default: SPECGRAPH_UNDO or %d; 0 = off)" % DEFAULT_UNDO)
    add("whoami", cmd_whoami, "show which user your SSH key maps to")
    sp = add("apply", cmd_apply, "apply operations (JSON list) - the write path for agents")
    sp.add_argument("ops", nargs="?", help="JSON; read from stdin when omitted")
    sp.add_argument("--yes", action="store_true", help="confirm element.delete and unlocking another user's lock")
    add("ops", cmd_ops, "list all operations and their arguments")
    sp = add("show", cmd_show, "show one element and where it is used")
    sp.add_argument("id", help="id, id prefix or label")
    sp = add("search", cmd_search, "search elements")
    sp.add_argument("query", nargs="?", default="")
    sp.add_argument("--stereotype")
    sp.add_argument("--status")
    sp.add_argument("--folder", help="folder id")
    sp.add_argument("--unused", action="store_true", help="only elements on no diagram")
    sp = add("trace", cmd_trace, "traceability of an element, both directions")
    sp.add_argument("id")
    sp.add_argument("--depth", type=int)
    sp = add("impact", cmd_impact, "everything depending on an element")
    sp.add_argument("id")
    sp = add("matrix", cmd_matrix, "traceability matrix")
    sp.add_argument("rows")
    sp.add_argument("cols")
    sp.add_argument("--types", help="comma separated link type keys")
    sp = add("history", cmd_history, "change history of an element from git")
    sp.add_argument("id")
    add("validate", cmd_validate, "validate the model")
    sp = add("check", cmd_check, "all checks on the working or staged file (used by hooks)")
    sp.add_argument("--staged", action="store_true")
    sp = add("audit", cmd_audit, "check every commit of the branch history")
    sp.add_argument("--rev", default="HEAD")
    sp.add_argument("--since", help="only commits after this revision")
    sp.add_argument("--quiet", action="store_true")
    sp = add("install-hooks", cmd_install_hooks, "one-time setup of hooks and merge driver for this clone")
    sp.add_argument("--force", action="store_true")
    sp = add("merge-driver", cmd_merge_driver, "(called by git)")
    sp.add_argument("base")
    sp.add_argument("ours")
    sp.add_argument("theirs")
    add("resolve", cmd_resolve, "rebuild the model after a git merge conflict")
    add("adopt", cmd_adopt, "accept a change made outside the tool, under your name")
    return p


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    a = build_parser().parse_args(argv)
    try:
        store = Store(a.file)
        return a.fn(store, a) or 0
    except (StoreError, M.ModelError, gitio.GitError, S.IdentityError) as exc:
        print("%s: %s" % (TOOL_NAME, exc), file=sys.stderr)
        return 2
