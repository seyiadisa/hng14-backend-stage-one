from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.enums import AgeGroup, Gender
from app.models.profile import Profile
from app.schemas.profile import ProfileListQueryParams
from app.services.profile_service import apply_filters, apply_sorting, parse_name
from app.services.utils import get_age_group


@pytest.mark.parametrize(
    ("raw_name", "expected"),
    [
        (" Ada ", "ada"),
        ("CHINEDU", "chinedu"),
    ],
)
def test_parse_name_normalizes_valid_names(raw_name, expected):
    assert parse_name(raw_name) == expected


@pytest.mark.parametrize("raw_name", ["", "   "])
def test_parse_name_rejects_empty_names(raw_name):
    with pytest.raises(HTTPException) as exc_info:
        parse_name(raw_name)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Missing or empty name"


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (12, AgeGroup.child),
        (13, AgeGroup.teenager),
        (19, AgeGroup.teenager),
        (20, AgeGroup.adult),
        (59, AgeGroup.adult),
        (60, AgeGroup.senior),
    ],
)
def test_get_age_group_boundaries(age, expected):
    assert get_age_group(age) == expected


def test_apply_filters_adds_expected_where_clauses():
    params = ProfileListQueryParams(
        gender=Gender.female,
        age_group=AgeGroup.adult,
        country_id="ng",
        min_age=20,
        max_age=40,
        min_gender_probability=Decimal("0.80"),
        min_country_probability=Decimal("0.50"),
    )

    statement = apply_filters(select(Profile), params)
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "profiles.gender = 'female'" in compiled
    assert "profiles.age_group = 'adult'" in compiled
    assert "profiles.country_id = 'NG'" in compiled
    assert "profiles.age >= 20" in compiled
    assert "profiles.age <= 40" in compiled
    assert "profiles.gender_probability >= 0.80" in compiled
    assert "profiles.country_probability >= 0.50" in compiled


def test_apply_sorting_orders_by_known_column():
    statement = apply_sorting(select(Profile), "age", "desc")
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "ORDER BY profiles.age DESC" in compiled


def test_apply_sorting_ignores_missing_sort_options():
    statement = apply_sorting(select(Profile), None, "desc")
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert "ORDER BY" not in compiled
