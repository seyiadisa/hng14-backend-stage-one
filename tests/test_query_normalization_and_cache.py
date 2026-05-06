import asyncio
from decimal import Decimal

from app.models.enums import AgeGroup, Gender
from app.schemas.profile import ProfileListQueryParams
from app.services.language_parser import parse_search_query
from app.services.query_cache import TTLQueryCache
from app.services.query_normalization import (
    canonical_profile_query,
    profile_query_cache_key,
)


def test_canonical_query_normalizes_country_case_and_defaults():
    lowercase = ProfileListQueryParams(country_id="ng")
    uppercase = ProfileListQueryParams(country_id="NG")

    assert canonical_profile_query(lowercase) == canonical_profile_query(uppercase)
    assert canonical_profile_query(lowercase) == {
        "gender": None,
        "age_group": None,
        "country_id": "NG",
        "min_age": None,
        "max_age": None,
        "min_gender_probability": None,
        "min_country_probability": None,
        "sort_by": None,
        "order": None,
        "page": 1,
        "limit": 10,
    }


def test_canonical_query_normalizes_enums_and_decimals():
    enum_params = ProfileListQueryParams(
        gender=Gender.female,
        age_group=AgeGroup.adult,
        min_gender_probability=Decimal("0.8"),
        min_country_probability=Decimal("0.50"),
    )
    string_params = ProfileListQueryParams(
        gender="female",
        age_group="adult",
        min_gender_probability=Decimal("0.80"),
        min_country_probability=Decimal("0.5"),
    )

    assert canonical_profile_query(enum_params) == canonical_profile_query(
        string_params
    )
    assert canonical_profile_query(enum_params)["min_gender_probability"] == "0.80"
    assert canonical_profile_query(enum_params)["min_country_probability"] == "0.50"


def test_equivalent_search_queries_generate_same_cache_key():
    first = parse_search_query("Nigerian females between ages 20 and 45")
    second = parse_search_query("Women aged 20-45 living in Nigeria")

    assert canonical_profile_query(first) == canonical_profile_query(second)
    assert profile_query_cache_key(first) == profile_query_cache_key(second)


def test_cache_returns_hits_before_expiry_and_misses_after_expiry():
    nonlocal_now = {"value": 0.0}

    async def scenario_with_mutable_clock():
        cache = TTLQueryCache(
            ttl_seconds=10,
            max_entries=2,
            clock=lambda: nonlocal_now["value"],
        )
        await cache.set("profiles:query:one", {"data": [1]})
        assert await cache.get("profiles:query:one") == {"data": [1]}

        nonlocal_now["value"] = 11.0
        assert await cache.get("profiles:query:one") is None

    asyncio.run(scenario_with_mutable_clock())


def test_cache_evicts_oldest_entry_when_full():
    async def scenario():
        cache = TTLQueryCache(ttl_seconds=60, max_entries=2, clock=lambda: 0.0)

        await cache.set("profiles:query:one", 1)
        await cache.set("profiles:query:two", 2)
        await cache.set("profiles:query:three", 3)

        assert await cache.get("profiles:query:one") is None
        assert await cache.get("profiles:query:two") == 2
        assert await cache.get("profiles:query:three") == 3

    asyncio.run(scenario())


def test_cache_clear_removes_all_entries():
    async def scenario():
        cache = TTLQueryCache(ttl_seconds=60, max_entries=2, clock=lambda: 0.0)

        await cache.set("profiles:query:one", 1)
        await cache.set("profiles:query:two", 2)
        await cache.clear()

        assert await cache.get("profiles:query:one") is None
        assert await cache.get("profiles:query:two") is None

    asyncio.run(scenario())
