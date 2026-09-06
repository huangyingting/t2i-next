from __future__ import annotations

import pytest

from t2i_prompt_pipeline.models import FrameMode
from t2i_prompt_pipeline.variation_plans import (
    build_frame_visual_plan,
    build_theme_variation_plan,
)


def test_theme_plan_varies_setting_and_character_axes() -> None:
    theme_ids = tuple(f"T{index:02d}" for index in range(1, 101))

    plan = build_theme_variation_plan(theme_ids, 3)

    assert list(plan) == list(theme_ids)
    assert plan == build_theme_variation_plan(theme_ids, 3)
    setting_signatures = {
        tuple(value["setting_variation"].values())
        for value in plan.values()
    }
    character_signatures = {
        (
            character["appearance_focus"],
            character["wardrobe_silhouette"],
            character["footwear"],
            character["accessory_strategy"],
        )
        for value in plan.values()
        for character in value["character_variations"].values()
    }
    assert len(setting_signatures) == len(theme_ids)
    assert len(character_signatures) == len(theme_ids) * 3


def test_theme_plan_is_stable_for_targeted_regeneration() -> None:
    complete = build_theme_variation_plan(("T01", "T02", "T03"), 3)
    targeted = build_theme_variation_plan(("T03",), 3)

    assert targeted["T03"] == complete["T03"]
    assert len(targeted["T03"]["character_variations"]) == 3


def test_theme_plan_uses_safe_single_character_color_and_material_directions() -> None:
    value = build_theme_variation_plan(("T01",), 1)["T01"]
    character = value["character_variations"]["T01-C01"]
    serialized = repr(value)

    assert character["wardrobe_color_role"] == "主色人物"
    assert character["wardrobe_material_focus"]
    assert value["setting_variation"]["palette_strategy"]
    assert "赤足" not in serialized
    assert "功能性腰带" not in serialized
    assert "天然皮革为主" not in serialized


def test_theme_plan_rejects_invalid_theme_id() -> None:
    with pytest.raises(ValueError, match="无效 Theme ID"):
        build_theme_variation_plan(("theme-1",), 1)


def test_frame_plan_rotates_camera_depth_and_light_axes() -> None:
    frame_ids = tuple(f"T01-F{index:02d}" for index in range(1, 6))
    plan = build_frame_visual_plan(
        "T01",
        frame_ids,
        ("左窗日光", "顶部暖灯"),
        3,
        FrameMode.VARIATIONS,
    )

    assert plan["T01-F01"]["focus"].startswith("空间关系")
    assert plan["T01-F02"]["focus"].startswith("人物互动")
    assert all(
        "独立落实 theme.story_plan 的同一目标"
        in value["story_requirement"]
        for value in plan.values()
    )
    assert len({value["lens_profile"] for value in plan.values()}) == 5
    assert len({value["shot_scale"] for value in plan.values()}) == 5
    assert len({value["camera_height"] for value in plan.values()}) == 4
    assert len({value["camera_direction"] for value in plan.values()}) == 5
    assert {value["depth_mode"] for value in plan.values()} == {
        "shallow",
        "moderate",
        "deep",
    }
    assert {
        value["light_source"] for value in plan.values()
    } == {"左窗日光", "顶部暖灯"}
    assert len({value["light_direction"] for value in plan.values()}) == 5
    assert all(
        value["light_direction"].startswith("沿所选光源实际方位照射")
        for value in plan.values()
    )
    assert all(
        "冷暖分区" not in value["color_treatment"]
        for value in plan.values()
    )


def test_frame_plan_is_stable_for_targeted_completion() -> None:
    sources = ("左窗日光", "顶部暖灯")
    complete = build_frame_visual_plan(
        "T03",
        tuple(f"T03-F{index:02d}" for index in range(1, 12)),
        sources,
        3,
        FrameMode.VARIATIONS,
    )
    targeted = build_frame_visual_plan(
        "T03",
        ("T03-F04", "T03-F11"),
        sources,
        3,
        FrameMode.VARIATIONS,
    )

    assert targeted["T03-F04"] == complete["T03-F04"]
    assert targeted["T03-F11"] == complete["T03-F11"]
    assert targeted["T03-F11"]["focus"].startswith("第 2 轮变化")


def test_frame_plan_recombines_axes_after_first_ten_slots() -> None:
    frame_ids = tuple(
        f"T01-F{index:02d}" if index < 100 else "T01-F100"
        for index in range(1, 101)
    )
    plan = build_frame_visual_plan(
        "T01",
        frame_ids,
        ("左窗日光",),
        3,
        FrameMode.VARIATIONS,
    )
    signatures = {
        (
            value["lens_profile"],
            value["shot_scale"],
            value["camera_height"],
            value["camera_direction"],
            value["depth_effect"],
            value["light_direction"],
            value["color_treatment"],
        )
        for value in plan.values()
    }

    assert len(signatures) == len(frame_ids)
    assert sum(
        value["lens_profile"] == "fisheye" for value in plan.values()
    ) == 10
    assert all(
        (value["camera_height"] == "overhead")
        == (value["camera_direction"] == "top_down")
        for value in plan.values()
    )


def test_frame_plan_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="至少需要一个可用光源"):
        build_frame_visual_plan(
            "T01", ("T01-F01",), (), 1, FrameMode.VARIATIONS
        )
    with pytest.raises(ValueError, match="不属于 Theme"):
        build_frame_visual_plan(
            "T01",
            ("T02-F01",),
            ("左窗日光",),
            1,
            FrameMode.VARIATIONS,
        )
    with pytest.raises(ValueError, match="至少需要一个人物"):
        build_frame_visual_plan(
            "T01",
            ("T01-F01",),
            ("左窗日光",),
            0,
            FrameMode.VARIATIONS,
        )


def test_sequential_plan_avoids_fisheye() -> None:
    frame_ids = tuple(f"T01-F{index:02d}" for index in range(1, 11))
    plan = build_frame_visual_plan(
        "T01",
        frame_ids,
        ("左窗日光",),
        3,
        FrameMode.SEQUENTIAL,
    )

    assert all(
        value["lens_profile"] != "fisheye" for value in plan.values()
    )
    assert all(
        "推进 theme.story_plan 的目标" in value["story_requirement"]
        for value in plan.values()
    )


def test_single_character_frame_plan_uses_single_subject_staging() -> None:
    value = build_frame_visual_plan(
        "T01",
        ("T01-F01",),
        ("左窗日光",),
        1,
        FrameMode.VARIATIONS,
    )["T01-F01"]

    assert "其余人物" not in value["group_topology"]
    assert "其余人物" not in value["depth_distribution"]
    assert value["body_dynamics"]
    assert "shadow_strategy" not in value
