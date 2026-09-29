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
        description="Customer TYPES (industries, sizes, roles - not company names) mentioned ONLY "
        "by web search results, not on the website. Empty list if you did not search or found none."
    )
    named_customers: list[str] = Field(
        description="Names of real organizations the sources say are customers of this company "
        "(logos, case studies, news). Exact names as written in the source. Never guess. "
        "Empty list if none."
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


# --- Step 2: ideal customer profile -----------------------------------------

class ICPSegment(BaseModel):
    """One group of companies worth selling to - output of agents/icp.py."""

    name: str = Field(description="Short label, 2-5 words, e.g. 'Saudi retail banks'.")
    description: str = Field(description="One or two sentences: who they are and why they buy.")
    industries: list[str] = Field(description="1-3 industries.")
    company_size: str = Field(description="Size range in employees, e.g. '500-5,000 employees'.")
    regions: list[str] = Field(description="Countries or regions, e.g. 'Saudi Arabia', 'GCC'.")
    buyer_roles: list[str] = Field(
        description="2-4 job titles who would buy or champion the product, e.g. 'Head of CX'."
    )
    pain_points: list[str] = Field(description="2-4 problems these buyers have that the product solves.")
    why_fit: list[str] = Field(
        description="2-4 reasons, each tied to a fact in the company profile. Name the field, "
        "e.g. 'named_customers includes Al-Rajhi Bank'."
    )
    signals: list[str] = Field(
        description="2-4 signs visible from outside that a company belongs here, "
        "e.g. 'active Arabic social media accounts', 'hiring CX managers'."
    )
    disqualifiers: list[str] = Field(description="1-3 signs a company is NOT a fit.")
    priority: Literal["high", "medium", "low"] = Field(
        description="high = strongest evidence in the profile and easiest to win."
    )


class ICPReport(BaseModel):
    """The full answer of the ICP agent, first proposal or after feedback."""

    segments: list[ICPSegment] = Field(description="2-3 segments, most promising first.")
    assumptions: list[str] = Field(
        description="Things you assumed that the profile does not state. Empty list if none."
    )
    questions_for_user: list[str] = Field(
        description="1-3 questions whose answers would sharpen the segments."
    )
    change_summary: str = Field(
        description="'Initial proposal' the first time; after feedback, what you changed and why."
    )


# --- Step 3: lead scoring ----------------------------------------------------

class LeadScore(BaseModel):
    """How well one lead fits the ICP - output of agents/scorer.py."""

    lead_id: str = Field(description="Copy the lead_id exactly as given.")
    segment: str = Field(
        description="Name of the best-matching ICP segment, copied exactly, or 'none'."
    )
    fit_score: int = Field(description="0-100, using the scoring rubric.")
    reasons: list[str] = Field(description="1-3 short reasons, each naming a lead field.")
    missing_info: list[str] = Field(
        description="Facts that would change the score if known. Empty list if none."
    )
    recommendation: Literal["contact", "nurture", "skip"] = Field(
        description="contact: score >= 70. nurture: 40-69. skip: below 40."
    )
