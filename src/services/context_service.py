"""
Gerencia o versionamento de contexto dos agentes.
Salva novas versões do AgentContext, calcula o diff de campos alterados para
popular o histórico (changes), e retorna versões anteriores sob demanda.
Cada PUT /agent/context cria uma nova linha em agent_contexts com version incrementado.
"""
from ..core.context_builder import build_context_xml
from src.routes.base_schemas import AgentContext

class ContextService:
    def __init__(self, storage):
        self.storage = storage

    def save_context(self, agent_id: str, context_data: AgentContext):
        #lista os contextos presentes
        #procura o com a versão mais alta
        #incrementa a versão do atual
        #salva o novo contexto com a versão incrementada
        pass

    def list_contexts(self, agent_id: str):
        #conecta no banco
        #faz fetch de todos os contextos do agent_id
        #retorna a lista de contextos em formato JSON
        pass

    def get_context(self, agent_id: str, version: int):
        #chama list contexts para obter a lista de contextos
        #procura o contexto pesquisado pela versão
        #retorna o contexto encontrado ou None se não encontrado
        pass

    def diff_contexts(self, old_context: AgentContext, new_context: AgentContext):
        #chama get_context para obter o contexto antigo
        #chama get_context para obter o contexto novo
        #compara os dois contextos e identifica os campos que foram alterados usando a biblioteca DeepDiff
        #retorna um dicionário com os campos alterados e seus valores antigos e novos
        pass

    def store_context_cache(self, agent_id: str, context_xml: str):
        #pega o ultimo contexto
        #armazena em cache para acesso rápido durante as chamadas de contexto
        #armazena conversation de chat em cache para acesso rápido durante as chamadas de contexto
        #armazena score de relevância em cache para acesso rápido durante as chamadas de contexto
        pass

