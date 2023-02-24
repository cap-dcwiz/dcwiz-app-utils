from enum import Enum
from http.client import HTTPException
from json import JSONDecodeError

from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse
from httpx import Response as HttpxResponse


class ErrorSeverity(str, Enum):
    CRITICAL = "Critical"
    ERROR = "Error"
    WARNING = "Warning"
    INFO = "Info"
    DEBUG = "Debug"


class Error(BaseModel):
    type: str = Field(..., description="Error type")
    severity: ErrorSeverity = Field(ErrorSeverity.ERROR, description="Error severity")
    message: str = Field(None, description="Error message")


class DCWizServiceException(Exception):
    def __init__(self, message=None, errors=None):
        super().__init__()
        self.message = message
        self.errors = errors

    @staticmethod
    async def exception_handler(_, exc):
        content = dict(
            message=exc.message or "Internal Service Error",
            errors=[e.dict() for e in exc.errors],
        )
        return JSONResponse(status_code=500, content=content)


class DCWizAPIException(Exception):
    def __init__(self, method, url, response: HttpxResponse, message=None):
        super().__init__()
        self.method = method
        self.url = url
        self.response = response
        self.message = message

    @staticmethod
    async def exception_handler(_, exc):
        status_code = exc.response.status_code
        content = dict(
            message=exc.message or f"API Error: {exc.method} {exc.url}: {status_code}",
            errors=[
                Error(
                    type="API Error",
                    severity=ErrorSeverity.ERROR,
                    message=exc.response.text,
                ).dict()
            ],
        )
        return JSONResponse(status_code=status_code, content=content)


class DCWizPlatformAPIException(DCWizAPIException):
    @staticmethod
    async def exception_handler(_, exc):
        status_code = exc.response.status_code
        try:
            error = exc.response.json()
        except JSONDecodeError:
            error = exc.response.text
        content = dict(
            message=exc.message or f"API Error: {exc.method} {exc.url}: {status_code}",
            errors=[
                Error(
                    type="API Error", severity=ErrorSeverity.ERROR, message=error
                ).dict()
            ],
        )
        return JSONResponse(status_code=status_code, content=content)


class DCWizDataAPIException(DCWizAPIException):
    @staticmethod
    async def exception_handler(_, exc):
        error = exc.response.json()
        content = dict(
            message=exc.message
            or f"Data Error: {exc.method} {exc.url}: {exc.response.status_code}",
            errors=[
                Error(
                    type="Data Error", severity=ErrorSeverity.ERROR, message=f"{k}:{v}"
                ).dict()
                for k, v in error["detail"]
            ],
        )
        return JSONResponse(status_code=exc.response.status_code, content=content)


class DCWizServiceAPIException(DCWizAPIException):
    @staticmethod
    async def exception_handler(_, exc):
        error = exc.response.json()
        content = dict(
            message=exc.message or error["message"],
            errors=[Error(**e).dict() for e in error["errors"]],
        )
        return JSONResponse(status_code=exc.response.status_code, content=content)


async def http_exception_handler(_, exc):
    content = dict(
        message=str(exc.detail),
        errors=[
            Error(
                type="HTTPException",
                message=str(exc.detail),
                severity=ErrorSeverity.ERROR,
            ).dict()
        ],
    )
    return JSONResponse(status_code=exc.status_code, content=content)


def setup_exception_handlers(app):
    app.add_exception_handler(
        DCWizServiceException, DCWizServiceException.exception_handler
    )
    app.add_exception_handler(DCWizAPIException, DCWizAPIException.exception_handler)
    app.add_exception_handler(
        DCWizPlatformAPIException, DCWizPlatformAPIException.exception_handler
    )
    app.add_exception_handler(
        DCWizDataAPIException, DCWizDataAPIException.exception_handler
    )
    app.add_exception_handler(
        DCWizServiceAPIException, DCWizServiceAPIException.exception_handler
    )
    app.add_exception_handler(HTTPException, http_exception_handler)
