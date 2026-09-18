"""Strict YAML loading shared by story documents, modules, catalogs and policies."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from yaml.events import AliasEvent, NodeEvent
from yaml.nodes import MappingNode, Node

from t2i_story_pipeline.errors import StoryConfigurationError
from t2i_story_pipeline.inputs.schema import StoryDocument, StoryRunConfiguration
from t2i_story_pipeline.models import Model


class _DocumentLoader(yaml.SafeLoader):
    # YAML 1.1 booleans would silently turn quality mode "off" into False.
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
            raise yaml.YAMLError("Story YAML does not support anchors or aliases")
        return super().compose_node(parent, index)

    def construct_mapping(
        self, node: MappingNode, deep: bool = False
    ) -> dict[str, object]:
        mapping: dict[str, object] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key == "<<":
                raise yaml.YAMLError(
                    "Story YAML requires string keys and forbids merge keys"
                )
            if key in mapping:
                raise yaml.YAMLError(f"Story YAML duplicate key: {key}")
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def load_yaml_model[T: Model](path: Path, model: type[T]) -> T:
    if path.suffix != ".yaml":
        raise StoryConfigurationError(f"Story input must use a .yaml file: {path}")
    try:
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            raise ValueError("empty YAML document")
        value: object = yaml.load(text, Loader=_DocumentLoader)
        if model is StoryDocument and (
            not isinstance(value, dict) or value.get("id") is None
        ):
            raise ValueError("story YAML requires an explicit id")
        return model.model_validate(value)
    except (
        OSError,
        UnicodeError,
        yaml.YAMLError,
        ValueError,
        RecursionError,
    ) as exc:
        raise StoryConfigurationError(f"Invalid Story input {path}: {exc}") from exc


def load_story_document(path: Path) -> StoryDocument:
    document = load_yaml_model(path, StoryDocument)
    document._source_path = path.resolve()
    return document


def load_run_configuration(path: Path) -> StoryRunConfiguration:
    """Load only strict UTF-8 JSON, with duplicate keys rejected at every depth."""
    if path.suffix != ".json":
        raise StoryConfigurationError(f"Story run configuration must use .json: {path}")
    try:
        text = path.read_text(encoding="utf-8")
        json.loads(text, object_pairs_hook=_unique_json_keys)
        return StoryRunConfiguration.model_validate_json(text, strict=True)
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise StoryConfigurationError(
            f"Invalid Story run configuration {path}: {exc}"
        ) from exc


def _unique_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def asset_path(root: Path, directory: str, asset_id: str) -> Path:
    """Resolve only explicitly named, root-contained local YAML assets."""
    try:
        resolved_root = root.resolve(strict=True)
        path = (resolved_root / directory / f"{asset_id}.yaml").resolve(strict=True)
        if not path.is_relative_to(resolved_root):
            raise ValueError("asset escapes asset root (including symlinks)")
        if not path.is_file():
            raise ValueError("asset is not a file")
        return path
    except (OSError, ValueError, RuntimeError) as exc:
        raise StoryConfigurationError(
            f"Cannot load asset {directory}/{asset_id}.yaml from {root}: {exc}"
        ) from exc
