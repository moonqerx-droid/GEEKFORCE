"""Answer a question with the sentences of a document that actually answer it.

A company document fragment often holds several rules: «Суточные — 700 ₽… Авансовый
отчёт сдаётся в течение трёх дней…». Asked «Когда сдавать авансовый отчёт?», the
employee needs the second sentence, not the whole fragment. The full fragment stays
the citation; the answer is the part that matches the question.

Matching is lexical on dictionary forms with a shared-stem fallback («менять» ≈
«меняется», «сдавать» ≈ «сдаётся»), so it is deterministic and needs no model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .understanding import morph

_WORD = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")
_HEADING = re.compile(r"^#{1,6}\s+")
# Question words, particles and fillers: «какие требования к паролю» → «требование пароль».
_FUNCTION = frozenset(
    "а и или но же ли бы не ни то это как какой каков что где когда куда откуда кто сколько "
    "почему зачем чем чего кому к в во на по о об от до для за из с со у при про над под "
    "мне меня мой моя мои наш наша свой нужно надо можно должный быть есть вообще сейчас "
    "подсказать сказать скажи подскажи пожалуйста такой весь всё все раз".split()
)
STEM = 5
# Share of the question's meaningful words a sentence must cover to count as an answer.
MIN_COVERAGE = 0.5


@dataclass(frozen=True)
class Focus:
    text: str          # the sentences to answer with
    coverage: float    # 0..1, how much of the question they cover


# Everyday spellings of the same thing.
_SAME = {"впн": "vpn", "впэн": "vpn", "вайфай": "wifi", "wi": "wifi", "аутлук": "outlook",
         "комп": "компьютер", "ноут": "ноутбук", "учетка": "учетный", "инет": "интернет"}


def content_words(text: str) -> list[str]:
    words = [_SAME.get(word, word) for word in (
        morph.lemma(raw.lower().replace("ё", "е")) for raw in _WORD.findall(text.replace("wi-fi", "wifi"))
    )]
    return list(dict.fromkeys(word for word in words if word not in _FUNCTION and len(word) > 1))


def _matches(word: str, pool: set[str], stems: set[str]) -> bool:
    return word in pool or (len(word) >= STEM and word[:STEM] in stems)


def sentences(text: str) -> list[str]:
    # Markdown headings name a section; they are never the answer.
    lines = [line.strip() for line in text.strip().splitlines() if not _HEADING.match(line.strip())]
    parts: list[str] = []
    for line in lines:
        parts += [part.strip() for part in _SENTENCE_END.split(line) if part.strip()]
    # A bare heading («Пароли») is not an answer on its own.
    return [part for part in parts if len(part.split()) > 3 or re.search(r"[.!?]$", part)]


def focus(question: str, text: str, title: str = "", limit: int = 2) -> Focus | None:
    """The sentences of `text` that answer `question`, or None if none covers it enough.

    Words of the document title count towards relevance («что сказано в «Правилах паролей»
    про …»), but the sentences are chosen by what they themselves say.
    """
    asked = content_words(question)
    if not asked:
        return None
    heading = set(content_words(title))
    scored = []
    for index, sentence in enumerate(sentences(text)):
        pool = set(content_words(sentence))
        stems = {word[:STEM] for word in pool if len(word) >= STEM}
        own = sum(_matches(word, pool, stems) for word in asked)
        pool |= heading
        stems |= {word[:STEM] for word in heading if len(word) >= STEM}
        total = sum(_matches(word, pool, stems) for word in asked)
        scored.append((own / len(asked), total / len(asked), index, sentence))
    if not scored:
        return None
    best_total = max(item[1] for item in scored)
    if best_total < MIN_COVERAGE:
        return None
    best_own = max(item[0] for item in scored)
    ranked = sorted((item for item in scored if item[0] >= best_own * 0.8), reverse=True)[:limit]
    chosen = sorted(ranked, key=lambda item: item[2])
    return Focus(" ".join(item[3] for item in chosen), round(best_total, 2))
