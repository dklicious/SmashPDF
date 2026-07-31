"""Generate deterministic Windows version metadata for PyInstaller."""

from __future__ import annotations

import argparse
from pathlib import Path

from _version import __version__


def numeric_version(version: str) -> tuple[int, int, int, int]:
    parts = version.split(".")
    if not 1 <= len(parts) <= 4 or not all(part.isdecimal() for part in parts):
        raise ValueError(f"Windows metadata requires a numeric version: {version!r}")
    values = tuple(int(part) for part in parts)
    if any(value > 65535 for value in values):
        raise ValueError("Windows version components must be at most 65535.")
    return (*values, *(0 for _ in range(4 - len(values))))


def render_version_info(version: str = __version__) -> str:
    version_tuple = numeric_version(version)
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={version_tuple!r},
    prodvers={version_tuple!r},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', 'dklicious'),
          StringStruct('FileDescription', 'SmashPDF'),
          StringStruct('FileVersion', '{version}'),
          StringStruct('InternalName', 'SmashPDF'),
          StringStruct('LegalCopyright', 'Copyright (c) dklicious'),
          StringStruct('OriginalFilename', 'SmashPDF.exe'),
          StringStruct('ProductName', 'SmashPDF'),
          StringStruct('ProductVersion', '{version}')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_version_info(), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
