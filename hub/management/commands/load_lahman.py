import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction

from hub.loading import BATCH, date, text, upsert
from hub.matching import Crosswalk
from hub.models import BattingSeason, Player, UnmatchedRecord
from hub.sources import lahman

# Appearances column -> position label.
POSITION_COLUMNS = {
    "G_p": "P", "G_c": "C", "G_1b": "1B", "G_2b": "2B", "G_3b": "3B",
    "G_ss": "SS", "G_lf": "LF", "G_cf": "CF", "G_rf": "RF", "G_dh": "DH",
}
BATTING_COLUMNS = {
    "G": "g", "AB": "ab", "R": "r", "H": "h", "2B": "doubles", "3B": "triples",
    "HR": "hr", "RBI": "rbi", "SB": "sb", "CS": "cs", "BB": "bb", "SO": "so",
    "HBP": "hbp", "SH": "sh", "SF": "sf",
}


def season_positions(appearances: pd.DataFrame) -> pd.Series:
    """(playerID, yearID) -> the position played most that season."""
    games = appearances[list(POSITION_COLUMNS)].apply(pd.to_numeric, errors="coerce").fillna(0)
    games = games.groupby([appearances["playerID"], appearances["yearID"]]).sum()
    games = games[games.sum(axis=1) > 0]
    return games.idxmax(axis=1).map(POSITION_COLUMNS)


def season_batting(batting: pd.DataFrame, teams: pd.DataFrame) -> pd.DataFrame:
    """One row per (playerID, yearID): stints summed, team shown as e.g. "2TM" when traded."""
    counts = batting[list(BATTING_COLUMNS)].apply(pd.to_numeric, errors="coerce").fillna(0).astype(int)
    keys = [batting["playerID"], batting["yearID"]]
    totals = counts.groupby(keys).sum().rename(columns=BATTING_COLUMNS)
    # Lahman's own team codes are dated (NYA, CHN); show the familiar ones.
    familiar = dict(zip(zip(teams["yearID"], teams["teamID"]), teams["teamIDBR"]))
    codes = pd.Series(
        [familiar.get(key, key[1]) for key in zip(batting["yearID"], batting["teamID"])], index=batting.index
    )
    totals["team"] = codes.groupby(keys).agg(
        lambda t: t.iloc[0] if t.nunique() == 1 else f"{t.nunique()}TM"
    )
    plate_appearances = totals[["ab", "bb", "hbp", "sh", "sf"]].sum(axis=1)
    return totals[plate_appearances > 0]


class Command(BaseCommand):
    help = "Load Lahman bio details, traditional batting lines and positions."

    def add_arguments(self, parser):
        parser.add_argument("--refresh", action="store_true", help="Re-download instead of using the raw files.")

    @transaction.atomic
    def handle(self, *args, **options):
        refresh = options["refresh"]
        people = lahman.people(refresh)
        positions = season_positions(lahman.appearances(refresh))
        batting = season_batting(lahman.batting(refresh), lahman.teams(refresh))

        crosswalk = Crosswalk()
        linked = {}  # Lahman playerID -> mlbam id
        bio = {}
        unmatched = []
        for row in people.itertuples(index=False):
            debut = date(row.debut)
            match = crosswalk.resolve(
                bbref=text(row.bbrefID) or text(row.playerID),
                retro=text(row.retroID),
                name=f"{text(row.nameFirst)} {text(row.nameLast)}",
                season=debut.year if debut else None,
            )
            if match and match.mlbam_id in bio:
                match.mlbam_id, match.reason = None, "player already linked to another Lahman id"
            if not match:
                unmatched.append(
                    UnmatchedRecord(
                        source="lahman",
                        source_id=row.playerID,
                        name=f"{text(row.nameFirst)} {text(row.nameLast)}".strip(),
                        reason=match.reason,
                    )
                )
                continue
            linked[row.playerID] = match.mlbam_id
            bio[match.mlbam_id] = (row.playerID, text(row.bats), text(row.throws), date(row.birthDate), debut)

        latest_position = (
            positions.reset_index(name="position").sort_values("yearID").groupby("playerID")["position"].last()
        )
        players = list(Player.objects.filter(pk__in=bio))
        for player in players:
            lahman_id, player.bats, player.throws, player.birth_date, player.debut = bio[player.pk]
            player.lahman_id = lahman_id
            player.primary_position = latest_position.get(lahman_id, "")
        Player.objects.bulk_update(
            players, ["lahman_id", "bats", "throws", "birth_date", "debut", "primary_position"], batch_size=BATCH
        )

        lines = []
        for (lahman_id, season), row in batting.iterrows():
            mlbam = linked.get(lahman_id)
            if mlbam is None:
                continue
            lines.append(
                BattingSeason(
                    player_id=mlbam,
                    season=season,
                    team=row["team"],
                    position=positions.get((lahman_id, season), ""),
                    **{field: int(row[field]) for field in BattingSeason.COUNTING_FIELDS},
                )
            )
        upsert(
            BattingSeason,
            lines,
            unique_fields=["player", "season"],
            update_fields=["team", "position", *BattingSeason.COUNTING_FIELDS],
        )

        UnmatchedRecord.objects.filter(source="lahman").delete()
        UnmatchedRecord.objects.bulk_create(unmatched, batch_size=BATCH)
        self.stdout.write(
            self.style.SUCCESS(
                f"Lahman: {len(linked)} people linked, {len(unmatched)} unmatched, "
                f"{len(lines)} batting seasons through {int(batting.index.get_level_values('yearID').max())}."
            )
        )
