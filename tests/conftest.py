import os
import re
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from specgraph.store import Store  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def keygen(tmp_path_factory):
    """The real ssh-keygen and ssh-agent (they ship with Git); the tool signs through the agent."""
    real = shutil.which("ssh-keygen")
    if not real:
        pytest.skip("needs ssh-keygen (installed with Git/OpenSSH)")
    os.environ["SPECGRAPH_SSH_KEYGEN"] = real
    return real


@pytest.fixture(scope="session", autouse=True)
def agent(keygen, keys):
    """A private ssh-agent holding ada's, bob's and eve's keys; removed at the end."""
    exe = None
    for cand in (os.path.join(os.path.dirname(keygen), n) for n in ("ssh-agent", "ssh-agent.exe")):
        if os.path.exists(cand):
            exe = cand
            break
    exe = exe or shutil.which("ssh-agent")
    if not exe:
        pytest.skip("needs ssh-agent (installed with Git/OpenSSH)")
    p = subprocess.run([exe, "-s"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    sock = re.search(r"SSH_AUTH_SOCK=([^;]+);", p.stdout)
    pid = re.search(r"SSH_AGENT_PID=(\d+);", p.stdout)
    if p.returncode != 0 or not sock:
        pytest.skip("could not start ssh-agent: %s" % (p.stderr or p.stdout))
    old = {k: os.environ.get(k) for k in ("SSH_AUTH_SOCK", "SSH_AGENT_PID", "SPECGRAPH_SSH_ADD")}
    os.environ["SSH_AUTH_SOCK"] = sock.group(1)
    if pid:
        os.environ["SSH_AGENT_PID"] = pid.group(1)
    add = os.path.join(os.path.dirname(exe), os.path.basename(exe).replace("agent", "add"))
    os.environ["SPECGRAPH_SSH_ADD"] = add
    for path in keys.values():
        subprocess.run([add, path], check=True, capture_output=True)
    yield
    if pid:
        subprocess.run([exe, "-k"], capture_output=True, env=dict(os.environ))
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.fixture
def only_key(agent, keys):
    """use(path): unload every key from the agent and load just that one (the tool needs exactly one)."""
    import specgraph.stamp as S

    def use(path):
        subprocess.run([S.ssh_add(), "-D"], capture_output=True, check=True)
        subprocess.run([S.ssh_add(), path], capture_output=True, check=True)

    yield use
    subprocess.run([S.ssh_add(), "-D"], capture_output=True)
    for path in keys.values():
        subprocess.run([S.ssh_add(), path], capture_output=True, check=True)


@pytest.fixture(scope="session")
def keys(keygen, tmp_path_factory):
    """Key files for three people: ada (admin), bob, eve (never registered)."""
    d = tmp_path_factory.mktemp("keys")
    out = {}
    for name in ("ada", "bob", "eve"):
        path = os.path.join(str(d), name)
        subprocess.run([keygen, "-t", "ed25519", "-N", "", "-f", path, "-C", name, "-q"], check=True)
        out[name] = path
    return out


def pub(path):
    with open(path + ".pub") as fh:
        return " ".join(fh.read().split()[:2])


def git(cwd, *args):
    p = subprocess.run(["git"] + list(args), cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert p.returncode == 0, "git %s failed:\n%s\n%s" % (" ".join(args), p.stdout, p.stderr)
    return p.stdout


@pytest.fixture
def repo(tmp_path, keys):
    """A git repo on docs/specifications with a model owned by ada; bob is a user."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "docs/specifications")
    git(root, "config", "user.name", "Ada")
    git(root, "config", "user.email", "ada@example.org")
    ada = Store(cwd=str(root), key=keys["ada"])
    ada.init("ada")
    ada.apply([{"op": "user.add", "args": {"name": "bob", "key": pub(keys["bob"])}}])
    return root


@pytest.fixture
def ada(repo, keys):
    return Store(cwd=str(repo), key=keys["ada"])


@pytest.fixture
def bob(repo, keys):
    return Store(cwd=str(repo), key=keys["bob"])


@pytest.fixture
def eve(repo, keys):
    return Store(cwd=str(repo), key=keys["eve"])


def do(store, op, **args):
    """Apply one op, return its result (the new id for create ops)."""
    return store.apply([{"op": op, "args": args}])[1][0]


def commit(root, msg="change"):
    git(root, "add", "-A")
    git(root, "commit", "-q", "--no-verify", "-m", msg)
