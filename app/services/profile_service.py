from sqlalchemy import Select, func, asc, desc
from fastapi import HTTPException, status

from app.models.profile import Profile
from app.models.enums import AgeGroup, Gender
from app.schemas.profile import ProfileListQueryParams


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
