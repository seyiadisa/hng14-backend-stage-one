import pytest
from fastapi import HTTPException

from app.models.enums import AgeGroup, Gender
from app.services.language_parser import (
    extract_age_bounds,
    extract_country_id,
    normalize_search_query,
    parse_search_query,
)


def test_normalize_search_query_lowercases_and_removes_punctuation():
    assert normalize_search_query("Young Males from NIGERIA!!!") == (
        "young males from nigeria"
    )


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("young males", (16, 24)),
        ("people above 30", (30, None)),
        ("people older than 45", (45, None)),
        ("people under 18", (None, 18)),
        ("people younger than 21", (None, 21)),
    ],
)
def test_extract_age_bounds(query, expected):
    assert extract_age_bounds(query) == expected


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("young males from nigeria", "NG"),
        ("adults from usa", "US"),
        ("people from south african male", "ZA"),
        ("people from uk", "GB"),
        ("people from unknownland", None),
    ],
)
def test_extract_country_id(query, expected):
    assert extract_country_id(query) == expected


def test_parse_search_query_combines_supported_filters():
    params = parse_search_query("young males from nigeria")

    assert params.gender == Gender.male
    assert params.min_age == 16
    assert params.max_age == 24
    assert params.country_id == "NG"


def test_parse_search_query_uses_last_age_group():
    params = parse_search_query("adult senior females")

    assert params.age_group == AgeGroup.senior
    assert params.gender == Gender.female


def test_parse_search_query_drops_ambiguous_gender():
    params = parse_search_query("male and female teenagers above 17")

    assert params.gender is None
    assert params.age_group == AgeGroup.teenager
    assert params.min_age == 17


@pytest.mark.parametrize("query", [None, "", "show me people"])
def test_parse_search_query_rejects_uninterpretable_query(query):
    with pytest.raises(HTTPException) as exc_info:
        parse_search_query(query)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Unable to interpret query"
