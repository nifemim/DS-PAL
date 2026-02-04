"""Application configuration from environment variables."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = True
    database_path: str = "ds_pal.db"
    cache_dir: str = ".cache/datasets"
    max_dataset_rows: int = 10000
    max_file_size_mb: int = 50

    # Optional API credentials
    kaggle_username: str = ""
    kaggle_key: str = ""
    huggingface_token: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
