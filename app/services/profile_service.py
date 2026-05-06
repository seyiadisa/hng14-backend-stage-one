from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import Select, asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AgeGroup, Gender
from app.models.profile import Profile
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


def apply_default_ordering(query: Select) -> Select:
    return query.order_by(desc(Profile.created_at), desc(Profile.id))


def apply_query_ordering(
    query: Select, sort_by: str | None, order: str | None
) -> Select:
    sorted_query = apply_sorting(query, sort_by, order)
    if sort_by is None or order is None:
        return apply_default_ordering(sorted_query)
    return sorted_query.order_by(desc(Profile.id))


def build_profile_page_query(params: ProfileListQueryParams) -> Select:
    offset = (params.page - 1) * params.limit
    query = select(Profile)
    query = apply_filters(query, params)
    query = apply_query_ordering(query, params.sort_by, params.order)
    return query.offset(offset).limit(params.limit)


def build_pagination_links(
    path: str,
    page: int,
    limit: int,
    total_pages: int,
    extra_query: str | None = None,
) -> dict[str, str | None]:
    query_prefix = f"{extra_query}&" if extra_query else ""
    self_link = f"{path}?{query_prefix}page={page}&limit={limit}"
    next_link = (
        None
        if page >= total_pages
        else f"{path}?{query_prefix}page={page + 1}&limit={limit}"
    )
    prev_link = (
        None if page == 1 else f"{path}?{query_prefix}page={page - 1}&limit={limit}"
    )

    return {
        "self": self_link,
        "next": next_link,
        "prev": prev_link,
    }


@dataclass(frozen=True)
class ProfilePage:
    profiles: list[Profile]
    total: int
    total_pages: int
    links: dict[str, str | None]


async def execute_profile_page_query(
    db: AsyncSession,
    params: ProfileListQueryParams,
    path: str,
    extra_query: str | None = None,
) -> ProfilePage:
    count_query = select(func.count()).select_from(Profile)
    count_result = await db.execute(apply_filters(count_query, params))
    total = count_result.scalar_one()
    total_pages = (total + params.limit - 1) // params.limit

    page_query = build_profile_page_query(params)
    db_profiles = await db.execute(page_query)
    profiles = list(db_profiles.scalars().all())

    return ProfilePage(
        profiles=profiles,
        total=total,
        total_pages=total_pages,
        links=build_pagination_links(
            path=path,
            page=params.page,
            limit=params.limit,
            total_pages=total_pages,
            extra_query=extra_query,
        ),
    )
