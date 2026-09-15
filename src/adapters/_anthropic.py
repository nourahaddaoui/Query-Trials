"""Shared code for both Claude models.

top.py and cheap.py are thin wrappers around this. Same code path, only the
model name differs - which is exactly what "compare fairly" requires.

ON TEMPERATURE
--------------
The brief asks for temperature 0 on all three models. The installed Anthropic
SDK (1.5.0) does not accept a `temperature` argument at all - it was removed
from Messages.create(), and passing it raises TypeError. Our first full run
failed all 120 API calls for exactly that reason.

We do not silently drop it. Instead:

  * we probe once, at import, whether this SDK accepts temperature
  * if it does, we pass 0, same as the local model
  * if it does not, we omit it and record `temperature_set: false` on every
    result row, so the report can state the asymmetry rather than imply a
    setting we never applied

This is a real limitation of the comparison and belongs in the write-up: the
local model is pinned to greedy decoding, the API models use whatever default
the provider applies.
"""

import inspect
import time

from anthropic import Anthropic
from dotenv import load_dotenv

from src.settings import TEMPERATURE, MAX_TOKENS, TIMEOUT_S

load_dotenv()
_client = Anthropic(timeout=TIMEOUT_S)

# Probe once rather than try/except on every call - a per-call fallback would
# hide the fact that the setting is not being applied.
SUPPORTS_TEMPERATURE = "temperature" in inspect.signature(
    _client.messages.create).parameters


def call(model_name: str, prompt: str) -> dict:
    """Send one prompt, return one result in the shape every adapter uses.

    We start the clock immediately before the request and stop it when the
    full answer has arrived. Streaming is off on purpose: we want the time
    to the complete answer, not the time to the first word.
    """
    kwargs = {
        "model": model_name,
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }
    if SUPPORTS_TEMPERATURE:
        kwargs["temperature"] = TEMPERATURE

    t0 = time.perf_counter()
    try:
        resp = _client.messages.create(**kwargs)
        latency_ms = (time.perf_counter() - t0) * 1000
        return {
            "text": resp.content[0].text,
            "prompt_tokens": resp.usage.input_tokens,
            "completion_tokens": resp.usage.output_tokens,
            "latency_ms": round(latency_ms, 1),
            "temperature_set": SUPPORTS_TEMPERATURE,
            "error": None,
        }
    except Exception as e:
        # A failure still costs time, so we still record it. The scorer
        # will mark this item wrong - that is what the brief asks for.
        latency_ms = (time.perf_counter() - t0) * 1000
        return {
            "text": "",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "latency_ms": round(latency_ms, 1),
            "temperature_set": SUPPORTS_TEMPERATURE,
            "error": f"{type(e).__name__}: {e}",
        }
