from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            "/Users/gusluna/.openclaw/workspace/.env",
            ".env",
            "/Users/gusluna/.openclaw/.env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    metiche_env: str = "development"
    database_url: str = "sqlite:////app/data/db/metiche_os.db"
    openclaw_readonly_root: str = "/mnt/openclaw-ro"
    openclaw_gateway_url: str = "http://127.0.0.1:18797"
    projections_root: str = "/app/projections"
    plane_sync_enabled: bool = True
    narrator_enabled: bool = True
    soul_enabled: bool = True
    worker_poll_seconds: int = 5
    plane_base_url: str = "https://api.plane.so"
    plane_workspace_slug: str = ""
    plane_project_id: str = ""
    plane_issues_base_url: str = ""
    plane_api_key: str = ""
    plane_bearer_token: str = ""
    plane_api_url: str = ""
    plane_api_token: str = ""
    plane_timeout_seconds: int = 15

    validation_timeout_seconds: int = 10
    validation_required_channels: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_username: str = ""
    telegram_user_id: str = ""
    telegram_allowed_ids: str = "123456789"
    telegram_sandbox_mode: bool = True
    whatsapp_health_url: str = ""
    whatsapp_access_token: str = ""
    whatsapp_gateway_port: str = ""
    whatsapp_business_number: str = ""
    whatsapp_allowed_numbers: str = "+5210000000000,+5210000000000"
    whatsapp_sandbox_mode: bool = True
    dashboard_health_url: str = ""
    dashboard_health_token: str = ""
    dashboard_port: str = ""
    shopify_store_domain: str = ""
    shopify_access_token: str = ""
    shopify_store_url: str = ""
    shopify_api_version: str = "2024-10"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"

    @property
    def projections_path(self) -> Path:
        return Path(self.projections_root)


settings = Settings()
