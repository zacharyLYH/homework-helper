from collections.abc import Sequence
from typing import Any, AsyncIterator, Optional
from unittest.mock import patch

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field


class FakeChatModel(BaseChatModel):
    content: str = "Hello!"
    _stream_done: bool = False

    def _generate(
        self,
        messages: list,
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        message = AIMessage(
            content=self.content,
            response_metadata={"model_name": "gpt-4"},
            usage_metadata={"input_tokens": 15, "output_tokens": 5, "total_tokens": 20},
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _astream(
        self,
        messages: list,
        stop: Optional[list[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        self._stream_done = False
        words = self.content.split(" ")
        for i, word in enumerate(words):
            suffix = " " if i < len(words) - 1 else ""
            chunk = AIMessageChunk(content=word + suffix)
            if i == len(words) - 1:
                chunk.response_metadata = {"model_name": "gpt-4"}
                chunk.usage_metadata = {"input_tokens": 15, "output_tokens": 5, "total_tokens": 20}
            yield ChatGenerationChunk(message=chunk)
        self._stream_done = True

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "FakeChatModel":
        return self

    @property
    def _llm_type(self) -> str:
        return "fake-chat-model"


class MockLLMResponse:
    def __init__(self, content: str = "Hello!", model: str = "test-model"):
        self.content = content
        self.model = model


def mock_stream_llm(responses: list[MockLLMResponse] | None = None):
    if responses is None:
        responses = [MockLLMResponse()]
    call_count = 0

    async def _mock_stream(messages, bind_tools=None, config=None):
        nonlocal call_count
        resp = responses[call_count % len(responses)]
        call_count += 1
        yield AIMessageChunk(content=resp.content), resp.model

    return patch("app.graph.stream_llm", side_effect=_mock_stream)


def mock_title_llm(title: str = "Test Chat Title"):
    from unittest.mock import MagicMock, patch

    mock = MagicMock()

    async def _mock_astream(prompt):
        chunk = MagicMock()
        chunk.content = title
        yield chunk

    mock.astream = _mock_astream
    return patch("app.routes.chat.title_llm", mock)


def mock_email_send():
    from unittest.mock import patch

    return patch("app.routes.auth.send_verification_email", return_value=True)


def mock_email_send_failure():
    from unittest.mock import patch

    return patch("app.routes.auth.send_verification_email", return_value=False)
