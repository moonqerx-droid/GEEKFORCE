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

from .understanding import morph

_WORD = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")
_HEADING = re.compile(r"^#{1,6}\s+")
# Question words, particles and fillers: «какие требования к паролю» → «требование пароль».
_FUNCTION = frozenset(
    "а и или но же ли бы не ни то это как какой каков что где когда куда откуда кто сколько "
    "почему зачем чем чего кому к в во на по о об от до для за из с со у при про над под "
    "мне меня мой моя мои наш наша свой нужно надо можно должный быть есть вообще сейчас "
    "подсказать сказать скажи подскажи пожалуйста такой весь всё все раз "
    "он она оно они его ее их это этот эта спасибо понятно ясно если тогда еще ещё".split()
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


# How a question names what a rule states: «какой длины» is answered by «не короче 10 символов».
_RELATED = {
    "длина": {"символ", "короткий", "длинный"},
    "размер": {"символ", "мб", "гб"},
    "стоимость": {"рубль"},
    "сумма": {"рубль"},
    "граница": {"рубеж"},
    "заграница": {"рубеж"},
}


def _matches(word: str, pool: set[str], stems: set[str]) -> bool:
    if word in pool or (len(word) >= STEM and word[:STEM] in stems):
        return True
    return any(related in pool for related in _RELATED.get(word, ()))


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
    if best_total < MIN_COVERAGE or max(item[0] for item in scored) == 0:
        # The title alone is not an answer: «как оформить больничный?» shares only the word
        # «Оформление» with a travel-approval rule.
        return None
    best_own = max(item[0] for item in scored)
    ranked = sorted((item for item in scored if item[0] >= best_own * 0.8), reverse=True)[:limit]
    chosen = sorted(ranked, key=lambda item: item[2])
    return Focus(" ".join(item[3] for item in chosen), round(best_total, 2))


# Nouns that frame a question rather than name its subject: «в этом году», «какие требования
# к паролю», «что сказано в регламенте», «какой длины». The subject is the other noun.
_FRAME_NOUNS = frozenset(
    "время год раз день неделя месяц случай дело вопрос человек вещь способ образ помощь "
    "ситуация проблема сотрудник компания требование документ регламент правило инструкция "
    "политика положение порядок условие норма ограничение срок длина размер сумма стоимость "
    "количество число максимум минимум".split()
)


def corpus_words(texts: list[str]) -> set[str]:
    """Every word of the company documents in its dictionary form, for `unknown_subjects`."""
    return {morph.lemma(word) for text in texts for word in _WORD.findall(text.lower().replace("ё", "е"))}


def unknown_subjects(question: str, corpus: set[str]) -> list[str]:
    """Nouns of the question that no company document ever mentions.

    «Когда перечислят зарплату?» shares «перечисл…» with a rule about holiday pay; if no
    document says «зарплата» at all, the documents cannot answer it, however close a
    sentence looks. Only dictionary nouns count: slang and typos are left to the matcher.
    """
    stems = {word[:STEM] for word in corpus if len(word) >= STEM}
    missing = []
    for noun in _subjects(question):
        if not _mentioned(noun, corpus, stems):
            missing.append(noun)
    return missing


def _subjects(question: str) -> list[str]:
    """Dictionary nouns of the question that name what it is about, in order, without repeats."""
    subjects = []
    for word in _WORD.findall(question.lower().replace("ё", "е")):
        noun = morph.known_noun(word)
        if noun is not None and noun not in _FRAME_NOUNS and noun not in subjects:
            subjects.append(noun)
    return subjects


def _mentioned(noun: str, words: set[str], stems: set[str]) -> bool:
    """The noun, its stem, a related word («граница» → «рубеж») or a clipped form it abbreviates
    («комп» → «компьютер», «ноут» → «ноутбук») occurs among `words`."""
    if noun in words or (len(noun) >= STEM and noun[:STEM] in stems):
        return True
    if any(related in words for related in _RELATED.get(noun, ())):
        return True
    return len(noun) >= 4 and any(word.startswith(noun) for word in words)


def covers_subjects(question: str, answer: str) -> bool:
    """Whether the chosen answer speaks about what was asked: at least half of the question's
    subject nouns appear in it. «Когда перечислят зарплату?» is not answered by a sentence
    about holiday pay, even when «зарплата» occurs elsewhere in the same document."""
    subjects = _subjects(question)
    if not subjects:
        return True
    present = corpus_words([answer])
    stems = {word[:STEM] for word in present if len(word) >= STEM}
    covered = sum(_mentioned(noun, present, stems) for noun in subjects)
    return covered * 2 >= len(subjects)
