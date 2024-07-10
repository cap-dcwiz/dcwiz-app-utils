import logging

from .api_proxy import APIProxy


class AppOrAuthServiceClient:
    def __init__(self, auth_url: str):
        if not auth_url:
            logging.error("auth_url is empty")
            raise ValueError("APIProxy base_url cannot be empty")
        self.auth_url = auth_url
        self.api_proxy = APIProxy(base_url=auth_url)

    def __getattr__(self, item):
        return getattr(self.api_proxy, item)

    @classmethod
    def from_config(cls, config=None):
        if config is None:
            from .app import get_config

            config = get_config()
        return cls(auth_url=config.get("auth.url"))

    @staticmethod
    def extract_bearer(request):
        if "Authorization" in request.headers:
            return request.headers["Authorization"].replace("Bearer ", "")
        return None

    async def get_self_scopes(self, bearer: str = None, request=None):
        if not bearer and request:
            bearer = self.extract_bearer(request)
        res = dict(data_halls=[], chiller_plants=[])
        if not bearer:
            return res
        resp = await self.api_proxy.auth.get("/authz/objects", bearer=bearer)

        for item in resp["result"]:
            if item.startswith("data_hall."):
                res["data_halls"].append(item.split(".")[1])
            elif item.startswith("chiller_plant."):
                res["chiller_plants"].append(item.split(".")[1])
        return res

    async def get_self_profile(self, bearer: str = None, request=None):
        if not bearer and request:
            bearer = self.extract_bearer(request)
        if not bearer:
            return {}
        return await self.api_proxy.auth.get("/users/profile", bearer=bearer)


def get_app_or_auth_service_client(config=None):
    return AppOrAuthServiceClient.from_config(config)


def get_auth_service_client(config=None):
    """
    Deprecated. Use get_app_or_auth_service_client instead.
    :param config:
    :return:
    """
    return AppOrAuthServiceClient.from_config(config)
