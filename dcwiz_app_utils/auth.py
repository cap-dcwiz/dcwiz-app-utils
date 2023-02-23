from fastapi import HTTPException

from .platform import PlatformClient


class AuthServiceClient:
    def __init__(self, auth_url: str):
        self.auth_url = auth_url
        self.platform_client = PlatformClient(base_url=auth_url)

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
        resp = await self.platform_client.get(
            "/authz/objects", bearer=bearer, expected_status_codes=(200, 401, 403)
        )

        if resp.status_code == 401:
            raise HTTPException(status_code=401, detail="Authorization failed")

        if resp.status_code == 403:
            raise HTTPException(status_code=403, detail="Not authorized")

        for item in resp.json():
            if item.startswith("data_hall."):
                res["data_halls"].append(int(item.split(".")[1]))
            elif item.startswith("chiller_plant."):
                res["chiller_plants"].append(int(item.split(".")[1]))
        return res


def get_auth_service_client(config=None):
    return AuthServiceClient.from_config(config)
