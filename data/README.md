# data/

Diretório de armazenamento gerado em runtime pelo driver de persistência local (`STORAGE_TYPE=local`).

**Não versione este diretório.** O `.gitignore` exclui `data/agents/` automaticamente.

A estrutura completa e os schemas de cada arquivo estão documentados na seção [Pasta data/](../README.md#pasta-data) do README principal.

## Estrutura

```
data/
└── agents/
    └── {agent_id}/
        ├── agent.json
        ├── context/
        │   ├── current.json
        │   └── history/
        │       └── v{n}.json
        ├── users/
        │   └── {user_id}.json
        └── chats/
            └── {session_id}/
                ├── session.json
                ├── scores.json
                └── insights.json
```

- Um agente recém-criado terá apenas `agent.json` e `context/`
- `chats/` é criado ao encerrar sessão (`POST /chat/{session_id}/end`)
- `users/` é criado conforme contextos de usuário são acumulados

Para limpar os dados gerados em desenvolvimento:

```bash
python src/tools/clear_data.py
```
