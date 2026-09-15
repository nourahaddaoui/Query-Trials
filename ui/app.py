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
import shutil
import sys
from pathlib import Path

from flask import Flask, jsonify, render_template, request

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests                                          # noqa: E402

from src import adapters, prompt as prompt_mod           # noqa: E402
from src.settings import (MODELS, DB_PATH, RESULTS_DIR,  # noqa: E402
                          OLLAMA_URL)
from src.sqlutil import parse_sql, is_safe, run_query, get_schema  # noqa: E402

app = Flask(__name__)

# Flask sorts JSON keys alphabetically by default, which silently destroyed the
# column order of the CSVs - the results table came out with "accuracy" first
# and "model_name" in the middle. Keep insertion order.
app.json.sort_keys = False

MAX_PREVIEW_ROWS = 50


def db_file() -> Path:
    return ROOT / DB_PATH


def availability():
    """Which models can actually run right now, and why not if they can't.

    Checked live on every call, so the page reflects reality without a restart:
    paste a key into .env and the Claude models light up; stop Ollama and Qwen
    goes dark. Distinguishes "not installed" from "installed but not running"
    from "running but the model was never pulled", because the fix differs.
    """
    from dotenv import load_dotenv
    # override=True matters: an empty ANTHROPIC_API_KEY is already in the
    # environment from the first load, and without this a newly pasted key
    # would be ignored until the server restarted.
    load_dotenv(ROOT / ".env", override=True)
    key_val = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()

    # A real key is ~100 chars. Reject the obvious placeholders too - pasting
    # the example "sk-ant-..." straight out of the README passed the prefix
    # check and made both models look available when they were not.
    if not key_val:
        api = (False, "no API key — add ANTHROPIC_API_KEY to .env")
    elif not key_val.startswith("sk-ant-"):
        api = (False, "the key in .env does not look like an Anthropic key")
    elif "..." in key_val or len(key_val) < 40:
        api = (False, "that is the placeholder, not a real key — paste the "
                      "one from console.anthropic.com")
    else:
        api = (True, "")

    local = _ollama_status()

    out = {}
    for key in MODELS:
        ok, reason = local if key == "local" else api
        out[key] = {"ok": ok, "reason": reason}
    return out


def _ollama_status():
    """(ok, reason) for the self-hosted model."""
    base = OLLAMA_URL.rsplit("/v1/", 1)[0]
    try:
        r = requests.get(f"{base}/api/tags", timeout=1.5)
        r.raise_for_status()
    except requests.exceptions.ConnectionError:
        if shutil.which("ollama"):
            return False, "Ollama is installed but not running — run: ollama serve"
        return False, "Ollama is not installed — see ollama.com/download"
    except Exception as e:
        return False, f"Ollama not reachable ({type(e).__name__})"

    tag = MODELS["local"]["name"]
    names = [m.get("name", "") for m in r.json().get("models", [])]
    if tag not in names:
        return False, f"Ollama is running but {tag} is not pulled — run: ollama pull {tag}"
    return True, ""


@app.route("/")
def index():
    return render_template(
        "index.html",
        models=MODELS,
        avail=availability(),
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


@app.get("/api/availability")
def availability_endpoint():
    """Polled by the page so the model chips stay honest without a refresh."""
    return jsonify(availability())


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

    # Drop models that cannot run, and say which and why, rather than making
    # sixty doomed calls and showing a wall of identical errors.
    avail = availability()
    skipped = [{"key": k, "label": MODELS[k]["label"],
                "reason": avail[k]["reason"]}
               for k in chosen if k in MODELS and not avail[k]["ok"]]
    runnable = [k for k in chosen if k in MODELS and avail[k]["ok"]]

    if not runnable:
        return jsonify({
            "error": "None of the selected models can run right now.",
            "skipped": skipped, "results": [],
        })

    schema = get_schema(str(db_file()))
    full_prompt = prompt_mod.build(schema, question)

    out = []
    for key in runnable:
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

    return jsonify({"results": out, "skipped": skipped})


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

    # Send column order explicitly rather than relying on the client to infer
    # it from object keys - that is what broke before.
    return jsonify({
        "summary": summary,
        "summary_cols": list(summary[0].keys()) if summary else [],
        "has_per_item": per_item is not None,
        "n_items": len(per_item) if per_item else 0,
        "wrong": wrong[:30],
        "wrong_cols": list(wrong[0].keys()) if wrong else [],
    })


if __name__ == "__main__":
    print(f"Prompt fingerprint: {prompt_mod.fingerprint()}")
    print(f"Database: {db_file()}  exists={db_file().exists()}")
    app.run(debug=True, port=int(os.environ.get("PORT", 5050)))
