"""The one write path: load -> check -> apply ops -> rules -> stamp -> save."""
import json
import os

from . import MODEL_FILENAME, TOOL_NAME, VERSION
from . import gitio, model as M, ops as O, query as Q, rules, stamp as S, validate as V


class StoreError(Exception):
    def __init__(self, message, code="rejected"):
        super().__init__(message)
        self.code = code


class Store:
    def __init__(self, path=None, cwd=None, key=None):
        cwd = cwd or os.getcwd()
        path = path or os.environ.get("SPECGRAPH_FILE")
        self.root = gitio.repo_root(os.path.dirname(os.path.abspath(path)) if path else cwd)
        self.path = os.path.abspath(path) if path else os.path.join(self.root or cwd, MODEL_FILENAME)
        self._key = key
        self.undo_steps = 0      # set by the editor server (ADR-017); the CLI keeps none
        self._undo = []          # [{before: model, op: text}], newest last
        self._undo_head = None   # stamp id the newest entry leads to

    # -- identity ----------------------------------------------------------
    def key(self):
        return self._key  # None: the one key in ssh-agent (an explicit choice is for tests)

    def me(self, model):
        try:
            name = S.whoami(model, self.key())
            return {"user": name, "role": model["users"][name]["role"], "error": None}
        except S.IdentityError as exc:
            return {"user": None, "role": None, "error": str(exc)}

    def prove_identity(self):
        """Sign a fresh challenge and verify it against the model's key list.

        Reading the public key from disk proves nothing, so the editor calls this before it
        opens: whoever cannot sign with the registered private key (passphrase unknown, key not
        in ssh-agent) cannot work as that user."""
        model = self.load()
        try:
            actor = S.whoami(model, self.key())
            msg = M.new_id().encode("ascii")
            sig = S.sign(S.resolve_key(self.key(), model, actor), msg)
        except S.IdentityError as exc:
            raise StoreError("cannot prove that you hold the private key: %s" % exc, "identity")
        if not S.verify(model["users"], actor, msg, sig):
            raise StoreError("cannot prove that you hold the private key of user %r" % actor, "identity")
        return actor

    def foreign_unlocks(self, model, ops):
        """Locks of other users that `ops` would clear (they need a confirmation, ADR-022)."""
        try:
            actor = S.whoami(model, self.key())
        except S.IdentityError:
            return []
        out = []
        for o in ops if isinstance(ops, list) else []:
            if isinstance(o, dict) and o.get("op") == "folder.unlock":
                fid = (o.get("args") or {}).get("id")
                f = model["folders"].get(fid) if isinstance(fid, str) else None
                lock = (f or {}).get("lock")
                if lock and lock.get("owner") != actor:
                    out.append({"id": fid, "name": f.get("name"), "owner": lock.get("owner"),
                                "reason": lock.get("reason", ""), "at": lock.get("at")})
        return out

    # -- reading -----------------------------------------------------------
    def exists(self):
        return os.path.exists(self.path)

    def load(self):
        try:
            return M.load(self.path)
        except M.ModelError as exc:
            raise StoreError(str(exc), "unreadable")

    def trusted_users(self):
        """Users of the last committed version, when there is one."""
        if not self.root:
            return None
        text = gitio.show(self.root, "HEAD:" + gitio.rel_path(self.root, self.path))
        if text is None:
            return None
        try:
            return M.parse(text).get("users")
        except M.ModelError:
            return None

    # -- writing -----------------------------------------------------------
    def init(self, user_name):
        if self.exists():
            raise StoreError("%s already exists" % self.path)
        if not V.USERNAME.match(user_name or ""):
            raise StoreError("user name may contain letters, digits and . _ @ - only")
        try:
            key = S.public_key(self.key())  # the key loaded in ssh-agent (or the chosen one)
            model = M.empty_model()
            model["users"][user_name] = {"role": "admin", "keys": [key]}
            S.make_stamp(model, user_name, key, "init", [])
        except S.IdentityError as exc:
            raise StoreError(str(exc), "identity")
        M.save(self.path, model)
        return model

    def apply(self, ops, base=None):
        """Apply operations as the local user. `base` is the stamp id the caller
        last saw; a mismatch means the file changed underneath (REQ-STO-07)."""
        with M.FileLock(self.path):
            model, head = self._load_checked(base)
            try:
                key = self.key()
                actor = S.whoami(model, key)
                new, results = O.apply_ops(model, ops, actor)
                violations = rules.check_change([model], new, actor)
                if violations:
                    raise StoreError("; ".join(violations), "locked")
                names = [o["op"] for o in ops]
                S.make_stamp(new, actor, key, names[0] if len(names) == 1 else "batch:" + ",".join(names)[:200], [head])
            except O.OpError as exc:
                raise StoreError(str(exc))
            except S.IdentityError as exc:
                raise StoreError(str(exc), "identity")
            if M.content_hash(new) != M.content_hash(model):
                self._log_deleted(model, new, actor, "conflict.resolve" in names)
                M.save(self.path, new)
                if self.undo_steps > 0:
                    if head != self._undo_head:
                        self._undo = []  # something else changed the file since our last change
                    label = names[0] if len(names) == 1 else "%d changes" % len(names)
                    self._undo = (self._undo + [{"before": model, "op": label}])[-self.undo_steps:]
                    self._undo_head = new["stamp"]["id"]
            else:
                new = model
            return new, results

    def _load_checked(self, base):
        model = self.load()
        head = (model.get("stamp") or {}).get("id")
        if base is not None and base != head:
            raise StoreError("the model file changed on disk since you loaded it; "
                             "it has been reloaded - please repeat your change", "stale")
        problems = S.check_integrity(model, None)
        if problems:
            raise StoreError(problems[0] + ". Restore the file from git, or run the 'adopt' "
                             "command to accept the outside change under your name.", "integrity")
        return model, head

    def undo(self, base=None):
        """Take back the last change made through this Store (ADR-017): write the
        state before it as a new stamped change. Lock and user rules apply."""
        with M.FileLock(self.path):
            model, head = self._load_checked(base)
            if self._undo and head != self._undo_head:
                self._undo = []
                raise StoreError("the model was changed outside this editor; the undo list was emptied", "undo")
            if not self._undo:
                raise StoreError("nothing to undo", "undo")
            entry = self._undo[-1]
            restored = {k: v for k, v in M.clone(entry["before"]).items() if k != "stamp"}
            try:
                key = self.key()
                actor = S.whoami(model, key)
                violations = rules.check_change([model], restored, actor)
                if violations:
                    raise StoreError("cannot undo: " + "; ".join(violations), "locked")
                S.make_stamp(restored, actor, key, ("undo:" + entry["op"])[:200], [head])
            except S.IdentityError as exc:
                raise StoreError(str(exc), "identity")
            self._log_deleted(model, restored, actor, True)
            M.save(self.path, restored)
            self._undo.pop()
            self._undo_head = restored["stamp"]["id"]
            return restored

    def undo_state(self, model):
        ok = bool(self._undo) and (model.get("stamp") or {}).get("id") == self._undo_head
        return {"steps": len(self._undo) if ok else 0, "next": self._undo[-1]["op"] if ok else None}

    # -- deleted elements log (ADR-018) --------------------------------------
    def _last_commit(self):
        """(hash, model) of the last commit that changed the model file, or (None, None)."""
        if not self.root:
            return None, None
        rel = gitio.rel_path(self.root, self.path)
        code, out = gitio.git(self.root, "log", "-1", "--format=%H", "--", rel, check=False)
        sha = out.strip() if code == 0 else ""
        text = gitio.show(self.root, "%s:%s" % (sha, rel)) if sha else None
        try:
            return (sha, M.parse(text)) if text else (None, None)
        except M.ModelError:
            return None, None

    def _log_deleted(self, old, new, actor, restoring=False):
        """Append one line per element that left the model, and (after an undo or
        a settled merge conflict) per element that came back. Append only."""
        a, b = old.get("elements", {}), new.get("elements", {})
        gone = sorted(set(a) - set(b))
        back = sorted(set(b) - set(a)) if restoring else []
        if not gone and not back:
            return
        at, lines = O.now_iso(), []
        sha, committed = self._last_commit() if gone else (None, None)
        for eid in gone:
            lines.append({"event": "deleted", "id": eid, "at": at, "by": actor,
                          "lastCommit": sha if committed and eid in committed.get("elements", {}) else None,
                          "folderPath": Q.folder_path(old, a[eid].get("folder")), "element": a[eid],
                          "links": {i: l for i, l in old.get("links", {}).items()
                                    if eid in (l.get("source"), l.get("target"))}})
        for eid in back:
            lines.append({"event": "restored", "id": eid, "at": at, "by": actor})
        with open(M.deleted_path(self.path), "a", encoding="utf-8", newline="\n") as fh:
            for rec in lines:
                fh.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")

    def adopt(self):
        """Accept content changed outside the tool: validate, check the rules
        against the last commit, and re-stamp it under the local user."""
        with M.FileLock(self.path):
            model = self.load()
            errs = V.errors(model)
            if errs:
                raise StoreError("cannot adopt, the model is invalid: " + "; ".join(e["message"] for e in errs[:5]))
            try:
                key = self.key()
                users = self.trusted_users() or model["users"]
                actor = S.user_of_key({"users": users}, S.resolve_key(key, {"users": users}))
                if not actor:
                    raise StoreError("your SSH key is not a registered user", "identity")
                old = None
                if self.root:
                    text = gitio.show(self.root, "HEAD:" + gitio.rel_path(self.root, self.path))
                    old = M.parse(text) if text else None
                violations = rules.check_change([old], model, actor)
                if violations:
                    raise StoreError("; ".join(violations), "locked")
                S.make_stamp(model, actor, key, "adopt", [(model.get("stamp") or {}).get("id")])
                if old:
                    self._log_deleted(old, model, actor)
            except S.IdentityError as exc:
                raise StoreError(str(exc), "identity")
            except M.ModelError as exc:
                raise StoreError(str(exc))
            M.save(self.path, model)
            return model

    def state(self):
        """Everything the UI needs in one answer."""
        model = self.load()
        return {"model": model, "head": (model.get("stamp") or {}).get("id"),
                "me": self.me(model), "integrity": S.check_integrity(model, None),
                "problems": V.validate(model), "locks": rules.effective_locks(model),
                "tool": TOOL_NAME, "version": VERSION,
                "undo": self.undo_state(model)}
