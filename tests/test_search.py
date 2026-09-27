"""Tests for the Tavily search tool and the function-calling loop (lesson 4.2).
No API keys, no network: fake HTTP session, fake search, fake model.

Run:  pytest -v
"""
import json
from types import SimpleNamespace

import pytest

import config
from agents import researcher
from core import search as search_mod
from core.web import parse_html
from tests.test_researcher import SAMPLE_HTML, sample_profile

USAGE = SimpleNamespace(input_tokens=10, output_tokens=5,
                        input_tokens_details=SimpleNamespace(cached_tokens=0))


@pytest.fixture(autouse=True)
def tmp_log(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_FILE", str(tmp_path / "calls.jsonl"))
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")


# --- core/search.py --------------------------------------------------------

class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.sent = None

    def post(self, url, headers, json, timeout):
        self.sent = {"url": url, "headers": headers, "json": json}
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: self.payload)


def test_search_web_sends_bearer_key_and_trims_content():
    session = FakeSession({"results": [
        {"title": " Rival A ", "url": "https://a.example", "content": "x" * 5000, "score": 0.9},
    ]})

    results = search_mod.search_web("acme competitors", session=session)

    assert session.sent["url"] == "https://api.tavily.com/search"
    assert session.sent["headers"]["Authorization"] == "Bearer tvly-test"
    assert session.sent["json"]["query"] == "acme competitors"
    assert session.sent["json"]["search_depth"] == "basic"
    assert results == [{"title": "Rival A", "url": "https://a.example",
                        "content": "x" * search_mod.MAX_CONTENT_CHARS}]


def test_search_web_without_key_fails_clearly(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY")
    with pytest.raises(RuntimeError, match="TAVILY_API_KEY"):
        search_mod.search_web("anything", session=FakeSession({}))


def test_format_results_numbers_sources():
    text = search_mod.format_results("q", [{"title": "T", "url": "https://u", "content": "C"}])
    assert '"q"' in text and "[1] T" in text and "URL: https://u" in text
    assert "No results" in search_mod.format_results("q", [])


# --- the loop in agents/researcher.py --------------------------------------

def function_call(query, call_id="call_1"):
    return SimpleNamespace(type="function_call", call_id=call_id, name="search_web",
                           arguments=json.dumps({"query": query}))


class ScriptedModel:
    """Replies in turn: each entry is a list of output items, or 'final'."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.responses = SimpleNamespace(parse=self._parse)

    def _parse(self, **params):
        self.calls.append(json.loads(json.dumps(params, default=str)))
        step = self.script.pop(0)
        if step == "final":
            return SimpleNamespace(id="r", output=[], output_parsed=sample_profile(),
                                   status="completed", usage=USAGE)
        return SimpleNamespace(id="r", output=step, output_parsed=None,
                               status="completed", usage=USAGE)


def test_loop_runs_search_and_sends_result_back():
    model = ScriptedModel([[function_call("acme competitors")], "final"])
    asked = []

    def fake_search(query):
        asked.append(query)
        return [{"title": "Rival A", "url": "https://a.example", "content": "Rival A tracks fleets"}]

    page = parse_html(SAMPLE_HTML, "https://acme.example")
    result = researcher.analyze_company(
        "x", page=page, client=model, web="tavily", search=fake_search)

    assert result.profile.name == "Acme Logistics"
    assert asked == ["acme competitors"]
    assert result.searches[0]["query"] == "acme competitors"

    first, second = model.calls
    assert first["tools"][0]["name"] == "search_web"
    assert first["tool_choice"] == "auto"
    # Round 2 carries the model's request and our result, linked by call_id.
    request, result = second["input"][-2:]
    assert request["type"] == "function_call" and request["call_id"] == "call_1"
    assert result["type"] == "function_call_output" and result["call_id"] == "call_1"
    assert "Rival A" in result["output"]


def test_loop_stops_searching_after_max_rounds(monkeypatch):
    monkeypatch.setattr(researcher, "MAX_SEARCH_ROUNDS", 2)
    script = [[function_call("q1")], [function_call("q2")], "final"]
    model = ScriptedModel(script)
    page = parse_html(SAMPLE_HTML, "https://acme.example")

    researcher.analyze_company("x", page=page, client=model, web="tavily", search=lambda q: [])

    assert [c["tool_choice"] for c in model.calls] == ["auto", "auto", "none"]


def test_search_error_is_reported_to_model_not_raised():
    model = ScriptedModel([[function_call("acme")], "final"])

    def broken_search(query):
        raise TimeoutError("tavily slow")

    page = parse_html(SAMPLE_HTML, "https://acme.example")
    result = researcher.analyze_company(
        "x", page=page, client=model, web="tavily", search=broken_search)

    assert result.profile is not None
    assert "Search failed: TimeoutError" in model.calls[1]["input"][-1]["output"]
