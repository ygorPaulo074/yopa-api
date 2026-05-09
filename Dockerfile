# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ── 1. Pacotes leves ─────────────────────────────────────────────────────────
# Raramente mudam → camada de cache estável.
COPY requirements-base.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout 180 -r requirements-base.txt

# ── 2. Pacotes pesados ───────────────────────────────────────────────────────
# spacy, litellm, torch (via argostranslate) e similares são grandes e lentos.
# 3 tentativas com intervalo crescente para tolerar timeouts de rede.
COPY requirements-heavy.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout 600 -r requirements-heavy.txt \
    || (echo "[retry 2/3] aguardando 30s..." && sleep 30 \
        && pip install --timeout 600 -r requirements-heavy.txt) \
    || (echo "[retry 3/3] aguardando 60s..." && sleep 60 \
        && pip install --timeout 600 -r requirements-heavy.txt)

# ── 3. Modelo spaCy ──────────────────────────────────────────────────────────
RUN python -m spacy download en_core_web_sm \
    || (sleep 10 && python -m spacy download en_core_web_sm)

# ── 4. Código da aplicação ───────────────────────────────────────────────────
COPY . .

ENV RUN_MODE=production

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
