"""Agent 2 - the ideal customer profile (ICP) strategist.

Input : a CompanyProfile saved by step 1 (data/output/company_<domain>.json)
Output: an ICPReport (core/schemas.py): 2-3 customer segments to target

Course lessons used here:
  2.6 Reasoning models  - task="reasoning" + reasoning={"effort": ...}
  2.3 Conversation state- previous_response_id: refine the answer with feedback
                          without re-sending the whole conversation ourselves
  2.5 Structured Outputs- text_format=ICPReport on every turn
"""
from __future__ import annotations

import json
from pathlib import Path

import config
from core.client import ask
from core.schemas import CompanyProfile, ICPReport

INSTRUCTIONS = """You are a B2B go-to-market strategist.
You receive a company profile as JSON. Decide which groups of companies this
company should sell to first, and describe each group so that a sales team
could find them and a writer could address them.

How to decide:
- Base every segment on facts in the profile. In why_fit, name the field
  you rely on (e.g. "named_customers includes Al-Rajhi Bank").
- Trust target_customers_site and named_customers more than
  target_customers_external: the first two are what the company itself shows.
- Prefer segments where the company already has customers or clear proof.
- Put anything you assume but the profile does not say in "assumptions".
- 2 or 3 segments, most promising first. No overlapping segments.

When the user sends feedback, return the WHOLE report again with the change
applied, keep everything they did not ask to change, and explain the change
in change_summary.

Write in English.
"""


def load_profile(path: str | Path) -> CompanyProfile:
    """Read a profile saved by step 1, with a clear error for old files."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} not found. Run step 1 first: python -m scripts.analyze_company <url> --web tavily"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    try:
        return CompanyProfile.model_validate(data)
    except Exception as err:
        raise ValueError(
            f"{path} does not match the current CompanyProfile (made by an older step?). "
            "Run step 1 again to regenerate it."
        ) from err


def _reasoning() -> dict:
    """The reasoning parameter, only when configured (non-reasoning models reject it)."""
    return {"reasoning": {"effort": config.REASONING_EFFORT}} if config.REASONING_EFFORT else {}


def propose_icp(profile: CompanyProfile, *, client=None):
    """First turn: send the whole profile. Returns (ICPReport, response)."""
    response = ask(
        "Company profile:\n" + profile.model_dump_json(indent=2),
        task="reasoning",
        instructions=INSTRUCTIONS,
        text_format=ICPReport,
        store=True,  # keep the response on the server so the next turn can point to it
        client=client,
        **_reasoning(),
    )
    return _parsed(response), response


def refine_icp(feedback: str, previous_response_id: str, *, client=None):
    """Next turns: send ONLY the feedback and point to the previous response.

    The server already holds the profile and the last report, so we don't send
    them again (lesson 2.3). Two things are NOT carried over and must be sent
    on every turn: `instructions` and `text_format`.
    """
    response = ask(
        feedback,
        task="reasoning",
        instructions=INSTRUCTIONS,
        text_format=ICPReport,
        previous_response_id=previous_response_id,
        store=True,
        client=client,
        **_reasoning(),
    )
    return _parsed(response), response


def _parsed(response) -> ICPReport:
    report = response.output_parsed
    if report is None:
        raise RuntimeError(
            f"No structured output. Status: {getattr(response, 'status', '?')}. "
            "If it says 'incomplete', the model may have used all tokens on reasoning: "
            "try REASONING_EFFORT=low."
        )
    return report
