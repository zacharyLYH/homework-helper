import enum
from datetime import datetime
from typing import Any, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages
from pydantic import BaseModel, ConfigDict
from typing_extensions import Annotated, TypedDict

from shared.schemas import Subject, User  # re-exported for backward compatibility

# --- LangGraph State ---


class GraphState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    pending_tool_calls: int
    pending_tool_calls_data: list[dict]
    called_tools: list[str]
    chat_id: int | None
    user_id: int | None
    subject_id: int | None
    memory_context: str
    memory_loaded: bool
    memory_enabled: bool
    rejected_reason: str
    alignment_score: float


# --- Enums ---


class RouteCategory(str, enum.Enum):
    MATH = "math"
    CODE = "code"
    GENERAL = "general"


# --- Whiteboard models ---


class NodeSpec(BaseModel):
    id: str
    label: str
    kind: str = "box"  # box | ellipse | diamond


class EdgeSpec(BaseModel):
    from_id: str
    to_id: str
    label: Optional[str] = None
    directed: bool = True


class ElementSpec(BaseModel):
    type: str  # line | arrow | rect | ellipse | path | text
    id: str
    points: Optional[list[list[float]]] = None
    from_pos: Optional[list[float]] = None
    to_pos: Optional[list[float]] = None
    x: Optional[float] = None
    y: Optional[float] = None
    w: Optional[float] = None
    h: Optional[float] = None
    cx: Optional[float] = None
    cy: Optional[float] = None
    rx: Optional[float] = None
    ry: Optional[float] = None
    d: Optional[str] = None
    text: Optional[str] = None
    label: Optional[str] = None
    fontSize: Optional[float] = None
    stroke: Optional[str] = None
    strokeWidth: Optional[float] = None
    fill: Optional[str] = None
    kind: Optional[str] = None
    directed: Optional[bool] = None


# --- API Models ---


class ChatRequest(BaseModel):
    message: str
    chat_id: Optional[int] = None
    image: Optional[str] = None
    image_media_type: Optional[str] = None
    messages: Optional[list[dict[str, Any]]] = None
    quote: Optional[str] = None
    is_diagram: Optional[bool] = None


class ToolInfo(BaseModel):
    name: str
    description: str


class HealthResponse(BaseModel):
    status: str
    model: str
    graph_compiled: bool
    memory_enabled: bool


class RootResponse(BaseModel):
    service: str
    docs: str


class MessageResponse(BaseModel):
    message: str


# --- Database Models ---


class Chat(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject_id: int
    user_id: int
    title: str
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
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
    drawing_json: Optional[str] = None
    quote: Optional[str] = None
    token_count: int = 0
    created_at: datetime


# --- Auth Models ---


class ChatSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    total_tokens: int


class SubjectWithChats(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    created_at: datetime
    chats: list[ChatSummary]


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


class AuthRefreshResponse(BaseModel):
    access_token: str


class AuthMeResponse(BaseModel):
    id: int
    email: str


# --- Settings / LLM config UI models ---


class SettingsProvider(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    key_url: str


class SettingsModelOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    label: str
    tier: str
    recommended: str
    supports_images: bool
    price_in: str
    price_out: str
    price_note: str


class SettingsCatalogResponse(BaseModel):
    providers: list[SettingsProvider]
    models: list[SettingsModelOption]


class RoutingRuleUI(BaseModel):
    when: str
    use: list[str]


class OperationConfigUI(BaseModel):
    order: list[str] = []
    rules: list[RoutingRuleUI] = []


class TripletUI(BaseModel):
    alias: str
    provider: str
    model: str
    api_key: str = ""
    has_key: bool = False


class LLMConfigUI(BaseModel):
    """The config as the UI exchanges it: masked api_key + has_key flag."""

    version: int = 1
    name: str = "My Config"
    triplets: list[TripletUI] = []
    chat: OperationConfigUI = OperationConfigUI()
    memory: OperationConfigUI = OperationConfigUI()


class ConfigExportResponse(BaseModel):
    yaml: str


class ConfigImportRequest(BaseModel):
    yaml: str


class PingResult(BaseModel):
    alias: str = ""
    provider: str = ""
    model: str = ""
    ok: bool = False
    error: str | None = None
    latency_ms: int | None = None
    kind: str | None = None


class ConfigTestResponse(BaseModel):
    results: list[PingResult]


# --- Debug / ops models ---


class SqlQueryResponse(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int


class StructuredLogEntry(BaseModel):
    id: int
    type: str
    created_at: str
    message_id: int | None
    log: str


class MessageTraceEntry(Message):
    chat_title: str | None = None
    subject_name: str | None = None
    user_email: str | None = None
