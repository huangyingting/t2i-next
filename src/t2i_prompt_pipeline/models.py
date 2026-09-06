"""Small domain model for style, stable themes, and current frames."""

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Union
from uuid import uuid4

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


class CharacterFraming(StrEnum):
    HEAD_AND_TORSO = "head_and_torso"
    FULL_BODY = "full_body"
    HEAD_CROPPED_TORSO = "head_cropped_torso"


class DepthMode(StrEnum):
    SHALLOW = "shallow"
    MODERATE = "moderate"
    DEEP = "deep"


class LensProfile(StrEnum):
    ULTRA_WIDE = "ultra_wide"
    WIDE = "wide"
    NORMAL = "normal"
    TELEPHOTO = "telephoto"
    FISHEYE = "fisheye"


class ShotScale(StrEnum):
    ESTABLISHING = "establishing"
    WIDE = "wide"
    FULL_BODY = "full_body"
    MEDIUM_FULL = "medium_full"
    MEDIUM = "medium"
    CLOSE_UP = "close_up"


class CameraHeight(StrEnum):
    EYE_LEVEL = "eye_level"
    HIGH_ANGLE = "high_angle"
    LOW_ANGLE = "low_angle"
    OVERHEAD = "overhead"


class CameraDirection(StrEnum):
    FRONT = "front"
    THREE_QUARTER = "three_quarter"
    SIDE = "side"
    TOP_DOWN = "top_down"
    REAR_THREE_QUARTER = "rear_three_quarter"


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
    THEME_SIMILARITY = "theme_similarity"
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


class ThemeSimilarityState(StrEnum):
    ANALYZED = "analyzed"
    CLEAN = "clean"
    ERROR = "error"
    REJECTION_PENDING = "rejection_pending"
    REGENERATING = "regenerating"
    EXHAUSTED = "exhausted"


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
    required_phrases: list[Text] = Field(
        default_factory=list,
        max_length=16,
        description=(
            "Brief-grounded reference expressions. Keep adjacent creator "
            "and titled work in one expression and insert only an accurate "
            "work-type relation label when needed for natural grammar."
        ),
    )


class CastMember(Model):
    display_name: Text | None
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
    age: int = Field(ge=21, le=99)
    appearance: Text = Field(
        description=(
            "Stable identity anchors: specific hair, face shape, and at "
            "least two facial features such as brows, eyes, nose, lips, "
            "complexion, cheekbones, or jawline."
        )
    )
    outfit: Text


class Setting(Model):
    time_context: Text = Field(
        description=(
            "Explicit visual period and immediate time. Preserve the brief; "
            "when unspecified, infer only a broad era and plausible season "
            "or time of day without inventing an exact historical date."
        )
    )
    location: Text = Field(
        description=(
            "Concrete geographic and physical place visible in the image, "
            "not only a fictional world, work title, or generic genre."
        )
    )
    fixed_elements: list[Text] = Field(min_length=1, max_length=12)
    available_light_sources: list[Text] = Field(min_length=1, max_length=8)
    background_population: Text
    atmosphere: Text


class StoryPlan(Model):
    immediate_goal: Text = Field(
        description=(
            "Exactly one coherent immediate goal shared by this Theme's "
            "Frames; never give alternatives joined by 'or'. "
            "Use the brief's action when present; otherwise derive a minimal "
            "scene-grounded goal without inventing identity or backstory."
        )
    )
    visible_trigger: Text = Field(
        description=(
            "The visible person, object, or event that initiates the goal. "
            "Every required object must also exist in setting.fixed_elements."
        )
    )
    visible_result: Text = Field(
        description=(
            "Name a concrete object or person and its directly imageable "
            "changed state caused by the action. Posture, mood, atmosphere, "
            "abstract tension, explanatory prose, and future events are not "
            "results."
        )
    )

    @model_validator(mode="after")
    def fields_choose_one_story(self) -> StoryPlan:
        alternatives = re.compile(r"或|二选一|\b(?:or|either)\b", re.IGNORECASE)
        if any(
            alternatives.search(value)
            for value in (
                self.immediate_goal,
                self.visible_trigger,
                self.visible_result,
            )
        ):
            raise ValueError("StoryPlan 每个字段必须选择一个具体故事，不得列备选")
        return self


class Theme(Model):
    theme_id: ThemeId
    setting: Setting
    story_plan: StoryPlan
    characters: list[Character] = Field(min_length=1, max_length=8)


class Foundation(Model):
    semantic_name: SemanticName
    style_constraints: StyleConstraints
    cast_plan: CastPlan


class ThemeBatch(Model):
    themes: list[Theme] = Field(min_length=1, max_length=100)


class Lighting(Model):
    source: Text
    position: Text
    color: Text
    scene_effect: Text


class DepthOfField(Model):
    mode: DepthMode
    focus_target: Text
    background_effect: Text


class Camera(Model):
    lens_profile: LensProfile
    shot_scale: ShotScale
    height: CameraHeight
    direction: CameraDirection
    depth_of_field: DepthOfField
    lighting: Lighting

    @model_validator(mode="after")
    def overhead_requires_top_down_direction(self) -> Camera:
        overhead = self.height == CameraHeight.OVERHEAD
        top_down = self.direction == CameraDirection.TOP_DOWN
        if overhead != top_down:
            raise ValueError("overhead 与 top_down 必须配对使用")
        return self


class CharacterMoment(Model):
    character_id: CharacterId
    framing: CharacterFraming
    placement: Text
    facing: Text
    visible_appearance: Text = Field(
        description=(
            "Stable identity anchors and clothing visible within framing. "
            "When the head is visible, include face shape and at least two "
            "facial features. HEAD_CROPPED_TORSO excludes face and hair."
        )
    )
    lighting_effect: Text
    expression: Text | None = None
    action: Text

    @model_validator(mode="after")
    def expression_matches_framing(self) -> CharacterMoment:
        head_cropped = self.framing == CharacterFraming.HEAD_CROPPED_TORSO
        if head_cropped and self.expression is not None:
            raise ValueError("head_cropped_torso 的 expression 必须为 null")
        if not head_cropped and self.expression is None:
            raise ValueError("头部入画时 expression 不能为空")
        return self


class Frame(Model):
    frame_id: FrameId
    camera: Camera
    characters: list[CharacterMoment] = Field(min_length=1, max_length=8)


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
            min_length=len(character_ids),
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
    style_constraints: StyleConstraints
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
            for index, character in enumerate(theme.characters, start=1):
                if character.character_id != format_character_id(
                    theme.theme_id, index
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
    theme_similarity: ThemeSimilaritySettings | None = None

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
        if self.theme_similarity != current.theme_similarity:
            raise ConfigurationError(
                "当前 Theme similarity 配置与 run manifest 不一致"
            )


class ThemeSimilaritySettings(Model):
    model: Text
    dimensions: int | None = Field(default=None, ge=1, le=65536)
    setting_threshold: float = Field(default=0.86, ge=-1, le=1)


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
    embedding_model: Text | None = None
    embedding_dimensions: int | None = Field(default=None, ge=1, le=65536)

    @model_validator(mode="after")
    def reasoning_controls_do_not_conflict(self) -> ProviderSettings:
        if self.thinking_mode is not None and self.reasoning_effort is not None:
            raise ValueError(
                "thinking_mode 与 reasoning_effort 不能同时配置"
            )
        if self.embedding_dimensions is not None and self.embedding_model is None:
            raise ValueError(
                "embedding_dimensions 需要同时配置 embedding_model"
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


class ThemeSimilarityPair(Model):
    first_theme_id: ThemeId
    second_theme_id: ThemeId
    setting_similarity: float = Field(ge=-1, le=1)
    potential_duplicate: bool


class ThemeSimilarityRejection(Model):
    rejected_theme_id: ThemeId
    kept_theme_id: ThemeId
    setting_similarity: float = Field(ge=-1, le=1)


class ThemeSimilarityReport(Model):
    audit_id: Text = Field(default_factory=lambda: uuid4().hex)
    audit_number: int = Field(default=1, ge=1)
    state: ThemeSimilarityState = ThemeSimilarityState.ANALYZED
    model: Text
    dimensions: int | None = Field(default=None, ge=1, le=65536)
    setting_threshold: float = Field(ge=-1, le=1)
    input_count: int = Field(ge=0)
    pairs: list[ThemeSimilarityPair]
    regeneration_round: int | None = Field(default=None, ge=1)
    rejections: list[ThemeSimilarityRejection] = Field(default_factory=list)
    duration_ms: int = Field(default=0, ge=0)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    error: Text | None = None


class GenerationAttempt(Model):
    operation_id: Text | None = None
    occurred_at: Text
    stage: GenerationStage
    requested_ids: list[Text] = Field(default_factory=list, max_length=100)
    attempt: int = Field(ge=1)
    max_output_tokens: int | None = Field(default=None, ge=256, le=65536)
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
