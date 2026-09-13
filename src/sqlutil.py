"""Small helpers shared by the UI and by score.py.

Keeping these in one place means the UI and the real scoring run use exactly
the same parsing and the same safety rules.
"""

import hashlib
import re
import sqlite3

FENCE = re.compile(r"^```(?:sql)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def parse_sql(raw: str) -> str:
    """Pull the SQL out of whatever the model returned.

    We ask for bare SQL, but models sometimes wrap it in markdown fences
    anyway. We strip them. Important: the SAME parser runs on all three
    models, so nobody gets an advantage.
    """
    text = FENCE.sub("", raw or "").strip()
    # Some models add a leading label like "SQL:" - drop it.
    text = re.sub(r"^\s*SQL\s*:\s*", "", text, flags=re.IGNORECASE)
    return text.strip().rstrip(";").strip()


def is_safe(sql: str) -> bool:
    """Only allow a single read-only SELECT.

    Anything that could change or inspect the database is rejected. In the
    real run this counts as a wrong answer, not as a crash.
    """
    s = sql.strip().lower()
    if not s.startswith(("select", "with")):
        return False
    banned = ("drop", "delete", "update ", "insert", "alter",
              "attach", "pragma", "create", "replace")
    return not any(b in s for b in banned)


def run_query(sql: str, db_path: str, timeout_s: int = 5):
    """Run a query against a read-only connection.

    Returns (columns, rows). Raises on bad SQL - the caller decides what a
    failure means.
    """
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=timeout_s)
    try:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall()
        return cols, rows
    finally:
        con.close()


def normalize(rows, ordered: bool):
    """Turn a result set into something two queries can be compared on.

    Column NAMES are ignored on purpose - a different alias is still a correct
    answer. Column COUNT and the values matter.

    Floats are rounded because SQLite can return 89005.789999 where the model's
    query returns 89005.79, and those are the same answer.

    If the gold query has an ORDER BY, row order is part of the answer, so we
    keep it. If it does not, we sort - otherwise a correct query that happens
    to return rows in a different order would be marked wrong.
    """
    out = []
    for row in rows:
        cells = []
        for v in row:
            if v is None:
                cells.append("\x00NULL")
            elif isinstance(v, float):
                cells.append(f"{round(v, 6):.6f}")
            else:
                cells.append(str(v).strip())
        out.append(tuple(cells))
    return out if ordered else sorted(out)


def result_hash(rows, ordered: bool) -> str:
    """A short fingerprint of a result set.

    Lets us store the gold answer for a query that returns 300,000 rows
    without storing 300,000 rows.
    """
    norm = normalize(rows, ordered)
    h = hashlib.sha256()
    h.update(str(len(norm)).encode())
    for row in norm:
        h.update(b"\x01".join(c.encode("utf-8", "replace") for c in row))
        h.update(b"\x02")
    return h.hexdigest()[:16]


def is_ordered(sql: str) -> bool:
    """Does this query's own ORDER BY make row order meaningful?

    We only look at the gold query - the model's query is judged against the
    gold query's rules, not its own.
    """
    return "order by" in sql.lower()


def get_schema(db_path: str) -> str:
    """Read the CREATE TABLE statements straight out of the database.

    This text goes into the prompt, so the models see the real schema and we
    never have to keep a copy in sync by hand.
    """
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"
        ).fetchall()
        return "\n\n".join(r[0] for r in rows)
    finally:
        con.close()
