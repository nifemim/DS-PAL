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

    # LLM insights
    llm_provider: str = ""  # "anthropic", "ollama", or empty to disable
    anthropic_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = ""  # optional override; defaults per provider

    @property
    def insights_enabled(self) -> bool:
        if self.llm_provider == "anthropic":
            return bool(self.anthropic_api_key)
        if self.llm_provider == "ollama":
            return True
        return False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
