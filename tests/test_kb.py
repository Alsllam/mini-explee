"""Tests for core/kb.py (crawl, chunk, embed, search) and core/moderation.py.
No API, no network: fake HTTP responses, fake embeddings, fake clients.

Run:  pytest -v
"""
from types import SimpleNamespace

import numpy as np
import openai
import pytest

import config
from core import kb, moderation
from core.web import parse_html

HOME = """<html><head><title>Acme</title></head><body>
<a href="/solutions/banking">Banking</a>
<a href="/about">About</a>
<a href="/blog/page/2">Old posts</a>
<a href="/login">Login</a>
<a href="https://other-site.example/x">Elsewhere</a>
<a href="/solutions/retail#top">Retail</a>
<a href="/contact">Contact</a>
<p>Acme helps banks listen to customers.</p></body></html>"""


def fake_get(robots="User-agent: *\nDisallow: /private", html=HOME):
    def get(url, headers=None, timeout=None):
        if url.endswith("/robots.txt"):
            return SimpleNamespace(status_code=200, text=robots)
        return SimpleNamespace(status_code=200, text=html, apparent_encoding="utf-8", encoding="utf-8",
                               raise_for_status=lambda: None)
    return get


# --- crawl ------------------------------------------------------------------

def test_pick_links_same_site_useful_first_no_junk():
    links = kb.pick_links(HOME, "https://acme.example", limit=10)
    assert links[0].endswith("/solutions/banking") or links[0].endswith("/solutions/retail")
    assert all(link.startswith("https://acme.example/") for link in links)
    assert not any("login" in link or "blog/page" in link or "#" in link for link in links)
    assert links.index("https://acme.example/about") < links.index("https://acme.example/contact")


def test_robots_txt_is_respected():
    get = fake_get()
    assert kb.robots_allows("https://acme.example/solutions", get)
    assert not kb.robots_allows("https://acme.example/private/x", get)


def test_crawl_reuses_home_page_and_follows_best_links():
    fetched = []

    def fetch(url):
        fetched.append(url)
        return parse_html(f"<title>{url}</title><p>text of {url}</p>", url)

    pages = kb.crawl("acme.example", max_pages=3, delay=0, fetch=fetch, get=fake_get())
    assert len(pages) == 3
    assert pages[0].title == "Acme"              # home page parsed from the first download
    assert "https://acme.example" not in fetched  # ...not downloaded twice
    assert all("solutions" in url for url in fetched)


def test_crawl_refuses_when_robots_disallows_everything():
    with pytest.raises(PermissionError):
        kb.crawl("acme.example", get=fake_get(robots="User-agent: *\nDisallow: /"), delay=0)


# --- chunk ------------------------------------------------------------------

def test_chunks_overlap_and_end_on_word_boundaries():
    text = " ".join(f"word{i}" for i in range(600))
    pieces = kb.chunk_text(text, size=200, overlap=50)
    assert len(pieces) > 5
    assert all(len(p) <= 200 for p in pieces)
    assert all(not p.endswith("wor") for p in pieces)            # no word cut in half
    assert pieces[0].split()[-1] in pieces[1]                    # overlap carries words over


def test_chunk_page_ids_and_headings_first():
    page = parse_html("<title>T</title><h1>Banks</h1><p>" + "x " * 50 + "</p>", "https://a.example")
    chunks = kb.chunk_page(page, 2)
    assert chunks[0].id == "p2-c0" and chunks[0].url == "https://a.example"
    assert chunks[0].text.startswith("T")


# --- embed / search -----------------------------------------------------------

class FakeEmbeddings:
    """Deterministic 3-d vectors from keywords, so similarity is predictable."""

    def __init__(self):
        self.calls = []
        self.embeddings = SimpleNamespace(create=self._create)

    @staticmethod
    def vector(text):
        t = text.lower()
        return [t.count("bank") + 0.01, t.count("retail") + 0.01, t.count("government") + 0.01]

    def _create(self, model, input):
        self.calls.append((model, list(input)))
        return SimpleNamespace(data=[SimpleNamespace(embedding=self.vector(t)) for t in input])


def test_embed_batches_and_normalizes(monkeypatch):
    monkeypatch.setattr(kb, "EMBED_BATCH", 2)
    fake = FakeEmbeddings()
    vectors = kb.embed(["bank bank", "retail", "government"], client=fake)
    assert len(fake.calls) == 2 and fake.calls[0][0] == config.MODEL_EMBED
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0)


def test_search_returns_closest_meaning_first(tmp_path, monkeypatch):
    monkeypatch.setattr(kb, "KB_DIR", tmp_path)
    fake = FakeEmbeddings()
    chunks = [kb.Chunk("p0-c0", "u", "t", "We help retail chains"),
              kb.Chunk("p1-c0", "u", "t", "Banking: banks trust us"),
              kb.Chunk("p2-c0", "u", "t", "Government agencies")]
    kb.save("acme.example", chunks, kb.embed([c.text for c in chunks], client=fake))

    base = kb.KnowledgeBase.load("acme.example")
    results = base.search("bank customer experience", k=2, client=fake)
    assert results[0][0].id == "p1-c0"
    assert results[0][1] > results[1][1]


def test_missing_kb_says_how_to_build_it(tmp_path, monkeypatch):
    monkeypatch.setattr(kb, "KB_DIR", tmp_path)
    with pytest.raises(FileNotFoundError, match="build_kb"):
        kb.KnowledgeBase.load("nothing.example")


# --- moderation ----------------------------------------------------------------

def make_bad_request(code):
    err = openai.BadRequestError.__new__(openai.BadRequestError)
    Exception.__init__(err, "bad request")
    err.code, err.message = code, "bad request"
    return err


@pytest.fixture
def log(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_FILE", str(tmp_path / "calls.jsonl"))


def test_openai_moderation_lists_flagged_categories(monkeypatch):
    monkeypatch.setattr(config, "IS_AZURE", False)
    cats = SimpleNamespace(model_dump=lambda: {"harassment": True, "violence": False})
    fake = SimpleNamespace(moderations=SimpleNamespace(
        create=lambda model, input: SimpleNamespace(results=[SimpleNamespace(flagged=True, categories=cats)])))
    result = moderation.moderate("some text", client=fake)
    assert result.flagged and result.categories == ["harassment"] and result.provider == "openai-moderations"


def test_azure_content_filter_block_means_flagged(monkeypatch, log):
    monkeypatch.setattr(config, "IS_AZURE", True)

    def create(**params):
        raise make_bad_request("content_filter")

    result = moderation.moderate("bad text", client=SimpleNamespace(responses=SimpleNamespace(create=create)))
    assert result.flagged and result.provider == "azure-content-filter"


def test_azure_clean_text_passes_and_other_errors_raise(monkeypatch, log):
    monkeypatch.setattr(config, "IS_AZURE", True)
    usage = SimpleNamespace(input_tokens=5, output_tokens=1, input_tokens_details=None, output_tokens_details=None)
    ok = SimpleNamespace(responses=SimpleNamespace(create=lambda **p: SimpleNamespace(id="r", usage=usage)))
    assert not moderation.moderate("hello", client=ok).flagged

    def create(**params):
        raise make_bad_request("invalid_value")

    with pytest.raises(openai.BadRequestError):
        moderation.moderate("hello", client=SimpleNamespace(responses=SimpleNamespace(create=create)))
