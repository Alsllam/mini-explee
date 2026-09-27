"""The single doorway to the OpenAI API for the whole project.

Every agent calls `ask()` instead of calling the SDK directly. That gives us,
in one place:
  1. The Responses API call itself                    (lesson 2.2)
  2. Model choice by task kind via config.py          (lesson 2.1)
  3. Retries with exponential backoff on safe errors  (lesson 5.1)
  4. A log line per call with tokens and latency      (groundwork for lesson 4.5)
"""
from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)

import config

# Errors worth retrying: the request was fine, the moment was bad (lesson 5.1).
#   RateLimitError      -> HTTP 429, too many requests or tokens per minute
#   APIConnectionError  -> network dropped before a reply arrived
#   APITimeoutError     -> no reply within the timeout
#   InternalServerError -> HTTP 5xx, a problem on OpenAI's side
# Everything else (bad key, bad parameters, unknown model) fails the same way
# every time, so retrying would only waste time and money.
RETRYABLE_ERRORS = (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError)

# HTTP 429 has two very different meanings, told apart by the error body:
#   "slow down"  -> rate_limit_exceeded: wait and retry, it will pass
#   "no money"   -> insufficient_quota: no credits left; waiting never fixes it
QUOTA_ERROR_MARKERS = {"insufficient_quota", "credit_balance_exhausted"}


def is_retryable(err: Exception) -> bool:
    """True if waiting and trying again can succeed."""
    if not isinstance(err, RETRYABLE_ERRORS):
        return False
    if isinstance(err, RateLimitError):
        markers = {getattr(err, "type", None), getattr(err, "code", None)}
        if markers & QUOTA_ERROR_MARKERS:
            return False
    return True

_client: OpenAI | None = None


def get_client() -> OpenAI:
    """Create the SDK client once and reuse it (it keeps connections open)."""
    global _client
    if _client is None:
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        # The SDK can retry on its own (default max_retries=2). We turn that off
        # so our own retry loop below is the only one, and we can see it work.
        # base_url=None means the default OpenAI endpoint; a URL means Azure
        # (or any other OpenAI-compatible endpoint). See config.OPENAI_BASE_URL.
        _client = OpenAI(base_url=config.OPENAI_BASE_URL, max_retries=0)
    return _client


def backoff_delay(attempt: int, base: float = 1.0, cap: float = 30.0) -> float:
    """Seconds to wait before retry number `attempt` (0-based).

    Doubles each time (1, 2, 4, 8 ... capped at `cap`) and adds random
    "jitter" so many clients that failed together don't all retry together.
    """
    return min(cap, base * (2 ** attempt)) * random.uniform(0.5, 1.0)


def ask(
    input: Any,
    *,
    task: str = "fast",
    instructions: str | None = None,
    text_format: type | None = None,
    client: OpenAI | None = None,
    sleep: Callable[[float], None] = time.sleep,
    **kwargs: Any,
):
    """Send one request through the Responses API and return the Response.

    input        : a string, or a list of messages (later steps use lists)
    task         : 'fast' | 'smart' | 'reasoning' -> picks the model (config.py)
    instructions : the system-level guidance for the model
    text_format  : a Pydantic model class -> Structured Outputs (lesson 2.5).
                   The model is forced to answer in that exact JSON shape and
                   the result is ready as `response.output_parsed`.
    client/sleep : injectable so tests can run without a key or real waiting
    **kwargs     : any other Responses API parameter (temperature, tools, text ...)
    """
    client = client or get_client()
    model = config.model_for(task)

    params: dict[str, Any] = {"model": model, "input": input, **kwargs}
    if instructions is not None:
        params["instructions"] = instructions

    attempts = config.MAX_RETRIES + 1
    for attempt in range(attempts):
        started = time.monotonic()
        try:
            if text_format is not None:
                response = client.responses.parse(text_format=text_format, **params)
            else:
                response = client.responses.create(**params)
        except RETRYABLE_ERRORS as err:
            if not is_retryable(err) or attempt == attempts - 1:
                _log_call(task, model, None, started, attempt + 1, error=err)
                raise
            wait = backoff_delay(attempt)
            print(f"[retry] {type(err).__name__} - attempt {attempt + 1}/{attempts}, waiting {wait:.1f}s")
            sleep(wait)
            continue
        except Exception as err:
            # Not retryable: log it and let the caller see the real error.
            _log_call(task, model, None, started, attempt + 1, error=err)
            raise

        _log_call(task, model, response, started, attempt + 1)
        return response


def _log_call(task, model, response, started, attempts, error=None) -> None:
    """Append one JSON line describing the call to config.LOG_FILE."""
    usage = getattr(response, "usage", None)
    details = getattr(usage, "input_tokens_details", None)
    record = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "task": task,
        "model": model,
        "response_id": getattr(response, "id", None),
        "input_tokens": getattr(usage, "input_tokens", None),
        "cached_tokens": getattr(details, "cached_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "latency_ms": round((time.monotonic() - started) * 1000),
        "attempts": attempts,
        "error": type(error).__name__ if error else None,
    }
    path = Path(config.LOG_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
