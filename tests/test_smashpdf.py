from __future__ import annotations

import hashlib
from pathlib import Path
from string import Formatter
from unittest.mock import patch

import pytest
from PIL import Image
from pypdf import PasswordType, PdfReader, PdfWriter
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
    IMAGE_COMPRESSION_PROFILES,
    LANGUAGE_NAMES,
    LOCKED_PERMISSIONS,
    TRANSLATIONS,
    USER_ACTION_PERMISSIONS,
    ImageCompressionResult,
    LockResult,
    PasswordRequiredError,
    PdfSearchResult,
    UnlockResult,
    _format_result,
    _format_size_change,
    collect_pdf_files,
    compress_image,
    default_image_output_path,
    default_lock_output_path,
    default_output_path,
    load_language_preference,
    lock_pdf,
    save_language_preference,
    search_pdf,
    unlock_pdf,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _blank_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(path)


def _text_pdf(path: Path, page_texts: list[str]) -> None:
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_reference = writer._add_object(font)
    for text in page_texts:
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_reference})}
        )
        content = DecodedStreamObject()
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content.set_data(f"BT /F1 12 Tf ({escaped}) Tj ET".encode("latin-1"))
        page[NameObject("/Contents")] = writer._add_object(content)
    writer.write(path)


def test_search_pdf_finds_names_with_pages_and_context(tmp_path: Path) -> None:
    source = tmp_path / "lease.pdf"
    _text_pdf(
        source,
        [
            "Lease for Jane Citizen at 3 Glasshouse Way.",
            "Bond for JANE CITIZEN. Contact Jane Citizen today.",
        ],
    )

    result = search_pdf(source, "jane citizen")

    assert isinstance(result, PdfSearchResult)
    assert result.source == source.resolve()
    assert result.page_count == 2
    assert result.searchable_pages == 2
    assert [match.page_number for match in result.matches] == [1, 2, 2]
    assert all("Citizen" in match.snippet for match in result.matches)
    assert result.truncated is False

    exact = search_pdf(source, "Jane Citizen", case_sensitive=True)
    assert [match.page_number for match in exact.matches] == [1, 2]


def test_search_pdf_reports_image_only_pages_and_match_limit(tmp_path: Path) -> None:
    blank = tmp_path / "scan.pdf"
    _blank_pdf(blank)
    blank_result = search_pdf(blank, "tenant")
    assert blank_result.searchable_pages == 0
    assert not blank_result.matches

    repeated = tmp_path / "repeated.pdf"
    _text_pdf(repeated, ["tenant tenant tenant"])
    limited = search_pdf(repeated, "tenant", max_matches=2, context_chars=0)
    assert len(limited.matches) == 2
    assert limited.truncated is True


def test_collect_pdf_files_expands_folders_and_removes_duplicates(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.PDF"
    nested = tmp_path / "nested"
    nested.mkdir()
    second = nested / "second.pdf"
    _blank_pdf(first)
    _blank_pdf(second)
    (nested / "notes.txt").write_text("ignored", encoding="utf-8")

    assert collect_pdf_files([tmp_path, first]) == [first.resolve(), second.resolve()]

    unsupported = tmp_path / "notes.txt"
    assert collect_pdf_files([unsupported, tmp_path / "missing.pdf"]) == []


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"context_chars": -1}, "cannot be negative"),
        ({"max_matches": 0}, "at least 1"),
    ],
)
def test_search_pdf_validates_options(
    tmp_path: Path,
    kwargs: dict[str, int],
    message: str,
) -> None:
    source = tmp_path / "source.pdf"
    _blank_pdf(source)
    with pytest.raises(ValueError, match=message):
        search_pdf(source, "tenant", **kwargs)


def test_search_pdf_rejects_empty_text(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    _blank_pdf(source)
    with pytest.raises(ValueError, match="cannot be empty"):
        search_pdf(source, "  \n ")

    with pytest.raises(ValueError, match="Not a PDF"):
        search_pdf(tmp_path / "missing.pdf", "tenant")


def test_app_uses_canonical_version() -> None:
    assert __version__ == APP_VERSION


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


def test_default_lock_output_path_uses_next_available_name(tmp_path: Path) -> None:
    source = tmp_path / "Document.PDF"
    _blank_pdf(source)
    (tmp_path / "Document_locked.PDF").touch()
    (tmp_path / "Document_locked (2).PDF").touch()

    assert default_lock_output_path(source) == tmp_path / "Document_locked (3).PDF"


def test_default_image_output_path_uses_next_available_name(tmp_path: Path) -> None:
    source = tmp_path / "Photo.JPG"
    Image.new("RGB", (100, 100), "red").save(source)
    (tmp_path / "Photo_compressed.JPG").touch()
    (tmp_path / "Photo_compressed (2).JPG").touch()

    assert default_image_output_path(source) == tmp_path / "Photo_compressed (3).JPG"


@pytest.mark.parametrize(
    ("extension", "image_format"),
    [
        ("jpg", "JPEG"),
        ("png", "PNG"),
        ("webp", "WEBP"),
        ("bmp", "BMP"),
        ("tiff", "TIFF"),
    ],
)
def test_compress_image_preserves_format_and_source(
    tmp_path: Path,
    extension: str,
    image_format: str,
) -> None:
    source = tmp_path / f"photo.{extension}"
    image = Image.effect_noise((1600, 1200), 100).convert("RGB")
    save_options = {"quality": 95} if image_format in {"JPEG", "WEBP"} else {}
    image.save(source, image_format, **save_options)
    source_hash = _sha256(source)

    result = compress_image(source, compression="major")

    assert isinstance(result, ImageCompressionResult)
    assert result.output.parent == source.parent
    assert result.output.name == f"photo_compressed.{extension}"
    assert result.compression_mode in IMAGE_COMPRESSION_PROFILES
    assert result.reduction_percent > 0
    assert result.output_size < result.source_size
    assert _sha256(source) == source_hash
    with Image.open(result.output) as compressed:
        assert compressed.format == image_format
        assert compressed.size == image.size


def test_compress_image_preserves_animation_frames(tmp_path: Path) -> None:
    source = tmp_path / "animation.gif"
    frames = [
        Image.effect_noise((600, 400), amount).convert("RGB")
        for amount in (60, 90, 120)
    ]
    frames[0].save(
        source,
        save_all=True,
        append_images=frames[1:],
        duration=[100, 200, 300],
        loop=0,
    )

    result = compress_image(source, compression="major")

    with Image.open(result.output) as compressed:
        assert result.frame_count == 3
        assert compressed.n_frames == 3
        assert compressed.info["loop"] == 0


def test_image_compression_preserves_transparency_and_metadata(
    tmp_path: Path,
) -> None:
    transparent_source = tmp_path / "transparent.png"
    transparent = Image.effect_noise((1200, 900), 100).convert("RGBA")
    transparent.putalpha(Image.linear_gradient("L").resize(transparent.size))
    transparent.save(transparent_source, "PNG")

    transparent_result = compress_image(
        transparent_source,
        compression="massive",
    )
    with Image.open(transparent_result.output) as compressed:
        alpha = compressed.convert("RGBA").getchannel("A")
        assert alpha.getextrema()[0] < 255
        assert alpha.getextrema()[1] > alpha.getextrema()[0]
        assert max(compressed.size) <= 1600

    jpeg_source = tmp_path / "metadata.jpg"
    exif = Image.Exif()
    exif[270] = "SmashPDF metadata test"
    Image.effect_noise((1600, 1200), 100).convert("RGB").save(
        jpeg_source,
        "JPEG",
        quality=95,
        exif=exif,
    )

    jpeg_result = compress_image(jpeg_source, compression="standard")
    with Image.open(jpeg_result.output) as compressed:
        assert compressed.getexif()[270] == "SmashPDF metadata test"


def test_massive_image_compression_limits_dimensions(tmp_path: Path) -> None:
    source = tmp_path / "large.jpg"
    Image.effect_noise((3200, 2400), 100).convert("RGB").save(
        source,
        "JPEG",
        quality=95,
    )

    result = compress_image(source, compression="massive")

    with Image.open(result.output) as compressed:
        assert max(compressed.size) <= 1600
        assert result.reduction_percent > 50


def test_compress_image_rejects_unsupported_and_unchanged_output(
    tmp_path: Path,
) -> None:
    source = tmp_path / "picture.png"
    Image.new("RGB", (1, 1), "red").save(source)

    with pytest.raises(RuntimeError, match="already optimised"):
        compress_image(source)
    assert not (tmp_path / "picture_compressed.png").exists()

    unsupported = tmp_path / "picture.svg"
    unsupported.write_text("<svg/>", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported image"):
        compress_image(unsupported)


def test_compress_image_rejects_excessive_total_pixels(tmp_path: Path) -> None:
    source = tmp_path / "many-pixels.png"
    Image.new("RGB", (20, 20), "red").save(source)

    with (
        patch("smashpdf.MAX_TOTAL_IMAGE_PIXELS", 100),
        pytest.raises(Image.DecompressionBombError, match="too large"),
    ):
        compress_image(source)

    assert not (tmp_path / "many-pixels_compressed.png").exists()


def test_lock_pdf_uses_aes256_and_disables_user_actions(tmp_path: Path) -> None:
    source = tmp_path / "contract.pdf"
    _blank_pdf(source)
    source_hash = _sha256(source)

    result = lock_pdf(source, "correct horse battery staple")

    assert isinstance(result, LockResult)
    assert result.output == tmp_path / "contract_locked.pdf"
    assert _sha256(source) == source_hash

    reader = PdfReader(result.output)
    assert reader.is_encrypted
    assert reader.decrypt("incorrect") == PasswordType.NOT_DECRYPTED
    assert reader.decrypt("correct horse battery staple") == PasswordType.USER_PASSWORD
    assert reader.are_permissions_valid
    assert len(reader.pages) == 1
    assert reader.user_access_permissions == LOCKED_PERMISSIONS
    assert not reader.user_access_permissions & USER_ACTION_PERMISSIONS
    encryption = reader.trailer["/Encrypt"]
    assert encryption["/V"] == 5
    assert encryption["/R"] == 6
    assert encryption["/Length"] == 256


def test_lock_pdf_requires_a_reasonable_password(tmp_path: Path) -> None:
    source = tmp_path / "contract.pdf"
    _blank_pdf(source)

    with pytest.raises(ValueError, match="at least 8"):
        lock_pdf(source, "short")

    assert not (tmp_path / "contract_locked.pdf").exists()


def test_lock_preserves_metadata_attachments_and_form_fields(tmp_path: Path) -> None:
    source = tmp_path / "records.pdf"
    output = tmp_path / "secured.pdf"
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
                [FloatObject(72), FloatObject(700), FloatObject(300), FloatObject(730)]
            ),
            NameObject("/P"): page.indirect_reference,
        }
    )
    widget_ref = writer._add_object(widget)
    page[NameObject("/Annots")] = ArrayObject([widget_ref])
    writer.root_object[NameObject("/AcroForm")] = writer._add_object(
        DictionaryObject({NameObject("/Fields"): ArrayObject([widget_ref])})
    )
    writer.add_metadata({"/Title": "Important contract"})
    writer.add_attachment("evidence.txt", b"retained attachment")
    writer.write(source)

    lock_pdf(source, "secure-password", output=output)

    reader = PdfReader(output)
    assert reader.decrypt("secure-password") == PasswordType.USER_PASSWORD
    assert reader.metadata.title == "Important contract"
    assert reader.attachments["evidence.txt"] == [b"retained attachment"]
    assert reader.get_fields()["TenantName"]["/V"] == "Example Tenant"


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


def test_search_pdf_prompts_for_encrypted_document_password(tmp_path: Path) -> None:
    source = tmp_path / "protected.pdf"
    _encrypted_pdf(source, user_password="correct-password")

    with pytest.raises(PasswordRequiredError):
        search_pdf(source, "tenant")

    result = search_pdf(source, "tenant", password="correct-password")
    assert result.page_count == 1


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


def test_massive_compression_surpasses_sixty_percent_on_scanned_pdf(
    tmp_path: Path,
) -> None:
    source = tmp_path / "high-resolution-scan.pdf"
    output = tmp_path / "massive.pdf"
    scan = Image.effect_noise((2200, 3000), 100).convert("RGB")
    scan.save(source, "PDF", resolution=300, quality=95)

    result = unlock_pdf(source, output=output, compression="massive")

    reader = PdfReader(output)
    output_image = reader.pages[0].images[0].image
    assert len(reader.pages) == 1
    assert result.streams_optimized == 1
    assert result.reduction_percent > 60
    assert max(output_image.size) <= 1440


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
