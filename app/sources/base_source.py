"""Shared interface for the CSV, HTTP API, and SQLite sources."""

from abc import ABC, abstractmethod

import pandas as pd


class BaseSource(ABC):
    """Common contract for every extractable source."""

    @abstractmethod
    def extract(self) -> pd.DataFrame:
        """Return the raw source records as a DataFrame."""
