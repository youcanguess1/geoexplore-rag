"""Unit tests for the shared Chinese-aware tokenizer.

The jieba path is asserted loosely (jieba's segmentation is its own business);
the CJK-bigram fallback is asserted exactly, since it is our code.
"""

from __future__ import annotations

from app.retrieval import tokenizer as tokenizer_mod
from app.retrieval.tokenizer import tokenize


def test_tokenize_empty_input() -> None:
    assert tokenize("") == []
    assert tokenize("   ") == []


def test_tokenize_uses_jieba_when_installed() -> None:
    # jieba is a hard dependency, so the fallback should not be the live path.
    assert tokenizer_mod.jieba is not None
    tokens = tokenize("地震波速")
    assert tokens
    assert all(token.strip() for token in tokens)


def test_tokenize_fallback_splits_han_into_bigrams(monkeypatch) -> None:
    monkeypatch.setattr(tokenizer_mod, "jieba", None)
    assert tokenize("地震波速") == ["地震", "震波", "波速"]


def test_tokenize_fallback_keeps_lone_han_character(monkeypatch) -> None:
    monkeypatch.setattr(tokenizer_mod, "jieba", None)
    assert tokenize("震") == ["震"]


def test_tokenize_fallback_extracts_latin_words(monkeypatch) -> None:
    monkeypatch.setattr(tokenizer_mod, "jieba", None)
    tokens = tokenize("地震 seismic 2024")
    assert "seismic" in tokens
    assert "2024" in tokens


def test_tokenize_fallback_lowercases_latin(monkeypatch) -> None:
    monkeypatch.setattr(tokenizer_mod, "jieba", None)
    assert "rag" in tokenize("RAG")
