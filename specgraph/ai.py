"""AI labels (ADR-034): a controlled vocabulary and per-element labels in a second, signed file.

`<model base>.ai.json` holds the vocabulary, the labels (keyed by a hash of each element's content) and people's
rules; `<model base>.ai.log.jsonl` records every operation. The tool never calls a language model: an agent reads
work packets and writes through `AIStore.apply`, which checks, signs and logs like `Store.apply` does for the
model. Labels find; specs answer: nothing in the tool decides anything from a label.
"""
import hashlib
import json
import os
import re

from . import model as M, stamp as S, validate as V
from .ops import now_iso

FORMAT = "specgraph-ai"
FORMAT_VERSION = 1
PROMPT_VERSION = 1          # version of the labelling prompt the tool ships (Phase 8)
DEFINITION_MAX = 300
ADMIN_KEYS = ("vocabVersion", "promptVersion", "vocabulary", "rules")


class AIError(Exception):
    """An AI operation is not allowed or its arguments are wrong."""


def _base(model_path):
    p = os.path.abspath(model_path)
    return p[:-5] if p.endswith(".json") else p


def ai_path(model_path):
    return _base(model_path) + ".ai.json"


def log_path(model_path):
    return _base(model_path) + ".ai.log.jsonl"


def empty():
    return {"format": FORMAT, "formatVersion": FORMAT_VERSION, "vocabVersion": 0, "promptVersion": PROMPT_VERSION,
            "vocabulary": {}, "labels": {}, "rules": {}}


def parse(text):
    try:
        ai = json.loads(text)
    except ValueError as exc:
        raise M.ModelError("AI file is not valid JSON (%s)" % exc)
    if not isinstance(ai, dict) or ai.get("format") != FORMAT:
        raise M.ModelError("file is not a %s file" % FORMAT)
    if ai.get("formatVersion") != FORMAT_VERSION:
        raise M.ModelError("unsupported AI formatVersion %r" % ai.get("formatVersion"))
    return ai


def element_hash(el):
    """sha256 of what an element is about: type, topic, notes, fields (ADR-034 §3)."""
    core = {"stereotype": el.get("stereotype"), "topic": el.get("topic", ""), "notes": el.get("notes", ""),
            "fields": el.get("fields") or {}}
    return hashlib.sha256(json.dumps(core, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()


def _active(ai, key):
    v = ai["vocabulary"].get(key)
    return v is not None and not v.get("retired")


def _rules_for(ai, eid):
    never = {r["label"] for r in ai["rules"].values() if r["element"] == eid and r["kind"] == "never"}
    always = {r["label"] for r in ai["rules"].values() if r["element"] == eid and r["kind"] == "always"}
    return never, always


def _current(ai, entry, eid):
    """An entry is current for an element when every label is active, unchanged since it was made, and the
    element's rules still hold."""
    never, always = _rules_for(ai, eid)
    labels = set(entry["labels"])
    for k in labels:
        if not _active(ai, k) or ai["vocabulary"][k].get("changed", 0) > entry["v"]:
            return False
    return not (labels & never) and always <= labels


def element_labels(ai, model):
    """{element id: (sorted labels, stale)} for every element that has or had labels (ADR-034 §3)."""
    by_hash = ai.get("labels", {})
    last_seen = {}                      # element -> entry it was last labelled with (content may have changed)
    for h, e in by_hash.items():
        for eid in e.get("elements", []):
            prev = last_seen.get(eid)
            if prev is None or e.get("v", 0) >= prev.get("v", 0):
                last_seen[eid] = e
    out = {}
    for eid, el in model["elements"].items():
        entry = by_hash.get(element_hash(el))
        if entry is not None:
            out[eid] = (sorted(entry["labels"]), not _current(ai, entry, eid))
        elif eid in last_seen:
            out[eid] = (sorted(last_seen[eid]["labels"]), True)
    return out


# -- operations ---------------------------------------------------------------------------------------

OPS = {}


def op(name, doc, admin=False):
    def deco(fn):
        fn.doc, fn.admin = doc, admin
        OPS[name] = fn
        return fn
    return deco


def _text(v, what, max_len):
    if not isinstance(v, str) or not v.strip() or len(v) > max_len:
        raise AIError("%s must be text of 1 to %d characters" % (what, max_len))
    return v.strip()


def _bump(ai, ctx):
    """The new vocabVersion of this batch (one raise per batch)."""
    if "v" not in ctx:
        ai["vocabVersion"] = ai.get("vocabVersion", 0) + 1
        ctx["v"] = ai["vocabVersion"]
    return ctx["v"]


def _key_for(ai, label):
    base = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "label"
    if not base[0].isalpha():
        base = "l-" + base
    base, key, n = base[:36], base[:36], 2
    while key in ai["vocabulary"]:
        key, n = "%s-%d" % (base, n), n + 1
    return key


def _vocab_key(ai, key, active=True):
    if not isinstance(key, str) or key not in ai["vocabulary"]:
        raise AIError("label %r is not in the vocabulary" % key)
    if active and ai["vocabulary"][key].get("retired"):
        raise AIError("label %r is retired" % key)
    return key


@op("ai.vocab.add", "{label, definition, parent?, key?} -> key. A new concept; makes no label stale.", admin=True)
def vocab_add(ai, model, a, ctx):
    label = _text(a.get("label"), "label", 100)
    entry = {"label": label, "definition": _text(a.get("definition"), "definition", DEFINITION_MAX)}
    key = a.get("key") or _key_for(ai, label)
    if not V.KEY.match(key) or key in ai["vocabulary"]:
        raise AIError("key %r is invalid or taken" % key)
    if a.get("parent") is not None:
        parent = _vocab_key(ai, a["parent"])
        if ai["vocabulary"][parent].get("parent"):
            raise AIError("the vocabulary has two levels at most")
        entry["parent"] = parent
    entry["changed"] = _bump(ai, ctx)
    ai["vocabulary"][key] = entry
    return key


@op("ai.vocab.update", "{key, label?, definition?, parent?, keepLabels?} a new definition makes the labels that "
    "carry it stale, unless keepLabels is true (a wording fix).", admin=True)
def vocab_update(ai, model, a, ctx):
    key = _vocab_key(ai, a.get("key"))
    e = ai["vocabulary"][key]
    if "label" in a:
        e["label"] = _text(a["label"], "label", 100)
    if "parent" in a:
        if a["parent"] is None:
            e.pop("parent", None)
        else:
            e["parent"] = _vocab_key(ai, a["parent"])
    v = _bump(ai, ctx)
    if "definition" in a:
        d = _text(a["definition"], "definition", DEFINITION_MAX)
        if d != e["definition"]:
            e["definition"] = d
            if not a.get("keepLabels"):
                e["changed"] = v


def _retire(ai, key, ctx, replaced_by=None):
    e = ai["vocabulary"][_vocab_key(ai, key)]
    e["retired"] = True
    e["changed"] = _bump(ai, ctx)
    if replaced_by:
        e["replacedBy"] = list(replaced_by)


@op("ai.vocab.retire", "{key} no new labels with it; elements carrying it become stale.", admin=True)
def vocab_retire(ai, model, a, ctx):
    _retire(ai, a.get("key"), ctx)


@op("ai.vocab.merge", "{keys, into} retire keys in favour of `into` (an active key).", admin=True)
def vocab_merge(ai, model, a, ctx):
    into = _vocab_key(ai, a.get("into"))
    keys = a.get("keys")
    if not isinstance(keys, list) or not keys or into in keys:
        raise AIError("keys must be a list of labels other than `into`")
    for k in keys:
        _retire(ai, k, ctx, [into])


@op("ai.vocab.split", "{key, into} retire key in favour of two or more active keys.", admin=True)
def vocab_split(ai, model, a, ctx):
    into = a.get("into")
    if not isinstance(into, list) or len(into) < 2 or a.get("key") in into:
        raise AIError("into must list at least two other labels")
    _retire(ai, a.get("key"), ctx, [_vocab_key(ai, k) for k in into])


@op("ai.rule.set", "{element, label, kind: never|always, reason} -> id. A person's correction.", admin=True)
def rule_set(ai, model, a, ctx):
    eid = a.get("element")
    if eid not in model["elements"]:
        raise AIError("element %r does not exist" % eid)
    if a.get("kind") not in ("never", "always"):
        raise AIError("kind must be never or always")
    rid = M.new_id()
    ai["rules"][rid] = {"element": eid, "label": _vocab_key(ai, a.get("label")), "kind": a["kind"],
                        "reason": _text(a.get("reason"), "reason", 300), "by": ctx["actor"], "at": now_iso()}
    return rid


@op("ai.rule.delete", "{id}", admin=True)
def rule_delete(ai, model, a, ctx):
    if a.get("id") not in ai["rules"]:
        raise AIError("rule %r does not exist" % a.get("id"))
    del ai["rules"][a["id"]]


@op("ai.gc", "{} drop label entries whose content no element has any more.", admin=True)
def gc(ai, model, a, ctx):
    live = {element_hash(e) for e in model["elements"].values()}
    gone = [h for h in ai["labels"] if h not in live]
    for h in gone:
        del ai["labels"][h]
    return len(gone)


def _element(model, ref):
    """An element id, or the unique label of one (packets name elements by label to save tokens)."""
    if isinstance(ref, str) and ref in model["elements"]:
        return ref
    hits = [i for i, e in model["elements"].items() if isinstance(ref, str) and ref and e.get("label") == ref]
    if len(hits) != 1:
        raise AIError("element %r does not exist" % ref)
    return hits[0]


@op("ai.label.set", "{element, hash, labels, reason?, confidence?, model?} labels of one element (id or label); "
    "hash: its current content hash or the first 12+ characters; labels may be empty (nothing fits); any user.")
def label_set(ai, model, a, ctx):
    eid = _element(model, a.get("element"))
    h = element_hash(model["elements"][eid])
    given = a.get("hash")
    if not isinstance(given, str) or len(given) < 12:
        raise AIError("hash must be the element's content hash or its first 12 or more characters")
    if not h.startswith(given):
        raise AIError("hash is not the element's current content hash (it changed since the packet was made)")
    labels = a.get("labels")
    if not isinstance(labels, list) or not all(isinstance(x, str) for x in labels):
        raise AIError("labels must be a list of vocabulary keys")
    never, always = _rules_for(ai, eid)
    for k in labels:
        _vocab_key(ai, k)
        if k in never:
            raise AIError("a rule says %s is never labelled %s" % (eid, k))
    labels = sorted(set(labels) | {k for k in always if _active(ai, k)})
    old = ai["labels"].get(h)
    elements = sorted(set((old or {}).get("elements", [])) | {eid})
    if old and old["labels"] == labels and _current(ai, old, eid) and old.get("elements") == elements:
        return None                                       # same labels again: no change
    llm = a.get("model") if a.get("model") is not None else ctx.get("model")
    ai["labels"][h] = {"v": ai.get("vocabVersion", 0), "labels": labels, "by": ctx["actor"],
                       "model": str(llm or "")[:100], "elements": elements}


# -- work packets for agents (ADR-034 §6) --------------------------------------------------------------

PROMPT = """You label elements of a specification model with concepts from a controlled vocabulary.

For each element in `elements`, choose the keys from `vocabulary` whose definition fits what the element itself is
about: its type, topic, notes and fields. Read the meaning, not only the words: "the parcel leaves the warehouse
the same day" is about delivery although it never says so. Use `links` (and `context` for neighbours outside the packet) only to understand
the element; being linked to an element about X does not make this element about X. Choose 0 to 3 keys; an empty
list is right when nothing fits. Never use a key that is not in `vocabulary`. `rules` are people's corrections: never
give a key a `never` rule forbids (the tool adds `always` keys itself). `was` shows labels that went stale; keep them
only if they still fit.

Write one operation per element of the packet, all in one JSON list, to a file:
  {"op": "ai.label.set", "args": {"element": "<label>", "hash": "<h>", "labels": ["<key>", ...]}}
then run:  python sg.py --file <model> ai apply --ops-file <that file> --model <your model name>
Add "reason" (a few words) only where the choice is not obvious. If `remaining` is above 0, ask for the next packet."""

VOCAB_PROMPT = """You propose a controlled vocabulary of concepts for a specification model, so that agents can later
find elements by what they are about (for example accessibility, delivery, performance, audit trail), however
each element words it.

Concepts are cross-cutting subjects, not the model's structure: types, statuses, folders and link types already exist
(see `types`). Aim for 100 to 200 concepts on a large model, fewer on a small one; two levels at most (a `parent`).
Each concept: a short `label`, and a one-line `definition` (at most 300 characters) precise enough to decide for any
element whether it fits, including wordings that do not use the concept's name. Use `counts`, `types` (with the
project's own descriptions), `terms` (frequent words) and `samples` (topics spread over the model) to see what the
model is about; keep concepts that already exist in `vocabulary` (`used` = elements labelled with it) unless they are
wrong.

Write the operations as one JSON list to a file, for an administrator to apply:
  {"op": "ai.vocab.add", "args": {"label": "...", "definition": "...", "parent": "$N"}}   ("$N" = the key created by
  operation N of the same list), ai.vocab.update / ai.vocab.merge / ai.vocab.split for existing concepts.
The administrator runs:  python sg.py --file <model> ai apply --ops-file <that file> --model <model name>"""

STOP = set("""a about above after again all also an and any are as at be because been before being below between
both but by can could did do does doing down during each every few for from further had has have having he her here
how i if in into is it its itself just me more most my no nor not now of off on once only or other our out over own
same she should so some such than that the their them then there these they this those through to too under until
up very was we were what when where which while who whom why will with would you your one two per new each only
must shall may""".split())


def _words(text):
    return [w for w in re.findall(r"[a-z][a-z0-9-]{3,}", text.lower()) if w not in STOP]


def _links(model, eid, types):
    """Traceable links of an element, 'type>LABEL' (outgoing) and '<type LABEL' (incoming), sorted."""
    out = []
    for lid, l in model["links"].items():
        if not V.traceable(types.get(l.get("type"), {})):
            continue
        if l.get("source") == eid and l.get("target") in model["elements"]:
            out.append(("%s>%s" % (l["type"], model["elements"][l["target"]].get("label") or l["target"]),
                        l["target"]))
        elif l.get("target") == eid and l.get("source") in model["elements"]:
            out.append(("<%s %s" % (l["type"], model["elements"][l["source"]].get("label") or l["source"]),
                        l["source"]))
    return sorted(out)


def todo(ai, model, limit=1000, all_=False, label_new=None, max_links=10):
    """A labelling packet: the elements whose labels are missing or stale (or all, or the candidates for a new
    label), each with light neighbours. `limit` 0 = no cap."""
    ai = ai or empty()
    got = element_labels(ai, model)
    els = model["elements"]
    if label_new is not None:
        e = ai["vocabulary"].get(label_new)
        if e is None:
            raise AIError("label %r is not in the vocabulary" % label_new)
        words = set(_words(e["label"] + " " + e["definition"]))
        pick = [i for i, x in els.items() if words & set(_words(x.get("topic", "") + " " + x.get("notes", "")))]
    else:
        pick = [i for i in els if all_ or i not in got or got[i][1]]
    paths = {}

    def path(fid):
        if fid not in paths:
            from .query import folder_path
            paths[fid] = folder_path(model, fid)
        return paths[fid]
    pick.sort(key=lambda i: (path(els[i].get("folder")), els[i].get("label", ""), i))
    remaining = max(0, len(pick) - limit) if limit else 0
    pick = pick[:limit] if limit else pick
    inside, types, out, context = set(pick), model["config"]["linkTypes"], [], {}
    for i in pick:
        x = els[i]
        e = {"label": x.get("label") or i, "h": element_hash(x)[:12], "type": x.get("stereotype"),
             "topic": x.get("topic", "")}
        if x.get("notes"):
            e["notes"] = x["notes"]
        if x.get("fields"):
            e["fields"] = x["fields"]
        links = _links(model, i, types)
        e["links"] = [t for t, _ in links[:max_links]]
        if len(links) > max_links:
            e["moreLinks"] = len(links) - max_links
        for _, other in links[:max_links]:
            if other not in inside:
                o = els[other]
                context[o.get("label") or other] = {"type": o.get("stereotype"), "topic": o.get("topic", ""),
                                                    "labels": got.get(other, ([], False))[0]}
        if i in got:
            e["was" if got[i][1] else "labels"] = got[i][0]
        out.append(e)
    rules = [{"element": els[r["element"]].get("label") or r["element"], "label": r["label"], "kind": r["kind"],
              "reason": r["reason"]} for r in ai["rules"].values() if r["element"] in inside]
    vocab = [dict({"key": k, "label": v["label"], "definition": v["definition"]},
                  **({"parent": v["parent"]} if v.get("parent") else {}))
             for k, v in sorted(ai["vocabulary"].items()) if not v.get("retired")]
    return {"promptVersion": PROMPT_VERSION, "prompt": PROMPT, "vocabVersion": ai.get("vocabVersion", 0),
            "vocabulary": vocab, "rules": rules, "context": context, "remaining": remaining, "elements": out}


def vocab_packet(ai, model, samples=400, terms=200):
    """Material for building or revising the vocabulary when no agent can read every element (ADR-034 §6)."""
    from .query import folder_path
    ai = ai or empty()
    els = model["elements"]
    by_type, by_folder, top = {}, {}, {}
    for i, x in els.items():
        by_type[x.get("stereotype")] = by_type.get(x.get("stereotype"), 0) + 1
        p = folder_path(model, x.get("folder")).split("/")[0]
        top[i] = p
        by_folder[p] = by_folder.get(p, 0) + 1
    used = {}
    for labels, _ in element_labels(ai, model).values():
        for k in labels:
            used[k] = used.get(k, 0) + 1
    freq = {}
    for x in els.values():
        for w in set(_words(x.get("topic", "") + " " + x.get("notes", ""))):
            freq[w] = freq.get(w, 0) + 1
    groups = {}                                           # round robin over (top folder, type) for spread
    for i in sorted(els, key=lambda i: (els[i].get("label", ""), i)):
        groups.setdefault((top[i], els[i].get("stereotype")), []).append(i)
    order, picked, k = sorted(groups), [], 0
    while len(picked) < samples and any(len(groups[g]) > k for g in order):
        for g in order:
            if k < len(groups[g]) and len(picked) < samples:
                i = groups[g][k]
                picked.append({"type": els[i].get("stereotype"), "folder": top[i], "topic": els[i].get("topic", "")})
        k += 1
    st = model["config"]["stereotypes"]
    return {"promptVersion": PROMPT_VERSION, "prompt": VOCAB_PROMPT, "vocabVersion": ai.get("vocabVersion", 0),
            "counts": {"elements": len(els), "byType": by_type, "byFolder": by_folder},
            "types": [{"key": k, "label": st[k].get("label"), "description": st[k].get("description", "")}
                      for k in sorted(by_type) if k in st],
            "vocabulary": [dict({"key": k, "label": v["label"], "definition": v["definition"],
                                 "used": used.get(k, 0)}, **({"parent": v["parent"]} if v.get("parent") else {}),
                                **({"retired": True} if v.get("retired") else {}))
                           for k, v in sorted(ai["vocabulary"].items())],
            "terms": sorted(([w, n] for w, n in freq.items() if n > 1), key=lambda t: (-t[1], t[0]))[:terms],
            "samples": picked}


def dump_packet(p):
    """JSON text with one element (or sample) per line, so a reader can page through it."""
    head = {k: v for k, v in p.items() if k not in ("elements", "samples")}
    tail = "elements" if "elements" in p else "samples"
    lines = ['%s: %s' % (json.dumps(k), json.dumps(v, ensure_ascii=False)) for k, v in head.items()]
    items = [json.dumps(e, ensure_ascii=False, separators=(",", ":")) for e in p[tail]]
    return "{\n" + ",\n".join(lines) + ',\n"%s": [\n' % tail + ",\n".join(items) + "\n]}\n"


# -- who may change what (shared by the tool, the commit check and the audit) --------------------------

def check_change(old, new, actor, users):
    """Violations for moving the AI file from `old` (None = no file) to `new`, signed by `actor`."""
    out = []
    if actor not in (users or {}):
        return ["the AI file is signed by %r, who is not a registered user of the model" % actor]
    admin = users[actor].get("role") == "admin"
    base = old or empty()
    if not admin and any(base.get(k) != new.get(k) for k in ADMIN_KEYS):
        out.append("only an administrator may change the AI vocabulary or rules (changed by %s)" % actor)
    if not admin and set(base.get("labels", {})) - set(new.get("labels", {})):
        out.append("only an administrator may remove label entries (ai.gc) (changed by %s)" % actor)
    return out


def check_version(new_text, parent_texts, users):
    """Findings for one committed or staged version of the AI file (ADR-034 §8). `users`: the trusted user list
    (the model's users in the parent commit)."""
    try:
        new = parse(new_text)
    except M.ModelError as exc:
        return ["ai: unreadable AI file: %s" % exc]
    parents = []
    for t in parent_texts:
        if t is not None:
            try:
                parents.append(parse(t))
            except M.ModelError:
                pass
    if any(M.canonical(p) == M.canonical(new) for p in parents):
        return []
    findings = ["ai: " + p for p in S.check_integrity(new, users)]
    if not findings:
        actor = (new.get("stamp") or {}).get("user")
        olds = parents or [None]
        per = [check_change(o, new, actor, users) for o in olds]
        findings += ["ai: " + v for v in sorted(set.intersection(*[set(p) for p in per]))]
    return findings


# -- the write path ---------------------------------------------------------------------------------------

class AIStore:
    """Reads and writes the AI file of a model (ADR-034 §4)."""

    def __init__(self, store):
        self.store = store
        self.path = ai_path(store.path)
        self.log = log_path(store.path)

    def load(self):
        if not os.path.exists(self.path):
            return None
        with open(self.path, "r", encoding="utf-8") as fh:
            return parse(fh.read())

    def _err(self, msg, code="rejected"):
        from .store import StoreError
        return StoreError(msg, code)

    def apply(self, ops, llm_model=None):
        """Apply AI operations atomically as the local user; sign, save, log. Returns (ai, results)."""
        if not isinstance(ops, list) or not ops:
            raise self._err("expected a non-empty list of operations")
        model = self.store.load()
        with M.FileLock(self.path):
            try:
                old = self.load()
            except M.ModelError as exc:
                raise self._err(str(exc), "unreadable")
            if old is not None:
                problems = S.check_integrity(old, model["users"])
                if problems:
                    raise self._err("AI file: " + problems[0] + ". Restore it from git.", "integrity")
            new = M.clone(old) if old else empty()
            new.pop("stamp", None)
            try:
                key = self.store.key()
                actor = S.whoami(model, key)
            except S.IdentityError as exc:
                raise self._err(str(exc), "identity")
            ctx, results, logs = {"actor": actor, "model": llm_model}, [], []

            def subst(v):
                if isinstance(v, str) and re.match(r"^\$\d+$", v):
                    i = int(v[1:])
                    if i >= len(results) or results[i] is None:
                        raise AIError("%s does not refer to an earlier created item" % v)
                    return results[i]
                if isinstance(v, list):
                    return [subst(x) for x in v]
                return v
            for i, o in enumerate(ops):
                if not isinstance(o, dict) or o.get("op") not in OPS:
                    raise self._err("operation %d: unknown op %r" % (i, o.get("op") if isinstance(o, dict) else o))
                args = o.get("args", {})
                if not isinstance(args, dict):
                    raise self._err("operation %d: args must be an object" % i)
                args = {k: subst(v) for k, v in args.items()}
                if OPS[o["op"]].admin and model["users"][actor].get("role") != "admin":
                    raise self._err("%s: only an administrator may change the AI vocabulary or rules" % o["op"],
                                    "locked")
                try:
                    results.append(OPS[o["op"]](new, model, args, ctx))
                except AIError as exc:
                    raise self._err("%s: %s" % (o["op"], exc))
                rec = dict({k: args[k] for k in ("element", "labels", "reason", "confidence", "key", "kind")
                            if k in args}, op=o["op"], result=results[-1])
                if o["op"] == "ai.label.set":
                    rec["model"] = str(args.get("model") or llm_model or "")
                logs.append(rec)
            violations = check_change(old, new, actor, model["users"])
            if violations:
                raise self._err("; ".join(violations), "locked")
            if old is not None and M.content_hash(new) == M.content_hash(old):
                return old, results
            names = [o["op"] for o in ops]
            try:
                S.make_stamp(new, actor, key, names[0] if len(names) == 1 else "batch:" + ",".join(names)[:200],
                             [(old or {}).get("stamp", {}).get("id")])
            except S.IdentityError as exc:
                raise self._err(str(exc), "identity")
            M.save(self.path, new)
            at = new["stamp"]["at"]
            with open(self.log, "a", encoding="utf-8", newline="\n") as fh:
                for rec in logs:
                    rec.update(at=at, by=actor, stamp=new["stamp"]["id"])
                    fh.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")
            return new, results

    def element_labels(self):
        ai = self.load()
        return element_labels(ai, self.store.load()) if ai else {}

    def todo(self, **kw):
        return todo(self.load(), self.store.load(), **kw)

    def vocab_packet(self, **kw):
        return vocab_packet(self.load(), self.store.load(), **kw)

    def status(self):
        model = self.store.load()
        ai = self.load()
        n = len(model["elements"])
        if ai is None:
            return {"file": False, "elements": n, "vocabulary": 0, "retired": 0, "vocabVersion": 0, "labelled": 0,
                    "stale": 0, "unlabelled": n, "rules": 0}
        got = element_labels(ai, model)
        stale = sum(1 for _, s in got.values() if s)
        return {"file": True, "elements": n,
                "vocabulary": sum(1 for v in ai["vocabulary"].values() if not v.get("retired")),
                "retired": sum(1 for v in ai["vocabulary"].values() if v.get("retired")),
                "vocabVersion": ai["vocabVersion"], "labelled": len(got) - stale, "stale": stale,
                "unlabelled": n - len(got), "rules": len(ai["rules"]),
                "integrity": S.check_integrity(ai, model["users"]) or "ok"}
