"""Tie rows from Statcast, FanGraphs and Lahman to one Player.

Ids are tried first, in order of how much we trust them. Only when no id hits
do we fall back to the name, and a name only counts when exactly one player
with that name was active around the season in question.
"""
from collections import defaultdict
from dataclasses import dataclass

from .models import Player
from .names import name_key

# How far outside a player's known first/last year a season may fall and still
# match by name. The register's years can lag a season behind.
YEAR_SLACK = 1


@dataclass
class Match:
    mlbam_id: int | None
    method: str  # the id type that hit, "name", or "" when unmatched
    reason: str = ""

    def __bool__(self):
        return self.mlbam_id is not None


class Crosswalk:
    def __init__(self):
        self._mlbam = set()
        self._fangraphs = {}
        self._bbref = {}
        self._retro = {}
        self._names = defaultdict(list)
        rows = Player.objects.values_list(
            "mlbam_id", "fangraphs_id", "bbref_id", "retro_id", "name_key", "first_year", "last_year"
        )
        for mlbam, fangraphs, bbref, retro, key, first, last in rows.iterator():
            self.add(mlbam, fangraphs, bbref, retro, key, first, last)

    def add(self, mlbam, fangraphs=None, bbref="", retro="", key="", first=None, last=None):
        self._mlbam.add(mlbam)
        if fangraphs is not None:
            self._fangraphs.setdefault(fangraphs, mlbam)
        if bbref:
            self._bbref.setdefault(bbref, mlbam)
        if retro:
            self._retro.setdefault(retro, mlbam)
        if key:
            self._names[key].append((mlbam, first, last))

    def resolve(self, *, mlbam=None, fangraphs=None, bbref=None, retro=None, name=None, season=None):
        if mlbam is not None and mlbam in self._mlbam:
            return Match(mlbam, "mlbam")
        for method, index, value in (
            ("fangraphs", self._fangraphs, fangraphs),
            ("bbref", self._bbref, bbref),
            ("retro", self._retro, retro),
        ):
            if value is not None and value in index:
                return Match(index[value], method)
        return self._by_name(name, season)

    def _by_name(self, name, season):
        key = name_key(name)
        if not key:
            return Match(None, "", "no id match and no name")
        candidates = [
            mlbam
            for mlbam, first, last in self._names.get(key, [])
            if season is None
            or first is None
            or last is None
            or first - YEAR_SLACK <= season <= last + YEAR_SLACK
        ]
        if len(candidates) == 1:
            return Match(candidates[0], "name")
        if not candidates:
            return Match(None, "", "no id or name match")
        return Match(None, "", f"name shared by {len(candidates)} players")
