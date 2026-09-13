"""Send every item to a model, one at a time, and save what comes back.

This is the measurement itself, so it is deliberately boring:

  * one model call per item, nothing clever
  * strictly sequential - running calls in parallel would measure our network
    and thread pool instead of the models
  * no retries - a failure is a result, and the brief says a timeout or a
    refusal counts as wrong
  * nothing is judged here. We save the raw answer and let score.py decide.

Usage
-----
    python -m src.run --model local --split dev          # try 10 practice items
    python -m src.run --model all   --split test         # the real run
    python -m src.run --model local --split test --limit 5

Writes results/raw/<run_id>__<model>.jsonl - one JSON object per line.
"""

import argparse
import json
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from src import adapters, prompt as prompt_mod
from src.settings import MODELS, DB_PATH, ITEMS_PATH, TEMPERATURE, MAX_TOKENS
from src.sqlutil import get_schema, parse_sql

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "results" / "raw"


def load_items(split, limit):
    path = ROOT / ITEMS_PATH
    if not path.exists():
        sys.exit(f"No items at {path}")
    items = [json.loads(line) for line in open(path, encoding="utf-8")]
    if split != "all":
        items = [i for i in items if i.get("split") == split]
    # Same items, same order, every model. Sorting by id makes that explicit
    # instead of relying on the order they happen to sit in the file.
    items.sort(key=lambda i: i["id"])
    return items[:limit] if limit else items


def run_one_model(key, items, schema, run_id):
    model_name = MODELS[key]["name"]
    adapter = adapters.get(key)

    # The local model loads from disk on its first call. That is real, but it
    # is not what we are measuring, so we throw the first few away - and we
    # say so in the report rather than hiding it.
    if key == "local":
        print("  warming up (3 calls, not counted)...", flush=True)
        adapter.warm_up(3)

    out_path = RAW_DIR / f"{run_id}__{key}.jsonl"
    latencies, errors = [], 0

    with open(out_path, "w", encoding="utf-8") as f:
        for n, item in enumerate(items, 1):
            text = prompt_mod.build(schema, item["question"])
            res = adapter.generate(text)

            record = {
                "run_id": run_id,
                "item_id": item["id"],
                "model_key": key,
                "model_name": model_name,
                "difficulty": item.get("difficulty"),
                "question": item["question"],
                "raw_output": res["text"],
                "parsed_sql": parse_sql(res["text"]),
                "latency_ms": res["latency_ms"],
                "prompt_tokens": res["prompt_tokens"],
                "completion_tokens": res["completion_tokens"],
                "tokens_per_sec": res.get("tokens_per_sec"),
                "error": res["error"],
                "prompt_sha": prompt_mod.fingerprint(),
                "temperature": TEMPERATURE,
                "max_tokens": MAX_TOKENS,
                "ts_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()          # so a crash at item 47 does not lose items 1-46

            latencies.append(res["latency_ms"])
            if res["error"]:
                errors += 1
                print(f"  [{n:>2}/{len(items)}] {item['id']}  ERROR  "
                      f"{res['error'][:60]}", flush=True)
            else:
                print(f"  [{n:>2}/{len(items)}] {item['id']}  "
                      f"{res['latency_ms']:>7.0f} ms", flush=True)

    return out_path, latencies, errors


def percentile(values, p):
    """p50 and p95 the simple way: sort, then index.

    We report these instead of the average because one very slow answer barely
    moves an average but is exactly the thing a user would notice.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, int(round((p / 100) * len(ordered))) - 1))
    return ordered[k]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="local",
                    choices=["top", "cheap", "local", "all"])
    ap.add_argument("--split", default="dev", choices=["dev", "test", "all"])
    ap.add_argument("--limit", type=int, default=0,
                    help="only the first N items (for quick tests)")
    args = ap.parse_args()

    db = ROOT / DB_PATH
    if not db.exists():
        sys.exit(f"No database at {db}. Run: python data/build_db.py")

    items = load_items(args.split, args.limit)
    if not items:
        sys.exit(f"No items in split '{args.split}'")

    schema = get_schema(str(db))
    keys = ["top", "cheap", "local"] if args.model == "all" else [args.model]
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    print(f"run_id     {run_id}")
    print(f"items      {len(items)}  (split={args.split})")
    print(f"prompt     {prompt_mod.fingerprint()}   temp={TEMPERATURE} "
          f"max_tokens={MAX_TOKENS}")
    print(f"machine    {platform.machine()}  {platform.system()} "
          f"{platform.release()}")
    print()

    summary = []
    for key in keys:
        print(f"{MODELS[key]['label']}  ({MODELS[key]['name']})")
        t0 = time.perf_counter()
        path, lats, errs = run_one_model(key, items, schema, run_id)
        wall = time.perf_counter() - t0
        summary.append((key, lats, errs, wall))
        print(f"  -> {path.relative_to(ROOT)}   {wall:.0f}s total\n")

    print("=" * 58)
    print(f"{'model':<22}{'p50':>9}{'p95':>9}{'mean':>9}{'err':>6}")
    for key, lats, errs, _ in summary:
        print(f"{MODELS[key]['label']:<22}"
              f"{percentile(lats, 50):>8.0f}m"
              f"{percentile(lats, 95):>8.0f}m"
              f"{statistics.mean(lats):>8.0f}m"
              f"{errs:>6}")
    print("=" * 58)
    print("\nNothing has been scored yet. Next:  python -m src.score")


if __name__ == "__main__":
    main()
