"""Contact Quality Score.

Three Statcast inputs, each turned into a z-score against that season's
qualified hitters, then blended:

    avg exit velocity   40%   how hard, on average
    hard-hit rate       30%   how often 95+ mph
    sweet-spot rate     30%   how often the launch angle is 8-32 degrees

Launch angle goes in as sweet-spot rate rather than the raw average because
average launch angle has no "more is better" direction: 12 and 25 degrees can
both be good, and a 45 degree average is a pop-up machine.

The blend is rescaled so 100 is the average qualified hitter and 15 points is
one standard deviation, the same way wRC+ style index stats read.
"""
import pandas as pd

WEIGHTS = {"avg_ev": 0.40, "hard_hit_pct": 0.30, "sweet_spot_pct": 0.30}
MIN_BBE = 100
SCALE_MEAN = 100
SCALE_SD = 15


def contact_quality(df: pd.DataFrame, min_bbe: int = MIN_BBE) -> pd.DataFrame:
    """Score one season of hitters.

    `df` needs `bbe` plus the three WEIGHTS columns. Returns only the hitters
    with at least `min_bbe` batted balls and complete inputs, with `<input>_z`,
    `score` and `percentile` columns added.
    """
    inputs = list(WEIGHTS)
    pool = df[df["bbe"] >= min_bbe].dropna(subset=inputs).copy()
    if len(pool) < 2:
        # No population to compare against.
        return pool.iloc[0:0].assign(score=[], percentile=[], **{f"{c}_z": [] for c in inputs})

    blend = 0
    for col, weight in WEIGHTS.items():
        sd = pool[col].std(ddof=0)
        pool[f"{col}_z"] = (pool[col] - pool[col].mean()) / sd if sd else 0.0
        blend = blend + weight * pool[f"{col}_z"]

    # The inputs are correlated, so the weighted sum is not unit variance yet.
    blend_sd = blend.std(ddof=0)
    pool["score"] = SCALE_MEAN + SCALE_SD * (blend / blend_sd if blend_sd else 0.0)
    pool["percentile"] = pool["score"].rank(pct=True) * 100
    return pool
