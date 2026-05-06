from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

PROFILE_INDEX_STATEMENTS = (
    """
    CREATE INDEX IF NOT EXISTS ix_profiles_country_gender_age
    ON profiles (country_id, gender, age)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_profiles_country_age_group
    ON profiles (country_id, age_group)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_profiles_gender_age
    ON profiles (gender, age)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_profiles_created_at_id
    ON profiles (created_at, id)
    """,
)


async def ensure_profile_indexes(conn: AsyncConnection) -> None:
    for statement in PROFILE_INDEX_STATEMENTS:
        await conn.execute(text(statement))
