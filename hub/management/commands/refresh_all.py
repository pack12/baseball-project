from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Run every loader in dependency order, then rebuild the metrics."

    def add_arguments(self, parser):
        parser.add_argument("--seasons", help='e.g. "2026", "2024,2025" or "2015-2026". Default: 2015 to now.')
        parser.add_argument("--refresh", action="store_true", help="Re-download instead of using the raw files.")

    def handle(self, *args, **options):
        refresh, seasons = options["refresh"], options["seasons"]
        call_command("load_players", refresh=refresh)
        call_command("load_lahman", refresh=refresh)
        call_command("load_statcast", seasons=seasons, refresh=refresh)
        try:
            call_command("load_fangraphs", seasons=seasons, refresh=refresh)
        except CommandError as exc:
            # FanGraphs is the one source that may refuse us; the rest still stands.
            self.stderr.write(self.style.WARNING(f"Skipped FanGraphs: {exc}"))
        call_command("build_metrics")
