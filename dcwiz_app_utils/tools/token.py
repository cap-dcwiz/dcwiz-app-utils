import os

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
import httpx
from starlette.responses import JSONResponse


class App(FastAPI):
    def __init__(self, *args, **kwargs):
        super(App, self).__init__(*args, **kwargs)
        self.auth_base = None
        self.client_id = None
        self.client_secret = None
        self.token_cache = None

    def init(
        self, auth_base: str = None, client_id: str = None, client_secret: str = None
    ):
        self.auth_base = auth_base
        self.client_id = client_id
        self.client_secret = client_secret

    @property
    def auth_url(self):
        if self.auth_base is None:
            raise ValueError("auth_base not set")
        return f"{self.auth_base}/auth"

    def get_oauth(self):
        oauth = OAuth()
        oauth.register(
            name="keycloak",
            client_id=self.client_id,
            client_secret=self.client_secret,
            server_metadata_url=f"{self.auth_base}/keycloak/realms/dcwiz/.well-known/openid-configuration",
            client_kwargs={"scope": "openid profile"},
        )
        return oauth


app = App()
app.add_middleware(SessionMiddleware, secret_key="0")


@app.get("/")
async def index():
    return RedirectResponse(url="/docs")


@app.get("/login")
async def login(request: Request):
    redirect_uri = str(request.url_for("auth"))
    return await app.get_oauth().keycloak.authorize_redirect(request, redirect_uri)


@app.get("/auth")
async def auth(request: Request):
    token = await app.get_oauth().keycloak.authorize_access_token(request)
    app.token_cache = token
    return RedirectResponse(url="/profile")


@app.get("/logout")
async def logout(request: Request):
    if app.token_cache:
        httpx.post(
            f"{app.auth_url}/users/logout",
            headers=dict(Authorization=f"Bearer {app.token_cache['refresh_token']}"),
        )
        app.token_cache = None
    return RedirectResponse(url="/login")


@app.get("/profile")
async def profile():
    if app.token_cache is None:
        return RedirectResponse(url="/login")
    res = httpx.get(
        f"{app.auth_url}/users/profile",
        headers=dict(Authorization=f"Bearer {app.token_cache['id_token']}"),
    )
    if res.status_code != 200:
        return RedirectResponse(url="/login")
    return res.json() | dict(
        access_token=app.token_cache["access_token"],
        refresh_token=app.token_cache["refresh_token"],
    )


@app.get("/token")
async def token():
    if app.token_cache is None:
        return RedirectResponse(url="/login")
    res = httpx.get(
        f"{app.auth_url}/users/profile",
        headers=dict(Authorization=f"Bearer {app.token_cache['id_token']}"),
    )
    if res.status_code != 200:
        return RedirectResponse(url="/login")
    return app.token_cache["access_token"]


@app.get("/list-users")
async def list_users():
    resp = httpx.get(
        f"{app.auth_url}/users/",
        headers=dict(Authorization=f"Bearer {app.token_cache['id_token']}"),
    )
    if resp.status_code != 200:
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    else:
        return resp.json()


def main():
    import uvicorn
    from dotenv import load_dotenv

    load_dotenv()

    app.init(
        auth_base=os.environ.get("AUTH_BASE", "https://auth.experimental.rda.ai"),
        client_id=os.environ.get("AUTH_CLIENT_ID", "dcwiz-client"),
        client_secret=os.environ.get("AUTH_CLIENT_SECRET", ""),
    )
    uvicorn.run(app, host="127.0.0.1", port=10010)
