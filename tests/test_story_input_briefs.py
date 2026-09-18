"""Visual asset contracts, independent of execution defaults and prompt templates."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

from t2i_story_pipeline.authoring_rules import resolve_story_rules
from t2i_story_pipeline.errors import StoryConfigurationError
from t2i_story_pipeline.inputs import (
    CatalogDocument,
    InputOverrides,
    ModuleDocument,
    ResolvedStoryInput,
    StoryDocument,
    StoryRunConfiguration,
    load_story_document,
    resolve_story_input,
)
from t2i_story_pipeline.models import ContentLevel, StoryAuthoring, StoryStage
from t2i_story_pipeline.prompts import frame_messages, theme_messages
from tests.story_factories import make_theme

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
RECIPES = REPOSITORY_ROOT / "story-inputs" / "recipes"
POLICIES = REPOSITORY_ROOT / "src" / "t2i_story_pipeline" / "rule_packs" / "policies"


def authoring_prose(authoring: StoryAuthoring) -> Iterator[tuple[str, str]]:
    for stage in StoryStage:
        for index, rule in enumerate(getattr(authoring, stage.value).common):
            yield f"authoring.{stage.value}.common[{index}]", rule
    for level, refinement in authoring.level_refinements.items():
        for owner in ("shared", "themes", "frames"):
            for index, rule in enumerate(getattr(refinement, owner)):
                yield (
                    f"authoring.level_refinements.{level.value}.{owner}[{index}]",
                    rule,
                )


def bundled_authoring_prose(path: Path) -> Iterator[tuple[str, str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if path.parent.name == "_catalogs":
        catalog = CatalogDocument.model_validate(data)
        for entry in catalog.entries:
            for stage in StoryStage:
                for index, rule in enumerate(getattr(entry, stage.value)):
                    yield f"entries.{entry.id}.{stage.value}[{index}]", rule
            if entry.frame_assignment:
                for slot in entry.frame_assignment.slots:
                    for index, rule in enumerate(slot.rules):
                        yield (
                            f"entries.{entry.id}.frame_assignment.{slot.frame_id}"
                            f".rules[{index}]",
                            rule,
                        )
        return
    if path.parent.name == "_modules":
        authoring = ModuleDocument.model_validate(data).authoring
    elif path.parent == POLICIES:
        authoring = StoryAuthoring.model_validate(data["authoring"])
    else:
        document = StoryDocument.model_validate(data)
        yield "description", document.description
        authoring = document.authoring
    yield from authoring_prose(authoring)


def story_contract(document: StoryDocument) -> str:
    """Read all visual facts, without resolving unselected branches into a prompt."""
    sections = [document.description]
    sections.extend(rule for _, rule in authoring_prose(document.authoring))
    assert document._source_path is not None
    root = document._source_path.parent
    paths = [
        root / "_modules" / f"{reference.id}.yaml" for reference in document.modules
    ]
    if document.allocation:
        paths.append(root / "_catalogs" / f"{document.allocation.catalog}.yaml")
    for path in paths:
        sections.extend(rule for _, rule in bundled_authoring_prose(path))
    return "\n".join(dict.fromkeys(sections))


def audit_run_configuration(
    document: StoryDocument, *, content_level: ContentLevel | None = None
) -> StoryRunConfiguration:
    """Explicit audit choices from visual applicability, never a filename map."""
    generation = {
        "theme_count": 1,
        "frames_per_theme": 6,
        "output_language": "chinese",
        "content_level": content_level
        or (document.requirements.content_levels or (ContentLevel.AESTHETIC,))[0],
    }
    if document.allocation:
        assert document._source_path is not None
        path = (
            document._source_path.parent
            / "_catalogs"
            / f"{document.allocation.catalog}.yaml"
        )
        catalog = CatalogDocument.model_validate(
            yaml.safe_load(path.read_text(encoding="utf-8"))
        )
        if document.allocation.type == "fixed_slots":
            generation["theme_count"] = len(catalog.slots)
        assigned_counts = {
            entry.frame_assignment.slot_count
            for entry in catalog.entries
            if entry.frame_assignment
        }
        assert len(assigned_counts) <= 1, "audit needs one compatible frame count"
        if assigned_counts:
            generation["frames_per_theme"] = assigned_counts.pop()
    return StoryRunConfiguration(generation=generation)


def authoring_pool(document, label, *, stage=StoryStage.THEMES):
    prefix = f"{label}: - "
    return [
        rule.removeprefix(prefix)
        for rule in document.authoring.selected(stage, ContentLevel.HARDCORE)
        if rule.startswith(prefix)
    ]


def untranslated_authoring(prose: str) -> list[str]:
    unquoted = re.sub(
        r'`[^`]*`|"[^"]*"|“[^”]*”|‘[^’]*’|(?<![A-Za-z])\'[^\'\n]+\'(?![A-Za-z])',
        "",
        " ".join(prose.split()),
    )
    if not unquoted.strip(" \t:;,.，。；：、-"):
        return []
    problems = []
    if not re.search(r"[\u3400-\u4dbf\u4e00-\u9fff]", unquoted):
        problems.append("natural-language instruction contains no Chinese")
    problems.extend(
        f"untranslated English prose: {run}"
        for run in re.findall(
            r"\b[A-Za-z][A-Za-z'-]*(?:[ \t]+[A-Za-z][A-Za-z'-]*){5,}\b", unquoted
        )
    )
    return problems


@pytest.fixture
def shared_authoring_document(tmp_path):
    module_path = tmp_path / "_modules" / "neutral-layout.yaml"
    module_path.parent.mkdir()
    module_path.write_text(
        yaml.safe_dump(
            {
                "id": "neutral-layout",
                "kind": "layout_multiview",
                "authoring": {
                    "level_refinements": {
                        "aesthetic": {"shared": ["模块共享的柔和纹理。"]},
                        "hardcore": {"shared": ["模块未选中的强烈纹理。"]},
                    },
                    "themes": {"common": ["模块主题布局说明。"]},
                    "frames": {"common": ["模块画面布局说明。"]},
                },
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    path = tmp_path / "neutral.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "id": "neutral",
                "description": "中性的候选场景。",
                "modules": [
                    {
                        "id": "neutral-layout",
                        "parameters": {"layout": "grid", "rows": 1, "columns": 2},
                    }
                ],
                "authoring": {
                    "level_refinements": {
                        "aesthetic": {"shared": ["候选池: - 未选中的唯美候选"]},
                        "hardcore": {
                            "shared": ["候选池: - 两阶段共享候选"],
                            "themes": ["候选池: - 主题独有候选"],
                            "frames": ["候选池: - 画面独有候选"],
                        },
                    },
                    "themes": {"common": ["候选池: - 主题通用候选"]},
                    "frames": {"common": ["候选池: - 画面通用候选"]},
                },
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return load_story_document(path), path, module_path


def test_source_conservation_reads_shared_recipe_and_module_rules(
    shared_authoring_document,
):
    document, document_path, module_path = shared_authoring_document
    contract = story_contract(document)
    resolved = resolve_story_input(document)
    for path in (document_path, module_path):
        fields = dict(bundled_authoring_prose(path))
        aesthetic = "authoring.level_refinements.aesthetic.shared[0]"
        hardcore = "authoring.level_refinements.hardcore.shared[0]"
        assert all(prose in contract for prose in fields.values())
        assert all(not untranslated_authoring(prose) for prose in fields.values())
        for stage in StoryStage:
            assert fields[aesthetic] in resolved.rules.text_for(stage)
            assert fields[hardcore] not in resolved.rules.text_for(stage)


@pytest.mark.parametrize(
    ("stage", "label"), [(StoryStage.THEMES, "主题"), (StoryStage.FRAMES, "画面")]
)
def test_authoring_pool_reads_shared_and_stage_specific_candidates(
    shared_authoring_document, stage, label
):
    document, _, _ = shared_authoring_document
    assert authoring_pool(document, "候选池", stage=stage) == [
        f"{label}通用候选",
        "两阶段共享候选",
        f"{label}独有候选",
    ]


@pytest.mark.parametrize("level", tuple(ContentLevel))
@pytest.mark.parametrize("owner", ("shared", "themes", "frames"))
def test_chinese_guard_does_not_skip_level_refinement_owners(level, owner):
    authoring = StoryAuthoring.model_validate(
        {
            "level_refinements": {level: {owner: ["Untranslated instruction."]}},
            "themes": {"common": ["中文的主题说明。"]},
            "frames": {"common": ["中文的画面说明。"]},
        }
    )
    fields = dict(authoring_prose(authoring))
    assert untranslated_authoring(
        fields[f"authoring.level_refinements.{level.value}.{owner}[0]"]
    ) == ["natural-language instruction contains no Chinese"]


@pytest.mark.parametrize(
    ("prose", "valid"),
    [
        ("使用 Blender 制作具有 ASCII 标题的中国场景。", True),
        ('海报标题为 "A Summer Together"，白色衬线字。', True),
        ("使用 `left leg` 和 “right leg” 分别描述两条腿。", True),
        ('"A Summer Together"', True),
        ("Create an original scene with a coherent adult cast.", False),
        ("完整场景。Create an original scene with a coherent adult cast.", False),
        ('Write a scene with "Chinese title" and keep every adult visible.', False),
    ],
)
def test_bundled_language_guard_preserves_literals_not_english_instructions(
    prose, valid
):
    assert (not untranslated_authoring(prose)) is valid


@pytest.mark.parametrize(
    "path",
    sorted((*RECIPES.rglob("*.yaml"), *POLICIES.glob("*.yaml"))),
    ids=lambda path: str(path.relative_to(REPOSITORY_ROOT)),
)
def test_all_bundled_authoring_is_chinese_except_literal_anchors(path):
    fields = list(bundled_authoring_prose(path))
    assert fields
    violations = [
        f"{field}: {problem}"
        for field, prose in fields
        for problem in untranslated_authoring(prose)
    ]
    assert not violations, "\n".join(violations)


def test_story_inputs_are_yaml_documents_with_matching_ids():
    paths = sorted(RECIPES.glob("*.yaml"))
    assert len(paths) == 48
    assert not list(RECIPES.parent.glob("*.yaml"))
    assert not list(RECIPES.glob("*.txt"))
    for path in paths:
        document = load_story_document(path)
        assert document.id == path.stem
        assert document.description.strip()


@pytest.mark.parametrize("path", sorted(RECIPES.glob("*.yaml")), ids=lambda p: p.stem)
def test_bundled_run_defaults_are_uniform_not_recipe_specific(path):
    document = load_story_document(path)
    requires_selection = (
        document.requirements.content_levels is not None
        and ContentLevel.AESTHETIC not in document.requirements.content_levels
    )
    fixed = document.allocation and document.allocation.type == "fixed_slots"
    if requires_selection or fixed:
        with pytest.raises(
            StoryConfigurationError, match="content_level|exactly match"
        ):
            resolve_story_input(document)
    else:
        resolved = resolve_story_input(document)
        assert resolved.run_configuration == StoryRunConfiguration()
        assert resolved.request.theme_count == 1
        assert resolved.request.frames_per_theme == 6
        assert resolved.request.content_level == ContentLevel.AESTHETIC
        assert resolved.request.output_language == "chinese"
        assert resolved.quality.frames.checks == ()
    configured = resolve_story_input(
        document, run_configuration=audit_run_configuration(document)
    )
    assert configured.request.story == document.description
    assert configured.request.source_prompt_stem == document.id
    assert configured.request.female_count == document.cast.female_count
    assert configured.request.male_count == document.cast.male_count


@pytest.mark.parametrize("path", sorted(RECIPES.glob("*.yaml")), ids=lambda p: p.stem)
def test_recipe_compilation_and_frozen_replay_select_only_active_level(
    path, monkeypatch
):
    document = load_story_document(path)
    for level in document.requirements.content_levels or tuple(ContentLevel):
        configuration = audit_run_configuration(document, content_level=level)
        resolved = resolve_story_input(
            document,
            run_configuration=configuration,
        )
        assert resolved.run_configuration == configuration
        assert resolved.request.content_level == level
        assert resolved.request.theme_count == configuration.generation.theme_count
        assert resolved.request.frames_per_theme == (
            configuration.generation.frames_per_theme
        )
        base = resolve_story_rules(resolved.request)
        theme_ids = [plan.theme_id for plan in resolved.plans]
        contexts = {
            stage: resolved.context_for(stage, theme_ids) for stage in StoryStage
        }
        for stage in StoryStage:
            selected = document.authoring.selected(stage, level)
            compiled = getattr(resolved.rules, stage.value)
            assert set(getattr(base, stage.value)) <= set(compiled)
            assert set(selected) <= set(compiled)
            excluded = {
                rule
                for other in document.authoring.level_refinements
                if other != level
                for rule in document.authoring.selected(stage, other)
            } - set(selected)
            assert excluded.isdisjoint(compiled)
            for plan, context in zip(
                resolved.plans, contexts[stage]["plans"], strict=True
            ):
                assignment = plan.entry.frame_assignment if plan.entry else None
                expected_slots = (
                    [slot.model_dump(mode="json") for slot in assignment.slots]
                    if stage == StoryStage.FRAMES and assignment
                    else []
                )
                assert context["frame_slots"] == expected_slots
                assert context["cast"] == plan.cast.model_dump(mode="json")
        messages = (
            theme_messages(resolved, count=1, existing_themes=[]),
            frame_messages(
                resolved,
                make_theme(),
                requested_frame_ids=["F02"],
                accepted_frames=[],
            ),
        )
        frozen = resolved.model_dump_json()

        def unexpected_asset_read(*args, **kwargs):
            raise AssertionError("frozen replay must not reopen recipe or rule files")

        with monkeypatch.context() as replay:
            replay.setattr(Path, "open", unexpected_asset_read)
            restored = ResolvedStoryInput.model_validate_json(frozen)
            assert restored.model_dump_json() == frozen
            assert restored.fingerprint() == resolved.fingerprint()
            assert restored.run_configuration == configuration
            for stage in StoryStage:
                assert restored.context_for(stage, theme_ids) == contexts[stage]
            assert theme_messages(restored, count=1, existing_themes=[]) == messages[0]
            assert (
                frame_messages(
                    restored,
                    make_theme(),
                    requested_frame_ids=["F02"],
                    accepted_frames=[],
                )
                == messages[1]
            )


def test_fixed_couple_catalog_preserves_one_hundred_ordered_plans():
    document = load_story_document(RECIPES / "indoor-couple-pose-aesthetic.yaml")
    configuration = StoryRunConfiguration(
        generation={
            "theme_count": 100,
            "frames_per_theme": 1,
            "output_language": "english",
        }
    )
    resolved = resolve_story_input(document, run_configuration=configuration)
    assert (resolved.request.female_count, resolved.request.male_count) == (1, 1)
    catalog = json.loads(
        next(s.content for s in resolved.sources if s.kind == "catalog")
    )
    assert len(resolved.plans) == len(set(catalog["slots"])) == 100
    assert [plan.entry.id for plan in resolved.plans] == catalog["slots"]
    for overrides in (
        InputOverrides(theme_count=99),
        InputOverrides(female_count=0),
        InputOverrides(male_count=0),
    ):
        with pytest.raises(StoryConfigurationError):
            resolve_story_input(document, overrides, run_configuration=configuration)
    changed = resolve_story_input(
        document,
        InputOverrides(frames_per_theme=2, output_language="chinese"),
        run_configuration=configuration,
    )
    assert changed.request.frames_per_theme == 2
    assert changed.request.output_language == "chinese"
    assert changed.plans == resolved.plans


@pytest.mark.parametrize("name", ["pose", "dress"])
def test_six_internal_views_remain_one_person_and_one_narrative_frame(name):
    document = load_story_document(RECIPES / f"{name}.yaml")
    resolved = resolve_story_input(document, InputOverrides(frames_per_theme=1))
    assert (resolved.request.female_count, resolved.request.male_count) == (1, 0)
    layout = next(m for m in resolved.modules if m.kind == "layout_multiview")
    assert (layout.parameters.min_views, layout.parameters.max_views) == (6, 6)
    assert resolved.request.frames_per_theme == 1
    assert resolved.plans[0].cast.total == 1
    with pytest.raises(StoryConfigurationError):
        resolve_story_input(document, InputOverrides(male_count=1))


def test_human_typography_retains_twenty_six_catalog_casts():
    document = load_story_document(RECIPES / "human-typography.yaml")
    resolved = resolve_story_input(document, InputOverrides(theme_count=26))
    assert resolved.request.female_count is None
    assert resolved.request.male_count is None
    assert len({plan.entry.id for plan in resolved.plans}) == 26
    for plan in resolved.plans:
        assert plan.cast.total == plan.entry.cast.total
        assert plan.cast.min_female == plan.entry.cast.min_female
        assert plan.cast.min_male == plan.entry.cast.min_male
    with pytest.raises(StoryConfigurationError):
        resolve_story_input(document, InputOverrides(female_count=1))


@pytest.mark.parametrize("name", ["miniature-giant-encounter", "giant-country-fantasy"])
@pytest.mark.parametrize("level", [ContentLevel.EROTIC, ContentLevel.HARDCORE])
def test_giant_is_one_additional_fixed_role_with_total_at_most_eight(name, level):
    document = load_story_document(RECIPES / f"{name}.yaml")
    resolved = resolve_story_input(
        document, InputOverrides(content_level=level, female_count=7, male_count=0)
    )
    assert resolved.request.female_count == 7
    for plan in resolved.plans:
        assert plan.cast.scope == document.cast.scope != "all_people"
        assert len(plan.cast.fixed_roles) == 1
        assert plan.cast.fixed_roles[0].sex == "theme_choice"
        assert plan.cast.total == 8
    with pytest.raises(StoryConfigurationError):
        resolve_story_input(
            document, InputOverrides(content_level=level, female_count=8, male_count=0)
        )
    with pytest.raises(StoryConfigurationError, match="content_level"):
        resolve_story_input(document)


@pytest.mark.parametrize("level", tuple(ContentLevel))
def test_motion_blur_background_bands_do_not_expand_principal_cast_capacity(level):
    document = load_story_document(RECIPES / "motion-blur-photography.yaml")
    resolved = resolve_story_input(
        document, InputOverrides(content_level=level, female_count=8, male_count=0)
    )
    cast = resolved.plans[0].cast
    assert cast.scope == "primary_people"
    assert cast.principal_total == 8
    assert cast.total is None
    assert (cast.total_min, cast.total_max) == (8, 38)
    assert [(band.min, band.max) for band in cast.background_counts] == [
        (0, 0),
        (2, 5),
        (6, 15),
        (16, 30),
    ]
    assert {
        count
        for band in cast.background_counts
        for count in range(band.min, band.max + 1)
    } == {0, *range(2, 31)}


@pytest.mark.parametrize(
    "name,product",
    [
        ("film-post", "poster"),
        ("post-layout", "poster"),
        ("magazine-cover", "magazine_cover"),
        ("jav-dvd-wrap", "sleeve"),
    ],
)
@pytest.mark.parametrize("language", ["chinese", "english"])
def test_visible_copy_is_independent_of_prompt_language_in_both_stages(
    name, product, language
):
    document = load_story_document(RECIPES / f"{name}.yaml")
    resolved = resolve_story_input(document, InputOverrides(output_language=language))
    assert resolved.quality.frames.checks == ()
    for stage in StoryStage:
        context = resolved.context_for(stage, ["T001"])
        copy = next(m for m in context["modules"] if m["kind"] == "visible_copy")
        assert copy["parameters"] == {
            "product": product,
            "copy_language": "english",
            "ascii": "required",
        }
        assert resolved.request.output_language == language
    frames = resolved.rules.text_for(StoryStage.FRAMES)
    assert "准确的物理载体、画内位置和排版方式" in frames
    assert "各处文字内容保持一致" in frames
    assert "而不是描述性提示词的语言" in frames
    assert "最后一个字符必须是" not in frames
    assert "添加字面 ASCII 字符 `: `" not in frames


@pytest.mark.parametrize("language", ["chinese", "english"])
@pytest.mark.parametrize("mode", ["off", "report", "enforce"])
def test_bundled_visual_recipe_accepts_external_output_constraints(language, mode):
    document = load_story_document(RECIPES / "surreal-conceptual-portrait.yaml")
    checks = (
        [
            {
                "type": "word_count",
                "when_language": "english",
                "min_words": 123,
                "max_words": 234,
            },
            {"type": "ascii", "when_language": "english"},
        ]
        if language == "english"
        else [{"type": "prose_length", "min_chars": 321, "max_chars": 654}]
    )
    configuration = StoryRunConfiguration(
        generation={"output_language": language},
        validation={"frames": {"mode": mode, "checks": checks}},
    )
    resolved = resolve_story_input(document, run_configuration=configuration)
    assert resolved.quality == configuration.validation
    assert resolved.run_configuration == configuration
    restored = ResolvedStoryInput.model_validate_json(resolved.model_dump_json())
    assert restored.fingerprint() == resolved.fingerprint()
    frames = frame_messages(
        restored, make_theme(), requested_frame_ids=["F01"], accepted_frames=[]
    )
    themes = theme_messages(restored, count=1, existing_themes=[])
    assert "123" not in themes[0].content
    assert "321" not in themes[0].content
    expected = ("123", "234") if language == "english" else ("321", "654")
    assert all(bound in frames[0].content for bound in expected)
    assert resolve_story_input(document).quality.frames.checks == ()


def test_restroom_age_and_camera_cycles_keep_f02_identity_after_freezing():
    resolved = resolve_story_input(
        load_story_document(RECIPES / "piss.yaml"),
        InputOverrides(theme_count=13, frames_per_theme=2),
    )
    ages = ("25–34", "35–49", "50–64", "65–79")
    views = (
        ("前缘，采用正面视角", "左缘，采用左侧视角"),
        ("右缘，采用右侧视角", "后缘，采用背面视角"),
        ("前侧缘，采用前四分之三视角", "后侧缘，采用后四分之三视角"),
    )
    restored = ResolvedStoryInput.model_validate_json(resolved.model_dump_json())
    for index, plan in enumerate(restored.plans):
        assert plan.entry.id == f"slot-{index % 12 + 1:02d}"
        assert ages[index % 4] in " ".join(plan.entry.themes)
        assert ages[index % 4] in " ".join(plan.entry.frames)
        slots = plan.entry.frame_assignment.slots
        assert [slot.frame_id for slot in slots] == ["F01", "F02"]
        for slot, view in zip(slots, views[index % 3], strict=True):
            assert view in " ".join(slot.rules)
        retry = restored.context_for(
            StoryStage.FRAMES, [plan.theme_id], frame_ids=["F02"]
        )
        assert retry["plans"][0]["frame_slots"] == [slots[1].model_dump(mode="json")]
        assert "VIEW DIRECTION LOCK" not in json.dumps(retry)
    assert restored.plans[0].entry == restored.plans[12].entry


@pytest.mark.parametrize("batch_size", [1, 2, 10])
def test_confined_pose_and_emotion_cycles_are_not_execution_count_minimums(batch_size):
    document = load_story_document(RECIPES / "confined-exhibition-fantasy.yaml")
    resolved = resolve_story_input(
        document, InputOverrides(theme_count=31, theme_batch_size=batch_size)
    )
    families = ("folded", "raised-hips", "spread-eagle")
    shapes = ("身体折叠", "抬高骨盆", "对角伸展")
    emotions = (
        "主动挑逗",
        "羞耻但享受",
        "得意炫耀",
        "从容自信",
        "调皮邀请",
        "紧张兴奋",
        "惊讶后微笑",
        "专注沉浸",
        "慵懒满足",
        "大胆直视",
    )
    for index, plan in enumerate(resolved.plans):
        assert plan.entry.id == f"{families[index % 3]}-emotion-{index % 10 + 1:02d}"
        assert shapes[index % 3] in " ".join(plan.entry.themes)
        assert emotions[index % 10] in " ".join(plan.entry.themes)
        assert emotions[index % 10] in " ".join(plan.entry.frames)
        assert plan.cast.total == 4
    for count in (1, 2, 3):
        selected = resolve_story_input(document, InputOverrides(theme_count=count))
        assert selected.plans == resolved.plans[:count]
    for cast in (
        {"female_count": 1, "male_count": 3},
        {"female_count": 3, "male_count": 0},
    ):
        with pytest.raises(StoryConfigurationError):
            resolve_story_input(document, InputOverrides(**cast))


def test_near_future_world_and_action_cycles_preserve_semantics_without_prefixes():
    resolved = resolve_story_input(
        load_story_document(RECIPES / "near-future-intimacy-realism.yaml"),
        InputOverrides(theme_count=31),
    )
    entries = [plan.entry for plan in resolved.plans]
    assert [entry.id for entry in entries] == [
        f"seed-{index % 30 + 1:02d}" for index in range(31)
    ]
    assert len(set(entry.themes for entry in entries[:30])) == 30
    assert entries[30] == entries[0]
    scenes, seeds, solo_actions, group_actions = [], [], [], []
    for entry in entries:
        assert not any("已选场景世界分桶" in rule for rule in entry.themes)
        assert not any("T001" in rule for rule in (*entry.themes, *entry.frames))
        assert set(entry.themes) <= set(entry.frames)
        for target, prefix in (
            (scenes, "场景："),
            (seeds, "环境构想："),
            (solo_actions, "当请求的总人数为一名成年人时，"),
            (group_actions, "当请求的总人物构成包含两名或更多成年人时，"),
        ):
            target.append(
                next(rule for rule in entry.themes if rule.startswith(prefix))
            )
    assert len(set(seeds[:30])) == 30
    for cycle in (scenes, solo_actions, group_actions):
        assert len(set(cycle[:10])) == 10
        assert all(value == cycle[index % 10] for index, value in enumerate(cycle))
    assert sum("自慰" in action for action in group_actions[:10]) >= 2
    assert (
        sum(
            any(family in action for family in ("束缚", "拍打", "蒙眼", "支配", "捆绑"))
            for action in group_actions[:10]
        )
        >= 4
    )
    assert sum("插入" in action for action in group_actions[:10]) <= 3
    for stage in StoryStage:
        context = resolved.context_for(stage, ["T009", "T011", "T030", "T031"])
        assert [plan["entry"]["id"] for plan in context["plans"]] == [
            "seed-09",
            "seed-11",
            "seed-30",
            "seed-01",
        ]


@pytest.mark.parametrize(
    "female,male", [(1, 0), (0, 2), (1, 1), (2, 0), (1, 7), (7, 1), (8, 0)]
)
def test_social_caricature_requires_multiple_people_and_at_least_one_woman(
    female, male
):
    document = load_story_document(RECIPES / "everyday-social-caricature.yaml")
    overrides = InputOverrides(female_count=female, male_count=male)
    if female < 1 or female + male < 2:
        with pytest.raises(StoryConfigurationError):
            resolve_story_input(document, overrides)
    else:
        resolved = resolve_story_input(document, overrides)
        assert resolved.plans[0].cast.total == female + male
        assert resolved.plans[0].cast.female_count == female


# These anchors are image properties, not verbatim output templates or word quotas.
VISUAL_FACTS = {
    "lifestyle-story": (
        "每日穿搭",
        "咖啡馆探访、城市漫步、周末旅行",
        "镜面自拍",
        "定时",
        "左右腿",
        "髋、膝、踝、脚",
        "生活痕迹",
        "二维码",
        "35-85mm",
    ),
    "intimate-liquid-editorial": (
        "站姿与弓步",
        "跪姿与蹲姿",
        "坐姿与椅子",
        "仰卧与桥式",
        "侧卧与蜷曲",
        "俯卧",
        "湿房、浴缸与水面",
        "家具、台面与建筑支撑",
        "双人编辑构图",
        "液体起点",
        "相机视线",
        "一至三件",
        "一至两件",
        "零至四件",
    ),
    "indoor-pure-desire-editorial": (
        "室内",
        "窗",
        "床",
        "沙发",
        "镜",
        "姿势",
        "光线",
    ),
    "piss": (
        "深蹲",
        "前倾",
        "蹲便器",
        "手机",
        "地砖",
        "陶瓷",
        "顶灯",
        "独立身体",
        "独立地面槽位",
        "25–34",
        "65–79",
    ),
    "confined-exhibition-fantasy": (
        "狭小空间",
        "出口开启",
        "身体折叠",
        "抬高骨盆",
        "对角伸展",
        "跪姿前倾",
        "侧卧卷曲",
        "俯卧抬臀",
        "坐姿折叠",
        "主表演者",
        "围观者",
    ),
    "intimate-lifestyle-portrait": (
        "高调",
        "东亚",
        "自然",
        "腮红",
        "蜜桃",
        "配饰",
        "猫眼",
        "毛孔",
        "绒毛",
        "全身",
        "镜头",
    ),
    "miniature-giant-encounter": (
        "微型",
        "巨人",
        "手腕至指尖",
        "比例",
        "支撑",
        "头顶到双脚完整可见",
        "地面",
        "灰粉",
        "芥末黄",
    ),
    "giant-country-fantasy": (
        "访客",
        "巨人",
        "尺度",
        "支撑",
        "接触",
        "衣物",
        "建筑",
    ),
    "furry-mythic-interactions": (
        "兽人",
        "人类",
        "两臂两腿",
        "左右大腿",
        "膝、小腿、脚",
        "尾巴",
        "承重",
        "35–65 毫米",
        "四分之三身",
        "全身",
    ),
    "dress": (
        "六个",
        "视图",
        "服装",
        "配饰",
        "身体",
        "材质",
        "版式",
    ),
    "post-layout": (
        "二十世纪中叶",
        "摄影蒙太奇",
        "拼贴海报",
        "主导照片",
        "较小摄影碎片",
        "标题",
        "票券",
        "半色调",
        "撕边",
    ),
    "film-post": (
        "院线",
        "片名",
        "宣传语",
        "演职员表",
        "署名",
        "档案",
        "排版",
    ),
    "jav-dvd-wrap": (
        "封底",
        "书脊",
        "封面",
        "43",
        "46",
        "47",
        "50",
        "条码",
        "13 位",
    ),
    "everyday-social-caricature": (
        "女性",
        "讽刺",
        "互动",
        "夸张",
        "道具",
        "社会",
        "面部",
        "剪影",
    ),
    "creative": (
        "两到五个",
        "熟悉物件",
        "身体",
        "物件之外",
        "2 列 3 行",
        "六个",
        "微缩",
        "明亮",
    ),
    "edo-warai-e": (
        "江户",
        "ukiyo-e",
        "nishiki-e",
        "平坦",
        "色块",
        "轮廓",
        "三",
        "衣袖",
        "obi",
        "屏风",
        "幽默",
    ),
    "ming-gongbi-mixi-tu": (
        "1573至1644",
        "江南",
        "熟绢",
        "游丝",
        "铁线",
        "界画",
        "三矾九染",
        "五至七个",
        "散点透视",
        "茶褐色氧化",
        "矿物色",
        "画布",
    ),
    "tang-guohua-figures": (
        "618至907",
        "绢本重彩",
        "铁线描",
        "矿物色平涂",
        "渲染",
        "披帛",
        "曲江",
        "马球场",
        "齐胸",
        "半臂",
        "胡服",
        "幂篱",
        "帷帽",
    ),
    "pose": (
        "六种",
        "姿势",
        "方位",
        "俯仰",
        "身体",
        "摄影",
        "关节",
        "视图",
    ),
    "threshold-emergence": (
        "门",
        "边界",
        "身体",
        "接触",
        "光",
        "材质",
    ),
    "magazine-cover": (
        "杂志",
        "刊头",
        "封面",
        "条码",
        "日期",
        "排版",
    ),
    "extreme-absurdity": (
        "荒诞",
        "身体",
        "道具",
        "接触",
        "因果",
        "承重",
    ),
    "near-future-intimacy-realism": (
        "近未来",
        "身体",
        "材料",
        "空间",
        "接触",
        "支撑",
    ),
    "precise-intimate-activity-geometry": (
        "骨盆",
        "支撑",
        "轴",
        "遮挡",
        "左",
        "右",
        "连续",
        "接触",
    ),
    "surreal-conceptual-portrait": (
        "实体装置",
        "面无表情",
        "一个主导隐喻",
        "负空间",
        "百分之四十至七十",
        "两种主导色相加一种点缀",
        "40-105",
        "承重路径",
        "亚克力",
    ),
    "demon-lord": (
        "核心恶魔",
        "王座",
        "二十五至七十九",
        "24-135mm",
        "低饱和",
        "翅膀",
        "盔甲",
        "前景",
        "中景",
        "背景",
    ),
    "angel": (
        "核心天使",
        "一对翅膀",
        "无翼人类",
        "二十五至七十九",
        "低饱和",
        "盔甲",
        "前景",
        "中景",
        "背景",
        "翅膀净空",
    ),
    "motion-blur-photography": (
        "35-50mm",
        "闪光",
        "景深",
        "左",
        "右",
        "载体",
        "拖迹",
        "1/15",
        "1/4",
        "相机",
        "腾空衣物",
        "手部释放",
    ),
}


@pytest.mark.parametrize("name", VISUAL_FACTS)
def test_recipe_preserves_visual_medium_cast_geometry_and_design_facts(name):
    document = load_story_document(RECIPES / f"{name}.yaml")
    prose = " ".join(story_contract(document).split())
    missing = [fact for fact in VISUAL_FACTS[name] if fact not in prose]
    assert not missing, f"{name}: {missing}"
    assert (
        resolve_story_input(
            document, run_configuration=audit_run_configuration(document)
        ).request.story
        == document.description
    )


@pytest.mark.parametrize(
    "name", ["edo-warai-e", "ming-gongbi-mixi-tu", "tang-guohua-figures"]
)
@pytest.mark.parametrize("level", tuple(ContentLevel))
def test_painting_medium_is_visual_not_a_verbatim_english_output_template(name, level):
    document = load_story_document(RECIPES / f"{name}.yaml")
    resolved = resolve_story_input(document, InputOverrides(content_level=level))
    frames = resolved.rules.text_for(StoryStage.FRAMES)
    assert resolved.request.output_language == "chinese"
    assert resolved.quality.frames.checks == ()
    for marker in ("空间", "人物", "轮廓"):
        assert marker in frames
    if name == "edo-warai-e":
        assert "nishiki-e" in frames
        assert "平面" in frames
    else:
        assert "绢" in frames
        assert "矿物" in frames
        assert "画布" in frames
    for retired in (
        "逐字保留这五句",
        "以下列四句原文开头",
        "空间位置句与当下动作句各须少于60词",
        "Full-canvas continuous-silk archival facsimile",
    ):
        assert retired not in frames


@pytest.mark.parametrize("name", ["angel", "demon-lord"])
def test_single_supernatural_principal_is_not_an_extra_cast_member(name):
    document = load_story_document(RECIPES / f"{name}.yaml")
    for female, male in ((1, 0), (0, 1), (1, 1), (3, 0), (2, 2)):
        resolved = resolve_story_input(
            document, InputOverrides(female_count=female, male_count=male)
        )
        assert resolved.plans[0].cast.total == female + male
        assert not resolved.plans[0].cast.fixed_roles
    prose = story_contract(document)
    assert "核心" in prose
    assert "计入" in prose
    if name == "angel":
        assert "无翼人类" in prose
        assert "一对" in prose
