"""Data shapes shared by the agents (lesson 2.5: Structured Outputs).

Each agent returns one of these models instead of free text. The next agent
can then read fields directly (profile.offering) instead of guessing from prose.

Rules for Structured Outputs schemas:
  - Every field is required. For "may be unknown", use an empty string or list,
    never a default value (the strict JSON schema does not allow defaults).
  - Field descriptions are sent to the model, so write them as instructions.
"""
from typing import Literal

from pydantic import BaseModel, Field


class CompanyProfile(BaseModel):
    """What a company sells and to whom - output of agents/researcher.py."""

    name: str = Field(description="Company name as written on the website.")
    website: str = Field(description="The URL that was analyzed.")
    one_liner: str = Field(description="One sentence: what the company does, in plain words.")
    offering: list[str] = Field(description="Main products or services, 1-6 short items.")
    value_props: list[str] = Field(
        description="Benefits the company claims for its customers, 1-5 short items."
    )
    target_customers_site: list[str] = Field(
        description="Who the company says it sells to, according to ITS OWN WEBSITE only "
        "(industries, company sizes, roles). Empty list if the website gives no hint."
    )
    target_customers_external: list[str] = Field(
        description="Customer types mentioned ONLY by web search results, not on the website. "
        "Empty list if you did not search or found none."
    )
    competitors: list[str] = Field(
        description="Competitor names ONLY if found in the sources. Never guess. Empty list if none."
    )
    language: Literal["ar", "en", "mixed"] = Field(description="Main language of the website.")
    evidence: list[str] = Field(
        description="2-5 full sentences copied WORD FOR WORD from the website text, in their "
        "original language, that support the analysis. At least 5 words each. "
        "Do not add quotation marks around them."
    )
    sources: list[str] = Field(
        description="URLs of web search results you actually used. Empty list if you did not search."
    )
    confidence: Literal["high", "medium", "low"] = Field(
        description="low if the page had little text or was mostly images/scripts."
    )
