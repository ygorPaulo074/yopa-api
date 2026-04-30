"""
Análise local de qualidade pós-resposta, sem consumo de tokens.
Usa textblob para calcular sentiment_score e sentiment_label por mensagem.
Usa spaCy para detectar tópicos, main_topic e intent da conversa.
Executado automaticamente após cada resposta do POST /chat e persiste
os resultados em scores.json (storage Local) ou na tabela scores (Database).
"""

def list_scores(agent_id: str):
    #conecta no banco
    #faz fetch de todos os scores do agent_id
    #retorna a lista de scores em formato JSON
    pass

def get_score(agent_id: str, score_id: str):
    #chama list_scores para obter a lista de scores
    #procura o score pesquisado pelo score_id
    #retorna o score encontrado ou None se não encontrado
    pass

def analyze_response(agent_id: str, response_text: str):
    #calcula sentiment_score e sentiment_label usando textblob
    #detecta tópicos, main_topic e intent usando spaCy
    #cria um dicionário com os resultados da análise
    #salva o dicionário em scores.json (storage Local) ou na tabela scores (Database)
    pass
