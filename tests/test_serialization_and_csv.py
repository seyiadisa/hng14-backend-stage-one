from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

from app.models.enums import AgeGroup, Gender
from app.services.csv_parser import CSV_COLUMNS, generate_csv
from app.services.utils import serialize_profile, serialize_profile_list_item


def profile_stub(**overrides):
    data = {
        "id": UUID("018f978a-6ee5-7d52-b2cb-0123456789ab"),
        "name": "ada",
        "gender": Gender.female,
        "gender_probability": Decimal("0.98"),
        "age": 31,
        "age_group": AgeGroup.adult,
        "country_id": "NG",
        "country_name": "Nigeria",
        "country_probability": Decimal("0.76"),
        "created_at": datetime(2026, 4, 29, 10, 30, 0),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_serialize_profile_outputs_json_safe_values():
    result = serialize_profile(profile_stub())

    assert result["id"] == "018f978a-6ee5-7d52-b2cb-0123456789ab"
    assert result["gender"] == "female"
    assert result["age_group"] == "adult"
    assert result["created_at"] == "2026-04-29T10:30:00Z"


def test_serialize_profile_list_item_matches_profile_shape():
    result = serialize_profile_list_item(profile_stub(name="tunde"))

    assert result["name"] == "tunde"
    assert result["country_id"] == "NG"


def test_generate_csv_writes_header_and_profile_rows():
    csv_data = generate_csv([profile_stub()])

    assert csv_data.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert "ada,female,0.98,31,adult,NG,Nigeria,0.76" in csv_data
