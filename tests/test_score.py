"""Tests for the scoring rules.

The scorer decides every accuracy number in the report. If it is subtly wrong,
every number is wrong and nothing else catches it - so these tests cover the
cases where a naive comparison silently gives the wrong verdict.

    python -m pytest tests/ -q
"""

import sqlite3

import pytest

from src.sqlutil import parse_sql, is_safe, normalize, result_hash, is_ordered
from src.score import score_one


# ---------------------------------------------------------------- parsing

def test_strips_markdown_fences():
    assert parse_sql("```sql\nSELECT 1;\n```") == "SELECT 1"

def test_strips_bare_fences():
    assert parse_sql("```\nSELECT 1\n```") == "SELECT 1"

def test_strips_sql_label():
    assert parse_sql("SQL: SELECT name FROM t;") == "SELECT name FROM t"

def test_plain_passthrough():
    assert parse_sql("SELECT 1") == "SELECT 1"


# ---------------------------------------------------------------- safety

def test_select_allowed():
    assert is_safe("SELECT * FROM t")

def test_cte_allowed():
    assert is_safe("WITH x AS (SELECT 1) SELECT * FROM x")

@pytest.mark.parametrize("bad", [
    "DROP TABLE t",
    "DELETE FROM t",
    "INSERT INTO t VALUES (1)",
    "UPDATE t SET a=1",
    "PRAGMA table_info(t)",
    "ATTACH DATABASE 'x' AS y",
])
def test_writes_rejected(bad):
    assert not is_safe(bad)


# ------------------------------------------------------- comparison rules

def test_row_order_ignored_when_unordered():
    a = [(1, "x"), (2, "y")]
    b = [(2, "y"), (1, "x")]
    assert result_hash(a, ordered=False) == result_hash(b, ordered=False)

def test_row_order_matters_when_ordered():
    a = [(1, "x"), (2, "y")]
    b = [(2, "y"), (1, "x")]
    assert result_hash(a, ordered=True) != result_hash(b, ordered=True)

def test_float_rounding():
    # SQLite AVG can give 89005.789999999; a model's ROUND gives 89005.79.
    # Same answer.
    assert result_hash([(89005.789999999,)], False) == \
           result_hash([(89005.79,)], False)

def test_null_is_not_zero():
    assert result_hash([(None,)], False) != result_hash([(0,)], False)

def test_null_is_not_the_string_null():
    assert result_hash([(None,)], False) != result_hash([("NULL",)], False)

def test_duplicates_matter():
    # A missing DISTINCT is a real error, not a formatting difference.
    assert result_hash([(1,), (1,)], False) != result_hash([(1,)], False)

def test_int_equals_string_of_same_value():
    # SQLite is loosely typed: COUNT returns int, some paths return "1".
    assert result_hash([(1,)], False) == result_hash([("1",)], False)

def test_empty_equals_empty():
    assert result_hash([], False) == result_hash([], False)

def test_is_ordered_detection():
    assert is_ordered("SELECT a FROM t ORDER BY a")
    assert not is_ordered("SELECT a FROM t")


# ------------------------------------------------- score_one, end to end

@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "t.sqlite"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE emp (id INTEGER, name TEXT, dept TEXT);
        INSERT INTO emp VALUES (1,'Ali','Sales'), (2,'Sara','Sales'),
                               (3,'Omar','HR');
    """)
    con.commit()
    con.close()
    return str(path)


def gold_for(sql, db):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = con.execute(sql).fetchall()
    con.close()
    o = is_ordered(sql)
    return {"hash": result_hash(rows, o), "n_rows": len(rows),
            "n_cols": len(rows[0]) if rows else 0, "ordered": o}


def rec(sql, error=None):
    return {"parsed_sql": sql, "error": error}


def test_correct_same_query(db):
    g = gold_for("SELECT COUNT(*) FROM emp", db)
    assert score_one(rec("SELECT COUNT(*) FROM emp"), g, db)[0] == "correct"

def test_correct_different_alias(db):
    g = gold_for("SELECT COUNT(*) AS n FROM emp", db)
    status, _ = score_one(rec("SELECT COUNT(id) AS total FROM emp"), g, db)
    assert status == "correct"          # column names are ignored

def test_wrong_values(db):
    g = gold_for("SELECT COUNT(*) FROM emp WHERE dept='Sales'", db)
    status, _ = score_one(rec("SELECT COUNT(*) FROM emp"), g, db)
    assert status == "wrong_result"

def test_wrong_shape_more_columns(db):
    g = gold_for("SELECT name FROM emp", db)
    status, _ = score_one(rec("SELECT name, dept FROM emp"), g, db)
    assert status == "wrong_result"

def test_sql_error(db):
    g = gold_for("SELECT COUNT(*) FROM emp", db)
    status, _ = score_one(rec("SELECT nope FROM emp"), g, db)
    assert status == "sql_error"

def test_unsafe(db):
    g = gold_for("SELECT COUNT(*) FROM emp", db)
    status, _ = score_one(rec("DROP TABLE emp"), g, db)
    assert status == "unsafe"

def test_api_error(db):
    g = gold_for("SELECT COUNT(*) FROM emp", db)
    status, _ = score_one(rec("", error="ConnectionError: refused"), g, db)
    assert status == "api_error"

def test_parse_error(db):
    g = gold_for("SELECT COUNT(*) FROM emp", db)
    status, _ = score_one(rec("   "), g, db)
    assert status == "parse_error"

def test_unordered_gold_accepts_any_row_order(db):
    g = gold_for("SELECT name FROM emp", db)   # no ORDER BY in gold
    status, _ = score_one(rec("SELECT name FROM emp ORDER BY name DESC"),
                          g, db)
    assert status == "correct"

def test_ordered_gold_rejects_wrong_order(db):
    g = gold_for("SELECT name FROM emp ORDER BY name ASC", db)
    status, _ = score_one(rec("SELECT name FROM emp ORDER BY name DESC"),
                          g, db)
    assert status == "wrong_result"
