import json
import litellm
import redis as redis_lib
import re
import os
from pydantic import BaseModel, HttpUrl, ValidationError
from litellm.exceptions import AuthenticationError
from src.tools.deployment_scripts import (
    create_sql_scripts,
    create_prisma_migrate,
    generate_dockerfile,
    generate_docker_compose,
)
DEPLOY_OPTIONS = {
    "1": "local",
    "2": "docker",
}

PROVIDER_OPTIONS = {
    "1": "claude-sonnet-4",
    "2": "gpt-4o",
    "3": "gemini/gemini-2.0-flash",
    "4": "deepseek/deepseek-chat",
    "5": "groq/llama-3.3-70b-versatile",
}

STORAGE_OPTIONS = {
    "1": "Local",
    "2": "Database",
    "3": "Webhook",
}

ANALYZER_LANGUAGE_OPTIONS = {
    "1": ("pt", "Portuguese"),
    "2": ("es", "Spanish"),
    "3": ("fr", "French"),
    "4": ("de", "German"),
    "5": ("it", "Italian"),
    "6": ("ja", "Japanese"),
    "7": ("zh", "Chinese"),
}


class CORSConfig(BaseModel):
    allowed_origins: list[HttpUrl]


def validate_api_key(api_key, model):
    try:
        litellm.completion(
            model=model,
            messages=[{"role": "user", "content": "test"}],
            api_key=api_key,
            max_tokens=1,
        )
        return True
    except AuthenticationError:
        print("Invalid API key. Please enter a valid API key.")
        return False
    except Exception as e:
        print(f"An unexpected error occurred while validating the API key: {e}")
        return False


def validate_redis_url(redis_url: str) -> bool:
    pattern = r"^rediss?://.*|^unix://.*"
    if not re.match(pattern, redis_url):
        print("Invalid format. Use redis://, rediss:// or unix://")
        print("  redis://localhost:6379")
        print("  redis://:password@localhost:6379")
        print("  rediss://user:password@host:6380  (TLS)")
        return False
    try:
        r = redis_lib.from_url(redis_url, socket_connect_timeout=5)
        r.ping()
        return True
    except Exception as e:
        print(f"Failed to connect to Redis: {e}")
        return False


def validate_database_url(database_url):
    pattern = r"^(postgresql|postgres|mysql|sqlite)(\+\w+)?://.*"
    if re.match(pattern, database_url):
        return True
    print("Invalid database URL format.")
    print("  postgresql://user:password@localhost:5432/mydb")
    print("  sqlite:///./mydb.db")
    return False


def get_allowed_origins() -> str:
    while True:
        raw = input("Allowed origins (comma separated) [default: http://localhost]: ") or "http://localhost"
        try:
            origins = [HttpUrl(o.strip()) for o in raw.split(",")]
            CORSConfig(allowed_origins=origins)
            return json.dumps([str(o) for o in origins])
        except ValidationError:
            print("Invalid URL detected. Please enter valid URLs (ex: https://your-website.com).")


def raise_initialization_flag():
    with open(".initialized", "w") as f:
        f.write("Setup completed. Delete this file to re-run setup.")


def run_setup():
    data_path = "./data"
    database_url = ""
    db_user = ""
    db_password = ""
    db_name = ""
    webhook_url = ""

    print("\n" + "\033[1m" + "=== INITIAL SYSTEM CONFIGURATION ===" + "\033[0m")
    print("\033[1m" + "WARNING:" + "\033[0m" + " This setup should be executed only once.")
    print("To reset, delete " + "\033[1m" + ".initialized" + "\033[0m" + " and run again.\n")

    # ── Step 0: Deployment target ──────────────────────────────────────────────
    print("\033[1m" + "STEP 0: DEPLOYMENT TARGET" + "\033[0m")
    print("  1. Local  — run with 'invoke run' on this machine")
    print("  2. Docker — generate Dockerfile + docker-compose.yml")
    while True:
        deploy_choice = input("\nEnter the option number [default: 1]: ").strip() or "1"
        if deploy_choice in DEPLOY_OPTIONS:
            deploy_target = DEPLOY_OPTIONS[deploy_choice]
            break
        print("\033[1m" + "Error:" + "\033[0m" + " Enter 1 or 2.")
    is_docker = deploy_target == "docker"

    # ── Step 1: AI Provider ────────────────────────────────────────────────────
    print("\n\033[1m" + "STEP 1: SELECT AI PROVIDER" + "\033[0m")
    for key, value in PROVIDER_OPTIONS.items():
        print(f"  {key}. {value}")
    while True:
        provider_choice = input("\nEnter the option number: ").strip()
        if provider_choice in PROVIDER_OPTIONS:
            model = PROVIDER_OPTIONS[provider_choice]
            break
        print("\033[1m" + "Error:" + "\033[0m" + " Invalid selection.")

    print("\n\033[1m" + "STEP 1.5: SET A TIMEOUT" + "\033[0m")
    while True:
        timeout = input("Timeout in seconds [default: 30]: ") or "30"
        if timeout.isdigit():
            break
        print("\033[1m" + "Error:" + "\033[0m" + " Enter a valid number.")

    # ── Step 2: API Key ────────────────────────────────────────────────────────
    print("\n\033[1m" + "STEP 2: AUTHENTICATION" + "\033[0m")
    api_key = input(f"Enter your API key for {model}: ")
    while not validate_api_key(api_key, model):
        api_key = input(f"Try again - Enter your API key for {model}: ")

    # ── Step 3: Run mode ───────────────────────────────────────────────────────
    print("\n\033[1m" + "STEP 3: EXECUTION MODE" + "\033[0m")
    if is_docker:
        print("Docker deployment detected — setting RUN_MODE=production automatically.")
        run_mode = "production"
    else:
        while True:
            run_mode = input("Execution mode (development/production): ")
            if run_mode in ["development", "production"]:
                break
            print("\033[1m" + "Error:" + "\033[0m" + " Enter 'development' or 'production'.")

    # ── Step 4: Port ───────────────────────────────────────────────────────────
    print("\n\033[1m" + "STEP 4: PORT CONFIGURATION" + "\033[0m")
    while True:
        port = input("Server port [default: 8000]: ") or "8000"
        if port.isdigit():
            break
        print("\033[1m" + "Error:" + "\033[0m" + " Enter a valid port number.")

    # ── Step 5: Storage ────────────────────────────────────────────────────────
    print("\n\033[1m" + "STEP 5: STORAGE TYPE" + "\033[0m")
    while True:
        for key, value in STORAGE_OPTIONS.items():
            print(f"  {key}. {value}")
        storage_type = input("\nSelect storage type [default: 1 - Local]: ") or "1"

        if storage_type in ["1", "Local"]:
            data_path = input(
                "Path to storage directory [default: ./data]: "
            ) or "./data"

        elif storage_type in ["2", "Database"]:
            print("\n\033[1m" + "CONFIGURATION: DATABASE STORAGE" + "\033[0m")
            database_url = input("Database connection string\n"
                                 "Format: protocol://user:password@host:port/database\n> ")
            while not validate_database_url(database_url):
                database_url = input("Try again\n> ")

            db_user = input("Database user [default: postgres]: ") or "postgres"
            db_password = input("Database password: ")
            while not db_password:
                print("\033[1m" + "Error:" + "\033[0m" + " Password cannot be empty.")
                db_password = input("Database password: ")
            db_name = input("Database name [default: chatbot]: ") or "chatbot"

            while True:
                use_schema = input("\nGenerate SQL schema scripts? (yes/no): ").strip().lower()
                if use_schema in ["yes", "sim"]:
                    print("\n  1. SQL Script\n  2. Prisma Migrate")
                    schema_type = input("Option: ")
                    os.makedirs("scripts", exist_ok=True)
                    if schema_type == "1":
                        create_sql_scripts()
                    elif schema_type == "2":
                        create_prisma_migrate()
                    break
                elif use_schema in ["no", "nao"]:
                    print("\033[1m" + "Warning:" + "\033[0m" + " Create the schema manually before running.")
                    break
                print("\033[1m" + "Error:" + "\033[0m" + " Enter 'yes' or 'no'.")

        elif storage_type in ["3", "Webhook"]:
            webhook_url = input("Webhook URL\nFormat: https://your-webhook-url.com\n> ")
        else:
            print("\033[1m" + "Error:" + "\033[0m" + " Invalid storage type. Try again.")
            continue

        if storage_type in STORAGE_OPTIONS.values() or storage_type in STORAGE_OPTIONS.keys():
            break

    storage_type = STORAGE_OPTIONS.get(storage_type, storage_type)

    # ── Step 6: Redis ──────────────────────────────────────────────────────────
    print("\n\033[1m" + "STEP 6: REDIS CONFIGURATION" + "\033[0m")
    print("Redis handles context caching, session history and NLP scores.")

    if is_docker:
        redis_default = "redis://redis:6379"
        print(f"Docker mode — default Redis URL is \033[1m{redis_default}\033[0m (compose service name).")
        redis_url = input(f"Redis URL [default: {redis_default}]: ").strip() or redis_default
        print("\033[1m" + "Note:" + "\033[0m" + " Redis connection will not be tested (container not running yet).")
    else:
        while True:
            redis_url = input("Redis URL [default: redis://localhost:6379]: ").strip() or "redis://localhost:6379"
            if validate_redis_url(redis_url):
                break

    print("\n\033[1m" + "STEP 6.5: SESSION TTL" + "\033[0m")
    while True:
        session_ttl = input("Session TTL in seconds [default: 86400 (24h)]: ").strip() or "86400"
        if session_ttl.isdigit():
            break
        print("\033[1m" + "Error:" + "\033[0m" + " Enter a valid number.")

    # ── Step 7: Analyzer languages ─────────────────────────────────────────────
    print("\n\033[1m" + "STEP 7: ANALYZER LANGUAGES" + "\033[0m")
    print("English is always included. Select additional languages:")
    for key, (code, name) in ANALYZER_LANGUAGE_OPTIONS.items():
        print(f"  {key}. {name} ({code})")
    analyzer_languages = ["en"]
    while True:
        raw = input("Languages (comma separated numbers) [default: none]: ").strip()
        if not raw:
            break
        selections = [s.strip() for s in raw.split(",")]
        invalid = [s for s in selections if s not in ANALYZER_LANGUAGE_OPTIONS]
        if invalid:
            print(f"\033[1m" + "Error:" + "\033[0m" + f" Invalid options: {', '.join(invalid)}.")
            continue
        selected_codes = [ANALYZER_LANGUAGE_OPTIONS[s][0] for s in selections]
        analyzer_languages += selected_codes
        print(f"\nDownloading translation packages: {', '.join(selected_codes)} → en")
        try:
            from argostranslate import package as argo_package
            argo_package.update_package_index()
            available = argo_package.get_available_packages()
            for code in selected_codes:
                pkg = next((p for p in available if p.from_code == code and p.to_code == "en"), None)
                if pkg:
                    argo_package.install_from_path(pkg.download())
                    print(f"  ✓ {code} → en installed.")
                else:
                    print(f"  ✗ Package {code} → en not found.")
        except Exception as e:
            print(f"\033[1m" + "Warning:" + "\033[0m" + f" Could not download packages: {e}")
        break

    # ── Step 8: CORS ───────────────────────────────────────────────────────────
    print("\n\033[1m" + "STEP 8: CORS CONFIGURATION" + "\033[0m")
    allowed_origins = get_allowed_origins()

    # ── Write .env ─────────────────────────────────────────────────────────────
    print("\n\033[1m" + "FINALIZING CONFIGURATION..." + "\033[0m")
    with open(".env", "w") as f:
        f.write(f"AI_API_KEY={api_key}\n")
        f.write(f"AI_TIMEOUT={timeout}\n")
        f.write(f"AI_MODEL={model}\n")
        f.write(f"RUN_MODE={run_mode}\n")
        f.write(f"PORT={port}\n")
        f.write(f"STORAGE_TYPE={storage_type}\n")
        if storage_type == "Local":
            f.write(f"DATA_PATH={data_path}\n")
        elif storage_type == "Database":
            f.write(f"DATABASE_URL={database_url}\n")
            f.write(f"DB_USER={db_user}\n")
            f.write(f"DB_PASSWORD={db_password}\n")
            f.write(f"DB_NAME={db_name}\n")
        elif storage_type == "Webhook":
            f.write(f"WEBHOOK_URL={webhook_url}\n")
        f.write(f"REDIS_URL={redis_url}\n")
        f.write(f"SESSION_TTL={session_ttl}\n")
        f.write(f"ALLOWED_ORIGINS={allowed_origins}\n")
        f.write(f"ANALYZER_LANGUAGES={json.dumps(analyzer_languages)}\n")

    # ── Generate Docker files ──────────────────────────────────────────────────
    if is_docker:
        print("\n\033[1m" + "GENERATING DOCKER FILES..." + "\033[0m")
        generate_dockerfile(port)
        generate_docker_compose(port, storage_type)
        print("\n\033[1m" + "Next steps:" + "\033[0m")
        print(f"  1. docker compose up --build")
        print(f"  2. API available at http://localhost:{port}")

    raise_initialization_flag()
    print("\n\033[1m" + "Configuration completed successfully!" + "\033[0m" + " .env generated.\n")


if __name__ == "__main__":
    run_setup()
