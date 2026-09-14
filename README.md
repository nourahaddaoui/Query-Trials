# Query-Trials

**CS496 AI Engineering — Project 0 (Bake-Off)**
Mediterranean Institute of Technology, Fall 2026

Three models write SQL from the same 50 questions. We measure how often each is
right, how fast it answers, and what it costs — then say which one we would use.

**Task:** natural-language question → SQL → run it → compare the result table
against the correct answer.
**Scoring:** execution match, automatic. No human judgement, no LLM judge.

| Slot | Model | Exact name |
|---|---|---|
| Top API | Claude Opus 5 | `claude-opus-5` |
| Cheap API | Claude Haiku 4.5 | `claude-haiku-4-5-20251001` |
| Open-weights, run by us | Qwen2.5-Coder 3B Instruct (Q4_K_M) | `qwen2.5-coder:3b-instruct-q4_K_M` |

All three get the identical prompt at temperature 0, the same 50 items in the
same order, and the same parser.

---

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```

Then three things the repo cannot carry for you:

**1. The data.** The CSVs (~92 MB) and the built database are gitignored.
Download the *Employees* dataset from Kaggle, unzip the six CSVs into
`data/raw/`, then:

```bash
python data/build_db.py        # builds data/database.sqlite, checks row counts
python -m src.cache_gold       # runs each gold query once, caches the answers
```

**2. The API key.** Copy `.env.example` to `.env` and paste an Anthropic key in.
Needed only for the two Claude models — Qwen runs without one.

```bash
cp .env.example .env
```

**3. The local model.**

```bash
ollama pull qwen2.5-coder:3b-instruct-q4_K_M
ollama serve
```

## Run

Check everything first — this takes two seconds and catches the failures that
otherwise surface forty minutes into a run:

```bash
python -m src.doctor
```

Then:

```bash
python -m src.run --model all --split test
```

If a run is interrupted, continue it instead of starting over:

```bash
python -m src.run --model all --split test --resume 20260914-110716
```

Then score and price it:

```bash
python -m src.score
python -m src.cost
```

Smaller runs while developing:

```bash
python -m src.run --model local --split dev            # 10 practice items
python -m src.run --model cheap --split test --limit 5
```

## The interface (optional)

A local page for demoing a single question against all three models, and for
browsing the results:

```bash
python -m ui.app          # http://127.0.0.1:5050
```

It sits outside `src/` on purpose — nothing in the graded pipeline imports it,
so the project runs from a clean clone whether or not Flask is installed.

---

## Results

Run date: _pending_ · Test set: 50 items · Temperature 0 · max_tokens 300

| Model | Correct | Accuracy | p50 | p95 | Errors | Cost / 1k |
|---|---:|---:|---:|---:|---:|---:|
| Claude Opus 5 | — / 50 | — | — | — | — | — |
| Claude Haiku 4.5 | — / 50 | — | — | — | — | — |
| Qwen2.5-Coder 3B | — / 50 | — | — | — | — | — |

Filled in from `results/summary.csv` after the run. Hardware for the local
model is in `results/hardware.md`.

---

## Layout

```
data/       the database and the 60 questions        Youssef
src/        prompt, adapters, runner, scorer, cost   Noura + Oumayma
results/    raw answers and the measured numbers     Oumayma
tests/      proof the scorer is trustworthy          Oumayma
ui/         optional local interface                 Noura
```

`data/labelling_note.md` covers where the data came from, how the labels were
checked, and the two items that were replaced before the run.

## Rules we held ourselves to

- One prompt, one parser, one set of settings for all three models. Changing
  anything between models breaks the comparison.
- Models run **sequentially**. Running them in parallel would measure the
  network, not the models.
- **No retries.** A timeout or a refusal is a result and counts as wrong.
- After the run starts, `src/prompt.py` and `data/items.jsonl` are frozen. If
  either changes, all three models are re-run from scratch.
- No API keys in the repo.

---

## Contributions

**Youssef — data.** Chose the dataset, built the database, wrote the 60
questions and their gold SQL, wrote the labelling note, worked out the cost
model, analysed the wrong answers.

**Noura — models and harness.** Wrote the prompt, the three model adapters, the
runner and its timing, set up and ran Ollama locally, recorded the hardware,
built the interface, wrote this README.

**Oumayma — scoring and report.** Wrote the scorer and its tests, built the
per-item and summary tables, calculated the percentiles, wrote the two-page
report and the postmortem, ran the clean-clone test.
