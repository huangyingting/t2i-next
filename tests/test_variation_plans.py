from __future__ import annotations

import pytest

from t2i_prompt_pipeline.variation_plans import (
    build_frame_visual_plan,
    build_theme_variation_plan,
)


def test_theme_plan_varies_setting_and_character_axes() -> None:
    theme_ids = tuple(f"T{index:02d}" for index in range(1, 11))

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
    assert len(setting_signatures) >= 5
    assert len(character_signatures) >= len(theme_ids)


def test_theme_plan_is_stable_for_targeted_regeneration() -> None:
    complete = build_theme_variation_plan(("T01", "T02", "T03"), 3)
    targeted = build_theme_variation_plan(("T03",), 3)

    assert targeted["T03"] == complete["T03"]
    assert len(targeted["T03"]["character_variations"]) == 3


def test_theme_plan_rejects_invalid_theme_id() -> None:
    with pytest.raises(ValueError, match="无效 Theme ID"):
        build_theme_variation_plan(("theme-1",), 1)


def test_frame_plan_rotates_camera_depth_and_light_axes() -> None:
    frame_ids = tuple(f"T01-F{index:02d}" for index in range(1, 6))
    plan = build_frame_visual_plan(
        "T01",
        frame_ids,
        ("左窗日光", "顶部暖灯"),
    )

    assert plan["T01-F01"]["focus"].startswith("空间关系")
    assert plan["T01-F02"]["focus"].startswith("人物互动")
    assert len({value["shot_strategy"] for value in plan.values()}) == 5
    assert len({value["view_strategy"] for value in plan.values()}) == 5
    assert {value["depth_mode"] for value in plan.values()} == {
        "shallow",
        "moderate",
        "deep",
    }
    assert {
        value["light_source"] for value in plan.values()
    } == {"左窗日光", "顶部暖灯"}
    assert len({value["light_direction"] for value in plan.values()}) == 5


def test_frame_plan_is_stable_for_targeted_completion() -> None:
    sources = ("左窗日光", "顶部暖灯")
    complete = build_frame_visual_plan(
        "T03",
        tuple(f"T03-F{index:02d}" for index in range(1, 7)),
        sources,
    )
    targeted = build_frame_visual_plan(
        "T03",
        ("T03-F04", "T03-F06"),
        sources,
    )

    assert targeted["T03-F04"] == complete["T03-F04"]
    assert targeted["T03-F06"] == complete["T03-F06"]
    assert targeted["T03-F06"]["focus"].startswith("第 2 轮变化")


def test_frame_plan_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="至少需要一个可用光源"):
        build_frame_visual_plan("T01", ("T01-F01",), ())
    with pytest.raises(ValueError, match="不属于 Theme"):
        build_frame_visual_plan("T01", ("T02-F01",), ("左窗日光",))
