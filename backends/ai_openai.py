import os
from openai import OpenAI

class AI:
    def __init__(self, config: dict):
        self.model = os.getenv("OPENAI_MODEL") or config.get("openai_model", "gpt-3.5-turbo")
        self.client = OpenAI()

    def reply(self, messages: list[dict]) -> str:
        response = self.client.chat.completions.create(model=self.model, messages=messages)
        return response.choices[0].message.content or ""
