from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_release_version import validate_release_tag
from scripts.generate_version_info import numeric_version, render_version_info


def test_release_tag_must_match_canonical_version() -> None:
    validate_release_tag("v1.2.3")

    with pytest.raises(ValueError, match="does not match"):
        validate_release_tag("v1.2.2")


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("1", (1, 0, 0, 0)),
        ("1.2", (1, 2, 0, 0)),
        ("1.2.3", (1, 2, 3, 0)),
        ("1.2.3.4", (1, 2, 3, 4)),
    ],
)
def test_numeric_windows_versions(
    version: str,
    expected: tuple[int, int, int, int],
) -> None:
    assert numeric_version(version) == expected


@pytest.mark.parametrize(
    "version",
    ["", "1.2.3.4.5", "1.2.beta", "65536.0.0"],
)
def test_invalid_windows_versions_are_rejected(version: str) -> None:
    with pytest.raises(ValueError):
        numeric_version(version)


def test_generated_windows_metadata_contains_version_and_brand() -> None:
    metadata = render_version_info()

    assert "filevers=(1, 2, 3, 0)" in metadata
    assert "StringStruct('FileVersion', '1.2.3')" in metadata
    assert "StringStruct('ProductName', 'SmashPDF')" in metadata
    assert "StringStruct('OriginalFilename', 'SmashPDF.exe')" in metadata


def test_pyproject_uses_dynamic_version() -> None:
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    contents = pyproject.read_text(encoding="utf-8")

    assert 'dynamic = ["version"]' in contents
    assert 'version = { attr = "_version.__version__" }' in contents
