"""Review pass: reasoning-enabled model emits structured Findings per chunk."""

from reviewbot.diff.parser import Chunk
from reviewbot.llm.provider import Provider
from reviewbot.ratelimit import RateLimiter
from reviewbot.schemas import Finding


def review(provider: Provider, limiter: RateLimiter, model: str,
           chunks: list[Chunk]) -> list[Finding]:
    raise NotImplementedError("weekend 1")
