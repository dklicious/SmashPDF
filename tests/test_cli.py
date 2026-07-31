from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

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

    with pytest.raises(SystemExit, match="one input PDF"):
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
