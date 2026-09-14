"""Grade every raw answer. No human, no LLM - just execution.

For each line in results/raw/*.jssonl... (see run.py for how those are made):

  1. reject anything that is not a single read-only SELECT
  2. run the model's SQL against the real database (read-only, 5s timeout)
  3. hash the rows it returns, with the same rules the gold cache used
  4. same hash as the gold answer -> correct

The gold queries themselves are never run here - cache_gold.py ran each one
once and stored its hash. That keeps scoring fast and means a slow gold query
cannot fail an item the model got right.

    python -m src.score                    # scores the newest run
    python -m src.score --run 20260914-110716

Writes results/per_item.csv and results/summary.csv.
"""

import argparse
import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from src.settings import DB_PATH
from src.sqlutil import is_safe, run_query, result_hash
from src.run import percentile

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "results" / "raw"
GOLD_PATH = ROOT / "data" / "gold_results.json"
PER_ITEM = ROOT / "results" / "per_item.csv"
SUMMARY = ROOT / "results" / "summary.csv"

QUERY_TIMEOUT_S = 5

PER_ITEM_COLS = ["run_id", "item_id", "model_key", "model_name", "difficulty",
                 "status", "correct", "latency_ms", "prompt_tokens",
                 "completion_tokens", "parsed_sql", "note"]


def score_one(rec, gold, db_path):
    """One raw record -> (status, note). The seven statuses match the brief:
    a parse error, refusal or timeout counts as wrong, shown in its own column.
    """
    if rec.get("error"):
        return "api_error", str(rec["error"])[:120]

    sql = (rec.get("parsed_sql") or "").strip()
    if not sql:
        return "parse_error", "model returned nothing usable"

    if not is_safe(sql):
        return "unsafe", "not a single read-only SELECT"

    try:
        _cols, rows = run_query(sql, str(db_path), timeout_s=QUERY_TIMEOUT_S)
    except Exception as e:
        msg = str(e)
        if "interrupt" in msg.lower() or "timeout" in msg.lower():
            return "timeout", f"exceeded {QUERY_TIMEOUT_S}s"
        return "sql_error", msg[:120]

    if len(rows) != gold["n_rows"]:
        return "wrong_result", f"returned {len(rows)} rows, expected {gold['n_rows']}"
    if rows and len(rows[0]) != gold["n_cols"]:
        return "wrong_result", (f"returned {len(rows[0])} columns, "
                                f"expected {gold['n_cols']}")

    if result_hash(rows, gold["ordered"]) == gold["hash"]:
        return "correct", ""
    return "wrong_result", "same shape, different values"


def pick_run(requested):
    runs = sorted({p.name.split("__")[0] for p in RAW_DIR.glob("*.jsonl")})
    if not runs:
        sys.exit("No raw files in results/raw/. Run: python -m src.run")
    if requested:
        if requested not in runs:
            sys.exit(f"No run '{requested}'. Available: {', '.join(runs)}")
        return requested
    return runs[-1]          # newest, since run_ids are timestamps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", help="run_id to score (default: newest)")
    args = ap.parse_args()

    db = ROOT / DB_PATH
    if not db.exists():
        sys.exit(f"No database at {db}. Run: python data/build_db.py")
    if not GOLD_PATH.exists():
        sys.exit("No gold cache. Run: python -m src.cache_gold")
    gold_all = json.loads(GOLD_PATH.read_text())

    run_id = pick_run(args.run)
    files = sorted(RAW_DIR.glob(f"{run_id}__*.jsonl"))
    print(f"Scoring run {run_id}  ({len(files)} model file(s))\n")

    # --- refuse to compare runs made with different prompts ---
    shas = set()
    records = []
    for f in files:
        for line in open(f, encoding="utf-8"):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue          # half-written line from an interrupted run
            records.append(rec)
            shas.add(rec.get("prompt_sha"))
    if len(shas) > 1:
        sys.exit(f"Refusing to score: raw files mix prompt fingerprints "
                 f"{sorted(shas)}. These runs are not comparable.")

    # --- score every record ---
    rows_out = []
    for rec in records:
        gold = gold_all.get(rec["item_id"])
        if gold is None:
            status, note = "sql_error", "item not in gold cache - re-run cache_gold"
        else:
            status, note = score_one(rec, gold, db)
        rows_out.append({
            "run_id": rec["run_id"],
            "item_id": rec["item_id"],
            "model_key": rec["model_key"],
            "model_name": rec["model_name"],
            "difficulty": rec.get("difficulty", ""),
            "status": status,
            "correct": status == "correct",
            "latency_ms": rec["latency_ms"],
            "prompt_tokens": rec["prompt_tokens"],
            "completion_tokens": rec["completion_tokens"],
            "parsed_sql": rec.get("parsed_sql", ""),
            "note": note,
        })

    rows_out.sort(key=lambda r: (r["model_key"], r["item_id"]))
    with open(PER_ITEM, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PER_ITEM_COLS)
        w.writeheader()
        w.writerows(rows_out)

    # --- summarise per model ---
    by_model = defaultdict(list)
    for r in rows_out:
        by_model[r["model_key"]].append(r)

    sum_cols = ["model_key", "model_name", "n_items", "n_correct", "accuracy",
                "p50_ms", "p95_ms", "mean_ms", "n_wrong_result", "n_sql_error",
                "n_timeout", "n_unsafe", "n_parse_error", "n_api_error"]
    sum_rows = []
    for key in ("top", "cheap", "local"):
        rs = by_model.get(key)
        if not rs:
            continue
        lats = [r["latency_ms"] for r in rs]
        counts = defaultdict(int)
        for r in rs:
            counts[r["status"]] += 1
        n = len(rs)
        ok = counts["correct"]
        sum_rows.append({
            "model_key": key,
            "model_name": rs[0]["model_name"],
            "n_items": n,
            "n_correct": ok,
            "accuracy": f"{ok / n:.0%}",
            "p50_ms": round(percentile(lats, 50)),
            "p95_ms": round(percentile(lats, 95)),
            "mean_ms": round(statistics.mean(lats)),
            "n_wrong_result": counts["wrong_result"],
            "n_sql_error": counts["sql_error"],
            "n_timeout": counts["timeout"],
            "n_unsafe": counts["unsafe"],
            "n_parse_error": counts["parse_error"],
            "n_api_error": counts["api_error"],
        })

    with open(SUMMARY, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=sum_cols)
        w.writeheader()
        w.writerows(sum_rows)

    # --- console table ---
    print(f"{'model':<10}{'correct':>10}{'accuracy':>10}{'p50':>8}{'p95':>8}"
          f"{'errors':>8}")
    for s in sum_rows:
        errs = s["n_items"] - s["n_correct"] - s["n_wrong_result"]
        print(f"{s['model_key']:<10}{s['n_correct']:>6}/{s['n_items']:<3}"
              f"{s['accuracy']:>10}{s['p50_ms']:>7}m{s['p95_ms']:>7}m"
              f"{errs:>8}")

    print(f"\nWrote {PER_ITEM.relative_to(ROOT)} ({len(rows_out)} rows)")
    print(f"Wrote {SUMMARY.relative_to(ROOT)} ({len(sum_rows)} rows)")
    print("\nNext: python -m src.cost")


if __name__ == "__main__":
    main()
