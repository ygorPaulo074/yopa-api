from invoke import task
from pathlib import Path
import shutil
import subprocess
import sys
import os
import json

ROOT = Path(__file__).resolve().parent


# ── Helpers ────────────────────────────────────────────────────────────────────

def _read_data_path() -> Path:
    env_file = ROOT / ".env"
    data_path = ROOT / "data"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("DATA_PATH="):
                val = line.split("=", 1)[1].strip()
                if val:
                    data_path = Path(val)
                break
    return data_path


def _clear_agents(data_path: Path) -> None:
    agents_path = data_path / "agents"
    if not agents_path.exists():
        print(f"[clear] Nada para limpar em {agents_path}")
        return
    try:
        shutil.rmtree(agents_path)
        agents_path.mkdir(parents=True)
        print(f"[clear] Limpo: {agents_path}")
    except Exception as e:
        print(f"[clear] Erro: {e}", file=sys.stderr)


def _ensure_initialized() -> bool:
    flag = ROOT / ".initialized"
    if not flag.exists():
        flag.write_text("invoke")
        return True
    return False


# ── Tasks ──────────────────────────────────────────────────────────────────────

@task
def setup(c):
    """Executa o assistente de configuração interativo."""
    c.run("python src/tools/setup.py", pty=True)


@task
def run(c):
    """Sobe o servidor FastAPI com uvicorn em modo reload."""
    _ensure_initialized()
    port = os.getenv("PORT", "8000")
    c.run(f"uvicorn main:app --reload --host 0.0.0.0 --port {port}", pty=True)


@task(help={"args": "Argumentos extras para o pytest (ex: -k test_agent)"})
def test(c, args=""):
    """Executa a suíte de testes e limpa os dados gerados ao final."""
    flag = ROOT / ".initialized"
    flag_created = not flag.exists()
    if flag_created:
        flag.write_text("invoke test")

    cmd = ["python", "-m", "pytest", "src/tests/", "-v", "--tb=short"]
    if args:
        cmd += args.split()

    try:
        result = subprocess.run(cmd, cwd=str(ROOT))
    finally:
        if flag_created and flag.exists():
            flag.unlink()
        _clear_agents(_read_data_path())

    sys.exit(result.returncode)


@task(help={"path": "Caminho alternativo para a pasta de dados"})
def clear(c, path=None):
    """Limpa os dados gerados em desenvolvimento (data/agents/)."""
    data_path = Path(path) if path else _read_data_path()
    _clear_agents(data_path)


@task
def lint(c):
    """Verifica o código com ruff (instale com: pip install ruff)."""
    c.run("ruff check src/ --statistics", warn=True)


@task
def docker_build(c):
    """Builda a imagem Docker (requer Dockerfile gerado pelo setup)."""
    if not (ROOT / "Dockerfile").exists():
        print("[docker-build] Dockerfile não encontrado. Execute 'invoke setup' e escolha Docker.")
        return
    c.run("docker build -t ai-chatbot .", pty=True)


@task(help={"agent_id": "ID do agente (busca em data/agents/{id}/context/current.json)"})
def prompt(c, agent_id):
    """Imprime o system prompt atual de um agente a partir do driver local."""
    sys.path.insert(0, str(ROOT))
    from src.core.schemas import AgentContextRecord
    from src.core.context_builder import build_system_prompt
    from src.routes.base_schemas import AgentContext

    data_path = _read_data_path()
    context_file = data_path / "agents" / agent_id / "context" / "current.json"

    if not context_file.exists():
        print(f"[prompt] Contexto não encontrado: {context_file}")
        sys.exit(1)

    record = AgentContextRecord.model_validate_json(context_file.read_text())
    context = AgentContext(**record.context.model_dump())
    result = build_system_prompt(context)

    print("\n" + "─" * 60)
    print(f"  System prompt — agente: {agent_id}  (v{record.version})")
    print("─" * 60)
    print(result)
    print("─" * 60 + "\n")


@task(help={"file": "Caminho para JSON com campos do AgentContext (campos omitidos usam None)"})
def prompt_preview(c, file):
    """Imprime o system prompt a partir de um arquivo JSON de contexto."""
    sys.path.insert(0, str(ROOT))
    from src.core.context_builder import build_system_prompt
    from src.routes.base_schemas import AgentContext

    json_path = Path(file)
    if not json_path.exists():
        print(f"[prompt-preview] Arquivo não encontrado: {json_path}")
        sys.exit(1)

    data = json.loads(json_path.read_text())
    context = AgentContext.model_validate(data)
    result = build_system_prompt(context)

    print("\n" + "─" * 60)
    print(f"  System prompt preview — {json_path.name}")
    print("─" * 60)
    print(result)
    print("─" * 60 + "\n")


@task
def purge(c, days=7):
    """Remove definitivamente agentes e sessões soft-deletados há mais de N dias (padrão: 7)."""
    import sys
    sys.path.insert(0, str(ROOT))
    _ensure_initialized()
    from datetime import datetime, timezone, timedelta
    from src.core.persistence.factory import get_driver

    cutoff = (datetime.now(timezone.utc) - timedelta(days=int(days))).isoformat()
    try:
        result = get_driver().purge_deleted(before=cutoff)
        print(f"[purge] Agentes removidos definitivamente: {result['agents_purged']}")
        print(f"[purge] Sessões removidas definitivamente:  {result['sessions_purged']}")
    except NotImplementedError:
        print("[purge] Driver atual não suporta purge.", file=sys.stderr)
        sys.exit(1)
