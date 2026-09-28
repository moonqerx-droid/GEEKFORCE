"""Word forms and typo correction for Russian support requests.

People write «принтр не пичатает» and «в очереди печати»; the playbooks say «принтер»
and «очередь печати». Two cheap, deterministic fixes close that gap:

* lemmas: keywords and text are also compared in their dictionary form;
* typos: a word the dictionary does not know is replaced by the closest word of the
  support vocabulary (playbook texts plus everyday complaint words, in every form),
  if one is within one or two edits.

Both degrade to a no-op when pymorphy3 or rapidfuzz is not installed.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from functools import lru_cache
from typing import Iterable

logger = logging.getLogger(__name__)

try:  # optional: the engine still works on exact keywords without them
    import pymorphy3
    from rapidfuzz.distance import DamerauLevenshtein
except ImportError:  # pragma: no cover - exercised only without the extras
    pymorphy3 = None
    DamerauLevenshtein = None

_WORD_RE = re.compile(r"[а-яё]+")
_QUOTED_RE = re.compile(r"«[^»]*»|\"[^\"]*\"|“[^”]*”")
MIN_LENGTH = 4

# Everyday words of IT complaints, as lemmas; every form of each is added.
GENERAL_LEMMAS = """
сегодня вчера утро вечер сейчас снова опять постоянно всегда вообще никак срочно быстро медленно долго
работать заработать открываться открыть открывать запускаться запустить войти заходить зайти входить
загружаться загрузить грузиться подключаться подключиться подключение отправлять отправить получать
получить приходить прийти печатать распечатать зависать зависнуть тормозить сломаться ломаться пропадать
пропасть появляться появиться показывать писать выдавать выдать вылетать отваливаться отключаться
ошибка сообщение уведомление окно кнопка компьютер ноутбук телефон смартфон экран клавиатура мышь монитор
программа приложение система сервис сайт страница браузер файл папка документ таблица диск флешка
доступ пароль логин учётный запись почта письмо вложение ящик сеть интернет роутер кабель принтер
бумага картридж звук микрофон камера наушники звонок встреча созвон видео конференция
помочь помогать мочь коллега отдел офис дом удалённо запретить запрещённый заблокировать блокировать
сбросить забыть поменять сменить истечь обновить обновление перезагрузить установить удалить вирус ссылка
сообщить срок работа рабочий доступный недоступный сервер база клиент сделка отчёт бухгалтерия
""".split()

# IT slang and chat shorthand -> the plain word the playbooks use (from the codex/nlu branch).
SLANG: dict[str, str] = {
    "конектится": "подключается", "коннектится": "подключается",
    "конектиться": "подключаться", "коннектиться": "подключаться",
    "конектит": "подключает", "коннектит": "подключает",
    "инет": "интернет", "инета": "интернета", "инете": "интернете", "инетом": "интернетом",
    "залочена": "заблокирована", "залочен": "заблокирован", "залочили": "заблокировали",
    "залочило": "заблокировало", "залочилась": "заблокировалась",
    "мобила": "телефон", "мобилы": "телефона", "мобиле": "телефоне", "мобилу": "телефон",
    "винда": "windows", "винду": "windows", "винде": "windows", "виндовс": "windows",
    "залогиниться": "войти", "залогинится": "войти",
    "форти": "forticlient", "фортиклиент": "forticlient",
    "тимсе": "teams", "тимсы": "teams",
    "учетка": "учетная запись", "учетку": "учетную запись", "учетки": "учетной записи",
    "учетке": "учетной записи", "учеткой": "учетной записью",
}

_morph = None
_by_letter: dict[str, list[str]] = {}
_vocabulary: frozenset[str] = frozenset()
# Words as the playbooks and the everyday list spell them: preferred over rarer forms
# of the same word («открывается» over «открывайся» for «открыватся»).
_base: frozenset[str] = frozenset()


def available() -> bool:
    return pymorphy3 is not None and DamerauLevenshtein is not None


def _analyzer():
    global _morph
    if _morph is None and pymorphy3 is not None:
        _morph = pymorphy3.MorphAnalyzer()
    return _morph


@lru_cache(maxsize=65536)
def is_known(word: str) -> bool:
    analyzer = _analyzer()
    return analyzer is None or analyzer.word_is_known(word)


@lru_cache(maxsize=65536)
def lemma(word: str) -> str:
    """Dictionary form of a known word; unknown words and stems stay as they are."""
    analyzer = _analyzer()
    if analyzer is None or not analyzer.word_is_known(word):
        return word
    return analyzer.parse(word)[0].normal_form.replace("ё", "е")


@lru_cache(maxsize=8192)
def lemmatize(norm_text: str) -> str:
    """The normalized text with every known word in its dictionary form."""
    return _WORD_RE.sub(lambda match: lemma(match.group(0)), norm_text)


def _forms(word: str) -> set[str]:
    analyzer = _analyzer()
    if analyzer is None or not analyzer.word_is_known(word):
        return {word}
    forms = {word}
    for parse in analyzer.parse(word)[:2]:
        forms.update(item.word for item in parse.lexeme)
    return {form.replace("ё", "е") for form in forms}


def vocabulary_from(playbooks: Iterable) -> frozenset[str]:
    """Every form of every word the playbooks use, plus everyday complaint words."""
    words: set[str] = set()
    for playbook in playbooks:
        texts = [playbook.title, *playbook.keywords, *getattr(playbook, "examples", [])]
        texts += [hint for hints in playbook.symptoms_hints.values() for hint in hints]
        texts += [q.text for q in playbook.questions] + [s.title + " " + s.instruction for s in playbook.steps]
        for text in texts:
            words.update(_WORD_RE.findall(text.lower().replace("ё", "е")))
    words.update(GENERAL_LEMMAS)
    return _expand(frozenset(words))


@lru_cache(maxsize=8)
def _expand(words: frozenset[str]) -> frozenset[str]:
    """Every form of every word; the costly part, so it is cached by the word set."""
    return frozenset(form for word in words if len(word) >= MIN_LENGTH - 1 for form in _forms(word))


def base_words_from(playbooks: Iterable) -> frozenset[str]:
    words: set[str] = set(GENERAL_LEMMAS)
    for playbook in playbooks:
        for text in [playbook.title, *playbook.keywords, *getattr(playbook, "examples", [])]:
            words.update(_WORD_RE.findall(text.lower().replace("ё", "е")))
    return frozenset(words)


def use_playbooks(playbooks: Iterable) -> None:
    """Build the correction vocabulary from the knowledge base (cheap, cached by content)."""
    playbooks = list(playbooks)
    set_vocabulary(vocabulary_from(playbooks), base_words_from(playbooks))


def set_vocabulary(words: Iterable[str], base: Iterable[str] = ()) -> None:
    global _vocabulary, _by_letter, _base
    vocabulary = frozenset(words)
    _base = frozenset(base)
    if vocabulary == _vocabulary:
        return
    grouped: dict[str, list[str]] = defaultdict(list)
    for word in vocabulary:
        grouped[word[0]].append(word)
    _vocabulary, _by_letter = vocabulary, dict(grouped)
    _correct_word.cache_clear()
    logger.info("understanding.vocabulary words=%s", len(vocabulary))


@lru_cache(maxsize=16384)
def _correct_word(word: str) -> str:
    if word in SLANG:
        return SLANG[word]
    if len(word) < MIN_LENGTH or word in _vocabulary or is_known(word):
        return word
    limit = 1 if len(word) <= 7 else 2
    best, best_key = word, None
    # A typo rarely hits the first letter; searching by it keeps this fast and precise.
    for candidate in _by_letter.get(word[0], ()):
        if abs(len(candidate) - len(word)) > limit:
            continue
        distance = DamerauLevenshtein.distance(word, candidate, score_cutoff=limit)
        if distance > limit:
            continue
        key = (distance, candidate not in _base, abs(len(candidate) - len(word)), candidate)
        if best_key is None or key < best_key:
            best, best_key = candidate, key
    return best


def correct(norm_text: str) -> str:
    """Fix typos and slang in a normalized text; quoted error messages are kept verbatim."""
    if not available() or not _vocabulary:
        return _WORD_RE.sub(lambda m: SLANG.get(m.group(0), m.group(0)), norm_text)
    parts, last = [], 0
    for quoted in _QUOTED_RE.finditer(norm_text):
        parts.append(_WORD_RE.sub(lambda m: _correct_word(m.group(0)), norm_text[last:quoted.start()]))
        parts.append(quoted.group(0))
        last = quoted.end()
    parts.append(_WORD_RE.sub(lambda m: _correct_word(m.group(0)), norm_text[last:]))
    return "".join(parts)
