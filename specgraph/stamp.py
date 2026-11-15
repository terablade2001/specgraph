"""Change stamps and identity (REQ-INT-01/02, REQ-USR-01/02).

Identity = an SSH key the team member already has, loaded in ssh-agent. A user is a
name plus public keys in the model file. Each change is stamped {id, user, at, tool,
version, op, contentHash} and the stamp is signed by the agent through
`ssh-keygen -Y sign` (part of OpenSSH, which is installed with Git). The tool never
reads a private key file and never asks for a passphrase (ADR-021).
"""
import os
import shutil
import subprocess
import tempfile

from . import TOOL_NAME, VERSION, SIG_NAMESPACE
from .model import canonical, content_hash, new_id
from .ops import now_iso


class IdentityError(Exception):
    pass


def ssh_keygen():
    exe = os.environ.get("SPECGRAPH_SSH_KEYGEN") or shutil.which("ssh-keygen")
    if not exe:
        git_exe = shutil.which("git")
        if git_exe:  # Git for Windows keeps it under <git>/usr/bin
            base = os.path.dirname(os.path.dirname(os.path.abspath(git_exe)))
            for cand in (os.path.join(base, "usr", "bin", "ssh-keygen.exe"),
                         os.path.join(os.path.dirname(base), "usr", "bin", "ssh-keygen.exe")):
                if os.path.exists(cand):
                    exe = cand
                    break
    if not exe:
        raise IdentityError("ssh-keygen was not found. It is installed with Git/OpenSSH; "
                            "set SPECGRAPH_SSH_KEYGEN to its path.")
    return exe


def _run(args, input_=None, exe=None):
    try:
        return subprocess.run([exe or ssh_keygen()] + args, capture_output=True, input=input_,
                              stdin=None if input_ is not None else subprocess.DEVNULL, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise IdentityError("cannot run ssh-keygen: %s" % exc)


def ssh_add():
    exe = os.environ.get("SPECGRAPH_SSH_ADD")
    if not exe:
        here = os.path.dirname(ssh_keygen())
        for name in ("ssh-add", "ssh-add.exe"):
            cand = os.path.join(here, name)
            if os.path.exists(cand):
                exe = cand
                break
    exe = exe or shutil.which("ssh-add")
    if not exe:
        raise IdentityError("ssh-add was not found. It is installed with Git/OpenSSH; "
                            "set SPECGRAPH_SSH_ADD to its path.")
    return exe


def norm_key(text):
    parts = text.split()
    return "%s %s" % (parts[0], parts[1]) if len(parts) >= 2 else ""


AGENT_HELP = ("Start the agent and load your key (Git Bash: eval \"$(ssh-agent -s)\" then ssh-add), "
              "or on Windows start the 'OpenSSH Authentication Agent' service and run ssh-add.")


def agent_keys():
    """Public keys currently loaded in ssh-agent."""
    p = _run(["-L"], exe=ssh_add())
    out = p.stdout.decode("utf-8", "replace")
    if p.returncode == 2 or "authentication agent" in p.stderr.decode("utf-8", "replace"):
        raise IdentityError("cannot reach ssh-agent. " + AGENT_HELP)
    keys = [norm_key(line) for line in out.splitlines() if line.startswith(("ssh-", "ecdsa-", "sk-"))]
    if not keys:
        raise IdentityError("no key is loaded in ssh-agent. Load yours with: ssh-add")
    return keys


def agent_key():
    """The one key loaded in ssh-agent. Zero or several is an error: the tool never guesses."""
    loaded = agent_keys()
    if len(loaded) != 1:
        raise IdentityError("%d keys are loaded in ssh-agent, but exactly one is required. Unload all "
                            "with ssh-add -D, then load only yours with ssh-add" % len(loaded))
    return loaded[0]


def public_key(key):
    """Public key text for `key`: the key text itself, or a .pub file (a private key
    path is read through its .pub sibling). None is the one key in ssh-agent."""
    if key is None:
        return agent_key()
    if key.startswith(("ssh-", "ecdsa-", "sk-")):
        return norm_key(key)
    path = key if key.endswith(".pub") else key + ".pub"
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as fh:
            found = norm_key(fh.read())
        if found:
            return found
    raise IdentityError("cannot read the public key %s" % key)


def resolve_key(key, model=None, user=None):
    """Public key to act with: the one key in ssh-agent. `key` (public key text or .pub file)
    is a programmatic choice for tests and tools; neither the command line nor an environment
    variable sets it."""
    return public_key(key)


def user_of_key(model, pub):
    for name, u in model.get("users", {}).items():
        if pub in [norm_key(k) for k in u.get("keys", [])]:
            return name
    return None


def whoami(model, key=None):
    pub = resolve_key(key, model)
    name = user_of_key(model, pub)
    if not name:
        raise IdentityError("your SSH key is not registered in this model. Ask an administrator "
                            "to add you:  user.add {name, key: \"%s\"}" % pub)
    return name


def sign(key, message):
    """Sign through ssh-agent; `key` is the public key to sign with."""
    pub = public_key(key)
    with tempfile.TemporaryDirectory() as tmp:
        msg, pubfile = os.path.join(tmp, "msg"), os.path.join(tmp, "key.pub")
        with open(msg, "wb") as fh:
            fh.write(message)
        with open(pubfile, "w", encoding="ascii") as fh:
            fh.write(pub + "\n")
        p = _run(["-Y", "sign", "-f", pubfile, "-n", SIG_NAMESPACE, msg])
        if p.returncode != 0 or not os.path.exists(msg + ".sig"):
            raise IdentityError("signing failed: %s (is your key loaded in ssh-agent? ssh-add -l)"
                                % p.stderr.decode("utf-8", "replace").strip())
        with open(msg + ".sig", "r", encoding="ascii") as fh:
            return fh.read().strip()


def verify(users, name, message, sig):
    """True when `sig` over `message` was made by one of `name`'s keys."""
    user = users.get(name) if isinstance(users, dict) else None
    if not user or not isinstance(sig, str) or not user.get("keys"):
        return False
    with tempfile.TemporaryDirectory() as tmp:
        allowed, sigfile = os.path.join(tmp, "allowed"), os.path.join(tmp, "sig")
        with open(allowed, "w", encoding="utf-8", newline="\n") as fh:
            for key in user["keys"]:
                fh.write('%s namespaces="%s" %s\n' % (name, SIG_NAMESPACE, norm_key(key)))
        with open(sigfile, "w", encoding="ascii", errors="replace", newline="\n") as fh:
            fh.write(sig + "\n")
        p = _run(["-Y", "verify", "-f", allowed, "-I", name, "-n", SIG_NAMESPACE, "-s", sigfile],
                 input_=message)
        return p.returncode == 0


def stamp_message(stamp):
    return canonical({k: v for k, v in stamp.items() if k != "sig"}).encode("utf-8")


def make_stamp(model, user, key, op, prev):
    """Stamp `model` in place (replacing any old stamp) and return it."""
    model.pop("stamp", None)
    st = {"id": new_id(), "user": user, "at": now_iso(), "tool": TOOL_NAME, "toolVersion": VERSION,
          "op": op, "prev": [p for p in prev if p], "contentHash": content_hash(model)}
    st["sig"] = sign(resolve_key(key, model, user), stamp_message(st))
    model["stamp"] = st
    return st


def check_integrity(model, trusted_users=None):
    """Problems with the stamp ([] = intact). `trusted_users` is the user list
    to verify against: the previous committed version's when available."""
    st = model.get("stamp")
    if not isinstance(st, dict) or not isinstance(st.get("contentHash"), str):
        return ["the file has no change stamp: it was not written by the tool"]
    if st["contentHash"] != content_hash(model):
        return ["the content does not match its stamp: the file was changed outside the tool "
                "(last stamp: %s by %s)" % (st.get("at"), st.get("user"))]
    users = trusted_users if trusted_users is not None else model.get("users", {})
    try:
        if not verify(users, st.get("user"), stamp_message(st), st.get("sig")):
            return ["the stamp signature is not valid for a known key of user %r" % st.get("user")]
    except IdentityError as exc:
        return ["the stamp signature could not be checked: %s" % exc]
    return []
