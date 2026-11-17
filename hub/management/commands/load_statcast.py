from django.core.management.base import BaseCommand

from hub.loading import integer, number, parse_seasons, upsert
from hub.matching import Crosswalk
from hub.models import Player, StatcastSeason
from hub.names import flip_last_first, name_key
from hub.sources import statcast

FLOAT_FIELDS = [
    "avg_ev", "max_ev", "avg_la", "sweet_spot_pct", "hard_hit_pct", "barrel_pct",
    "ba", "xba", "slg", "xslg", "woba", "xwoba",
]


class Command(BaseCommand):
    help = "Load season Statcast batted-ball and expected stats from Baseball Savant."

    def add_arguments(self, parser):
        parser.add_argument("--seasons", help='e.g. "2026", "2024,2025" or "2015-2026". Default: 2015 to now.')
        parser.add_argument("--refresh", action="store_true", help="Re-download instead of using the raw files.")

    def handle(self, *args, **options):
        crosswalk = Crosswalk()
        for season in parse_seasons(options["seasons"]):
            frame = statcast.season_frame(season, options["refresh"])
            if frame.empty:
                self.stdout.write(f"Statcast {season}: no data.")
                continue

            # Savant is the authority on MLBAM ids, so a hitter the register has
            # not caught up with yet becomes a new Player rather than a mismatch.
            newcomers = []
            for row in frame.itertuples(index=False):
                if crosswalk.resolve(mlbam=int(row.mlbam_id)):
                    continue
                full = flip_last_first(row.name)
                first, _, last = full.partition(" ")
                newcomers.append(
                    Player(
                        mlbam_id=int(row.mlbam_id),
                        name_first=first,
                        name_last=last,
                        name_full=full,
                        name_key=name_key(full),
                        first_year=season,
                        last_year=season,
                    )
                )
                crosswalk.add(int(row.mlbam_id), key=name_key(full), first=season, last=season)
            Player.objects.bulk_create(newcomers)

            rows = [
                StatcastSeason(
                    player_id=int(row.mlbam_id),
                    season=season,
                    bbe=int(row.bbe),
                    pa=integer(row.pa),
                    **{field: number(getattr(row, field)) for field in FLOAT_FIELDS},
                )
                for row in frame.itertuples(index=False)
            ]
            upsert(
                StatcastSeason,
                rows,
                unique_fields=["player", "season"],
                update_fields=["bbe", "pa", *FLOAT_FIELDS],
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Statcast {season}: {len(rows)} hitters, {len(newcomers)} not yet in the register."
                )
            )
