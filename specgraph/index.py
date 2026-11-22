"""The derived, read-only SQLite index of a model (ADR-032, REQ-AGT-01/02/05/06).

`<model folder>/.specgraph/<model file name>.db`, built from the model file's bytes. It is never committed,
never edited and never read to decide a change: deleting it loses nothing. Logic stays in Python: folder
paths, effective locks and coverage come from query.py, rules.py and validate.py.
"""
import hashlib
import json
import os
import sqlite3
import time
from datetime import datetime, timezone

from . import VERSION
from . import model as M, query as Q, rules, stamp as S, validate as V

SCHEMA_VERSION = 1
SWAP_WAIT = 2.0        # seconds to retry the swap while another process holds the old index (Windows)

# (table, column, meaning); column "" is the table itself. Feeds `columns_doc` and `sql --schema`.
DOC = [
    ("meta", "", "facts about this index: one row per key"),
    ("meta", "key", "schema_version, tool_version, model_file, model_sha256, format_version, built_at, "
                    "integrity ('ok' or what is wrong with the stamp), fts ('fts5', 'fts5+trigram' or 'none')"),
    ("meta", "value", "the value, as text"),
    ("elements", "", "one row per element (deleted elements are not here); long notes are in element_notes"),
    ("elements", "id", "element id (UUID); links, fields and diagrams refer to it"),
    ("elements", "label", "short human name, e.g. REQ-3d6e7863; may be empty"),
    ("elements", "stereotype", "type key, see config_stereotypes.key"),
    ("elements", "status", "status key, see config_statuses.key"),
    ("elements", "topic", "the statement of the element, one line"),
    ("elements", "folder", "id of the folder it lives in, see folders.id"),
    ("elements", "folder_path", "names of the folder and its parents, e.g. 'Payments/Refunds'"),
    ("elements", "modified_at", "time of the last change (ISO 8601)"),
    ("elements", "modified_by", "user of the last change"),
    ("elements", "notes_chars", "length of the notes in characters (0 = no notes)"),
    ("element_notes", "", "the notes of each element that has notes"),
    ("element_notes", "id", "element id"),
    ("element_notes", "notes", "free text"),
    ("element_fields", "", "custom field values, one row per element and field"),
    ("element_fields", "element", "element id"),
    ("element_fields", "key", "field key, see config_fields.key"),
    ("element_fields", "value", "the value: text, a number, 1/0 for booleans, YYYY-MM-DD for dates"),
    ("element_fields", "type", "field type: string, text, number, boolean, enum, date"),
    ("links", "", "typed links between elements; a link belongs to the model, not to a diagram"),
    ("links", "id", "link id"),
    ("links", "type", "link type key, see config_link_types.key"),
    ("links", "source", "element id at the start"),
    ("links", "target", "element id at the end"),
    ("links", "label", "optional text on the link"),
    ("v_links", "", "links joined with their two elements and their type, for reading"),
    ("v_links", "id", "link id"),
    ("v_links", "type", "link type key"),
    ("v_links", "label", "text on the link"),
    ("v_links", "traceable", "1 when trace and impact follow this link type"),
    ("v_links", "source", "source element id"),
    ("v_links", "source_label", "source element label"),
    ("v_links", "source_stereotype", "source element type key"),
    ("v_links", "source_status", "source element status key"),
    ("v_links", "source_topic", "source element topic"),
    ("v_links", "target", "target element id"),
    ("v_links", "target_label", "target element label"),
    ("v_links", "target_stereotype", "target element type key"),
    ("v_links", "target_status", "target element status key"),
    ("v_links", "target_topic", "target element topic"),
    ("folders", "", "the folder tree, with the lock in force on each folder"),
    ("folders", "id", "folder id"),
    ("folders", "name", "folder name"),
    ("folders", "parent", "parent folder id; NULL at the top"),
    ("folders", "path", "names from the top, e.g. 'Payments/Refunds'"),
    ("folders", "lock_owner", "user who locked this folder itself; NULL when not locked here"),
    ("folders", "lock_reason", "reason given with that lock"),
    ("folders", "lock_at", "time of that lock"),
    ("folders", "locked_by", "owner of the lock in force here, set on this folder or an ancestor; NULL = free"),
    ("folders", "locked_from", "id of the folder that carries the lock in force"),
    ("diagrams", "", "diagrams; a diagram shows elements, it does not own them"),
    ("diagrams", "id", "diagram id"),
    ("diagrams", "name", "diagram name"),
    ("diagrams", "folder", "folder id"),
    ("diagrams", "folder_path", "folder names from the top"),
    ("diagram_elements", "", "which element is shown on which diagram"),
    ("diagram_elements", "diagram", "diagram id"),
    ("diagram_elements", "element", "element id"),
    ("users", "", "people who may change the model"),
    ("users", "name", "user name, as in elements.modified_by and folders.lock_owner"),
    ("users", "role", "admin or user"),
    ("config_stereotypes", "", "element types; read the descriptions to learn what each type means here"),
    ("config_stereotypes", "key", "type key, as in elements.stereotype"),
    ("config_stereotypes", "label", "name shown to people"),
    ("config_stereotypes", "description", "what this type means in this project; may be empty"),
    ("config_stereotypes", "label_prefix", "prefix of generated element labels"),
    ("config_stereotypes", "statuses", "JSON list of the status keys this type may have; NULL = all"),
    ("config_stereotypes", "retired", "1 = no new elements of this type"),
    ("config_statuses", "", "statuses of elements"),
    ("config_statuses", "key", "status key, as in elements.status"),
    ("config_statuses", "label", "name shown to people"),
    ("config_statuses", "description", "what this status means in this project; may be empty"),
    ("config_statuses", "order", "position in lists (smaller first)"),
    ("config_statuses", "retired", "1 = not offered any more"),
    ("config_link_types", "", "link types"),
    ("config_link_types", "key", "link type key, as in links.type"),
    ("config_link_types", "label", "name shown to people"),
    ("config_link_types", "description", "what this link means in this project; may be empty"),
    ("config_link_types", "traceable", "1 when trace and impact follow it"),
    ("config_link_types", "retired", "1 = no new links of this type"),
    ("config_link_type_ends", "", "which element types a link type may connect; no row for an end = any type"),
    ("config_link_type_ends", "link_type", "link type key"),
    ("config_link_type_ends", "end", "'source' or 'target'"),
    ("config_link_type_ends", "stereotype", "an element type allowed at that end"),
    ("config_fields", "", "custom fields each element type defines"),
    ("config_fields", "stereotype", "element type key"),
    ("config_fields", "key", "field key, as in element_fields.key"),
    ("config_fields", "label", "name shown to people"),
    ("config_fields", "type", "string, text, number, boolean, enum, date"),
    ("config_fields", "options", "JSON list of the allowed values of an enum; NULL otherwise"),
    ("config_coverage_rules", "", "rules such as 'every approved REQ has an incoming implements link'"),
    ("config_coverage_rules", "key", "rule key"),
    ("config_coverage_rules", "description", "the rule in words"),
    ("config_coverage_rules", "stereotype", "elements of this type must be covered"),
    ("config_coverage_rules", "statuses", "JSON list of the statuses the rule applies to; NULL = all"),
    ("config_coverage_rules", "link_type", "the link type that covers"),
    ("config_coverage_rules", "direction", "'incoming' or 'outgoing', seen from the covered element"),
    ("config_coverage_rules", "other", "type of the element at the other end; NULL = any"),
    ("coverage_violations", "", "elements that break a coverage rule (as sg.py validate reports them)"),
    ("coverage_violations", "rule", "rule key, see config_coverage_rules.key"),
    ("coverage_violations", "element", "element id"),
    ("coverage_violations", "message", "the warning in words"),
    ("columns_doc", "", "this description of every table and column"),
    ("columns_doc", "table", "table or view name"),
    ("columns_doc", "column", "column name; '' for the table itself"),
    ("columns_doc", "meaning", "what it holds"),
]
FTS_DOC = [
    ("elements_fts", "", "full-text search (FTS5, stemmed, accents ignored): WHERE elements_fts MATCH 'word*'; "
                         "ORDER BY rank. Only when meta fts is not 'none'"),
    ("elements_fts", "id", "element id (not searched)"),
    ("elements_fts", "label", "element label"),
    ("elements_fts", "topic", "element topic"),
    ("elements_fts", "notes", "element notes"),
    ("elements_fts", "fields", "the element's text field values"),
]
TRIGRAM_DOC = [
    ("elements_trigram", "", "substring search (FTS5 trigram) over the same columns: MATCH 'abc' finds any "
                             "3+ character piece. Only when meta fts is 'fts5+trigram'"),
    ("elements_trigram", "id", "element id (not searched)"),
    ("elements_trigram", "label", "element label"),
    ("elements_trigram", "topic", "element topic"),
    ("elements_trigram", "notes", "element notes"),
    ("elements_trigram", "fields", "the element's text field values"),
]

TABLES = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE elements (id TEXT PRIMARY KEY, label TEXT, stereotype TEXT, status TEXT, topic TEXT,
  folder TEXT, folder_path TEXT, modified_at TEXT, modified_by TEXT, notes_chars INTEGER);
CREATE TABLE element_notes (id TEXT PRIMARY KEY, notes TEXT);
CREATE TABLE element_fields (element TEXT, key TEXT, value, type TEXT, PRIMARY KEY (element, key));
CREATE TABLE links (id TEXT PRIMARY KEY, type TEXT, source TEXT, target TEXT, label TEXT);
CREATE TABLE folders (id TEXT PRIMARY KEY, name TEXT, parent TEXT, path TEXT, lock_owner TEXT,
  lock_reason TEXT, lock_at TEXT, locked_by TEXT, locked_from TEXT);
CREATE TABLE diagrams (id TEXT PRIMARY KEY, name TEXT, folder TEXT, folder_path TEXT);
CREATE TABLE diagram_elements (diagram TEXT, element TEXT, PRIMARY KEY (diagram, element));
CREATE TABLE users (name TEXT PRIMARY KEY, role TEXT);
CREATE TABLE config_stereotypes (key TEXT PRIMARY KEY, label TEXT, description TEXT, label_prefix TEXT,
  statuses TEXT, retired INTEGER);
CREATE TABLE config_statuses (key TEXT PRIMARY KEY, label TEXT, description TEXT, "order" INTEGER,
  retired INTEGER);
CREATE TABLE config_link_types (key TEXT PRIMARY KEY, label TEXT, description TEXT, traceable INTEGER,
  retired INTEGER);
CREATE TABLE config_link_type_ends (link_type TEXT, "end" TEXT, stereotype TEXT);
CREATE TABLE config_fields (stereotype TEXT, key TEXT, label TEXT, type TEXT, options TEXT,
  PRIMARY KEY (stereotype, key));
CREATE TABLE config_coverage_rules (key TEXT PRIMARY KEY, description TEXT, stereotype TEXT, statuses TEXT,
  link_type TEXT, direction TEXT, other TEXT);
CREATE TABLE coverage_violations (rule TEXT, element TEXT, message TEXT);
CREATE TABLE columns_doc ("table" TEXT, "column" TEXT, meaning TEXT, PRIMARY KEY ("table", "column"));
CREATE INDEX links_source ON links(source);
CREATE INDEX links_target ON links(target);
CREATE INDEX links_type ON links(type);
CREATE INDEX elements_stereotype_status ON elements(stereotype, status);
CREATE INDEX element_fields_key ON element_fields(key, value);
CREATE VIEW v_links AS
  SELECT l.id, l.type, l.label, t.traceable,
         l.source, s.label AS source_label, s.stereotype AS source_stereotype, s.status AS source_status,
         s.topic AS source_topic,
         l.target, d.label AS target_label, d.stereotype AS target_stereotype, d.status AS target_status,
         d.topic AS target_topic
  FROM links l LEFT JOIN elements s ON s.id = l.source LEFT JOIN elements d ON d.id = l.target
  LEFT JOIN config_link_types t ON t.key = l.type;
"""
STEMMED = "porter unicode61 remove_diacritics 2"


def index_path(model_path):
    folder, name = os.path.split(os.path.abspath(model_path))
    return os.path.join(folder, ".specgraph", name + ".db")


def _can(tokenize):
    try:
        con = sqlite3.connect(":memory:")
        try:
            con.execute("CREATE VIRTUAL TABLE t USING fts5(a, tokenize=%r)" % tokenize)
            return True
        finally:
            con.close()
    except sqlite3.Error:
        return False


def _stemmer():
    """Tokenizer of elements_fts: diacritics option needs SQLite 3.27; else plain unicode61."""
    return STEMMED if _can(STEMMED) else "porter unicode61"


def fts_mode():
    """'fts5+trigram', 'fts5' or 'none': what this Python's SQLite offers (REQ-AGT-06)."""
    if not _can("unicode61"):
        return "none"
    return "fts5+trigram" if _can("trigram") else "fts5"


def _read(model_path):
    try:
        with open(model_path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        raise M.ModelError("cannot read %s: %s" % (model_path, exc))
    return data, hashlib.sha256(data).hexdigest()


def _meta(db):
    """The meta table of an existing index, or None when there is none or it is not readable."""
    if not os.path.exists(db):
        return None
    try:
        con = _open_ro(db)
        try:
            return dict(con.execute("SELECT key, value FROM meta").fetchall())
        finally:
            con.close()
    except sqlite3.Error:
        return None


def _fresh(meta, sha):
    return bool(meta) and meta.get("model_sha256") == sha and meta.get("schema_version") == str(SCHEMA_VERSION) \
        and meta.get("tool_version") == VERSION


def _text(v):
    return None if v is None else str(v)


def _field_value(v):
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float, str)) or v is None:
        return v
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def _list(v):
    return None if v is None else json.dumps(v, ensure_ascii=False)


def _fill(con, model, info):
    """Write the whole model into an empty database (one transaction, done by the caller)."""
    cfg = model["config"]
    for statement in TABLES.split(";"):          # not executescript(): it would end the transaction
        if statement.strip():
            con.execute(statement)
    paths = {fid: Q.folder_path(model, fid) for fid in model["folders"]}
    locks = rules.effective_locks(model)
    stereo = cfg["stereotypes"]
    ins = con.executemany
    ins("INSERT INTO meta VALUES (?, ?)", sorted(info.items()))
    els = model["elements"]
    ins("INSERT INTO elements VALUES (?,?,?,?,?,?,?,?,?,?)", [
        (eid, e.get("label", ""), e.get("stereotype"), e.get("status"), e.get("topic", ""), e.get("folder"),
         paths.get(e.get("folder"), ""), (e.get("modified") or {}).get("at"), (e.get("modified") or {}).get("by"),
         len(e.get("notes") or "")) for eid, e in sorted(els.items())])
    ins("INSERT INTO element_notes VALUES (?, ?)",
        [(eid, e["notes"]) for eid, e in sorted(els.items()) if e.get("notes")])
    field_rows = []
    for eid, e in sorted(els.items()):
        defs = (stereo.get(e.get("stereotype")) or {}).get("fields", {})
        for key, value in sorted((e.get("fields") or {}).items()):
            field_rows.append((eid, key, _field_value(value), (defs.get(key) or {}).get("type")))
    ins("INSERT INTO element_fields VALUES (?,?,?,?)", field_rows)
    ins("INSERT INTO links VALUES (?,?,?,?,?)", [
        (lid, l.get("type"), l.get("source"), l.get("target"), l.get("label", ""))
        for lid, l in sorted(model["links"].items())])
    frows = []
    for fid, f in sorted(model["folders"].items()):
        lock, eff = f.get("lock") or {}, locks.get(fid) or {}
        frows.append((fid, f.get("name"), f.get("parent"), paths[fid], lock.get("owner"), lock.get("reason"),
                      lock.get("at"), eff.get("owner"), eff.get("from")))
    ins("INSERT INTO folders VALUES (?,?,?,?,?,?,?,?,?)", frows)
    ins("INSERT INTO diagrams VALUES (?,?,?,?)", [
        (did, d.get("name"), d.get("folder"), paths.get(d.get("folder"), ""))
        for did, d in sorted(model["diagrams"].items())])
    ins("INSERT INTO diagram_elements VALUES (?, ?)", [
        (did, eid) for did, d in sorted(model["diagrams"].items()) for eid in sorted(d.get("nodes") or {})])
    ins("INSERT INTO users VALUES (?, ?)", [(n, u.get("role")) for n, u in sorted(model["users"].items())])
    ins("INSERT INTO config_stereotypes VALUES (?,?,?,?,?,?)", [
        (k, s.get("label"), s.get("description", ""), s.get("labelPrefix", ""), _list(s.get("statuses")),
         int(bool(s.get("retired")))) for k, s in sorted(stereo.items())])
    ins("INSERT INTO config_statuses VALUES (?,?,?,?,?)", [
        (k, s.get("label"), s.get("description", ""), s.get("order", 0), int(bool(s.get("retired"))))
        for k, s in sorted(cfg["statuses"].items())])
    lts = sorted(cfg["linkTypes"].items())
    ins("INSERT INTO config_link_types VALUES (?,?,?,?,?)", [
        (k, t.get("label"), t.get("description", ""), int(V.traceable(t)), int(bool(t.get("retired"))))
        for k, t in lts])
    ins("INSERT INTO config_link_type_ends VALUES (?,?,?)", [
        (k, end, st) for k, t in lts for end, key in (("source", "sources"), ("target", "targets"))
        for st in (t.get(key) or [])])
    ins("INSERT INTO config_fields VALUES (?,?,?,?,?)", [
        (sk, fk, f.get("label"), f.get("type"), _list(f.get("options")))
        for sk, s in sorted(stereo.items()) for fk, f in sorted((s.get("fields") or {}).items())])
    ins("INSERT INTO config_coverage_rules VALUES (?,?,?,?,?,?,?)", [
        (k, r.get("description", ""), r.get("stereotype"), _list(r.get("statuses")), r.get("linkType"),
         r.get("direction"), r.get("other")) for k, r in sorted(cfg.get("coverageRules", {}).items())])
    ins("INSERT INTO coverage_violations VALUES (?,?,?)", V.coverage_violations(model))
    doc = list(DOC)
    if info["fts"] != "none":
        doc += FTS_DOC
        texts = [(eid, e.get("label", ""), e.get("topic", ""), e.get("notes") or "",
                  " ".join(str(v) for _, v in sorted((e.get("fields") or {}).items()) if isinstance(v, str)))
                 for eid, e in sorted(els.items())]
        con.execute("CREATE VIRTUAL TABLE elements_fts USING fts5(id UNINDEXED, label, topic, notes, fields, "
                    "tokenize=%r)" % _stemmer())
        ins("INSERT INTO elements_fts VALUES (?,?,?,?,?)", texts)
        if info["fts"] == "fts5+trigram":
            doc += TRIGRAM_DOC
            con.execute("CREATE VIRTUAL TABLE elements_trigram USING fts5(id UNINDEXED, label, topic, notes, "
                        "fields, tokenize='trigram')")
            ins("INSERT INTO elements_trigram VALUES (?,?,?,?,?)", texts)
    ins("INSERT INTO columns_doc VALUES (?,?,?)", doc)


def _prepare(folder):
    os.makedirs(folder, exist_ok=True)
    ignore = os.path.join(folder, ".gitignore")
    if not os.path.exists(ignore):
        with open(ignore, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("*\n")


def _swap(tmp, db):
    """os.replace, retried while another process holds the old file open (Windows). False = gave up."""
    end = time.monotonic() + SWAP_WAIT
    while True:
        try:
            os.replace(tmp, db)
            return True
        except PermissionError:
            if time.monotonic() >= end:
                return False
            time.sleep(0.05)


def build(model_path, _data=None):
    """Build the index of a model file now. Returns {path, built, private, seconds, elements, links, fts,
    integrity}. `private` is true when the old index could not be replaced in time (another process has it
    open): `path` is then a fresh copy for this caller only, to be removed with release()."""
    t0 = time.perf_counter()
    data, sha = _data or _read(model_path)
    model = M.parse(data.decode("utf-8"))
    problems = S.check_integrity(model)
    db = index_path(model_path)
    folder = os.path.dirname(db)
    _prepare(folder)
    fts = fts_mode()
    info = {"schema_version": str(SCHEMA_VERSION), "tool_version": VERSION,
            "model_file": os.path.basename(model_path), "model_sha256": sha,
            "format_version": str(model.get("formatVersion")),
            "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "integrity": "; ".join(problems) if problems else "ok", "fts": fts}
    tmp = "%s.tmp-%d-%d" % (db, os.getpid(), time.monotonic_ns())
    try:
        con = sqlite3.connect(tmp, isolation_level=None)
        try:
            con.execute("PRAGMA journal_mode=OFF")
            con.execute("PRAGMA synchronous=OFF")
            con.execute("BEGIN")
            _fill(con, model, info)
            con.execute("COMMIT")
        finally:
            con.close()
        private = not _swap(tmp, db)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return {"path": tmp if private else db, "built": True, "private": private,
            "seconds": round(time.perf_counter() - t0, 3), "elements": len(model["elements"]),
            "links": len(model["links"]), "fts": fts, "integrity": info["integrity"]}


def ensure(model_path):
    """The index of a model, rebuilt first when stale (ADR-032 §2): same result shape as build()."""
    data, sha = _read(model_path)
    db = index_path(model_path)
    meta = _meta(db)
    if _fresh(meta, sha):
        return {"path": db, "built": False, "private": False, "seconds": 0.0, "fts": meta.get("fts"),
                "integrity": meta.get("integrity")}
    return build(model_path, (data, sha))


def release(info):
    """Remove a private copy made by build() when the swap was not possible."""
    if info.get("private") and os.path.exists(info["path"]):
        os.remove(info["path"])


# -- reading: `sg.py sql` (ADR-032 §5, REQ-AGT-03/04) -----------------------------------------------------

TIME_LIMIT = 10.0         # seconds a query may run
COUNT_CEILING = 10000     # left-out rows counted at most; beyond that "more than N"
READ_PRAGMAS = {"table_info", "table_xinfo", "index_list", "index_info", "index_xinfo", "foreign_key_list",
                "data_version", "collation_list", "function_list", "compile_options"}   # these never write
_READING = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, getattr(sqlite3, "SQLITE_RECURSIVE", 33)}


class QueryError(Exception):
    """A query that was refused or failed."""


def _authorize(action, arg1, arg2, _db, _trigger):
    """Allow reading only: no write, DDL, ATTACH, transaction, writing pragma or extension loading."""
    if action in _READING:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION:
        return sqlite3.SQLITE_DENY if (arg2 or "").lower() == "load_extension" else sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_PRAGMA and (arg1 or "").lower() in READ_PRAGMAS:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def _open_ro(db):
    return sqlite3.connect("file:%s?mode=ro" % db.replace("\\", "/").replace("?", "%3f"), uri=True)


def _cut(v, width):
    if width and isinstance(v, str) and len(v) > width:
        return v[:width] + "…", True
    return v, False


def query(db, sql, limit=50, width=200):
    """Run one reading statement on an index file; 0 = no cap. Returns {columns, rows, total, truncatedRows,
    truncatedCells}, with `totalAtLeast` and total None when counting stopped at COUNT_CEILING."""
    con = _open_ro(db)
    try:
        con.execute("PRAGMA query_only = 1")
        con.set_authorizer(_authorize)
        deadline = time.monotonic() + TIME_LIMIT
        con.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10000)
        try:
            cur = con.execute(sql)
            columns = [d[0] for d in cur.description or ()]
            rows = cur.fetchmany(limit) if limit else cur.fetchall()
            total, at_least = len(rows), None
            if limit and len(rows) == limit:
                extra = 0
                while extra <= COUNT_CEILING:
                    got = len(cur.fetchmany(min(1000, COUNT_CEILING + 1 - extra)))
                    if not got:
                        break
                    extra += got
                if extra > COUNT_CEILING:
                    total, at_least = None, limit + extra
                else:
                    total += extra
        except (sqlite3.Error, sqlite3.Warning) as exc:
            msg = str(exc)
            if "not authorized" in msg:
                raise QueryError("refused: the index is read-only; only reading statements (SELECT, WITH) "
                                 "are allowed")
            if "interrupted" in msg:
                raise QueryError("refused: the query ran longer than the time limit of %g s" % TIME_LIMIT)
            raise QueryError("SQL error: %s" % msg)
    finally:
        con.close()
    cut_any, out = False, []
    for row in rows:
        cells = []
        for v in row:
            v, cut = _cut(v, width)
            cut_any = cut_any or cut
            cells.append(v)
        out.append(cells)
    res = {"columns": columns, "rows": out, "total": total, "truncatedRows": total != len(out),
           "truncatedCells": cut_any}
    if at_least is not None:
        res["totalAtLeast"] = at_least
    return res


def schema(db):
    """[(table, meaning, [(column, meaning)])] in the order of DOC, read from the index (REQ-AGT-05)."""
    con = _open_ro(db)
    try:
        doc = con.execute('SELECT "table", "column", meaning FROM columns_doc ORDER BY rowid').fetchall()
    finally:
        con.close()
    out = []
    for table, column, meaning in doc:
        if column == "":
            out.append((table, meaning, []))
        else:
            out[-1][2].append((column, meaning))
    return out
