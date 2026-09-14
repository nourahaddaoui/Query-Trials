# Code walkthrough

For explaining the project out loud. Covers what every file does, why it does
it that way, and how one question travels from the database to a saved result.

---

# Part 1 — Youssef's side: `data/`

Everything the models are tested **on**. No code here ever calls a model.

## `data/raw/` — the source CSVs

Six files from the Kaggle *Employees* dataset: `departments`, `dept_emp`,
`dept_manager`, `employees`, `salaries`, `titles`. About 92 MB, **gitignored** —
GitHub rejects files over 100 MB and gets unhappy well before that.

The repo carries the *recipe*, not the output. Anyone cloning downloads the
CSVs themselves and rebuilds.

## `data/build_db.py` — CSVs into one database

```python
df = pd.read_csv(RAW_DIR / csv_name, index_col=0)
df.to_sql(table, con, if_exists="replace", index=False)
```

`index_col=0` matters: the Kaggle CSVs start with an unnamed row-number column.
Without it you'd get a junk column in every table.

Then two things worth pointing out:

**Indexes.** Several gold queries scan the 967k-row `salaries` table and took
3–10 seconds. Indexes don't change any answer — they make the same answer
arrive faster. That matters because the scorer has a timeout.

**Row-count assertions.** After loading, it checks every table against the
expected count:

```python
EXPECTED_ROWS = {"employees": 300024, "salaries": 967330, ...}
```

If a CSV were truncated or the wrong file, the build **fails loudly** instead
of quietly producing a database that all 60 questions are then wrong about.

**Output:** `data/database.sqlite` — also gitignored (83 MB).

## `data/generate_items.py` — where the questions came from

The 60 questions and their gold SQL, written as Python so they can be validated
before being written out. It asserts the difficulty counts and that every
question is unique, and runs `EXPLAIN` on each query against the real database
to catch typos and missing columns.

Kept in the repo as **provenance** — it answers "where did the questions come
from?" without anyone having to remember.

## `data/items.jsonl` — the test set

One JSON object per line, 60 lines:

```json
{"id": "q001",
 "question": "How many employees are in the database?",
 "gold_sql": "SELECT COUNT(*) AS employee_count FROM employees;",
 "difficulty": "easy",
 "split": "dev"}
```

| Field | Why it exists |
|---|---|
| `id` | stable key joining results back to questions in `per_item.csv` |
| `question` | what the model is asked |
| `gold_sql` | the correct answer — the thing everything is compared against |
| `difficulty` | easy / medium / hard, so the report can break accuracy down |
| `split` | `dev` (10, for testing the harness) or `test` (50, graded) |

**Split:** 10 dev / 50 test. Test set is 10 easy, 22 medium, 18 hard.

Dev exists so the pipeline can be exercised without touching the 50 items that
produce the reported numbers. Two hard items were moved into dev deliberately —
otherwise the first three-join query any model ever saw would be during the
real run.

## `data/schema.sql` — what goes in the prompt

The `CREATE TABLE` statements, extracted from the database. This exact text is
injected into every prompt so all three models see the identical schema.

## `data/labelling_note.md` — provenance and honesty

Where the data came from, the difficulty rubric, how labels were checked, and
**the problems found**. Two questions were broken and were replaced *before any
model ran*:

- **`q051`** asked which departments have no current manager. All nine do, so
  it returned zero rows. The SQL was correct; the item was weak — a model could
  return an empty result from a completely wrong query and still be marked
  correct.
- **`q060`** asked which departments have more employees than the maximum of
  all departments starting with `d00`. Every department code starts with `d00`,
  so it asked a set to exceed its own maximum. Never satisfiable.

**The distinction that matters:** replacing a broken item before any model runs
is not the same as removing an item a model failed. The second is explicitly
forbidden by the brief.

## The dataset quirk worth knowing

This data stores "still current" as `to_date = '9999-01-01'`, not `NULL`.
Several questions depend on it. A model that assumes `NULL` gets them wrong —
which is legitimate difficulty, not a flaw in the question.

---

# Part 2 — Noura's side: `src/` and `ui/`

## `src/settings.py` — the fairness contract, in one file

```python
TEMPERATURE = 0
MAX_TOKENS  = 300
MODELS = {
  "top":   {"label": "Claude Opus 5",    "name": "claude-opus-5"},
  "cheap": {"label": "Claude Haiku 4.5", "name": "claude-haiku-4-5-20251001"},
  "local": {"label": "Qwen2.5-Coder 3B", "name": "qwen2.5-coder:3b-instruct-q4_K_M"},
}
```

Everything that must stay identical across models lives here. One file to point
at when asked "how do you know the comparison was fair?"

**Temperature 0** means take the highest-probability token every time instead of
sampling — the model's single best answer, repeatable rather than creative.

**Why the 3B and not the 7B:** the machine doing the local run is an Intel
i5-8210Y, 8 GB RAM, no usable GPU. A 4.7 GB model on CPU there takes minutes per
question — we'd have been measuring the laptop, not the model. The brief allows
1B–14B, so the 3B is valid, but it's a **different model** and is reported by
its own name.

## `src/prompt.py` — the one prompt

```python
PROMPT = """You are given a SQLite database with this schema:

{schema}

Write one SQL query that answers the question.
Output only the SQL. No explanation, no markdown fences.

Question: {question}
SQL:"""
```

Plus `fingerprint()` — a SHA-256 hash of the prompt text, shortened to 12
characters. It's printed at the start of every run and **saved on every result
row**. If two runs have different fingerprints, the prompt changed and they
aren't comparable. This makes prompt drift impossible to hide, including from
ourselves.

## `src/adapters/` — three models, one shape

Every adapter exposes the same function:

```python
def generate(prompt: str) -> dict:
    # {text, prompt_tokens, completion_tokens, latency_ms, error}
```

Because they look identical from outside, `run.py` doesn't know or care which
model it's talking to — **the same code path runs for all three**. That is the
structural reason the comparison is fair; there's no per-model branch where a
difference could sneak in.

| File | What it is |
|---|---|
| `_anthropic.py` | shared code for both Claude models |
| `top.py` | passes `claude-opus-5` to it |
| `cheap.py` | passes `claude-haiku-4-5-20251001` to it |
| `local.py` | posts to Ollama on `localhost:11434` |
| `__init__.py` | `get("top" / "cheap" / "local")` returns the right one |

**Timing:**

```python
t0 = time.perf_counter()
resp = client.messages.create(...)
latency_ms = (time.perf_counter() - t0) * 1000
```

`perf_counter` is a monotonic clock — it can't jump backwards if the system
clock adjusts mid-run. **Streaming is off on purpose**: we want time to the
*complete* answer, not time to the first word.

**Errors are caught, not raised.** A failed call returns a record with `error`
set and latency still measured. A failure is a result: the brief says a timeout
or refusal counts as wrong.

`local.py` also computes `tokens_per_sec`, which the report needs for the
self-hosted model, and has `warm_up()` — three throwaway calls so the first
timed item doesn't include loading the model from disk.

## `src/sqlutil.py` — the shared rules

Used by the UI, the gold cache **and** the scorer, so none of them can drift
apart.

**`parse_sql()`** — strips markdown fences and a leading `SQL:`. Models
sometimes wrap output in ```` ```sql ```` despite being told not to. The same
parser runs on all three, so nobody gets an advantage.

**`is_safe()`** — only a single read-only `SELECT` or `WITH` is allowed.
Anything else is rejected and counts as wrong.

**`normalize()` and `result_hash()`** — how two result sets are compared:

| Rule | Why |
|---|---|
| column **names** ignored | a different alias is still a correct answer |
| column **count** must match | returning extra columns is a different answer |
| floats rounded to 6 dp | `89005.789999` and `89005.79` are the same answer |
| `NULL` ≠ `0` ≠ `"NULL"` | they mean different things |
| duplicate rows significant | a missing `DISTINCT` is a real error |
| order compared **only** if gold has `ORDER BY` | otherwise row order is arbitrary |

`result_hash` fingerprints a result set so a 300,000-row answer can be stored
as 16 characters.

## `src/cache_gold.py` — run the gold queries once

Two gold queries take several seconds because they scan the salaries table.
Running them for all 150 comparisons would be slow, and worse — if a *gold*
query hit the scorer's timeout, the item would fail through no fault of the
model.

So each gold query runs **once**, with a 120-second timeout, and a hash of its
answer goes into `data/gold_results.json`. Scoring then runs only the model's
query and compares hashes. One query per item instead of two, and gold timing
stops mattering.

## `src/run.py` — the measurement

For each model, for each item, in order:

1. build the prompt from the schema + the question
2. call the adapter — **one call, no retries**
3. parse the SQL
4. write one JSON line to `results/raw/<run_id>__<model>.jsonl`
5. `flush()` immediately, so a crash at item 47 doesn't lose items 1–46

**Strictly sequential.** Running models in parallel would measure our network
and thread pool instead of the models.

**Items sorted by id** before running, so all three genuinely get the same
order rather than relying on the file's order.

**`--resume <run_id>`** reads which ids are already in the raw file and skips
them. On a slow local model, losing 40 finished items to a crash at item 41 is
avoidable.

At the end it prints p50 / p95 / mean per model. **p50** is the middle value,
**p95** is the value 95% of answers beat. We report both and never only the
mean — one 30-second answer barely moves an average of fifty, but it's exactly
what a user would notice.

## `src/doctor.py` — check before a long run

Verifies disk space, that the database exists *and opens*, that items parse
with no duplicate ids, that the gold cache covers every item, the API key, that
Ollama is serving **and has the exact model tag pulled**, and whether earlier
raw files used a different prompt.

Every check exists because that thing actually went wrong at least once.

## `ui/` — the optional interface

Flask, two tabs: ask one question across models and see the SQL and rows side
by side; or browse the summary and wrong answers.

**It lives outside `src/` on purpose.** Nothing in the graded pipeline imports
it, so the project runs from a clean clone whether or not Flask is installed.
It also shares `sqlutil.py` with the scorer — if the UI parsed SQL differently
than the scorer, we'd demo one answer and report another.

---

# Part 3 — How one question actually flows

Following `q027` from database to saved result.

### Before any model runs — once

```
data/raw/*.csv
      │  python data/build_db.py
      ▼
data/database.sqlite          6 tables, indexed, row counts verified
      │
      ├─ get_schema()  ────────►  the CREATE TABLE text
      │
      │  python -m src.cache_gold
      ▼
data/gold_results.json        {"q027": {"hash": "8f3b…", "ordered": true, …}}
```

Each gold query runs once; its answer is hashed and stored.

### The run — per item, per model

```
data/items.jsonl ──► {"id": "q027", "question": "...", "gold_sql": "..."}
                            │
                            ▼
                   prompt.build(schema, question)
                            │  one string, ~700 tokens
                            ▼
                   adapters.get("local").generate(prompt)
                            │  stopwatch starts
                            │  ONE call, temperature 0, max 300 tokens
                            │  stopwatch stops on the complete answer
                            ▼
                   {text, prompt_tokens, completion_tokens, latency_ms, error}
                            │
                            ▼
                   parse_sql(text)      strips ```sql fences
                            │
                            ▼
      results/raw/20260914-110716__local.jsonl      one line appended, flushed
```

Repeated 50 times, then the next model. Never in parallel.

### Scoring — Oumayma's half

```
raw/*.jsonl  ──►  parsed_sql
                      │
                      ├─ is_safe()?  no  ──► status "unsafe", wrong
                      │
                      ▼
                 run_query(sql, db, timeout=5s)
                      │
                      ├─ raises  ──► status "sql_error", wrong
                      │
                      ▼
                 result_hash(rows, gold["ordered"])
                      │
                      ▼
                 == gold["hash"] ?  ──► "correct"  /  "wrong_result"
                      │
                      ▼
        results/per_item.csv  ──►  results/summary.csv  ──►  report.pdf
```

**The model's query is never compared to the gold query as text.** Two people
can write the same query differently and both be right. We compare the *rows
that come back*. That's what "run both queries, compare results" means.

---

# Likely questions

**"How do you know the comparison was fair?"**
One prompt file with a hash printed on every result row. One settings file for
temperature and token limits. One parser and one comparison function, shared by
the UI, the cache and the scorer. One code path for all three models — the
adapters are interchangeable. And the items are sorted by id so the order is
identical.

**"What counts as wrong?"**
A wrong result, a query that errors, a timeout, anything that isn't a read-only
`SELECT`, an unparseable answer, and a failed API call. Each has its own status
so the report can show them separately, and all of them count as wrong.

**"Why p50 and p95 instead of the average?"**
If 49 answers arrive in 1 second and one takes 30, the average says 1.6 seconds
— which sounds fine, but someone waited half a minute. p95 catches the bad
experience an average hides.

**"Why is the database not in the repo?"**
83 MB, plus 92 MB of CSVs. GitHub rejects files that large. `build_db.py` is
the recipe and it verifies its own output, so anyone can rebuild it identically.

**"Why the 3B model rather than the 7B you planned?"**
The machine has 8 GB of RAM, no usable GPU, and a fanless dual-core CPU. The 7B
would have measured the laptop, not the model. The brief allows 1B–14B. It's
reported as the 3B, not as a footnote — the reasoning is in `settings.py`,
`results/hardware.md` and the postmortem.

**"Did you change anything after seeing results?"**
No. Two questions were replaced, but before any model ran, and both are
documented with the reason. The prompt and items are frozen from the run
onward; if either changed, all three models would be re-run.
