# Postmortem — Project 0

> **DRAFT.** Written from `NOTES.md` before the final run. After the real run,
> add anything that went wrong on run day and delete this banner.

One page: what went wrong, what it cost us, what we do differently now.

## What went wrong

**A full disk corrupted a database silently.** The laptop assigned to the
local model had 173 MB free on a 113 GB drive. Three failures followed that
looked completely unrelated: a copied SQLite file reported "database disk
image is malformed", a Homebrew build died mid-compile, and the Ollama
download failed with a write error. SQLite is the nasty one — it does not
error when a write cannot finish; it produces a file that looks fine until
you open it. We lost most of an evening treating three symptoms before
finding the one cause.
*Now:* `src/doctor.py` checks free disk space before anything else runs.

**We planned a model our hardware could not run.** The 7B model we chose is
4.7 GB of weights; the machine assigned to run it is a fanless dual-core with
8 GB of RAM and no GPU. On CPU that means minutes per question — we would
have been measuring the laptop, not the model. We switched to the 3B and
report it as its own model, with the reasoning in `results/hardware.md`.
*Now:* check the hardware before choosing the model, not after.

**Two of our 60 questions were broken, and executing them was not enough to
notice.** Every gold query parsed and ran — but `q051` returned zero rows
(every department has a current manager, so "which have none" is empty) and
`q060` was logically unsatisfiable (it asked a set to exceed its own maximum).
An empty gold result is dangerous: a model could return an empty result from a
completely wrong query and be marked correct. Both were replaced *before any
model ran* — which is not the same as dropping items a model failed, and the
labelling note documents both.
*Now:* validation checks row counts, not just execution.

**Slow gold queries could have failed items the models got right.** Several
reference queries scan the 967k-row salaries table and took 3–10 seconds;
the scorer's timeout is 5. Indexes fixed most. For the rest, `cache_gold.py`
runs every gold query once with a generous timeout and stores a hash of the
answer, so scoring never re-runs them.
*Now:* the speed of the answer key cannot affect any model's score.

**A hidden server made a 404 look like our bug.** The Flask UI returned 404
on every request. The cause was macOS AirPlay Receiver, which binds port 5000
— something else was answering our requests. Separately, our own forgotten
server later occupied the replacement port.
*Lesson:* when a server misbehaves, first confirm it is your process answering.

**The UI swallowed the real error.** A crash in the server returned an HTML
traceback; the page tried to parse it as JSON and Safari reported only
"SyntaxError: The string did not match the expected pattern". The fix returns
JSON on every error path. An error path that hides the error is worse than
none.

**No free API credits.** The console account had no trial; a Claude chat
subscription does not include API access. This blocked the two API models for
days. ⟨Update with how it was resolved.⟩

## What went right, deliberately

Building and testing the whole harness against the free local model first
meant the API-key delay blocked nothing else. Replaying scoring from saved
raw files meant scorer bugs cost seconds, not API money. And writing NOTES.md
as things broke is the only reason this document could be written honestly.

## The one-sentence version

Most of our failures were environmental — disk, ports, hardware, credits —
not model-related, and every one of them now has an automatic check that
would have caught it in seconds.
