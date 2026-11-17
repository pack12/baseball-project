"""FanGraphs batting leaderboards.

Two ways in: pybaseball's scraper, or a CSV exported by hand from the
FanGraphs leaderboard page ("Export Data"). Both end up as the same frame.
"""
import pandas as pd
import pybaseball

from .raw import SourceUnavailable, cached

MIN_PA = 25

_COLUMNS = {
    "IDfg": "fangraphs_id",
    "PlayerId": "fangraphs_id",
    "playerid": "fangraphs_id",
    "MLBAMID": "mlbam_id",
    "Name": "name",
    "Team": "team",
    "G": "g",
    "PA": "pa",
    "HR": "hr",
    "BB%": "bb_pct",
    "K%": "k_pct",
    "ISO": "iso",
    "BABIP": "babip",
    "wOBA": "woba",
    "wRC+": "wrc_plus",
    "WAR": "war",
}


def _scrape(season: int) -> pd.DataFrame:
    try:
        df = pybaseball.batting_stats(season, qual=MIN_PA)
    except Exception as exc:
        raise SourceUnavailable(f"FanGraphs request failed: {exc}") from exc
    if df.empty or "Name" not in df.columns:
        # What a blocked request looks like from pybaseball: no error, no rows.
        raise SourceUnavailable(
            "FanGraphs returned no data. It is refusing pybaseball's requests; "
            "export the leaderboard as CSV from fangraphs.com and load it with --csv."
        )
    return df


def _tidy(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=_COLUMNS)
    df = df.loc[:, ~df.columns.duplicated()]
    if "fangraphs_id" not in df.columns or "name" not in df.columns:
        raise SourceUnavailable("Not a FanGraphs batting leaderboard: no player id / name column.")
    for col in ("bb_pct", "k_pct"):
        if col in df.columns:
            # Scraped pages give 0.123, some exports give "12.3%" or 12.3.
            values = pd.to_numeric(df[col].astype(str).str.rstrip(" %"), errors="coerce")
            df[col] = values.where(values <= 1, values / 100)
    return df[[c for c in dict.fromkeys(_COLUMNS.values()) if c in df.columns]]


def season_frame(season: int, refresh: bool = False) -> pd.DataFrame:
    return _tidy(cached("fangraphs", f"batting_{season}", lambda: _scrape(season), refresh))


def csv_frame(path: str) -> pd.DataFrame:
    return _tidy(pd.read_csv(path, encoding="utf-8-sig"))
