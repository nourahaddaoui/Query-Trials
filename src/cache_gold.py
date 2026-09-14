"""Run every gold query once and save a fingerprint of its answer.

Why this exists: a few gold queries scan the 967k-row salaries table and take
several seconds. If scoring runs the gold query for every item, those seconds
are paid 50 times over - and worse, a gold query that exceeds the scorer's
timeout would fail the item through no fault of the model.

So we run each gold query ONCE here, with a generous timeout, and store a hash
of its normalised result. score.py then runs only the model's query and
compares hashes. Scoring becomes one query per item instead of two, and the
speed of the gold query stops mattering.

    python -m src.cache_gold

Writes data/gold_results.json. Re-run it if items.jsonl changes.
"""

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

from src.settings import DB_PATH, ITEMS_PATH
from src.sqlutil import result_hash, is_ordered

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "gold_results.json"

# Generous on purpose - this runs once, not 50 times. Overridable because a
# slow machine may need more (GOLD_TIMEOUT_S=300 python -m src.cache_gold).
#
# The clean-clone test caught a bug here: the timeout was originally passed to
# sqlite3.connect(), but that is a LOCK timeout - it does nothing for a slow
# query, so on a weak machine the script hung forever with no output. The real
# cap is enforced below with a progress handler, which SQLite calls
# periodically during query execution and which can interrupt it.
GOLD_TIMEOUT_S = float(os.environ.get("GOLD_TIMEOUT_S", 120))


def run_with_deadline(con, sql, seconds):
    """Run one query, interrupting it if it exceeds the deadline."""
    t0 = time.perf_counter()

    def guard():
        return 1 if time.perf_counter() - t0 > seconds else 0

    con.set_progress_handler(guard, 50_000)   # check every ~50k VM steps
    try:
        return con.execute(sql).fetchall(), time.perf_counter() - t0
    finally:
        con.set_progress_handler(None, 0)


def main():
    db = ROOT / DB_PATH
    items_file = ROOT / ITEMS_PATH
    if not db.exists():
        sys.exit(f"No database at {db}. Run: python data/build_db.py")
    if not items_file.exists():
        sys.exit(f"No items at {items_file}")

    items = [json.loads(line) for line in open(items_file, encoding="utf-8")]
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)

    # Resume: keep answers already cached, redo only what is missing. An
    # interrupted caching run (Ctrl+C, timeout, crash) then costs nothing.
    cache = {}
    if OUT_PATH.exists():
        cache = json.loads(OUT_PATH.read_text())
        todo = [i for i in items if i["id"] not in cache]
        if len(todo) < len(items):
            print(f"  resuming - {len(cache)} already cached, "
                  f"{len(todo)} to do", flush=True)
        items = todo

    failures, slowest = [], []
    for item in items:
        sql = item["gold_sql"]
        try:
            rows, elapsed = run_with_deadline(con, sql, GOLD_TIMEOUT_S)
        except sqlite3.OperationalError as e:
            if "interrupt" in str(e).lower():
                failures.append((item["id"],
                                 f"exceeded {GOLD_TIMEOUT_S:.0f}s - raise "
                                 f"GOLD_TIMEOUT_S or simplify the query"))
            else:
                failures.append((item["id"], str(e)[:70]))
            continue
        except Exception as e:
            failures.append((item["id"], str(e)[:70]))
            continue
        ordered = is_ordered(sql)

        cache[item["id"]] = {
            "hash": result_hash(rows, ordered),
            "n_rows": len(rows),
            "n_cols": len(rows[0]) if rows else 0,
            "ordered": ordered,
            "seconds": round(elapsed, 2),
        }
        slowest.append((elapsed, item["id"]))
        flag = "  <-- returns nothing" if not rows else ""
        print(f"  {item['id']}  {elapsed:6.2f}s  {len(rows):>7,} rows{flag}",
              flush=True)
        # checkpoint after every item, so an interruption loses nothing
        OUT_PATH.write_text(json.dumps(cache, indent=1), encoding="utf-8")

    con.close()

    if failures:
        # Still write what succeeded - a partial cache plus a clear error
        # beats losing everything to one bad query.
        OUT_PATH.write_text(json.dumps(cache, indent=1), encoding="utf-8")
        print(f"\nWrote {len(cache)} answers, but {len(failures)} FAILED:")
        for i, e in failures:
            print(f"  {i}: {e}")
        sys.exit("Fix these (or raise GOLD_TIMEOUT_S) before scoring.")

    empty = [i for i, c in cache.items() if c["n_rows"] == 0]
    if empty:
        print(f"\nWARNING - these return no rows: {', '.join(empty)}")
        print("A model could return an empty result from a wrong query and still match.")

    OUT_PATH.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    slowest.sort(reverse=True)
    print(f"\nCached {len(cache)} gold results -> {OUT_PATH}")
    print("Slowest:", ", ".join(f"{i} ({s:.1f}s)" for s, i in slowest[:3]))


if __name__ == "__main__":
    main()
