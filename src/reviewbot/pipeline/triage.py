"""Cheap-model pass: score each chunk for review-worthiness before the
expensive model spends rate-limit budget on it."""

from reviewbot.diff.parser import Chunk
from reviewbot.llm.provider import Provider
from reviewbot.ratelimit import RateLimiter


def triage(provider: Provider, limiter: RateLimiter, model: str,
           chunks: list[Chunk], threshold: int) -> list[Chunk]:
    raise NotImplementedError("weekend 4")
