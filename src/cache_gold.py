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
import sqlite3
import sys
import time
from pathlib import Path

from src.settings import DB_PATH, ITEMS_PATH
from src.sqlutil import result_hash, is_ordered

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "gold_results.json"
GOLD_TIMEOUT_S = 120  # generous on purpose - this runs once, not 50 times


def main():
    db = ROOT / DB_PATH
    items_file = ROOT / ITEMS_PATH
    if not db.exists():
        sys.exit(f"No database at {db}. Run: python data/build_db.py")
    if not items_file.exists():
        sys.exit(f"No items at {items_file}")

    items = [json.loads(line) for line in open(items_file, encoding="utf-8")]
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=GOLD_TIMEOUT_S)

    cache, failures, slowest = {}, [], []
    for item in items:
        sql = item["gold_sql"]
        t0 = time.perf_counter()
        try:
            rows = con.execute(sql).fetchall()
        except Exception as e:
            failures.append((item["id"], str(e)[:70]))
            continue
        elapsed = time.perf_counter() - t0
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
        print(f"  {item['id']}  {elapsed:6.2f}s  {len(rows):>7,} rows{flag}")

    con.close()

    if failures:
        print("\nFAILED:")
        for i, e in failures:
            print(f"  {i}: {e}")
        sys.exit("Fix these before scoring.")

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
