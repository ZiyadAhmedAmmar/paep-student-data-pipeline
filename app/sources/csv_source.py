"""CSV file source."""

from pathlib import Path

import pandas as pd

from app.sources.base_source import BaseSource


class CSVSource(BaseSource):
    """Extract raw records from a CSV file."""

    def __init__(self, file_path: str | Path) -> None:
        self.file_path = Path(file_path)

    def extract(self) -> pd.DataFrame:
        if not self.file_path.exists():
            raise FileNotFoundError(
                f"Input file does not exist: {self.file_path}"
            )

        df = pd.read_csv(self.file_path)

        if df.empty:
            raise ValueError("Input dataset is empty")


        return df


def load_data(file_path: str | Path) -> pd.DataFrame:
    """Load the raw CSV file."""
    return CSVSource(file_path).extract()
