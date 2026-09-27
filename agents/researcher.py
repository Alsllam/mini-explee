"""Agent 1 - the company researcher.

Input : a company website URL (+ optional screenshot of its homepage)
Output: a CompanyProfile (core/schemas.py)

Course lessons used here:
  2.2 Responses API     - a message list with several content parts
  2.5 Structured Outputs- text_format=CompanyProfile, no JSON parsing by hand
  3.2 Vision            - the homepage screenshot as an input_image part
  4.3 Built-in tools    - web="openai": OpenAI's own web_search (not on Azure)
  4.2 Function calling  - web="tavily": our search_web() tool, works on Azure too
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path

import config
from core.client import ask
from core.grounding import GroundingReport, check_grounding, strip_quotes
from core.schemas import CompanyProfile
from core.search import format_results, search_web, tavily_key
from core.web import Page, fetch_page

# Most searches the model may request before it must write the profile.
MAX_SEARCH_ROUNDS = 3

# Lower temperature = less variety between runs (lesson 1.2: outputs are not
# deterministic). It reduces, not removes, differences. Reasoning models reject
# this parameter: set ANALYSIS_TEMPERATURE= (empty) in .env if you use one.
_temp = os.getenv("ANALYSIS_TEMPERATURE", "0.2").strip()
ANALYSIS_TEMPERATURE = float(_temp) if _temp else None

# Function tool description (lesson 4.2). The model never sees our Python code,
# only this JSON: the name, what it is for, and the arguments it takes.
SEARCH_TOOL = {
    "type": "function",
    "name": "search_web",
    "description": (
        "Search the web for facts that are not on the company website, "
        "such as competitors or what others say about the company."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query, 2-8 words, e.g. 'Lucidya competitors'"}
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    "strict": True,
}

INSTRUCTIONS = """You are a B2B market analyst.
You receive the text of a company's website, and sometimes a screenshot of it.
Fill in the company profile using ONLY what the sources say.

Rules:
- Do not invent facts, numbers, customers or competitors.
- If something is not in the sources, use an empty list or say so in plain words.
- Keep every list item short (under 12 words).
- Customer types stated on the website go in target_customers_site.
  Customer types found ONLY in web search results go in target_customers_external.
- Write the profile in English, even if the website is in Arabic;
  copy the evidence quotes in their original language.
"""

WEB_SEARCH_NOTE = """
You can also search the web. Search at most twice: once to confirm what the
company does, once to find its main competitors. List competitors only if a
search result names them, and put the URLs you used in "sources".
"""


def resolve_web_mode(web: str | None) -> str | None:
    """Pick how to search: None (no search), 'tavily' or 'openai'.

    'auto' prefers Tavily when TAVILY_API_KEY is set, because it works on any
    provider; otherwise it falls back to OpenAI's built-in tool.
    """
    if web in (None, False, "", "none"):
        return None
    if web == "auto":
        web = "tavily" if tavily_key() else "openai"
    if web == "openai" and config.IS_AZURE:
        raise ValueError(
            "The built-in web_search tool is not available on Azure OpenAI. "
            "Add TAVILY_API_KEY to .env and use --web tavily "
            "(see docs/step-01b-web-search.md)."
        )
    if web == "tavily" and not tavily_key():
        raise ValueError("TAVILY_API_KEY is not set in .env.")
    if web not in ("tavily", "openai"):
        raise ValueError(f"Unknown web mode {web!r}. Use tavily, openai or auto.")
    return web


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


@dataclass
class AnalysisResult:
    profile: CompanyProfile
    response: object          # the last API response (for token counts)
    searches: list[dict]      # every search made, with its results
    grounding: GroundingReport


def _sampling() -> dict:
    return {} if ANALYSIS_TEMPERATURE is None else {"temperature": ANALYSIS_TEMPERATURE}


def analyze_company(
    url: str,
    *,
    screenshot: str | Path | None = None,
    web: str | None = None,
    page: Page | None = None,
    client=None,
    search=search_web,
    strict: bool = False,
) -> AnalysisResult:
    """Research one company, then check its claims against the sources.

    web    : None | "auto" | "tavily" | "openai"  (see resolve_web_mode)
    strict : drop evidence and competitors that the grounding check can't find
    page/client/search are injectable so tests run offline.
    """
    mode = resolve_web_mode(web)
    page = page or fetch_page(url)

    instructions = INSTRUCTIONS + (WEB_SEARCH_NOTE if mode else "")
    input_items = build_input(page, screenshot)

    if mode == "openai":
        # Lesson 4.3: one call; OpenAI runs the searches on its side.
        response = ask(
            input_items,
            task="smart",
            instructions=instructions,
            text_format=CompanyProfile,
            tools=[{"type": "web_search"}],
            client=client,
            **_sampling(),
        )
        searches = [
            {"query": getattr(getattr(item, "action", None), "query", ""), "results": []}
            for item in response.output
            if item.type == "web_search_call"
        ]
    elif mode == "tavily":
        # Lesson 4.2: the model asks, our code searches, we send results back.
        response, searches = _run_search_loop(input_items, instructions, client, search)
    else:
        response = ask(
            input_items,
            task="smart",
            instructions=instructions,
            text_format=CompanyProfile,
            client=client,
            **_sampling(),
        )
        searches = []

    profile = response.output_parsed
    if profile is None:
        # The model refused or ran out of tokens before finishing the JSON.
        raise RuntimeError(f"No structured output. Status: {getattr(response, 'status', '?')}")

    # Deterministic clean-up: code, not the model, removes stray quote marks.
    profile.evidence = [strip_quotes(q) for q in profile.evidence]

    grounding = check_grounding(
        profile.evidence,
        profile.competitors,
        website_text=page.as_prompt(),
        searches=searches,
        # OpenAI's built-in tool doesn't give us the result texts to check against.
        search_results_available=(mode != "openai"),
    )

    if strict:
        profile.evidence = [c.text for c in grounding.evidence if c.found]
        if grounding.competitors_verifiable:
            profile.competitors = [c.text for c in grounding.competitors if c.found]

    return AnalysisResult(profile, response, searches, grounding)


def _run_search_loop(input_items, instructions, client, search):
    """The function-calling loop (lesson 4.2).

    Each round: send the conversation + the tool description. If the model
    answers with function_call items, run them, append the results, repeat.
    If it answers with the profile, we are done.
    """
    items = list(input_items)
    searches: list[dict] = []

    for round_no in range(MAX_SEARCH_ROUNDS + 1):
        last_round = round_no == MAX_SEARCH_ROUNDS
        response = ask(
            items,
            task="smart",
            instructions=instructions,
            text_format=CompanyProfile,
            tools=[SEARCH_TOOL],
            # On the last round forbid more searches, so the model must answer.
            tool_choice="none" if last_round else "auto",
            client=client,
            **_sampling(),
        )

        calls = [item for item in response.output if item.type == "function_call"]
        if not calls:
            return response, searches

        for call in calls:
            # 1) Echo the model's request back into the history, as plain data.
            items.append(
                {
                    "type": "function_call",
                    "call_id": call.call_id,
                    "name": call.name,
                    "arguments": call.arguments,
                }
            )
            # 2) Run it and attach the result with the SAME call_id.
            query = json.loads(call.arguments).get("query", "")
            try:
                results = search(query)
                output = format_results(query, results)
            except Exception as err:  # tell the model instead of crashing
                results, output = [], f"Search failed: {type(err).__name__}: {err}"
            print(f"[search] {query!r} -> {len(results)} results")
            searches.append({"query": query, "results": results})
            items.append({"type": "function_call_output", "call_id": call.call_id, "output": output})

    return response, searches
