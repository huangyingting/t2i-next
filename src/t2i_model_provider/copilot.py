"""Typed structured generation through the GitHub Copilot SDK."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from tempfile import TemporaryDirectory
from typing import Any, Protocol, TypeVar

from copilot import CopilotClient, ToolSet
from copilot.session_events import (
    AssistantMessageData,
    AssistantUsageData,
    SessionErrorData,
    SessionIdleData,
)
from copilot.tools import Tool, ToolInvocation, ToolResult
from pydantic import BaseModel, ValidationError

ResponseT = TypeVar("ResponseT", bound=BaseModel)


class CopilotSettings(Protocol):
    model: str
    reasoning_effort: Any
    output_token_limit: int
    timeout_seconds: float


class Message(Protocol):
    role: str
    content: str


class CopilotGenerationError(Exception):
    """The Copilot runtime could not produce a typed response."""

    def __init__(
        self,
        message: str,
        *,
        raw_content: str = "",
        validation_issues: tuple[str, ...] = (),
        truncated: bool = False,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        super().__init__(message)
        self.raw_content = raw_content
        self.validation_issues = validation_issues
        self.truncated = truncated
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = prompt_tokens + completion_tokens


@dataclass(frozen=True, slots=True)
class CopilotResponse:
    value: BaseModel
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class CopilotTextResponse:
    text: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class CopilotStructuredModel:
    """Use a terminal custom tool as the structured-output boundary."""

    def __init__(
        self,
        settings: CopilotSettings,
        *,
        client: CopilotClient | None = None,
    ) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._runtime_directory: TemporaryDirectory[str] | None = None
        if client is not None:
            self._client = client
            return
        self._runtime_directory = TemporaryDirectory(prefix="t2i-copilot-")
        try:
            self._client = CopilotClient(
                mode="empty",
                base_directory=self._runtime_directory.name,
            )
        except Exception:
            self._cleanup_runtime_directory()
            raise

    async def __aenter__(self) -> CopilotStructuredModel:
        if self._owns_client:
            started = False
            try:
                try:
                    await self._client.start()
                except RuntimeError as exc:
                    raise CopilotGenerationError(
                        "Copilot runtime failed to start"
                    ) from exc
                started = True
            finally:
                if not started:
                    self._cleanup_runtime_directory()
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._owns_client:
            try:
                await self._client.stop()
            finally:
                self._cleanup_runtime_directory()

    def _cleanup_runtime_directory(self) -> None:
        if self._runtime_directory is not None:
            self._runtime_directory.cleanup()
            self._runtime_directory = None

    async def generate(
        self,
        *,
        messages: Sequence[Message],
        response_model: type[ResponseT],
        max_output_tokens: int,
        validation_context: dict[str, object] | None = None,
        argument_transform: Callable[[Any], Any] | None = None,
    ) -> CopilotResponse:
        captured: list[ResponseT] = []
        rejected_issues: list[str] = []
        usages: list[AssistantUsageData] = []
        assistant_messages: list[str] = []
        session_error: list[str] = []
        idle = asyncio.Event()
        tool_name = _tool_name(response_model.__name__)

        async def submit(invocation: ToolInvocation) -> ToolResult:
            if captured:
                return ToolResult(
                    text_result_for_llm="A response was already accepted.",
                    result_type="failure",
                    error="duplicate structured response",
                )
            try:
                arguments = (
                    argument_transform(invocation.arguments)
                    if argument_transform is not None
                    else invocation.arguments
                )
                value = response_model.model_validate(
                    arguments,
                    context=validation_context,
                )
            except ValidationError as exc:
                issues = _validation_issues(exc)
                rejected_issues.extend(issues)
                return ToolResult(
                    text_result_for_llm=(
                        "Invalid structured response:\n" + "\n".join(issues)
                    ),
                    result_type="failure",
                    error=str(exc),
                )
            captured.append(value)
            return ToolResult(text_result_for_llm="Response accepted.")

        tool = Tool(
            name=tool_name,
            description=(
                "Submit the complete final response. You must call this tool "
                "exactly once and must not answer with ordinary prose."
            ),
            parameters=response_model.model_json_schema(),
            handler=submit,
            skip_permission=True,
            defer="never",
            is_terminal=True,
        )

        def on_event(event) -> None:
            match event.data:
                case AssistantUsageData() as data:
                    usages.append(data)
                case AssistantMessageData() as data:
                    assistant_messages.append(data.content)
                case SessionErrorData() as data:
                    session_error.append(data.message or "Copilot session failed")
                    idle.set()
                case SessionIdleData():
                    idle.set()

        system_content, prompt = _compile_messages(
            messages,
            response_model=response_model,
            max_output_tokens=min(
                max_output_tokens,
                self._settings.output_token_limit,
            ),
            tool_name=tool_name,
        )
        reasoning_effort = (
            self._settings.reasoning_effort.value
            if self._settings.reasoning_effort is not None
            else None
        )
        try:
            session = await self._client.create_session(
                model=self._settings.model,
                reasoning_effort=reasoning_effort,
                tools=[tool],
                available_tools=ToolSet().add_custom(tool_name),
                system_message={"mode": "replace", "content": system_content},
                infinite_sessions={"enabled": False},
                on_event=on_event,
            )
        except RuntimeError as exc:
            raise CopilotGenerationError(
                "Copilot session could not be created"
            ) from exc
        try:
            try:
                await session.send(prompt)
            except RuntimeError as exc:
                raise CopilotGenerationError(
                    "Copilot request could not be sent"
                ) from exc
            try:
                await asyncio.wait_for(
                    idle.wait(),
                    timeout=self._settings.timeout_seconds,
                )
            except TimeoutError as exc:
                raise CopilotGenerationError(
                    "Copilot structured generation timed out"
                ) from exc
        finally:
            await session.disconnect()

        prompt_tokens = sum(item.input_tokens or 0 for item in usages)
        completion_tokens = sum(item.output_tokens or 0 for item in usages)
        truncated = any(item.finish_reason == "length" for item in usages)
        raw_content = "\n".join(assistant_messages)
        if session_error:
            raise CopilotGenerationError(
                f"Copilot session failed: {session_error[-1]}",
                raw_content=raw_content,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        if truncated:
            raise CopilotGenerationError(
                "Copilot output reached its token limit",
                raw_content=raw_content,
                validation_issues=("finish_reason=length",),
                truncated=True,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        if len(captured) != 1:
            raise CopilotGenerationError(
                "Copilot did not submit a valid structured response",
                raw_content=raw_content,
                validation_issues=tuple(rejected_issues),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        return CopilotResponse(
            value=captured[0],
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )

    async def generate_text(
        self,
        *,
        messages: Sequence[Message],
        max_output_tokens: int,
    ) -> CopilotTextResponse:
        usages: list[AssistantUsageData] = []
        assistant_messages: list[str] = []
        session_error: list[str] = []
        idle = asyncio.Event()

        def on_event(event) -> None:
            match event.data:
                case AssistantUsageData() as data:
                    usages.append(data)
                case AssistantMessageData() as data:
                    assistant_messages.append(data.content)
                case SessionErrorData() as data:
                    session_error.append(data.message or "Copilot session failed")
                    idle.set()
                case SessionIdleData():
                    idle.set()

        system_content, prompt = _compile_text_messages(
            messages,
            max_output_tokens=min(
                max_output_tokens,
                self._settings.output_token_limit,
            ),
        )
        reasoning_effort = (
            self._settings.reasoning_effort.value
            if self._settings.reasoning_effort is not None
            else None
        )
        try:
            session = await self._client.create_session(
                model=self._settings.model,
                reasoning_effort=reasoning_effort,
                tools=[],
                available_tools=ToolSet(),
                system_message={"mode": "replace", "content": system_content},
                infinite_sessions={"enabled": False},
                on_event=on_event,
            )
        except RuntimeError as exc:
            raise CopilotGenerationError(
                "Copilot text session could not be created"
            ) from exc
        try:
            try:
                await session.send(prompt)
            except RuntimeError as exc:
                raise CopilotGenerationError(
                    "Copilot text request could not be sent"
                ) from exc
            try:
                await asyncio.wait_for(
                    idle.wait(),
                    timeout=self._settings.timeout_seconds,
                )
            except TimeoutError as exc:
                raise CopilotGenerationError(
                    "Copilot text generation timed out"
                ) from exc
        finally:
            await session.disconnect()

        prompt_tokens = sum(item.input_tokens or 0 for item in usages)
        completion_tokens = sum(item.output_tokens or 0 for item in usages)
        raw_content = "\n".join(assistant_messages).strip()
        if session_error:
            raise CopilotGenerationError(
                f"Copilot session failed: {session_error[-1]}",
                raw_content=raw_content,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        if any(item.finish_reason == "length" for item in usages):
            raise CopilotGenerationError(
                "Copilot output reached its token limit",
                raw_content=raw_content,
                validation_issues=("finish_reason=length",),
                truncated=True,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        if not raw_content:
            raise CopilotGenerationError(
                "Copilot returned empty text",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
        return CopilotTextResponse(
            text=raw_content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )


def _compile_messages(
    messages: Sequence[Message],
    *,
    response_model: type[BaseModel],
    max_output_tokens: int,
    tool_name: str,
) -> tuple[str, str]:
    system_messages = [
        message.content for message in messages if message.role == "system"
    ]
    transcript = [
        f"{message.role.upper()} MESSAGE:\n{message.content}"
        for message in messages
        if message.role != "system"
    ]
    system_messages.append(
        "\n".join(
            (
                "Return only a structured result through the provided terminal tool.",
                f"Call {tool_name} exactly once.",
                "Do not use any other tool and do not return the result as prose.",
                f"The response type is {response_model.__name__}.",
                f"Keep the result within approximately {max_output_tokens} tokens.",
            )
        )
    )
    return "\n\n".join(system_messages), "\n\n".join(transcript)


def _compile_text_messages(
    messages: Sequence[Message],
    *,
    max_output_tokens: int,
) -> tuple[str, str]:
    system_messages = [
        message.content for message in messages if message.role == "system"
    ]
    transcript = [
        f"{message.role.upper()} MESSAGE:\n{message.content}"
        for message in messages
        if message.role != "system"
    ]
    system_messages.append(
        "\n".join(
            (
                "Return only the requested final prose.",
                "Do not return JSON, Markdown fences, a title, an ID, or commentary.",
                f"Keep the response within approximately {max_output_tokens} tokens.",
            )
        )
    )
    return "\n\n".join(system_messages), "\n\n".join(transcript)


def _tool_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_").lower()
    return f"submit_{normalized[:48] or 'response'}"


def _validation_issues(exc: ValidationError) -> tuple[str, ...]:
    return tuple(
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
        for error in exc.errors()
    )
