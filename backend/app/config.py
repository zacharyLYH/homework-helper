from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openrouter_api_key: str = ""
    openrouter_model: str = "openrouter/free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    host: str = "127.0.0.1"
    port: int = 8000
    database_path: str = ""
    log_level: str = "INFO"
    environment: str = "dev"

    #TODO: Replace with actual models to use in production
    available_models: list[str] = [
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "poolside/laguna-m.1:free",
    ]

    jwt_secret_key: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
