import csv
import io
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Gender
from app.models.profile import Profile
from app.services.profile_service import parse_name
from app.services.query_cache import invalidate_profile_query_cache
from app.services.utils import get_age_group, get_country_name

CHUNK_SIZE = 5_000
DECIMAL_PLACES = Decimal("0.01")
REQUIRED_COLUMNS = (
    "name",
    "gender",
    "gender_probability",
    "age",
    "country_id",
    "country_probability",
)
REPLACEMENT_CHARACTER = "\ufffd"


@dataclass
class IngestionSummary:
    total_rows: int = 0
    inserted: int = 0
    reasons: Counter[str] = field(default_factory=Counter)

    @property
    def skipped(self) -> int:
        return sum(self.reasons.values())

    def skip(self, reason: str) -> None:
        self.reasons[reason] += 1

    def to_response(self) -> dict[str, Any]:
        return {
            "status": "success",
            "total_rows": self.total_rows,
            "inserted": self.inserted,
            "skipped": self.skipped,
            "reasons": dict(self.reasons),
        }


def validate_profile_csv_row(
    row: dict[str, str | None],
    seen_names: set[str],
) -> tuple[dict[str, Any] | None, str | None]:
    if (
        None in row
        or has_broken_encoding(row)
        or any(row.get(column) is None for column in REQUIRED_COLUMNS)
    ):
        return None, "malformed_row"

    if any(not (row.get(column) or "").strip() for column in REQUIRED_COLUMNS):
        return None, "missing_fields"

    try:
        name = parse_name(row["name"] or "")
    except Exception:
        return None, "missing_fields"

    if name in seen_names:
        return None, "duplicate_name"

    gender_value = (row["gender"] or "").strip().lower()
    try:
        gender = Gender(gender_value).value
    except ValueError:
        return None, "invalid_gender"

    try:
        age = int((row["age"] or "").strip())
    except ValueError:
        return None, "invalid_age"
    if age < 0:
        return None, "invalid_age"

    gender_probability = parse_probability(row["gender_probability"])
    country_probability = parse_probability(row["country_probability"])
    if gender_probability is None or country_probability is None:
        return None, "invalid_probability"

    country_id = (row["country_id"] or "").strip().upper()
    country_name = get_country_name(country_id)
    if country_name is None:
        return None, "invalid_country"

    seen_names.add(name)
    return {
        "name": name,
        "gender": gender,
        "gender_probability": gender_probability,
        "age": age,
        "age_group": get_age_group(age).value,
        "country_id": country_id,
        "country_name": country_name,
        "country_probability": country_probability,
    }, None


def has_broken_encoding(row: dict[str | None, Any]) -> bool:
    return any(
        isinstance(value, str) and REPLACEMENT_CHARACTER in value
        for value in row.values()
    )


def parse_probability(value: str | None) -> Decimal | None:
    try:
        probability = Decimal((value or "").strip())
    except InvalidOperation:
        return None

    if probability < 0 or probability > 1:
        return None

    return probability.quantize(DECIMAL_PLACES)


async def ingest_profile_csv(
    db: AsyncSession,
    upload_file: UploadFile,
    chunk_size: int = CHUNK_SIZE,
) -> dict[str, Any]:
    summary = IngestionSummary()
    seen_names: set[str] = set()
    chunk: list[dict[str, Any]] = []

    upload_file.file.seek(0)
    text_stream = io.TextIOWrapper(
        upload_file.file,
        encoding="utf-8",
        errors="replace",
        newline="",
    )
    reader = csv.DictReader(text_stream, delimiter=",")

    for row in reader:
        summary.total_rows += 1
        valid_row, reason = validate_profile_csv_row(row, seen_names)
        if reason is not None:
            summary.skip(reason)
            continue

        if valid_row is not None:
            chunk.append(valid_row)

        if len(chunk) >= chunk_size:
            await insert_profile_chunk(db, chunk, summary)
            chunk.clear()

    if chunk:
        await insert_profile_chunk(db, chunk, summary)

    return summary.to_response()


async def insert_profile_chunk(
    db: AsyncSession,
    rows: list[dict[str, Any]],
    summary: IngestionSummary,
) -> None:
    names = [row["name"] for row in rows]
    existing_result = await db.execute(
        select(Profile.name).where(Profile.name.in_(names))
    )
    existing_names = set(existing_result.scalars().all())

    rows_to_insert = [row for row in rows if row["name"] not in existing_names]
    duplicate_count = len(rows) - len(rows_to_insert)
    if duplicate_count:
        summary.reasons["duplicate_name"] += duplicate_count

    if not rows_to_insert:
        return

    statement = (
        insert(Profile)
        .values(rows_to_insert)
        .on_conflict_do_nothing(index_elements=["name"])
    )
    result = await db.execute(statement)
    await db.commit()

    inserted = result.rowcount if result.rowcount is not None else len(rows_to_insert)
    inserted = max(inserted, 0)
    summary.inserted += inserted
    conflict_count = len(rows_to_insert) - inserted
    if conflict_count:
        summary.reasons["duplicate_name"] += conflict_count

    if inserted:
        await invalidate_profile_query_cache()
