import httpx
from typing import Any
from fastapi import HTTPException, status
from sqlalchemy import Select, func, asc, desc

from models import Profile
from enums import AgeGroup, Gender
from schemas import Profile as ProfileSchema, ProfileListItem, ProfileListQueryParams


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


def parse_name(payload: dict[str, Any]) -> str:
    if "name" not in payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing or empty name",
        )

    name = payload["name"]
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
        query = query.where(func.lower(Profile.country_id) == params.country_id.lower())
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
