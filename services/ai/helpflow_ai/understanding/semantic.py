"""Meaning-based matching of a request to playbooks, with a local embedding model.

Keywords miss «комп жутко тупит» or «скинь пароль от админки»; an embedding model
(bge-m3 through Ollama, free and offline) places them next to the playbook examples
that mean the same thing. The index of examples is built once in the background and
cached on disk; until it is ready, and whenever Ollama is unavailable, `rank` returns
None and the engine keeps to its rules.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import threading
import time
from pathlib import Path
from typing import Iterable, Protocol

import httpx

logger = logging.getLogger(__name__)

DEFAULT_EMBED_MODEL = "bge-m3"
# After a failed call, stay on rules for a while instead of slowing every request.
RETRY_AFTER_SECONDS = 60.0


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OllamaEmbedder:
    def __init__(self, base_url: str, model: str = DEFAULT_EMBED_MODEL, timeout: float = 5.0,
                 keep_alive: str = "30m"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.name = f"ollama:{model}"
        self.timeout = timeout
        self.keep_alive = keep_alive

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = httpx.post(
            f"{self.base_url}/api/embed",
            json={"model": self.model, "input": texts, "keep_alive": self.keep_alive},
            timeout=httpx.Timeout(max(self.timeout, 10.0 * math.ceil(len(texts) / 20)), connect=2.0),
        )
        response.raise_for_status()
        vectors = response.json()["embeddings"]
        if len(vectors) != len(texts):
            raise ValueError("embedding count mismatch")
        return vectors


def _unit(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class SemanticIndex:
    """Playbook examples as vectors; `rank(text)` gives playbooks by closeness in meaning."""

    def __init__(self, embedder: Embedder, playbooks: Iterable, cache_dir: Path | None = None,
                 background: bool = True):
        self.embedder = embedder
        self._entries = [
            (playbook.id, text)
            for playbook in playbooks if playbook.id != "unknown"
            for text in [playbook.title, *playbook.examples]
        ]
        self._vectors: list[list[float]] | None = None
        self._failed_at: float | None = None
        self._lock = threading.Lock()
        self._cache_file = (cache_dir or _default_cache_dir()) / f"embeddings-{_slug(embedder.name)}.json"
        if background:
            threading.Thread(target=self._build, name="semantic-index", daemon=True).start()
        else:
            self._build()

    @property
    def ready(self) -> bool:
        return self._vectors is not None

    def rank(self, text: str) -> list[tuple[str, float]] | None:
        """Playbooks with the similarity of their closest example, best first; None if unavailable."""
        if self._vectors is None or not self._healthy():
            return None
        try:
            query = _unit(self.embedder.embed([text])[0])
        except Exception as error:  # noqa: BLE001 - any failure means «use the rules»
            self._fail(error)
            return None
        best: dict[str, float] = {}
        for (playbook_id, _), vector in zip(self._entries, self._vectors):
            score = _dot(query, vector)
            if score > best.get(playbook_id, -1.0):
                best[playbook_id] = score
        return sorted(best.items(), key=lambda item: item[1], reverse=True)

    # --- internals ----------------------------------------------------------

    def _healthy(self) -> bool:
        return self._failed_at is None or time.monotonic() - self._failed_at > RETRY_AFTER_SECONDS

    def _fail(self, error: Exception) -> None:
        self._failed_at = time.monotonic()
        logger.warning("semantic.unavailable model=%s error=%s", self.embedder.name, type(error).__name__)

    def _build(self) -> None:
        with self._lock:
            texts = [text for _, text in self._entries]
            cache = self._read_cache()
            missing = [text for text in dict.fromkeys(texts) if _key(text) not in cache]
            try:
                for start in range(0, len(missing), 32):
                    chunk = missing[start:start + 32]
                    for text, vector in zip(chunk, self.embedder.embed(chunk)):
                        cache[_key(text)] = _unit(vector)
            except Exception as error:  # noqa: BLE001
                self._fail(error)
                return
            if missing:
                self._write_cache(cache)
            self._vectors = [cache[_key(text)] for text in texts]
            self._failed_at = None
            logger.info("semantic.ready examples=%s embedded=%s", len(texts), len(missing))

    def _read_cache(self) -> dict[str, list[float]]:
        try:
            return json.loads(self._cache_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _write_cache(self, cache: dict[str, list[float]]) -> None:
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            self._cache_file.write_text(json.dumps(cache), encoding="utf-8")
        except OSError as error:
            logger.warning("semantic.cache_not_saved error=%s", error)


def _key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _slug(name: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in name)


def _default_cache_dir() -> Path:
    return Path(os.getenv("HELPFLOW_CACHE_DIR", Path.home() / ".cache" / "helpflow"))


def from_env(playbooks: Iterable) -> SemanticIndex | None:
    """On by default with a local Ollama; SEMANTIC_MATCHING=off disables it."""
    mode = os.getenv("SEMANTIC_MATCHING", "auto").strip().lower()
    provider = os.getenv("AI_PROVIDER", "mock").strip().lower()
    if mode == "off" or (mode == "auto" and provider != "ollama"):
        return None
    embedder = OllamaEmbedder(
        os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        os.getenv("OLLAMA_EMBED_MODEL", DEFAULT_EMBED_MODEL),
        timeout=float(os.getenv("SEMANTIC_TIMEOUT_SECONDS", "3")),
    )
    return SemanticIndex(embedder, playbooks)
