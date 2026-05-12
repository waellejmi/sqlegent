import uuid

from langchain_core.callbacks.usage import UsageMetadataCallbackHandler
from langchain_core.runnables import RunnableConfig

from agent.state import SqlAgentState


def build_initial_state(question: str) -> SqlAgentState:
    return SqlAgentState(
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
        last_user_question=None,
        base_user_question=question,
    )


def make_runnable_config(
    thread_id: str | None = None,
    *,
    usage_callback: UsageMetadataCallbackHandler | None = None,
) -> RunnableConfig:
    callbacks: list[UsageMetadataCallbackHandler] = []
    if usage_callback is not None:
        callbacks.append(usage_callback)

    return RunnableConfig(
        configurable={
            "thread_id": thread_id if thread_id is not None else str(uuid.uuid4()),
        },
        callbacks=callbacks,
    )
