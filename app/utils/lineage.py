"""Data lineage tracking for pipeline records."""

from __future__ import annotations

import pandas as pd


def add_lineage(
    data: pd.DataFrame,
    source: str = "CSV|API|DATABASE",
) -> pd.DataFrame:
    """Return a copy of ``data`` with the ``source`` lineage column set.

    Every row in the returned frame receives ``source`` as its lineage
    value, matching the canonical lineage format defined in
    ``DATA_CONTRACT.md``. The input frame is never modified. If a
    ``source`` column already exists, it is overwritten in the returned
    copy only.

    Args:
        data: Input records; rows, columns, and their order are preserved.
        source: Lineage value assigned to every row.

    Returns:
        A new DataFrame with the ``source`` column set to ``source``.

    Raises:
        ValueError: If ``source`` is not a non-empty string.
    """
    if not isinstance(source, str) or not source.strip():
        raise ValueError(f"source must be a non-empty string, got: {source!r}")

    result = data.copy(deep=True)
    result["source"] = source
    return result
