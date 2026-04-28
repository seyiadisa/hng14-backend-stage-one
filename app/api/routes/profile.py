from typing import Annotated

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Response, status, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.profile import Profile
from app.services.language_parser import parse_search_query
from app.schemas.profile import (
    ProfileListQueryParams,
    ProfileCreate,
    ProfileSearchQueryParams,
)
from app.services.profile_service import (
    parse_name,
    apply_filters,
    apply_sorting,
)
from app.services.utils import (
    serialize_profile,
    serialize_profile_list_item,
    invalid_upstream,
    fetch_json,
    get_age_group,
)

router = APIRouter()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_profile(
    response: Response,
    payload: Annotated[ProfileCreate, Body()],
    db: AsyncSession = Depends(get_db),
):
    name = parse_name(payload.name)
    db_profile = await db.execute(select(Profile).where(Profile.name == name))
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
        # sample_size=sample_size,
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


@router.get("")
async def get_profiles(
    params: Annotated[ProfileListQueryParams, Query()],
    db: AsyncSession = Depends(get_db),
):
    count = select(func.count()).select_from(Profile)
    count = await db.execute(apply_filters(count, params))
    total = count.scalar_one()

    offset = (params.page - 1) * params.limit

    query = select(Profile)
    query = apply_filters(query, params)
    query = apply_sorting(query, params.sort_by, params.order)
    query = query.offset(offset).limit(params.limit)

    db_profiles = await db.execute(query)
    profiles = db_profiles.scalars().all()

    if not profiles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No profiles found matching the criteria",
        )

    return {
        "status": "success",
        "page": params.page,
        "limit": params.limit,
        "total": total,
        "data": [serialize_profile_list_item(profile) for profile in profiles],
    }


@router.get("/search")
async def search_profiles_with_natural_language(
    params: Annotated[ProfileSearchQueryParams, Query()],
    db: AsyncSession = Depends(get_db),
):
    filters = parse_search_query(params.q)

    count = select(func.count()).select_from(Profile)
    count = await db.execute(apply_filters(count, filters))
    total = count.scalar_one()

    offset = (params.page - 1) * params.limit

    query = select(Profile)
    query = apply_filters(query, filters)
    query = query.offset(offset).limit(params.limit)

    db_profiles = await db.execute(query)
    profiles = db_profiles.scalars().all()

    if not profiles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No profiles found matching the criteria",
        )

    return {
        "status": "success",
        "page": params.page,
        "limit": params.limit,
        "total": total,
        "data": [serialize_profile_list_item(profile) for profile in profiles],
    }


@router.get("/{profile_id}")
async def get_profile_by_id(profile_id: str, db: AsyncSession = Depends(get_db)):
    db_profile = await db.execute(select(Profile).where(Profile.id == profile_id))
    profile = db_profile.scalar_one_or_none()

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )

    return {"status": "success", "data": serialize_profile(profile)}


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
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
