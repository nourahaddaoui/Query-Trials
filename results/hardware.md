# Hardware — the machine that ran the open-weights model

Recorded automatically by `results/collect_hardware.py` on 2026-09-14.
Re-run it if you change machines; do not edit by hand.

## Machine

| | |
|---|---|
| Model | MacBookAir8,2 |
| OS | Darwin 23.6.0 (x86_64) |
| CPU | Intel(R) Core(TM) i5-8210Y CPU @ 1.60GHz |
| Cores | 4 |
| Memory | 8 GB |
| GPU | Apple Silicon integrated GPU (Metal), unified memory |

## Model runtime

| | |
|---|---|
| Runtime | Ollama |
| Version | ollama version is 0.34.0 |
| Model | `qwen2.5-coder:3b-instruct-q4_K_M` |
| Digest | f72c60cabf62 |
| Quantisation | Q4_K_M (~4.8 bits per weight, ~2 GB on disk) |
| Python | 3.14.7 |

**On the model size.** We planned the 7B and ran the 3B. This machine has 8 GB
of RAM, no usable GPU, and a fanless dual-core CPU; a 4.7 GB model on CPU there
takes minutes per question, which would have told us more about the laptop than
about the model. The brief allows 1B–14B, so the 3B is a valid choice — but it
is a different model and is reported as such, not as a footnote on the 7B.

**On the quantisation.** The local model runs at 4-bit while the two API models
run at whatever precision the provider serves. That is a real difference and it
is stated here rather than glossed over. Running Qwen at full precision is not
what a laptop deployment would actually do — so this is the honest comparison,
but it compares *deployments*, not model weights in the abstract.

## Measurement conditions

- Three warm-up calls before timing, excluded from all results. The first call
  after a cold start includes loading the model from disk, which is real but is
  not what we are measuring.
- `keep_alive` left at the Ollama default so the model stays resident between
  items.
- Models run one after another, never at the same time.
- Nothing else running on the machine during the timed run.

## Tokens per second

Taken from `completion_tokens / (latency_ms / 1000)` per item, recorded in
`results/raw/*__local.jsonl`. Report the median, not the mean.

_Fill in after the run:_ median ___ tok/s across 50 items.

---

```
$ ollama list
NAME                                ID              SIZE      MODIFIED      
qwen2.5-coder:3b-instruct-q4_K_M    f72c60cabf62    1.9 GB    5 minutes ago
```
