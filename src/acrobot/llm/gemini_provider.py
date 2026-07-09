"""Gemini adapter (google-genai SDK) for the Provider protocol."""

import re

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel

from acrobot.llm.provider import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponse,
    Usage,
)

# Gemini reports "retry in 8.34s" in the message and "'retryDelay': '8s'" in
# the structured detail — match either. Conservative fallback when neither is
# present, so we never hammer a limit we can't measure.
_RETRY_MESSAGE = re.compile(r"retry in ([\d.]+)s", re.IGNORECASE)
_RETRY_DETAIL = re.compile(r"retrydelay['\"]?\s*[:=]\s*['\"]?(\d+)s", re.IGNORECASE)
_DEFAULT_RETRY_AFTER = 30.0


def _rate_limit_error(exc: Exception, model: str) -> ProviderRateLimitError:
    text = str(exc)
    # quotaId carries "...PerDay..." vs "...PerMinute..."; whitespace-strip so
    # the substring test survives pretty-printing.
    is_daily = "perday" in text.lower().replace(" ", "")
    match = _RETRY_MESSAGE.search(text) or _RETRY_DETAIL.search(text)
    retry_after = float(match.group(1)) if match else _DEFAULT_RETRY_AFTER
    scope = "daily" if is_daily else "per-minute"
    return ProviderRateLimitError(
        f"Gemini {scope} quota exhausted on {model}",
        retry_after=retry_after,
        is_daily=is_daily,
    )


class GeminiProvider:
    def __init__(
        self, api_key: str | None = None, *, client: genai.Client | None = None
    ) -> None:
        # `client` is an injection seam for tests and future reuse; production
        # passes nothing and we build from the key (or the GEMINI_API_KEY env).
        if client is not None:
            self._client = client
        elif api_key:
            self._client = genai.Client(api_key=api_key)
        else:
            self._client = genai.Client()

    def generate(
        self,
        *,
        model: str,
        system: str,
        prompt: str,
        schema: type[BaseModel],
        reasoning: bool = False,
    ) -> ProviderResponse:
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
            # Protocol `reasoning` → Gemini thinking budget: -1 dynamic, 0 off.
            thinking_config=types.ThinkingConfig(thinking_budget=-1 if reasoning else 0),
        )
        try:
            response = self._client.models.generate_content(
                model=model, contents=prompt, config=config
            )
        except genai_errors.APIError as exc:
            code = getattr(exc, "code", None)
            if code == 429 or "RESOURCE_EXHAUSTED" in str(exc):
                raise _rate_limit_error(exc, model) from exc
            # Google reports an invalid key as 400 API_KEY_INVALID, not 401/403,
            # so a status-code check alone can't catch it — hence the message
            # match (case-insensitive to survive wording drift).
            if "api key" in str(exc).lower() or code in (401, 403):
                raise ProviderAuthError(
                    "Gemini rejected the API key — re-set the GEMINI_API_KEY secret"
                ) from exc
            raise ProviderError(f"Gemini API error on {model}: {exc}") from exc
        parsed = response.parsed
        if not isinstance(parsed, schema):
            raise ProviderError(
                f"{model} returned unparseable output: {response.text!r:.200}"
            )
        meta = response.usage_metadata
        usage = Usage(
            input_tokens=(meta.prompt_token_count or 0) if meta else 0,
            output_tokens=(meta.candidates_token_count or 0) if meta else 0,
            thinking_tokens=(meta.thoughts_token_count or 0) if meta else 0,
        )
        return ProviderResponse(parsed=parsed, usage=usage, model=model)
