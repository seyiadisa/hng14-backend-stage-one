from fastapi import Request
from fastapi.responses import JSONResponse


async def http_exception_handler(request: Request, exc) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "message": str(exc.detail)},
    )


async def validation_exception_handler(request: Request, exc) -> JSONResponse:
    is_query_validation_error = any(
        isinstance(error.get("loc"), (tuple, list))
        and len(error["loc"]) > 0
        and error["loc"][0] == "query"
        for error in exc.errors()
    )

    return JSONResponse(
        status_code=422,
        content={
            "status": "error",
            "message": (
                "Invalid query parameters"
                if is_query_validation_error
                else "Invalid type"
            ),
        },
    )


async def generic_exception_handler(request: Request, exc) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": "Internal server error"},
    )
