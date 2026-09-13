# results/ — handoff to Oumayma

Everything in this folder is produced by code. Nothing here is typed by hand.

## What you get from the run

`results/raw/<run_id>__<model>.jsonl` — one JSON object per item per model,
written by `src/run.py`. Three files per run.

```json
{
  "run_id": "20260913-224930",
  "item_id": "q001",
  "model_key": "local",
  "model_name": "qwen2.5-coder:3b-instruct-q4_K_M",
  "difficulty": "easy",
  "question": "How many employees are in the database?",
  "raw_output": "```sql\nSELECT COUNT(*) FROM employees;\n```",
  "parsed_sql": "SELECT COUNT(*) FROM employees",
  "latency_ms": 1840.2,
  "prompt_tokens": 210,
  "completion_tokens": 18,
  "tokens_per_sec": 9.8,
  "error": null,
  "prompt_sha": "49d316aa74d2",
  "temperature": 0,
  "max_tokens": 300,
  "ts_utc": "2026-09-13T21:49:30+00:00"
}
```

`parsed_sql` is already stripped of markdown fences by the shared parser —
score it, don't re-parse it. `error` is non-null when the call itself failed;
those items are wrong, but they belong in their own column, not lumped in with
wrong answers.

**Check `prompt_sha` is identical across all three files.** If it isn't, the
prompt changed mid-run and the comparison is invalid.

## What you produce

### `results/per_item.csv` — one row per item per model (150 rows)

| Column | Meaning |
|---|---|
| `run_id` | from the raw file |
| `item_id` | `q001` … `q060` — joins back to `data/items.jsonl` |
| `model_key` | `top` / `cheap` / `local` |
| `model_name` | exact model string, goes in the report |
| `difficulty` | `easy` / `medium` / `hard` |
| `status` | see the table below |
| `correct` | `true` / `false` |
| `latency_ms` | as recorded |
| `prompt_tokens`, `completion_tokens` | for the cost model |
| `parsed_sql` | so wrong answers can be read without opening the JSON |
| `note` | short reason when wrong — e.g. *hallucinated column `dept.salary`* |

### `results/summary.csv` — one row per model (3 rows)

`model_key, model_name, n_items, n_correct, accuracy, p50_ms, p95_ms, mean_ms,
median_tokens_per_sec, n_parse_error, n_sql_error, n_timeout, n_unsafe,
n_api_error, cost_per_1k_usd`

## Status values

A parse error, refusal, or timeout counts as **wrong**, and the brief wants
them shown in their own column — so keep the statuses separate rather than
collapsing everything into a boolean.

| `status` | When | `correct` |
|---|---|---|
| `correct` | result matches the gold answer | true |
| `wrong_result` | query ran, gave different rows | false |
| `sql_error` | query failed to execute | false |
| `timeout` | query exceeded the timeout | false |
| `unsafe` | not a read-only `SELECT` | false |
| `parse_error` | nothing usable came back | false |
| `api_error` | `error` field was non-null | false |

## How to compare answers

**Do not re-run the gold query.** `src/cache_gold.py` has already run all 60
once and stored a fingerprint of each answer in `data/gold_results.json`:

```json
{"q001": {"hash": "a3f2...", "n_rows": 1, "n_cols": 1,
          "ordered": false, "seconds": 0.08}}
```

Two gold queries take several seconds because they scan the 967k-row salaries
table. Running them 150 times would be slow, and worse, a gold query hitting
the timeout would fail the item through no fault of the model. So: run the
model's query, hash the result the same way, compare hashes.

```python
from src.sqlutil import parse_sql, is_safe, run_query, result_hash

gold = json.load(open("data/gold_results.json"))[item_id]
cols, rows = run_query(model_sql, db_path, timeout_s=5)
ok = result_hash(rows, gold["ordered"]) == gold["hash"]
```

**Import the helpers from `src/sqlutil.py` — do not write your own.** The cache
was built with those exact rules, so a scorer that normalised differently would
mark every item wrong. The rules are:

- column **names** ignored (a different alias is still correct), column **count**
  matters
- floats rounded to 6 decimal places
- `NULL` distinct from `0` and from the string `"NULL"`
- duplicate rows significant
- row order compared **only** when the gold query has its own `ORDER BY`

These are already unit-tested; extend `tests/test_score.py` rather than
re-deriving them.

## Latency

Report **p50 and p95**, never only the mean. `src/run.py` already has a
`percentile()` function using the same sort-and-index method — reuse it so the
runner's console output and the report agree.

## Cost

- **API:** sum the real `prompt_tokens` and `completion_tokens` across the 50
  items, multiply by list price, scale to 1,000 requests. Put prices in
  `src/prices.yaml` **with the date you looked them up**.
- **Local:** `(hardware cost per hour + electricity per hour) ÷ requests per
  hour`. Write down every assumption — machine price, amortisation period,
  $/kWh, utilisation.
- **At 100×:** API cost scales linearly; self-hosted is a **step function** —
  one machine absorbs the growth until it saturates, then you buy another. Say
  this explicitly, it's the part that shows you understood the question.
- **Break-even:** solve `api_per_1k × N/1000 = fixed_local + marginal × N/1000`.

## Hardware

```bash
python results/collect_hardware.py
```

Writes `results/hardware.md` by asking the machine. Run it on whichever laptop
did the real Qwen run, not on a different one.

## Known issues

- `q043` and `q045` have slow gold queries — handled by the cache, but worth a
  line in the postmortem.
- `q051` and `q060` were replaced before the run because the originals were
  broken. `data/labelling_note.md` explains both.
- The two-person label check has **not** been done yet.
