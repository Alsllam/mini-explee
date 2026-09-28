"""Tests for core/grounding.py and the --strict option. No API, no network.

Run:  pytest -v
"""
from types import SimpleNamespace

import pytest

import config
from agents import researcher
from core.grounding import check_grounding, normalize, strip_quotes
from core.web import parse_html
from tests.test_researcher import SAMPLE_HTML, sample_profile

SITE = "المنصة الذكية لتجربة العملاء في العالم العربي. مزوّد حلول وكيل الذكاء الإصطناعي الأسرع نموًا"

SEARCHES = [{"query": "lucidya competitors", "results": [
    {"title": "Top Lucidya alternatives", "url": "https://cbinsights.example/lucidya",
     "content": "Competitors include Brandwatch, Sprinklr and Crowd Analyzer."},
]}]


# --- normalize / strip_quotes ---------------------------------------------

def test_strip_quotes_removes_wrapping_marks_only():
    assert strip_quotes('"لحظة بلحظة"') == "لحظة بلحظة"
    assert strip_quotes("«نص» ") == "نص"
    assert strip_quotes('He said "hi" today') == 'He said "hi" today'


def test_normalize_ignores_arabic_diacritics_and_alef_forms():
    # tanween on a different letter, hamza forms, tatweel, extra spaces
    assert normalize("الأسرع نمواً") == normalize("الاسرع  نموًا")
    assert normalize("إصطـناعي") == normalize("اصطناعي")
    assert normalize("Brandwatch") == normalize("BRANDWATCH")


# --- check_grounding -------------------------------------------------------

def test_evidence_found_despite_small_differences():
    report = check_grounding(
        evidence=["مزوّد حلول وكيل الذكاء الإصطناعي الأسرع نمواً"],  # tanween moved
        competitors=[], website_text=SITE, searches=[])
    assert report.evidence[0].found
    assert report.ok


def test_invented_evidence_is_flagged():
    report = check_grounding(
        evidence=["نخدم أكثر من 500 بنك حول العالم"], competitors=[],
        website_text=SITE, searches=[])
    assert report.unverified_evidence == ["نخدم أكثر من 500 بنك حول العالم"]
    assert not report.ok


def test_competitors_checked_against_search_results_with_url():
    report = check_grounding(
        evidence=[], competitors=["Brandwatch", "Neticle"],
        website_text=SITE, searches=SEARCHES)

    found = {c.text: c for c in report.competitors}
    assert found["Brandwatch"].found
    assert found["Brandwatch"].where == "https://cbinsights.example/lucidya"
    assert not found["Neticle"].found
    assert report.unverified_competitors == ["Neticle"]


def test_competitors_unverifiable_without_result_texts():
    report = check_grounding(evidence=[], competitors=["Neticle"], website_text=SITE,
                             searches=[], search_results_available=False)
    assert report.unverified_competitors == []  # can't judge -> no false alarm
    assert not report.names_verifiable


def test_report_to_dict_has_summary_fields():
    report = check_grounding(["x y z w v"], ["Neticle"], SITE, SEARCHES)
    data = report.to_dict()
    assert data["ok"] is False
    assert data["unverified_competitors"] == ["Neticle"]
    assert data["evidence"][0]["status"] == "missing"


# --- --strict in the researcher -------------------------------------------

class FakeClient:
    def __init__(self, profile):
        self.profile = profile
        usage = SimpleNamespace(input_tokens=1, output_tokens=1,
                                input_tokens_details=SimpleNamespace(cached_tokens=0))
        self.responses = SimpleNamespace(parse=lambda **p: SimpleNamespace(
            id="r", output=[], output_parsed=self.profile, status="completed", usage=usage))


@pytest.fixture(autouse=True)
def tmp_log(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_FILE", str(tmp_path / "calls.jsonl"))


def make_profile():
    p = sample_profile()
    p.evidence = ["Acme helps delivery companies cut fuel costs by 20%.", "Invented quote here"]
    p.competitors = ["Rival Invented"]
    p.named_customers = ["Invented Bank"]
    return p


def test_default_keeps_items_but_flags_them():
    page = parse_html(SAMPLE_HTML, "https://acme.example")
    result = researcher.analyze_company("x", page=page, client=FakeClient(make_profile()))

    assert len(result.profile.evidence) == 2  # nothing removed
    assert result.grounding.unverified_evidence == ["Invented quote here"]
    assert result.grounding.unverified_competitors == ["Rival Invented"]
    assert result.grounding.unverified_customers == ["Invented Bank"]


def test_strict_drops_unverified_items():
    page = parse_html(SAMPLE_HTML, "https://acme.example")
    result = researcher.analyze_company("x", page=page, client=FakeClient(make_profile()), strict=True)

    assert result.profile.evidence == ["Acme helps delivery companies cut fuel costs by 20%."]
    assert result.profile.competitors == []
    assert result.profile.named_customers == []


def test_temperature_can_be_disabled_for_reasoning_models(monkeypatch):
    monkeypatch.setattr(researcher, "ANALYSIS_TEMPERATURE", None)
    calls = []
    fake = FakeClient(sample_profile())
    original = fake.responses.parse
    fake.responses.parse = lambda **p: (calls.append(p), original(**p))[1]
    page = parse_html(SAMPLE_HTML, "https://acme.example")

    researcher.analyze_company("x", page=page, client=fake)

    assert "temperature" not in calls[0]


# --- fixes after the first real run on lucidya.com -------------------------

SITE_CARDS = ("العميل الذكي قدّم دعمًا فوريًا ومخصصًا يعزز الرضا والكفاءة "
              "حلول تمكّن جميع فرقك بمختلف تخصصاتها من العمل بفعالية وسرعة "
              "رصد الإعلام تابع كل ما يُذكر")


def test_added_final_period_is_still_exact():
    """Website cards have no period; the model added one. Real case from lucidya.com."""
    report = check_grounding(["قدّم دعمًا فوريًا ومخصصًا يعزز الرضا والكفاءة."], [], SITE_CARDS, [])
    assert report.evidence[0].status == "exact"


def test_one_added_word_is_close_not_missing():
    """The model appended "وثقة" to a real sentence. Real case from lucidya.com."""
    report = check_grounding(
        ["حلول تمكّن جميع فرقك بمختلف تخصصاتها من العمل بفعالية وسرعة وثقة."], [], SITE_CARDS, [])
    check = report.evidence[0]
    assert check.status == "close"
    assert check.score >= 0.8
    assert report.unverified_evidence == []
    assert report.close_evidence == [check.text]


def test_sentence_of_common_words_in_wrong_order_is_missing():
    report = check_grounding(["العمل الذكي يعزز كل الحلول مع الإعلام"], [], SITE_CARDS, [])
    assert report.evidence[0].status == "missing"


def test_named_customers_checked_like_competitors():
    searches = [{"query": "lucidya clients", "results": [
        {"title": "Lucidya case study", "url": "https://news.example/sib",
         "content": "Saudi Investment Bank uses Lucidya to track sentiment."}]}]
    report = check_grounding([], [], SITE_CARDS, searches,
                             customers=["Saudi Investment Bank", "Invented Bank"])
    assert report.customers[0].where == "https://news.example/sib"
    assert report.unverified_customers == ["Invented Bank"]
