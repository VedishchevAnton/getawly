from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Getawly"
    app_env: str = "development"
    secret_key: str = "dev-insecure-change-me"
    base_url: str = "http://localhost:8088"

    database_url: str = "postgresql+asyncpg://getawly:getawly@localhost:5432/getawly"

    session_cookie_name: str = "getawly_session"
    session_max_age: int = 60 * 60 * 24 * 14

    trial_days: int = 30

    subscription_price_rub: int = 100
    subscription_period_days: int = 30

    # stub | manual | yookassa
    payment_provider: str = "stub"
    manual_payment_details: str = ""
    admin_emails: str = ""

    platform_bot_token: str | None = None
    yookassa_shop_id: str | None = None
    yookassa_secret_key: str | None = None

    @property
    def admin_email_list(self) -> list[str]:
        return [e.strip().lower() for e in self.admin_emails.split(",") if e.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
