"""
Entry point da aplicação AI-ChatBot.
Rate limiting e CORS são responsabilidade do Yopa Proxy (deploy integrado)
ou do Caddy (deploy self-hosted via docker-compose.selfhosted.yml).
"""
from fastapi import FastAPI
from fastapi.responses import FileResponse
from src.interfaces.http.routes.agent import router as agent_router
from src.interfaces.http.routes.chat import router as chat_router
from src.interfaces.http.routes.data import router as data_router
from src.interfaces.http.routes.admin import router as admin_router

app = FastAPI()

app.include_router(agent_router)
app.include_router(chat_router)
app.include_router(data_router)
app.include_router(admin_router)


@app.get("/chat-ui", include_in_schema=False)
def chat_ui():
    return FileResponse("chat.html")
