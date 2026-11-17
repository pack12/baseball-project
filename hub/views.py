from django.db.models import Max, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from .charts import trend
from .metrics import MIN_BBE, SCALE_MEAN, WEIGHTS
from .models import BattingSeason, ContactQuality, Player, StatcastSeason
from .names import name_key
from .templatetags.hubfmt import rate

SEARCH_LIMIT = 50
OUTFIELD = ["LF", "CF", "RF"]
POSITIONS = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "OF", "DH"]

# Stats offered on the batting chart: (BattingSeason attribute, heading, is a rate stat).
BATTING_CHART_STATS = [
    ("g", "G", False), ("pa", "PA", False), ("ab", "AB", False), ("r", "R", False), ("h", "H", False),
    ("doubles", "2B", False), ("triples", "3B", False), ("hr", "HR", False), ("rbi", "RBI", False),
    ("sb", "SB", False), ("bb", "BB", False), ("so", "SO", False),
    ("avg", "AVG", True), ("obp", "OBP", True), ("slg", "SLG", True), ("ops", "OPS", True),
]
BATTING_CHART_DEFAULT = "hr"


def _batting_charts(batting):
    charts = []
    for key, title, is_rate in BATTING_CHART_STATS:
        # A rate stat is undefined (None) in a season without an at-bat.
        values = {row.season: getattr(row, key) for row in batting if getattr(row, key) is not None}
        if is_rate:
            layout = trend(values, label=rate)
        else:
            layout = trend(values, floor=0, whole=True, label=lambda v: str(round(v)))
        if layout:
            charts.append({"key": key, "title": title, "trend": layout, "selected": key == BATTING_CHART_DEFAULT})
    if charts and not any(chart["selected"] for chart in charts):
        charts[0]["selected"] = True
    return charts


def _latest_season():
    return ContactQuality.objects.aggregate(latest=Max("season"))["latest"]


def _leaders(season, position=None, limit=None):
    rows = ContactQuality.objects.filter(season=season).select_related("player")
    if position == "OF":
        rows = rows.filter(position__in=OUTFIELD)
    elif position:
        rows = rows.filter(position=position)
    rows = list(rows.order_by("-score")[:limit])  # limit=None: every qualified hitter
    statcast = {
        s.player_id: s
        for s in StatcastSeason.objects.filter(season=season, player_id__in=[r.player_id for r in rows])
    }
    for rank, row in enumerate(rows, start=1):
        row.rank = rank
        row.statcast = statcast.get(row.player_id)
    return rows


def home(request):
    season = _latest_season()
    return render(
        request,
        "hub/home.html",
        {"season": season, "leaders": _leaders(season, limit=10) if season else []},
    )


def search(request):
    query = request.GET.get("q", "").strip()
    players = []
    if query:
        # Every word typed must appear in the name, in any order, accents or not.
        match = Q()
        for token in name_key(query).split():
            match &= Q(name_key__contains=token)
        players = list(
            Player.objects.filter(match).order_by("-last_year", "name_last", "name_first")[: SEARCH_LIMIT + 1]
        )
        if len(players) == 1:
            return redirect("hub:player", mlbam_id=players[0].pk)
    return render(
        request,
        "hub/search.html",
        {"query": query, "players": players[:SEARCH_LIMIT], "truncated": len(players) > SEARCH_LIMIT},
    )


def player_detail(request, mlbam_id):
    player = get_object_or_404(Player, pk=mlbam_id)

    scores = {cq.season: cq for cq in player.contact_quality.all()}
    statcast = list(player.statcast_seasons.order_by("-season"))
    for row in statcast:
        row.contact_quality = scores.get(row.season)

    headline = scores[max(scores)] if scores else None
    if headline:
        peers = ContactQuality.objects.filter(season=headline.season)
        headline.rank = peers.filter(score__gt=headline.score).count() + 1
        headline.of = peers.count()
        if headline.position:
            at_position = peers.filter(position=headline.position)
            headline.position_rank = at_position.filter(score__gt=headline.score).count() + 1
            headline.position_of = at_position.count()
        headline.inputs = next(s for s in statcast if s.season == headline.season)

    batting = list(player.batting_seasons.order_by("-season"))
    career = None
    if len(batting) > 1:
        totals = player.batting_seasons.aggregate(**{f: Sum(f) for f in BattingSeason.COUNTING_FIELDS})
        career = BattingSeason(**totals)

    return render(
        request,
        "hub/player.html",
        {
            "player": player,
            "headline": headline,
            "trend": trend(
                {season: cq.score for season, cq in scores.items()},
                reference=SCALE_MEAN,
                whole=True,
                label=lambda v: str(round(v)),
            ),
            "batting_charts": _batting_charts(batting),
            "statcast": statcast,
            "batting": batting,
            "career": career,
            "fangraphs": list(player.fangraphs_seasons.order_by("-season")),
            "min_bbe": MIN_BBE,
        },
    )


def leaderboard(request):
    seasons = list(
        ContactQuality.objects.values_list("season", flat=True).distinct().order_by("-season")
    )
    try:
        season = int(request.GET.get("season", ""))
    except ValueError:
        season = None
    if season not in seasons:
        season = seasons[0] if seasons else None
    position = request.GET.get("pos", "").upper()
    if position not in POSITIONS:
        position = ""

    # Lahman trails the current season, so recent positions may be carried over.
    last_lahman = BattingSeason.objects.aggregate(latest=Max("season"))["latest"]
    return render(
        request,
        "hub/leaderboard.html",
        {
            "season": season,
            "seasons": seasons,
            "position": position,
            "positions": POSITIONS,
            "leaders": _leaders(season, position) if season else [],
            "min_bbe": MIN_BBE,
            "weights": {k: round(v * 100) for k, v in WEIGHTS.items()},
            "positions_carried_from": last_lahman if season and last_lahman and season > last_lahman else None,
        },
    )
