"""Agent 1 - the company researcher.

Input : a company website URL (+ optional screenshot of its homepage)
Output: a CompanyProfile (core/schemas.py)

Course lessons used here:
  2.2 Responses API     - a message list with several content parts
  2.5 Structured Outputs- text_format=CompanyProfile, no JSON parsing by hand
  3.2 Vision            - the homepage screenshot as an input_image part
  4.3 Built-in tools    - optional web_search (OpenAI only, not on Azure)
"""
from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

import config
from core.client import ask
from core.schemas import CompanyProfile
from core.web import Page, fetch_page

INSTRUCTIONS = """You are a B2B market analyst.
You receive the text of a company's website, and sometimes a screenshot of it.
Fill in the company profile using ONLY what the sources say.

Rules:
- Do not invent facts, numbers, customers or competitors.
- If something is not in the sources, use an empty list or say so in plain words.
- Keep every list item short (under 12 words).
- Write the profile in English, even if the website is in Arabic;
  copy the evidence quotes in their original language.
"""

WEB_SEARCH_NOTE = """
You also have a web_search tool. Use it at most twice: once to confirm what the
company does, once to find its main competitors. List competitors only if a
search result names them.
"""


def image_part(path: str | Path) -> dict:
    """Turn a local image file into an input_image content part (lesson 3.2).

    The API accepts an https URL or a base64 "data URL". A local file has no
    public URL, so we embed the bytes as base64.
    """
    path = Path(path)
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return {
        "type": "input_image",
        "image_url": f"data:{mime};base64,{data}",
        # "low" = a fixed, small token cost; "high" = reads fine print but costs more.
        "detail": "low",
    }


def build_input(page: Page, screenshot: str | Path | None = None) -> list[dict]:
    """One user message holding the page text and, optionally, the screenshot."""
    content: list[dict] = [{"type": "input_text", "text": page.as_prompt()}]
    if screenshot:
        content.append({"type": "input_text", "text": "Screenshot of the homepage:"})
        content.append(image_part(screenshot))
    return [{"role": "user", "content": content}]


def analyze_company(
    url: str,
    *,
    screenshot: str | Path | None = None,
    use_web_search: bool = False,
    page: Page | None = None,
    client=None,
) -> tuple[CompanyProfile, object]:
    """Research one company. Returns (profile, raw response).

    page/client are optional so tests can pass a ready Page and a fake client.
    """
    if use_web_search and config.IS_AZURE:
        raise ValueError(
            "web_search is not available on Azure OpenAI. Run without --web, "
            "or use an OpenAI key (see docs/step-01-company-analyzer.md)."
        )

    page = page or fetch_page(url)

    instructions = INSTRUCTIONS
    extra: dict = {}
    if use_web_search:
        instructions += WEB_SEARCH_NOTE
        extra["tools"] = [{"type": "web_search"}]

    response = ask(
        build_input(page, screenshot),
        task="smart",
        instructions=instructions,
        text_format=CompanyProfile,
        client=client,
        **extra,
    )

    profile = response.output_parsed
    if profile is None:
        # The model refused or ran out of tokens before finishing the JSON.
        raise RuntimeError(f"No structured output. Status: {getattr(response, 'status', '?')}")
    return profile, response
