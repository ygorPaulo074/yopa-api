"""
Driver de persistência via banco de dados relacional.
Executa queries contra o schema gerado por create_db_scripts.py usando
a DATABASE_URL configurada no .env (PostgreSQL 14+).
Responsável por gravar e ler agentes, agent_contexts, user_contexts,
sessions, messages, scores e insights nas tabelas correspondentes.
"""
