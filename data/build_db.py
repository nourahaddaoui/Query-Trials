"""Build the database from the Kaggle CSVs.

Source: the classic "Employees" sample database (6 linked tables).
The CSVs live in data/raw/ and are NOT committed - they are ~92 MB, over
GitHub's comfortable limit. Anyone cloning the repo downloads them from
Kaggle and runs this script.

    python data/build_db.py

Produces data/database.sqlite, which is also gitignored. The repo carries
the recipe, not the output - that is what "runs from a clean clone" means.
"""

import sqlite3
import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "raw"
DB_PATH = BASE_DIR / "database.sqlite"

FILES_TO_LOAD = {
    "departments.csv": "departments",
    "dept_emp.csv": "dept_emp",
    "dept_manager.csv": "dept_manager",
    "employees.csv": "employees",
    "salaries.csv": "salaries",
    "titles.csv": "titles",
}

# Without these, several gold queries take 5-10 seconds because SQLite has to
# scan a million salary rows. Indexes do not change any answer - they only make
# the same answer arrive faster, which matters because the scorer times out.
INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_dept_emp_emp      ON dept_emp(emp_no)",
    "CREATE INDEX IF NOT EXISTS ix_dept_emp_dept     ON dept_emp(dept_no)",
    "CREATE INDEX IF NOT EXISTS ix_dept_emp_to       ON dept_emp(to_date)",
    "CREATE INDEX IF NOT EXISTS ix_salaries_emp      ON salaries(emp_no)",
    "CREATE INDEX IF NOT EXISTS ix_salaries_to       ON salaries(to_date)",
    "CREATE INDEX IF NOT EXISTS ix_titles_emp        ON titles(emp_no)",
    "CREATE INDEX IF NOT EXISTS ix_titles_to         ON titles(to_date)",
    "CREATE INDEX IF NOT EXISTS ix_dept_manager_dept ON dept_manager(dept_no)",
    "CREATE INDEX IF NOT EXISTS ix_employees_emp     ON employees(emp_no)",
]

# What we expect after a correct load. If these do not match, something went
# wrong with the CSVs and every question built on top would be wrong too.
EXPECTED_ROWS = {
    "departments": 9,
    "dept_manager": 24,
    "dept_emp": 331603,
    "employees": 300024,
    "salaries": 967330,
    "titles": 443308,
}


def build():
    missing = [n for n in FILES_TO_LOAD if not (RAW_DIR / n).exists()]
    if missing:
        sys.exit(
            f"Missing CSVs in {RAW_DIR}: {', '.join(missing)}\n"
            "Download the Employees dataset from Kaggle and unzip it there."
        )

    if DB_PATH.exists():
        DB_PATH.unlink()

    with sqlite3.connect(DB_PATH) as con:
        for csv_name, table in FILES_TO_LOAD.items():
            # index_col=0 drops the unnamed row-number column Kaggle ships with.
            df = pd.read_csv(RAW_DIR / csv_name, index_col=0)
            df.to_sql(table, con, if_exists="replace", index=False)
            print(f"  loaded {table:<13} {len(df):>7,} rows")

        for stmt in INDEXES:
            con.execute(stmt)
        con.execute("ANALYZE")

    check()
    print(f"\nBuilt {DB_PATH}")


def check():
    """Fail loudly if the data is not what we expect."""
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        problems = []
        for table, expected in EXPECTED_ROWS.items():
            got = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            if got != expected:
                problems.append(f"{table}: expected {expected:,}, got {got:,}")
        if problems:
            sys.exit("Row counts are wrong:\n  " + "\n  ".join(problems))
        print("\n  row counts OK")
    finally:
        con.close()


if __name__ == "__main__":
    build()
