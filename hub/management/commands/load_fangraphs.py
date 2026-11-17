from django.core.management.base import BaseCommand, CommandError

from hub.loading import BATCH, integer, number, parse_seasons, text, upsert
from hub.matching import Crosswalk
from hub.models import FangraphsSeason, Player, UnmatchedRecord
from hub.sources import fangraphs
from hub.sources.raw import SourceUnavailable

INT_FIELDS = ["g", "pa", "hr"]
FLOAT_FIELDS = ["bb_pct", "k_pct", "iso", "babip", "woba", "wrc_plus", "war"]


class Command(BaseCommand):
    help = "Load FanGraphs batting stats, by scraping or from a CSV exported from fangraphs.com."

    def add_arguments(self, parser):
        parser.add_argument("--seasons", help='e.g. "2026", "2024,2025" or "2015-2026". Default: 2015 to now.')
        parser.add_argument("--csv", help="Leaderboard CSV exported from fangraphs.com (needs a single --seasons).")
        parser.add_argument("--refresh", action="store_true", help="Re-download instead of using the raw files.")

    def handle(self, *args, **options):
        seasons = parse_seasons(options["seasons"])
        if options["csv"] and len(seasons) != 1:
            raise CommandError("--csv holds one season; say which with --seasons YYYY.")

        crosswalk = Crosswalk()
        for season in seasons:
            try:
                if options["csv"]:
                    frame = fangraphs.csv_frame(options["csv"])
                else:
                    frame = fangraphs.season_frame(season, options["refresh"])
            except SourceUnavailable as exc:
                raise CommandError(f"FanGraphs {season}: {exc}") from exc
            self.load_season(season, frame, crosswalk)

    def load_season(self, season, frame, crosswalk):
        rows, unmatched, by_name, learned = [], [], 0, {}
        for record in frame.to_dict("records"):
            fangraphs_id = integer(_numeric(record.get("fangraphs_id")))
            match = crosswalk.resolve(
                mlbam=integer(_numeric(record.get("mlbam_id"))),
                fangraphs=fangraphs_id,
                name=text(record["name"]),
                season=season,
            )
            if not match:
                unmatched.append(
                    UnmatchedRecord(
                        source="fangraphs",
                        season=season,
                        source_id=text(record.get("fangraphs_id")),
                        name=text(record["name"]),
                        reason=match.reason,
                    )
                )
                continue
            if match.method != "fangraphs" and fangraphs_id is not None:
                # Matched some other way: remember the FanGraphs id for next time.
                learned[match.mlbam_id] = fangraphs_id
                by_name += match.method == "name"
            rows.append(
                FangraphsSeason(
                    player_id=match.mlbam_id,
                    season=season,
                    team=text(record.get("team")),
                    **{f: integer(_numeric(record.get(f))) for f in INT_FIELDS},
                    **{f: number(_numeric(record.get(f))) for f in FLOAT_FIELDS},
                )
            )

        # Two source rows can land on one player (a bad name match); keep the first.
        rows = list({row.player_id: row for row in reversed(rows)}.values())
        upsert(
            FangraphsSeason,
            rows,
            unique_fields=["player", "season"],
            update_fields=["team", *INT_FIELDS, *FLOAT_FIELDS],
        )
        for mlbam, fangraphs_id in learned.items():
            Player.objects.filter(pk=mlbam, fangraphs_id=None).update(fangraphs_id=fangraphs_id)
        UnmatchedRecord.objects.filter(source="fangraphs", season=season).delete()
        UnmatchedRecord.objects.bulk_create(unmatched, batch_size=BATCH)
        self.stdout.write(
            self.style.SUCCESS(
                f"FanGraphs {season}: {len(rows)} hitters ({by_name} matched by name), {len(unmatched)} unmatched."
            )
        )


def _numeric(value):
    """Ids and stats arrive as numbers, numeric strings, or junk like "sa3012345"."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
