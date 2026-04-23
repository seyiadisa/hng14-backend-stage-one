from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models import Profile

from utils import (
    AgeGroup,
    parse_name,
    serialize_profile,
    serialize_profile_list_item,
    invalid_upstream,
    fetch_json,
    get_age_group,
)

router = APIRouter(prefix="/api")


@router.post("/profiles", status_code=status.HTTP_201_CREATED)
async def create_profile(
    response: Response,
    payload: Annotated[dict[str, Any], Body()],
    db: AsyncSession = Depends(get_db),
):
    name = parse_name(payload)
    db_profile = await db.execute(
        select(Profile).where(func.lower(Profile.name) == name)
    )
    existing_profile = db_profile.scalar_one_or_none()

    if existing_profile:
        response.status_code = status.HTTP_200_OK
        return {
            "status": "success",
            "message": "Profile already exists",
            "data": serialize_profile(existing_profile),
        }

    async with httpx.AsyncClient() as client:
        genderize = await fetch_json(
            client, "https://api.genderize.io", name, "Genderize"
        )
        agify = await fetch_json(client, "https://api.agify.io", name, "Agify")
        nationalize = await fetch_json(
            client, "https://api.nationalize.io", name, "Nationalize"
        )

    gender = genderize.get("gender")
    sample_size = genderize.get("count")
    gender_probability = genderize.get("probability")
    if gender is None or sample_size in (None, 0) or gender_probability is None:
        raise invalid_upstream("Genderize")

    age = agify.get("age")
    if age is None:
        raise invalid_upstream("Agify")

    countries = nationalize.get("country")
    if not isinstance(countries, list) or not countries:
        raise invalid_upstream("Nationalize")

    top_country = max(countries, key=lambda item: item.get("probability", 0))
    country_id = top_country.get("country_id")
    country_probability = top_country.get("probability")
    if country_id is None or country_probability is None:
        raise invalid_upstream("Nationalize")

    new_profile = Profile(
        name=name,
        gender=gender,
        gender_probability=gender_probability,
        sample_size=sample_size,
        age=age,
        age_group=get_age_group(age),
        country_id=country_id,
        country_probability=country_probability,
    )
    db.add(new_profile)
    await db.commit()
    await db.refresh(new_profile)

    return {
        "status": "success",
        "data": serialize_profile(new_profile),
    }


@router.get("/profiles/{profile_id}")
async def get_profile_by_id(profile_id: str, db: AsyncSession = Depends(get_db)):
    db_profile = await db.execute(select(Profile).where(Profile.id == profile_id))
    profile = db_profile.scalar_one_or_none()

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )

    return {"status": "success", "data": serialize_profile(profile)}


@router.get("/profiles")
async def get_profiles(
    db: AsyncSession = Depends(get_db),
    gender: str | None = None,
    country_id: str | None = None,
    age_group: str | None = None,
):
    query = select(Profile)

    if gender:
        query = query.where(func.lower(Profile.gender) == gender.lower())
    if country_id:
        query = query.where(func.lower(Profile.country_id) == country_id.lower())
    if age_group:
        try:
            normalized_age_group = AgeGroup(age_group.lower())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid type",
            ) from None
        query = query.where(Profile.age_group == normalized_age_group)

    db_profiles = await db.execute(query)
    profiles = db_profiles.scalars().all()

    return {
        "status": "success",
        "count": len(profiles),
        "data": [serialize_profile_list_item(profile) for profile in profiles],
    }


@router.delete("/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(profile_id: str, db: AsyncSession = Depends(get_db)):
    db_profile = await db.execute(select(Profile).where(Profile.id == profile_id))
    profile = db_profile.scalar_one_or_none()

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )

    await db.delete(profile)
    await db.commit()
