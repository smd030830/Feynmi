"""API 오류 형식 (architecture.md 8.2).

모든 오류는 `{"error": {"code", "message", "retryable"}}`로 응답한다.
사용자에게 보여줄 한국어 문구는 프론트엔드가 `code`로 정하고, `message`는 디버깅용이다.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(
        self, status_code: int, code: str, message: str = "", *, retryable: bool = False
    ) -> None:
        super().__init__(message or code)
        self.status_code = status_code
        self.code = code
        self.message = message or code
        self.retryable = retryable


def error_response(
    status_code: int, code: str, message: str, *, retryable: bool = False
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "retryable": retryable}},
    )


# 라우팅 단계에서 Starlette가 내는 HTTP 오류를 8.2 코드로 옮긴다.
_HTTP_STATUS_CODES = {404: "not_found", 409: "invalid_state"}


async def _handle_app_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return error_response(exc.status_code, exc.code, exc.message, retryable=exc.retryable)


async def _handle_validation_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return error_response(400, "validation_error", str(exc.errors()))


async def _handle_http_exception(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    if exc.status_code == 405:
        # 405는 8.2 표에 없어서 존재하지 않는 경로와 같게 취급한다.
        return error_response(404, "not_found", str(exc.detail))
    if exc.status_code >= 500:
        return error_response(500, "internal_error", str(exc.detail), retryable=True)
    code = _HTTP_STATUS_CODES.get(exc.status_code, "validation_error")
    return error_response(exc.status_code, code, str(exc.detail))


async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error", exc_info=exc)
    return error_response(500, "internal_error", "Internal server error", retryable=True)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(Exception, _handle_unexpected)
