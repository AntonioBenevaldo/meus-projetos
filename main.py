
import os
from openai import OpenAI

# Lê a chave do ambiente OPENAI_API_KEY
client = OpenAI()


class BotEngine:
    def __init__(self):
        self.previous_response_id = None  # mantém contexto (memória)

    def start_message(self) -> str:
        return "Olá! Eu sou seu Chatbot com FastAPI + WebSocket + OpenAI. Digite sua pergunta."

    def respond(self, user_text: str) -> str:
        user_text = (user_text or "").strip()
        if not user_text:
            return "Digite alguma coisa para eu responder."

        # Exemplo: comandos locais (sem gastar IA)
        if user_text.lower() in ("menu", "ajuda"):
            return (
                "Menu:\n"
                "- Escreva qualquer pergunta e eu respondo com IA\n"
                "- Digite 'reiniciar' para limpar a memória"
            )

        if user_text.lower() == "reiniciar":
            self.previous_response_id = None
            return "Memória reiniciada. Pode mandar sua próxima pergunta."

        # Resposta via OpenAI Responses API (com contexto)
        kwargs = {
            "model": "gpt-4o-mini",
            "input": user_text,
        }

        # Mantém estado da conversa
        if self.previous_response_id:
            kwargs["previous_response_id"] = self.previous_response_id

        response = client.responses.create(**kwargs)

        # salva o id para manter contexto na próxima msg
        self.previous_response_id = response.id

        return response.output_text
