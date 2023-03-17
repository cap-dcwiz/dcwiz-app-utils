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
    message: str | dict = Field(None, description="Error message")


class DCWizException(Exception):
    @classmethod
    async def exception_handler_and_response(cls, _, exc):
        return JSONResponse(**await cls.exception_handler(_, exc))

    @classmethod
    async def exception_handler(cls, _, exc):
        raise NotImplementedError("Must be implemented by subclass")


class DCWizServiceException(DCWizException):
    def __init__(self, message=None, errors=None):
        super().__init__()
        self.message = message
        self.errors = errors

    @staticmethod
    async def exception_handler(_, exc):
        content = dict(
            message=exc.message or "Internal Service Error",
        )
        if exc.errors:
            content["errors"] = exc.errors
        return dict(status_code=500, content=content)


class DCWizAPIException(DCWizException):
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
            message=exc.message or f"Error {exc.method}ing {exc.url}, get status code {status_code}",
            errors=[
                Error(
                    type="API Error",
                    severity=ErrorSeverity.ERROR,
                    message=exc.response.text,
                ).dict()
            ],
        )
        return dict(status_code=status_code, content=content)


class DCWizPlatformAPIException(DCWizAPIException):
    @staticmethod
    async def exception_handler(_, exc):
        status_code = exc.response.status_code
        try:
            error = exc.response.json()
        except JSONDecodeError:
            error = exc.response.text
        content = dict(
            message=exc.message or f"Error {exc.method}ing {exc.url}, get status code {status_code}",
            errors=[
                Error(
                    type="API Error", severity=ErrorSeverity.ERROR, message=error
                ).dict()
            ],
        )
        return dict(status_code=status_code, content=content)


class DCWizDataAPIException(DCWizAPIException):
    @staticmethod
    async def exception_handler(_, exc):
        error = exc.response.json()
        if isinstance(error["detail"], list):
            errors = [
                Error(
                    type="Data Error", severity=ErrorSeverity.ERROR, message=f"{k}:{v}"
                ).dict()
                for k, v in error["detail"]
            ]
        else:
            errors = [
                Error(
                    type="Data Error", severity=ErrorSeverity.ERROR, message=str(error["detail"])
                ).dict()
            ]
        content = dict(
            message=exc.message
            or f"Data Error: {exc.method} {exc.url}: {exc.response.status_code}",
            errors=errors,
        )
        return dict(status_code=exc.response.status_code, content=content)


class DCWizServiceAPIException(DCWizAPIException):
    @staticmethod
    async def exception_handler(_, exc):
        error = exc.response.json()
        content = dict(
            message=exc.message or error["message"],
        )
        if "errors" in error:
            content["errors"] = [Error(**e).dict() for e in error["errors"]]
        return dict(status_code=exc.response.status_code, content=content)


class DCWizAuthException(DCWizAPIException):
    @staticmethod
    async def exception_handler(_, exc):
        if exc.response.status_code == 401:
            message = "Not Authenticated, please login."
        else:
            message = "Not Authorized, please use a different account."
        error = exc.response.json()
        content = dict(
            message=exc.message or message,
        )
        if "errors" in error:
            content["errors"] = [Error(**e).dict() for e in error["errors"]]
        return dict(status_code=exc.response.status_code, content=content)


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


async def exception_group_handler(_, exc):
    errors = []
    for inner_exc in exc.exceptions:
        if isinstance(inner_exc, DCWizAPIException) or isinstance(inner_exc, DCWizServiceException):
            result = await inner_exc.exception_handler(_, inner_exc)
            summary = result["content"]["message"]
            inner_errors = result["content"]["errors"]
            for error in inner_errors:
                error["message"] = f"{summary}: {error['message']}"
            errors.extend(inner_errors)
        else:
            errors.append(
                Error(
                    type="ExceptionGroup",
                    message=str(inner_exc),
                    severity=ErrorSeverity.ERROR,
                ).dict()
            )
    content = dict(
        message=str(exc.message),
        errors=errors,
    )
    return JSONResponse(status_code=500, content=content)


def setup_exception_handlers(app):
    app.add_exception_handler(
        DCWizServiceException, DCWizServiceException.exception_handler_and_response
    )
    app.add_exception_handler(DCWizAPIException, DCWizAPIException.exception_handler_and_response)
    app.add_exception_handler(
        DCWizPlatformAPIException, DCWizPlatformAPIException.exception_handler_and_response
    )
    app.add_exception_handler(
        DCWizDataAPIException, DCWizDataAPIException.exception_handler_and_response
    )
    app.add_exception_handler(
        DCWizServiceAPIException, DCWizServiceAPIException.exception_handler_and_response
    )
    app.add_exception_handler(
        DCWizAuthException, DCWizAuthException.exception_handler_and_response
    )
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ExceptionGroup, exception_group_handler)
