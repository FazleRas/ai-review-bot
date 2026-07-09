"""Provider-agnostic LLM interface.

The pipeline never imports a vendor SDK — it talks to this protocol. Vendor
parameters stay inside adapters: `reasoning=True` maps to Gemini's dynamic
thinking budget, or to Anthropic's adaptive thinking in a future adapter. Do
not add vendor-shaped parameters (thinking budgets, effort levels) here.
"""

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0


@dataclass
class ProviderResponse[T: BaseModel]:
    parsed: T
    usage: Usage
    model: str


class ProviderError(RuntimeError):
    """Per-request failure (bad JSON, transient API error) — skip the chunk."""


class ProviderAuthError(RuntimeError):
    """Credentials are bad — every chunk will fail, so abort the whole run.

    Deliberately NOT a ProviderError subclass: the pipeline's per-chunk
    error handling must never swallow an auth failure into a green check.
    """


class ProviderRateLimitError(RuntimeError):
    """A rate/quota limit was hit. Carries the provider's own advice so the
    caller can act on it instead of guessing.

    Not a ProviderError subclass: the two demand different responses. A
    per-minute limit (`is_daily=False`) is transient — wait `retry_after` and
    retry. A per-day limit (`is_daily=True`) means the run is out of budget —
    stop and post a partial review, exactly like DailyBudgetExhausted.
    """

    def __init__(self, message: str, *, retry_after: float, is_daily: bool) -> None:
        super().__init__(message)
        self.retry_after = retry_after
        self.is_daily = is_daily


class Provider(Protocol):
    def generate[T: BaseModel](
        self,
        *,
        model: str,
        system: str,
        prompt: str,
        schema: type[T],
        reasoning: bool = False,
    ) -> ProviderResponse[T]:
        """One structured-output completion. Implementations must return a
        validated `schema` instance or raise ProviderError."""
        ...
