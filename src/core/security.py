"""
Utilitários de segurança chamados internamente pelos drivers de persistência.
Nunca deve ser importado por services ou routes — a camada de persistência
(base.py e drivers) é a única responsável por acionar estas funções.

  - sanitize_pii(text)     → limpa PII de mensagens antes de persistir
  - generate_api_key()     → gera a API Key bruta no POST /agent
  - hash_api_key(key)      → armazena o hash — nunca a chave em claro
  - verify_api_key(key, hash) → valida o header Authorization nos drivers de leitura
"""

import hmac
import secrets
import hashlib
from typing import cast
from fastapi import Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from loguru import logger
from cryptography.fernet import Fernet, InvalidToken
from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities.engine.recognizer_result import RecognizerResult as AnonymizerRecognizerResult


_nlp_config = {
    "nlp_engine_name": "spacy",
    "models": [{"lang_code": "pt", "model_name": "pt_core_news_sm"}],
}
_analyzer = AnalyzerEngine(
    nlp_engine=NlpEngineProvider(nlp_configuration=_nlp_config).create_engine(),
    supported_languages=["pt", "en"],
)
_anonymizer = AnonymizerEngine()

_bearer = HTTPBearer()

def sanitize_pii(text: str) -> str:
    """Remove PII do texto antes de persistir."""
    if not text or not text.strip():
        return text
    try:
        results = cast(list[AnonymizerRecognizerResult], _analyzer.analyze(text=text, language="pt"))
        if not results:
            return text
        anonymized = _anonymizer.anonymize(text=text, analyzer_results=results)
        return anonymized.text
    except Exception as exc:
        logger.warning(f"sanitize_pii falhou, texto persiste sem sanitização: {exc}")
        return text


def generate_api_key() -> str:
    """Gera API Key bruta com 256 bits de entropia."""
    return secrets.token_urlsafe(32)


def hash_api_key(key: str) -> str:
    """Retorna SHA-256 hex da key. Nunca armazenar a key em claro."""
    return hashlib.sha256(key.encode()).hexdigest()


def verify_api_key(key: str, stored_hash: str) -> bool:
    """Compara timing-safe o hash da key com o hash armazenado."""
    return hmac.compare_digest(hash_api_key(key), stored_hash)


async def get_api_key(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> str:
    """Dependência FastAPI: extrai e retorna o token Bearer bruto."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key ausente",
        )
    return credentials.credentials


# ── Credential encryption (SQL datasource) ────────────────────────────────────

_ENC_PREFIX = "enc:"
_fernet_instance: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance
    from src.infrastructure.config import settings
    key = settings.SQL_ENCRYPTION_KEY
    if not key:
        # Gera chave efêmera — conexões SQL não podem ser reutilizadas entre restarts sem persistir a chave
        logger.warning("SQL_ENCRYPTION_KEY não configurada — usando chave efêmera (não persistente).")
        key = Fernet.generate_key().decode()
    _fernet_instance = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet_instance


def encrypt_secret(plaintext: str) -> str:
    """Criptografa um secret (ex: connection string). Retorna string com prefixo 'enc:'."""
    if plaintext.startswith(_ENC_PREFIX):
        return plaintext  # já criptografado
    token = _get_fernet().encrypt(plaintext.encode()).decode()
    return f"{_ENC_PREFIX}{token}"


def decrypt_secret(ciphertext: str) -> str:
    """Descriptografa um secret criptografado por encrypt_secret."""
    if not ciphertext.startswith(_ENC_PREFIX):
        return ciphertext  # plaintext (compatibilidade)
    try:
        return _get_fernet().decrypt(ciphertext[len(_ENC_PREFIX):].encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Falha ao descriptografar credencial — chave inválida ou dado corrompido.") from exc


def mask_connection_string(conn_str: str) -> str:
    """Retorna a connection string com a senha mascarada para exibição na API."""
    if conn_str.startswith(_ENC_PREFIX):
        return "[criptografado]"
    try:
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(conn_str)
        if parsed.password:
            netloc = parsed.netloc.replace(f":{parsed.password}@", ":***@")
            masked = urlunparse(parsed._replace(netloc=netloc))
            return masked
    except Exception:
        pass
    return conn_str
