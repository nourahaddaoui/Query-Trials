# What's in here

Drop these into your repo, keeping the same folder structure.

    src/prompt.py              the one frozen prompt + its fingerprint
    src/settings.py            shared settings - model names, temperature, paths
    src/sqlutil.py             SQL parsing, safety check, running queries
    src/adapters/__init__.py   picks an adapter by name
    src/adapters/_anthropic.py shared code for both Claude models
    src/adapters/top.py        Claude Opus 5
    src/adapters/cheap.py      Claude Haiku 4.5
    src/adapters/local.py      Qwen through Ollama
    ui/app.py                  the Flask server
    ui/templates/index.html    the page

## Install

    pip install flask
    pip freeze > requirements.txt

## Run

    python -m ui.app

Then open http://localhost:5000

## Notes

- `src/settings.py` is new - it wasn't in the original skeleton. Everything
  that must stay identical across the three models lives there.
- The database path is `data/database.sqlite`. Change it in settings.py once
  Youssef names the real one.
- The UI works with no API keys. Untick the two Claude models and use the
  local one only until the key question is sorted.
- The UI is deliberately outside `src/`. Nothing in the graded pipeline
  imports it, so the project still runs from a clean clone without Flask.
