import pybaseball
from django.core.management.base import BaseCommand

from hub.loading import integer, text, upsert
from hub.models import Player
from hub.names import name_key
from hub.sources.raw import cached


class Command(BaseCommand):
    help = "Load the player id crosswalk (MLBAM / FanGraphs / BBRef / Retrosheet) from the Chadwick register."

    def add_arguments(self, parser):
        parser.add_argument("--refresh", action="store_true", help="Re-download instead of using the raw file.")

    def handle(self, *args, **options):
        register = cached("chadwick", "register", pybaseball.chadwick_register, options["refresh"])
        register = register.dropna(subset=["key_mlbam"]).drop_duplicates("key_mlbam")

        # A FanGraphs id learned from an earlier name match must survive a reload
        # when the register still has none.
        known_fangraphs = dict(
            Player.objects.exclude(fangraphs_id=None).values_list("mlbam_id", "fangraphs_id")
        )

        players = []
        for row in register.itertuples(index=False):
            mlbam = int(row.key_mlbam)
            fangraphs = integer(row.key_fangraphs)
            if fangraphs is None or fangraphs <= 0:
                fangraphs = known_fangraphs.get(mlbam)
            first, last = text(row.name_first), text(row.name_last)
            full = f"{first} {last}".strip()
            players.append(
                Player(
                    mlbam_id=mlbam,
                    fangraphs_id=fangraphs,
                    bbref_id=text(row.key_bbref),
                    retro_id=text(row.key_retro),
                    name_first=first,
                    name_last=last,
                    name_full=full,
                    name_key=name_key(full),
                    first_year=integer(row.mlb_played_first),
                    last_year=integer(row.mlb_played_last),
                )
            )
        upsert(
            Player,
            players,
            unique_fields=["mlbam_id"],
            update_fields=[
                "fangraphs_id", "bbref_id", "retro_id", "name_first", "name_last",
                "name_full", "name_key", "first_year", "last_year",
            ],
        )
        self.stdout.write(self.style.SUCCESS(f"Players: {len(players)} loaded from the Chadwick register."))
