import dotenv
import os
from slowapi import Limiter
from slowapi.util import get_remote_address

dotenv.load_dotenv()

if not os.path.exists(".initialized"):
    from src.tools.setup import run_setup
    run_setup()

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost").split(",")

LIMITER = Limiter(key_func=get_remote_address)