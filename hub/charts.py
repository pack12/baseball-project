"""Geometry for the season-by-season line charts, drawn as inline SVG by `_trend.html`."""
import math

WIDTH, HEIGHT = 720, 250
LEFT, RIGHT, TOP, BOTTOM = 44, 20, 26, 30

# Beyond these counts the labels would run into each other.
MAX_VALUE_LABELS = 12
MAX_SEASON_LABELS = 14


def _nice_step(span: float, whole: bool, target: int = 5) -> float:
    """Smallest of 1, 2, 2.5, 5 x 10^n that splits `span` into at most `target` intervals."""
    raw = span / target
    magnitude = 10 ** math.floor(math.log10(raw))
    for multiple in (1, 2, 5, 10) if whole else (1, 2, 2.5, 5, 10):
        if multiple * magnitude >= raw:
            return max(multiple * magnitude, 1) if whole else multiple * magnitude


def trend(values, *, reference=None, floor=None, whole=False, label=str):
    """Lay out one line: `values` maps season -> number.

    `reference` draws a dashed comparison line and keeps it on the axis.
    `floor` pins the bottom of the axis (0 for counting stats).
    `whole` keeps the axis ticks on whole numbers.
    `label` formats a number for display.

    Returns None with fewer than two seasons: one point is not a trend.
    """
    if len(values) < 2:
        return None
    seasons = sorted(values)
    first, last = seasons[0], seasons[-1]

    extremes = list(values.values()) + ([reference] if reference is not None else [])
    low, high = min(extremes), max(extremes)
    pad = (high - low) * 0.08 or abs(high) * 0.1 or 1
    if floor is not None:
        low = floor
    else:
        # Nothing we chart goes negative, so padding must not push the axis below zero.
        low = max(low - pad, 0) if low >= 0 else low - pad
    high = high + pad
    step = _nice_step(high - low, whole)
    low_tick, high_tick = math.floor(low / step), math.ceil(high / step)
    low, high = low_tick * step, high_tick * step

    def x(season):
        return round(LEFT + (season - first) / (last - first) * (WIDTH - LEFT - RIGHT), 1)

    def y(value):
        return round(TOP + (high - value) / (high - low) * (HEIGHT - TOP - BOTTOM), 1)

    points = [
        {"season": s, "value": values[s], "label": label(values[s]), "x": x(s), "y": y(values[s]),
         "label_y": round(y(values[s]) - 9, 1), "labelled": True}
        for s in seasons
    ]
    if len(points) > MAX_VALUE_LABELS:
        # Long careers: only the ends and the extremes carry a number; the rest
        # are in the hover text and the table.
        keep = {first, last, max(values, key=values.get), min(values, key=values.get)}
        for point in points:
            point["labelled"] = point["season"] in keep

    # In a dip the line rises on both sides, so a number above the point would
    # sit on the line. Put it underneath when there is room above the axis.
    for before, point, after in zip([None] + points, points, points[1:] + [None]):
        neighbours = [p["value"] for p in (before, after) if p]
        if all(point["value"] < n for n in neighbours) and point["y"] + 20 <= HEIGHT - BOTTOM:
            point["label_y"] = round(point["y"] + 17, 1)

    # A missing season breaks the line rather than being drawn straight through.
    runs, run = [], [points[0]]
    for point in points[1:]:
        if point["season"] == run[-1]["season"] + 1:
            run.append(point)
        else:
            runs.append(run)
            run = [point]
    runs.append(run)

    every = math.ceil((last - first + 1) / MAX_SEASON_LABELS)
    return {
        "width": WIDTH,
        "height": HEIGHT,
        "left": LEFT,
        "right": WIDTH - RIGHT,
        "label_y": HEIGHT - BOTTOM + 18,
        "points": points,
        "lines": [" ".join(f"{p['x']},{p['y']}" for p in run) for run in runs if len(run) > 1],
        "y_ticks": [
            {"label": label(k * step), "y": y(k * step), "label_y": round(y(k * step) + 4, 1)}
            for k in range(low_tick, high_tick + 1)
        ],
        "x_ticks": [
            {"season": s, "x": x(s), "present": s in values}
            for s in range(first, last + 1)
            if (last - s) % every == 0
        ],
        "reference_y": y(reference) if reference is not None else None,
        "has_gap": len(runs) > 1,
        "summary": ", ".join(f"{p['season']}: {p['label']}" for p in points),
    }
