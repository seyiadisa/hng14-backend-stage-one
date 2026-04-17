from httpx import AsyncClient
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from schemas import ProfileResponse, ProfileCreate, Profile as ProfileSchema
from models import Profile
from utils import AgeGroup
from db import get_db

router = APIRouter(prefix="/api")


@router.post("/profiles", status_code=201)
async def create_profile(profile: ProfileCreate, db: AsyncSession = Depends(get_db)):
    db_profile = await db.execute(select(Profile).where(Profile.name == profile.name))
    db_profile = db_profile.scalar_one_or_none()

    if db_profile:
        return {
            "status": "success",
            "message": "Profile already exists",
            "data": ProfileResponse.model_validate(db_profile),
        }

    async with AsyncClient() as client:
        try:
            genderize = await client.get(
                "https://api.genderize.io",
                params={"name": profile.name},
            )

            agify = await client.get(
                "https://api.agify.io",
                params={"name": profile.name},
            )
            nationalize = await client.get(
                "https://api.nationalize.io",
                params={"name": profile.name},
            )

            age = agify.json().get("age", 0)
            age_group = (
                AgeGroup.child
                if age < 13
                else (
                    AgeGroup.teenager
                    if age < 20
                    else AgeGroup.adult if age < 60 else AgeGroup.senior
                )
            )
            country_max = max(
                nationalize.json().get("country", []),
                key=lambda x: x["probability"],
                default={"country_id": None, "probability": 0},
            )
            country_id = country_max.get("country_id")
            country_prob = country_max.get("probability")

            new_profile = Profile(
                name=profile.name,
                gender=genderize.json().get("gender"),
                gender_probability=genderize.json().get("probability", 0),
                sample_size=genderize.json().get("count", 0),
                age=age,
                age_group=age_group,
                country_id=country_id,
                country_probability=country_prob,
            )
            db.add(new_profile)
            await db.commit()
            await db.refresh(new_profile)

            return {
                "status": "success",
                "data": ProfileResponse.model_validate(new_profile),
            }

        except:
            pass


@router.get("/profiles/{profile_id}")
async def get_profile_by_id(profile_id: str, db: AsyncSession = Depends(get_db)):
    db_profile = await db.execute(select(Profile).where(Profile.id == profile_id))
    db_profile = db_profile.scalar_one_or_none()

    if not db_profile:
        return {"status": "error", "message": "Profile not found"}

    return {"status": "success", "data": ProfileResponse.model_validate(db_profile)}


@router.get("/profiles")
async def get_profiles(
    db: AsyncSession = Depends(get_db),
    gender: str | None = None,
    country_id: str | None = None,
    age_group: AgeGroup | None = None,
):
    query = select(Profile)
    if gender:
        query = query.where(Profile.gender == gender)
    if country_id:
        query = query.where(Profile.country_id == country_id)
    if age_group:
        query = query.where(Profile.age_group == age_group)

    db_profiles = await db.execute(query)
    db_profiles = db_profiles.scalars().all()

    return {
        "status": "success",
        "count": len(db_profiles),
        "data": [ProfileResponse.model_validate(profile) for profile in db_profiles],
    }
