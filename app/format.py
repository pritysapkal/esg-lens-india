"""One place for how numbers are written on every page (thousands separators, fixed decimals,
units). Thin wrappers over labels.fmt, so a figure reads the same as it always did."""

from __future__ import annotations

from app import labels


def count(value) -> str:
    return labels.fmt(value, 0)


def intensity(value) -> str:
    """Intensities: 1 decimal (2 in tables that compare small values)."""
    return labels.fmt(value, 1)


def intensity2(value) -> str:
    return labels.fmt(value, 2)


def pct(value, digits: int = 1) -> str:
    return labels.fmt(value, digits, "%")


def score(value) -> str:
    return labels.fmt(value, 1)
