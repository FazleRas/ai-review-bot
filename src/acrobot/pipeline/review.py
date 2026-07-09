"""Review pass: reasoning-enabled model emits structured Findings per unit.

A unit is one file with one or more of its hunks (see diff/chunker.py).
Each finding stays paired with the unit it came from — downstream anchor
validation and fingerprinting need the unit's merged line map, and we never
trust the model to report its own file path.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib.resources import files

from acrobot.diff.chunker import ReviewUnit
from acrobot.llm.provider import (
    Provider,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponse,
)
from acrobot.ratelimit import DailyBudgetExhausted, RateLimiter
from acrobot.schemas import Finding, FindingList
from acrobot.telemetry import RunTelemetry

# Cap the honored retry delay so a large or malformed value can't wedge a CI
# job; the free-tier per-minute window is 60s, so this never truncates a real one.
_MAX_RETRY_SLEEP = 65.0


@dataclass
class ReviewOutcome:
    findings: list[tuple[Finding, ReviewUnit]] = field(default_factory=list)
    units_reviewed: int = 0
    units_errored: int = 0
    budget_exhausted: bool = False


def _generate_with_retry(
    provider: Provider,
    model: str,
    system: str,
    prompt: str,
    sleep: Callable[[float], None],
) -> ProviderResponse:
    """One review call, retrying a per-minute rate limit once using the delay
    the provider reported. A per-day limit is re-raised for the loop to treat
    as budget exhaustion; an exhausted per-minute retry degrades to a normal
    ProviderError (skip this unit)."""
    try:
        return provider.generate(
            model=model, system=system, prompt=prompt, schema=FindingList, reasoning=True
        )
    except ProviderRateLimitError as exc:
        if exc.is_daily:
            raise
        sleep(min(exc.retry_after, _MAX_RETRY_SLEEP))
        try:
            return provider.generate(
                model=model, system=system, prompt=prompt, schema=FindingList, reasoning=True
            )
        except ProviderRateLimitError as retry_exc:
            if retry_exc.is_daily:
                raise
            raise ProviderError(f"rate limited after retry: {retry_exc}") from retry_exc


def _system_prompt() -> str:
    return files("acrobot.llm.prompts").joinpath("review_system.md").read_text()


def _user_prompt(unit: ReviewUnit) -> str:
    # The numbered new-file listing is what keeps anchors honest: the model
    # cites these numbers instead of counting diff lines itself.
    sections = []
    for chunk in unit.chunks:
        numbered = "\n".join(f"{n:>5} | {text}" for n, text in sorted(chunk.new_lines.items()))
        sections.append(
            f"Hunk `{chunk.hunk_header}`:\n```diff\n{chunk.content}```\n\n"
            f"New-file line numbers you may anchor findings to:\n```\n{numbered}\n```"
        )
    return f"File: `{unit.path}`\n\n" + "\n\n".join(sections)


def review(
    provider: Provider,
    limiter: RateLimiter,
    model: str,
    units: list[ReviewUnit],
    telemetry: RunTelemetry | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> ReviewOutcome:
    outcome = ReviewOutcome()
    system = _system_prompt()
    for unit in units:
        try:
            limiter.acquire()
        except DailyBudgetExhausted:
            outcome.budget_exhausted = True
            break
        started = time.monotonic()
        try:
            response = _generate_with_retry(provider, model, system, _user_prompt(unit), sleep)
        except ProviderRateLimitError:
            # Only per-day limits reach here (per-minute is retried inside).
            # Same outcome as the local RPD budget dying: stop, review partial.
            outcome.budget_exhausted = True
            break
        except ProviderError as exc:
            print(f"acrobot: provider error on {unit.path}: {exc}")
            outcome.units_errored += 1
            continue
        if telemetry is not None:
            telemetry.record("review", model, response.usage, time.monotonic() - started)
        outcome.units_reviewed += 1
        for finding in response.parsed.findings:
            finding.path = unit.path  # pipeline knows the path; the model doesn't get a vote
            outcome.findings.append((finding, unit))
    return outcome
