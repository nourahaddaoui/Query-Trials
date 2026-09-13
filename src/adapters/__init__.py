"""Pick an adapter by name.

Every adapter exposes the same function:

    generate(prompt: str) -> dict with keys
        text, prompt_tokens, completion_tokens, latency_ms, error

Because they all look the same from the outside, run.py does not need to know
which model it is talking to.
"""


def get(name: str):
    if name == "top":
        from src.adapters import top
        return top
    if name == "cheap":
        from src.adapters import cheap
        return cheap
    if name == "local":
        from src.adapters import local
        return local
    raise ValueError(f"Unknown model '{name}'. Use: top, cheap, local")
