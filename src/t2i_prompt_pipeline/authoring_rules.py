"""Resolve ordered Chinese authoring rules from simple line files."""

from __future__ import annotations

from pathlib import Path

from t2i_prompt_pipeline.errors import ConfigurationError
from t2i_prompt_pipeline.models import (
    GenerationSpec,
    GenerationStage,
    OutputLanguage,
    ResolvedRuleSet,
)

_SYSTEM_RULES_DIRECTORY = (
    Path(__file__).resolve().parent / "rule_packs" / "system"
)
_STAGE_FILENAMES = {
    GenerationStage.FOUNDATION: "foundation.rules",
    GenerationStage.THEMES: "themes.rules",
    GenerationStage.FRAMES: "frames.rules",
}


def resolve_rules(
    spec: GenerationSpec,
    *,
    user_directory: Path | None = None,
) -> ResolvedRuleSet:
    """Resolve the immutable rules used by one new run."""
    system_directory = _require_directory(
        _SYSTEM_RULES_DIRECTORY,
        "系统规则目录",
    )
    resolved_user_directory = (
        _require_directory(user_directory.resolve(), "用户规则目录")
        if user_directory is not None
        else None
    )
    return ResolvedRuleSet(
        foundation=_compile(
            GenerationStage.FOUNDATION,
            spec,
            system_directory,
            resolved_user_directory,
        ),
        themes=_compile(
            GenerationStage.THEMES,
            spec,
            system_directory,
            resolved_user_directory,
        ),
        frames=_compile(
            GenerationStage.FRAMES,
            spec,
            system_directory,
            resolved_user_directory,
        ),
    )


def _compile(
    stage: GenerationStage,
    spec: GenerationSpec,
    system_directory: Path,
    user_directory: Path | None,
) -> tuple[str, ...]:
    rules = [
        rule
        for path in _selected_paths(system_directory, stage, spec)
        for rule in _read_rule_file(path, required=True)
    ]
    if user_directory is not None:
        rules.extend(
            rule
            for path in _selected_paths(user_directory, stage, spec)
            for rule in _read_rule_file(path, required=False)
        )
    if stage == GenerationStage.THEMES:
        rules.append(_character_label_rule(spec))
    rules.append(_output_language_rule(spec))
    return tuple(rules)


def _selected_paths(
    directory: Path,
    stage: GenerationStage,
    spec: GenerationSpec,
) -> tuple[Path, ...]:
    paths = [
        directory / "common.rules",
        directory / _STAGE_FILENAMES[stage],
        directory / "content_levels" / f"{spec.content_level.value}.rules",
    ]
    if stage == GenerationStage.FRAMES:
        paths.append(
            directory / "frame_modes" / f"{spec.frame_mode.value}.rules"
        )
    return tuple(paths)


def _require_directory(path: Path, label: str) -> Path:
    if not path.is_dir():
        raise ConfigurationError(f"{label}不存在：{path}")
    return path


def _read_rule_file(path: Path, *, required: bool) -> tuple[str, ...]:
    if not path.exists():
        if required:
            raise ConfigurationError(f"规则文件不存在：{path}")
        return ()
    if not path.is_file():
        raise ConfigurationError(f"规则路径不是文件：{path}")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise ConfigurationError(f"规则文件无法读取：{path}：{exc}") from exc
    return tuple(
        stripped
        for line in text.splitlines()
        if (stripped := line.strip()) and not stripped.startswith("#")
    )


def _output_language_rule(spec: GenerationSpec) -> str:
    if spec.output_language == OutputLanguage.ENGLISH:
        return (
            "输出语言要求：所有自然语言创作字段使用自然、流利、简练的英文；"
            "除姓名和不可替代的专有术语外，不得夹杂中文或其他语言。"
        )
    return (
        "输出语言要求：所有自然语言创作字段使用自然、流利、简练的中文；"
        "除 brief 原文或其他规则明确允许原样保留的姓名和专有术语外，"
        "只使用中文、阿拉伯数字和常规标点，"
        "摄影、服饰和材质术语也必须译为中文，不得夹杂英文单词或状态占位词；"
        "返回前逐个自然语言字段搜索 A-Z 和 a-z 字符，未获上述允许的内容"
        "全部翻译或删除；semantic_name 等 schema 规定的机器标识字段不受此限制。"
    )


def _character_label_rule(spec: GenerationSpec) -> str:
    if spec.output_language == OutputLanguage.ENGLISH:
        female_labels = "Woman 1、Woman 2"
        male_labels = "Man 1、Man 2"
    else:
        female_labels = "女1、女2"
        male_labels = "男1、男2"
    return (
        "Character.label 是最终显示名：人物有真实姓名就填写姓名；没有姓名的"
        f"女性按出现顺序填写 {female_labels}，没有姓名的男性按出现顺序填写 "
        f"{male_labels}。label 不得只填写笼统性别、主角、人物序号或内部角色 ID。"
    )
