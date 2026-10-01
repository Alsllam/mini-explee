"""Content moderation before anything goes to the outbox (lesson 5.2).

Two providers, chosen automatically:

  OpenAI : the Moderations API (client.moderations.create, omni-moderation).
           Free; returns flagged + one true/false per harm category.

  Azure  : Azure OpenAI has NO /moderations endpoint. Instead every deployment
           runs a built-in content filter (hate, sexual, violence, self-harm)
           on prompts and answers. A blocked request fails with HTTP 400 and
           error code "content_filter". To check a finished text, we send it
           as the PROMPT of a tiny request: if the filter blocks it, it is flagged.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from openai import BadRequestError

import config
from core.client import ask, get_client

OPENAI_MODERATION_MODEL = "omni-moderation-latest"


@dataclass
class ModerationResult:
    flagged: bool
    provider: str
    categories: list[str] = field(default_factory=list)  # which harms, when flagged


def moderate(text: str, client=None) -> ModerationResult:
    if config.IS_AZURE:
        return _azure_filter(text, client)
    return _openai_moderation(text, client)


def _openai_moderation(text: str, client=None) -> ModerationResult:
    client = client or get_client()
    resp = client.moderations.create(model=OPENAI_MODERATION_MODEL, input=text)
    result = resp.results[0]
    cats = result.categories.model_dump() if hasattr(result.categories, "model_dump") else dict(result.categories)
    return ModerationResult(bool(result.flagged), "openai-moderations",
                            sorted(name for name, hit in cats.items() if hit))


def is_content_filter_error(err: Exception) -> bool:
    return isinstance(err, BadRequestError) and getattr(err, "code", None) == "content_filter"


def _azure_filter(text: str, client=None) -> ModerationResult:
    try:
        ask(
            "Reply with the single word OK.\n\nTEXT TO CHECK:\n" + text,
            task="fast",
            max_output_tokens=16,
            client=client,
        )
    except BadRequestError as err:
        if is_content_filter_error(err):
            return ModerationResult(True, "azure-content-filter", ["blocked by content filter"])
        raise
    return ModerationResult(False, "azure-content-filter")
