from langchain_groq import ChatGroq

from config.env_config import EnvConfig
from config.app_config import AppConfig

def get_model():
    env_config = EnvConfig()
    app_config = AppConfig()
    
    return ChatGroq(
        model=app_config.LLM_ACTIVE_MODEL,
        api_key=env_config.LLM_API_KEY,
        temperature=0,
        max_tokens=None,
        reasoning_format="parsed",
        timeout=None,
        max_retries=2,
    )

