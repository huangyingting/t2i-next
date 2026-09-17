"""Strict data-only story documents and explicit CLI overrides."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import yaml
from pydantic import Field, StringConstraints, ValidationError, model_validator
from yaml.events import AliasEvent, NodeEvent
from yaml.nodes import MappingNode, Node

from t2i_story_pipeline.errors import StoryConfigurationError
from t2i_story_pipeline.models import (
    ContentLevel,
    Model,
    OutputLanguage,
    StoryAuthoring,
    StoryQualityPolicy,
    StoryRequest,
    StoryRuntime,
    StoryText,
)


class StoryCast(Model):
    female_count: int | None = Field(default=None, ge=0, le=8, strict=True)
    male_count: int | None = Field(default=None, ge=0, le=8, strict=True)


class StoryGeneration(Model):
    theme_count: int = Field(default=1, ge=1, le=100, strict=True)
    frames_per_theme: int = Field(default=6, ge=1, le=6, strict=True)
    content_level: ContentLevel = ContentLevel.AESTHETIC
    output_language: OutputLanguage = OutputLanguage.CHINESE
    cast: StoryCast = Field(default_factory=StoryCast)

    def request(self, description: str, source_id: str | None) -> StoryRequest:
        return StoryRequest(
            story=description,
            source_prompt_stem=source_id,
            theme_count=self.theme_count,
            frames_per_theme=self.frames_per_theme,
            female_count=self.cast.female_count,
            male_count=self.cast.male_count,
            content_level=self.content_level,
            output_language=self.output_language,
        )


class StoryDocument(Model):
    id: Annotated[
        str,
        StringConstraints(
            min_length=1, max_length=120, pattern=r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$"
        ),
    ]
    description: StoryText
    generation: StoryGeneration = Field(default_factory=StoryGeneration)
    authoring: StoryAuthoring = Field(default_factory=StoryAuthoring)
    validation: StoryQualityPolicy = Field(default_factory=StoryQualityPolicy)
    runtime: StoryRuntime = Field(default_factory=StoryRuntime)

    @model_validator(mode="after")
    def request_is_valid(self) -> StoryDocument:
        self.generation.request(self.description, self.id)
        return self


class _DocumentLoader(yaml.SafeLoader):
    # YAML 1.1 treats "off" as False; mode names must remain strings.
    yaml_implicit_resolvers = {
        key: [
            (tag, pattern)
            for tag, pattern in resolvers
            if tag != "tag:yaml.org,2002:bool"
        ]
        for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }

    def compose_node(self, parent: Node | None, index: str | int | None) -> Node:
        event = self.peek_event()
        if isinstance(event, AliasEvent) or (
            isinstance(event, NodeEvent) and event.anchor is not None
        ):
            raise yaml.YAMLError("Story YAML 不支持 anchors 或 aliases")
        return super().compose_node(parent, index)

    def construct_mapping(
        self, node: MappingNode, deep: bool = False
    ) -> dict[str, object]:
        mapping: dict[str, object] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key == "<<":
                raise yaml.YAMLError("Story YAML 只支持字符串字段，不支持 merge keys")
            if key in mapping:
                raise yaml.YAMLError(f"Story YAML 字段重复：{key}")
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def load_story_document(path: Path) -> StoryDocument:
    if path.suffix != ".yaml":
        raise StoryConfigurationError("故事输入必须使用 .yaml 文档，不再支持 TXT 输入")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise StoryConfigurationError(f"无法读取 UTF-8 故事文档 {path}：{exc}") from exc
    if not text.strip():
        raise StoryConfigurationError(f"故事文档不能为空：{path}")
    try:
        value: object = yaml.load(text, Loader=_DocumentLoader)
        document = StoryDocument.model_validate(value)
    except (yaml.YAMLError, ValidationError) as exc:
        raise StoryConfigurationError(f"故事文档无效 {path}：{exc}") from exc
    return document
