"""The open-weights model, running on our own machine through Ollama.

Ollama exposes an OpenAI-compatible endpoint, so this looks almost identical
to the Claude adapters. That similarity is deliberate: same code path for all
three models means the comparison stays fair.
"""

import time
import requests

from src.settings import TEMPERATURE, MAX_TOKENS, TIMEOUT_S, MODELS, OLLAMA_URL

MODEL = MODELS["local"]["name"]


def generate(prompt: str) -> dict:
    t0 = time.perf_counter()
    try:
        r = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "temperature": TEMPERATURE,
                "max_tokens": MAX_TOKENS,
                "stream": False,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=TIMEOUT_S,
        )
        latency_ms = (time.perf_counter() - t0) * 1000
        r.raise_for_status()
        data = r.json()
        usage = data.get("usage", {})
        completion = usage.get("completion_tokens", 0)
        return {
            "text": data["choices"][0]["message"]["content"],
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": completion,
            "latency_ms": round(latency_ms, 1),
            # Tokens per second - the report needs this for our own model only.
            "tokens_per_sec": round(completion / (latency_ms / 1000), 1) if completion else 0,
            "error": None,
        }
    except Exception as e:
        latency_ms = (time.perf_counter() - t0) * 1000
        return {
            "text": "",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "latency_ms": round(latency_ms, 1),
            "tokens_per_sec": 0,
            "error": f"{type(e).__name__}: {e}",
        }


def warm_up(n: int = 3) -> None:
    """Load the model into memory before timing anything.

    The first call after a cold start includes several seconds of loading the
    model from disk. That is real, but it is not what we are measuring, so we
    throw away the first few calls. We say so in the report.
    """
    for _ in range(n):
        generate("SELECT 1;")
