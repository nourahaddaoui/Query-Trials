"""Check everything a run needs, before starting a run that takes an hour.

Every check here exists because it actually went wrong at least once:

  * the disk filled up and silently produced a malformed database
  * the database did not exist yet
  * Ollama was not installed, then not running
  * the model tag in settings.py did not match what was pulled
  * the API key was an empty string, so 50 calls failed one by one
  * the gold cache was stale after items.jsonl changed

    python -m src.doctor
"""

import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

from src import prompt as prompt_mod
from src.settings import (MODELS, DB_PATH, ITEMS_PATH, OLLAMA_URL,
                          TEMPERATURE, MAX_TOKENS)

ROOT = Path(__file__).resolve().parent.parent
GOLD_PATH = ROOT / "data" / "gold_results.json"

OK, WARN, FAIL = "ok  ", "warn", "FAIL"
_rows = []


def check(name, status, detail=""):
    _rows.append((status, name, detail))
    mark = {OK: "  ok  ", WARN: " warn ", FAIL: " FAIL "}[status]
    print(f"[{mark}] {name}" + (f"\n         {detail}" if detail else ""))


# ---------------------------------------------------------------- disk

def check_disk():
    free_gb = shutil.disk_usage(ROOT).free / (1024 ** 3)
    if free_gb < 1:
        check("disk space", FAIL,
              f"only {free_gb:.1f} GB free - writes will corrupt silently")
    elif free_gb < 5:
        check("disk space", WARN, f"{free_gb:.1f} GB free - tight for a model")
    else:
        check("disk space", OK, f"{free_gb:.0f} GB free")


# ---------------------------------------------------------------- data

def check_db():
    db = ROOT / DB_PATH
    if not db.exists():
        check("database", FAIL, f"missing - run: python data/build_db.py")
        return None
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        rows = con.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
        con.close()
    except Exception as e:
        check("database", FAIL, f"{e} - delete it and re-run build_db.py")
        return None
    size_mb = db.stat().st_size / (1024 ** 2)
    check("database", OK,
          f"{len(tables)} tables, {rows:,} employees, {size_mb:.0f} MB")
    return db


def check_items():
    path = ROOT / ITEMS_PATH
    if not path.exists():
        check("items", FAIL, "data/items.jsonl missing")
        return []
    try:
        items = [json.loads(line) for line in open(path, encoding="utf-8")]
    except Exception as e:
        check("items", FAIL, f"not valid JSONL: {e}")
        return []

    ids = [i.get("id") for i in items]
    problems = []
    if len(set(ids)) != len(ids):
        problems.append("duplicate ids")
    if any(not i.get("gold_sql") for i in items):
        problems.append("missing gold_sql")
    if any(i.get("split") not in ("dev", "test") for i in items):
        problems.append("bad split value")

    n_test = sum(1 for i in items if i.get("split") == "test")
    n_dev = len(items) - n_test
    detail = f"{len(items)} items ({n_dev} dev, {n_test} test)"

    if problems:
        check("items", FAIL, detail + " - " + ", ".join(problems))
    elif n_test < 50:
        check("items", WARN, detail + " - the brief wants at least 50 test items")
    else:
        check("items", OK, detail)
    return items


def check_gold(items):
    if not GOLD_PATH.exists():
        check("gold cache", FAIL, "missing - run: python -m src.cache_gold")
        return
    cache = json.loads(GOLD_PATH.read_text())
    missing = [i["id"] for i in items if i["id"] not in cache]
    empty = [k for k, v in cache.items() if v.get("n_rows") == 0]

    if missing:
        check("gold cache", FAIL,
              f"{len(missing)} items not cached ({', '.join(missing[:4])}...) "
              "- items.jsonl changed since. Re-run: python -m src.cache_gold")
    elif empty:
        check("gold cache", WARN,
              f"{len(empty)} gold queries return no rows: {', '.join(empty)}")
    else:
        check("gold cache", OK, f"{len(cache)} answers cached")


# ---------------------------------------------------------------- models

def check_api_key():
    load_dotenv(ROOT / ".env")
    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not key:
        check("API key", FAIL,
              "ANTHROPIC_API_KEY is empty - Opus and Haiku cannot run")
    elif not key.startswith("sk-"):
        check("API key", WARN, "does not look like an Anthropic key")
    else:
        check("API key", OK, f"set ({len(key)} chars)")


def check_ollama():
    tag = MODELS["local"]["name"]
    base = OLLAMA_URL.rsplit("/v1/", 1)[0]
    try:
        r = requests.get(f"{base}/api/tags", timeout=4)
        r.raise_for_status()
    except Exception:
        check("Ollama", FAIL,
              "not reachable at localhost:11434 - start the Ollama app, "
              "or run: ollama serve")
        return

    names = [m.get("name", "") for m in r.json().get("models", [])]
    if tag in names:
        check("Ollama", OK, f"serving, {tag} is pulled")
    else:
        check("Ollama", FAIL,
              f"running, but {tag} is not pulled.\n"
              f"         have: {', '.join(names) or '(nothing)'}\n"
              f"         fix:  ollama pull {tag}")


# ---------------------------------------------------------------- settings

def check_settings():
    if TEMPERATURE != 0:
        check("settings", WARN, f"temperature is {TEMPERATURE}, not 0")
    else:
        check("settings", OK,
              f"temp {TEMPERATURE}, max_tokens {MAX_TOKENS}, "
              f"prompt {prompt_mod.fingerprint()}")


def check_previous_runs():
    raw = ROOT / "results" / "raw"
    files = sorted(raw.glob("*.jsonl")) if raw.exists() else []
    if not files:
        check("previous runs", OK, "none yet")
        return
    shas = set()
    for f in files:
        for line in open(f, encoding="utf-8"):
            try:
                shas.add(json.loads(line).get("prompt_sha"))
            except Exception:
                pass
            break
    now = prompt_mod.fingerprint()
    stale = shas - {now}
    if stale:
        check("previous runs", WARN,
              f"{len(files)} raw file(s); some used a different prompt "
              f"({', '.join(sorted(x or '?' for x in stale))} vs {now}). "
              "Those results are not comparable with a new run.")
    else:
        check("previous runs", OK, f"{len(files)} raw file(s), prompt matches")


# ---------------------------------------------------------------- main

def main():
    print(f"\nQuery-Trials preflight\n{'-' * 58}")
    check_disk()
    db = check_db()
    items = check_items()
    if items:
        check_gold(items)
    check_settings()
    check_api_key()
    check_ollama()
    check_previous_runs()

    fails = [r for r in _rows if r[0] == FAIL]
    warns = [r for r in _rows if r[0] == WARN]
    print("-" * 58)

    if fails:
        print(f"{len(fails)} problem(s) must be fixed before running:")
        for _, name, _d in fails:
            print(f"  - {name}")
        print("\nThe local model can still run if only the API key failed:")
        print("  python -m src.run --model local --split dev")
        sys.exit(1)

    print(f"Ready.{f'  ({len(warns)} warning(s))' if warns else ''}")
    print("  python -m src.run --model local --split dev     # 10 items first")
    print("  python -m src.run --model all --split test      # the real run")


if __name__ == "__main__":
    main()
