from operator import add
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages
from pydantic import BaseModel


class AnalysisResult(BaseModel):
    status: Literal["success", "empty_result", "irrelevant", "error"]
    explanation: str


class SkipDecision(BaseModel):
    reason: str
    skip: bool = False


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    user_question: str
    last_query: str | None
    previous_queries: Annotated[list[str], add]
    analysis_result: AnalysisResult | None
    skip_decision: SkipDecision | None
    db_output: str | None
    retry_count: int
