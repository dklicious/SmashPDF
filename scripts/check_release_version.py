"""Fail a release build when its Git tag does not match the app version."""

from __future__ import annotations

import argparse

from _version import __version__


def validate_release_tag(tag: str) -> None:
    expected = f"v{__version__}"
    if tag != expected:
        raise ValueError(
            f"Release tag {tag!r} does not match application version {expected!r}."
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tag", help="Git release tag, for example v1.2.3")
    args = parser.parse_args()
    validate_release_tag(args.tag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
