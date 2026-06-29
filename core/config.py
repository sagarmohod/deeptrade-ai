"""DeepTrade AI — Configuration management.

Loads from .env file and environment variables.
Single source of truth for all runtime configuration.
"""
from __future__ import annotations

from decimal import Decimal
from enum import Enum
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Mode(str, Enum):
    """System operating mode."""

    PAPER = "paper"
    LIVE = "live"
    BACKTEST = "backtest"


class Environment(str, Enum):
    """Runtime environment."""

    DEVELOPMENT = "development"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "DeepTrade AI"
    app_env: Environment = Environment.DEVELOPMENT
    log_level: str = "INFO"

    # Mode
    mode: Mode = Mode.PAPER
    live_trading_enabled: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://deeptrade:deeptrade_dev_password@localhost:5432/deeptrade"
    timescale_url: str = "postgresql+asyncpg://deeptrade:deeptrade_dev_password@localhost:5432/deeptrade_timeseries"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Zerodha
    kite_api_key: str = ""
    kite_api_secret: SecretStr = SecretStr("")
    kite_redirect_url: str = "http://localhost:8000/api/v1/auth/kite/callback"
    kite_access_token: str = ""
    algo_id: str = "personal_001"

    # Capital
    paper_simulated_capital: Decimal = Decimal("1000000")
    live_deployed_capital: Decimal = Decimal("15000")
    live_require_paper_validation: bool = True

    # Risk defaults
    default_per_trade_risk_pct: Decimal = Decimal("1.0")
    default_daily_loss_limit_pct: Decimal = Decimal("3.0")
    default_weekly_loss_limit_pct: Decimal = Decimal("6.0")
    default_max_concurrent_positions: int = 5

    # LLM
    llm_base_url: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = "gpt-4"

    # Frontend
    frontend_url: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Security
    secret_key: SecretStr = SecretStr("change-this-in-production")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # Observability
    prometheus_port: int = 9090
    enable_metrics: bool = True

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins to list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_live_safe(self) -> bool:
        """Live mode is safe only if explicitly enabled."""
        return self.live_trading_enabled and self.mode == Mode.LIVE


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()


settings = get_settings()
