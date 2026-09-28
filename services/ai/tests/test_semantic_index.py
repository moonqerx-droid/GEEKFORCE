"""The meaning layer recovers on its own when Ollama was slow or down."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from helpflow_ai.understanding import semantic
from helpflow_ai.understanding.semantic import LOAD_TIMEOUT_SECONDS, SemanticIndex

PLAYBOOKS = [SimpleNamespace(id="printer", title="Принтер", examples=["не печатает"]),
             SimpleNamespace(id="vpn_connection", title="VPN", examples=["впн не подключается"])]


class FlakyEmbedder:
    """Fails the first `failures` calls, like Ollama while it loads the model."""

    name = "fake"

    def __init__(self, failures: int = 0):
        self.failures = failures
        self.timeouts: list[float | None] = []

    def embed(self, texts, timeout=None):
        self.timeouts.append(timeout)
        if self.failures:
            self.failures -= 1
            raise TimeoutError("model is loading")
        return [[1.0, 0.0] if "печат" in text.lower() or "принтер" in text.lower() else [0.0, 1.0]
                for text in texts]


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(semantic, "RETRY_AFTER_SECONDS", 0.0)


def _index(embedder, tmp_path):
    return SemanticIndex(embedder, PLAYBOOKS, cache_dir=tmp_path, background=False)


def test_an_index_that_failed_at_start_is_built_later(tmp_path):
    index = _index(FlakyEmbedder(failures=1), tmp_path)
    assert not index.ready
    assert index.rank("принтер не печатает") is None  # this call starts the rebuild
    assert index.ready
    assert index.rank("принтер не печатает")[0][0] == "printer"


def test_building_waits_for_the_model_to_load_but_a_query_does_not(tmp_path):
    embedder = FlakyEmbedder()
    index = _index(embedder, tmp_path)
    index.rank("впн не подключается")
    assert embedder.timeouts[0] == LOAD_TIMEOUT_SECONDS
    assert embedder.timeouts[-1] is None


def test_after_a_failed_query_the_model_is_warmed_up_again(tmp_path):
    embedder = FlakyEmbedder()
    index = _index(embedder, tmp_path)
    embedder.failures = 1
    assert index.rank("впн не подключается") is None  # the model was unloaded
    assert index.rank("впн не подключается") is None  # warm-up with the long timeout
    assert embedder.timeouts[-1] == LOAD_TIMEOUT_SECONDS
    assert index.rank("впн не подключается")[0][0] == "vpn_connection"
