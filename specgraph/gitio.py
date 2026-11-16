"""Thin wrapper around the git command line (git is the only external program
besides ssh-keygen, which ships with it)."""
import os
import subprocess


class GitError(Exception):
    pass


def git(cwd, *args, check=True, input_=None):
    try:
        p = subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, input=input_,
                           stdin=None if input_ is not None else subprocess.DEVNULL)
    except OSError as exc:
        raise GitError("cannot run git: %s" % exc)
    if check and p.returncode != 0:
        raise GitError("git %s failed: %s" % (" ".join(args), p.stderr.decode("utf-8", "replace").strip()))
    return p.returncode, p.stdout.decode("utf-8", "replace")


def repo_root(cwd):
    code, out = git(cwd, "rev-parse", "--show-toplevel", check=False)
    return out.strip() if code == 0 and out.strip() else None


def config_get(root, key):
    code, out = git(root or os.getcwd(), "config", "--get", key, check=False)
    return out.strip() if code == 0 else None


def show(root, spec):
    """Content of e.g. 'HEAD:path' or ':1:path', or None when it does not exist."""
    code, out = git(root, "show", spec, check=False)
    return out if code == 0 else None


def rel_path(root, path):
    return os.path.relpath(os.path.abspath(path), root).replace(os.sep, "/")
