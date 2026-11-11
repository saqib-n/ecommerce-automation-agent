"""Builds the chat model every step of the agent uses.

Pick the provider and model with LLM_MODEL in .env, e.g.
    openai:gpt-5.5
    anthropic:claude-opus-5-5
    google_genai:gemini-3.5-flash

No temperature is set on purpose. Current OpenAI GPT-5 models ignore it and
current Claude models reject anything but the default, so passing one would
make the Anthropic option fail. Gemini works fine on its default too.
"""

import os

from langchain.chat_models import init_chat_model

DEFAULT_MODEL = "openai:gpt-5.5"


def get_llm(model: str | None = None):
    return init_chat_model(model or os.getenv("LLM_MODEL") or DEFAULT_MODEL)
