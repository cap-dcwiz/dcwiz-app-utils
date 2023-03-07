import asyncio
import contextlib
import json
from loguru import logger
from random import uniform
from typing import Union

from .error import (
    DCWizPlatformAPIException,
    DCWizServiceAPIException,
    DCWizDataAPIException,
    DCWizAPIException,
    DCWizServiceException,
    Error,
    ErrorSeverity, DCWizAuthException,
)
from httpx import AsyncClient, Response, BasicAuth
import pandas as pd
from cachetools import TTLCache, cached
from cachetools.keys import hashkey
from asyncache import cached as async_cached
from dynaconf import Dynaconf

EVENT_URL = "/task/{category}/api/task-manager/event/{event}"


class _Alias:
    def __init__(self, parent, name=None):
        self.parent = parent
        self.name = name

    def request(self, *args, **kwargs):
        if self.name:
            return getattr(self.parent, f"{self.name}_request")(*args, **kwargs)
        else:
            return self.parent.request(*args, **kwargs)

    def parallel_request(self, *args, **kwargs):
        if self.name:
            return getattr(self.parent, f"{self.name}_parallel_request")(
                *args, **kwargs
            )
        else:
            return self.parent.parallel_request(*args, **kwargs)

    def get(self, *args, **kwargs):
        return self.request("GET", *args, **kwargs)

    def post(self, *args, **kwargs):
        return self.request("POST", *args, **kwargs)

    def put(self, *args, **kwargs):
        return self.request("PUT", *args, **kwargs)

    def delete(self, *args, **kwargs):
        return self.request("DELETE", *args, **kwargs)


class APIProxy:
    ALIASES = {
        "api": None,
        "platform": None,
        "data": "utinni",
        "utinni": "utinni",
        "service": "service",
        "auth": "auth",
    }

    def __init__(
        self,
        base_url: str,
        cache_ttl=120,
        cache_ttl_var=60,
        timeout=60,
        auth_info=None,
        verify=False,
    ):
        self.base_url = base_url.rstrip("/")
        self.cache_ttl = cache_ttl
        self.cache_ttl_var = cache_ttl_var
        self.timeout = timeout
        self.auth_info = auth_info
        self.verify = verify

        for alias, name in self.ALIASES.items():
            setattr(self, alias, _Alias(self, name))

    @contextlib.asynccontextmanager
    async def client(self, client=None, bearer=None):
        if client:
            yield client
        else:
            client = AsyncClient(
                timeout=self.timeout,
                auth=self.auth_info,
                verify=self.verify,
                headers={"Authorization": f"Bearer {bearer}"} if bearer else None,
            )
            yield client
            await client.aclose()

    async def _request(
        self,
        method,
        url,
        *args,
        bearer=None,
        client=None,
        exception_class=DCWizAPIException,
        **kwargs,
    ):
        if "://" in url:
            full_url = url
        else:
            full_url = f"{self.base_url}{url}"

        async with self.client(client, bearer) as client:
            res = await client.request(method, full_url, *args, **kwargs)
            if res.status_code != 200:
                logger.error(f"API Error: {method} {full_url}: {res.status_code}")
                logger.debug(res.text)
                raise exception_class(method=method, url=full_url, response=res)

        return res.json()

    @staticmethod
    def _merge_dataframe(df, on: str = None):
        if isinstance(df, dict):
            df = list[df.values()]
        if on != "_index":
            df = [r.set_index(on) for r in df]
        guessed_type = None
        for r in df:
            if r.index.dtype != object:
                guessed_type = r.index.dtype
                break
        if guessed_type:
            for r in df:
                r.index = r.index.astype(guessed_type, copy=False)
        return pd.concat(df, axis=1)

    def _process_dataframe(self, df, merge_dataframe_on: str):
        if isinstance(df, list):
            df = [pd.DataFrame.from_dict(r) for r in df]
        else:
            df = {k: pd.DataFrame.from_dict(v) for k, v in df.items()}
        if merge_dataframe_on:
            df = self._merge_dataframe(df, merge_dataframe_on)
        return df

    async def _parallel(
        self,
        requests: Union[dict, list],
        bearer=None,
        request_method=None,
        **extra_kwargs,
    ):
        if isinstance(requests, list):
            async with self.client(bearer=bearer) as client:
                async with asyncio.TaskGroup() as tg:
                    tasks = [
                        tg.create_task(
                            request_method(
                                method,
                                url,
                                client=client,
                                bearer=bearer,
                                **kwargs,
                                **extra_kwargs,
                            )
                        )
                        for method, url, kwargs in requests
                    ]
                return [t.result() for t in tasks]
        elif isinstance(requests, dict):
            async with self.client(bearer=bearer) as client:
                async with asyncio.TaskGroup() as tg:
                    tasks = {
                        k: tg.create_task(
                            request_method(
                                method,
                                url,
                                client=client,
                                bearer=bearer,
                                **kwargs,
                                **extra_kwargs,
                            )
                        )
                        for k, (method, url, kwargs) in requests.items()
                    }
                return {k: t.result() for k, t in tasks.items()}
        else:
            raise DCWizServiceException(
                message="Internal Error",
                errors=[
                    Error(
                        type="Invalid API Request",
                        severity=ErrorSeverity.CRITICAL,
                        message=f"Request: {type(requests)}",
                    )
                ],
            )

    async def request(self, method, url, *args, **kwargs):
        kwargs["exception_class"] = kwargs.get(
            "exception_class", DCWizPlatformAPIException
        )
        return await self._request(method, url, *args, **kwargs)

    async def utinni_request(self, method, url, *args, as_dataframe=False, **kwargs):
        kwargs["exception_class"] = kwargs.get("exception_class", DCWizDataAPIException)
        res = await self.request(method, url, *args, **kwargs)
        if as_dataframe:
            res = pd.DataFrame.from_dict(res)
        return res

    async def service_request(self, method, url, *args, **kwargs):
        kwargs["exception_class"] = kwargs.get(
            "exception_class", DCWizServiceAPIException
        )
        return await self.request(method, url, *args, **kwargs)

    async def auth_request(self, method, url, *args, **kwargs):
        kwargs["exception_class"] = kwargs.get("exception_class", DCWizAuthException)
        return await self.request(method, url, *args, **kwargs)

    async def parallel_request(
        self,
        requests: Union[dict, list],
        bearer=None,
        **extra_kwargs,
    ):
        return await self._parallel(requests, bearer, self.request, **extra_kwargs)

    async def utinni_parallel_request(
        self,
        requests: Union[dict, list],
        as_dataframe=False,
        merge_dataframe_on=None,
        **kwargs,
    ):
        res = await self._parallel(
            requests, request_method=self.utinni_request, **kwargs
        )
        if as_dataframe or merge_dataframe_on:
            res = self._process_dataframe(res, merge_dataframe_on)
        return res

    async def service_parallel_request(
        self,
        requests: Union[dict, list],
        **kwargs,
    ):
        return await self._parallel(
            requests, request_method=self.service_request, **kwargs
        )

    async def auth_parallel_request(
        self,
        requests: Union[dict, list],
        **kwargs,
    ):
        return await self._parallel(
            requests, request_method=self.auth_request, **kwargs
        )

    @staticmethod
    def _cache_hash_key(*args, **kwargs):
        args = tuple(json.dumps(a, default=str) for a in args)
        kwargs = {k: json.dumps(v, default=str) for k, v in kwargs.items()}
        return hashkey(*args, **kwargs)

    @property
    def cache(self):
        if self.cache_ttl > 0:
            return cached(
                cache=TTLCache(
                    maxsize=1024,
                    ttl=self.cache_ttl + uniform(-0.5, 0.5) * self.cache_ttl_var,
                ),
                key=self._cache_hash_key,
            )
        else:
            return lambda func: func

    @property
    def async_cache(self):
        if self.cache_ttl > 0:
            return async_cached(
                cache=TTLCache(
                    maxsize=1024,
                    ttl=self.cache_ttl + uniform(-0.5, 0.5) * self.cache_ttl_var,
                ),
                key=self._cache_hash_key,
            )
        else:
            return lambda func: func

    @classmethod
    def from_config(cls, config: Dynaconf = None):
        if config is None:
            from .app import get_config

            config = get_config()

        username = config.get("platform.username", None)
        if username:
            auth_info = BasicAuth(username, config.platform.password)
        else:
            auth_info = None
        return cls(
            base_url=config.get("platform.base_url"),
            cache_ttl=config.get("platform.cache_ttl", 120),
            cache_ttl_var=config.get("platform.cache_ttl_var", 60),
            timeout=config.get("platform.timeout", 60),
            verify=config.get("platform.verify", True),
            auth_info=auth_info,
        )

    def __getattr__(self, item):
        return getattr(_Alias(self), item)


def get_api_proxy(config: Dynaconf = None):
    return APIProxy.from_config(config)
