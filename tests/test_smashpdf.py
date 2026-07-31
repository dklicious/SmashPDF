from __future__ import annotations

import hashlib
from pathlib import Path
from string import Formatter
from unittest.mock import patch

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.constants import UserAccessPermissions
from pypdf.errors import PdfReadError
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

from _version import __version__
from smashpdf import (
    APP_VERSION,
    LANGUAGE_NAMES,
    TRANSLATIONS,
    PasswordRequiredError,
    UnlockResult,
    _format_result,
    _format_size_change,
    default_output_path,
    load_language_preference,
    save_language_preference,
    unlock_pdf,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _blank_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(path)


def test_app_uses_canonical_version() -> None:
    assert APP_VERSION == __version__ == "1.2.3"


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
        "简体中文",
        "繁體中文",
        "English",
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
                for _, field, _, _ in formatter.parse(TRANSLATIONS["en"][key])
                if field
            }
            actual_fields = {
                field for _, field, _, _ in formatter.parse(value) if field
            }
            assert actual_fields == expected_fields, (language, key)


def test_language_preference_defaults_to_english_and_persists(
    tmp_path: Path,
) -> None:
    settings = tmp_path / "preferences" / "settings.json"

    assert load_language_preference(settings) == "en"

    save_language_preference("zh_hant", settings)
    assert load_language_preference(settings) == "zh_hant"
    assert settings.read_text(encoding="utf-8") == ('{"language":"zh_hant"}\n')

    settings.write_text('{"language":"unsupported"}', encoding="utf-8")
    assert load_language_preference(settings) == "en"


def test_language_preference_rejects_unknown_language(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported language"):
        save_language_preference("unknown", tmp_path / "settings.json")


@pytest.mark.parametrize(
    ("source_size", "output_size", "expected"),
    [
        (100, 75, "25.0% smaller"),
        (100, 125, "25.0% larger"),
        (100, 100, "same size"),
        (0, 10, "same size"),
    ],
)
def test_size_change_reporting_is_truthful(
    tmp_path: Path,
    source_size: int,
    output_size: int,
    expected: str,
) -> None:
    result = UnlockResult(
        source=tmp_path / "source.pdf",
        output=tmp_path / "output.pdf",
        page_count=1,
        was_encrypted=False,
        removed_signature_fields=0,
        preserved_signature_appearances=0,
        compression_mode="standard",
        streams_optimized=1,
        source_size=source_size,
        output_size=output_size,
    )

    assert _format_size_change(result) == expected
    assert f"({expected})" in _format_result(result)


def test_default_output_path_uses_next_available_name(tmp_path: Path) -> None:
    source = tmp_path / "Document.PDF"
    _blank_pdf(source)
    first = tmp_path / "Document_unlocked.PDF"
    second = tmp_path / "Document_unlocked (2).PDF"
    first.touch()
    second.touch()

    assert default_output_path(source) == tmp_path / "Document_unlocked (3).PDF"


def test_explicit_output_created_during_processing_is_not_overwritten(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    sentinel = b"concurrent output"
    _blank_pdf(source)

    from smashpdf import _publish_without_overwrite

    def concurrent_publish(temp_path: Path, output_path: Path) -> None:
        output_path.write_bytes(sentinel)
        _publish_without_overwrite(temp_path, output_path)

    with (
        patch(
            "smashpdf._publish_without_overwrite",
            side_effect=concurrent_publish,
        ),
        pytest.raises(FileExistsError, match="Output already exists"),
    ):
        unlock_pdf(source, output=output)

    assert output.read_bytes() == sentinel
    assert not list(tmp_path.glob("*.tmp.pdf"))


def test_automatic_output_retries_after_concurrent_collision(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.pdf"
    collided_output = tmp_path / "source_unlocked.pdf"
    sentinel = b"concurrent output"
    _blank_pdf(source)

    from smashpdf import _publish_without_overwrite

    publish_calls = 0

    def concurrent_publish(temp_path: Path, output_path: Path) -> None:
        nonlocal publish_calls
        publish_calls += 1
        if publish_calls == 1:
            output_path.write_bytes(sentinel)
        _publish_without_overwrite(temp_path, output_path)

    with patch(
        "smashpdf._publish_without_overwrite",
        side_effect=concurrent_publish,
    ):
        result = unlock_pdf(source)

    assert collided_output.read_bytes() == sentinel
    assert result.output == tmp_path / "source_unlocked (2).pdf"
    assert PdfReader(result.output).pages
    assert not list(tmp_path.glob("*.tmp.pdf"))


def test_overwrite_replaces_only_explicit_output(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    _blank_pdf(source)
    output.write_bytes(b"old output")

    unlock_pdf(source, output=output, overwrite=True)

    assert output.read_bytes().startswith(b"%PDF")


def test_rejects_source_as_output(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    _blank_pdf(source)

    with pytest.raises(ValueError, match="different from the source"):
        unlock_pdf(source, output=source, overwrite=True)


def test_corrupt_pdf_fails_without_leaving_output(tmp_path: Path) -> None:
    source = tmp_path / "corrupt.pdf"
    output = tmp_path / "output.pdf"
    source.write_bytes(b"%PDF-1.7\ninvalid")

    with pytest.raises(PdfReadError):
        unlock_pdf(source, output=output)

    assert not output.exists()
    assert not list(tmp_path.glob("*.tmp.pdf"))


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


def test_preserves_metadata_and_attachments(tmp_path: Path) -> None:
    source = tmp_path / "document.pdf"
    output = tmp_path / "unlocked.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_metadata(
        {
            "/Title": "Important contract",
            "/Author": "SmashPDF audit",
        }
    )
    writer.add_attachment("evidence.txt", b"retained attachment")
    writer.write(source)

    unlock_pdf(source, output=output, compression="major")

    reader = PdfReader(output)
    assert reader.metadata.title == "Important contract"
    assert reader.metadata.author == "SmashPDF audit"
    assert reader.attachments["evidence.txt"] == [b"retained attachment"]


def test_preserves_non_signature_form_fields(tmp_path: Path) -> None:
    source = tmp_path / "form.pdf"
    output = tmp_path / "unlocked.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    widget = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Widget"),
            NameObject("/FT"): NameObject("/Tx"),
            NameObject("/T"): TextStringObject("TenantName"),
            NameObject("/V"): TextStringObject("Example Tenant"),
            NameObject("/Rect"): ArrayObject(
                [
                    FloatObject(72),
                    FloatObject(700),
                    FloatObject(300),
                    FloatObject(730),
                ]
            ),
            NameObject("/P"): page.indirect_reference,
        }
    )
    widget_ref = writer._add_object(widget)
    page[NameObject("/Annots")] = ArrayObject([widget_ref])
    writer.root_object[NameObject("/AcroForm")] = writer._add_object(
        DictionaryObject(
            {
                NameObject("/Fields"): ArrayObject([widget_ref]),
            }
        )
    )
    writer.write(source)

    unlock_pdf(source, output=output)

    fields = PdfReader(output).get_fields()
    assert fields is not None
    assert fields["TenantName"]["/V"] == "Example Tenant"
