from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

from config.app_config import AppConfig
from config.env_config import EnvConfig


def get_model(provider="groq"):
    env_config = EnvConfig()
    app_config = AppConfig()

    if provider == "groq":
        return ChatGroq(
            model=app_config.LLM_ACTIVE_MODEL,
            api_key=env_config.LLM_API_KEY,
            temperature=0,
            max_tokens=None,
            reasoning_format="parsed",
            timeout=None,
            max_retries=2,
        )

    elif provider == "llamacpp":
        return ChatOpenAI(
            model=env_config.LOCAL_LLM_ID,
            base_url="http://localhost:8080/v1",
            api_key="bla-bla",
            temperature=0.1,
            max_tokens=None,
            timeout=None,
            max_retries=2,
        )
