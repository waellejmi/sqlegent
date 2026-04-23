from langchain_groq import ChatGroq

from config.env_config import EnvConfig

config = EnvConfig()

model = ChatGroq(
    # model="qwen/qwen3-32b",
    model="openai/gpt-oss-120b",
    api_key=config.LLM_API_KEY,
    temperature=0,
    max_tokens=None,
    reasoning_format="parsed",
    timeout=None,
    max_retries=2,
)
