"""REQ-AGT-03/04, ADR-032 §5: `sg.py sql`, a read-only query on the index with capped output."""
import hashlib
import json
import os

import pytest

from conftest import do
from specgraph import cli, index as I


@pytest.fixture
def run(capsys, ada):
    """run(*args) -> (exit code, stdout, stderr) of `sg.py --file <model> sql ...`, in this process."""
    def go(*args):
        code = cli.main(["--file", ada.path, "sql"] + list(args))
        out, err = capsys.readouterr()
        return code, out, err
    return go


@pytest.fixture
def many(ada):
    """A folder with 60 requirements, one with a 300-character topic and one with notes on two lines."""
    fid = do(ada, "folder.create", name="Many")
    ops = [{"op": "element.create", "args": {"stereotype": "REQ", "folder": fid, "topic": "Requirement %02d" % i}}
           for i in range(58)]
    ops.append({"op": "element.create", "args": {"stereotype": "REQ", "folder": fid, "topic": "L" * 300}})
    ops.append({"op": "element.create", "args": {"stereotype": "REQ", "folder": fid, "topic": "Two lines",
                                                 "notes": "first\nsecond"}})
    ada.apply(ops)
    return fid


def digest(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


# -- AGT-03: read only ---------------------------------------------------------------------------------

def test_agt03_reading_queries_work(run, many):
    code, out, _ = run("SELECT count(*) AS n FROM elements WHERE stereotype = 'REQ'", "--json")
    assert code == 0 and json.loads(out)["rows"] == [[60]]
    reads = [
        "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r WHERE n < 3) SELECT n FROM r",
        "SELECT name FROM pragma_table_info('elements')",
        "SELECT e.id FROM elements e LEFT JOIN links l ON l.source = e.id OR l.target = e.id WHERE l.id IS NULL",
        "SELECT count(*) FROM v_links",
        "select upper(topic), length(topic) from elements limit 1",
    ]
    if I.fts_mode() != "none":
        reads.append("SELECT id FROM elements_fts WHERE elements_fts MATCH 'requirement*' ORDER BY rank LIMIT 3")
    for q in reads:
        code, out, err = run(q)
        assert code == 0, (q, err)


@pytest.mark.parametrize("q", [
    "INSERT INTO users VALUES ('mallory', 'admin')",
    "UPDATE elements SET status = 'approved'",
    "DELETE FROM links",
    "REPLACE INTO meta VALUES ('integrity', 'ok')",
    "CREATE TABLE x (a)",
    "CREATE TEMP TABLE x (a)",
    "CREATE TEMP VIEW v AS SELECT 1",
    "DROP TABLE elements",
    "ALTER TABLE elements ADD COLUMN x",
    "CREATE INDEX i ON elements(topic)",
    "ATTACH DATABASE 'other.db' AS other",
    "DETACH DATABASE main",
    "PRAGMA user_version = 5",
    "PRAGMA query_only = 0",
    "PRAGMA journal_mode = WAL",
    "PRAGMA writable_schema = 1",
    "VACUUM",
    "VACUUM INTO 'copy.db'",
    "BEGIN",
    "SAVEPOINT a",
    "SELECT load_extension('evil')",
    "SELECT 1; DELETE FROM links",
    "ANALYZE",
    "REINDEX",
])
def test_agt03_anything_but_reading_is_refused(run, ada, many, q):
    run("SELECT 1")                                  # the index exists and is fresh
    db = I.index_path(ada.path)
    before = digest(db)
    code, out, err = run(q)
    assert code == 2, (q, out, err)
    assert out == "" and err.strip()
    assert digest(db) == before
    assert not os.path.exists(os.path.join(os.path.dirname(ada.path), "copy.db"))
    assert not os.path.exists(os.path.join(os.path.dirname(ada.path), "other.db"))


def test_agt03_errors_are_refused_with_a_message(run, many):
    code, _, err = run("SELEC id FROM elements")
    assert code == 2 and "syntax error" in err
    code, _, err = run("SELECT no_such FROM elements")
    assert code == 2 and "no such column" in err


def test_agt03_runaway_query_is_stopped(run, many, monkeypatch):
    monkeypatch.setattr(I, "TIME_LIMIT", 0.3)
    code, _, err = run("WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r) SELECT count(*) FROM r")
    assert code == 2 and "time limit" in err


def test_agt03_sql_rebuilds_a_stale_index_first(run, ada, many):
    run("SELECT 1")
    do(ada, "element.create", stereotype="ADR", topic="Fresh decision", folder=many)
    code, out, _ = run("SELECT topic FROM elements WHERE stereotype = 'ADR'", "--json")
    assert code == 0 and json.loads(out)["rows"] == [["Fresh decision"]]


def test_agt03_hand_edited_model_gives_a_warning(run, ada, many):
    from specgraph import model as M
    m = ada.load()
    next(iter(m["elements"].values()))["topic"] = "by hand"
    M.save(ada.path, m)
    code, out, err = run("SELECT count(*) FROM elements WHERE topic = 'by hand'")
    assert code == 0 and "warning" in err and "stamp" in err
    assert out.splitlines()[1] == "1"


# -- AGT-04: capped output -----------------------------------------------------------------------------

def test_agt04_text_output_is_a_compact_table_with_a_footer(run, many):
    code, out, _ = run("SELECT topic, status FROM elements WHERE topic LIKE 'Requirement 0%' ORDER BY topic")
    lines = out.splitlines()
    assert code == 0
    assert lines[0] == "topic | status"
    assert lines[1].startswith("Requirement 00 | ")
    assert lines[-1] == "(10 rows)"


def test_agt04_rows_are_capped_at_50_by_default_and_say_how_many_were_left_out(run, many):
    code, out, _ = run("SELECT id FROM elements")
    lines = out.splitlines()
    assert len(lines) == 1 + 50 + 1
    assert lines[-1] == "(50 of 60 rows shown; refine the query or use LIMIT/OFFSET, or --limit N)"
    code, out, _ = run("SELECT id FROM elements", "--json")
    res = json.loads(out)
    assert len(res["rows"]) == 50 and res["total"] == 60 and res["truncatedRows"] is True


def test_agt04_row_cap_is_configurable(run, many, monkeypatch):
    assert len(run("SELECT id FROM elements", "--limit", "5")[1].splitlines()) == 1 + 5 + 1
    assert run("SELECT id FROM elements", "--limit", "0")[1].splitlines()[-1] == "(60 rows)"
    monkeypatch.setenv("SPECGRAPH_SQL_LIMIT", "7")
    assert len(run("SELECT id FROM elements")[1].splitlines()) == 1 + 7 + 1
    assert len(run("SELECT id FROM elements", "--limit", "3")[1].splitlines()) == 1 + 3 + 1   # the call wins
    monkeypatch.setenv("SPECGRAPH_SQL_LIMIT", "many")
    code, _, err = run("SELECT 1")
    assert code == 2 and "SPECGRAPH_SQL_LIMIT" in err


def test_agt04_counting_left_out_rows_stops_at_a_ceiling(run, many, monkeypatch):
    monkeypatch.setattr(I, "COUNT_CEILING", 20)
    _, out, _ = run("SELECT id FROM elements", "--limit", "5")
    assert out.splitlines()[-1] == "(5 of more than 25 rows shown; refine the query or use LIMIT/OFFSET, or --limit N)"
    res = json.loads(run("SELECT id FROM elements", "--limit", "5", "--json")[1])
    assert res["total"] is None and res["totalAtLeast"] == 26


def test_agt04_long_cells_are_cut_at_200_characters_by_default(run, many, monkeypatch):
    q = "SELECT topic FROM elements WHERE topic LIKE 'LLL%'"
    lines = run(q)[1].splitlines()
    assert lines[1] == "L" * 200 + "…"
    assert "cut at 200 characters" in lines[-1] and "--width" in lines[-1]
    assert run(q, "--width", "10")[1].splitlines()[1] == "L" * 10 + "…"
    assert run(q, "--width", "0")[1].splitlines()[1] == "L" * 300
    monkeypatch.setenv("SPECGRAPH_SQL_WIDTH", "20")
    res = json.loads(run(q, "--json")[1])
    assert res["rows"] == [["L" * 20 + "…"]] and res["truncatedCells"] is True


def test_agt04_text_shows_nulls_and_line_breaks_on_one_line(run, ada, many):
    _, out, _ = run("SELECT n.notes, NULL AS empty FROM element_notes n")
    assert out.splitlines()[1] == "first\\nsecond | NULL"
    res = json.loads(run("SELECT n.notes, NULL AS empty FROM element_notes n", "--json")[1])
    assert res["rows"] == [["first\nsecond", None]]


def test_agt04_json_shape(run, many):
    res = json.loads(run("SELECT topic, notes_chars FROM elements WHERE topic = 'Two lines'", "--json")[1])
    assert res == {"columns": ["topic", "notes_chars"], "rows": [["Two lines", 12]], "total": 1,
                   "truncatedRows": False, "truncatedCells": False}


def test_agt05_schema_lists_every_table_and_column_with_its_meaning(run, ada, many):
    code, out, _ = run("--schema")
    assert code == 0
    assert "config_stereotypes: element types" in out
    assert "  description: what this type means in this project; may be empty" in out
    assert ("elements_fts:" in out) == (I.fts_mode() != "none")
    code, _, err = run()
    assert code == 2 and "query" in err


@pytest.mark.skipif(not hasattr(__import__("sqlite3").Connection, "setlimit"), reason="needs Python 3.11+")
def test_sec_a_query_cannot_build_huge_values(run, many):
    code, _, err = run("WITH RECURSIVE r(s, n) AS (SELECT 'xxxxxxxx', 0 UNION ALL SELECT s || s, n + 1 FROM r "
                       "WHERE n < 40) SELECT max(length(s)) FROM r")
    assert code == 2 and "too big" in err
