"""Write pipeline DataFrames to configured CSV destinations."""

from pathlib import Path

import pandas as pd


def write_csv(dataframe: pd.DataFrame, output_path: str | Path) -> None:
    """Write UTF-8 CSV without an index, creating parent folders as needed.

    Existing files are overwritten. Pass a resolved output path from load_config;
    relative paths supplied directly are relative to the working directory.
    Invalid input types raise TypeError, blank paths raise ValueError, and
    directory destinations raise IsADirectoryError. Other I/O errors propagate.
    """
    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError("dataframe must be a pandas DataFrame")
    if not isinstance(output_path, (str, Path)):
        raise TypeError("output_path must be a string or pathlib.Path")
    if isinstance(output_path, str) and not output_path.strip():
        raise ValueError("output_path must not be empty")
    path = Path(output_path)
    if path.is_dir():
        raise IsADirectoryError(f"CSV output path is a directory: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(path, index=False, encoding="utf-8")
