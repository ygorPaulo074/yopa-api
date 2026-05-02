import json
import litellm
import redis as redis_lib
import re
import os
from pydantic import BaseModel, HttpUrl, ValidationError
from litellm.exceptions import AuthenticationError
from src.tools.create_db_scripts import (
    create_sql_scripts,
    create_prisma_migrate,
    generate_docker_compose,
    create_docker_compose_with_db
)
from typing import List

ANALYZER_LANGUAGE_OPTIONS = {
    "1": ("pt", "Portuguese"),
    "2": ("es", "Spanish"),
    "3": ("fr", "French"),
    "4": ("de", "German"),
    "5": ("it", "Italian"),
    "6": ("ja", "Japanese"),
    "7": ("zh", "Chinese"),
}

PROVIDER_OPTIONS = {
    "1": "claude-sonnet-4",
    "2": "gpt-4o",
    "3": "gemini/gemini-2.0-flash",
    "4": "deepseek/deepseek-chat",
    "5": "groq/llama-3.3-70b-versatile"
}

STORAGE_OPTIONS = {
    "1": "Local",
    "2": "Database",
    "3": "Webhook"
}

class CORSConfig(BaseModel):
    allowed_origins: List[HttpUrl]

def validate_api_key(api_key, model):
    try:
        litellm.completion(
            model=model,
            messages=[{"role": "user", "content": "test"}],
            api_key=api_key,
            max_tokens=1
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
        print("Examples:")
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
    print("Examples:")
    print("  postgresql://user:password@localhost:5432/mydb")
    print("  mysql://user:password@localhost:3306/mydb")
    print("  sqlite:///./mydb.db")
    return False

def get_allowed_origins() -> str:
    while True:
        raw = input("Allowed origins (comma separated) [default: http://localhost]: ") or "http://localhost"
        origins = [HttpUrl(o.strip()) for o in raw.split(",")]
        try:
            CORSConfig(allowed_origins=origins)
            return json.dumps([str(origin) for origin in origins])
        except ValidationError:
            print("Invalid URL detected. Please enter valid URLs (ex: https://your-website.com).")

def raise_initialization_flag():
    with open(".initialized", "w") as f:
        f.write("This file indicates that the setup has been completed. "
                "Do not delete this file unless you want to reset the setup process.")

def run_setup():

    data_path = "./data"
    database_url = ""
    db_user = ""
    db_password = ""
    db_name = ""
    webhook_url = ""

    print("\n" + "\033[1m" + "=== INITIAL SYSTEM CONFIGURATION ===" + "\033[0m")
    print("\033[1m" + "WARNING:" + "\033[0m" + " This setup process should be executed only once.")
    print("To reset, delete the file" + "\033[1m" + " .initialized" + "\033[0m" + " and run again.\n")

    print("\033[1m" + "STEP 1: SELECT AI PROVIDER" + "\033[0m")
    print("Available options:")
    for key, value in PROVIDER_OPTIONS.items():
        print(f"  {key}. {value}")
    while True:
        provider_choice = input("\nEnter the option number: ").strip()
        if provider_choice in PROVIDER_OPTIONS:
            model = PROVIDER_OPTIONS[provider_choice]
            break
        print("\033[1m" + "Error:" + "\033[0m" + " Invalid selection. Enter a valid number.")

    print(f"\n\033[1m" + "STEP 1.5: SET A TIMEOUT" + "\033[0m")
    while True:
        timeout = input("Enter the timeout value in seconds [default: 30]: ") or "30"
        if timeout.isdigit():
            break
        print("\033[1m" + "Error:" + "\033[0m" + " Enter a valid number.")

    print(f"\n\033[1m" + "STEP 2: AUTHENTICATION" + "\033[0m")
    api_key = input(f"Enter your API key for {model}: ")
    while not validate_api_key(api_key, model):
        api_key = input(f"Try again - Enter your API key for {model}: ")

    print(f"\n\033[1m" + "STEP 3: EXECUTION MODE" + "\033[0m")
    while True:
        run_mode = input("Execution mode (development/production): ")
        if run_mode in ["development", "production"]:
            break
        print("\033[1m" + "Error:" + "\033[0m" + " Enter 'development' or 'production'.")

    print(f"\n\033[1m" + "STEP 4: PORT CONFIGURATION" + "\033[0m")
    while True:
        port = input("Server port [default: 8000]: ") or "8000"
        if port.isdigit():
            break
        print("\033[1m" + "Error:" + "\033[0m" + " Enter a valid port number.")

    print(f"\n\033[1m" + "STEP 5: STORAGE TYPE" + "\033[0m")
    while True:
        print("Storage options:")
        for key, value in STORAGE_OPTIONS.items():
            print(f"  {key}. {value}")
        storage_type = input("\nSelect storage type [default: Local]: ") or "1"

        if storage_type in ["1", "Local"]:
            print("\n\033[1m" + "CONFIGURATION: LOCAL STORAGE" + "\033[0m")
            data_path = input("Path to storage directory (ex: /path/to/storage)\n"
                              "Make sure the application has read/write permissions: ") or "./data"

        elif storage_type in ["2", "Database"]:
            print("\n\033[1m" + "CONFIGURATION: DATABASE STORAGE" + "\033[0m")
            database_url = input("Enter the database connection string:\n"
                                 "Format: protocol://user:password@host:port/database\n> ")
            while not validate_database_url(database_url):
                database_url = input("Try again - Enter the database connection string:\n"
                                     "Format: protocol://user:password@host:port/database\n> ")

            print("\n\033[1m" + "DATABASE CREDENTIALS" + "\033[0m")
            print("These are required for the database service in docker-compose.")
            db_user = input("Database user [default: postgres]: ") or "postgres"
            db_password = input("Database password: ")
            while not db_password:
                print("\033[1m" + "Error:" + "\033[0m" + " Password cannot be empty.")
                db_password = input("Database password: ")
            db_name = input("Database name [default: chatbot]: ") or "chatbot"

            print("\n\033[1m" + "Attention:" + "\033[0m" + " This only validates the format, please make sure the database is accessible.")

            while True:
                print("\n\033[1m" + "DATA SCHEMA:" + "\033[0m")
                print("This API uses a predefined schema for data accuracy.")
                use_prebuilt_schema = input("Do you want to use the pre-built SQL schema? [You can analyse it at our wiki: "
                                            "https://github.com/your-repo/wiki] (yes/no): ").strip().lower()

                if use_prebuilt_schema in ["yes", "sim"]:
                    os.makedirs("scripts", exist_ok=True)
                    print("\nSelect the schema format: ")
                    schema_type = input("1. SQL Script\n2. Prisma Migrate\nOption: ")

                    if schema_type == "1":
                        print("\n\033[1m" + "Note:" + "\033[0m" + " The SQL script uses PostgreSQL-specific syntax (SERIAL, JSONB). "
                              "It is not compatible with MySQL or SQLite.")
                        create_sql_scripts()
                    elif schema_type == "2":
                        create_prisma_migrate()

                    print("\n\033[1m" + "Success:" + "\033[0m" + " Schema scripts created in 'scripts/'.")
                    print("Review and execute the scripts against your database.\n")

                    print("\033[1m" + "Important:" + "\033[0m" + " If you are using Docker, you can generate a docker-compose.yml. "
                          "We provide 2 options: one with the database service and schema already applied on first run, "
                          "and one without the database service (if you manage the database externally). "
                          "[You can analyse it at our wiki: https://github.com/your-repo/wiki]")

                    generate_compose = input("Would you like to generate the docker-compose.yml? (yes/no): ").strip().lower()
                    if generate_compose in ["yes", "sim"]:
                        include_db = input("Include database service with schema applied on first run? (yes/no): ").strip().lower()
                        if include_db in ["yes", "sim"]:
                            create_docker_compose_with_db()
                        else:
                            generate_docker_compose()
                        print("\n\033[1m" + "Success:" + "\033[0m" + " docker-compose.yml generated.\n")
                    break

                elif use_prebuilt_schema in ["no", "nao"]:
                    print("\n\033[1m" + "Warning:" + "\033[0m" + " Make sure to create tables and schema in the database before running the application.")
                    break
                else:
                    print("\033[1m" + "Error:" + "\033[0m" + " Enter 'yes' or 'no'.")

        elif storage_type in ["3", "Webhook"]:
            print("\n\033[1m" + "CONFIGURATION: WEBHOOK STORAGE" + "\033[0m")
            webhook_url = input("Enter the webhook URL:\nFormat: https://your-webhook-url.com\n> ")
            print("\n\033[1m" + "Attention:" + "\033[0m" + " The webhook URL must be added to ALLOWED_CORS_ORIGINS")
            print("so the application can send data correctly.\n")
        else:
            print("\033[1m" + "Error:" + "\033[0m" + " Invalid storage type. Try again.")
            continue

        if storage_type in STORAGE_OPTIONS.values() or storage_type in STORAGE_OPTIONS.keys():
            break

    storage_type = STORAGE_OPTIONS.get(storage_type, storage_type)

    print(f"\n\033[1m" + "STEP 6: REDIS CONFIGURATION" + "\033[0m")
    print("Redis is required — it handles context caching, session history and NLP scores.")
    while True:
        redis_url = input("Redis URL [default: redis://localhost:6379]: ").strip() or "redis://localhost:6379"
        if validate_redis_url(redis_url):
            break

    session_ttl = "86400"
    print(f"\n\033[1m" + "STEP 6.5: SESSION TTL" + "\033[0m")
    while True:
        session_ttl = input("Session TTL in seconds [default: 86400 (24h)]: ").strip() or "86400"
        if session_ttl.isdigit():
            break
        print("\033[1m" + "Error:" + "\033[0m" + " Enter a valid number.")

    print(f"\n\033[1m" + "STEP 7: ANALYZER LANGUAGES" + "\033[0m")
    print("Select the languages your chatbot will receive (English is always included).")
    print("The corresponding translation packages will be downloaded now (~80MB each).")
    print("Available languages:")
    for key, (code, name) in ANALYZER_LANGUAGE_OPTIONS.items():
        print(f"  {key}. {name} ({code})")
    print("  Enter the numbers separated by commas, or press Enter to skip.")
    analyzer_languages = ["en"]
    while True:
        raw = input("Languages [default: none]: ").strip()
        if not raw:
            break
        selections = [s.strip() for s in raw.split(",")]
        invalid = [s for s in selections if s not in ANALYZER_LANGUAGE_OPTIONS]
        if invalid:
            print(f"\033[1m" + "Error:" + "\033[0m" + f" Invalid options: {', '.join(invalid)}. Try again.")
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
                    print(f"  ✗ Package {code} → en not found. Skipping.")
        except Exception as e:
            print(f"\033[1m" + "Warning:" + "\033[0m" + f" Could not download packages: {e}")
            print("You can install them manually later via argostranslate.")
        break

    print(f"\n\033[1m" + "STEP 8: CORS CONFIGURATION" + "\033[0m")
    allowed_origins = get_allowed_origins()

    print(f"\n\033[1m" + "FINALIZING CONFIGURATION..." + "\033[0m")
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

    raise_initialization_flag()
    print("\n\033[1m" + "Configuration completed successfully!" + "\033[0m" + " .env file generated.\n")

if __name__ == "__main__":
    run_setup()