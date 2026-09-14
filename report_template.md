# Report skeleton — 2 pages

For Oumayma. The structure follows the brief's six points exactly. Everything
in ⟨angle brackets⟩ gets filled from real results — nothing is invented.
Convert to PDF when done (export from any editor); the repo ships `report.pdf`.

---

## Query-Trials: three models write SQL

⟨Youssef · Noura · Oumayma⟩ — CS496 Project 0 — run date ⟨YYYY-MM-DD⟩

### 1. The task

A model receives a database schema and a plain-English question, and must
write one SQLite query that answers it. We score by **execution match**: run
the model's query and the reference query, compare the returned rows. No
human judgement, no LLM judge.

Example item (`q⟨NNN⟩`):

> **Q:** ⟨question text⟩
> **Gold:** `⟨gold SQL⟩`
> **Model wrote:** `⟨model SQL⟩` → ⟨same rows → correct⟩

### 2. The data

The *Employees* sample database from Kaggle: 6 linked tables, 300,024
employees, 967,330 salary records. "Still current" is encoded as
`to_date = '9999-01-01'`, which several questions deliberately depend on.

60 questions (10 dev / **50 test**; test = 10 easy, 22 medium, 18 hard),
written and verified by hand. Labels double-checked by a second person
⟨confirm done⟩. Two items were replaced **before any model ran** because the
originals returned empty results by construction (`data/labelling_note.md`).

### 3. Setup

| Slot | Model | Exact name |
|---|---|---|
| Top API | Claude Opus 5 | `claude-opus-5` |
| Cheap API | Claude Haiku 4.5 | `claude-haiku-4-5-20251001` |
| Open-weights, self-hosted | Qwen2.5-Coder 3B (Q4_K_M) | `qwen2.5-coder:3b-instruct-q4_K_M` |

Identical for all three: one prompt (fingerprint `⟨sha⟩`, schema included),
temperature 0, max 300 output tokens, same 50 items in the same order, same
parser, sequential calls, no retries. Local model on ⟨machine from
hardware.md⟩ via Ollama; 3 warm-up calls excluded.

We planned the 7B but the assigned machine (8 GB RAM, no GPU) could not run
it usefully; the 3B is reported as its own model, not as a substitute 7B.

### 4. Results

⟨paste summary.csv as a table⟩

| Model | Correct | Acc | p50 | p95 | Errors | $/1k |
|---|---|---|---|---|---|---|
| Opus 5 | ⟨n⟩/50 | | | | | |
| Haiku 4.5 | ⟨n⟩/50 | | | | | |
| Qwen 3B | ⟨n⟩/50 | | | | | |

Errors (parse/SQL/timeout/refusal) count as wrong and are broken out per
class in `summary.csv`.

**Three wrong answers per model** — say *why*, not just "wrong":

- Opus, `q⟨N⟩`: ⟨e.g. missed the 9999-01-01 sentinel, counted all history⟩
- Opus, `q⟨N⟩`: ⟨…⟩
- Opus, `q⟨N⟩`: ⟨…⟩
- Haiku, `q⟨N⟩`: ⟨…⟩ ×3
- Qwen, `q⟨N⟩`: ⟨e.g. hallucinated column `employees.dept_no`⟩ ×3

### 5. Our choice, and when it changes

⟨Written together after seeing the table. The shape of the argument:⟩

We would use **⟨model⟩** because ⟨accuracy gap vs cost gap, in numbers:
"Haiku is ⟨X⟩ pp behind Opus at ⟨Y⟩× lower cost"⟩.

We would switch if: accuracy on hard items mattered more than cost (→ Opus);
if volume passed the break-even (→ self-hosted); if p95 latency of the local
model were acceptable for the use case (→ Qwen for cost).

### 6. Cost at 100× and break-even

At 100× traffic (100,000 requests): API cost scales **linearly** —
Opus $⟨n⟩, Haiku $⟨n⟩. Self-hosting is a **step function**: one machine
absorbs growth until ~⟨n⟩ requests/day, then you buy another.

Break-even vs Haiku: ~⟨n⟩ requests (from `python -m src.cost`). Below that,
the API is cheaper overall once setup time is counted; above it, self-hosting
wins if the latency is acceptable.

---
*Repo: github.com/nourahaddaoui/Query-Trials — `python -m src.doctor && python -m src.run --model all --split test && python -m src.score && python -m src.cost` reproduces everything.*
