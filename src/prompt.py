"""The one prompt. Every model gets exactly this, word for word.

If this file changes after the real run starts, all three models must be
re-run from scratch. That is the whole point of the bake-off.
"""

import hashlib

PROMPT = """You are given a SQLite database with this schema:

{schema}

Write one SQL query that answers the question.
Output only the SQL. No explanation, no markdown fences.

Question: {question}
SQL:"""


def build(schema: str, question: str) -> str:
    """Fill the template in for one item."""
    return PROMPT.format(schema=schema, question=question)


def fingerprint() -> str:
    """Short hash of the prompt text.

    We print this at the start of every run and save it with the results.
    If two runs have different fingerprints, they are not comparable.
    """
    return hashlib.sha256(PROMPT.encode()).hexdigest()[:12]
