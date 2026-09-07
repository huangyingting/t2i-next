"""Domain models for prose-first story prompt generation."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    create_model,
    model_validator,
)


def _single_line(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError("文本不能包含换行")
    return value.strip()


def _directly_imageable(value: str) -> str:
    if "不可见" in value:
        raise ValueError("场景内容必须能够直接成像")
    return value


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


Text = Annotated[
    str,
    StringConstraints(min_length=1, strip_whitespace=True),
    AfterValidator(_single_line),
]
Prose = Annotated[
    str,
    StringConstraints(min_length=1, max_length=20000, strip_whitespace=True),
]
ReviewProblem = Annotated[
    str,
    StringConstraints(min_length=1, max_length=240, strip_whitespace=True),
    AfterValidator(_single_line),
]
RequiredChange = Annotated[
    str,
    StringConstraints(min_length=1, max_length=320, strip_whitespace=True),
    AfterValidator(_single_line),
]
ReviewSummary = Annotated[
    str,
    StringConstraints(min_length=1, max_length=500, strip_whitespace=True),
    AfterValidator(_single_line),
]
CreativeText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=320, strip_whitespace=True),
    AfterValidator(_single_line),
]
SceneClause = Annotated[
    str,
    StringConstraints(min_length=1, max_length=240, strip_whitespace=True),
    Field(json_schema_extra={"not": {"pattern": "不可见"}}),
    AfterValidator(_single_line),
    AfterValidator(_directly_imageable),
]
SceneText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=400, strip_whitespace=True),
    Field(json_schema_extra={"not": {"pattern": "不可见"}}),
    AfterValidator(_single_line),
    AfterValidator(_directly_imageable),
]
CharacterId = Annotated[str, StringConstraints(pattern=r"^C\d{2}$")]
BeatId = Annotated[str, StringConstraints(pattern=r"^B\d{2}$")]
SceneId = Annotated[str, StringConstraints(pattern=r"^S\d{2}$")]
ThemeId = Annotated[str, StringConstraints(pattern=r"^T\d{3}$")]


class OutputLanguage(StrEnum):
    CHINESE = "chinese"
    ENGLISH = "english"


class StoryStage(StrEnum):
    INTERPRET = "interpret"
    THEMES = "themes"
    SCENES = "scenes"
    REVIEW = "review"
    REVISE = "revise"


class NarrativeMode(StrEnum):
    TABLEAU = "tableau"
    ATMOSPHERIC = "atmospheric"
    DRAMATIC = "dramatic"


class ReviewDimension(StrEnum):
    TEMPORAL_SPATIAL_GROUNDING = "temporal_spatial_grounding"
    ENVIRONMENTAL_STORYTELLING = "environmental_storytelling"
    CAUSAL_ACTION = "causal_action"
    PHYSICAL_FEEDBACK = "physical_feedback"
    CINEMATOGRAPHY_INTEGRATION = "cinematography_integration"
    SENSORY_VISUALIZATION = "sensory_visualization"
    THEMATIC_CLOSURE = "thematic_closure"
    LANGUAGE_COHERENCE = "language_coherence"
    CREATIVE_UNITY = "creative_unity"
    STORY_SPECIFICITY = "story_specificity"


class StoryRequest(Model):
    story: Prose
    theme_count: int = Field(default=1, ge=1, le=100)
    frames_per_theme: int = Field(default=6, ge=1, le=6)
    output_language: OutputLanguage = OutputLanguage.CHINESE


class StoryCharacter(Model):
    character_id: CharacterId
    display_name: Text
    age: int = Field(ge=21, le=99)
    role: Text
    appearance: Text
    outfit: Text
    initial_emotion: Text


class StoryRelationship(Model):
    participant_ids: list[CharacterId] = Field(min_length=2, max_length=8)
    source_relationship: Text
    relationship: Text
    interaction_dynamic: Text

    @model_validator(mode="after")
    def participants_are_unique(self) -> StoryRelationship:
        if len(self.participant_ids) != len(set(self.participant_ids)):
            raise ValueError("关系中的人物 ID 不能重复")
        return self


class StoryBeat(Model):
    beat_id: BeatId
    participant_ids: list[CharacterId] = Field(min_length=1, max_length=8)
    source_action: Text
    action: Text
    visible_response: Text
    emotional_turn: Text
    visible_result: Text

    @model_validator(mode="after")
    def participants_are_unique(self) -> StoryBeat:
        if len(self.participant_ids) != len(set(self.participant_ids)):
            raise ValueError("故事节拍中的人物 ID 不能重复")
        return self


class CinematographyIntent(Model):
    camera: Text
    lighting: Text
    color_and_texture: Text


class CreativeIntent(Model):
    emotional_core: CreativeText
    narrative_tension: CreativeText
    decisive_moment: CreativeText
    visual_motif: CreativeText
    motif_progression: CreativeText
    restraint: CreativeText


class NarrativeTheme(Model):
    theme_id: ThemeId
    title: Text
    creative_intent: CreativeIntent


class NarrativeThemeBatch(Model):
    themes: list[NarrativeTheme] = Field(min_length=1, max_length=10)


class StoryBlueprint(Model):
    title: Text
    logline: Text
    time: Text
    location: Text
    environment: Text
    atmosphere: Text
    characters: list[StoryCharacter] = Field(min_length=1, max_length=8)
    relationships: list[StoryRelationship] = Field(default_factory=list)
    beats: list[StoryBeat] = Field(min_length=1, max_length=24)
    cinematography: CinematographyIntent

    @model_validator(mode="after")
    def ids_and_references_are_valid(self) -> StoryBlueprint:
        character_ids = [item.character_id for item in self.characters]
        expected_character_ids = [
            f"C{index:02d}" for index in range(1, len(self.characters) + 1)
        ]
        if character_ids != expected_character_ids:
            raise ValueError(
                f"人物 ID 必须按首次出现顺序连续编号：{expected_character_ids}"
            )

        beat_ids = [item.beat_id for item in self.beats]
        expected_beat_ids = [f"B{index:02d}" for index in range(1, len(self.beats) + 1)]
        if beat_ids != expected_beat_ids:
            raise ValueError(f"故事节拍 ID 必须按叙事顺序连续编号：{expected_beat_ids}")

        known_characters = set(character_ids)
        for relationship in self.relationships:
            unknown = set(relationship.participant_ids) - known_characters
            if unknown:
                raise ValueError(f"关系引用未知人物 ID：{sorted(unknown)}")
        for beat in self.beats:
            unknown = set(beat.participant_ids) - known_characters
            if unknown:
                raise ValueError(f"{beat.beat_id} 引用未知人物 ID：{sorted(unknown)}")
        return self


class SceneAction(Model):
    participant_ids: list[CharacterId] = Field(min_length=1, max_length=8)
    action: SceneClause
    visible_response: SceneClause
    resulting_state: SceneClause

    @model_validator(mode="after")
    def participants_are_unique(self) -> SceneAction:
        if len(self.participant_ids) != len(set(self.participant_ids)):
            raise ValueError("场景动作中的人物 ID 不能重复")
        if re.search(
            r"逐渐|随后|随即|然后|继而|先后|最终",
            f"{self.action}{self.visible_response}{self.resulting_state}",
        ):
            raise ValueError("单帧动作不得包含连续时间推进")
        return self


class VisibleText(Model):
    content: Text
    carrier: Text
    placement: Text
    appearance: Text


class NarrativeScene(Model):
    scene_id: SceneId
    beat_id: BeatId
    mode: NarrativeMode
    source_context: list[SceneClause] = Field(min_length=1, max_length=3)
    visible_character_ids: list[CharacterId] = Field(
        min_length=1,
        max_length=8,
    )
    temporal_spatial_opening: SceneText
    environmental_evidence: list[SceneClause] = Field(
        min_length=1,
        max_length=4,
    )
    character_entry: SceneText
    present_actions: list[SceneAction] = Field(min_length=1, max_length=1)
    material_and_physical_feedback: list[SceneClause] = Field(
        min_length=1,
        max_length=4,
    )
    camera_composition: SceneText
    lighting_and_color: SceneText
    sensory_evidence: list[SceneClause] = Field(min_length=1, max_length=4)
    visible_text: list[VisibleText] = Field(default_factory=list, max_length=8)
    thematic_closure: SceneText

    @model_validator(mode="after")
    def references_are_unique(self) -> NarrativeScene:
        if len(self.visible_character_ids) != len(set(self.visible_character_ids)):
            raise ValueError("叙事场景中的人物 ID 不能重复")
        if re.search(
            r"转为(?:近景|中景|远景)|跟拍|推镜|拉镜|摇镜|镜头移动",
            self.camera_composition,
        ):
            raise ValueError("单帧摄影不得包含镜头运动或景别转换")
        if re.search(
            r"逐渐|随后|随即|然后|继而|先后|最终",
            self.character_entry,
        ):
            raise ValueError("人物入画不得包含连续时间推进")
        return self


class NarrativeSequence(Model):
    scenes: list[NarrativeScene] = Field(min_length=1, max_length=24)


class RenderedNarrative(Model):
    scene_id: SceneId
    prose: Text
    prompt: Text


class NarrativeScores(Model):
    temporal_spatial_grounding: int = Field(ge=1, le=5)
    environmental_storytelling: int = Field(ge=1, le=5)
    causal_action: int = Field(ge=1, le=5)
    physical_feedback: int = Field(ge=1, le=5)
    cinematography_integration: int = Field(ge=1, le=5)
    sensory_visualization: int = Field(ge=1, le=5)
    thematic_closure: int = Field(ge=1, le=5)
    language_coherence: int = Field(ge=1, le=5)
    creative_unity: int = Field(ge=1, le=5)
    story_specificity: int = Field(ge=1, le=5)

    def meets_threshold(self, threshold: int = 4) -> bool:
        return all(value >= threshold for value in self.model_dump().values())


class ReviewIssue(Model):
    scene_id: SceneId
    dimension: ReviewDimension
    problem: ReviewProblem
    required_change: RequiredChange


class SceneReview(Model):
    scene_id: SceneId
    scores: NarrativeScores
    issues: list[ReviewIssue] = Field(max_length=16)


class NarrativeReview(Model):
    scene_reviews: list[SceneReview] = Field(min_length=1, max_length=24)
    overall_summary: ReviewSummary

    def meets_threshold(self, threshold: int = 4) -> bool:
        return all(
            review.scores.meets_threshold(threshold) and not review.issues
            for review in self.scene_reviews
        )


class TokenUsage(Model):
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)

    def __add__(self, other: TokenUsage) -> TokenUsage:
        def add_optional(left: int | None, right: int | None) -> int | None:
            if left is None and right is None:
                return None
            return (left or 0) + (right or 0)

        return TokenUsage(
            prompt_tokens=add_optional(
                self.prompt_tokens,
                other.prompt_tokens,
            ),
            completion_tokens=add_optional(
                self.completion_tokens,
                other.completion_tokens,
            ),
            total_tokens=add_optional(
                self.total_tokens,
                other.total_tokens,
            ),
        )


class NarrativeThemeResult(Model):
    theme: NarrativeTheme
    sequence: NarrativeSequence
    narratives: list[RenderedNarrative] = Field(min_length=1, max_length=6)
    reviews: list[NarrativeReview] = Field(min_length=1, max_length=6)
    revision_count: int = Field(ge=0, le=5)

    @model_validator(mode="after")
    def outputs_match_sequence(self) -> NarrativeThemeResult:
        expected_scene_ids = [
            f"S{index:02d}" for index in range(1, len(self.sequence.scenes) + 1)
        ]
        sequence_ids = [scene.scene_id for scene in self.sequence.scenes]
        narrative_ids = [narrative.scene_id for narrative in self.narratives]
        if sequence_ids != expected_scene_ids:
            raise ValueError(f"场景 ID 必须连续且数量正确：{expected_scene_ids}")
        if narrative_ids != expected_scene_ids:
            raise ValueError(f"叙事输出必须与场景一一对应：{expected_scene_ids}")
        if len(self.reviews) != self.revision_count + 1:
            raise ValueError("评审数量必须等于修订次数加一")
        if not self.reviews[-1].meets_threshold():
            raise ValueError("最终叙事评审未达到发布标准")
        return self


class StoryResult(Model):
    run_id: Annotated[
        str,
        StringConstraints(pattern=r"^[a-f0-9]{12}$"),
    ]
    request: StoryRequest
    blueprint: StoryBlueprint
    themes: list[NarrativeThemeResult] = Field(min_length=1, max_length=100)
    usage: TokenUsage

    @model_validator(mode="after")
    def outputs_match_request(self) -> StoryResult:
        expected_theme_ids = [
            f"T{index:03d}" for index in range(1, self.request.theme_count + 1)
        ]
        actual_theme_ids = [theme_result.theme.theme_id for theme_result in self.themes]
        if actual_theme_ids != expected_theme_ids:
            raise ValueError(f"主题 ID 必须连续且数量正确：{expected_theme_ids}")
        for theme_result in self.themes:
            if len(theme_result.sequence.scenes) != self.request.frames_per_theme:
                raise ValueError(
                    f"{theme_result.theme.theme_id} 的画面数量必须为 "
                    f"{self.request.frames_per_theme}"
                )
        return self


def exact_theme_batch_model(count: int) -> type[NarrativeThemeBatch]:
    return create_model(
        f"NarrativeThemeBatch{count}",
        __base__=NarrativeThemeBatch,
        themes=(
            list[NarrativeTheme],
            Field(min_length=count, max_length=count),
        ),
    )


def exact_narrative_sequence_model(
    count: int,
) -> type[NarrativeSequence]:
    return create_model(
        f"NarrativeSequence{count}",
        __base__=NarrativeSequence,
        scenes=(
            list[NarrativeScene],
            Field(min_length=count, max_length=count),
        ),
    )


def exact_narrative_review_model(
    count: int,
) -> type[NarrativeReview]:
    return create_model(
        f"NarrativeReview{count}",
        __base__=NarrativeReview,
        scene_reviews=(
            list[SceneReview],
            Field(min_length=count, max_length=count),
        ),
    )


def schema_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")
    return normalized[:64] or "story_response"
