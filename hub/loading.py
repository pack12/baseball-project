"""Small helpers shared by the load_* management commands."""
import datetime

import pandas as pd
from django.conf import settings

BATCH = 1000


def upsert(model, objs, unique_fields, update_fields):
    model.objects.bulk_create(
        objs,
        update_conflicts=True,
        unique_fields=unique_fields,
        update_fields=update_fields,
        batch_size=BATCH,
    )


def parse_seasons(text: str | None) -> list[int]:
    """"2024", "2022,2024" or "2015-2026"; every Statcast season when omitted."""
    if not text:
        return list(range(settings.FIRST_STATCAST_SEASON, datetime.date.today().year + 1))
    seasons = []
    for part in text.split(","):
        if "-" in part:
            start, end = part.split("-", 1)
            seasons.extend(range(int(start), int(end) + 1))
        else:
            seasons.append(int(part))
    return seasons


def text(value) -> str:
    return "" if pd.isna(value) else str(value).strip()


def integer(value):
    return None if pd.isna(value) else int(value)


def number(value):
    return None if pd.isna(value) else float(value)


def date(value):
    stamp = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(stamp) else stamp.date()
