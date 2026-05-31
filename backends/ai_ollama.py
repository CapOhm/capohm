from openai import OpenAI


class AI:
    """Ollama backend with optional model profiles.

    Config options:
      - ollama_base_url: OpenAI-compatible Ollama endpoint
      - ollama_model: fallback/default model name
      - ollama_model_profile: selected profile key
      - ollama_model_profiles: mapping of profile name -> model/options

    Profile values override the base config for this backend only.
    """

    def __init__(self, config):
        self.config = config
        self.profile_name = config.get("ollama_model_profile")
        self.profile = self._load_profile(config, self.profile_name)

        self.model = self.profile.get("model", config.get("ollama_model", "llama3.2:1b"))
        self.base_url = config.get("ollama_base_url", "http://localhost:11434/v1")
        self.keep_alive = self.profile.get("keep_alive", config.get("ollama_keep_alive", "30m"))

        self.options = self._build_options(config, self.profile)

        self.client = OpenAI(
            base_url=self.base_url,
            api_key="ollama",
        )

    def _load_profile(self, config, profile_name):
        profiles = config.get("ollama_model_profiles", {}) or {}
        if not profile_name:
            return {}
        profile = profiles.get(profile_name)
        if isinstance(profile, dict):
            return profile
        return {}

    def _build_options(self, config, profile):
        # These are Ollama generation options. Profile values win over base config.
        option_map = {
            "num_predict": "ollama_num_predict",
            "num_ctx": "ollama_num_ctx",
            "temperature": "ollama_temperature",
            "top_p": "ollama_top_p",
            "top_k": "ollama_top_k",
            "repeat_penalty": "ollama_repeat_penalty",
        }

        options = {}
        for option_key, config_key in option_map.items():
            value = profile.get(option_key, config.get(config_key))
            if value is not None:
                options[option_key] = value
        return options

    def reply(self, messages):
        # Ollama's OpenAI-compatible endpoint accepts Ollama-specific options via extra_body.
        extra_body = {}
        if self.keep_alive:
            extra_body["keep_alive"] = self.keep_alive
        if self.options:
            extra_body["options"] = self.options

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            extra_body=extra_body or None,
        )
        return response.choices[0].message.content
