"""
Thin LiteLLM wrapper.
Returns a simple callable: llm_fn(system: str, user: str) -> str
The API key and model are passed per-request from the frontend,
so nothing is stored server-side.
"""

import litellm
from models import LLMConfig


def make_llm_fn(config: LLMConfig):
    """
    Returns a callable llm_fn(system, user) -> str
    that calls LiteLLM with the supplied model + API key.
    """

    def llm_fn(system: str, user: str) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        kwargs = {
            "model": config.model,
            "messages": messages,
            "api_key": config.api_key,
        }

        if config.api_base:
            kwargs["api_base"] = config.api_base

        response = litellm.completion(**kwargs)
        return response.choices[0].message.content.strip()

    return llm_fn
