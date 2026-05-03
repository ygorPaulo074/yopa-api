"""
Configurações globais da aplicação.
Carrega variáveis de ambiente via Pydantic BaseSettings (pydantic-settings),
instancia o rate limiter (slowapi) e expõe o objeto `settings` como ponto
único de acesso às variáveis de ambiente em todo o projeto.
"""
import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from slowapi import Limiter
from slowapi.util import get_remote_address

# Setup interativo só em development — em production o .env deve estar pré-configurado.
if os.getenv("RUN_MODE", "development") == "development" and not os.path.exists(".initialized"):
    print("\n[AI-ChatBot] Primeira execução detectada.")
    print("  1. Executar assistente de configuração (src/tools/setup.py)")
    print("  2. Configurar manualmente (.env.example → .env)\n")
    choice = input("Opção [1]: ").strip() or "1"
    if choice == "1":
        from src.tools.setup import run_setup
        run_setup()


class Settings(BaseSettings):
    AI_API_KEY: str = ""
    AI_MODEL: str = ""
    AI_TIMEOUT: int = 30
    APP_NAME: str = "AI-ChatBot"
    RUN_MODE: str = "development"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DATA_PATH: str = "./data"
    ALLOWED_ORIGINS: list[str] = ["http://localhost"]
    LOG_LEVEL: str = "INFO"
    REDIS_URL: str = "redis://localhost:6379"
    SESSION_TTL: int = 86400
    STORAGE_TYPE: str = "local"
    DATABASE_URL: str = ""
    DB_USER: str = ""
    DB_PASSWORD: str = ""
    DB_NAME: str = ""
    WEBHOOK_URL: str = ""
    ANALYZER_LANGUAGES: list[str] = ["en"]

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()

LIMITER = Limiter(key_func=get_remote_address)