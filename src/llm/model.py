from langchain_groq import ChatGroq

from utils.env_config import MyConfig

config = MyConfig()

model = ChatGroq(
    model="qwen/qwen3-32b",
    api_key=config.LLM_API_KEY,
    temperature=0,
    max_tokens=None,
    reasoning_format="parsed",
    timeout=None,
    max_retries=2,
)
