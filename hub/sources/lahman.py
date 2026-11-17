"""Lahman database tables.

pybaseball's own Lahman loader points at chadwickbureau/baseballdatabank, a
GitHub repo that no longer exists, so `pybaseball.lahman.*` fails. The same
tables are published, and kept current, in the Lahman R package; we read its
.RData files directly instead.
"""
import pandas as pd
import pyreadr
import requests
from django.conf import settings

from .raw import cached

RDATA_URL = "https://raw.githubusercontent.com/cdalzell/Lahman/master/data/{table}.RData"


def _fetch(table: str) -> pd.DataFrame:
    response = requests.get(RDATA_URL.format(table=table), timeout=60)
    response.raise_for_status()
    rdata = settings.RAW_DATA_DIR / "lahman" / f"{table}.RData"
    rdata.parent.mkdir(parents=True, exist_ok=True)
    rdata.write_bytes(response.content)
    return pyreadr.read_r(str(rdata))[table]


def table(name: str, refresh: bool = False) -> pd.DataFrame:
    return cached("lahman", name, lambda: _fetch(name), refresh)


def people(refresh: bool = False) -> pd.DataFrame:
    return table("People", refresh)


def batting(refresh: bool = False) -> pd.DataFrame:
    # R cannot start a column name with a digit, so 2B/3B arrive as X2B/X3B.
    return table("Batting", refresh).rename(columns={"X2B": "2B", "X3B": "3B"})


def appearances(refresh: bool = False) -> pd.DataFrame:
    return table("Appearances", refresh)


def teams(refresh: bool = False) -> pd.DataFrame:
    return table("Teams", refresh)
