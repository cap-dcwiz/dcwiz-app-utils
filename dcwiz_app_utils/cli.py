from typing import Callable

import uvicorn
from pathlib import Path
from typer import Typer, Option
from dynaconf import Dynaconf
from fastapi import FastAPI

from .app import setup_app, set_config


def create_cli_main(
    make_app: Callable[[...], FastAPI],
    envvar_prefix: str = "DCWIZ_APP",
    default_config: str | Path = "config/config.toml",
    **kwargs
):
    def main():
        typer_app = Typer()

        @typer_app.command()
        def start(
            config_path: Path = Option(
                default_config, "--config", "-c", help="Config file path"
            ),
            host: str = Option("0.0.0.0", "--host", "-h", help="Host to listen to"),
            port: int = Option(8000, "--port", "-p", help="Port to listen to"),
            loglevel: str = Option("info", "--loglevel", "-l", help="Log level"),
            root_path: str = Option(
                "", "--root-path", "-r", help="Root path for use behind reverse proxy"
            ),
        ):
            config = Dynaconf(settings_files=[config_path], envvar_prefix=envvar_prefix)
            set_config(config)
            auth_app = make_app(**kwargs)
            setup_app(auth_app)
            uvicorn.run(
                auth_app, host=host, port=port, log_level=loglevel, root_path=root_path
            )

        typer_app()

    return main
