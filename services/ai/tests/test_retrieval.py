from __future__ import annotations

from pathlib import Path

import pytest

from helpflow_ai.knowledge import KnowledgeBase, KnowledgeBaseError
from helpflow_ai.retrieval import KnowledgeRetriever
from helpflow_ai.schemas import KnowledgeChunk


def test_vpn_query_returns_only_approved_chunks(kb):
    matches = KnowledgeRetriever(kb.chunks).search(
        "VPN пишет authentication failed", "vpn_connection"
    )

    assert matches
    assert matches[0].chunk.service == "VPN"
    assert all(match.chunk.id for match in matches)
    assert all(0.0 <= match.score <= 1.0 for match in matches)


def test_empty_and_unrelated_query_returns_no_confident_match(kb):
    retriever = KnowledgeRetriever(kb.chunks)

    assert retriever.search("", None) == []
    assert retriever.search("как приготовить борщ", "unknown") == []


def test_limit_and_ids_are_deterministic(kb):
    retriever = KnowledgeRetriever(kb.chunks)

    first = retriever.search("не подключается VPN", "vpn_connection", limit=3)
    second = retriever.search("не подключается VPN", "vpn_connection", limit=3)

    assert [match.chunk.id for match in first] == [match.chunk.id for match in second]
    assert len(first) <= 3


def test_exact_title_and_phrase_outrank_noisy_token_overlap():
    chunks = [
        KnowledgeChunk(
            id="noise",
            service="Browser",
            title="Общие проблемы браузера",
            text="кэш браузера ошибка очистить данные обновить страницу браузера",
            keywords=["браузер", "кэш", "ошибка"],
            escalation_team="Service Desk L1",
        ),
        KnowledgeChunk(
            id="exact",
            service="Browser",
            title="Как очистить кэш браузера",
            text="Откройте настройки и очистите кэш браузера.",
            keywords=["очистить кэш браузера"],
            escalation_team="Service Desk L1",
        ),
    ]

    matches = KnowledgeRetriever(chunks).search("как очистить кэш браузера", None)

    assert [match.chunk.id for match in matches][:2] == ["exact", "noise"]


def test_title_match_beats_same_overlap_in_body():
    chunks = [
        KnowledgeChunk(
            id="body",
            service="VPN",
            title="Сетевая инструкция",
            text="VPN authentication failed",
            escalation_team="Service Desk L1",
        ),
        KnowledgeChunk(
            id="title",
            service="VPN",
            title="VPN authentication failed",
            text="Проверьте подключение.",
            escalation_team="Service Desk L1",
        ),
    ]

    assert KnowledgeRetriever(chunks).search("VPN authentication failed", None)[0].chunk.id == "title"


def test_duplicate_article_ids_fail_closed(tmp_path: Path):
    _write_minimal_playbook(tmp_path)
    articles = tmp_path / "articles"
    articles.mkdir()
    articles.joinpath("duplicates.yaml").write_text(
        """
- id: duplicate.entry
  service: VPN
  title: First
  text: First approved answer
  escalation_team: Service Desk L1
- id: duplicate.entry
  service: VPN
  title: Second
  text: Second approved answer
  escalation_team: Service Desk L1
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(KnowledgeBaseError, match="Duplicate chunk ids"):
        KnowledgeBase.load(tmp_path)


def test_malformed_article_file_is_rejected(tmp_path: Path):
    _write_minimal_playbook(tmp_path)
    articles = tmp_path / "articles"
    articles.mkdir()
    articles.joinpath("malformed.yaml").write_text(
        "id: article-must-be-a-list", encoding="utf-8"
    )

    with pytest.raises(KnowledgeBaseError, match="Invalid article"):
        KnowledgeBase.load(tmp_path)


def _write_minimal_playbook(root: Path) -> None:
    playbooks = root / "playbooks"
    playbooks.mkdir()
    playbooks.joinpath("unknown.yaml").write_text(
        """
id: unknown
title: Unknown issue
service: Unknown
keywords: []
escalation_team: Service Desk L1
""".strip(),
        encoding="utf-8",
    )
