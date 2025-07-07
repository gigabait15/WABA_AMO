import logging
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger("uvicorn.error")
log.setLevel(logging.DEBUG)

load_dotenv()


class DBSettings(BaseSettings):
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str
    DB_PORT: int
    DB_HOST: str
    DB_URL: str

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] /".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


class MetaSettings(BaseSettings):
    TOKEN: str
    ACCOUNT_ID: str
    PHONE_NUMBER_ID: str
    VERIFY_TOKEN: str
    BASE_URL: str
    APP_ID: str
    BUS_ID: str

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] /".env.meta",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    def get_headers(self) -> Dict[str, str]:
        return {"Content-Type": "application/json", "Authorization": f"Bearer {self.TOKEN}"}


class RedisSettings(BaseSettings):
    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_DB: int
    # REDIS_PASSWORD: str
    
    @property
    def redis_url(self) -> str:
        # if self.REDIS_PASSWORD:
        #     return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] /".env.redis",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        validate_default=True,
        env_ignore_empty=True,
    )


class AmoCRMSettings(BaseSettings):
    TOKEN: str
    BASE_URL: str
    SUBDOMAIN: str
    CLIENT_SECRET: str
    CLIENT_ID: str
    CLOSED_STATUSES:list[int] = [142, 143]
    DEFAULT_PIPELINE_ID: str
    DEFAULT_STATUS_ID: str

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env.amo",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    def get_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.TOKEN}", "Content-Type": "application/json"}


class AmoChatsSettings(BaseSettings):
    AMO_CHATS_CHANNEL_ID: str
    AMO_CHATS_SECRET: str
    AMO_CHATS_ACCOUNT_ID: str
    AMO_CHATS_SCOPE_ID: str
    AMO_CHATS_SENDER_USER_AMOJO_ID: str

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env.chat",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

dbsettings = DBSettings()
metasettings = MetaSettings()
amosettings = AmoCRMSettings()
chatsettings = AmoChatsSettings()
redissettings = RedisSettings()
