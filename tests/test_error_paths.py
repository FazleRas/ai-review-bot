"""Error-path coverage — auth, rate limits, and the retry loop."""

import json

import pytest
from google.genai import errors as genai_errors

import acrobot.__main__ as entry
from acrobot.llm.gemini_provider import GeminiProvider
from acrobot.llm.provider import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
)
from acrobot.schemas import FindingList

PATCH = (
    "@@ -1,2 +1,3 @@\n"
    " def f():\n"
    "+    x = 1\n"
    "     return None\n"
)


class _AuthFailProvider:
    def generate(self, **kwargs):  # noqa: ANN003
        raise ProviderAuthError("bad key")


class TestMainAuthHandling:
    """main() must exit 1 with a clear stderr line on bad credentials."""

    def test_auth_error_exits_1_and_prints_to_stderr(self, monkeypatch, tmp_path, capsys):
        event = tmp_path / "event.json"
        event.write_text(
            json.dumps({"pull_request": {"number": 7, "draft": False, "head": {"sha": "abc"}}})
        )
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")
        monkeypatch.setattr(entry, "GeminiProvider", _AuthFailProvider)
        monkeypatch.setattr(
            entry,
            "fetch_changed_files",
            lambda gh, n: [{"filename": "a.py", "status": "modified", "patch": PATCH}],
        )

        assert entry.main() == 1
        captured = capsys.readouterr()
        assert "bad key" in captured.err


class _FakeClient:
    """Injectable client whose generate_content raises a fixed exception —
    the seam the bot asked for on PR #4, replacing the __new__ bypass."""

    def __init__(self, exc: Exception) -> None:
        outer = self

        class _Models:
            def generate_content(self, **kwargs):  # noqa: ANN003
                raise outer._exc

        self._exc = exc
        self.models = _Models()


def _provider_raising(exc: Exception) -> GeminiProvider:
    return GeminiProvider(client=_FakeClient(exc))


def _api_error(code: int, message: str) -> genai_errors.APIError:
    return genai_errors.APIError(code, {"error": {"message": message, "code": code}})


class TestGeminiErrorMapping:
    @pytest.mark.parametrize(
        "exc",
        [
            _api_error(400, "API key not valid. Please pass a valid API key."),
            _api_error(401, "Request had invalid authentication credentials."),
            _api_error(403, "Permission denied."),
        ],
    )
    def test_auth_failures_raise_provider_auth_error(self, exc):
        with pytest.raises(ProviderAuthError):
            _provider_raising(exc).generate(model="m", system="s", prompt="p", schema=FindingList)

    @pytest.mark.parametrize(
        "exc",
        [
            _api_error(500, "Internal error."),
            _api_error(503, "The service is currently unavailable."),
        ],
    )
    def test_other_api_errors_raise_provider_error(self, exc):
        with pytest.raises(ProviderError):
            _provider_raising(exc).generate(model="m", system="s", prompt="p", schema=FindingList)


class TestRateLimitMapping:
    """429s are parsed into ProviderRateLimitError with the right scope + delay."""

    def test_per_minute_quota_is_transient_with_delay(self):
        msg = (
            "429 RESOURCE_EXHAUSTED. Quota exceeded ... quotaId: "
            "'GenerateRequestsPerMinutePerProjectPerModel-FreeTier' ... "
            "Please retry in 8.34s."
        )
        with pytest.raises(ProviderRateLimitError) as caught:
            _provider_raising(_api_error(429, msg)).generate(
                model="m", system="s", prompt="p", schema=FindingList
            )
        assert caught.value.is_daily is False
        assert caught.value.retry_after == pytest.approx(8.34)

    def test_per_day_quota_is_daily(self):
        msg = (
            "429 RESOURCE_EXHAUSTED. quotaId: "
            "'GenerateRequestsPerDayPerProjectPerModel-FreeTier', quotaValue: '20'"
        )
        with pytest.raises(ProviderRateLimitError) as caught:
            _provider_raising(_api_error(429, msg)).generate(
                model="m", system="s", prompt="p", schema=FindingList
            )
        assert caught.value.is_daily is True

    def test_unparseable_delay_falls_back_conservatively(self):
        with pytest.raises(ProviderRateLimitError) as caught:
            _provider_raising(_api_error(429, "429 RESOURCE_EXHAUSTED, no details")).generate(
                model="m", system="s", prompt="p", schema=FindingList
            )
        assert caught.value.retry_after == 30.0
