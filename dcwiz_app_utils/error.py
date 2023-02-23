from enum import Enum

from pydantic import BaseModel, Field
from starlette.responses import JSONResponse


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


class DCWizException(Exception):
    def __init__(self, message=None, errors=None):
        super().__init__()
        self.errors = errors or []
        if message:
            self.message = message
        else:
            self.message = ";".join(f"{e.type}: {e.message}" for e in self.errors)


async def http_exception_handler(_, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content=dict(
            message=str(exc.detail),
            errors=[
                Error(
                    type="HTTPException",
                    message=str(exc.detail),
                    severity=ErrorSeverity.ERROR,
                )
            ],
        ),
    )


async def dcwiz_exception_handler(_, exc: DCWizException):
    return JSONResponse(
        status_code=500,
        content=dict(
            message=exc.message,
            errors=exc.errors,
        ),
    )
