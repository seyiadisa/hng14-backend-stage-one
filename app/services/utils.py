import httpx
from typing import Any
from fastapi import HTTPException, status

from app.models.profile import Profile
from app.models.enums import AgeGroup
from app.schemas.profile import (
    Profile as ProfileSchema,
    ProfileListItem,
)


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


def invalid_search_query() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unable to interpret query",
    )


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
