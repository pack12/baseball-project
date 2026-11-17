import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction

from hub.loading import BATCH
from hub.metrics import MIN_BBE, contact_quality
from hub.models import BattingSeason, ContactQuality, Player, StatcastSeason


class Command(BaseCommand):
    help = "Rebuild the Contact Quality Score for every loaded Statcast season."

    @transaction.atomic
    def handle(self, *args, **options):
        primary = dict(Player.objects.exclude(primary_position="").values_list("mlbam_id", "primary_position"))
        seasons = StatcastSeason.objects.values_list("season", flat=True).distinct().order_by("season")
        ContactQuality.objects.all().delete()
        for season in seasons:
            frame = pd.DataFrame(
                StatcastSeason.objects.filter(season=season).values(
                    "player_id", "bbe", "avg_ev", "hard_hit_pct", "sweet_spot_pct"
                )
            )
            scored = contact_quality(frame)

            # Position played that season; for seasons Lahman does not cover yet,
            # fall back to the player's most recent one.
            played = dict(
                BattingSeason.objects.filter(season=season)
                .exclude(position="")
                .values_list("player_id", "position")
            )
            ContactQuality.objects.bulk_create(
                [
                    ContactQuality(
                        player_id=row.player_id,
                        season=season,
                        score=row.score,
                        percentile=row.percentile,
                        ev_z=row.avg_ev_z,
                        hard_hit_z=row.hard_hit_pct_z,
                        sweet_spot_z=row.sweet_spot_pct_z,
                        position=played.get(row.player_id) or primary.get(row.player_id, ""),
                    )
                    for row in scored.itertuples(index=False)
                ],
                batch_size=BATCH,
            )
            self.stdout.write(
                self.style.SUCCESS(f"Contact quality {season}: {len(scored)} hitters with {MIN_BBE}+ batted balls.")
            )
