from django.db import models


def _ratio(num, den):
    return num / den if den else None


class Player(models.Model):
    """One row per person, keyed on the MLBAM id.

    The other id columns are the crosswalk: Statcast speaks MLBAM, FanGraphs
    has its own id, and Lahman uses Baseball-Reference style ids.
    """

    mlbam_id = models.IntegerField(primary_key=True)
    fangraphs_id = models.IntegerField(null=True, blank=True, db_index=True)
    bbref_id = models.CharField(max_length=16, blank=True, db_index=True)
    retro_id = models.CharField(max_length=16, blank=True, db_index=True)
    lahman_id = models.CharField(max_length=16, blank=True, db_index=True)

    name_first = models.CharField(max_length=64, blank=True)
    name_last = models.CharField(max_length=64, blank=True)
    name_full = models.CharField(max_length=128)
    name_key = models.CharField(max_length=128, db_index=True)

    first_year = models.IntegerField(null=True, blank=True)
    last_year = models.IntegerField(null=True, blank=True)
    bats = models.CharField(max_length=1, blank=True)
    throws = models.CharField(max_length=1, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    debut = models.DateField(null=True, blank=True)
    primary_position = models.CharField(max_length=2, blank=True)

    class Meta:
        ordering = ["name_last", "name_first"]

    def __str__(self):
        return self.name_full


class BattingSeason(models.Model):
    """Traditional batting line for one season (Lahman), stints combined."""

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="batting_seasons")
    season = models.IntegerField()
    team = models.CharField(max_length=8, blank=True)
    position = models.CharField(max_length=2, blank=True)
    g = models.IntegerField(default=0)
    ab = models.IntegerField(default=0)
    r = models.IntegerField(default=0)
    h = models.IntegerField(default=0)
    doubles = models.IntegerField(default=0)
    triples = models.IntegerField(default=0)
    hr = models.IntegerField(default=0)
    rbi = models.IntegerField(default=0)
    sb = models.IntegerField(default=0)
    cs = models.IntegerField(default=0)
    bb = models.IntegerField(default=0)
    so = models.IntegerField(default=0)
    hbp = models.IntegerField(default=0)
    sh = models.IntegerField(default=0)
    sf = models.IntegerField(default=0)

    COUNTING_FIELDS = [
        "g", "ab", "r", "h", "doubles", "triples", "hr", "rbi",
        "sb", "cs", "bb", "so", "hbp", "sh", "sf",
    ]

    class Meta:
        ordering = ["season"]
        constraints = [
            models.UniqueConstraint(fields=["player", "season"], name="uniq_batting_player_season"),
        ]

    @property
    def pa(self):
        return self.ab + self.bb + self.hbp + self.sh + self.sf

    @property
    def avg(self):
        return _ratio(self.h, self.ab)

    @property
    def obp(self):
        return _ratio(self.h + self.bb + self.hbp, self.ab + self.bb + self.hbp + self.sf)

    @property
    def slg(self):
        total_bases = self.h + self.doubles + 2 * self.triples + 3 * self.hr
        return _ratio(total_bases, self.ab)

    @property
    def ops(self):
        if self.obp is None or self.slg is None:
            return None
        return self.obp + self.slg


class StatcastSeason(models.Model):
    """Season batted-ball and expected-stat aggregates from Baseball Savant."""

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="statcast_seasons")
    season = models.IntegerField()
    bbe = models.IntegerField()
    avg_ev = models.FloatField(null=True)
    max_ev = models.FloatField(null=True)
    avg_la = models.FloatField(null=True)
    sweet_spot_pct = models.FloatField(null=True)
    hard_hit_pct = models.FloatField(null=True)
    barrel_pct = models.FloatField(null=True)
    pa = models.IntegerField(null=True)
    ba = models.FloatField(null=True)
    xba = models.FloatField(null=True)
    slg = models.FloatField(null=True)
    xslg = models.FloatField(null=True)
    woba = models.FloatField(null=True)
    xwoba = models.FloatField(null=True)

    class Meta:
        ordering = ["season"]
        constraints = [
            models.UniqueConstraint(fields=["player", "season"], name="uniq_statcast_player_season"),
        ]


class FangraphsSeason(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="fangraphs_seasons")
    season = models.IntegerField()
    team = models.CharField(max_length=8, blank=True)
    g = models.IntegerField(null=True)
    pa = models.IntegerField(null=True)
    hr = models.IntegerField(null=True)
    bb_pct = models.FloatField(null=True)
    k_pct = models.FloatField(null=True)
    iso = models.FloatField(null=True)
    babip = models.FloatField(null=True)
    woba = models.FloatField(null=True)
    wrc_plus = models.FloatField(null=True)
    war = models.FloatField(null=True)

    class Meta:
        ordering = ["season"]
        constraints = [
            models.UniqueConstraint(fields=["player", "season"], name="uniq_fangraphs_player_season"),
        ]


class ContactQuality(models.Model):
    """Derived metric, rebuilt from StatcastSeason by `build_metrics`."""

    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="contact_quality")
    season = models.IntegerField()
    score = models.FloatField()
    percentile = models.FloatField()
    ev_z = models.FloatField()
    hard_hit_z = models.FloatField()
    sweet_spot_z = models.FloatField()
    position = models.CharField(max_length=2, blank=True, db_index=True)

    class Meta:
        ordering = ["-score"]
        constraints = [
            models.UniqueConstraint(fields=["player", "season"], name="uniq_cq_player_season"),
        ]


class UnmatchedRecord(models.Model):
    """A source row the crosswalk could not tie to a Player, kept for review."""

    source = models.CharField(max_length=16)
    season = models.IntegerField(null=True, blank=True)
    source_id = models.CharField(max_length=32, blank=True)
    name = models.CharField(max_length=128, blank=True)
    reason = models.CharField(max_length=64)

    class Meta:
        ordering = ["source", "season", "name"]
