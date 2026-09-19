from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from t2i_story_pipeline.authoring_rules import resolve_story_rules
from t2i_story_pipeline.inputs import (
    InputOverrides,
    StoryDocument,
    load_story_document,
    resolve_story_input,
)
from t2i_story_pipeline.models import ContentLevel, NarrativeFrame, StoryStage
from t2i_story_pipeline.prompts import (
    frame_messages as compile_frame_messages,
)
from t2i_story_pipeline.prompts import (
    theme_messages as compile_theme_messages,
)
from tests.story_factories import (
    make_story_input,
    make_story_request,
    make_theme,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def theme_messages(request, **kwargs):
    return compile_theme_messages(
        make_story_input(request),
        **kwargs,
    )


def frame_messages(request, theme):
    return compile_frame_messages(
        make_story_input(request),
        theme,
        requested_frame_ids=[
            f"F{index:02d}" for index in range(1, request.frames_per_theme + 1)
        ],
        accepted_frames=[],
    )


def test_theme_prompt_requests_distinct_coherent_story_concepts() -> None:
    request = make_story_request(theme_count=100, frames_per_theme=6)
    messages = theme_messages(
        request,
        count=10,
        existing_themes=[],
    )
    prompt = messages[0].content
    payload = json.loads(messages[1].content)

    assert payload["story"] == request.story
    assert payload["theme_count"] == 10
    assert "content_level" not in payload
    assert payload["semantic_name"] is None
    assert "concise lowercase English snake_case name" in prompt
    assert "Follow the Story Description, selected authoring" in prompt
    assert "module parameters, and assigned slot facts" in prompt
    assert "requested counts and slots, runtime settings, or output format" in prompt
    assert "Never infer requirements from a filename or a known brief type" in prompt
    assert "Theme-stage facts from Frame-stage rendering detail" in prompt
    assert "unless the Story Description explicitly promotes that detail" in prompt
    assert "Do not impose narrative conflict, chronology, or a decision" in prompt
    assert "defines another organizing principle" in prompt
    assert "axes that the Story Description makes important" in prompt


def test_later_theme_batches_preserve_the_run_semantic_name() -> None:
    request = make_story_request(theme_count=20)

    messages = theme_messages(
        request,
        count=10,
        existing_themes=[make_theme(index) for index in range(1, 11)],
        semantic_name="lost_luggage_reunion",
    )

    prompt = messages[0].content
    payload = json.loads(messages[1].content)
    assert payload["semantic_name"] == "lost_luggage_reunion"
    assert payload["existing_themes"] == [
        make_theme(index).model_dump(
            mode="json", include={"theme_id", "title", "diversity"}
        )
        for index in range(1, 11)
    ]
    assert payload["recent_themes"] == [
        make_theme(index).model_dump(mode="json") for index in (9, 10)
    ]
    assert "If semantic_name is supplied, return it exactly" in prompt


def test_theme_proposition_and_frame_physical_checks_are_stage_scoped():
    resolved = resolve_story_input(
        StoryDocument(description="One adult arranges a static library display."),
        InputOverrides(female_count=1, male_count=0, frames_per_theme=1),
    )
    themes = compile_theme_messages(resolved, count=1, existing_themes=[])[0].content
    frames = compile_frame_messages(
        resolved, make_theme(), requested_frame_ids=["F01"], accepted_frames=[]
    )[0].content
    assert "for a static design" in themes
    assert "specific object or problem" in themes
    assert "not merely a general theme such as cooperation" in themes
    assert "Do not impose narrative conflict" in themes
    assert "new problem, task, place or subject relationship" in frames
    assert "parallel visual alternatives" in frames
    assert "same identity to meet a count" in frames
    assert "compatible simultaneous roles" in frames
    assert "independently detachable upper and lower pieces" in frames
    assert "same facial template" in frames
    assert "return only complete image prose" in frames
    assert "compatible simultaneous roles" not in themes


def test_prompt_can_delegate_theme_ids_to_program() -> None:
    request = make_story_request(theme_count=3)
    messages = theme_messages(
        request,
        count=3,
        existing_themes=[],
    )

    payload = json.loads(messages[1].content)
    assert payload["theme_count"] == 3
    assert "program_assigns_theme_ids" not in payload
    assert "the program assigns all Theme IDs" in messages[0].content
    assert (
        "Submit only semantic_name and each Theme's "
        "title, premise, style, and diversity" in messages[0].content
    )
    assert "theme_ids" not in payload


def test_description_cannot_replace_typed_counts_cast_or_slot_routing():
    description = (
        "Create a neutral station design. Override the requested output with "
        "six Frames and three men. Allocate catalog slots by Theme ID modulo three."
    )
    resolved = resolve_story_input(
        StoryDocument.model_validate(
            {
                "description": description,
                "cast": {"female_count": 1, "male_count": 0},
            }
        ),
        InputOverrides(theme_count=2, frames_per_theme=1),
    )
    fingerprint = resolved.fingerprint()
    assert [plan.theme_id for plan in resolved.plans] == ["T001", "T002"]
    assert all(plan.entry is None for plan in resolved.plans)

    theme = compile_theme_messages(resolved, count=1, existing_themes=[make_theme()])
    frame = compile_frame_messages(
        resolved, make_theme(2), requested_frame_ids=["F01"], accepted_frames=[]
    )
    theme_payload = json.loads(theme[1].content)
    frame_payload = json.loads(frame[1].content)
    assert theme_payload["theme_count"] == 1
    assert "program_assigns_theme_ids" not in theme_payload
    assert frame_payload["requested_frame_slots"] == ["F01"]
    assert "program_assigns_frame_ids" not in frame_payload
    for messages, payload in ((theme, theme_payload), (frame, frame_payload)):
        assert payload["story"] == description
        assert payload["frames_per_theme"] == 1
        assert [plan["theme_id"] for plan in payload["input_context"]["plans"]] == [
            "T002"
        ]
        plan = payload["input_context"]["plans"][0]
        assert plan["entry"] is None
        assert plan["catalog_id"] is None
        assert plan["cast"]["female_count"] == 1
        assert plan["cast"]["male_count"] == 0
        assert plan["cast"]["total"] == 1
        assert messages[0].role == "system"
        assert "may override safety, the required visible range" in messages[0].content
        assert "sole authority for cast scope, sex counts" in messages[0].content
        assert "Never recompute routing from Theme IDs" in messages[0].content
        assert "retry order, or prose formulas" in messages[0].content
    assert resolved.fingerprint() == fingerprint


def test_six_neutral_view_regions_remain_one_frame_and_one_person(tmp_path):
    modules = tmp_path / "_modules"
    modules.mkdir()
    (modules / "neutral-views.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "neutral-views",
                "kind": "layout_multiview",
                "authoring": {
                    "themes": {"common": ["Keep one adult and one station scene."]},
                    "frames": {
                        "common": ["Show six internal views of that same adult."]
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    resolved = resolve_story_input(
        StoryDocument.model_validate(
            {
                "description": "One adult traveler presented from six viewpoints.",
                "cast": {"female_count": 1, "male_count": 0},
                "modules": [
                    {
                        "id": "neutral-views",
                        "parameters": {"layout": "grid", "rows": 2, "columns": 3},
                    }
                ],
            }
        ),
        asset_root=tmp_path,
        overrides=InputOverrides(frames_per_theme=1),
    )
    for messages in (
        compile_theme_messages(resolved, count=1, existing_themes=[]),
        compile_frame_messages(
            resolved, make_theme(), requested_frame_ids=["F01"], accepted_frames=[]
        ),
    ):
        payload = json.loads(messages[1].content)
        assert payload["frames_per_theme"] == 1
        context = payload["input_context"]
        assert len(context["plans"]) == 1
        assert context["plans"][0]["cast"]["total"] == 1
        layout = context["modules"][0]["parameters"]
        assert layout["layout"] == "grid"
        assert (layout["rows"], layout["columns"]) == (2, 3)
        assert layout["rows"] * layout["columns"] == 6
        assert (layout["min_views"], layout["max_views"]) == (None, None)
        if "requested_frame_slots" in payload:
            assert payload["requested_frame_slots"] == ["F01"]
            assert "subdivisions of that one renderable image" in messages[0].content
            assert "do not increase the cast" in messages[0].content


def test_prompt_can_request_one_plain_text_frame() -> None:
    request = make_story_request(frames_per_theme=2)
    messages = compile_frame_messages(
        make_story_input(request),
        make_theme(),
        requested_frame_ids=["F02"],
        accepted_frames=[NarrativeFrame(frame_id="F01", prose="先前完成的画面。")],
    )

    payload = json.loads(messages[1].content)
    assert payload["requested_frame_slots"] == ["F02"]
    assert "program_assigns_frame_ids" not in payload
    assert "The program assigns all Frame IDs" in messages[0].content
    assert "Output no JSON, IDs," in messages[0].content
    assert payload["accepted_frames"] == [
        {"frame_id": "F01", "prose": "先前完成的画面。"}
    ]
    assert "frame_ids" not in payload


@pytest.mark.parametrize(
    ("female_count", "male_count", "total"),
    [(2, 1, 3), (2, 0, 2), (0, 2, 2), (0, None, None), (None, 0, None)],
)
def test_prompts_compile_exact_cast_counts_only_in_input_context(
    female_count, male_count, total
) -> None:
    request = make_story_request(female_count=female_count, male_count=male_count)

    for messages in (
        theme_messages(
            request,
            count=1,
            existing_themes=[],
        ),
        frame_messages(request, make_theme()),
    ):
        prompt = messages[0].content
        payload = json.loads(messages[1].content)

        cast = payload["input_context"]["plans"][0]["cast"]
        assert cast == {
            "female_count": female_count,
            "male_count": male_count,
            "total": total,
            "principal_total": total,
            "total_min": total if total is not None else 1,
            "total_max": total if total is not None else 8,
            "scope": "all_people",
            "fixed_roles": [],
            "background_counts": [],
            "min_female": 0,
            "min_male": 0,
        }
        assert (
            not {"cast_constraints", "female_count", "male_count", "cast"}
            & payload.keys()
        )
        assert "Follow each input_context plan's cast facts exactly" in prompt
        assert "female_count and male_count apply only to the named scope" in prompt
        assert "fixed role is one additional distinct adult" in prompt
        assert "must not exceed eight principal people" in prompt
        assert (
            "Without background_counts there are no additional background people"
            in prompt
        )


def test_prompts_preserve_unspecified_cast_from_story() -> None:
    request = make_story_request()

    for messages in (
        theme_messages(
            request,
            count=1,
            existing_themes=[],
        ),
        frame_messages(request, make_theme()),
    ):
        payload = json.loads(messages[1].content)
        cast = payload["input_context"]["plans"][0]["cast"]
        assert cast["female_count"] is None
        assert cast["male_count"] is None
        assert cast["total"] is None
        assert "cast_constraints" not in payload
        assert (
            "Unspecified sex counts remain model choices, not zero"
            in messages[0].content
        )


def test_scoped_cast_context_counts_the_giant_as_one_additional_fixed_role():
    resolved = resolve_story_input(
        StoryDocument.model_validate(
            {
                "description": "Adult miniature travelers meet one giant adult guide.",
                "cast": {
                    "female_count": 2,
                    "male_count": 0,
                    "scope": "miniatures",
                    "fixed_roles": [{"id": "giant", "sex": "theme_choice"}],
                },
            }
        ),
        InputOverrides(theme_count=2, frames_per_theme=1),
    )
    for messages, expected_ids in (
        (
            compile_theme_messages(resolved, count=2, existing_themes=[]),
            ["T001", "T002"],
        ),
        (
            compile_frame_messages(
                resolved, make_theme(2), requested_frame_ids=["F01"], accepted_frames=[]
            ),
            ["T002"],
        ),
    ):
        payload = json.loads(messages[1].content)
        assert (
            not {"cast_constraints", "female_count", "male_count", "cast"}
            & payload.keys()
        )
        assert [
            plan["theme_id"] for plan in payload["input_context"]["plans"]
        ] == expected_ids
        for plan in payload["input_context"]["plans"]:
            assert plan["cast"] == {
                "scope": "miniatures",
                "female_count": 2,
                "male_count": 0,
                "fixed_roles": [{"id": "giant", "sex": "theme_choice"}],
                "background_counts": [],
                "principal_total": 3,
                "total": 3,
                "total_min": 3,
                "total_max": 3,
                "min_female": 0,
                "min_male": 0,
            }
    assert resolved.request.female_count == 2
    assert resolved.request.male_count == 0


@pytest.mark.parametrize("female_count,include_host", [(2, False), (7, True)])
def test_background_bands_do_not_become_a_global_eight_person_cap(
    female_count, include_host
):
    bands = [
        {"min": 0, "max": 0},
        {"min": 2, "max": 5},
        {"min": 6, "max": 15},
        {"min": 16, "max": 30},
    ]
    roles = [{"id": "host", "sex": "theme_choice"}] if include_host else []
    principal_total = female_count + len(roles)
    resolved = resolve_story_input(
        StoryDocument.model_validate(
            {
                "description": "Adult travelers and background adults share a station.",
                "cast": {
                    "scope": "principal_adults",
                    "female_count": female_count,
                    "male_count": 0,
                    "fixed_roles": roles,
                    "background_counts": bands,
                },
            }
        ),
        InputOverrides(frames_per_theme=1),
    )
    for messages in (
        compile_theme_messages(resolved, count=1, existing_themes=[]),
        compile_frame_messages(
            resolved, make_theme(), requested_frame_ids=["F01"], accepted_frames=[]
        ),
    ):
        payload = json.loads(messages[1].content)
        cast = payload["input_context"]["plans"][0]["cast"]
        assert cast["scope"] == "principal_adults"
        assert cast["female_count"] == female_count
        assert cast["male_count"] == 0
        assert cast["fixed_roles"] == roles
        assert cast["background_counts"] == bands
        assert cast["principal_total"] == principal_total
        assert cast["total"] is None
        assert cast["total_min"] == principal_total
        assert cast["total_max"] == principal_total + 30
        assert not {"cast_constraints", "female_count", "male_count"} & payload.keys()
        assert "preserve gaps between bands" in messages[0].content
        if "theme" in payload:
            assert (
                "background adults at the detail their visibility supports"
                in messages[0].content
            )
            assert "preserving their population bounds and adult status" in (
                messages[0].content
            )
        else:
            assert "establish its adult population tier" in messages[0].content
            assert "preserve that choice within the Theme" in messages[0].content


def test_catalog_cast_context_keeps_each_themes_total_and_sex_minima(tmp_path):
    catalogs = tmp_path / "_catalogs"
    catalogs.mkdir()
    (catalogs / "station-groups.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "station-groups",
                "slots": ["solo", "group"],
                "entries": [
                    {"id": "solo", "cast": {"total": 1, "min_female": 1}},
                    {
                        "id": "group",
                        "cast": {"total": 3, "min_female": 1, "min_male": 1},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    resolved = resolve_story_input(
        StoryDocument.model_validate(
            {
                "description": "Adult travelers wait at a station.",
                "allocation": {"type": "fixed_slots", "catalog": "station-groups"},
            }
        ),
        asset_root=tmp_path,
        overrides=InputOverrides(theme_count=2, frames_per_theme=1),
    )
    expected = [
        {
            "scope": "all_people",
            "female_count": None,
            "male_count": None,
            "fixed_roles": [],
            "background_counts": [],
            "principal_total": total,
            "total": total,
            "total_min": total,
            "total_max": total,
            "min_female": 1,
            "min_male": min_male,
        }
        for total, min_male in [(1, 0), (3, 1)]
    ]
    for messages, expected_casts in (
        (compile_theme_messages(resolved, count=2, existing_themes=[]), expected),
        (
            compile_theme_messages(resolved, count=1, existing_themes=[make_theme()]),
            expected[1:],
        ),
        (
            compile_frame_messages(
                resolved, make_theme(2), requested_frame_ids=["F01"], accepted_frames=[]
            ),
            expected[1:],
        ),
    ):
        payload = json.loads(messages[1].content)
        assert (
            not {"cast_constraints", "female_count", "male_count", "cast"}
            & payload.keys()
        )
        assert [
            plan["cast"] for plan in payload["input_context"]["plans"]
        ] == expected_casts
    assert resolved.request.female_count is None
    assert resolved.request.male_count is None


def test_prompts_default_unspecified_people_and_setting_to_china() -> None:
    request = make_story_request()

    for stage, messages in (
        (
            "Theme 的 premise",
            theme_messages(
                request,
                count=1,
                existing_themes=[],
            ),
        ),
        ("Frame", frame_messages(request, make_theme())),
    ):
        prompt = messages[0].content

        assert "未指定时，每个人物分别默认为中国籍" in prompt
        assert "不得根据地点、姓名、语言、肤色或外貌推断国籍" in prompt
        assert f"必须在每个 {stage} 中明确写出人物国籍" in prompt
        assert "否则场景国家默认为中国" in prompt
        assert f"必须在每个 {stage} 中明确写出场景所在国家" in prompt


def test_frame_prompt_prioritizes_coherent_standalone_prose() -> None:
    request = make_story_request(frames_per_theme=6)
    messages = frame_messages(request, make_theme())
    prompt = messages[0].content
    payload = json.loads(messages[1].content)

    assert payload["story"] == request.story
    assert payload["theme"]["theme_id"] == "T001"
    assert payload["requested_frame_slots"] == [
        "F01",
        "F02",
        "F03",
        "F04",
        "F05",
        "F06",
    ]
    assert "Each Narrative Frame is one standalone renderable image" in prompt
    assert "Fully redescribe each visible principal person's adult identity" in prompt
    assert (
        "one coherent body configuration appropriate to the physical setting" in prompt
    )
    assert "Assign every visible limb a consistent contact or force role" in prompt
    assert "Do not describe successive repositioning as a narrative" in prompt
    assert "Follow the Story Description, selected authoring" in prompt
    assert "requested counts and slots, runtime settings, or output format" in prompt
    assert "Grounded scenes require credible support" in prompt
    assert "floating or zero-gravity scenes require coherent free-flight" in prompt
    assert "exposure may visibly record motion through blur or light trails" in prompt
    assert "those traces are not additional bodies or chronological Frames" in prompt
    assert "subdivisions of that one renderable image" in prompt
    assert "do not spread one required image across Narrative Frames" in prompt
    assert "Repeated depictions of one named person inside a single image" in prompt
    assert "Preserve the requested medium" in prompt
    assert "Do not default to cinematic photography" in prompt
    assert "viewpoint and illumination in terms appropriate to that medium" in prompt
    assert "visible state explicitly required by the Story Description" in prompt
    assert "Resolve conditional instructions only from the current request" in prompt
    assert "never borrow a branch assigned to another alternative" in prompt
    assert "Explicit Story Description creative constraints take priority" in prompt
    assert "may override safety, the required visible range and its limits" in prompt
    assert "input_context plans govern assignments and slot identity" in prompt
    assert "rope art" not in prompt
    assert "do not mix in untranslated foreign prose" in prompt.lower()
    assert "parallel visual alternatives" in prompt
    assert "share stable Theme facts" in prompt
    assert "All alternatives depict an equivalent point" in prompt
    assert "variation must not imply elapsed time" in prompt
    assert "Never refer to another Frame or use backward-pointing" in prompt
    assert "Follow the requested writing targets when supplied" in prompt
    assert "without a fixed word quota or padding" in prompt
    assert "follow exactly six sections" not in prompt
    assert "must begin exactly with" not in prompt
    assert "penultimate sentence" not in prompt
    assert "exact quality gate" not in prompt


def test_prompt_compiler_does_not_encode_story_input_archetypes() -> None:
    request = make_story_request()
    prompts = (
        theme_messages(
            request,
            count=1,
            existing_themes=[],
        )[0].content,
        frame_messages(request, make_theme())[0].content,
    )

    archetype_phrases = (
        "campaign",
        "design board",
        "multi-view",
        "six-region",
        "Region 1",
        "miniature-world",
        "thumbnail scale",
        "visual-stunt",
        "rope paths",
    )
    assert all(
        phrase not in prompt for prompt in prompts for phrase in archetype_phrases
    )


def test_english_frame_prompt_requires_english_only_output() -> None:
    request = make_story_request(output_language="english")

    prompt = frame_messages(request, make_theme())[0].content

    assert "Write every natural-language output field" in prompt
    assert "in precise, fluent English" in prompt
    assert "Preserve only literal foreign text explicitly required" in prompt


def test_chinese_prompts_allow_story_required_english_labels_and_copy() -> None:
    request = make_story_request(output_language="chinese")

    theme_prompt = theme_messages(
        request,
        count=1,
        existing_themes=[],
    )[0].content
    frame_prompt = frame_messages(request, make_theme())[0].content

    assert "in precise, fluent Chinese" in theme_prompt
    assert "in precise, fluent Chinese" in frame_prompt
    assert "Preserve only literal foreign text explicitly required" in theme_prompt
    assert "Preserve only literal foreign text explicitly required" in frame_prompt


@pytest.mark.parametrize("output_language", ("chinese", "english"))
def test_system_instructions_keep_shared_rule_language_across_output_languages(
    output_language: str,
) -> None:
    request = make_story_request(output_language=output_language)

    prompts = (
        theme_messages(
            request,
            count=1,
            existing_themes=[],
        )[0].content,
        frame_messages(request, make_theme())[0].content,
    )

    for prompt in prompts:
        assert (
            "may override safety, the required visible range and its limits" in prompt
        )
        assert (
            "requested counts and slots, runtime settings, or output format" in prompt
        )
        assert "尺度下限是静止画面可见的形体表达" in prompt


@pytest.mark.parametrize(
    ("level", "required", "excluded"),
    (
        (
            ContentLevel.AESTHETIC,
            "尺度下限是静止画面可见的形体表达",
            (
                "当前画面直接呈现裸露、挑逗和非露骨亲密互动",
                "当前画面直接、清晰地呈现角色之间的明确性行为",
            ),
        ),
        (
            ContentLevel.EROTIC,
            "当前画面直接呈现裸露、挑逗和非露骨亲密互动",
            (
                "尺度下限是静止画面可见的形体表达",
                "当前画面直接、清晰地呈现角色之间的明确性行为",
            ),
        ),
        (
            ContentLevel.HARDCORE,
            "当前画面直接、清晰地呈现角色之间的明确性行为",
            (
                "尺度下限是静止画面可见的形体表达",
                "当前画面直接呈现裸露、挑逗和非露骨亲密互动",
            ),
        ),
    ),
)
def test_prompts_compile_only_selected_content_level(
    level: ContentLevel,
    required: str,
    excluded: tuple[str, str],
) -> None:
    request = make_story_request(content_level=level)

    for messages in (
        theme_messages(
            request,
            count=1,
            existing_themes=[],
        ),
        frame_messages(request, make_theme()),
    ):
        prompt = messages[0].content
        assert "content_level" not in json.loads(messages[1].content)
        assert required in prompt
        assert all(item not in prompt for item in excluded)
        assert "Do not write configuration metadata, internal IDs" in prompt
        assert all(candidate.value not in prompt for candidate in ContentLevel)
        assert "本次使用" not in prompt
        assert "本级" not in prompt
        assert "Every depicted person must be an unmistakable adult" in prompt
        assert (
            "All participants must be alert, consenting, responsive, and able to stop"
            in prompt
        )
        assert "不要把内容等级名称、英文名或合规说明写进生成内容" not in prompt
        grade_boundary = {
            ContentLevel.AESTHETIC: "不得描写自慰、口交、插入或明确性行为",
            ContentLevel.EROTIC: "不出现性器官特写、插入或口部性行为、自慰",
            ContentLevel.HARDCORE: "所有角色必须外观明确为二十一岁以上成年人",
        }
        assert grade_boundary[level] in prompt


@pytest.mark.parametrize("level", tuple(ContentLevel))
def test_avantgarde_shared_refinements_preserve_base_grade_and_stage_duties(level):
    document = load_story_document(REPOSITORY_ROOT / "recipes" / "avantgarde.yaml")
    refinements = document.authoring.level_refinements
    assert refinements[ContentLevel.HARDCORE].shared
    assert all(
        anchor in " ".join(refinements[ContentLevel.HARDCORE].shared)
        for anchor in ("发型", "服装", "配饰")
    )
    resolved = resolve_story_input(
        document,
        InputOverrides(
            content_level=level, frames_per_theme=1, female_count=1, male_count=0
        ),
    )
    base = resolve_story_rules(resolved.request)
    for stage, messages in (
        (
            StoryStage.THEMES,
            compile_theme_messages(resolved, count=1, existing_themes=[]),
        ),
        (
            StoryStage.FRAMES,
            compile_frame_messages(
                resolved, make_theme(), requested_frame_ids=["F01"], accepted_frames=[]
            ),
        ),
    ):
        compiled = "\n".join(message.content for message in messages)
        assert "content_level" not in json.loads(messages[1].content)
        assert resolved.request.content_level == level
        selected = document.authoring.selected(stage, level)
        assert all(rule in compiled for rule in getattr(base, stage.value))
        assert all(rule in compiled for rule in selected)
        selected_shared = refinements[level].shared if level in refinements else ()
        assert all(compiled.count(rule) == 1 for rule in selected_shared)
        for other_level in ContentLevel:
            if other_level != level:
                assert all(
                    rule not in compiled
                    for rule in document.authoring.selected(stage, other_level)
                    if rule not in selected
                )
        other_stage = (
            StoryStage.FRAMES if stage == StoryStage.THEMES else StoryStage.THEMES
        )
        other_duties = set(document.authoring.selected(other_stage, level)) - set(
            selected
        )
        assert other_duties
        assert all(rule not in compiled for rule in other_duties)
        if stage == StoryStage.THEMES:
            for prefix, count in (
                ("发型灵感：", 65),
                ("服装灵感：", 156),
                ("配饰灵感：", 92),
            ):
                assert sum(rule.startswith(prefix) for rule in selected) == count


@pytest.mark.parametrize(
    ("level", "required_contract"),
    (
        (
            ContentLevel.AESTHETIC,
            "主导照片必须明确保持非露骨",
        ),
        (
            ContentLevel.EROTIC,
            ("主导照片中呈现非露骨的亲密互动"),
        ),
        (
            ContentLevel.HARDCORE,
            ("直接露骨的互动置于主导照片中"),
        ),
    ),
)
def test_post_layout_prompt_compiles_dominant_hero_content_contract(
    level: ContentLevel,
    required_contract: str,
) -> None:
    document = load_story_document(REPOSITORY_ROOT / "recipes" / "post-layout.yaml")
    resolved = resolve_story_input(
        document,
        InputOverrides(
            content_level=level, frames_per_theme=1, female_count=1, male_count=1
        ),
    )
    messages = compile_frame_messages(
        resolved, make_theme(), requested_frame_ids=["F01"], accepted_frames=[]
    )
    compiled = " ".join(
        "\n".join(message.content for message in messages).replace("\\n", " ").split()
    )
    payload = json.loads(messages[1].content)

    assert "content_level" not in payload
    assert resolved.request.content_level == level
    assert required_contract in compiled
    selected = document.authoring.selected(StoryStage.FRAMES, level)
    for other in document.authoring.level_refinements:
        if other != level:
            assert all(
                rule not in compiled
                for rule in document.authoring.selected(StoryStage.FRAMES, other)
                if rule not in selected
            )
    assert "内容级别可见性锚点" in compiled
    assert "不能替代所选级别的可见内容" in compiled


def test_prompts_express_era_consistency_holistically() -> None:
    request = make_story_request()

    for messages in (
        theme_messages(
            request,
            count=1,
            existing_themes=[],
        ),
        frame_messages(request, make_theme()),
    ):
        prompt = messages[0].content
        assert "Architecture, furnishings, objects, materials, clothing, hair" in prompt
        assert "titles, etiquette, season, and language" in prompt
        assert "When historical facts are uncertain" in prompt
        assert "temporal dislocation" in prompt
