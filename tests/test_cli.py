from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image
from pypdf import PasswordType, PdfReader, PdfWriter

from smashpdf import build_parser, main


def _blank_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(path)


def test_cli_processes_pdf_and_reports_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    _blank_pdf(source)

    exit_code = main([str(source), "--output", str(output)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"Created: {output}" in captured.out
    assert not captured.err
    assert len(PdfReader(output).pages) == 1


def test_cli_locks_pdf_with_aes256(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "locked.pdf"
    _blank_pdf(source)

    exit_code = main(
        [
            str(source),
            "--output",
            str(output),
            "--lock",
            "--lock-password",
            "secure-password",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "AES-256 encrypted" in captured.out
    reader = PdfReader(output)
    assert reader.decrypt("secure-password") == PasswordType.USER_PASSWORD
    assert len(reader.pages) == 1


def test_cli_compresses_picture_in_same_folder(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "photo.jpg"
    Image.effect_noise((1600, 1200), 100).convert("RGB").save(
        source,
        "JPEG",
        quality=95,
    )

    exit_code = main([str(source), "--compress-images", "--compression", "major"])

    captured = capsys.readouterr()
    output = tmp_path / "photo_compressed.jpg"
    assert exit_code == 0
    assert f"Created: {output}" in captured.out
    assert output.stat().st_size < source.stat().st_size
    assert not captured.err


def test_cli_rejects_lock_password_without_lock() -> None:
    with pytest.raises(SystemExit, match="requires --lock"):
        main(["document.pdf", "--lock-password", "secure-password"])


def test_cli_rejects_compression_with_lock() -> None:
    with pytest.raises(SystemExit, match="cannot be used"):
        main(
            [
                "document.pdf",
                "--lock",
                "--lock-password",
                "secure-password",
                "--compression",
                "major",
            ]
        )


def test_cli_rejects_lock_with_picture_compression() -> None:
    with pytest.raises(SystemExit, match="cannot be used"):
        main(
            [
                "document.pdf",
                "--lock",
                "--lock-password",
                "secure-password",
                "--compress-images",
            ]
        )


def test_cli_reports_failure_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "missing.pdf"

    exit_code = main([str(missing)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Failed:" in captured.err
    assert "Traceback" not in captured.err


def test_cli_rejects_one_output_for_multiple_inputs(tmp_path: Path) -> None:
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    _blank_pdf(first)
    _blank_pdf(second)

    with pytest.raises(SystemExit, match="one input file"):
        main([str(first), str(second), "--output", str(tmp_path / "output.pdf")])


def test_parser_rejects_unknown_compression() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["document.pdf", "--compression", "destructive"])


def test_parser_accepts_massive_compression() -> None:
    args = build_parser().parse_args(
        ["document.pdf", "--compression", "massive"],
    )

    assert args.compression == "massive"
