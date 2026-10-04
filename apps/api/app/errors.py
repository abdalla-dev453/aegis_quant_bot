from typing import NoReturn

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette import status

from app.contracts import ErrorResponse


class APIError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, str | int | float | bool | None] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)


async def api_error_handler(_request: Request, exc: APIError) -> JSONResponse:
    payload = ErrorResponse(code=exc.code, message=exc.message, details=exc.details)
    return JSONResponse(status_code=exc.status_code, content=payload.model_dump(exclude_none=True))


async def validation_error_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    fields = [".".join(str(part) for part in error["loc"]) for error in exc.errors()]
    payload = ErrorResponse(
        code="invalid_request",
        message="Request validation failed",
        details={"fields": ", ".join(fields)},
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=payload.model_dump(exclude_none=True),
    )


def unauthorized() -> NoReturn:
    raise APIError("unauthorized", "Authentication required", status.HTTP_401_UNAUTHORIZED)