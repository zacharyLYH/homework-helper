from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openrouter_model: str = "openrouter/free"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    homework_alignment_threshold: float = 0.4
    host: str = "127.0.0.1"
    port: int = 8000
    database_path: str = ""
    debug_database_path: str = ""
    environment: str = "dev"
    memory_enabled: bool = False
    memory_strict_mode: bool = True

    jwt_secret_key: str = ""
    aes_secret_key: str = ""
    cookie_domain: str = ""
    structured_logging_pct: int = 50
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
