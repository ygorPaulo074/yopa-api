import litellm
import re
import os
from pydantic import BaseModel, HttpUrl, ValidationError
from src.tools.create_db_scripts import create_sql_scripts, create_prisma_migrate
from typing import List

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
    except litellm.AuthenticationError:
        print("Invalid API key. Please enter a valid API key.")
        return False
    except Exception as e:
        print(f"An unexpected error occurred while validating the API key: {e}")
        return False

def validate_database_url(database_url):
    pattern = r"^(postgresql|mysql|sqlite)://.*"
    if re.match(pattern, database_url):
        return True
    print("Invalid database URL format. Expected: driver://user:password@host:port/database")
    return False
    
def get_allowed_origins() -> str:
    while True:
        raw = input("Allowed origins (comma separated) [default: http://localhost]: ") or "http://localhost"
        origins = [o.strip() for o in raw.split(",")]
        try:
            CORSConfig(allowed_origins=origins)
            return ",".join(origins)
        except ValidationError:
            print("Invalid URL detected. Please enter valid URLs (ex: https://your-website.com).")

def raise_initialization_flag():
    with open(".initialized", "w") as f:
        f.write("This file indicates that the setup has been completed. "
                "Do not delete this file unless you want to reset the setup process.")

def run_setup():

    data_path = "./data"
    database_url = ""
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
        storage_type = input("\nSelect storage type [default: Local]: ") or "Local"

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
                        create_sql_scripts()
                    elif schema_type == "2":
                        create_prisma_migrate()

                    print("\n\033[1m" + "Success:" + "\033[0m" + " Schema scripts created in 'scripts/'.")
                    print("Review and execute the scripts against your database.\n")

                    print("\033[1m" + "Important:" + "\033[0m" + " If you are using docker, you can use our pre-made docker-compose.yml. "
                    "Do you want to generate a docker-compose.yml with the database service included [You can analyse it at our wiki: https://github.com/your-repo/wiki]? (yes/no): ")
                                                                                                                                      # TODO: Criar wiki 

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
    
    print(f"\n\033[1m" + "STEP 6: CORS CONFIGURATION" + "\033[0m")
    allowed_origins = get_allowed_origins()

    print(f"\n\033[1m" + "FINALIZING CONFIGURATION..." + "\033[0m")
    with open(".env", "w") as f:
        f.write(f"IA_API_KEY={api_key}\n")
        f.write(f"MODEL={model}\n")
        f.write(f"RUN_MODE={run_mode}\n")
        f.write(f"PORT={port}\n")
        f.write(f"STORAGE_TYPE={storage_type}\n")
        if storage_type == "Local":
            f.write(f"DATA_PATH={data_path}\n")
        elif storage_type == "Database":
            f.write(f"DATABASE_URL={database_url}\n")
        elif storage_type == "Webhook":
            f.write(f"WEBHOOK_URL={webhook_url}\n")
        f.write(f"ALLOWED_ORIGINS={allowed_origins}\n")

    raise_initialization_flag()
    print("\n\033[1m" + "Configuration completed successfully!" + "\033[0m" + " .env file generated.\n")

if __name__ == "__main__":
    run_setup()
