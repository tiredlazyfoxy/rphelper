"""Application configuration.

One `Settings` model, with explicit `RPHELPER_<FIELD>` validation aliases rather than
an `env_prefix`, and an `lru_cache` accessor so the environment is parsed once per
process. The env file resolves relative to the backend working directory. Ports are
deliberately not settings — they are topology, hardcoded elsewhere.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Field(default=Path("data"), validation_alias="RPHELPER_DATA_DIR")
    db_filename: str = Field(default="rphelper.sqlite", validation_alias="RPHELPER_DB_FILENAME")
    node_id: int = Field(default=0, validation_alias="RPHELPER_NODE_ID")
    session_cookie_name: str = Field(default="rphelper_session", validation_alias="RPHELPER_SESSION_COOKIE_NAME")
    session_ttl_hours: int = Field(default=720, validation_alias="RPHELPER_SESSION_TTL_HOURS")

    # logging — sinks and their thresholds (deployment.md owns the posture)
    log_console_level: str  = Field(default="DEBUG",   validation_alias="RPHELPER_LOG_CONSOLE_LEVEL")
    log_file_level: str     = Field(default="WARNING", validation_alias="RPHELPER_LOG_FILE_LEVEL")
    log_file_path: Path     = Field(default=Path("data/logs/rphelper.log"), validation_alias="RPHELPER_LOG_FILE_PATH")
    log_file_rotation: str  = Field(default="10 MB",   validation_alias="RPHELPER_LOG_FILE_ROTATION")
    log_file_retention: int = Field(default=5,         validation_alias="RPHELPER_LOG_FILE_RETENTION")


@lru_cache
def get_settings() -> Settings:
    return Settings()
