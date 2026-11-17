"""Raw file store: each download lands on disk as CSV before it is loaded.

Loaders read the file back when it already exists, so a re-run does not hit the
source again unless asked to refresh.
"""
from pathlib import Path

import pandas as pd
from django.conf import settings


class SourceUnavailable(Exception):
    """The upstream source gave us nothing usable."""


def raw_path(source: str, name: str) -> Path:
    return Path(settings.RAW_DATA_DIR) / source / f"{name}.csv"


def cached(source: str, name: str, fetch, refresh: bool = False) -> pd.DataFrame:
    path = raw_path(source, name)
    if refresh or not path.exists():
        df = fetch()
        if df.empty:
            # Nothing worth keeping (a season that has not started, say).
            return df
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
    # Always hand back the file's contents so a first run and a re-run see
    # identical dtypes.
    return pd.read_csv(path)
