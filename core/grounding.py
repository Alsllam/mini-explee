"""Grounding checks: is every claim backed by the text we actually gave the model?

"Grounded" means: the answer can be traced to a source. The model was told
not to invent anything, but telling is not checking. Here plain Python code
(no AI, no cost) looks for each quote and each competitor name in the sources:

  evidence quotes  -> must appear in the website text
  competitor names -> must appear in the search results (or the website)

Anything not found is flagged. A flag does not prove the model invented it
(the wording may differ slightly), but it tells a human exactly what to check.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field

# Quote marks the model sometimes wraps around evidence: " ' “ ” ‘ ’ « » „
QUOTE_CHARS = "\"'“”‘’«»„`"

# Arabic short vowels (harakat), tanween, shadda, sukun, dagger alef.
ARABIC_MARKS = re.compile(r"[ً-ْٰ]")
TATWEEL = "ـ"


def strip_quotes(text: str) -> str:
    """Remove quote marks around a quote: '"لحظة بلحظة"' -> 'لحظة بلحظة'."""
    return text.strip().strip(QUOTE_CHARS).strip()


def normalize(text: str) -> str:
    """Make two texts comparable despite small, meaningless differences.

    - Unicode NFKC (e.g. full-width letters -> normal letters)
    - lower case
    - Arabic: drop harakat and tatweel, unify alef forms, alef maqsura -> yeh
      so "نموًا" and "نمواً" and "نموا" all match
    - quote marks removed, all whitespace collapsed to one space
    """
    text = unicodedata.normalize("NFKC", text).lower()
    text = ARABIC_MARKS.sub("", text).replace(TATWEEL, "")
    text = re.sub("[أإآ]", "ا", text)  # أ إ آ -> ا
    text = text.replace("ى", "ي")  # ى -> ي
    text = text.translate({ord(c): " " for c in QUOTE_CHARS})
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class Check:
    text: str
    found: bool
    where: str = ""  # "website" or a search result URL


@dataclass
class GroundingReport:
    evidence: list[Check] = field(default_factory=list)
    competitors: list[Check] = field(default_factory=list)
    competitors_verifiable: bool = True  # False when search results are not available

    @property
    def unverified_evidence(self) -> list[str]:
        return [c.text for c in self.evidence if not c.found]

    @property
    def unverified_competitors(self) -> list[str]:
        if not self.competitors_verifiable:
            return []
        return [c.text for c in self.competitors if not c.found]

    @property
    def ok(self) -> bool:
        return not self.unverified_evidence and not self.unverified_competitors

    def to_dict(self) -> dict:
        data = asdict(self)
        data["unverified_evidence"] = self.unverified_evidence
        data["unverified_competitors"] = self.unverified_competitors
        data["ok"] = self.ok
        return data


def check_grounding(
    evidence: list[str],
    competitors: list[str],
    website_text: str,
    searches: list[dict],
    search_results_available: bool = True,
) -> GroundingReport:
    """Look up each quote in the website text and each competitor in the sources."""
    site = normalize(website_text)
    report = GroundingReport(competitors_verifiable=search_results_available)

    for quote in evidence:
        report.evidence.append(Check(quote, normalize(quote) in site, "website"))

    # Every search result as (url, normalized text), searched in order.
    result_texts = [
        (r.get("url", ""), normalize(f"{r.get('title', '')} {r.get('content', '')}"))
        for s in searches
        for r in s.get("results", [])
    ]

    for name in competitors:
        needle = normalize(name)
        where = "website" if needle in site else ""
        if not where:
            where = next((url for url, text in result_texts if needle in text), "")
        report.competitors.append(Check(name, bool(where), where))

    return report
