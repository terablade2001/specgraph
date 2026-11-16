"""Model file: canonical (de)serialization, hashing, atomic save, file lock."""
import copy
import hashlib
import json
import os
import time
import uuid

from . import FORMAT, FORMAT_VERSION, READABLE_VERSIONS
from .defaults import default_config

COLLECTIONS = ("folders", "elements", "links", "diagrams")
CONFIG_KINDS = ("stereotypes", "statuses", "linkTypes", "coverageRules")


class ModelError(Exception):
    """The model file cannot be read or is not a model."""


def new_id():
    """Random UUID: unique without coordination across people and branches."""
    return str(uuid.uuid4())


def canonical(obj):
    """Deterministic text form: sorted keys, one value per line, LF, final newline."""
    return json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=False) + "\n"


def content_hash(model):
    """Hash of everything except the stamp (the stamp signs this hash)."""
    body = {k: v for k, v in model.items() if k != "stamp"}
    return "sha256:" + hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


def empty_model():
    return {
        "format": FORMAT,
        "formatVersion": FORMAT_VERSION,
        "settings": {},
        "config": default_config(),
        "users": {},
        "folders": {},
        "elements": {},
        "links": {},
        "diagrams": {},
    }


def parse(text):
    try:
        model = json.loads(text)
    except ValueError as exc:
        raise ModelError("model file is not valid JSON (%s). If it contains git "
                         "conflict markers, run the 'resolve' command." % exc)
    if not isinstance(model, dict) or model.get("format") != FORMAT:
        raise ModelError("file is not a %s file" % FORMAT)
    if model.get("formatVersion") not in READABLE_VERSIONS:
        raise ModelError("unsupported formatVersion %r" % model.get("formatVersion"))
    return model


def load(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return parse(fh.read())
    except OSError as exc:
        raise ModelError("cannot read %s: %s" % (path, exc))


def save(path, model):
    """Atomic write, always LF line endings."""
    tmp = "%s.tmp-%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(canonical(model))
    os.replace(tmp, path)


def deleted_path(path):
    """The log of deleted elements that sits next to a model file (ADR-018)."""
    return (path[:-5] if path.endswith(".json") else path) + ".deleted.jsonl"


def clone(model):
    return copy.deepcopy(model)


class FileLock:
    """Short-lived lock so the UI server and CLI/agents never interleave writes."""

    def __init__(self, path, timeout=10.0, stale=60.0):
        self.lock_path = path + ".lock"
        self.timeout, self.stale = timeout, stale

    def __enter__(self):
        deadline = time.time() + self.timeout
        while True:
            try:
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(self.lock_path) > self.stale:
                        os.unlink(self.lock_path)
                        continue
                except OSError:
                    continue
                if time.time() > deadline:
                    raise ModelError("model file is busy (lock %s)" % self.lock_path)
                time.sleep(0.05)

    def __exit__(self, *exc):
        try:
            os.unlink(self.lock_path)
        except OSError:
            pass
