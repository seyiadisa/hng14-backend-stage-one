import httpx
from enum import Enum
from typing import Any
from fastapi import HTTPException, status

from models import Profile
from schemas import Profile as ProfileSchema, ProfileListItem


class AgeGroup(str, Enum):
    child = "child"
    teenager = "teenager"
    adult = "adult"
    senior = "senior"


class Gender(str, Enum):
    male = "male"
    female = "female"


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
