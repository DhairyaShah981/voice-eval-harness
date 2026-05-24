"""Optional offline KB matcher using sentence-transformers cosine similarity.

This module is lazily imported by ``kb/matcher.py`` when the user has the
``[kb]`` extra installed AND has set ``matcher: sentence_transformers`` in
their voxeval.yaml. Without sentence-transformers the default LLM-judge
matcher is used.

Model: ``sentence-transformers/all-MiniLM-L6-v2`` (~80MB, downloads on
first use, cached under ~/.cache/huggingface).
"""

from __future__ import annotations

import logging
from functools import lru_cache

log = logging.getLogger(__name__)

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_THRESHOLD = 0.78


@lru_cache(maxsize=1)
def _load_model(name: str = DEFAULT_MODEL):
    """Lazy-load the sentence-transformer model. Heavy import — only run
    when the user explicitly opts in to the offline matcher."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        raise RuntimeError(
            "sentence-transformers is not installed. Run "
            "`pip install voice-eval-harness[kb]` to enable the offline matcher."
        ) from e
    log.info("loading sentence-transformer model %s (one-time download)", name)
    return SentenceTransformer(name)


def cosine_match(
    agent_reply: str,
    expected_answer: str,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    model_name: str = DEFAULT_MODEL,
) -> bool:
    """Return True iff cosine(agent_reply, expected_answer) >= threshold.
    Cheap-and-cheerful: no judge call, no API spend."""
    if not agent_reply.strip():
        return False
    model = _load_model(model_name)
    import numpy as np
    embeddings = model.encode(
        [agent_reply, expected_answer], normalize_embeddings=True,
    )
    sim = float(np.dot(embeddings[0], embeddings[1]))
    return sim >= threshold
