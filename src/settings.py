"""Settings shared by every model. These must be identical across all three."""

TEMPERATURE = 0        # no creativity - we want the model's single best answer
MAX_TOKENS = 300       # enough for a long SQL query, not enough to ramble
TIMEOUT_S = 60         # a call that takes longer than this counts as a failure

# Exact model names. Write these in the report, with the date you ran them.
#
# On "local": we planned the 7B, but the machine doing the local run is an
# Intel i5-8210Y with 8 GB of RAM and no usable GPU. A 4.7 GB model on CPU
# there would take minutes per question and distort the latency numbers, so we
# use the 3B (~2 GB) instead. The brief allows 1B-14B. This is a DIFFERENT
# MODEL, not a footnote - report it by the exact name below.
MODELS = {
    "top":   {"label": "Claude Opus 5",     "name": "claude-opus-5"},
    "cheap": {"label": "Claude Haiku 4.5",  "name": "claude-haiku-4-5-20251001"},
    "local": {"label": "Qwen2.5-Coder 3B",  "name": "qwen2.5-coder:3b-instruct-q4_K_M"},
}

OLLAMA_URL = "http://localhost:11434/v1/chat/completions"

# Where things live, relative to the project root.
DB_PATH = "data/database.sqlite"
ITEMS_PATH = "data/items.jsonl"
RESULTS_DIR = "results"
