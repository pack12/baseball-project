import tempfile
from pathlib import Path

import pandas as pd
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .management.commands.load_lahman import season_batting, season_positions
from .matching import Crosswalk
from .metrics import contact_quality
from .models import BattingSeason, ContactQuality, FangraphsSeason, Player, StatcastSeason, UnmatchedRecord
from .names import flip_last_first, name_key


def make_player(mlbam_id, name, **extra):
    return Player.objects.create(mlbam_id=mlbam_id, name_full=name, name_key=name_key(name), **extra)


class NameTests(TestCase):
    def test_name_key_strips_accents_punctuation_and_suffixes(self):
        self.assertEqual(name_key("Ronald Acuña Jr."), "ronald acuna")
        self.assertEqual(name_key("J.D. Martinez"), "jd martinez")
        self.assertEqual(name_key("Pete Crow-Armstrong"), "pete crow armstrong")
        self.assertEqual(name_key("Travis d'Arnaud"), "travis darnaud")
        self.assertEqual(name_key(None), "")

    def test_flip_last_first(self):
        self.assertEqual(flip_last_first("Crow-Armstrong, Pete"), "Pete Crow-Armstrong")
        self.assertEqual(flip_last_first("Witt Jr., Bobby"), "Bobby Witt Jr.")
        self.assertEqual(flip_last_first("Shohei Ohtani"), "Shohei Ohtani")


class CrosswalkTests(TestCase):
    def setUp(self):
        make_player(1, "José Ramírez", fangraphs_id=13510, bbref_id="ramirjo01", first_year=2013, last_year=2026)
        make_player(2, "José Ramírez", fangraphs_id=10171, bbref_id="ramirjo02", first_year=2014, last_year=2018)
        make_player(3, "Will Smith", retro_id="smitw003", first_year=2019, last_year=2026)
        self.crosswalk = Crosswalk()

    def test_ids_win_over_names(self):
        match = self.crosswalk.resolve(fangraphs=10171, name="Somebody Else", season=2016)
        self.assertEqual((match.mlbam_id, match.method), (2, "fangraphs"))
        self.assertEqual(self.crosswalk.resolve(bbref="ramirjo01").mlbam_id, 1)
        self.assertEqual(self.crosswalk.resolve(retro="smitw003").method, "retro")

    def test_unique_name_matches_without_an_id(self):
        match = self.crosswalk.resolve(fangraphs=999999, name="Will Smith", season=2024)
        self.assertEqual((match.mlbam_id, match.method), (3, "name"))

    def test_shared_name_is_settled_by_season_or_left_unmatched(self):
        # Only one José Ramírez was active in 2024.
        self.assertEqual(self.crosswalk.resolve(name="Jose Ramirez", season=2024).mlbam_id, 1)
        # Both were active in 2016: refuse to guess.
        match = self.crosswalk.resolve(name="Jose Ramirez", season=2016)
        self.assertFalse(match)
        self.assertEqual(match.reason, "name shared by 2 players")

    def test_unknown_player(self):
        match = self.crosswalk.resolve(mlbam=42, name="Nobody Here", season=2024)
        self.assertFalse(match)
        self.assertEqual(match.reason, "no id or name match")


class ContactQualityTests(TestCase):
    def frame(self):
        return pd.DataFrame(
            {
                "player_id": [1, 2, 3, 4, 5],
                "bbe": [400, 300, 200, 150, 40],
                "avg_ev": [95.0, 91.0, 89.0, 86.0, 99.0],
                "hard_hit_pct": [58.0, 45.0, 40.0, 28.0, 70.0],
                "sweet_spot_pct": [40.0, 35.0, 33.0, 30.0, 50.0],
            }
        )

    def test_scale_and_order(self):
        scored = contact_quality(self.frame(), min_bbe=100)
        # The 40-BBE hitter has the best raw numbers but too small a sample.
        self.assertEqual(list(scored["player_id"]), [1, 2, 3, 4])
        self.assertAlmostEqual(scored["score"].mean(), 100)
        self.assertAlmostEqual(scored["score"].std(ddof=0), 15)
        self.assertTrue(scored["score"].is_monotonic_decreasing)
        self.assertEqual(scored["percentile"].max(), 100)

    def test_missing_input_drops_the_hitter(self):
        frame = self.frame()
        frame.loc[0, "sweet_spot_pct"] = None
        self.assertNotIn(1, list(contact_quality(frame, min_bbe=100)["player_id"]))

    def test_too_few_hitters_gives_nothing(self):
        self.assertTrue(contact_quality(self.frame(), min_bbe=350).empty)


class LahmanShapingTests(TestCase):
    def test_stints_are_combined(self):
        batting = pd.DataFrame(
            {
                "playerID": ["a", "a", "b"],
                "yearID": [2024, 2024, 2024],
                "teamID": ["NYA", "CHN", "NYA"],
                "G": [50, 60, 10], "AB": [180, 200, 0], "R": [20, 30, 0], "H": [50, 60, 0],
                "2B": [10, 12, 0], "3B": [1, 0, 0], "HR": [5, 9, 0], "RBI": [20, None, 0],
                "SB": [1, 2, 0], "CS": [0, 1, 0], "BB": [15, 20, 0], "SO": [40, 50, 0],
                "HBP": [1, 2, 0], "SH": [0, 0, 0], "SF": [2, 1, 0],
            }
        )
        teams = pd.DataFrame({"yearID": [2024, 2024], "teamID": ["NYA", "CHN"], "teamIDBR": ["NYY", "CHC"]})
        seasons = season_batting(batting, teams)
        # Player b never came to the plate, so has no batting line.
        self.assertEqual(list(seasons.index), [("a", 2024)])
        row = seasons.loc[("a", 2024)]
        self.assertEqual((row["ab"], row["hr"], row["rbi"], row["team"]), (380, 14, 20, "2TM"))

    def test_position_is_where_most_games_were_played(self):
        appearances = pd.DataFrame(
            {
                "playerID": ["a", "a"], "yearID": [2024, 2024],
                "G_p": [0, 0], "G_c": [0, 0], "G_1b": [0, 0], "G_2b": [30, 5], "G_3b": [0, 0],
                "G_ss": [20, 40], "G_lf": [0, 0], "G_cf": [0, 0], "G_rf": [0, 0], "G_dh": [0, 0],
            }
        )
        self.assertEqual(season_positions(appearances).loc[("a", 2024)], "SS")


class FangraphsCsvTests(TestCase):
    def test_csv_rows_are_matched_and_ids_learned(self):
        make_player(10, "Aaron Judge", fangraphs_id=15640, first_year=2016, last_year=2026)
        make_player(11, "Bobby Witt Jr.", first_year=2022, last_year=2026)  # no FanGraphs id yet
        csv = Path(tempfile.mkdtemp()) / "fg.csv"
        csv.write_text(
            "Name,Team,G,PA,HR,BB%,K%,ISO,BABIP,wOBA,wRC+,WAR,PlayerId\n"
            "Aaron Judge,NYY,152,679,53,18.3%,23.6%,.357,.376,.463,204,10.1,15640\n"
            "Bobby Witt,KCR,157,687,23,0.071,0.182,.206,.330,.361,130,8.0,25764\n"
            "Mystery Man,FA,1,30,0,0.1,0.2,.100,.300,.300,90,0.1,sa999\n"
        )
        call_command("load_fangraphs", seasons="2025", csv=str(csv), verbosity=0)

        judge = FangraphsSeason.objects.get(player_id=10, season=2025)
        self.assertEqual((judge.hr, judge.wrc_plus, judge.team), (53, 204, "NYY"))
        self.assertAlmostEqual(judge.bb_pct, 0.183)
        self.assertAlmostEqual(FangraphsSeason.objects.get(player_id=11).bb_pct, 0.071)
        # Witt matched on name, and the hub now knows his FanGraphs id.
        self.assertEqual(Player.objects.get(pk=11).fangraphs_id, 25764)
        unmatched = UnmatchedRecord.objects.get(source="fangraphs")
        self.assertEqual((unmatched.name, unmatched.season), ("Mystery Man", 2025))


class ViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        judge = make_player(592450, "Aaron Judge", primary_position="RF", first_year=2016, last_year=2026)
        soto = make_player(665742, "Juan Soto", primary_position="LF", first_year=2018, last_year=2026)
        make_player(1, "Joe Judge", first_year=1915, last_year=1934)
        for player, score, ev in ((judge, 131.0, 94.0), (soto, 125.0, 93.0)):
            StatcastSeason.objects.create(
                player=player, season=2026, bbe=300, avg_ev=ev, hard_hit_pct=55.0, sweet_spot_pct=36.0, xwoba=0.4
            )
            ContactQuality.objects.create(
                player=player, season=2026, score=score, percentile=99, ev_z=2, hard_hit_z=2, sweet_spot_z=0.1,
                position=player.primary_position,
            )
        for season, hr in ((2024, 58), (2025, 53)):
            BattingSeason.objects.create(player=judge, season=season, team="NYY", g=150, ab=550, h=180, hr=hr)

    def test_home_lists_leaders(self):
        response = self.client.get(reverse("hub:home"))
        self.assertContains(response, "Contact Quality leaders, 2026")
        self.assertContains(response, "Juan Soto")

    def test_search_goes_straight_to_a_single_match(self):
        response = self.client.get(reverse("hub:search"), {"q": "soto"})
        self.assertRedirects(response, reverse("hub:player", args=[665742]))

    def test_search_lists_several_matches_most_recent_first(self):
        response = self.client.get(reverse("hub:search"), {"q": "JUDGE"})
        self.assertEqual([p.pk for p in response.context["players"]], [592450, 1])

    def test_player_page_shows_every_section(self):
        response = self.client.get(reverse("hub:player", args=[592450]))
        self.assertContains(response, "#1 of 2 hitters")
        self.assertContains(response, "#1 of 1 at")
        self.assertEqual(response.context["career"].hr, 111)
        self.assertContains(response, "No FanGraphs seasons loaded")

    def test_player_without_data_still_renders(self):
        response = self.client.get(reverse("hub:player", args=[1]))
        self.assertContains(response, "No score")
        self.assertEqual(self.client.get(reverse("hub:player", args=[999])).status_code, 404)

    def test_leaderboard_filters_by_position(self):
        url = reverse("hub:leaderboard")
        names = lambda r: [row.player.name_full for row in r.context["leaders"]]
        self.assertEqual(names(self.client.get(url)), ["Aaron Judge", "Juan Soto"])
        self.assertEqual(names(self.client.get(url, {"pos": "LF"})), ["Juan Soto"])
        self.assertEqual(names(self.client.get(url, {"pos": "of", "season": "2026"})), ["Aaron Judge", "Juan Soto"])
        self.assertEqual(names(self.client.get(url, {"pos": "C"})), [])
        self.assertEqual(self.client.get(url, {"season": "junk", "pos": "junk"}).status_code, 200)
