import asyncio
import contextlib
import json
import logging
from random import uniform
from typing import Union

from .error import DCWizException, Error, ErrorSeverity
from httpx import AsyncClient, Response, BasicAuth
import pandas as pd
from cachetools import TTLCache, cached
from cachetools.keys import hashkey
from asyncache import cached as async_cached
from dynaconf import Dynaconf

EVENT_URL = "/task/{category}/api/task-manager/event/{event}"


class PlatformClient:
    def __init__(
        self,
        base_url: str,
        cache_ttl=120,
        cache_ttl_var=60,
        timeout=60,
        auth=None,
        verify=False,
    ):
        self.base_url = base_url
        self.cache_ttl = cache_ttl
        self.cache_ttl_var = cache_ttl_var
        self.timeout = timeout
        self.auth = auth
        self.verify = verify

    @contextlib.asynccontextmanager
    async def client(self, client=None, bearer=None):
        if client:
            yield client
        else:
            client = AsyncClient(
                timeout=self.timeout,
                auth=self.auth,
                verify=self.verify,
                headers={"Authorization": f"Bearer {bearer}"} if bearer else None,
            )
            yield client
            await client.aclose()

    @staticmethod
    def default_error_handler(method, url, response: Response):
        raise DCWizException(
            message=f"API Error: {method} {url}: {response.status_code}",
            errors=[
                Error(
                    type="API Error",
                    severity=ErrorSeverity.ERROR,
                    message=response.text,
                )
            ],
        )

    @staticmethod
    def utinni_error_handler(method, url, response: Response):
        raise DCWizException(
            message=f"Data Error: {method} {url}: {response.status_code}",
            errors=[
                Error(
                    type="Data Error", severity=ErrorSeverity.ERROR, message=f"{k}:{v}"
                )
                for k, v in response.json()["detail"]
            ],
        )

    async def request(
        self,
        method,
        url,
        *args,
        bearer=None,
        client=None,
        error_handler=default_error_handler,
        expected_status_codes=(200,),
        **kwargs,
    ):
        if "://" in url:
            full_url = url
        else:
            full_url = f"{self.base_url}{url}"

        try:
            async with self.client(client, bearer) as client:
                res = await client.request(method, full_url, *args, **kwargs)
        except Exception as e:
            raise DCWizException(
                message=f"Request Error: {str(e)} when {method} {full_url}",
                errors=[
                    Error(
                        type="API Error", severity=ErrorSeverity.ERROR, message=str(e)
                    )
                ],
            )

        if res.status_code not in expected_status_codes:
            logging.error(res.json()["detail"])
            error_handler(method, full_url, res)

        return res.json()

    async def utinni_request(self, method, url, *args, as_dataframe=False, **kwargs):
        res = await self.request(
            method, url, *args, error_handler=self.utinni_error_handler, **kwargs
        )
        if as_dataframe:
            res = pd.DataFrame.from_dict(res)
        return res

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

    async def parallel_request(
        self,
        requests: Union[dict, list],
        bearer=None,
        error_handler=default_error_handler,
        **extra_kwargs,
    ):
        if isinstance(requests, list):
            async with self.client(bearer=bearer) as client:
                async with asyncio.TaskGroup() as tg:
                    res = [
                        tg.create_task(
                            self.request(
                                method,
                                url,
                                client=client,
                                bearer=bearer,
                                error_handler=error_handler,
                                **kwargs,
                                **extra_kwargs,
                            )
                        )
                        for method, url, kwargs in requests
                    ]
        elif isinstance(requests, dict):
            async with self.client(bearer=bearer) as client:
                async with asyncio.TaskGroup() as tg:
                    return {
                        k: tg.create_task(
                            self.request(
                                method,
                                url,
                                client=client,
                                bearer=bearer,
                                error_handler=error_handler,
                                **kwargs,
                                **extra_kwargs,
                            )
                        )
                        for k, (method, url, kwargs) in requests.items()
                    }
        else:
            raise DCWizException(
                errors=[
                    Error(
                        type="Internal Error",
                        severity=ErrorSeverity.CRITICAL,
                        message=f"Invalid request type: {type(requests)}",
                    )
                ],
            )

    async def utinni_parallel_request(
        self,
        requests: Union[dict, list],
        as_dataframe=False,
        merge_dataframe_on=None,
        **kwargs,
    ):
        res = await self.parallel_request(
            requests, error_handler=self.utinni_error_handler, **kwargs
        )
        if as_dataframe or merge_dataframe_on:
            res = self._process_dataframe(res, merge_dataframe_on)
        return res

    async def get(self, url, *args, **kwargs):
        return await self.request("GET", url, *args, **kwargs)

    async def post(self, url, *args, **kwargs):
        return await self.request("POST", url, *args, **kwargs)

    async def put(self, url, *args, **kwargs):
        return await self.request("PUT", url, *args, **kwargs)

    async def delete(self, url, *args, **kwargs):
        return await self.request("DELETE", url, *args, **kwargs)

    async def utinni_get(self, url, *args, **kwargs):
        return await self.utinni_request("GET", url, *args, **kwargs)

    async def utinni_post(self, url, *args, **kwargs):
        return await self.utinni_request("POST", url, *args, **kwargs)

    async def utinni_put(self, url, *args, **kwargs):
        return await self.utinni_request("PUT", url, *args, **kwargs)

    async def utinni_delete(self, url, *args, **kwargs):
        return await self.utinni_request("DELETE", url, *args, **kwargs)

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

    def task_emit_event(self, event, category="system", **kwargs):
        return self.post(EVENT_URL.format(category=category, event=event), json=kwargs)

    @classmethod
    def from_config(cls, config: Dynaconf = None):
        if config is None:
            from .app import get_config

            config = get_config()

        username = config.get("platform.username", None)
        if username:
            auth = BasicAuth(username, config.platform.password)
        else:
            auth = None
        return cls(
            base_url=config.get("platform.base_url"),
            cache_ttl=config.get("platform.cache_ttl", 120),
            cache_ttl_var=config.get("platform.cache_ttl_var", 60),
            timeout=config.get("platform.timeout", 60),
            verify=config.get("platform.verify", True),
            auth=auth,
        )


def get_platform_client(config: Dynaconf = None):
    return PlatformClient.from_config(config)
