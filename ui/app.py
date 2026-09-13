"""Query-Trials UI.

Two things in one page:
  Compare  - type a question, run it on any of the three models, see the SQL
             each one wrote and the rows it returned, side by side.
  Results  - read results/summary.csv and results/per_item.csv and show the
             numbers that go in the report.

This sits BESIDE the graded pipeline. Nothing in src/ imports it, and the
project still runs from a clean clone without it.

Run with:  python -m ui.app      then open http://localhost:5000
"""

import csv
import os
import sys
from pathlib import Path

from flask import Flask, jsonify, render_template, request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import adapters, prompt as prompt_mod          # noqa: E402
from src.settings import MODELS, DB_PATH, RESULTS_DIR   # noqa: E402
from src.sqlutil import parse_sql, is_safe, run_query, get_schema  # noqa: E402

app = Flask(__name__)

MAX_PREVIEW_ROWS = 50


def db_file() -> Path:
    return ROOT / DB_PATH


@app.route("/")
def index():
    return render_template(
        "index.html",
        models=MODELS,
        db_ready=db_file().exists(),
        prompt_hash=prompt_mod.fingerprint(),
    )


@app.errorhandler(Exception)
def as_json(e):
    """Never hand the browser an HTML traceback.

    Flask's debug pages are HTML, and the page expects JSON - so a crash here
    surfaced in the browser as an unhelpful JSON parse error instead of the
    real problem. Now the real message comes through.
    """
    import traceback
    traceback.print_exc()
    return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.post("/api/ask")
def ask():
    """Run one question on the models the user ticked."""
    body = request.get_json(force=True)
    question = (body.get("question") or "").strip()
    chosen = body.get("models") or []

    if not question:
        return jsonify({"error": "Type a question first."}), 400
    if not db_file().exists():
        return jsonify({"error": f"No database at {DB_PATH} yet. "
                                 "Youssef needs to run build_db.py first."}), 400

    schema = get_schema(str(db_file()))
    full_prompt = prompt_mod.build(schema, question)

    out = []
    for key in chosen:
        if key not in MODELS:
            continue
        try:
            adapter = adapters.get(key)
        except Exception as e:
            out.append({"key": key, "label": MODELS[key]["label"],
                        "error": str(e)})
            continue

        # One model call. Exactly what run.py does for the real evaluation.
        res = adapter.generate(full_prompt)
        sql = parse_sql(res["text"])

        row = {
            "key": key,
            "label": MODELS[key]["label"],
            "model_name": MODELS[key]["name"],
            "sql": sql,
            "latency_ms": res["latency_ms"],
            "prompt_tokens": res["prompt_tokens"],
            "completion_tokens": res["completion_tokens"],
            "tokens_per_sec": res.get("tokens_per_sec"),
            "error": res["error"],
            "columns": [],
            "rows": [],
            "status": "",
        }

        if res["error"]:
            row["status"] = "call failed"
        elif not sql:
            row["status"] = "empty answer"
        elif not is_safe(sql):
            row["status"] = "rejected - not a read-only SELECT"
        else:
            try:
                cols, rows = run_query(sql, str(db_file()))
                row["columns"] = cols
                row["rows"] = [list(map(_show, r)) for r in rows[:MAX_PREVIEW_ROWS]]
                row["total_rows"] = len(rows)
                row["status"] = "ok"
            except Exception as e:
                row["status"] = f"SQL error: {e}"
        out.append(row)

    return jsonify({"results": out})


def _show(v):
    return "NULL" if v is None else str(v)


def _read_csv(name):
    path = ROOT / RESULTS_DIR / name
    if not path.exists():
        return None
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@app.get("/api/results")
def results():
    """Whatever the scoring run has produced so far."""
    summary = _read_csv("summary.csv")
    per_item = _read_csv("per_item.csv")

    wrong = []
    if per_item:
        for r in per_item:
            correct = str(r.get("correct", "")).strip().lower()
            if correct in ("false", "0", "no", "wrong"):
                wrong.append(r)

    return jsonify({
        "summary": summary,
        "has_per_item": per_item is not None,
        "n_items": len(per_item) if per_item else 0,
        "wrong": wrong[:30],
    })


if __name__ == "__main__":
    print(f"Prompt fingerprint: {prompt_mod.fingerprint()}")
    print(f"Database: {db_file()}  exists={db_file().exists()}")
    app.run(debug=True, port=int(os.environ.get("PORT", 5050)))
