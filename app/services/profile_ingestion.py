import asyncio
import csv
import io
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import Gender
from app.models.profile import Profile
from app.services.profile_service import parse_name
from app.services.query_cache import invalidate_profile_query_cache
from app.services.utils import get_age_group, get_country_name

CHUNK_SIZE = 5_000
UPLOAD_CONCURRENCY_LIMIT = 2
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
STAGING_TABLE_PREFIX = "profile_upload_stage_"
STAGING_COLUMNS = (
    "name",
    "gender",
    "gender_probability",
    "age",
    "age_group",
    "country_id",
    "country_name",
    "country_probability",
)
_upload_semaphore = asyncio.Semaphore(UPLOAD_CONCURRENCY_LIMIT)


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
    async with _upload_semaphore:
        return await _ingest_profile_csv(db, upload_file, chunk_size)


async def _ingest_profile_csv(
    db: AsyncSession,
    upload_file: UploadFile,
    chunk_size: int,
) -> dict[str, Any]:
    bind = getattr(db, "bind", None)
    if bind is not None:
        async with bind.connect() as connection:
            return await ingest_profile_csv_on_connection(
                connection,
                upload_file,
                chunk_size,
            )

    connection = await db.connection()
    return await ingest_profile_csv_on_connection(connection, upload_file, chunk_size)


async def ingest_profile_csv_on_connection(
    connection: Any,
    upload_file: UploadFile,
    chunk_size: int,
) -> dict[str, Any]:
    summary = IngestionSummary()
    seen_names: set[str] = set()
    chunk: list[dict[str, Any]] = []
    staging_table = f"{STAGING_TABLE_PREFIX}{uuid4().hex}"

    try:
        await create_profile_upload_staging_table(connection, staging_table)

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
                await insert_profile_chunk(connection, chunk, summary, staging_table)
                chunk.clear()

        if chunk:
            await insert_profile_chunk(connection, chunk, summary, staging_table)
    finally:
        await drop_profile_upload_staging_table(connection, staging_table)

    return summary.to_response()


def quote_identifier(identifier: str) -> str:
    return f'"{identifier}"'


async def create_profile_upload_staging_table(
    connection: Any,
    staging_table: str,
) -> None:
    await connection.execute(
        text(
            f"""
            CREATE TABLE {quote_identifier(staging_table)} (
                name VARCHAR NOT NULL,
                gender gender NOT NULL,
                gender_probability NUMERIC(3, 2) NOT NULL,
                age INTEGER NOT NULL,
                age_group agegroup NOT NULL,
                country_id VARCHAR(2) NOT NULL,
                country_name VARCHAR NOT NULL,
                country_probability NUMERIC(3, 2) NOT NULL
            )
            """
        )
    )
    await connection.commit()


async def drop_profile_upload_staging_table(
    connection: Any,
    staging_table: str,
) -> None:
    try:
        if connection.in_transaction():
            await connection.rollback()
        await connection.execute(
            text(f"DROP TABLE IF EXISTS {quote_identifier(staging_table)}")
        )
        await connection.commit()
    except Exception:
        await connection.rollback()


async def insert_profile_chunk(
    connection: Any,
    rows: list[dict[str, Any]],
    summary: IngestionSummary,
    staging_table: str,
) -> None:
    if not rows:
        return

    await copy_profile_rows_to_staging(connection, rows, staging_table)
    inserted = await merge_profile_upload_staging(connection, staging_table)
    await connection.execute(
        text(f"TRUNCATE TABLE {quote_identifier(staging_table)}")
    )
    await connection.commit()

    summary.inserted += inserted
    conflict_count = len(rows) - inserted
    if conflict_count:
        summary.reasons["duplicate_name"] += conflict_count

    if inserted:
        await invalidate_profile_query_cache()


async def copy_profile_rows_to_staging(
    connection: Any,
    rows: list[dict[str, Any]],
    staging_table: str,
) -> None:
    raw_connection = await connection.get_raw_connection()
    driver_connection = raw_connection.driver_connection
    records = [tuple(row[column] for column in STAGING_COLUMNS) for row in rows]
    await driver_connection.copy_records_to_table(
        staging_table,
        records=records,
        columns=STAGING_COLUMNS,
    )


async def merge_profile_upload_staging(connection: Any, staging_table: str) -> int:
    result = await connection.execute(
        text(
            f"""
            WITH inserted AS (
                INSERT INTO {Profile.__tablename__} (
                    name,
                    gender,
                    gender_probability,
                    age,
                    age_group,
                    country_id,
                    country_name,
                    country_probability
                )
                SELECT
                    name,
                    gender,
                    gender_probability,
                    age,
                    age_group,
                    country_id,
                    country_name,
                    country_probability
                FROM {quote_identifier(staging_table)}
                ON CONFLICT (name) DO NOTHING
                RETURNING name
            )
            SELECT COUNT(*) FROM inserted
            """
        )
    )
    return int(result.scalar_one())
