"""Grounding checks: is every claim backed by the text we actually gave the model?

"Grounded" means: the answer can be traced to a source. The model was told
not to invent anything, but telling is not checking. Here plain Python code
(no AI, no cost) looks for each quote and each name in the sources:

  evidence quotes  -> must appear in the website text
  competitor names -> must appear in the website or the search results
  customer names   -> must appear in the website or the search results

Every item gets one of three statuses:
  exact   : found word for word (after normalize())
  close   : most words found in the same order - the model changed a word or two
  missing : not found - check it by hand, it may be invented
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher

# Quote marks the model sometimes wraps around evidence: " ' “ ” ‘ ’ « » „
QUOTE_CHARS = "\"'“”‘’«»„`"

# Arabic short vowels (harakat), tanween, shadda, sukun, dagger alef.
ARABIC_MARKS = re.compile(r"[ً-ْٰ]")
TATWEEL = "ـ"

# A quote counts as "close" when at least this share of its words match the
# website in order, and one unbroken run covers at least half of it.
CLOSE_SHARE = 0.8


def strip_quotes(text: str) -> str:
    """Remove quote marks around a quote: '"لحظة بلحظة"' -> 'لحظة بلحظة'."""
    return text.strip().strip(QUOTE_CHARS).strip()


def normalize(text: str) -> str:
    """Make two texts comparable despite small, meaningless differences.

    - Unicode NFKC (e.g. full-width letters -> normal letters), lower case
    - Arabic: drop harakat and tatweel, unify alef forms, alef maqsura -> yeh
      so "نموًا" and "نمواً" and "نموا" all match
    - every punctuation mark (. , ، ؛ ! ؟ quotes ...) becomes a space:
      website cards often have no final period, the model often adds one
    - all whitespace collapsed to one space
    """
    text = unicodedata.normalize("NFKC", text).lower()
    text = ARABIC_MARKS.sub("", text).replace(TATWEEL, "")
    text = re.sub("[أإآ]", "ا", text)  # أ إ آ -> ا
    text = text.replace("ى", "ي")  # ى -> ي
    text = "".join(" " if unicodedata.category(ch).startswith("P") else ch for ch in text)
    return re.sub(r"\s+", " ", text).strip()


def word_match_share(quote: str, source: str) -> tuple[float, float]:
    """How much of the quote appears in the source, word by word, in order.

    Returns (share of quote words matched, share covered by the longest
    unbroken run). Both between 0 and 1. Inputs must be normalized.
    """
    q, s = quote.split(), source.split()
    if not q:
        return 0.0, 0.0
    # autojunk=False: otherwise frequent words in a long page are ignored.
    matcher = SequenceMatcher(None, q, s, autojunk=False)
    blocks = matcher.get_matching_blocks()
    matched = sum(b.size for b in blocks)
    longest = max((b.size for b in blocks), default=0)
    return matched / len(q), longest / len(q)


@dataclass
class Check:
    text: str
    status: str          # "exact" | "close" | "missing"
    where: str = ""      # "website" or a search result URL
    score: float = 1.0   # share of words matched (evidence only)

    @property
    def found(self) -> bool:
        return self.status != "missing"


@dataclass
class GroundingReport:
    evidence: list[Check] = field(default_factory=list)
    competitors: list[Check] = field(default_factory=list)
    customers: list[Check] = field(default_factory=list)
    names_verifiable: bool = True  # False when search result texts are not available

    @property
    def unverified_evidence(self) -> list[str]:
        return [c.text for c in self.evidence if c.status == "missing"]

    @property
    def close_evidence(self) -> list[str]:
        return [c.text for c in self.evidence if c.status == "close"]

    @property
    def unverified_competitors(self) -> list[str]:
        return [c.text for c in self.competitors if not c.found] if self.names_verifiable else []

    @property
    def unverified_customers(self) -> list[str]:
        return [c.text for c in self.customers if not c.found] if self.names_verifiable else []

    @property
    def ok(self) -> bool:
        return not (self.unverified_evidence or self.unverified_competitors or self.unverified_customers)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["unverified_evidence"] = self.unverified_evidence
        data["close_evidence"] = self.close_evidence
        data["unverified_competitors"] = self.unverified_competitors
        data["unverified_customers"] = self.unverified_customers
        data["ok"] = self.ok
        return data


def _check_quote(quote: str, site: str) -> Check:
    needle = normalize(quote)
    if needle and needle in site:
        return Check(quote, "exact", "website", 1.0)
    share, longest = word_match_share(needle, site)
    status = "close" if share >= CLOSE_SHARE and longest >= 0.5 else "missing"
    return Check(quote, status, "website" if status == "close" else "", round(share, 2))


def _check_name(name: str, site: str, result_texts: list[tuple[str, str]]) -> Check:
    needle = normalize(name)
    if needle and needle in site:
        return Check(name, "exact", "website")
    url = next((u for u, text in result_texts if needle and needle in text), "")
    return Check(name, "exact" if url else "missing", url)


def check_grounding(
    evidence: list[str],
    competitors: list[str],
    website_text: str,
    searches: list[dict],
    search_results_available: bool = True,
    customers: list[str] | None = None,
) -> GroundingReport:
    """Look up each quote in the website text and each name in all sources."""
    site = normalize(website_text)
    result_texts = [
        (r.get("url", ""), normalize(f"{r.get('title', '')} {r.get('content', '')}"))
        for s in searches
        for r in s.get("results", [])
    ]

    return GroundingReport(
        evidence=[_check_quote(q, site) for q in evidence],
        competitors=[_check_name(n, site, result_texts) for n in competitors],
        customers=[_check_name(n, site, result_texts) for n in (customers or [])],
        names_verifiable=search_results_available,
    )
