"""Small domain model for style, stable themes, and current frames."""

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Union

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    create_model,
    model_validator,
)

from t2i_prompt_pipeline.errors import ConfigurationError


def _single_line(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError("文本不能包含换行")
    return value.strip()


Text = Annotated[
    str,
    StringConstraints(min_length=1, strip_whitespace=True),
    AfterValidator(_single_line),
]
ThemeId = Annotated[str, StringConstraints(pattern=r"^T\d{2,4}$")]
CharacterId = Annotated[str, StringConstraints(pattern=r"^T\d{2,4}-C\d{2}$")]
FrameId = Annotated[
    str,
    StringConstraints(pattern=r"^T\d{2,4}-F\d{2,3}$"),
]
SemanticName = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$",
    ),
]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Gender(StrEnum):
    FEMALE = "女性"
    MALE = "男性"


class FrameMode(StrEnum):
    SEQUENTIAL = "sequential"
    VARIATIONS = "variations"


class ContentLevel(StrEnum):
    AESTHETIC = "aesthetic"
    EROTIC = "erotic"
    HARDCORE = "hardcore"


class OutputLanguage(StrEnum):
    CHINESE = "chinese"
    ENGLISH = "english"


class GenerationStage(StrEnum):
    FOUNDATION = "foundation"
    THEMES = "themes"
    FRAMES = "frames"


class RunStatus(StrEnum):
    RUNNING = "running"
    FAILED = "failed"
    COMPLETED = "completed"


class AttemptOutcome(StrEnum):
    ACCEPTED = "accepted"
    PARTIAL = "partial"
    REJECTED = "rejected"
    PROVIDER_ERROR = "provider_error"


class ProviderAuthMode(StrEnum):
    BEARER = "bearer"
    API_KEY = "api_key"


class StructuredOutputMode(StrEnum):
    JSON_SCHEMA = "json_schema"
    JSON_OBJECT = "json_object"
    PROMPT_ONLY = "prompt_only"


class ThinkingMode(StrEnum):
    ENABLED = "enabled"
    DISABLED = "disabled"


class ReasoningEffort(StrEnum):
    NONE = "none"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


class GenerationSpec(Model):
    brief: Text
    theme_count: int = Field(default=1, ge=1, le=100)
    frames_per_theme: int = Field(default=1, ge=1, le=100)
    female_count: int | None = Field(default=None, ge=0, le=8)
    male_count: int | None = Field(default=None, ge=0, le=8)
    content_level: ContentLevel = ContentLevel.AESTHETIC
    frame_mode: FrameMode = FrameMode.SEQUENTIAL
    output_language: OutputLanguage = OutputLanguage.CHINESE

    @model_validator(mode="after")
    def cast_constraints_fit(self) -> GenerationSpec:
        counts = tuple(
            count
            for count in (self.female_count, self.male_count)
            if count is not None
        )
        if self.female_count == 0 and self.male_count == 0:
            raise ValueError("人物约束不能同时为零")
        if sum(counts) > 8:
            raise ValueError("每个主题最多包含八名角色")
        return self


class StyleConstraints(Model):
    required_phrases: list[Text] = Field(default_factory=list, max_length=16)


class CastMember(Model):
    role: Text | None = None
    gender: Gender


class CastPlan(Model):
    members: list[CastMember] = Field(min_length=1, max_length=8)

    @property
    def member_count(self) -> int:
        return len(self.members)

    def gender_count(self, gender: Gender) -> int:
        return sum(member.gender == gender for member in self.members)


class Character(Model):
    character_id: CharacterId
    label: Text = Field(
        description=(
            "Final display name. Use a real name when available; otherwise "
            "follow the output-language-specific naming rule in the request."
        )
    )
    gender: Gender
    age: int = Field(ge=21, le=99)
    appearance: Text
    outfit: Text


class Theme(Model):
    theme_id: ThemeId
    title: Text
    scene: Text = Field(
        description=(
            "Complete stable spatial envelope for this Theme. Include every "
            "brief-required route location and the fixed connections between "
            "them; do not describe transient character actions."
        )
    )
    style: Text = Field(
        description=(
            "Complete photography, cinematography, or videography treatment "
            "for this Theme. Illustration and rendered-art media are invalid."
        )
    )
    characters: list[Character] = Field(min_length=1, max_length=8)


class Foundation(Model):
    semantic_name: SemanticName
    style_constraints: StyleConstraints
    cast_plan: CastPlan


class ThemeBatch(Model):
    themes: list[Theme] = Field(min_length=1, max_length=100)


class Camera(Model):
    shot: Text
    view: Text
    composition: Text


class CharacterMoment(Model):
    character_id: CharacterId
    expression: Text | None = None
    action: Text


class Frame(Model):
    frame_id: FrameId
    camera: Camera
    characters: list[CharacterMoment] = Field(min_length=1, max_length=8)
    details: Text


class FrameBatch(Model):
    theme_id: ThemeId
    frames: list[Frame] = Field(min_length=1, max_length=100)


@lru_cache(maxsize=128)
def theme_batch_response_model(
    theme_ids: tuple[str, ...],
    character_count: int,
) -> type[ThemeBatch]:
    response_themes: list[type[Theme]] = []
    for theme_id in theme_ids:
        character_ids = tuple(
            format_character_id(theme_id, index)
            for index in range(1, character_count + 1)
        )
        response_character = create_model(
            f"CharacterFor{theme_id}",
            __base__=Character,
            character_id=(Literal.__getitem__(character_ids), ...),
        )
        exact_characters = Annotated[
            list[response_character],
            Field(min_length=character_count, max_length=character_count),
        ]
        response_themes.append(
            create_model(
                f"ThemeFor{theme_id}",
                __base__=Theme,
                theme_id=(Literal.__getitem__(theme_id), ...),
                characters=(exact_characters, ...),
            )
        )
    theme_item = (
        response_themes[0]
        if len(response_themes) == 1
        else Union.__getitem__(tuple(response_themes))
    )
    exact_themes = Annotated[
        list[theme_item],
        Field(min_length=1, max_length=len(theme_ids)),
    ]
    return create_model(
        f"ThemeBatchFor{theme_ids[0]}Through{theme_ids[-1]}",
        __base__=ThemeBatch,
        themes=(exact_themes, ...),
    )


@lru_cache(maxsize=128)
def frame_batch_response_model(
    theme_id: str,
    frame_ids: tuple[str, ...],
    character_ids: tuple[str, ...],
) -> type[FrameBatch]:
    exact_character_id = Literal.__getitem__(character_ids)
    response_moment = create_model(
        f"CharacterMomentFor{theme_id}",
        __base__=CharacterMoment,
        character_id=(exact_character_id, ...),
    )
    visible_moments = Annotated[
        list[response_moment],
        Field(
            min_length=1,
            max_length=len(character_ids),
        ),
    ]
    response_frame = create_model(
        f"FrameFor{theme_id}",
        __base__=Frame,
        frame_id=(Literal.__getitem__(frame_ids), ...),
        characters=(visible_moments, ...),
    )
    exact_frames = Annotated[
        list[response_frame],
        Field(min_length=1, max_length=len(frame_ids)),
    ]
    return create_model(
        f"FrameBatchFor{theme_id}",
        __base__=FrameBatch,
        theme_id=(Literal.__getitem__(theme_id), ...),
        frames=(exact_frames, ...),
    )


class ThemeBook(Model):
    theme: Theme
    frames: list[Frame]


class PromptBook(Model):
    semantic_name: SemanticName
    cast_plan: CastPlan
    themes: list[ThemeBook]

    @model_validator(mode="after")
    def themes_match_cast_plan(self) -> PromptBook:
        for theme_book in self.themes:
            theme = theme_book.theme
            if len(theme.characters) != self.cast_plan.member_count:
                raise ValueError(
                    f"{theme.theme_id} 人物数量不符合 Cast Plan"
                )
            for index, (character, cast_member) in enumerate(
                zip(
                    theme.characters,
                    self.cast_plan.members,
                    strict=True,
                ),
                start=1,
            ):
                if (
                    character.character_id
                    != format_character_id(theme.theme_id, index)
                    or character.gender != cast_member.gender
                ):
                    raise ValueError(
                        f"{character.character_id} 不符合 Cast Plan 顺序"
                    )
        return self


class RenderedPrompt(Model):
    theme_id: ThemeId
    frame_id: FrameId
    text: Text


class GenerationResult(Model):
    spec: GenerationSpec
    book: PromptBook
    prompts: list[RenderedPrompt]


class ArchivedRun(Model):
    run_id: Text
    request_file: Text
    book_file: Text
    prompt_file: Text
    result: GenerationResult


class ResolvedRuleSet(Model):
    foundation: tuple[Text, ...] = Field(min_length=1)
    themes: tuple[Text, ...] = Field(min_length=1)
    frames: tuple[Text, ...] = Field(min_length=1)

    def for_stage(self, stage: GenerationStage) -> tuple[str, ...]:
        if stage == GenerationStage.FOUNDATION:
            return self.foundation
        if stage == GenerationStage.THEMES:
            return self.themes
        return self.frames

    def text_for(self, stage: GenerationStage) -> str:
        return "\n".join(self.for_stage(stage))

    def fingerprint(self) -> str:
        return _json_fingerprint(self.model_dump(mode="json"))


class RunSettings(Model):
    theme_batch_size: int = Field(default=5, ge=1, le=20)
    generation_retries: int = Field(default=2, ge=0, le=5)
    max_concurrency: int = Field(default=8, ge=1, le=16)
    provider_signature: Text
    output_token_limit: int = Field(ge=256, le=65536)

    def ensure_resumable_with(self, current: RunSettings) -> None:
        if self.provider_signature != current.provider_signature:
            raise ConfigurationError(
                "当前 provider 生成配置与 run manifest 不一致"
            )
        if current.output_token_limit < self.output_token_limit:
            raise ConfigurationError(
                "当前 OPENAI_OUTPUT_TOKEN_LIMIT 小于 run 所需硬上限 "
                f"{self.output_token_limit}"
            )


class RunManifest(Model):
    run_id: Text
    status: RunStatus
    created_at: Text
    updated_at: Text
    settings: RunSettings
    prompts_directory: Text
    rules_fingerprint: Text
    prompt_file: Text | None = None
    error: str | None = None


class RunSummary(Model):
    run_id: Text
    status: RunStatus
    created_at: Text
    updated_at: Text
    brief: Text
    theme_count: int = Field(ge=1)
    frames_per_theme: int = Field(ge=1)
    prompt_file: Text | None = None
    error: str | None = None


class ProviderSettings(Model):
    base_url: Text = "https://api.openai.com/v1"
    api_key_env: Text = "OPENAI_API_KEY"
    auth_mode: ProviderAuthMode = ProviderAuthMode.BEARER
    model: Text
    structured_output_mode: StructuredOutputMode = StructuredOutputMode.JSON_SCHEMA
    thinking_mode: ThinkingMode | None = None
    reasoning_effort: ReasoningEffort | None = None
    temperature: float = Field(default=0.6, ge=0, le=2)
    output_token_limit: int = Field(default=16384, ge=256, le=65536)
    timeout_seconds: float = Field(default=180, gt=0, le=600)
    transport_retries: int = Field(default=2, ge=0, le=8)

    @model_validator(mode="after")
    def reasoning_controls_do_not_conflict(self) -> ProviderSettings:
        if self.thinking_mode is not None and self.reasoning_effort is not None:
            raise ValueError(
                "thinking_mode 与 reasoning_effort 不能同时配置"
            )
        return self

    def signature(self) -> str:
        return _json_fingerprint(
            {
                "base_url": self.base_url.rstrip("/"),
                "model": self.model,
                "structured_output_mode": self.structured_output_mode.value,
                "thinking_mode": (
                    self.thinking_mode.value
                    if self.thinking_mode is not None
                    else None
                ),
                "reasoning_effort": (
                    self.reasoning_effort.value
                    if self.reasoning_effort is not None
                    else None
                ),
                "temperature": (
                    self.temperature
                    if self.thinking_mode is None
                    and self.reasoning_effort is None
                    else None
                ),
            }
        )


class AppConfig(Model):
    spec: GenerationSpec
    provider: ProviderSettings
    runs_directory: Path
    prompts_directory: Path
    run_settings: RunSettings
    rules: ResolvedRuleSet


class TokenUsage(Model):
    prompt_tokens: int | None = Field(default=None, ge=0)
    cached_prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class GenerationAttempt(Model):
    occurred_at: Text
    stage: GenerationStage
    requested_ids: list[Text] = Field(default_factory=list, max_length=100)
    attempt: int = Field(ge=1)
    max_output_tokens: int = Field(ge=256, le=65536)
    outcome: AttemptOutcome
    accepted_ids: list[Text] = Field(default_factory=list, max_length=100)
    issues: list[Text] = Field(default_factory=list)
    duration_ms: int = Field(ge=0)
    usage: TokenUsage = Field(default_factory=TokenUsage)


def _json_fingerprint(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def format_theme_id(index: int, total: int) -> str:
    width = max(2, len(str(total)))
    return f"T{index:0{width}d}"


def format_character_id(theme_id: str, index: int) -> str:
    return f"{theme_id}-C{index:02d}"


def format_frame_id(theme_id: str, index: int, total: int) -> str:
    width = max(2, len(str(total)))
    return f"{theme_id}-F{index:0{width}d}"


def safe_run_id(value: str) -> bool:
    return re.fullmatch(r"\d{8}T\d{6}Z-[a-f0-9]{8}", value) is not None
