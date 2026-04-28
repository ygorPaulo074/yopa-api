import litellm
from pydantic import BaseModel, HttpUrl, ValidationError
from typing import List

PROVIDER_OPTIONS = {
    "1": "claude-sonnet-4",
    "2": "gpt-4o",
    "3": "gemini/gemini-2.0-flash",
    "4": "deepseek/deepseek-chat",
    "5": "groq/llama-3.3-70b-versatile"
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
    print("This setup process is intended to be run only once. \n"
          "If you need to reset the setup, please delete the" + "\033[1m" + ".initialized" + "\033[0m" + " file and run this script again.")
    print("Please select your AI provider:")
    print("1. Anthropic")
    print("2. OpenAI")
    print("3. Gemini")
    print("4. Deepseek")
    print("5. Groq")

    while True:
        provider_choice = input("Enter the number corresponding to your choice: ").strip()
        if provider_choice in PROVIDER_OPTIONS:
            model = PROVIDER_OPTIONS[provider_choice]
            break
        print("Invalid choice. Please enter a valid number.")
    
    api_key = input(f"Enter your API key for {model}: ")
    while not validate_api_key(api_key, model):
        api_key = input(f"Enter your API key for {model}: ")

    while True:
        run_mode = input("Enter run mode (development/production): ")
        if run_mode in ["development", "production"]:
            break
        print("Invalid run mode. Please enter 'development' or 'production'.")

    while True:
        port = input("Enter port [default: 8000]: ") or "8000"
        if port.isdigit():
            break
        print("Invalid port. Please enter a valid number.")

    allowed_origins = get_allowed_origins()
    
    with open(".env", "w") as f:
        f.write(f"IA_API_KEY={api_key}\n")
        f.write(f"MODEL={model}\n")
        f.write(f"RUN_MODE={run_mode}\n")
        f.write(f"PORT={port}\n")
        f.write(f"ALLOWED_ORIGINS={allowed_origins}\n")

    raise_initialization_flag()

if __name__ == "__main__":
    run_setup()



