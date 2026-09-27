import pytest

from app.services.document_extraction import (
    ExtractionError,
    extract_document,
    media_type_for,
    safe_filename,
)
from tests.knowledge_files import (
    blank_pdf,
    docx_with,
    encrypted_pdf,
    pdf_with_text,
    zip_without_docx,
)

LIMITS = {"max_chars": 200_000, "max_pdf_pages": 200}


def extract(filename, content, **limits):
    return extract_document(filename, content, **(LIMITS | limits))


def failure(filename, content, **limits) -> str:
    with pytest.raises(ExtractionError) as error:
        extract(filename, content, **limits)
    return error.value.code


# --- formats ------------------------------------------------------------------

@pytest.mark.parametrize("filename", ["vpn.txt", "vpn.md"])
def test_utf8_russian_text(filename):
    body = "# Подключение VPN\n\nОткройте клиент «Континент» и нажмите «Подключить».\n"
    result = extract(filename, body.encode("utf-8"))

    assert "Откройте клиент «Континент»" in result.text
    assert result.format == filename.rsplit(".", 1)[1]


def test_utf8_bom_and_windows_newlines_are_normalized():
    result = extract("rules.txt", "﻿Первая строка\r\n\r\n\r\n\r\nВторая  строка\r\n".encode("utf-8"))

    assert result.text == "Первая строка\n\nВторая строка"


def test_pdf_text_is_extracted():
    result = extract("vpn.pdf", pdf_with_text("VPN guide", "Restart the client and connect again."))

    assert "Restart the client and connect again." in result.text
    assert result.pages == 1
    assert result.media_type == "application/pdf"


def test_docx_keeps_headings_and_tables():
    content = docx_with(
        "Отпуск",
        ["Заявление подаётся за две недели.", "Согласует руководитель."],
        table=[["Тип", "Дней"], ["Ежегодный", "28"]],
    )

    result = extract("policy.docx", content)

    assert result.text.startswith("# Отпуск")
    assert "Заявление подаётся за две недели." in result.text
    assert "Ежегодный | 28" in result.text


# --- broken, hostile and empty files --------------------------------------------

def test_encrypted_pdf_is_rejected():
    assert failure("secret.pdf", encrypted_pdf()) == "encrypted"


def test_pdf_without_text_is_rejected():
    assert failure("scan.pdf", blank_pdf()) == "no_text"


def test_corrupt_pdf_is_rejected():
    assert failure("broken.pdf", b"%PDF-1.4\n1 0 obj << /Type /Catalog") == "corrupt"


def test_pdf_page_limit():
    assert failure("vpn.pdf", pdf_with_text("one page"), max_pdf_pages=0) == "too_many_pages"


def test_zip_that_is_not_a_word_document_is_rejected():
    assert failure("fake.docx", zip_without_docx()) == "corrupt"


@pytest.mark.parametrize(("filename", "content"), [
    ("fake.pdf", "обычный текст, а не PDF".encode()),
    ("fake.docx", b"%PDF-1.4 pretending to be docx"),
    ("fake.txt", b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00" * 8),
    ("fake.md", pdf_with_text("a pdf renamed to md")),
])
def test_content_must_match_the_extension(filename, content):
    assert failure(filename, content) == "content_mismatch"


def test_text_in_another_encoding_is_rejected():
    assert failure("cp1251.txt", "Привет, мир".encode("cp1251")) == "not_utf8"


@pytest.mark.parametrize(("filename", "content"), [
    ("empty.txt", b"   \n\t\n"),
    ("empty.docx", docx_with("", [])),
])
def test_documents_without_text_are_rejected(filename, content):
    assert failure(filename, content) == "no_text"


def test_too_much_extracted_text_is_rejected():
    assert failure("big.txt", ("слово " * 100).encode(), max_chars=50) == "too_large"


def test_unsupported_extension():
    assert failure("macro.docm", b"PK\x03\x04") == "unsupported_format"


def test_control_characters_are_removed():
    # NUL marks binary content and is refused; other control and invisible characters are dropped.
    result = extract("x.txt", "Строка\x07 с мусором​ и нормальным\x0b текстом".encode())

    assert result.text == "Строка с мусором и нормальным текстом"


# --- names ----------------------------------------------------------------------

@pytest.mark.parametrize(("raw", "expected"), [
    ("../../etc/passwd.txt", "passwd.txt"),
    ("..\\..\\windows\\system.ini.md", "system.ini.md"),
    ("  Правила VPN (2026).pdf  ", "Правила VPN (2026).pdf"),
    ("a\x00b<script>.txt", "abscript.txt"),
    ("/", "document"),
])
def test_safe_filename(raw, expected):
    assert safe_filename(raw) == expected


def test_media_types():
    assert media_type_for("pdf") == "application/pdf"
    assert media_type_for("md") == "text/markdown"
