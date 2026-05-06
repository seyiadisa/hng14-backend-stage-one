import asyncio
from decimal import Decimal
from io import BytesIO

from fastapi import UploadFile

from app.models.enums import AgeGroup, Gender
from app.services.profile_ingestion import ingest_profile_csv, validate_profile_csv_row


class FakeScalarResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class FakeSelectResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return FakeScalarResult(self.values)


class FakeInsertResult:
    def __init__(self, rowcount):
        self.rowcount = rowcount


class FakeDB:
    def __init__(self, existing_names=None, inserted_rowcount=None):
        self.existing_names = set(existing_names or [])
        self.inserted_rowcount = inserted_rowcount
        self.insert_calls = 0
        self.commits = 0

    async def execute(self, statement):
        if getattr(statement, "is_select", False):
            return FakeSelectResult(self.existing_names)

        self.insert_calls += 1
        return FakeInsertResult(self.inserted_rowcount)

    async def commit(self):
        self.commits += 1


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


def test_ingest_profile_csv_returns_summary_for_mixed_rows():
    async def scenario():
        upload = UploadFile(
            file=BytesIO(csv_data.encode("utf-8")),
            filename="profiles.csv",
        )
        db = FakeDB(existing_names={"existing"}, inserted_rowcount=1)

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
        assert db.commits == 1

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
    asyncio.run(scenario())
