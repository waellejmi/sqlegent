import logging

from langchain_core.runnables import RunnableConfig

from agent.prompts import (
    ANALYZE_RESULT,
    EXPLAIN_RESULT,
    GENERATE_QUERY,
    GET_SCHEMA_PROMPT,
    HANDLE_IRRELEVANT_RESULT,
    QUESTION_SYNTHESIS_PROMPT,
    REGEN_PROMPTS,
    SHOULD_SKIP,
)
from agent.state import AnalysisResult, SkipDecision, SqlAgentState, SynthesisResult
from config.app_config import AppConfig
from context_layer.service import get_context_service
from llm.model import get_model
from tools.database import (
    db,
    get_schema_tool_with_cache,
    list_tables_with_cache,
    run_query_tool_with_interrupt,
)
from tools.metadata_cache import get_cached_metadata, set_cached_metadata
from utils.helpers import _canonicalize_table_names, normalize_table_names_csv
from utils.logger_setup import LoggerSetup
from utils.logger_setup import log_node_payload as _log_node_payload
from utils.logger_setup import log_node_response as _log_node_response
from utils.message_helpers import ai_message_to_text as _ai_message_to_text

logger = LoggerSetup.get_logger(__name__, logging.DEBUG)


def question_synthesis(state: SqlAgentState):
    if not AppConfig().ENABLE_ORCHESTRATOR:
        return
    current_question = state["user_question"]

    last_user_question = state.get("last_user_question")
    if not last_user_question:
        _log_node_payload("Question Synthesis (Skipped)", current_question, logger)
        return {"user_question": current_question}

    system_message = {
        "role": "system",
        "content": QUESTION_SYNTHESIS_PROMPT.format(
            user_question=current_question,
            last_user_question=last_user_question,
        ),
    }

    structured_model = get_model().with_structured_output(SynthesisResult)
    result = structured_model.invoke([system_message])

    _log_node_payload(
        "Question Synthesis",
        {
            "original": current_question,
            "last": last_user_question,
            "synthesized": result.synthesized_question,
        },
        logger,
    )

    return {"user_question": result.synthesized_question}


def list_tables(_state: SqlAgentState):
    result = list_tables_with_cache.invoke({})

    _log_node_payload("List of tables in the database", result, logger)
    if not result:
        raise ValueError("Failed to retrieve table names from the database.")

    return {"available_tables": result}


def retrieve_context(state: SqlAgentState):
    if not AppConfig().ENABLE_CONTEXT_LAYER:
        return

    question = state["base_user_question"]

    operation_args = {
        "question": question,
    }

    cached = get_cached_metadata(
        operation="retrieve_context",
        operation_args=operation_args,
    )
    if cached is not None:
        logger.debug("retrieve_context cache hit")
        return cached

    service = get_context_service()
    result = service.retrieve_context(question)
    payload = {
        "schema_context": result.schema_text,
        "instruction_context": result.instruction_text,
        "query_memory_context": result.query_memory_text,
    }
    _log_node_payload(
        "Retrieved context for the question",
        {
            "schema_text": result.schema_text,
            "instruction_text": result.instruction_text,
            "query_memory_text": result.query_memory_text,
            "schema_hits": len(result.schema_hits),
            "instruction_hits": len(result.instruction_hits),
            "query_memory_hits": len(result.query_memory_hits),
        },
        logger,
    )
    set_cached_metadata(
        operation="retrieve_context",
        operation_args=operation_args,
        value=payload,
    )

    return payload


def skip_pipeline(state: SqlAgentState):
    system_message = {
        "role": "system",
        "content": SHOULD_SKIP.format(
            available_tables=", ".join(state["available_tables"]),
            user_question=state["user_question"],
            schema_context=state.get("schema_context", "Not available"),
        ),
    }
    structured_model = get_model().with_structured_output(SkipDecision)
    result = structured_model.invoke([system_message])

    _log_node_payload("Skip Decision", result, logger)
    return {
        "skip_decision": result,
    }


def should_skip(state: SqlAgentState):
    if state["skip_decision"] and state["skip_decision"].skip:
        return "explain_result"

    return "call_get_schema"


def call_get_schema(state: SqlAgentState):
    llm_with_tools = get_model().bind_tools(
        [get_schema_tool_with_cache], tool_choice="any"
    )
    current_retry_count = state["retry_count"]
    if (
        state["analysis_result"] is not None
        and state["analysis_result"].status == "irrelevant"
    ):
        system_message = {
            "role": "system",
            "content": HANDLE_IRRELEVANT_RESULT.format(
                user_question=state["user_question"],
                available_tables=", ".join(state["available_tables"]),
                schema_context=state.get("schema_context", "Not available"),
                instruction_context=state.get("instruction_context", "Not available"),
                candidate_tables=", ".join(state.get("candidate_tables", [])),
                query=state["last_query"],
                database_output=state["db_output"],
                explanation=state["analysis_result"].explanation,
            ),
        }
        current_retry_count += 1
    else:
        system_message = {
            "role": "system",
            "content": GET_SCHEMA_PROMPT.format(
                available_tables=", ".join(state["available_tables"]),
                user_question=state["user_question"],
                schema_context=state.get("schema_context", "Not available"),
                instruction_context=state.get("instruction_context", "Not available"),
            ),
        }

    response = llm_with_tools.invoke([system_message])
    _log_node_response("Schema Tool Response", response, logger)
    table_list = _canonicalize_table_names(
        response.tool_calls[0]["args"]["table_names"],
        state.get("available_tables", []),
    )
    _log_node_payload("Candidate Tables", table_list, logger)
    return {
        "candidate_tables": table_list,
        "retry_count": current_retry_count,
    }


def get_schema_for_candidate_tables(
    state: SqlAgentState,
    config: RunnableConfig | None = None,
):
    candidate_tables = state.get("candidate_tables", [])
    if not candidate_tables:
        logger.warning("No candidate tables were selected for schema retrieval.")
        return {"schema_for_candidate_tables": ""}

    table_names = normalize_table_names_csv(candidate_tables)
    schema_output = get_schema_tool_with_cache.invoke(
        {"table_names": table_names},
        config=config,
    )
    schema_text = str(schema_output) if schema_output is not None else ""

    _log_node_payload(
        "Fetched schema for %d candidate table(s).", len(candidate_tables), logger
    )

    if not schema_text:
        return {"schema_for_candidate_tables": ""}

    return {"schema_for_candidate_tables": schema_text}


def generate_query(state: SqlAgentState):
    system_message = {
        "role": "system",
        "content": GENERATE_QUERY.format(
            dialect=db.dialect,
            top_k=5,
            schema_for_candidate_tables=state.get(
                "schema_for_candidate_tables", "Not available"
            ),
            instruction_context=state.get("instruction_context", "Not available"),
            query_memory_context=state.get("query_memory_context", "Not available"),
        ),
    }
    llm_with_tools = get_model().bind_tools(
        [run_query_tool_with_interrupt], tool_choice="any"
    )

    prompt_messages = [system_message]

    if state["analysis_result"] is not None and state["analysis_result"].status in [
        "error",
        "empty_result",
    ]:
        prompt_messages.append(
            {
                "role": "user",
                "content": REGEN_PROMPTS[state["analysis_result"].status].format(
                    query=state["last_query"],
                    explanation=state["analysis_result"].explanation,
                    previous_queries=", ".join(state["previous_queries"]),
                ),
            }
        )
    else:
        prompt_messages.append({"role": "user", "content": state["user_question"]})

    response = llm_with_tools.invoke(prompt_messages)
    _log_node_response("Generate Query Response", response, logger)

    if not response.tool_calls:
        raise ValueError("Model failed to generate a tool call.")

    try:
        generated_query = response.tool_calls[0]["args"]["query"]
    except Exception:
        raise ValueError("Failed TO PARSE QUERY from RESPONSE")

    current_retry_count = state["retry_count"] + 1
    _log_node_payload("Generated Query", generated_query, logger)

    return {
        "last_query": generated_query,
        "retry_count": current_retry_count,
        "previous_queries": [generated_query],
    }


def should_execute(_state: SqlAgentState):
    if not AppConfig().EXECUTE_SQL_QUERIES:
        return "explain_result"
    return "run_query"


def run_query(state: SqlAgentState, config: RunnableConfig | None = None):
    last_gen_query = state.get("last_query")
    if not last_gen_query:
        logger.warning("No query found to be executed.")
        return {"db_output": ""}
    db_output = run_query_tool_with_interrupt.invoke(
        {"query": last_gen_query},
        config=config,
    )
    db_txt = str(db_output) if db_output is not None else ""

    _log_node_payload("Database Output", db_txt, logger)
    return {"db_output": db_txt}


def analyze_result(state: SqlAgentState):
    db_output = state.get("db_output", "Empty, 0 rows returned")

    system_message = {
        "role": "system",
        "content": ANALYZE_RESULT.format(
            user_input=state["user_question"],
            query_executed=state["last_query"],
            database_output=db_output,
            retry_count=state["retry_count"],
            instruction_context=state.get("instruction_context", "Not available"),
        ),
    }
    structured_llm = get_model().with_structured_output(AnalysisResult)

    response = structured_llm.invoke([system_message])

    _log_node_payload("Analysis Result", response.model_dump(), logger)

    return {
        "db_output": db_output,
        "analysis_result": response,
    }


def should_retry(state: SqlAgentState):
    analysis_result = state.get("analysis_result")

    if state["retry_count"] < AppConfig().MAX_SQL_RETRIES:
        if analysis_result.status == "irrelevant":
            return "call_get_schema"
        if analysis_result.status in ["error", "empty_result"]:
            return "generate_query"
        # explicit exit to prevent repeated queries
        if (
            len(state["previous_queries"]) > 1
            and state["last_query"] in state["previous_queries"][:-1]
        ):
            return "explain_result"

    return "explain_result"


def explain_result(state: SqlAgentState):
    if not AppConfig().EXECUTE_SQL_QUERIES:
        explanation = f"SQL execution is disabled. Skipping query . Here is last generated query: {state['last_query']}"
        _log_node_payload("No Execution", explanation, logger)
        return {
            "final_answer": explanation,
            "last_user_question": state["user_question"],
        }

    if state["skip_decision"] and state["skip_decision"].skip:
        explanation = f"The agent decided to skip executing the query because: {state['skip_decision'].reason}"
        _log_node_payload("Skip Explanation", explanation, logger)
        return {
            "final_answer": explanation,
            "last_user_question": state["user_question"],
        }

    # Maybe to save on tokens, we drop the LLM call and rely on analysis_node to form a phrase and pass it for the conversational agent
    if not AppConfig().ENABLE_ORCHESTRATOR:
        system_message = {
            "role": "system",
            "content": EXPLAIN_RESULT.format(
                user_question=state["user_question"],
                query=state["last_query"],
                status=state["analysis_result"].status,
                database_output=state["db_output"],
                explanation=state["analysis_result"].explanation,
            ),
        }
        response = get_model().invoke([system_message])
        final_answer = _ai_message_to_text(response)
        _log_node_payload("Explanation", _ai_message_to_text(response), logger)
        return {
            "final_answer": final_answer,
        }

    else:
        _log_node_payload(
            "Passed formating to orchestrator", "ORCHESTRATOR_FORMAT_REQUIRED", logger
        )
        return {
            "final_answer": "ORCHESTRATOR_FORMAT_REQUIRED",
            "last_user_question": state["user_question"],
        }
