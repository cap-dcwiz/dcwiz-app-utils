"""
This module defines various exception classes and exception handlers for error handling in the DCWiz application.
"""

from enum import Enum
from json import JSONDecodeError
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from httpx import Response as HttpxResponse, ConnectError
from pydantic import BaseModel, Field


class ErrorCode(str, Enum):
    ERR_API_ERROR = "ERR_API_ERROR"
    ERR_DATA_ERROR = "ERR_DATA_ERROR"
    ERR_INTERNAL_ERROR = "ERR_INTERNAL_ERROR"
    ERR_AUTH_ERROR = "ERR_AUTH_ERROR"


class ErrorSeverity(str, Enum):
    """
    Enum class representing the severity levels of errors.

    Possible values:
    - CRITICAL: Indicates a critical error.
    - ERROR: Indicates an error.
    - WARNING: Indicates a warning.
    - INFO: Indicates an informational message.
    - DEBUG: Indicates a debug message.
    """

    CRITICAL = "Critical"
    ERROR = "Error"
    WARNING = "Warning"
    INFO = "Info"
    DEBUG = "Debug"


class Error(BaseModel):
    """
    Represents an error.

    Attributes:
        type (str): Error type.
        severity (ErrorSeverity): Error severity.
        message (str | dict): Error message.
    """

    type: str = Field(..., description="Error type")
    severity: ErrorSeverity = Field(ErrorSeverity.ERROR, description="Error severity")
    message: str | dict = Field(None, description="Error message")


class DCWizException(Exception):
    """
    Base exception class for DCWiz application.
    """

    @classmethod
    async def exception_handler_and_response(cls, _, exc):
        return JSONResponse(**await cls.exception_handler(_, exc))

    @classmethod
    async def exception_handler(cls, _, exc):
        raise NotImplementedError("Must be implemented by subclass")


class DCWizServiceException(DCWizException):
    """
    Exception class for DCWiz service-level errors.

    Attributes:
        error_message_key (str): The key for the error message for translation purposes.
        message (str): The error message.
        errors (dict): Additional error details.
        status_code (int): The HTTP status code associated with the exception.

    Methods:
        exception_handler: A static method that handles the exception and returns a response.
    """

    def __init__(
        self,
        error_message_key=ErrorCode.ERR_INTERNAL_ERROR,
        message=None,
        errors=None,
        status_code=500,
    ):
        super().__init__()
        self.message = message
        self.errors = errors
        self.status_code = status_code
        self.error_message_key = error_message_key

    @staticmethod
    async def exception_handler(_, exc, **kwargs):
        content = dict(
            message=exc.message or "Internal Service Error",
            error_message_key=exc.error_message_key,
        )
        if exc.errors:
            content["errors"] = exc.errors
        return dict(status_code=exc.status_code, content=content)


class DCWizAPIException(DCWizException):
    """
    Exception class for handling API errors in the DCWiz application.

    Attributes:
        method (str): The HTTP method used for the request.
        url (str): The URL of the request.
        response (HttpxResponse): The response object.
        message (str): The error message.

    Methods:
        exception_handler: A static method that handles the exception and returns a response.
    """

    def __init__(self, method, url, response: HttpxResponse, message=None):
        super().__init__()
        self.method = method
        self.url = url
        self.response = response
        self.message = message
        self.error_message_key = ErrorCode.ERR_INTERNAL_ERROR

    @staticmethod
    async def exception_handler(_, exc, **kwargs):
        status_code = exc.response.status_code
        content = dict(
            error_message_key=exc.response.error_message_key,
            message=exc.message
            or f"Error {exc.method}ing {exc.url}, get status code {status_code}",
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
    """
    Exception class for handling errors related to the DCWiz platform API.
    """

    @staticmethod
    async def exception_handler(_, exc, **kwargs):
        status_code = exc.response.status_code
        try:
            error = exc.response.json()
        except JSONDecodeError:
            error = exc.response.text
        content = dict(
            error_message_key=ErrorCode.ERR_DATA_ERROR,
            message=exc.message
            or f"Error {exc.method}ing {exc.url}, get status code {status_code}",
            errors=[
                Error(
                    type="API Error", severity=ErrorSeverity.ERROR, message=error
                ).dict()
            ],
        )
        return dict(
            status_code=status_code,
            content=content,
        )


class DCWizDataAPIException(DCWizAPIException):
    """
    Exception class for handling errors related to the DCWiz Data API (Utinni).
    """

    @staticmethod
    async def exception_handler(_, exc, **kwargs):
        try:
            error = exc.response.json()
            if isinstance(error["detail"], list):
                errors = [
                    Error(
                        type="Data Error",
                        severity=ErrorSeverity.ERROR,
                        message=f"{k}:{v}",
                    ).dict()
                    for k, v in error["detail"]
                ]
            else:
                errors = [
                    Error(
                        type="Data Error",
                        severity=ErrorSeverity.ERROR,
                        message=str(error["detail"]),
                    ).dict()
                ]
        except JSONDecodeError:
            errors = [
                Error(
                    type="API Error",
                    severity=ErrorSeverity.ERROR,
                    message=exc.response.text,
                ).dict()
            ]
        content = dict(
            error_message_key=ErrorCode.ERR_API_ERROR,
            message=exc.message
            or f"Data Error: {exc.method} {exc.url}: {exc.response.status_code}",
            errors=errors,
        )
        return dict(
            status_code=exc.response.status_code,
            content=content,
        )


class DCWizServiceAPIException(DCWizAPIException):
    """
    Exception class for handling errors from the DCWiz service API.
    """

    @staticmethod
    async def exception_handler(_, exc, **kwargs):
        error = exc.response.json()
        content = dict(
            error_message_key=ErrorCode.ERR_API_ERROR,
            message=exc.message or error["message"],
        )
        if "errors" in error:
            content["errors"] = [Error(**e).dict() for e in error["errors"]]
        return dict(
            status_code=exc.response.status_code,
            content=content,
        )


class DCWizAuthException(DCWizAPIException):
    """
    Exception class for handling authentication errors in the DCWiz application.
    """

    @staticmethod
    async def exception_handler(_, exc, **kwargs):
        if exc.response.status_code == 401:
            message = "Not Authenticated, please login."
        else:
            message = "Not Authorized, please use a different account."
        error = exc.response.json()
        content = dict(
            error_message_key=ErrorCode.ERR_AUTH_ERROR,
            message=exc.message or message,
        )
        if "errors" in error:
            content["errors"] = [Error(**e).dict() for e in error["errors"]]
        return dict(
            status_code=exc.response.status_code,
            content=content,
        )


async def http_exception_handler(_, exc):
    """
    Exception Handler for HTTP errors
    :param exc: Exception object
    :return: JSON response with error
    """
    message = str(exc.detail)
    content = dict(
        error_message_key=ErrorCode.ERR_INTERNAL_ERROR,
        message=message,
        errors=[
            Error(
                type="HTTP Error",
                message=message,
                severity=ErrorSeverity.ERROR,
            ).dict()
        ],
    )
    return JSONResponse(status_code=exc.status_code, content=content)


async def connect_error_handler(request, exc):
    """
    Exception Handler for Connection failure
    :param request: Request object
    :param exc: Exception object
    :return: JSON response with error
    """
    content = dict(
        error_message_key=ErrorCode.ERR_API_ERROR,
        message="Connection Error",
        errors=[
            Error(
                type="Connection Error",
                message=f"{str(exc)}: {request.url}",
                severity=ErrorSeverity.ERROR,
            ).dict()
        ],
    )
    return JSONResponse(status_code=503, content=content)


async def exception_group_handler(_, exc):
    """
    Exception Handler for Exception Groups
    :param exc: Exception object
    :return: JSON response with error
    """
    errors = []
    status_code = (
        exc.exceptions[0].status_code
        if len(exc.exceptions) == 1
        and isinstance(exc.exceptions[0], DCWizServiceException)
        else 500
    )
    for inner_exc in exc.exceptions:
        if isinstance(inner_exc, DCWizAPIException) or isinstance(
            inner_exc, DCWizServiceException
        ):
            result = await inner_exc.exception_handler(_, inner_exc)
            summary = result["content"]["message"]
            inner_errors: list[Any] = result["content"].get("errors", [])
            if not inner_errors:
                errors.append(
                    Error(
                        type="Unknown",
                        message=summary,
                        severity=ErrorSeverity.ERROR,
                    ).dict()
                )
            for error in inner_errors:
                error["message"] = (
                    f"{summary.rstrip('.!')}: {error.get('message', None)}"
                )
            errors.extend(inner_errors)
        else:
            errors.append(
                Error(
                    type="Unknown Exception Group",
                    message=str(inner_exc),
                    severity=ErrorSeverity.ERROR,
                ).dict()
            )
    content = dict(
        message="Multiple Errors" if len(errors) > 1 else errors[0]["message"],
        errors=errors,
    )
    if len(exc.exceptions) == 1 and isinstance(
        exc.exceptions[0], DCWizServiceException
    ):
        content["error_message_key"] = exc.exceptions[0].error_message_key

    return JSONResponse(status_code=status_code, content=content)


def setup_exception_handlers(app) -> None:
    """
    Setup handlers for all app level exception
    :param app: App instance
    """
    app.add_exception_handler(
        DCWizServiceException, DCWizServiceException.exception_handler_and_response
    )
    app.add_exception_handler(
        DCWizAPIException, DCWizAPIException.exception_handler_and_response
    )
    app.add_exception_handler(
        DCWizPlatformAPIException,
        DCWizPlatformAPIException.exception_handler_and_response,
    )
    app.add_exception_handler(
        DCWizDataAPIException, DCWizDataAPIException.exception_handler_and_response
    )
    app.add_exception_handler(
        DCWizServiceAPIException,
        DCWizServiceAPIException.exception_handler_and_response,
    )
    app.add_exception_handler(
        DCWizAuthException, DCWizAuthException.exception_handler_and_response
    )
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(ConnectError, connect_error_handler)
    app.add_exception_handler(ExceptionGroup, exception_group_handler)
