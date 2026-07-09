"""Bot configuration, loaded from `.github/acrobot.yml` in the target repo.

Missing file or missing keys fall back to defaults, so consumers can adopt the
bot with zero config and tune later.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from acrobot.schemas import Severity


class ModelsConfig(BaseModel):
    triage: str = "gemini-2.5-flash-lite"
    review: str = "gemini-2.5-flash"


class RateLimitConfig(BaseModel):
    """Client-side throttle for the review model's free-tier quota.

    Defaults sit just under the observed gemini-2.5-flash free-tier caps
    (5 requests/min, 20/day) to leave headroom. Two caveats these numbers
    can't fix, only soften:
      * The daily pool is shared across every workflow run and every repo on
        the same API key — this limiter only meters within a single run, so
        the real ceiling is lower than `rpd` on a busy day.
      * Google adjusts free-tier limits over time; treat these as config, not
        truth, and check ai.google.dev/gemini-api/docs/rate-limits.
    The provider still honors server-sent retry delays on top of this, so
    conservative defaults plus server backoff cover the gap.
    """

    rpm: int = 4
    rpd: int = 18


class BotConfig(BaseModel):
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    rate_limits: RateLimitConfig = Field(default_factory=RateLimitConfig)
    triage_threshold: int = Field(default=4, ge=0, le=10)
    confidence_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    max_comments: int = 10
    severity_floor: Severity = "warning"
    max_patch_bytes: int = 100_000
    max_tokens_per_request: int = 8_000
    ignore: list[str] = Field(
        default_factory=lambda: ["**/*.lock", "**/generated/**", "**/*.min.*"]
    )

    @classmethod
    def load(cls, path: Path | None) -> "BotConfig":
        if path is None or not path.exists():
            return cls()
        return cls.model_validate(yaml.safe_load(path.read_text()) or {})
