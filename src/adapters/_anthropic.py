"""Shared code for both Claude models.

top.py and cheap.py are thin wrappers around this. Same code path, only the
model name differs - which is exactly what "compare fairly" requires.
"""

import time
from anthropic import Anthropic
from dotenv import load_dotenv

from src.settings import TEMPERATURE, MAX_TOKENS, TIMEOUT_S

load_dotenv()
_client = Anthropic(timeout=TIMEOUT_S)


def call(model_name: str, prompt: str) -> dict:
    """Send one prompt, return one result in the shape every adapter uses.

    We start the clock immediately before the request and stop it when the
    full answer has arrived. Streaming is off on purpose: we want the time
    to the complete answer, not the time to the first word.
    """
    t0 = time.perf_counter()
    try:
        resp = _client.messages.create(
            model=model_name,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            messages=[{"role": "user", "content": prompt}],
        )
        latency_ms = (time.perf_counter() - t0) * 1000
        return {
            "text": resp.content[0].text,
            "prompt_tokens": resp.usage.input_tokens,
            "completion_tokens": resp.usage.output_tokens,
            "latency_ms": round(latency_ms, 1),
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
            "error": f"{type(e).__name__}: {e}",
        }
