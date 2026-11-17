"""Season-level Statcast leaderboards from Baseball Savant, via pybaseball."""
import pandas as pd
import pybaseball

from .raw import cached

# Low enough to keep part-time hitters on their player page; the contact
# quality score applies its own, higher, threshold.
MIN_BBE = 25
MIN_PA = 25

_NAME_COL = "last_name, first_name"


def batted_ball(season: int, refresh: bool = False) -> pd.DataFrame:
    df = cached(
        "statcast",
        f"exitvelo_barrels_{season}",
        lambda: pybaseball.statcast_batter_exitvelo_barrels(season, MIN_BBE),
        refresh,
    )
    return df.rename(
        columns={
            _NAME_COL: "name",
            "player_id": "mlbam_id",
            "attempts": "bbe",
            "avg_hit_speed": "avg_ev",
            "max_hit_speed": "max_ev",
            "avg_hit_angle": "avg_la",
            "anglesweetspotpercent": "sweet_spot_pct",
            "ev95percent": "hard_hit_pct",
            "brl_percent": "barrel_pct",
        }
    )


def expected_stats(season: int, refresh: bool = False) -> pd.DataFrame:
    df = cached(
        "statcast",
        f"expected_stats_{season}",
        lambda: pybaseball.statcast_batter_expected_stats(season, MIN_PA),
        refresh,
    )
    return df.rename(
        columns={
            "player_id": "mlbam_id",
            "est_ba": "xba",
            "est_slg": "xslg",
            "est_woba": "xwoba",
        }
    )[["mlbam_id", "pa", "ba", "xba", "slg", "xslg", "woba", "xwoba"]]


def season_frame(season: int, refresh: bool = False) -> pd.DataFrame:
    """One row per hitter: batted-ball columns, with expected stats where Savant has them."""
    bb = batted_ball(season, refresh)
    if bb.empty:
        return bb
    return bb.merge(expected_stats(season, refresh), on="mlbam_id", how="left")
