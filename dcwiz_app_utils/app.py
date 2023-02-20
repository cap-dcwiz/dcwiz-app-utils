import pkgutil
from importlib import import_module

from fastapi import HTTPException, FastAPI
from fastapi.responses import JSONResponse
from dynaconf import Dynaconf

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


config: Dynaconf = NotImplemented


def get_config() -> Dynaconf:
    global config
    if config is NotImplemented:
        raise RuntimeError("Config not initialized")
    return config


def set_config(_config: Dynaconf):
    global config
    config = _config


def setup_app(app: FastAPI):
    app.add_exception_handler(HTTPException, http_exception_handler)


def get_router_maps(_path, _name):
    router_map = {}
    for module in pkgutil.iter_modules(_path):
        if not module.ispkg:
            continue
        try:
            sub_app = import_module(f"{_name}.{module.name}.router")
            router = getattr(sub_app, "router", None)
            if router:
                if module.name == "default":
                    router_map[""] = router
                else:
                    router_map[f"/{module.name}"] = router
        except Exception as e:
            print(e)
    return router_map
