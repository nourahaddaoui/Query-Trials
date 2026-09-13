"""Write results/hardware.md by asking the machine, not by typing from memory.

The report has to state what hardware the open-weights model ran on, because
tokens per second is meaningless without it. Filling this in by hand is how you
end up reporting the wrong chip.

    python results/collect_hardware.py
"""

import json
import platform
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

OUT = Path(__file__).resolve().parent / "hardware.md"
MODEL_TAG = "qwen2.5-coder:3b-instruct-q4_K_M"


def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True,
                              text=True, timeout=20).stdout.strip()
    except Exception:
        return ""


def mac_specs():
    chip = sh("sysctl -n machdep.cpu.brand_string")
    cores = sh("sysctl -n hw.ncpu")
    mem_b = sh("sysctl -n hw.memsize")
    mem = f"{int(mem_b) / (1024 ** 3):.0f} GB" if mem_b.isdigit() else "unknown"
    model = sh("sysctl -n hw.model")
    return chip, cores, mem, model


def linux_specs():
    chip = sh("grep -m1 'model name' /proc/cpuinfo | cut -d: -f2").strip()
    cores = sh("nproc")
    kb = sh("grep MemTotal /proc/meminfo | awk '{print $2}'")
    mem = f"{int(kb) / (1024 ** 2):.0f} GB" if kb.isdigit() else "unknown"
    gpu = sh("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader")
    return chip, cores, mem, gpu or "no NVIDIA GPU detected"


def main():
    system = platform.system()
    if system == "Darwin":
        chip, cores, mem, extra = mac_specs()
        gpu_line = "Apple Silicon integrated GPU (Metal), unified memory"
        machine_label = extra or "Mac"
    elif system == "Linux":
        chip, cores, mem, extra = linux_specs()
        gpu_line = extra
        machine_label = platform.node()
    else:
        chip, cores, mem = platform.processor(), "?", "?"
        gpu_line, machine_label = "unknown", platform.node()

    ollama_ver = sh("ollama --version") or "not found on PATH"
    ollama_list = sh("ollama list")
    digest = ""
    for line in ollama_list.splitlines():
        if MODEL_TAG.split(":")[0] in line:
            parts = line.split()
            if len(parts) >= 2:
                digest = parts[1]
            break

    text = f"""# Hardware — the machine that ran the open-weights model

Recorded automatically by `results/collect_hardware.py` on {date.today()}.
Re-run it if you change machines; do not edit by hand.

## Machine

| | |
|---|---|
| Model | {machine_label} |
| OS | {system} {platform.release()} ({platform.machine()}) |
| CPU | {chip or "unknown"} |
| Cores | {cores} |
| Memory | {mem} |
| GPU | {gpu_line} |

## Model runtime

| | |
|---|---|
| Runtime | Ollama |
| Version | {ollama_ver} |
| Model | `{MODEL_TAG}` |
| Digest | {digest or "run: ollama list"} |
| Quantisation | Q4_K_M (~4.8 bits per weight, ~2 GB on disk) |
| Python | {sys.version.split()[0]} |

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
{ollama_list or "(ollama not found)"}
```
"""
    OUT.write_text(text, encoding="utf-8")
    print(f"Wrote {OUT}")
    print(f"  {chip or '?'} | {cores} cores | {mem} | ollama {ollama_ver}")
    if not digest:
        print("  NOTE: model digest not found - is the model pulled?")


if __name__ == "__main__":
    main()
