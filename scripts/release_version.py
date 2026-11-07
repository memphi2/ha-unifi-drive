"""Canonical stable and prerelease versions shared by release checks."""

from __future__ import annotations

import re

VERSION_PATTERN = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:(?:b|rc)[1-9][0-9]*)?"


def validate_version(value: str) -> str:
    """Accept canonical X.Y.Z, X.Y.ZbN and X.Y.ZrcN versions only."""
    if not isinstance(value, str) or not re.fullmatch(VERSION_PATTERN, value):
        raise ValueError("expected X.Y.Z, X.Y.ZbN or X.Y.ZrcN")
    return value


def is_prerelease(tag: str) -> bool:
    """Determine the release channel only after validating the complete tag."""
    if not tag.startswith("v"):
        raise ValueError("release tag must start with v")
    version = validate_version(tag[1:])
    return re.search(r"(?:b|rc)[0-9]+$", version) is not None
