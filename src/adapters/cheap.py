"""The cheap model - the one we are really asking about."""

from src.adapters import _anthropic
from src.settings import MODELS

MODEL = MODELS["cheap"]["name"]


def generate(prompt: str) -> dict:
    return _anthropic.call(MODEL, prompt)
