"""One-time setup per clone (REQ-CHK-02): git hooks + merge driver."""
import os
import stat
import sys

from . import TOOL_NAME
from . import gitio, model as M

MARK = "# managed by %s" % TOOL_NAME


def _script():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sg.py")


def _cmd(store):
    script = _script()
    try:
        rel = os.path.relpath(script, store.root)
        if not rel.startswith(".."):
            script = rel.replace(os.sep, "/")
    except ValueError:
        pass
    return '"%s" "%s"' % (sys.executable.replace("\\", "/"), script.replace("\\", "/"))


def install(store, force=False):
    if not store.root:
        raise gitio.GitError("not inside a git repository")
    rel = gitio.rel_path(store.root, store.path)
    cmd = _cmd(store)
    _, hooks_dir = gitio.git(store.root, "rev-parse", "--git-path", "hooks")
    hooks_dir = os.path.join(store.root, hooks_dir.strip())
    os.makedirs(hooks_dir, exist_ok=True)
    done = []
    bodies = {
        "pre-commit": '%s --file "%s" check --staged || exit 1\n' % (cmd, rel),
        "pre-push": '%s --file "%s" audit --quiet --push "$1" || {\n  echo "%s: push blocked, see findings above" >&2\n  exit 1\n}\n' % (cmd, rel, TOOL_NAME),
    }
    for name, body in bodies.items():
        path = os.path.join(hooks_dir, name)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                if MARK not in fh.read() and not force:
                    done.append("SKIPPED %s: a hook already exists (use --force to replace it)" % name)
                    continue
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("#!/bin/sh\n%s\n%s" % (MARK, body))
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        done.append("installed %s hook" % name)
    gitio.git(store.root, "config", "merge.%s.name" % TOOL_NAME, "%s model merge" % TOOL_NAME)
    gitio.git(store.root, "config", "merge.%s.driver" % TOOL_NAME, "%s merge-driver %%O %%A %%B" % cmd)
    done.append("configured merge driver")
    attr = os.path.join(store.root, ".gitattributes")
    lines = [("%s text eol=lf merge=%s" % (rel, TOOL_NAME), "added merge rule to .gitattributes (commit this file)"),
             ("%s text eol=lf merge=union" % M.deleted_path(rel), "added the deleted-elements log to .gitattributes")]
    for line, note in lines:
        existing = ""
        if os.path.exists(attr):
            with open(attr, "r", encoding="utf-8") as fh:
                existing = fh.read()
        if line not in existing.splitlines():
            with open(attr, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(("" if not existing or existing.endswith("\n") else "\n") + line + "\n")
            done.append(note)
    return done
