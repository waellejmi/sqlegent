import uuid

from langchain_core.callbacks.usage import UsageMetadataCallbackHandler
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from agent.state import AgentState


def build_initial_state(question: str) -> AgentState:
    return AgentState(
        messages=[HumanMessage(content=question)],
        user_question=question,
        last_query=None,
        previous_queries=[],
        analysis_result=None,
        skip_decision=None,
        db_output=None,
        retry_count=0,
        schema_context=None,
        instruction_context=None,
        query_memory_context=None,
    )


def make_runnable_config(
    *,
    bypass_cache: bool = False,
    invalidate_cache: bool = False,
    usage_callback: UsageMetadataCallbackHandler | None = None,
) -> RunnableConfig:
    callbacks: list[UsageMetadataCallbackHandler] = []
    if usage_callback is not None:
        callbacks.append(usage_callback)

    return RunnableConfig(
        configurable={
            "thread_id": str(uuid.uuid4()),
            "metadata_bypass_cache": bypass_cache,
            "metadata_invalidate_cache": invalidate_cache,
        },
        callbacks=callbacks,
    )
