"""Tests for step 1. No API key, no network: a fake client and fixed HTML.

Run:  pytest -v
"""
import base64
from types import SimpleNamespace

import pytest
from openai.lib._pydantic import to_strict_json_schema

import config
from agents import researcher
from core.schemas import CompanyProfile
from core.web import normalize_url, parse_html

SAMPLE_HTML = """
<html><head>
  <title>Acme Logistics | Fleet tracking</title>
  <meta name="description" content="Real-time fleet tracking for delivery companies.">
  <style>.x{color:red}</style>
  <script>var tracking = "should not appear";</script>
</head><body>
  <h1>Track every truck</h1>
  <h2>حلول تتبع الأساطيل</h2>
  <p>Acme helps delivery companies cut fuel costs by 20%.</p>
  <noscript>enable js</noscript>
</body></html>
"""


def sample_profile():
    return CompanyProfile(
        name="Acme Logistics",
        website="https://acme.example",
        one_liner="Fleet tracking software for delivery companies.",
        offering=["Fleet tracking"],
        value_props=["Lower fuel costs"],
        target_customers=["Delivery companies"],
        competitors=[],
        language="mixed",
        evidence=["cut fuel costs by 20%"],
        confidence="medium",
    )


class FakeClient:
    def __init__(self):
        self.calls = []
        self.responses = SimpleNamespace(parse=self._parse, create=None)

    def _parse(self, **params):
        self.calls.append(params)
        usage = SimpleNamespace(input_tokens=900, output_tokens=150,
                                input_tokens_details=SimpleNamespace(cached_tokens=0))
        return SimpleNamespace(id="resp_1", output_parsed=sample_profile(),
                               status="completed", usage=usage)


@pytest.fixture(autouse=True)
def tmp_log(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_FILE", str(tmp_path / "calls.jsonl"))


# --- core/web.py -----------------------------------------------------------

def test_parse_html_keeps_content_and_drops_scripts():
    page = parse_html(SAMPLE_HTML, "https://acme.example")

    assert page.title == "Acme Logistics | Fleet tracking"
    assert page.description == "Real-time fleet tracking for delivery companies."
    assert page.headings == ["Track every truck", "حلول تتبع الأساطيل"]
    assert "cut fuel costs by 20%" in page.text
    assert "should not appear" not in page.text
    assert "color:red" not in page.text
    assert "enable js" not in page.text


def test_parse_html_truncates_long_pages():
    html = "<p>" + "word " * 5000 + "</p>"
    page = parse_html(html, "https://x.example", max_chars=1000)
    assert len(page.text) == 1000
    assert page.truncated
    assert "cut at" in page.as_prompt()


def test_normalize_url_adds_https():
    assert normalize_url(" acme.com ") == "https://acme.com"
    assert normalize_url("http://acme.com") == "http://acme.com"


# --- agents/researcher.py --------------------------------------------------

def test_analyze_sends_structured_request():
    fake = FakeClient()
    page = parse_html(SAMPLE_HTML, "https://acme.example")

    profile, _ = researcher.analyze_company("https://acme.example", page=page, client=fake)

    assert profile.name == "Acme Logistics"
    [call] = fake.calls
    assert call["text_format"] is CompanyProfile
    assert call["model"] == config.model_for("smart")
    assert "tools" not in call
    [message] = call["input"]
    assert message["role"] == "user"
    assert message["content"][0]["type"] == "input_text"
    assert "Track every truck" in message["content"][0]["text"]


def test_screenshot_becomes_base64_image_part(tmp_path):
    png = tmp_path / "home.png"
    png.write_bytes(b"\x89PNG fake bytes")
    page = parse_html(SAMPLE_HTML, "https://acme.example")

    content = researcher.build_input(page, png)[0]["content"]

    image = content[-1]
    assert image["type"] == "input_image"
    assert image["image_url"].startswith("data:image/png;base64,")
    encoded = image["image_url"].split(",", 1)[1]
    assert base64.b64decode(encoded) == b"\x89PNG fake bytes"


def test_web_search_adds_tool_on_openai(monkeypatch):
    monkeypatch.setattr(config, "IS_AZURE", False)
    fake = FakeClient()
    page = parse_html(SAMPLE_HTML, "https://acme.example")

    researcher.analyze_company("x", page=page, client=fake, use_web_search=True)

    assert fake.calls[0]["tools"] == [{"type": "web_search"}]
    assert "web_search tool" in fake.calls[0]["instructions"]


def test_web_search_refused_on_azure(monkeypatch):
    monkeypatch.setattr(config, "IS_AZURE", True)
    with pytest.raises(ValueError, match="not available on Azure"):
        researcher.analyze_company("x", page=None, client=FakeClient(), use_web_search=True)


def test_missing_parsed_output_raises():
    fake = FakeClient()
    fake.responses.parse = lambda **p: SimpleNamespace(
        id="r", output_parsed=None, status="incomplete",
        usage=SimpleNamespace(input_tokens=1, output_tokens=1, input_tokens_details=None))
    page = parse_html(SAMPLE_HTML, "https://acme.example")

    with pytest.raises(RuntimeError, match="incomplete"):
        researcher.analyze_company("x", page=page, client=fake)


# --- core/schemas.py -------------------------------------------------------

def test_schema_is_valid_for_strict_structured_outputs():
    """The SDK converts the Pydantic model to a strict JSON schema. Strict mode
    requires every property to be listed in 'required' and no extra keys."""
    schema = to_strict_json_schema(CompanyProfile)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["properties"]["confidence"]["enum"] == ["high", "medium", "low"]
