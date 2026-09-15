# Notes

Running log of things that went wrong and what we learned. Written as they
happen, because on the last day nobody remembers the first day. This feeds
`postmortem.md`.

One line per problem: what happened, why, what we did.

---

## 2026-09-13 — Setup

**macOS AirPlay was answering on port 5000.** The Flask UI returned 404 on
every request and the page came up blank. `lsof -i :5000` showed `ControlCe` —
macOS AirPlay Receiver binds port 5000, which is Flask's default. Our app was
never receiving the requests; something else was replying to them. Moved the
default to 5050.

A second, separate collision followed: `Port 5050 is in use` turned out to be
our *own* earlier server still running in another window — not AirPlay.
`PORT=5055` worked around it while we killed the old process.
*Lesson: when a server "works" but answers wrongly, check that it's actually
your process answering. A 404 from the wrong server looks identical to a 404
from yours.*

**Homebrew tried to compile Ollama from source.** On an Intel Mac, Homebrew
now classes the platform as "Tier 3", so there's no prebuilt bottle — it
started building Go from scratch and failed partway. Installing the official
`.dmg` from ollama.com avoids compilation entirely.
*Lesson: on Intel Macs, prefer vendor installers over Homebrew.*

**The disk was full and nothing said so directly.** `df -h /` showed **173 MB
free** on a 113 GB drive. This was the hidden cause of three separate failures
that all looked unrelated:
- a copied `database.sqlite` reported `database disk image is malformed`
- the Homebrew build died mid-compile
- the Ollama download failed with `Failure writing output to destination`

Reclaimed ~5 GB by removing a duplicate Docker.app and its container data.
*Lesson: SQLite does not error when it cannot finish writing — it produces a
file that looks fine until you open it. Check disk space early.* This is why
`src/doctor.py` now checks free space first.

**Repeated `command not found: python`.** Every new terminal window needs
`source .venv/bin/activate`. Obvious in hindsight, but it cost real time
across a dozen windows.

---

## 2026-09-13 — Data

**Two of the 60 questions were broken**, found by running every gold query
before any model saw them:

- `q051` "Which departments have no current manager?" — returned zero rows,
  because all nine departments do have a current manager. The SQL was correct;
  the item was the problem. A model could return an empty result from a
  completely wrong query and still be marked correct.
- `q060` asked which departments have more employees than the maximum of all
  departments starting with `d00` — but every department code starts with
  `d00`, so it asked a set to exceed its own maximum. Never satisfiable.

Both replaced with questions of the same difficulty that return rows. Done
*before* any model ran, which is the important distinction — removing an item
after a model fails it is explicitly against the rules.
*Lesson: "the query executes" is not the same as "the item is a good test".
Check the row count too.*

**Seven gold queries were slow** (3–10s), because they scan the 967k-row
salaries table. This matters more than it first looks: if the *gold* query
exceeds the scorer's timeout, the item fails regardless of what the model did.
Two fixes: indexes in `build_db.py`, and `src/cache_gold.py`, which runs each
gold query once and stores a hash of the answer so scoring only ever runs the
model's query.

**`items.jsonl` was missing an `id` field.** Without stable ids there's no way
to join `per_item.csv` back to the questions for the wrong-answer analysis.
Added `id`, `difficulty` and `split`. The difficulty labels already existed
inside `generate_items.py` but were being dropped when the file was written.

**The dev split had no hard items** — 5 easy, 5 medium. That meant the first
three-join query with date arithmetic any model would see was during the real
run. Swapped two hard items in.

**The database was named `.db`, and `.gitignore` only covered `.sqlite`.**
At 83 MB it would have been committed and rejected by GitHub. Renamed to
`database.sqlite` and added `*.db` as a second guard.

---

## 2026-09-13 — Models

**No free API credit.** The Anthropic console showed "Buy credits from $5" —
no trial on this account. A Claude Pro subscription does not include API
access; they are separately billed products. Still unresolved at time of
writing. The local model needs no key, so the harness was built and tested
against Ollama alone.

**Planned the 7B, had to use the 3B.** The machine assigned to the local run
is an Intel i5-8210Y with 8 GB RAM and no usable GPU. Qwen2.5-Coder 7B at
Q4_K_M is 4.7 GB of weights running on CPU — minutes per question, and memory
pressure. Switched to `qwen2.5-coder:3b-instruct-q4_K_M` (~2 GB). The brief
allows 1B–14B so this is legitimate, but it is a **different model** and is
reported by its own name, not as a footnote on the 7B.
*Lesson: check the hardware before choosing the model, not after.*

**The UI hid a server error.** A crash in the Flask handler returned an HTML
traceback, and the page tried to `JSON.parse` it — surfacing in Safari as
`SyntaxError: The string did not match the expected pattern`, which says
nothing useful. Added an error handler that returns JSON, and made the page
show the raw response when parsing fails.
*Lesson: an error path that hides the error is worse than no error handling.*

---

## 2026-09-14 — Clean-clone test (early run, on a slow sandbox machine)

**`requirements.txt` failed on any Python older than 3.12.** It was a frozen
`pip freeze` from one laptop; `numpy==2.5.3` simply does not exist for the
clone machine's Python 3.10, so `pip install` died before anything ran.
Replaced exact pins with loose requirements.
*Lesson: a freeze file describes one machine, not the project.*

**`cache_gold.py` could hang forever, and its "timeout" was a lie.** The
120-second timeout was passed to `sqlite3.connect()` — which is a *lock*
timeout and does nothing for a slow query. On the slow test machine a heavy
gold query ran indefinitely with zero output. Fixed with a progress-handler
deadline that genuinely interrupts the query, an env override
(`GOLD_TIMEOUT_S=300` for slow machines), per-item checkpointing so an
interrupted caching run resumes instead of restarting, and partial results
are now written even when some queries fail.
*Lesson: verify what a timeout parameter actually times.*

**A background process "kept running" only in our heads.** Checks with
`pgrep -f cache_gold` kept reporting the process alive — but `pgrep -f` was
matching the checking command's own command line. The process had died long
before. Verified with `ps aux` instead.
*Lesson: `pgrep -f X` from a shell whose own command line contains X matches
itself.*

**The committed dev raw file turned out to be a real run** — Qwen 3B on the
Intel Mac: 7/10 correct on dev items, but median latency **18.6 s** and one
item hitting the 60 s adapter timeout. Real numbers, and they say the Intel
Mac is workable for a one-off 50-item run (~20 min) but marginal; if the
Windows machine is available for the graded run, use it.

**End-to-end proof:** from a fresh clone with no gitignored files, the
sequence install → build_db → cache_gold → pytest (31 passing) → doctor →
score → cost ran to completion. Doctor correctly flagged the missing API key,
missing Ollama, and the 4 gold items the slow sandbox could not cache.

## 2026-09-14 — The timeout was measuring our laptop, not the model

Hard items started failing with `ReadTimeout ... (read timeout=60)`. The 3B on
a CPU-only machine generates longer SQL for harder questions and genuinely
needs more than 60 seconds; the earlier dev run had one item at 60.1s, right
on the line.

A timeout counts as wrong, so a 60s cap was marking the model wrong for *our
hardware* rather than for its answer — the opposite of what we are trying to
measure. Raised `TIMEOUT_S` to 180s. It applies identically to all three
models, so it remains part of the fairness contract; the two API models never
approach it.

*Lesson: a timeout is a measurement decision, not a technical detail. Set it
where it catches genuine failures and not slow-but-working ones — and fix it
before the graded run, because changing it afterwards invalidates the
comparison.*

## 2026-09-15 — The API SDK has no temperature parameter

The first full three-model run failed **all 120 API calls** with
`TypeError: Messages.create() got an unexpected keyword argument
'temperature'`. Not a typo on our side: the installed Anthropic SDK (1.5.0)
removed `temperature` from `messages.create()` entirely.

This is awkward, because temperature 0 is part of our fairness contract. The
local model is pinned to greedy decoding; the API models now use whatever
default the provider applies, and we cannot override it.

We did **not** quietly delete the argument. The adapter now probes the SDK
once at import, passes `temperature` only if it is supported, and records
`temperature_set: true/false` on every result row. The report states the
asymmetry rather than claiming a setting we never applied.

*Lesson: when the environment refuses a setting your methodology depends on,
record the refusal. A silent fallback would have produced a report claiming
temperature 0 for all three models, which would have been false.*

Related: this surfaced only because we had loosened `requirements.txt` from
pinned versions to open ones (itself a fix for the clean-clone test). Loose
requirements make the project portable and make the SDK a moving target. Worth
pinning `anthropic` specifically once the graded run is done, so the result is
reproducible.

## Still open

- API key for Opus and Haiku
- Two-person label check: Noura `q001`–`q030`, Oumayma `q031`–`q060`
- No full run has been done yet — only dev-split testing
