import re
import httpx
import pycountry
from typing import Any
from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import Select, func, asc, desc

from app.models.profile import Profile
from app.models.enums import AgeGroup, Gender
from app.schemas.profile import (
    Profile as ProfileSchema,
    ProfileListItem,
    ProfileListQueryParams,
)

COUNTRY_ALIASES = {
    "angolan": "Angola",
    "canadian": "Canada",
    "ghanaian": "Ghana",
    "kenyan": "Kenya",
    "nigerian": "Nigeria",
    "south african": "South Africa",
    "uk": "United Kingdom",
    "britain": "United Kingdom",
    "british": "United Kingdom",
    "usa": "United States",
    "us": "United States",
    "america": "United States",
    "american": "United States",
}

AGE_GROUP_ALIASES = {
    "child": AgeGroup.child,
    "children": AgeGroup.child,
    "teenager": AgeGroup.teenager,
    "teenagers": AgeGroup.teenager,
    "adult": AgeGroup.adult,
    "adults": AgeGroup.adult,
    "senior": AgeGroup.senior,
    "seniors": AgeGroup.senior,
}

GENDER_ALIASES = {
    "male": Gender.male,
    "males": Gender.male,
    "female": Gender.female,
    "females": Gender.female,
}

COUNTRY_STOP_WORDS = {
    "above",
    "adult",
    "adults",
    "and",
    "child",
    "children",
    "female",
    "females",
    "male",
    "males",
    "older",
    "over",
    "senior",
    "seniors",
    "teenager",
    "teenagers",
    "than",
    "young",
}


def get_age_group(age: int) -> AgeGroup:
    if age <= 12:
        return AgeGroup.child
    if age <= 19:
        return AgeGroup.teenager
    if age <= 59:
        return AgeGroup.adult
    return AgeGroup.senior


def serialize_profile(profile: Profile) -> dict[str, Any]:
    return ProfileSchema.model_validate(profile).model_dump(mode="json")


def serialize_profile_list_item(profile: Profile) -> dict[str, Any]:
    return ProfileListItem.model_validate(profile).model_dump(mode="json")


def invalid_upstream(api_name: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"{api_name} returned an invalid response",
    )


def parse_name(name: str) -> str:
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing or empty name",
        )

    if not isinstance(name, str):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid type",
        )

    normalized_name = name.strip().lower()
    if not normalized_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing or empty name",
        )

    return normalized_name


async def fetch_json(
    client: httpx.AsyncClient,
    url: str,
    name: str,
    api_name: str,
) -> dict[str, Any]:
    try:
        response = await client.get(url, params={"name": name})
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        raise invalid_upstream(api_name) from None

    if not isinstance(payload, dict):
        raise invalid_upstream(api_name)

    return payload


def apply_filters(query: Select, params: ProfileListQueryParams) -> Select:
    if params.gender:
        try:
            normalized_gender = Gender(params.gender.value)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid type",
            ) from None
        query = query.where(Profile.gender == normalized_gender)
    if params.age_group:
        try:
            normalized_age_group = AgeGroup(params.age_group.value)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid type",
            ) from None
        query = query.where(Profile.age_group == normalized_age_group)
    if params.country_id:
        query = query.where(Profile.country_id == params.country_id.upper())
    if params.min_age:
        query = query.where(Profile.age >= params.min_age)
    if params.max_age:
        query = query.where(Profile.age <= params.max_age)
    if params.min_gender_probability:
        query = query.where(Profile.gender_probability >= params.min_gender_probability)
    if params.min_country_probability:
        query = query.where(
            Profile.country_probability >= params.min_country_probability
        )

    return query


def apply_sorting(query: Select, sort_by: str | None, order: str | None) -> Select:
    if sort_by is None or order is None:
        return query

    sort_column = {
        "age": Profile.age,
        "created_at": Profile.created_at,
        "gender_probability": Profile.gender_probability,
    }.get(sort_by)

    if sort_column is None:
        return query

    order_by = asc(sort_column) if order == "asc" else desc(sort_column)

    return query.order_by(order_by)


def invalid_search_query() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unable to interpret query",
    )


def parse_search_query(
    raw_query: str | None,
) -> ProfileListQueryParams:
    if raw_query is None or not raw_query.strip():
        raise invalid_search_query()

    normalized_query = normalize_search_query(raw_query)
    words = normalized_query.split()

    genders_found = {GENDER_ALIASES[word] for word in words if word in GENDER_ALIASES}
    gender = genders_found.pop() if len(genders_found) == 1 else None

    age_groups_found = [
        AGE_GROUP_ALIASES[word] for word in words if word in AGE_GROUP_ALIASES
    ]
    age_group = age_groups_found[-1] if age_groups_found else None

    min_age, max_age = extract_age_bounds(normalized_query)
    country_id = extract_country_id(normalized_query)

    if all(
        value is None for value in (gender, age_group, min_age, max_age, country_id)
    ):
        raise invalid_search_query()

    try:
        return ProfileListQueryParams(
            gender=gender,
            age_group=age_group,
            country_id=country_id,
            min_age=min_age,
            max_age=max_age,
        )
    except ValidationError as exc:
        raise invalid_search_query() from exc


def normalize_search_query(query: str) -> str:
    return re.sub(r"[^a-z0-9\s]", " ", query.lower()).strip()


def extract_age_bounds(query: str) -> tuple[int | None, int | None]:
    min_age = None
    max_age = None

    if "young" in query.split():
        min_age = 16
        max_age = 24

    minimum_age_patterns = (
        r"\babove\s+(\d+)\b",
        r"\bover\s+(\d+)\b",
        r"\bolder\s+than\s+(\d+)\b",
    )

    maximum_age_patterns = (
        r"\bbelow\s+(\d+)\b",
        r"\bunder\s+(\d+)\b",
        r"\byounger\s+than\s+(\d+)\b",
    )

    for pattern in minimum_age_patterns:
        match = re.search(pattern, query)
        if match:
            min_age = int(match.group(1))
            break

    for pattern in maximum_age_patterns:
        match = re.search(pattern, query)
        if match:
            max_age = int(match.group(1))
            break

    return min_age, max_age


def extract_country_id(query: str) -> str | None:
    words = query.split()
    if "from" not in words:
        return None

    from_index = words.index("from") + 1
    country_tokens: list[str] = []

    for word in words[from_index:]:
        if word in COUNTRY_STOP_WORDS:
            break
        country_tokens.append(word)

    if not country_tokens:
        return None

    country_phrase = " ".join(country_tokens)
    normalized_country_phrase = COUNTRY_ALIASES.get(country_phrase, country_phrase)

    try:
        country = pycountry.countries.search_fuzzy(normalized_country_phrase)[0]
    except LookupError:
        return None

    return country.alpha_2
