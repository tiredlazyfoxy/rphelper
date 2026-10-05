"""Application configuration.

One `Settings` model, with explicit `RPHELPER_<FIELD>` validation aliases rather than
an `env_prefix`, and an `lru_cache` accessor so the environment is parsed once per
process. The env file resolves relative to the backend working directory. Ports are
deliberately not settings — they are topology, hardcoded elsewhere.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Field(default=Path("data"), validation_alias="RPHELPER_DATA_DIR")
    db_filename: str = Field(default="rphelper.sqlite", validation_alias="RPHELPER_DB_FILENAME")
    node_id: int = Field(default=0, validation_alias="RPHELPER_NODE_ID")
    session_cookie_name: str = Field(default="rphelper_session", validation_alias="RPHELPER_SESSION_COOKIE_NAME")
    session_ttl_hours: int = Field(default=720, validation_alias="RPHELPER_SESSION_TTL_HOURS")

    # outbound LLM calls — one timeout, in seconds, for every call feature 006 makes (D13)
    llm_request_timeout_seconds: float = Field(default=30.0, validation_alias="RPHELPER_LLM_REQUEST_TIMEOUT_SECONDS")

    # logging — sinks and their thresholds (deployment.md owns the posture)
    log_console_level: str  = Field(default="DEBUG",   validation_alias="RPHELPER_LOG_CONSOLE_LEVEL")
    log_file_level: str     = Field(default="WARNING", validation_alias="RPHELPER_LOG_FILE_LEVEL")
    log_file_path: Path     = Field(default=Path("data/logs/rphelper.log"), validation_alias="RPHELPER_LOG_FILE_PATH")
    log_file_rotation: str  = Field(default="10 MB",   validation_alias="RPHELPER_LOG_FILE_ROTATION")
    log_file_retention: int = Field(default=5,         validation_alias="RPHELPER_LOG_FILE_RETENTION")

    # web search credentials — deliberately *without* the RPHELPER_ prefix: these are the names the
    # operator's environment already uses (028 D2). Explicit aliases still, so both stay greppable.
    # The key is a `SecretStr` so no `repr`/`str` of a `Settings` can leak it; read it with
    # `.get_secret_value()`. Neither is a `$ENV_VAR` secret pointer, and neither is ever exported.
    search_cse_key: SecretStr | None = Field(default=None, validation_alias="SEARCH_CSE_KEY")
    search_cse_id: str | None = Field(default=None, validation_alias="SEARCH_CSE_ID")


@lru_cache
def get_settings() -> Settings:
    return Settings()
