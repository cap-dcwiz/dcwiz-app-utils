import pkgutil
from importlib import import_module

from fastapi import HTTPException, FastAPI, APIRouter as APIRouterBase
from dynaconf import Dynaconf

from .response import wrap_response
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


class APIRouter(APIRouterBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _make_wrapper(self, method: str, path: str, *args, ret_msg=None, **kwargs):
        def wrapper(func):
            if "response_model_exclude_unset" not in kwargs:
                kwargs["response_model_exclude_unset"] = True
            return super(APIRouter, self).api_route(
                path=path, methods=[method], *args, **kwargs
            )(wrap_response(message=ret_msg)(func))

        return wrapper

    def get(self, path: str, *args, ret_msg=None, **kwargs):
        return self._make_wrapper("GET", path, *args, ret_msg=ret_msg, **kwargs)

    def post(self, path: str, *args, ret_msg=None, **kwargs):
        return self._make_wrapper("POST", path, *args, ret_msg=ret_msg, **kwargs)

    def put(self, path: str, *args, ret_msg=None, **kwargs):
        return self._make_wrapper("PUT", path, *args, ret_msg=ret_msg, **kwargs)

    def delete(self, path: str, *args, ret_msg=None, **kwargs):
        return self._make_wrapper("DELETE", path, *args, ret_msg=ret_msg, **kwargs)

    def patch(self, path: str, *args, ret_msg=None, **kwargs):
        return self._make_wrapper("PATCH", path, *args, ret_msg=ret_msg, **kwargs)
