from openai import OpenAI


class AI:
    def __init__(self, config):
        self.model = config.get("ollama_model", "llama3.2:1b")
        self.base_url = config.get("ollama_base_url", "http://localhost:11434/v1")

        self.client = OpenAI(
            base_url=self.base_url,
            api_key="ollama",
        )

    def reply(self, messages):
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
        )
        return response.choices[0].message.content