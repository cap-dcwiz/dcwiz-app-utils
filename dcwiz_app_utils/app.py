import pkgutil
from importlib import import_module

from fastapi import HTTPException, FastAPI
from dynaconf import Dynaconf

from .error import http_exception_handler, dcwiz_exception_handler, DCWizException

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
    app.add_exception_handler(DCWizException, dcwiz_exception_handler)


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
