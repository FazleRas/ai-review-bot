"""Group hunks into review chunks under a per-request token budget."""

from reviewbot.diff.parser import Chunk


def build_chunks(chunks: list[Chunk], max_tokens_per_request: int = 8000) -> list[list[Chunk]]:
    """Merge small hunks from the same file; split oversized ones. Token counts
    come from the provider's tokenizer, not a character-count guess."""
    raise NotImplementedError("weekend 2")
