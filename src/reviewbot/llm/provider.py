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
    """The provider returned something unusable (bad JSON, empty candidate)."""


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
