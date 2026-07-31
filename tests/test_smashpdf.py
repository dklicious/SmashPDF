from __future__ import annotations

import hashlib
from pathlib import Path
from string import Formatter

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.constants import UserAccessPermissions
from pypdf.generic import (
    ArrayObject,
    ByteStringObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

from smashpdf import (
    LANGUAGE_NAMES,
    TRANSLATIONS,
    PasswordRequiredError,
    unlock_pdf,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_all_supported_languages_have_complete_translations() -> None:
    assert set(LANGUAGE_NAMES) == {
        "en",
        "zh",
        "zh_hant",
        "es",
        "ja",
        "ko",
    }
    assert list(LANGUAGE_NAMES.values()) == [
        "English",
        "简体中文",
        "繁體中文",
        "Español",
        "日本語",
        "한국어",
    ]
    english_keys = set(TRANSLATIONS["en"])
    formatter = Formatter()

    assert set(TRANSLATIONS) == set(LANGUAGE_NAMES)
    for language, translations in TRANSLATIONS.items():
        assert set(translations) == english_keys, language
        assert all(value.strip() for value in translations.values()), language
        for key, value in translations.items():
            expected_fields = {
                field
                for _, field, _, _ in formatter.parse(
                    TRANSLATIONS["en"][key]
                )
                if field
            }
            actual_fields = {
                field
                for _, field, _, _ in formatter.parse(value)
                if field
            }
            assert actual_fields == expected_fields, (language, key)


def _encrypted_pdf(
    path: Path,
    *,
    user_password: str,
    owner_password: str = "owner-secret",
) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt(
        user_password=user_password,
        owner_password=owner_password,
        permissions_flag=UserAccessPermissions.PRINT,
        algorithm="AES-256",
    )
    writer.write(path)


def test_removes_permission_encryption_without_touching_source(tmp_path: Path) -> None:
    source = tmp_path / "restricted.pdf"
    output = tmp_path / "unlocked.pdf"
    _encrypted_pdf(source, user_password="")
    original_hash = _sha256(source)

    result = unlock_pdf(source, output=output)

    unlocked = PdfReader(output)
    assert result.was_encrypted is True
    assert unlocked.is_encrypted is False
    assert len(unlocked.pages) == 1
    assert _sha256(source) == original_hash


def test_requires_correct_opening_password(tmp_path: Path) -> None:
    source = tmp_path / "password.pdf"
    output = tmp_path / "unlocked.pdf"
    _encrypted_pdf(source, user_password="correct-password")

    with pytest.raises(PasswordRequiredError):
        unlock_pdf(source, output=output)

    unlock_pdf(source, password="correct-password", output=output)
    assert PdfReader(output).is_encrypted is False


def _visible_signature_pdf(path: Path) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    appearance = DecodedStreamObject()
    appearance.set_data(b"q 0 0 0 RG 2 w 5 10 m 115 35 l S Q")
    appearance.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Form"),
            NameObject("/FormType"): NumberObject(1),
            NameObject("/BBox"): ArrayObject(
                [
                    FloatObject(0),
                    FloatObject(0),
                    FloatObject(120),
                    FloatObject(60),
                ]
            ),
            NameObject("/Resources"): DictionaryObject(),
        }
    )
    appearance_ref = writer._add_object(appearance)

    signature = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Sig"),
            NameObject("/Filter"): NameObject("/Adobe.PPKLite"),
            NameObject("/SubFilter"): NameObject("/adbe.pkcs7.detached"),
            NameObject("/ByteRange"): ArrayObject(
                [
                    NumberObject(0),
                    NumberObject(0),
                    NumberObject(0),
                    NumberObject(0),
                ]
            ),
            NameObject("/Contents"): ByteStringObject(b"test-signature"),
        }
    )
    signature_ref = writer._add_object(signature)

    widget = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Widget"),
            NameObject("/FT"): NameObject("/Sig"),
            NameObject("/T"): TextStringObject("VisibleSignature"),
            NameObject("/Rect"): ArrayObject(
                [
                    FloatObject(150),
                    FloatObject(640),
                    FloatObject(270),
                    FloatObject(700),
                ]
            ),
            NameObject("/F"): NumberObject(4),
            NameObject("/AP"): DictionaryObject({NameObject("/N"): appearance_ref}),
            NameObject("/V"): signature_ref,
            NameObject("/P"): page.indirect_reference,
        }
    )
    widget_ref = writer._add_object(widget)
    page[NameObject("/Annots")] = ArrayObject([widget_ref])

    acroform = DictionaryObject(
        {
            NameObject("/Fields"): ArrayObject([widget_ref]),
            NameObject("/SigFlags"): NumberObject(3),
        }
    )
    writer.root_object[NameObject("/AcroForm")] = writer._add_object(acroform)
    writer.root_object[NameObject("/Perms")] = DictionaryObject(
        {NameObject("/DocMDP"): signature_ref}
    )
    writer.write(path)


def test_preserves_visible_signature_appearance_as_stamp(tmp_path: Path) -> None:
    source = tmp_path / "signed.pdf"
    output = tmp_path / "unlocked.pdf"
    _visible_signature_pdf(source)

    unlock_pdf(source, output=output)

    reader = PdfReader(output)
    annotations = reader.pages[0]["/Annots"]
    annotation = annotations[0].get_object()
    assert reader.root_object.get("/Perms") is None
    assert reader.get_fields() == {}
    assert annotation["/Subtype"] == "/Stamp"
    assert annotation.get("/AP") is not None
    assert annotation.get("/V") is None


def test_lossless_compression_preserves_pages_and_text(tmp_path: Path) -> None:
    source = tmp_path / "large.pdf"
    output = tmp_path / "compressed.pdf"

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 12 Tf (SmashPDF) Tj ET\n" + b"%padding\n" * 5000)
    content_ref = writer._add_object(content)
    page[NameObject("/Contents")] = content_ref
    writer.write(source)

    unlock_pdf(source, output=output, compression="major")

    original = PdfReader(source)
    compressed = PdfReader(output)
    assert len(compressed.pages) == len(original.pages)
    assert compressed.pages[0].extract_text() == original.pages[0].extract_text()
    assert output.stat().st_size < source.stat().st_size
