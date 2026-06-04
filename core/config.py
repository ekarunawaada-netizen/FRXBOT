import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    telegram_bot_token: str
    telegram_admin_ids: str
    gemini_api_key: str | None = None
    groq_api_key: str | None = None
    groq_model: str = "llama3-70b-8192"

    # Price data
    alpha_vantage_key: str | None = None
    price_cache_ttl_seconds: int = 300

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/forex_bot"
    db_pool_min: int = 2
    db_pool_max: int = 10

    # Risk engine defaults
    default_risk_pct: float = 1.0
    default_capital_usd: float = 5000.00
    default_atr_period: int = 14

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def admin_ids(self) -> List[int]:
        if not self.telegram_admin_ids:
            return []
        return [int(x.strip()) for x in self.telegram_admin_ids.split(",") if x.strip().isdigit()]

# Instantiate settings
settings = Settings()
