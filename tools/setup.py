"""
Wizard de configuração inicial do AI-ChatBot.
Gera .env e, opcionalmente, Dockerfile + docker-compose.yml.
Execute a partir da raiz do projeto: python tools/setup.py
"""
import json
import os
import secrets
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from deployment_scripts import (
    create_sql_scripts,
    create_prisma_migrate,
    generate_dockerfile,
    generate_docker_compose,
)

# ── Catálogo ───────────────────────────────────────────────────────────────────

DEPLOY_OPTIONS = {"1": "local", "2": "docker"}

AUTH_MODE_OPTIONS = {"1": "standalone", "2": "internal"}

PROVIDERS = {
    "1": {
        "name": "OpenAI",
        "validate_url": "https://api.openai.com/v1/models",
        "auth_type": "bearer",
        "models": [
            ("gpt-4o",        "multimodal, melhor custo-benefício"),
            ("gpt-4o-mini",   "versão leve e barata do 4o"),
            ("o3",            "reasoning model"),
            ("o4-mini",       "reasoning leve"),
            ("gpt-5",         "mais recente, uso geral avançado"),
            ("gpt-5-mini",    "variante econômica do GPT-5"),
            ("gpt-5-nano",    "variante ultra-leve do GPT-5"),
        ],
    },
    "2": {
        "name": "Anthropic",
        "validate_url": "https://api.anthropic.com/v1/models",
        "auth_type": "anthropic",
        "models": [
            ("claude-sonnet-4-6", "equilíbrio velocidade/capacidade"),
            ("claude-opus-4-6",   "mais poderoso, tarefas complexas"),
            ("claude-haiku-4-5",  "mais rápido e barato"),
        ],
    },
    "3": {
        "name": "Google",
        "validate_url": None,
        "auth_type": "google",
        "models": [
            ("gemini/gemini-2.0-flash", "rápido e eficiente"),
            ("gemini/gemini-2.5-pro",   "contexto enorme, multimodal"),
        ],
    },
    "4": {
        "name": "Mistral",
        "validate_url": "https://api.mistral.ai/v1/models",
        "auth_type": "bearer",
        "models": [
            ("mistral/mistral-large-latest", "mais capaz"),
            ("mistral/mistral-small-latest", "leve"),
            ("mistral/codestral-latest",     "especializado em código"),
        ],
    },
    "5": {
        "name": "DeepSeek",
        "validate_url": "https://api.deepseek.com/v1/models",
        "auth_type": "bearer",
        "models": [
            ("deepseek/deepseek-chat",     "DeepSeek-V3, competitivo em custo"),
            ("deepseek/deepseek-reasoner", "modelo de raciocínio"),
        ],
    },
    "6": {
        "name": "Cohere",
        "validate_url": "https://api.cohere.ai/v1/models",
        "auth_type": "bearer",
        "models": [
            ("command-r-plus", "forte em RAG e busca semântica"),
            ("command-r",      "versão mais leve"),
        ],
    },
}

STORAGE_OPTIONS = {"1": "local", "2": "database", "3": "webhook"}

ANALYZER_LANGUAGE_OPTIONS = {
    "1": ("pt", "Português"),
    "2": ("es", "Espanhol"),
    "3": ("fr", "Francês"),
    "4": ("de", "Alemão"),
    "5": ("it", "Italiano"),
    "6": ("ja", "Japonês"),
    "7": ("zh", "Chinês"),
}

LOG_LEVEL_OPTIONS = {"1": "DEBUG", "2": "INFO", "3": "WARNING", "4": "ERROR"}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _b(text: str) -> str:
    return f"\033[1m{text}\033[0m"


def _err(text: str) -> None:
    print(f"\033[1mErro:\033[0m {text}")


def validate_api_key(provider_num: str, api_key: str) -> tuple[bool, str]:
    p = PROVIDERS[provider_num]
    auth_type = p["auth_type"]
    url = p["validate_url"]

    if auth_type == "google":
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        headers: dict = {}
    elif auth_type == "anthropic":
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    else:
        headers = {"Authorization": f"Bearer {api_key}"}

    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return True, ""
        if r.status_code in (401, 403):
            return False, "API key inválida."
        return False, f"Status inesperado: {r.status_code}."
    except requests.exceptions.ConnectionError:
        return False, "Falha de conexão. Verifique sua internet."
    except requests.exceptions.Timeout:
        return False, "Timeout ao validar a key."
    except Exception as e:
        return False, str(e)[:120]


def validate_redis_url(url: str) -> bool:
    import re
    import redis as redis_lib
    if not re.match(r"^rediss?://.*|^unix://.*", url):
        print("  Formato inválido. Use redis://, rediss:// ou unix://")
        print("  Ex: redis://localhost:6379  |  rediss://user:pass@host:6380")
        return False
    try:
        redis_lib.from_url(url, socket_connect_timeout=5).ping()
        return True
    except Exception as e:
        print(f"  Falha ao conectar: {e}")
        return False


def validate_database_url(url: str) -> bool:
    import re
    if re.match(r"^(postgresql|postgres|mysql|sqlite)(\+\w+)?://.*", url):
        return True
    print("  Formato inválido. Ex: postgresql://user:pass@localhost:5432/db")
    return False


def _gen_encryption_key() -> str:
    try:
        from cryptography.fernet import Fernet
        return Fernet.generate_key().decode()
    except ImportError:
        import base64
        return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


def _raise_init_flag() -> None:
    with open(".initialized", "w") as f:
        f.write("Setup completed. Delete this file to re-run setup.")


# ── Wizard ─────────────────────────────────────────────────────────────────────

def run_setup() -> None:
    database_url = db_user = db_password = db_name = ""
    webhook_url = internal_token = data_path = ""

    print("\n" + _b("=== CONFIGURAÇÃO INICIAL DO AI-CHATBOT ==="))
    print(_b("AVISO:") + " Este setup deve ser executado apenas uma vez.")
    print("Para reconfigurar, delete " + _b(".initialized") + " e execute novamente.\n")

    # ── Step 0: Destino do deploy ──────────────────────────────────────────────
    print(_b("STEP 0: DESTINO DO DEPLOY"))
    print("  1. Local  — executa com 'invoke run' nesta máquina")
    print("  2. Docker — gera Dockerfile + docker-compose.yml")
    while True:
        c = input("\nOpção [default: 1]: ").strip() or "1"
        if c in DEPLOY_OPTIONS:
            deploy_target = DEPLOY_OPTIONS[c]
            break
        _err("Digite 1 ou 2.")
    is_docker = deploy_target == "docker"

    # ── Step 1: Modo de autenticação ───────────────────────────────────────────
    print("\n" + _b("STEP 1: MODO DE AUTENTICAÇÃO"))
    print("  1. Standalone — a API autentica diretamente via Bearer {agent_id}.{secret}")
    print("  2. Internal   — atrás do Yopa Proxy; X-Agent-Id injetado pelo proxy")
    while True:
        c = input("\nOpção [default: 1]: ").strip() or "1"
        if c in AUTH_MODE_OPTIONS:
            auth_mode = AUTH_MODE_OPTIONS[c]
            break
        _err("Digite 1 ou 2.")

    if auth_mode == "internal":
        internal_token = secrets.token_hex(32)
        print(f"\n  {_b('INTERNAL_TOKEN gerado:')}")
        print(f"  {_b(internal_token)}")
        print(f"  {_b('Guarde este token')} e configure-o no Yopa Proxy.")
        print("  A configuração do proxy deve ser feita separadamente.")

    # ── Step 2: Provedor de IA ─────────────────────────────────────────────────
    print("\n" + _b("STEP 2: PROVEDOR DE IA"))
    for k, p in PROVIDERS.items():
        print(f"  {k}. {p['name']}")
    while True:
        c = input("\nOpção: ").strip()
        if c in PROVIDERS:
            provider_num = c
            provider = PROVIDERS[c]
            break
        _err("Seleção inválida.")

    # ── Step 3: API Key ────────────────────────────────────────────────────────
    print(f"\n{_b('STEP 3: API KEY — ' + provider['name'])}")
    while True:
        api_key = input("Cole sua API key: ").strip()
        if not api_key:
            _err("A key não pode ser vazia.")
            continue
        print("  Validando...", end="", flush=True)
        ok, err = validate_api_key(provider_num, api_key)
        if ok:
            print(" ✓")
            break
        print(f" ✗\n  \033[1mErro:\033[0m {err}")

    # ── Step 4: Modelo ─────────────────────────────────────────────────────────
    print(f"\n{_b('STEP 4: MODELO — ' + provider['name'])}")
    models = provider["models"]
    for i, (model_id, desc) in enumerate(models, 1):
        print(f"  {i}. {model_id:<42} {desc}")
    while True:
        c = input("\nOpção: ").strip()
        if c.isdigit() and 1 <= int(c) <= len(models):
            ai_model = models[int(c) - 1][0]
            break
        _err(f"Digite um número entre 1 e {len(models)}.")

    # ── Step 5: Timeout ────────────────────────────────────────────────────────
    print("\n" + _b("STEP 5: TIMEOUT DA IA"))
    while True:
        timeout = input("Timeout em segundos [default: 30]: ").strip() or "30"
        if timeout.isdigit() and int(timeout) > 0:
            break
        _err("Digite um número válido.")

    # ── Step 6: Modo de execução ───────────────────────────────────────────────
    if is_docker:
        run_mode = "production"
        print(f"\n  Deploy Docker — RUN_MODE=production definido automaticamente.")
    else:
        print("\n" + _b("STEP 6: MODO DE EXECUÇÃO"))
        while True:
            run_mode = input("Modo (development/production): ").strip()
            if run_mode in ("development", "production"):
                break
            _err("Digite 'development' ou 'production'.")

    # ── Step 7: Porta ──────────────────────────────────────────────────────────
    print("\n" + _b("STEP 7: PORTA"))
    while True:
        port = input("Porta do servidor [default: 8000]: ").strip() or "8000"
        if port.isdigit() and 1 <= int(port) <= 65535:
            break
        _err("Porta inválida.")

    # ── Step 8: Armazenamento ──────────────────────────────────────────────────
    print("\n" + _b("STEP 8: TIPO DE ARMAZENAMENTO"))
    print("  1. Local    — arquivos JSON no disco")
    print("  2. Database — PostgreSQL / MySQL / SQLite")
    print("  3. Webhook  — persiste via HTTP para endpoint externo")
    while True:
        c = input("\nOpção [default: 1]: ").strip() or "1"
        if c not in STORAGE_OPTIONS:
            _err("Digite 1, 2 ou 3.")
            continue
        storage_type = STORAGE_OPTIONS[c]

        if storage_type == "local":
            data_path = input("Caminho do diretório de dados [default: ./data]: ").strip() or "./data"

        elif storage_type == "database":
            print("\n  " + _b("CONFIGURAÇÃO: DATABASE"))
            while True:
                database_url = input("Connection string\n  Ex: postgresql://user:pass@localhost:5432/db\n> ").strip()
                if validate_database_url(database_url):
                    break
            db_user = input("Usuário [default: postgres]: ").strip() or "postgres"
            while True:
                db_password = input("Senha: ").strip()
                if db_password:
                    break
                _err("Senha não pode ser vazia.")
            db_name = input("Nome do banco [default: chatbot]: ").strip() or "chatbot"
            while True:
                gen = input("\nGerar scripts de schema? (sim/nao): ").strip().lower()
                if gen in ("sim", "yes", "s"):
                    print("  1. SQL Script\n  2. Prisma Migrate")
                    schema_type = input("Opção: ").strip()
                    os.makedirs("scripts", exist_ok=True)
                    if schema_type == "1":
                        create_sql_scripts()
                    elif schema_type == "2":
                        create_prisma_migrate()
                    break
                elif gen in ("nao", "não", "no", "n"):
                    print("  " + _b("Atenção:") + " crie o schema manualmente antes de iniciar.")
                    break
                _err("Digite 'sim' ou 'nao'.")

        elif storage_type == "webhook":
            webhook_url = input("Webhook URL (https://...): ").strip()

        break

    # ── Step 9: Redis ──────────────────────────────────────────────────────────
    print("\n" + _b("STEP 9: REDIS"))
    print("  Usado para cache de contexto, histórico de sessão e scores NLP.")
    if is_docker:
        redis_default = "redis://redis:6379"
        print(f"  Modo Docker — URL padrão: {_b(redis_default)}")
        redis_url = input(f"Redis URL [default: {redis_default}]: ").strip() or redis_default
        print("  " + _b("Nota:") + " conexão não será testada (container ainda não rodando).")
    else:
        while True:
            redis_url = input("Redis URL [default: redis://localhost:6379]: ").strip() or "redis://localhost:6379"
            if validate_redis_url(redis_url):
                break

    # ── Step 10: TTL de sessão ─────────────────────────────────────────────────
    print("\n" + _b("STEP 10: TTL DE SESSÃO"))
    while True:
        session_ttl = input("TTL em segundos [default: 86400 (24h)]: ").strip() or "86400"
        if session_ttl.isdigit() and int(session_ttl) > 0:
            break
        _err("Digite um número válido.")

    # ── Step 11: Chave de criptografia ─────────────────────────────────────────
    print("\n" + _b("STEP 11: CHAVE DE CRIPTOGRAFIA"))
    print("  Usada para criptografar API keys por agente (BYOK) e connection strings SQL.")
    encryption_key = _gen_encryption_key()
    print(f"\n  {_b('Chave gerada:')}")
    print(f"  {_b(encryption_key)}")
    print(f"  {_b('⚠  Guarde esta chave em local seguro.')}")
    print("  Perder a chave torna os secrets armazenados irrecuperáveis.")

    # ── Step 12: Configurações de tools ───────────────────────────────────────
    print("\n" + _b("STEP 12: CONFIGURAÇÕES DE TOOLS"))
    while True:
        max_tool_rounds = input("Máximo de rounds de tool-use por mensagem [default: 5]: ").strip() or "5"
        if max_tool_rounds.isdigit() and int(max_tool_rounds) > 0:
            break
        _err("Digite um número válido.")
    while True:
        sql_timeout = input("Timeout de queries SQL em segundos [default: 10]: ").strip() or "10"
        if sql_timeout.isdigit() and int(sql_timeout) > 0:
            break
        _err("Digite um número válido.")
    while True:
        sql_max_rows = input("Máximo de linhas retornadas por query SQL [default: 50]: ").strip() or "50"
        if sql_max_rows.isdigit() and int(sql_max_rows) > 0:
            break
        _err("Digite um número válido.")

    # ── Step 13: Idiomas do analisador ─────────────────────────────────────────
    print("\n" + _b("STEP 13: IDIOMAS DO ANALISADOR NLP"))
    print("  Inglês sempre incluído. Selecione idiomas adicionais:")
    for k, (code, name) in ANALYZER_LANGUAGE_OPTIONS.items():
        print(f"  {k}. {name} ({code})")
    analyzer_languages = ["en"]
    while True:
        raw = input("Idiomas (números separados por vírgula) [default: nenhum]: ").strip()
        if not raw:
            break
        selections = [s.strip() for s in raw.split(",")]
        invalid = [s for s in selections if s not in ANALYZER_LANGUAGE_OPTIONS]
        if invalid:
            _err(f"Opções inválidas: {', '.join(invalid)}.")
            continue
        selected_codes = [ANALYZER_LANGUAGE_OPTIONS[s][0] for s in selections]
        analyzer_languages += selected_codes
        print(f"\n  Baixando pacotes: {', '.join(selected_codes)} → en")
        try:
            from argostranslate import package as argo_pkg
            argo_pkg.update_package_index()
            available = argo_pkg.get_available_packages()
            for code in selected_codes:
                pkg = next((p for p in available if p.from_code == code and p.to_code == "en"), None)
                if pkg:
                    argo_pkg.install_from_path(pkg.download())
                    print(f"  ✓ {code} → en instalado.")
                else:
                    print(f"  ✗ Pacote {code} → en não encontrado.")
        except Exception as e:
            print(_b("Aviso:") + f" não foi possível baixar pacotes: {e}")
        break

    # ── Step 14: Nível de log ──────────────────────────────────────────────────
    print("\n" + _b("STEP 14: NÍVEL DE LOG"))
    for k, lvl in LOG_LEVEL_OPTIONS.items():
        print(f"  {k}. {lvl}")
    while True:
        c = input("\nOpção [default: 2 (INFO)]: ").strip() or "2"
        if c in LOG_LEVEL_OPTIONS:
            log_level = LOG_LEVEL_OPTIONS[c]
            break
        _err("Opção inválida.")

    # ── Gravar .env ────────────────────────────────────────────────────────────
    print("\n" + _b("GERANDO .env..."))
    lines = [
        f"AI_API_KEY={api_key}",
        f"AI_MODEL={ai_model}",
        f"AI_TIMEOUT={timeout}",
        f"RUN_MODE={run_mode}",
        f"PORT={port}",
        f"STORAGE_TYPE={storage_type}",
    ]
    if storage_type == "local":
        lines.append(f"DATA_PATH={data_path}")
    elif storage_type == "database":
        lines += [
            f"DATABASE_URL={database_url}",
            f"DB_USER={db_user}",
            f"DB_PASSWORD={db_password}",
            f"DB_NAME={db_name}",
        ]
    elif storage_type == "webhook":
        lines.append(f"WEBHOOK_URL={webhook_url}")
    lines += [
        f"REDIS_URL={redis_url}",
        f"SESSION_TTL={session_ttl}",
        f"AUTH_MODE={auth_mode}",
    ]
    if auth_mode == "internal":
        lines.append(f"INTERNAL_TOKEN={internal_token}")
    lines += [
        f"SQL_ENCRYPTION_KEY={encryption_key}",
        f"MAX_TOOL_ROUNDS={max_tool_rounds}",
        f"SQL_QUERY_TIMEOUT={sql_timeout}",
        f"SQL_MAX_ROWS={sql_max_rows}",
        f"ANALYZER_LANGUAGES={json.dumps(analyzer_languages)}",
        f"LOG_LEVEL={log_level}",
    ]
    with open(".env", "w") as f:
        f.write("\n".join(lines) + "\n")
    print("  ✓ .env gerado.")

    # ── Arquivos Docker ────────────────────────────────────────────────────────
    if is_docker:
        print("\n" + _b("GERANDO ARQUIVOS DOCKER..."))
        generate_dockerfile(port)
        generate_docker_compose(port, storage_type)
        print("\n" + _b("Próximos passos:"))
        print(f"  1. docker compose up --build")
        print(f"  2. API disponível em http://localhost:{port}")

    _raise_init_flag()
    print("\n" + _b("Configuração concluída!") + " .env gerado.\n")


if __name__ == "__main__":
    run_setup()
