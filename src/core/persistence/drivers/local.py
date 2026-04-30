"""
Driver de persistência em sistema de arquivos local.
Armazena agentes, sessões e scores como arquivos XML/JSON em DATA_PATH.
Estrutura de diretórios:
  {DATA_PATH}/agents/{agent_id}/context.xml
  {DATA_PATH}/agents/{agent_id}/chats/{session_id}/scores.json
  {DATA_PATH}/agents/{agent_id}/chats/{session_id}/insights.xml
Indicado para desenvolvimento e ambientes sem banco de dados.
"""
