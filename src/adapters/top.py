"""The expensive model - our accuracy ceiling."""

from src.adapters import _anthropic
from src.settings import MODELS

MODEL = MODELS["top"]["name"]


def generate(prompt: str) -> dict:
    return _anthropic.call(MODEL, prompt)
