from __future__ import annotations

from types import SimpleNamespace

import pytest
from copilot.session_events import (
    AssistantMessageData,
    AssistantUsageData,
    SessionErrorData,
    SessionIdleData,
)
from copilot.tools import ToolInvocation
from pydantic import BaseModel, ConfigDict

import t2i_model_provider.copilot as copilot_provider
from t2i_model_provider import (
    CopilotGenerationError,
    CopilotStructuredModel,
    ModelBackend,
)
from t2i_story_pipeline.provider import ChatMessage, StoryProviderSettings


class ExampleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    count: int


class FakeSession:
    def __init__(
        self,
        options,
        payloads,
        *,
        finish_reason: str = "stop",
        session_error: str | None = None,
        emit_idle: bool = True,
    ) -> None:
        self.options = options
        self.payloads = payloads
        self.finish_reason = finish_reason
        self.session_error = session_error
        self.emit_idle = emit_idle
        self.disconnected = False

    async def send(self, _prompt: str) -> None:
        tool = self.options["tools"][0]
        for payload in self.payloads:
            result = await tool.handler(
                ToolInvocation(
                    session_id="test",
                    tool_call_id="call",
                    tool_name=tool.name,
                    arguments=payload,
                )
            )
            if result.result_type == "success":
                break
        self.options["on_event"](
            SimpleNamespace(
                data=AssistantUsageData(
                    model="gpt-5",
                    input_tokens=11,
                    output_tokens=7,
                    finish_reason=self.finish_reason,
                )
            )
        )
        self.options["on_event"](
            SimpleNamespace(
                data=AssistantMessageData(
                    content="ordinary prose",
                    message_id="message",
                )
            )
        )
        if self.session_error is not None:
            self.options["on_event"](
                SimpleNamespace(
                    data=SessionErrorData(
                        error_type="provider",
                        message=self.session_error,
                    )
                )
            )
        elif self.emit_idle:
            self.options["on_event"](
                SimpleNamespace(data=SessionIdleData())
            )

    async def disconnect(self) -> None:
        self.disconnected = True


class FakeClient:
    def __init__(self, payloads, **session_options) -> None:
        self.payloads = payloads
        self.session_options = session_options
        self.options = None
        self.session = None

    async def create_session(self, **options):
        self.options = options
        self.session = FakeSession(
            options,
            self.payloads,
            **self.session_options,
        )
        return self.session


class FailingStartClient:
    async def start(self) -> None:
        raise RuntimeError("not signed in")

    async def stop(self) -> None:
        pytest.fail("a client that failed to start must not be stopped")


@pytest.mark.asyncio
async def test_copilot_uses_only_terminal_typed_submission_tool() -> None:
    client = FakeClient(
        [
            {"title": "invalid"},
            {"title": "accepted", "count": 3},
        ]
    )
    settings = StoryProviderSettings(
        backend=ModelBackend.COPILOT,
        model="gpt-5",
    )
    model = CopilotStructuredModel(settings, client=client)

    response = await model.generate(
        messages=[
            ChatMessage(role="system", content="Create one result."),
            ChatMessage(role="user", content="Use count three."),
        ],
        response_model=ExampleResponse,
        max_output_tokens=1000,
    )

    assert response.value == ExampleResponse(title="accepted", count=3)
    assert response.prompt_tokens == 11
    assert response.completion_tokens == 7
    assert response.total_tokens == 18
    assert client.options["model"] == "gpt-5"
    assert client.options["reasoning_effort"] is None
    assert client.options["system_message"]["mode"] == "replace"
    assert list(client.options["available_tools"]) == [
        "custom:submit_exampleresponse"
    ]
    tool = client.options["tools"][0]
    assert tool.is_terminal is True
    assert tool.skip_permission is True
    assert client.session.disconnected is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("client", "message", "truncated"),
    [
        (
            FakeClient(
                [{"title": "accepted", "count": 3}],
                session_error="quota exhausted",
            ),
            "Copilot session failed: quota exhausted",
            False,
        ),
        (
            FakeClient(
                [{"title": "accepted", "count": 3}],
                finish_reason="length",
            ),
            "Copilot output reached its token limit",
            True,
        ),
        (
            FakeClient([{"title": "invalid"}]),
            "Copilot did not submit a valid structured response",
            False,
        ),
    ],
)
async def test_copilot_surfaces_incomplete_session_outcomes(
    client,
    message,
    truncated,
) -> None:
    settings = StoryProviderSettings(
        backend=ModelBackend.COPILOT,
        model="gpt-5",
    )
    model = CopilotStructuredModel(settings, client=client)

    with pytest.raises(CopilotGenerationError, match=message) as captured:
        await model.generate(
            messages=[ChatMessage(role="user", content="Create one result.")],
            response_model=ExampleResponse,
            max_output_tokens=1000,
        )

    assert captured.value.truncated is truncated
    assert captured.value.raw_content == "ordinary prose"
    assert captured.value.total_tokens == 18
    assert client.session.disconnected is True
    if message.startswith("Copilot did not submit"):
        assert captured.value.validation_issues == ("count: Field required",)


@pytest.mark.asyncio
async def test_copilot_times_out_and_disconnects() -> None:
    client = FakeClient([], emit_idle=False)
    settings = StoryProviderSettings(
        backend=ModelBackend.COPILOT,
        model="gpt-5",
        timeout_seconds=0.001,
    )
    model = CopilotStructuredModel(settings, client=client)

    with pytest.raises(CopilotGenerationError, match="timed out"):
        await model.generate(
            messages=[ChatMessage(role="user", content="Create one result.")],
            response_model=ExampleResponse,
            max_output_tokens=1000,
        )

    assert client.session.disconnected is True


@pytest.mark.asyncio
async def test_copilot_maps_runtime_start_failure_and_cleans_storage(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        copilot_provider,
        "CopilotClient",
        lambda **_options: FailingStartClient(),
    )
    settings = StoryProviderSettings(
        backend=ModelBackend.COPILOT,
        model="gpt-5",
    )
    model = CopilotStructuredModel(settings)

    with pytest.raises(CopilotGenerationError, match="failed to start"):
        async with model:
            pytest.fail("the model must not enter after a start failure")

    assert model._runtime_directory is None
