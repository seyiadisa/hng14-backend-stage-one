import asyncio
from decimal import Decimal
from io import BytesIO

from fastapi import UploadFile

from app.models.enums import AgeGroup, Gender
from app.services import profile_ingestion
from app.services.profile_ingestion import ingest_profile_csv, validate_profile_csv_row


class FakeCountResult:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


class FakeRawConnection:
    def __init__(self, connection):
        self.driver_connection = connection


class FakeConnection:
    def __init__(self, existing_names=None):
        self.existing_names = set(existing_names or [])
        self.staging_rows = []
        self.copy_calls = []
        self.executed_sql = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, statement):
        sql = str(statement)
        self.executed_sql.append(sql)

        if "TRUNCATE TABLE" in sql:
            self.staging_rows.clear()

        if "SELECT COUNT(*) FROM inserted" in sql:
            inserted = 0
            for row in self.staging_rows:
                name = row[0]
                if name in self.existing_names:
                    continue
                self.existing_names.add(name)
                inserted += 1
            return FakeCountResult(inserted)

        return FakeCountResult(0)

    async def get_raw_connection(self):
        return FakeRawConnection(self)

    async def copy_records_to_table(self, table_name, records, columns):
        copied_records = list(records)
        self.copy_calls.append(
            {
                "table_name": table_name,
                "records": copied_records,
                "columns": columns,
            }
        )
        self.staging_rows.extend(copied_records)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    def in_transaction(self):
        return False


class FakeDB:
    def __init__(self, existing_names=None):
        self.connection_obj = FakeConnection(existing_names)

    async def connection(self):
        return self.connection_obj


def valid_row(**overrides):
    row = {
        "name": " Ada ",
        "gender": "female",
        "gender_probability": "0.987",
        "age": "31",
        "country_id": "ng",
        "country_probability": "0.76",
    }
    row.update(overrides)
    return row


def test_validate_profile_csv_row_prepares_valid_profile_data():
    seen_names = set()
    result, reason = validate_profile_csv_row(valid_row(), seen_names)

    assert reason is None
    assert result == {
        "name": "ada",
        "gender": Gender.female.value,
        "gender_probability": Decimal("0.99"),
        "age": 31,
        "age_group": AgeGroup.adult.value,
        "country_id": "NG",
        "country_name": "Nigeria",
        "country_probability": Decimal("0.76"),
    }
    assert seen_names == {"ada"}


def test_validate_profile_csv_row_skips_missing_fields():
    result, reason = validate_profile_csv_row(valid_row(name=" "), set())

    assert result is None
    assert reason == "missing_fields"


def test_validate_profile_csv_row_skips_invalid_age():
    result, reason = validate_profile_csv_row(valid_row(age="-1"), set())

    assert result is None
    assert reason == "invalid_age"


def test_validate_profile_csv_row_skips_invalid_gender():
    result, reason = validate_profile_csv_row(valid_row(gender="unknown"), set())

    assert result is None
    assert reason == "invalid_gender"


def test_validate_profile_csv_row_skips_invalid_probability():
    result, reason = validate_profile_csv_row(
        valid_row(gender_probability="1.25"),
        set(),
    )

    assert result is None
    assert reason == "invalid_probability"


def test_validate_profile_csv_row_skips_invalid_country():
    result, reason = validate_profile_csv_row(valid_row(country_id="xx"), set())

    assert result is None
    assert reason == "invalid_country"


def test_validate_profile_csv_row_skips_duplicate_name_in_file():
    seen_names = {"ada"}
    result, reason = validate_profile_csv_row(valid_row(), seen_names)

    assert result is None
    assert reason == "duplicate_name"


def test_validate_profile_csv_row_skips_malformed_rows():
    result, reason = validate_profile_csv_row({None: ["extra"]}, set())

    assert result is None
    assert reason == "malformed_row"


def test_validate_profile_csv_row_skips_short_rows_as_malformed():
    row = valid_row()
    row.pop("country_probability")
    result, reason = validate_profile_csv_row(row, set())

    assert result is None
    assert reason == "malformed_row"


def test_ingest_profile_csv_returns_summary_for_mixed_rows(monkeypatch):
    async def scenario(monkeypatch):
        invalidations = 0

        async def fake_invalidate():
            nonlocal invalidations
            invalidations += 1

        monkeypatch.setattr(
            profile_ingestion,
            "invalidate_profile_query_cache",
            fake_invalidate,
        )
        upload = UploadFile(
            file=BytesIO(csv_data.encode("utf-8")),
            filename="profiles.csv",
        )
        db = FakeDB(existing_names={"existing"})

        summary = await ingest_profile_csv(db, upload, chunk_size=2)

        assert summary == {
            "status": "success",
            "total_rows": 7,
            "inserted": 1,
            "skipped": 6,
            "reasons": {
                "duplicate_name": 2,
                "invalid_age": 1,
                "invalid_gender": 1,
                "invalid_country": 1,
                "missing_fields": 1,
            },
        }
        assert db.connection_obj.commits == 3
        assert invalidations == 1
        assert len(db.connection_obj.copy_calls) == 1
        assert db.connection_obj.copy_calls[0]["table_name"].startswith(
            "profile_upload_stage_"
        )
        assert all(
            "VALUES" not in sql.upper()
            for sql in db.connection_obj.executed_sql
        )

    csv_data = "\n".join(
        [
            "name,gender,gender_probability,age,country_id,country_probability",
            "Ada,female,0.98,31,NG,0.76",
            "Ada,female,0.98,31,NG,0.76",
            "Existing,male,0.80,20,US,0.60",
            "BadAge,female,0.98,-1,NG,0.76",
            "BadGender,unknown,0.98,31,NG,0.76",
            "BadCountry,female,0.98,31,XX,0.76",
            ",female,0.98,31,NG,0.76",
        ]
    )
    asyncio.run(scenario(monkeypatch))


def test_ingest_profile_csv_commits_and_invalidates_per_inserted_chunk(monkeypatch):
    async def scenario():
        invalidations = 0

        async def fake_invalidate():
            nonlocal invalidations
            invalidations += 1

        monkeypatch.setattr(
            profile_ingestion,
            "invalidate_profile_query_cache",
            fake_invalidate,
        )
        upload = UploadFile(
            file=BytesIO(csv_data.encode("utf-8")),
            filename="profiles.csv",
        )
        db = FakeDB()

        summary = await ingest_profile_csv(db, upload, chunk_size=2)

        assert summary["inserted"] == 3
        assert summary["skipped"] == 0
        assert len(db.connection_obj.copy_calls) == 2
        assert db.connection_obj.commits == 4
        assert invalidations == 2

    csv_data = "\n".join(
        [
            "name,gender,gender_probability,age,country_id,country_probability",
            "Ada,female,0.98,31,NG,0.76",
            "Grace,female,0.88,40,US,0.66",
            "Linus,male,0.80,55,FI,0.60",
        ]
    )
    asyncio.run(scenario())


def test_ingest_profile_csv_counts_conflicts_without_invalidating_empty_chunk(
    monkeypatch,
):
    async def scenario():
        invalidations = 0

        async def fake_invalidate():
            nonlocal invalidations
            invalidations += 1

        monkeypatch.setattr(
            profile_ingestion,
            "invalidate_profile_query_cache",
            fake_invalidate,
        )
        upload = UploadFile(
            file=BytesIO(csv_data.encode("utf-8")),
            filename="profiles.csv",
        )
        db = FakeDB(existing_names={"ada"})

        summary = await ingest_profile_csv(db, upload, chunk_size=1)

        assert summary == {
            "status": "success",
            "total_rows": 1,
            "inserted": 0,
            "skipped": 1,
            "reasons": {"duplicate_name": 1},
        }
        assert db.connection_obj.commits == 3
        assert invalidations == 0

    csv_data = "\n".join(
        [
            "name,gender,gender_probability,age,country_id,country_probability",
            "Ada,female,0.98,31,NG,0.76",
        ]
    )
    asyncio.run(scenario())
