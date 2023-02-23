from functools import wraps
from types import GenericAlias

from typing import Type, get_origin, get_args

import pydantic
from pydantic import BaseModel, Field

from .error import Error


class ORMLinkedSchema(BaseModel):
    class Config:
        orm_mode = True
        allow_population_by_field_name = True


class ResponseBase(BaseModel):
    message: str = Field(None, description="Message")
    errors: list[Error] = Field(None, description="List of errors")


_response_wrapper_cache = {}


def response_wrapper(base_model_type=None) -> Type[ResponseBase]:
    if not base_model_type:
        return ResponseBase
    if (
        isinstance(base_model_type, GenericAlias)
        and get_origin(base_model_type) is list
    ):
        many = True
        base_model_type = get_args(base_model_type)[0]
    else:
        many = False
    if many:
        name = f"{base_model_type.__name__}ListResponse"
    else:
        name = f"{base_model_type.__name__}Response"
    if name not in _response_wrapper_cache:
        if base_model_type is None:
            _response_wrapper_cache[name] = pydantic.create_model(
                name, __base__=ResponseBase
            )
        else:
            result_field = (
                (list[base_model_type], None) if many else (base_model_type, None)
            )
            _response_wrapper_cache[name] = pydantic.create_model(
                name, __base__=ResponseBase, result=result_field
            )
    return _response_wrapper_cache[name]


def wrap_response(message=None):
    def wrapper(func):
        ret_type = func.__annotations__.get("return")
        response_model = response_wrapper(ret_type)
        func.__annotations__["return"] = response_model

        @wraps(func)
        async def wrapped(*args, **kwargs):
            result = await func(*args, **kwargs)
            if ret_type is None:
                return response_model(message=message)
            else:
                return response_model(message=message, result=result)

        return wrapped

    return wrapper
