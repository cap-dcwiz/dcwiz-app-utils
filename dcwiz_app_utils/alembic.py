import os
from logging.config import fileConfig
from dynaconf import Dynaconf
from .db import DBBase


def get_url_from_env():
    server = os.getenv("POSTGRES_SERVER", "localhost")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")
    db = os.getenv("POSTGRES_DB", "dcwiz_auth")
    return f"postgresql://{user}:{password}@{server}/{db}"


def get_url():
    config_file = os.getenv("DCWIZ_APP_CONFIG", False)
    if config_file:
        config_dict = Dynaconf(settings_files=[config_file])
        return config_dict["sqlalchemy.url"]
    else:
        return get_url_from_env()


def get_config(context):
    config = context.config
    if config.config_file_name is not None:
        fileConfig(config.config_file_name)
    config.set_main_option("sqlalchemy.url", get_url())
    return config
