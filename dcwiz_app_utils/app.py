from fastapi import HTTPException
from fastapi.responses import JSONResponse

from .response import ResponseBase, Error, ErrorSeverity


async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content=ResponseBase(
            message=str(exc.detail),
            errors=[
                Error(
                    type="HTTPException",
                    message=str(exc.detail),
                    severity=ErrorSeverity.ERROR,
                )
            ],
        ).dict(exclude_none=True),
    )


def setup_app(app):
    app.add_exception_handler(HTTPException, http_exception_handler)
