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
    openclaw_gateway_token: str = ""
    openclaw_cli_path: str = ""
    openclaw_config_path: str = ""
    openclaw_state_dir: str = "/mnt/openclaw-state"
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
    whatsapp_allowed_numbers: str = "+5210000000000,+5210000000001"
    whatsapp_sandbox_mode: bool = True
    openclaw_autoreply_polling_enabled: bool = True
    openclaw_autoreply_log_glob: str = "/mnt/openclaw-logs/openclaw-*.log"
    openclaw_autoreply_poll_seconds: int = 3
    openclaw_autoreply_state_path: str = "/app/data/openclaw-autoreply-state.json"
    openclaw_autoreply_backfill_on_start: bool = False
    openclaw_autoreply_sender_name: str = "Masa Madre"
    openclaw_session_resolver_enabled: bool = True
    openclaw_session_globs: str = (
        "/mnt/openclaw-ro/agents/masa-madre/sessions/*.jsonl,"
        "/mnt/openclaw-ro/agents/masa-madre/sessions-backup/*.jsonl,"
        "/mnt/openclaw-ro/agents/masa-madre/sessions_backup/*.jsonl"
    )
    openclaw_session_resolver_max_files: int = 15
    openclaw_session_resolver_max_lines_per_file: int = 600
    openclaw_session_resolver_max_delta_seconds: int = 300
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
