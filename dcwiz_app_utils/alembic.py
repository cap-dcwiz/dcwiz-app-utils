import os
from logging.config import fileConfig
from .db import DBBase


def get_url_from_env():
    server = os.getenv("POSTGRES_SERVER", "localhost")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")
    db = os.getenv("POSTGRES_DB", "dcwiz_auth")
    return f"postgresql://{user}:{password}@{server}/{db}"


def get_config(context):
    config = context.config
    if config.config_file_name is not None:
        fileConfig(config.config_file_name)
    config.set_main_option("sqlalchemy.url", get_url_from_env())
    return config


def get_config_and_target_metadata(context):
    config = get_config(context)
    return config, DBBase.metadata
