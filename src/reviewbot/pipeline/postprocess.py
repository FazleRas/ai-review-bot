"""Anchor validation, confidence threshold, dedupe, comment cap."""

from reviewbot.config import BotConfig
from reviewbot.diff.parser import Chunk
from reviewbot.schemas import Finding


def postprocess(findings: list[Finding], chunks: list[Chunk],
                existing_fingerprints: set[str], config: BotConfig) -> list[Finding]:
    raise NotImplementedError("weekend 2")
