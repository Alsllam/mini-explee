"""Tests for core/client.py. They need no API key and make no network calls:
a fake client stands in for OpenAI, and `sleep` is replaced so no real waiting.

Run:  pytest -v
"""
import json
from types import SimpleNamespace

import openai
import pytest

import config
from core import client as core_client


def make_error(cls, message="simulated"):
    """Build an SDK exception without a real HTTP response."""
    err = cls.__new__(cls)
    Exception.__init__(err, message)
    err.message = message
    return err


def fake_response():
    usage = SimpleNamespace(
        input_tokens=12,
        output_tokens=30,
        input_tokens_details=SimpleNamespace(cached_tokens=0),
    )
    return SimpleNamespace(id="resp_test", model="fake-model", output_text="ok", usage=usage)


class FakeClient:
    """Raises the given errors in order, then returns a fake response."""

    def __init__(self, errors=()):
        self.errors = list(errors)
        self.calls = []
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **params):
        self.calls.append(params)
        if self.errors:
            raise self.errors.pop(0)
        return fake_response()


@pytest.fixture(autouse=True)
def tmp_log(tmp_path, monkeypatch):
    log = tmp_path / "calls.jsonl"
    monkeypatch.setattr(config, "LOG_FILE", str(log))
    monkeypatch.setattr(config, "MAX_RETRIES", 3)
    return log


def read_log(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_success_first_try_logs_tokens(tmp_log):
    fake = FakeClient()
    resp = core_client.ask("hi", client=fake, sleep=lambda s: None)

    assert resp.output_text == "ok"
    assert len(fake.calls) == 1
    assert fake.calls[0]["model"] == config.model_for("fast")
    assert "instructions" not in fake.calls[0]  # not sent when not given

    [line] = read_log(tmp_log)
    assert line["input_tokens"] == 12 and line["output_tokens"] == 30
    assert line["attempts"] == 1 and line["error"] is None


def test_retries_rate_limit_then_succeeds(tmp_log):
    fake = FakeClient([make_error(openai.RateLimitError), make_error(openai.APIConnectionError)])
    waits = []
    resp = core_client.ask("hi", client=fake, sleep=waits.append)

    assert resp.id == "resp_test"
    assert len(fake.calls) == 3
    assert len(waits) == 2
    assert read_log(tmp_log)[0]["attempts"] == 3


def test_gives_up_after_max_retries(tmp_log):
    errors = [make_error(openai.RateLimitError) for _ in range(10)]
    fake = FakeClient(errors)

    with pytest.raises(openai.RateLimitError):
        core_client.ask("hi", client=fake, sleep=lambda s: None)

    assert len(fake.calls) == config.MAX_RETRIES + 1
    assert read_log(tmp_log)[0]["error"] == "RateLimitError"


def test_no_credits_429_is_not_retried(tmp_log):
    err = make_error(openai.RateLimitError, "You have no credits remaining.")
    err.type, err.code = "insufficient_quota", "credit_balance_exhausted"
    fake = FakeClient([err])
    waits = []

    with pytest.raises(openai.RateLimitError):
        core_client.ask("hi", client=fake, sleep=waits.append)

    assert len(fake.calls) == 1  # failed fast, no wasted retries
    assert waits == []
    assert read_log(tmp_log)[0]["attempts"] == 1


def test_bad_request_is_not_retried(tmp_log):
    fake = FakeClient([make_error(openai.BadRequestError)])

    with pytest.raises(openai.BadRequestError):
        core_client.ask("hi", client=fake, sleep=lambda s: None)

    assert len(fake.calls) == 1


def test_backoff_grows_and_is_capped():
    for attempt in range(10):
        delay = core_client.backoff_delay(attempt, base=1.0, cap=30.0)
        assert 0 < delay <= min(30.0, 2 ** attempt)


def test_unknown_task_kind_is_rejected():
    with pytest.raises(ValueError):
        config.model_for("turbo")


def test_base_url_from_config_reaches_client(monkeypatch):
    azure = "https://my-resource.openai.azure.com/openai/v1/"
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(config, "OPENAI_BASE_URL", azure)
    monkeypatch.setattr(core_client, "_client", None)

    client = core_client.get_client()
    assert str(client.base_url) == azure

    monkeypatch.setattr(core_client, "_client", None)  # don't leak into other tests
