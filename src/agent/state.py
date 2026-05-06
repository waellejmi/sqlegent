from operator import add
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel


class AnalysisResult(BaseModel):
    status: Literal["success", "empty_result", "irrelevant", "error"]
    explanation: str


class SkipDecision(BaseModel):
    reason: str
    skip: bool = False


class SynthesisResult(BaseModel):
    synthesized_question: str


class SqlAgentState(TypedDict):
    user_question: str
    last_user_question: str | None

    available_tables: list[str]

    schema_context: str | None

    skip_decision: SkipDecision | None

    candidate_tables: list[str]
    schema_for_candidate_tables: str | None

    instruction_context: str | None
    query_memory_context: str | None
    last_query: str | None
    previous_queries: Annotated[list[str], add]

    db_output: str | None
    analysis_result: AnalysisResult | None
    final_answer: str | None

    retry_count: int
