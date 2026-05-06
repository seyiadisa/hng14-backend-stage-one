import hashlib
import json
from decimal import Decimal
from enum import Enum
from typing import Any

from app.schemas.profile import ProfileListQueryParams

DECIMAL_PLACES = Decimal("0.01")


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _decimal_value(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(value.quantize(DECIMAL_PLACES))


def canonical_profile_query(params: ProfileListQueryParams) -> dict[str, Any]:
    return {
        "gender": _enum_value(params.gender),
        "age_group": _enum_value(params.age_group),
        "country_id": params.country_id.upper() if params.country_id else None,
        "min_age": params.min_age,
        "max_age": params.max_age,
        "min_gender_probability": _decimal_value(params.min_gender_probability),
        "min_country_probability": _decimal_value(params.min_country_probability),
        "sort_by": params.sort_by,
        "order": params.order,
        "page": params.page,
        "limit": params.limit,
    }


def profile_query_cache_key(params: ProfileListQueryParams) -> str:
    canonical = canonical_profile_query(params)
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"profiles:query:{digest}"
