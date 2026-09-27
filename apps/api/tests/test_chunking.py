from app.services.chunking import chunk_text

POLICY = """# Удалённая работа

Сотрудник работает из дома по согласованию с руководителем.

Для доступа к рабочим системам используйте VPN.

## Подключение VPN

Откройте клиент и введите корпоративный логин.

Если подключение не удаётся, перезагрузите компьютер.

## Безопасность

Не сохраняйте пароль в браузере."""


def test_headings_start_new_chunks_and_are_kept():
    chunks = chunk_text(POLICY, max_chars=1200, overlap=150)

    assert [chunk.heading for chunk in chunks] == [
        "Удалённая работа", "Подключение VPN", "Безопасность",
    ]
    assert chunks[1].text.startswith("## Подключение VPN")
    assert "перезагрузите компьютер" in chunks[1].text


def test_positions_are_stable_and_chunks_are_never_empty():
    chunks = chunk_text(POLICY, max_chars=1200, overlap=150)

    assert [chunk.position for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.text.strip() for chunk in chunks)
    assert all(chunk.char_count == len(chunk.text) for chunk in chunks)
    assert all(chunk.token_count > 0 for chunk in chunks)


def test_same_text_gives_the_same_chunks():
    assert chunk_text(POLICY, max_chars=300, overlap=60) == chunk_text(POLICY, max_chars=300, overlap=60)


def test_long_sections_split_at_paragraphs_with_overlap():
    paragraphs = [f"Пункт {index}. " + "Правило про доступ к системам. " * 6 for index in range(12)]
    text = "# Регламент\n\n" + "\n\n".join(paragraphs)

    chunks = chunk_text(text, max_chars=600, overlap=120)

    assert len(chunks) > 3
    assert all(chunk.char_count <= 600 for chunk in chunks)
    assert all(chunk.heading == "Регламент" for chunk in chunks)
    for previous, current in zip(chunks, chunks[1:]):
        tail = previous.text[-40:]
        assert tail.split()[-1] in current.text[:200], "neighbouring chunks overlap"


def test_one_huge_paragraph_is_split_at_word_boundaries():
    text = " ".join(f"слово{index}" for index in range(2000))

    chunks = chunk_text(text, max_chars=500, overlap=50)

    assert all(chunk.char_count <= 500 for chunk in chunks)
    words = {word for chunk in chunks for word in chunk.text.split()}
    assert {f"слово{index}" for index in range(2000)} <= words


def test_offsets_point_into_the_source():
    chunks = chunk_text(POLICY, max_chars=1200, overlap=150)

    for chunk in chunks:
        assert POLICY[chunk.start:chunk.end].startswith(chunk.text[:20])


def test_blank_text_has_no_chunks():
    assert chunk_text("  \n\n  ", max_chars=500, overlap=50) == []
