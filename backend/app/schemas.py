import enum
from datetime import datetime
from typing import Any, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages
from pydantic import BaseModel, ConfigDict
from typing_extensions import Annotated, TypedDict


# --- LangGraph State ---


class GraphState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    category: str


# --- Enums ---


class RouteCategory(str, enum.Enum):
    MATH = "math"
    CODE = "code"
    GENERAL = "general"


# --- API Models ---


class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None
    chat_id: Optional[int] = None
    image: Optional[str] = None
    image_media_type: Optional[str] = None
    messages: Optional[list[dict[str, Any]]] = None


class ToolCallInfo(BaseModel):
    name: str
    args: dict[str, Any]
    result: str


class RunMetadata(BaseModel):
    node: str
    thread_id: str
    token_usage: Optional[dict[str, int]] = None
    tool_calls: list[ToolCallInfo] = []


class ChatResponse(BaseModel):
    reply: str
    thread_id: str
    run: RunMetadata


class ToolInfo(BaseModel):
    name: str
    description: str


class HealthResponse(BaseModel):
    status: str
    model: str
    graph_compiled: bool


# --- Database Models ---


class User(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    created_at: datetime


class Subject(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    created_at: datetime


class Chat(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject_id: int
    user_id: int
    mode: str
    title: str
    created_at: datetime
    updated_at: datetime


class Message(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chat_id: int
    role: str
    content: str
    image_base64: Optional[str] = None
    image_media_type: Optional[str] = None
    metadata_json: Optional[str] = None
    created_at: datetime


# --- Auth Models ---


class AuthRequestCodeRequest(BaseModel):
    email: str


class AuthRequestCodeResponse(BaseModel):
    message: str


class AuthVerifyRequest(BaseModel):
    email: str
    code: str


class AuthVerifyResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: User
