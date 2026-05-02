from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from src.infrastructure.config import settings, LIMITER
from src.routes.agent.index import router as agent_router
from src.routes.chat.index import router as chat_router
from src.routes.data.index import router as data_router

app = FastAPI()

app.state.limiter = LIMITER

async def rate_limit_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"error": "rate_limit_exceeded", "message": "Too many requests."}
    )

app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

_origins = ["*"] if settings.RUN_MODE == "development" else settings.ALLOWED_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agent_router)
app.include_router(chat_router)
app.include_router(data_router)
