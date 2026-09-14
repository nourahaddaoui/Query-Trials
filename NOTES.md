# Notes

Running log of things that went wrong and what we learned. Written as they
happen, because on the last day nobody remembers the first day. This feeds
`postmortem.md`.

One line per problem: what happened, why, what we did.

---

## 2026-09-13 — Setup

**Port 5050 was already taken on macOS.** The Flask UI returned 404 on every
request and the page came up blank. `lsof -i :5050` showed `ControlCe` —
macOS AirPlay Receiver listens on 5000 and 5050 by default. Our app was never
receiving the requests at all. Moved the default to 5055.
*Lesson: when a server "works" but answers wrongly, check that it's actually
the thing answering.*

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

## Still open

- API key for Opus and Haiku
- Two-person label check: Noura `q001`–`q030`, Oumayma `q031`–`q060`
- No full run has been done yet — only dev-split testing
